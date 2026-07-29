from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    ExpenseCategoryViewSet,
    ExpenseViewSet,
    OtherIncomeViewSet,
    RecurringExpenseViewSet,
)

router = DefaultRouter()
router.register("expense-categories", ExpenseCategoryViewSet, basename="expensecategory")
router.register("expenses", ExpenseViewSet, basename="expense")
router.register("recurring-expenses", RecurringExpenseViewSet, basename="recurringexpense")
router.register("other-incomes", OtherIncomeViewSet, basename="otherincome")

urlpatterns = [path("", include(router.urls))]
