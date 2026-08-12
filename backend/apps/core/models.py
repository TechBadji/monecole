import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from .tenancy import TenantScopedModel


class Role(models.TextChoices):
    SUPER_ADMIN = "SUPER_ADMIN", "Super administrateur"
    ADMIN = "ADMIN", "Administrateur d'établissement"
    ACCOUNTANT = "ACCOUNTANT", "Comptable / Trésorier"
    SECRETARY = "SECRETARY", "Secrétaire"
    TEACHER = "TEACHER", "Enseignant"
    PARENT = "PARENT", "Parent"


class Subscription(models.Model):
    """Abonnement SaaS de l'établissement à la plateforme.

    À ne pas confondre avec la gestion financière interne de l'école : ici,
    l'établissement est le client et l'éditeur le fournisseur.
    """

    class Plan(models.TextChoices):
        TRIAL = "TRIAL", "Essai"
        STANDARD = "STANDARD", "Standard"
        PREMIUM = "PREMIUM", "Premium"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Actif"
        PAST_DUE = "PAST_DUE", "Impayé"
        SUSPENDED = "SUSPENDED", "Suspendu"
        CANCELLED = "CANCELLED", "Résilié"

    plan = models.CharField(max_length=20, choices=Plan.choices, default=Plan.TRIAL)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    current_period_end = models.DateField(null=True, blank=True)
    payment_method = models.CharField(max_length=50, blank=True)
    max_students = models.PositiveIntegerField(
        default=100, help_text="Plafond d'effectif inclus dans le plan."
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "abonnement"

    def __str__(self):
        return f"{self.get_plan_display()} ({self.get_status_display()})"


class School(models.Model):
    """Établissement scolaire — c'est le tenant."""

    name = models.CharField("nom", max_length=200)
    slug = models.SlugField(unique=True)
    address = models.CharField("adresse", max_length=255, blank=True)
    phone = models.CharField("téléphone", max_length=30, blank=True)
    email = models.EmailField(blank=True)
    country = models.CharField("pays", max_length=2, default=settings.DEFAULT_COUNTRY)
    currency = models.CharField("devise", max_length=3, default=settings.DEFAULT_CURRENCY)
    subscription = models.OneToOneField(
        Subscription, on_delete=models.SET_NULL, null=True, blank=True, related_name="school"
    )
    is_active = models.BooleanField("actif", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "établissement"
        verbose_name_plural = "établissements"
        ordering = ["name"]

    def __str__(self):
        return self.name


class SchoolYear(TenantScopedModel):
    """Année scolaire.

    Deux calendriers cohabitent, et les confondre fausse tous les agrégats :

    - l'**exercice financier** court d'octobre à septembre (12 mois) et porte les
      dépenses, les salaires et le bilan ;
    - l'**année pédagogique** court d'octobre à juin (9 mois) et porte les
      mensualités des élèves.

    Voir `docs/modele-excel.md`, section « Calendriers ».
    """

    label = models.CharField("libellé", max_length=20, help_text="Par exemple : 2025/2026")
    start_date = models.DateField("début de l'exercice")
    end_date = models.DateField("fin de l'exercice")
    tuition_months = models.PositiveSmallIntegerField(
        "nombre de mois de mensualité", default=9
    )
    is_current = models.BooleanField("année courante", default=False)

    class Meta:
        verbose_name = "année scolaire"
        verbose_name_plural = "années scolaires"
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "label"], name="unique_year_label_per_school"
            ),
            models.UniqueConstraint(
                fields=["school"],
                condition=models.Q(is_current=True),
                name="one_current_year_per_school",
            ),
        ]

    def __str__(self):
        return self.label

    @property
    def fiscal_months(self):
        """Les 12 fins de mois de l'exercice, d'octobre à septembre."""
        from .periods import month_ends

        return month_ends(self.start_date, 12)

    @property
    def tuition_month_ends(self):
        """Les fins de mois portant une mensualité, d'octobre à juin."""
        from .periods import month_ends

        return month_ends(self.start_date, self.tuition_months)


