from django.contrib import admin
from .models import AIConversation, AIMessage


class AIMessageInline(admin.TabularInline):
    model = AIMessage
    extra = 0
    readonly_fields = ['role', 'content', 'tokens_used', 'model_used', 'created_at']
    max_num = 0
    can_delete = False


@admin.register(AIConversation)
class AIConversationAdmin(admin.ModelAdmin):
    list_display = ['user', 'patient', 'context_type', 'message_count', 'created_at']
    list_filter = ['context_type', 'is_active']
    search_fields = ['user__email', 'patient__first_name']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [AIMessageInline]
