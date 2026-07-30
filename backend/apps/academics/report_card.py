"""Bulletin scolaire PDF — présentation sénégalaise.

L'en-tête, le logo, les mentions et la signature viennent de
`ReportCardSettings` : c'est le document que l'école remet aux familles et
présente à l'inspection, il doit être réglable sans intervention technique.
"""

import io

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

BRAND = colors.HexColor("#1F3864")
SOFT = colors.HexColor("#EAEFFA")
GREY = colors.HexColor("#666666")
LINE = colors.HexColor("#CCCCCC")


def _grade(value):
    """Note à la française : virgule décimale, un seul chiffre après."""
    if value is None:
        return "—"
    return f"{float(value):.2f}".rstrip("0").rstrip(".").replace(".", ",")


def _styles():
    base = getSampleStyleSheet()
    return {
        "normal": base["Normal"],
        "center": ParagraphStyle("c", parent=base["Normal"], fontSize=8, alignment=1),
        "header": ParagraphStyle(
            "h", parent=base["Normal"], fontSize=7.5, alignment=1, textColor=GREY,
            leading=10,
        ),
        "title": ParagraphStyle(
            "t", parent=base["Normal"], fontSize=13, alignment=1,
            fontName="Helvetica-Bold", textColor=BRAND, spaceBefore=4, spaceAfter=2,
        ),
        "small": ParagraphStyle("s", parent=base["Normal"], fontSize=7, textColor=GREY),
    }


def _header(settings, school, styles):
    """En-tête administratif : mentions officielles à gauche, école à droite."""
    official = "<br/>".join(
        line for line in (
            settings.header_line_1, settings.header_line_2, settings.header_line_3
        ) if line
    )

    logo_cell = ""
    if settings.logo:
        try:
            logo_cell = Image(settings.logo.path, width=20 * mm, height=20 * mm,
                              kind="proportional")
        except Exception:  # noqa: BLE001 — un logo illisible ne bloque pas un bulletin
            logo_cell = ""

    school_block = f"<b>{school.name}</b>"
    if settings.establishment_code:
        school_block += f"<br/>Code : {settings.establishment_code}"
    if school.address:
        school_block += f"<br/>{school.address}"
    if school.phone:
        school_block += f"<br/>{school.phone}"

    table = Table(
        [[
            Paragraph(official, styles["header"]),
            logo_cell,
            Paragraph(school_block, styles["header"]),
        ]],
        colWidths=[62 * mm, 24 * mm, 62 * mm],
    )
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


def _identity(student, classroom, composition, styles):
    rows = [[
        Paragraph(f"<b>Élève :</b> {student.full_name}", styles["normal"]),
        Paragraph(f"<b>Matricule :</b> {student.matricule}", styles["normal"]),
    ], [
        Paragraph(f"<b>Classe :</b> {classroom.name}", styles["normal"]),
        Paragraph(
            "<b>Né(e) le :</b> "
            + (student.date_of_birth.strftime("%d/%m/%Y") if student.date_of_birth else "—"),
            styles["normal"],
        ),
    ]]
    table = Table(rows, colWidths=[92 * mm, 56 * mm])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("GRID", (0, 0), (-1, -1), 0.25, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _grades_table(result, styles):
    rows = [["Matière", "Coef.", "Note /20", "Points", "Appréciation"]]
    for line in result["lines"]:
        note = "Abs." if line["is_absent"] else _grade(line["value"])
        rows.append([
            line["subject"],
            str(line["coefficient"]),
            note,
            _grade(line["points"]),
            Paragraph(line["comment"] or "", styles["small"]),
        ])

    rows.append([
        "Total",
        str(result["total_coefficients"]),
        "",
        _grade(result["total_points"]),
        "",
    ])
    total_row = len(rows) - 1

    table = Table(
        rows,
        colWidths=[58 * mm, 14 * mm, 20 * mm, 20 * mm, 36 * mm],
        repeatRows=1,
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (3, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, LINE),
        ("ROWBACKGROUNDS", (0, 1), (-1, total_row - 1), [colors.white, colors.HexColor("#F7F8FA")]),
        ("BACKGROUND", (0, total_row), (-1, total_row), SOFT),
        ("FONTNAME", (0, total_row), (-1, total_row), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
    ]))
    return table


