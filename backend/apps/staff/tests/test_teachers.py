"""Personnel enseignant : création, modification et départ.

Les cas couverts ici sont ceux dont l'échec passerait inaperçu : un matricule
imposé par le client, des coordonnées absentes du sérialiseur alors que le
modèle les porte, ou un enseignant supprimé avec ses bulletins de paie.
"""

from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import Role
from apps.core.tenancy import tenant_context
from apps.core.tests.factories import make_school, make_user
from apps.staff.models import Teacher


class TeacherCrudTests(TestCase):
    """Création et modification d'un enseignant depuis l'écran d'administration.

    Le matricule est attribué par le système, jamais soumis : un client qui
    l'imposerait créerait des collisions que la contrainte d'unicité ne
    signalerait qu'à l'insertion suivante.
    """

    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")
        cls.accountant = make_user(cls.school, Role.ACCOUNTANT, "compta@test.sn")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def create(self, **extra):
        payload = {
            "first_name": "Fatou", "last_name": "Ndione",
            "email": "fatou@test.sn", "phone": "+221771234567",
            "contract_type": "PERMANENT",
        }
        payload.update(extra)
        return self.client.post("/api/teachers/", payload, format="json")

    def test_a_teacher_is_created_with_an_automatic_matricule(self):
        response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["matricule"])
        self.assertEqual(response.data["full_name"], "Fatou Ndione")

    def test_a_submitted_matricule_is_ignored(self):
        response = self.create(matricule="TRICHE")
        self.assertNotEqual(response.data["matricule"], "TRICHE")

    def test_contact_details_are_exposed(self):
        """Ils manquaient au sérialiseur alors que le modèle les portait."""
        response = self.create(address="Sicap Liberté 6", emergency_contact="+221770000000")
        for field in ["phone", "email", "address", "emergency_contact"]:
            self.assertIn(field, response.data, field)
        self.assertEqual(response.data["address"], "Sicap Liberté 6")

    def test_a_teacher_can_be_edited(self):
        created = self.create()
        response = self.client.patch(
            f"/api/teachers/{created.data['id']}/",
            {"function": "Maîtresse titulaire", "phone": "+221780000000"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["function"], "Maîtresse titulaire")

    def test_a_departure_is_marked_not_deleted(self):
        """Supprimer emporterait bulletins de paie, notes et historique."""
        created = self.create()
        response = self.client.patch(
            f"/api/teachers/{created.data['id']}/", {"is_active": False}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_active"])

        with tenant_context(self.school):
            self.assertTrue(Teacher.objects.filter(pk=created.data["id"]).exists())

    def test_the_account_link_is_reported(self):
        """Un enseignant sans compte ne peut pas saisir ses notes."""
        without = self.create()
        self.assertFalse(without.data["has_account"])

        make_user(self.school, Role.TEACHER, "avec@test.sn")
        with_account = self.create(
            first_name="Cheikh", last_name="Sy", email="avec@test.sn"
        )
        self.assertTrue(with_account.data["has_account"])

    def test_an_accountant_cannot_create_a_teacher(self):
        client = APIClient()
        client.force_authenticate(self.accountant)
        response = client.post(
            "/api/teachers/",
            {"first_name": "Pirate", "last_name": "Test", "contract_type": "PERMANENT"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
