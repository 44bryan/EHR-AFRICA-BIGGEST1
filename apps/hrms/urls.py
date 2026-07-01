from django.urls import path
from . import views

app_name = 'hrms'

urlpatterns = [
    path('', views.hrms_dashboard, name='dashboard'),
    path('staff/', views.staff_list, name='staff_list'),
    path('staff/<uuid:profile_id>/', views.staff_detail, name='staff_detail'),
    path('leave/', views.leave_requests, name='leave_requests'),
    path('leave/apply/', views.apply_leave, name='apply_leave'),
    path('leave/my/', views.my_leaves, name='my_leaves'),
    path('leave/<uuid:leave_id>/action/', views.approve_leave, name='approve_leave'),
    path('attendance/', views.attendance_register, name='attendance'),
    path('clock/', views.clock_in_out, name='clock_in_out'),
    # Payroll
    path('payroll/', views.payroll_list, name='payroll_list'),
    path('payroll/create/', views.payroll_create, name='payroll_create'),
    path('payroll/<uuid:run_id>/', views.payroll_detail, name='payroll_detail'),
    path('payroll/payslip/<uuid:entry_id>/', views.payslip, name='payslip'),
]
