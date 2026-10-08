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
    path('admissions/<uuid:admission_id>/post-bed-charge/', views.post_bed_charge, name='post_bed_charge'),
    path('admissions/<uuid:admission_id>/transfer-bed/', views.bed_transfer, name='bed_transfer'),

    # ── Surgical pathway ──────────────────────────────────────────────────────
    path('counseling/', views.counseling_queue, name='counseling_queue'),
    path('counseling/<uuid:visit_id>/', views.counseling_record, name='counseling_record'),
    path('surgical-booking/', views.surgical_booking_queue, name='surgical_booking_queue'),
    path('surgical-booking/<uuid:visit_id>/create/', views.surgical_booking_create, name='surgical_booking_create'),
    path('surgical-booking/detail/<uuid:booking_id>/', views.surgical_booking_detail, name='surgical_booking_detail'),
    path('surgical-booking/detail/<uuid:booking_id>/pdf/', views.surgical_booking_slip_pdf, name='surgical_booking_slip_pdf'),
    path('surgical-booking/<uuid:booking_id>/admit/', views.admit_from_booking, name='admit_from_booking'),
    path('surgical-booking/<uuid:booking_id>/cancel/', views.surgical_booking_cancel, name='surgical_booking_cancel'),
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

    # ── Ward & Bed Management (Super Admin) ───────────────────────────────────
    path('wards/manage/', views.ward_manage, name='ward_manage'),
    path('wards/create/', views.ward_create, name='ward_create'),
    path('wards/<uuid:ward_id>/beds/add/', views.bed_add, name='bed_add'),
    path('beds/<uuid:bed_id>/toggle/', views.bed_toggle_status, name='bed_toggle_status'),
    path('beds/<uuid:bed_id>/delete/', views.bed_delete, name='bed_delete'),
    path('wards/<uuid:ward_id>/delete/', views.ward_delete, name='ward_delete'),

    # ── Anaesthetic Record (JCI ASC.5/6) ──────────────────────────────────────
    path('anaesthetic/', views.anaesthetic_record_list, name='anaesthetic_record_list'),
    path('surgical-booking/<uuid:booking_id>/anaesthetic/', views.anaesthetic_record_create, name='anaesthetic_record_create'),
    path('anaesthetic/<uuid:record_id>/', views.anaesthetic_record_detail, name='anaesthetic_record_detail'),

    # ── Nursing Care Plan (JCI COP.8) ─────────────────────────────────────────
    path('admissions/<uuid:admission_id>/care-plan/', views.care_plan_create, name='care_plan_create'),
    path('care-plan/<uuid:plan_id>/', views.care_plan_detail, name='care_plan_detail'),

    # ── Pre-op Check-in, Stats & Printables ───────────────────────────────────
    path('pre-op/checkin/', views.pre_op_checkin, name='pre_op_checkin'),
    path('stats/', views.admission_stats, name='admission_stats'),

    # ── Registration Statistics & Journal ─────────────────────────────────────
    path('registration-stats/', views.registration_stats, name='registration_stats'),
    path('journal/', views.journal_of_registrations, name='journal_of_registrations'),
    path('surgical-booking/<uuid:booking_id>/preop-sheet/', views.preop_instruction_sheet, name='preop_instruction_sheet'),

    # ── Vital Signs Flowsheet ─────────────────────────────────────────────────
    path('admissions/<uuid:admission_id>/vitals/', views.vital_signs_flowsheet, name='vital_signs'),

    # ── Fluid Balance Chart ───────────────────────────────────────────────────
    path('admissions/<uuid:admission_id>/fluids/', views.fluid_balance_chart, name='fluid_balance'),

    # ── Bed Map ───────────────────────────────────────────────────────────────
    path('bed-map/', views.bed_map_view, name='bed_map'),

    # ── Surgical Outcome Tracking ─────────────────────────────────────────────
    path('surgical-outcomes/', views.surgical_outcome_list, name='surgical_outcome_list'),
    path('surgical-booking/<uuid:booking_id>/outcome/', views.surgical_outcome_create, name='surgical_outcome_create'),
    path('surgical-outcomes/report/', views.surgical_outcome_report, name='surgical_outcome_report'),

    # 25002500 Theatre Utilization Report 25002500250025002500250025002500250025002500250025002500250025002500250025002500250025002500250025002500250025002500250025002500250025002500250025002500250025002500250025002500
    path('theatre/utilization/', views.theatre_utilization_report, name='theatre_utilization'),

    # ── Medication Reconciliation (JCI MMU.4) ───────────────────────────────
    path('admissions/<uuid:admission_id>/medrec/', views.medrec_list, name='medrec_list'),
    path('admissions/<uuid:admission_id>/medrec/create/', views.medrec_create, name='medrec_create'),
    path('medrec/<uuid:medrec_id>/', views.medrec_detail, name='medrec_detail'),
    path('medrec/<uuid:medrec_id>/verify/', views.medrec_verify, name='medrec_verify'),
    path('medrec/item/<uuid:item_id>/delete/', views.medrec_item_delete, name='medrec_item_delete'),

    # ── Procedure Room (Injections / Laser / Minor Procedures) ──────────────
    path('procedure-room/', views.procedure_room_queue, name='procedure_room_queue'),
    path('procedure-room/<uuid:visit_id>/create/', views.procedure_room_create, name='procedure_room_create'),
    path('procedure-room/<uuid:record_id>/record/', views.procedure_room_record, name='procedure_room_record'),
    path('procedure-room/<uuid:record_id>/detail/', views.procedure_room_detail, name='procedure_room_detail'),
    path('procedure-room/stats/', views.procedure_room_stats, name='procedure_room_stats'),

    # ── Pre-Op Counselling Checklist G001–G007 ────────────────────────────────
    path('surgical-booking/<uuid:booking_id>/preop-checklist/', views.preop_checklist_view, name='preop_checklist'),
]
