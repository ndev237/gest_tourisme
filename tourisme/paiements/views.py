"""
paiements/views.py
==================
Vues de l'app paiements.

ORGANISATION (4 sections) :
A. TOURISTE — Tunnel de paiement
   - choix_moyen_view        : choix MTN/Orange/Stripe/Cash
   - initier_paiement_view   : démarre la transaction
   - callback_paiement_view  : retour utilisateur après paiement
   - simuler_paiement_view   : mock pour développement
B. WEBHOOKS (publiques, appelées par les providers)
   - webhook_mtn_view
   - webhook_orange_view
   - webhook_stripe_view
C. ADMIN — CRUD MoyenPaiement + liste paiements
   - liste_moyenpaiement_view, add_moyenpaiement_view,
     update_moyenpaiement_view, delete_moyenpaiement_view
   - admin_paiements_view
   - rembourser_view
D. HELPERS

INITIATIVES PÉDAGOGIQUES :
1. WEBHOOK SAFETY : @csrf_exempt + vérification signature provider.
2. IDEMPOTENCE : si callback rappelé 2x, on ne décrémente les
   Disponibilites qu'UNE seule fois (vérif statut avant).
3. SELECT_FOR_UPDATE : verrou pessimiste anti-race-condition lors
   du décrément des places (2 paiements simultanés sur 1 place).
4. AuditLog systématique pour traçabilité financière.
5. Logique métier complexe → fonctions helpers extraites.
"""

import json
import logging
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from paiements.models import MoyenPaiement, Paiement
from paiements.forms import (
    ChoixMoyenForm, NumeroTelephoneForm,
    MoyenPaiementForm, PaiementFiltreForm, RembourserForm,
)
from paiements.providers import get_provider, PROVIDERS_REGISTRY
from reservation.models import Reservation, BonReservation

# Imports défensifs
try:
    from catalogue.models import Disponibilite
except ImportError:
    Disponibilite = None

try:
    from reservation.utils import generer_bon_complet
except ImportError:
    generer_bon_complet = None

try:
    from core.models import AuditLog
except ImportError:
    AuditLog = None

logger = logging.getLogger(__name__)


# ============================================================
# D. HELPERS (en haut pour visibilité)
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


def est_admin(user):
    return user.is_authenticated and user.type_user == 'admin'


def decrementer_disponibilites(reservation):
    """
    Décrémente les places restantes après confirmation du paiement.

    PÉDAGO TRÈS IMPORTANT :
    - `select_for_update()` : verrou pessimiste DB → si 2 touristes
      paient en même temps pour les 3 dernières places, le second
      attend que le premier termine sa transaction avant de lire.
    - À appeler UNIQUEMENT après paiement réussi (pas avant) pour
      éviter les places fantômes.
    - À l'intérieur d'un with transaction.atomic() pour garantir
      la cohérence.
    """
    if Disponibilite is None:
        return  # App catalogue absente

    try:
        # On verrouille la ligne Disponibilite pour cette date
        dispo = (Disponibilite.objects
            .select_for_update()
            .filter(site=reservation.site, date=reservation.date_visite)
            .first()
        )
        if dispo:
            nb_total = reservation.nb_total_personnes
            if dispo.places_restantes >= nb_total:
                dispo.places_restantes -= nb_total
                dispo.save(update_fields=['places_restantes'])
                logger.info(
                    f"Décrément OK pour {reservation.numero} : "
                    f"{dispo.places_restantes} places restantes"
                )
            else:
                logger.warning(
                    f"⚠️ Pas assez de places pour {reservation.numero} ! "
                    f"Demandé {nb_total}, disponible {dispo.places_restantes}"
                )
    except Exception as e:
        logger.error(f"Erreur décrément dispo : {e}", exc_info=True)


