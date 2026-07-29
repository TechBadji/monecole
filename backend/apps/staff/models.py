from django.core.validators import MinValueValidator
from django.db import models, transaction

from apps.core.models import SchoolYear
from apps.core.tenancy import TenantScopedModel

MONEY = {"validators": [MinValueValidator(0)], "default": 0}


class Teacher(TenantScopedModel):
    """Personnel enseignant — onglet « Enseignants » du classeur source.

    Reprend les 19 colonnes de l'état nominatif. Le matricule est attribué
    automatiquement, comme le faisait la formule `TEXT(D8+1,"000")`.
    """

    class ContractType(models.TextChoices):
        PERMANENT = "PERMANENT", "CDI"
        FIXED_TERM = "FIXED_TERM", "CDD"
        SUBSTITUTE = "SUBSTITUTE", "Vacataire"

    class MaritalStatus(models.TextChoices):
        SINGLE = "SINGLE", "Célibataire"
        MARRIED = "MARRIED", "Marié(e)"
        DIVORCED = "DIVORCED", "Divorcé(e)"
        WIDOWED = "WIDOWED", "Veuf / Veuve"

    matricule = models.CharField("matricule", max_length=10, editable=False)
    first_name = models.CharField("prénom(s)", max_length=100)
    last_name = models.CharField("nom", max_length=100)
    sex = models.CharField(
        "sexe", max_length=1, choices=[("M", "Masculin"), ("F", "Féminin")], blank=True
    )
    date_of_birth = models.DateField("date de naissance", null=True, blank=True)
    cni = models.CharField("CNI", max_length=30, blank=True)
    marital_status = models.CharField(
        "situation matrimoniale", max_length=10, choices=MaritalStatus.choices, blank=True
    )
    corps = models.CharField("corps", max_length=100, blank=True)
    grade = models.CharField("grade / génération", max_length=100, blank=True)
    academic_diploma = models.CharField("diplôme académique", max_length=150, blank=True)
    professional_diploma = models.CharField("diplôme professionnel", max_length=150, blank=True)
    entry_date = models.DateField("entrée dans l'enseignement", null=True, blank=True)
    specialty = models.CharField("spécialité", max_length=150, blank=True)
    function = models.CharField("fonction", max_length=150, blank=True)
    service_start_date = models.DateField(
        "prise de service dans l'établissement", null=True, blank=True
    )
    courses_taught = models.CharField("cours tenu(s)", max_length=255, blank=True)
    class_type = models.CharField("type de classe", max_length=100, blank=True)
    students_count = models.PositiveSmallIntegerField("effectifs", null=True, blank=True)
    contract_type = models.CharField(
        "type de contrat", max_length=15, choices=ContractType.choices, default=ContractType.PERMANENT
    )
    is_active = models.BooleanField("en activité", default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "enseignant"
        verbose_name_plural = "enseignants"
        ordering = ["matricule"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "matricule"], name="unique_matricule_per_school"
            )
        ]

    def __str__(self):
        return f"{self.matricule} — {self.full_name}"

    @property
    def full_name(self):
        """Équivalent de la colonne calculée `B` : Prénom & " " & Nom."""
        return f"{self.first_name} {self.last_name}".strip()

    def save(self, *args, **kwargs):
        # L'établissement doit être connu **avant** le calcul du matricule, qui
        # numérote par établissement. `TenantScopedModel.save()` le renseigne depuis
        # le contexte, mais trop tard pour nous : on le résout donc ici d'abord.
        if self.school_id is None:
            from apps.core.tenancy import get_current_tenant

            tenant = get_current_tenant()
            if tenant is not None:
                self.school = tenant
        if not self.matricule:
            self.matricule = self._next_matricule()
        return super().save(*args, **kwargs)

    def _next_matricule(self):
        """Matricule suivant, sur trois chiffres, à l'échelle de l'établissement.

        `select_for_update` sur les lignes existantes sérialise deux créations
        concurrentes ; sans cela, deux secrétaires enregistrant un enseignant au même
        instant obtiendraient le même matricule. La contrainte d'unicité en base
        reste le garde-fou final.
        """
        if self.school_id is None:
            raise ValueError(
                "L'établissement doit être connu pour attribuer un matricule : "
                "la numérotation est propre à chaque école."
            )
        with transaction.atomic():
            last = (
                Teacher.all_objects.select_for_update()
                .filter(school=self.school_id)
                .order_by("-matricule")
                .first()
            )
            nxt = int(last.matricule) + 1 if last and last.matricule.isdigit() else 1
            return f"{nxt:03d}"


