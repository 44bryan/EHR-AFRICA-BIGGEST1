from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('password-change/', views.password_change_view, name='password_change'),
    path('profile/', views.profile_view, name='profile'),
    # Legacy list (still accessible)
    path('users/', views.user_list_view, name='user_list'),
    path('users/create/', views.user_create_view, name='user_create'),
    path('users/<uuid:pk>/edit/', views.user_edit_view, name='user_edit'),
    # Super Admin staff hub
    path('staff/', views.staff_hub_view, name='staff_hub'),
    path('staff/<uuid:pk>/toggle-active/', views.toggle_user_active_view, name='toggle_active'),
    path('staff/<uuid:pk>/reset-password/', views.reset_staff_password_view, name='reset_password'),
    # Two-Factor Authentication
    path('2fa/verify/', views.two_fa_verify_view, name='two_fa_verify'),
    path('2fa/setup/', views.two_fa_setup_view, name='two_fa_setup'),
    # System Module Settings
    path('system/modules/', views.system_modules_view, name='system_modules'),
]
