"""Calcul de paie — schéma sénégalais.

Enchaînement réglementaire :

    Brut imposable  = salaire de base + primes imposables
    Cotisations sal.= IPRES RG (+ RC si cadre)
    Net imposable   = brut − cotisations salariales − abattement frais pro.
    IR brut         = barème progressif annuel appliqué au net imposable
    IR net          = IR brut − réduction pour charges de famille (parts)
    TRIMF           = barème forfaitaire par tranche
    Net à payer     = brut − cotisations − IR net − TRIMF − autres retenues
                      + primes non imposables

⚠️ **Les barèmes sont des valeurs par défaut, à faire valider.** Ils sont stockés en
base (`PayrollScale`), datés, et modifiables sans redéploiement — une loi de
finances peut les changer chaque année. Le module ne prétend pas se substituer à un
expert-comptable : il automatise un calcul, il ne le certifie pas.

Sources des valeurs par défaut : IPRES (régimes RG et cadres), Caisse de Sécurité
Sociale, Code général des impôts sénégalais — barème IR et TRIMF.
"""

from dataclasses import dataclass, field
from decimal import Decimal

# --------------------------------------------------------------------------- #
# Barèmes par défaut                                                           #
# --------------------------------------------------------------------------- #

# IPRES — assiettes plafonnées mensuelles et taux.
DEFAULT_IPRES_RG_CEILING = 432_000
DEFAULT_IPRES_RG_EMPLOYEE = Decimal("5.6")
DEFAULT_IPRES_RG_EMPLOYER = Decimal("8.4")

DEFAULT_IPRES_RC_CEILING = 1_296_000
DEFAULT_IPRES_RC_EMPLOYEE = Decimal("2.4")
DEFAULT_IPRES_RC_EMPLOYER = Decimal("3.6")

# CSS — entièrement à la charge de l'employeur, aucune retenue salariale.
DEFAULT_CSS_CEILING = 63_000
DEFAULT_CSS_FAMILY_RATE = Decimal("7.0")
DEFAULT_CSS_ACCIDENT_RATE = Decimal("1.0")

# Abattement forfaitaire pour frais professionnels : 30 % du brut, plafonné.
DEFAULT_ALLOWANCE_RATE = Decimal("30.0")
DEFAULT_ALLOWANCE_CEILING_ANNUAL = 900_000

# Barème IR annuel : (borne supérieure incluse, taux %). None = tranche ouverte.
DEFAULT_INCOME_TAX_BRACKETS = [
    (630_000, Decimal("0")),
    (1_500_000, Decimal("20")),
    (4_000_000, Decimal("30")),
    (8_000_000, Decimal("35")),
    (13_500_000, Decimal("37")),
    (None, Decimal("40")),
]

# Réduction pour charges de famille : parts → (taux %, minimum, maximum) annuels.
DEFAULT_FAMILY_RELIEF = {
    "1": (Decimal("0"), 0, 0),
    "1.5": (Decimal("10"), 100_000, 300_000),
    "2": (Decimal("15"), 200_000, 650_000),
    "2.5": (Decimal("20"), 300_000, 1_100_000),
    "3": (Decimal("25"), 400_000, 1_650_000),
    "3.5": (Decimal("30"), 500_000, 2_030_000),
    "4": (Decimal("35"), 600_000, 2_490_000),
    "4.5": (Decimal("40"), 700_000, 2_755_000),
    "5": (Decimal("45"), 800_000, 3_180_000),
}

# TRIMF : (borne supérieure du revenu annuel, montant annuel dû).
DEFAULT_TRIMF_BRACKETS = [
    (599_999, 900),
    (999_999, 3_600),
    (1_999_999, 4_800),
    (6_999_999, 12_000),
    (11_999_999, 18_000),
    (None, 36_000),
]


def default_scale_values():
    """Barèmes par défaut, sous forme sérialisable pour stockage en base."""
    return {
        "ipres_rg_ceiling": DEFAULT_IPRES_RG_CEILING,
        "ipres_rg_employee": str(DEFAULT_IPRES_RG_EMPLOYEE),
        "ipres_rg_employer": str(DEFAULT_IPRES_RG_EMPLOYER),
        "ipres_rc_ceiling": DEFAULT_IPRES_RC_CEILING,
        "ipres_rc_employee": str(DEFAULT_IPRES_RC_EMPLOYEE),
        "ipres_rc_employer": str(DEFAULT_IPRES_RC_EMPLOYER),
        "css_ceiling": DEFAULT_CSS_CEILING,
        "css_family_rate": str(DEFAULT_CSS_FAMILY_RATE),
        "css_accident_rate": str(DEFAULT_CSS_ACCIDENT_RATE),
        "allowance_rate": str(DEFAULT_ALLOWANCE_RATE),
        "allowance_ceiling_annual": DEFAULT_ALLOWANCE_CEILING_ANNUAL,
        "income_tax_brackets": [[b, str(r)] for b, r in DEFAULT_INCOME_TAX_BRACKETS],
        "family_relief": {k: [str(v[0]), v[1], v[2]] for k, v in DEFAULT_FAMILY_RELIEF.items()},
        "trimf_brackets": [[b, a] for b, a in DEFAULT_TRIMF_BRACKETS],
    }


# --------------------------------------------------------------------------- #
# Calcul                                                                       #
# --------------------------------------------------------------------------- #


@dataclass
class PayslipLine:
    label: str
    base: int = 0
    rate: Decimal | None = None
    employee: int = 0
    employer: int = 0