def generer_bon_post_paiement(reservation):
    """
    Génère le bon de réservation + QR + PDF après paiement confirmé.

    PÉDAGO : on extrait ça d'une view pour le rendre testable
    et appelable depuis les webhooks ET les vues sync.
    """
    if generer_bon_complet is None:
        logger.warning("reservation.utils.generer_bon_complet indisponible")
        return None

    try:
        bon, created = BonReservation.objects.get_or_create(reservation=reservation)
        if created or not bon.pdf_fichier:
            success = generer_bon_complet(bon)
            if not success:
                logger.warning(f"Échec génération bon pour {reservation.numero}")
        return bon
    except Exception as e:
        logger.error(f"Erreur génération bon : {e}", exc_info=True)
        return None


def finaliser_paiement_reussi(paiement, callback_data=None):
    """
    Pipeline de finalisation post-paiement réussi.

    SÉQUENCE :
    1. Marquer le paiement comme reussi (méthode du modèle, qui
       confirme aussi la réservation automatiquement)
    2. Décrémenter les disponibilités (avec verrou)
    3. Générer le bon de réservation (QR + PDF)
    4. TODO : envoyer notifications email + SMS (Vague C)

    PÉDAGO : tout dans une transaction atomique pour cohérence.
    Si une étape échoue, on rollback tout (sauf le marquage paiement
    qui est l'étape 1 critique).
    """
    if paiement.statut == Paiement.Statut.REUSSI:
        # IDEMPOTENCE : si déjà traité, on ne refait rien
        logger.info(f"Paiement {paiement.id} déjà reussi, skip.")
        return paiement.reservation

    try:
        with transaction.atomic():
            # 1. Marquer le paiement comme reussi (confirme la réservation)
            paiement.marquer_reussi(
                reference_externe=paiement.reference_externe,
                callback_data=callback_data or {},
            )

            # 2. Décrémenter les places
            decrementer_disponibilites(paiement.reservation)

            # 3. Générer le bon
            generer_bon_post_paiement(paiement.reservation)

            logger.info(f"✅ Paiement {paiement.reference_interne} finalisé.")
            return paiement.reservation

    except Exception as e:
        logger.error(f"Erreur finalisation paiement : {e}", exc_info=True)
        raise


# ============================================================
# A. TOURISTE — TUNNEL DE PAIEMENT
# ============================================================

@login_required
@user_passes_test(est_touriste, login_url='compte:connexion')
def choix_moyen_view(request, reservation_id):
    """
    Étape 1 : choix du moyen de paiement pour une réservation.

    URL: /paiement/<uuid:reservation_id>/choix-moyen/
    """
    reservation = get_object_or_404(
        Reservation.objects.select_related('site', 'touriste__user'),
        id=reservation_id,
    )

    # Sécurité : seul le propriétaire peut payer SA réservation
    if reservation.touriste_id != request.user.profil_touriste.id:
        return HttpResponseForbidden("Cette réservation ne vous appartient pas.")

    # Si déjà payée, on redirige vers le détail
    if reservation.statut == Reservation.Statut.CONFIRMEE:
        messages.info(request, "Cette réservation est déjà payée.")
        return redirect('reservation:detail_reservation',
                        reservation_id=reservation.id)

    if reservation.statut == Reservation.Statut.ANNULEE:
        messages.warning(request, "Cette réservation a été annulée.")
        return redirect('reservation:mes_reservations')

    if request.method == 'POST':
        form = ChoixMoyenForm(request.POST, montant=reservation.montant_total)
        if form.is_valid():
            moyen = form.cleaned_data['moyen']
            # Redirection vers initier_paiement avec le moyen choisi
            return redirect(
                'paiements:initier_paiement',
                reservation_id=reservation.id,
                moyen_id=moyen.id,
            )
    else:
        form = ChoixMoyenForm(montant=reservation.montant_total)

    return render(request, 'paiements/choix_moyen.html', {
        'form': form,
        'reservation': reservation,
        'page_title': 'Choisir un moyen de paiement',
    })


