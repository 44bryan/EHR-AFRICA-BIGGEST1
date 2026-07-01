from django.urls import path
from . import views

app_name = 'cssd'

urlpatterns = [
    path('', views.cssd_dashboard, name='dashboard'),
    path('instruments/', views.instrument_list, name='instrument_list'),
    path('instruments/add/', views.add_instrument, name='add_instrument'),
    path('cycles/', views.sterilization_cycles, name='cycles'),
    path('cycles/record/', views.record_cycle, name='record_cycle'),
    path('dispatch/', views.dispatch_list, name='dispatch_list'),
    path('dispatch/new/', views.dispatch_instrument, name='dispatch_instrument'),
    path('cycles/<uuid:cycle_id>/complete/', views.complete_cycle, name='complete_cycle'),
]
