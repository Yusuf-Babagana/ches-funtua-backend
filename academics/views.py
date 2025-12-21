from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count # Import Count

from .models import (
    Department, Course, Enrollment, Grade,
    Attendance, Semester, StudentAcademicRecord
)
from .serializers import (
    DepartmentSerializer, CourseSerializer, EnrollmentSerializer,
    GradeSerializer, AttendanceSerializer, SemesterSerializer,
    StudentAcademicRecordSerializer, DepartmentSerializer 
)
from users.permissions import (
    IsAdminStaff, CanManageGrades, IsLecturer, IsStudent
)


# academics/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import Semester, CourseRegistration
from finance.models import Invoice

class RegistrationViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'])
    def eligibility(self, request):
        """
        Check if the student is allowed to register courses.
        Returns: Fee status, Semester status, and final eligibility.
        """
        user = request.user
        if not hasattr(user, 'student_profile'):
            return Response({'error': 'Student profile not found'}, status=403)
            
        student = user.student_profile
        
        # 1. Get Current Semester
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            return Response({
                'can_register': False,
                'reason': 'No active academic session.',
                'is_registration_active': False
            })

        # 2. Check Registration Window (Time)
        now = timezone.now()
        is_registration_active = True
        reason = "Eligible to register."
        
        if current_semester.registration_deadline and now > current_semester.registration_deadline:
            is_registration_active = False
            reason = "Registration period has closed."

        # 3. Check Fee Status (Finance)
        # Find the invoice for this specific session/semester
        # We consider 'paid' or 'partially_paid' (depending on your school policy)
        # STRICT MODE: Must be 'paid'
        has_paid_fees = False
        
        invoice = Invoice.objects.filter(
            student=student, 
            session=current_semester.session,
            semester=current_semester.semester
        ).first()

        if invoice and invoice.status == 'paid':
            has_paid_fees = True
        
        # If no invoice exists, they obviously haven't paid
        if not invoice:
            has_paid_fees = False

        # 4. Final Decision
        can_register = is_registration_active and has_paid_fees

        if not has_paid_fees:
            reason = "Tuition fees not paid."
        elif not is_registration_active:
            reason = "Registration closed."

        return Response({
            'can_register': can_register,
            'has_paid_fees': has_paid_fees,
            'is_registration_active': is_registration_active,
            'registration_deadline': current_semester.registration_deadline,
            'current_semester': f"{current_semester.session} {current_semester.semester}",
            'reason': reason
        })


# ========================
# Department Viewset
# ========================

