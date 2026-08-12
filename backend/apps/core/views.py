from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_datetime
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .audit import AuditedModelViewSetMixin, record
from .models import (
    AuditLog,
    LoginSession,
    Notification,
    Role,
    School,
    SchoolYear,
    Subscription,
)
from .serializers import (
    AuditLogSerializer,
    LoginSerializer,
    NotificationSerializer,
    SchoolSerializer,
    SchoolYearSerializer,
    SubscriptionSerializer,
    UserSerializer,
)
from .tenancy import unscoped
from .views_base import TenantModelViewSet

User = get_user_model()


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            user = User.objects.filter(email=request.data.get("email")).first()
            if user:
                record(request, AuditLog.Action.LOGIN, user)
                self.open_session(request, response, user)
        return response

    def open_session(self, request, response, user):
        """Enregistre la session pour la rendre visible et révocable."""
        from .account import client_ip, device_label

        LoginSession.objects.update_or_create(
            sid=response.data["sid"],
            defaults={
                "user": user,
                "device_label": device_label(request),
                "ip_address": client_ip(request),
                "remembered": response.data.get("remembered", False),
                "expires_at": parse_datetime(response.data["expires_at"]),
                "revoked_at": None,
            },
        )


class MeView(APIView):
    """Profil de l'utilisateur connecté, avec ses permissions effectives."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .account import profile_payload

        return Response(profile_payload(request.user))


class SchoolViewSet(viewsets.ModelViewSet):
    """Établissements — réservé au super-administrateur, sauf lecture de la sienne.

    Ce modèle n'est pas `TenantScopedModel` (il *est* le tenant) : le filtrage est
    donc explicite ici.
    """

    serializer_class = SchoolSerializer
    resource = "school"

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return School.objects.all()
        return School.objects.filter(pk=user.school_id)

    @action(detail=False, methods=["post"], url_path="provision")
    def provision(self, request):
        """Ouvre un établissement : année courante, classes et accès.

        Les mots de passe ne sont renvoyés qu'ici, une seule fois. Ils ne sont
        stockés nulle part en clair et ne peuvent pas être relus : le
        super-administrateur les transmet, l'école les change à la première
        connexion.
        """
        from .provisioning import provision_school

        if not request.user.is_super_admin:
            raise PermissionDenied("Seul le super-administrateur ouvre un établissement.")

        name = (request.data.get("name") or "").strip()
        if not name:
            raise ValidationError({"name": "Le nom de l'établissement est requis."})

        try:
            start_year = int(request.data.get("start_year") or 0)
        except (TypeError, ValueError):
            start_year = 0
        if not 2000 <= start_year <= 2100:
            raise ValidationError(
                {"start_year": "Indiquez l'année d'ouverture de l'exercice, par exemple 2026."}
            )

        school, year, accounts = provision_school(
            name=name,
            start_year=start_year,
            address=request.data.get("address") or "",
            phone=request.data.get("phone") or "",
            email=request.data.get("email") or "",
            max_students=int(request.data.get("max_students") or 100),
        )
        record(request, AuditLog.Action.CREATE, school)

        return Response(
            {
                "school": SchoolSerializer(school).data,
                "year": year.label,
                "classes": 10,
                "accounts": [
                    {
                        "role": a.role,
                        "label": a.full_name,
                        "email": a.email,
                        "password": a.password,
                    }
                    for a in accounts
                ],
                "detail": (
                    "Établissement ouvert. Transmettez ces accès : les mots de "
                    "passe ne sont affichés qu'une fois et devront être changés "
                    "à la première connexion."
                ),
            },
            status=201,
        )


class SubscriptionViewSet(viewsets.ModelViewSet):
    serializer_class = SubscriptionSerializer
    resource = "subscription"

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return Subscription.objects.all()
        return Subscription.objects.filter(school__pk=user.school_id)


class SchoolYearViewSet(TenantModelViewSet):
    serializer_class = SchoolYearSerializer
    resource = "schoolyear"
    model = SchoolYear


class UserViewSet(TenantModelViewSet):
    serializer_class = UserSerializer
    resource = "user"
    search_fields = ["email", "first_name", "last_name"]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            with unscoped():
                return User.objects.all()
        # Un administrateur ne voit que les comptes de son établissement.
        return User.objects.filter(school=user.school)


class AuditLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Journal d'audit — lecture seule, par construction."""

    serializer_class = AuditLogSerializer
    resource = "auditlog"
    filterset_fields = ["action", "entity", "user"]
    ordering = ["-timestamp"]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin:
            return AuditLog.objects.all()
        return AuditLog.objects.filter(school=user.school)


class NotificationViewSet(AuditedModelViewSetMixin, TenantModelViewSet):
    serializer_class = NotificationSerializer
    resource = "auditlog"
    model = Notification
    filterset_fields = ["channel", "status"]
