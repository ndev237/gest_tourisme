"""
localisation/urls.py
====================
Routes pour l'app localisation.

ORGANISATION :
A. PUBLIQUES : carte interactive
B. ADMIN : CRUD régions

CONVENTION URL :
- Carte publique sur /carte/ (URL courte, mémorisable)
- Admin sous /admin/ pour isoler le back-office
"""

from django.urls import path
from localisation import views

app_name = 'localisation'

urlpatterns = [
    # =========================================================
    # A. PUBLIQUES
    # =========================================================
    path('carte/', views.carte_view, name='carte'),
    path('regions/', views.liste_regions_publique_view, name='liste_regions_publique'),

    # =========================================================
    # B. ADMIN — REGIONS
    # =========================================================
    path('admin/regions/', views.liste_region_view, name='liste_region'),
    path('admin/region/ajouter/', views.add_region_view, name='add_region'),
    path('admin/region/<int:region_id>/modifier/',
         views.update_region_view, name='update_region'),
    path('admin/region/<int:region_id>/supprimer/',
         views.delete_region_view, name='delete_region'),

    # =========================================================
    # C. GESTIONNAIRE — LOCALISATIONS (CRUD partiel)
    # =========================================================
    # PÉDAGO : pas de add_ ni delete_ ici car OneToOne avec Site.
    # Création = via catalogue:add_sites / Suppression = via catalogue:delete_sites
    path('gestionnaire/localisations/',
         views.liste_localisation_view, name='liste_localisation'),
    path('gestionnaire/localisation/<int:localisation_id>/',
         views.detail_localisation_view, name='detail_localisation'),
    path('gestionnaire/localisation/<int:localisation_id>/modifier/',
         views.update_localisation_view, name='update_localisation'),
]