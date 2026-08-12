"""Le catalogue des matières, et la fidélité du calcul aux bulletins réels.

Le test décisif de ce module est `test_a_real_report_card_is_reproduced` : il
rejoue un bulletin papier du Groupe Scolaire Keur Mame Nafissa et exige la
moyenne imprimée, au centième. Tant qu'il passe, le moteur de notes reproduit
ce que l'école produit à la main — c'est le critère d'acceptation du projet.
"""

from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient

from apps.academics.catalogue import (
    SUBJECT_CATALOGUE,
    all_subject_names,
    catalogue_for,
    subject_code,
)
from apps.academics.models import ClassSubject, Composition, Grade, GradeSheet, Subject
from apps.academics.services import student_results
from apps.core.models import Role
from apps.core.tenancy import tenant_context
from apps.core.tests.factories import (
    make_classroom,
    make_school,
    make_student,
    make_user,
    make_year,
)


class CatalogueTests(TestCase):
    def test_every_level_of_the_elementary_is_covered(self):
        self.assertEqual(
            set(SUBJECT_CATALOGUE), {"CI", "CP", "CE1", "CE2", "CM1", "CM2"}
        )

    def test_scales_are_plausible(self):
        """Un barème nul ou négatif ferait une division par zéro au bulletin."""
        for level, entries in SUBJECT_CATALOGUE.items():
            for name, scale in entries:
                self.assertGreater(scale, 0, f"{level} / {name}")
                self.assertLessEqual(scale, 60, f"{level} / {name}")

    def test_no_subject_appears_twice_in_a_level(self):
        """Deux lignes pour une matière, c'est un total faux au bulletin."""
        for level, entries in SUBJECT_CATALOGUE.items():
            names = [name for name, _ in entries]
            self.assertEqual(len(names), len(set(names)), level)

    def test_codes_are_unique_across_the_catalogue(self):
        """Le code est la clé d'unicité par établissement."""
        codes = [subject_code(name) for name in all_subject_names()]
        self.assertEqual(len(codes), len(set(codes)))

    def test_a_class_name_is_matched_to_its_level(self):
        self.assertEqual(catalogue_for("CE2B"), SUBJECT_CATALOGUE["CE2"])
        self.assertEqual(catalogue_for("CM2 A"), SUBJECT_CATALOGUE["CM2"])
        self.assertEqual(catalogue_for("ce1 a"), SUBJECT_CATALOGUE["CE1"])

    def test_ce1_is_not_mistaken_for_ce2(self):
        """Le rapprochement se fait sur le préfixe : l'ordre de test compte."""
        self.assertNotEqual(catalogue_for("CE1A"), catalogue_for("CE2A"))

    def test_an_unknown_level_returns_nothing_rather_than_a_guess(self):
        self.assertEqual(catalogue_for("Grande section"), [])
        self.assertEqual(catalogue_for("6e"), [])


class ApplyCatalogueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.year = make_year(cls.school)
        cls.ce2 = make_classroom(cls.school, "CE2B", order=4)
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")
        cls.teacher = make_user(cls.school, Role.TEACHER, "prof@test.sn")

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def apply(self, classroom=None):
        return self.client.post(
            "/api/class-subjects/apply-catalogue/",
            {"classroom": (classroom or self.ce2).id, "year": self.year.id},
            format="json",
        )

    def test_the_level_catalogue_is_applied_with_its_scales(self):
        response = self.apply()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["created"], len(SUBJECT_CATALOGUE["CE2"]))

        with tenant_context(self.school):
            links = ClassSubject.objects.filter(classroom=self.ce2, year=self.year)
            self.assertEqual(links.count(), len(SUBJECT_CATALOGUE["CE2"]))
            by_name = {link.subject.name: link.max_score for link in links}
            for name, scale in SUBJECT_CATALOGUE["CE2"]:
                self.assertEqual(by_name[name], scale, name)

    def test_applying_twice_creates_nothing_and_keeps_adjusted_scales(self):
        """Une école qui a corrigé un barème ne doit pas le voir écrasé."""
        self.apply()
        with tenant_context(self.school):
            link = ClassSubject.objects.filter(classroom=self.ce2).first()
            link.max_score = 3
            link.save()

        response = self.apply()
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(response.data["skipped"], len(SUBJECT_CATALOGUE["CE2"]))

        with tenant_context(self.school):
            link.refresh_from_db()
            self.assertEqual(link.max_score, 3)

    def test_an_unlisted_level_is_refused_with_guidance(self):
        preschool = make_classroom(self.school, "Grande section", order=1)
        response = self.apply(preschool)
        self.assertEqual(response.status_code, 400)
        self.assertIn("CI, CP, CE1", str(response.data))

    def test_a_teacher_cannot_configure_the_subjects(self):
        client = APIClient()
        client.force_authenticate(self.teacher)
        response = client.post(
            "/api/class-subjects/apply-catalogue/",
            {"classroom": self.ce2.id, "year": self.year.id},
            format="json",
        )
        self.assertEqual(response.status_code, 403)


