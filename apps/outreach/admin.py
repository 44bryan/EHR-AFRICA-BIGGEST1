from django.contrib import admin
from .models import OutreachActivity, OutreachRecord


class OutreachRecordInline(admin.TabularInline):
    model = OutreachRecord
    extra = 0
    fields = ['record_date', 'total_screened', 'total_treated',
              'total_referred', 'surgeries_performed', 'glasses_dispensed']


@admin.register(OutreachActivity)
class OutreachActivityAdmin(admin.ModelAdmin):
    list_display  = ['title', 'activity_type', 'status', 'activity_date',
                     'location_name', 'region', 'team_leader']
    list_filter   = ['status', 'activity_type', 'region']
    search_fields = ['title', 'location_name', 'region', 'town']
    ordering      = ['-activity_date']
    inlines       = [OutreachRecordInline]
    filter_horizontal = ['team_members']


@admin.register(OutreachRecord)
class OutreachRecordAdmin(admin.ModelAdmin):
    list_display  = ['activity', 'record_date', 'total_screened',
                     'total_treated', 'total_referred', 'surgeries_performed']
    list_filter   = ['activity__activity_type']
    search_fields = ['activity__title']
    ordering      = ['-record_date']
