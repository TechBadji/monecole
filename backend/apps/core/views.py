from django.contrib.auth import get_user_model
from django.utils.dateparse import parse_datetime
from rest_framework import mixins, viewsets
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
