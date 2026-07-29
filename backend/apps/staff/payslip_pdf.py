"""Bulletin de paie PDF — présentation sénégalaise."""

import io

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.core.periods import label as period_label

BRAND = colors.HexColor("#1F3864")
SOFT = colors.HexColor("#EAEFFA")
GREY = colors.HexColor("#666666")
LINE = colors.HexColor("#CCCCCC")


def _money(value):
    return f"{value:,}".replace(",", " ") if value else "—"


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=13, spaceAfter=2,
                                textColor=BRAND),
        "normal": base["Normal"],
        "small": ParagraphStyle("s", parent=base["Normal"], fontSize=7.5, textColor=GREY),
        "section": ParagraphStyle("h", parent=base["Normal"], fontSize=9,
                                  fontName="Helvetica-Bold", textColor=BRAND,
                                  spaceBefore=8, spaceAfter=3),
    }


def _payslip_story(payslip, school, styles):
    """Contenu d'un bulletin. Isolé pour permettre la génération en masse."""
    teacher = payslip.teacher
    profile = getattr(teacher, "payroll_profile", None)
    detail = payslip.computation or {}
    story = []

    # --- En-tête -----------------------------------------------------------
    header = Table(
        [[
            Paragraph(f"<b>{school.name}</b><br/>"
                      f"<font size=7.5 color='#666666'>{school.address or ''}<br/>"
                      f"{school.phone or ''}</font>", styles["normal"]),
            Paragraph("<b>BULLETIN DE PAIE</b><br/>"
                      f"<font size=8>{period_label(payslip.period)}</font>",
                      ParagraphStyle("r", parent=styles["normal"], alignment=2)),
        ]],
        colWidths=[100 * mm, 76 * mm],
    )
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 1, BRAND),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
    ]))
    story.append(header)
    story.append(Spacer(1, 8))

    # --- Identité ----------------------------------------------------------
    identity = [
        ["Matricule", teacher.matricule, "Fonction", teacher.function or "—"],
        ["Nom et prénom(s)", teacher.full_name, "Contrat", teacher.get_contract_type_display()],
        [
            "N° sécurité sociale",
            (profile.social_security_number if profile else "") or "—",
            "Catégorie",
            "Cadre" if (profile and profile.is_executive) else "Non-cadre",
        ],
        [
            "Prise de service",
            teacher.service_start_date.strftime("%d/%m/%Y") if teacher.service_start_date else "—",
            "Parts fiscales",
            profile.get_family_shares_display() if profile else "1 part",
        ],
    ]
    table = Table(identity, colWidths=[32 * mm, 56 * mm, 30 * mm, 58 * mm])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (0, -1), GREY),
        ("TEXTCOLOR", (2, 0), (2, -1), GREY),
        ("GRID", (0, 0), (-1, -1), 0.25, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    story.append(table)

    # --- Rémunération et cotisations --------------------------------------
    story.append(Paragraph("Rémunération et cotisations", styles["section"]))

    rows = [["Libellé", "Base", "Taux", "Part salarié", "Part employeur"]]
    rows.append(["Salaire brut imposable", "", "", _money(payslip.gross), ""])
    if payslip.non_taxable:
        rows.append(["Indemnités non imposables", "", "", _money(payslip.non_taxable), ""])

    for line in detail.get("lines", []):
        rows.append([
            line["label"],
            _money(line["base"]),
            f"{line['rate']} %" if line.get("rate") else "",
            f"-{_money(line['employee'])}" if line["employee"] else "—",
            _money(line["employer"]),
        ])

    rows.append(["Total cotisations", "", "",
                 f"-{_money(payslip.employee_contributions)}",
                 _money(payslip.employer_contributions)])
    contributions_row = len(rows) - 1

    rows.append(["Impôt sur le revenu (IR)", "", "", f"-{_money(payslip.income_tax)}", ""])
    rows.append(["TRIMF", "", "", f"-{_money(payslip.trimf)}", ""])
    if payslip.other_deductions:
        rows.append(["Autres retenues", "", "", f"-{_money(payslip.other_deductions)}", ""])

    rows.append(["NET À PAYER", "", "", _money(payslip.net_pay), ""])
    net_row = len(rows) - 1

    table = Table(rows, colWidths=[62 * mm, 26 * mm, 18 * mm, 34 * mm, 36 * mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7.8),
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.25, LINE),
        ("BACKGROUND", (0, contributions_row), (-1, contributions_row), SOFT),
        ("FONTNAME", (0, contributions_row), (-1, contributions_row), "Helvetica-Bold"),
        ("BACKGROUND", (0, net_row), (-1, net_row), BRAND),
        ("TEXTCOLOR", (0, net_row), (-1, net_row), colors.white),
        ("FONTNAME", (0, net_row), (-1, net_row), "Helvetica-Bold"),
        ("FONTSIZE", (0, net_row), (-1, net_row), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    story.append(table)

    # --- Récapitulatif -----------------------------------------------------
    story.append(Spacer(1, 8))
    summary = Table(
        [[
            f"Coût total employeur : {_money(payslip.employer_cost)} {school.currency}",
            f"Net imposable annuel : {_money(detail.get('taxable_income_annual', 0))} "
            f"{school.currency}",
            f"Payé le : {payslip.paid_at:%d/%m/%Y}" if payslip.paid_at else "Non réglé",
        ]],
        colWidths=[62 * mm, 62 * mm, 52 * mm],
    )
    summary.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), GREY),
        ("BOX", (0, 0), (-1, -1), 0.25, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(summary)

    # --- Signatures --------------------------------------------------------
    story.append(Spacer(1, 12))
    signatures = Table(
        [["L'employeur", "Le salarié"], ["", ""]],
        colWidths=[88 * mm, 88 * mm], rowHeights=[6 * mm, 16 * mm],
    )
    signatures.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, 0), GREY),
        ("BOX", (0, 0), (-1, -1), 0.25, LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, LINE),
    ]))
    story.append(signatures)

    # --- Mentions ----------------------------------------------------------
    story.append(Spacer(1, 6))
    scale_note = (
        f"Barème « {payslip.scale.label} », en vigueur depuis le "
        f"{payslip.scale.effective_from:%d/%m/%Y}"
    )
    if not payslip.scale.is_validated:
        # Mention explicite : un bulletin calculé sur un barème non validé ne doit
        # pas être remis à un salarié comme s'il faisait foi.
        scale_note += " — <b>non validé par un expert-comptable</b>"
    story.append(Paragraph(scale_note, styles["small"]))
    story.append(Paragraph(
        "Document à conserver sans limitation de durée. "
        "Bulletin établi conformément au Code du travail sénégalais.",
        styles["small"],
    ))
    return story


def payslip_pdf(payslip, school):
    """Bulletin individuel."""
    return _render([payslip], school, f"Bulletin {payslip.teacher.full_name}")


def payslips_pdf(payslips, school, title="Bulletins de paie"):
    """Génération en masse — un bulletin par page."""
    return _render(list(payslips), school, title)


def _render(payslips, school, title):
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=17 * mm, rightMargin=17 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title=title,
    )
    styles = _styles()

    story = []
    for index, payslip in enumerate(payslips):
        if index:
            story.append(PageBreak())
        story.extend(_payslip_story(payslip, school, styles))

    if not story:
        story = [Paragraph("Aucun bulletin pour cette période.", styles["normal"])]

    generated = timezone.localtime().strftime("%d/%m/%Y à %H:%M")

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(GREY)
        canvas.drawString(17 * mm, 9 * mm, f"Généré le {generated} — MonÉcole")
        canvas.drawRightString(A4[0] - 17 * mm, 9 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return HttpResponse(buffer.read(), content_type="application/pdf")
