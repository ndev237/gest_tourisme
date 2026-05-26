"""
Génère le guide utilisateur PDF "Tourisme Cameroun".
Design éditorial : couverture pleine page, sommaire, sections numérotées,
palette assortie au design system du projet (forêt + or + sable).
"""
from pathlib import Path
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, NextPageTemplate,
    Paragraph, Spacer, PageBreak, Table, TableStyle, KeepTogether,
)
from reportlab.pdfgen import canvas as canvas_mod

# ---------- Palette assortie au design system ----------
COLOR_FORET = colors.HexColor('#0F2B1B')   # foret-900
COLOR_FORET_700 = colors.HexColor('#1F4A33')
COLOR_ACCENT = colors.HexColor('#D4A24C')  # or
COLOR_ACCENT_DARK = colors.HexColor('#B5862A')
COLOR_SABLE = colors.HexColor('#F5EFE3')   # sable-50
COLOR_SABLE_100 = colors.HexColor('#E9DEC4')
COLOR_TEXT = colors.HexColor('#1B2A1B')
COLOR_MUTED = colors.HexColor('#6B7765')
COLOR_ERROR = colors.HexColor('#B91C1C')
COLOR_INFO = colors.HexColor('#1E40AF')
COLOR_SUCCESS = colors.HexColor('#15803D')

# ---------- Styles ----------
styles = getSampleStyleSheet()


def style(name, **kw):
    parent = styles['Normal']
    s = ParagraphStyle(name=name, parent=parent)
    for k, v in kw.items():
        setattr(s, k, v)
    return s


eyebrow = style('eyebrow',
                fontName='Helvetica-Bold', fontSize=8, leading=12,
                textColor=COLOR_ACCENT_DARK, spaceAfter=4,
                tracking=2)

h1 = style('h1', fontName='Helvetica-Bold', fontSize=28, leading=34,
           textColor=COLOR_FORET, spaceBefore=4, spaceAfter=14)

h2 = style('h2', fontName='Helvetica-Bold', fontSize=18, leading=24,
           textColor=COLOR_FORET, spaceBefore=14, spaceAfter=10)

h3 = style('h3', fontName='Helvetica-Bold', fontSize=13, leading=18,
           textColor=COLOR_FORET_700, spaceBefore=10, spaceAfter=6)

body = style('body', fontName='Helvetica', fontSize=10.5, leading=15,
             textColor=COLOR_TEXT, alignment=TA_JUSTIFY, spaceAfter=8)

body_l = style('body_l', fontName='Helvetica', fontSize=10.5, leading=15,
               textColor=COLOR_TEXT, alignment=TA_LEFT, spaceAfter=8)

bullet = style('bullet', fontName='Helvetica', fontSize=10, leading=14,
               textColor=COLOR_TEXT, leftIndent=18, bulletIndent=4,
               spaceAfter=4)

mono = style('mono', fontName='Courier', fontSize=9, leading=12,
             textColor=COLOR_FORET, backColor=COLOR_SABLE_100,
             leftIndent=8, rightIndent=8, spaceBefore=4, spaceAfter=8,
             borderPadding=(6, 8, 6, 8))

caption = style('caption', fontName='Helvetica-Oblique', fontSize=9,
                leading=12, textColor=COLOR_MUTED, alignment=TA_CENTER)

footer_text = style('footer_text', fontName='Helvetica', fontSize=8,
                    textColor=COLOR_MUTED, alignment=TA_CENTER)