@login_required
@user_passes_test(est_touriste, login_url='compte:connexion')
def initier_paiement_view(request, reservation_id, moyen_id):
    """
    Étape 2 : initie le paiement via le provider.

    Pour MoMo/Orange : affiche un form de saisie numéro, puis appelle le provider.
    Pour Stripe : redirige immédiatement vers Stripe Checkout.
    Pour Cash : marque comme "à payer à l'arrivée".
    """
    reservation = get_object_or_404(Reservation, id=reservation_id)
    moyen = get_object_or_404(MoyenPaiement, id=moyen_id, est_actif=True)

    if reservation.touriste_id != request.user.profil_touriste.id:
        return HttpResponseForbidden()

    # Récupérer le provider approprié
    provider = get_provider(moyen)

    # === CAS 1 : MoMo / Orange → saisie du numéro de téléphone ===
    if moyen.type == 'mobile_money':
        if request.method == 'POST':
            form = NumeroTelephoneForm(request.POST, provider=moyen.provider)
            if form.is_valid():
                numero = form.cleaned_data['numero_telephone']
                # Créer le paiement DB et tenter l'initiation
                return _initier_et_rediriger(
                    request, reservation, moyen, provider,
                    numero_telephone=numero,
                )
        else:
            form = NumeroTelephoneForm(provider=moyen.provider)

        return render(request, 'paiements/saisie_numero.html', {
            'form': form,
            'reservation': reservation,
            'moyen': moyen,
            'page_title': f'Paiement {moyen.libelle}',
        })

    # === CAS 2 : Stripe / Flutterwave / Manuel → initiation directe ===
    return _initier_et_rediriger(request, reservation, moyen, provider)


def _initier_et_rediriger(request, reservation, moyen, provider,
                           numero_telephone=''):
    """
    Helper : crée un Paiement DB + appelle le provider + redirige.

    PÉDAGO : extrait des views pour DRY (utilisé pour les 3 flux).
    """
    try:
        with transaction.atomic():
            # 1. Créer le Paiement en BDD (statut 'initie')
            paiement = Paiement.objects.create(
                reservation=reservation,
                moyen=moyen,
                montant=reservation.montant_total,
                devise='XAF',
                numero_telephone=numero_telephone,
                statut=Paiement.Statut.INITIE,
            )

            # 2. URL de callback (où l'user reviendra après paiement)
            callback_url = request.build_absolute_uri(
                reverse('paiements:callback_paiement',
                        kwargs={'paiement_id': paiement.id})
            )

            # 3. Appeler le provider
            result = provider.initier_paiement(paiement, callback_url)

            if not result['success']:
                paiement.marquer_echoue(motif=result.get('error', 'Erreur inconnue'))
                messages.error(request, f"❌ {result.get('error', 'Échec du paiement')}")
                return redirect('paiements:choix_moyen',
                                reservation_id=reservation.id)

            # 4. Enregistrer la référence externe
            paiement.reference_externe = result.get('reference_externe', '')
            paiement.statut = Paiement.Statut.EN_COURS
            paiement.save(update_fields=['reference_externe', 'statut'])

            log_action(request.user, 'create', 'Paiement', paiement.id, request,
                       details={
                           'moyen': moyen.libelle,
                           'montant': str(paiement.montant),
                       })

            # 5. Routage selon le retour du provider
            if result.get('redirect_url'):
                # Stripe / Orange WebPay → redirection externe
                return redirect(result['redirect_url'])
            else:
                # MoMo / Cash → page d'attente avec instructions
                return redirect('paiements:attente_paiement',
                                paiement_id=paiement.id)

    except Exception as e:
        logger.error(f"Erreur initiation paiement : {e}", exc_info=True)
        messages.error(request, f"Erreur technique : {e}")
        return redirect('paiements:choix_moyen', reservation_id=reservation.id)


