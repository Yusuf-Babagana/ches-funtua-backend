from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Q
from django.utils import timezone
from django.db import transaction

# ✅ CORRECTED IMPORTS
from .models import (
    Department, Course, Enrollment, Grade,
    Attendance, Semester, CourseOffering, 
    CourseRegistration,  # Fixed: Registration -> CourseRegistration
    StudentAcademicRecord
)
from .serializers import (
    DepartmentSerializer, CourseSerializer, EnrollmentSerializer,
    GradeSerializer, AttendanceSerializer, SemesterSerializer,
    StudentAcademicRecordSerializer, CourseDetailSerializer
)
from users.permissions import (
    IsAdminStaff, CanManageGrades, IsLecturer, IsStudent
)
from users.models import Student

# ==============================================
# LECTURER DASHBOARD VIEW
# ==============================================

class LecturerDashboardViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsLecturer]

    @action(detail=False, methods=['get'])
    def overview(self, request):
        user = request.user
        
        if not hasattr(user, 'lecturer_profile'):
            return Response({"error": "Profile not found"}, status=400)
        
        lecturer = user.lecturer_profile
        
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            current_semester = Semester.objects.order_by('-id').first()

        if current_semester:
            active_offerings = CourseOffering.objects.filter(
                lecturer=lecturer,
                semester=current_semester
            )
        else:
            active_offerings = CourseOffering.objects.none()
        
        total_students = 0
        if active_offerings.exists():
            total_students = CourseRegistration.objects.filter(
                course_offering__in=active_offerings,
                status='registered'
            ).values('student').distinct().count()

        recent_courses_data = []
        for offering in active_offerings:
            student_count = CourseRegistration.objects.filter(
                course_offering=offering,
                status='registered'
            ).count()
            
            recent_courses_data.append({
                'id': offering.course.id,
                'course_id': offering.course.id,
                'code': offering.course.code,
                'title': offering.course.title,
                'credits': offering.course.credits,
                'enrolled_students': student_count,
                'semester': current_semester.semester if current_semester else '-',
                'level': offering.course.level
            })

        return Response({
            "lecturer": {
                "name": f"{user.first_name} {user.last_name}",
                "staff_id": lecturer.staff_id,
                "designation": lecturer.designation,
                "department": {
                    "name": lecturer.department.name if lecturer.department else "General"
                }
            },
            "current_semester": {
                "session": current_semester.session if current_semester else "N/A",
                "semester": current_semester.semester if current_semester else "-"
            },
            "statistics": {
                "current_semester_courses": active_offerings.count(),
                "current_students": total_students,
                "grades_to_enter": 0
            },
            "current_courses": recent_courses_data,
            "recent_courses": recent_courses_data 
        })


class LecturerCourseViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CourseSerializer
    permission_classes = [IsAuthenticated, IsLecturer]

    def get_queryset(self):
        if hasattr(self.request.user, 'lecturer_profile'):
            return Course.objects.filter(lecturer=self.request.user.lecturer_profile)
        return Course.objects.none()

    @action(detail=True, methods=['get'])
    def students(self, request, pk=None):
        """
        Get students for a course + their current grades.
        STRICTLY filters by Current Semester.
        """
        try:
            course = Course.objects.get(id=pk)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=404)

        # 1. Get Current Semester (Crucial for filtering grades)
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            # Fallback for testing/setup
            current_semester = Semester.objects.last()

        # 2. Get registered students for this semester only
        registrations = CourseRegistration.objects.filter(
            course_offering__course=course,
            course_offering__semester=current_semester,
            status__in=['registered', 'approved_exam_officer'] 
        ).select_related('student__user')

        student_list = []
        
        for reg in registrations:
            student = reg.student
            
            # 3. Find existing grade for THIS semester
            grade = Grade.objects.filter(
                student=student,
                course=course,
                session=current_semester.session,
                semester=current_semester.semester
            ).first()

            # Default values
            ca_score = 0
            exam_score = 0
            total_score = 0
            grade_letter = '-'
            status = 'new'
            is_locked = False
            has_grade = False

            if grade:
                has_grade = True
                total_score = grade.score
                ca_score = grade.ca_score
                exam_score = grade.exam_score
                grade_letter = grade.grade_letter
                status = grade.status
                # Lock if submitted or approved
                is_locked = grade.status in ['submitted', 'hod_approved', 'verified', 'published']

            # Construct response
            student_list.append({
                'student': {
                    'id': student.id,
                    'full_name': student.user.get_full_name(),
                    'matric_number': student.matric_number,
                    'level': student.level,
                },
                'grade': {
                    'id': grade.id if grade else None,
                    'score': total_score,
                    'ca_score': ca_score,
                    'exam_score': exam_score,
                    'grade_letter': grade_letter,
                    'status': status,
                    'is_locked': is_locked,
                    'has_grade': has_grade
                }
            })

        return Response({
            'course': {
                'title': course.title,
                'code': course.code,
                'credits': course.credits,
                'session': current_semester.session if current_semester else "N/A"
            },
            'grades': student_list 
        })


