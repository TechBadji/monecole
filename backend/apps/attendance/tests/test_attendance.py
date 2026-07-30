"""Badgeage au portail et suivi d'assiduité.

Le poste de badgeage est utilisé au portail, à sept heures et demie, par un agent
qui a une file d'élèves devant lui. Les tests portent donc autant sur la
tolérance aux erreurs de manipulation que sur la justesse des données.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.attendance.models import AttendanceEvent, AttendanceSettings
from apps.attendance.qr import resolve_payload
from apps.core.models import Role
from apps.core.tenancy import tenant_context
from apps.core.tests.factories import (
    make_classroom,
    make_school,
    make_student,
    make_user,
    make_year,
)
from apps.students.models import StudentStatus


class BadgeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.year = make_year(cls.school)
        cls.cp = make_classroom(cls.school, "CP")
        cls.student = make_student(cls.school, cls.cp, "Aminata", "Diop")
        cls.secretary = make_user(cls.school, Role.SECRETARY, "secret@test.sn")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.secretary)

    def badge(self, payload=None, **extra):
        return self.client.post(
            "/api/scan/badge/",
            {"payload": payload if payload is not None else self.student.qr_payload, **extra},
            format="json",
        )

    def test_first_badge_of_the_day_is_an_entry(self):
        response = self.badge()
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["event"]["direction"], "IN")
        self.assertEqual(response.data["student"]["matricule"], self.student.matricule)

    def test_direction_alternates_without_being_asked(self):
        """L'agent ne choisit pas le sens : il est déduit du dernier passage."""
        self.badge()
        with tenant_context(self.school):
            AttendanceEvent.objects.update(occurred_at=timezone.now() - timedelta(hours=3))

        response = self.badge()
        self.assertEqual(response.data["event"]["direction"], "OUT")

    def test_two_scans_in_a_row_are_reported_as_a_duplicate(self):
        """Une carte passée deux fois ne doit pas créer un second passage."""
        self.badge()
        response = self.badge()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["duplicate"])
        with tenant_context(self.school):
            self.assertEqual(AttendanceEvent.objects.count(), 1)

    def test_manual_matricule_is_accepted(self):
        """Carte illisible : l'agent saisit le matricule à la main."""
        response = self.client.post(
            "/api/scan/badge/", {"matricule": self.student.matricule}, format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["event"]["source"], "MANUAL")

    def test_unknown_card_is_refused_with_a_usable_message(self):
        response = self.badge("M9999|Inconnu|Test||")
        self.assertEqual(response.status_code, 404)

    def test_inactive_student_is_refused(self):
        with tenant_context(self.school):
            self.student.status = StudentStatus.TRANSFERRED
            self.student.status_effective_date = timezone.localdate()
            self.student.save()

        response = self.badge()
        self.assertEqual(response.status_code, 400)
        self.assertIn("Transféré", str(response.data))

    def test_late_arrival_is_flagged(self):
        with tenant_context(self.school):
            settings = AttendanceSettings.for_school(self.school)
            # Toute entrée est en retard : le seuil est placé avant l'instant du test.
            settings.late_after = (timezone.localtime() - timedelta(hours=1)).time()
            settings.save()

        response = self.badge()
        self.assertTrue(response.data["is_late"])
        self.assertEqual(response.data["event"]["note"], "Retard")

    def test_day_is_derived_from_the_timestamp(self):
        self.badge()
        with tenant_context(self.school):
            event = AttendanceEvent.objects.get()
        self.assertEqual(event.day, timezone.localdate())


class PayloadResolutionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        make_year(cls.school)
        cls.cp = make_classroom(cls.school, "CP")
        cls.student = make_student(cls.school, cls.cp)

    def test_full_payload_resolves(self):
        with tenant_context(self.school):
            self.assertEqual(resolve_payload(self.student.qr_payload), self.student)

    def test_bare_matricule_resolves(self):
        with tenant_context(self.school):
            self.assertEqual(resolve_payload(self.student.matricule), self.student)

    def test_lowercase_matricule_resolves(self):
        with tenant_context(self.school):
            self.assertEqual(resolve_payload(self.student.matricule.lower()), self.student)

    def test_empty_payload_resolves_to_nothing(self):
        with tenant_context(self.school):
            self.assertIsNone(resolve_payload(""))
            self.assertIsNone(resolve_payload(None))


class DailySheetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.year = make_year(cls.school)
        cls.cp = make_classroom(cls.school, "CP")
        cls.present = make_student(cls.school, cls.cp, "Présent", "Test")
        cls.absent = make_student(cls.school, cls.cp, "Sans", "Badge")
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")

        with tenant_context(cls.school):
            AttendanceEvent.objects.create(
                school=cls.school, student=cls.present,
                direction=AttendanceEvent.Direction.IN,
                occurred_at=timezone.now(),
            )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_daily_sheet_counts_presence(self):
        response = self.client.get("/api/attendance/daily/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["total"], 2)
        self.assertEqual(response.data["present"], 1)
        self.assertEqual(response.data["no_badge"], 1)

    def test_sheet_states_that_no_badge_is_not_absence(self):
        """Une panne de lecteur ne doit pas se lire comme une école vide."""
        response = self.client.get("/api/attendance/daily/")
        self.assertIn("ne signifie pas", response.data["note"])

    def test_student_history(self):
        response = self.client.get(f"/api/attendance/student/{self.present.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["present_days"], 1)
        self.assertEqual(response.data["results"][0]["passages"], 1)


class QrSheetTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        make_year(cls.school)
        cls.cp = make_classroom(cls.school, "CP")
        make_student(cls.school, cls.cp, "Aminata", "Diop")
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_sheet_is_a_pdf(self):
        response = self.client.get(f"/api/qr-sheet/?classroom={self.cp.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_individual_qr_is_a_png(self):
        from apps.students.models import Student

        with tenant_context(self.school):
            student = Student.objects.first()
        response = self.client.get(f"/api/students/{student.pk}/qr/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")

    def test_empty_selection_is_refused(self):
        empty = make_classroom(self.school, "CM2", order=9)
        response = self.client.get(f"/api/qr-sheet/?classroom={empty.pk}")
        self.assertEqual(response.status_code, 400)


class AttendanceIsolationTests(TestCase):
    """Un badge de l'école A ne doit rien ouvrir dans l'école B."""

    @classmethod
    def setUpTestData(cls):
        cls.school_a = make_school("École A", "ecole-a")
        cls.school_b = make_school("École B", "ecole-b")
        make_year(cls.school_a)
        make_year(cls.school_b)
        cls.class_a = make_classroom(cls.school_a, "CP")
        cls.class_b = make_classroom(cls.school_b, "CP")
        cls.student_b = make_student(cls.school_b, cls.class_b, "Moussa", "Fall")
        cls.admin_a = make_user(cls.school_a, Role.ADMIN, "admin@a.test")

    def test_badging_another_schools_card_is_refused(self):
        client = APIClient()
        client.force_authenticate(self.admin_a)
        response = client.post(
            "/api/scan/badge/", {"payload": self.student_b.qr_payload}, format="json"
        )
        self.assertEqual(response.status_code, 404)
        with tenant_context(self.school_b):
            self.assertEqual(AttendanceEvent.objects.count(), 0)
