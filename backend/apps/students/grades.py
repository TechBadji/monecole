"""Niveaux d'enseignement et sections d'un même niveau.

Le **niveau** (CI, CP, CE1…) n'est pas un champ du modèle : il se lit au début
du nom de la classe. C'est ce qui permet à `CI-A`, `CI-B` et `CI` de partager le
catalogue de matières du CI sans qu'aucune table ne les relie.

Ce module donne la liste canonique de ces niveaux et le rang pédagogique de
chacun, dont dérive l'ordre d'affichage.
"""

from .models import Level

# (code, intitulé, cycle). L'ordre de la liste **est** l'ordre pédagogique.
GRADES = [
    ("GARDERIE", "Garderie", Level.PRESCHOOL),
    ("PS", "Petite section", Level.PRESCHOOL),
    ("MS", "Moyenne section", Level.PRESCHOOL),
    ("GS", "Grande section", Level.PRESCHOOL),
    ("CI", "Cours d'initiation", Level.PRIMARY),
    ("CP", "Cours préparatoire", Level.PRIMARY),
    ("CE1", "Cours élémentaire 1", Level.PRIMARY),
    ("CE2", "Cours élémentaire 2", Level.PRIMARY),
    ("CM1", "Cours moyen 1", Level.PRIMARY),
    ("CM2", "Cours moyen 2", Level.PRIMARY),
]

GRADE_CODES = [code for code, _label, _level in GRADES]

# Écart entre deux niveaux dans l'ordre d'affichage. Laisse la place à neuf
# sections par niveau — au-delà, une école tient un registre, pas une classe.
STEP = 10

SEPARATOR = "-"
# A, B, C… : la lettre est la convention des écoles sénégalaises pour les
# sections d'un même niveau, et c'est ainsi que les bulletins fournis les
# nomment (CE1A, CE2B).
SECTION_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def grade_rank(name: str) -> int | None:
    """Rang pédagogique d'une classe, déduit du début de son nom.

    Du plus long au plus court, sans quoi « CE1-A » serait pris pour un « CE »
    inexistant et « CM1 » pour un « CM ».
    """
    key = (name or "").strip().upper().replace(" ", "")
    for code in sorted(GRADE_CODES, key=len, reverse=True):
        if key.startswith(code):
            return GRADE_CODES.index(code)
    return None


def level_of(grade_code: str):
    for code, _label, level in GRADES:
        if code == grade_code:
            return level
    return None


def section_name(grade_code: str, index: int) -> str:
    """`CI-A` pour l'index 0, `CI-B` pour 1, etc."""
    return f"{grade_code}{SEPARATOR}{SECTION_LETTERS[index]}"


def display_order(grade_code: str, index: int) -> int:
    """Ordre d'affichage : le niveau commande, la section départage.

    `rang × 10 + index` garde les sections d'un niveau groupées et permet d'en
    insérer une sans renuméroter les autres niveaux.
    """
    return GRADE_CODES.index(grade_code) * STEP + index
