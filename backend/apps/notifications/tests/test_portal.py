"""Portail parent : authentification par SMS et cloisonnement des données.

Le portail expose des données d'enfants mineurs à un public non professionnel,
authentifié par un simple numéro de téléphone. C'est la surface la plus exposée du
produit — d'où le poids des tests d'isolation et d'énumération ici.
"""

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import Role
from apps.core.tenancy import tenant_context, unscoped
from apps.core.tests.factories import (
    make_classroom,
    make_fee_schedule,
    make_school,
    make_student,
    make_year,
)
from apps.notifications.models import OTP_MAX_ATTEMPTS, OtpCode
from apps.notifications.sms import SmsResult, normalize_phone
from apps.students.models import Family, MonthlyPayment

PHONE = "+221 77 123 45 67"
NORMALIZED = "221771234567"

# Résultat d'envoi simulé. Un `MagicMock` nu ne convient pas : son attribut
# `status` finirait écrit tel quel dans la boîte d'envoi.
SIMULATED = SmsResult(success=True, message_id="sim_test", simulated=True, segments=1)


class PhoneNormalizationTests(TestCase):
    """Les numéros sont saisis dans tous les formats imaginables."""

    def test_all_senegalese_forms_converge(self):
        for raw in (
            "+221771234567", "00221771234567", "221771234567",
            "771234567", "77 123 45 67", "77-123-45-67",
            "(221) 77.123.45.67", "0771234567",
        ):
            self.assertEqual(
                normalize_phone(raw), NORMALIZED, f"« {raw} » mal normalisé."
            )

    def test_empty_input_is_safe(self):
        self.assertEqual(normalize_phone(""), "221")


class OtpRequestTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.year = make_year(cls.school)
        cls.classroom = make_classroom(cls.school, "CP")
        make_fee_schedule(cls.school, cls.classroom, cls.year)
        cls.student = make_student(cls.school, cls.classroom, "Awa", "Diop")
        with tenant_context(cls.school):
            cls.student.parent_phone = PHONE
            cls.student.parent_name = "Fatou Diop"
            cls.student.save()

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def request_code(self, phone=PHONE):
        return self.client.post(
            "/api/portal/auth/request-code/", {"phone": phone}, format="json"
        )

    @patch("apps.notifications.services.send_sms", return_value=SIMULATED)
    def test_known_number_receives_a_code(self, send_sms):
        response = self.request_code()
        self.assertEqual(response.status_code, 200)
        send_sms.assert_called_once()
        with unscoped():
            self.assertEqual(OtpCode.objects.filter(phone=NORMALIZED).count(), 1)

    @patch("apps.notifications.services.send_sms", return_value=SIMULATED)
    def test_unknown_number_gets_the_same_answer(self, send_sms):
        """L'endpoint ne doit pas permettre d'énumérer les parents d'une école."""
        known = self.request_code()
        unknown = self.request_code("+221 70 000 00 00")

        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.data["detail"], unknown.data["detail"])
        # Aucun SMS pour un numéro inconnu : la réponse est identique, pas le coût.
        self.assertEqual(send_sms.call_count, 1)

    @patch("apps.notifications.services.send_sms", return_value=SIMULATED)
    def test_requesting_again_invalidates_the_previous_code(self, send_sms):
        self.request_code()
        self.request_code()
        with unscoped():
            live = OtpCode.objects.filter(phone=NORMALIZED, consumed_at__isnull=True)
            self.assertEqual(live.count(), 1, "Un seul code doit rester actif.")

    def test_missing_phone_is_rejected(self):
        response = self.client.post("/api/portal/auth/request-code/", {}, format="json")
        self.assertEqual(response.status_code, 400)


class OtpVerifyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.year = make_year(cls.school)
        cls.classroom = make_classroom(cls.school, "CP")
        make_fee_schedule(cls.school, cls.classroom, cls.year)
        cls.student = make_student(cls.school, cls.classroom, "Awa", "Diop")
        with tenant_context(cls.school):
            cls.student.parent_phone = PHONE
            cls.student.parent_name = "Fatou Diop"
            cls.student.save()

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        with tenant_context(self.school):
            self.otp, self.code = OtpCode.issue(self.school, NORMALIZED)

    def verify(self, code, phone=PHONE):
        return self.client.post(
            "/api/portal/auth/verify-code/", {"phone": phone, "code": code}, format="json"
        )

    def test_correct_code_returns_tokens_and_children(self):
        response = self.verify(self.code)
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertEqual(len(response.data["children"]), 1)
        self.assertEqual(response.data["children"][0]["name"], "Awa Diop")

    def test_code_is_single_use(self):
        self.assertEqual(self.verify(self.code).status_code, 200)
        self.assertEqual(self.verify(self.code).status_code, 400)

    def test_wrong_code_is_refused(self):
        wrong = "000000" if self.code != "000000" else "111111"
        self.assertEqual(self.verify(wrong).status_code, 400)

    def test_code_is_bound_to_its_phone_number(self):
        """Un code intercepté ne doit valoir que pour la ligne qui l'a reçu."""
        with tenant_context(self.school):
            other = make_student(self.school, self.classroom, "Moussa", "Fall")
            other.parent_phone = "+221 70 999 88 77"
            other.save()
        self.assertEqual(self.verify(self.code, "+221 70 999 88 77").status_code, 400)

    def test_expired_code_is_refused(self):
        with unscoped():
            OtpCode.objects.filter(pk=self.otp.pk).update(
                expires_at=timezone.now() - timezone.timedelta(minutes=1)
            )
        self.assertEqual(self.verify(self.code).status_code, 400)

    def test_brute_force_locks_the_code(self):
        for _ in range(OTP_MAX_ATTEMPTS):
            self.verify("000000")
        response = self.verify(self.code)
        self.assertEqual(
            response.status_code, 429,
            "Après cinq essais, le code doit être verrouillé même s'il est correct.",
        )

    def test_code_is_not_stored_in_clear_text(self):
        with unscoped():
            stored = OtpCode.objects.get(pk=self.otp.pk)
        self.assertNotIn(self.code, stored.code_hash)
        self.assertEqual(len(stored.code_hash), 64)


