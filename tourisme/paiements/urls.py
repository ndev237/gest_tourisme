"""
paiements/urls.py
=================
Routes pour l'app paiements.

ORGANISATION :
A. TOURISTE  : tunnel de paiement (choix → init → callback)
B. WEBHOOKS  : appelés par les providers (PUBLIC, signature vérifiée)
C. ADMIN     : CRUD MoyenPaiement + liste paiements + remboursements

CONVENTION :
- UUID dans l'URL pour paiement_id (sécurité)
- /webhook/ pour les hooks publics (pas authentifiés mais signés)
"""

from django.urls import path
from paiements import views

app_name = 'paiement'

urlpatterns = [
    # =========================================================
    # A. TOURISTE — TUNNEL DE PAIEMENT
    # =========================================================
    path('<uuid:reservation_id>/choix-moyen/',
         views.choix_moyen_view, name='choix_moyen'),

    path('<uuid:reservation_id>/initier/<int:moyen_id>/',
         views.initier_paiement_view, name='initier_paiement'),

    path('<uuid:paiement_id>/attente/',
         views.attente_paiement_view, name='attente_paiement'),

    # Mode mock : simulation paiement réussi
    path('<uuid:paiement_id>/simuler/',
         views.simuler_paiement_view, name='simuler_paiement'),

    path('<uuid:paiement_id>/callback/',
         views.callback_paiement_view, name='callback_paiement'),

    # =========================================================
    # B. WEBHOOKS (publiques, signature vérifiée)
    # =========================================================
    path('webhook/mtn/', views.webhook_mtn_view, name='webhook_mtn'),
    path('webhook/orange/', views.webhook_orange_view, name='webhook_orange'),
    path('webhook/stripe/', views.webhook_stripe_view, name='webhook_stripe'),

    # =========================================================
    # C. ADMIN — MOYENS DE PAIEMENT (CRUD)
    # =========================================================
    path('admin/moyens/',
         views.liste_moyenpaiement_view, name='liste_moyenpaiement'),
    path('admin/moyen/ajouter/',
         views.add_moyenpaiement_view, name='add_moyenpaiement'),
    path('admin/moyen/<int:moyen_id>/modifier/',
         views.update_moyenpaiement_view, name='update_moyenpaiement'),
    path('admin/moyen/<int:moyen_id>/supprimer/',
         views.delete_moyenpaiement_view, name='delete_moyenpaiement'),

    # =========================================================
    # C. ADMIN — VUE GLOBALE PAIEMENTS
    # =========================================================
    path('admin/paiement/',
         views.admin_paiements_view, name='admin_paiements'),

    path('admin/paiement/<uuid:paiement_id>/rembourser/',
         views.rembourser_view, name='rembourser'),
]