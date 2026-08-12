"""Calcul des moyennes, du rang et des données de bulletin.

Deux règles gouvernent tout le module :

1. **Une absence n'est pas un zéro.** Une note absente sort du calcul : son
   barème est retiré du dénominateur, au lieu de tirer la moyenne
   vers le bas. Compter une absence comme zéro pénaliserait un élève malade
   exactement comme un élève ayant rendu copie blanche.
2. **Le rang se calcule sur les élèves effectivement notés.** Un élève sans
   aucune note n'est pas classé dernier, il n'est pas classé.
"""

from decimal import Decimal, ROUND_HALF_UP

from .models import AVERAGE_SCALE, ClassSubject, Grade, GradeSheet, mention_for

TWO_PLACES = Decimal("0.01")

# Moitié de l'échelle, comme le 10 sur 20 de l'usage.
PASSING_AVERAGE = AVERAGE_SCALE / 2


def _round(value):
    if value is None:
        return None
    return Decimal(value).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def student_results(composition, classroom):
    """Résultats de tous les élèves d'une classe pour une composition.

    Retourne un dictionnaire par élève : notes par matière, total de points,
    moyenne pondérée et rang. Tout est calculé en une passe — un bulletin de
    classe entière ne doit pas déclencher une requête par élève.
    """
    from apps.students.models import Student, StudentStatus

    subjects = list(
        ClassSubject.objects.filter(classroom=classroom, year=composition.year)
        .select_related("subject", "teacher", "classroom__teacher")
        .order_by("order", "subject__order")
    )
    sheets = {
        sheet.class_subject_id: sheet
        for sheet in GradeSheet.objects.filter(
            composition=composition, class_subject__in=subjects
        )
    }
    grades = {
        (grade.sheet_id, grade.student_id): grade
        for grade in Grade.objects.filter(sheet__in=sheets.values())
    }

    students = list(
        Student.objects.filter(classroom=classroom, status=StudentStatus.ACTIVE).order_by(
            "last_name", "first_name"
        )
    )

    results = {}
    for student in students:
        lines = []
        points = Decimal("0")
        scale = 0   # somme des barèmes des matières effectivement notées

        for class_subject in subjects:
            sheet = sheets.get(class_subject.id)
            grade = grades.get((sheet.id, student.id)) if sheet else None
            value = grade.value if grade and grade.counts else None
            # Le barème de l'épreuve prime sur celui de la classe : la même
            # matière est notée sur 4 à un contrôle et sur 12 au suivant.
            # `class_subject` est déjà chargé : passer par
            # `sheet.effective_max_score` déclencherait un accès paresseux à
            # `sheet.class_subject`, soit une requête par matière — mesuré à
            # 33 requêtes pour une classe de 29 matières, contre 5.
            max_score = (sheet.max_score if sheet else None) or class_subject.max_score

            line = {
                "class_subject": class_subject.id,
                "subject": class_subject.subject.name,
                "max_score": max_score,
                "value": value,
                "is_absent": bool(grade and grade.is_absent),
                "comment": grade.comment if grade else "",
                "validated": bool(sheet and sheet.is_validated),
                "teacher": (
                    class_subject.effective_teacher.full_name
                    if class_subject.effective_teacher
                    else None
                ),
            }
            lines.append(line)

            if value is not None:
                points += value
                scale += max_score

        # Le barème fait le poids : aucune multiplication n'intervient. Une
        # matière sur 20 pèse cinq fois une matière sur 4 parce qu'elle apporte
        # cinq fois plus de points au numérateur comme au dénominateur.
        average = _round(points / scale * AVERAGE_SCALE) if scale else None
        results[student.id] = {
            "student": student.id,
            "matricule": student.matricule,
            "name": student.full_name,
            "lines": lines,
            "total_points": _round(points) if scale else None,
            "total_max_score": scale,
            "average": average,
            "mention": mention_for(float(average)) if average is not None else "",
            "graded": scale > 0,
        }

    _assign_ranks(results)
    return results, subjects, students


def _assign_ranks(results):
    """Attribue le rang, ex æquo compris.

    Deux élèves à la même moyenne partagent le rang, et le suivant reprend au
    numéro qui suit le nombre d'élèves déjà classés — la convention scolaire, qui
    évite de faire disparaître un rang.
    """
    graded = [r for r in results.values() if r["graded"]]
    graded.sort(key=lambda r: r["average"], reverse=True)

    ranked = 0
    previous_average = None
    previous_rank = 0
    for entry in graded:
        ranked += 1
        if entry["average"] == previous_average:
            entry["rank"] = previous_rank
        else:
            entry["rank"] = ranked
            previous_rank = ranked
            previous_average = entry["average"]
        entry["ranked_out_of"] = len(graded)

    for entry in results.values():
        entry.setdefault("rank", None)
        entry.setdefault("ranked_out_of", len(graded))


def class_summary(composition, classroom):
    """Indicateurs de classe : moyenne générale, extrêmes, taux de réussite."""
    results, subjects, _ = student_results(composition, classroom)
    averages = [r["average"] for r in results.values() if r["average"] is not None]

    if not averages:
        return {
            "graded": 0,
            "class_average": None,
            "best": None,
            "lowest": None,
            "pass_rate": None,
            "subjects": len(subjects),
        }

    # La moyenne est sur 10 : le seuil de passage est 5, non 10. Laissé à 10, il
    # aurait affiché 0 % de réussite dans toutes les classes de l'établissement.
    passing = sum(1 for a in averages if a >= PASSING_AVERAGE)
    return {
        "graded": len(averages),
        "class_average": _round(sum(averages) / len(averages)),
        "best": max(averages),
        "lowest": min(averages),
        "pass_rate": round(passing * 100 / len(averages), 1),
        "subjects": len(subjects),
    }


def sheet_completeness(composition):
    """État de saisie par matière, pour savoir si un bulletin est éditable.

    L'administration doit voir ce qui manque avant d'imprimer : éditer un
    bulletin dont trois matières ne sont pas saisies produit un document faux
    qu'il faudra reprendre auprès des familles.
    """
    sheets = (
        GradeSheet.objects.filter(composition=composition)
        .select_related("class_subject__subject", "class_subject__classroom")
        .order_by("class_subject__classroom__order", "class_subject__order")
    )

    rows = []
    for sheet in sheets:
        total = Grade.objects.filter(sheet=sheet).count()
        filled = (
            Grade.objects.filter(sheet=sheet)
            .exclude(value__isnull=True, is_absent=False)
            .count()
        )
        rows.append(
            {
                "sheet": sheet.id,
                "classroom": sheet.class_subject.classroom.name,
                "subject": sheet.class_subject.subject.name,
                "max_score": sheet.effective_max_score,
                "validated": sheet.is_validated,
                "entered": filled,
                "expected": total,
                "complete": total > 0 and filled == total,
            }
        )
    return rows
