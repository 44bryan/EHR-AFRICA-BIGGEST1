from django.contrib import admin
from .models import InventoryItem, Vendor, PurchaseOrder, PurchaseOrderItem, StockMovement


@admin.register(InventoryItem)
class InventoryItemAdmin(admin.ModelAdmin):
    list_display = ['item_code', 'name', 'category', 'current_stock', 'reorder_level', 'needs_reorder']
    list_filter = ['category', 'is_active']
    search_fields = ['name', 'item_code']


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact_person', 'phone', 'email', 'is_active']
    search_fields = ['name']


class POItemInline(admin.TabularInline):
    model = PurchaseOrderItem
    extra = 0
    readonly_fields = ['subtotal']


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ['po_number', 'vendor', 'status', 'ordered_date', 'total_amount']
    list_filter = ['status']
    inlines = [POItemInline]


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ['item', 'movement_type', 'quantity', 'balance_after', 'performed_by', 'created_at']
    list_filter = ['movement_type']
    readonly_fields = ['created_at']
