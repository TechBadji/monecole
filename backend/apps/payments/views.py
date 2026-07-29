"""Initiation des paiements, webhook Wave et encaissement en espèces."""

import logging

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from apps.core.audit import record
from apps.core.models import AuditLog, Role
from apps.core.tenancy import tenant_context, unscoped
from apps.core.views_base import TenantViewSetMixin
from apps.students.models import Student, StudentStatus

from . import wave
from .models import PaymentTransaction, WaveWebhookEvent
from .services import confirm_transaction, fail_transaction, open_transaction

logger = logging.getLogger(__name__)


def _serialize(txn):
    return {
        "id": txn.id,
        "reference": txn.reference,
        "student": txn.student_id,
        "student_name": txn.student.full_name,
        "purpose": txn.purpose,
        "period": txn.period,
        "amount": txn.amount,
        "method": txn.method,
        "method_label": txn.get_method_display(),
        "status": txn.status,
        "status_label": txn.get_status_display(),
        "checkout_url": txn.checkout_url,
        "simulated": txn.simulated,
        "created_at": txn.created_at,
        "confirmed_at": txn.confirmed_at,
    }


class PaymentViewSet(TenantViewSetMixin, ViewSet):
    """Paiements initiés depuis l'école (guichet) ou le portail parent."""

    resource = "monthlypayment"

    def list(self, request):
        transactions = PaymentTransaction.objects.select_related("student")[:100]
        return Response({"results": [_serialize(t) for t in transactions]})

    def _resolve_student(self, request, student_id):
        """Élève visé, dans le périmètre de l'appelant.

        Un parent ne peut initier un paiement que pour ses propres enfants ; le
        rattachement vient de son numéro, jamais d'un identifiant fourni.
        """
        queryset = Student.objects.filter(status=StudentStatus.ACTIVE)
        if request.user.role == Role.PARENT:
            phone = request.user.phone
            queryset = queryset.filter(
                Q(parent_phone_e164=phone) | Q(family__phone_e164=phone)
            )
        student = queryset.filter(pk=student_id).first()
        if student is None:
            raise NotFound("Élève introuvable.")
        return student

    @action(detail=False, methods=["post"], url_path="wave")
    def wave_checkout(self, request):
        """Ouvre une session Wave et retourne l'URL de paiement."""
        year = self.current_year()
        student = self._resolve_student(request, request.data.get("student"))
        amount = int(request.data.get("amount") or 0)
        if amount <= 0:
            raise ValidationError({"amount": "Montant invalide."})

        purpose = request.data.get("purpose") or PaymentTransaction.Purpose.TUITION
        period = request.data.get("period")

        txn = open_transaction(
            school=request.user.school,
            student=student,
            year=year,
            amount=amount,
            method=PaymentTransaction.Method.WAVE,
            purpose=purpose,
            period=period and timezone.datetime.fromisoformat(period).date(),
            received_by=request.user.get_full_name() or request.user.email,
        )

        base = settings.PUBLIC_BASE_URL.rstrip("/")
        session = wave.create_checkout_session(
            amount=amount,
            reference=txn.reference,
            success_url=f"{base}/paiement/succes?ref={txn.reference}",
            error_url=f"{base}/paiement/echec?ref={txn.reference}",
        )

        if not session.success:
            fail_transaction(txn, error=session.error or "Wave indisponible")
            return Response(
                {"detail": f"Wave indisponible : {session.error}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        txn.provider_session_id = session.session_id
        txn.checkout_url = session.checkout_url
        txn.simulated = session.simulated
        txn.provider_payload = session.raw
        txn.save(update_fields=[
            "provider_session_id", "checkout_url", "simulated", "provider_payload"
        ])

        record(request, AuditLog.Action.CREATE, txn)
        return Response(_serialize(txn), status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="cash")
    def cash(self, request):
        """Encaissement en espèces au guichet — confirmé immédiatement.

        Contrairement à Wave, il n'y a pas d'attente de confirmation externe :
        l'agent a l'argent en main. La transaction est donc ouverte et confirmée
        dans la foulée, mais elle reste tracée comme toute autre.
        """
        if request.user.role not in (Role.ADMIN, Role.ACCOUNTANT):
            raise PermissionDenied("Seul le comptable ou l'administrateur encaisse.")

        year = self.current_year()
        student = self._resolve_student(request, request.data.get("student"))
        amount = int(request.data.get("amount") or 0)
        if amount <= 0:
            raise ValidationError({"amount": "Montant invalide."})

        period = request.data.get("period")
        txn = open_transaction(
            school=request.user.school,
            student=student,
            year=year,
            amount=amount,
            method=PaymentTransaction.Method.CASH,
            purpose=request.data.get("purpose") or PaymentTransaction.Purpose.TUITION,
            period=period and timezone.datetime.fromisoformat(period).date(),
            received_by=request.user.get_full_name() or request.user.email,
        )
        txn, _ = confirm_transaction(
            txn, notify=bool(request.data.get("send_receipt", True))
        )
        record(request, AuditLog.Action.CREATE, txn)
        return Response(_serialize(txn), status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def receipt(self, request, pk=None):
        """Reçu PDF d'un règlement confirmé."""
        txn = PaymentTransaction.objects.filter(pk=pk).select_related("student").first()
        if txn is None:
            raise NotFound("Transaction introuvable.")
        if request.user.role == Role.PARENT:
            phone = request.user.phone
            allowed = Student.objects.filter(pk=txn.student_id).filter(
                Q(parent_phone_e164=phone) | Q(family__phone_e164=phone)
            ).exists()
            if not allowed:
                raise NotFound("Transaction introuvable.")
        if txn.status != PaymentTransaction.Status.SUCCEEDED:
            raise ValidationError({"detail": "Aucun reçu pour un paiement non confirmé."})

        from .receipts import receipt_pdf

        response = receipt_pdf(txn, request.user.school)
        response["Content-Disposition"] = f'attachment; filename="recu-{txn.reference}.pdf"'
        record(request, AuditLog.Action.EXPORT, txn)
        return response


class WaveWebhookView(APIView):
    """Réception des événements Wave.

    Public par nécessité — Wave n'a pas de jeton utilisateur —, donc protégé par la
    seule signature HMAC. Tout événement dont la signature ne se vérifie pas est
    conservé pour analyse mais **jamais** appliqué à la comptabilité.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        raw_body = request.body
        signature = request.headers.get("Wave-Signature", "")
        valid = wave.verify_signature(raw_body, signature)
        payload = wave.parse_event(raw_body) or {}

        event_id = payload.get("id") or f"unsigned-{timezone.now().timestamp()}"
        event_type = payload.get("type", "")

        event, created = WaveWebhookEvent.objects.get_or_create(
            event_id=event_id,
            defaults={
                "event_type": event_type,
                "payload": payload,
                "signature_valid": valid,
            },
        )
        if not created and event.processed:
            # Wave réémet légitimement ses webhooks : on acquitte sans retraiter.
            return Response({"detail": "Événement déjà traité."})

        if not valid:
            logger.warning("[WAVE] Signature invalide pour l'événement %s.", event_id)
            return Response(
                {"detail": "Signature invalide."}, status=status.HTTP_401_UNAUTHORIZED
            )

        try:
            self._process(event_type, payload)
            event.processed = True
        except Exception as error:  # noqa: BLE001
            logger.exception("[WAVE] Traitement impossible pour %s", event_id)
            event.processing_error = str(error)
            event.save(update_fields=["processing_error"])
            # 500 volontaire : Wave réessaiera, plutôt que de perdre le paiement.
            return Response(
                {"detail": "Erreur de traitement."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        event.save(update_fields=["processed", "processing_error"])
        return Response({"detail": "Traité."})

    def _process(self, event_type, payload):
        data = payload.get("data", payload)
        reference = data.get("client_reference")
        if not reference:
            logger.info("[WAVE] Événement sans client_reference — ignoré.")
            return

        with unscoped():
            txn = PaymentTransaction.all_objects.select_related("school", "student").filter(
                reference=reference
            ).first()
        if txn is None:
            logger.warning("[WAVE] Référence inconnue : %s", reference)
            return

        with tenant_context(txn.school):
            if event_type in ("checkout.session.completed", "checkout.session.payment_succeeded"):
                confirm_transaction(
                    txn, provider_payment_id=data.get("id", ""), payload=payload
                )
            elif event_type == "checkout.session.payment_failed":
                fail_transaction(txn, error=data.get("last_payment_error", "Paiement refusé"))
            elif event_type == "checkout.session.expired":
                fail_transaction(txn, status=PaymentTransaction.Status.EXPIRED)


class SimulatedWaveCheckoutView(APIView):
    """Confirme une transaction simulée, en développement uniquement.

    Rejoue ce que ferait le webhook Wave, pour que le parcours parent reste
    testable sans compte marchand. Refusé dès que Wave est réellement configuré, et
    hors mode DEBUG — sinon ce serait un moyen de créer des encaissements fictifs.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, reference):
        if wave.is_configured() or not settings.DEBUG:
            raise PermissionDenied("Indisponible : Wave est configuré en mode réel.")

        with unscoped():
            txn = PaymentTransaction.all_objects.select_related("school", "student").filter(
                reference=reference, simulated=True
            ).first()
        if txn is None:
            raise NotFound("Transaction simulée introuvable.")

        outcome = request.data.get("outcome", "success")
        with tenant_context(txn.school):
            if outcome == "success":
                txn, _ = confirm_transaction(txn, provider_payment_id=f"sim_{txn.id}")
            else:
                txn = fail_transaction(txn, error="Refus simulé")

        return Response(_serialize(txn))
