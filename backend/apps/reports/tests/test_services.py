"""Calculs financiers.

Priorité absolue du cahier des charges. Chaque agrégat du bilan est vérifié contre
une valeur calculée à la main dans le test, et non contre une seconde implémentation
du même calcul — sans quoi une erreur de raisonnement serait reproduite des deux
côtés et le test la validerait.

La classe `ExcelBugRegressionTests` reproduit les quatre configurations qui
donnaient un résultat faux dans le classeur source (voir `docs/modele-excel.md`).
"""

import datetime

from django.test import TestCase

from apps.core.periods import end_of_month
from apps.core.tenancy import tenant_context
from apps.core.tests.factories import (
    make_category,
    make_classroom,
    make_fee_schedule,
    make_school,
    make_student,
    make_year,
)
from apps.finance.models import Expense, OtherIncome
from apps.reports.services import bilan, encaissements
from apps.students.models import Enrollment, MonthlyPayment, Student, StudentStatus


class ReportTestCase(TestCase):
    """Base fournissant une école, une année et un contexte tenant actif."""

    def setUp(self):
        self.school = make_school()
        self.year = make_year(self.school, 2025)
        self.periods = self.year.fiscal_months
        self._ctx = tenant_context(self.school)
        self._ctx.__enter__()
        self.addCleanup(lambda: self._ctx.__exit__(None, None, None))

    def add_payment(self, student, period, tuition, **extra):
        return MonthlyPayment.objects.create(
            school=self.school, student=student, year=self.year,
            period=period, tuition=tuition, payment_date=period, **extra,
        )

    def add_expense(self, category, period, amount, transfer_fee=0, status=None):
        return Expense.objects.create(
            school=self.school, year=self.year,
            operation_date=period.replace(day=15),
            label="Dépense de test", amount=amount, transfer_fee=transfer_fee,
            category=category, status=status or Expense.Status.APPROVED,
        )


class EncaissementsTests(ReportTestCase):
    def setUp(self):
        super().setUp()
        self.cp = make_classroom(self.school, "CP", order=5)
        make_fee_schedule(self.school, self.cp, self.year, tuition=15_000)
        self.student = make_student(self.school, self.cp)

    def test_tuition_lands_in_its_own_month(self):
        self.add_payment(self.student, self.periods[0], 15_000)
        self.add_payment(self.student, self.periods[1], 15_000)

        data = encaissements(self.year)
        row = data["classes"][0]["tuition"]
        self.assertEqual(row["values"][0], 15_000)
        self.assertEqual(row["values"][1], 15_000)
        self.assertEqual(row["values"][2], 0)
        self.assertEqual(row["total"], 30_000)

    def test_registration_is_attributed_to_its_settlement_month(self):
        Enrollment.objects.create(
            school=self.school, student=self.student, year=self.year, classroom=self.cp,
            registration_paid=True, registration_amount=25_000, paid_at=self.periods[2],
        )
        data = encaissements(self.year)
        row = data["classes"][0]["registration"]
        self.assertEqual(row["values"][2], 25_000)
        self.assertEqual(row["total"], 25_000)

    def test_registration_without_date_falls_into_first_month(self):
        """Un encaissement sans date doit rester visible, pas disparaître."""
        Enrollment.objects.create(
            school=self.school, student=self.student, year=self.year, classroom=self.cp,
            registration_paid=True, registration_amount=25_000, paid_at=None,
        )
        data = encaissements(self.year)
        self.assertEqual(data["classes"][0]["registration"]["values"][0], 25_000)
        self.assertEqual(data["registration_total"]["total"], 25_000)

    def test_class_revenue_is_registration_plus_tuition(self):
        Enrollment.objects.create(
            school=self.school, student=self.student, year=self.year, classroom=self.cp,
            registration_paid=True, registration_amount=25_000, paid_at=self.periods[0],
        )
        self.add_payment(self.student, self.periods[0], 15_000)
        data = encaissements(self.year)
        self.assertEqual(data["classes"][0]["revenue"], 40_000)
        self.assertEqual(data["revenue_total"], 40_000)

    def test_canteen_and_reinforcement_stay_out_of_revenue(self):
        """Conformément au classeur, ces postes sont suivis mais hors chiffre d'affaires."""
        self.add_payment(
            self.student, self.periods[0], 15_000, canteen=10_000, reinforcement=5_000
        )
        data = encaissements(self.year)
        self.assertEqual(data["classes"][0]["tuition"]["total"], 15_000)
        self.assertEqual(data["revenue_total"], 15_000)
        self.assertEqual(data["ancillary"]["canteen"]["total"], 10_000)
        self.assertEqual(data["ancillary"]["reinforcement"]["total"], 5_000)


