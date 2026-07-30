"""Calcul des états financiers : synthèse des encaissements et rapport bilan.

Ces états sont **toujours calculés à la volée** à partir des écritures, jamais
stockés. Un total mémorisé finit par diverger de ses données sources dès la
première correction rétroactive ; le cahier des charges l'exige d'ailleurs
explicitement pour les soldes de l'onglet ENCAIS.

Les quatre bugs du classeur source (voir `docs/modele-excel.md`) sont corrigés par
construction. Les écarts correspondants sont attendus et testés :

- **B1** chaque classe n'agrège que ses propres élèves — la jointure ne peut pas
  pointer vers une autre classe comme le faisait `ENCAIS!F21:M21` ;
- **B2** les totaux portent sur l'intégralité des élèves, sans plage de lignes ;
- **B3** le total annuel couvre les 12 mois de l'exercice, septembre compris ;
- **B4** l'effectif compte les élèves actifs, indépendamment du règlement de
  l'inscription, qui est restitué séparément.
"""

from dataclasses import dataclass, field

from django.db.models import Count, Q, Sum

from apps.core.periods import label as period_label
from apps.finance.models import (
    TRANSFER_FEES_CODE,
    TRANSFER_FEES_LABEL,
    Expense,
    ExpenseCategory,
    OtherIncome,
)
from apps.students.models import (
    ClassRoom,
    Enrollment,
    MonthlyPayment,
    Student,
    StudentStatus,
)


def _zeros(periods):
    return {p: 0 for p in periods}


@dataclass
class SeriesRow:
    """Une ligne d'état : un libellé et une valeur par période."""

    key: str
    label: str
    values: dict = field(default_factory=dict)

    @property
    def total(self):
        # Somme sur toutes les périodes de l'exercice — septembre inclus (B3).
        return sum(self.values.values())

    def as_dict(self, periods):
        return {
            "key": self.key,
            "label": self.label,
            "values": [self.values.get(p, 0) for p in periods],
            "total": self.total,
        }


# --------------------------------------------------------------------------- #
# ENCAIS — synthèse des encaissements                                          #
# --------------------------------------------------------------------------- #


def encaissements(year):
    """Synthèse des encaissements pour une année scolaire.

    Reproduit l'onglet ENCAIS : inscriptions et mensualités par classe et par mois,
    effectifs, et chiffre d'affaires par classe.
    """
    periods = year.fiscal_months
    classrooms = list(ClassRoom.objects.order_by("order", "name"))

    # --- Effectifs ---------------------------------------------------------
    # B4 : l'effectif est le nombre d'élèves actifs de la classe. Le nombre
    # d'inscriptions réglées est une information distincte, restituée à part.
    headcount = {
        row["classroom"]: row["n"]
        for row in Student.objects.filter(status=StudentStatus.ACTIVE)
        .values("classroom")
        .annotate(n=Count("id"))
    }
    paid_registrations = {
        row["classroom"]: row["n"]
        for row in Enrollment.objects.filter(year=year, registration_paid=True)
        .values("classroom")
        .annotate(n=Count("id"))
    }

    # --- Inscriptions ------------------------------------------------------
    # Rattachées au mois de règlement ; à défaut, au premier mois de l'exercice —
    # une inscription encaissée sans date reste ainsi visible dans le bilan plutôt
    # que de disparaître silencieusement.
    registration_rows = {c.id: SeriesRow(f"reg_{c.id}", c.name, _zeros(periods)) for c in classrooms}
    for enr in Enrollment.objects.filter(year=year).select_related("classroom"):
        row = registration_rows.get(enr.classroom_id)
        if row is None:
            continue
        bucket = _bucket_for(enr.paid_at, periods)
        row.values[bucket] += enr.registration_amount

    # --- Mensualités -------------------------------------------------------
    tuition_rows = {c.id: SeriesRow(f"tui_{c.id}", c.name, _zeros(periods)) for c in classrooms}
    aggregated = (
        MonthlyPayment.objects.filter(year=year)
        .values("student__classroom", "period")
        .annotate(
            tuition=Sum("tuition"),
            canteen=Sum("canteen"),
            reinforcement=Sum("reinforcement"),
            uniform=Sum("uniform"),
        )
    )
    ancillary = {  # cantine / renforcement / uniforme : suivis mais hors chiffre d'affaires
        "canteen": _zeros(periods),
        "reinforcement": _zeros(periods),
        "uniform": _zeros(periods),
    }
    for entry in aggregated:
        row = tuition_rows.get(entry["student__classroom"])
        period = entry["period"]
        if row is not None and period in row.values:
            row.values[period] += entry["tuition"] or 0
        if period in ancillary["canteen"]:
            for key in ancillary:
                ancillary[key][period] += entry[key] or 0

    # --- Totaux ------------------------------------------------------------
    registration_total = SeriesRow("registration_total", "Total inscription reçue", _zeros(periods))
    tuition_total = SeriesRow("tuition_total", "Total mensualité reçue", _zeros(periods))
    for period in periods:
        registration_total.values[period] = sum(r.values[period] for r in registration_rows.values())
        tuition_total.values[period] = sum(r.values[period] for r in tuition_rows.values())

    per_class = []
    for classroom in classrooms:
        reg = registration_rows[classroom.id]
        tui = tuition_rows[classroom.id]
        per_class.append(
            {
                "classroom_id": classroom.id,
                "classroom": classroom.name,
                "headcount": headcount.get(classroom.id, 0),
                "paid_registrations": paid_registrations.get(classroom.id, 0),
                "registration": reg.as_dict(periods),
                "tuition": tui.as_dict(periods),
                # Chiffre d'affaires par classe — colonne `ENCAIS!R`.
                "revenue": reg.total + tui.total,
            }
        )

    return {
        "year": year.label,
        "periods": [{"date": p, "label": period_label(p)} for p in periods],
        "classes": per_class,
        "registration_total": registration_total.as_dict(periods),
        "tuition_total": tuition_total.as_dict(periods),
        "headcount_total": sum(headcount.get(c.id, 0) for c in classrooms),
        "revenue_total": registration_total.total + tuition_total.total,
        "ancillary": {
            key: {"values": [values[p] for p in periods], "total": sum(values.values())}
            for key, values in ancillary.items()
        },
    }


