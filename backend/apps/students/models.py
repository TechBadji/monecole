from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import SchoolYear
from apps.core.tenancy import TenantScopedModel

# Montants : entiers. Le franc CFA n'a pas de subdivision décimale en pratique, et
# un entier écarte d'emblée toute dérive d'arrondi sur les agrégats financiers.
MONEY = {"validators": [MinValueValidator(0)], "default": 0}


class Level(models.TextChoices):
    PRESCHOOL = "PRESCHOOL", "Préscolaire"
    PRIMARY = "PRIMARY", "Élémentaire"


class ClassRoom(TenantScopedModel):
    """Classe. Les dix classes du classeur source, dans l'ordre pédagogique."""

    name = models.CharField("nom", max_length=30)
    level = models.CharField("cycle", max_length=20, choices=Level.choices)
    order = models.PositiveSmallIntegerField(
        "rang", default=0, help_text="Ordre d'affichage, de la garderie au CM2."
    )
    capacity = models.PositiveSmallIntegerField("capacité", null=True, blank=True)

    class Meta:
        verbose_name = "classe"
        ordering = ["order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="unique_class_per_school")
        ]

    def __str__(self):
        return self.name


class Family(TenantScopedModel):
    """Famille — regroupe une fratrie sous un même payeur.

    Permet de consolider la facturation et d'appliquer une réduction « famille
    nombreuse » à l'échelle du foyer plutôt qu'élève par élève.
    """

    name = models.CharField("nom de famille", max_length=150)
    primary_contact = models.CharField("contact principal", max_length=150)
    phone = models.CharField("téléphone", max_length=30, blank=True)
    phone_e164 = models.CharField(
        "téléphone normalisé", max_length=20, blank=True, db_index=True, editable=False
    )
    email = models.EmailField(blank=True)
    address = models.CharField("adresse", max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "famille"
        verbose_name_plural = "familles"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        from apps.notifications.sms import normalize_phone

        self.phone_e164 = normalize_phone(self.phone) if self.phone else ""
        return super().save(*args, **kwargs)


class StudentStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Actif"
    TRANSFERRED = "TRANSFERRED", "Transféré"
    EXPELLED = "EXPELLED", "Exclu"
    DROPPED = "DROPPED", "Abandon"
    GRADUATED = "GRADUATED", "Diplômé"


class Student(TenantScopedModel):
    """Élève.

    Le statut et sa date d'effet permettent de ne pas fausser les effectifs en cours
    d'année : un élève parti en février reste comptabilisé jusqu'à cette date, et
    ses encaissements antérieurs demeurent acquis.
    """

    matricule = models.CharField(
        "matricule",
        max_length=10,
        default="",
        editable=False,
        help_text="Format MXXXX, attribué à l'inscription et conservé pour tout "
        "le cursus, même en cas de changement de classe ou de redoublement.",
    )
    first_name = models.CharField("prénom", max_length=100)
    last_name = models.CharField("nom", max_length=100)
    date_of_birth = models.DateField("date de naissance", null=True, blank=True)
    sex = models.CharField(
        "sexe", max_length=1, choices=[("M", "Masculin"), ("F", "Féminin")], blank=True
    )
    classroom = models.ForeignKey(
        ClassRoom, on_delete=models.PROTECT, related_name="students", verbose_name="classe"
    )
    family = models.ForeignKey(
        Family, on_delete=models.SET_NULL, null=True, blank=True, related_name="students"
    )
    parent_name = models.CharField("parent / tuteur", max_length=150, blank=True)
    parent_phone = models.CharField("téléphone du parent", max_length=30, blank=True)
    parent_phone_e164 = models.CharField(
        "téléphone normalisé",
        max_length=20,
        blank=True,
        db_index=True,
        editable=False,
        help_text="Forme « 221XXXXXXXXX », dérivée de parent_phone. Sert au "
        "rattachement du portail parent : les numéros sont saisis dans des "
        "formats trop variés pour être comparés tels quels.",
    )
    parent_email = models.EmailField("email du parent", blank=True)
    address = models.CharField("adresse", max_length=255, blank=True)
    enrollment_date = models.DateField("date d'inscription", null=True, blank=True)
    status = models.CharField(
        "statut", max_length=20, choices=StudentStatus.choices, default=StudentStatus.ACTIVE
    )
    status_effective_date = models.DateField("date d'effet du statut", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "élève"
        verbose_name_plural = "élèves"
        ordering = ["last_name", "first_name"]
        indexes = [models.Index(fields=["school", "classroom", "status"])]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "matricule"], name="unique_student_matricule_per_school"
            )
        ]

    def __str__(self):
        return f"{self.matricule} — {self.full_name}" if self.matricule else self.full_name

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_active(self):
        return self.status == StudentStatus.ACTIVE

    def save(self, *args, **kwargs):
        from apps.notifications.sms import normalize_phone

        self.parent_phone_e164 = normalize_phone(self.parent_phone) if self.parent_phone else ""

        # L'établissement doit être connu avant le calcul du matricule, qui
        # numérote par école. `TenantScopedModel.save()` le renseigne depuis le
        # contexte, mais trop tard pour nous.
        if self.school_id is None:
            from apps.core.tenancy import get_current_tenant

            tenant = get_current_tenant()
            if tenant is not None:
                self.school = tenant
        if not self.matricule:
            self.matricule = self._next_matricule()

        return super().save(*args, **kwargs)

    def _next_matricule(self):
        """Matricule suivant au format MXXXX, propre à l'établissement.

        `select_for_update` sérialise deux inscriptions concurrentes : sans cela,
        deux secrétaires enregistrant un élève au même instant obtiendraient le
        même numéro. La contrainte d'unicité reste le garde-fou final.
        """
        from django.db import transaction

        if self.school_id is None:
            raise ValueError(
                "L'établissement doit être connu pour attribuer un matricule : "
                "la numérotation est propre à chaque école."
            )
        with transaction.atomic():
            last = (
                Student.all_objects.select_for_update()
                .filter(school=self.school_id, matricule__startswith="M")
                .order_by("-matricule")
                .first()
            )
            nxt = 1
            if last and last.matricule[1:].isdigit():
                nxt = int(last.matricule[1:]) + 1
            return f"M{nxt:04d}"

    @classmethod
    def assign_matricules(cls, students, school):
        """Attribue les matricules d'un lot avant `bulk_create`.

        `bulk_create` court-circuite `save()` : sans cet appel, tous les élèves du
        lot partiraient avec un matricule vide et se heurteraient à la contrainte
        d'unicité. Les chemins d'insertion en masse — import, seed, tests — doivent
        passer par ici.
        """
        from django.db import transaction

        with transaction.atomic():
            last = (
                cls.all_objects.select_for_update()
                .filter(school=school, matricule__startswith="M")
                .order_by("-matricule")
                .first()
            )
            nxt = int(last.matricule[1:]) + 1 if last and last.matricule[1:].isdigit() else 1
            for offset, student in enumerate(students):
                if not student.matricule:
                    student.matricule = f"M{nxt + offset:04d}"
        return students

    @property
    def qr_payload(self):
        """Contenu du QR code de l'élève.

        ⚠️ Décision explicite du client (30/07/2026) : les données sont en clair,
        pour que le badge reste scannable hors ligne et sans compte. Le risque a
        été exposé et assumé — une carte perdue révèle l'identité d'un mineur, sa
        date de naissance et le numéro de son parent. Ce n'est pas un oubli.
        L'alternative (jeton signé résolu par l'API) reste implémentable sans
        changer le reste du module : seul ce champ et le scanner évolueraient.
        """
        birth = self.date_of_birth.isoformat() if self.date_of_birth else ""
        return "|".join([
            self.matricule,
            self.last_name,
            self.first_name,
            birth,
            self.parent_phone_e164 or "",
        ])


