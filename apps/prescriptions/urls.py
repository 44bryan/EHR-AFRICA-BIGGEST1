from django.urls import path
from . import views

app_name = 'prescriptions'

urlpatterns = [
    path('drug/new/<uuid:consultation_pk>/', views.drug_prescription_new, name='drug_new'),
    path('drug/<uuid:pk>/', views.drug_prescription_detail, name='drug_detail'),
    path('optical/new/<uuid:consultation_pk>/', views.optical_prescription_new, name='optical_new'),
    path('optical/<uuid:pk>/', views.optical_prescription_detail, name='optical_detail'),
    path('drug/inline/<uuid:consultation_pk>/', views.inline_drug_prescribe, name='drug_inline'),
    path('drug/search/', views.drug_search_ajax, name='drug_search'),
    path('interactions/check/', views.drug_interaction_check_ajax, name='interaction_check'),
    path('interactions/bulk-check/', views.drug_interactions_bulk_check_ajax, name='interaction_bulk_check'),
]
