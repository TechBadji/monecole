"""Calcul de paie sénégalais.

Chaque montant attendu est **calculé à la main dans le test**, tranche par tranche.
Réutiliser `compute_payslip` pour produire la valeur de référence ne prouverait
rien : une erreur de raisonnement serait reproduite des deux côtés.

Rappel du barème vérifié ici (valeurs par défaut, cf. `apps/staff/payroll.py`) :

    IPRES RG      5,6 % salarié / 8,4 % employeur, assiette plafonnée à 432 000
    IPRES cadres  2,4 % / 3,6 %, plafond 1 296 000
    CSS           7 % + 1 % employeur seul, plafond 63 000
    Abattement    30 % du brut après cotisations, plafonné à 900 000 par an
    IR            0 / 20 / 30 / 35 / 37 / 40 % par tranches annuelles
    TRIMF         forfait annuel par tranche de revenu
"""

from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import Role
from apps.core.tenancy import tenant_context
from apps.core.tests.factories import make_school, make_user, make_year
from apps.staff.models import PayrollProfile, PayrollScale, Payslip, Teacher
from apps.staff.payroll import compute_payslip, default_scale_values


class PayrollComputationTests(TestCase):
    """Le calcul lui-même, sans base de données."""

    def setUp(self):
        self.scale = default_scale_values()

    def compute(self, **kwargs):
        return compute_payslip(scale=self.scale, **kwargs).as_dict()

    def test_reference_case_350000_two_shares(self):
        """Cas de référence, entièrement vérifié à la main.

            Brut ................................. 350 000
            IPRES RG  5,6 % × 350 000 ............. -19 600
            Brut après cotisations ................ 330 400
            Annualisé × 12 ...................... 3 964 800
            Abattement 30 % = 1 189 440, plafonné . -900 000
            Net imposable annuel ................ 3 064 800
            IR : 20 % × (1 500 000 − 630 000) ..... 174 000
                 30 % × (3 064 800 − 1 500 000) ... 469 440
                 total ............................ 643 440
            Réduction 2 parts : 15 % = 96 516,
                 relevée au plancher .............. 200 000
            IR net annuel ......................... 443 440  → 36 953 / mois
            TRIMF tranche 2 M–7 M : 12 000 / an ... 1 000 / mois
            Net = 350 000 − 19 600 − 36 953 − 1 000 + 25 000 = 317 447
        """
        result = self.compute(gross=350_000, non_taxable=25_000, family_shares="2")

        self.assertEqual(result["total_employee"], 19_600)
        self.assertEqual(result["taxable_income_annual"], 3_064_800)
        self.assertEqual(result["income_tax"], 36_953)
        self.assertEqual(result["trimf"], 1_000)
        self.assertEqual(result["net_pay"], 317_447)

    def test_employer_contributions_and_total_cost(self):
        """IPRES 8,4 % × 350 000 = 29 400 ; CSS (7 % + 1 %) × 63 000 = 5 040."""
        result = self.compute(gross=350_000)
        self.assertEqual(result["total_employer"], 29_400 + 4_410 + 630)
        self.assertEqual(result["employer_cost"], 350_000 + 34_440)

    def test_ipres_base_is_capped(self):
        """Au-delà de 432 000, l'assiette IPRES ne suit plus le salaire."""
        result = self.compute(gross=800_000)
        ipres = next(l for l in result["lines"] if "général" in l["label"])
        self.assertEqual(ipres["base"], 432_000)
        self.assertEqual(ipres["employee"], 24_192)  # 5,6 % × 432 000

    def test_css_base_is_capped_at_63000(self):
        result = self.compute(gross=800_000)
        css = next(l for l in result["lines"] if "familiales" in l["label"])
        self.assertEqual(css["base"], 63_000)
        self.assertEqual(css["employee"], 0, "La CSS n'est pas retenue au salarié.")
        self.assertEqual(css["employer"], 4_410)

    def test_executive_pays_the_supplementary_scheme(self):
        standard = self.compute(gross=600_000)
        executive = self.compute(gross=600_000, is_executive=True)

        # 2,4 % × 600 000 = 14 400 de cotisation salariale supplémentaire.
        self.assertEqual(
            executive["total_employee"] - standard["total_employee"], 14_400
        )
        self.assertLess(executive["net_pay"], standard["net_pay"])

    def test_low_salary_pays_no_income_tax(self):
        """Sous le seuil de 630 000 annuels de net imposable, l'IR est nul."""
        result = self.compute(gross=60_000)
        self.assertEqual(result["income_tax"], 0)
        self.assertGreater(result["trimf"], 0, "Le TRIMF reste dû.")

    def test_more_shares_lower_the_tax(self):
        """La réduction pour charges de famille doit être monotone."""
        taxes = [
            self.compute(gross=500_000, family_shares=shares)["income_tax"]
            for shares in ("1", "2", "3", "4", "5")
        ]
        self.assertEqual(taxes, sorted(taxes, reverse=True))
        self.assertLess(taxes[-1], taxes[0])

    def test_relief_never_makes_the_tax_negative(self):
        """Le plancher de réduction ne doit pas produire un impôt négatif."""
        for gross in (70_000, 90_000, 120_000):
            result = self.compute(gross=gross, family_shares="5")
            self.assertGreaterEqual(result["income_tax"], 0, f"brut {gross}")

    def test_professional_allowance_is_capped(self):
        """Au-delà d'un certain brut, l'abattement plafonne à 900 000 par an."""
        high = self.compute(gross=1_000_000)
        gross_after = (1_000_000 - high["total_employee"]) * 12
        self.assertEqual(high["taxable_income_annual"], gross_after - 900_000)

    def test_non_taxable_allowance_bears_no_charge(self):
        """L'indemnité exonérée s'ajoute au net sans modifier l'impôt."""
        without = self.compute(gross=300_000)
        with_allowance = self.compute(gross=300_000, non_taxable=25_000)

        self.assertEqual(with_allowance["income_tax"], without["income_tax"])
        self.assertEqual(with_allowance["total_employee"], without["total_employee"])
        self.assertEqual(with_allowance["net_pay"], without["net_pay"] + 25_000)

    def test_other_deductions_reduce_only_the_net(self):
        result = self.compute(gross=300_000, other_deductions=20_000)
        reference = self.compute(gross=300_000)
        self.assertEqual(result["net_pay"], reference["net_pay"] - 20_000)
        self.assertEqual(result["income_tax"], reference["income_tax"])

    def test_net_is_always_below_gross_plus_allowance(self):
        for gross in (50_000, 150_000, 350_000, 700_000, 1_500_000):
            result = self.compute(gross=gross, non_taxable=25_000)
            self.assertLess(result["net_pay"], gross + 25_000, f"brut {gross}")
            self.assertGreater(result["net_pay"], 0, f"brut {gross}")

    def test_progressive_brackets_are_not_applied_to_the_whole_income(self):
        """Chaque tranche n'est imposée qu'à son propre taux.

        Un revenu franchissant tout juste un seuil ne doit pas voir l'ensemble de
        son revenu basculer au taux supérieur.
        """
        below = self.compute(gross=200_000)
        above = self.compute(gross=205_000)
        extra_tax = above["income_tax"] - below["income_tax"]
        self.assertLess(
            extra_tax, 5_000,
            "5 000 F de brut supplémentaire ne peuvent pas coûter plus en impôt.",
        )


class PayslipGenerationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.year = make_year(cls.school)
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")
        cls.accountant = make_user(cls.school, Role.ACCOUNTANT, "compta@test.sn")

        with tenant_context(cls.school):
            cls.scale = PayrollScale.objects.create(
                school=cls.school, label="Barème test",
                effective_from=cls.year.start_date,
            )
            cls.teacher = Teacher.objects.create(
                school=cls.school, first_name="Ousmane", last_name="Bodian"
            )
            PayrollProfile.objects.create(
                school=cls.school, teacher=cls.teacher,
                base_salary=350_000, non_taxable_allowance=25_000, family_shares="2",
            )
            cls.inactive = Teacher.objects.create(
                school=cls.school, first_name="Parti", last_name="Test", is_active=False
            )
            PayrollProfile.objects.create(
                school=cls.school, teacher=cls.inactive, base_salary=200_000
            )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def generate(self, period="2025-10-31"):
        return self.client.post("/api/payslips/generate/", {"period": period}, format="json")

    def test_generation_uses_the_applicable_scale(self):
        response = self.generate()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["created"], 1)
        self.assertEqual(response.data["scale"], "Barème test")

        with tenant_context(self.school):
            payslip = Payslip.objects.get()
            self.assertEqual(payslip.gross, 350_000)
            self.assertEqual(payslip.net_pay, 317_447)
            self.assertEqual(payslip.scale, self.scale)

    def test_inactive_staff_is_excluded(self):
        self.generate()
        with tenant_context(self.school):
            self.assertFalse(Payslip.objects.filter(teacher=self.inactive).exists())

    def test_generation_is_idempotent(self):
        """Régénérer ne doit pas écraser un bulletin déjà remis à l'employé."""
        self.generate()
        second = self.generate()
        self.assertEqual(second.data["created"], 0)
        self.assertEqual(second.data["skipped"], 1)
        with tenant_context(self.school):
            self.assertEqual(Payslip.objects.count(), 1)

    def test_unvalidated_scale_raises_a_warning(self):
        response = self.generate()
        self.assertFalse(response.data["scale_validated"])
        self.assertIn("expert-comptable", response.data["warning"])

    def test_validated_scale_raises_no_warning(self):
        with tenant_context(self.school):
            PayrollScale.objects.filter(pk=self.scale.pk).update(
                validated_by="Cabinet Diop & Associés"
            )
        response = self.generate()
        self.assertTrue(response.data["scale_validated"])
        self.assertIsNone(response.data["warning"])

    def test_computation_detail_is_frozen_on_the_payslip(self):
        """Le bulletin doit rester reproductible même si le profil change ensuite."""
        self.generate()
        with tenant_context(self.school):
            payslip = Payslip.objects.get()
            detail = payslip.computation
            self.assertIn("lines", detail)
            self.assertEqual(detail["net_pay"], 317_447)

            # Le salaire change : le bulletin déjà émis ne doit pas bouger.
            PayrollProfile.objects.filter(teacher=self.teacher).update(base_salary=500_000)
            payslip.refresh_from_db()
            self.assertEqual(payslip.net_pay, 317_447)

    def test_individual_pdf_is_produced(self):
        self.generate()
        with tenant_context(self.school):
            payslip_id = Payslip.objects.get().pk
        response = self.client.get(f"/api/payslips/{payslip_id}/pdf/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn("attachment;", response["Content-Disposition"])

    def test_batch_pdf_is_produced(self):
        self.generate()
        response = self.client.get("/api/payslips/pdf-batch/?period=2025-10-31")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_batch_pdf_requires_a_period(self):
        self.assertEqual(self.client.get("/api/payslips/pdf-batch/").status_code, 400)

    def test_payslips_cannot_be_edited_through_the_api(self):
        """Un bulletin se génère et se supprime, il ne se retouche pas."""
        self.generate()
        with tenant_context(self.school):
            payslip_id = Payslip.objects.get().pk
        response = self.client.patch(
            f"/api/payslips/{payslip_id}/", {"net_pay": 999_999}, format="json"
        )
        self.assertEqual(response.status_code, 405)

    def test_generation_without_a_scale_is_refused(self):
        with tenant_context(self.school):
            PayrollScale.objects.all().delete()
        response = self.generate()
        self.assertEqual(response.status_code, 400)
        self.assertIn("scale", response.data)


class PayrollScaleHistoryTests(TestCase):
    """Les barèmes sont datés : un bulletin ancien reste calculé à l'ancien barème."""

    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.year = make_year(cls.school)

    def test_applicable_scale_follows_the_period(self):
        import datetime

        with tenant_context(self.school):
            old = PayrollScale.objects.create(
                school=self.school, label="Barème 2025",
                effective_from=datetime.date(2024, 10, 1),
            )
            new = PayrollScale.objects.create(
                school=self.school, label="Barème 2026",
                effective_from=datetime.date(2026, 1, 1),
            )

            self.assertEqual(PayrollScale.applicable(datetime.date(2025, 11, 30)), old)
            self.assertEqual(PayrollScale.applicable(datetime.date(2026, 3, 31)), new)

    def test_default_values_are_populated_on_creation(self):
        with tenant_context(self.school):
            scale = PayrollScale.objects.create(
                school=self.school, label="Vide", effective_from=self.year.start_date
            )
        self.assertIn("ipres_rg_ceiling", scale.values)
        self.assertIn("income_tax_brackets", scale.values)
        self.assertFalse(scale.is_validated)
