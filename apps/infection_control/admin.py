from django.contrib import admin
from .models import HAIReport, AntibioticSensitivity, OutbreakAlert

admin.site.register(HAIReport)
admin.site.register(AntibioticSensitivity)
admin.site.register(OutbreakAlert)
