"""Notes, moyennes pondérées, rang et bulletins.

Les valeurs attendues sont posées à la main dans chaque test : réutiliser le
service pour produire la référence ne prouverait rien.
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.academics.models import (
    ClassSubject,
    Composition,
    Grade,
    GradeSheet,
    ReportCardSettings,
    Subject,
    mention_for,
)
from apps.academics.services import class_summary, student_results
from apps.core.models import Role
from apps.core.tenancy import tenant_context
from apps.core.tests.factories import (
    make_classroom,
    make_school,
    make_student,
    make_user,
    make_year,
)
from apps.staff.models import Teacher


class AcademicsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.year = make_year(cls.school)
        cls.cm2 = make_classroom(cls.school, "CM2", order=9)
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")
        cls.teacher_user = make_user(cls.school, Role.TEACHER, "prof@test.sn")

        with tenant_context(cls.school):
            cls.teacher = Teacher.objects.create(
                school=cls.school, first_name="Ousmane", last_name="Bodian",
                email="prof@test.sn",
            )
            # Français coefficient 4, Mathématiques 4, Anglais 1 : total 9.
            cls.subjects = {}
            for order, (code, name, coefficient) in enumerate(
                [("FR", "Français", 4), ("MATH", "Mathématiques", 4), ("EN", "Anglais", 1)]
            ):
                subject = Subject.objects.create(
                    school=cls.school, code=code, name=name,
                    default_coefficient=coefficient, order=order,
                )
                cls.subjects[code] = ClassSubject.objects.create(
                    school=cls.school, classroom=cls.cm2, subject=subject,
                    year=cls.year, coefficient=coefficient, teacher=cls.teacher,
                    order=order,
                )

            cls.composition = Composition.objects.create(
                school=cls.school, year=cls.year, name="1er trimestre",
                kind=Composition.Kind.TERM, term=1, date=cls.year.start_date,
                status=Composition.Status.OPEN,
            )

    def grade(self, student, code, value=None, absent=False):
        with tenant_context(self.school):
            sheet, _ = GradeSheet.objects.get_or_create(
                school=self.school,
                composition=self.composition,
                class_subject=self.subjects[code],
            )
            return Grade.objects.create(
                school=self.school, sheet=sheet, student=student,
                value=None if absent else Decimal(str(value)), is_absent=absent,
            )


class WeightedAverageTests(AcademicsTestCase):
    def test_weighted_average_is_computed_by_hand(self):
        """Français 14×4 = 56, Maths 12×4 = 48, Anglais 16×1 = 16.

        Total 120 points sur 9 coefficients → 13,33.
        """
        student = make_student(self.school, self.cm2, "Awa", "Diop")
        self.grade(student, "FR", 14)
        self.grade(student, "MATH", 12)
        self.grade(student, "EN", 16)

        with tenant_context(self.school):
            results, _, _ = student_results(self.composition, self.cm2)

        result = results[student.id]
        self.assertEqual(result["total_points"], Decimal("120.00"))
        self.assertEqual(result["total_coefficients"], 9)
        self.assertEqual(result["average"], Decimal("13.33"))

    def test_absence_is_not_a_zero(self):
        """Une absence retire son coefficient au lieu de tirer la moyenne à zéro.

        Français 14×4 = 56 sur 4 coefficients → 14,00. Compter l'absence en maths
        comme un zéro donnerait 56/8 = 7,00.
        """
        student = make_student(self.school, self.cm2, "Awa", "Diop")
        self.grade(student, "FR", 14)
        self.grade(student, "MATH", absent=True)

        with tenant_context(self.school):
            results, _, _ = student_results(self.composition, self.cm2)

        result = results[student.id]
        self.assertEqual(result["total_coefficients"], 4)
        self.assertEqual(result["average"], Decimal("14.00"))

    def test_student_without_any_grade_has_no_average(self):
        student = make_student(self.school, self.cm2, "Sans", "Note")
        with tenant_context(self.school):
            results, _, _ = student_results(self.composition, self.cm2)

        result = results[student.id]
        self.assertIsNone(result["average"])
        self.assertFalse(result["graded"])

    def test_coefficient_belongs_to_the_class_not_the_subject(self):
        """Une école doit pouvoir pondérer le français différemment selon le niveau."""
        with tenant_context(self.school):
            self.subjects["FR"].coefficient = 2
            self.subjects["FR"].save()

        student = make_student(self.school, self.cm2, "Awa", "Diop")
        self.grade(student, "FR", 14)   # 14 × 2 = 28
        self.grade(student, "MATH", 12)  # 12 × 4 = 48

        with tenant_context(self.school):
            results, _, _ = student_results(self.composition, self.cm2)

        # 76 points sur 6 coefficients → 12,67.
        self.assertEqual(results[student.id]["average"], Decimal("12.67"))


class RankTests(AcademicsTestCase):
    def test_rank_follows_the_average(self):
        best = make_student(self.school, self.cm2, "Premier", "Test")
        middle = make_student(self.school, self.cm2, "Second", "Test")
        last = make_student(self.school, self.cm2, "Troisieme", "Test")

        for student, value in ((best, 18), (middle, 14), (last, 8)):
            self.grade(student, "FR", value)

        with tenant_context(self.school):
            results, _, _ = student_results(self.composition, self.cm2)

        self.assertEqual(results[best.id]["rank"], 1)
        self.assertEqual(results[middle.id]["rank"], 2)
        self.assertEqual(results[last.id]["rank"], 3)
        self.assertEqual(results[best.id]["ranked_out_of"], 3)

    def test_ties_share_a_rank(self):
        """Deux élèves à égalité partagent le rang ; le suivant reprend au troisième."""
        first = make_student(self.school, self.cm2, "Ex", "Aequo1")
        second = make_student(self.school, self.cm2, "Ex", "Aequo2")
        third = make_student(self.school, self.cm2, "Suivant", "Test")

        self.grade(first, "FR", 15)
        self.grade(second, "FR", 15)
        self.grade(third, "FR", 10)

        with tenant_context(self.school):
            results, _, _ = student_results(self.composition, self.cm2)

        self.assertEqual(results[first.id]["rank"], 1)
        self.assertEqual(results[second.id]["rank"], 1)
        self.assertEqual(results[third.id]["rank"], 3)

    def test_ungraded_student_is_not_ranked_last(self):
        """Ne pas être noté n'est pas être dernier."""
        graded = make_student(self.school, self.cm2, "Noté", "Test")
        ungraded = make_student(self.school, self.cm2, "Absent", "Total")
        self.grade(graded, "FR", 12)

        with tenant_context(self.school):
            results, _, _ = student_results(self.composition, self.cm2)

        self.assertEqual(results[graded.id]["rank"], 1)
        self.assertIsNone(results[ungraded.id]["rank"])
        self.assertEqual(results[graded.id]["ranked_out_of"], 1)


