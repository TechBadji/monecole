"""Badgeage au portail, suivi d'assiduité et cartes QR."""

from datetime import date, datetime, timedelta

from django.db.models import Count, Max, Min, Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from apps.core.models import Role
from apps.core.views_base import TenantViewSetMixin
from apps.students.models import ClassRoom, Student, StudentStatus

from .models import AttendanceEvent, AttendanceSettings
from .qr import qr_sheet_pdf, resolve_payload

# Deux scans de la même carte dans cet intervalle valent un seul passage.
DEBOUNCE = timedelta(minutes=2)


class AttendanceEventSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    matricule = serializers.CharField(source="student.matricule", read_only=True)
    classroom = serializers.CharField(source="student.classroom.name", read_only=True)

    class Meta:
        model = AttendanceEvent
        fields = [
            "id", "student", "student_name", "matricule", "classroom",
            "direction", "occurred_at", "day", "source", "recorded_by",
            "note", "is_anomaly",
        ]
        read_only_fields = ["day", "is_anomaly"]


class AttendanceSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceSettings
        fields = [
            "id", "school_opens_at", "late_after", "school_closes_at",
            "notify_parent_on_entry", "notify_parent_on_exit",
            "notify_parent_on_absence",
        ]


class ScanViewSet(TenantViewSetMixin, ViewSet):
    """Poste de badgeage : un appareil au portail scanne les cartes."""

    resource = "attendance"

    @action(detail=False, methods=["post"])
    def badge(self, request):
        """Enregistre un passage à partir d'un QR scanné ou d'un matricule saisi.

        Le sens (entrée ou sortie) est **déduit** du dernier passage du jour, et non
        demandé à l'agent : au portail, à sept heures et demie, personne ne
        sélectionne un sens dans une liste.

        Deux scans rapprochés de la même carte comptent pour un seul passage, et
        l'agent en est informé — sans quoi une carte passée deux fois produirait
        une entrée suivie d'une sortie immédiate.
        """
        payload = request.data.get("payload") or request.data.get("matricule") or ""
        student = resolve_payload(payload)
        if student is None:
            raise NotFound(
                {"detail": "Carte inconnue. Vérifiez le matricule ou saisissez-le à la main."}
            )
        if student.status != StudentStatus.ACTIVE:
            raise ValidationError(
                {"detail": f"{student.full_name} n'est plus actif ({student.get_status_display()})."}
            )

        now = timezone.now()
        today = timezone.localtime(now).date()

        last = (
            AttendanceEvent.objects.filter(student=student, day=today)
            .order_by("-occurred_at")
            .first()
        )

        # Anti-rebond, évalué **avant** la déduction du sens. Un élève dont la
        # carte est passée deux fois en quelques secondes n'est pas entré puis
        # ressorti : c'est un double scan, et l'enregistrer comme une sortie
        # fausserait la feuille de présence de toute la journée.
        if last is not None and (now - last.occurred_at) < DEBOUNCE:
            return Response(
                {
                    "duplicate": True,
                    "detail": f"{student.full_name} vient déjà d'être scanné "
                    f"({last.get_direction_display().lower()} à "
                    f"{timezone.localtime(last.occurred_at):%H:%M}).",
                    "student": _student_card(student),
                    "event": AttendanceEventSerializer(last).data,
                }
            )

        # Premier passage du jour : entrée. Ensuite, on alterne.
        direction = (
            AttendanceEvent.Direction.IN
            if last is None or last.direction == AttendanceEvent.Direction.OUT
            else AttendanceEvent.Direction.OUT
        )

        # Un sens imposé par l'agent prime sur la déduction — il corrige alors une
        # anomalie qu'il constate, et on la marque comme telle.
        forced = request.data.get("direction")
        anomaly = False
        if forced in (AttendanceEvent.Direction.IN, AttendanceEvent.Direction.OUT):
            anomaly = last is not None and last.direction == forced
            direction = forced

        settings = AttendanceSettings.for_school(request.user.school)
        local_time = timezone.localtime(now).time()
        is_late = (
            direction == AttendanceEvent.Direction.IN and local_time > settings.late_after
        )

        event = AttendanceEvent.objects.create(
            school=request.user.school,
            student=student,
            direction=direction,
            occurred_at=now,
            source=AttendanceEvent.Source.QR
            if request.data.get("payload")
            else AttendanceEvent.Source.MANUAL,
            recorded_by=request.user.get_full_name() or request.user.email,
            is_anomaly=anomaly,
            note="Retard" if is_late else "",
        )

        self._notify(request.user.school, settings, event, student)

        return Response(
            {
                "duplicate": False,
                "student": _student_card(student),
                "event": AttendanceEventSerializer(event).data,
                "is_late": is_late,
                "direction_label": event.get_direction_display(),
            },
            status=201,
        )

    def _notify(self, school, settings, event, student):
        """Avertit le parent, si l'école l'a activé.

        Un échec d'envoi ne fait jamais échouer le badgeage : l'élève est entré,
        l'événement doit être enregistré même si le SMS ne part pas.
        """
        entering = event.direction == AttendanceEvent.Direction.IN
        wanted = (
            settings.notify_parent_on_entry if entering else settings.notify_parent_on_exit
        )
        if not wanted:
            return

        phone = student.parent_phone or (
            student.family.phone if student.family_id else ""
        )
        if not phone:
            return

        try:
            from apps.notifications.services import dispatch_sms

            moment = timezone.localtime(event.occurred_at).strftime("%H:%M")
            verb = "est arrive a" if entering else "a quitte"
            dispatch_sms(
                school,
                recipient=phone,
                message=(
                    f"{school.name} : {student.full_name} {verb} l'ecole a {moment}."
                ),
                template="attendance_notice",
                payload={"student": student.id, "direction": event.direction},
            )
        except Exception:  # noqa: BLE001 — le badgeage prime sur la notification
            import logging

            logging.getLogger(__name__).exception(
                "Notification d'assiduité impossible pour %s", student.matricule
            )


