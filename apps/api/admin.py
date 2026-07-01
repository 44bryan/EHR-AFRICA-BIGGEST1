from django.contrib import admin
from .models import APIToken


@admin.register(APIToken)
class APITokenAdmin(admin.ModelAdmin):
    list_display = ('name', 'token', 'is_active', 'last_used', 'expires_at', 'created_at')
    list_filter = ('is_active',)
    readonly_fields = ('token', 'last_used', 'created_at', 'updated_at')
    search_fields = ('name',)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
