"""Import CSV pour la migration des données existantes.

Deux principes gouvernent ce module :

1. **Pré-contrôle systématique.** Tout import s'exécute d'abord en `dry_run`, qui
   valide chaque ligne et retourne un rapport sans rien écrire. Importer 400 élèves
   puis découvrir que la colonne « classe » ne correspond à rien laisserait la base
   dans un état pire que le point de départ.
2. **Tout ou rien.** L'écriture se fait dans une transaction : si une ligne échoue,
   rien n'est appliqué. Un import à moitié passé est le pire des cas — on ne sait
   plus ce qui a été repris et ce qui reste à reprendre.

Les fichiers issus d'Excel sont souvent en Windows-1252 avec des points-virgules :
l'encodage et le séparateur sont détectés plutôt qu'imposés.
"""

import csv
import datetime
import io
import re

from django.db import transaction

from apps.core.periods import end_of_month
from apps.finance.models import Expense, ExpenseCategory
from apps.staff.models import Teacher
from apps.students.models import ClassRoom, Family, Level, Student, StudentStatus

# Encodages essayés dans l'ordre. Windows-1252 avant latin-1 : il couvre les
# apostrophes et guillemets typographiques qu'Excel produit sous Windows.
ENCODINGS = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]


class ImportError_(Exception):
    """Erreur bloquante empêchant même la lecture du fichier."""


def decode(raw: bytes) -> str:
    for encoding in ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ImportError_(
        "Encodage du fichier non reconnu. Enregistrez-le en UTF-8 depuis Excel "
        "(Fichier ▸ Enregistrer sous ▸ CSV UTF-8)."
    )


def read_rows(raw: bytes):
    """Retourne (en-têtes normalisés, lignes) à partir d'un CSV."""
    text = decode(raw)
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        # Le point-virgule est le défaut d'Excel en locale française.
        dialect = csv.excel
        dialect.delimiter = ";" if sample.count(";") > sample.count(",") else ","

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ImportError_("Fichier vide ou sans ligne d'en-tête.")

    headers = [normalize_header(name) for name in reader.fieldnames]
    rows = []
    for raw_row in reader:
        rows.append(
            {normalize_header(k): (v or "").strip() for k, v in raw_row.items() if k}
        )
    return headers, rows