class TeacherContract(TenantScopedModel):
    """Contrat ou avenant, avec pièce jointe."""

    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="contracts")
    reference = models.CharField("référence", max_length=100, blank=True)
    contract_type = models.CharField(max_length=15, choices=Teacher.ContractType.choices)
    start_date = models.DateField("date de début")
    end_date = models.DateField("date de fin", null=True, blank=True)
    gross_salary = models.PositiveIntegerField("salaire brut", **MONEY)
    document = models.FileField("document", upload_to="contracts/", null=True, blank=True)
    notes = models.TextField("notes", blank=True)

    class Meta:
        verbose_name = "contrat"
        ordering = ["-start_date"]


class Absence(TenantScopedModel):
    """Absence ou congé."""

    class Kind(models.TextChoices):
        LEAVE = "LEAVE", "Congé"
        SICK = "SICK", "Maladie"
        UNPAID = "UNPAID", "Absence non rémunérée"
        OTHER = "OTHER", "Autre"

    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="absences")
    kind = models.CharField("nature", max_length=10, choices=Kind.choices)
    start_date = models.DateField("du")
    end_date = models.DateField("au")
    reason = models.CharField("motif", max_length=255, blank=True)

    class Meta:
        verbose_name = "absence"
        ordering = ["-start_date"]


class SalaryRubric(TenantScopedModel):
    """Rubrique salariale — lignes A, B, C de l'onglet « Salaires ».

    C'est une **ventilation comptable** des charges de personnel, distincte du
    bulletin de paie nominatif : le classeur source ne rattache aucune rubrique à un
    employé identifié. Le rattachement facultatif d'un enseignant, ajouté ici, permet
    d'éditer les bulletins individuels demandés par le cahier des charges sans
    rompre la logique d'origine.
    """

    code = models.CharField("code", max_length=10, help_text="A, B, C…")
    label = models.CharField("libellé", max_length=150, blank=True)
    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="salary_rubrics",
        help_text="Facultatif — renseigné si la rubrique correspond à un employé identifié.",
    )
    order = models.PositiveSmallIntegerField("rang", default=0)

    class Meta:
        verbose_name = "rubrique salariale"
        verbose_name_plural = "rubriques salariales"
        ordering = ["order", "code"]
        constraints = [
            models.UniqueConstraint(fields=["school", "code"], name="unique_rubric_per_school")
        ]

    def __str__(self):
        return f"{self.code} — {self.label}" if self.label else self.code


class Salary(TenantScopedModel):
    """Montant d'une rubrique salariale pour un mois de l'exercice.

    `period` est une fin de mois. L'exercice de paie couvre 12 mois (octobre à
    septembre), à la différence des 9 mois de mensualité des élèves.
    """

    rubric = models.ForeignKey(SalaryRubric, on_delete=models.CASCADE, related_name="entries")
    year = models.ForeignKey(SchoolYear, on_delete=models.PROTECT, related_name="salaries")
    period = models.DateField("période", help_text="Dernier jour du mois concerné.")
    gross_amount = models.PositiveIntegerField("brut", **MONEY)
    social_contributions = models.PositiveIntegerField("cotisations sociales", **MONEY)
    other_deductions = models.PositiveIntegerField("autres retenues", **MONEY)
    paid_at = models.DateField("date de paiement", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "salaire"
        verbose_name_plural = "salaires"
        ordering = ["period", "rubric__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["rubric", "period"], name="unique_salary_per_rubric_period"
            )
        ]
        indexes = [models.Index(fields=["school", "year", "period"])]

    def __str__(self):
        return f"{self.rubric} — {self.period:%m/%Y}"

    @property
    def net_amount(self):
        return self.gross_amount - self.social_contributions - self.other_deductions


class SalaryRaise(TenantScopedModel):
    """Historique des augmentations."""

    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="raises")
    effective_date = models.DateField("date d'effet")
    previous_amount = models.PositiveIntegerField("montant précédent", **MONEY)
    new_amount = models.PositiveIntegerField("nouveau montant", **MONEY)
    reason = models.CharField("motif", max_length=255, blank=True)
    approved_by = models.CharField("approuvé par", max_length=150, blank=True)

    class Meta:
        verbose_name = "augmentation"
        ordering = ["-effective_date"]
