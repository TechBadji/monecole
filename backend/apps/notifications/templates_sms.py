"""Modèles de messages SMS.

Les messages sont volontairement courts : au-delà de 160 caractères, l'opérateur
découpe le SMS en segments facturés séparément. Un rappel de paiement envoyé à
400 parents chaque mois double de coût pour vingt caractères de trop.
"""

from apps.core.periods import label as period_label


def _money(value):
    return f"{value:,}".replace(",", " ")


def payment_reminder(*, parent_name, student_name, amount, school_name, due_label):
    """Rappel d'échéance à venir."""
    return (
        f"Bonjour {parent_name}, {school_name} vous rappelle la scolarite de "
        f"{student_name} : {_money(amount)} FCFA a regler avant {due_label}. Merci."
    )


def arrears_notice(*, parent_name, student_name, amount, school_name, months):
    """Relance sur arriérés constatés."""
    return (
        f"Bonjour {parent_name}, la scolarite de {student_name} presente un arriere "
        f"de {_money(amount)} FCFA ({months} mois). Merci de regulariser aupres de "
        f"{school_name}."
    )


def payment_receipt(*, parent_name, student_name, amount, period, school_name, reference):
    """Accusé d'encaissement — sert de reçu au parent."""
    return (
        f"Bonjour {parent_name}, {school_name} confirme un paiement de "
        f"{_money(amount)} FCFA pour {student_name} ({period_label(period)}). "
        f"Ref {reference}. Merci."
    )


def otp_code(*, code, school_name):
    """Code de connexion au portail parent.

    Aucune donnée personnelle : un SMS d'authentification peut être lu sur un écran
    verrouillé, il ne doit rien révéler du dossier de l'enfant.
    """
    return (
        f"{school_name} : votre code de connexion est {code}. "
        f"Valable 10 minutes. Ne le communiquez a personne."
    )


def wave_payment_request(*, parent_name, student_name, amount, url):
    """Invitation à payer par Wave."""
    return (
        f"Bonjour {parent_name}, reglez la scolarite de {student_name} "
        f"({_money(amount)} FCFA) par Wave : {url}"
    )
