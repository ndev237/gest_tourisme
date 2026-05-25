"""
compte/urls.py
==============
Routes pour l'app compte.

INITIATIVES PÉDAGOGIQUES :
1. `app_name = 'compte'` → namespace, on appelle via {% url 'compte:connexion' %}.
   Évite les collisions si une autre app a aussi une URL nommée 'connexion'.
2. URLs en français, parlantes, alignées avec votre convention.
"""

from django.urls import path
from compte import views

app_name = 'compte'

urlpatterns = [
    # ===== AUTHENTIFICATION =====
    path('connexion/', views.connexion_view, name='connexion'),
    path('inscription/', views.inscription_view, name='inscription'),
    path('deconnexion/', views.deconnexion_view, name='deconnexion'),

    # ===== GESTION DU COMPTE =====
    path('profil/', views.profil_view, name='profil'),
    path('profil/modifier/', views.profil_update_view, name='profil_update'),
    path('changer-password/', views.changer_password_view, name='changer_password'),
    path('compte-suspendu/', views.compte_suspendu_view, name='compte_suspendu'),

    # ===== DASHBOARDS (un par type d'utilisateur) =====
    path('dashboard/touriste/', views.dashbord_touriste_view, name='dashbord_touriste'),
    path('dashboard/gestionnaire/', views.dashbord_gestionnaire_view, name='dashbord_gestionnaire_site'),
    path('dashboard/guide/', views.dashbord_guide_view, name='dashbord_guide'),
    path('dashboard/admin/', views.dashbord_admin_view, name='dashbord_admin'),
]