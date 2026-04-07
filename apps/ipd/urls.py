from django.urls import path
from . import views

app_name = 'ipd'

urlpatterns = [
    path('', views.ipd_dashboard, name='dashboard'),
    path('wards/', views.ward_list, name='ward_list'),
    path('admit/', views.admit_patient, name='admit'),
    path('admissions/<uuid:admission_id>/', views.admission_detail, name='admission_detail'),
    path('admissions/<uuid:admission_id>/nursing-note/', views.add_nursing_note, name='add_nursing_note'),
    path('admissions/<uuid:admission_id>/discharge/', views.discharge_patient, name='discharge'),

    # ── Surgical pathway ──────────────────────────────────────────────────────
    path('counseling/', views.counseling_queue, name='counseling_queue'),
    path('counseling/<uuid:visit_id>/', views.counseling_record, name='counseling_record'),
    path('surgical-booking/', views.surgical_booking_queue, name='surgical_booking_queue'),
    path('surgical-booking/<uuid:visit_id>/create/', views.surgical_booking_create, name='surgical_booking_create'),
    path('surgical-booking/detail/<uuid:booking_id>/', views.surgical_booking_detail, name='surgical_booking_detail'),
    path('surgical-booking/detail/<uuid:booking_id>/pdf/', views.surgical_booking_slip_pdf, name='surgical_booking_slip_pdf'),
    path('surgical-booking/<uuid:booking_id>/admit/', views.admit_from_booking, name='admit_from_booking'),
    path('nursing-stats/', views.ipd_nursing_stats, name='nursing_stats'),

    # ── MAR — Medication Administration Record ────────────────────────────────
    path('admissions/<uuid:admission_id>/mar/add/', views.mar_add, name='mar_add'),
    path('mar/<uuid:mar_id>/administer/', views.mar_administer, name='mar_administer'),

    # ── Theatre scheduling board ──────────────────────────────────────────────
    path('theatre/', views.theatre_board, name='theatre_board'),
    path('theatre/update-status/', views.theatre_update_status, name='theatre_update_status'),
]
