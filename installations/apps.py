from django.apps import AppConfig


class InstallationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "installations"

    def ready(self):
        import installations.signals as signals

        _ = signals