class LecturerGradeViewSet(viewsets.ModelViewSet):
    """Grade management for lecturers"""
    queryset = Grade.objects.all()
    serializer_class = GradeSerializer
    permission_classes = [IsAuthenticated, IsLecturer]

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def bulk_enter_grades(self, request):
        """
        Enter grades for multiple students.
        Handles Draft vs Submit logic.
        """
        if not hasattr(request.user, 'lecturer_profile'):
            return Response({'error': 'Lecturer profile not found'}, status=400)
        
        lecturer = request.user.lecturer_profile
        course_id = request.data.get('course_id')
        grades_data = request.data.get('grades', [])
        action_type = request.data.get('action', 'draft') # 'draft' or 'submit'
        
        if not course_id or not grades_data:
            return Response({'error': 'course_id and grades are required'}, status=400)
        
        try:
            course = Course.objects.get(id=course_id, lecturer=lecturer)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found or access denied'}, status=404)
        
        # Get Semester
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            current_semester = Semester.objects.last()

        if not current_semester:
             return Response({'error': 'No academic session found'}, status=400)

        successful = []
        errors = []
        
        # Determine status based on action
        target_status = 'submitted' if action_type == 'submit' else 'draft'

        for entry in grades_data:
            student_id = entry.get('student_id')
            
            # Scores
            ca_score = float(entry.get('ca_score', 0))
            exam_score = float(entry.get('exam_score', 0))
            # Recalculate total to be safe
            total_score = ca_score + exam_score
            
            if not student_id:
                continue

            try:
                student = Student.objects.get(id=student_id)
                
                # Ensure Enrollment Exists
                enrollment, _ = Enrollment.objects.get_or_create(
                    student=student,
                    course=course,
                    session=current_semester.session,
                    semester=current_semester.semester,
                    defaults={'status': 'enrolled'}
                )
                
                # ✅ FIX: Move 'enrollment' to defaults to prevent duplication errors
                grade, created = Grade.objects.update_or_create(
                    student=student,
                    course=course,
                    session=current_semester.session,
                    semester=current_semester.semester,
                    defaults={
                        'enrollment': enrollment, # Link enrollment
                        'ca_score': ca_score,
                        'exam_score': exam_score,
                        'score': total_score,
                        'uploaded_by': lecturer,
                        'status': target_status, # Update status
                        'remarks': entry.get('remarks', '')
                    }
                )
                
                successful.append(student.matric_number)
                
            except Exception as e:
                print(f"Error saving grade for {student_id}: {e}")
                errors.append(f"Student ID {student_id}: {str(e)}")
        
        return Response({
            'message': f'Successfully saved {len(successful)} grades as {target_status}',
            'errors': errors,
            'status': target_status
        })

    def get_queryset(self):
        """Get grades for lecturer's courses only"""
        if not hasattr(self.request.user, 'lecturer_profile'):
            return Grade.objects.none()
        
        lecturer = self.request.user.lecturer_profile
        return Grade.objects.filter(course__lecturer=lecturer)


# ==============================================
# ATTENDANCE (Re-exporting for completeness)
# ==============================================

class LecturerAttendanceViewSet(viewsets.ModelViewSet):
    queryset = Attendance.objects.all()
    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated, IsLecturer]

    def get_queryset(self):
        if not hasattr(self.request.user, 'lecturer_profile'):
            return Attendance.objects.none()
        return Attendance.objects.filter(course__lecturer=self.request.user.lecturer_profile)

class LecturerApprovalViewSet(viewsets.ViewSet):
    """Placeholder for approval logic if needed separately"""
    permission_classes = [IsAuthenticated, IsLecturer]

class LecturerAPIView(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsLecturer]