"""Ouverture d'un établissement par le super-administrateur.

Un établissement neuf doit pouvoir travailler le jour même : son année
courante, ses classes et ses accès. Les cas couverts ici sont ceux dont
l'échec se découvrirait au pire moment — une école sans année courante ne peut
ni encaisser ni noter.
"""

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.models import Role, School, SchoolYear, User
from apps.core.provisioning import provision_school, school_slug, temporary_password
from apps.core.tenancy import tenant_context, unscoped
from apps.core.tests.factories import make_school, make_user
from apps.students.models import ClassRoom

SUPER_PASSWORD = "MonEcole2026!"


class TemporaryPasswordTests(TestCase):
    def test_passwords_differ_from_one_account_to_another(self):
        """Un mot de passe commun serait devinable : le code est public."""
        drawn = {temporary_password() for _ in range(50)}
        self.assertEqual(len(drawn), 50)

    def test_ambiguous_characters_are_excluded(self):
        """Un mot de passe se dicte au téléphone : « l » contre « 1 » coûte un appel."""
        joined = "".join(temporary_password() for _ in range(40))
        for char in "lI1O0":
            self.assertNotIn(char, joined)


class SlugTests(TestCase):
    def test_accents_and_spaces_are_folded(self):
        self.assertEqual(school_slug("École Sainte-Thérèse"), "ecole-sainte-therese")

    def test_a_duplicate_name_gets_its_own_slug(self):
        make_school(name="Les Palmiers", slug="les-palmiers")
        self.assertEqual(school_slug("Les Palmiers"), "les-palmiers-2")


class ProvisioningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.super_admin = User.objects.create_user(
            email="super@monecole.sn", password=SUPER_PASSWORD,
            role=Role.SUPER_ADMIN, school=None,
        )
        cls.other_school = make_school()
        cls.admin = make_user(cls.other_school, Role.ADMIN, "admin@autre.sn")

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.force_authenticate(self.super_admin)

    def provision(self, name="École de la Médina", start_year=2026):
        return self.client.post(
            "/api/schools/provision/",
            {"name": name, "start_year": start_year},
            format="json",
        )

    def test_a_school_opens_with_its_year_classes_and_accounts(self):
        response = self.provision()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["year"], "2026/2027")
        self.assertEqual(len(response.data["accounts"]), 3)

        with unscoped():
            school = School.objects.get(slug="ecole-de-la-medina")
        with tenant_context(school):
            year = SchoolYear.objects.get(school=school)
            self.assertTrue(year.is_current)
            self.assertEqual(ClassRoom.objects.count(), 10)
            self.assertEqual(User.objects.filter(school=school).count(), 3)

    def test_the_fiscal_year_runs_october_to_september(self):
        """Les deux calendriers de l'école : celui-ci est l'exercice financier."""
        self.provision(start_year=2026)
        with unscoped():
            year = SchoolYear.objects.get(school__slug="ecole-de-la-medina")
        self.assertEqual((year.start_date.month, year.start_date.day), (10, 1))
        self.assertEqual((year.end_date.month, year.end_date.day), (9, 30))

    def test_the_three_roles_are_created(self):
        response = self.provision()
        self.assertEqual(
            {a["role"] for a in response.data["accounts"]},
            {Role.ADMIN, Role.SECRETARY, Role.TEACHER},
        )

    def test_every_account_must_change_its_password(self):
        self.provision()
        with unscoped():
            users = User.objects.filter(school__slug="ecole-de-la-medina")
            self.assertTrue(all(u.must_change_password for u in users))

    def test_the_passwords_are_returned_once_and_work(self):
        response = self.provision()
        account = next(a for a in response.data["accounts"] if a["role"] == Role.ADMIN)

        client = APIClient()
        login = client.post(
            "/api/auth/login/",
            {"email": account["email"], "password": account["password"]},
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.data)

    def test_an_administrator_cannot_open_a_school(self):
        client = APIClient()
        client.force_authenticate(self.admin)
        response = client.post(
            "/api/schools/provision/",
            {"name": "École pirate", "start_year": 2026},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_a_missing_name_or_year_is_refused(self):
        self.assertEqual(self.provision(name="").status_code, 400)
        self.assertEqual(self.provision(start_year=1899).status_code, 400)

    def test_a_failed_creation_leaves_nothing_behind(self):
        """Tout ou rien : une école à moitié créée se découvrirait au pire moment."""
        before = School.objects.count()
        with self.assertRaises(Exception):
            provision_school(name="École cassée", start_year=None)
        self.assertEqual(School.objects.count(), before)


class ProvisionalPasswordLockTests(TestCase):
    """Tant que le mot de passe provisoire tient, le compte ne fait rien d'autre.

    Un écran de rappel côté interface laisserait l'API grande ouverte à un mot
    de passe qui a transité par courrier ou par téléphone.
    """

    @classmethod
    def setUpTestData(cls):
        with unscoped():
            cls.school, cls.year, cls.accounts = provision_school(
                name="École du Verrou", start_year=2026
            )
        cls.account = next(a for a in cls.accounts if a.role == Role.ADMIN)

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        login = self.client.post(
            "/api/auth/login/",
            {"email": self.account.email, "password": self.account.password},
            format="json",
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    def test_the_application_is_closed(self):
        for path in ["/api/students/", "/api/classes/", "/api/auth/sessions/"]:
            self.assertEqual(self.client.get(path).status_code, 403, path)

    def test_the_profile_stays_readable(self):
        """Sans quoi l'interface ne saurait pas quoi afficher."""
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

    def test_changing_the_password_opens_the_application(self):
        response = self.client.post(
            "/api/auth/me/password/",
            {
                "current_password": self.account.password,
                "new_password": "Medina-Rentree-2026",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)

        login = APIClient()
        fresh = login.post(
            "/api/auth/login/",
            {"email": self.account.email, "password": "Medina-Rentree-2026"},
            format="json",
        )
        login.credentials(HTTP_AUTHORIZATION=f"Bearer {fresh.data['access']}")
        self.assertEqual(login.get("/api/students/").status_code, 200)

    def test_the_flag_is_reported_to_the_interface(self):
        profile = self.client.get("/api/auth/me/")
        self.assertTrue(profile.data["must_change_password"])
