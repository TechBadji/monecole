"""Sections d'un même niveau : CI-A, CI-B, CI-C.

Une école à deux classes de CI ne doit pas avoir à saisir chaque classe et à
deviner son rang d'affichage.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import Role
from apps.core.tenancy import tenant_context
from apps.core.tests.factories import (
    make_classroom,
    make_school,
    make_student,
    make_user,
    make_year,
)
from apps.students.grades import display_order
from apps.students.models import ClassRoom


class SectionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")
        cls.secretary = make_user(cls.school, Role.SECRETARY, "sec@test.sn")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def create(self, grade="CI", count=3, **extra):
        return self.client.post(
            "/api/classes/sections/", {"grade": grade, "count": count, **extra}, format="json"
        )

    def names(self):
        with tenant_context(self.school):
            return list(ClassRoom.objects.order_by("order").values_list("name", flat=True))

    def test_sections_are_created_in_pedagogical_order(self):
        response = self.create("CI", 3)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(self.names(), ["CI-A", "CI-B", "CI-C"])

        with tenant_context(self.school):
            orders = list(ClassRoom.objects.order_by("order").values_list("order", flat=True))
        self.assertEqual(orders, [display_order("CI", i) for i in range(3)])

    def test_levels_stay_in_order_when_sections_are_added(self):
        """Le pas de dix garde chaque niveau à sa place."""
        self.create("CM2", 1)
        self.create("CI", 2)
        self.create("CP", 1)
        self.assertEqual(self.names(), ["CI-A", "CI-B", "CP-A", "CM2-A"])

    def test_an_existing_bare_class_is_renamed_not_duplicated(self):
        """« CI » devient « CI-A » et garde ses élèves.

        Laisser « CI » à côté de « CI-A » abandonnerait une classe sans section,
        et ses élèves avec elle.
        """
        bare = make_classroom(self.school, "CI", order=4)
        student = make_student(self.school, bare, "Awa", "Diop")

        response = self.create("CI", 2)
        self.assertEqual(response.data["renamed"], "CI-A")
        self.assertEqual(self.names(), ["CI-A", "CI-B"])

        with tenant_context(self.school):
            bare.refresh_from_db()
            student.refresh_from_db()
            self.assertEqual(bare.name, "CI-A")
            # Même identifiant : les élèves, tarifs et notes suivent.
            self.assertEqual(student.classroom_id, bare.id)

    def test_replaying_creates_nothing(self):
        self.create("CI", 3)
        response = self.create("CI", 3)
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(self.names(), ["CI-A", "CI-B", "CI-C"])

    def test_extending_adds_only_the_missing_sections(self):
        self.create("CI", 2)
        response = self.create("CI", 4)
        self.assertEqual(response.data["created"], 2)
        self.assertEqual(self.names(), ["CI-A", "CI-B", "CI-C", "CI-D"])

    def test_an_unknown_grade_is_refused(self):
        response = self.create("6EME", 2)
        self.assertEqual(response.status_code, 400)
        self.assertIn("6EME", str(response.data))

    def test_the_section_count_is_bounded(self):
        for count in (0, -1, 99):
            self.assertEqual(self.create("CI", count).status_code, 400, count)

    def test_only_an_administrator_creates_classes(self):
        client = APIClient()
        client.force_authenticate(self.secretary)
        response = client.post(
            "/api/classes/sections/", {"grade": "CI", "count": 2}, format="json"
        )
        self.assertEqual(response.status_code, 403)

    def test_sections_inherit_the_level_of_their_grade(self):
        self.create("GARDERIE", 2)
        self.create("CM1", 1)
        with tenant_context(self.school):
            self.assertEqual(ClassRoom.objects.get(name="GARDERIE-A").level, "PRESCHOOL")
            self.assertEqual(ClassRoom.objects.get(name="CM1-A").level, "PRIMARY")

    def test_the_subject_catalogue_still_matches_a_sectioned_class(self):
        """« CE1-B » doit relever du catalogue du CE1, comme « CE1 »."""
        from apps.academics.catalogue import SUBJECT_CATALOGUE, catalogue_for

        self.create("CE1", 2)
        self.assertEqual(catalogue_for("CE1-B"), SUBJECT_CATALOGUE["CE1"])


class ClassDeletionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")
        cls.classroom = make_classroom(cls.school, "CI-A", order=40)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_an_empty_class_can_be_deleted(self):
        response = self.client.delete(f"/api/classes/{self.classroom.id}/")
        self.assertEqual(response.status_code, 204)

    def test_a_class_with_students_is_refused_with_a_count(self):
        """La clé étrangère est en PROTECT : sans ce garde, une 500 illisible."""
        make_student(self.school, self.classroom, "Awa", "Diop")
        response = self.client.delete(f"/api/classes/{self.classroom.id}/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("1 élève", str(response.data))

        with tenant_context(self.school):
            self.assertTrue(ClassRoom.objects.filter(pk=self.classroom.pk).exists())


class GradeListTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")

    def test_the_grade_list_reports_existing_sections(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        client.post("/api/classes/sections/", {"grade": "CI", "count": 2}, format="json")

        response = client.get("/api/classes/grades/")
        self.assertEqual(response.status_code, 200)
        grades = {row["code"]: row for row in response.data}
        self.assertEqual(grades["CI"]["sections"], ["CI-A", "CI-B"])
        self.assertEqual(grades["CM2"]["sections"], [])
        self.assertEqual(grades["GARDERIE"]["level"], "PRESCHOOL")


class ClassTeacherAssignmentTests(TestCase):
    """Affectation du titulaire d'une classe.

    Le champ `teacher` de la classe est calculé — l'affectation porte une
    année. Un `PATCH` qui le posait était ignoré en silence : la requête
    répondait 200 et rien ne changeait. Un appel qui ne fait rien sans le dire
    est pire qu'un appel refusé.
    """

    @classmethod
    def setUpTestData(cls):
        from apps.staff.models import Teacher

        cls.school = make_school()
        cls.year = make_year(cls.school)
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")
        cls.secretary = make_user(cls.school, Role.SECRETARY, "sec@test.sn")
        with tenant_context(cls.school):
            cls.room = make_classroom(cls.school, "CI-A", order=40)
            cls.teacher = Teacher.objects.create(
                school=cls.school, first_name="Fatou", last_name="Ndione"
            )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_the_titular_is_assigned_for_the_year(self):
        response = self.client.put(
            f"/api/classes/{self.room.id}/teacher/",
            {"teacher": self.teacher.id, "year": self.year.id},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        with tenant_context(self.school):
            self.assertEqual(self.room.teacher_for(self.year), self.teacher)

    def test_the_assignment_shows_in_the_class_list(self):
        self.client.put(
            f"/api/classes/{self.room.id}/teacher/",
            {"teacher": self.teacher.id, "year": self.year.id},
            format="json",
        )
        listed = self.client.get("/api/classes/").data["results"]
        row = next(r for r in listed if r["id"] == self.room.id)
        self.assertEqual(row["teacher"], self.teacher.id)
        self.assertEqual(row["teacher_name"], "Fatou Ndione")

    def test_patching_the_class_is_refused_rather_than_ignored(self):
        """Le défaut d'origine : la requête répondait 200 sans rien faire."""
        response = self.client.patch(
            f"/api/classes/{self.room.id}/",
            {"teacher": self.teacher.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("teacher", str(response.data))
        with tenant_context(self.school):
            self.assertIsNone(self.room.teacher_for(self.year))

    def test_an_empty_teacher_clears_the_assignment(self):
        self.client.put(
            f"/api/classes/{self.room.id}/teacher/",
            {"teacher": self.teacher.id, "year": self.year.id},
            format="json",
        )
        self.client.put(
            f"/api/classes/{self.room.id}/teacher/",
            {"teacher": None, "year": self.year.id},
            format="json",
        )
        with tenant_context(self.school):
            self.assertIsNone(self.room.teacher_for(self.year))

    def test_an_inactive_teacher_is_refused(self):
        """Un enseignant parti ne doit pas être affecté à une classe."""
        with tenant_context(self.school):
            self.teacher.is_active = False
            self.teacher.save()
        response = self.client.put(
            f"/api/classes/{self.room.id}/teacher/",
            {"teacher": self.teacher.id, "year": self.year.id},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("inactif", str(response.data))

    def test_a_secretary_cannot_assign(self):
        client = APIClient()
        client.force_authenticate(self.secretary)
        response = client.put(
            f"/api/classes/{self.room.id}/teacher/",
            {"teacher": self.teacher.id, "year": self.year.id},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
