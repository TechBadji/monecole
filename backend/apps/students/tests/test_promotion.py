"""Passage d'une année scolaire à la suivante.

Une rentrée touche tous les élèves de l'établissement d'un coup. Les cas
couverts ici sont ceux dont l'erreur ne se verrait qu'en novembre : un arriéré
réclamé à un élève qui n'est pas revenu, un redoublant monté de classe, ou
l'année passée réécrite par la nouvelle.
"""

from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import Role, SchoolYear
from apps.core.tenancy import tenant_context
from apps.core.tests.factories import (
    make_classroom,
    make_fee_schedule,
    make_school,
    make_student,
    make_user,
    make_year,
)
from apps.students.fees import due_for, due_map, pending_students
from apps.students.models import ClassTeacher, Enrollment, EnrollmentStatus
from apps.students.promotion import apply_promotion, next_classroom, plan_promotion


class NextClassroomTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        with tenant_context(cls.school):
            cls.rooms = {
                name: make_classroom(cls.school, name, order=order)
                for order, name in enumerate(
                    ["CI-A", "CI-B", "CP-A", "CP-B", "CE1-A", "CM2"]
                )
            }

    def test_the_section_is_kept_when_it_exists(self):
        """Un CI-B rejoint le CP-B : casser les sections casse des habitudes."""
        with tenant_context(self.school):
            self.assertEqual(next_classroom(self.rooms["CI-B"]).name, "CP-B")

    def test_it_falls_back_to_the_first_section(self):
        with tenant_context(self.school):
            self.assertEqual(next_classroom(self.rooms["CP-B"]).name, "CE1-A")

    def test_the_last_level_leads_nowhere(self):
        """Le CM2 sort de l'école : ce n'est pas une classe à deviner."""
        with tenant_context(self.school):
            self.assertIsNone(next_classroom(self.rooms["CM2"]))


class PromotionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")
        cls.year = make_year(cls.school, start_year=2025)
        with tenant_context(cls.school):
            cls.next_year = SchoolYear.objects.create(
                school=cls.school, label="2026/2027",
                start_date=date(2026, 10, 1), end_date=date(2027, 9, 30),
                tuition_months=9, is_current=False,
            )
            cls.ci = make_classroom(cls.school, "CI-A", order=40)
            cls.cp = make_classroom(cls.school, "CP-A", order=50)
            cls.cm2 = make_classroom(cls.school, "CM2", order=90)

            cls.passant = make_student(cls.school, cls.ci, "Awa", "Diop")
            cls.redoublant = make_student(cls.school, cls.ci, "Moussa", "Fall")
            cls.sortant = make_student(cls.school, cls.cm2, "Bineta", "Sow")

            make_fee_schedule(cls.school, cls.cp, cls.next_year)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def promote(self, repeating=()):
        with tenant_context(self.school):
            return apply_promotion(
                self.year, self.next_year, repeating, school=self.school
            )

    def test_a_plan_writes_nothing(self):
        with tenant_context(self.school):
            plan = plan_promotion(self.year, self.next_year)
            self.assertEqual(plan.summary["moves"], 2)
            self.assertEqual(Enrollment.objects.filter(year=self.next_year).count(), 0)

    def test_students_move_up_a_level(self):
        self.promote()
        with tenant_context(self.school):
            enrollment = Enrollment.objects.get(
                student=self.passant, year=self.next_year
            )
            self.assertEqual(enrollment.classroom, self.cp)
            self.assertEqual(enrollment.promoted_from, self.ci)

    def test_a_new_enrollment_is_pending_not_confirmed(self):
        """C'est la règle qui gouverne tout le module."""
        self.promote()
        with tenant_context(self.school):
            enrollment = Enrollment.objects.get(
                student=self.passant, year=self.next_year
            )
            self.assertEqual(enrollment.status, EnrollmentStatus.PENDING)
            self.assertFalse(enrollment.registration_paid)

    def test_a_repeater_stays_in_place_and_is_marked(self):
        self.promote(repeating=[self.redoublant.id])
        with tenant_context(self.school):
            enrollment = Enrollment.objects.get(
                student=self.redoublant, year=self.next_year
            )
            self.assertEqual(enrollment.classroom, self.ci)
            self.assertTrue(enrollment.is_repeat)

    def test_a_last_year_student_is_reported_not_guessed(self):
        """Le CM2 sort de l'école : l'administration tranche, pas le logiciel."""
        with tenant_context(self.school):
            plan = plan_promotion(self.year, self.next_year)
        self.assertEqual([s.id for s in plan.blocked], [self.sortant.id])

    def test_promoting_twice_creates_nothing(self):
        self.promote()
        _plan, created, _carried = self.promote()
        self.assertEqual(created, 0)

    def test_the_previous_year_is_untouched(self):
        """Une rentrée n'efface pas l'année précédente."""
        with tenant_context(self.school):
            before = self.passant.classroom_id
        self.promote()
        with tenant_context(self.school):
            self.passant.refresh_from_db()
            self.assertEqual(self.passant.classroom_id, before)

    def test_titulars_are_carried_over(self):
        """Réaffecter douze classes chaque rentrée serait du travail perdu."""
        from apps.staff.models import Teacher

        with tenant_context(self.school):
            teacher = Teacher.objects.create(
                school=self.school, first_name="Fatou", last_name="Ndione"
            )
            ClassTeacher.objects.create(
                school=self.school, classroom=self.ci, year=self.year, teacher=teacher
            )

        self.promote()
        with tenant_context(self.school):
            self.assertEqual(self.ci.teacher_for(self.next_year), teacher)