def _student_card(student):
    """Ce que le poste de badgeage affiche à l'agent après un scan."""
    return {
        "id": student.id,
        "matricule": student.matricule,
        "name": student.full_name,
        "classroom": student.classroom.name,
        "parent_phone": student.parent_phone,
    }


class AttendanceViewSet(TenantViewSetMixin, ViewSet):
    """Consultation de l'assiduité."""

    resource = "attendance"

    def list(self, request):
        """Derniers passages, filtrables par jour et par classe."""
        day = request.query_params.get("day")
        classroom = request.query_params.get("classroom")

        events = AttendanceEvent.objects.select_related("student", "student__classroom")
        events = events.filter(day=date.fromisoformat(day)) if day else events
        if classroom:
            events = events.filter(student__classroom_id=classroom)

        return Response(
            {"results": AttendanceEventSerializer(events[:300], many=True).data}
        )

    @action(detail=False, methods=["get"])
    def daily(self, request):
        """Feuille de présence d'une journée, classe par classe.

        Un élève est « présent » s'il a au moins une entrée ce jour-là. L'absence
        de badge n'est pas la même chose qu'une absence constatée : la feuille
        distingue les deux, faute de quoi une panne de lecteur transformerait
        toute l'école en absents.
        """
        day = request.query_params.get("day")
        target = date.fromisoformat(day) if day else timezone.localdate()
        classroom_id = request.query_params.get("classroom")

        students = Student.objects.filter(status=StudentStatus.ACTIVE).select_related(
            "classroom"
        )
        if classroom_id:
            students = students.filter(classroom_id=classroom_id)

        events = (
            AttendanceEvent.objects.filter(day=target)
            .values("student")
            .annotate(
                first_in=Min("occurred_at", filter=Q(direction=AttendanceEvent.Direction.IN)),
                last_out=Max("occurred_at", filter=Q(direction=AttendanceEvent.Direction.OUT)),
                passages=Count("id"),
            )
        )
        by_student = {row["student"]: row for row in events}
        settings = AttendanceSettings.for_school(request.user.school)

        rows = []
        for student in students:
            record = by_student.get(student.id)
            arrival = record["first_in"] if record else None
            rows.append(
                {
                    "student": student.id,
                    "matricule": student.matricule,
                    "name": student.full_name,
                    "classroom": student.classroom.name,
                    "present": record is not None,
                    "arrival": timezone.localtime(arrival).strftime("%H:%M") if arrival else None,
                    "departure": (
                        timezone.localtime(record["last_out"]).strftime("%H:%M")
                        if record and record["last_out"]
                        else None
                    ),
                    "late": bool(
                        arrival and timezone.localtime(arrival).time() > settings.late_after
                    ),
                    "passages": record["passages"] if record else 0,
                }
            )

        present = sum(1 for row in rows if row["present"])
        return Response(
            {
                "day": target,
                "total": len(rows),
                "present": present,
                "no_badge": len(rows) - present,
                "late": sum(1 for row in rows if row["late"]),
                "note": "« Sans badge » ne signifie pas « absent » : un lecteur en "
                "panne ou une carte oubliée produisent le même état.",
                "results": sorted(rows, key=lambda r: (r["classroom"], r["name"])),
            }
        )

    @action(detail=False, methods=["get"], url_path="student/(?P<student_id>[^/.]+)")
    def student_history(self, request, student_id=None):
        """Historique d'assiduité d'un élève, jour par jour."""
        student = Student.objects.filter(pk=student_id).first()
        if student is None:
            raise NotFound("Élève introuvable.")

        days = int(request.query_params.get("days") or 30)
        since = timezone.localdate() - timedelta(days=days)

        events = AttendanceEvent.objects.filter(
            student=student, day__gte=since
        ).order_by("-occurred_at")

        grouped = {}
        for event in events:
            entry = grouped.setdefault(
                event.day, {"day": event.day, "arrival": None, "departure": None, "passages": 0}
            )
            entry["passages"] += 1
            local = timezone.localtime(event.occurred_at).strftime("%H:%M")
            if event.direction == AttendanceEvent.Direction.IN:
                entry["arrival"] = local
            else:
                entry["departure"] = local

        return Response(
            {
                "student": _student_card(student),
                "days": days,
                "present_days": len(grouped),
                "results": sorted(grouped.values(), key=lambda d: d["day"], reverse=True),
            }
        )

    @action(detail=False, methods=["get", "put"], url_path="settings")
    def settings_view(self, request):
        settings = AttendanceSettings.for_school(request.user.school)
        if request.method == "PUT":
            if request.user.role != Role.ADMIN:
                raise ValidationError({"detail": "Réservé à l'administrateur."})
            serializer = AttendanceSettingsSerializer(settings, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return Response(AttendanceSettingsSerializer(settings).data)


class QrSheetView(TenantViewSetMixin, APIView):
    """Planche de cartes QR à imprimer, par classe ou pour toute l'école."""

    resource = "student"

    def get(self, request):
        students = Student.objects.filter(status=StudentStatus.ACTIVE).select_related(
            "classroom"
        )
        classroom_id = request.query_params.get("classroom")
        label = "toutes classes"
        if classroom_id:
            classroom = ClassRoom.objects.filter(pk=classroom_id).first()
            if classroom is None:
                raise NotFound("Classe introuvable.")
            students = students.filter(classroom=classroom)
            label = classroom.name

        students = list(students.order_by("classroom__order", "last_name", "first_name"))
        if not students:
            raise ValidationError({"detail": "Aucun élève actif pour cette sélection."})

        response = qr_sheet_pdf(students, request.user.school)
        response["Content-Disposition"] = (
            f'attachment; filename="cartes-{label.lower().replace(" ", "-")}.pdf"'
        )
        return response