@dataclass
class PayslipComputation:
    gross: int
    taxable_gross: int
    non_taxable: int
    lines: list = field(default_factory=list)
    total_employee: int = 0
    total_employer: int = 0
    income_tax: int = 0
    trimf: int = 0
    other_deductions: int = 0
    net_pay: int = 0
    taxable_income_annual: int = 0

    def as_dict(self):
        return {
            "gross": self.gross,
            "taxable_gross": self.taxable_gross,
            "non_taxable": self.non_taxable,
            "lines": [
                {
                    "label": line.label,
                    "base": line.base,
                    "rate": str(line.rate) if line.rate is not None else None,
                    "employee": line.employee,
                    "employer": line.employer,
                }
                for line in self.lines
            ],
            "total_employee": self.total_employee,
            "total_employer": self.total_employer,
            "income_tax": self.income_tax,
            "trimf": self.trimf,
            "other_deductions": self.other_deductions,
            "net_pay": self.net_pay,
            "taxable_income_annual": self.taxable_income_annual,
            "employer_cost": self.gross + self.total_employer,
        }


def _rate(scale, key):
    return Decimal(str(scale[key]))


def _apply(base, rate):
    """Arrondi à l'unité : le franc CFA n'a pas de subdivision."""
    return int((Decimal(base) * rate / 100).to_integral_value())


def compute_payslip(
    *,
    scale,
    gross,
    non_taxable=0,
    is_executive=False,
    family_shares="1",
    other_deductions=0,
):
    """Calcule un bulletin mensuel.

    `gross` est le brut imposable, `non_taxable` les indemnités exonérées (transport
    dans la limite légale, par exemple) qui s'ajoutent au net sans supporter de
    charges.
    """
    result = PayslipComputation(
        gross=gross,
        taxable_gross=gross,
        non_taxable=non_taxable,
        other_deductions=other_deductions,
    )

    # --- IPRES régime général ---------------------------------------------
    rg_base = min(gross, int(scale["ipres_rg_ceiling"]))
    rg_employee = _apply(rg_base, _rate(scale, "ipres_rg_employee"))
    rg_employer = _apply(rg_base, _rate(scale, "ipres_rg_employer"))
    result.lines.append(
        PayslipLine("IPRES — régime général", rg_base,
                    _rate(scale, "ipres_rg_employee"), rg_employee, rg_employer)
    )

    # --- IPRES régime complémentaire cadres --------------------------------
    if is_executive:
        rc_base = min(gross, int(scale["ipres_rc_ceiling"]))
        rc_employee = _apply(rc_base, _rate(scale, "ipres_rc_employee"))
        rc_employer = _apply(rc_base, _rate(scale, "ipres_rc_employer"))
        result.lines.append(
            PayslipLine("IPRES — régime cadres", rc_base,
                        _rate(scale, "ipres_rc_employee"), rc_employee, rc_employer)
        )

    # --- CSS : employeur uniquement ----------------------------------------
    css_base = min(gross, int(scale["css_ceiling"]))
    result.lines.append(
        PayslipLine("CSS — prestations familiales", css_base,
                    _rate(scale, "css_family_rate"), 0,
                    _apply(css_base, _rate(scale, "css_family_rate")))
    )
    result.lines.append(
        PayslipLine("CSS — accidents du travail", css_base,
                    _rate(scale, "css_accident_rate"), 0,
                    _apply(css_base, _rate(scale, "css_accident_rate")))
    )

    result.total_employee = sum(line.employee for line in result.lines)
    result.total_employer = sum(line.employer for line in result.lines)

    # --- Revenu net imposable ----------------------------------------------
    # Le barème IR est annuel : on annualise, on calcule, puis on ramène au mois.
    annual_gross = (gross - result.total_employee) * 12
    allowance = min(
        _apply(annual_gross, _rate(scale, "allowance_rate")),
        int(scale["allowance_ceiling_annual"]),
    )
    taxable_annual = max(0, annual_gross - allowance)
    result.taxable_income_annual = taxable_annual

    tax_annual = _progressive_tax(taxable_annual, scale["income_tax_brackets"])
    relief = _family_relief(tax_annual, family_shares, scale["family_relief"])
    result.income_tax = max(0, (tax_annual - relief)) // 12

    # --- TRIMF --------------------------------------------------------------
    result.trimf = _trimf(taxable_annual, scale["trimf_brackets"]) // 12

    result.net_pay = (
        gross
        - result.total_employee
        - result.income_tax
        - result.trimf
        - other_deductions
        + non_taxable
    )
    return result


def _progressive_tax(taxable, brackets):
    """Barème progressif par tranches : chaque tranche n'est taxée qu'à son taux."""
    tax = Decimal(0)
    lower = 0
    for ceiling, rate in brackets:
        rate = Decimal(str(rate))
        upper = taxable if ceiling is None else min(taxable, int(ceiling))
        if upper > lower:
            tax += Decimal(upper - lower) * rate / 100
        if ceiling is not None and taxable <= int(ceiling):
            break
        if ceiling is not None:
            lower = int(ceiling)
    return int(tax.to_integral_value())


def _family_relief(tax_annual, shares, relief_table):
    """Réduction pour charges de famille, bornée par un plancher et un plafond."""
    entry = relief_table.get(str(shares)) or relief_table.get("1")
    rate, minimum, maximum = Decimal(str(entry[0])), int(entry[1]), int(entry[2])
    if rate == 0:
        return 0
    relief = int((Decimal(tax_annual) * rate / 100).to_integral_value())
    # Le plancher ne s'applique pas au-delà de l'impôt dû : une réduction ne peut
    # pas rendre l'impôt négatif.
    return min(max(relief, minimum), maximum, tax_annual)


def _trimf(taxable_annual, brackets):
    for ceiling, amount in brackets:
        if ceiling is None or taxable_annual <= int(ceiling):
            return int(amount)
    return 0
