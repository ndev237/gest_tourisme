"""
reservation/utils.py
====================
Utilitaires pour la génération des bons de réservation.

ARCHITECTURE :
- generer_qr_code_image(token, bon) → enregistre un PNG dans bon.qr_code_image
- generer_bon_pdf(bon) → enregistre un PDF dans bon.pdf_fichier

INITIATIVES PÉDAGOGIQUES :
1. SÉPARATION DES RESPONSABILITÉS (SRP) : la génération PDF/QR est
   isolée des vues. On peut la tester en isolation, et la remplacer
   sans toucher au reste du code (ex: passer de reportlab à weasyprint).
2. Génération EN MÉMOIRE puis save via ContentFile : pas de fichier
   temporaire sur disque → plus propre et plus sûr.
3. Le QR Code contient un TOKEN, pas l'ID de réservation. Évite qu'un
   attaquant scanne un QR fabriqué avec un ID deviné.
4. PDF généré avec reportlab (canvas) car plus léger que weasyprint
   (pas de dépendance système comme libpango).
5. Gestion d'erreur défensive : si reportlab/qrcode pas installés,
   les fonctions ne plantent pas — elles renvoient None et logguent
   un warning. Permet de déployer même sans les libs (mode dégradé).
"""

import io
import logging
from django.core.files.base import ContentFile

logger = logging.getLogger(__name__)

# Imports défensifs (les libs peuvent ne pas être installées en dev)
try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False
    logger.warning("Module 'qrcode' non installé. Installez avec: pip install qrcode[pil]")

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A5, A4
    from reportlab.lib.units import cm, mm
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.lib.utils import ImageReader
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False
    logger.warning("Module 'reportlab' non installé. Installez avec: pip install reportlab")


# ============================================================
# CONSTANTES (charte graphique cohérente avec le thème "cameroun")
# ============================================================
COULEUR_PRIMARY = '#15803D'   # Vert Cameroun (primary du thème)
COULEUR_ACCENT = '#EAB308'    # Jaune/Or (accent du thème)
COULEUR_TEXTE = '#1F2937'
COULEUR_GRIS = '#6B7280'


# ============================================================
# 1. GÉNÉRATION QR CODE
# ============================================================
def generer_qr_code_image(token, bon):
    """
    Génère l'image PNG du QR Code à partir du token, et l'enregistre
    dans le champ bon.qr_code_image.

    Arguments :
    - token : la chaîne à encoder (le qr_code_data du bon)
    - bon : l'instance BonReservation à mettre à jour

    Retourne True si succès, False sinon.
    """
    if not QRCODE_AVAILABLE:
        logger.error("Impossible de générer le QR : module 'qrcode' manquant")
        return False

    try:
        # Pédago : on configure le QR pour une lisibilité optimale
        # - version=None → auto-détection de la taille
        # - error_correction=H → 30% de tolérance (résiste aux taches, plis)
        # - box_size=10 → chaque "case" fait 10×10 pixels
        # - border=2 → marge blanche de 2 cases autour (norme ISO/IEC 18004)
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=2,
        )
        qr.add_data(token)
        qr.make(fit=True)

        # Génération de l'image (PIL)
        img = qr.make_image(
            fill_color=COULEUR_PRIMARY,  # Vert Cameroun
            back_color="white",
        )

        # Sauvegarde en mémoire (BytesIO) plutôt que sur disque
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)

        # Pédago : ContentFile permet de sauver depuis BytesIO sans fichier
        # temporaire. Le path final est déterminé par upload_to du modèle.
        nom_fichier = f"qr_{bon.reservation.numero}.png"
        bon.qr_code_image.save(nom_fichier, ContentFile(buffer.getvalue()), save=False)

        return True

    except Exception as e:
        logger.error(f"Erreur génération QR pour bon {bon.id} : {e}", exc_info=True)
        return False


