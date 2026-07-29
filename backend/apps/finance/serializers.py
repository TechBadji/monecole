from rest_framework import serializers

from .models import Expense, ExpenseCategory, OtherIncome, RecurringExpense


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ["id", "code", "label", "order", "is_active", "monthly_budget"]


class ExpenseSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="category.label", read_only=True)
    total_cost = serializers.IntegerField(read_only=True)

    class Meta:
        model = Expense
        fields = [
            "id", "year", "operation_date", "payment_date", "period", "channel",
            "invoice_number", "label", "amount", "transfer_fee", "category",
            "category_label", "receipt", "status", "approved_by", "approved_at",
            "total_cost", "created_at",
        ]
        # `period` est dérivée de `operation_date` : la laisser modifiable
        # permettrait de rattacher une dépense à un mois qui n'est pas le sien.
        read_only_fields = ["period", "approved_by", "approved_at", "created_at"]

    def validate_operation_date(self, value):
        year = self.initial_data.get("year") or getattr(self.instance, "year_id", None)
        if year:
            from apps.core.models import SchoolYear

            school_year = SchoolYear.objects.filter(pk=year).first()
            if school_year and not (school_year.start_date <= value <= school_year.end_date):
                raise serializers.ValidationError(
                    f"La date d'opération sort de l'exercice {school_year.label} "
                    f"({school_year.start_date} — {school_year.end_date})."
                )
        return value


class RecurringExpenseSerializer(serializers.ModelSerializer):
    class Meta:
        model = RecurringExpense
        fields = [
            "id", "label", "category", "amount", "channel", "day_of_month",
            "start_date", "end_date", "is_active",
        ]


class OtherIncomeSerializer(serializers.ModelSerializer):
    class Meta:
        model = OtherIncome
        fields = [
            "id", "year", "operation_date", "period", "label",
            "amount", "channel", "reference", "created_at",
        ]
        read_only_fields = ["period", "created_at"]