class RealReportCardTests(TestCase):
    """Rejoue un bulletin papier et exige la moyenne imprimée.

    Source : AMINATA ELIE BADJI, CE2B, année 2025-2026, 3ᵉ composition.
    Total imprimé 182,00 sur 190,00 — moyenne 9,58.
    """

    BULLETIN = [
        ("Vivre ensemble", 6, 6),
        ("Activités de mesure", 10, 10),
        ("Compétence EDD", 8, 8),
        ("Compétence maths", 20, 20),
        ("Activités géométriques", 6.5, 10),
        ("Géographie", 4, 4),
        ("Activités numériques", 10, 10),
        ("Compétence DM", 6, 8),
        ("Vivre dans son milieu", 6, 6),
        ("Vocabulaire", 8, 8),
        ("Arts plastiques", 9.5, 10),
        ("Histoire", 4, 4),
        ("Arabe", 9, 10),
        ("Récitation / chant", 10, 10),
        ("Grammaire", 8, 8),
        ("Conjugaison", 12, 12),
        ("Résolution de problèmes", 10, 10),
        ("Orthographe", 3, 4),
        ("IST", 4, 4),
        ("Production d'écrits", 20, 20),
        ("TSQ", 8, 8),
    ]
    PRINTED_TOTAL = Decimal("182.00")
    PRINTED_SCALE = 190
    PRINTED_AVERAGE = Decimal("9.58")

    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.year = make_year(cls.school)
        cls.ce2 = make_classroom(cls.school, "CE2B", order=4)

        with tenant_context(cls.school):
            cls.composition = Composition.objects.create(
                school=cls.school, year=cls.year, name="3e composition",
                kind=Composition.Kind.TERM, term=3, date=cls.year.start_date,
                status=Composition.Status.OPEN,
            )
            cls.student = make_student(cls.school, cls.ce2, "Aminata", "Badji")

            for order, (name, value, scale) in enumerate(cls.BULLETIN):
                subject = Subject.objects.create(
                    school=cls.school, code=subject_code(name), name=name,
                    default_max_score=scale, order=order,
                )
                link = ClassSubject.objects.create(
                    school=cls.school, classroom=cls.ce2, subject=subject,
                    year=cls.year, max_score=scale, order=order,
                )
                sheet = GradeSheet.objects.create(
                    school=cls.school, composition=cls.composition,
                    class_subject=link, is_validated=True,
                )
                Grade.objects.create(
                    school=cls.school, sheet=sheet, student=cls.student,
                    value=Decimal(str(value)),
                )

    def test_a_real_report_card_is_reproduced(self):
        with tenant_context(self.school):
            results, _, _ = student_results(self.composition, self.ce2)

        result = results[self.student.id]
        self.assertEqual(result["total_points"], self.PRINTED_TOTAL)
        self.assertEqual(result["total_max_score"], self.PRINTED_SCALE)
        self.assertEqual(
            result["average"],
            self.PRINTED_AVERAGE,
            "La moyenne calculée s'écarte du bulletin papier de l'école.",
        )

    def test_the_mention_is_read_on_the_ten_point_scale(self):
        """9,58 sur 10 est un « Très bien », pas un « Insuffisant »."""
        with tenant_context(self.school):
            results, _, _ = student_results(self.composition, self.ce2)
        self.assertEqual(results[self.student.id]["mention"], "Très bien")


