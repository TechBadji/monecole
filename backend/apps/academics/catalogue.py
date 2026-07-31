"""Catalogue des matières et de leurs barèmes, par niveau.

Établi à partir de **vingt bulletins réels** du Groupe Scolaire Keur Mame
Nafissa, couvrant les six niveaux de l'élémentaire et les années 2022-2023 à
2025-2026. Le calcul de chaque bulletin a été rejoué et retrouve la moyenne
imprimée au centième — voir `docs/bareme-gsk.md`.

Ce que ces bulletins établissent, et qui gouverne tout le module de notes :

- **Le barème est le poids.** Aucun coefficient multiplicateur n'intervient.
  Une matière sur 20 pèse cinq fois une matière sur 4, par construction.
- **La moyenne est sur 10** : `somme des notes / somme des barèmes × 10`.
- **Le barème d'une matière varie d'une épreuve à l'autre.** Les valeurs
  ci-dessous sont des références — la médiane des barèmes observés — que
  l'administration ajuste à la création de chaque composition.

Le total d'un niveau dépasse celui d'une épreuve réelle : aucune épreuve ne
convoque toutes les matières à la fois. C'est attendu, pas une erreur.

Les intitulés sont unifiés : l'école écrit indifféremment « Compétences DM » et
« Compétence DM », « Activités de Mesure » et « Activités de Mesures ». Deux
libellés pour une matière, ce sont deux lignes au bulletin et un total faux.
"""

# {niveau: [(intitulé, barème de référence), ...]}
SUBJECT_CATALOGUE: dict[str, list[tuple[str, int]]] = {
    # CI — 23 matières · barème total 170 (épreuves réelles : 170–170)
    "CI": [
    ("Activités de mesure", 7),
    ("Activités géométriques", 7),
    ("Activités numériques", 9),
    ("Arts plastiques", 10),
    ("AutoDictée", 10),
    ("Compétence DM", 8),
    ("Compétence EDD", 8),
    ("Compétence maths", 20),
    ("Copie", 10),
    ("Correspondances graphophonologiques", 3),
    ("Fluidité", 5),
    ("Géographie", 4),
    ("Histoire", 4),
    ("IST", 4),
    ("Identification de mots", 3),
    ("Lecture compréhension", 5),
    ("Production d'écrits", 10),
    ("Récitation / chant", 10),
    ("Résolution de problèmes", 7),
    ("Vivre dans son milieu", 6),
    ("Vivre ensemble", 6),
    ("Vocabulaire", 4),
    ("Écriture", 10),
    ],
    # CP — 27 matières · barème total 198 (épreuves réelles : 170–200)
    "CP": [
    ("Activités de mesure", 10),
    ("Activités géométriques", 10),
    ("Activités numériques", 10),
    ("Arts plastiques", 10),
    ("AutoDictée", 10),
    ("Compétence DM", 8),
    ("Compétence EDD", 8),
    ("Compétence maths", 10),  # observé [10, 20]
    ("Conscience phonologique", 4),  # observé [4, 10]
    ("Copie", 10),  # observé [5, 10]
    ("Correspondances graphophonologiques", 2),  # observé [2, 4]
    ("Déchiffrage de mots", 3),  # observé [3, 10]
    ("Fluidité", 5),  # observé [5, 10]
    ("Géographie", 4),  # observé [4, 6, 10]
    ("Histoire", 4),  # observé [4, 8, 10]
    ("IST", 4),  # observé [4, 6, 10]
    ("Identification de mots", 4),  # observé [4, 6]
    ("Lecture compréhension", 6),  # observé [4, 6, 10]
    ("Principe alphabétique", 10),
    ("Production d'écrits", 10),
    ("Récitation / chant", 10),
    ("Résolution de problèmes", 10),
    ("TSQ", 10),
    ("Vivre dans son milieu", 6),  # observé [6, 10]
    ("Vivre ensemble", 6),  # observé [6, 10]
    ("Vocabulaire", 4),  # observé [3, 4, 5, 10]
    ("Écriture", 10),  # observé [5, 10]
    ],
    # CE1 — 24 matières · barème total 181 (épreuves réelles : 160–180)
    "CE1": [
    ("Activités de mesure", 10),  # observé [10, 12]
    ("Activités géométriques", 10),  # observé [8, 10]
    ("Activités numériques", 10),  # observé [10, 16]
    ("Arts plastiques", 10),
    ("Compétence DM", 8),
    ("Compétence EDD", 8),
    ("Compétence maths", 20),  # observé [10, 20]
    ("Conjugaison", 4),  # observé [2, 3, 4, 6, 9]
    ("Conscience phonologique", 5),
    ("Déchiffrage de mots", 5),
    ("Fluidité", 5),  # observé [5, 10]
    ("Grammaire", 4),  # observé [4, 6, 9]
    ("Géographie", 4),
    ("Histoire", 4),
    ("IST", 4),
    ("Orthographe", 4),  # observé [4, 5]
    ("Principe alphabétique", 5),  # observé [5, 10]
    ("Production d'écrits", 20),  # observé [10, 20]
    ("Récitation / chant", 10),
    ("Résolution de problèmes", 10),  # observé [4, 10]
    ("TSQ", 5),  # observé [3, 4, 5]
    ("Vivre dans son milieu", 6),
    ("Vivre ensemble", 6),
    ("Vocabulaire", 4),  # observé [3, 4, 6]
    ],
    # CE2 — 29 matières · barème total 219 (épreuves réelles : 180–200)
    "CE2": [
    ("Activités de mesure", 12),  # observé [10, 12]
    ("Activités géométriques", 8),  # observé [8, 10]
    ("Activités numériques", 16),  # observé [10, 16]
    ("Anglais", 10),
    ("Arabe", 10),
    ("Arts plastiques", 10),
    ("Compétence DM", 8),
    ("Compétence EDD", 8),
    ("Compétence maths", 20),  # observé [10, 20]
    ("Conjugaison", 4),  # observé [4, 8, 10, 12]
    ("Conscience phonologique", 5),
    ("Correspondances graphophonologiques", 5),
    ("Déchiffrage de mots", 5),
    ("Fluidité", 5),  # observé [5, 10]
    ("Grammaire", 4),  # observé [4, 8, 10]
    ("Géographie", 4),
    ("Histoire", 4),
    ("IST", 4),
    ("Identification de mots", 5),
    ("Lecture compréhension", 7),  # observé [7, 10]
    ("Orthographe", 4),  # observé [4, 5]
    ("Principe alphabétique", 5),
    ("Production d'écrits", 20),
    ("Récitation / chant", 10),
    ("Résolution de problèmes", 4),  # observé [4, 10]
    ("TSQ", 6),  # observé [4, 6, 8, 10]
    ("Vivre dans son milieu", 6),
    ("Vivre ensemble", 6),
    ("Vocabulaire", 4),  # observé [3, 4, 8]
    ],
    # CM1 — 21 matières · barème total 298 (épreuves réelles : 300–300)
    "CM1": [
    ("Activités de mesure", 10),
    ("Activités géométriques", 10),
    ("Activités numériques", 10),
    ("Arts plastiques", 10),
    ("Compétence DM", 16),
    ("Compétence EDD", 16),
    ("Compétence maths", 60),
    ("Conjugaison", 8),
    ("Fluidité", 5),
    ("Grammaire", 8),
    ("Géographie", 8),
    ("Histoire", 8),
    ("IST", 8),
    ("Orthographe", 5),  # observé [5, 10]
    ("Production d'écrits", 60),
    ("Récitation / chant", 10),
    ("Résolution de problèmes", 10),
    ("TSQ", 8),  # observé [8, 10]
    ("Vivre dans son milieu", 12),
    ("Vivre ensemble", 12),
    ("Vocabulaire", 4),  # observé [4, 6]
    ],
    # CM2 — 20 matières · barème total 286 (épreuves réelles : 290–300)
    "CM2": [
    ("Activités de mesure", 10),  # observé [10, 12]
    ("Activités géométriques", 8),  # observé [8, 10]
    ("Activités numériques", 10),  # observé [10, 16]
    ("Arts plastiques", 10),
    ("Compétence DM", 16),
    ("Compétence EDD", 16),
    ("Compétence maths", 60),
    ("Conjugaison", 6),  # observé [6, 10]
    ("Grammaire", 13),
    ("Géographie", 6),  # observé [6, 8]
    ("Histoire", 8),
    ("IST", 8),  # observé [8, 10]
    ("Lecture compréhension", 8),  # observé [8, 10]
    ("Orthographe", 5),
    ("Production d'écrits", 60),
    ("Récitation / chant", 10),
    ("Résolution de problèmes", 4),  # observé [4, 10]
    ("Vivre dans son milieu", 12),
    ("Vivre ensemble", 12),
    ("Vocabulaire", 4),  # observé [4, 6]
    ],
}


