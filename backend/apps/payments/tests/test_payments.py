"""Paiements Wave et espèces.

L'enjeu central : une transaction ne doit produire une écriture comptable qu'une
seule fois, et seulement sur confirmation authentifiée. Un webhook non signé ou
rejoué ne doit jamais gonfler les recettes.
"""

import hashlib
import hmac
import json
import time

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.core.models import Role
from apps.core.tenancy import tenant_context, unscoped
from apps.core.tests.factories import (
    make_classroom,
    make_fee_schedule,
    make_school,
    make_student,
    make_user,
    make_year,
)
from apps.payments.models import PaymentTransaction, WaveWebhookEvent
from apps.payments.services import confirm_transaction, open_transaction
from apps.students.models import MonthlyPayment

SECRET = "whsec_test_123"


def sign(body: bytes, secret=SECRET, timestamp=None):
    timestamp = timestamp or str(int(time.time()))
    digest = hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={digest}"


class PaymentTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.year = make_year(cls.school)
        cls.classroom = make_classroom(cls.school, "CP")
        make_fee_schedule(cls.school, cls.classroom, cls.year, tuition=15_000)
        cls.student = make_student(cls.school, cls.classroom)
        cls.accountant = make_user(cls.school, Role.ACCOUNTANT, "compta@test.sn")
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")
        cls.secretary = make_user(cls.school, Role.SECRETARY, "secret@test.sn")

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def make_transaction(self, amount=15_000, method=PaymentTransaction.Method.WAVE):
        with tenant_context(self.school):
            return open_transaction(
                school=self.school, student=self.student, year=self.year,
                amount=amount, method=method,
                purpose=PaymentTransaction.Purpose.TUITION,
                period=self.year.tuition_month_ends[0],
            )