class ClassEnrollmentHistory(TenantScopedModel):
    """Historique des changements de classe et des redoublements.

    Le changement de classe en cours d'année ne doit pas effacer l'historique de
    paiement : les encaissements restent rattachés à l'élève, pas à la classe.
    """

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="class_history")
    year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE)
    from_classroom = models.ForeignKey(
        ClassRoom, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    to_classroom = models.ForeignKey(ClassRoom, on_delete=models.PROTECT, related_name="+")
    effective_date = models.DateField("date d'effet")
    is_repeat = models.BooleanField("redoublement", default=False)
    reason = models.CharField("motif", max_length=255, blank=True)

    class Meta:
        verbose_name = "changement de classe"
        verbose_name_plural = "changements de classe"
        ordering = ["-effective_date"]


class FeeSchedule(TenantScopedModel):
    """Tarifs d'une classe pour une année donnée.

    Absent du classeur source, qui n'enregistre que les sommes *reçues* et ne permet
    donc pas de distinguer un paiement partiel d'un paiement complet. Ce référentiel
    fournit le montant *dû*, sans lequel ni les arriérés, ni les échéanciers, ni les
    relances exigés par le cahier des charges ne sont calculables.
    """

    classroom = models.ForeignKey(ClassRoom, on_delete=models.CASCADE, related_name="fee_schedules")
    year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE, related_name="fee_schedules")
    registration_fee = models.PositiveIntegerField("frais d'inscription", **MONEY)
    monthly_tuition = models.PositiveIntegerField("mensualité", **MONEY)
    monthly_canteen = models.PositiveIntegerField("cantine mensuelle", **MONEY)
    monthly_reinforcement = models.PositiveIntegerField("renforcement mensuel", **MONEY)
    uniform_fee = models.PositiveIntegerField("uniforme", **MONEY)
    insurance_fee = models.PositiveIntegerField("assurance", **MONEY)
    ape_fee = models.PositiveIntegerField("cotisation APE", **MONEY)

    class Meta:
        verbose_name = "grille tarifaire"
        verbose_name_plural = "grilles tarifaires"
        ordering = ["classroom__order"]
        constraints = [
            models.UniqueConstraint(
                fields=["classroom", "year"], name="unique_fee_schedule_per_class_year"
            )
        ]

    def __str__(self):
        return f"{self.classroom} — {self.year}"


