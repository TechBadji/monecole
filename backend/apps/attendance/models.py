import datetime

from django.db import models
from django.utils import timezone

from apps.core.tenancy import TenantScopedModel


class AttendanceEvent(TenantScopedModel):
    """Passage d'un élève au portail de l'école.

    Le modèle enregistre des **événements**, pas un état. Un état (« présent »,
    « absent ») serait faux dès qu'un badge est raté ou scanné deux fois ; une
    suite d'événements horodatés reste vraie et permet de reconstituer la journée
    telle qu'elle s'est passée, anomalies comprises.
    """

    class Direction(models.TextChoices):
        IN = "IN", "Entrée"
        OUT = "OUT", "Sortie"

    class Source(models.TextChoices):
        QR = "QR", "QR code"
        MANUAL = "MANUAL", "Saisie manuelle"

    student = models.ForeignKey(
        "students.Student", on_delete=models.CASCADE, related_name="attendance_events"
    )
    direction = models.CharField("sens", max_length=3, choices=Direction.choices)
    occurred_at = models.DateTimeField("horodatage", default=timezone.now, db_index=True)
    day = models.DateField(
        "journée", editable=False, db_index=True,
        help_text="Dérivée de l'horodatage, pour regrouper sans calcul de fuseau.",
    )
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.QR)
    recorded_by = models.CharField("enregistré par", max_length=150, blank=True)
    note = models.CharField("remarque", max_length=255, blank=True)
    #: Vrai si l'événement a suivi un sens identique au précédent — double scan,
    #: sortie sans entrée. Conservé plutôt que rejeté : c'est une information.
    is_anomaly = models.BooleanField("anomalie", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "passage"
        verbose_name_plural = "passages"
        ordering = ["-occurred_at"]
        indexes = [
            models.Index(fields=["school", "day", "student"]),
            models.Index(fields=["school", "student", "occurred_at"]),
        ]

    def __str__(self):
        return f"{self.student} — {self.get_direction_display()} {self.occurred_at:%d/%m %H:%M}"

    def save(self, *args, **kwargs):
        self.day = timezone.localtime(self.occurred_at).date()
        return super().save(*args, **kwargs)


class AttendanceSettings(TenantScopedModel):
    """Paramètres d'assiduité de l'établissement."""

    school_opens_at = models.TimeField("ouverture", default=datetime.time(7, 30))
    late_after = models.TimeField(
        "retard au-delà de", default=datetime.time(8, 15),
        help_text="Une entrée après cette heure est comptée comme un retard.",
    )
    school_closes_at = models.TimeField("fermeture", default=datetime.time(17, 30))
    notify_parent_on_entry = models.BooleanField(
        "prévenir le parent à l'entrée", default=False,
        help_text="Un SMS par entrée et par élève : à activer en connaissance du coût.",
    )
    notify_parent_on_exit = models.BooleanField(
        "prévenir le parent à la sortie", default=False
    )
    notify_parent_on_absence = models.BooleanField(
        "prévenir le parent en cas d'absence", default=True
    )

    class Meta:
        verbose_name = "paramètres d'assiduité"
        verbose_name_plural = "paramètres d'assiduité"

    def __str__(self):
        return f"Assiduité — {self.school}"

    @classmethod
    def for_school(cls, school):
        settings, _ = cls.objects.get_or_create(school=school)
        return settings