class ParentPortalScopeTests(TestCase):
    """Un parent ne voit que ses propres enfants, dans sa propre école."""

    @classmethod
    def setUpTestData(cls):
        cls.school = make_school("École A", "ecole-a")
        cls.other_school = make_school("École B", "ecole-b")
        cls.year = make_year(cls.school)
        make_year(cls.other_school)

        cls.classroom = make_classroom(cls.school, "CP")
        make_fee_schedule(cls.school, cls.classroom, cls.year)
        cls.other_classroom = make_classroom(cls.other_school, "CP")

        with tenant_context(cls.school):
            family = Family.objects.create(
                school=cls.school, name="Diop", primary_contact="Fatou Diop", phone=PHONE
            )
            cls.mine = make_student(cls.school, cls.classroom, "Awa", "Diop")
            cls.mine.family = family
            cls.mine.parent_phone = PHONE
            cls.mine.save()

            cls.sibling = make_student(cls.school, cls.classroom, "Ibrahima", "Diop")
            cls.sibling.family = family
            cls.sibling.save()

            cls.stranger = make_student(cls.school, cls.classroom, "Moussa", "Fall")
            cls.stranger.parent_phone = "+221 70 555 44 33"
            cls.stranger.save()

        with tenant_context(cls.other_school):
            cls.foreign = make_student(cls.other_school, cls.other_classroom, "Ndeye", "Ba")
            # Même numéro de parent, autre établissement : ne doit rien ouvrir ici.
            cls.foreign.parent_phone = PHONE
            cls.foreign.save()

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        with tenant_context(self.school):
            otp, code = OtpCode.issue(self.school, NORMALIZED)
        response = self.client.post(
            "/api/portal/auth/verify-code/",
            {"phone": PHONE, "code": code},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")

    def test_siblings_are_grouped_through_the_family(self):
        response = self.client.get("/api/portal/children/")
        self.assertEqual(response.status_code, 200)
        names = sorted(child["name"] for child in response.data["children"])
        self.assertEqual(names, ["Awa Diop", "Ibrahima Diop"])

    def test_other_families_children_are_invisible(self):
        response = self.client.get(f"/api/portal/children/{self.stranger.pk}/ledger/")
        self.assertEqual(response.status_code, 404)

    def test_same_phone_in_another_school_is_not_reachable(self):
        """Le rattachement est par établissement, pas par numéro seul."""
        response = self.client.get(f"/api/portal/children/{self.foreign.pk}/ledger/")
        self.assertEqual(response.status_code, 404)

    def test_ledger_reports_what_is_actually_due_now(self):
        with tenant_context(self.school):
            MonthlyPayment.objects.create(
                school=self.school, student=self.mine, year=self.year,
                period=self.year.tuition_month_ends[0], tuition=15_000,
            )
        response = self.client.get(f"/api/portal/children/{self.mine.pk}/ledger/")
        self.assertEqual(response.status_code, 200)
        data = response.data

        self.assertEqual(data["months"][0]["status"], "PAID")
        # Dû : inscription 25 000 + 9 × 15 000 = 160 000. Réglé : 15 000.
        self.assertEqual(data["total_due"], 160_000)
        self.assertEqual(data["total_paid"], 15_000)
        self.assertEqual(data["balance"], 145_000)
        self.assertNotIn(
            data["months"][0]["period"],
            [m["period"] for m in data["months"] if m["balance"] > 0],
            "Le mois réglé ne doit plus figurer parmi les impayés.",
        )

    def test_due_now_excludes_months_not_yet_elapsed(self):
        """Distinction entre ce qui est exigible aujourd'hui et le total de l'année.

        Vérifié sur une année à venir, dont aucun mois n'est échu — sur l'année
        courante, tous les mois de mensualité le sont déjà et les deux montants
        coïncident, ce qui ne prouverait rien.
        """
        from apps.core.models import SchoolYear

        with tenant_context(self.school):
            SchoolYear.objects.filter(pk=self.year.pk).update(is_current=False)
            future = make_year(self.school, start_year=2030)
            make_fee_schedule(self.school, self.classroom, future)

        response = self.client.get(f"/api/portal/children/{self.mine.pk}/ledger/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["due_now"], 25_000, "Seule l'inscription est exigible.")
        self.assertEqual(response.data["balance"], 160_000)

    def test_parent_cannot_reach_the_administration(self):
        for url in ("/api/reports/bilan/", "/api/expenses/", "/api/teachers/"):
            self.assertEqual(
                self.client.get(url).status_code, 403, f"{url} accessible à un parent."
            )

    def test_parent_cannot_list_all_students(self):
        response = self.client.get("/api/students/")
        self.assertEqual(response.status_code, 200)
        names = [row["full_name"] for row in response.data["results"]]
        self.assertNotIn("Moussa Fall", names)