class Enrollment(TenantScopedModel):
    """Inscription d'un élève pour une année scolaire.

    Reprend le bloc « TOTAL INSCRIPTION » des onglets de classe (colonnes H à L) :
    inscription payée, montant, uniforme, assurance, APE.
    """

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    year = models.ForeignKey(SchoolYear, on_delete=models.PROTECT, related_name="enrollments")
    classroom = models.ForeignKey(
        ClassRoom,
        on_delete=models.PROTECT,
        related_name="enrollments",
        help_text="Classe à l'inscription — l'élève peut changer de classe ensuite.",
    )
    registration_paid = models.BooleanField("inscription réglée", default=False)
    registration_amount = models.PositiveIntegerField("montant inscription", **MONEY)
    uniform_amount = models.PositiveIntegerField("uniforme", **MONEY)
    insurance_amount = models.PositiveIntegerField("assurance", **MONEY)
    ape_amount = models.PositiveIntegerField("APE", **MONEY)
    paid_at = models.DateField("date de règlement", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "inscription"
        ordering = ["-year__start_date", "student__last_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "year"], name="unique_enrollment_per_student_year"
            )
        ]
        indexes = [models.Index(fields=["school", "year", "classroom"])]

    def __str__(self):
        return f"{self.student} — {self.year}"

    @property
    def total_received(self):
        """Total encaissé à l'inscription.

        Attention : seul `registration_amount` alimente la ligne « TOTAL INSCRIPTION
        REÇUE » du bilan (`ENCAIS!E` reporte `I8`, la colonne *Montant inscription*).
        Uniforme, assurance et APE sont suivis mais hors chiffre d'affaires — voir
        `docs/modele-excel.md`.
        """
        return (
            self.registration_amount
            + self.uniform_amount
            + self.insurance_amount
            + self.ape_amount
        )


