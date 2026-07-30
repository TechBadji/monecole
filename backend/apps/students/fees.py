"""Calcul des montants dus, réductions comprises.

Source unique de vérité. La logique était auparavant recopiée dans la situation
élève et dans le portail parent, et **absente** du calcul des arriérés : un élève
boursier apparaissait donc en retard de paiement sur une somme qu'il ne devait pas.
Un même élève doit voir le même montant dû, quel que soit l'écran.
"""

from dataclasses import dataclass

from django.db.models import Q

from .models import Discount, FeeSchedule


@dataclass
class DueAmounts:
    """Montants dus par un élève, après réductions."""

    registration: int
    monthly_tuition: int
    #: Tarifs pleins, avant réduction — nécessaires pour chiffrer le manque à gagner.
    full_registration: int
    full_monthly_tuition: int
    discounts: list

    @property
    def has_discount(self):
        return bool(self.discounts)

    @property
    def scholarship_rate(self):
        """Taux de bourse effectif sur la mensualité, en pourcentage.

        Calculé sur le montant, non lu sur la réduction : deux réductions
        cumulées, ou une réduction en montant fixe, doivent aboutir au même
        indicateur qu'un pourcentage unique.
        """
        if not self.full_monthly_tuition:
            return 0
        saved = self.full_monthly_tuition - self.monthly_tuition
        return round(saved * 100 / self.full_monthly_tuition, 1)

    @property
    def is_full_scholarship(self):
        return self.full_monthly_tuition > 0 and self.monthly_tuition == 0

    def forgone(self, months):
        """Manque à gagner sur l'année : ce que la réduction coûte à l'école."""
        tuition_gap = (self.full_monthly_tuition - self.monthly_tuition) * months
        registration_gap = self.full_registration - self.registration
        return tuition_gap + registration_gap


def discounts_for(student, year):
    """Réductions applicables à un élève : les siennes et celles de sa famille."""
    query = Q(student=student)
    if student.family_id:
        query |= Q(family=student.family_id)
    return list(Discount.objects.filter(year=year).filter(query))


def due_for(student, year, *, schedule=None, discounts=None):
    """Montants dus par un élève, réductions appliquées.

    Retourne `None` si la classe n'a pas de grille tarifaire : le montant dû est
    alors indéterminable, et le signaler vaut mieux que de retourner zéro — un
    zéro se lirait comme « à jour ».
    """
    if schedule is None:
        schedule = FeeSchedule.objects.filter(
            classroom=student.classroom_id, year=year
        ).first()
    if schedule is None:
        return None

    if discounts is None:
        discounts = discounts_for(student, year)

    registration = schedule.registration_fee
    tuition = schedule.monthly_tuition

    # Les réductions se cumulent dans l'ordre d'enregistrement. Une bourse totale
    # ramène à zéro et rend les suivantes sans effet, ce qui est le comportement
    # attendu : on ne descend pas en dessous de zéro.
    for discount in discounts:
        if discount.scope in (Discount.Scope.REGISTRATION, Discount.Scope.BOTH):
            registration = discount.apply_to(registration)
        if discount.scope in (Discount.Scope.TUITION, Discount.Scope.BOTH):
            tuition = discount.apply_to(tuition)

    return DueAmounts(
        registration=registration,
        monthly_tuition=tuition,
        full_registration=schedule.registration_fee,
        full_monthly_tuition=schedule.monthly_tuition,
        discounts=discounts,
    )


def due_map(year, students):
    """Montants dus pour un ensemble d'élèves, en un minimum de requêtes.

    Les grilles tarifaires et les réductions sont chargées en une passe : sans
    cela, une école de 500 élèves déclencherait un millier de requêtes pour
    afficher ses arriérés.
    """
    schedules = {s.classroom_id: s for s in FeeSchedule.objects.filter(year=year)}

    by_student = {}
    by_family = {}
    for discount in Discount.objects.filter(year=year):
        if discount.student_id:
            by_student.setdefault(discount.student_id, []).append(discount)
        elif discount.family_id:
            by_family.setdefault(discount.family_id, []).append(discount)

    result = {}
    for student in students:
        applicable = by_student.get(student.id, []) + by_family.get(student.family_id, [])
        result[student.id] = due_for(
            student,
            year,
            schedule=schedules.get(student.classroom_id),
            discounts=applicable,
        )
    return result
