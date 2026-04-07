from django.urls import path
from . import views

app_name = 'prescriptions'

urlpatterns = [
    path('drug/new/<uuid:consultation_pk>/', views.drug_prescription_new, name='drug_new'),
    path('drug/<uuid:pk>/', views.drug_prescription_detail, name='drug_detail'),
    path('optical/new/<uuid:consultation_pk>/', views.optical_prescription_new, name='optical_new'),
    path('optical/<uuid:pk>/', views.optical_prescription_detail, name='optical_detail'),
]
