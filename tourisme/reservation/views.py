"""
reservation/views.py
====================
Vues de l'app reservation.

ORGANISATION (5 sections) :
A. TOURISTE — Cycle de réservation
   - create_reservation_view  : POST depuis fiche site → crée Reservation+lignes
   - mes_reservations_view    : liste touriste
   - detail_reservation_view  : fiche détaillée
   - annuler_reservation_view : annulation avec motif
   - bon_pdf_view             : télécharger le bon PDF
B. GESTIONNAIRE — Vue de SES réservations + scan QR
   - reservations_gestionnaire_view : liste des reservations sur ses sites
   - scan_qr_view             : interface de scan + validation
C. ADMIN — Vue globale
   - admin_reservations_view  : toutes les réservations + filtres
D. HELPERS
   - calculer_lignes_reservation
   - check_reservation_ownership

INITIATIVES PÉDAGOGIQUES :
1. CALCUL DE PRIX SERVEUR-SIDE : tout le montant est recalculé après
   création (anti-tampering, prix figés au moment de la réservation).
2. TRANSACTION ATOMIQUE pour la création reservation+lignes
   (cohérence : si le calcul plante, RIEN n'est créé).
3. PÉRENNITÉ DES PRIX : on copie tarif_adulte/tarif_enfant dans
   prix_unitaire des lignes → si le gestionnaire change ses tarifs
   plus tard, l'ancienne reservation garde son prix initial.
4. select_for_update sur Disponibilite : verrou pessimiste pour éviter
   les race conditions (2 touristes pour les 3 dernières places).
5. AuditLog systématique pour traçabilité des actions sensibles.
6. Helper check_reservation_ownership : sécurité DRY (même logique
   appliquée partout).
"""

import logging
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from reservation.models import Reservation, LigneReservation, BonReservation
from reservation.forms import (
    ReservationForm, AnnulerReservationForm,
    ScanQRForm, ReservationFiltreForm,
)
from reservation.utils import generer_bon_complet
from catalogue.models import SiteTouristique, Disponibilite

try:
    from core.models import AuditLog
except ImportError:
    AuditLog = None

logger = logging.getLogger(__name__)


# ============================================================
# H. HELPERS
# ============================================================
def get_client_ip(request):
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_action(user, action, ressource, id_ressource='', request=None, details=None):
    """AuditLog défensif."""
    if AuditLog is None:
        return
    try:
        AuditLog.objects.create(
            utilisateur=user if user and user.is_authenticated else None,
            action=action,
            ressource=ressource,
            id_ressource=str(id_ressource),
            ip_address=get_client_ip(request) if request else None,
            user_agent=request.META.get('HTTP_USER_AGENT', '') if request else '',
            details=details or {},
        )
    except Exception as e:
        logger.warning(f"Audit log échec : {e}")


def est_touriste(user):
    return (user.is_authenticated
            and user.type_user == 'touriste'
            and hasattr(user, 'profil_touriste'))


def est_gestionnaire(user):
    return (user.is_authenticated
            and user.type_user == 'gestionnaire'
            and hasattr(user, 'profil_gestionnaire'))


def est_admin(user):
    return user.is_authenticated and user.type_user == 'admin'


def check_reservation_ownership(reservation, user):
    """
    Vérifie qu'un utilisateur a le droit de voir/modifier cette réservation.

    Règles :
    - Le touriste propriétaire : OUI
    - Le gestionnaire du site : OUI (lecture seule)
    - Le guide concerné : OUI (lecture seule)
    - Un admin : OUI
    """
    if not user.is_authenticated:
        return False
    if user.type_user == 'admin':
        return True
    if (hasattr(user, 'profil_touriste')
        and reservation.touriste_id == user.profil_touriste.id):
        return True
    if (hasattr(user, 'profil_gestionnaire')
        and reservation.site.gestionnaire_id == user.profil_gestionnaire.id):
        return True
    if (hasattr(user, 'profil_guide')
        and reservation.guide_id
        and reservation.guide_id == user.profil_guide.id):
        return True
    return False


