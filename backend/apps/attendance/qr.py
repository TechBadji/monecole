"""Génération des QR codes élèves et planches à imprimer.

⚠️ **Le QR contient les données personnelles en clair.** Décision explicite du
client le 30/07/2026, après exposition du risque : matricule, nom, prénom, date de
naissance et téléphone du parent sont lisibles par n'importe quel téléphone. Le
motif retenu est de pouvoir badger hors ligne et sans compte.

Conséquence assumée : une carte perdue livre l'identité d'un mineur, sa date de
naissance et le numéro de ses parents. Ce n'est pas un oubli d'implémentation.

L'alternative — un jeton signé résolu par l'API — reste implémentable sans toucher
au reste du module : seuls `Student.qr_payload` et `resolve_payload` changeraient.
"""

import io

import qrcode
from django.http import HttpResponse
from qrcode.image.pil import PilImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as pdf_canvas
from reportlab.lib.utils import ImageReader

# Correction d'erreur haute : ces cartes sont manipulées quotidiennement par des
# enfants. Un QR corné doit rester lisible.
ERROR_CORRECTION = qrcode.constants.ERROR_CORRECT_H


def build_qr_buffer(payload, box_size=8):
    """QR rendu en PNG dans un tampon mémoire.

    ReportLab n'accepte pas l'enveloppe retournée par `qrcode` : il lui faut un
    fichier image. Le tampon évite d'écrire sur disque pour chaque carte.
    """
    buffer = io.BytesIO()
    build_qr_image(payload, box_size).save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def build_qr_image(payload, box_size=10):
    code = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECTION,
        box_size=box_size,
        border=2,
    )
    code.add_data(payload)
    code.make(fit=True)
    return code.make_image(image_factory=PilImage, fill_color="black", back_color="white")


def student_qr_png(student, box_size=10):
    buffer = io.BytesIO()
    build_qr_image(student.qr_payload, box_size).save(buffer, format="PNG")
    buffer.seek(0)
    return HttpResponse(buffer.read(), content_type="image/png")


def resolve_payload(payload):
    """Retrouve un élève à partir d'un contenu de QR scanné.

    Tolère qu'on présente le seul matricule : les scanners du commerce lisent
    parfois mal les séparateurs, et un agent doit pouvoir saisir « M0042 » à la
    main quand la carte est illisible.
    """
    from apps.students.models import Student

    raw = (payload or "").strip()
    if not raw:
        return None

    matricule = raw.split("|")[0].strip().upper()
    if not matricule:
        return None
    return Student.objects.filter(matricule=matricule).first()


# --------------------------------------------------------------------------- #
# Planche de cartes à imprimer                                                 #
# --------------------------------------------------------------------------- #

CARD_WIDTH = 85 * mm      # format carte bancaire, tient dans un porte-badge
CARD_HEIGHT = 54 * mm
COLUMNS = 2
ROWS = 5


def qr_sheet_pdf(students, school, title="Cartes élèves"):
    """Planche de cartes, dix par page A4.

    Le format carte bancaire est retenu parce que les porte-badges et pochettes
    plastifiées de ce format se trouvent partout — une carte hors standard finit
    au fond d'un cartable.
    """
    buffer = io.BytesIO()
    canvas = pdf_canvas.Canvas(buffer, pagesize=A4)
    canvas.setTitle(title)

    page_width, page_height = A4
    margin_x = (page_width - COLUMNS * CARD_WIDTH) / 2
    margin_y = (page_height - ROWS * CARD_HEIGHT) / 2

    for index, student in enumerate(students):
        position = index % (COLUMNS * ROWS)
        if position == 0 and index:
            canvas.showPage()

        column = position % COLUMNS
        row = position // COLUMNS
        x = margin_x + column * CARD_WIDTH
        y = page_height - margin_y - (row + 1) * CARD_HEIGHT

        _draw_card(canvas, x, y, student, school)

    canvas.save()
    buffer.seek(0)
    return HttpResponse(buffer.read(), content_type="application/pdf")


def _draw_card(canvas, x, y, student, school):
    canvas.setStrokeColor(colors.HexColor("#CCCCCC"))
    canvas.setLineWidth(0.4)
    canvas.rect(x, y, CARD_WIDTH, CARD_HEIGHT)

    # Bandeau d'identification de l'école.
    canvas.setFillColor(colors.HexColor("#1F3864"))
    canvas.rect(x, y + CARD_HEIGHT - 9 * mm, CARD_WIDTH, 9 * mm, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 7.5)
    canvas.drawString(x + 4 * mm, y + CARD_HEIGHT - 6 * mm, school.name[:44].upper())

    # QR à gauche, identité à droite.
    canvas.drawImage(
        ImageReader(build_qr_buffer(student.qr_payload)),
        x + 4 * mm,
        y + 7 * mm,
        width=32 * mm,
        height=32 * mm,
        preserveAspectRatio=True,
    )

    text_x = x + 40 * mm
    canvas.setFillColor(colors.HexColor("#1F3864"))
    canvas.setFont("Helvetica-Bold", 13)
    canvas.drawString(text_x, y + CARD_HEIGHT - 17 * mm, student.matricule)

    canvas.setFillColor(colors.black)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(text_x, y + CARD_HEIGHT - 24 * mm, student.last_name.upper()[:22])
    canvas.setFont("Helvetica", 9)
    canvas.drawString(text_x, y + CARD_HEIGHT - 29 * mm, student.first_name[:22])

    canvas.setFillColor(colors.HexColor("#666666"))
    canvas.setFont("Helvetica", 7.5)
    canvas.drawString(text_x, y + CARD_HEIGHT - 36 * mm, f"Classe {student.classroom.name}")
    if student.date_of_birth:
        canvas.drawString(
            text_x, y + CARD_HEIGHT - 41 * mm, f"Né(e) le {student.date_of_birth:%d/%m/%Y}"
        )

    canvas.setFont("Helvetica", 6)
    canvas.drawString(x + 4 * mm, y + 3 * mm, "Carte scolaire — à présenter au portail")
