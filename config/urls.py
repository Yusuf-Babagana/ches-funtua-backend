"""
URL Configuration for College Management System
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('admin/', admin.site.urls),

    # API endpoints
    path('api/auth/', include('users.urls')),
    path('api/academics/', include('academics.urls')),
    path('api/finance/', include('finance.urls')),
    path('api/admissions/', include('admissions.urls')),
    path('api/', include('academics.urls')), # Expose academics endpoints at root api/ for frontend compatibility


    # JWT token refresh
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Django-rendered frontend (session-authenticated templates). Mounted at
    # the root, after the api/ and admin/ prefixes above so it never shadows
    # them -- landing page, login/logout, and every /dashboard/<role>/ page.
    path('', include('portal.urls')),
]

# Custom error pages (see templates/errors/) -- only take effect when
# DEBUG=False, i.e. in production; Django's own debug pages are used locally.
handler403 = 'portal.views_errors.error_403'
handler404 = 'portal.views_errors.error_404'
handler500 = 'portal.views_errors.error_500'

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

# Admin site customization
admin.site.site_header = "College Management System"
admin.site.site_title = "CMS Admin"
admin.site.index_title = "Welcome to College Management System Administration"