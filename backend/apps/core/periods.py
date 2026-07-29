"""Périodes mensuelles.

Toute la comptabilité du classeur source est indexée par **fin de mois** : la colonne
`DEPENSES!B` est un `EOMONTH(date_opération)` et sert de clé de jointure aux `SUMIFS`
du bilan. On reproduit fidèlement cette convention — une période est identifiée par
le dernier jour du mois, jamais par le premier.
"""

import calendar
import datetime

MONTH_NAMES_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]


def end_of_month(date):
    """Dernier jour du mois de `date` — équivalent de `EOMONTH(date, 0)`."""
    return date.replace(day=calendar.monthrange(date.year, date.month)[1])


def add_months(date, n):
    """Décale de `n` mois en bornant le jour au dernier jour du mois d'arrivée."""
    total = date.month - 1 + n
    year = date.year + total // 12
    month = total % 12 + 1
    return date.replace(year=year, month=month, day=min(date.day, calendar.monthrange(year, month)[1]))


def month_ends(start, count):
    """Retourne `count` fins de mois consécutives à partir du mois de `start`.

    >>> month_ends(datetime.date(2025, 10, 1), 3)
    [date(2025, 10, 31), date(2025, 11, 30), date(2025, 12, 31)]
    """
    first = start.replace(day=1)
    return [end_of_month(add_months(first, i)) for i in range(count)]


def label(date):
    """Libellé lisible d'une période : « octobre 2025 »."""
    return f"{MONTH_NAMES_FR[date.month - 1]} {date.year}"


def short_label(date):
    """Libellé court : « oct. 2025 »."""
    name = MONTH_NAMES_FR[date.month - 1]
    return f"{name[:4]}. {date.year}" if len(name) > 5 else f"{name} {date.year}"


def default_year_bounds(start_year):
    """Bornes de l'exercice financier : 1er octobre → 30 septembre."""
    return (
        datetime.date(start_year, 10, 1),
        datetime.date(start_year + 1, 9, 30),
    )
