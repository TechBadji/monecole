from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import SchoolYear
from apps.core.tenancy import TenantScopedModel

MONEY = {"validators": [MinValueValidator(0)], "default": 0}

# Rubriques de charge du « Rapport Bilan », dans l'ordre des lignes 18 à 34.
# Le libellé sert de clé de jointure au tableur (`SUMIFS` sur `DEPENSES!J`) ; en base,
# c'est `code` qui joue ce rôle, ce qui permet de corriger un libellé sans casser
# l'historique.
DEFAULT_EXPENSE_CATEGORIES = [
    ("SALARY_ARREARS", "ARRIERE SALAIRE PAYE"),
    ("RENT", "LOCATIONS DE BÂTIMENTS"),
    ("SALARY", "SALAIRE"),
    ("WATER", "EAU EXPLOITATION - SEN'EAU"),
    ("ELECTRICITY", "ELECTRICITÉ EXPLOITATION - SENELEC"),
    ("SUPPLIES", "FOURNITURES D'ENTRETIEN, DE BUREAU ET SCOLAIRE"),
    ("SMALL_EQUIPMENT", "AUTRE PETIT MATÉRIEL"),
    ("TEACHING_EQUIPMENT", "MATÉRIELS ET ÉQUIPEMENTS PEDAGOGIQUE"),
    ("MAINTENANCE", "TRAVAUX, ENTRETIEN ET RÉPARATIONS"),
    ("TRANSPORT", "TRANSPORTS FG"),
    ("INSURANCE", "ASSURANCES"),
    ("ADVERTISING", "PUBLICITE, PUBLICATIONS, RELATIONS PUBLIQUES"),
    ("ADMIN_CHARGES", "CHARGES ADMINISTRATIVES - DOSSIERS DE REGULARISATION"),
    ("TELECOM", "TELECOMMUNICATIONS"),
    ("TRAINING", "FRAIS DE FORMATION DU PERSONNEL"),
    ("HOSPITALITY", "FRAIS DE RÉCEPTIONS - RESTAURATION"),
]

# Ligne 32 du bilan, « FRAIS BANCAIRES ET TRANSFERT ». Ce n'est pas une catégorie :
# sa formule somme la colonne `frais de transfert` de *toutes* les dépenses du mois,
# sans filtre de catégorie. Elle est donc calculée par le service de reporting et
# n'existe pas comme `ExpenseCategory`.
TRANSFER_FEES_CODE = "BANK_TRANSFER_FEES"
TRANSFER_FEES_LABEL = "FRAIS BANCAIRES ET TRANSFERT"


class ExpenseCategory(TenantScopedModel):
    """Rubrique de charge du bilan."""

    code = models.CharField("code", max_length=30)
    label = models.CharField("libellé", max_length=150)
    order = models.PositiveSmallIntegerField("rang", default=0)
    is_active = models.BooleanField("active", default=True)
    monthly_budget = models.PositiveIntegerField(
        "budget mensuel", null=True, blank=True, help_text="Sert au comparatif prévu / réalisé."
    )

    class Meta:
        verbose_name = "rubrique de charge"
        verbose_name_plural = "rubriques de charge"
        ordering = ["order", "label"]
        constraints = [
            models.UniqueConstraint(fields=["school", "code"], name="unique_category_per_school")
        ]

    def __str__(self):
        return self.label


