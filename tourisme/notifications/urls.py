"""
notifications/urls.py
=====================
Routes pour la cloche et la page Mes notifications.
"""

from django.urls import path
from notifications import views

app_name = 'notifications'

urlpatterns = [
    path('', views.liste_notifications_view, name='liste'),
    path('<int:notif_id>/lire/', views.marquer_lue_view, name='marquer_lue'),
    path('tout-lire/', views.marquer_toutes_lues_view, name='marquer_toutes_lues'),
    path('ajax/recentes/', views.ajax_recentes_view, name='ajax_recentes'),
]