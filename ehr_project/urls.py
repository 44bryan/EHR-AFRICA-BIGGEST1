from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import render

# Custom error handlers
def handler403(request, exception=None):
    return render(request, '403.html', status=403)

handler403 = handler403

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.dashboard.urls', namespace='dashboard')),
    path('accounts/', include('apps.accounts.urls', namespace='accounts')),
    path('patients/', include('apps.patients.urls', namespace='patients')),
    path('appointments/', include('apps.appointments.urls', namespace='appointments')),
    path('consultations/', include('apps.consultations.urls', namespace='consultations')),
    path('prescriptions/', include('apps.prescriptions.urls', namespace='prescriptions')),
    path('investigations/', include('apps.investigations.urls', namespace='investigations')),
    path('laboratory/', include('apps.laboratory.urls', namespace='laboratory')),
    path('reports/', include('apps.reports.urls', namespace='reports')),
    path('ai-assistant/', include('apps.ai_assistant.urls', namespace='ai_assistant')),
    path('api/', include('apps.api.urls', namespace='api')),
    # Phase 2 modules
    path('qms/', include('apps.qms.urls', namespace='qms')),
    path('pharmacy/', include('apps.pharmacy.urls', namespace='pharmacy')),
    path('inventory/', include('apps.inventory.urls', namespace='inventory')),
    path('opticals/', include('apps.opticals.urls', namespace='opticals')),
    path('ipd/', include('apps.ipd.urls', namespace='ipd')),
    path('cssd/', include('apps.cssd.urls', namespace='cssd')),
    path('hrms/', include('apps.hrms.urls', namespace='hrms')),
    path('leads/', include('apps.leads.urls', namespace='leads')),
    path('feedback/', include('apps.feedback.urls', namespace='feedback')),
    path('opd/', include('apps.opd.urls', namespace='opd')),
    path('leadership/', include('apps.leadership.urls', namespace='leadership')),
    path('billing/', include('apps.billing.urls', namespace='billing')),
    path('reception/', include('apps.reception.urls', namespace='reception')),
    path('notifications/', include('apps.notifications.urls', namespace='notifications')),
    path('outreach/', include('apps.outreach.urls', namespace='outreach')),
    path('departments/', include('apps.departments.urls', namespace='departments')),
    path('portal/', include('apps.patient_portal.urls', namespace='portal')),
    # New enterprise modules
    path('hmo/', include('apps.hmo.urls', namespace='hmo')),
    path('blood-bank/', include('apps.blood_bank.urls', namespace='blood_bank')),
    path('infection-control/', include('apps.infection_control.urls', namespace='infection_control')),
    path('dietary/', include('apps.dietary.urls', namespace='dietary')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    try:
        import debug_toolbar
        urlpatterns = [path('__debug__/', include(debug_toolbar.urls))] + urlpatterns
    except ImportError:
        pass

# Admin customization
admin.site.site_header = 'EHR Africa Administration'
admin.site.site_title = 'EHR Africa'
admin.site.index_title = 'Ophthalmology EHR System'
