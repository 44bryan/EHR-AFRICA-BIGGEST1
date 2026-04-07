from django.apps import AppConfig


class ConsultationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.consultations'
    verbose_name = 'Consultations'

    def ready(self):
        import apps.consultations.signals  # noqa: F401