class PendingDuesTests(TestCase):
    """Un élève en attente ne doit rien.

    Le compter dès le passage gonflerait les arriérés dès octobre, sur des
    élèves dont on ignore encore s'ils reviendront.
    """

    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.year = make_year(cls.school)
        with tenant_context(cls.school):
            cls.room = make_classroom(cls.school, "CP-A", order=50)
            make_fee_schedule(cls.school, cls.room, cls.year, tuition=15_000)
            cls.attente = make_student(cls.school, cls.room, "Awa", "Diop")
            cls.confirme = make_student(cls.school, cls.room, "Moussa", "Fall")

            Enrollment.objects.create(
                school=cls.school, student=cls.attente, year=cls.year,
                classroom=cls.room, status=EnrollmentStatus.PENDING,
            )
            Enrollment.objects.create(
                school=cls.school, student=cls.confirme, year=cls.year,
                classroom=cls.room, status=EnrollmentStatus.CONFIRMED,
            )

    def test_a_pending_student_owes_nothing(self):
        with tenant_context(self.school):
            amounts = due_map(self.year, [self.attente, self.confirme])
        self.assertIsNone(amounts[self.attente.id])
        self.assertIsNotNone(amounts[self.confirme.id])
        self.assertEqual(amounts[self.confirme.id].monthly_tuition, 15_000)

    def test_the_pending_set_is_computed_in_one_query(self):
        with tenant_context(self.school):
            self.assertEqual(pending_students(self.year), {self.attente.id})

    def test_confirming_makes_the_dues_appear(self):
        from apps.students.promotion import confirm_enrollment

        with tenant_context(self.school):
            enrollment = Enrollment.objects.get(student=self.attente, year=self.year)
            confirm_enrollment(enrollment, paid=True)
            amounts = due_map(self.year, [self.attente])

        self.assertIsNotNone(amounts[self.attente.id])
        self.assertEqual(amounts[self.attente.id].monthly_tuition, 15_000)

    def test_a_student_without_any_enrollment_keeps_the_old_behaviour(self):
        """Les écoles qui ne suivent pas les inscriptions ne doivent rien perdre."""
        with tenant_context(self.school):
            libre = make_student(self.school, self.room, "Sans", "Inscription")
            self.assertIsNotNone(due_for(libre, self.year))
