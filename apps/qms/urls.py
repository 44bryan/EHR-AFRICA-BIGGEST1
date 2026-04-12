from django.urls import path
from . import views

app_name = 'qms'

urlpatterns = [
    # Dashboard
    path('', views.queue_dashboard, name='dashboard'),

    # Entry ticket issuance — per entrance point
    path('gate/', views.gate_issue, name='gate_issue'),                       # Standard patients only
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

    # Daily census
    path('census/', views.daily_census, name='daily_census'),

    # Counter assignment (admin only)
    path('counter-assign/', views.counter_assign_view, name='counter_assign'),

    # Counter staff
    path('counter/<uuid:counter_id>/', views.counter_view, name='counter'),
    path('counter/<uuid:counter_id>/call-next/', views.call_next, name='call_next'),
    path('counter/<uuid:counter_id>/clear/', views.clear_counter, name='clear_counter'),

    # Token actions
    path('token/<uuid:token_id>/complete/', views.complete_token, name='complete_token'),
    path('token/<uuid:token_id>/cashier-done/', views.cashier_complete, name='cashier_complete'),
    path('token/<uuid:token_id>/skip/', views.skip_token, name='skip_token'),
    path('token/<uuid:token_id>/no-show/', views.no_show, name='no_show'),

    # JSON endpoints
    path('stats/', views.queue_stats, name='stats'),
    path('patient/<str:patient_id>/status/', views.patient_queue_status, name='patient_status'),
]
