from django.urls import path
from . import views

app_name = 'billing'

urlpatterns = [
    path('', views.billing_dashboard, name='dashboard'),
    path('pos/', views.pos_landing, name='pos_landing'),
    path('invoices/', views.invoice_list, name='invoice_list'),
    path('invoices/new/', views.invoice_create, name='invoice_create'),
    path('invoices/<uuid:invoice_id>/', views.invoice_detail, name='invoice_detail'),
    path('invoices/<uuid:invoice_id>/pay/', views.add_payment, name='add_payment'),
    path('invoices/<uuid:invoice_id>/cancel/', views.cancel_invoice, name='cancel_invoice'),

    # POS (Point of Sale)
    path('pos/<uuid:token_id>/', views.cashier_pos, name='cashier_pos'),
    path('pos/<uuid:token_id>/finalize/', views.pos_finalize, name='pos_finalize'),
    path('invoice/<uuid:invoice_id>/add-item/', views.pos_add_item, name='pos_add_item'),
    path('invoice/<uuid:invoice_id>/discount/', views.pos_apply_discount, name='pos_apply_discount'),
    path('item/<uuid:item_id>/remove/', views.pos_remove_item, name='pos_remove_item'),
    path('invoice/<uuid:invoice_id>/record-payment/', views.pos_record_payment, name='pos_record_payment'),
    path('receipt/<uuid:invoice_id>/', views.receipt_view, name='receipt'),
]