def _bucket_for(date, periods):
    """Période d'imputation d'une date, bornée à l'exercice.

    Une date antérieure à l'exercice est imputée au premier mois, une date
    postérieure au dernier : aucun encaissement ne doit être perdu, même saisi hors
    bornes.
    """
    if date is None:
        return periods[0]
    from apps.core.periods import end_of_month

    target = end_of_month(date)
    if target in periods:
        return target
    return periods[0] if target < periods[0] else periods[-1]


# --------------------------------------------------------------------------- #
# Rapport Bilan                                                                #
# --------------------------------------------------------------------------- #


def bilan(year):
    """Rapport bilan annuel.

        TOTAL RESSOURCE = inscriptions + mensualités + autres produits
        TOTAL CHARGE    = Σ rubriques + frais bancaires et de transfert
        EBE             = ressources − charges
        SOLDE CUMULE    = cumul mensuel de l'EBE
    """
    periods = year.fiscal_months
    encais = encaissements(year)

    # --- Ressources --------------------------------------------------------
    registration = SeriesRow(
        "registration", "TOTAL INSCRIPTION REÇUE",
        dict(zip(periods, encais["registration_total"]["values"])),
    )
    tuition = SeriesRow(
        "tuition", "TOTAL MENSUALITÉ REÇUE",
        dict(zip(periods, encais["tuition_total"]["values"])),
    )

    other = SeriesRow("other_income", "AUTRE PRODUIT", _zeros(periods))
    for entry in (
        OtherIncome.objects.filter(year=year).values("period").annotate(total=Sum("amount"))
    ):
        if entry["period"] in other.values:
            other.values[entry["period"]] = entry["total"] or 0

    resources = [registration, tuition, other]
    total_resources = SeriesRow("total_resources", "TOTAL RESSOURCE", _zeros(periods))
    for period in periods:
        total_resources.values[period] = sum(r.values[period] for r in resources)

    # --- Charges -----------------------------------------------------------
    # Seules les dépenses validées entrent au bilan : un brouillon ou une dépense en
    # attente d'approbation ne doit pas déjà peser sur le résultat.
    approved = Expense.objects.filter(year=year, status=Expense.Status.APPROVED)

    categories = list(ExpenseCategory.objects.order_by("order", "label"))
    charge_rows = {c.id: SeriesRow(c.code, c.label, _zeros(periods)) for c in categories}
    for entry in approved.values("category", "period").annotate(total=Sum("amount")):
        row = charge_rows.get(entry["category"])
        if row is not None and entry["period"] in row.values:
            row.values[entry["period"]] = entry["total"] or 0

    # Ligne 32 du bilan : somme des frais de transfert de *toutes* les dépenses du
    # mois, toutes rubriques confondues. Agrégat transversal, pas une rubrique.
    transfer_fees = SeriesRow(TRANSFER_FEES_CODE, TRANSFER_FEES_LABEL, _zeros(periods))
    for entry in approved.values("period").annotate(total=Sum("transfer_fee")):
        if entry["period"] in transfer_fees.values:
            transfer_fees.values[entry["period"]] = entry["total"] or 0

    charges = list(charge_rows.values()) + [transfer_fees]
    total_charges = SeriesRow("total_charges", "TOTAL CHARGE", _zeros(periods))
    for period in periods:
        total_charges.values[period] = sum(c.values[period] for c in charges)

    # --- Résultat ----------------------------------------------------------
    ebe = SeriesRow("ebe", "EXCÉDENT BRUT D'EXPLOITATION (EBE)", _zeros(periods))
    cumulative = SeriesRow("cumulative_balance", "SOLDE CUMULE", _zeros(periods))
    running = 0
    for period in periods:
        ebe.values[period] = total_resources.values[period] - total_charges.values[period]
        running += ebe.values[period]
        cumulative.values[period] = running

    # `cumulative.total` n'aurait pas de sens : c'est un cumul, pas un flux. Le solde
    # final est la dernière valeur de la série.
    current_balance = cumulative.values[periods[-1]]

    # --- Poids relatif des rubriques --------------------------------------
    def weight(row, base):
        return round(row.total / base, 4) if base else None

    return {
        "year": year.label,
        "periods": [{"date": p, "label": period_label(p)} for p in periods],
        "resources": [r.as_dict(periods) for r in resources],
        "total_resources": total_resources.as_dict(periods),
        # Pour mémoire, hors totaux : une bourse n'est ni une recette ni une charge,
        # c'est une recette à laquelle l'école renonce.
        "scholarships": scholarships(year),
        "charges": [
            {**c.as_dict(periods), "weight": weight(c, total_charges.total)} for c in charges
        ],
        "total_charges": total_charges.as_dict(periods),
        "ebe": ebe.as_dict(periods),
        "cumulative_balance": {
            "key": cumulative.key,
            "label": cumulative.label,
            "values": [cumulative.values[p] for p in periods],
        },
        "current_balance": current_balance,
        "headcount_by_class": [
            {"classroom": c["classroom"], "headcount": c["headcount"], "revenue": c["revenue"]}
            for c in encais["classes"]
        ],
        "headcount_total": encais["headcount_total"],
        "revenue_total": encais["revenue_total"],
    }


