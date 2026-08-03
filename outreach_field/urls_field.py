"""Field app URL configuration — outreach module only."""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.shortcuts import redirect

urlpatterns = [
    path('', lambda req: redirect('outreach:dashboard')),
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls', namespace='accounts')),
    path('outreach/', include('apps.outreach.urls', namespace='outreach')),
] + static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
