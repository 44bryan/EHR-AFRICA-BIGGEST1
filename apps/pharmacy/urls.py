from django.urls import path
from . import views

app_name = 'pharmacy'

urlpatterns = [
    path('', views.pharmacy_dashboard, name='dashboard'),
    path('drugs/', views.drug_list, name='drug_list'),
    path('drugs/new/', views.drug_create, name='drug_create'),
    path('drugs/<uuid:drug_id>/', views.drug_detail, name='drug_detail'),
    path('drugs/<uuid:drug_id>/edit/', views.drug_edit, name='drug_edit'),
    path('drugs/<uuid:drug_id>/add-stock/', views.add_stock, name='add_stock'),
    path('drugs/stock-ajax/', views.drug_stock_ajax, name='drug_stock_ajax'),
    path('drugs/search/', views.drug_search_ajax, name='drug_search_ajax'),
    path('dispensing/<uuid:dispensing_id>/add-item-ajax/', views.add_dispensing_item_ajax, name='add_dispensing_item_ajax'),
    path('dispensing/<uuid:dispensing_id>/add-manual-ajax/', views.add_manual_item_ajax, name='add_manual_item_ajax'),
    path('dispensing/<uuid:dispensing_id>/remove-item/<uuid:item_id>/', views.remove_dispensing_item_ajax, name='remove_dispensing_item_ajax'),
    path('dispense/', views.dispense, name='dispense'),
    path('dispensing/', views.dispensing_list, name='dispensing_list'),
    path('dispensing/<uuid:dispensing_id>/', views.dispensing_detail, name='dispensing_detail'),
    path('dispensing/<uuid:dispensing_id>/add-item/', views.add_dispensing_item, name='add_dispensing_item'),
    path('dispensing/<uuid:dispensing_id>/complete/', views.complete_dispensing, name='complete_dispensing'),
    path('pilferage/', views.pilferage_dashboard, name='pilferage'),
    path('dispensing/<uuid:dispensing_id>/receipt/', views.dispensing_receipt, name='dispensing_receipt'),
    path('search/', views.patient_search, name='patient_search'),
    path('rx/<uuid:rx_id>/start-dispensing/', views.start_rx_dispensing, name='start_rx_dispensing'),
    path('rx/<uuid:rx_id>/declined/', views.rx_declined, name='rx_declined'),
    path('adjustments/', views.stock_adjustment_list, name='stock_adjustment_list'),
    path('stock/<uuid:batch_id>/adjust/', views.stock_adjustment_create, name='stock_adjustment_create'),
]
