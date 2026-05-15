"""
compte/urls.py
==============
URLs de l'app compte (authentification, profil, dashboards).

Toutes ces routes sont préfixées par /compte/ depuis tourisme/urls.py.
Ex : /compte/connexion/, /compte/dashboard/touriste/

Initiative : on utilise `app_name` pour pouvoir référencer les URLs
avec un namespace dans les templates :
    {% url 'compte:connexion' %}
    {% url 'compte:dashboard_touriste' %}
Cela évite les collisions de noms entre apps.
"""

from django.urls import path

from . import views

app_name = 'compte'

urlpatterns = [
    # ============================================================
    # AUTHENTIFICATION
    # ============================================================
    path('connexion/', views.connexion_view, name='connexion'),
    path('inscription/', views.inscription_view, name='inscription'),
    path('deconnexion/', views.deconnexion_view, name='deconnexion'),
    path('compte-suspendu/', views.compte_suspendu_view, name='compte_suspendu'),

    # ============================================================
    # PROFIL & MOT DE PASSE
    # ============================================================
    path('profil/', views.profil_view, name='profil'),
    path('changer-mot-de-passe/', views.changer_password_view, name='changer_password'),

    # ============================================================
    # DASHBOARDS PAR TYPE D'UTILISATEUR
    # ============================================================
    path('dashboard/touriste/', views.dashboard_touriste_view, name='dashboard_touriste'),
    path('dashboard/gestionnaire/', views.dashboard_gestionnaire_view, name='dashboard_gestionnaire'),
    path('dashboard/guide/', views.dashboard_guide_view, name='dashboard_guide'),
    path('dashboard/admin/', views.dashboard_admin_view, name='dashboard_admin'),
]