class BilanTests(ReportTestCase):
    def setUp(self):
        super().setUp()
        self.cp = make_classroom(self.school, "CP", order=5)
        make_fee_schedule(self.school, self.cp, self.year, tuition=15_000)
        self.student = make_student(self.school, self.cp)
        self.rent = make_category(self.school, "RENT", "LOCATIONS DE BÂTIMENTS", 0)
        self.salary = make_category(self.school, "SALARY", "SALAIRE", 1)

    def test_total_resources_sums_the_three_income_lines(self):
        Enrollment.objects.create(
            school=self.school, student=self.student, year=self.year, classroom=self.cp,
            registration_paid=True, registration_amount=25_000, paid_at=self.periods[0],
        )
        self.add_payment(self.student, self.periods[0], 15_000)
        OtherIncome.objects.create(
            school=self.school, year=self.year,
            operation_date=self.periods[0].replace(day=5),
            label="Apport actionnaire", amount=100_000,
        )

        report = bilan(self.year)
        self.assertEqual(report["total_resources"]["values"][0], 140_000)
        self.assertEqual(report["total_resources"]["total"], 140_000)

    def test_total_charges_includes_transfer_fees_as_a_separate_line(self):
        """Les frais de transfert sont un agrégat transversal, pas une rubrique."""
        self.add_expense(self.rent, self.periods[0], 450_000, transfer_fee=1_000)
        self.add_expense(self.salary, self.periods[0], 900_000, transfer_fee=2_500)

        report = bilan(self.year)
        lines = {row["key"]: row["total"] for row in report["charges"]}
        self.assertEqual(lines["RENT"], 450_000)
        self.assertEqual(lines["SALARY"], 900_000)
        self.assertEqual(lines["BANK_TRANSFER_FEES"], 3_500)
        self.assertEqual(report["total_charges"]["total"], 1_353_500)

    def test_ebe_is_resources_minus_charges(self):
        self.add_payment(self.student, self.periods[0], 15_000)
        self.add_expense(self.rent, self.periods[0], 10_000)

        report = bilan(self.year)
        self.assertEqual(report["ebe"]["values"][0], 5_000)
        self.assertEqual(report["ebe"]["total"], 5_000)

    def test_cumulative_balance_accumulates_month_over_month(self):
        self.add_payment(self.student, self.periods[0], 30_000)
        self.add_payment(self.student, self.periods[1], 20_000)
        self.add_expense(self.rent, self.periods[1], 45_000)

        report = bilan(self.year)
        cumulative = report["cumulative_balance"]["values"]
        self.assertEqual(cumulative[0], 30_000)          # +30 000
        self.assertEqual(cumulative[1], 5_000)           # +30 000 +20 000 −45 000
        self.assertEqual(cumulative[2], 5_000)           # aucun mouvement ensuite
        self.assertEqual(report["current_balance"], 5_000)

    def test_current_balance_can_be_negative(self):
        """Une école déficitaire doit voir son solde négatif, pas plancher à zéro."""
        self.add_expense(self.rent, self.periods[0], 500_000)
        report = bilan(self.year)
        self.assertEqual(report["current_balance"], -500_000)
        self.assertEqual(report["ebe"]["total"], -500_000)

    def test_draft_and_pending_expenses_stay_out_of_the_balance(self):
        """Une dépense non validée ne doit pas déjà peser sur le résultat."""
        self.add_expense(self.rent, self.periods[0], 100_000, status=Expense.Status.DRAFT)
        self.add_expense(self.rent, self.periods[0], 200_000, status=Expense.Status.PENDING)
        self.add_expense(self.rent, self.periods[0], 50_000, status=Expense.Status.APPROVED)

        report = bilan(self.year)
        self.assertEqual(report["total_charges"]["total"], 50_000)

    def test_empty_year_produces_zeros_not_an_error(self):
        report = bilan(self.year)
        self.assertEqual(report["total_resources"]["total"], 0)
        self.assertEqual(report["total_charges"]["total"], 0)
        self.assertEqual(report["ebe"]["total"], 0)
        self.assertEqual(report["current_balance"], 0)
        self.assertEqual(len(report["periods"]), 12)


