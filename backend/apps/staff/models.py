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
    phone = models.CharField("téléphone", max_length=30, blank=True)
    email = models.EmailField("email", blank=True)
    address = models.CharField("adresse", max_length=255, blank=True)
    emergency_contact = models.CharField(
        "numéro de secours", max_length=60, blank=True,
        help_text="Personne à joindre en cas d'urgence.",
    )
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


class PayrollScale(TenantScopedModel):
    """Barèmes de paie applicables à partir d'une date.

    Stockés en base et datés plutôt que codés en dur : IPRES, CSS, IR et TRIMF
    relèvent de la loi de finances et changent d'une année sur l'autre. Recalculer
    un bulletin de l'exercice précédent doit donner le même résultat qu'à l'époque,
    ce qui impose de conserver les barèmes historiques plutôt que de les écraser.

    Les valeurs par défaut sont celles du schéma sénégalais courant — elles doivent
    être validées par un expert-comptable avant tout usage réel.
    """

    label = models.CharField("libellé", max_length=100, help_text="Par exemple : Barème 2026")
    effective_from = models.DateField("applicable à partir du")
    values = models.JSONField("barèmes", default=dict)
    validated_by = models.CharField(
        "validé par", max_length=150, blank=True,
        help_text="Expert-comptable ayant vérifié les taux. Vide = non validé.",
    )
    notes = models.TextField("notes", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "barème de paie"
        verbose_name_plural = "barèmes de paie"
        ordering = ["-effective_from"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "effective_from"], name="unique_scale_per_date"
            )
        ]

    def __str__(self):
        return f"{self.label} (dès le {self.effective_from:%d/%m/%Y})"

    @property
    def is_validated(self):
        return bool(self.validated_by)

    def save(self, *args, **kwargs):
        if not self.values:
            from .payroll import default_scale_values

            self.values = default_scale_values()
        return super().save(*args, **kwargs)

    @classmethod
    def applicable(cls, date):
        """Barème en vigueur à une date. Crée le barème par défaut si aucun n'existe."""
        scale = cls.objects.filter(effective_from__lte=date).order_by("-effective_from").first()
        if scale is None:
            scale = cls.objects.order_by("effective_from").first()
        return scale


class PayrollProfile(TenantScopedModel):
    """Éléments de paie propres à un employé."""

    class FamilyShares(models.TextChoices):
        S1 = "1", "1 part"
        S15 = "1.5", "1,5 part"
        S2 = "2", "2 parts"
        S25 = "2.5", "2,5 parts"
        S3 = "3", "3 parts"
        S35 = "3.5", "3,5 parts"
        S4 = "4", "4 parts"
        S45 = "4.5", "4,5 parts"
        S5 = "5", "5 parts"

    teacher = models.OneToOneField(
        Teacher, on_delete=models.CASCADE, related_name="payroll_profile"
    )
    base_salary = models.PositiveIntegerField("salaire de base mensuel", **MONEY)
    taxable_bonus = models.PositiveIntegerField("primes imposables", **MONEY)
    non_taxable_allowance = models.PositiveIntegerField(
        "indemnités non imposables", **MONEY,
        help_text="Transport et assimilés, dans la limite d'exonération légale.",
    )
    is_executive = models.BooleanField(
        "cadre", default=False,
        help_text="Assujettit au régime complémentaire IPRES cadres.",
    )
    family_shares = models.CharField(
        "parts fiscales", max_length=4, choices=FamilyShares.choices, default=FamilyShares.S1
    )
    social_security_number = models.CharField("n° de sécurité sociale", max_length=40, blank=True)
    bank_account = models.CharField("compte bancaire", max_length=40, blank=True)

    class Meta:
        verbose_name = "profil de paie"
        verbose_name_plural = "profils de paie"
        ordering = ["teacher__matricule"]

    def __str__(self):
        return f"Paie — {self.teacher.full_name}"

    @property
    def gross(self):
        return self.base_salary + self.taxable_bonus


class Payslip(TenantScopedModel):
    """Bulletin de paie nominatif d'un mois.

    Le détail du calcul est figé dans `computation` à l'émission. Un bulletin remis
    à un employé doit rester reproductible à l'identique, même si le barème, le
    salaire ou les parts fiscales changent ensuite.
    """

    teacher = models.ForeignKey(Teacher, on_delete=models.PROTECT, related_name="payslips")
    year = models.ForeignKey(SchoolYear, on_delete=models.PROTECT, related_name="payslips")
    scale = models.ForeignKey(PayrollScale, on_delete=models.PROTECT, related_name="payslips")
    period = models.DateField("période", help_text="Dernier jour du mois concerné.")

    gross = models.PositiveIntegerField("brut imposable", **MONEY)
    non_taxable = models.PositiveIntegerField("indemnités non imposables", **MONEY)
    employee_contributions = models.PositiveIntegerField("cotisations salariales", **MONEY)
    employer_contributions = models.PositiveIntegerField("charges patronales", **MONEY)
    income_tax = models.PositiveIntegerField("impôt sur le revenu", **MONEY)
    trimf = models.PositiveIntegerField("TRIMF", **MONEY)
    other_deductions = models.PositiveIntegerField("autres retenues", **MONEY)
    net_pay = models.PositiveIntegerField("net à payer", **MONEY)

    computation = models.JSONField("détail du calcul", default=dict)
    paid_at = models.DateField("payé le", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "bulletin de paie"
        verbose_name_plural = "bulletins de paie"
        ordering = ["-period", "teacher__matricule"]
        constraints = [
            models.UniqueConstraint(
                fields=["teacher", "period"], name="one_payslip_per_teacher_period"
            )
        ]
        indexes = [models.Index(fields=["school", "year", "period"])]

    def __str__(self):
        return f"{self.teacher.full_name} — {self.period:%m/%Y}"

    @property
    def employer_cost(self):
        return self.gross + self.employer_contributions
