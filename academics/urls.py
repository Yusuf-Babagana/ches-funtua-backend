from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DepartmentViewSet, CourseViewSet, EnrollmentViewSet,
    GradeViewSet, AttendanceViewSet, SemesterViewSet
)
from .views_student import (
    StudentDashboardViewSet, 
    CurrentSemesterAPIView, 
    StudentRegistrationStatusAPIView
)
from .views_registration import CourseOfferingViewSet, RegistrationViewSet
from .views_hod import HODDashboardViewSet 
from .views_approval import RegistrationApprovalViewSet
from .views_admin import (
    SuperAdminDepartmentViewSet, 
    SuperAdminCourseViewSet,
    SuperAdminManagementViewSet,
    SuperAdminSemesterViewSet,
    SystemHealthViewSet,
    LevelConfigurationViewSet
)
from .views_lecturer import (
    LecturerDashboardViewSet,
    LecturerCourseViewSet,
    LecturerGradeViewSet,
    LecturerAttendanceViewSet,
    LecturerApprovalViewSet,
    LecturerAPIView
)
from .views_registrar import (
    RegistrarDashboardViewSet,
    MatricAssignmentViewSet,
    AcademicSessionViewSet,
    FinalResultApprovalViewSet,
    StudentClearanceViewSet,
    RegistrarAPIView
)
from .views_exam_officer import (
    ExamOfficerDashboardViewSet,
    ExamOfficerRegistrationViewSet,
    ResultCompilationViewSet,
    ExamListViewSet,
    ExamTimetableViewSet,
    ExamOfficerAPIView
)
from .views_result_workflow import (
    HODResultWorkflowViewSet,
    ExamOfficerResultWorkflowViewSet,
    RegistrarResultWorkflowViewSet
)
from .views_transcript import TranscriptViewSet

router = DefaultRouter()

# General Academics
router.register(r'departments', DepartmentViewSet, basename='department')
router.register(r'courses', CourseViewSet, basename='course')
router.register(r'enrollments', EnrollmentViewSet, basename='enrollment')
router.register(r'grades', GradeViewSet, basename='grade')
router.register(r'attendance', AttendanceViewSet, basename='attendance')
router.register(r'semesters', SemesterViewSet, basename='semester')

# HOD Routes
router.register(r'hod/dashboard', HODDashboardViewSet, basename='hod-dashboard')

# Registration
router.register(r'course-offerings', CourseOfferingViewSet, basename='course-offering')
router.register(r'registrations', RegistrationViewSet, basename='course-registration')

# Dashboards
router.register(r'student/dashboard', StudentDashboardViewSet, basename='student-dashboard')

router.register(r'lecturer/dashboard', LecturerDashboardViewSet, basename='lecturer-dashboard')
router.register(r'lecturer/courses', LecturerCourseViewSet, basename='lecturer-courses')
router.register(r'lecturer/grades', LecturerGradeViewSet, basename='lecturer-grades')
router.register(r'lecturer/attendance', LecturerAttendanceViewSet, basename='lecturer-attendance')
router.register(r'lecturer/approvals', LecturerApprovalViewSet, basename='lecturer-approvals')

# Registrar Routes
router.register(r'registrar/dashboard', RegistrarDashboardViewSet, basename='registrar-dashboard')
router.register(r'registrar/matric-assignment', MatricAssignmentViewSet, basename='registrar-matric')
router.register(r'registrar/academic-sessions', AcademicSessionViewSet, basename='registrar-sessions')
router.register(r'registrar/final-approvals', FinalResultApprovalViewSet, basename='registrar-approvals')
router.register(r'registrar/clearance', StudentClearanceViewSet, basename='registrar-clearance')

# Exam Officer Routes
router.register(r'exam-officer/dashboard', ExamOfficerDashboardViewSet, basename='exam-officer-dashboard')
router.register(r'exam-officer/registrations', ExamOfficerRegistrationViewSet, basename='exam-officer-registrations')
router.register(r'exam-officer/results', ResultCompilationViewSet, basename='exam-officer-results')
router.register(r'exam-officer/exam-list', ExamListViewSet, basename='exam-officer-list')
router.register(r'exam-officer/timetable', ExamTimetableViewSet, basename='exam-officer-timetable')

# Approval Routes
router.register(r'registration-approvals', RegistrationApprovalViewSet, basename='registration-approval')

# Super Admin Routes
router.register(r'admin/departments', SuperAdminDepartmentViewSet, basename='admin-department')
router.register(r'admin/courses', SuperAdminCourseViewSet, basename='admin-course')
router.register(r'admin/semesters', SuperAdminSemesterViewSet, basename='admin-semesters')
router.register(r'admin/management', SuperAdminManagementViewSet, basename='admin-management')
router.register(r'admin/system-health', SystemHealthViewSet, basename='admin-system-health')
router.register(r'admin/level-config', LevelConfigurationViewSet, basename='admin-level-config')

# Result Workflow Routes
router.register(r'workflow/hod/results', HODResultWorkflowViewSet, basename='hod-result-workflow')
router.register(r'workflow/exam-officer/results', ExamOfficerResultWorkflowViewSet, basename='eo-result-workflow')
router.register(r'workflow/registrar/results', RegistrarResultWorkflowViewSet, basename='registrar-result-workflow')

# Transcript Route
router.register(r'transcripts', TranscriptViewSet, basename='transcript')

urlpatterns = [
    path('current-semester/', CurrentSemesterAPIView.as_view(), name='current-semester'),
    path('registration-status/', StudentRegistrationStatusAPIView.as_view(), name='registration-status'),
    path('semesters/current/', CurrentSemesterAPIView.as_view(), name='semesters-current'),
    path('registrar/profile/', RegistrarAPIView.as_view(), name='registrar-profile'),
    path('exam-officer/profile/', ExamOfficerAPIView.as_view(), name='exam-officer-profile'),
    
    path('', include(router.urls)),
]