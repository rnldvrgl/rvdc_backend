from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'analytics'

    def ready(self):
        # Import signal handlers to register them
        try:
            import analytics.signals  # noqa: F401
        except Exception:
            pass
