from django.contrib import admin
from .models import (Invoice, InvoiceItem, Payment, ServicePrice, Refund, CashierShift,
                     InvoiceVoidReason, Proforma, ProformaItem)


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    fields = ('description', 'category', 'quantity', 'unit_price')
    readonly_fields = ()


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'patient', 'status', 'total', 'amount_paid', 'issue_date')
    list_filter = ('status', 'issue_date')
    search_fields = ('invoice_number', 'patient__first_name', 'patient__last_name')
    inlines = [InvoiceItemInline]
    date_hierarchy = 'issue_date'


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'amount', 'payment_method', 'payment_date', 'received_by')
    list_filter = ('payment_method', 'payment_date')
    search_fields = ('invoice__invoice_number', 'invoice__patient__first_name', 'reference')
    date_hierarchy = 'payment_date'


@admin.register(ServicePrice)
class ServicePriceAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price', 'nhis_price', 'insurance_price',
                    'requires_price_entry', 'is_active', 'code')
    list_filter = ('category', 'is_active', 'requires_price_entry')
    search_fields = ('name', 'code')
    list_editable = ('price', 'nhis_price', 'insurance_price', 'is_active')
    ordering = ('category', 'name')
    fieldsets = (
        ('Service Info', {
            'fields': ('name', 'code', 'category', 'is_active', 'requires_price_entry')
        }),
        ('Pricing', {
            'fields': ('price', 'nhis_price', 'insurance_price'),
            'description': 'Prices in FCFA. Leave NHIS/Insurance blank to use standard price.'
        }),
    )


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ('invoice', 'amount', 'payment_method', 'reason', 'refund_date', 'processed_by')
    list_filter = ('payment_method', 'refund_date')
    search_fields = ('invoice__invoice_number', 'invoice__patient__first_name', 'reason')
    date_hierarchy = 'refund_date'
    readonly_fields = ('processed_by', 'refund_date')


@admin.register(CashierShift)
class CashierShiftAdmin(admin.ModelAdmin):
    list_display = ('cashier', 'shift_date', 'status', 'opening_cash',
                    'closing_cash_declared', 'opened_at', 'closed_at', 'verified_by')
    list_filter = ('status', 'shift_date')
    search_fields = ('cashier__first_name', 'cashier__last_name', 'cashier__username')
    date_hierarchy = 'shift_date'
    readonly_fields = ('opened_at', 'closed_at', 'submitted_at', 'verified_at', 'verified_by')


@admin.register(InvoiceVoidReason)
class InvoiceVoidReasonAdmin(admin.ModelAdmin):
    list_display = ('code', 'label', 'requires_supervisor', 'is_active')
    list_filter = ('is_active', 'requires_supervisor')
    search_fields = ('code', 'label')
    list_editable = ('is_active',)
    ordering = ('code',)


class ProformaItemInline(admin.TabularInline):
    model = ProformaItem
    extra = 0
    fields = ('category', 'description', 'quantity', 'unit_price')


@admin.register(Proforma)
class ProformaAdmin(admin.ModelAdmin):
    list_display = ('proforma_number', 'patient', 'status', 'issue_date',
                    'insurance_amount', 'issued_by')
    list_filter = ('status', 'issue_date')
    search_fields = ('proforma_number', 'patient__first_name', 'patient__last_name')
    inlines = [ProformaItemInline]
    date_hierarchy = 'issue_date'
    readonly_fields = ('proforma_number', 'issued_by', 'invoice')


@admin.register(ProformaItem)
class ProformaItemAdmin(admin.ModelAdmin):
    list_display = ('proforma', 'category', 'description', 'quantity', 'unit_price')
    list_filter = ('category',)
    search_fields = ('description', 'proforma__proforma_number')