def _summary(result, summary, settings, styles):
    """Bloc de synthèse : moyenne, rang, mention."""
    cells = [
        ("Moyenne générale", f"{_grade(result['average'])} / 20"),
        ("Mention", result["mention"] or "—"),
    ]
    if settings.show_rank:
        rank = (
            f"{result['rank']}{'er' if result['rank'] == 1 else 'e'} / {result['ranked_out_of']}"
            if result["rank"]
            else "non classé"
        )
        cells.append(("Rang", rank))
    if settings.show_class_average and summary.get("class_average") is not None:
        cells.append(("Moyenne de la classe", f"{_grade(summary['class_average'])} / 20"))

    table = Table(
        [[Paragraph(f"<b>{label}</b>", styles["center"]) for label, _ in cells],
         [Paragraph(value, styles["center"]) for _, value in cells]],
        colWidths=[148 * mm / len(cells)] * len(cells),
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), SOFT),
        ("GRID", (0, 0), (-1, -1), 0.25, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("FONTSIZE", (0, 1), (-1, 1), 10),
        ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
    ]))
    return table


def _signatures(settings, styles):
    principal = settings.principal_title or "Le Directeur"
    if settings.principal_name:
        principal += f"<br/><font size=7>{settings.principal_name}</font>"

    table = Table(
        [[
            Paragraph("Le Parent / Tuteur", styles["center"]),
            Paragraph("L'Enseignant", styles["center"]),
            Paragraph(principal, styles["center"]),
        ], ["", "", ""]],
        colWidths=[49.3 * mm] * 3,
        rowHeights=[7 * mm, 18 * mm],
    )
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.25, LINE),
    ]))
    return table


def report_cards_pdf(
    *, students, results, subjects, composition, classroom, summary, school, settings
):
    """Un bulletin par page, prêt à imprimer en lot."""
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm, rightMargin=16 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm,
        title=f"Bulletins {classroom.name} — {composition.name}",
    )
    styles = _styles()
    generated = timezone.localtime().strftime("%d/%m/%Y à %H:%M")

    story = []
    for index, student in enumerate(students):
        result = results.get(student.id)
        if result is None:
            continue
        if index:
            story.append(PageBreak())

        story.append(_header(settings, school, styles))
        story.append(Spacer(1, 4))
        story.append(Paragraph("BULLETIN DE NOTES", styles["title"]))
        story.append(Paragraph(
            f"{composition.name} — année scolaire {composition.year.label}",
            styles["center"],
        ))
        story.append(Spacer(1, 8))

        story.append(_identity(student, classroom, composition, styles))
        story.append(Spacer(1, 8))
        story.append(_grades_table(result, styles))
        story.append(Spacer(1, 8))
        story.append(_summary(result, summary, settings, styles))
        story.append(Spacer(1, 10))

        # Une matière non validée par son enseignant doit se voir sur le document :
        # un bulletin incomplet remis sans réserve serait pris pour définitif.
        pending = [line["subject"] for line in result["lines"] if not line["validated"]]
        if pending:
            story.append(Paragraph(
                f"<b>Document provisoire</b> — notes non encore validées : "
                f"{', '.join(pending)}.",
                ParagraphStyle("w", parent=styles["normal"], fontSize=8,
                               textColor=colors.HexColor("#B42318")),
            ))
            story.append(Spacer(1, 6))

        story.append(_signatures(settings, styles))

        if settings.footer_note:
            story.append(Spacer(1, 6))
            story.append(Paragraph(settings.footer_note, styles["small"]))

    if not story:
        story = [Paragraph("Aucun bulletin à éditer.", styles["normal"])]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 6.5)
        canvas.setFillColor(GREY)
        canvas.drawString(16 * mm, 8 * mm, f"Édité le {generated} — MonÉcole")
        canvas.drawRightString(A4[0] - 16 * mm, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return HttpResponse(buffer.read(), content_type="application/pdf")