class MonthlyPayment(TenantScopedModel):
    """Encaissements d'un élève pour un mois donné.

    Une ligne par élève et par mois, portant les quatre postes récurrents des onglets
    de classe — mensualité (M:U), cantine (W:AE), renforcement (AG:AO) et uniforme
    en cours d'année (AQ:AY). La disposition « large » du tableur (36 colonnes) est
    ainsi normalisée sans perte d'information.

    `period` est une **fin de mois**, conformément à la convention `EOMONTH` du
    classeur (voir `apps.core.periods`).
    """

    class Method(models.TextChoices):
        CASH = "CASH", "Espèces"
        MOBILE_MONEY = "MOBILE_MONEY", "Mobile money"
        TRANSFER = "TRANSFER", "Virement"
        CHECK = "CHECK", "Chèque"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="monthly_payments")
    year = models.ForeignKey(SchoolYear, on_delete=models.PROTECT, related_name="monthly_payments")
    period = models.DateField("période", help_text="Dernier jour du mois concerné.")
    tuition = models.PositiveIntegerField("mensualité", **MONEY)
    canteen = models.PositiveIntegerField("cantine", **MONEY)
    reinforcement = models.PositiveIntegerField("renforcement", **MONEY)
    uniform = models.PositiveIntegerField("uniforme", **MONEY)
    payment_date = models.DateField("date de paiement", null=True, blank=True)
    method = models.CharField("moyen", max_length=20, choices=Method.choices, default=Method.CASH)
    reference = models.CharField("référence", max_length=100, blank=True)
    received_by = models.CharField("encaissé par", max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "encaissement mensuel"
        verbose_name_plural = "encaissements mensuels"
        ordering = ["period", "student__last_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "period"], name="unique_payment_per_student_period"
            )
        ]
        indexes = [models.Index(fields=["school", "year", "period"])]

    def __str__(self):
        return f"{self.student} — {self.period:%m/%Y}"

    @property
    def total(self):
        return self.tuition + self.canteen + self.reinforcement + self.uniform


class Discount(TenantScopedModel):
    """Réduction ou bourse, accordée à un élève ou à une famille.

    Traçable : motif et approbateur sont obligatoires côté sérialiseur, une remise
    non justifiée étant un angle mort classique du contrôle interne.
    """

    class Kind(models.TextChoices):
        PERCENT = "PERCENT", "Pourcentage"
        FIXED = "FIXED", "Montant fixe"
        FULL = "FULL", "Bourse totale"

    class Scope(models.TextChoices):
        REGISTRATION = "REGISTRATION", "Inscription"
        TUITION = "TUITION", "Mensualité"
        BOTH = "BOTH", "Inscription et mensualité"

    class Category(models.TextChoices):
        """Nature de la réduction.

        La distinction n'est pas cosmétique : le bilan chiffre séparément l'effort
        social de l'établissement (`SOCIAL`) et les gestes commerciaux ou
        familiaux. Les confondre empêcherait l'administration de savoir ce que ses
        bourses lui coûtent réellement.
        """

        SOCIAL = "SOCIAL", "Bourse sociale"
        SIBLING = "SIBLING", "Réduction fratrie"
        STAFF = "STAFF", "Enfant du personnel"
        MERIT = "MERIT", "Bourse au mérite"
        OTHER = "OTHER", "Autre"

    student = models.ForeignKey(
        Student, on_delete=models.CASCADE, null=True, blank=True, related_name="discounts"
    )
    family = models.ForeignKey(
        Family, on_delete=models.CASCADE, null=True, blank=True, related_name="discounts"
    )
    year = models.ForeignKey(SchoolYear, on_delete=models.CASCADE, related_name="discounts")
    kind = models.CharField("type", max_length=10, choices=Kind.choices)
    category = models.CharField(
        "nature", max_length=15, choices=Category.choices, default=Category.SOCIAL
    )
    scope = models.CharField("portée", max_length=15, choices=Scope.choices, default=Scope.BOTH)
    value = models.PositiveIntegerField(
        "valeur", **MONEY, help_text="Pourcentage de 0 à 100, ou montant en devise."
    )
    reason = models.CharField("motif", max_length=255)
    approved_by = models.CharField("approuvé par", max_length=150)
    approved_at = models.DateField("date d'approbation", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "réduction"
        verbose_name_plural = "réductions"
        ordering = ["-created_at"]
        constraints = [
            # Une réduction porte sur un élève ou sur une famille, jamais sur les deux
            # ni sur aucun des deux : sinon le montant à déduire est indéterminé.
            models.CheckConstraint(
                check=(
                    models.Q(student__isnull=False, family__isnull=True)
                    | models.Q(student__isnull=True, family__isnull=False)
                ),
                name="discount_targets_student_xor_family",
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.value} — {self.student or self.family}"

    @property
    def is_scholarship(self):
        """Bourse à proprement parler, par opposition à un geste commercial."""
        return self.category in (self.Category.SOCIAL, self.Category.MERIT)

    def apply_to(self, amount):
        """Montant après application de la réduction."""
        if self.kind == self.Kind.FULL:
            return 0
        if self.kind == self.Kind.PERCENT:
            return max(0, amount - (amount * min(self.value, 100)) // 100)
        return max(0, amount - self.value)
