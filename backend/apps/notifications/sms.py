"""Envoi de SMS via LaFricaMobile (LAMPUSH).

Transposition du client `lib/sms.ts` du projet gynaeasy, dont la logique est
conservée à l'identique — normalisation sénégalaise, tolérance aux deux formes de
réponse de LAM, et surtout le **mode simulation** quand les identifiants ne sont
pas configurés : l'application reste utilisable de bout en bout en développement
sans consommer de crédit ni exiger de compte.

Documentation : https://developers.lafricamobile.com/docs/sms/introduction

Variables d'environnement :
    LAM_ACCESS_KEY       identifiant de compte fourni par LAM (ex. MONECOLE.SN_01)
    LAM_ACCESS_PASSWORD  mot de passe
    LAM_SENDER_ID        nom d'expéditeur affiché (défaut : MonEcole)
"""

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

LAM_API_URL = "https://lamsms.lafricamobile.com/api"
REQUEST_TIMEOUT = 15

# Un SMS « standard » fait 160 caractères en GSM-7. Au-delà, l'opérateur découpe et
# facture chaque segment : on trace le compte pour que le coût reste prévisible.
SMS_SEGMENT_LENGTH = 160


@dataclass
class SmsResult:
    success: bool
    message_id: str | None = None
    simulated: bool = False
    error: str | None = None
    segments: int = 1

    @property
    def status(self):
        from apps.core.models import Notification

        return Notification.Status.SENT if self.success else Notification.Status.FAILED


def normalize_phone(phone: str) -> str:
    """Normalise un numéro sénégalais en « 221XXXXXXXXX », sans + ni 00.

    Accepte +221…, 00221…, 221…, 77XXXXXXX et 0XXXXXXXXX.
    """
    number = re.sub(r"[\s\-().]", "", phone or "")
    number = re.sub(r"^\+", "", number)
    number = re.sub(r"^00", "", number)
    if not number.startswith("221") and number.startswith("0"):
        number = number[1:]
    if not number.startswith("221"):
        number = f"221{number}"
    return number


def count_segments(message: str) -> int:
    return max(1, -(-len(message) // SMS_SEGMENT_LENGTH))


def send_sms(to: str, message: str) -> SmsResult:
    """Envoie un SMS. Ne lève jamais : l'échec est porté par le résultat.

    Un envoi raté ne doit pas faire échouer l'opération métier qui l'a déclenché —
    un encaissement enregistré reste valide même si le reçu par SMS n'est pas parti.
    """
    account_id = getattr(settings, "LAM_ACCESS_KEY", "")
    password = getattr(settings, "LAM_ACCESS_PASSWORD", "")
    sender = getattr(settings, "LAM_SENDER_ID", "") or "MonEcole"
    segments = count_segments(message)

    if not account_id or not password:
        missing = ", ".join(
            name
            for name, value in (
                ("LAM_ACCESS_KEY", account_id),
                ("LAM_ACCESS_PASSWORD", password),
            )
            if not value
        )
        logger.info(
            "[SMS SIMULATION] -> %s | %s… (manquant : %s)",
            to, message[:60], missing,
        )
        return SmsResult(
            success=True,
            message_id=f"sim_{uuid.uuid4().hex[:7]}",
            simulated=True,
            segments=segments,
        )

    gsm = normalize_phone(to)
    ret_id = f"monecole_{int(time.time() * 1000)}"
    payload = {
        "accountid": account_id,
        "password": password,
        "sender": sender,
        "ret_id": ret_id,
        "priority": "2",
        "text": message,
        "to": [{ret_id: gsm}],
    }

    try:
        response = requests.post(
            LAM_API_URL,
            json=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
        raw = response.text
    except requests.RequestException as error:
        logger.error("[SMS LAM] Erreur réseau vers %s : %s", to, error)
        return SmsResult(success=False, error=str(error), segments=segments)

    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        data = None

    # LAM répond soit en JSON, soit en texte brut contenant directement
    # l'identifiant du message (ex. « 6a3cf950c7c60 »). Les deux valent succès.
    json_success = isinstance(data, dict) and (
        data.get("success") is True
        or data.get("status") == "success"
        or str(data.get("code", "")) == "200"
        or "message_id" in data
    )
    raw_id = (
        data is None
        and 0 < len(raw.strip()) < 100
        and re.fullmatch(r"[a-f0-9]+", raw.strip(), re.IGNORECASE) is not None
    )

    if json_success or raw_id:
        message_id = str(
            (isinstance(data, dict)
             and (data.get("message_id") or data.get("msg_id") or data.get("id")))
            or raw.strip()
        )
        logger.info("[SMS LAM] Envoyé à %s — id %s", to, message_id)
        return SmsResult(success=True, message_id=message_id, segments=segments)

    error = "Erreur LAM inconnue"
    if isinstance(data, dict):
        error = data.get("message") or data.get("error") or data.get("msg") or error
    elif len(raw) < 200:
        error = raw

    logger.error("[SMS LAM] Échec vers %s : %s", to, raw)
    return SmsResult(success=False, error=str(error), segments=segments)