def normalize_header(name: str) -> str:
    """« Date de naissance » → « date_de_naissance ».

    Tolère accents, majuscules et espaces multiples : la ligne d'en-tête d'un
    fichier réel n'est jamais propre.
    """
    import unicodedata

    text = unicodedata.normalize("NFKD", (name or "").strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def parse_date(value):
    if not value:
        return None
    value = value.strip()
    for pattern in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y"):
        try:
            return datetime.datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    raise ValueError(f"date « {value} » illisible (attendu JJ/MM/AAAA)")


def parse_amount(value):
    """« 15 000 », « 15.000 », « 15000,00 », « 15 000 FCFA » → 15000.

    Le franc CFA n'a pas de subdivision décimale. Cela lève l'ambiguïté du point :
    dans « 15.000 », il ne peut pas séparer une partie décimale — c'est un
    séparateur de milliers, et l'utilisateur veut quinze mille. On ne traite le
    point comme décimal que s'il n'est pas suivi d'exactement trois chiffres.
    """
    if not value:
        return 0

    cleaned = re.sub(r"[^\d,.-]", "", str(value))
    if not cleaned or cleaned in ("-", ".", ","):
        raise ValueError(f"montant « {value} » illisible")

    if "," in cleaned:
        # Locale française : la virgule est le séparateur décimal, le point les
        # milliers.
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif re.search(r"\.\d{3}(?:\.\d{3})*$", cleaned):
        # Un ou plusieurs groupes de trois chiffres : séparateur de milliers.
        cleaned = cleaned.replace(".", "")

    try:
        return int(round(float(cleaned)))
    except ValueError:
        raise ValueError(f"montant « {value} » illisible")


def parse_sex(value):
    if not value:
        return ""
    initial = value.strip().upper()[0]
    if initial in ("M", "H"):
        return "M"
    if initial == "F":
        return "F"
    return ""


class Report:
    """Rapport d'import, ligne à ligne."""

    def __init__(self, kind, dry_run):
        self.kind = kind
        self.dry_run = dry_run
        self.created = 0
        self.updated = 0
        self.errors = []
        self.warnings = []

    def error(self, line, message):
        # +2 : l'en-tête occupe la ligne 1, et l'utilisateur compte à partir de 1.
        self.errors.append({"line": line + 2, "message": message})

    def warn(self, line, message):
        self.warnings.append({"line": line + 2, "message": message})

    def as_dict(self):
        return {
            "kind": self.kind,
            "dry_run": self.dry_run,
            "created": self.created,
            "updated": self.updated,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            # Bornés : un fichier entièrement erroné produirait des milliers de
            # lignes que personne ne lira.
            "errors": self.errors[:100],
            "warnings": self.warnings[:100],
            "ok": not self.errors,
        }


# --------------------------------------------------------------------------- #
# Élèves                                                                       #
# --------------------------------------------------------------------------- #

STUDENT_COLUMNS = {
    "required": ["prenom", "nom", "classe"],
    "optional": [
        "date_de_naissance", "sexe", "parent", "telephone", "email",
        "adresse", "famille", "statut",
    ],
}


def import_students(school, year, rows, *, dry_run=True):
    report = Report("students", dry_run)
    if not rows:
        report.errors.append({"line": 0, "message": "Aucune ligne à importer."})
        return report, []

    missing = [c for c in STUDENT_COLUMNS["required"] if c not in rows[0]]
    if missing:
        report.errors.append(
            {
                "line": 1,
                "message": f"Colonnes obligatoires absentes : {', '.join(missing)}. "
                f"Attendu : {', '.join(STUDENT_COLUMNS['required'])}.",
            }
        )
        return report, []

    classrooms = {c.name.upper(): c for c in ClassRoom.objects.all()}
    existing = {
        (s.first_name.lower(), s.last_name.lower()): s
        for s in Student.objects.all()
    }
    families = {f.name.lower(): f for f in Family.objects.all()}

    prepared = []
    for index, row in enumerate(rows):
        first_name = row.get("prenom", "").strip()
        last_name = row.get("nom", "").strip()
        class_name = row.get("classe", "").strip().upper()

        if not first_name or not last_name:
            report.error(index, "Prénom et nom sont obligatoires.")
            continue

        classroom = classrooms.get(class_name)
        if classroom is None:
            report.error(
                index,
                f"Classe « {row.get('classe')} » inconnue. "
                f"Classes disponibles : {', '.join(sorted(classrooms))}.",
            )
            continue

        try:
            birth_date = parse_date(row.get("date_de_naissance"))
        except ValueError as error:
            report.error(index, str(error))
            continue

        key = (first_name.lower(), last_name.lower())
        if key in existing:
            report.warn(
                index,
                f"« {first_name} {last_name} » existe déjà — la fiche sera mise à jour.",
            )

        prepared.append(
            {
                "index": index,
                "key": key,
                "first_name": first_name,
                "last_name": last_name,
                "classroom": classroom,
                "date_of_birth": birth_date,
                "sex": parse_sex(row.get("sexe")),
                "parent_name": row.get("parent", ""),
                "parent_phone": row.get("telephone", ""),
                "parent_email": row.get("email", ""),
                "address": row.get("adresse", ""),
                "family_name": row.get("famille", "").strip() or last_name,
            }
        )

    if report.errors or dry_run:
        report.created = sum(1 for p in prepared if p["key"] not in existing)
        report.updated = sum(1 for p in prepared if p["key"] in existing)
        return report, prepared

    with transaction.atomic():
        for item in prepared:
            family = families.get(item["family_name"].lower())
            if family is None:
                family = Family.objects.create(
                    school=school,
                    name=item["family_name"],
                    primary_contact=item["parent_name"] or item["family_name"],
                    phone=item["parent_phone"],
                    email=item["parent_email"],
                )
                families[item["family_name"].lower()] = family

            student = existing.get(item["key"])
            fields = {
                "classroom": item["classroom"],
                "date_of_birth": item["date_of_birth"],
                "sex": item["sex"],
                "parent_name": item["parent_name"],
                "parent_phone": item["parent_phone"],
                "parent_email": item["parent_email"],
                "address": item["address"],
                "family": family,
            }
            if student:
                for key, value in fields.items():
                    setattr(student, key, value)
                student.save()
                report.updated += 1
            else:
                Student.objects.create(
                    school=school,
                    first_name=item["first_name"],
                    last_name=item["last_name"],
                    status=StudentStatus.ACTIVE,
                    **fields,
                )
                report.created += 1

    return report, prepared


# --------------------------------------------------------------------------- #
# Enseignants                                                                  #
# --------------------------------------------------------------------------- #


def import_teachers(school, year, rows, *, dry_run=True):
    report = Report("teachers", dry_run)
    if not rows:
        report.errors.append({"line": 0, "message": "Aucune ligne à importer."})
        return report, []

    if "nom" not in rows[0] or "prenom" not in rows[0]:
        report.errors.append(
            {"line": 1, "message": "Colonnes obligatoires : prenom, nom."}
        )
        return report, []

    prepared = []
    for index, row in enumerate(rows):
        if not row.get("prenom") or not row.get("nom"):
            report.error(index, "Prénom et nom sont obligatoires.")
            continue
        try:
            prepared.append(
                {
                    "first_name": row["prenom"],
                    "last_name": row["nom"],
                    "sex": parse_sex(row.get("sexe")),
                    "date_of_birth": parse_date(row.get("date_de_naissance")),
                    "cni": row.get("cni", ""),
                    "corps": row.get("corps", ""),
                    "grade": row.get("grade", ""),
                    "academic_diploma": row.get("diplome_academique", ""),
                    "professional_diploma": row.get("diplome_professionnel", ""),
                    "entry_date": parse_date(row.get("date_d_entree")),
                    "specialty": row.get("specialite", ""),
                    "function": row.get("fonction", ""),
                    "service_start_date": parse_date(row.get("prise_de_service")),
                    "courses_taught": row.get("cours_tenus", ""),
                    "class_type": row.get("type_classe", ""),
                }
            )
        except ValueError as error:
            report.error(index, str(error))

    if report.errors or dry_run:
        report.created = len(prepared)
        return report, prepared

    with transaction.atomic():
        for item in prepared:
            # Le matricule est attribué par le modèle, jamais repris du fichier :
            # deux sources de numérotation finiraient par diverger.
            Teacher.objects.create(school=school, **item)
            report.created += 1

    return report, prepared


# --------------------------------------------------------------------------- #
# Dépenses                                                                     #
# --------------------------------------------------------------------------- #


def import_expenses(school, year, rows, *, dry_run=True):
    report = Report("expenses", dry_run)
    if not rows:
        report.errors.append({"line": 0, "message": "Aucune ligne à importer."})
        return report, []

    required = ["date", "intitule", "montant", "rubrique"]
    missing = [c for c in required if c not in rows[0]]
    if missing:
        report.errors.append(
            {"line": 1, "message": f"Colonnes obligatoires absentes : {', '.join(missing)}."}
        )
        return report, []

    categories = {}
    for category in ExpenseCategory.objects.all():
        categories[category.label.upper()] = category
        categories[category.code.upper()] = category

    prepared = []
    for index, row in enumerate(rows):
        try:
            operation_date = parse_date(row.get("date"))
            amount = parse_amount(row.get("montant"))
        except ValueError as error:
            report.error(index, str(error))
            continue

        if operation_date is None:
            report.error(index, "Date d'opération manquante.")
            continue
        if not (year.start_date <= operation_date <= year.end_date):
            report.error(
                index,
                f"Date {operation_date:%d/%m/%Y} hors de l'exercice {year.label} "
                f"({year.start_date:%d/%m/%Y} — {year.end_date:%d/%m/%Y}).",
            )
            continue

        category = categories.get(row.get("rubrique", "").strip().upper())
        if category is None:
            report.error(index, f"Rubrique « {row.get('rubrique')} » inconnue.")
            continue

        prepared.append(
            {
                "operation_date": operation_date,
                "payment_date": parse_date(row.get("date_de_paiement")) or None,
                "label": row.get("intitule", ""),
                "amount": amount,
                "transfer_fee": parse_amount(row.get("frais_de_transfert")),
                "category": category,
                "invoice_number": row.get("numero_de_facture", ""),
            }
        )

    if report.errors or dry_run:
        report.created = len(prepared)
        return report, prepared

    with transaction.atomic():
        for item in prepared:
            Expense.objects.create(
                school=school, year=year, status=Expense.Status.APPROVED, **item
            )
            report.created += 1

    return report, prepared


IMPORTERS = {
    "students": (import_students, STUDENT_COLUMNS),
    "teachers": (import_teachers, {"required": ["prenom", "nom"], "optional": []}),
    "expenses": (
        import_expenses,
        {"required": ["date", "intitule", "montant", "rubrique"],
         "optional": ["date_de_paiement", "frais_de_transfert", "numero_de_facture"]},
    ),
}
