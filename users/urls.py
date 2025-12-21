from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AuthViewSet, UserViewSet, StudentViewSet,
    LecturerViewSet, StaffProfileViewSet
)


router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'students', StudentViewSet, basename='student')
router.register(r'lecturers', LecturerViewSet, basename='lecturer')
router.register(r'staff', StaffProfileViewSet, basename='staff')
# Register AuthViewSet without basename since it's not a model viewset
router.register(r'auth', AuthViewSet, basename='auth')


# Import ICT views
from .views_ict import (
    ICTDashboardViewSet,
    UserManagementViewSet,
    StaffAccountCreationViewSet,
    PasswordManagementViewSet,
    SystemConfigurationViewSet,
    ICTOfficerAPIView
)




router = DefaultRouter()
# Existing routes
router.register(r'users', UserViewSet, basename='user')
router.register(r'students', StudentViewSet, basename='student')
router.register(r'lecturers', LecturerViewSet, basename='lecturer')
router.register(r'staff', StaffProfileViewSet, basename='staff')
router.register(r'auth', AuthViewSet, basename='auth')

# ICT Officer routes
router.register(r'ict/dashboard', ICTDashboardViewSet, basename='ict-dashboard')
router.register(r'ict/user-management', UserManagementViewSet, basename='ict-user-management')
router.register(r'ict/staff-accounts', StaffAccountCreationViewSet, basename='ict-staff-accounts')
router.register(r'ict/password-management', PasswordManagementViewSet, basename='ict-password-management')
router.register(r'ict/system-config', SystemConfigurationViewSet, basename='ict-system-config')


urlpatterns = [
    # All auth endpoints are now under /api/auth/auth/ - we need to fix this
    
    # Alternative: Keep explicit paths for auth endpoints
    path('login/', AuthViewSet.as_view({'post': 'login'}), name='login'),
    path('register/student/', AuthViewSet.as_view({'get': 'register_student', 'post': 'register_student'}), name='register-student'),
    path('register/lecturer/', AuthViewSet.as_view({'get': 'register_lecturer', 'post': 'register_lecturer'}), name='register-lecturer'),
    path('register/staff/', AuthViewSet.as_view({'get': 'register_staff', 'post': 'register_staff'}), name='register-staff'),
    path('register/hod/', AuthViewSet.as_view({'get': 'register_hod', 'post': 'register_hod'}), name='register-hod'),
    path('me/', AuthViewSet.as_view({'get': 'me'}), name='current-user'),
    
    # User management routes
    path('', include(router.urls)),
]