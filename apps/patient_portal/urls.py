from django.urls import path
from . import views

app_name = 'portal'

urlpatterns = [
    path('', views.portal_login, name='login'),
    path('logout/', views.portal_logout, name='logout'),
    path('dashboard/', views.portal_dashboard, name='dashboard'),
    path('appointments/', views.portal_appointments, name='appointments'),
    path('appointments/book/', views.portal_book_appointment, name='book_appointment'),
    path('invoices/', views.portal_invoices, name='invoices'),
    path('prescriptions/', views.portal_prescriptions, name='prescriptions'),
]
