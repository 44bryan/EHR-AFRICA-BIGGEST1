from django.urls import path
from . import views

app_name = 'qms'

urlpatterns = [
    # Dashboard
    path('', views.queue_dashboard, name='dashboard'),

    # Entry ticket issuance — per entrance point
    path('gate/', views.gate_issue, name='gate_issue'),                       # Standard patients only
    path('gate/prereg/<str:code>/arrive/', views.prereg_mark_arrived, name='prereg_arrive'),  # Gatekeeper confirms pre-reg arrival
    path('vip-reception/', views.vip_reception_issue, name='vip_reception'),  # VIP back entrance
    path('express-desk/', views.express_desk_issue, name='express_desk'),     # Express/FT side entrance
    path('cashier/', views.cashier_issue, name='cashier_issue'),              # Fallback / walk-in

    # Receptionist — new patient registration queue
    path('receptionist/', views.receptionist_queue, name='receptionist'),
    path('receptionist/<uuid:token_id>/complete/', views.receptionist_complete_registration, name='receptionist_complete'),

    # Department routing (AJAX/HTMX)
    path('route/', views.route_to_dept, name='route_to_dept'),

    # Staff shortcuts
    path('my-counter/', views.my_counter, name='my_counter'),
    path('no-counter/', views.no_counter_view, name='no_counter'),
    path('doctor-queue/', views.doctor_queue, name='doctor_queue'),

    # TV display board (public, no login)
    path('display/', views.display_board, name='display_board'),
    path('display/names/', views.names_board, name='names_board'),
    path('display/rooms/', views.consult_room_display, name='consult_room_display'),

    # Daily census
    path('census/', views.daily_census, name='daily_census'),

    # Counter assignment (admin only)
    path('counter-assign/', views.counter_assign_view, name='counter_assign'),

    # Counter management CRUD (admin only)
    path('counters/', views.counter_manage_view, name='counter_manage'),
    path('counters/new/', views.counter_create_view, name='counter_create'),
    path('counters/<uuid:counter_id>/edit/', views.counter_edit_view, name='counter_edit'),
    path('counters/<uuid:counter_id>/toggle/', views.counter_toggle_view, name='counter_toggle'),
    path('counters/<uuid:counter_id>/delete/', views.counter_delete_view, name='counter_delete'),

    # Zone management CRUD (admin only)
    path('zones/', views.zone_manage_view, name='zone_manage'),
    path('zones/new/', views.zone_create_view, name='zone_create'),
    path('zones/<uuid:zone_id>/edit/', views.zone_edit_view, name='zone_edit'),
    path('zones/remap-tier/', views.tier_remap_view, name='tier_remap'),

    # Counter staff
    path('counter/<uuid:counter_id>/', views.counter_view, name='counter'),
    path('counter/<uuid:counter_id>/call-next/', views.call_next, name='call_next'),
    path('counter/<uuid:counter_id>/clear/', views.clear_counter, name='clear_counter'),

    # Token actions
    path('token/<uuid:token_id>/complete/', views.complete_token, name='complete_token'),
    path('token/<uuid:token_id>/cashier-done/', views.cashier_complete, name='cashier_complete'),
    path('token/<uuid:token_id>/skip/', views.skip_token, name='skip_token'),
    path('token/<uuid:token_id>/no-show/', views.no_show, name='no_show'),

    # Today's Roster — admin assigns doctors to rooms
    path('roster/', views.roster_view, name='roster'),

    # My Room Today — doctor sees their assigned room (read-only)
    path('room-checkin/', views.room_checkin_view, name='room_checkin'),

    # Room board AJAX (triage dispatch panel + room check-in page)
    path('room-board/', views.room_board_ajax, name='room_board'),

    # JSON endpoints
    path('stats/', views.queue_stats, name='stats'),
    path('patient/<str:patient_id>/status/', views.patient_queue_status, name='patient_status'),
]
