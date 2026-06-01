"""reservation/admin.py — CRUD complet via backoffice."""
from django.contrib import admin
from reservation.models import Reservation, LigneReservation, BonReservation


class LigneReservationInline(admin.TabularInline):
    model = LigneReservation
    extra = 0
    fields = ('designation', 'quantite', 'prix_unitaire', 'sous_total')
    readonly_fields = ('sous_total',)


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ('numero', 'touriste', 'site', 'date_visite', 'montant_total', 'statut', 'created_at')
    list_filter = ('statut', 'date_visite')
    search_fields = ('numero', 'touriste__user__email', 'site__nom')
    date_hierarchy = 'date_visite'
    autocomplete_fields = ('touriste', 'site', 'hebergement', 'guide')
    readonly_fields = ('numero', 'date_confirmation', 'date_annulation')
    inlines = [LigneReservationInline]
    list_editable = ('statut',)


@admin.register(LigneReservation)
class LigneReservationAdmin(admin.ModelAdmin):
    list_display = ('reservation', 'designation', 'quantite', 'prix_unitaire', 'sous_total')
    search_fields = ('reservation__numero', 'designation')


@admin.register(BonReservation)
class BonReservationAdmin(admin.ModelAdmin):
    list_display = ('reservation', 'qr_code_data', 'est_utilise', 'date_utilisation')
    list_filter = ('est_utilise',)
    search_fields = ('reservation__numero',)
    readonly_fields = ('qr_code_data', 'date_utilisation')