class SheetFilteringTests(TestCase):
    """Filtrage des feuilles de notes par composition et par classe.

    Un administrateur voit les feuilles de toutes les classes : sans filtre,
    la liste dépasse deux cents lignes pour une seule composition.
    """

    @classmethod
    def setUpTestData(cls):
        cls.school = make_school()
        cls.year = make_year(cls.school)
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")

        with tenant_context(cls.school):
            cls.composition = Composition.objects.create(
                school=cls.school, year=cls.year, name="1er trimestre",
                kind=Composition.Kind.TERM, term=1, date=cls.year.start_date,
                status=Composition.Status.OPEN,
            )
            cls.rooms = {}
            for order, name in enumerate(["CI-A", "CI-B", "CM1"]):
                room = make_classroom(cls.school, name, order=40 + order)
                cls.rooms[name] = room
                for index in range(3):
                    subject = Subject.objects.create(
                        school=cls.school, code=f"{name}{index}",
                        name=f"Matière {index}", default_max_score=10,
                    )
                    link = ClassSubject.objects.create(
                        school=cls.school, classroom=room, subject=subject,
                        year=cls.year, max_score=60 if name == "CM1" else 10,
                    )
                    GradeSheet.objects.create(
                        school=cls.school, composition=cls.composition,
                        class_subject=link, is_validated=(name == "CI-A"),
                    )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_without_a_class_every_sheet_is_returned(self):
        response = self.client.get(f"/api/grade-sheets/?composition={self.composition.id}")
        self.assertEqual(len(response.data["results"]), 9)

    def test_a_class_narrows_the_list_in_the_database(self):
        room = self.rooms["CM1"]
        response = self.client.get(
            f"/api/grade-sheets/?composition={self.composition.id}&classroom={room.id}"
        )
        self.assertEqual(len(response.data["results"]), 3)
        self.assertEqual(
            {row["classroom"] for row in response.data["results"]}, {"CM1"}
        )

    def test_the_class_list_reports_validation_progress(self):
        """Le sélecteur sert aussi à voir qui n'a pas fini de saisir."""
        response = self.client.get(
            f"/api/grade-sheets/classrooms/?composition={self.composition.id}"
        )
        self.assertEqual(response.status_code, 200)
        rooms = {row["name"]: row for row in response.data}
        self.assertEqual(rooms["CI-A"], {"id": self.rooms["CI-A"].id, "name": "CI-A",
                                         "sheets": 3, "validated": 3})
        self.assertEqual(rooms["CM1"]["validated"], 0)

    def test_only_classes_with_sheets_are_offered(self):
        """Proposer une classe sans feuille mène à un écran vide."""
        make_classroom(self.school, "CM2", order=90)
        response = self.client.get(
            f"/api/grade-sheets/classrooms/?composition={self.composition.id}"
        )
        self.assertNotIn("CM2", {row["name"] for row in response.data})

    def test_a_grade_may_reach_the_sheet_scale_not_twenty(self):
        """Les compétences maths du CM1 sont notées sur 60.

        Une borne fixée à 20 refusait la note sans rien expliquer.
        """
        with tenant_context(self.school):
            sheet = GradeSheet.objects.filter(
                class_subject__classroom=self.rooms["CM1"]
            ).first()
            student = make_student(self.school, self.rooms["CM1"], "Awa", "Diop")
            grade = Grade.objects.create(
                school=self.school, sheet=sheet, student=student
            )

        response = self.client.post(
            f"/api/grade-sheets/{sheet.id}/save/",
            {"rows": [{"grade": grade.pk, "value": "45"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)

        with tenant_context(self.school):
            grade.refresh_from_db()
            self.assertEqual(grade.value, Decimal("45.00"))

    def test_a_grade_above_the_sheet_scale_is_refused(self):
        with tenant_context(self.school):
            sheet = GradeSheet.objects.filter(
                class_subject__classroom=self.rooms["CI-A"]
            ).first()
            sheet.is_validated = False
            sheet.save()
            student = make_student(self.school, self.rooms["CI-A"], "Moussa", "Fall")
            grade = Grade.objects.create(
                school=self.school, sheet=sheet, student=student
            )

        response = self.client.post(
            f"/api/grade-sheets/{sheet.id}/save/",
            {"rows": [{"grade": grade.pk, "value": "45"}]},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.data)


class ClassTeacherTests(TestCase):
    """Le titulaire tient toutes les matières de sa classe.

    C'est le fonctionnement de l'élémentaire, et ce que montrent les bulletins
    de l'école pilote : une seule enseignante sur les dix-neuf matières du CM2.
    Attribuer un enseignant matière par matière imposerait vingt-neuf gestes
    par classe.
    """

    @classmethod
    def setUpTestData(cls):
        from apps.staff.models import Teacher

        cls.school = make_school()
        cls.year = make_year(cls.school)
        cls.admin = make_user(cls.school, Role.ADMIN, "admin@test.sn")
        cls.titulaire_user = make_user(cls.school, Role.TEACHER, "maitre@test.sn")
        cls.arabe_user = make_user(cls.school, Role.TEACHER, "arabe@test.sn")

        with tenant_context(cls.school):
            cls.titulaire = Teacher.objects.create(
                school=cls.school, first_name="Fatou", last_name="Ndione",
                email="maitre@test.sn",
            )
            cls.intervenant = Teacher.objects.create(
                school=cls.school, first_name="Cheikh", last_name="Sy",
                email="arabe@test.sn",
            )
            cls.room = make_classroom(cls.school, "CE2-A", order=70)
            cls.room.teacher = cls.titulaire
            cls.room.save()
            cls.autre = make_classroom(cls.school, "CM1-A", order=80)

            cls.composition = Composition.objects.create(
                school=cls.school, year=cls.year, name="1er contrôle",
                kind=Composition.Kind.TERM, term=1, date=cls.year.start_date,
                status=Composition.Status.OPEN,
            )

            cls.links = {}
            for name, room, intervenant in [
                ("Grammaire", cls.room, None),
                ("Arabe", cls.room, cls.intervenant),
                ("Histoire", cls.autre, None),
            ]:
                subject = Subject.objects.create(
                    school=cls.school, code=subject_code(name + room.name),
                    name=name, default_max_score=10,
                )
                link = ClassSubject.objects.create(
                    school=cls.school, classroom=room, subject=subject,
                    year=cls.year, max_score=10, teacher=intervenant,
                )
                cls.links[name] = link
                GradeSheet.objects.create(
                    school=cls.school, composition=cls.composition, class_subject=link
                )

    def sheets_for(self, user):
        client = APIClient()
        client.force_authenticate(user)
        response = client.get("/api/grade-sheets/")
        self.assertEqual(response.status_code, 200, response.data)
        return {row["subject"] for row in response.data["results"]}

    def test_the_class_teacher_sees_every_subject_of_the_class(self):
        """Sans intervenant désigné, la matière revient au titulaire."""
        self.assertIn("Grammaire", self.sheets_for(self.titulaire_user))

    def test_a_subject_with_its_own_teacher_leaves_the_titular(self):
        """L'arabe est confié à un intervenant : il sort du lot du titulaire."""
        self.assertNotIn("Arabe", self.sheets_for(self.titulaire_user))
        self.assertEqual(self.sheets_for(self.arabe_user), {"Arabe"})

    def test_a_teacher_sees_nothing_of_another_class(self):
        self.assertNotIn("Histoire", self.sheets_for(self.titulaire_user))

    def test_the_bulletin_names_the_titular_on_every_line(self):
        """Les bulletins portent le nom de l'enseignant sur chaque ligne.

        Sans la cascade, la colonne resterait vide dès qu'une matière n'a pas
        d'intervenant propre — c'est-à-dire presque toujours.
        """
        with tenant_context(self.school):
            make_student(self.school, self.room, "Awa", "Diop")
            _results, subjects, _students = student_results(self.composition, self.room)
            noms = {
                link.effective_teacher.full_name if link.effective_teacher else None
                for link in subjects
            }
        self.assertEqual(noms, {"Fatou Ndione", "Cheikh Sy"})

    def test_a_class_without_a_titular_names_nobody_rather_than_guessing(self):
        with tenant_context(self.school):
            link = self.links["Histoire"]
            self.assertIsNone(link.effective_teacher)