@login_required
def attente_paiement_view(request, paiement_id):
    """
    Page d'attente avec instructions provider-spécifiques.

    Affichée pour MoMo (en attendant la confirmation sur téléphone)
    ou cash (informations pour payer à l'arrivée).
    """
    paiement = get_object_or_404(
        Paiement.objects.select_related('reservation', 'moyen'),
        id=paiement_id,
    )

    # Sécurité : seul le touriste propriétaire ou l'admin
    if (paiement.reservation.touriste_id !=
        getattr(getattr(request.user, 'profil_touriste', None), 'id', None)
        and request.user.type_user != 'admin'):
        return HttpResponseForbidden()

    return render(request, 'paiements/attente_paiement.html', {
        'paiement': paiement,
        'reservation': paiement.reservation,
        'page_title': 'Paiement en cours',
    })


@login_required
@require_POST
def simuler_paiement_view(request, paiement_id):
    """
    MODE MOCK : simule un paiement réussi (pour développement).

    À DÉSACTIVER en production (vérification settings.PAIEMENT_MODE_MOCK).
    """
    if not getattr(__import__('django.conf').conf.settings, 'PAIEMENT_MODE_MOCK', False):
        return HttpResponseForbidden("Mode mock désactivé.")

    paiement = get_object_or_404(Paiement, id=paiement_id)

    # Sécurité : seul le touriste propriétaire
    if paiement.reservation.touriste_id != request.user.profil_touriste.id:
        return HttpResponseForbidden()

    if paiement.statut == Paiement.Statut.REUSSI:
        messages.info(request, "Ce paiement est déjà confirmé.")
    else:
        try:
            finaliser_paiement_reussi(paiement, callback_data={'simulation': True})
            messages.success(
                request,
                f"✅ Paiement simulé avec succès ! "
                f"Votre réservation {paiement.reservation.numero} est confirmée."
            )
        except Exception as e:
            logger.error(f"Erreur simulation : {e}", exc_info=True)
            messages.error(request, f"Erreur : {e}")

    return redirect('paiements:callback_paiement', paiement_id=paiement.id)


@login_required
def callback_paiement_view(request, paiement_id):
    """
    Étape 3 : retour utilisateur après paiement.

    PÉDAGO : ne PAS modifier le paiement ici (c'est le rôle du webhook).
    On affiche juste le statut actuel.
    """
    paiement = get_object_or_404(
        Paiement.objects.select_related('reservation', 'moyen', 'reservation__site'),
        id=paiement_id,
    )

    # Sécurité
    is_owner = (paiement.reservation.touriste_id ==
                getattr(getattr(request.user, 'profil_touriste', None), 'id', None))
    is_admin = request.user.type_user == 'admin'
    if not (is_owner or is_admin):
        return HttpResponseForbidden()

    return render(request, 'paiements/callback_paiement.html', {
        'paiement': paiement,
        'reservation': paiement.reservation,
        'reussi': paiement.statut == Paiement.Statut.REUSSI,
        'echec': paiement.statut == Paiement.Statut.ECHOUE,
        'en_cours': paiement.statut in [Paiement.Statut.INITIE,
                                         Paiement.Statut.EN_COURS],
        'page_title': 'Résultat du paiement',
    })


# ============================================================
# B. WEBHOOKS (publiques, signature vérifiée)
# ============================================================

@csrf_exempt
@require_POST
def webhook_mtn_view(request):
    """
    Webhook appelé par MTN MoMo après confirmation/rejet du paiement.

    SÉCURITÉ : @csrf_exempt nécessaire (l'appel vient de MTN, pas du
    navigateur). En revanche, on vérifie la SIGNATURE du provider.
    """
    return _traiter_webhook(request, 'mtn_momo')


@csrf_exempt
@require_POST
def webhook_orange_view(request):
    """Webhook Orange Money."""
    return _traiter_webhook(request, 'orange_money')


@csrf_exempt
@require_POST
def webhook_stripe_view(request):
    """Webhook Stripe (checkout.session.completed)."""
    return _traiter_webhook(request, 'stripe')