# ---------- Couverture custom ----------
def cover_page(canv, doc):
    """Couverture pleine page, fond forêt avec accent or."""
    width, height = A4
    # Fond forêt
    canv.setFillColor(COLOR_FORET)
    canv.rect(0, 0, width, height, fill=1, stroke=0)

    # Bande or en haut
    canv.setFillColor(COLOR_ACCENT)
    canv.rect(0, height - 8 * mm, width, 8 * mm, fill=1, stroke=0)

    # Logo monogramme tc dans cercle or
    canv.setFillColor(COLOR_ACCENT)
    canv.circle(width / 2, height - 60 * mm, 18 * mm, fill=1, stroke=0)
    canv.setFillColor(COLOR_FORET)
    canv.setFont('Helvetica-BoldOblique', 28)
    canv.drawCentredString(width / 2, height - 65 * mm, 'tc')

    # Eyebrow
    canv.setFillColor(COLOR_ACCENT)
    canv.setFont('Helvetica-Bold', 9)
    canv.drawCentredString(width / 2, height - 95 * mm,
                           'GUIDE UTILISATEUR  ·  EDITION {}'.format(date.today().year))

    # Titre principal
    canv.setFillColor(colors.white)
    canv.setFont('Helvetica-Bold', 38)
    canv.drawCentredString(width / 2, height - 115 * mm, 'Tourisme')
    canv.drawCentredString(width / 2, height - 130 * mm, 'Cameroun')

    # Sous-titre
    canv.setFillColor(colors.HexColor('#A8B5AC'))
    canv.setFont('Helvetica-Oblique', 14)
    canv.drawCentredString(width / 2, height - 148 * mm,
                           'Manuel de manipulation et de tests de la plateforme')

    # Petits accents décoratifs
    canv.setStrokeColor(COLOR_ACCENT)
    canv.setLineWidth(0.5)
    canv.line(width / 2 - 40 * mm, height - 160 * mm, width / 2 - 5 * mm, height - 160 * mm)
    canv.line(width / 2 + 5 * mm, height - 160 * mm, width / 2 + 40 * mm, height - 160 * mm)
    canv.setFillColor(COLOR_ACCENT)
    canv.setFont('Helvetica', 8)
    canv.drawCentredString(width / 2, height - 160 * mm, 'No 01')

    # Bas de page
    canv.setFillColor(colors.HexColor('#A8B5AC'))
    canv.setFont('Helvetica', 8)
    canv.drawCentredString(width / 2, 25 * mm, 'L\'AFRIQUE EN MINIATURE')

    canv.setFillColor(COLOR_ACCENT)
    canv.setFont('Helvetica-Bold', 7)
    canv.drawCentredString(width / 2, 18 * mm,
                           'INSTALLATION  ·  COMPTES  ·  PARCOURS  ·  TESTS  ·  ARCHITECTURE')

    canv.setFillColor(colors.HexColor('#A8B5AC'))
    canv.setFont('Helvetica', 8)
    canv.drawCentredString(width / 2, 11 * mm,
                           'Yaounde  ·  Douala  ·  Buea  ·  {}'.format(date.today().strftime('%d.%m.%Y')))


# ---------- Layout des autres pages ----------
def page_layout(canv, doc):
    """En-tête + pied de page sur toutes les pages internes."""
    width, height = A4

    # Header : titre court à gauche, numero de page à droite
    canv.setStrokeColor(COLOR_SABLE_100)
    canv.setLineWidth(0.5)
    canv.line(2 * cm, height - 1.8 * cm, width - 2 * cm, height - 1.8 * cm)

    canv.setFillColor(COLOR_MUTED)
    canv.setFont('Helvetica', 7.5)
    canv.drawString(2 * cm, height - 1.5 * cm, 'TOURISME CAMEROUN  ·  GUIDE UTILISATEUR')

    canv.setFillColor(COLOR_ACCENT_DARK)
    canv.setFont('Helvetica-Bold', 8)
    canv.drawRightString(width - 2 * cm, height - 1.5 * cm,
                         'No {:02d}'.format(doc.page))

    # Pied de page : ligne + copyright
    canv.line(2 * cm, 1.5 * cm, width - 2 * cm, 1.5 * cm)
    canv.setFillColor(COLOR_MUTED)
    canv.setFont('Helvetica', 7.5)
    canv.drawString(2 * cm, 1.1 * cm, 'TOURISME.CAMEROUN')
    canv.drawCentredString(width / 2, 1.1 * cm,
                           'Yaounde  ·  Cameroun')
    canv.drawRightString(width - 2 * cm, 1.1 * cm,
                         'Edition {}'.format(date.today().year))


# ---------- Composants réutilisables ----------
def callout(text, color_bg=COLOR_SABLE, color_fg=COLOR_FORET, label='ASTUCE'):
    """Bloc d'info coloré."""
    tbl = Table(
        [[Paragraph(
            '<para><font color="{}"><b>{}</b></font><br/><font color="{}">{}</font></para>'.format(
                color_fg.hexval(), label, COLOR_TEXT.hexval(), text),
            body_l,
        )]],
        colWidths=[16.5 * cm],
    )
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), color_bg),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LINEBEFORE', (0, 0), (0, -1), 3, color_fg),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    return tbl


def chapter_header(num, title):
    """En-tête de chapitre avec numéro éditorial."""
    t = Table(
        [[Paragraph(
            '<para fontSize=44 textColor="{}"><b><i>{}</i></b></para>'.format(
                COLOR_ACCENT_DARK.hexval(), num),
            ParagraphStyle('big', fontName='Helvetica-BoldOblique', fontSize=44, leading=48),
        ),
          Paragraph(
              '<para fontSize=8 textColor="{}"><b>CHAPITRE {}</b></para><para fontSize=24 textColor="{}"><b>{}</b></para>'.format(
                  COLOR_ACCENT_DARK.hexval(), num, COLOR_FORET.hexval(), title),
              ParagraphStyle('chapt', fontName='Helvetica-Bold', fontSize=24, leading=28),
          )]],
        colWidths=[3 * cm, 13.5 * cm],
    )
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('LINEBELOW', (0, 0), (-1, -1), 1, COLOR_ACCENT),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    return t


