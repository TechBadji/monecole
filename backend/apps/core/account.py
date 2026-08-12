"""Compte utilisateur : profil, photo, mot de passe, sessions.

Regroupé hors de `views.py`, qui porte déjà les vues métier. Tout ce qui touche
à l'identité d'un compte se lit ici d'un seul tenant.

Deux règles y reviennent :

- **Ne jamais révéler si une adresse existe.** Les réponses de réinitialisation
  sont identiques que le compte existe ou non. Un formulaire qui répond
  « adresse inconnue » est un outil d'énumération offert à qui veut dresser la
  liste du personnel d'une école.
- **Un changement de mot de passe coupe les autres appareils.** Sans cela, un
  utilisateur qui change son mot de passe parce qu'il se croit compromis laisse
  l'intrus connecté.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .audit import record
from .models import AuditLog, LoginSession, PasswordResetToken, User
from .permissions import PasswordChangeRequired

# Taille maximale d'une photo de profil. Le personnel charge des photos prises
# au téléphone, qui pèsent couramment 4 à 8 Mo ; on borne avant de redimensionner.
MAX_PHOTO_BYTES = 8 * 1024 * 1024
PHOTO_SIDE = 512
ALLOWED_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def device_label(request):
    """Étiquette lisible tirée de l'agent utilisateur.

    Volontairement grossière : il s'agit d'aider quelqu'un à reconnaître son
    propre téléphone dans une liste, pas de faire de l'empreinte d'appareil.
    """
    agent = request.META.get("HTTP_USER_AGENT", "")
    if not agent:
        return "Appareil inconnu"

    if "iPhone" in agent:
        device = "iPhone"
    elif "iPad" in agent:
        device = "iPad"
    elif "Android" in agent:
        device = "Android"
    elif "Windows" in agent:
        device = "Windows"
    elif "Mac OS X" in agent or "Macintosh" in agent:
        device = "Mac"
    elif "Linux" in agent:
        device = "Linux"
    else:
        device = "Appareil"

    # L'ordre compte : Chrome et Edge se déclarent tous deux « Safari », et Edge
    # se déclare aussi « Chrome ». Du plus spécifique au plus général.
    for needle, name in (
        ("Edg/", "Edge"),
        ("OPR/", "Opera"),
        ("Chrome/", "Chrome"),
        ("Firefox/", "Firefox"),
        ("Safari/", "Safari"),
    ):
        if needle in agent:
            return f"{name} sur {device}"
    return device


# --- Profil ------------------------------------------------------------------


class ProfileSerializer(serializers.ModelSerializer):
    """Ce que l'utilisateur peut modifier lui-même.

    Ni `role` ni `school` : un utilisateur ne se promeut pas, et ne change pas
    d'établissement. L'email non plus — c'est l'identifiant de connexion, et le
    changer par ce formulaire permettrait de détourner un compte sans repasser
    par le mot de passe.
    """

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone"]

    def validate_phone(self, value):
        value = value.strip()
        if value and not value.replace(" ", "").replace("+", "").isdigit():
            raise serializers.ValidationError(
                "Le téléphone ne doit contenir que des chiffres, un espace ou un « + »."
            )
        return value


class ProfileView(APIView):
    """Lecture et modification du profil de l'utilisateur connecté."""

    permission_classes = [IsAuthenticated, PasswordChangeRequired]

    def patch(self, request):
        serializer = ProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        record(request, AuditLog.Action.UPDATE, request.user)
        return Response(profile_payload(request.user))


def profile_payload(user):
    """Charge utile du profil, partagée par `/auth/me/` et les mises à jour.

    Un seul point de vérité : c'est en la dupliquant qu'un champ finit exposé
    d'un côté et absent de l'autre.
    """
    from .permissions import MATRIX

    permissions = {
        resource: sorted(roles.get(user.role, []))
        for resource, roles in MATRIX.items()
        if roles.get(user.role)
    }
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": user.get_full_name(),
        "phone": user.phone,
        "photo": user.photo.url if user.photo else None,
        "initials": user.initials,
        # L'interface doit pouvoir imposer l'écran de changement dès la
        # connexion, sans attendre un premier refus de l'API.
        "must_change_password": user.must_change_password,
        "role": user.role,
        "role_label": user.get_role_display(),
        "school": (
            {
                "id": user.school.id,
                "name": user.school.name,
                "currency": user.school.currency,
            }
            if user.school
            else None
        ),
        "permissions": permissions,
    }


