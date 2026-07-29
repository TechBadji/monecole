"""Reçu de paiement en PDF."""

import io

from django.http import HttpResponse
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.core.periods import label as period_label


def _money(value):
    return f"{value:,}".replace(",", " ")


def receipt_pdf(txn, school):
    """Reçu nominatif d'un règlement confirmé.

    Format A5 : ces reçus sont imprimés en série au guichet, souvent sur des
    imprimantes modestes, et deux tiennent sur une feuille A4.
    """
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A5,
        leftMargin=14 * mm, rightMargin=14 * mm,
        topMargin=14 * mm, bottomMargin=14 * mm,
        title=f"Reçu {txn.reference}",
    )

    styles = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=styles["Title"], fontSize=14, spaceAfter=2)
    small = ParagraphStyle("s", parent=styles["Normal"], fontSize=8,
                           textColor=colors.HexColor("#555555"))

    story = [
        Paragraph(school.name, title),
        Paragraph(school.address or "", small),
        Spacer(1, 8),
        Paragraph("<b>REÇU DE PAIEMENT</b>", styles["Heading2"]),
        Spacer(1, 4),
    ]

    period = period_label(txn.period) if txn.period else "—"
    purpose = "Frais d'inscription" if txn.purpose == "REGISTRATION" else f"Scolarité — {period}"

    rows = [
        ["Référence", txn.reference],
        ["Date", timezone.localtime(txn.confirmed_at or txn.created_at).strftime("%d/%m/%Y à %H:%M")],
        ["Élève", txn.student.full_name],
        ["Classe", txn.student.classroom.name],
        ["Objet", purpose],
        ["Moyen de paiement", txn.get_method_display()],
        ["Montant réglé", f"{_money(txn.amount)} {school.currency}"],
    ]
    if txn.received_by:
        rows.append(["Encaissé par", txn.received_by])

    table = Table(rows, colWidths=[42 * mm, 76 * mm])
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#555555")),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#DDDDDD")),
        ("BACKGROUND", (0, 6), (-1, 6), colors.HexColor("#EAEFFA")),
        ("FONTNAME", (0, 6), (-1, 6), "Helvetica-Bold"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    table.setStyle(TableStyle(style))
    story.append(table)
    story.append(Spacer(1, 10))

    if txn.simulated:
        # Un reçu issu d'une transaction simulée doit être impossible à confondre
        # avec un reçu réel — il n'a aucune valeur probante.
        story.append(
            Paragraph(
                "<b>DOCUMENT DE TEST</b> — transaction simulée, sans valeur.",
                ParagraphStyle("w", parent=styles["Normal"], fontSize=10,
                               textColor=colors.HexColor("#B42318")),
            )
        )
        story.append(Spacer(1, 6))

    story.append(
        Paragraph(
            f"Reçu émis le {timezone.localtime().strftime('%d/%m/%Y à %H:%M')} — MonÉcole. "
            f"Conservez ce document, il fait foi du règlement.",
            small,
        )
    )

    document.build(story)
    buffer.seek(0)
    return HttpResponse(buffer.read(), content_type="application/pdf")