# ============================================================
# Génération du document
# ============================================================
def build(output):
    doc = BaseDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2.5 * cm, bottomMargin=2 * cm,
        title='Guide Utilisateur — Tourisme Cameroun',
        author='Tourisme Cameroun',
        subject='Manuel de manipulation et de tests',
        keywords='tourisme,cameroun,django,guide',
    )

    frame_cover = Frame(0, 0, A4[0], A4[1], id='cover',
                        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    frame_body = Frame(doc.leftMargin, doc.bottomMargin,
                       doc.width, doc.height, id='body')

    doc.addPageTemplates([
        PageTemplate(id='cover', frames=[frame_cover], onPage=cover_page),
        PageTemplate(id='inner', frames=[frame_body], onPage=page_layout),
    ])

    story = []

    # ========== COUVERTURE ==========
    story.append(NextPageTemplate('inner'))
    story.append(PageBreak())

    # ========== SOMMAIRE ==========
    story.append(Paragraph('Sommaire', h1))
    story.append(Spacer(1, 4 * mm))
    toc_data = [
        ['No', 'Chapitre', 'Page'],
        ['01', 'Presentation et objectifs', '3'],
        ['02', 'Installation et premier lancement', '4'],
        ['03', 'Comptes de demonstration', '5'],
        ['04', 'Parcours touriste — reserver une visite', '6'],
        ['05', 'Parcours gestionnaire — publier un site', '7'],
        ['06', 'Parcours guide — gerer ses missions', '8'],
        ['07', 'Parcours administrateur — moderation', '9'],
        ['08', 'Scenarios de tests manuels', '10'],
        ['09', 'Architecture technique', '12'],
        ['10', 'Depannage et FAQ', '13'],
    ]
    toc = Table(toc_data, colWidths=[1.2 * cm, 12 * cm, 1.5 * cm])
    toc.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 8),
        ('TEXTCOLOR', (0, 0), (-1, 0), COLOR_ACCENT_DARK),
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_SABLE),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 10),
        ('FONT', (0, 1), (0, -1), 'Courier-Bold', 9),
        ('FONT', (2, 1), (2, -1), 'Courier', 9),
        ('TEXTCOLOR', (0, 1), (-1, -1), COLOR_TEXT),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (2, -1), 'RIGHT'),
        ('LINEBELOW', (0, 0), (-1, 0), 1, COLOR_ACCENT),
        ('LINEBELOW', (0, 1), (-1, -2), 0.3, COLOR_SABLE_100),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
    ]))
    story.append(toc)
    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph(
        "Ce manuel decrit l'utilisation pratique de la plateforme Tourisme Cameroun, "
        "des etapes d'installation jusqu'aux scenarios de test pour la soutenance.",
        caption,
    ))
    story.append(PageBreak())

    # ========== CHAPITRE 01 ==========
    story.append(chapter_header('01', 'Presentation'))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph('Objectifs de la plateforme', h2))
    story.append(Paragraph(
        "Tourisme Cameroun est une plateforme officielle de reservation des sites touristiques "
        "du Cameroun. Elle reunit en un seul endroit le catalogue des sites, leurs disponibilites, "
        "les hebergements partenaires, et le tunnel complet de reservation et de paiement.",
        body,
    ))
    story.append(Paragraph(
        "Quatre roles utilisent la plateforme : "
        "<b>touriste</b> (decouvre et reserve), "
        "<b>gestionnaire</b> (publie ses sites), "
        "<b>guide</b> (propose ses services), "
        "<b>administrateur</b> (valide et modere). "
        "Chaque role dispose d'un tableau de bord dedie.",
        body,
    ))

    story.append(Paragraph('Stack technique', h3))
    story.append(Paragraph(
        "Backend : Django 5 (Python 3.14) avec une base SQLite en developpement. "
        "Frontend : Tailwind CSS v4 et DaisyUI v5 avec un theme custom (Cameroun). "
        "Carte : Leaflet + OpenStreetMap. "
        "Paiement : architecture Strategy pattern multi-provider (MTN MoMo, Orange Money, Stripe, manuel).",
        body,
    ))

    story.append(callout(
        "Cette plateforme est en mode <b>demonstration</b>. Les paiements sont mockes : "
        "aucun vrai prelevement n'est effectue. Toutes les notifications email/SMS sont loggees mais non envoyees.",
        color_bg=colors.HexColor('#FEF3C7'), color_fg=colors.HexColor('#B45309'),
        label='MODE DEMO',
    ))
    story.append(PageBreak())

    # ========== CHAPITRE 02 ==========
    story.append(chapter_header('02', 'Installation'))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph('Prerequis', h3))
    story.append(Paragraph('Verifier la presence des outils suivants :', body))
    for line in [
        '<b>Python 3.11+</b> (3.14 recommande)',
        '<b>Node.js 18+</b> (pour la compilation Tailwind/DaisyUI)',
        '<b>Git</b> pour cloner le depot',
    ]:
        story.append(Paragraph('• ' + line, bullet))

    story.append(Paragraph('Installation pas a pas', h3))
    story.append(Paragraph('Cloner le projet et installer les dependances :', body))
    story.append(Paragraph(
        '# 1. Cloner<br/>'
        'git clone https://github.com/votre-org/gest_tourisme.git<br/>'
        'cd gest_tourisme<br/><br/>'
        '# 2. Environnement Python<br/>'
        'python -m venv .venv<br/>'
        '.venv\\Scripts\\activate    (Windows)<br/>'
        'source .venv/bin/activate   (macOS / Linux)<br/>'
        'pip install -r requirements.txt<br/><br/>'
        '# 3. Compiler les styles Tailwind/DaisyUI<br/>'
        'cd tourisme/theme/static_src<br/>'
        'npm install<br/>'
        'npm run build<br/><br/>'
        '# 4. Initialiser la base<br/>'
        'cd ../../..<br/>'
        'cd tourisme<br/>'
        'python manage.py migrate<br/>'
        'python manage.py seed_demo --reset<br/><br/>'
        '# 5. Lancer le serveur<br/>'
        'python manage.py runserver',
        mono,
    ))

    story.append(Paragraph('Acceder a la plateforme', h3))
    story.append(Paragraph(
        "Une fois le serveur lance, ouvrir <font name='Courier'>http://127.0.0.1:8000</font> "
        "dans le navigateur. Le backoffice admin Django est accessible sur "
        "<font name='Courier'>/backoffice/</font> (createsuperuser ou compte admin de demo).",
        body,
    ))

    story.append(callout(
        "La commande <font name='Courier'><b>seed_demo --reset</b></font> vide la base puis cree : "
        "10 regions, 8 categories, 12 tags, 3 admins, 5 gestionnaires, 4 guides, 8 touristes, "
        "30 sites reels avec GPS, 1800 disponibilites, 20 reservations a differents statuts, "
        "17 paiements, 6 avis et 18 favoris. Utiliser <font name='Courier'><b>--light</b></font> pour une version reduite.",
        color_bg=COLOR_SABLE, color_fg=COLOR_ACCENT_DARK, label='SEED_DEMO',
    ))
    story.append(PageBreak())

    # ========== CHAPITRE 03 — Comptes ==========
    story.append(chapter_header('03', 'Comptes de demo'))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "Apres avoir execute <font name='Courier'>seed_demo</font>, les comptes suivants sont disponibles. "
        "Le mot de passe est le meme pour tous : <font name='Courier'><b>Demo1234!</b></font>.",
        body,
    ))
    story.append(Spacer(1, 4 * mm))

    comptes = [
        ['Role',          'Email',                'Profil de demonstration'],
        ['Administrateur', 'admin@demo.cm',        'Niveau 5 — acces complet, moderation'],
        ['Gestionnaire',   'gestionnaire@demo.cm', 'Eteki Tours SARL, statut valide'],
        ['Guide',          'guide@demo.cm',        'Yannick Etoundi, 8 ans d\'experience'],
        ['Touriste',       'touriste@demo.cm',     'Alice Dupont, touriste etranger'],
    ]
    t = Table(comptes, colWidths=[3.5 * cm, 5 * cm, 8 * cm])
    t.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 8.5),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_FORET),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 9.5),
        ('FONT', (1, 1), (1, -1), 'Courier', 9),
        ('TEXTCOLOR', (1, 1), (1, -1), COLOR_ACCENT_DARK),
        ('TEXTCOLOR', (0, 1), (-1, -1), COLOR_TEXT),
        ('BACKGROUND', (0, 1), (-1, -1), COLOR_SABLE),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COLOR_SABLE, colors.white]),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(t)

    story.append(Paragraph('Comptes additionnels', h3))
    story.append(Paragraph(
        "D'autres comptes de meme profil existent : <font name='Courier'>admin2@demo.cm</font>, "
        "<font name='Courier'>ges2@ges5@demo.cm</font>, <font name='Courier'>guide2@guide4@demo.cm</font>, "
        "<font name='Courier'>tou2@tou8@demo.cm</font>. Utiles pour tester les interactions entre utilisateurs.",
        body,
    ))

    story.append(callout(
        "Pour vous deconnecter, cliquer sur l'avatar en haut a droite puis sur le bouton <b>Deconnexion</b>. "
        "Le bouton declenche un POST securise (CSRF) qui invalide bien la session. "
        "Un simple GET sur l'URL de deconnexion ne deconnecte pas (volontaire, securite).",
        color_bg=colors.HexColor('#E0F2FE'), color_fg=COLOR_INFO, label='SECURITE',
    ))
    story.append(PageBreak())

    # ========== CHAPITRE 04 — Touriste ==========
    story.append(chapter_header('04', 'Parcours touriste'))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "Le touriste est l'utilisateur final. Il decouvre les sites, reserve et paie. "
        "Son parcours complet de bout en bout passe par 6 etapes.",
        body,
    ))

    etapes = [
        ('Explorer', "Page d'accueil et catalogue. Filtrer par region, categorie, prix, accessibilite PMR."),
        ('Choisir', "Ouvrir la fiche d'un site, lire la description, regarder la galerie, consulter les avis."),
        ('Mettre en favori', "Cliquer sur le coeur en haut de la fiche (besoin d'etre connecte)."),
        ('Reserver', "Bouton <b>Reserver maintenant</b>. Wizard 3 etapes : dates et personnes, options, recap."),
        ('Payer', "Choisir un moyen (Mobile Money, carte, especes). En mode demo, cliquer <b>Simuler paiement reussi</b>."),
        ('Recevoir le bon', "QR Code genere automatiquement. Le QR est aussi telechargeable en PDF."),
    ]
    for n, (titre, desc) in enumerate(etapes, 1):
        story.append(Paragraph(
            '<b><font color="{}">{:02d}.</font> {}</b>  —  {}'.format(
                COLOR_ACCENT_DARK.hexval(), n, titre, desc),
            body_l,
        ))

    story.append(Paragraph("Apres la visite", h3))
    story.append(Paragraph(
        "Quand l'administrateur passe le statut de la reservation a <b>Terminee</b>, "
        "un bouton <b>Laisser un avis</b> apparait sur la fiche de la reservation. "
        "L'avis passe en moderation et devient public sous 24 h.",
        body,
    ))

    story.append(callout(
        "<b>Regle metier importante :</b> un touriste ne peut laisser un avis que si "
        "(1) il a une reservation au statut <b>terminee</b> sur le site, et "
        "(2) il n'a pas deja d'avis sur cette reservation. C'est garantit par la "
        "OneToOne sur le modele <font name='Courier'>Avis.reservation</font>.",
        color_bg=COLOR_SABLE, color_fg=COLOR_FORET, label='ANTI-FRAUDE',
    ))
    story.append(PageBreak())

    # ========== CHAPITRE 05 — Gestionnaire ==========
    story.append(chapter_header('05', 'Parcours gestionnaire'))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "Le gestionnaire est le propriete ou le responsable d'un site touristique. Il s'inscrit, "
        "se fait valider par un admin, puis publie ses sites et gere ses reservations.",
        body,
    ))

    story.append(Paragraph("Du compte au premier site", h3))
    story.append(Paragraph(
        "L'inscription du gestionnaire necessite un numero de registre de commerce. "
        "Le compte est cree en statut <b>en_attente</b> et le gestionnaire ne peut "
        "rien publier tant qu'un administrateur ne l'a pas valide. "
        "Apres validation, le tableau de bord debloque toutes les fonctionnalites.",
        body,
    ))

    story.append(Paragraph("Cycle d'un site", h3))
    cycle = [
        ('Creer', 'Ajouter un site via le wizard 3 etapes (infos, tarifs, GPS).'),
        ('Photos', 'Telecharger 4 a 10 photos. La premiere est designee photo principale.'),
        ('Hebergements', 'Lier 0 a N hebergements (hotels, lodges) avec etoiles et prix.'),
        ('Disponibilites', 'Configurer le calendrier (places restantes par jour ; jours fermes).'),
        ('Publier', 'Bascule on/off sur la fiche pour publier ou retirer du catalogue.'),
        ('Statistiques', "Suivre les vues, reservations, revenus et notes recus sur le dashboard."),
    ]
    for n, (titre, desc) in enumerate(cycle, 1):
        story.append(Paragraph(
            '<b><font color="{}">{:02d}.</font> {}</b>  —  {}'.format(
                COLOR_ACCENT_DARK.hexval(), n, titre, desc),
            body_l,
        ))

    story.append(Paragraph("Repondre aux avis", h3))
    story.append(Paragraph(
        "Le gestionnaire peut repondre publiquement a chaque avis sur ses sites. "
        "La reponse apparait directement sous l'avis original sur la fiche publique du site. "
        "Une reponse argumentee, meme apres un mauvais avis, ameliore la perception du serieux du gestionnaire.",
        body,
    ))
    story.append(PageBreak())

    # ========== CHAPITRE 06 — Guide ==========
    story.append(chapter_header('06', 'Parcours guide'))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "Le guide touristique propose ses services d'accompagnement. Il est rattache "
        "a aucun site en particulier mais peut etre selectionne lors d'une reservation "
        "via l'option <b>Avec guide</b> du wizard.",
        body,
    ))

    story.append(Paragraph("Fiche professionnelle", h3))
    story.append(Paragraph(
        "Le guide renseigne sa biographie, son tarif journalier (FCFA), ses annees d'experience, "
        "et son numero de licence professionnelle. Comme pour le gestionnaire, le compte doit etre "
        "valide par un admin avant publication.",
        body,
    ))

    story.append(Paragraph("Gestion de la disponibilite", h3))
    story.append(Paragraph(
        "Sur son tableau de bord, le guide bascule un toggle <b>Disponible pour de nouvelles missions</b>. "
        "Quand il est sur <b>off</b>, il n'apparait plus dans le selecteur du wizard de reservation. "
        "Quand des touristes le selectionnent, il recoit une notification dans la cloche du navbar.",
        body,
    ))

    story.append(callout(
        "Les guides ne gerent pas les sites — c'est le role du gestionnaire. "
        "Si un guide veut publier ses propres sites, il faut creer un compte gestionnaire separe.",
        color_bg=colors.HexColor('#FEF3C7'), color_fg=colors.HexColor('#B45309'),
        label='DISTINCTION',
    ))
    story.append(PageBreak())

    # ========== CHAPITRE 07 — Admin ==========
    story.append(chapter_header('07', 'Parcours administrateur'))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "L'administrateur joue trois roles : <b>validation</b> (gestionnaires et guides), "
        "<b>moderation</b> (avis signales ou en attente), et <b>supervision</b> (KPI globaux, paiements, "
        "remboursements).",
        body,
    ))

    story.append(Paragraph("Validation des comptes pros", h3))
    story.append(Paragraph(
        "Sur le tableau de bord admin, la section <b>Validations en attente</b> liste les nouveaux "
        "gestionnaires et guides. Chaque ligne a un bouton ✓ et un bouton ×. L'approbation ouvre "
        "immediatement les fonctionnalites au compte. Le rejet doit etre accompagne d'un motif.",
        body,
    ))

    story.append(Paragraph("Moderation des avis", h3))
    story.append(Paragraph(
        "La page <b>Moderation</b> (/avis/admin/moderation/) liste les avis a examiner — soit "
        "en attente (statut par defaut), soit signales par des utilisateurs (5+ signalements declenchent "
        "un masquage automatique). Pour chaque avis : <b>approuver</b> (publication immediate + recalcul "
        "de la note du site) ou <b>rejeter</b> avec motif (visible par l'auteur).",
        body,
    ))

    story.append(Paragraph("Remboursements", h3))
    story.append(Paragraph(
        "Sur la page <b>Paiements</b>, chaque transaction reussie peut etre remboursee. Le formulaire "
        "permet un montant partiel (max = montant initial), un motif obligatoire et une checkbox de "
        "confirmation. Le remboursement cree une transaction de type <b>remboursement</b> liee au paiement source.",
        body,
    ))

    story.append(callout(
        "Le backoffice Django (<font name='Courier'>/backoffice/</font>) reste disponible pour les "
        "operations sensibles : creer un super-admin, editer un modele en CRUD complet, voir l'audit log.",
        color_bg=COLOR_SABLE, color_fg=COLOR_FORET, label='BACKOFFICE',
    ))
    story.append(PageBreak())

    # ========== CHAPITRE 08 — Tests ==========
    story.append(chapter_header('08', 'Scenarios de tests'))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "Voici les parcours a derouler pour valider que tout fonctionne avant la soutenance. "
        "Chaque scenario commence apres execution de <font name='Courier'>seed_demo --reset</font>.",
        body,
    ))

    def scenario(num, titre, etapes):
        elems = []
        elems.append(Paragraph(
            '<b><font color="{}" size="11">SCENARIO {}</font></b>  <font color="{}">{}</font>'.format(
                COLOR_ACCENT_DARK.hexval(), num, COLOR_FORET.hexval(), titre),
            body_l,
        ))
        for i, e in enumerate(etapes, 1):
            elems.append(Paragraph('  {}.  {}'.format(i, e), bullet))
        elems.append(Spacer(1, 4 * mm))
        return KeepTogether(elems)

    story.append(scenario('01', 'Reservation complete bout en bout', [
        'Se connecter en tant que <b>touriste@demo.cm</b>.',
        'Cliquer sur <b>Sites</b> puis ouvrir un site (ex. Plages de Kribi).',
        'Cliquer sur <b>Reserver maintenant</b>.',
        'Wizard etape 1 : choisir une date dans les 60 jours, mettre 2 adultes + 1 enfant.',
        'Wizard etape 2 : sans hebergement ni guide. Wizard etape 3 : valider.',
        'Choisir <b>MTN Mobile Money</b>, entrer un numero camerounais.',
        'Sur la page d\'attente, cliquer <b>Simuler paiement reussi</b>.',
        'Verifier la presence du QR Code et la possibilite de telecharger le bon PDF.',
        'Aller dans <b>Mes reservations</b> : la reservation est en statut <b>Confirmee</b>.',
        'Verifier la cloche du navbar : 2 notifications (reservation creee + paiement reussi).',
    ]))

    story.append(scenario('02', 'Validation d\'un gestionnaire par un admin', [
        'Creer un nouveau compte gestionnaire via <b>Inscription</b> (type gestionnaire).',
        'Se deconnecter, se reconnecter en <b>admin@demo.cm</b>.',
        'Verifier que le nouveau gestionnaire apparait dans <b>Validations en attente</b> du dashboard.',
        'Cliquer ✓ pour valider.',
        'Se reconnecter en tant que ce gestionnaire — le dashboard doit maintenant proposer <b>+ Nouveau site</b>.',
    ]))

    story.append(scenario('03', 'Moderation d\'un avis', [
        'Se connecter en <b>touriste@demo.cm</b>.',
        "Aller sur une reservation deja terminee (le seed en cree quelques-unes).",
        'Cliquer <b>Laisser un avis</b>, mettre 4 etoiles, titre + 30 caracteres de commentaire.',
        'Verifier que l\'avis apparait dans <b>Mes avis</b> avec statut <b>en moderation</b>.',
        'Se reconnecter en <b>admin@demo.cm</b> et ouvrir <b>Moderation des avis</b>.',
        'Approuver l\'avis. Verifier qu\'il devient visible sur la fiche publique du site.',
    ]))

    story.append(scenario('04', 'Scan QR a l\'entree du site', [
        'Avoir une reservation confirmee sur un site. Telecharger son bon PDF.',
        'Se connecter en gestionnaire du site et aller dans <b>Scanner un QR</b>.',
        'Avec un autre device (ou en photo), presenter le QR du PDF a la camera.',
        'Verifier que la page bascule sur <b>Entree validee</b> avec le recap (visiteur, nb personnes, heure).',
    ]))
    story.append(PageBreak())

    story.append(scenario('05', 'Remboursement d\'un paiement', [
        'Se connecter en <b>admin@demo.cm</b>, aller dans <b>Paiements</b>.',
        'Choisir un paiement <b>reussi</b> recent, cliquer <b>Rembourser</b>.',
        'Saisir un montant partiel (par exemple 50% du montant initial) et un motif > 10 caracteres.',
        'Cocher la confirmation et soumettre.',
        'Verifier qu\'une nouvelle ligne de type <b>Remb.</b> apparait dans le tableau.',
        'Verifier dans le statut de la reservation : passage a <b>Annulee</b> + notification au touriste.',
    ]))

    story.append(scenario('06', 'Notifications temps reel (cloche navbar)', [
        'Se connecter en touriste, ouvrir un site et creer une reservation.',
        'Sans rafraichir la page, observer la cloche : un badge rouge avec le compteur apparait.',
        'Cliquer sur la cloche : un dropdown affiche les 5 dernieres notifications non lues.',
        'Cliquer sur une notification : redirection vers la fiche concernee, le compteur diminue.',
        'Verifier la page <b>/notifications/</b> avec les filtres (toutes / non lues / lues).',
    ]))

    story.append(scenario('07', 'Recherche et filtres du catalogue', [
        "Sur <b>/sites/</b>, taper 'Kribi' dans la barre de recherche → seuls les sites de Kribi apparaissent.",
        'Filtrer par <b>Region = Sud</b> puis ajouter <b>Categorie = Plage</b>.',
        'Verifier que l\'URL contient bien les querystrings (partage de lien possible).',
        'Tester le filtre <b>Accessible PMR</b> et <b>Avec hebergement</b>.',
        'Cliquer sur la pagination — les filtres doivent etre preserves.',
    ]))

    story.append(scenario('08', 'Carte interactive Leaflet', [
        'Aller sur <b>/carte/</b>. Verifier que les markers couvrent tout le pays.',
        'Cliquer sur un marker : popup avec photo, categorie, note et bouton <b>Decouvrir</b>.',
        'Utiliser le filtre <b>Region</b> de la sidebar : seuls les sites de cette region restent.',
        'Cliquer <b>Centrer sur ma position</b> : autoriser la geolocalisation du navigateur.',
        "Verifier que la liste laterale des sites visibles correspond au filtre actif.",
    ]))
    story.append(PageBreak())

    # ========== CHAPITRE 09 — Architecture ==========
    story.append(chapter_header('09', 'Architecture technique'))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Apps Django", h3))
    apps_data = [
        ['App', 'Role', 'Modeles cles'],
        ['compte', 'Auth + profils', 'User, Touriste, Gestionnaire, Guide, Administrateur'],
        ['catalogue', 'Sites + categories + hebergements + dispos', 'SiteTouristique, Categorie, Tag, Hebergement, PhotoSite, Disponibilite'],
        ['localisation', 'Geographie', 'Region, Localisation'],
        ['reservation', 'Reservations + bons QR', 'Reservation, LigneReservation, BonReservation'],
        ['paiements', 'Tunnel paiement + remboursements', 'Paiement, MoyenPaiement'],
        ['reviews', 'Avis + favoris + moderation', 'Avis, Favori, UtiliteAvis'],
        ['notifications', 'Notifications systeme + cloche', 'Notification, Message, PreferencesNotification'],
        ['core', 'Utilitaires transverses', 'AuditLog, TimestampedModel'],
    ]
    t = Table(apps_data, colWidths=[2.5 * cm, 4.5 * cm, 9.5 * cm])
    t.setStyle(TableStyle([
        ('FONT', (0, 0), (-1, 0), 'Helvetica-Bold', 8.5),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_FORET),
        ('FONT', (0, 1), (-1, -1), 'Helvetica', 8.5),
        ('FONT', (0, 1), (0, -1), 'Courier-Bold', 9),
        ('TEXTCOLOR', (0, 1), (0, -1), COLOR_ACCENT_DARK),
        ('TEXTCOLOR', (1, 1), (-1, -1), COLOR_TEXT),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [COLOR_SABLE, colors.white]),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    story.append(t)

    story.append(Paragraph("Patterns et choix techniques", h3))
    story.append(Paragraph(
        "<b>Strategy pattern</b> pour les providers de paiement (MTN, Orange, Stripe, Manuel). "
        "<b>OneToOne</b> Avis ↔ Reservation pour empecher les faux avis. "
        "<b>FK PROTECT</b> sur Region et Categorie : impossible de supprimer une categorie utilisee. "
        "<b>Signaux post_save</b> Django pour les notifications automatiques. "
        "<b>UUID</b> comme PK sur User, Reservation et SiteTouristique pour empecher l'enumeration.",
        body,
    ))

    story.append(Paragraph("Securite", h3))
    story.append(Paragraph(
        "Tous les formulaires utilisent le token CSRF. La deconnexion est exclusivement en POST. "
        "Les vues sont protegees par <font name='Courier'>@login_required</font> et "
        "<font name='Courier'>@user_passes_test</font> selon le role. Les paiements n'enregistrent jamais "
        "ni numero de carte ni code PIN — confirmation 100% cote provider.",
        body,
    ))
    story.append(PageBreak())

    # ========== CHAPITRE 10 — FAQ ==========
    story.append(chapter_header('10', 'Depannage et FAQ'))
    story.append(Spacer(1, 6 * mm))

    faqs = [
        ('Le bouton Deconnexion ne fonctionne pas',
         "C\'est volontaire si vous cliquez sur un lien GET : la vue n\'accepte que POST (securite CSRF). "
         "Le navbar utilise un formulaire POST avec token CSRF. Si vous developpez une page custom, "
         "utilisez bien <font name='Courier'>&lt;form method=\"post\"&gt;</font>."),

        ('Aucun site n\'apparait sur la home',
         "La base est probablement vide. Lancer <font name='Courier'>python manage.py seed_demo --reset</font>. "
         "Verifier ensuite que <font name='Courier'>SiteTouristique.est_publie = True</font> et que le gestionnaire "
         "associe a un <font name='Courier'>statut_validation = 'valide'</font>."),

        ('Les images des sites ne s\'affichent pas',
         "Les images sont generees aleatoirement par le seed mais le seed n\'uploade pas de fichier image — "
         "seuls les modeles sont crees. Pour ajouter de vraies photos, utiliser le backoffice Django ou "
         "l\'interface gestionnaire <b>Photos</b> apres connexion."),

        ('Le CSS semble cassse',
         "Si <font name='Courier'>theme/static/css/dist/styles.css</font> n\'existe pas, executer "
         "<font name='Courier'>npm run build</font> dans <font name='Courier'>tourisme/theme/static_src/</font>. "
         "En production, executer aussi <font name='Courier'>python manage.py collectstatic</font>."),

        ('La carte Leaflet ne s\'affiche pas',
         "Verifier que JavaScript est active. La librairie Leaflet est chargee depuis unpkg.com — verifier la connexion internet. "
         "Les tuiles utilisees viennent de Carto Voyager (gratuites). En cas de panne, basculer sur OpenStreetMap brut."),

        ('Comment creer un super-admin Django ?',
         "Dans le terminal : <font name='Courier'>python manage.py createsuperuser</font>. Renseigner email "
         "et mot de passe. Le compte aura acces a <font name='Courier'>/backoffice/</font> en plus du frontoffice."),

        ('Les notifications ne s\'envoient pas par email',
         "C\'est volontaire en mode demo. Les signaux <font name='Courier'>post_save</font> creent les notifications "
         "in-app (visibles dans la cloche), mais l\'envoi email/SMS reel necessite de brancher un worker "
         "(Celery + Mailgun / Twilio). C\'est un TODO documente dans <font name='Courier'>notifications/signals.py</font>."),
    ]
    for q, a in faqs:
        story.append(Paragraph('<b>' + q + '</b>', h3))
        story.append(Paragraph(a, body))

    story.append(Spacer(1, 1 * cm))
    story.append(callout(
        "Pour signaler un bug ou demander de l\'aide : "
        "<font name='Courier'>support@tourisme-cameroun.cm</font>. "
        "Notre equipe vous repond sous 24 h ouvrees.",
        color_bg=COLOR_SABLE, color_fg=COLOR_FORET, label='SUPPORT',
    ))

    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph(
        '<para alignment="center" textColor="{}" fontSize="8">— FIN DU GUIDE —</para>'.format(
            COLOR_MUTED.hexval()),
        caption,
    ))
    story.append(Paragraph(
        '<para alignment="center" textColor="{}" fontSize="9"><i>Bonne demonstration !</i></para>'.format(
            COLOR_ACCENT_DARK.hexval()),
        caption,
    ))

    doc.build(story)


if __name__ == '__main__':
    out = Path('Guide_Utilisateur_Tourisme_Cameroun.pdf')
    build(out)
    print('OK ->', out.resolve())
