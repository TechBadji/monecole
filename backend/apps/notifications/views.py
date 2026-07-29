"""Authentification du portail parent et pilotage des rappels."""

import logging

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.models import Notification, Role, School
from apps.core.tenancy import tenant_context, unscoped
from apps.core.views_base import TenantViewSetMixin
from apps.students.models import Family, Student, StudentStatus

from .models import OtpCode
from .services import run_arrears_reminders, send_otp
from .sms import normalize_phone

logger = logging.getLogger(__name__)
User = get_user_model()


def _students_for_phone(phone):
    """Élèves rattachés à un numéro, via la fiche élève ou la famille."""
    return (
        Student.objects.filter(status=StudentStatus.ACTIVE)
        .filter(Q(parent_phone_e164=phone) | Q(family__phone_e164=phone))
        .select_related("classroom", "family")
        .distinct()
    )


class ParentOtpRequestView(APIView):
    """Demande d'un code de connexion.

    Répond **toujours** un succès, que le numéro soit connu ou non. Distinguer les
    deux cas transformerait cet endpoint public en oracle permettant d'énumérer les
    numéros de parents inscrits dans un établissement.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "otp"

    def post(self, request):
        raw_phone = (request.data.get("phone") or "").strip()
        school_slug = (request.data.get("school") or "").strip()
        if not raw_phone:
            raise ValidationError({"phone": "Numéro de téléphone requis."})

        phone = normalize_phone(raw_phone)

        with unscoped():
            school = (
                School.objects.filter(slug=school_slug, is_active=True).first()
                if school_slug
                else None
            )
            if school is None:
                # Sans établissement précisé, on retrouve celui de l'élève rattaché
                # au numéro : le parent n'a pas à connaître l'identifiant technique
                # de l'école de son enfant.
                student = (
                    Student.all_objects.filter(
                        Q(parent_phone_e164=phone) | Q(family__phone_e164=phone),
                        status=StudentStatus.ACTIVE,
                    )
                    .select_related("school")
                    .first()
                )
                school = student.school if student else None

        if school is not None:
            with tenant_context(school):
                if _students_for_phone(phone).exists():
                    otp, code = OtpCode.issue(
                        school, phone, ip_address=request.META.get("REMOTE_ADDR")
                    )
                    send_otp(school, phone, code)
                else:
                    logger.info("Demande de code pour un numéro sans élève : %s", phone)
        else:
            logger.info("Demande de code pour un numéro inconnu : %s", phone)

        return Response(
            {
                "detail": "Si ce numéro est rattaché à un élève, un code vient d'être "
                "envoyé par SMS.",
                "expires_in": 600,
            }
        )


class ParentOtpVerifyView(APIView):
    """Vérification du code et délivrance des jetons."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "otp"

    def post(self, request):
        raw_phone = (request.data.get("phone") or "").strip()
        code = (request.data.get("code") or "").strip()
        if not raw_phone or not code:
            raise ValidationError({"detail": "Numéro et code requis."})

        phone = normalize_phone(raw_phone)

        with unscoped():
            otp = (
                OtpCode.objects.filter(phone=phone, consumed_at__isnull=True)
                .select_related("school")
                .order_by("-created_at")
                .first()
            )

        generic_error = Response(
            {"detail": "Code invalide ou expiré."}, status=status.HTTP_400_BAD_REQUEST
        )

        if otp is None or otp.expires_at <= timezone.now():
            return generic_error
        if otp.is_locked:
            return Response(
                {"detail": "Trop de tentatives. Demandez un nouveau code."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if not otp.verify(code):
            return generic_error

        school = otp.school
        with tenant_context(school):
            students = list(_students_for_phone(phone))
            if not students:
                return generic_error

            user = self._get_or_create_parent(school, phone, students[0])

        refresh = RefreshToken.for_user(user)
        refresh["role"] = user.role
        refresh["school_id"] = user.school_id

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "full_name": user.get_full_name(),
                    "role": user.role,
                    "phone": phone,
                },
                "school": {"id": school.id, "name": school.name, "currency": school.currency},
                "children": [
                    {"id": s.id, "name": s.full_name, "classroom": s.classroom.name}
                    for s in students
                ],
            }
        )

    def _get_or_create_parent(self, school, phone, student):
        """Compte parent, créé au premier accès.

        Aucun provisionnement manuel : le secrétariat saisit déjà le numéro dans la
        fiche élève, exiger une seconde saisie serait une source d'écart.
        L'email est synthétique — l'identifiant réel est le numéro.
        """
        with unscoped():
            user = User.objects.filter(phone=phone, role=Role.PARENT, school=school).first()
            if user:
                return user

            name = student.parent_name or (
                student.family.primary_contact if student.family_id else ""
            )
            first_name, _, last_name = name.partition(" ")
            user = User(
                email=f"parent+{phone}@{school.slug}.portal",
                phone=phone,
                first_name=first_name or "Parent",
                last_name=last_name,
                role=Role.PARENT,
                school=school,
            )
            user.set_unusable_password()  # la connexion passe uniquement par le code
            user.save()
            return user


class ReminderViewSet(TenantViewSetMixin, ViewSet):
    """Campagnes de rappels de paiement."""

    resource = "monthlypayment"

    def list(self, request):
        from .models import ReminderRun

        runs = ReminderRun.objects.all()[:20]
        return Response(
            {
                "results": [
                    {
                        "id": run.id,
                        "kind": run.get_kind_display(),
                        "run_date": run.run_date,
                        "sent": run.sent,
                        "failed": run.failed,
                        "skipped": run.skipped,
                        "simulated": run.simulated,
                        "triggered_by": run.triggered_by,
                    }
                    for run in runs
                ]
            }
        )

    @action(detail=False, methods=["post"], url_path="arrears")
    def arrears(self, request):
        """Lance — ou simule — la relance des impayés.

        `dry_run` à vrai retourne la liste des messages sans rien envoyer. C'est le
        mode par défaut attendu avant d'engager plusieurs centaines de SMS.
        """
        if request.user.role not in (Role.ADMIN, Role.ACCOUNTANT):
            return Response({"detail": "Non autorisé."}, status=status.HTTP_403_FORBIDDEN)

        year = self.current_year()
        dry_run = bool(request.data.get("dry_run", True))
        min_amount = int(request.data.get("min_amount") or 0)

        result = run_arrears_reminders(
            request.user.school,
            year,
            triggered_by=request.user.get_full_name() or request.user.email,
            dry_run=dry_run,
            min_amount=min_amount,
        )
        if "run" in result:
            result["run"] = result["run"].id
        return Response(result)


class NotificationOutboxView(TenantViewSetMixin, APIView):
    """Boîte d'envoi — succès et échecs, pour répondre à une réclamation."""

    resource = "auditlog"

    def get(self, request):
        notifications = Notification.objects.all()[:200]
        return Response(
            {
                "count": Notification.objects.count(),
                "results": [
                    {
                        "id": n.id,
                        "recipient": n.recipient,
                        "channel": n.channel,
                        "template": n.template,
                        "status": n.status,
                        "error": n.error,
                        "simulated": n.payload.get("simulated", False),
                        "segments": n.payload.get("segments", 1),
                        "sent_at": n.sent_at,
                        "created_at": n.created_at,
                    }
                    for n in notifications
                ],
            }
        )
