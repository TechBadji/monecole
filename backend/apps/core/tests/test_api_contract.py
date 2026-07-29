"""Garde-fous d'API.

`test_every_list_endpoint_returns_its_data` existe à cause d'un bug réel : déclarer
`queryset = Model.objects.select_related(...)` sur une vue tenant évalue le manager à
l'import du module, sans tenant en contexte. `TenantManager` renvoie alors `.none()`,
qui reste figé dans l'attribut de classe — la vue ne retourne plus jamais rien, sans
lever la moindre erreur. Aucun test unitaire de service ne l'aurait vu.
"""

from django.test import TestCase
from django.urls import get_resolver
from rest_framework.test import APIClient

from apps.core.models import Role
from apps.core.tenancy import tenant_context
from apps.finance.models import Expense
from apps.staff.models import Salary, SalaryRubric, Teacher
from apps.students.models import (
    ClassEnrollmentHistory,
    Discount,
    Enrollment,
    Family,
    MonthlyPayment,
)

from .factories import (
    make_category,
    make_classroom,
    make_fee_schedule,
    make_school,
    make_student,
    make_user,
    make_year,
)


class ListEndpointDataTests(TestCase):
    """Chaque endpoint de liste doit renvoyer les données qu'il est censé servir.

    On crée exactement un objet par ressource, puis on vérifie que la liste en
    contient un. Un `0` signale que le filtrage tenant a été appliqué au mauvais
    moment.
    """

    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.year = make_year(cls.school)
        cls.classroom = make_classroom(cls.school, "CP")
        make_fee_schedule(cls.school, cls.classroom, cls.year)
        cls.student = make_student(cls.school, cls.classroom)
        cls.category = make_category(cls.school, "RENT", "LOCATIONS DE BÂTIMENTS")
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")

        with tenant_context(cls.school):
            family = Family.objects.create(
                school=cls.school, name="Diop", primary_contact="Awa Diop"
            )
            cls.student.family = family
            cls.student.save()
            Enrollment.objects.create(
                school=cls.school, student=cls.student, year=cls.year,
                classroom=cls.classroom, registration_paid=True,
                registration_amount=25_000, paid_at=cls.year.start_date,
            )
            MonthlyPayment.objects.create(
                school=cls.school, student=cls.student, year=cls.year,
                period=cls.year.fiscal_months[0], tuition=15_000,
            )
            Discount.objects.create(
                school=cls.school, student=cls.student, year=cls.year,
                kind=Discount.Kind.PERCENT, value=10,
                reason="Fratrie", approved_by="Direction",
            )
            ClassEnrollmentHistory.objects.create(
                school=cls.school, student=cls.student, year=cls.year,
                to_classroom=cls.classroom, effective_date=cls.year.start_date,
            )
            teacher = Teacher.objects.create(
                school=cls.school, first_name="Ousmane", last_name="Bodian"
            )
            rubric = SalaryRubric.objects.create(
                school=cls.school, code="A", label="Enseignants", teacher=teacher
            )
            Salary.objects.create(
                school=cls.school, rubric=rubric, year=cls.year,
                period=cls.year.fiscal_months[0], gross_amount=900_000,
            )
            Expense.objects.create(
                school=cls.school, year=cls.year,
                operation_date=cls.year.fiscal_months[0].replace(day=15),
                label="Loyer", amount=450_000, category=cls.category,
            )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_every_list_endpoint_returns_its_data(self):
        endpoints = [
            "/api/classes/", "/api/families/", "/api/students/",
            "/api/fee-schedules/", "/api/enrollments/", "/api/monthly-payments/",
            "/api/discounts/", "/api/class-history/",
            "/api/teachers/", "/api/salary-rubrics/", "/api/salaries/",
            "/api/expense-categories/", "/api/expenses/",
            "/api/school-years/", "/api/users/",
        ]
        empty = []
        for url in endpoints:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, f"{url} a répondu {response.status_code}")
            if response.data["count"] == 0:
                empty.append(url)

        self.assertEqual(
            empty, [],
            "Ces endpoints renvoient 0 résultat alors que la donnée existe — "
            "le filtrage tenant a probablement été figé à l'import du module.",
        )

    def test_detail_endpoints_are_reachable(self):
        response = self.client.get(f"/api/students/{self.student.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["full_name"], "Aminata Diop")

    def test_student_ledger_reports_partial_payment(self):
        """Un paiement partiel doit se distinguer d'un paiement complet."""
        response = self.client.get(f"/api/students/{self.student.pk}/ledger/")
        self.assertEqual(response.status_code, 200)

        october = response.data["months"][0]
        self.assertEqual(october["status"], "PAID")
        november = response.data["months"][1]
        self.assertEqual(november["status"], "UNPAID")
        self.assertGreater(response.data["balance"], 0)


class MatriculeSequenceTests(TestCase):
    """Le matricule est attribué par établissement, sans collision."""

    @classmethod
    def setUpTestData(cls):
        cls.school_a = make_school("École A", "ecole-a")
        cls.school_b = make_school("École B", "ecole-b")
        make_year(cls.school_a)
        make_year(cls.school_b)
        cls.admin_a = make_user(cls.school_a, Role.ADMIN, "admin@a.test")
        cls.admin_b = make_user(cls.school_b, Role.ADMIN, "admin@b.test")

    def create_teacher(self, user, first_name):
        client = APIClient()
        client.force_authenticate(user)
        return client.post(
            "/api/teachers/", {"first_name": first_name, "last_name": "Test"}, format="json"
        )

    def test_matricule_increments_across_api_creations(self):
        """Sans résolution préalable de l'établissement, tous vaudraient « 001 »."""
        matricules = [
            self.create_teacher(self.admin_a, f"Enseignant{index}").data["matricule"]
            for index in range(3)
        ]
        self.assertEqual(matricules, ["001", "002", "003"])

    def test_each_school_has_its_own_sequence(self):
        self.assertEqual(self.create_teacher(self.admin_a, "A1").data["matricule"], "001")
        self.assertEqual(self.create_teacher(self.admin_b, "B1").data["matricule"], "001")
        self.assertEqual(self.create_teacher(self.admin_a, "A2").data["matricule"], "002")

    def test_matricule_cannot_be_forced_by_the_client(self):
        client = APIClient()
        client.force_authenticate(self.admin_a)
        response = client.post(
            "/api/teachers/",
            {"first_name": "Test", "last_name": "Test", "matricule": "999"},
            format="json",
        )
        self.assertEqual(response.data["matricule"], "001")


class RouteDeclarationTests(TestCase):
    """Toute vue d'API est soit gouvernée par un rôle, soit explicitement publique.

    Une vue sans `resource` est refusée par `RoleBasedPermission` — le bon
    comportement, mais qui se manifeste en production par un 403 incompréhensible.
    Ce test force le choix à être conscient : déclarer une ressource, ou déclarer
    `AllowAny`. L'oubli, lui, est signalé ici.

    Les vues publiques légitimes sont celles qu'un tiers non authentifié doit
    pouvoir atteindre : demande de code SMS par un parent, webhook du prestataire
    de paiement. Chacune porte sa propre protection — limitation de débit pour les
    premières, signature HMAC pour la seconde.
    """

    def api_views(self):
        for pattern in get_resolver().url_patterns:
            for route in getattr(pattern, "url_patterns", []):
                view_class = getattr(getattr(route, "callback", None), "cls", None)
                if view_class is None:
                    continue
                if view_class.__module__.startswith("apps."):
                    yield view_class

    def test_every_view_is_role_gated_or_explicitly_public(self):
        from rest_framework.permissions import AllowAny

        undeclared = []
        for view_class in self.api_views():
            if hasattr(view_class, "resource"):
                continue
            permissions = getattr(view_class, "permission_classes", [])
            if AllowAny in permissions:
                continue
            # `LoginView` et `MeView` s'appuient sur l'authentification seule.
            if view_class.__name__ in {"LoginView", "MeView"}:
                continue
            undeclared.append(f"{view_class.__module__}.{view_class.__name__}")

        self.assertEqual(
            sorted(set(undeclared)), [],
            "Ces vues ne déclarent ni `resource` ni `AllowAny` — elles répondront "
            "403 sans explication.",
        )

    def test_public_views_are_a_short_known_list(self):
        """La surface non authentifiée doit rester petite et surveillée.

        Ce test échoue dès qu'une vue publique est ajoutée. C'est voulu : chaque
        ajout mérite une revue, pas un passage silencieux.
        """
        from rest_framework.permissions import AllowAny

        public = {
            view.__name__
            for view in self.api_views()
            if AllowAny in getattr(view, "permission_classes", [])
        }
        self.assertEqual(
            public,
            {
                "ParentOtpRequestView",    # limité en débit, ne révèle rien
                "ParentOtpVerifyView",     # code à usage unique, verrouillé
                "WaveWebhookView",         # signature HMAC obligatoire
                "SimulatedWaveCheckoutView",  # refusé hors DEBUG
            },
        )