class Expense(TenantScopedModel):
    """Dépense — onglet « DEPENSES ».

    `period` reproduit la colonne calculée `B` (`EOMONTH(date_opération)`), clé de
    jointure des `SUMIFS` du bilan. Elle est dérivée de `operation_date` à
    l'enregistrement, jamais saisie : c'est ce qui garantit que le rattachement
    comptable d'une dépense ne peut pas diverger de sa date d'opération.
    """

    class Channel(models.TextChoices):
        CASH = "CASH", "Espèces"
        MOBILE_MONEY = "MOBILE_MONEY", "Mobile money"
        TRANSFER = "TRANSFER", "Virement"
        CHECK = "CHECK", "Chèque"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Brouillon"
        PENDING = "PENDING", "En attente de validation"
        APPROVED = "APPROVED", "Validée"
        REJECTED = "REJECTED", "Rejetée"

    year = models.ForeignKey(SchoolYear, on_delete=models.PROTECT, related_name="expenses")
    operation_date = models.DateField("date d'opération")
    payment_date = models.DateField("date de paiement", null=True, blank=True)
    period = models.DateField("période", editable=False, db_index=True)
    channel = models.CharField("canal", max_length=20, choices=Channel.choices, default=Channel.CASH)
    invoice_number = models.CharField("n° de facture", max_length=100, blank=True)
    label = models.CharField("intitulé", max_length=255)
    amount = models.PositiveIntegerField("montant", **MONEY)
    transfer_fee = models.PositiveIntegerField("frais de transfert", **MONEY)
    category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, related_name="expenses", verbose_name="rubrique"
    )
    receipt = models.FileField("justificatif", upload_to="receipts/", null=True, blank=True)
    status = models.CharField(
        "statut", max_length=10, choices=Status.choices, default=Status.APPROVED
    )
    approved_by = models.CharField("validée par", max_length=150, blank=True)
    approved_at = models.DateTimeField("validée le", null=True, blank=True)
    recurring_template = models.ForeignKey(
        "RecurringExpense", on_delete=models.SET_NULL, null=True, blank=True, related_name="generated"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "dépense"
        verbose_name_plural = "dépenses"
        ordering = ["-operation_date", "-id"]
        indexes = [models.Index(fields=["school", "year", "period", "category"])]

    def __str__(self):
        return f"{self.label} — {self.amount}"

    def save(self, *args, **kwargs):
        from apps.core.periods import end_of_month

        self.period = end_of_month(self.operation_date)
        return super().save(*args, **kwargs)

    @property
    def total_cost(self):
        return self.amount + self.transfer_fee


class RecurringExpense(TenantScopedModel):
    """Dépense récurrente — génère un brouillon mensuel (loyer, abonnements…)."""

    label = models.CharField("intitulé", max_length=255)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name="recurrences")
    amount = models.PositiveIntegerField("montant", **MONEY)
    channel = models.CharField(max_length=20, choices=Expense.Channel.choices, default=Expense.Channel.TRANSFER)
    day_of_month = models.PositiveSmallIntegerField("jour du mois", default=1)
    start_date = models.DateField("à partir du")
    end_date = models.DateField("jusqu'au", null=True, blank=True)
    is_active = models.BooleanField("active", default=True)

    class Meta:
        verbose_name = "dépense récurrente"
        verbose_name_plural = "dépenses récurrentes"
        ordering = ["label"]

    def __str__(self):
        return self.label


class OtherIncome(TenantScopedModel):
    """Autre produit — ligne 14 « AUTRE PRODUIT » du bilan.

    Saisie libre dans le classeur ; ici, une écriture datée et justifiée. C'est
    notamment ce qui porte les apports d'actionnaires mentionnés dans le commentaire
    de bilan de l'exercice précédent.
    """

    year = models.ForeignKey(SchoolYear, on_delete=models.PROTECT, related_name="other_incomes")
    operation_date = models.DateField("date d'opération")
    period = models.DateField("période", editable=False, db_index=True)
    label = models.CharField("intitulé", max_length=255)
    amount = models.PositiveIntegerField("montant", **MONEY)
    channel = models.CharField(max_length=20, choices=Expense.Channel.choices, default=Expense.Channel.CASH)
    reference = models.CharField("référence", max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "autre produit"
        verbose_name_plural = "autres produits"
        ordering = ["-operation_date"]

    def __str__(self):
        return f"{self.label} — {self.amount}"

    def save(self, *args, **kwargs):
        from apps.core.periods import end_of_month

        self.period = end_of_month(self.operation_date)
        return super().save(*args, **kwargs)
