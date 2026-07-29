"""Isolation multi-tenant.

C'est le risque de sécurité principal du produit : une fuite de données entre
écoles clientes. Ces tests vérifient l'isolation à trois niveaux — l'ORM, l'écriture
et l'API — parce qu'une seule de ces barrières ne suffit pas.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import Role
from apps.core.tenancy import get_current_tenant, tenant_context, unscoped
from apps.students.models import Student

from .factories import make_classroom, make_school, make_student, make_user, make_year


class TenantQuerysetIsolationTests(TestCase):
    """Le manager par défaut ne laisse jamais passer les données d'un autre tenant."""

    @classmethod
    def setUpTestData(cls):
        cls.school_a = make_school("École A", "ecole-a")
        cls.school_b = make_school("École B", "ecole-b")
        cls.class_a = make_classroom(cls.school_a, "CP")
        cls.class_b = make_classroom(cls.school_b, "CP")
        cls.student_a = make_student(cls.school_a, cls.class_a, "Awa", "Diop")
        cls.student_b = make_student(cls.school_b, cls.class_b, "Moussa", "Fall")

    def test_context_scopes_queryset_to_its_own_school(self):
        with tenant_context(self.school_a):
            self.assertEqual(list(Student.objects.all()), [self.student_a])
        with tenant_context(self.school_b):
            self.assertEqual(list(Student.objects.all()), [self.student_b])

    def test_no_tenant_context_returns_nothing(self):
        """Sans tenant en contexte, on ne devine pas : l'ensemble vide est la réponse sûre."""
        self.assertIsNone(get_current_tenant())
        self.assertEqual(Student.objects.count(), 0)

    def test_fetching_other_tenant_object_by_pk_fails(self):
        with tenant_context(self.school_a):
            self.assertFalse(Student.objects.filter(pk=self.student_b.pk).exists())
            with self.assertRaises(Student.DoesNotExist):
                Student.objects.get(pk=self.student_b.pk)

    def test_unscoped_is_the_only_way_to_see_everything(self):
        with unscoped():
            self.assertEqual(Student.objects.count(), 2)

    def test_cross_tenant_write_is_refused(self):
        """Écrire dans l'école B depuis le contexte de l'école A doit échouer."""
        with tenant_context(self.school_a):
            student = Student(
                school=self.school_b, classroom=self.class_b,
                first_name="Intrus", last_name="Test",
            )
            with self.assertRaises(PermissionError):
                student.save()

    def test_school_is_filled_from_context_when_omitted(self):
        with tenant_context(self.school_a):
            student = Student.objects.create(
                classroom=self.class_a, first_name="Bineta", last_name="Sow"
            )
        self.assertEqual(student.school_id, self.school_a.pk)


class TenantAPIIsolationTests(TestCase):
    """Un jeton valide de l'école A ne donne aucun accès aux données de l'école B.

    C'est le critère d'acceptation du cahier des charges : « aucun utilisateur d'une
    école A ne peut, par manipulation d'URL ou d'API, consulter une donnée de
    l'école B ».
    """

    @classmethod
    def setUpTestData(cls):
        cls.school_a = make_school("École A", "ecole-a")
        cls.school_b = make_school("École B", "ecole-b")
        make_year(cls.school_a)
        make_year(cls.school_b)
        cls.class_a = make_classroom(cls.school_a, "CP")
        cls.class_b = make_classroom(cls.school_b, "CP")
        cls.student_a = make_student(cls.school_a, cls.class_a, "Awa", "Diop")
        cls.student_b = make_student(cls.school_b, cls.class_b, "Moussa", "Fall")
        cls.admin_a = make_user(cls.school_a, Role.ADMIN, "admin@a.test")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin_a)

    def test_list_returns_only_own_students(self):
        response = self.client.get("/api/students/")
        self.assertEqual(response.status_code, 200)
        names = [row["full_name"] for row in response.data["results"]]
        self.assertEqual(names, ["Awa Diop"])

    def test_retrieving_other_tenant_student_returns_404(self):
        """404 et non 403 : révéler qu'un identifiant existe est déjà une fuite."""
        response = self.client.get(f"/api/students/{self.student_b.pk}/")
        self.assertEqual(response.status_code, 404)

    def test_updating_other_tenant_student_returns_404(self):
        response = self.client.patch(
            f"/api/students/{self.student_b.pk}/", {"first_name": "Piraté"}, format="json"
        )
        self.assertEqual(response.status_code, 404)
        self.student_b.refresh_from_db()
        self.assertEqual(self.student_b.first_name, "Moussa")

    def test_deleting_other_tenant_student_returns_404(self):
        response = self.client.delete(f"/api/students/{self.student_b.pk}/")
        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            Student.all_objects.filter(pk=self.student_b.pk).exists(),
            "L'élève de l'école B a été supprimé depuis l'école A.",
        )

    def test_creating_student_in_other_tenant_classroom_fails(self):
        """Poser l'identifiant d'une classe de l'école B ne doit rien permettre."""
        response = self.client.post(
            "/api/students/",
            {"first_name": "Intrus", "last_name": "Test", "classroom": self.class_b.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_reports_never_aggregate_other_tenant_data(self):
        """Le filtrage doit aussi tenir dans les agrégats, pas seulement dans les listes."""
        response = self.client.get("/api/reports/encais/")
        self.assertEqual(response.status_code, 200)
        classes = response.data["classes"]
        self.assertEqual(response.data["headcount_total"], 1)
        self.assertEqual(sum(c["headcount"] for c in classes), 1)

    def test_unauthenticated_access_is_refused(self):
        client = APIClient()
        self.assertEqual(client.get("/api/students/").status_code, 401)
