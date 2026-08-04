"""Renumérote l'ordre d'affichage des classes sur le rang du niveau.

Les classes existantes portaient 0 à 9, un rang par niveau. L'arrivée des
sections — CI-A, CI-B — impose un pas de dix, faute de quoi une section créée
avec l'ordre 41 se rangerait après toutes les classes existantes au lieu de
suivre son propre niveau.

Les classes dont le nom ne correspond à aucun niveau connu conservent leur
position relative, à la fin : renuméroter au hasard une classe qu'on ne sait pas
situer serait pire que la laisser où elle est.
"""

from django.db import migrations

GRADE_CODES = ["GARDERIE", "PS", "MS", "GS", "CI", "CP", "CE1", "CE2", "CM1", "CM2"]
STEP = 10
SECTION_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def rank_of(name):
    key = (name or "").strip().upper().replace(" ", "")
    for code in sorted(GRADE_CODES, key=len, reverse=True):
        if key.startswith(code):
            return GRADE_CODES.index(code), key[len(code):].lstrip("-_ ")
    return None, ""


def renumber(apps, schema_editor):
    ClassRoom = apps.get_model("students", "ClassRoom")
    unknown_base = len(GRADE_CODES) * STEP

    for school_id in ClassRoom.objects.values_list("school_id", flat=True).distinct():
        classes = list(ClassRoom.objects.filter(school_id=school_id).order_by("order", "name"))
        used = {}
        leftovers = []

        for classroom in classes:
            rank, suffix = rank_of(classroom.name)
            if rank is None:
                leftovers.append(classroom)
                continue
            # La lettre de section fixe la place ; à défaut, l'ordre d'arrivée.
            letter = suffix[:1].upper()
            index = SECTION_LETTERS.index(letter) if letter in SECTION_LETTERS else used.get(rank, 0)
            while (rank, index) in used.get("taken", set()):
                index += 1
            used.setdefault("taken", set()).add((rank, index))
            used[rank] = index + 1
            classroom.order = rank * STEP + index
            classroom.save(update_fields=["order"])

        for offset, classroom in enumerate(leftovers):
            classroom.order = unknown_base + offset
            classroom.save(update_fields=["order"])


def noop(apps, schema_editor):
    """Pas de retour arrière : l'ancien schéma d'ordre n'est pas reconstituable
    et l'ordre d'affichage ne porte aucune donnée métier."""


class Migration(migrations.Migration):
    dependencies = [("students", "0006_discount_category")]
    operations = [migrations.RunPython(renumber, noop)]
