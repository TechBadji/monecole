"""Matrice de permissions par rôle.

Vérifie la séparation des tâches exigée par le cahier des charges, en particulier
que le comptable ne peut pas créer ou supprimer d'élèves et que la secrétaire n'a
qu'un accès en lecture aux données financières.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import Role
from apps.core.permissions import ADD, CHANGE, DELETE, VIEW, has_perm
from apps.core.tenancy import tenant_context
from apps.students.models import Student

from .factories import (
    make_classroom,
    make_fee_schedule,
    make_school,
    make_student,
    make_user,
    make_year,
)


class PermissionMatrixTests(TestCase):
    """La matrice elle-même, indépendamment du transport HTTP."""

    def test_accountant_reads_students_but_cannot_create_or_delete(self):
        self.assertTrue(has_perm(Role.ACCOUNTANT, "student", VIEW))
        self.assertFalse(has_perm(Role.ACCOUNTANT, "student", ADD))
        self.assertFalse(has_perm(Role.ACCOUNTANT, "student", CHANGE))
        self.assertFalse(has_perm(Role.ACCOUNTANT, "student", DELETE))

    def test_accountant_records_payments_but_cannot_delete_them(self):
        """Supprimer un encaissement doit rester un geste d'administrateur."""
        self.assertTrue(has_perm(Role.ACCOUNTANT, "monthlypayment", ADD))
        self.assertTrue(has_perm(Role.ACCOUNTANT, "monthlypayment", CHANGE))
        self.assertFalse(has_perm(Role.ACCOUNTANT, "monthlypayment", DELETE))

    def test_secretary_manages_students_but_only_reads_finances(self):
        self.assertTrue(has_perm(Role.SECRETARY, "student", ADD))
        self.assertTrue(has_perm(Role.SECRETARY, "student", DELETE))
        self.assertTrue(has_perm(Role.SECRETARY, "monthlypayment", VIEW))
        self.assertFalse(has_perm(Role.SECRETARY, "monthlypayment", ADD))
        self.assertFalse(has_perm(Role.SECRETARY, "expense", ADD))

    def test_secretary_has_no_access_to_reports(self):
        self.assertFalse(has_perm(Role.SECRETARY, "report", VIEW))

    def test_admin_has_full_control_over_its_school(self):
        for resource in ("student", "monthlypayment", "expense", "teacher", "salary"):
            for action in (VIEW, ADD, CHANGE, DELETE):
                self.assertTrue(
                    has_perm(Role.ADMIN, resource, action),
                    f"L'administrateur devrait pouvoir {action} sur {resource}.",
                )

    def test_teacher_and_parent_are_read_only(self):
        for role in (Role.TEACHER, Role.PARENT):
            self.assertTrue(has_perm(role, "student", VIEW))
            self.assertFalse(has_perm(role, "student", ADD))
            self.assertFalse(has_perm(role, "student", CHANGE))
            self.assertFalse(has_perm(role, "student", DELETE))

    def test_parent_cannot_reach_reports_or_expenses(self):
        self.assertFalse(has_perm(Role.PARENT, "report", VIEW))
        self.assertFalse(has_perm(Role.PARENT, "expense", VIEW))
        self.assertFalse(has_perm(Role.PARENT, "teacher", VIEW))

    def test_super_admin_has_no_reach_into_school_finances(self):
        """Le super-administrateur gère la plateforme, pas la comptabilité des écoles."""
        self.assertFalse(has_perm(Role.SUPER_ADMIN, "monthlypayment", VIEW))
        self.assertFalse(has_perm(Role.SUPER_ADMIN, "expense", VIEW))
        self.assertFalse(has_perm(Role.SUPER_ADMIN, "report", VIEW))

    def test_unknown_resource_is_denied(self):
        """Un oubli de déclaration doit fermer l'accès, pas l'ouvrir."""
        self.assertFalse(has_perm(Role.ADMIN, "ressource-inexistante", VIEW))


