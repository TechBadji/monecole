from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import SchoolYear
from apps.core.tenancy import TenantScopedModel

MONEY = {"validators": [MinValueValidator(0)], "default": 0}


class PaymentTransaction(TenantScopedModel):
    """Tentative de règlement, quel qu'en soit le moyen.

    Distincte de `MonthlyPayment`, qui est l'écriture comptable : une transaction
    peut être ouverte, abandonnée ou échouée sans jamais donner lieu à écriture.
    Ne confondre les deux ferait apparaître au bilan des paiements jamais reçus.

    L'écriture n'est créée qu'à la confirmation (webhook Wave, ou encaissement
    immédiat pour les espèces).
    """

    class Method(models.TextChoices):
        WAVE = "WAVE", "Wave"
        CASH = "CASH", "Espèces"
        ORANGE_MONEY = "ORANGE_MONEY", "Orange Money"
        TRANSFER = "TRANSFER", "Virement"
        CHECK = "CHECK", "Chèque"

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        SUCCEEDED = "SUCCEEDED", "Confirmé"
        FAILED = "FAILED", "Échoué"
        CANCELLED = "CANCELLED", "Annulé"
        EXPIRED = "EXPIRED", "Expiré"

    class Purpose(models.TextChoices):
        TUITION = "TUITION", "Mensualité"
        REGISTRATION = "REGISTRATION", "Inscription"

    student = models.ForeignKey(
        "students.Student", on_delete=models.PROTECT, related_name="transactions"
    )
    year = models.ForeignKey(SchoolYear, on_delete=models.PROTECT, related_name="transactions")
    purpose = models.CharField(max_length=15, choices=Purpose.choices, default=Purpose.TUITION)
    period = models.DateField(
        "période", null=True, blank=True, help_text="Fin de mois visée, pour une mensualité."
    )
    amount = models.PositiveIntegerField("montant", **MONEY)
    method = models.CharField("moyen", max_length=20, choices=Method.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)

    # Références externes
    reference = models.CharField(
        "référence interne", max_length=64, unique=True,
        help_text="Transmise au prestataire comme `client_reference`.",
    )
    provider_session_id = models.CharField(max_length=128, blank=True, db_index=True)
    provider_payment_id = models.CharField(max_length=128, blank=True)
    checkout_url = models.URLField(blank=True)
    provider_payload = models.JSONField(default=dict, blank=True)

    simulated = models.BooleanField(
        "simulé", default=False,
        help_text="Vrai si le prestataire n'était pas configuré. Ces transactions "
        "ne doivent jamais être prises pour des encaissements réels.",
    )
    error = models.TextField(blank=True)

    # Écriture comptable alimentée à la confirmation.
    #
    # `ForeignKey` et non `OneToOne` : une mensualité peut être réglée en plusieurs
    # versements — c'est le paiement partiel exigé par le cahier des charges. Chaque
    # versement est une transaction distincte, toutes rattachées à la même écriture.
    monthly_payment = models.ForeignKey(
        "students.MonthlyPayment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )
    received_by = models.CharField("encaissé par", max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "transaction de paiement"
        verbose_name_plural = "transactions de paiement"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "status", "method"]),
            models.Index(fields=["school", "student", "year"]),
        ]

    def __str__(self):
        return f"{self.reference} — {self.get_method_display()} {self.amount}"

    @property
    def is_final(self):
        return self.status != self.Status.PENDING


class WaveWebhookEvent(models.Model):
    """Événement Wave reçu, conservé brut.

    Non rattaché à un établissement : à la réception, le tenant n'est pas encore
    connu. Le stockage systématique permet de rejouer un traitement qui aurait
    échoué, et de prouver ce que le prestataire a réellement envoyé.
    """

    event_id = models.CharField(max_length=128, unique=True)
    event_type = models.CharField(max_length=64)
    payload = models.JSONField()
    signature_valid = models.BooleanField(default=False)
    processed = models.BooleanField(default=False)
    processing_error = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "événement Wave"
        verbose_name_plural = "événements Wave"
        ordering = ["-received_at"]

    def __str__(self):
        return f"{self.event_type} — {self.event_id}"
