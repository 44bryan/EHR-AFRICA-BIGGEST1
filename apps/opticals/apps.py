from django.apps import AppConfig


class OpticalsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.opticals'
    label = 'opticals'

    def ready(self):
        import apps.opticals.signals  # noqa: F401 — connect signal receivers
