from django.contrib import admin
from .models import Drug, DrugStock, Dispensing, DispensingItem


class DrugStockInline(admin.TabularInline):
    model = DrugStock
    extra = 0
    fields = ['batch_number', 'expiry_date', 'quantity_received', 'quantity_remaining', 'supplier']
    readonly_fields = ['quantity_remaining']


@admin.register(Drug)
class DrugAdmin(admin.ModelAdmin):
    list_display = ['name', 'generic_name', 'form', 'category', 'current_stock', 'needs_reorder', 'is_active']
    list_filter = ['category', 'form', 'is_active']
    search_fields = ['name', 'generic_name', 'brand_name']
    inlines = [DrugStockInline]


@admin.register(DrugStock)
class DrugStockAdmin(admin.ModelAdmin):
    list_display = ['drug', 'batch_number', 'expiry_date', 'quantity_received', 'quantity_remaining', 'is_expired']
    list_filter = ['expiry_date']
    search_fields = ['drug__name', 'batch_number']


class DispensingItemInline(admin.TabularInline):
    model = DispensingItem
    extra = 0
    readonly_fields = ['subtotal']


@admin.register(Dispensing)
class DispensingAdmin(admin.ModelAdmin):
    list_display = ['dispensing_number', 'patient', 'status', 'dispensed_by', 'dispensed_at', 'total_amount']
    list_filter = ['status', 'dispensed_at']
    search_fields = ['dispensing_number', 'patient__first_name', 'patient__last_name']
    inlines = [DispensingItemInline]