class MentionTests(TestCase):
    def test_thresholds(self):
        for average, expected in [
            (17, "Très bien"), (16, "Très bien"), (15, "Bien"), (14, "Bien"),
            (13, "Assez bien"), (12, "Assez bien"), (11, "Passable"),
            (10, "Passable"), (9.5, "Insuffisant"),
        ]:
            self.assertEqual(mention_for(average), expected, f"moyenne {average}")

    def test_none_average_has_no_mention(self):
        self.assertEqual(mention_for(None), "")


class GradeEntryTests(AcademicsTestCase):
    """Saisie par l'enseignant et validation."""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.teacher_user)
        self.student = make_student(self.school, self.cm2, "Awa", "Diop")
        with tenant_context(self.school):
            self.sheet = GradeSheet.objects.create(
                school=self.school, composition=self.composition,
                class_subject=self.subjects["FR"],
            )
            self.grade_row = Grade.objects.create(
                school=self.school, sheet=self.sheet, student=self.student
            )

    def test_teacher_sees_only_their_own_subjects(self):
        with tenant_context(self.school):
            other_teacher = Teacher.objects.create(
                school=self.school, first_name="Autre", last_name="Prof",
                email="autre@test.sn",
            )
            self.subjects["MATH"].teacher = other_teacher
            self.subjects["MATH"].save()
            GradeSheet.objects.create(
                school=self.school, composition=self.composition,
                class_subject=self.subjects["MATH"],
            )

        response = self.client.get("/api/grade-sheets/")
        subjects = [row["subject"] for row in response.data["results"]]
        self.assertIn("Français", subjects)
        self.assertNotIn("Mathématiques", subjects)

    def test_saving_grades(self):
        response = self.client.post(
            f"/api/grade-sheets/{self.sheet.pk}/save/",
            {"rows": [{"grade": self.grade_row.pk, "value": "14.5"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.grade_row.refresh_from_db()
        self.assertEqual(self.grade_row.value, Decimal("14.50"))

    def test_grade_above_twenty_is_refused(self):
        response = self.client.post(
            f"/api/grade-sheets/{self.sheet.pk}/save/",
            {"rows": [{"grade": self.grade_row.pk, "value": "22"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("hors barème", str(response.data))

    def test_unreadable_grade_names_the_student(self):
        response = self.client.post(
            f"/api/grade-sheets/{self.sheet.pk}/save/",
            {"rows": [{"grade": self.grade_row.pk, "value": "quatorze"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Awa Diop", str(response.data))

    def test_validation_requires_every_grade(self):
        """Valider une feuille incomplète produirait un bulletin faux."""
        response = self.client.post(f"/api/grade-sheets/{self.sheet.pk}/validate_sheet/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Awa Diop", str(response.data))

    def test_validation_succeeds_once_complete(self):
        self.client.post(
            f"/api/grade-sheets/{self.sheet.pk}/save/",
            {"rows": [{"grade": self.grade_row.pk, "value": "14"}]},
            format="json",
        )
        response = self.client.post(f"/api/grade-sheets/{self.sheet.pk}/validate_sheet/")
        self.assertEqual(response.status_code, 200)
        self.sheet.refresh_from_db()
        self.assertTrue(self.sheet.is_validated)

    def test_validated_sheet_refuses_further_edits(self):
        self.client.post(
            f"/api/grade-sheets/{self.sheet.pk}/save/",
            {"rows": [{"grade": self.grade_row.pk, "value": "14"}]},
            format="json",
        )
        self.client.post(f"/api/grade-sheets/{self.sheet.pk}/validate_sheet/")

        response = self.client.post(
            f"/api/grade-sheets/{self.sheet.pk}/save/",
            {"rows": [{"grade": self.grade_row.pk, "value": "18"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Dévalidez", str(response.data))

    def test_teacher_cannot_unvalidate(self):
        """Rouvrir une feuille est un acte d'administration."""
        response = self.client.post(f"/api/grade-sheets/{self.sheet.pk}/unvalidate/")
        self.assertEqual(response.status_code, 403)

    def test_closed_composition_refuses_entry(self):
        with tenant_context(self.school):
            self.composition.status = Composition.Status.CLOSED
            self.composition.save()

        response = self.client.post(
            f"/api/grade-sheets/{self.sheet.pk}/save/",
            {"rows": [{"grade": self.grade_row.pk, "value": "14"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class ReportCardTests(AcademicsTestCase):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        self.student = make_student(self.school, self.cm2, "Awa", "Diop")
        self.grade(self.student, "FR", 14)
        self.grade(self.student, "MATH", 12)

    def test_class_summary(self):
        with tenant_context(self.school):
            summary = class_summary(self.composition, self.cm2)
        # (14×4 + 12×4) / 8 = 13,00
        self.assertEqual(summary["class_average"], Decimal("13.00"))
        self.assertEqual(summary["graded"], 1)
        self.assertEqual(summary["pass_rate"], 100.0)

    def test_individual_pdf(self):
        response = self.client.get(
            f"/api/report-cards/pdf/?composition={self.composition.pk}"
            f"&classroom={self.cm2.pk}&student={self.student.pk}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_batch_pdf(self):
        make_student(self.school, self.cm2, "Second", "Élève")
        response = self.client.get(
            f"/api/report-cards/pdf/?composition={self.composition.pk}&classroom={self.cm2.pk}"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_pdf_requires_a_composition(self):
        response = self.client.get(f"/api/report-cards/pdf/?classroom={self.cm2.pk}")
        self.assertEqual(response.status_code, 400)

    def test_settings_are_editable_by_admin_only(self):
        response = self.client.put(
            "/api/report-card-settings/",
            {"principal_name": "Awa Diop", "header_line_1": "République du Sénégal"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        with tenant_context(self.school):
            settings = ReportCardSettings.for_school(self.school)
        self.assertEqual(settings.principal_name, "Awa Diop")

        teacher_client = APIClient()
        teacher_client.force_authenticate(self.teacher_user)
        self.assertEqual(
            teacher_client.put(
                "/api/report-card-settings/", {"principal_name": "Pirate"}, format="json"
            ).status_code,
            403,
        )
