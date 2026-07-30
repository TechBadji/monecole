"""Jeu de données de démonstration.

Reproduit la structure du classeur source — les dix classes, les rubriques
salariales A/B/C, les seize rubriques de charge — et la renseigne avec des données
plausibles mais **déterministes** : un `random.seed` fixe garantit que deux
exécutions produisent les mêmes totaux, condition nécessaire pour que les tests de
non-régression aient un sens.

    python manage.py seed_demo --reset
"""

import datetime
import random
from decimal import Decimal

from django.utils import timezone

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.core.models import Role, School, SchoolYear, Subscription
from apps.core.periods import default_year_bounds, end_of_month, month_ends
from apps.core.tenancy import tenant_context, unscoped
from apps.finance.models import DEFAULT_EXPENSE_CATEGORIES, Expense, ExpenseCategory, OtherIncome
from apps.staff.models import PayrollProfile, PayrollScale, Salary, SalaryRubric, Teacher
from apps.academics.models import (
    DEFAULT_SUBJECTS,
    ClassSubject,
    Composition,
    Grade,
    GradeSheet,
    ReportCardSettings,
    Subject,
)
from apps.attendance.models import AttendanceEvent, AttendanceSettings
from apps.students.models import (
    Discount,
    ClassRoom,
    Enrollment,
    Family,
    FeeSchedule,
    Level,
    MonthlyPayment,
    Student,
)

User = get_user_model()

# Les dix classes du classeur, dans l'ordre pédagogique.
CLASSES = [
    ("GARDERIE", Level.PRESCHOOL), ("PS", Level.PRESCHOOL), ("MS", Level.PRESCHOOL),
    ("GS", Level.PRESCHOOL), ("CI", Level.PRIMARY), ("CP", Level.PRIMARY),
    ("CE1", Level.PRIMARY), ("CE2", Level.PRIMARY), ("CM1", Level.PRIMARY),
    ("CM2", Level.PRIMARY),
]

# Tarifs indicatifs en FCFA, croissants du préscolaire au CM2.
FEES = {
    "GARDERIE": (15_000, 10_000), "PS": (20_000, 12_000), "MS": (20_000, 12_000),
    "GS": (20_000, 13_000), "CI": (25_000, 15_000), "CP": (25_000, 15_000),
    "CE1": (25_000, 16_000), "CE2": (25_000, 16_000), "CM1": (30_000, 18_000),
    "CM2": (30_000, 18_000),
}

FIRST_NAMES = [
    "Aminata", "Mamadou", "Fatou", "Ibrahima", "Aïssatou", "Ousmane", "Khadija",
    "Cheikh", "Mariama", "Abdoulaye", "Ndeye", "Moussa", "Awa", "Modou", "Bineta",
    "Serigne", "Sokhna", "Alioune", "Coumba", "Babacar", "Rokhaya", "Pape",
]
LAST_NAMES = [
    "Diop", "Ndiaye", "Fall", "Sow", "Ba", "Sarr", "Gueye", "Diallo", "Faye",
    "Mbaye", "Cissé", "Sylla", "Camara", "Thiam", "Seck", "Niang", "Bodian", "Sakho",
]

TEACHERS = [
    ("Ousmane", "Bodian", "M", "Instituteur", "CM1-CM2"),
    ("Aïssatou", "Sakho", "F", "Institutrice", "CE1-CE2"),
    ("Mamadou", "Diallo", "M", "Instituteur", "CI-CP"),
    ("Fatou", "Ndiaye", "F", "Éducatrice préscolaire", "PS-MS"),
    ("Bineta", "Faye", "F", "Éducatrice préscolaire", "GS-Garderie"),
    ("Cheikh", "Thiam", "M", "Professeur d'arabe", "Toutes classes"),
    ("Rokhaya", "Seck", "F", "Professeure d'anglais", "Élémentaire"),
    ("Awa", "Camara", "F", "Assistante stagiaire", "Préscolaire"),
    ("Modou", "Sylla", "M", "Gardien", ""),
    ("Coumba", "Sarr", "F", "Femme de ménage", ""),
]

