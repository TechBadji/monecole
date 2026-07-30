from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import SchoolYear
from apps.core.tenancy import TenantScopedModel

# Barème sénégalais : notes sur 20, au demi-point.
MAX_GRADE = Decimal("20")

# Matières usuelles de l'élémentaire sénégalais, avec leurs coefficients d'usage.
DEFAULT_SUBJECTS = [
    ("FR", "Français", 4),
    ("MATH", "Mathématiques", 4),
    ("SCI", "Sciences et vie de la terre", 2),
    ("HG", "Histoire-Géographie", 2),
    ("AR", "Arabe", 2),
    ("EN", "Anglais", 1),
    ("EPS", "Éducation physique et sportive", 1),
    ("CONDUITE", "Conduite", 1),
]


class Subject(TenantScopedModel):
    """Matière enseignée."""

    code = models.CharField("code", max_length=16)
    name = models.CharField("intitulé", max_length=100)
    default_coefficient = models.PositiveSmallIntegerField("coefficient par défaut", default=1)
    order = models.PositiveSmallIntegerField("rang", default=0)
    is_active = models.BooleanField("active", default=True)

    class Meta:
        verbose_name = "matière"
        verbose_name_plural = "matières"
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "code"], name="unique_subject_per_school")
        ]

    def __str__(self):
        return self.name


class ClassSubject(TenantScopedModel):
    """Matière rattachée à une classe, avec son coefficient et son enseignant.

    Le coefficient est porté ici et non sur la matière : le français ne pèse pas
    le même poids en garderie et en CM2, et une école doit pouvoir l'ajuster
    classe par classe sans dupliquer ses matières.
    """

    classroom = models.ForeignKey(
        "students.ClassRoom", on_delete=models.CASCADE, related_name="class_subjects"
    )
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="class_subjects")
    year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE, related_name="class_subjects")
    coefficient = models.PositiveSmallIntegerField("coefficient", default=1)
    teacher = models.ForeignKey(
        "staff.Teacher",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="class_subjects",
        help_text="Enseignant autorisé à saisir les notes de cette matière.",
    )
    order = models.PositiveSmallIntegerField("rang", default=0)

    class Meta:
        verbose_name = "matière de classe"
        verbose_name_plural = "matières de classe"
        ordering = ["order", "subject__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["classroom", "subject", "year"],
                name="unique_class_subject_per_year",
            )
        ]

    def __str__(self):
        return f"{self.classroom} — {self.subject} (coef {self.coefficient})"


class Composition(TenantScopedModel):
    """Période d'évaluation : composition trimestrielle ou devoir libre.

    Créée par l'administration, avec un intitulé libre et une date. Le statut
    gouverne qui peut écrire : une composition clôturée n'accepte plus de note,
    sans quoi un bulletin déjà remis pourrait changer après coup.
    """

    class Kind(models.TextChoices):
        TERM = "TERM", "Composition trimestrielle"
        FREE = "FREE", "Évaluation libre"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "En préparation"
        OPEN = "OPEN", "Saisie ouverte"
        CLOSED = "CLOSED", "Clôturée"

    year = models.ForeignKey(SchoolYear, on_delete=models.PROTECT, related_name="compositions")
    name = models.CharField("intitulé", max_length=120, help_text="Par exemple : 1er trimestre")
    kind = models.CharField("nature", max_length=6, choices=Kind.choices, default=Kind.TERM)
    term = models.PositiveSmallIntegerField(
        "trimestre", null=True, blank=True,
        help_text="1, 2 ou 3 pour une composition trimestrielle.",
    )
    date = models.DateField("date de l'évaluation")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "composition"
        verbose_name_plural = "compositions"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "year", "name"], name="unique_composition_name_per_year"
            )
        ]

    def __str__(self):
        return f"{self.name} — {self.year}"

    @property
    def accepts_grades(self):
        return self.status == self.Status.OPEN


class GradeSheet(TenantScopedModel):
    """Feuille de notes d'un enseignant : une classe, une matière, une composition.

    Porte la validation. C'est l'enseignant qui déclare sa saisie terminée ; sans
    ce jalon, l'administration ne saurait pas distinguer une note manquante d'une
    note pas encore saisie, et éditerait des bulletins incomplets.
    """

    composition = models.ForeignKey(
        Composition, on_delete=models.CASCADE, related_name="sheets"
    )
    class_subject = models.ForeignKey(
        ClassSubject, on_delete=models.CASCADE, related_name="sheets"
    )
    is_validated = models.BooleanField("validée", default=False)
    validated_at = models.DateTimeField(null=True, blank=True)
    validated_by = models.CharField(max_length=150, blank=True)

    class Meta:
        verbose_name = "feuille de notes"
        verbose_name_plural = "feuilles de notes"
        constraints = [
            models.UniqueConstraint(
                fields=["composition", "class_subject"], name="unique_sheet_per_composition"
            )
        ]

    def __str__(self):
        return f"{self.class_subject} — {self.composition.name}"


class Grade(TenantScopedModel):
    """Note d'un élève dans une matière pour une composition."""

    sheet = models.ForeignKey(GradeSheet, on_delete=models.CASCADE, related_name="grades")
    student = models.ForeignKey(
        "students.Student", on_delete=models.CASCADE, related_name="grades"
    )
    value = models.DecimalField(
        "note",
        max_digits=4,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(MAX_GRADE)],
        help_text="Sur 20. Vide signifie « absent », ce qui n'est pas un zéro.",
    )
    is_absent = models.BooleanField("absent", default=False)
    comment = models.CharField("appréciation", max_length=255, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "note"
        verbose_name_plural = "notes"
        ordering = ["student__last_name", "student__first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["sheet", "student"], name="unique_grade_per_sheet_student"
            ),
            # Une absence n'est pas un zéro : elle n'entre pas dans la moyenne.
            # Porter les deux serait contradictoire.
            models.CheckConstraint(
                check=models.Q(is_absent=True, value__isnull=True)
                | models.Q(is_absent=False),
                name="absent_grade_has_no_value",
            ),
        ]

    def __str__(self):
        return f"{self.student} — {self.value if self.value is not None else 'abs'}"

    @property
    def counts(self):
        """La note entre-t-elle dans la moyenne ?"""
        return not self.is_absent and self.value is not None


class ReportCardSettings(TenantScopedModel):
    """Éléments paramétrables du bulletin scolaire.

    Le bulletin est le document que l'école remet aux familles et présente à
    l'inspection : son en-tête, ses mentions et ses signatures doivent être
    réglables sans intervention technique.
    """

    logo = models.ImageField("logo", upload_to="school-logos/", null=True, blank=True)
    header_line_1 = models.CharField(
        "première ligne d'en-tête", max_length=120, blank=True,
        help_text="Par exemple : République du Sénégal",
    )
    header_line_2 = models.CharField(
        "deuxième ligne d'en-tête", max_length=120, blank=True,
        help_text="Par exemple : Ministère de l'Éducation nationale",
    )
    header_line_3 = models.CharField(
        "troisième ligne d'en-tête", max_length=120, blank=True,
        help_text="Par exemple : Inspection de l'Éducation et de la Formation de Dakar",
    )
    establishment_code = models.CharField("code établissement", max_length=40, blank=True)
    principal_name = models.CharField("nom du directeur", max_length=120, blank=True)
    principal_title = models.CharField(
        "fonction", max_length=80, blank=True, default="Le Directeur"
    )
    show_rank = models.BooleanField("afficher le rang", default=True)
    show_class_average = models.BooleanField("afficher la moyenne de classe", default=True)
    footer_note = models.TextField("mention de pied", blank=True)

    class Meta:
        verbose_name = "paramètres du bulletin"
        verbose_name_plural = "paramètres du bulletin"

    def __str__(self):
        return f"Bulletin — {self.school}"

    @classmethod
    def for_school(cls, school):
        settings, _ = cls.objects.get_or_create(school=school)
        return settings


def mention_for(average):
    """Mention correspondant à une moyenne sur 20, usage sénégalais."""
    if average is None:
        return ""
    if average >= 16:
        return "Très bien"
    if average >= 14:
        return "Bien"
    if average >= 12:
        return "Assez bien"
    if average >= 10:
        return "Passable"
    return "Insuffisant"