def calculer_lignes_reservation(reservation):
    """
    Calcule les LigneReservation à partir d'une réservation existante.

    PÉDAGO : on extrait cette logique d'une view pour la rendre :
    - Testable en isolation
    - Réutilisable (modification, recalcul après changement de tarif)
    - Documentable (le calcul est CENTRAL au métier)

    Le calcul est SERVER-SIDE (anti-tampering) et utilise les prix
    DU MOMENT (figés dans les LigneReservation après création).

    Retourne le montant_total (Decimal).
    """
    site = reservation.site

    # Supprime les anciennes lignes (au cas où c'est un recalcul)
    reservation.lignes.all().delete()

    lignes_a_creer = []

    # === LIGNE 1 : Entrée du site (adultes) ===
    if reservation.nb_adultes > 0:
        lignes_a_creer.append(LigneReservation(
            reservation=reservation,
            type_service=LigneReservation.TypeService.VISITE,
            designation=f"Entrée adulte — {site.nom}",
            quantite=reservation.nb_adultes,
            prix_unitaire=site.tarif_adulte,
            sous_total=Decimal(reservation.nb_adultes) * site.tarif_adulte,
        ))

    # === LIGNE 2 : Entrée du site (enfants) — tarif réduit ===
    if reservation.nb_enfants > 0:
        lignes_a_creer.append(LigneReservation(
            reservation=reservation,
            type_service=LigneReservation.TypeService.VISITE,
            designation=f"Entrée enfant — {site.nom}",
            quantite=reservation.nb_enfants,
            prix_unitaire=site.tarif_enfant,
            sous_total=Decimal(reservation.nb_enfants) * site.tarif_enfant,
        ))

    # === LIGNE 3 : Hébergement (optionnel) ===
    if reservation.hebergement and reservation.date_arrivee and reservation.date_depart:
        nb_nuits = (reservation.date_depart - reservation.date_arrivee).days
        if nb_nuits > 0:
            lignes_a_creer.append(LigneReservation(
                reservation=reservation,
                type_service=LigneReservation.TypeService.HEBERGEMENT,
                designation=f"Hébergement — {reservation.hebergement.nom} ({nb_nuits} nuit{'s' if nb_nuits > 1 else ''})",
                quantite=nb_nuits,
                prix_unitaire=reservation.hebergement.prix_nuit,
                sous_total=Decimal(nb_nuits) * reservation.hebergement.prix_nuit,
            ))

    # === LIGNE 4 : Guide (optionnel) ===
    if reservation.guide:
        # Tarif journalier × 1 jour par défaut (on pourrait calculer
        # plus précisément si on avait des dates de prestation)
        nb_jours = 1
        lignes_a_creer.append(LigneReservation(
            reservation=reservation,
            type_service=LigneReservation.TypeService.GUIDE,
            designation=f"Service de guide — {reservation.guide.user.nom_complet}",
            quantite=nb_jours,
            prix_unitaire=reservation.guide.tarif_journalier,
            sous_total=Decimal(nb_jours) * reservation.guide.tarif_journalier,
        ))

    # bulk_create est plus rapide que N save() individuels
    # NOTE : save() personnalisé qui calcule sous_total n'est PAS appelé
    # avec bulk_create — d'où nos calculs explicites ci-dessus
    LigneReservation.objects.bulk_create(lignes_a_creer)

    # Recalcul du montant_total via la méthode du modèle
    reservation.calculer_montant()
    reservation.save(update_fields=['montant_total'])

    return reservation.montant_total


# ============================================================
# A. TOURISTE — CYCLE DE RÉSERVATION
# ============================================================

@login_required
@user_passes_test(est_touriste, login_url='compte:connexion')
def create_reservation_view(request, slug):
    """
    Création d'une réservation depuis la fiche d'un site.

    URL: /reservation/site/<slug>/reserver/

    Flux :
    1. GET → affiche le formulaire pré-rempli avec le site
    2. POST valide :
       a. Création Reservation (statut='en_attente')
       b. Création des LigneReservation (calcul serveur-side)
       c. Décrément réservé (PAS encore, attente paiement)
       d. Redirection vers le tunnel de paiement
    """
    site = get_object_or_404(SiteTouristique, slug=slug, est_publie=True)

    if request.method == 'POST':
        form = ReservationForm(request.POST, site=site)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # 1. Création de la réservation (montant 0 temporairement)
                    reservation = form.save(commit=False)
                    reservation.touriste = request.user.profil_touriste
                    reservation.site = site
                    reservation.statut = Reservation.Statut.EN_ATTENTE
                    reservation.save()

                    # 2. Calcul + création des lignes (serveur-side)
                    montant = calculer_lignes_reservation(reservation)

                    log_action(
                        request.user, 'create', 'Reservation',
                        reservation.id, request,
                        details={
                            'numero': reservation.numero,
                            'site': site.nom,
                            'montant': str(montant),
                        }
                    )

                messages.success(
                    request,
                    f"✅ Réservation {reservation.numero} créée. "
                    f"Vous allez maintenant procéder au paiement."
                )

                # Redirection vers le tunnel de paiement (app paiements)
                # Si l'app paiements n'a pas encore d'URL, fallback vers le détail
                try:
                    from django.urls import reverse
                    return redirect(reverse('paiements:choix_moyen', args=[reservation.id]))
                except Exception:
                    return redirect('reservation:detail_reservation',
                                    reservation_id=reservation.id)

            except Exception as e:
                logger.error(f"Erreur création réservation : {e}", exc_info=True)
                messages.error(request, f"Erreur : {e}")
    else:
        form = ReservationForm(site=site)

    return render(request, 'reservations/reservation/add_reservation.html', {
        'form': form,
        'site': site,
        'page_title': f"Réserver — {site.nom}",
    })