class DepartmentViewSet(viewsets.ModelViewSet):
    """Department operations"""
    # We remove the static queryset property and use get_queryset
    serializer_class = DepartmentSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'code']

    def get_queryset(self):
        """
        Dynamically calculate counts for students, lecturers, and courses
        """
        return Department.objects.select_related('hod__user').annotate(
            student_count=Count('student', distinct=True),
            # Note: 'lecturer' refers to the related_name from the Lecturer model. 
            # If not defined in models.py, Django defaults to 'lecturer_set' or 'lecturer' (lowercase model name)
            lecturer_count=Count('lecturer', distinct=True),
            course_count=Count('courses', distinct=True)
        ).all()

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated()]

    

    @action(detail=False, methods=['get'])
    def my_department(self, request):
        """
        Get the department managed by the currently logged-in HOD.
        Endpoint: /api/academics/departments/my_department/
        """
        user = request.user

        # 1. Safety Check: Is the user a Lecturer?
        # Accessing the reverse relationship safely
        try:
            lecturer_profile = user.lecturer_profile
        except (AttributeError, Lecturer.DoesNotExist):
            return Response(
                {'error': 'User is not a lecturer'}, 
                status=status.HTTP_403_FORBIDDEN
            )

        # 2. Safety Check: Is this lecturer an HOD for a department?
        try:
            # We look for a Department where 'hod' matches this lecturer
            department = Department.objects.get(hod=lecturer_profile)
            
            # 3. Serialize and return
            serializer = self.get_serializer(department)
            return Response({
                'department': serializer.data,
                'status': 'success'
            })
            
        except Department.DoesNotExist:
            return Response(
                {'error': 'You are not assigned as HOD to any department'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            # Catch unexpected errors to prevent 500 crashes
            print(f"Error in my_department: {str(e)}")
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
# ========================
# Course Viewset
# ========================

class CourseViewSet(viewsets.ModelViewSet):
    """Course operations"""
    queryset = Course.objects.select_related('department', 'lecturer__user').all()
    serializer_class = CourseSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['department', 'level', 'semester', 'lecturer', 'is_elective']
    search_fields = ['code', 'title']
    ordering_fields = ['code', 'title', 'credits']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsAuthenticated()]

    @action(detail=True, methods=['get'])
    def students(self, request, pk=None):
        """Get students enrolled in the course"""
        course = self.get_object()
        enrollments = Enrollment.objects.filter(
            course=course,
            status='enrolled'
        ).select_related('student__user')

        page = self.paginate_queryset(enrollments)
        serializer = EnrollmentSerializer(page, many=True)
        return self.get_paginated_response(serializer.data)


# ========================
# Enrollment Viewset
# ========================

class EnrollmentViewSet(viewsets.ModelViewSet):
    """Enrollment operations"""
    queryset = Enrollment.objects.select_related(
        'student__user',
        'course__department'
    ).all()
    serializer_class = EnrollmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['student', 'course', 'session', 'semester', 'status']
    search_fields = ['student__matric_number', 'course__code']
    ordering_fields = ['enrollment_date', 'created_at']

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        # Students see only their enrollments
        if user.role == 'student' and hasattr(user, 'student_profile'):
            queryset = queryset.filter(student=user.student_profile)

        # Lecturers see enrollments for their courses
        elif user.role == 'lecturer' and hasattr(user, 'lecturer_profile'):
            queryset = queryset.filter(course__lecturer=user.lecturer_profile)

        return queryset


# ========================
# Grade Viewset
# ========================

class GradeViewSet(viewsets.ModelViewSet):
    """Grade operations"""
    queryset = Grade.objects.select_related(
        'student__user',
        'course',
        'uploaded_by__user'
    ).all()
    serializer_class = GradeSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['student', 'course', 'session', 'semester', 'grade_letter']
    search_fields = ['student__matric_number', 'course__code']
    ordering_fields = ['created_at', 'score']

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        if user.role == 'student' and hasattr(user, 'student_profile'):
            return queryset.filter(student=user.student_profile)

        if user.role == 'lecturer' and hasattr(user, 'lecturer_profile'):
            return queryset.filter(course__lecturer=user.lecturer_profile)

        return queryset

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [CanManageGrades()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        if hasattr(self.request.user, 'lecturer_profile'):
            serializer.save(uploaded_by=self.request.user.lecturer_profile)
        else:
            serializer.save()

    # -------- GPA --------
    @action(detail=False, methods=['get'])
    def student_gpa(self, request):
        """Calculate GPA"""
        student_id = request.query_params.get('student')
        session = request.query_params.get('session')
        semester = request.query_params.get('semester')

        if not student_id:
            return Response({'error': 'student parameter is required'}, status=400)

        grades = Grade.objects.filter(student_id=student_id)
        if session:
            grades = grades.filter(session=session)
        if semester:
            grades = grades.filter(semester=semester)

        if not grades.exists():
            return Response({'gpa': 0, 'total_credits': 0})

        total_points = sum(float(g.grade_points) * g.course.credits for g in grades)
        total_credits = sum(g.course.credits for g in grades)

        gpa = total_points / total_credits if total_credits else 0

        return Response({
            'gpa': round(gpa, 2),
            'total_credits': total_credits,
            'courses_taken': grades.count()
        })

    # -------- CGPA --------
    @action(detail=False, methods=['get'])
    def student_cgpa(self, request):
        student_id = request.query_params.get('student')

        if not student_id:
            return Response({'error': 'student parameter is required'}, status=400)

        grades = Grade.objects.filter(student_id=student_id)
        if not grades.exists():
            return Response({'cgpa': 0, 'total_credits': 0})

        total_points = sum(float(g.grade_points) * g.course.credits for g in grades)
        total_credits = sum(g.course.credits for g in grades)
        cgpa = total_points / total_credits if total_credits else 0

        return Response({
            'cgpa': round(cgpa, 2),
            'total_credits': total_credits,
            'total_courses': grades.count()
        })

    # -------- Grades for authenticated student --------
    @action(detail=False, methods=['get'], permission_classes=[IsStudent])
    def student_grades(self, request):
        if not hasattr(request.user, 'student_profile'):
            return Response({'error': 'Student profile not found'}, status=400)

        student = request.user.student_profile
        grades = Grade.objects.filter(student=student).select_related('course', 'uploaded_by__user')

        page = self.paginate_queryset(grades)
        if page:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(grades, many=True)
        return Response(serializer.data)


# ========================
# Student Academic Record Viewset
# ========================

class StudentAcademicRecordViewSet(viewsets.ReadOnlyModelViewSet):
    """Student academic record operations"""
    queryset = StudentAcademicRecord.objects.select_related(
        'student__user', 'student__department'
    ).all()
    serializer_class = StudentAcademicRecordSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['student', 'level', 'session', 'semester']
    search_fields = ['student__matric_number']
    ordering_fields = ['session', 'semester', 'gpa']

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        if user.role == 'student' and hasattr(user, 'student_profile'):
            return queryset.filter(student=user.student_profile)

        if user.role == 'lecturer' and hasattr(user, 'lecturer_profile'):
            return queryset.filter(student__department=user.lecturer_profile.department)

        return queryset

    @action(detail=False, methods=['get'], permission_classes=[IsStudent])
    def current_gpa(self, request):
        """Get current semester GPA for the authenticated student"""
        if not hasattr(request.user, 'student_profile'):
            return Response({'error': 'Student profile not found'}, status=400)

        student = request.user.student_profile
        current_semester = Semester.objects.filter(is_current=True).first()

        if not current_semester:
            return Response({'error': 'No current semester set'}, status=400)

        try:
            record = StudentAcademicRecord.objects.get(
                student=student,
                session=current_semester.session,
                semester=current_semester.semester
            )
        except StudentAcademicRecord.DoesNotExist:
            record = StudentAcademicRecord(
                student=student,
                level=student.level,
                session=current_semester.session,
                semester=current_semester.semester
            )
            record.save()

        serializer = self.get_serializer(record)
        return Response(serializer.data)


# ========================
# Attendance Viewset
# ========================

class AttendanceViewSet(viewsets.ModelViewSet):
    """Attendance operations"""
    queryset = Attendance.objects.select_related(
        'student__user', 'course', 'marked_by__user'
    ).all()
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['student', 'course', 'date', 'status']
    search_fields = ['student__matric_number', 'course__code']
    ordering_fields = ['date', 'created_at']

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user

        if user.role == 'student' and hasattr(user, 'student_profile'):
            return queryset.filter(student=user.student_profile)

        if user.role == 'lecturer' and hasattr(user, 'lecturer_profile'):
            return queryset.filter(course__lecturer=user.lecturer_profile)

        return queryset

    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsLecturer() | IsAdminStaff()]
        return [IsAuthenticated()]

    def perform_create(self, serializer):
        if hasattr(self.request.user, 'lecturer_profile'):
            serializer.save(marked_by=self.request.user.lecturer_profile)
        else:
            serializer.save()


# ========================
# Semester Viewset
# ========================

class SemesterViewSet(viewsets.ModelViewSet):
    """Semester operations"""
    queryset = Semester.objects.all()
    serializer_class = SemesterSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['session', 'semester', 'is_current']
    ordering_fields = ['start_date', 'session']

    @action(detail=False, methods=['get'])
    def current(self, request):
        """Get current semester"""
        try:
            semester = Semester.objects.get(is_current=True)
            serializer = self.get_serializer(semester)
            return Response(serializer.data)
        except Semester.DoesNotExist:
            return Response(
                {'error': 'No current semester set'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['post'])
    def activate_registration(self, request, pk=None):
        semester = self.get_object()

        if not semester.is_current:
            return Response(
                {'error': 'Only current semester can be activated'},
                status=400
            )

        semester.is_registration_active = True
        semester.save()

        return Response({
            'message': f'Registration activated for {semester}',
            'semester': SemesterSerializer(semester).data
        })

    @action(detail=True, methods=['post'])
    def deactivate_registration(self, request, pk=None):
        semester = self.get_object()

        semester.is_registration_active = False
        semester.save()

        return Response({
            'message': f'Registration deactivated for {semester}',
            'semester': SemesterSerializer(semester).data
        })
