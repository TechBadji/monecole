from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import SchoolYear
from apps.core.tenancy import TenantScopedModel

# Barème sénégalais : notes sur 20, au demi-point.
# Borne haute d'un barème. Aucune matière relevée ne dépasse 60 (Compétences
# Maths et Production d'écrits en CM1/CM2) ; 100 laisse de la marge sans rendre
# une faute de frappe indolore.
MAX_SCORE = 100

# Échelle de la moyenne. Les bulletins de l'école élémentaire sénégalaise
# retenue sont sur 10 : moyenne = somme des notes / somme des barèmes × 10.
AVERAGE_SCALE = Decimal("10")


class Subject(TenantScopedModel):
    """Matière enseignée."""

    code = models.CharField("code", max_length=16)
    name = models.CharField("intitulé", max_length=100)
    default_max_score = models.PositiveSmallIntegerField(
        "barème par défaut",
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_SCORE)],
    )
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
    """Matière rattachée à une classe, avec son barème et son enseignant.

    **Le barème est le poids.** Il n'y a pas de coefficient multiplicateur : une
    matière sur 20 pèse cinq fois une matière sur 4, et la moyenne vaut
    `somme des notes / somme des barèmes × 10`. C'est la règle établie sur vingt
    bulletins réels — voir `catalogue.py` et `docs/bareme-gsk.md`.

    Le barème est porté ici et non sur la matière : la conjugaison ne pèse pas
    le même poids au CI et au CM2, et une école doit pouvoir l'ajuster classe
    par classe sans dupliquer ses matières.
    """

    classroom = models.ForeignKey(
        "students.ClassRoom", on_delete=models.CASCADE, related_name="class_subjects"
    )
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name="class_subjects")
    year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE, related_name="class_subjects")
    max_score = models.PositiveSmallIntegerField(
        "barème",
        default=10,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_SCORE)],
        help_text="Note maximale de la matière. C'est elle qui fait son poids.",
    )
    teacher = models.ForeignKey(
        "staff.Teacher",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="class_subjects",
        help_text=(
            "Intervenant propre à cette matière — arabe, anglais. Vide, c'est le "
            "titulaire de la classe qui saisit."
        ),
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
        return f"{self.classroom} — {self.subject} (sur {self.max_score})"

    @property
    def effective_teacher(self):
        """Qui enseigne réellement cette matière.

        L'intervenant s'il y en a un, sinon le titulaire de la classe. Les
        bulletins de l'école portent le nom de l'enseignant sur **chaque
        ligne** : sans cette cascade, la colonne resterait vide dès lors que la
        matière n'a pas d'intervenant propre — c'est-à-dire presque toujours.
        """
        return self.teacher or self.classroom.teacher


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
    # Le barème change d'une épreuve à l'autre : au CE2, la conjugaison a été
    # notée sur 4, 8, 10 puis 12 dans la même année. Vide signifie « celui de la
    # classe » — le cas courant, qu'on ne veut pas faire ressaisir.
    max_score = models.PositiveSmallIntegerField(
        "barème de l'épreuve",
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(MAX_SCORE)],
        help_text="Laisser vide pour reprendre le barème de la classe.",
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

    @property
    def effective_max_score(self):
        """Barème qui fait foi pour cette feuille."""
        return self.max_score or self.class_subject.max_score


class Grade(TenantScopedModel):
    """Note d'un élève dans une matière pour une composition."""

    sheet = models.ForeignKey(GradeSheet, on_delete=models.CASCADE, related_name="grades")
    student = models.ForeignKey(
        "students.Student", on_delete=models.CASCADE, related_name="grades"
    )
    value = models.DecimalField(
        "note",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text=(
            "Sur le barème de la feuille, et non sur 20. Vide signifie "
            "« absent », ce qui n'est pas un zéro."
        ),
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

    def clean(self):
        """La borne haute est le barème de la feuille, et lui seul.

        Un `MaxValueValidator` fixe ne conviendrait pas : la même note vaut 16
        sur 16 en activités numériques et serait aberrante sur un barème de 4.
        """
        super().clean()
        if self.value is not None and self.sheet_id:
            ceiling = self.sheet.effective_max_score
            if self.value > ceiling:
                raise ValidationError(
                    {"value": f"La note dépasse le barème de la matière (sur {ceiling})."}
                )

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
    """Mention correspondant à une moyenne **sur 10**, usage sénégalais.

    Les seuils sont ceux de l'échelle sur 20, divisés par deux : la moyenne du
    produit est sur 10, comme celle des bulletins de l'école. Conserver les
    seuils sur 20 aurait classé tout un établissement « Insuffisant » sans que
    rien ne le signale.
    """
    if average is None:
        return ""
    if average >= 8:
        return "Très bien"
    if average >= 7:
        return "Bien"
    if average >= 6:
        return "Assez bien"
    if average >= 5:
        return "Passable"
    return "Insuffisant"
