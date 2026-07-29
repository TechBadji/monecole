from rest_framework import serializers

from .models import (
    ClassEnrollmentHistory,
    ClassRoom,
    Discount,
    Enrollment,
    Family,
    FeeSchedule,
    MonthlyPayment,
    Student,
)


class ClassRoomSerializer(serializers.ModelSerializer):
    student_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = ClassRoom
        fields = ["id", "name", "level", "order", "capacity", "student_count"]


class FamilySerializer(serializers.ModelSerializer):
    student_count = serializers.IntegerField(source="students.count", read_only=True)

    class Meta:
        model = Family
        fields = [
            "id", "name", "primary_contact", "phone", "email",
            "address", "student_count", "created_at",
        ]


class StudentSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    classroom_name = serializers.CharField(source="classroom.name", read_only=True)

    class Meta:
        model = Student
        fields = [
            "id", "first_name", "last_name", "full_name", "date_of_birth", "sex",
            "classroom", "classroom_name", "family", "parent_name", "parent_phone",
            "parent_email", "address", "enrollment_date", "status",
            "status_effective_date", "created_at",
        ]

    def validate(self, attrs):
        status = attrs.get("status", getattr(self.instance, "status", None))
        effective = attrs.get(
            "status_effective_date", getattr(self.instance, "status_effective_date", None)
        )
        if status and status != Student._meta.get_field("status").default and not effective:
            raise serializers.ValidationError(
                {
                    "status_effective_date": "Une date d'effet est requise dès que l'élève "
                    "n'est plus actif : elle détermine son maintien dans les effectifs."
                }
            )
        return attrs


class FeeScheduleSerializer(serializers.ModelSerializer):
    classroom_name = serializers.CharField(source="classroom.name", read_only=True)

    class Meta:
        model = FeeSchedule
        fields = [
            "id", "classroom", "classroom_name", "year", "registration_fee",
            "monthly_tuition", "monthly_canteen", "monthly_reinforcement",
            "uniform_fee", "insurance_fee", "ape_fee",
        ]


class EnrollmentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    classroom_name = serializers.CharField(source="classroom.name", read_only=True)
    total_received = serializers.IntegerField(read_only=True)

    class Meta:
        model = Enrollment
        fields = [
            "id", "student", "student_name", "year", "classroom", "classroom_name",
            "registration_paid", "registration_amount", "uniform_amount",
            "insurance_amount", "ape_amount", "paid_at", "total_received", "created_at",
        ]

    def validate(self, attrs):
        paid = attrs.get("registration_paid", getattr(self.instance, "registration_paid", False))
        amount = attrs.get(
            "registration_amount", getattr(self.instance, "registration_amount", 0)
        )
        if paid and not amount:
            raise serializers.ValidationError(
                {"registration_amount": "Une inscription marquée réglée doit porter un montant."}
            )
        return attrs


class MonthlyPaymentSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    total = serializers.IntegerField(read_only=True)

    class Meta:
        model = MonthlyPayment
        fields = [
            "id", "student", "student_name", "year", "period", "tuition", "canteen",
            "reinforcement", "uniform", "payment_date", "method", "reference",
            "received_by", "total", "created_at",
        ]

    def validate_period(self, value):
        """Normalise la période en fin de mois.

        Le client peut envoyer n'importe quel jour du mois ; la convention `EOMONTH`
        du modèle comptable est appliquée ici, une fois pour toutes.
        """
        from apps.core.periods import end_of_month

        return end_of_month(value)


class BulkMonthlyPaymentSerializer(serializers.Serializer):
    """Saisie groupée des encaissements d'une classe pour un mois.

    Le cahier des charges vise moins de 30 secondes par encaissement : saisir une
    classe entière en une requête, depuis une grille, est ce qui permet de tenir
    cette cible — pas l'optimisation d'un formulaire unitaire.
    """

    period = serializers.DateField()
    entries = serializers.ListField(child=serializers.DictField(), allow_empty=False)

    def validate_period(self, value):
        from apps.core.periods import end_of_month

        return end_of_month(value)


class DiscountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Discount
        fields = [
            "id", "student", "family", "year", "kind", "scope", "value",
            "reason", "approved_by", "approved_at", "created_at",
        ]

    def validate(self, attrs):
        student = attrs.get("student", getattr(self.instance, "student", None))
        family = attrs.get("family", getattr(self.instance, "family", None))
        if bool(student) == bool(family):
            raise serializers.ValidationError(
                "Une réduction porte soit sur un élève, soit sur une famille — pas les deux."
            )
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        value = attrs.get("value", getattr(self.instance, "value", 0))
        if kind == Discount.Kind.PERCENT and value > 100:
            raise serializers.ValidationError(
                {"value": "Un pourcentage de réduction ne peut pas dépasser 100."}
            )
        return attrs


class ClassEnrollmentHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ClassEnrollmentHistory
        fields = [
            "id", "student", "year", "from_classroom", "to_classroom",
            "effective_date", "is_repeat", "reason",
        ]
