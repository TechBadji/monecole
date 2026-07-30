"""Matricule élève et bourses sociales.

Le matricule accompagne l'élève tout son cursus : il ne doit jamais être
réattribué, ni changer parce que l'élève a changé de classe ou redoublé.

Les bourses touchent trois écrans qui calculaient auparavant chacun leur montant
dû — situation élève, arriérés, rappels SMS. Les tests vérifient qu'ils
s'accordent, faute de quoi un boursier serait relancé pour une somme qu'il ne
doit pas.
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import Role
from apps.core.tenancy import tenant_context, unscoped
from apps.core.tests.factories import (
    make_classroom,
    make_fee_schedule,
    make_school,
    make_student,
    make_user,
    make_year,
)
from apps.students.fees import due_for, due_map
from apps.students.models import Discount, Enrollment, MonthlyPayment, Student


class MatriculeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school("École A", "ecole-a")
        cls.other = make_school("École B", "ecole-b")
        cls.year = make_year(cls.school)
        make_year(cls.other)
        cls.cp = make_classroom(cls.school, "CP")
        cls.ce1 = make_classroom(cls.school, "CE1", order=6)
        cls.other_cp = make_classroom(cls.other, "CP")

    def test_format_is_m_plus_four_digits(self):
        student = make_student(self.school, self.cp)
        self.assertRegex(student.matricule, r"^M\d{4}$")
        self.assertEqual(student.matricule, "M0001")

    def test_numbering_increments(self):
        matricules = [
            make_student(self.school, self.cp, f"Élève{i}", "Test").matricule
            for i in range(3)
        ]
        self.assertEqual(matricules, ["M0001", "M0002", "M0003"])

    def test_each_school_has_its_own_sequence(self):
        first = make_student(self.school, self.cp, "A", "Test")
        foreign = make_student(self.other, self.other_cp, "B", "Test")
        second = make_student(self.school, self.cp, "C", "Test")

        self.assertEqual(first.matricule, "M0001")
        self.assertEqual(foreign.matricule, "M0001", "Chaque école repart de M0001.")
        self.assertEqual(second.matricule, "M0002")

    def test_matricule_survives_a_class_change(self):
        """Le matricule suit l'élève, pas sa classe — y compris au redoublement."""
        student = make_student(self.school, self.cp)
        original = student.matricule

        with tenant_context(self.school):
            student.classroom = self.ce1
            student.save()
            student.refresh_from_db()

        self.assertEqual(student.matricule, original)

    def test_bulk_creation_assigns_matricules(self):
        """`bulk_create` court-circuite `save()` : l'utilitaire doit combler ce trou."""
        with tenant_context(self.school):
            batch = [
                Student(school=self.school, classroom=self.cp, first_name=f"E{i}", last_name="T")
                for i in range(5)
            ]
            Student.objects.bulk_create(Student.assign_matricules(batch, self.school))
            matricules = sorted(Student.objects.values_list("matricule", flat=True))

        self.assertEqual(matricules, ["M0001", "M0002", "M0003", "M0004", "M0005"])

    def test_qr_payload_carries_the_requested_fields(self):
        """Contenu en clair, conformément à la décision explicite du client."""
        student = make_student(self.school, self.cp, "Aminata", "Diop")
        with tenant_context(self.school):
            student.parent_phone = "+221 77 123 45 67"
            student.save()

        parts = student.qr_payload.split("|")
        self.assertEqual(parts[0], student.matricule)
        self.assertEqual(parts[1], "Diop")
        self.assertEqual(parts[2], "Aminata")
        self.assertEqual(parts[3], "2018-05-12")
        self.assertEqual(parts[4], "221771234567")


class ScholarshipTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.year = make_year(cls.school)
        cls.cp = make_classroom(cls.school, "CP")
        make_fee_schedule(cls.school, cls.cp, cls.year, tuition=15_000, registration=25_000)

        cls.full = make_student(cls.school, cls.cp, "Boursier", "Total")
        cls.half = make_student(cls.school, cls.cp, "Boursier", "Partiel")
        cls.regular = make_student(cls.school, cls.cp, "Élève", "Ordinaire")

        with tenant_context(cls.school):
            Discount.objects.create(
                school=cls.school, student=cls.full, year=cls.year,
                kind=Discount.Kind.FULL, category=Discount.Category.SOCIAL,
                scope=Discount.Scope.TUITION, value=100,
                reason="Orphelin", approved_by="Conseil",
            )
            Discount.objects.create(
                school=cls.school, student=cls.half, year=cls.year,
                kind=Discount.Kind.PERCENT, category=Discount.Category.SOCIAL,
                scope=Discount.Scope.TUITION, value=50,
                reason="Situation familiale", approved_by="Conseil",
            )

        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")

    def test_full_scholarship_owes_nothing_on_tuition(self):
        with tenant_context(self.school):
            due = due_for(self.full, self.year)
        self.assertEqual(due.monthly_tuition, 0)
        self.assertTrue(due.is_full_scholarship)
        self.assertEqual(due.scholarship_rate, 100)

    def test_partial_scholarship_halves_the_tuition(self):
        with tenant_context(self.school):
            due = due_for(self.half, self.year)
        self.assertEqual(due.monthly_tuition, 7_500)
        self.assertFalse(due.is_full_scholarship)
        self.assertEqual(due.scholarship_rate, 50)

    def test_scope_tuition_leaves_registration_untouched(self):
        """Une bourse sur la scolarité ne dispense pas des frais d'inscription."""
        with tenant_context(self.school):
            due = due_for(self.full, self.year)
        self.assertEqual(due.registration, 25_000)

    def test_forgone_is_the_full_year_gap(self):
        """9 mois × 15 000 = 135 000 de manque à gagner pour une bourse totale."""
        with tenant_context(self.school):
            due = due_for(self.full, self.year)
        self.assertEqual(due.forgone(self.year.tuition_months), 135_000)

    def test_due_map_matches_due_for(self):
        """Le calcul en lot doit donner exactement le calcul unitaire."""
        with tenant_context(self.school):
            students = list(Student.objects.all())
            batch = due_map(self.year, students)
            for student in students:
                single = due_for(student, self.year)
                self.assertEqual(
                    batch[student.id].monthly_tuition, single.monthly_tuition,
                    f"Écart pour {student.full_name}",
                )

    def test_full_scholarship_never_appears_in_arrears(self):
        """Le défaut corrigé : un boursier total figurait en tête des impayés."""
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.get("/api/monthly-payments/arrears/")
        self.assertEqual(response.status_code, 200)

        names = [row["name"] for row in response.data["results"]]
        self.assertNotIn("Boursier Total", names)
        self.assertIn("Élève Ordinaire", names)

    def test_partial_scholarship_owes_only_the_reduced_amount(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        rows = {r["name"]: r for r in client.get("/api/monthly-payments/arrears/").data["results"]}

        partial = rows["Boursier Partiel"]
        regular = rows["Élève Ordinaire"]
        self.assertEqual(partial["due"], regular["due"] // 2)
        self.assertEqual(partial["scholarship_rate"], 50)

    def test_sms_reminders_skip_full_scholarships(self):
        """Les rappels doivent voir exactement ce que le comptable voit à l'écran."""
        from apps.notifications.services import arrears_by_student

        with tenant_context(self.school):
            rows = arrears_by_student(self.year)
        names = [row["student"].full_name for row in rows]
        self.assertNotIn("Boursier Total", names)

    def test_report_quantifies_the_social_effort(self):
        from apps.reports.services import scholarships

        with tenant_context(self.school):
            report = scholarships(self.year)

        self.assertEqual(report["beneficiaries"], 2)
        self.assertEqual(report["full_scholarships"], 1)
        # 135 000 pour la bourse totale + 67 500 pour la demi-bourse.
        self.assertEqual(report["total_forgone"], 135_000 + 67_500)
        self.assertEqual(len(report["by_rate"]), 2)

    def test_bilan_carries_the_scholarship_section(self):
        from apps.reports.services import bilan

        with tenant_context(self.school):
            report = bilan(self.year)

        self.assertIn("scholarships", report)
        self.assertEqual(report["scholarships"]["full_scholarships"], 1)
        # La section est « pour mémoire » : elle ne gonfle aucun total.
        self.assertEqual(report["total_resources"]["total"], 0)

    def test_student_ledger_exposes_the_rate(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.get(f"/api/students/{self.half.pk}/ledger/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["scholarship"]["rate"], 50)
        self.assertEqual(response.data["months"][0]["due"], 7_500)


class StudentHistoryTests(TestCase):
    """Consultation des années antérieures."""

    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.previous = make_year(cls.school, 2024, is_current=False)
        cls.current = make_year(cls.school, 2025)
        cls.cp = make_classroom(cls.school, "CP")
        make_fee_schedule(cls.school, cls.cp, cls.previous, tuition=12_000)
        make_fee_schedule(cls.school, cls.cp, cls.current, tuition=15_000)
        cls.student = make_student(cls.school, cls.cp)
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")

        with tenant_context(cls.school):
            for year, amount in ((cls.previous, 12_000), (cls.current, 15_000)):
                Enrollment.objects.create(
                    school=cls.school, student=cls.student, year=year, classroom=cls.cp,
                    registration_paid=True, registration_amount=25_000,
                    paid_at=year.start_date,
                )
                MonthlyPayment.objects.create(
                    school=cls.school, student=cls.student, year=year,
                    period=year.tuition_month_ends[0], tuition=amount,
                )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_history_lists_every_year_newest_first(self):
        response = self.client.get(f"/api/students/{self.student.pk}/history/")
        self.assertEqual(response.status_code, 200)
        labels = [entry["year"] for entry in response.data["years"]]
        self.assertEqual(labels, ["2025/2026", "2024/2025"])

    def test_each_year_carries_its_own_tariff(self):
        response = self.client.get(f"/api/students/{self.student.pk}/history/")
        by_year = {e["year"]: e for e in response.data["years"]}

        # 25 000 d'inscription + 9 × le tarif de l'année.
        self.assertEqual(by_year["2024/2025"]["total_due"], 25_000 + 12_000 * 9)
        self.assertEqual(by_year["2025/2026"]["total_due"], 25_000 + 15_000 * 9)

    def test_ledger_accepts_a_past_year(self):
        response = self.client.get(
            f"/api/students/{self.student.pk}/ledger/?year={self.previous.pk}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["year"], "2024/2025")
        self.assertEqual(response.data["months"][0]["due"], 12_000)