class ExcelBugRegressionTests(ReportTestCase):
    """Les quatre bugs du classeur source ne doivent pas se reproduire.

    Chaque test reconstruit la situation qui donnait un résultat faux dans Excel et
    vérifie que l'application produit le résultat juste.
    """

    def setUp(self):
        super().setUp()
        self.ci = make_classroom(self.school, "CI", order=4)
        self.cp = make_classroom(self.school, "CP", order=5)
        make_fee_schedule(self.school, self.ci, self.year, tuition=15_000)
        make_fee_schedule(self.school, self.cp, self.year, tuition=15_000)

    def test_b1_each_class_aggregates_only_its_own_students(self):
        """B1 — `ENCAIS!F21:M21` lisait `CP!` sur la ligne du CI.

        Les mensualités du CP étaient comptées deux fois et celles du CI perdues,
        de novembre à juin.
        """
        student_ci = make_student(self.school, self.ci, "Awa", "Diop")
        student_cp = make_student(self.school, self.cp, "Moussa", "Fall")

        # Novembre — le mois où le classeur se trompait.
        november = self.periods[1]
        self.add_payment(student_ci, november, 11_000)
        self.add_payment(student_cp, november, 77_000)

        data = encaissements(self.year)
        by_class = {row["classroom"]: row for row in data["classes"]}

        self.assertEqual(by_class["CI"]["tuition"]["values"][1], 11_000)
        self.assertEqual(by_class["CP"]["tuition"]["values"][1], 77_000)
        # Le total ne doit pas être 154 000 (le CP compté deux fois).
        self.assertEqual(data["tuition_total"]["values"][1], 88_000)

    def test_b2_totals_cover_every_student_regardless_of_headcount(self):
        """B2 — les totaux de mensualité s'arrêtaient au 21ᵉ élève (`SUM(M9:M29)`).

        Avec 30 élèves, le classeur en ignorait 9. On vérifie ici que les 30 comptent.
        """
        students = [
            make_student(self.school, self.cp, f"Élève{index}", "Test")
            for index in range(30)
        ]
        for student in students:
            self.add_payment(student, self.periods[0], 1_000)

        data = encaissements(self.year)
        row = next(r for r in data["classes"] if r["classroom"] == "CP")
        self.assertEqual(row["tuition"]["values"][0], 30_000)
        self.assertEqual(row["headcount"], 30)

    def test_b3_annual_total_includes_september(self):
        """B3 — `SUM(E12:O12)` s'arrêtait en août, excluant septembre.

        Septembre est le douzième et dernier mois de l'exercice.
        """
        september = self.periods[-1]
        self.assertEqual(september.month, 9)

        student = make_student(self.school, self.cp)
        self.add_payment(student, september, 50_000)
        rent = make_category(self.school, "RENT", "LOCATIONS DE BÂTIMENTS")
        self.add_expense(rent, september, 20_000)

        report = bilan(self.year)
        self.assertEqual(report["total_resources"]["values"][-1], 50_000)
        self.assertEqual(report["total_resources"]["total"], 50_000)
        self.assertEqual(report["total_charges"]["total"], 20_000)
        self.assertEqual(report["ebe"]["total"], 30_000)

    def test_b3_ebe_total_reconciles_with_final_cumulative_balance(self):
        """B3 — le classeur rendait `Q37` et `P39` irréconciliables dès qu'un
        mouvement existait en septembre. Les deux doivent coïncider."""
        student = make_student(self.school, self.cp)
        self.add_payment(student, self.periods[0], 40_000)
        self.add_payment(student, self.periods[-1], 25_000)

        report = bilan(self.year)
        self.assertEqual(report["ebe"]["total"], report["current_balance"])

    def test_b4_headcount_counts_active_students_not_paid_registrations(self):
        """B4 — l'effectif était un `COUNTA` sur « Inscription payée ».

        Un élève inscrit mais n'ayant pas encore réglé disparaissait des effectifs.
        """
        paid = make_student(self.school, self.cp, "Payé", "Test")
        unpaid = make_student(self.school, self.cp, "Impayé", "Test")

        Enrollment.objects.create(
            school=self.school, student=paid, year=self.year, classroom=self.cp,
            registration_paid=True, registration_amount=25_000, paid_at=self.periods[0],
        )
        Enrollment.objects.create(
            school=self.school, student=unpaid, year=self.year, classroom=self.cp,
            registration_paid=False, registration_amount=0,
        )

        data = encaissements(self.year)
        row = next(r for r in data["classes"] if r["classroom"] == "CP")
        self.assertEqual(row["headcount"], 2, "Les deux élèves comptent dans l'effectif.")
        self.assertEqual(row["paid_registrations"], 1, "Une seule inscription est réglée.")

    def test_inactive_students_leave_the_headcount(self):
        """Un élève transféré ne doit plus gonfler l'effectif."""
        active = make_student(self.school, self.cp, "Actif", "Test")
        gone = make_student(self.school, self.cp, "Parti", "Test")
        gone.status = StudentStatus.TRANSFERRED
        gone.status_effective_date = datetime.date(2026, 2, 1)
        gone.save()

        data = encaissements(self.year)
        row = next(r for r in data["classes"] if r["classroom"] == "CP")
        self.assertEqual(row["headcount"], 1)


