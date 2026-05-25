"""
reservation/urls.py
===================
Routes pour l'app reservation.

ORGANISATION :
A. TOURISTE  : création, liste, détail, annulation, bon PDF
B. GESTIONNAIRE : liste de ses réservations + scan QR
C. ADMIN     : vue globale

CONVENTION :
- UUID dans l'URL pour la réservation (sécurité : non devinable)
- Slug pour la création (URL parlante depuis fiche site)
- Préfixes /touriste/, /gestionnaire/, /admin/ pour clarté
"""

from django.urls import path
from reservation import views

app_name = 'reservation'

urlpatterns = [
    # =========================================================
    # A. TOURISTE
    # =========================================================
    path('site/<slug:slug>/reserver/',
         views.create_reservation_view, name='add_reservation'),

    path('mes-reservations/',
         views.mes_reservations_view, name='mes_reservations'),

    path('detail/<uuid:reservation_id>/',
         views.detail_reservation_view, name='detail_reservation'),

    path('<uuid:reservation_id>/annuler/',
         views.annuler_reservation_view, name='annuler_reservation'),

    path('<uuid:reservation_id>/bon-pdf/',
         views.bon_pdf_view, name='bon_pdf'),

    # =========================================================
    # B. GESTIONNAIRE
    # =========================================================
    path('gestionnaire/reservations/',
         views.reservations_gestionnaire_view, name='reservations_gestionnaire'),

    path('gestionnaire/scan/',
         views.scan_qr_view, name='scan_qr'),

    # =========================================================
    # C. ADMIN
    # =========================================================
    path('admin/reservations/',
         views.admin_reservations_view, name='admin_reservations'),
]