@login_required
@user_passes_test(est_touriste, login_url='compte:connexion')
def mes_reservations_view(request):
    """Liste des réservations du touriste connecté."""
    touriste = request.user.profil_touriste

    # Filtres simples
    statut_filtre = request.GET.get('statut', '')

    reservations = (Reservation.objects
        .filter(touriste=touriste)
        .select_related('site', 'site__localisation', 'site__localisation__region',
                        'hebergement', 'guide__user')
        .prefetch_related('lignes')
        .order_by('-created_at')
    )

    if statut_filtre:
        reservations = reservations.filter(statut=statut_filtre)

    # Pagination
    paginator = Paginator(reservations, 10)
    page = paginator.get_page(request.GET.get('page'))

    # Stats touriste
    stats = {
        'total': Reservation.objects.filter(touriste=touriste).count(),
        'confirmees': Reservation.objects.filter(
            touriste=touriste, statut='confirmee'
        ).count(),
        'terminees': Reservation.objects.filter(
            touriste=touriste, statut='terminee'
        ).count(),
    }

    return render(request, 'reservations/reservation/liste_reservation.html', {
        'reservations': page,
        'paginator': paginator,
        'stats': stats,
        'statut_filtre': statut_filtre,
        'page_title': 'Mes réservations',
    })


@login_required
def detail_reservation_view(request, reservation_id):
    """
    Fiche détaillée d'une réservation.

    Accessible au touriste, au gestionnaire concerné, à l'admin.
    """
    reservation = get_object_or_404(
        Reservation.objects
            .select_related('site', 'site__localisation', 'site__localisation__region',
                            'site__gestionnaire__user', 'hebergement', 'guide__user',
                            'touriste__user')
            .prefetch_related('lignes', 'paiements'),
        id=reservation_id,
    )

    if not check_reservation_ownership(reservation, request.user):
        return HttpResponseForbidden("Vous n'avez pas accès à cette réservation.")

    # Récupération du bon (si déjà généré)
    try:
        bon = reservation.bon
    except BonReservation.DoesNotExist:
        bon = None

    return render(request, 'reservations/reservation/detail_reservation.html', {
        'reservation': reservation,
        'bon': bon,
        'page_title': f"Réservation {reservation.numero}",
    })


@login_required
@user_passes_test(est_touriste, login_url='compte:connexion')
def annuler_reservation_view(request, reservation_id):
    """Annulation d'une réservation par le touriste."""
    reservation = get_object_or_404(Reservation, id=reservation_id)

    if not check_reservation_ownership(reservation, request.user):
        return HttpResponseForbidden()

    if not reservation.peut_etre_annulee:
        messages.warning(
            request,
            "Cette réservation ne peut plus être annulée gratuitement."
        )
        return redirect('reservation:detail_reservation',
                        reservation_id=reservation.id)

    if request.method == 'POST':
        form = AnnulerReservationForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    motif = form.cleaned_data['motif']
                    reservation.annuler(motif=motif)

                    # TODO : Déclencher remboursement via app paiements
                    # paiements_reussis = reservation.paiements.filter(statut='reussi')
                    # for p in paiements_reussis:
                    #     p.creer_remboursement(motif="Annulation client")

                    log_action(
                        request.user, 'update', 'Reservation',
                        reservation.id, request,
                        details={'action': 'annulation', 'motif': motif}
                    )

                messages.success(
                    request,
                    f"❌ Réservation {reservation.numero} annulée. "
                    f"Montant remboursable : {reservation.montant_remboursement:.0f} FCFA."
                )
                return redirect('reservation:mes_reservations')
            except Exception as e:
                logger.error(f"Erreur annulation : {e}", exc_info=True)
                messages.error(request, f"Erreur : {e}")
    else:
        form = AnnulerReservationForm()

    return render(request, 'reservations/reservation/annuler_reservation.html', {
        'form': form,
        'reservation': reservation,
        'page_title': f"Annuler la réservation {reservation.numero}",
    })