# ============================================================
# 2. GÉNÉRATION BON PDF
# ============================================================
def generer_bon_pdf(bon):
    """
    Génère le PDF du bon de réservation (format A5 pour impression facile).

    Arguments :
    - bon : l'instance BonReservation (avec sa qr_code_image déjà générée)

    Le PDF contient :
    - En-tête avec logo/titre Tourisme Cameroun
    - Numéro de réservation et code-barre du QR
    - Détails de la visite (date, heure, nombre de personnes)
    - Détails du site (nom, adresse, contact)
    - Lignes facturées + montant total
    - Conditions d'utilisation
    - QR code en pied (scannable à l'entrée)

    Retourne True si succès, False sinon.
    """
    if not REPORTLAB_AVAILABLE:
        logger.error("Impossible de générer le PDF : module 'reportlab' manquant")
        return False

    try:
        reservation = bon.reservation
        site = reservation.site
        touriste = reservation.touriste

        # ----- Création du PDF en mémoire -----
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=A5)
        largeur, hauteur = A5  # 148 × 210 mm

        # ===================================================
        # SECTION 1 : EN-TÊTE (bandeau vert)
        # ===================================================
        p.setFillColor(HexColor(COULEUR_PRIMARY))
        p.rect(0, hauteur - 3 * cm, largeur, 3 * cm, fill=1, stroke=0)

        p.setFillColor(white)
        p.setFont("Helvetica-Bold", 18)
        p.drawString(1 * cm, hauteur - 1.3 * cm, "🇨🇲 TOURISME CAMEROUN")
        p.setFont("Helvetica", 9)
        p.drawString(1 * cm, hauteur - 2.0 * cm, "Bon de réservation officiel")
        p.drawString(1 * cm, hauteur - 2.5 * cm, "À présenter à l'entrée du site")

        # ===================================================
        # SECTION 2 : N° de réservation (zone proéminente)
        # ===================================================
        y = hauteur - 4.5 * cm
        p.setFillColor(HexColor(COULEUR_TEXTE))
        p.setFont("Helvetica-Bold", 14)
        p.drawString(1 * cm, y, "N° de réservation")
        p.setFont("Helvetica-Bold", 20)
        p.setFillColor(HexColor(COULEUR_PRIMARY))
        p.drawString(1 * cm, y - 0.8 * cm, reservation.numero)

        # ===================================================
        # SECTION 3 : Détails de la réservation
        # ===================================================
        y -= 2 * cm
        p.setFillColor(HexColor(COULEUR_TEXTE))
        p.setFont("Helvetica-Bold", 11)
        p.drawString(1 * cm, y, "🎫 Détails de la visite")
        p.line(1 * cm, y - 0.15 * cm, largeur - 1 * cm, y - 0.15 * cm)

        details = [
            ("Site", site.nom),
            ("Localisation", f"{site.localisation.ville}, {site.localisation.region.nom}"),
            ("Date de visite", reservation.date_visite.strftime("%d/%m/%Y")),
        ]
        if reservation.heure_visite:
            details.append(("Heure", reservation.heure_visite.strftime("%H:%M")))
        details.append(("Visiteur", touriste.user.nom_complet))
        details.append((
            "Personnes",
            f"{reservation.nb_adultes} adulte(s)"
            + (f", {reservation.nb_enfants} enfant(s)" if reservation.nb_enfants else "")
        ))
        if reservation.hebergement:
            details.append(("Hébergement", reservation.hebergement.nom))
            if reservation.date_arrivee and reservation.date_depart:
                details.append((
                    "Séjour",
                    f"{reservation.date_arrivee.strftime('%d/%m')} → "
                    f"{reservation.date_depart.strftime('%d/%m/%Y')}"
                ))
        if reservation.guide:
            details.append(("Guide", reservation.guide.user.nom_complet))

        y -= 0.7 * cm
        p.setFont("Helvetica", 9)
        for label, value in details:
            p.setFillColor(HexColor(COULEUR_GRIS))
            p.drawString(1 * cm, y, f"{label} :")
            p.setFillColor(HexColor(COULEUR_TEXTE))
            p.setFont("Helvetica-Bold", 9)
            p.drawString(4 * cm, y, str(value)[:50])  # tronque pour rester sur la ligne
            p.setFont("Helvetica", 9)
            y -= 0.55 * cm

        # ===================================================
        # SECTION 4 : Tableau des lignes facturées
        # ===================================================
        y -= 0.3 * cm
        p.setFillColor(HexColor(COULEUR_TEXTE))
        p.setFont("Helvetica-Bold", 11)
        p.drawString(1 * cm, y, "💰 Détail du paiement")
        p.line(1 * cm, y - 0.15 * cm, largeur - 1 * cm, y - 0.15 * cm)
        y -= 0.6 * cm

        p.setFont("Helvetica-Bold", 8)
        p.drawString(1 * cm, y, "Désignation")
        p.drawString(8 * cm, y, "Qté")
        p.drawString(9.5 * cm, y, "P.U.")
        p.drawRightString(largeur - 1 * cm, y, "Sous-total")
        y -= 0.3 * cm
        p.line(1 * cm, y, largeur - 1 * cm, y)
        y -= 0.4 * cm

        p.setFont("Helvetica", 8)
        for ligne in reservation.lignes.all():
            p.drawString(1 * cm, y, ligne.designation[:40])
            p.drawString(8 * cm, y, str(ligne.quantite))
            p.drawString(9.5 * cm, y, f"{ligne.prix_unitaire:,.0f}".replace(',', ' '))
            p.drawRightString(largeur - 1 * cm, y, f"{ligne.sous_total:,.0f}".replace(',', ' '))
            y -= 0.45 * cm

        # Total
        y -= 0.2 * cm
        p.line(1 * cm, y, largeur - 1 * cm, y)
        y -= 0.5 * cm
        p.setFillColor(HexColor(COULEUR_PRIMARY))
        p.setFont("Helvetica-Bold", 12)
        p.drawString(1 * cm, y, "TOTAL TTC")
        p.drawRightString(
            largeur - 1 * cm, y,
            f"{reservation.montant_total:,.0f} FCFA".replace(',', ' ')
        )

        # ===================================================
        # SECTION 5 : QR Code + Conditions
        # ===================================================
        y -= 2.2 * cm

        # QR Code à gauche
        if bon.qr_code_image and hasattr(bon.qr_code_image, 'path'):
            try:
                qr_img = ImageReader(bon.qr_code_image.path)
                p.drawImage(
                    qr_img,
                    1 * cm, y - 1 * cm,
                    width=3.5 * cm, height=3.5 * cm,
                )
            except Exception as e:
                logger.warning(f"Impossible d'inclure le QR dans le PDF : {e}")

        # Texte à droite
        p.setFillColor(HexColor(COULEUR_TEXTE))
        p.setFont("Helvetica-Bold", 9)
        p.drawString(5.5 * cm, y + 2 * cm, "📱 SCANNER À L'ENTRÉE")
        p.setFont("Helvetica", 7)
        p.setFillColor(HexColor(COULEUR_GRIS))

        conditions = [
            "• Présenter ce bon (papier ou écran)",
            "• Pièce d'identité obligatoire",
            "• Bon valable uniquement à la date",
            "  indiquée",
            "• Non remboursable après visite",
        ]
        cy = y + 1.5 * cm
        for ligne_cond in conditions:
            p.drawString(5.5 * cm, cy, ligne_cond)
            cy -= 0.35 * cm

        # ===================================================
        # SECTION 6 : Pied de page
        # ===================================================
        p.setFillColor(HexColor(COULEUR_GRIS))
        p.setFont("Helvetica", 6)
        p.drawCentredString(
            largeur / 2, 0.8 * cm,
            f"Document généré le {bon.created_at.strftime('%d/%m/%Y à %H:%M')}"
            f" · tourisme-cameroun.cm · contact@tourisme-cameroun.cm"
        )

        # Finalisation
        p.showPage()
        p.save()
        buffer.seek(0)

        # Sauvegarde dans le modèle
        nom_fichier = f"bon_{reservation.numero}.pdf"
        bon.pdf_fichier.save(nom_fichier, ContentFile(buffer.getvalue()), save=False)

        return True

    except Exception as e:
        logger.error(f"Erreur génération PDF bon {bon.id} : {e}", exc_info=True)
        return False


# ============================================================
# 3. PIPELINE COMPLET (QR + PDF en une seule fois)
# ============================================================
def generer_bon_complet(bon):
    """
    Pipeline complet : génère le QR code PUIS le PDF, puis sauve le bon.

    Pédago : on encapsule les 2 appels pour que la view appelle UNE
    seule méthode plutôt que de gérer l'ordre. DRY + moins d'oublis.

    Retourne True si TOUT a réussi, False sinon.
    """
    qr_ok = generer_qr_code_image(bon.qr_code_data, bon)
    pdf_ok = generer_bon_pdf(bon) if qr_ok else False

    if qr_ok or pdf_ok:
        # Au moins une partie a réussi, on sauve les fichiers attachés
        bon.save()

    return qr_ok and pdf_ok