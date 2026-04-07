from django.apps import AppConfig


class IpdConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.ipd'
    verbose_name = 'Inpatient (IPD)'

    def ready(self):
        import apps.consultations.signals  # noqa: F401 — registers SurgicalBooking post_save signal