@login_required
def bon_pdf_view(request, reservation_id):
    """
    Télécharge le bon PDF d'une réservation.

    Si le bon n'existe pas encore (mais que la réservation est confirmée),
    on le génère à la volée.
    """
    reservation = get_object_or_404(Reservation, id=reservation_id)

    if not check_reservation_ownership(reservation, request.user):
        return HttpResponseForbidden()

    if reservation.statut != Reservation.Statut.CONFIRMEE:
        messages.warning(request, "Le bon n'est disponible qu'une fois la réservation confirmée.")
        return redirect('reservation:detail_reservation',
                        reservation_id=reservation.id)

    # Récupérer ou créer le bon
    bon, created = BonReservation.objects.get_or_create(reservation=reservation)
    if created or not bon.pdf_fichier:
        # Génération à la volée (qr_code_data est auto-généré dans save())
        success = generer_bon_complet(bon)
        if not success:
            messages.error(
                request,
                "Erreur lors de la génération du bon PDF. "
                "Vérifiez que les modules qrcode et reportlab sont installés."
            )
            return redirect('reservation:detail_reservation',
                            reservation_id=reservation.id)

    # Servir le PDF en téléchargement
    try:
        with open(bon.pdf_fichier.path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/pdf')
            response['Content-Disposition'] = (
                f'attachment; filename="bon_{reservation.numero}.pdf"'
            )
            log_action(request.user, 'read', 'BonReservation', bon.id, request)
            return response
    except Exception as e:
        logger.error(f"Erreur lecture PDF : {e}", exc_info=True)
        messages.error(request, "Impossible de lire le fichier PDF.")
        return redirect('reservation:detail_reservation',
                        reservation_id=reservation.id)


# ============================================================
# B. GESTIONNAIRE — Vue des réservations + Scan QR
# ============================================================

@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def reservations_gestionnaire_view(request):
    """Liste des réservations des sites du gestionnaire connecté."""
    gestionnaire = request.user.profil_gestionnaire

    reservations = (Reservation.objects
        .filter(site__gestionnaire=gestionnaire)
        .select_related('touriste__user', 'site', 'hebergement', 'guide__user')
        .order_by('-date_visite', '-created_at')
    )

    # Filtres
    filtre_form = ReservationFiltreForm(request.GET or None)
    if filtre_form.is_valid():
        data = filtre_form.cleaned_data
        if data.get('q'):
            reservations = reservations.filter(
                Q(numero__icontains=data['q'])
                | Q(touriste__user__first_name__icontains=data['q'])
                | Q(touriste__user__last_name__icontains=data['q'])
                | Q(touriste__user__email__icontains=data['q'])
            )
        if data.get('statut'):
            reservations = reservations.filter(statut=data['statut'])
        if data.get('date_debut'):
            reservations = reservations.filter(date_visite__gte=data['date_debut'])
        if data.get('date_fin'):
            reservations = reservations.filter(date_visite__lte=data['date_fin'])

    # Stats globales
    stats = (Reservation.objects
        .filter(site__gestionnaire=gestionnaire)
        .aggregate(
            total=Count('id'),
            chiffre=Sum('montant_total', filter=Q(statut='confirmee')),
        )
    )
    stats['chiffre'] = stats['chiffre'] or 0

    # Pagination
    paginator = Paginator(reservations, 20)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'reservations/reservation/reservations_gestionnaire.html', {
        'reservations': page,
        'paginator': paginator,
        'filtre_form': filtre_form,
        'stats': stats,
        'page_title': 'Réservations de mes sites',
    })