def catalogue_for(level_name: str) -> list[tuple[str, int]]:
    """Matières d'un niveau, ou liste vide si le niveau n'est pas répertorié.

    Le rapprochement se fait sur le début du nom de la classe : « CE2B » et
    « CE2 A » relèvent tous deux du CE2. Les écoles nomment leurs classes comme
    elles l'entendent, et une correspondance stricte ne servirait personne.
    """
    key = level_name.strip().upper().replace(" ", "")
    # Du plus long au plus court : « CE1 » ne doit pas capter un « CE2 », et
    # « CM1 » testé avant « CM » éviterait un faux positif si l'on ajoutait « CM ».
    for level in sorted(SUBJECT_CATALOGUE, key=len, reverse=True):
        if key.startswith(level):
            return SUBJECT_CATALOGUE[level]
    return []


def all_subject_names() -> list[str]:
    """Intitulés distincts, tous niveaux confondus, pour peupler le catalogue."""
    names: dict[str, None] = {}
    for entries in SUBJECT_CATALOGUE.values():
        for name, _bareme in entries:
            names[name] = None
    return sorted(names)


def subject_code(name: str) -> str:
    """Code court et stable dérivé de l'intitulé.

    Le code est la clé d'unicité par établissement : il doit rester le même
    d'un amorçage à l'autre, faute de quoi un second appel créerait des
    doublons. Les accents sont retirés et la longueur bornée à 16, comme le
    champ.
    """
    import re
    import unicodedata

    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    slug = re.sub(r"[^A-Za-z0-9]+", "_", folded).strip("_").upper()
    return slug[:16].rstrip("_")
