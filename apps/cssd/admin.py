from django.contrib import admin
from .models import Instrument, InstrumentSet, SterilizationCycle, DispatchRecord


@admin.register(Instrument)
class InstrumentAdmin(admin.ModelAdmin):
    list_display = ['instrument_code', 'name', 'status', 'last_sterilized', 'is_sterile', 'department']
    list_filter = ['status', 'department']
    search_fields = ['name', 'instrument_code']


@admin.register(InstrumentSet)
class InstrumentSetAdmin(admin.ModelAdmin):
    list_display = ['set_code', 'name', 'department']
    filter_horizontal = ['instruments']


@admin.register(SterilizationCycle)
class SterilizationCycleAdmin(admin.ModelAdmin):
    list_display = ['cycle_number', 'method', 'start_time', 'is_successful', 'bi_test_result', 'operator']
    list_filter = ['method', 'is_successful', 'bi_test_result']
    filter_horizontal = ['instruments', 'sets']


@admin.register(DispatchRecord)
class DispatchRecordAdmin(admin.ModelAdmin):
    list_display = ['dispatch_number', 'to_department', 'dispatch_time', 'dispatched_by', 'return_time']
    filter_horizontal = ['instruments', 'sets']
