"""Services d'envoi et campagnes de rappels."""

import logging
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.core.models import Notification
from apps.students.models import FeeSchedule, MonthlyPayment, Student, StudentStatus

from . import templates_sms
from .models import ReminderRun
from .sms import normalize_phone, send_sms

logger = logging.getLogger(__name__)


def dispatch_sms(school, *, recipient, message, template, payload=None):
    """Envoie un SMS et consigne l'envoi dans la boîte d'envoi.

    La trace est écrite **dans tous les cas**, succès comme échec : sans elle,
    impossible de répondre à un parent qui affirme n'avoir jamais été relancé.
    """
    notification = Notification.objects.create(
        school=school,
        recipient=normalize_phone(recipient),
        channel=Notification.Channel.SMS,
        template=template,
        payload=payload or {},
    )

    result = send_sms(recipient, message)

    notification.status = result.status
    notification.error = result.error or ""
    notification.sent_at = timezone.now() if result.success else None
    notification.payload = {
        **notification.payload,
        "message_id": result.message_id,
        "simulated": result.simulated,
        "segments": result.segments,
    }
    notification.save(update_fields=["status", "error", "sent_at", "payload"])
    return result


def _contactable(student):
    """Un élève relançable : actif, avec un numéro de parent exploitable."""
    phone = student.parent_phone or (student.family.phone if student.family_id else "")
    return phone.strip() if phone else None


def _parent_name(student):
    return (
        student.parent_name
        or (student.family.primary_contact if student.family_id else "")
        or "Madame, Monsieur"
    )


def arrears_by_student(year, as_of=None):
    """Arriérés de mensualité par élève, sur les mois échus.

    Même calcul que l'endpoint `/monthly-payments/arrears/` — factorisé ici pour
    que la relance porte exactement sur ce que le comptable voit à l'écran.
    """
    as_of = as_of or date.today()
    elapsed = [p for p in year.tuition_month_ends if p <= as_of]
    if not elapsed:
        return []

    schedules = {s.classroom_id: s.monthly_tuition for s in FeeSchedule.objects.filter(year=year)}
    from django.db.models import Sum

    paid = {
        row["student"]: row["total"] or 0
        for row in MonthlyPayment.objects.filter(year=year, period__in=elapsed)
        .values("student")
        .annotate(total=Sum("tuition"))
    }

    results = []
    for student in Student.objects.filter(status=StudentStatus.ACTIVE).select_related(
        "classroom", "family"
    ):
        tuition = schedules.get(student.classroom_id)
        if not tuition:
            continue
        due = tuition * len(elapsed)
        settled = paid.get(student.id, 0)
        if settled < due:
            results.append(
                {
                    "student": student,
                    "due": due,
                    "paid": settled,
                    "arrears": due - settled,
                    "months": len(elapsed),
                }
            )
    return sorted(results, key=lambda row: row["arrears"], reverse=True)


@transaction.atomic
def run_arrears_reminders(school, year, *, triggered_by="", dry_run=False, min_amount=0):
    """Relance par SMS les parents d'élèves en retard.

    Idempotent à la journée : une campagne déjà passée le même jour pour la même
    période n'est pas rejouée. Un ordonnanceur relancé, ou un administrateur qui
    reclique, ne double donc pas les envois — ni la facture.
    """
    period = year.tuition_month_ends[0]
    today = timezone.localdate()

    existing = ReminderRun.objects.filter(
        kind=ReminderRun.Kind.ARREARS, period=period, run_date=today
    ).first()
    if existing and not dry_run:
        logger.info("Campagne d'arriérés déjà exécutée aujourd'hui — ignorée.")
        return {"already_run": True, "run": existing, "sent": 0, "failed": 0, "skipped": 0}

    rows = [row for row in arrears_by_student(year) if row["arrears"] >= min_amount]

    sent = failed = skipped = 0
    simulated = False
    preview = []

    for row in rows:
        student = row["student"]
        phone = _contactable(student)
        if not phone:
            skipped += 1
            continue

        message = templates_sms.arrears_notice(
            parent_name=_parent_name(student),
            student_name=student.full_name,
            amount=row["arrears"],
            school_name=school.name,
            months=row["months"],
        )
        preview.append({"phone": phone, "student": student.full_name, "message": message})

        if dry_run:
            continue

        result = dispatch_sms(
            school,
            recipient=phone,
            message=message,
            template="arrears_notice",
            payload={"student": student.id, "arrears": row["arrears"]},
        )
        simulated = simulated or result.simulated
        if result.success:
            sent += 1
        else:
            failed += 1

    if dry_run:
        return {
            "dry_run": True,
            "would_send": len(preview),
            "skipped": skipped,
            "preview": preview[:20],
        }

    run = ReminderRun.objects.create(
        school=school,
        kind=ReminderRun.Kind.ARREARS,
        period=period,
        run_date=today,
        sent=sent,
        failed=failed,
        skipped=skipped,
        simulated=simulated,
        triggered_by=triggered_by,
    )
    return {"run": run, "sent": sent, "failed": failed, "skipped": skipped, "simulated": simulated}


def send_payment_receipt(school, payment):
    """Accusé d'encaissement au parent.

    Appelé après enregistrement d'un règlement. L'échec d'envoi n'invalide jamais
    l'encaissement : le reçu est un service rendu, pas une condition de validité.
    """
    student = payment.student
    phone = _contactable(student)
    if not phone:
        return None

    message = templates_sms.payment_receipt(
        parent_name=_parent_name(student),
        student_name=student.full_name,
        amount=payment.total,
        period=payment.period,
        school_name=school.name,
        reference=payment.reference or f"MP{payment.id}",
    )
    return dispatch_sms(
        school,
        recipient=phone,
        message=message,
        template="payment_receipt",
        payload={"student": student.id, "payment": payment.id, "amount": payment.total},
    )


def send_otp(school, phone, code):
    """Code de connexion au portail parent."""
    return dispatch_sms(
        school,
        recipient=phone,
        message=templates_sms.otp_code(code=code, school_name=school.name),
        template="otp_code",
        # Le code n'est jamais recopié dans la charge utile : la boîte d'envoi est
        # consultable par l'administration, qui n'a pas à pouvoir se connecter à la
        # place d'un parent.
        payload={"purpose": "parent_login"},
    )
