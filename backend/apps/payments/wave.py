"""Client Wave Business API (Checkout).

Même principe que le client SMS : sans `WAVE_API_KEY`, le module bascule en **mode
simulation** et fabrique une session locale. Le parcours de paiement reste donc
testable de bout en bout sans compte marchand — mais les transactions produites
portent `simulated=True` et ne doivent jamais être confondues avec de vrais
encaissements.

Documentation : https://docs.wave.com/business
"""

import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass, field

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 20

# Tolérance sur l'horodatage du webhook. Sans elle, une signature valide capturée
# resterait rejouable indéfiniment.
SIGNATURE_TOLERANCE_SECONDS = 300


@dataclass
class CheckoutSession:
    success: bool
    session_id: str = ""
    checkout_url: str = ""
    simulated: bool = False
    error: str | None = None
    raw: dict = field(default_factory=dict)


def is_configured():
    return bool(getattr(settings, "WAVE_API_KEY", ""))


def create_checkout_session(*, amount, reference, success_url, error_url, currency="XOF"):
    """Ouvre une session de paiement Wave.

    `reference` est notre identifiant : Wave le restitue en `client_reference` dans
    le webhook, ce qui permet de rattacher le paiement sans se fier à un montant ou
    à un horodatage.
    """
    if not is_configured():
        session_id = f"sim_cs_{uuid.uuid4().hex[:16]}"
        logger.info("[WAVE SIMULATION] session %s pour %s (%s XOF)", session_id, reference, amount)
        return CheckoutSession(
            success=True,
            session_id=session_id,
            # Page interne qui rejoue le webhook — voir `SimulatedWaveCheckoutView`.
            checkout_url=f"{settings.PUBLIC_BASE_URL}/paiement/simulation/{reference}",
            simulated=True,
        )

    payload = {
        "amount": str(amount),
        "currency": currency,
        "client_reference": reference,
        "success_url": success_url,
        "error_url": error_url,
    }

    try:
        response = requests.post(
            f"{settings.WAVE_API_URL}/checkout/sessions",
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.WAVE_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as error:
        logger.error("[WAVE] Erreur réseau : %s", error)
        return CheckoutSession(success=False, error=str(error))

    try:
        data = response.json()
    except ValueError:
        data = {}

    if response.status_code >= 400:
        message = data.get("message") or data.get("error_message") or response.text[:200]
        logger.error("[WAVE] Échec création de session (%s) : %s", response.status_code, message)
        return CheckoutSession(success=False, error=str(message), raw=data)

    return CheckoutSession(
        success=True,
        session_id=data.get("id", ""),
        checkout_url=data.get("wave_launch_url", ""),
        raw=data,
    )


def verify_signature(raw_body: bytes, header: str) -> bool:
    """Vérifie l'en-tête `Wave-Signature`.

    Format : `t=<timestamp>,v1=<hmac_sha256(timestamp + body)>`.

    Sans cette vérification, n'importe qui pouvant atteindre l'URL du webhook
    pourrait déclarer des paiements reçus — et créer des écritures comptables de
    toutes pièces.
    """
    secret = getattr(settings, "WAVE_WEBHOOK_SECRET", "")
    if not secret:
        # Refus explicite plutôt qu'acceptation par défaut : un webhook non
        # vérifiable ne doit jamais alimenter la comptabilité.
        logger.warning("[WAVE] WAVE_WEBHOOK_SECRET absent — webhook refusé.")
        return False
    if not header:
        return False

    parts = dict(
        piece.split("=", 1) for piece in header.split(",") if "=" in piece
    )
    timestamp = parts.get("t", "")
    provided = parts.get("v1", "")
    if not timestamp or not provided:
        return False

    import time

    try:
        age = abs(time.time() - int(timestamp))
    except ValueError:
        return False
    if age > SIGNATURE_TOLERANCE_SECONDS:
        logger.warning("[WAVE] Signature hors fenêtre de tolérance (%.0f s).", age)
        return False

    expected = hmac.new(
        secret.encode(), f"{timestamp}".encode() + raw_body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, provided)


def parse_event(raw_body: bytes):
    try:
        return json.loads(raw_body)
    except (ValueError, TypeError):
        return None
