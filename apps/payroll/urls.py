from django.urls import path
from . import views

app_name = 'payroll'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('structures/', views.structure_list, name='structure_list'),
    path('structures/create/', views.structure_create, name='structure_create'),
    path('structures/<uuid:structure_id>/edit/', views.structure_edit, name='structure_edit'),
    path('components/', views.component_list, name='component_list'),
    path('components/create/', views.component_create, name='component_create'),
    path('staff/', views.assignment_list, name='assignment_list'),
    path('staff/<uuid:user_id>/assign/', views.assignment_save, name='assignment_save'),
    path('runs/', views.run_list, name='run_list'),
    path('runs/create/', views.run_create, name='run_create'),
    path('runs/<uuid:run_id>/', views.run_detail, name='run_detail'),
    path('runs/<uuid:run_id>/generate/', views.run_generate, name='run_generate'),
    path('runs/<uuid:run_id>/approve/', views.run_approve, name='run_approve'),
    path('runs/<uuid:run_id>/mark-paid/', views.run_mark_paid, name='run_mark_paid'),
    path('payslips/<uuid:slip_id>/', views.payslip_detail, name='payslip_detail'),
    path('payslips/<uuid:slip_id>/print/', views.payslip_print, name='payslip_print'),
    path('payslips/<uuid:slip_id>/pdf/', views.payslip_pdf, name='payslip_pdf'),
    path('runs/<uuid:run_id>/cnps/', views.cnps_declaration, name='cnps_declaration'),
]
