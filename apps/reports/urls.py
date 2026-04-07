from django.urls import path
from . import views

app_name = 'reports'

urlpatterns = [
    path('consultation/<uuid:pk>/pdf/', views.consultation_pdf_view, name='consultation_pdf'),
    path('prescription/<uuid:pk>/pdf/', views.drug_prescription_pdf_view, name='drug_prescription_pdf'),
    path('optical/<uuid:pk>/pdf/', views.optical_prescription_pdf_view, name='optical_prescription_pdf'),
    path('investigation/<uuid:pk>/pdf/', views.investigation_pdf_view, name='investigation_pdf'),
    path('lab/<uuid:pk>/pdf/', views.lab_report_pdf_view, name='lab_pdf'),
    path('visit/<uuid:pk>/pdf/', views.visit_summary_pdf_view, name='visit_summary_pdf'),
    path('consultation/<uuid:consultation_pk>/certificate/', views.medical_certificate_view, name='medical_certificate'),
    path('consultation/<uuid:consultation_pk>/referral/', views.referral_letter_view, name='referral_letter'),
    path('patient/<str:patient_id>/summary/', views.patient_summary_pdf_view, name='patient_summary_pdf'),
]