def scholarships(year):
    """Effort social de l'établissement : bourses accordées et manque à gagner.

    Aucune recette n'est enregistrée pour une bourse — la ligne est donc « pour
    mémoire ». Elle chiffre ce que l'école renonce à percevoir, information que
    ni le chiffre d'affaires ni les charges ne portent, et sans laquelle
    l'administration ne peut pas arbitrer sa politique de bourses.
    """
    from apps.students.fees import due_map

    students = list(
        Student.objects.filter(status=StudentStatus.ACTIVE).select_related("classroom")
    )
    dues = due_map(year, students)
    months = year.tuition_months

    # Regroupement par taux : « 12 élèves à 100 % » se lit mieux que douze lignes.
    buckets = {}
    total_forgone = 0
    full_count = 0
    beneficiaries = 0
    detail = []

    for student in students:
        due = dues.get(student.id)
        if due is None or not due.has_discount:
            continue
        forgone = due.forgone(months)
        if forgone <= 0:
            continue

        beneficiaries += 1
        total_forgone += forgone
        rate = due.scholarship_rate
        if due.is_full_scholarship:
            full_count += 1

        bucket = buckets.setdefault(rate, {"rate": rate, "students": 0, "forgone": 0})
        bucket["students"] += 1
        bucket["forgone"] += forgone

        detail.append(
            {
                "student": student.id,
                "matricule": student.matricule,
                "name": student.full_name,
                "classroom": student.classroom.name,
                "rate": rate,
                "is_full": due.is_full_scholarship,
                "forgone": forgone,
                "categories": sorted({d.get_category_display() for d in due.discounts}),
            }
        )

    # Assiette théorique : ce que l'école percevrait sans aucune bourse.
    potential = sum(
        (due.full_registration + due.full_monthly_tuition * months)
        for due in dues.values()
        if due is not None
    )
    effort_rate = round(total_forgone * 100 / potential, 1) if potential else 0

    return {
        "year": year.label,
        "beneficiaries": beneficiaries,
        "full_scholarships": full_count,
        "total_forgone": total_forgone,
        "potential_revenue": potential,
        "effort_rate": effort_rate,
        "by_rate": sorted(buckets.values(), key=lambda b: b["rate"], reverse=True),
        "detail": sorted(detail, key=lambda d: d["forgone"], reverse=True),
    }


def comparison(year, previous_year):
    """Comparatif N / N-1 sur les agrégats du bilan."""
    current = bilan(year)
    if previous_year is None:
        return {"current": current, "previous": None, "variation": None}
    previous = bilan(previous_year)

    def delta(a, b):
        if not b:
            return None
        return round((a - b) / abs(b), 4)

    keys = ["total_resources", "total_charges", "ebe"]
    variation = {
        key: {
            "current": current[key]["total"],
            "previous": previous[key]["total"],
            "delta_ratio": delta(current[key]["total"], previous[key]["total"]),
        }
        for key in keys
    }
    return {"current": current, "previous": previous, "variation": variation}
