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

    # ── Theatre scheduling board (legacy booking board) ──────────────────────
    path('theatre/', views.theatre_board, name='theatre_board'),
    path('theatre/update-status/', views.theatre_update_status, name='theatre_update_status'),

    # ── Theatre Sessions (full OR management) ────────────────────────────────
    path('theatre/sessions/', views.theatre_session_list, name='theatre_session_list'),
    path('theatre/sessions/new/', views.theatre_session_create, name='theatre_session_create'),
    path('theatre/sessions/<uuid:session_id>/', views.theatre_session_detail, name='theatre_session_detail'),
    path('theatre/sessions/<uuid:session_id>/status/', views.theatre_session_update_status, name='theatre_session_update_status'),
    path('theatre/sessions/<uuid:session_id>/add-procedure/', views.theatre_add_procedure, name='theatre_add_procedure'),
    path('theatre/procedures/<uuid:procedure_id>/record/', views.theatre_procedure_record, name='theatre_procedure_record'),

    # ── Ward Rounds ───────────────────────────────────────────────────────────
    path('admissions/<uuid:admission_id>/ward-round/', views.ward_round_add, name='ward_round_add'),
    path('admissions/<uuid:admission_id>/discharge-pdf/', views.discharge_summary_pdf, name='discharge_summary_pdf'),
]