class ProfilePhotoView(APIView):
    """Chargement et retrait de la photo de profil."""

    permission_classes = [IsAuthenticated, PasswordChangeRequired]

    def post(self, request):
        upload = request.FILES.get("photo")
        if not upload:
            return Response(
                {"detail": "Aucun fichier reçu."}, status=status.HTTP_400_BAD_REQUEST
            )
        if upload.size > MAX_PHOTO_BYTES:
            return Response(
                {
                    "detail": "La photo dépasse 8 Mo. Réduisez-la ou prenez-la "
                    "en qualité moindre."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if upload.content_type not in ALLOWED_PHOTO_TYPES:
            return Response(
                {"detail": "Formats acceptés : JPEG, PNG ou WebP."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            processed = square_thumbnail(upload)
        except OSError:
            # Pillow refuse le fichier : extension trompeuse, ou image tronquée
            # par un envoi interrompu — courant sur une connexion qui coupe.
            return Response(
                {"detail": "Ce fichier n'est pas une image lisible."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        user.photo.delete(save=False)  # ne pas laisser l'ancienne sur le disque
        user.photo.save(f"user-{user.id}.jpg", processed, save=True)
        record(request, AuditLog.Action.UPDATE, user)
        return Response(profile_payload(user))

    def delete(self, request):
        user = request.user
        user.photo.delete(save=True)
        record(request, AuditLog.Action.UPDATE, user)
        return Response(profile_payload(user))


def square_thumbnail(upload):
    """Recadre au centre et redimensionne à 512 px de côté.

    Stocker l'original serait offrir des photos de 8 Mo à une vignette de 32 px,
    sur des connexions qui ne le supportent pas. Le recadrage central est le
    moins mauvais choix automatique pour un portrait.
    """
    from io import BytesIO

    from django.core.files.base import ContentFile
    from PIL import Image, ImageOps

    image = Image.open(upload)
    # Les photos de téléphone portent leur orientation dans les métadonnées
    # EXIF : sans cette normalisation, un portrait s'affiche couché.
    image = ImageOps.exif_transpose(image)
    image = ImageOps.fit(
        image.convert("RGB"), (PHOTO_SIDE, PHOTO_SIDE), method=Image.LANCZOS
    )
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=85, optimize=True)
    return ContentFile(buffer.getvalue())


# --- Mot de passe ------------------------------------------------------------


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField()
    new_password = serializers.CharField()

    def validate_current_password(self, value):
        if not self.context["user"].check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value

    def validate_new_password(self, value):
        run_password_validators(value, self.context["user"])
        return value

    def validate(self, attrs):
        if attrs["current_password"] == attrs["new_password"]:
            raise serializers.ValidationError(
                {"new_password": "Le nouveau mot de passe doit différer de l'actuel."}
            )
        return attrs


def run_password_validators(value, user=None):
    """Applique les validateurs Django en remontant des messages français."""
    try:
        validate_password(value, user)
    except DjangoValidationError as error:
        raise serializers.ValidationError(list(error.messages)) from error


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(
            data=request.data, context={"user": request.user}
        )
        serializer.is_valid(raise_exception=True)

        user = request.user
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])

        # L'appareil courant survit : forcer l'utilisateur à se reconnecter
        # après avoir changé son mot de passe est une punition, pas une mesure.
        if user.must_change_password:
            user.must_change_password = False
            user.save(update_fields=["must_change_password"])

        kept = current_session_sid(request)
        revoked = revoke_sessions(user, keep_sid=kept)
        record(request, AuditLog.Action.UPDATE, user)
        return Response({"detail": "Mot de passe modifié.", "sessions_closed": revoked})


def current_session_sid(request):
    token = getattr(request, "auth", None)
    return token.get("sid") if token else None


def revoke_sessions(user, keep_sid=None):
    """Révoque les sessions de l'utilisateur ; renvoie le nombre fermé."""
    queryset = user.sessions.filter(revoked_at__isnull=True)
    if keep_sid:
        queryset = queryset.exclude(sid=keep_sid)
    return queryset.update(revoked_at=timezone.now())


# --- Réinitialisation --------------------------------------------------------


class PasswordResetRequestView(APIView):
    """Demande d'un lien de réinitialisation.

    Répond systématiquement 200, quel que soit le sort de l'adresse.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "password_reset"

    NEUTRAL = {
        "detail": "Si un compte correspond à cette adresse, un lien de "
        "réinitialisation vient d'y être envoyé. Pensez à regarder dans les "
        "indésirables."
    }

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        if not email:
            return Response(
                {"email": ["Indiquez votre adresse email."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user:
            # Les demandes précédentes tombent : deux liens valides en même
            # temps rallongent la fenêtre d'attaque sans rendre service.
            user.reset_tokens.filter(used_at__isnull=True).update(
                used_at=timezone.now()
            )
            token, raw = PasswordResetToken.issue(user, ip=client_ip(request))
            send_reset_email(user, raw, token)

        return Response(self.NEUTRAL)


def reset_link(raw_token):
    """Lien vers l'**interface**, pas vers l'API.

    `PUBLIC_BASE_URL` désigne déjà cette base et sert aux retours de paiement
    Wave : une seconde variable pour la même notion finirait renseignée d'un
    côté et pas de l'autre.
    """
    from django.conf import settings as django_settings

    base = django_settings.PUBLIC_BASE_URL.rstrip("/")
    return f"{base}/reinitialiser?token={raw_token}"


def send_reset_email(user, raw_token, token):
    from django.conf import settings as django_settings

    link = reset_link(raw_token)
    hours = int(PasswordResetToken.TTL / timedelta(hours=1))
    context = {
        "user": user,
        "link": link,
        "hours": hours,
        "school": user.school.name if user.school else "MonÉcole",
    }
    send_mail(
        subject="MonÉcole — réinitialisation de votre mot de passe",
        message=render_to_string("emails/password_reset.txt", context),
        html_message=render_to_string("emails/password_reset.html", context),
        from_email=django_settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        # Un envoi qui échoue ne doit pas transformer la réponse neutre en 500 :
        # le code d'erreur révélerait que l'adresse existe.
        fail_silently=True,
    )


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_scope = "password_reset"

    def post(self, request):
        raw = (request.data.get("token") or "").strip()
        new_password = request.data.get("new_password") or ""
        if not raw:
            return Response(
                {"token": ["Lien de réinitialisation absent."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        token = PasswordResetToken.objects.filter(
            token_hash=PasswordResetToken.hash(raw)
        ).first()
        if not token or not token.is_usable:
            return Response(
                {
                    "token": [
                        "Ce lien n'est plus valable. Il expire au bout de deux "
                        "heures et ne sert qu'une fois — demandez-en un nouveau."
                    ]
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        run_password_validators(new_password, token.user)

        with transaction.atomic():
            user = token.user
            user.set_password(new_password)
            user.save(update_fields=["password"])
            token.used_at = timezone.now()
            token.save(update_fields=["used_at"])
            # Ici, contrairement au changement volontaire, **tout** tombe :
            # qui réinitialise par ce chemin peut précisément être en train de
            # reprendre un compte à quelqu'un d'autre.
            revoke_sessions(user)

        return Response(
            {"detail": "Mot de passe réinitialisé. Vous pouvez vous connecter."}
        )


class PasswordResetCheckView(APIView):
    """Valide un lien avant d'afficher le formulaire.

    Évite de faire saisir deux fois un mot de passe pour apprendre ensuite que
    le lien avait expiré.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        raw = (request.query_params.get("token") or "").strip()
        token = PasswordResetToken.objects.filter(
            token_hash=PasswordResetToken.hash(raw)
        ).first()
        valid = bool(token and token.is_usable)
        return Response(
            {"valid": valid, "email": token.user.email if valid else None}
        )


# --- Sessions ----------------------------------------------------------------


class SessionSerializer(serializers.ModelSerializer):
    is_current = serializers.SerializerMethodField()

    class Meta:
        model = LoginSession
        fields = [
            "id", "device_label", "ip_address", "remembered",
            "created_at", "last_seen_at", "expires_at", "is_current",
        ]

    def get_is_current(self, obj):
        return obj.sid == self.context.get("current_sid")


class SessionListView(APIView):
    permission_classes = [IsAuthenticated, PasswordChangeRequired]

    def get(self, request):
        sessions = request.user.sessions.filter(
            revoked_at__isnull=True, expires_at__gt=timezone.now()
        )
        return Response(
            SessionSerializer(
                sessions, many=True, context={"current_sid": current_session_sid(request)}
            ).data
        )


class SessionRevokeView(APIView):
    permission_classes = [IsAuthenticated, PasswordChangeRequired]

    def delete(self, request, pk):
        session = request.user.sessions.filter(pk=pk).first()
        if not session:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if session.sid == current_session_sid(request):
            return Response(
                {
                    "detail": "C'est la session courante. Utilisez « Se "
                    "déconnecter » pour la fermer."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        session.revoked_at = timezone.now()
        session.save(update_fields=["revoked_at"])
        return Response({"detail": "Appareil déconnecté."})
