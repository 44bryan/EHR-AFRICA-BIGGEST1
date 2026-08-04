from django.urls import path
from . import views

app_name = 'dietary'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('orders/', views.order_list, name='order_list'),
    path('orders/new/', views.order_create, name='order_create'),
    path('orders/<int:pk>/', views.order_detail, name='order_detail'),
    path('admission/<int:admission_id>/restriction/add/', views.restriction_add, name='restriction_add'),
    path('admission/<int:admission_id>/assessment/new/', views.assessment_create, name='assessment_create'),
    path('orders/<int:order_id>/meal-plan/new/', views.meal_plan_create, name='meal_plan_create'),
    path('meal-plans/<int:pk>/serve/', views.meal_plan_serve, name='meal_plan_serve'),
]