EXPENSE_SAMPLES = [
    ("RENT", "Loyer des bâtiments", 450_000, 12),
    ("SALARY", "Salaires du personnel", 1_350_000, 12),
    ("ELECTRICITY", "Facture SENELEC", 85_000, 12),
    ("WATER", "Facture SEN'EAU", 32_000, 12),
    ("SUPPLIES", "Fournitures scolaires et de bureau", 120_000, 6),
    ("TEACHING_EQUIPMENT", "Matériel pédagogique", 180_000, 3),
    ("TELECOM", "Internet et téléphonie", 45_000, 12),
    ("MAINTENANCE", "Travaux et réparations", 220_000, 4),
    ("TRANSPORT", "Frais de transport", 60_000, 8),
    ("INSURANCE", "Assurance de l'établissement", 350_000, 1),
    ("HOSPITALITY", "Réceptions et restauration", 75_000, 3),
    ("ADVERTISING", "Campagne d'inscription", 150_000, 2),
    ("SMALL_EQUIPMENT", "Petit matériel", 40_000, 5),
    ("ADMIN_CHARGES", "Dossiers de régularisation", 90_000, 2),
    ("TRAINING", "Formation du personnel", 200_000, 1),
    ("SALARY_ARREARS", "Arriéré de salaire réglé", 250_000, 2),
]


