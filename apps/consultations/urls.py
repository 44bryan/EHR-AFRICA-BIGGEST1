from django.urls import path
from . import views

app_name = 'consultations'

urlpatterns = [
    path('', views.consultation_list_view, name='list'),
    path('workstation/', views.workstation_view, name='workstation'),
    path('triage/', views.triage_workstation_view, name='triage_workstation'),
    path('new/<str:patient_id>/', views.consultation_create_view, name='create'),
    path('<uuid:pk>/', views.consultation_detail_view, name='detail'),
    path('<uuid:pk>/edit/', views.consultation_edit_view, name='edit'),
    path('<uuid:pk>/complete/', views.consultation_complete_view, name='complete'),
    path('<uuid:pk>/cosign/', views.cosign_consultation_view, name='cosign'),
    path('<uuid:pk>/delete/', views.consultation_delete_view, name='delete'),
    path('<uuid:pk>/notes/add/', views.add_note_view, name='add_note'),
    path('<uuid:pk>/clinical-save/', views.save_dept_clinical_view, name='save_clinical'),
    path('<uuid:pk>/exam-update/', views.update_exam_findings_view, name='update_exam'),
    path('<uuid:pk>/diagnosis/add/', views.diagnosis_add_view, name='diagnosis_add'),
    path('<uuid:pk>/diagnosis/<uuid:cd_pk>/remove/', views.diagnosis_remove_view, name='diagnosis_remove'),
    path('autosave/', views.consultation_autosave_view, name='autosave'),
    path('diagnoses/search/', views.diagnosis_search_view, name='diagnosis_search'),
    path('clinic-nurse/', views.clinic_nurse_view, name='clinic_nurse'),
    path('clinic-nurse/call/<uuid:visit_pk>/', views.clinic_call_patient_view, name='clinic_call'),
    path('clinic-nurse/route/<uuid:visit_pk>/', views.nurse_route_patient_view, name='nurse_route'),
]
