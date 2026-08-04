from django.contrib import admin
from .models import InsuranceScheme, InsuredMember, PreAuthorization, ClaimBatch, Claim, ClaimItem

admin.site.register(InsuranceScheme)
admin.site.register(InsuredMember)
admin.site.register(PreAuthorization)
admin.site.register(ClaimBatch)
admin.site.register(Claim)
admin.site.register(ClaimItem)
