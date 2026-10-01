from django.urls import path
from . import views

app_name = 'procurement'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('requests/', views.pr_list, name='pr_list'),
    path('requests/create/', views.pr_create, name='pr_create'),
    path('requests/<uuid:pr_id>/', views.pr_detail, name='pr_detail'),
    path('requests/<uuid:pr_id>/add-item/', views.pr_add_item, name='pr_add_item'),
    path('requests/<uuid:pr_id>/submit/', views.pr_submit, name='pr_submit'),
    path('requests/<uuid:pr_id>/approve/', views.pr_approve, name='pr_approve'),
    path('orders/', views.po_list, name='po_list'),
    path('orders/create/', views.po_create, name='po_create'),
    path('orders/<uuid:po_id>/', views.po_detail, name='po_detail'),
    path('orders/<uuid:po_id>/add-item/', views.po_add_item, name='po_add_item'),
    path('orders/<uuid:po_id>/send/', views.po_send, name='po_send'),
    path('orders/<uuid:po_id>/grn/', views.grn_create, name='grn_create'),
]