class PeriodBoundaryTests(ReportTestCase):
    """Le rattachement d'une écriture à sa période comptable."""

    def setUp(self):
        super().setUp()
        self.cp = make_classroom(self.school, "CP", order=5)
        make_fee_schedule(self.school, self.cp, self.year, tuition=15_000)
        self.category = make_category(self.school, "RENT", "LOCATIONS DE BÂTIMENTS")

    def test_expense_period_is_derived_from_operation_date(self):
        expense = Expense.objects.create(
            school=self.school, year=self.year,
            operation_date=datetime.date(2026, 2, 3),
            label="Loyer de février", amount=450_000, category=self.category,
        )
        # Février 2026 n'a pas de 29 : la fin de mois doit être le 28.
        self.assertEqual(expense.period, datetime.date(2026, 2, 28))

    def test_period_follows_operation_date_not_payment_date(self):
        """Une facture de décembre payée en janvier reste une charge de décembre."""
        expense = Expense.objects.create(
            school=self.school, year=self.year,
            operation_date=datetime.date(2025, 12, 20),
            payment_date=datetime.date(2026, 1, 15),
            label="Facture SENELEC", amount=85_000, category=self.category,
        )
        self.assertEqual(expense.period, datetime.date(2025, 12, 31))

        report = bilan(self.year)
        self.assertEqual(report["total_charges"]["values"][2], 85_000)  # décembre
        self.assertEqual(report["total_charges"]["values"][3], 0)       # janvier

    def test_fiscal_year_spans_october_to_september(self):
        self.assertEqual(len(self.periods), 12)
        self.assertEqual((self.periods[0].month, self.periods[0].year), (10, 2025))
        self.assertEqual((self.periods[-1].month, self.periods[-1].year), (9, 2026))

    def test_tuition_calendar_stops_in_june(self):
        tuition_periods = self.year.tuition_month_ends
        self.assertEqual(len(tuition_periods), 9)
        self.assertEqual((tuition_periods[-1].month, tuition_periods[-1].year), (6, 2026))
