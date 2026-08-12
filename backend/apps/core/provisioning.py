"""Ouverture d'un établissement par le super-administrateur.

Un établissement neuf n'est pas une ligne dans une table : c'est une année
scolaire, dix classes, et trois comptes qui doivent pouvoir se connecter le
jour même. Laisser l'éditeur créer tout cela à la main, école par école, c'est
garantir qu'une école partira sans son année courante et que personne ne s'en
apercevra avant la première saisie.

**Les mots de passe sont tirés au sort, un par compte.** Un mot de passe
commun à toutes les écoles serait devinable — le code est public — et le
premier compte administrateur de chaque établissement tomberait avec lui. Ils
ne sont affichés qu'une fois, à la création, et chaque compte doit changer le
sien à la première connexion.
"""

from __future__ import annotations

import secrets
import unicodedata
from dataclasses import dataclass

from django.db import transaction
from django.utils.text import slugify

from .models import Role, School, SchoolYear, Subscription, User

# Structure de départ : les dix niveaux de l'élémentaire sénégalais, préscolaire
# compris. Une école qui n'en tient qu'une partie supprime les classes vides
# depuis Paramètres — plus rapide que de créer les siennes une par une.
BASE_CLASSES = [
    ("GARDERIE", "PRESCHOOL"),
    ("PS", "PRESCHOOL"),
    ("MS", "PRESCHOOL"),
    ("GS", "PRESCHOOL"),
    ("CI", "PRIMARY"),
    ("CP", "PRIMARY"),
    ("CE1", "PRIMARY"),
    ("CE2", "PRIMARY"),
    ("CM1", "PRIMARY"),
    ("CM2", "PRIMARY"),
]

STAFF_ROLES = [
    (Role.ADMIN, "admin", "Administration"),
    (Role.SECRETARY, "secretariat", "Secrétariat"),
    (Role.TEACHER, "enseignant", "Salle des maîtres"),
]

# Alphabet sans caractères ambigus : un mot de passe se dicte au téléphone, et
# « l » contre « 1 » ou « O » contre « 0 » coûte un appel de plus.
ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def temporary_password(length: int = 12) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))


def school_slug(name: str) -> str:
    """Identifiant d'établissement, sans accent ni espace."""
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    base = slugify(folded)[:40] or "ecole"

    slug, suffix = base, 2
    while School.objects.filter(slug=slug).exists():
        slug = f"{base}-{suffix}"
        suffix += 1
    return slug


def default_year_bounds(start_year: int):
    """Exercice d'octobre à septembre — celui des écoles sénégalaises."""
    import datetime

    return (
        datetime.date(start_year, 10, 1),
        datetime.date(start_year + 1, 9, 30),
    )


@dataclass
class ProvisionedAccount:
    role: str
    email: str
    password: str
    full_name: str


@transaction.atomic
def provision_school(
    *,
    name: str,
    start_year: int,
    address: str = "",
    phone: str = "",
    email: str = "",
    plan: str = Subscription.Plan.TRIAL,
    max_students: int = 100,
) -> tuple[School, SchoolYear, list[ProvisionedAccount]]:
    """Crée l'établissement, son année courante, ses classes et ses accès.

    Tout ou rien : une école sans année courante ne peut ni encaisser ni noter,
    et une création à moitié faite se découvrirait au pire moment.
    """
    from apps.students.models import ClassRoom

    from .tenancy import tenant_context

    slug = school_slug(name)
    school = School.objects.create(
        name=name.strip(),
        slug=slug,
        address=address.strip(),
        phone=phone.strip(),
        email=email.strip(),
        subscription=Subscription.objects.create(plan=plan, max_students=max_students),
    )

    start, end = default_year_bounds(start_year)
    with tenant_context(school):
        year = SchoolYear.objects.create(
            school=school,
            label=f"{start_year}/{start_year + 1}",
            start_date=start,
            end_date=end,
            tuition_months=9,
            is_current=True,
        )
        for order, (class_name, level) in enumerate(BASE_CLASSES):
            ClassRoom.objects.create(
                school=school, name=class_name, level=level, order=order * 10
            )

    accounts = []
    for role, local, label in STAFF_ROLES:
        password = temporary_password()
        address_email = f"{local}@{slug}.monecole.sn"
        User.objects.create_user(
            email=address_email,
            password=password,
            role=role,
            school=school,
            first_name=label,
            last_name=school.name[:60],
            must_change_password=True,
        )
        accounts.append(
            ProvisionedAccount(
                role=role, email=address_email, password=password, full_name=label
            )
        )

    return school, year, accounts