class Command(BaseCommand):
    help = "Charge un jeu de données de démonstration reproduisant le classeur source."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Supprime l'école de démo existante.")
        parser.add_argument("--students", type=int, default=18, help="Élèves par classe (défaut : 18).")
        parser.add_argument("--year", type=int, default=2025, help="Année de début de l'exercice.")

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(20252026)  # déterminisme : mêmes totaux à chaque exécution

        if options["reset"]:
            self._teardown()

        subscription = Subscription.objects.create(
            plan=Subscription.Plan.STANDARD,
            status=Subscription.Status.ACTIVE,
            current_period_end=datetime.date(options["year"] + 1, 9, 30),
            max_students=300,
        )
        school = School.objects.create(
            name="Groupe Scolaire Darou Louqmane",
            slug="darou-louqmane",
            address="Dakar, Sénégal",
            phone="+221 33 000 00 00",
            email="contact@darou-louqmane.sn",
            country="SN",
            currency="XOF",
            subscription=subscription,
        )

        with tenant_context(school):
            year = self._create_year(school, options["year"])
            self._create_users(school)
            classrooms = self._create_classes(school, year)
            teachers = self._create_teachers(school)
            self._create_salaries(school, year, teachers)
            self._create_payroll(school, year, teachers)
            categories = self._create_categories(school)
            self._create_students(school, year, classrooms, options["students"])
            self._create_expenses(school, year, categories)
            self._create_other_income(school, year)
            self._create_scholarships(school, year, classrooms)
            self._create_academics(school, year, classrooms, teachers)
            self._create_attendance(school, year, classrooms)

        self._summary(school, year)

    # ------------------------------------------------------------------ #

    def _teardown(self):
        """Supprime l'école de démonstration, écritures comprises.

        `School.delete()` ne suffit pas : `SchoolYear` est en cascade depuis
        l'établissement, mais les écritures qui la référencent (inscriptions,
        encaissements, dépenses, bulletins) sont en `PROTECT` — c'est voulu, une
        année scolaire ne doit jamais emporter sa comptabilité par accident. Le
        nettoyage se fait donc de la feuille vers la racine.
        """
        from apps.payments.models import PaymentTransaction
        from apps.staff.models import Payslip

        with unscoped():
            school = School.objects.filter(slug="darou-louqmane").first()
            if school is None:
                return

            # De la plus dépendante à la moins dépendante.
            # Écritures d'abord, puis les référentiels qu'elles protègent.
            from apps.academics.models import ReportCardSettings as RCS
            from apps.attendance.models import AttendanceEvent as AE, AttendanceSettings as AS
            from apps.notifications.models import OtpCode, ReminderRun
            from apps.staff.models import PayrollProfile, PayrollScale

            for model in (
                PaymentTransaction, Payslip, MonthlyPayment, Enrollment,
                Expense, OtherIncome, Salary, PayrollProfile, PayrollScale,
                OtpCode, ReminderRun, AE, AS, RCS, Grade, GradeSheet,
                Composition, ClassSubject, Subject, Discount,
            ):
                model.all_objects.filter(school=school).delete()

            # `ClassRoom` et `Teacher` sont protégés par les élèves et le personnel :
            # on vide donc les uns avant les autres.
            Student.all_objects.filter(school=school).delete()
            Family.all_objects.filter(school=school).delete()
            Teacher.all_objects.filter(school=school).delete()
            ClassRoom.all_objects.filter(school=school).delete()
            ExpenseCategory.all_objects.filter(school=school).delete()
            SchoolYear.all_objects.filter(school=school).delete()

            school.delete()
            User.objects.filter(school__isnull=True, email="super@monecole.sn").delete()

        self.stdout.write(self.style.WARNING("École de démonstration supprimée."))

    def _create_year(self, school, start_year):
        start, end = default_year_bounds(start_year)
        return SchoolYear.objects.create(
            school=school,
            label=f"{start_year}/{start_year + 1}",
            start_date=start,
            end_date=end,
            tuition_months=9,
            is_current=True,
        )

    def _create_users(self, school):
        accounts = [
            ("admin@darou-louqmane.sn", "Awa", "Diop", Role.ADMIN),
            ("comptable@darou-louqmane.sn", "Ibrahima", "Fall", Role.ACCOUNTANT),
            ("secretaire@darou-louqmane.sn", "Ndeye", "Gueye", Role.SECRETARY),
        ]
        for email, first, last, role in accounts:
            User.objects.create_user(
                email=email, password="MonEcole2026!", first_name=first,
                last_name=last, role=role, school=school,
            )
        User.objects.create_superuser(
            email="super@monecole.sn", password="MonEcole2026!",
            first_name="Super", last_name="Admin",
        )

    def _create_classes(self, school, year):
        classrooms = []
        for order, (name, level) in enumerate(CLASSES):
            classroom = ClassRoom.objects.create(
                school=school, name=name, level=level, order=order, capacity=35
            )
            registration, tuition = FEES[name]
            FeeSchedule.objects.create(
                school=school, classroom=classroom, year=year,
                registration_fee=registration, monthly_tuition=tuition,
                monthly_canteen=10_000, monthly_reinforcement=5_000,
                uniform_fee=12_000, insurance_fee=3_000, ape_fee=5_000,
            )
            classrooms.append(classroom)
        return classrooms

    def _create_teachers(self, school):
        teachers = []
        for first, last, sex, function, classes in TEACHERS:
            teachers.append(
                Teacher.objects.create(
                    school=school, first_name=first, last_name=last, sex=sex,
                    function=function, class_type=classes,
                    specialty=function, corps="Enseignement privé",
                    service_start_date=datetime.date(2020, 10, 1),
                    contract_type=Teacher.ContractType.PERMANENT,
                )
            )
        return teachers

    def _create_salaries(self, school, year, teachers):
        """Trois rubriques A, B, C comme dans l'onglet « Salaires »."""
        rubrics = [
            SalaryRubric.objects.create(school=school, code="A", label="Personnel enseignant", order=0),
            SalaryRubric.objects.create(school=school, code="B", label="Personnel administratif", order=1),
            SalaryRubric.objects.create(school=school, code="C", label="Personnel de service", order=2),
        ]
        monthly = {"A": 900_000, "B": 300_000, "C": 150_000}
        for period in year.fiscal_months:
            for rubric in rubrics:
                Salary.objects.create(
                    school=school, rubric=rubric, year=year, period=period,
                    gross_amount=monthly[rubric.code],
                    social_contributions=monthly[rubric.code] // 10,
                    paid_at=period,
                )

    def _create_payroll(self, school, year, teachers):
        """Barème sénégalais par défaut et profils de paie."""
        PayrollScale.objects.create(
            school=school,
            label=f"Barème {year.start_date.year + 1}",
            effective_from=year.start_date,
            notes="Valeurs par défaut du schéma sénégalais — à faire valider par un "
            "expert-comptable avant remise de bulletins réels.",
        )
        # Salaires plausibles : direction, enseignants, personnel de service.
        grid = [
            (450_000, True), (280_000, False), (280_000, False), (240_000, False),
            (240_000, False), (200_000, False), (200_000, False), (120_000, False),
            (100_000, False), (90_000, False),
        ]
        for teacher, (base, executive) in zip(teachers, grid):
            PayrollProfile.objects.create(
                school=school,
                teacher=teacher,
                base_salary=base,
                non_taxable_allowance=25_000,  # indemnité de transport
                is_executive=executive,
                family_shares=random.choice(["1", "1.5", "2", "2.5", "3"]),
            )

    def _create_categories(self, school):
        categories = {}
        for order, (code, label) in enumerate(DEFAULT_EXPENSE_CATEGORIES):
            categories[code] = ExpenseCategory.objects.create(
                school=school, code=code, label=label, order=order
            )
        return categories

    def _create_students(self, school, year, classrooms, per_class):
        periods = year.tuition_month_ends
        today = datetime.date.today()

        for classroom in classrooms:
            schedule = FeeSchedule.objects.get(classroom=classroom, year=year)
            for index in range(per_class):
                first = random.choice(FIRST_NAMES)
                last = random.choice(LAST_NAMES)
                family = Family.objects.create(
                    school=school, name=last,
                    primary_contact=f"{random.choice(FIRST_NAMES)} {last}",
                    phone=f"+2217{random.randint(0, 9)}{random.randint(1000000, 9999999)}",
                )
                student = Student.objects.create(
                    school=school, first_name=first, last_name=last,
                    # Âge cohérent avec le niveau : ~3 ans en garderie, ~12 en CM2.
                    # La formule était inversée et produisait des CM2 de quatre ans.
                    date_of_birth=datetime.date(
                        year.start_date.year - 3 - classroom.order,
                        random.randint(1, 12),
                        random.randint(1, 28),
                    ),
                    sex=random.choice(["M", "F"]), classroom=classroom, family=family,
                    parent_name=family.primary_contact, parent_phone=family.phone,
                    enrollment_date=datetime.date(year.start_date.year, 9, random.randint(1, 30)),
                )

                # 85 % des inscriptions sont réglées — un reliquat d'impayés rend le
                # jeu de données représentatif de la réalité d'une école.
                paid = random.random() < 0.85
                Enrollment.objects.create(
                    school=school, student=student, year=year, classroom=classroom,
                    registration_paid=paid,
                    registration_amount=schedule.registration_fee if paid else 0,
                    uniform_amount=schedule.uniform_fee if paid else 0,
                    insurance_amount=schedule.insurance_fee if paid else 0,
                    ape_amount=schedule.ape_fee if paid else 0,
                    paid_at=end_of_month(year.start_date) if paid else None,
                )

                takes_canteen = random.random() < 0.4
                takes_reinforcement = random.random() < 0.25
                for period in periods:
                    if period > today:
                        break
                    # Taux de recouvrement dégressif : les impayés s'accumulent en
                    # cours d'année, comme observé en pratique.
                    if random.random() > 0.9:
                        continue
                    MonthlyPayment.objects.create(
                        school=school, student=student, year=year, period=period,
                        tuition=schedule.monthly_tuition,
                        canteen=schedule.monthly_canteen if takes_canteen else 0,
                        reinforcement=schedule.monthly_reinforcement if takes_reinforcement else 0,
                        uniform=0,
                        payment_date=period,
                        method=random.choice([
                            MonthlyPayment.Method.CASH,
                            MonthlyPayment.Method.CASH,
                            MonthlyPayment.Method.MOBILE_MONEY,
                        ]),
                    )

    def _create_expenses(self, school, year, categories):
        periods = year.fiscal_months
        today = datetime.date.today()
        for code, label, amount, occurrences in EXPENSE_SAMPLES:
            for period in periods[:occurrences]:
                if period > today:
                    break
                variation = random.randint(-5, 10) / 100
                Expense.objects.create(
                    school=school, year=year,
                    operation_date=period.replace(day=min(15, period.day)),
                    payment_date=period,
                    label=label,
                    amount=int(amount * (1 + variation)),
                    transfer_fee=random.choice([0, 0, 500, 1_000, 2_500]),
                    category=categories[code],
                    channel=random.choice([
                        Expense.Channel.CASH,
                        Expense.Channel.TRANSFER,
                        Expense.Channel.MOBILE_MONEY,
                    ]),
                    status=Expense.Status.APPROVED,
                )

    def _create_other_income(self, school, year):
        """Apports d'actionnaires — ligne « AUTRE PRODUIT » du bilan."""
        today = datetime.date.today()
        for period in year.fiscal_months[:6]:
            if period > today:
                break
            OtherIncome.objects.create(
                school=school, year=year,
                operation_date=period.replace(day=min(10, period.day)),
                label="Apport en compte courant d'actionnaire",
                amount=random.choice([500_000, 750_000, 1_000_000]),
            )

    def _create_scholarships(self, school, year, classrooms):
        """Bourses sociales : quelques élèves à 100 %, d'autres partiellement.

        Reflète une politique réaliste — une poignée de bourses totales, plus
        d'aides partielles — pour que la ligne « manque à gagner » du bilan porte
        des chiffres crédibles.
        """
        students = list(Student.objects.order_by("matricule"))
        grants = [
            (students[0::37], 100, Discount.Kind.FULL, "Orphelin — décision du conseil"),
            (students[5::29], 50, Discount.Kind.PERCENT, "Situation familiale difficile"),
            (students[11::41], 25, Discount.Kind.PERCENT, "Fratrie de trois enfants"),
        ]
        for cohort, rate, kind, reason in grants:
            for student in cohort[:6]:
                Discount.objects.create(
                    school=school,
                    student=student,
                    year=year,
                    kind=kind,
                    category=Discount.Category.SIBLING
                    if "Fratrie" in reason
                    else Discount.Category.SOCIAL,
                    scope=Discount.Scope.TUITION,
                    value=rate,
                    reason=reason,
                    approved_by="Conseil de l'établissement",
                    approved_at=year.start_date,
                )

    def _create_academics(self, school, year, classrooms, teachers):
        """Matières, coefficients, une composition trimestrielle et ses notes."""
        ReportCardSettings.objects.create(
            school=school,
            header_line_1="République du Sénégal",
            header_line_2="Ministère de l'Éducation nationale",
            header_line_3="Inspection de l'Éducation et de la Formation de Dakar",
            establishment_code="IEF-DK-0147",
            principal_name="Awa Diop",
            principal_title="La Directrice",
            footer_note="Bulletin à conserver. Toute réclamation doit être formulée "
            "dans les quinze jours suivant la remise.",
        )
        AttendanceSettings.objects.create(school=school)

        subjects = [
            Subject.objects.create(
                school=school, code=code, name=name,
                default_coefficient=coefficient, order=order,
            )
            for order, (code, name, coefficient) in enumerate(DEFAULT_SUBJECTS)
        ]

        # Seul l'élémentaire est noté : le préscolaire ne compose pas.
        primary = [c for c in classrooms if c.level == Level.PRIMARY]
        for classroom in primary:
            for order, subject in enumerate(subjects):
                ClassSubject.objects.create(
                    school=school,
                    classroom=classroom,
                    subject=subject,
                    year=year,
                    coefficient=subject.default_coefficient,
                    teacher=random.choice(teachers[:7]),
                    order=order,
                )

        composition = Composition.objects.create(
            school=school,
            year=year,
            name="1er trimestre",
            kind=Composition.Kind.TERM,
            term=1,
            date=datetime.date(year.start_date.year, 12, 15),
            status=Composition.Status.OPEN,
        )

        for class_subject in ClassSubject.objects.filter(year=year).select_related("classroom"):
            sheet = GradeSheet.objects.create(
                school=school,
                composition=composition,
                class_subject=class_subject,
                is_validated=True,
                validated_at=timezone.now(),
                validated_by="Enseignant",
            )
            students = Student.objects.filter(classroom=class_subject.classroom)
            Grade.objects.bulk_create([
                Grade(
                    school=school,
                    sheet=sheet,
                    student=student,
                    # Distribution centrée sur 12, bornée au barème : des notes
                    # uniformes rendraient le rang et les mentions insignifiants.
                    value=Decimal(str(min(20, max(0, round(random.gauss(12, 3.2) * 2) / 2)))),
                )
                for student in students
            ])

    def _create_attendance(self, school, year, classrooms):
        """Passages des dix derniers jours ouvrés."""
        today = datetime.date.today()
        days = []
        cursor = today
        while len(days) < 10:
            if cursor.weekday() < 5:  # du lundi au vendredi
                days.append(cursor)
            cursor -= datetime.timedelta(days=1)

        students = list(Student.objects.all())
        events = []
        for day in days:
            for student in students:
                if random.random() < 0.08:   # absences
                    continue
                arrival = timezone.make_aware(
                    datetime.datetime.combine(
                        day,
                        datetime.time(7, random.randint(30, 59))
                        if random.random() > 0.12
                        else datetime.time(8, random.randint(16, 45)),  # retards
                    )
                )
                departure = timezone.make_aware(
                    datetime.datetime.combine(day, datetime.time(17, random.randint(0, 30)))
                )
                events.append(AttendanceEvent(
                    school=school, student=student,
                    direction=AttendanceEvent.Direction.IN,
                    occurred_at=arrival, day=day,
                ))
                if random.random() > 0.05:  # quelques sorties non badgées
                    events.append(AttendanceEvent(
                        school=school, student=student,
                        direction=AttendanceEvent.Direction.OUT,
                        occurred_at=departure, day=day,
                    ))
        AttendanceEvent.objects.bulk_create(events, batch_size=1000)

    def _summary(self, school, year):
        from apps.reports.services import bilan

        with tenant_context(school):
            report = bilan(year)
            students = Student.objects.count()
            expenses = Expense.objects.count()

        def money(value):
            return f"{value:,}".replace(",", " ")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"  {school.name} — {year.label}"))
        self.stdout.write(f"  Élèves ............... {students}")
        self.stdout.write(f"  Dépenses ............. {expenses}")
        self.stdout.write(f"  Total ressources ..... {money(report['total_resources']['total'])} XOF")
        self.stdout.write(f"  Total charges ........ {money(report['total_charges']['total'])} XOF")
        self.stdout.write(f"  EBE .................. {money(report['ebe']['total'])} XOF")
        self.stdout.write(f"  Solde du compte ...... {money(report['current_balance'])} XOF")
        self.stdout.write("")
        self.stdout.write("  Comptes (mot de passe : MonEcole2026!)")
        self.stdout.write("    admin@darou-louqmane.sn ....... Administrateur")
        self.stdout.write("    comptable@darou-louqmane.sn ... Comptable")
        self.stdout.write("    secretaire@darou-louqmane.sn .. Secrétaire")
        self.stdout.write("    super@monecole.sn ............. Super administrateur")
        self.stdout.write("")