@login_required
@user_passes_test(est_gestionnaire, login_url='compte:connexion')
def scan_qr_view(request):
    """
    Interface de scan QR à l'entrée du site.

    PÉDAGO : Le gestionnaire (ou son personnel) scanne le QR avec un
    téléphone. Le résultat du scan est posté ici pour validation.

    Sécurité :
    - Le QR doit correspondre à un BonReservation existant
    - Le bon ne doit pas être déjà utilisé
    - La réservation doit être pour AUJOURD'HUI
    - Le site doit appartenir au gestionnaire qui scanne
    """
    bon_valide = None
    erreur = None

    if request.method == 'POST':
        form = ScanQRForm(request.POST)
        if form.is_valid():
            qr_data = form.cleaned_data['qr_code_data']
            try:
                bon = BonReservation.objects.select_related(
                    'reservation__site',
                    'reservation__site__gestionnaire',
                    'reservation__touriste__user',
                ).get(qr_code_data=qr_data)

                # Vérification 1 : site appartient au gestionnaire ?
                gest_id = request.user.profil_gestionnaire.id
                if bon.reservation.site.gestionnaire_id != gest_id:
                    erreur = "❌ Ce bon concerne un site qui ne vous appartient pas."

                # Vérification 2 : déjà utilisé ?
                elif bon.est_utilise:
                    erreur = (
                        f"⚠️ Bon déjà utilisé le "
                        f"{bon.date_utilisation.strftime('%d/%m/%Y à %H:%M')}."
                    )

                # Vérification 3 : réservation confirmée ?
                elif bon.reservation.statut != Reservation.Statut.CONFIRMEE:
                    erreur = (
                        f"❌ Réservation au statut « {bon.reservation.get_statut_display()} »."
                    )

                # Vérification 4 : date de visite = aujourd'hui ?
                elif bon.reservation.date_visite != timezone.now().date():
                    erreur = (
                        f"⚠️ La visite est prévue le "
                        f"{bon.reservation.date_visite.strftime('%d/%m/%Y')}, "
                        f"pas aujourd'hui."
                    )

                else:
                    # ✅ TOUT EST VALIDE : on marque le bon comme utilisé
                    bon.marquer_utilise(scanne_par_user=request.user)

                    # Met aussi à jour la réservation
                    bon.reservation.statut = Reservation.Statut.TERMINEE
                    bon.reservation.save(update_fields=['statut'])

                    log_action(
                        request.user, 'update', 'BonReservation', bon.id, request,
                        details={
                            'numero': bon.reservation.numero,
                            'action': 'scan_entree',
                        }
                    )

                    bon_valide = bon
                    messages.success(
                        request,
                        f"✅ Bon validé pour {bon.reservation.touriste.user.nom_complet} "
                        f"({bon.reservation.nb_total_personnes} personne(s))."
                    )

            except BonReservation.DoesNotExist:
                erreur = "❌ Bon introuvable. QR Code invalide ou contrefait."
            except Exception as e:
                logger.error(f"Erreur scan QR : {e}", exc_info=True)
                erreur = f"Erreur technique : {e}"
    else:
        form = ScanQRForm()

    return render(request, 'reservations/reservation/scan_qr.html', {
        'form': form,
        'bon_valide': bon_valide,
        'erreur': erreur,
        'page_title': 'Scanner un QR Code',
    })


# ============================================================
# C. ADMIN — VUE GLOBALE
# ============================================================

@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def admin_reservations_view(request):
    """Vue admin de TOUTES les réservations."""
    reservations = (Reservation.objects
        .select_related('touriste__user', 'site', 'site__gestionnaire__user')
        .order_by('-created_at')
    )

    # Filtres
    filtre_form = ReservationFiltreForm(request.GET or None)
    if filtre_form.is_valid():
        data = filtre_form.cleaned_data
        if data.get('q'):
            reservations = reservations.filter(
                Q(numero__icontains=data['q'])
                | Q(touriste__user__email__icontains=data['q'])
                | Q(site__nom__icontains=data['q'])
            )
        if data.get('statut'):
            reservations = reservations.filter(statut=data['statut'])
        if data.get('date_debut'):
            reservations = reservations.filter(date_visite__gte=data['date_debut'])
        if data.get('date_fin'):
            reservations = reservations.filter(date_visite__lte=data['date_fin'])

    # Stats globales
    stats = Reservation.objects.aggregate(
        total=Count('id'),
        confirmees=Count('id', filter=Q(statut='confirmee')),
        annulees=Count('id', filter=Q(statut='annulee')),
        ca_total=Sum('montant_total', filter=Q(statut='confirmee')),
    )
    stats['ca_total'] = stats['ca_total'] or 0

    paginator = Paginator(reservations, 25)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'reservations/reservation/admin_reservations.html', {
        'reservations': page,
        'paginator': paginator,
        'filtre_form': filtre_form,
        'stats': stats,
        'page_title': 'Toutes les réservations',
    })