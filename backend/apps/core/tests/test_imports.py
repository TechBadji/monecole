"""Import CSV de migration.

Un import est l'opération la plus destructrice offerte à un utilisateur non
technique : elle écrit en masse, à partir d'un fichier qu'il a lui-même bricolé.
D'où l'insistance des tests sur le pré-contrôle et sur l'atomicité.
"""

import io

from django.test import TestCase
from rest_framework.test import APIClient

from apps.core.imports import normalize_header, parse_amount, parse_date, read_rows
from apps.core.models import Role
from apps.core.tenancy import tenant_context
from apps.finance.models import Expense
from apps.staff.models import Teacher
from apps.students.models import Family, Student

from .factories import (
    make_category,
    make_classroom,
    make_school,
    make_user,
    make_year,
)


class ParsingTests(TestCase):
    """Les fichiers réels sortent d'Excel, pas d'un exporteur propre."""

    def test_headers_are_normalized(self):
        for raw, expected in [
            ("Prénom", "prenom"),
            ("  Date de Naissance  ", "date_de_naissance"),
            ("N° de facture", "n_de_facture"),
            ("TÉLÉPHONE", "telephone"),
            ("Montant (FCFA)", "montant_fcfa"),
        ]:
            self.assertEqual(normalize_header(raw), expected)

    def test_french_and_iso_dates_are_accepted(self):
        import datetime

        expected = datetime.date(2025, 10, 15)
        for raw in ("15/10/2025", "2025-10-15", "15-10-2025", "15.10.2025"):
            self.assertEqual(parse_date(raw), expected)

    def test_unreadable_date_is_reported(self):
        with self.assertRaises(ValueError):
            parse_date("le 15 octobre")

    def test_amounts_survive_excel_formatting(self):
        for raw, expected in [
            ("15000", 15_000),
            ("15 000", 15_000),
            ("15.000", 15_000),
            ("15 000,00", 15_000),
            ("15 000 FCFA", 15_000),
            ("1.250.000", 1_250_000),
            ("450000", 450_000),
            ("", 0),
        ]:
            self.assertEqual(parse_amount(raw), expected, f"« {raw} » mal interprété")

    def test_semicolon_and_comma_separators_are_detected(self):
        for content in (
            "prenom;nom;classe\nAwa;Diop;CP\n",
            "prenom,nom,classe\nAwa,Diop,CP\n",
        ):
            _, rows = read_rows(content.encode())
            self.assertEqual(rows[0]["prenom"], "Awa")

    def test_windows_1252_encoding_is_accepted(self):
        """Excel sous Windows produit du CP1252, pas de l'UTF-8."""
        content = "prenom;nom;classe\nAïssatou;Sène;CP\n".encode("cp1252")
        _, rows = read_rows(content)
        self.assertEqual(rows[0]["prenom"], "Aïssatou")

    def test_utf8_bom_is_stripped(self):
        content = "prenom;nom;classe\nAwa;Diop;CP\n".encode("utf-8-sig")
        _, rows = read_rows(content)
        self.assertIn("prenom", rows[0])


class ImportEndpointTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.year = make_year(cls.school)
        cls.cp = make_classroom(cls.school, "CP", order=5)
        cls.ce1 = make_classroom(cls.school, "CE1", order=6)
        cls.category = make_category(cls.school, "RENT", "LOCATIONS DE BÂTIMENTS")
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")
        cls.accountant = make_user(cls.school, Role.ACCOUNTANT, "compta@test.sn")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def upload(self, kind, content, dry_run=True, user=None):
        client = self.client
        if user:
            client = APIClient()
            client.force_authenticate(user)
        return client.post(
            "/api/imports/",
            {
                "kind": kind,
                "file": io.BytesIO(content.encode()),
                "dry_run": "true" if dry_run else "false",
            },
            format="multipart",
        )

    # --- Élèves ---------------------------------------------------------

    STUDENTS = (
        "prenom;nom;classe;date de naissance;sexe;parent;telephone\n"
        "Awa;Diop;CP;12/05/2018;F;Fatou Diop;77 123 45 67\n"
        "Moussa;Fall;CE1;03/09/2017;M;Ibrahima Fall;+221 70 555 44 33\n"
    )

    def test_dry_run_writes_nothing(self):
        response = self.upload("students", self.STUDENTS)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ok"])
        self.assertEqual(response.data["created"], 2)
        self.assertFalse(response.data["applied"])

        with tenant_context(self.school):
            self.assertEqual(Student.objects.count(), 0)

    def test_applying_creates_students_and_families(self):
        response = self.upload("students", self.STUDENTS, dry_run=False)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["applied"])

        with tenant_context(self.school):
            self.assertEqual(Student.objects.count(), 2)
            self.assertEqual(Family.objects.count(), 2)
            awa = Student.objects.get(first_name="Awa")
            self.assertEqual(awa.classroom, self.cp)
            self.assertEqual(awa.sex, "F")
            # Le téléphone normalisé doit être posé : sans lui, pas de portail parent.
            self.assertEqual(awa.parent_phone_e164, "221771234567")

    def test_unknown_class_blocks_with_a_usable_message(self):
        content = "prenom;nom;classe\nAwa;Diop;TERMINALE\n"
        response = self.upload("students", content)
        self.assertFalse(response.data["ok"])
        message = response.data["errors"][0]["message"]
        self.assertIn("TERMINALE", message)
        # Le message doit lister les classes valides, sinon l'utilisateur devine.
        self.assertIn("CP", message)

    def test_error_line_numbers_match_the_spreadsheet(self):
        """L'utilisateur corrige dans Excel : le numéro doit être celui qu'il y voit."""
        content = (
            "prenom;nom;classe\n"
            "Awa;Diop;CP\n"        # ligne 2
            "Moussa;Fall;INEXISTANTE\n"  # ligne 3
        )
        response = self.upload("students", content)
        self.assertEqual(response.data["errors"][0]["line"], 3)

    def test_missing_required_column_is_reported_before_anything_else(self):
        response = self.upload("students", "prenom;nom\nAwa;Diop\n")
        self.assertFalse(response.data["ok"])
        self.assertIn("classe", response.data["errors"][0]["message"])

    def test_nothing_is_written_when_one_line_fails(self):
        """Tout ou rien : un import à moitié passé est ingérable."""
        content = (
            "prenom;nom;classe\n"
            "Awa;Diop;CP\n"
            "Moussa;Fall;INEXISTANTE\n"
        )
        response = self.upload("students", content, dry_run=False)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["applied"])
        with tenant_context(self.school):
            self.assertEqual(Student.objects.count(), 0)

    def test_existing_student_is_updated_with_a_warning(self):
        self.upload("students", self.STUDENTS, dry_run=False)
        updated = (
            "prenom;nom;classe;telephone\n"
            "Awa;Diop;CE1;77 999 88 77\n"
        )
        response = self.upload("students", updated, dry_run=False)
        self.assertEqual(response.data["updated"], 1)
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(response.data["warning_count"], 1)

        with tenant_context(self.school):
            # Les deux élèves du premier import subsistent ; seul Awa change de classe.
            self.assertEqual(Student.objects.count(), 2)
            awa = Student.objects.get(first_name="Awa")
            self.assertEqual(awa.classroom, self.ce1)
            self.assertEqual(awa.parent_phone_e164, "221779998877")

    # --- Enseignants ----------------------------------------------------

    def test_teachers_receive_generated_matricules(self):
        content = (
            "prenom;nom;sexe;fonction\n"
            "Ousmane;Bodian;M;Instituteur\n"
            "Fatou;Ndiaye;F;Institutrice\n"
        )
        response = self.upload("teachers", content, dry_run=False)
        self.assertEqual(response.data["created"], 2)
        with tenant_context(self.school):
            self.assertEqual(
                sorted(Teacher.objects.values_list("matricule", flat=True)),
                ["001", "002"],
            )

    # --- Dépenses -------------------------------------------------------

    def test_expenses_are_imported_by_category_label(self):
        content = (
            "date;intitule;montant;rubrique\n"
            "15/11/2025;Loyer novembre;450 000;LOCATIONS DE BÂTIMENTS\n"
        )
        response = self.upload("expenses", content, dry_run=False)
        self.assertEqual(response.data["created"], 1)
        with tenant_context(self.school):
            expense = Expense.objects.get()
            self.assertEqual(expense.amount, 450_000)
            # La période est dérivée de la date d'opération.
            self.assertEqual(expense.period.month, 11)

    def test_expense_outside_the_fiscal_year_is_refused(self):
        content = (
            "date;intitule;montant;rubrique\n"
            "15/11/2030;Loyer;450 000;LOCATIONS DE BÂTIMENTS\n"
        )
        response = self.upload("expenses", content)
        self.assertFalse(response.data["ok"])
        self.assertIn("hors de l'exercice", response.data["errors"][0]["message"])

    def test_unknown_category_is_refused(self):
        content = "date;intitule;montant;rubrique\n15/11/2025;X;1000;INCONNUE\n"
        response = self.upload("expenses", content)
        self.assertFalse(response.data["ok"])

    # --- Garde-fous -----------------------------------------------------

    def test_unknown_kind_is_rejected(self):
        self.assertEqual(self.upload("licornes", "a;b\n1;2\n").status_code, 400)

    def test_accountant_cannot_import(self):
        """L'import est réservé à l'administration et au secrétariat."""
        response = self.upload("students", self.STUDENTS, user=self.accountant)
        self.assertEqual(response.status_code, 403)

    def test_dry_run_defaults_to_true_when_unspecified(self):
        """Un paramètre oublié ne doit jamais déclencher une écriture."""
        response = self.client.post(
            "/api/imports/",
            {"kind": "students", "file": io.BytesIO(self.STUDENTS.encode())},
            format="multipart",
        )
        self.assertFalse(response.data["applied"])
        with tenant_context(self.school):
            self.assertEqual(Student.objects.count(), 0)

    def test_typo_in_dry_run_does_not_apply(self):
        response = self.client.post(
            "/api/imports/",
            {
                "kind": "students",
                "file": io.BytesIO(self.STUDENTS.encode()),
                "dry_run": "faux",  # ni "false" ni "0"
            },
            format="multipart",
        )
        self.assertFalse(response.data["applied"])

    def test_import_formats_are_documented(self):
        response = self.client.get("/api/imports/")
        self.assertEqual(response.status_code, 200)
        kinds = {entry["kind"] for entry in response.data["kinds"]}
        self.assertEqual(kinds, {"students", "teachers", "expenses"})
