"""Compte utilisateur : profil, photo, mot de passe, réinitialisation, sessions.

Les cas couverts ici sont ceux dont l'échec est silencieux : une révocation qui
ne révoque rien, une réponse qui trahit l'existence d'une adresse, un jeton qui
resservirait une seconde fois.
"""

import io
import tempfile
from datetime import timedelta

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.core.models import LoginSession, PasswordResetToken, Role, User
from apps.core.tests.factories import make_school, make_user

PASSWORD = "MonEcole2026!"
NEW_PASSWORD = "Kaolack-2027-Thies"


def png_bytes(size=(64, 64), color=(31, 56, 100)):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


class AccountTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.user = make_user(cls.school, Role.ADMIN, "admin@test.sn")
        cls.user.set_password(PASSWORD)
        cls.user.first_name = "Awa"
        cls.user.last_name = "Diop"
        cls.user.save()

    def setUp(self):
        self.client = APIClient()
        # Le limiteur de débit compte dans le cache, partagé d'un test à
        # l'autre : sans ce nettoyage, la suite se bride elle-même. On le vide
        # plutôt que de désactiver la protection, qui reste ainsi testable.
        cache.clear()

    def login(self, remember=False, agent="Mozilla/5.0 (iPhone) Safari/605"):
        response = self.client.post(
            "/api/auth/login/",
            {"email": self.user.email, "password": PASSWORD, "remember_me": remember},
            format="json",
            HTTP_USER_AGENT=agent,
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        return response.data


class ProfileTests(AccountTestCase):
    def test_profile_is_updated_and_returned_whole(self):
        self.login()
        response = self.client.patch(
            "/api/auth/me/profile/",
            {"first_name": "Awa", "last_name": "Ndiaye", "phone": "+221 771234567"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["full_name"], "Awa Ndiaye")
        self.assertEqual(response.data["phone"], "+221 771234567")
        # La réponse porte le profil complet : l'écran n'a pas à recharger.
        self.assertIn("permissions", response.data)
        self.assertEqual(response.data["initials"], "AN")

    def test_role_and_school_cannot_be_raised_through_the_profile_form(self):
        """Le point d'entrée le plus tentant pour une élévation de privilège."""
        self.login()
        other = make_school(name="Autre école", slug="autre")
        response = self.client.patch(
            "/api/auth/me/profile/",
            {"role": Role.SUPER_ADMIN, "school": other.id, "email": "pirate@test.sn"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, Role.ADMIN)
        self.assertEqual(self.user.school_id, self.school.id)
        self.assertEqual(self.user.email, "admin@test.sn")

    def test_initials_fall_back_to_the_email(self):
        """Un compte peut exister sans état civil ; la vignette doit tenir."""
        user = make_user(self.school, Role.TEACHER, "sansnom@test.sn")
        user.first_name = user.last_name = ""
        self.assertEqual(user.initials, "SA")


# Les photos partent sur le disque : un répertoire jetable évite de semer des
# fichiers dans `backend/media/` à chaque exécution de la suite.
@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="monecole-test-media-"))
class ProfilePhotoTests(AccountTestCase):
    def test_photo_is_squared_and_downscaled(self):
        from PIL import Image

        self.login()
        upload = png_bytes(size=(1600, 900))
        upload.name = "photo.png"
        response = self.client.post(
            "/api/auth/me/photo/", {"photo": upload}, format="multipart"
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIsNotNone(response.data["photo"])

        self.user.refresh_from_db()
        with Image.open(self.user.photo.path) as image:
            self.assertEqual(image.size, (512, 512))

    def test_a_pdf_renamed_as_png_is_refused(self):
        self.login()
        fake = io.BytesIO(b"%PDF-1.4 ceci n'est pas une image")
        fake.name = "photo.png"
        response = self.client.post(
            "/api/auth/me/photo/",
            {"photo": fake},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("image", response.data["detail"].lower())

    def test_photo_can_be_removed(self):
        self.login()
        upload = png_bytes()
        upload.name = "photo.png"
        self.client.post("/api/auth/me/photo/", {"photo": upload}, format="multipart")
        response = self.client.delete("/api/auth/me/photo/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["photo"])


class PasswordChangeTests(AccountTestCase):
    def test_password_is_changed_and_other_devices_are_closed(self):
        # Deux appareils connectés.
        phone = self.login(agent="Mozilla/5.0 (iPhone) Safari/605")
        phone_session = LoginSession.objects.get(sid=phone["sid"])
        desk = self.login(agent="Mozilla/5.0 (Windows NT) Chrome/120")

        response = self.client.post(
            "/api/auth/me/password/",
            {"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["sessions_closed"], 1)

        phone_session.refresh_from_db()
        self.assertIsNotNone(phone_session.revoked_at)
        # L'appareil courant survit.
        self.assertIsNone(LoginSession.objects.get(sid=desk["sid"]).revoked_at)

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    def test_wrong_current_password_is_refused(self):
        self.login()
        response = self.client.post(
            "/api/auth/me/password/",
            {"current_password": "faux", "new_password": NEW_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("current_password", response.data)

    def test_a_weak_password_is_refused_with_a_reason(self):
        self.login()
        response = self.client.post(
            "/api/auth/me/password/",
            {"current_password": PASSWORD, "new_password": "12345678"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("new_password", response.data)

    def test_reusing_the_same_password_is_refused(self):
        self.login()
        response = self.client.post(
            "/api/auth/me/password/",
            {"current_password": PASSWORD, "new_password": PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 400)


class SessionRevocationTests(AccountTestCase):
    def test_a_revoked_session_stops_working_immediately(self):
        """Sans cela, « Déconnecter cet appareil » ne serait qu'un bouton."""
        phone = self.login(agent="Mozilla/5.0 (iPhone) Safari/605")
        phone_client = APIClient()
        phone_client.credentials(HTTP_AUTHORIZATION=f"Bearer {phone['access']}")
        self.assertEqual(phone_client.get("/api/auth/me/").status_code, 200)

        self.login(agent="Mozilla/5.0 (Windows NT) Chrome/120")
        session = LoginSession.objects.get(sid=phone["sid"])
        response = self.client.delete(f"/api/auth/sessions/{session.id}/")
        self.assertEqual(response.status_code, 200, response.data)

        self.assertEqual(phone_client.get("/api/auth/me/").status_code, 401)

    def test_revocation_survives_a_token_refresh(self):
        """Le `jti` change à chaque renouvellement ; le `sid`, non.

        C'est le défaut qui rendrait la révocation inopérante au bout de trente
        minutes sans qu'aucun test ne s'en aperçoive.
        """
        data = self.login()
        refreshed = self.client.post(
            "/api/auth/refresh/", {"refresh": data["refresh"]}, format="json"
        )
        self.assertEqual(refreshed.status_code, 200)

        new_client = APIClient()
        new_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {refreshed.data['access']}"
        )
        self.assertEqual(new_client.get("/api/auth/me/").status_code, 200)

        LoginSession.objects.filter(sid=data["sid"]).update(
            revoked_at=timezone.now()
        )
        self.assertEqual(new_client.get("/api/auth/me/").status_code, 401)

    def test_the_device_label_is_readable(self):
        data = self.login(agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Safari/605.1")
        self.assertEqual(
            LoginSession.objects.get(sid=data["sid"]).device_label, "Safari sur iPhone"
        )

    def test_sessions_of_other_users_are_invisible_and_unrevocable(self):
        other = make_user(self.school, Role.TEACHER, "autre@test.sn")
        other.set_password(PASSWORD)
        other.save()
        foreign = LoginSession.objects.create(
            user=other,
            sid="autre-session",
            expires_at=timezone.now() + timedelta(days=1),
        )

        self.login()
        listed = self.client.get("/api/auth/sessions/")
        self.assertNotIn(foreign.id, [row["id"] for row in listed.data])
        self.assertEqual(
            self.client.delete(f"/api/auth/sessions/{foreign.id}/").status_code, 404
        )
        foreign.refresh_from_db()
        self.assertIsNone(foreign.revoked_at)

    def test_the_current_session_is_flagged_and_not_revocable_from_the_list(self):
        data = self.login()
        listed = self.client.get("/api/auth/sessions/")
        current = next(row for row in listed.data if row["is_current"])
        self.assertEqual(
            LoginSession.objects.get(pk=current["id"]).sid, data["sid"]
        )
        response = self.client.delete(f"/api/auth/sessions/{current['id']}/")
        self.assertEqual(response.status_code, 400)


class RememberMeTests(AccountTestCase):
    def test_remembering_lengthens_the_session(self):
        short = self.login(remember=False)
        long = self.login(remember=True)

        self.assertFalse(short["remembered"])
        self.assertTrue(long["remembered"])
        self.assertTrue(LoginSession.objects.get(sid=long["sid"]).remembered)

        gap = (
            LoginSession.objects.get(sid=long["sid"]).expires_at
            - LoginSession.objects.get(sid=short["sid"]).expires_at
        )
        self.assertGreater(gap, timedelta(days=28))


@override_settings(PUBLIC_BASE_URL="https://ecole.example")
class PasswordResetTests(AccountTestCase):
    def request_reset(self, email):
        return self.client.post(
            "/api/auth/password-reset/", {"email": email}, format="json"
        )

    def test_a_link_is_sent_and_lets_the_password_be_reset(self):
        response = self.request_reset(self.user.email)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

        token = PasswordResetToken.objects.get(user=self.user)
        raw = self.extract_token(mail.outbox[0].body)
        self.assertEqual(PasswordResetToken.hash(raw), token.token_hash)

        confirm = self.client.post(
            "/api/auth/password-reset/confirm/",
            {"token": raw, "new_password": NEW_PASSWORD},
            format="json",
        )
        self.assertEqual(confirm.status_code, 200, confirm.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

    @staticmethod
    def extract_token(body):
        import re

        return re.search(r"token=([\w\-]+)", body).group(1)

    def test_an_unknown_address_gets_the_same_answer_as_a_known_one(self):
        """Sinon le formulaire énumère le personnel de l'établissement."""
        known = self.request_reset(self.user.email)
        mail.outbox.clear()
        unknown = self.request_reset("personne@test.sn")

        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.data, unknown.data)
        self.assertEqual(len(mail.outbox), 0)

    def test_the_raw_token_is_never_stored(self):
        self.request_reset(self.user.email)
        raw = self.extract_token(mail.outbox[0].body)
        self.assertFalse(
            PasswordResetToken.objects.filter(token_hash=raw).exists(),
            "Le jeton est stocké en clair : une fuite de la table ouvrirait les comptes.",
        )

    def test_a_token_serves_only_once(self):
        self.request_reset(self.user.email)
        raw = self.extract_token(mail.outbox[0].body)
        payload = {"token": raw, "new_password": NEW_PASSWORD}

        self.assertEqual(
            self.client.post(
                "/api/auth/password-reset/confirm/", payload, format="json"
            ).status_code,
            200,
        )
        second = self.client.post(
            "/api/auth/password-reset/confirm/",
            {"token": raw, "new_password": "Encore-Un-Autre-2027"},
            format="json",
        )
        self.assertEqual(second.status_code, 400)

    def test_an_expired_token_is_refused(self):
        self.request_reset(self.user.email)
        raw = self.extract_token(mail.outbox[0].body)
        PasswordResetToken.objects.update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )
        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            {"token": raw, "new_password": NEW_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_a_new_request_invalidates_the_previous_link(self):
        self.request_reset(self.user.email)
        first = self.extract_token(mail.outbox[0].body)
        self.request_reset(self.user.email)

        response = self.client.post(
            "/api/auth/password-reset/confirm/",
            {"token": first, "new_password": NEW_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_resetting_closes_every_device(self):
        """Ce chemin sert précisément quand un compte est repris à quelqu'un."""
        data = self.login()
        self.client.credentials()

        self.request_reset(self.user.email)
        raw = self.extract_token(mail.outbox[0].body)
        self.client.post(
            "/api/auth/password-reset/confirm/",
            {"token": raw, "new_password": NEW_PASSWORD},
            format="json",
        )
        self.assertIsNotNone(LoginSession.objects.get(sid=data["sid"]).revoked_at)

    def test_the_link_check_reports_validity_without_consuming_it(self):
        self.request_reset(self.user.email)
        raw = self.extract_token(mail.outbox[0].body)

        checked = self.client.get(f"/api/auth/password-reset/check/?token={raw}")
        self.assertTrue(checked.data["valid"])

        self.assertEqual(
            self.client.post(
                "/api/auth/password-reset/confirm/",
                {"token": raw, "new_password": NEW_PASSWORD},
                format="json",
            ).status_code,
            200,
        )

    def test_an_invented_token_is_reported_invalid(self):
        checked = self.client.get("/api/auth/password-reset/check/?token=nimportequoi")
        self.assertFalse(checked.data["valid"])
        self.assertIsNone(checked.data["email"])

    def test_an_inactive_account_receives_nothing(self):
        User.objects.filter(pk=self.user.pk).update(is_active=False)
        self.request_reset(self.user.email)
        self.assertEqual(len(mail.outbox), 0)