def _traiter_webhook(request, provider_code):
    """
    Logique commune de traitement des webhooks.

    PÉDAGO :
    1. Parse le payload JSON
    2. Vérifie la signature via le provider
    3. Trouve le Paiement correspondant (par reference_externe)
    4. Appelle finaliser_paiement_reussi() ou marquer_echoue()
    5. Retourne 200 OK (ou 4xx en cas d'erreur)
    """
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    # Récupère le provider correspondant
    provider_class = PROVIDERS_REGISTRY.get(provider_code)
    if not provider_class:
        return JsonResponse({'error': 'Provider inconnu'}, status=400)

    provider = provider_class()

    # Vérification de la signature
    result = provider.verifier_callback(payload)
    if not result['valid']:
        logger.warning(f"Webhook {provider_code} : signature invalide")
        return JsonResponse({'error': 'Signature invalide'}, status=403)

    # Trouve le paiement par reference_externe
    try:
        paiement = Paiement.objects.get(
            reference_externe=result['reference_externe']
        )
    except Paiement.DoesNotExist:
        logger.warning(
            f"Webhook {provider_code} : paiement introuvable "
            f"({result['reference_externe']})"
        )
        return JsonResponse({'error': 'Paiement introuvable'}, status=404)

    # Traitement selon le statut
    try:
        if result['statut'] == 'reussi':
            finaliser_paiement_reussi(paiement, callback_data=result['raw_data'])
        else:
            paiement.marquer_echoue(
                motif=f"Échec depuis {provider_code}",
                callback_data=result['raw_data'],
            )
    except Exception as e:
        logger.error(f"Erreur traitement webhook : {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'success': True})


# ============================================================
# C. ADMIN — CRUD MOYEN DE PAIEMENT
# ============================================================

@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def liste_moyenpaiement_view(request):
    """Liste de tous les moyens de paiement (admin)."""
    moyens = (MoyenPaiement.objects
        .annotate(
            nb_paiements=Count('paiements'),
            nb_reussis=Count('paiements', filter=Q(paiements__statut='reussi')),
        )
        .order_by('ordre_affichage', 'libelle')
    )

    stats = {
        'total': moyens.count(),
        'actifs': moyens.filter(est_actif=True).count(),
    }

    return render(request, 'paiements/moyenpaiement/liste_moyenpaiement.html', {
        'moyens': moyens,
        'stats': stats,
        'page_title': 'Moyens de paiement',
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def add_moyenpaiement_view(request):
    """Création d'un moyen de paiement."""
    if request.method == 'POST':
        form = MoyenPaiementForm(request.POST)
        if form.is_valid():
            moyen = form.save()
            log_action(request.user, 'create', 'MoyenPaiement', moyen.id, request)
            messages.success(request, f"✅ Moyen « {moyen.libelle} » créé.")
            return redirect('paiements:liste_moyenpaiement')
    else:
        form = MoyenPaiementForm()

    return render(request, 'paiements/moyenpaiement/add_moyenpaiement.html', {
        'form': form,
        'page_title': 'Nouveau moyen de paiement',
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def update_moyenpaiement_view(request, moyen_id):
    """Modification d'un moyen de paiement."""
    moyen = get_object_or_404(MoyenPaiement, id=moyen_id)

    if request.method == 'POST':
        form = MoyenPaiementForm(request.POST, instance=moyen)
        if form.is_valid():
            form.save()
            log_action(request.user, 'update', 'MoyenPaiement', moyen.id, request)
            messages.success(request, "✅ Moyen mis à jour.")
            return redirect('paiements:liste_moyenpaiement')
    else:
        form = MoyenPaiementForm(instance=moyen)

    return render(request, 'paiements/moyenpaiement/update_moyenpaiement.html', {
        'form': form,
        'moyen': moyen,
        'page_title': f"Modifier : {moyen.libelle}",
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def delete_moyenpaiement_view(request, moyen_id):
    """Suppression d'un moyen (impossible s'il a des paiements)."""
    moyen = get_object_or_404(MoyenPaiement, id=moyen_id)
    nb_paiements = moyen.paiements.count()

    if request.method == 'POST':
        if nb_paiements > 0:
            messages.error(
                request,
                f"❌ Impossible de supprimer : {nb_paiements} paiement(s) y sont liés. "
                f"Désactivez-le plutôt."
            )
        else:
            libelle = moyen.libelle
            log_action(request.user, 'delete', 'MoyenPaiement', moyen.id, request)
            moyen.delete()
            messages.success(request, f"✅ Moyen « {libelle} » supprimé.")
        return redirect('paiements:liste_moyenpaiement')

    return render(request, 'paiements/moyenpaiement/delete_moyenpaiement.html', {
        'moyen': moyen,
        'nb_paiements': nb_paiements,
        'page_title': f"Supprimer : {moyen.libelle}",
    })


# ============================================================
# C. ADMIN — VUE GLOBALE PAIEMENTS
# ============================================================

@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def admin_paiements_view(request):
    """Liste de tous les paiements avec filtres et stats."""
    paiements = (Paiement.objects
        .select_related('reservation__touriste__user', 'reservation__site', 'moyen')
        .order_by('-created_at')
    )

    filtre_form = PaiementFiltreForm(request.GET or None)
    if filtre_form.is_valid():
        data = filtre_form.cleaned_data
        if data.get('q'):
            paiements = paiements.filter(
                Q(reference_interne__icontains=data['q'])
                | Q(reference_externe__icontains=data['q'])
                | Q(reservation__numero__icontains=data['q'])
                | Q(numero_telephone__icontains=data['q'])
            )
        if data.get('statut'):
            paiements = paiements.filter(statut=data['statut'])
        if data.get('moyen'):
            paiements = paiements.filter(moyen=data['moyen'])
        if data.get('date_debut'):
            paiements = paiements.filter(created_at__date__gte=data['date_debut'])
        if data.get('date_fin'):
            paiements = paiements.filter(created_at__date__lte=data['date_fin'])

    # Stats globales
    stats = Paiement.objects.aggregate(
        total=Count('id'),
        reussis=Count('id', filter=Q(statut='reussi')),
        echoues=Count('id', filter=Q(statut='echoue')),
        ca_total=Sum('montant', filter=Q(statut='reussi',
                                          type_transaction='paiement')),
        rembourses=Sum('montant', filter=Q(statut='reussi',
                                             type_transaction='remboursement')),
    )
    stats['ca_total'] = stats['ca_total'] or 0
    stats['rembourses'] = stats['rembourses'] or 0
    stats['ca_net'] = stats['ca_total'] - stats['rembourses']

    paginator = Paginator(paiements, 25)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'paiements/admin_paiements.html', {
        'paiements': page,
        'paginator': paginator,
        'filtre_form': filtre_form,
        'stats': stats,
        'page_title': 'Tous les paiements',
    })


@login_required
@user_passes_test(est_admin, login_url='compte:connexion')
def rembourser_view(request, paiement_id):
    """Initie un remboursement (admin)."""
    paiement = get_object_or_404(Paiement, id=paiement_id)

    if not paiement.peut_etre_rembourse:
        messages.error(
            request,
            "Ce paiement ne peut pas être remboursé "
            "(non réussi, déjà remboursé, ou de type remboursement)."
        )
        return redirect('paiements:admin_paiements')

    if request.method == 'POST':
        form = RembourserForm(request.POST, paiement=paiement)
        if form.is_valid():
            try:
                remboursement = paiement.creer_remboursement(
                    montant=form.cleaned_data['montant'],
                    motif=form.cleaned_data['motif'],
                )
                log_action(
                    request.user, 'create', 'Paiement',
                    remboursement.id, request,
                    details={'type': 'remboursement',
                             'paiement_origine': str(paiement.id)},
                )
                messages.success(
                    request,
                    f"✅ Remboursement {remboursement.reference_interne} initié."
                )
                return redirect('paiements:admin_paiements')
            except Exception as e:
                logger.error(f"Erreur remboursement : {e}", exc_info=True)
                messages.error(request, f"Erreur : {e}")
    else:
        form = RembourserForm(paiement=paiement)

    return render(request, 'paiements/rembourser.html', {
        'form': form,
        'paiement': paiement,
        'page_title': f"Rembourser : {paiement.reference_interne}",
    })