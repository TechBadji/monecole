"""Performance du calcul du bilan.

Critère d'acceptation : « le temps de génération du bilan annuel pour une école de
500 élèves reste sous 5 secondes ».

Le bilan étant recalculé à chaque consultation plutôt que stocké, ce seuil est ce
qui rend ce choix tenable — il est donc vérifié automatiquement, pas seulement
mesuré une fois à la main.
"""

import time

from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection

from apps.core.tenancy import tenant_context
from apps.core.tests.factories import make_category, make_school, make_year
from apps.finance.models import Expense
from apps.students.models import (
    ClassRoom,
    Enrollment,
    FeeSchedule,
    Level,
    MonthlyPayment,
    Student,
)

CLASSES = ["GARDERIE", "PS", "MS", "GS", "CI", "CP", "CE1", "CE2", "CM1", "CM2"]
STUDENTS_PER_CLASS = 50  # 500 élèves au total
BUDGET_SECONDS = 5.0


class BilanPerformanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.year = make_year(cls.school, 2025)

        with tenant_context(cls.school):
            classrooms = [
                ClassRoom.objects.create(
                    school=cls.school, name=name,
                    level=Level.PRESCHOOL if index < 4 else Level.PRIMARY,
                    order=index,
                )
                for index, name in enumerate(CLASSES)
            ]
            FeeSchedule.objects.bulk_create([
                FeeSchedule(
                    school=cls.school, classroom=classroom, year=cls.year,
                    registration_fee=25_000, monthly_tuition=15_000,
                    monthly_canteen=10_000, monthly_reinforcement=5_000,
                    uniform_fee=12_000, insurance_fee=3_000, ape_fee=5_000,
                )
                for classroom in classrooms
            ])

            students = Student.objects.bulk_create([
                Student(
                    school=cls.school, classroom=classroom,
                    first_name=f"Élève{index}", last_name=classroom.name,
                )
                for classroom in classrooms
                for index in range(STUDENTS_PER_CLASS)
            ])

            Enrollment.objects.bulk_create([
                Enrollment(
                    school=cls.school, student=student, year=cls.year,
                    classroom_id=student.classroom_id, registration_paid=True,
                    registration_amount=25_000, paid_at=cls.year.start_date,
                )
                for student in students
            ])

            # 9 mensualités par élève, soit 4 500 encaissements.
            MonthlyPayment.objects.bulk_create([
                MonthlyPayment(
                    school=cls.school, student=student, year=cls.year,
                    period=period, tuition=15_000, canteen=10_000,
                )
                for student in students
                for period in cls.year.tuition_month_ends
            ])

            categories = [
                make_category(cls.school, f"CAT{index}", f"RUBRIQUE {index}", index)
                for index in range(16)
            ]
            Expense.objects.bulk_create([
                Expense(
                    school=cls.school, year=cls.year,
                    operation_date=period.replace(day=15), period=period,
                    label="Dépense", amount=100_000, transfer_fee=1_000,
                    category=category, status=Expense.Status.APPROVED,
                )
                for category in categories
                for period in cls.year.fiscal_months
            ])

    def test_dataset_is_the_expected_size(self):
        with tenant_context(self.school):
            self.assertEqual(Student.objects.count(), 500)
            self.assertEqual(MonthlyPayment.objects.count(), 4_500)
            self.assertEqual(Expense.objects.count(), 192)

    def test_bilan_for_500_students_stays_under_five_seconds(self):
        from apps.reports.services import bilan

        with tenant_context(self.school):
            start = time.perf_counter()
            report = bilan(self.year)
            elapsed = time.perf_counter() - start

        self.assertEqual(report["headcount_total"], 500)
        self.assertLess(
            elapsed, BUDGET_SECONDS,
            f"Bilan calculé en {elapsed:.2f} s pour 500 élèves — "
            f"le budget est de {BUDGET_SECONDS} s.",
        )

    def test_bilan_query_count_does_not_grow_with_the_number_of_students(self):
        """Le nombre de requêtes doit rester constant, pas proportionnel à l'effectif.

        Cadenasse l'agrégation en SQL : une régression vers une boucle Python sur
        les élèves ferait exploser ce compteur bien avant de dépasser le budget de
        temps sur un jeu de données de test.
        """
        from apps.reports.services import bilan

        with tenant_context(self.school):
            with CaptureQueriesContext(connection) as captured:
                bilan(self.year)

        self.assertLess(
            len(captured), 30,
            f"{len(captured)} requêtes pour un bilan — l'agrégation a probablement "
            f"quitté le SQL pour une boucle Python.",
        )