class UserManager(BaseUserManager):
    """Gestionnaire d'utilisateurs identifiés par email."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("L'adresse email est obligatoire.")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", Role.SUPER_ADMIN)
        if extra.get("is_staff") is not True:
            raise ValueError("Un super-utilisateur doit avoir is_staff=True.")
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    """Utilisateur de la plateforme.

    Rattaché à un établissement, sauf le super-administrateur qui est transverse.
    L'identifiant de connexion est l'email : le username hérité est retiré.
    """

    username = None
    email = models.EmailField("adresse email", unique=True)
    first_name = models.CharField("prénom", max_length=150, blank=True)
    last_name = models.CharField("nom", max_length=150, blank=True)
    phone = models.CharField("téléphone", max_length=30, blank=True)
    photo = models.ImageField("photo", upload_to="avatars/", null=True, blank=True)
    must_change_password = models.BooleanField(
        "mot de passe à renouveler",
        default=False,
        help_text=(
            "Posé sur les comptes créés à l'ouverture d'un établissement. Tant "
            "qu'il est vrai, le compte ne peut rien faire d'autre que changer "
            "son mot de passe."
        ),
    )
    role = models.CharField("rôle", max_length=20, choices=Role.choices, default=Role.SECRETARY)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="users",
        null=True,
        blank=True,
        help_text="Nul uniquement pour le super-administrateur.",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        verbose_name = "utilisateur"
        ordering = ["last_name", "first_name", "email"]

    def __str__(self):
        return f"{self.get_full_name() or self.email} ({self.get_role_display()})"

    @property
    def is_super_admin(self):
        return self.role == Role.SUPER_ADMIN

    @property
    def initials(self):
        """Repli quand aucune photo n'est chargée.

        L'email sert de dernier recours : un compte peut exister sans état civil
        renseigné, et une vignette vide ne désigne personne.
        """
        parts = [self.first_name.strip(), self.last_name.strip()]
        letters = "".join(part[0] for part in parts if part)
        return (letters or self.email[:2]).upper()


class PasswordResetToken(models.Model):
    """Jeton de réinitialisation, à usage unique et de courte durée.

    Le jeton n'est **pas** stocké en clair : seul son condensé l'est. Une fuite
    de la table ne permet donc pas de prendre la main sur un compte, alors que
    ces lignes vivent à côté des adresses email de tout le personnel.
    """

    TTL = timedelta(hours=2)

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reset_tokens"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    requested_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = "jeton de réinitialisation"
        verbose_name_plural = "jetons de réinitialisation"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Réinitialisation pour {self.user.email}"

    @staticmethod
    def hash(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    @classmethod
    def issue(cls, user, ip=None):
        """Émet un jeton et renvoie `(instance, valeur en clair)`.

        La valeur en clair n'existe qu'ici et dans le message envoyé : elle
        n'est jamais réécrite en base ni journalisée.
        """
        raw = secrets.token_urlsafe(32)
        instance = cls.objects.create(
            user=user,
            token_hash=cls.hash(raw),
            expires_at=timezone.now() + cls.TTL,
            requested_ip=ip,
        )
        return instance, raw

    @property
    def is_usable(self):
        return self.used_at is None and self.expires_at > timezone.now()


class LoginSession(models.Model):
    """Une session ouverte sur un appareil.

    Sert à deux choses que le seul jeton JWT ne permet pas : montrer à
    l'utilisateur où son compte est connecté, et **révoquer** un appareil. Un
    JWT est autoporteur — sans cette table, un jeton volé reste valide jusqu'à
    son expiration et rien ne peut l'interrompre.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions"
    )
    # Volontairement **pas** le `jti` du jeton : celui-ci change à chaque
    # rafraîchissement, et la session serait perdue au bout de trente minutes.
    # `sid` est posé à la connexion et recopié de rafraîchissement en
    # rafraîchissement, car SimpleJWT reporte les revendications personnalisées
    # du jeton de rafraîchissement vers le jeton d'accès.
    sid = models.CharField("identifiant de session", max_length=64, unique=True)
    device_label = models.CharField("appareil", max_length=120, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    remembered = models.BooleanField(
        "session prolongée",
        default=False,
        help_text="Case « se souvenir de moi » cochée à la connexion.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "session de connexion"
        verbose_name_plural = "sessions de connexion"
        ordering = ["-last_seen_at"]

    def __str__(self):
        return f"{self.device_label or 'Appareil inconnu'} — {self.user.email}"

    @property
    def is_active(self):
        return self.revoked_at is None and self.expires_at > timezone.now()


class AuditLog(models.Model):
    """Journal d'audit des opérations sensibles.

    Immuable : ni `save()` sur une instance existante ni `delete()` ne sont permis.
    Le cahier des charges l'exige sur toute opération financière — création,
    modification ou suppression d'un paiement ou d'une dépense.
    """

    class Action(models.TextChoices):
        CREATE = "CREATE", "Création"
        UPDATE = "UPDATE", "Modification"
        DELETE = "DELETE", "Suppression"
        LOGIN = "LOGIN", "Connexion"
        EXPORT = "EXPORT", "Export"

    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="audit_logs", null=True, blank=True
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="audit_logs"
    )
    user_label = models.CharField(
        max_length=255, blank=True, help_text="Identité figée au moment de l'action."
    )
    action = models.CharField(max_length=10, choices=Action.choices)
    entity = models.CharField(max_length=100)
    entity_id = models.CharField(max_length=64, blank=True)
    before = models.JSONField(null=True, blank=True)
    after = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "entrée d'audit"
        verbose_name_plural = "journal d'audit"
        ordering = ["-timestamp"]
        indexes = [models.Index(fields=["school", "entity", "entity_id"])]

    def __str__(self):
        return f"{self.timestamp:%Y-%m-%d %H:%M} — {self.action} {self.entity}#{self.entity_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionError("Le journal d'audit est immuable : modification refusée.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Le journal d'audit est immuable : suppression refusée.")


class Notification(TenantScopedModel):
    """Trace des envois sortants (rappels de paiement, factures)."""

    class Channel(models.TextChoices):
        EMAIL = "EMAIL", "Email"
        SMS = "SMS", "SMS"

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        SENT = "SENT", "Envoyé"
        FAILED = "FAILED", "Échec"

    recipient = models.CharField("destinataire", max_length=255)
    channel = models.CharField(max_length=10, choices=Channel.choices)
    template = models.CharField(max_length=100)
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "notification"
        ordering = ["-created_at"]
