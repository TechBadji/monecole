"""Cycle de vie d'une transaction de paiement."""

import logging
import uuid

from django.db import transaction as db_transaction
from django.utils import timezone

from apps.core.periods import end_of_month
from apps.students.models import Enrollment, MonthlyPayment

from .models import PaymentTransaction

logger = logging.getLogger(__name__)


def build_reference(school, student):
    """Référence courte, unique et lisible : « ME-<école>-<élève>-<aléa> »."""
    return f"ME-{school.id}-{student.id}-{uuid.uuid4().hex[:10].upper()}"


@db_transaction.atomic
def open_transaction(*, school, student, year, amount, method, purpose, period=None,
                     received_by=""):
    """Ouvre une transaction en attente."""
    if amount <= 0:
        raise ValueError("Le montant doit être strictement positif.")

    return PaymentTransaction.objects.create(
        school=school,
        student=student,
        year=year,
        purpose=purpose,
        period=end_of_month(period) if period else None,
        amount=amount,
        method=method,
        reference=build_reference(school, student),
        received_by=received_by,
    )


@db_transaction.atomic
def confirm_transaction(txn, *, provider_payment_id="", payload=None, notify=True):
    """Confirme une transaction et produit l'écriture comptable correspondante.

    Idempotent : rejouer la confirmation d'une transaction déjà confirmée ne crée
    pas de seconde écriture. Wave peut légitimement réémettre un webhook, et un
    double encaissement serait invisible au bilan tout en étant faux.
    """
    txn = PaymentTransaction.all_objects.select_for_update().get(pk=txn.pk)

    if txn.status == PaymentTransaction.Status.SUCCEEDED:
        logger.info("Transaction %s déjà confirmée — ignorée.", txn.reference)
        return txn, False

    txn.status = PaymentTransaction.Status.SUCCEEDED
    txn.confirmed_at = timezone.now()
    txn.provider_payment_id = provider_payment_id or txn.provider_payment_id
    if payload:
        txn.provider_payload = payload

    if txn.purpose == PaymentTransaction.Purpose.REGISTRATION:
        _apply_registration(txn)
    else:
        txn.monthly_payment = _apply_tuition(txn)

    txn.save()

    if notify:
        _notify(txn)
    return txn, True


def _apply_tuition(txn):
    """Impute le règlement sur la mensualité de la période visée.

    `update_or_create` sur (élève, période) : le modèle impose déjà une seule
    écriture par élève et par mois. Un règlement complémentaire s'ajoute au montant
    déjà encaissé plutôt que de l'écraser — sinon un paiement en deux fois ferait
    disparaître le premier versement.
    """
    period = txn.period or txn.year.tuition_month_ends[0]
    payment = MonthlyPayment.all_objects.filter(student=txn.student, period=period).first()

    if payment is None:
        return MonthlyPayment.objects.create(
            school=txn.school,
            student=txn.student,
            year=txn.year,
            period=period,
            tuition=txn.amount,
            payment_date=timezone.localdate(),
            method=_ledger_method(txn.method),
            reference=txn.reference,
            received_by=txn.received_by,
        )

    payment.tuition += txn.amount
    payment.payment_date = timezone.localdate()
    payment.method = _ledger_method(txn.method)
    payment.reference = txn.reference
    payment.save(update_fields=["tuition", "payment_date", "method", "reference"])
    return payment


def _apply_registration(txn):
    enrollment = Enrollment.objects.filter(student=txn.student, year=txn.year).first()
    if enrollment is None:
        enrollment = Enrollment.objects.create(
            school=txn.school,
            student=txn.student,
            year=txn.year,
            classroom=txn.student.classroom,
        )
    enrollment.registration_amount += txn.amount
    enrollment.registration_paid = True
    enrollment.paid_at = timezone.localdate()
    enrollment.save(update_fields=["registration_amount", "registration_paid", "paid_at"])
    return enrollment


def _ledger_method(method):
    """Correspondance vers les moyens de paiement de l'écriture comptable."""
    mapping = {
        PaymentTransaction.Method.WAVE: MonthlyPayment.Method.MOBILE_MONEY,
        PaymentTransaction.Method.ORANGE_MONEY: MonthlyPayment.Method.MOBILE_MONEY,
        PaymentTransaction.Method.CASH: MonthlyPayment.Method.CASH,
        PaymentTransaction.Method.TRANSFER: MonthlyPayment.Method.TRANSFER,
        PaymentTransaction.Method.CHECK: MonthlyPayment.Method.CHECK,
    }
    return mapping.get(method, MonthlyPayment.Method.CASH)


def _notify(txn):
    """Accusé de réception au parent. Un échec d'envoi n'annule pas le paiement."""
    if txn.monthly_payment is None:
        return
    try:
        from apps.notifications.services import send_payment_receipt

        send_payment_receipt(txn.school, txn.monthly_payment)
    except Exception:  # noqa: BLE001 — le reçu ne doit jamais faire échouer l'encaissement
        logger.exception("Envoi du reçu impossible pour %s", txn.reference)


@db_transaction.atomic
def fail_transaction(txn, *, status=None, error=""):
    txn = PaymentTransaction.all_objects.select_for_update().get(pk=txn.pk)
    if txn.status == PaymentTransaction.Status.SUCCEEDED:
        # Un paiement confirmé ne redevient jamais un échec : ce serait ouvrir la
        # porte à l'annulation silencieuse d'une écriture comptable.
        logger.warning("Refus de faire échouer %s, déjà confirmée.", txn.reference)
        return txn
    txn.status = status or PaymentTransaction.Status.FAILED
    txn.error = error
    txn.save(update_fields=["status", "error"])
    return txn
