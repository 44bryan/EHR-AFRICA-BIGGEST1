from django.urls import path
from django.views.generic import RedirectView
from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.home_view, name='home'),
    # Super Admin IT panel — main
    path('sysadmin/', views.sysadmin_view, name='sysadmin'),
    path('sysadmin/health/', views.health_check_view, name='health_check'),
    path('sysadmin/backup/', views.sysadmin_trigger_backup, name='trigger_backup'),
    path('sysadmin/tools/', views.sysadmin_tools, name='sysadmin_tools'),
    path('sysadmin/audit/', views.sysadmin_audit_log, name='sysadmin_audit'),
    path('sysadmin/settings/', views.sysadmin_settings, name='sysadmin_settings'),
    path('sysadmin/export/audit/', views.export_audit_log, name='export_audit_log'),
    path('sysadmin/export/patients/', views.export_patient_list, name='export_patient_list'),
    # Super Admin user management
    path('sysadmin/users/create/', views.sysadmin_user_create, name='sysadmin_user_create'),
    path('sysadmin/users/<uuid:pk>/edit/', views.sysadmin_user_edit, name='sysadmin_user_edit'),
    path('sysadmin/users/<uuid:pk>/reset-password/', views.sysadmin_user_reset_password, name='sysadmin_reset_password'),
    path('sysadmin/users/<uuid:pk>/toggle/', views.sysadmin_user_toggle, name='sysadmin_user_toggle'),
    # Leadership audit trail (CEO, Medical Director, Finance Director, Admin Director)
    path('audit-log/', views.leadership_audit_log, name='audit_log'),
    # Recycle Bin (Super Admin only)
    path('sysadmin/recycle-bin/', views.recycle_bin, name='recycle_bin'),
    path('sysadmin/recycle-bin/<str:model>/<str:pk>/restore/', views.recycle_bin_restore, name='recycle_bin_restore'),
    path('sysadmin/recycle-bin/<str:model>/<str:pk>/delete/', views.recycle_bin_delete, name='recycle_bin_delete'),
    # Legacy redirect — old receipts linked to this before the POS refactor
    path('dashboard/cashier/', RedirectView.as_view(url='/billing/pos/', permanent=False)),
    # Cashier self-select desk/tier
    path('cashier/select-desk/', views.cashier_select_desk, name='cashier_select_desk'),
]
