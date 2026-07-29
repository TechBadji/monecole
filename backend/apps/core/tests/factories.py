"""Fabriques partagées par les tests."""

import datetime

from django.contrib.auth import get_user_model

from apps.core.models import Role, School, SchoolYear, Subscription
from apps.core.periods import default_year_bounds
from apps.core.tenancy import tenant_context
from apps.finance.models import ExpenseCategory
from apps.students.models import ClassRoom, FeeSchedule, Level, Student

User = get_user_model()


def make_school(name="École Test", slug="ecole-test"):
    return School.objects.create(
        name=name,
        slug=slug,
        subscription=Subscription.objects.create(),
        country="SN",
        currency="XOF",
    )


def make_year(school, start_year=2025, is_current=True):
    start, end = default_year_bounds(start_year)
    with tenant_context(school):
        return SchoolYear.objects.create(
            school=school,
            label=f"{start_year}/{start_year + 1}",
            start_date=start,
            end_date=end,
            tuition_months=9,
            is_current=is_current,
        )


def make_user(school, role=Role.ADMIN, email=None, password="TestPassw0rd!"):
    email = email or f"{role.lower()}@{school.slug}.test"
    return User.objects.create_user(
        email=email, password=password, role=role, school=school, first_name="Test"
    )


def make_classroom(school, name="CP", order=5, level=Level.PRIMARY):
    with tenant_context(school):
        return ClassRoom.objects.create(school=school, name=name, level=level, order=order)


def make_fee_schedule(school, classroom, year, tuition=15_000, registration=25_000):
    with tenant_context(school):
        return FeeSchedule.objects.create(
            school=school, classroom=classroom, year=year,
            registration_fee=registration, monthly_tuition=tuition,
            monthly_canteen=10_000, monthly_reinforcement=5_000,
            uniform_fee=12_000, insurance_fee=3_000, ape_fee=5_000,
        )


def make_student(school, classroom, first_name="Aminata", last_name="Diop"):
    with tenant_context(school):
        return Student.objects.create(
            school=school, classroom=classroom,
            first_name=first_name, last_name=last_name,
            date_of_birth=datetime.date(2018, 5, 12),
        )


def make_category(school, code="RENT", label="LOCATIONS DE BÂTIMENTS", order=0):
    with tenant_context(school):
        return ExpenseCategory.objects.create(
            school=school, code=code, label=label, order=order
        )
