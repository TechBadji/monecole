from rest_framework import serializers

from .models import (
    Absence,
    PayrollProfile,
    PayrollScale,
    Payslip,
    Salary,
    SalaryRaise,
    SalaryRubric,
    Teacher,
    TeacherContract,
)


class TeacherSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Teacher
        fields = [
            "id", "matricule", "first_name", "last_name", "full_name", "sex",
            "date_of_birth", "cni", "marital_status", "corps", "grade",
            "academic_diploma", "professional_diploma", "entry_date", "specialty",
            "function", "service_start_date", "courses_taught", "class_type",
            "students_count", "contract_type", "is_active", "created_at",
        ]
        # Le matricule est attribué par le système, jamais soumis par le client.
        read_only_fields = ["matricule", "created_at"]


class TeacherContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeacherContract
        fields = [
            "id", "teacher", "reference", "contract_type", "start_date",
            "end_date", "gross_salary", "document", "notes",
        ]


class AbsenceSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source="teacher.full_name", read_only=True)

    class Meta:
        model = Absence
        fields = ["id", "teacher", "teacher_name", "kind", "start_date", "end_date", "reason"]

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "La fin précède le début."})
        return attrs


class SalaryRubricSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source="teacher.full_name", read_only=True, default=None)

    class Meta:
        model = SalaryRubric
        fields = ["id", "code", "label", "teacher", "teacher_name", "order"]


class SalarySerializer(serializers.ModelSerializer):
    rubric_code = serializers.CharField(source="rubric.code", read_only=True)
    net_amount = serializers.IntegerField(read_only=True)

    class Meta:
        model = Salary
        fields = [
            "id", "rubric", "rubric_code", "year", "period", "gross_amount",
            "social_contributions", "other_deductions", "net_amount",
            "paid_at", "created_at",
        ]

    def validate_period(self, value):
        from apps.core.periods import end_of_month

        return end_of_month(value)

    def validate(self, attrs):
        gross = attrs.get("gross_amount", getattr(self.instance, "gross_amount", 0))
        social = attrs.get("social_contributions", getattr(self.instance, "social_contributions", 0))
        other = attrs.get("other_deductions", getattr(self.instance, "other_deductions", 0))
        if social + other > gross:
            raise serializers.ValidationError(
                "Les retenues dépassent le brut : le net serait négatif."
            )
        return attrs


class SalaryRaiseSerializer(serializers.ModelSerializer):
    class Meta:
        model = SalaryRaise
        fields = [
            "id", "teacher", "effective_date", "previous_amount",
            "new_amount", "reason", "approved_by",
        ]


class PayrollScaleSerializer(serializers.ModelSerializer):
    is_validated = serializers.BooleanField(read_only=True)

    class Meta:
        model = PayrollScale
        fields = [
            "id", "label", "effective_from", "values",
            "validated_by", "is_validated", "notes", "created_at",
        ]


class PayrollProfileSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source="teacher.full_name", read_only=True)
    matricule = serializers.CharField(source="teacher.matricule", read_only=True)
    gross = serializers.IntegerField(read_only=True)

    class Meta:
        model = PayrollProfile
        fields = [
            "id", "teacher", "teacher_name", "matricule", "base_salary",
            "taxable_bonus", "non_taxable_allowance", "gross", "is_executive",
            "family_shares", "social_security_number", "bank_account",
        ]


class PayslipSerializer(serializers.ModelSerializer):
    teacher_name = serializers.CharField(source="teacher.full_name", read_only=True)
    matricule = serializers.CharField(source="teacher.matricule", read_only=True)
    employer_cost = serializers.IntegerField(read_only=True)
    scale_validated = serializers.BooleanField(source="scale.is_validated", read_only=True)

    class Meta:
        model = Payslip
        fields = [
            "id", "teacher", "teacher_name", "matricule", "year", "scale",
            "scale_validated", "period", "gross", "non_taxable",
            "employee_contributions", "employer_contributions", "income_tax",
            "trimf", "other_deductions", "net_pay", "employer_cost",
            "computation", "paid_at", "created_at",
        ]
        read_only_fields = fields
