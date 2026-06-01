"""reviews/admin.py — CRUD avis et favoris via backoffice."""
from django.contrib import admin
from reviews.models import Avis, Favori, UtiliteAvis


@admin.register(Avis)
class AvisAdmin(admin.ModelAdmin):
    list_display = ('touriste', 'site', 'note', 'statut_moderation', 'est_visible', 'nombre_signalements', 'created_at')
    list_filter = ('statut_moderation', 'est_visible', 'note')
    search_fields = ('touriste__user__email', 'site__nom', 'titre', 'commentaire')
    date_hierarchy = 'created_at'
    autocomplete_fields = ('touriste', 'site', 'reservation')
    list_editable = ('statut_moderation', 'est_visible')
    actions = ('approuver_selection', 'rejeter_selection')

    def approuver_selection(self, request, queryset):
        for avis in queryset:
            avis.approuver()
        self.message_user(request, f"{queryset.count()} avis approuvé(s) et publié(s).")
    approuver_selection.short_description = "✓ Approuver et publier"

    def rejeter_selection(self, request, queryset):
        for avis in queryset:
            avis.rejeter(motif="Rejeté en masse depuis le backoffice")
        self.message_user(request, f"{queryset.count()} avis rejeté(s).")
    rejeter_selection.short_description = "✕ Rejeter"


@admin.register(Favori)
class FavoriAdmin(admin.ModelAdmin):
    list_display = ('touriste', 'site', 'created_at')
    search_fields = ('touriste__user__email', 'site__nom')
    autocomplete_fields = ('touriste', 'site')
    date_hierarchy = 'created_at'


@admin.register(UtiliteAvis)
class UtiliteAvisAdmin(admin.ModelAdmin):
    list_display = ('avis', 'touriste', 'est_utile', 'created_at')
    list_filter = ('est_utile',)
    autocomplete_fields = ('avis', 'touriste')
