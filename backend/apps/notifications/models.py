import secrets
from datetime import timedelta

from django.db import models
from django.utils import timezone

from apps.core.tenancy import TenantScopedModel

OTP_LENGTH = 6
OTP_VALIDITY = timedelta(minutes=10)
OTP_MAX_ATTEMPTS = 5


class OtpCodeQuerySet(models.QuerySet):
    def valid(self):
        return self.filter(
            consumed_at__isnull=True,
            expires_at__gt=timezone.now(),
            attempts__lt=OTP_MAX_ATTEMPTS,
        )


class OtpCode(TenantScopedModel):
    """Code à usage unique pour la connexion du portail parent.

    Le code n'est **pas** stocké en clair : seule son empreinte l'est. Une fuite de
    la table ne permettrait donc pas de se connecter à la place d'un parent.
    """

    phone = models.CharField("téléphone normalisé", max_length=20, db_index=True)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField("tentatives", default=0)
    consumed_at = models.DateTimeField("utilisé le", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    objects = OtpCodeQuerySet.as_manager()

    class Meta:
        verbose_name = "code de connexion"
        verbose_name_plural = "codes de connexion"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["school", "phone", "consumed_at"])]

    def __str__(self):
        return f"{self.phone} — {self.created_at:%d/%m %H:%M}"

    @staticmethod
    def hash_code(phone, code):
        import hashlib

        from django.conf import settings

        # Le numéro entre dans l'empreinte : un code intercepté ne vaut alors que
        # pour la ligne à laquelle il a été envoyé.
        payload = f"{phone}:{code}:{settings.SECRET_KEY}".encode()
        return hashlib.sha256(payload).hexdigest()

    @classmethod
    def issue(cls, school, phone, ip_address=None):
        """Génère un code et retourne (instance, code en clair)."""
        # Les codes en cours pour ce numéro sont invalidés : sinon plusieurs codes
        # coexistent et la fenêtre d'attaque se multiplie.
        cls.objects.filter(phone=phone, consumed_at__isnull=True).update(
            consumed_at=timezone.now()
        )
        code = f"{secrets.randbelow(10**OTP_LENGTH):0{OTP_LENGTH}d}"
        instance = cls.objects.create(
            school=school,
            phone=phone,
            code_hash=cls.hash_code(phone, code),
            expires_at=timezone.now() + OTP_VALIDITY,
            ip_address=ip_address,
        )
        return instance, code

    def verify(self, code):
        """Vérifie le code et le consomme en cas de succès."""
        import hmac

        self.attempts += 1
        matched = hmac.compare_digest(self.code_hash, self.hash_code(self.phone, code))
        if matched:
            self.consumed_at = timezone.now()
        self.save(update_fields=["attempts", "consumed_at"])
        return matched

    @property
    def is_locked(self):
        return self.attempts >= OTP_MAX_ATTEMPTS


class ReminderRun(TenantScopedModel):
    """Trace d'une campagne de rappels.

    Évite qu'un ordonnanceur relancé, ou un administrateur impatient, n'envoie deux
    fois le même rappel aux mêmes parents dans la journée.
    """

    class Kind(models.TextChoices):
        UPCOMING = "UPCOMING", "Échéance à venir"
        ARREARS = "ARREARS", "Arriérés"

    kind = models.CharField(max_length=15, choices=Kind.choices)
    period = models.DateField("période visée")
    run_date = models.DateField("date d'exécution", default=timezone.localdate)
    sent = models.PositiveIntegerField("envoyés", default=0)
    failed = models.PositiveIntegerField("échecs", default=0)
    skipped = models.PositiveIntegerField("ignorés", default=0)
    simulated = models.BooleanField("mode simulation", default=False)
    triggered_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "campagne de rappels"
        verbose_name_plural = "campagnes de rappels"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "kind", "period", "run_date"],
                name="one_reminder_run_per_day",
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.run_date}"
