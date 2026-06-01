"""notifications/admin.py — CRUD notifications, messages, préférences."""
from django.contrib import admin
from notifications.models import Notification, Message, PreferencesNotification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('sujet', 'destinataire', 'type', 'canal', 'statut', 'created_at')
    list_filter = ('type', 'canal', 'statut')
    search_fields = ('sujet', 'contenu', 'destinataire__email')
    date_hierarchy = 'created_at'
    autocomplete_fields = ('destinataire', 'reservation')
    readonly_fields = ('date_envoi', 'date_lecture')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('sujet', 'expediteur', 'destinataire', 'statut', 'created_at')
    list_filter = ('statut',)
    search_fields = ('sujet', 'corps', 'expediteur__email', 'destinataire__email')
    autocomplete_fields = ('expediteur', 'destinataire', 'reservation', 'message_parent')
    date_hierarchy = 'created_at'


@admin.register(PreferencesNotification)
class PreferencesNotificationAdmin(admin.ModelAdmin):
    list_display = ('utilisateur', 'reservations_email', 'reservations_sms', 'paiements_email', 'paiements_sms', 'newsletter')
    search_fields = ('utilisateur__email',)
    autocomplete_fields = ('utilisateur',)
