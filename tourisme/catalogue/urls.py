"""
catalogue/urls.py
=================
URLs des pages publiques du catalogue touristique.
"""

from django.urls import path
from . import views

app_name = 'catalogue'  # Important pour le namespace

urlpatterns = [
    # Page d'accueil
    path('', views.accueil, name='accueil'),

    # Liste des sites avec filtres
    path('sites/', views.ListeSitesView.as_view(), name='liste_sites'),

    # Détail d'un site (avec slug pour SEO)
    path('sites/<slug:slug>/', views.detail_site, name='detail_site'),

    # Liste filtrée par catégorie
    path('categorie/<slug:slug>/', views.sites_par_categorie, name='sites_categorie'),

    # Liste filtrée par région
    path('region/<int:region_id>/', views.sites_par_region, name='sites_region'),

    # Recherche
    path('recherche/', views.recherche_sites, name='recherche'),
]