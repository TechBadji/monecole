"""Passage d'une année scolaire à la suivante.

Une rentrée n'est pas une remise à zéro : les élèves montent d'un niveau, les
classes et les enseignants sont réaffectés, et les inscriptions repartent à
zéro **sans effacer** ce qui précède. Chaque année garde ses notes, ses
matières, ses barèmes et ses titulaires.

Le principe qui gouverne ce module : **une inscription en attente n'est pas une
inscription**. Les élèves passés arrivent dans la nouvelle année en attente ;
ils apparaissent au secrétariat, qui doit les relancer, mais aucune mensualité
ne leur est réclamée avant confirmation. Les compter d'emblée gonflerait les
arriérés dès octobre, sur des élèves dont on ignore encore s'ils reviendront.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.db import transaction

from .grades import GRADE_CODES, grade_rank
from .models import (
    ClassRoom,
    ClassTeacher,
    Enrollment,
    EnrollmentStatus,
    Student,
    StudentStatus,
)


@dataclass
class PromotionPlan:
    """Ce que le passage ferait, avant qu'il ne le fasse."""

    moves: list = field(default_factory=list)
    repeats: list = field(default_factory=list)
    blocked: list = field(default_factory=list)
    already: list = field(default_factory=list)

    @property
    def summary(self):
        return {
            "moves": len(self.moves),
            "repeats": len(self.repeats),
            "blocked": len(self.blocked),
            "already": len(self.already),
        }


def next_classroom(classroom: ClassRoom) -> ClassRoom | None:
    """Classe du niveau suivant, en conservant la section si elle existe.

    Un élève de CI-B rejoint le CP-B si la section existe, le CP-A sinon. Le
    contraire — répartir au hasard — casserait des fratries et des habitudes
    que l'école a ses raisons de tenir.
    """
    rank = grade_rank(classroom.name)
    if rank is None or rank + 1 >= len(GRADE_CODES):
        return None

    target = GRADE_CODES[rank + 1]
    candidates = [
        room for room in ClassRoom.objects.all() if grade_rank(room.name) == rank + 1
    ]
    if not candidates:
        return None

    suffix = classroom.name.strip().upper().replace(" ", "")[len(GRADE_CODES[rank]):]
    suffix = suffix.lstrip("-_ ")
    if suffix:
        same = [c for c in candidates if c.name.upper().rstrip().endswith(suffix)]
        if same:
            return same[0]
    return sorted(candidates, key=lambda c: c.order)[0]


def plan_promotion(from_year, to_year, repeating_ids=()) -> PromotionPlan:
    """Calcule le passage sans rien écrire.

    Toujours appelé avant d'appliquer : un passage touche tous les élèves de
    l'établissement, et l'administration doit voir ce qu'il ferait avant de s'y
    engager.
    """
    repeating = set(repeating_ids or ())
    plan = PromotionPlan()

    existing = set(
        Enrollment.objects.filter(year=to_year).values_list("student_id", flat=True)
    )
    students = (
        Student.objects.filter(status=StudentStatus.ACTIVE)
        .select_related("classroom")
        .order_by("classroom__order", "last_name", "first_name")
    )

    for student in students:
        if student.id in existing:
            plan.already.append(student)
            continue

        if student.id in repeating:
            plan.repeats.append((student, student.classroom))
            continue

        target = next_classroom(student.classroom)
        if target is None:
            # Fin de cursus, ou niveau supérieur inexistant dans l'école : c'est
            # une décision à prendre, pas une classe à deviner.
            plan.blocked.append(student)
            continue

        plan.moves.append((student, student.classroom, target))

    return plan


@transaction.atomic
def apply_promotion(from_year, to_year, repeating_ids=(), *, school):
    """Crée les inscriptions en attente de la nouvelle année.

    Ne touche ni aux notes, ni aux matières, ni aux paiements de l'année
    précédente : elles restent rattachées à leur propre année.
    """
    plan = plan_promotion(from_year, to_year, repeating_ids)
    created = []

    for student, origin, target in plan.moves:
        created.append(
            Enrollment(
                school=school,
                student=student,
                year=to_year,
                classroom=target,
                status=EnrollmentStatus.PENDING,
                promoted_from=origin,
            )
        )
    for student, origin in plan.repeats:
        created.append(
            Enrollment(
                school=school,
                student=student,
                year=to_year,
                classroom=origin,
                status=EnrollmentStatus.PENDING,
                promoted_from=origin,
                is_repeat=True,
            )
        )

    Enrollment.objects.bulk_create(created)

    # Les titulaires de l'année précédente sont reconduits : c'est le cas le
    # plus fréquent, et l'administration corrige les exceptions. Ne rien
    # reconduire obligerait à réaffecter douze classes chaque rentrée.
    carried = []
    for link in ClassTeacher.objects.filter(year=from_year).select_related("classroom"):
        if not ClassTeacher.objects.filter(
            classroom=link.classroom, year=to_year
        ).exists():
            carried.append(
                ClassTeacher(
                    school=school,
                    classroom=link.classroom,
                    year=to_year,
                    teacher_id=link.teacher_id,
                )
            )
    ClassTeacher.objects.bulk_create(carried)

    return plan, len(created), len(carried)


def confirm_enrollment(enrollment, *, paid=None):
    """Confirme une inscription : l'élève entre réellement dans l'année.

    C'est à partir de là que les mensualités lui sont dues.
    """
    from django.utils import timezone

    enrollment.status = EnrollmentStatus.CONFIRMED
    enrollment.confirmed_at = timezone.now().date()
    fields = ["status", "confirmed_at"]

    if paid is not None:
        enrollment.registration_paid = paid
        fields.append("registration_paid")
        if paid and enrollment.paid_at is None:
            enrollment.paid_at = timezone.now().date()
            fields.append("paid_at")

    enrollment.save(update_fields=fields)

    # La classe de l'élève suit son inscription confirmée : c'est elle qui fait
    # foi pour les listes, les notes et l'assiduité de l'année en cours.
    if enrollment.student.classroom_id != enrollment.classroom_id:
        enrollment.student.classroom = enrollment.classroom
        enrollment.student.save(update_fields=["classroom"])

    return enrollment
