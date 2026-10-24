"""
Génération des documents PDF de l'application : quittances de loyer et
rapports financiers. Utilise reportlab (pure Python, aucune dépendance
système comme Cairo/Pango, contrairement à WeasyPrint).
"""
from io import BytesIO
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)
from reportlab.lib.enums import TA_CENTER

from .utils import mois_annee_fr

BLEU = colors.HexColor('#185FA5')
GRIS = colors.HexColor('#5f5e5a')


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='TitrePDF', fontSize=18, textColor=BLEU,
        spaceAfter=4, fontName='Helvetica-Bold'
    ))
    styles.add(ParagraphStyle(
        name='SousTitrePDF', fontSize=10, textColor=GRIS, spaceAfter=16
    ))
    styles.add(ParagraphStyle(
        name='Centre', alignment=TA_CENTER, fontSize=9, textColor=GRIS
    ))
    return styles


def generer_quittance_pdf(paiement):
    """
    Génère la quittance de loyer d'un objet Paiement et renvoie les octets
    du PDF (bytes), prêts à être renvoyés dans une HttpResponse.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm,
        leftMargin=2 * cm, rightMargin=2 * cm,
        title=f"Quittance de loyer - {mois_annee_fr(paiement.mois)}",
    )
    styles = _styles()
    story = []

    contrat = paiement.contrat
    bien = contrat.bien
    locataire = contrat.locataire
    proprietaire = bien.proprietaire

    story.append(Paragraph("QUITTANCE DE LOYER", styles['TitrePDF']))
    story.append(Paragraph(f"Période concernée : {mois_annee_fr(paiement.mois)}", styles['SousTitrePDF']))

    proprio_nom = proprietaire.get_full_name() or proprietaire.username
    info_table = Table([
        ["Bailleur (propriétaire)", "Locataire"],
        [proprio_nom, f"{locataire.prenom} {locataire.nom}"],
        [proprietaire.email or "—", locataire.email or "—"],
        ["", locataire.telephone or "—"],
    ], colWidths=[8.5 * cm, 8.5 * cm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 0), (-1, 0), BLEU),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor('#1a1a18')),
        ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.HexColor('#e0dfd8')),
        ('TOPPADDING', (0, 1), (-1, -1), 3),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 14))

    story.append(Paragraph(
        f"<b>Bien loué :</b> {bien.nom} — {bien.adresse}, {bien.ville}",
        styles['Normal']
    ))
    story.append(Spacer(1, 14))

    montant_du = paiement.montant_du
    montant_paye = paiement.montant_paye
    detail = [
        ["Désignation", "Montant"],
        ["Loyer mensuel", f"{contrat.loyer_mensuel:,.0f} F CFA".replace(',', ' ')],
        ["Charges", f"{contrat.charges_mensuelles:,.0f} F CFA".replace(',', ' ')],
        ["Total dû", f"{montant_du:,.0f} F CFA".replace(',', ' ')],
        ["Montant réglé", f"{montant_paye:,.0f} F CFA".replace(',', ' ')],
    ]
    detail_table = Table(detail, colWidths=[11 * cm, 6 * cm])
    detail_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), BLEU),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0dfd8')),
        ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 3), (-1, 3), colors.HexColor('#f0efe9')),
    ]))
    story.append(detail_table)
    story.append(Spacer(1, 20))

    mode = paiement.get_mode_paiement_display() if paiement.mode_paiement else "non précisé"
    date_paie = paiement.date_paiement.strftime('%d/%m/%Y') if paiement.date_paiement else "—"
    story.append(Paragraph(
        f"Le bailleur soussigné reconnaît avoir reçu de <b>{locataire.prenom} {locataire.nom}</b> "
        f"la somme de <b>{montant_paye:,.0f} F CFA</b>".replace(',', ' ') +
        f" au titre du loyer et des charges pour la période ci-dessus, "
        f"réglée par {mode} le {date_paie}, et lui en donne quittance, "
        f"sous réserve de tous ses droits.",
        styles['Normal']
    ))
    story.append(Spacer(1, 40))
    story.append(Paragraph(
        f"Fait le {date.today():%d/%m/%Y}", styles['Normal']
    ))
    story.append(Spacer(1, 30))
    story.append(Paragraph(
        "Document généré automatiquement par ImmoGest — ne constitue pas une pièce comptable "
        "officielle sans signature du bailleur.",
        styles['Centre']
    ))

    doc.build(story)
    return buffer.getvalue()


def generer_rapport_financier_pdf(proprietaire, paiements_qs, periode_label):
    """
    Génère un rapport financier PDF (liste des paiements + total) pour un
    propriétaire donné, sur la période fournie (déjà filtrée dans paiements_qs).
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm,
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        title="Rapport financier ImmoGest",
    )
    styles = _styles()
    story = []

    story.append(Paragraph("RAPPORT FINANCIER", styles['TitrePDF']))
    nom = proprietaire.get_full_name() or proprietaire.username
    story.append(Paragraph(f"{nom} — {periode_label}", styles['SousTitrePDF']))

    rows = [["Mois", "Bien", "Locataire", "Dû", "Payé", "Statut"]]
    total_du = 0
    total_paye = 0
    for p in paiements_qs.select_related('contrat__bien', 'contrat__locataire').order_by('-mois'):
        rows.append([
            p.mois.strftime('%m/%Y'),
            p.contrat.bien.nom,
            f"{p.contrat.locataire.prenom} {p.contrat.locataire.nom}",
            f"{p.montant_du:,.0f}".replace(',', ' '),
            f"{p.montant_paye:,.0f}".replace(',', ' '),
            p.get_statut_display(),
        ])
        total_du += p.montant_du
        total_paye += p.montant_paye

    rows.append(["", "", "TOTAL", f"{total_du:,.0f}".replace(',', ' '),
                 f"{total_paye:,.0f}".replace(',', ' '), ""])

    table = Table(rows, colWidths=[2 * cm, 4 * cm, 4.5 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm])
    style = TableStyle([
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), BLEU),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8.5),
        ('ALIGN', (3, 0), (4, -1), 'RIGHT'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#e0dfd8')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f0efe9')),
    ])
    table.setStyle(style)
    story.append(table)
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f"Généré le {date.today():%d/%m/%Y} par ImmoGest.", styles['Centre']
    ))

    doc.build(story)
    return buffer.getvalue()
