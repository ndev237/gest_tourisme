"""
catalogue/urls.py
=================
Routes pour l'app catalogue.

ORGANISATION (alignée avec views.py) :
A. PUBLIQUES        : accueil, liste, détail, favori AJAX
B. GESTIONNAIRE SITES
C. GESTIONNAIRE HEBERGEMENT (sous un site)
D. GESTIONNAIRE PHOTO (sous un site)
E. GESTIONNAIRE DISPONIBILITE (sous un site)
F. ADMIN CATEGORIE
G. ADMIN TAG

CONVENTION URL :
- Slug pour les URLs publiques (SEO) : /site/<slug>/
- ID/UUID pour les actions du gestionnaire (sécurité, pas devinable)
- Préfixe /gestionnaire/ pour les espaces gestionnaire
- Préfixe /admin/ pour les espaces admin

INITIATIVES PÉDAGOGIQUES :
1. `app_name = 'catalogue'` → namespace → {% url 'catalogue:liste_sites' %}
   Évite les collisions avec d'autres apps (ex: si reservation a aussi
   une URL 'liste').
2. Les noms d'URLs correspondent EXACTEMENT à votre arborescence de
   templates : `liste_sites`, `add_sites`, `update_sites`, `delete_sites`.
3. Routes hiérarchiques pour les sous-objets : `/site/<slug>/hebergements/`
   plutôt que `/hebergements/?site=<slug>` → URLs lisibles + SEO.
"""

from django.urls import path
from catalogue import views

app_name = 'catalogue'

urlpatterns = [
    # =========================================================
    # A. PUBLIQUES (touristes et anonymes)
    # =========================================================
    path('', views.accueil_view, name='accueil'),
    path('sites/', views.liste_sites_view, name='liste_sites'),
    path('site/<slug:slug>/', views.detail_site_view, name='detail_site'),
    path('site/<slug:slug>/favori/', views.toggle_favori_view, name='toggle_favori'),

    # =========================================================
    # B. GESTIONNAIRE — SITES (CRUD)
    # =========================================================
    path('gestionnaire/mes-sites/', views.mes_sites_view, name='mes_sites'),
    path('gestionnaire/sites/ajouter/', views.add_site_view, name='add_sites'),
    path('gestionnaire/site/<slug:slug>/modifier/',
         views.update_site_view, name='update_sites'),
    path('gestionnaire/site/<slug:slug>/supprimer/',
         views.delete_site_view, name='delete_sites'),

    # =========================================================
    # C. GESTIONNAIRE — HEBERGEMENT (sous un site)
    # =========================================================
    path('gestionnaire/site/<slug:slug>/hebergements/',
         views.liste_hebergement_view, name='liste_hebergement'),
    path('gestionnaire/site/<slug:slug>/hebergement/ajouter/',
         views.add_hebergement_view, name='add_hebergement'),
    path('gestionnaire/hebergement/<int:hebergement_id>/modifier/',
         views.update_hebergement_view, name='update_hebergement'),
    path('gestionnaire/hebergement/<int:hebergement_id>/supprimer/',
         views.delete_hebergement_view, name='delete_hebergement'),

    # =========================================================
    # D. GESTIONNAIRE — PHOTOS (galerie d'un site)
    # =========================================================
    path('gestionnaire/site/<slug:slug>/photos/',
         views.liste_photosite_view, name='liste_photosite'),
    path('gestionnaire/site/<slug:slug>/photo/ajouter/',
         views.add_photosite_view, name='add_photosite'),
    path('gestionnaire/photo/<int:photo_id>/modifier/',
         views.update_photosite_view, name='update_photosite'),
    path('gestionnaire/photo/<int:photo_id>/supprimer/',
         views.delete_photosite_view, name='delete_photosite'),

    # =========================================================
    # E. GESTIONNAIRE — DISPONIBILITES (calendrier)
    # =========================================================
    path('gestionnaire/site/<slug:slug>/disponibilites/',
         views.liste_disponibilite_view, name='liste_disponibilite'),
    path('gestionnaire/site/<slug:slug>/disponibilite/ajouter/',
         views.add_disponibilite_view, name='add_disponibilite'),
    path('gestionnaire/disponibilite/<int:dispo_id>/modifier/',
         views.update_disponibilite_view, name='update_disponibilite'),
    path('gestionnaire/disponibilite/<int:dispo_id>/supprimer/',
         views.delete_disponibilite_view, name='delete_disponibilite'),

    # =========================================================
    # F. ADMIN — CATEGORIES
    # =========================================================
    path('admin/categories/', views.liste_categorie_view, name='liste_categorie'),
    path('admin/categorie/ajouter/', views.add_categorie_view, name='add_categorie'),
    path('admin/categorie/<int:categorie_id>/modifier/',
         views.update_categorie_view, name='update_categorie'),
    path('admin/categorie/<int:categorie_id>/supprimer/',
         views.delete_categorie_view, name='delete_categorie'),

    # =========================================================
    # G. ADMIN — TAGS
    # =========================================================
    path('admin/tags/', views.liste_tag_view, name='liste_tag'),
    path('admin/tag/ajouter/', views.add_tag_view, name='add_tag'),
    path('admin/tag/<int:tag_id>/modifier/',
         views.update_tag_view, name='update_tag'),
    path('admin/tag/<int:tag_id>/supprimer/',
         views.delete_tag_view, name='delete_tag'),
]