class CashPaymentTests(PaymentTestCase):
    def test_accountant_records_cash_and_ledger_entry_is_created(self):
        response = self.client_for(self.accountant).post(
            "/api/payments/cash/",
            {"student": self.student.pk, "amount": 15_000,
             "period": "2025-10-31", "send_receipt": False},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], "SUCCEEDED")

        with tenant_context(self.school):
            payment = MonthlyPayment.objects.get(student=self.student)
            self.assertEqual(payment.tuition, 15_000)
            self.assertEqual(payment.method, MonthlyPayment.Method.CASH)

    def test_secretary_cannot_take_cash(self):
        """Séparation des tâches : la secrétaire ne manipule pas la caisse."""
        response = self.client_for(self.secretary).post(
            "/api/payments/cash/",
            {"student": self.student.pk, "amount": 15_000, "period": "2025-10-31"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)

    def test_zero_amount_is_refused(self):
        response = self.client_for(self.accountant).post(
            "/api/payments/cash/",
            {"student": self.student.pk, "amount": 0, "period": "2025-10-31"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_second_payment_adds_up_instead_of_replacing(self):
        """Un règlement en deux fois ne doit pas effacer le premier versement."""
        client = self.client_for(self.accountant)
        for amount in (5_000, 7_000):
            client.post(
                "/api/payments/cash/",
                {"student": self.student.pk, "amount": amount,
                 "period": "2025-10-31", "send_receipt": False},
                format="json",
            )
        with tenant_context(self.school):
            payment = MonthlyPayment.objects.get(student=self.student)
            self.assertEqual(payment.tuition, 12_000)

    def test_receipt_pdf_is_available_once_confirmed(self):
        created = self.client_for(self.accountant).post(
            "/api/payments/cash/",
            {"student": self.student.pk, "amount": 15_000,
             "period": "2025-10-31", "send_receipt": False},
            format="json",
        )
        response = self.client_for(self.accountant).get(
            f"/api/payments/{created.data['id']}/receipt/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))

    def test_no_receipt_for_a_pending_transaction(self):
        txn = self.make_transaction()
        response = self.client_for(self.accountant).get(f"/api/payments/{txn.pk}/receipt/")
        self.assertEqual(response.status_code, 400)


class WaveCheckoutTests(PaymentTestCase):
    def test_checkout_falls_back_to_simulation_without_credentials(self):
        """Sans clé Wave, le parcours reste testable mais clairement marqué."""
        response = self.client_for(self.accountant).post(
            "/api/payments/wave/",
            {"student": self.student.pk, "amount": 15_000, "period": "2025-10-31"},
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["simulated"])
        self.assertTrue(response.data["checkout_url"])
        self.assertEqual(response.data["status"], "PENDING")

    def test_opening_a_checkout_creates_no_ledger_entry(self):
        """Une session ouverte n'est pas un encaissement : rien au bilan tant
        qu'aucune confirmation n'est parvenue."""
        self.client_for(self.accountant).post(
            "/api/payments/wave/",
            {"student": self.student.pk, "amount": 15_000, "period": "2025-10-31"},
            format="json",
        )
        with tenant_context(self.school):
            self.assertEqual(MonthlyPayment.objects.count(), 0)


@override_settings(WAVE_WEBHOOK_SECRET=SECRET)
class WaveWebhookTests(PaymentTestCase):
    def post_event(self, payload, signature=None):
        body = json.dumps(payload).encode()
        return self.client.post(
            "/api/webhooks/wave/",
            data=body,
            content_type="application/json",
            HTTP_WAVE_SIGNATURE=signature if signature is not None else sign(body),
        )

    def completed_event(self, reference, event_id="evt_1"):
        return {
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {"id": "cs_123", "client_reference": reference, "amount": "15000"},
        }

    def test_signed_event_confirms_and_creates_the_ledger_entry(self):
        txn = self.make_transaction()
        response = self.post_event(self.completed_event(txn.reference))
        self.assertEqual(response.status_code, 200)

        with unscoped():
            txn.refresh_from_db()
        self.assertEqual(txn.status, PaymentTransaction.Status.SUCCEEDED)
        with tenant_context(self.school):
            self.assertEqual(MonthlyPayment.objects.get(student=self.student).tuition, 15_000)

    def test_unsigned_event_is_rejected(self):
        """Sans signature valable, n'importe qui pourrait déclarer des recettes."""
        txn = self.make_transaction()
        response = self.post_event(self.completed_event(txn.reference), signature="")
        self.assertEqual(response.status_code, 401)

        with unscoped():
            txn.refresh_from_db()
        self.assertEqual(txn.status, PaymentTransaction.Status.PENDING)
        with tenant_context(self.school):
            self.assertEqual(MonthlyPayment.objects.count(), 0)

    def test_wrong_signature_is_rejected(self):
        txn = self.make_transaction()
        body = json.dumps(self.completed_event(txn.reference)).encode()
        response = self.post_event(
            self.completed_event(txn.reference), signature=sign(body, secret="mauvais")
        )
        self.assertEqual(response.status_code, 401)

    def test_replayed_old_signature_is_rejected(self):
        """Une signature capturée ne doit pas rester valable indéfiniment."""
        txn = self.make_transaction()
        body = json.dumps(self.completed_event(txn.reference)).encode()
        stale = str(int(time.time()) - 3600)
        response = self.post_event(
            self.completed_event(txn.reference), signature=sign(body, timestamp=stale)
        )
        self.assertEqual(response.status_code, 401)

    def test_the_same_event_twice_creates_one_ledger_entry(self):
        """Wave réémet légitimement ses webhooks — sans effet de bord."""
        txn = self.make_transaction()
        self.post_event(self.completed_event(txn.reference))
        self.post_event(self.completed_event(txn.reference))

        with tenant_context(self.school):
            payments = MonthlyPayment.objects.filter(student=self.student)
            self.assertEqual(payments.count(), 1)
            self.assertEqual(payments.first().tuition, 15_000)

    def test_distinct_events_on_a_confirmed_transaction_do_not_double_count(self):
        """Même avec deux identifiants d'événement différents, une transaction
        confirmée ne s'applique qu'une fois."""
        txn = self.make_transaction()
        self.post_event(self.completed_event(txn.reference, event_id="evt_1"))
        self.post_event(self.completed_event(txn.reference, event_id="evt_2"))

        with tenant_context(self.school):
            self.assertEqual(
                MonthlyPayment.objects.get(student=self.student).tuition, 15_000
            )

    def test_unknown_reference_is_acknowledged_without_effect(self):
        response = self.post_event(self.completed_event("ME-inconnue"))
        self.assertEqual(response.status_code, 200)
        with tenant_context(self.school):
            self.assertEqual(MonthlyPayment.objects.count(), 0)

    def test_failed_event_marks_the_transaction_without_ledger_entry(self):
        txn = self.make_transaction()
        payload = {
            "id": "evt_fail",
            "type": "checkout.session.payment_failed",
            "data": {"client_reference": txn.reference, "last_payment_error": "Solde insuffisant"},
        }
        self.assertEqual(self.post_event(payload).status_code, 200)

        with unscoped():
            txn.refresh_from_db()
        self.assertEqual(txn.status, PaymentTransaction.Status.FAILED)
        with tenant_context(self.school):
            self.assertEqual(MonthlyPayment.objects.count(), 0)

    def test_a_confirmed_payment_cannot_be_downgraded_to_failed(self):
        """Annuler silencieusement une écriture comptable serait pire qu'un doublon."""
        txn = self.make_transaction()
        self.post_event(self.completed_event(txn.reference, event_id="evt_ok"))
        self.post_event({
            "id": "evt_late_fail",
            "type": "checkout.session.payment_failed",
            "data": {"client_reference": txn.reference},
        })

        with unscoped():
            txn.refresh_from_db()
        self.assertEqual(txn.status, PaymentTransaction.Status.SUCCEEDED)

    def test_every_event_is_stored_even_when_refused(self):
        txn = self.make_transaction()
        self.post_event(self.completed_event(txn.reference), signature="")
        self.assertEqual(WaveWebhookEvent.objects.count(), 1)
        event = WaveWebhookEvent.objects.first()
        self.assertFalse(event.signature_valid)
        self.assertFalse(event.processed)


@override_settings(WAVE_WEBHOOK_SECRET="")
class WebhookWithoutSecretTests(PaymentTestCase):
    def test_webhook_is_refused_when_no_secret_is_configured(self):
        """Une configuration incomplète doit fermer la porte, pas l'ouvrir."""
        txn = self.make_transaction()
        body = json.dumps({
            "id": "evt_x", "type": "checkout.session.completed",
            "data": {"client_reference": txn.reference},
        }).encode()
        response = self.client.post(
            "/api/webhooks/wave/", data=body, content_type="application/json",
            HTTP_WAVE_SIGNATURE=sign(body, secret="peu importe"),
        )
        self.assertEqual(response.status_code, 401)


class TransactionIdempotencyTests(PaymentTestCase):
    def test_confirming_twice_returns_false_the_second_time(self):
        txn = self.make_transaction()
        with tenant_context(self.school):
            _, created_first = confirm_transaction(txn, notify=False)
            _, created_second = confirm_transaction(txn, notify=False)
        self.assertTrue(created_first)
        self.assertFalse(created_second)

        with tenant_context(self.school):
            self.assertEqual(MonthlyPayment.objects.count(), 1)
