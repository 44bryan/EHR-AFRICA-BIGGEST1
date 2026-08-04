from django.contrib import admin
from .models import BloodDonor, BloodUnit, CrossMatch, BloodIssue

admin.site.register(BloodDonor)
admin.site.register(BloodUnit)
admin.site.register(CrossMatch)
admin.site.register(BloodIssue)
