from django.contrib import admin
from .models import Frame, Lens, OpticalOrder


@admin.register(Frame)
class FrameAdmin(admin.ModelAdmin):
    list_display = ['brand', 'model', 'color', 'shape', 'selling_price', 'quantity_in_stock']
    list_filter = ['brand', 'shape']
    search_fields = ['brand', 'model', 'sku']


@admin.register(Lens)
class LensAdmin(admin.ModelAdmin):
    list_display = ['name', 'lens_type', 'material', 'selling_price']
    list_filter = ['lens_type']


@admin.register(OpticalOrder)
class OpticalOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'patient', 'status', 'total_amount', 'ordered_date', 'expected_date']
    list_filter = ['status']
    search_fields = ['order_number', 'patient__first_name', 'patient__last_name']
