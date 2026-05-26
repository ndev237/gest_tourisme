from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'notifications'

    def ready(self):
        """
        Connecte les signaux au démarrage de l'app.
        Sans cette méthode, les receivers ne sont jamais déclenchés.
        """
        # Import ici (pas en tête de fichier) pour éviter les imports circulaires
        from notifications import signals  # noqa: F401
        signals.connect_signals()