class PermissionEnforcementTests(TestCase):
    """La matrice est bien appliquée par l'API."""

    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.year = make_year(cls.school)
        cls.classroom = make_classroom(cls.school, "CP")
        make_fee_schedule(cls.school, cls.classroom, cls.year)
        cls.student = make_student(cls.school, cls.classroom)
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")
        cls.accountant = make_user(cls.school, Role.ACCOUNTANT, "compta@test.sn")
        cls.secretary = make_user(cls.school, Role.SECRETARY, "secret@test.sn")

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_accountant_cannot_create_a_student(self):
        response = self.client_for(self.accountant).post(
            "/api/students/",
            {"first_name": "Nouveau", "last_name": "Élève", "classroom": self.classroom.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_accountant_cannot_delete_a_student(self):
        response = self.client_for(self.accountant).delete(f"/api/students/{self.student.pk}/")
        self.assertEqual(response.status_code, 403)
        with tenant_context(self.school):
            self.assertTrue(Student.objects.filter(pk=self.student.pk).exists())

    def test_accountant_can_list_students(self):
        response = self.client_for(self.accountant).get("/api/students/")
        self.assertEqual(response.status_code, 200)

    def test_accountant_can_record_a_payment(self):
        response = self.client_for(self.accountant).post(
            "/api/monthly-payments/",
            {
                "student": self.student.pk, "year": self.year.pk,
                "period": "2025-10-31", "tuition": 15_000,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

    def test_secretary_cannot_record_a_payment(self):
        response = self.client_for(self.secretary).post(
            "/api/monthly-payments/",
            {
                "student": self.student.pk, "year": self.year.pk,
                "period": "2025-10-31", "tuition": 15_000,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_secretary_cannot_open_the_balance_sheet(self):
        response = self.client_for(self.secretary).get("/api/reports/bilan/")
        self.assertEqual(response.status_code, 403)

    def test_admin_and_accountant_can_open_the_balance_sheet(self):
        for user in (self.admin, self.accountant):
            response = self.client_for(user).get("/api/reports/bilan/")
            self.assertEqual(response.status_code, 200, f"Refusé pour {user.role}.")

    def test_secretary_can_create_a_student(self):
        response = self.client_for(self.secretary).post(
            "/api/students/",
            {"first_name": "Nouveau", "last_name": "Élève", "classroom": self.classroom.pk},
            format="json",
        )
        self.assertEqual(response.status_code, 201)


class ExpenseApprovalTests(TestCase):
    """Séparation des tâches sur les dépenses importantes."""

    @classmethod
    def setUpTestData(cls):
        from apps.core.tests.factories import make_category

        cls.school = make_school()
        cls.year = make_year(cls.school)
        cls.category = make_category(cls.school, "RENT", "LOCATIONS DE BÂTIMENTS")
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")
        cls.accountant = make_user(cls.school, Role.ACCOUNTANT, "compta@test.sn")

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def _payload(self, amount):
        return {
            "year": self.year.pk, "operation_date": "2025-11-10",
            "label": "Dépense de test", "amount": amount, "category": self.category.pk,
        }

    def test_large_expense_by_accountant_awaits_approval(self):
        response = self.client_for(self.accountant).post(
            "/api/expenses/", self._payload(600_000), format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "PENDING")

    def test_small_expense_by_accountant_is_approved_immediately(self):
        response = self.client_for(self.accountant).post(
            "/api/expenses/", self._payload(50_000), format="json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "APPROVED")

    def test_accountant_cannot_approve_its_own_expense(self):
        created = self.client_for(self.accountant).post(
            "/api/expenses/", self._payload(600_000), format="json"
        )
        response = self.client_for(self.accountant).post(
            f"/api/expenses/{created.data['id']}/approve/"
        )
        self.assertEqual(response.status_code, 403)

    def test_admin_approves_a_pending_expense(self):
        created = self.client_for(self.accountant).post(
            "/api/expenses/", self._payload(600_000), format="json"
        )
        response = self.client_for(self.admin).post(
            f"/api/expenses/{created.data['id']}/approve/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "APPROVED")
        self.assertTrue(response.data["approved_by"])

    def test_pending_expense_stays_out_of_the_balance_until_approved(self):
        from apps.reports.services import bilan

        self.client_for(self.accountant).post(
            "/api/expenses/", self._payload(600_000), format="json"
        )
        with tenant_context(self.school):
            self.assertEqual(bilan(self.year)["total_charges"]["total"], 0)
