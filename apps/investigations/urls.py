from django.urls import path
from . import views

app_name = 'investigations'

urlpatterns = [
    path('', views.investigation_list_view, name='list'),
    path('workstation/', views.investigation_workstation_view, name='workstation'),
    path('order/<uuid:consultation_pk>/', views.investigation_order_view, name='order'),
    path('<uuid:pk>/', views.investigation_detail_view, name='detail'),
    path('<uuid:pk>/result/', views.add_result_view, name='add_result'),
    path('<uuid:pk>/verify/', views.verify_result_view, name='verify'),
    path('<uuid:pk>/cancel/', views.cancel_investigation_order, name='cancel'),

    # ── DICOM Imaging Studies ─────────────────────────────────────────────────
    path('imaging/', views.imaging_study_list, name='imaging_list'),
    path('imaging/create/', views.imaging_study_create, name='imaging_create'),
    path('imaging/<uuid:study_id>/', views.imaging_study_detail, name='imaging_detail'),
    path('imaging/<uuid:study_id>/report/', views.imaging_study_report, name='imaging_report'),
    path('patient/<str:patient_id>/imaging/', views.patient_imaging_list, name='patient_imaging'),
]
