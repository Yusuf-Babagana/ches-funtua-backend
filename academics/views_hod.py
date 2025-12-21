# academics/views_hod.py
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count, Q
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

# ✅ Updated Import: Registration -> CourseRegistration
from .models import (
    Department, Course, 
    CourseOffering, Semester, CourseRegistration
)
from .serializers import (
    DepartmentSerializer, CourseSerializer, CourseDetailSerializer,
    CourseOfferingSerializer
)
from users.models import User, Student, Lecturer
from users.serializers import StudentSerializer, LecturerSerializer
from users.permissions import IsHOD


class HODDashboardViewSet(viewsets.ViewSet):
    """HOD Dashboard - All operations for Head of Department"""
    permission_classes = [IsAuthenticated, IsHOD]
    
    def get_department(self, request):
        """Get the department managed by the HOD"""
        user = request.user
        
        # Check if user is a lecturer and is HOD
        if not hasattr(user, 'lecturer_profile'):
            return None, Response(
                {'error': 'User is not a lecturer'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        lecturer = user.lecturer_profile
        
        # Get department where this lecturer is HOD
        # HOD is linked via the Department model
        # Use filter().first() to handle cases where one HOD manages multiple departments safely
        department = Department.objects.filter(hod=lecturer).first()
        
        if department:
            return department, None
            
        return None, Response(
            {'error': 'You are not assigned as HOD to any department'}, 
            status=status.HTTP_404_NOT_FOUND
        )
    
    def paginate_queryset(self, queryset, request):
        """Custom pagination method"""
        page_size = request.query_params.get('page_size', 20)
        page = request.query_params.get('page', 1)
        
        paginator = Paginator(queryset, page_size)
        
        try:
            return paginator.page(page)
        except PageNotAnInteger:
            return paginator.page(1)
        except EmptyPage:
            return paginator.page(paginator.num_pages)
    
    def get_paginated_response(self, data, request):
        """Create paginated response"""
        from django.core.paginator import Paginator
        
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
        
        # Just creating a mock paginator structure for consistent response format
        # Since 'data' is already a page, we wrap it manually
        
        return Response({
            'count': len(data), # This might need adjustment if count isn't passed
            'next': False,
            'previous': False,
            'results': data
        })
    
    @action(detail=False, methods=['get'])
    def department_overview(self, request):
        """Get complete department overview for HOD dashboard"""
        department, error_response = self.get_department(request)
        if error_response:
            return error_response
        
        # Get statistics
        total_students = Student.objects.filter(department=department).count()
        total_lecturers = Lecturer.objects.filter(department=department).count()
        total_courses = Course.objects.filter(department=department).count()
        
        # Get recent students (last 30 days)
        thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
        recent_students = Student.objects.filter(
            department=department,
            created_at__gte=thirty_days_ago
        ).select_related('user').order_by('-created_at')[:10]
        
        # Get courses with lecturer assignments
        department_courses = Course.objects.filter(
            department=department
        ).select_related('lecturer__user', 'department')
        
        # Get current semester
        current_semester = Semester.objects.filter(is_current=True).first()
        
        return Response({
            'department': {
                'id': department.id,
                'name': department.name,
                'code': department.code,
                'hod': {
                    'id': department.hod.id,
                    'name': department.hod.user.get_full_name(),
                    'staff_id': department.hod.staff_id
                } if department.hod else None
            },
            'statistics': {
                'students': total_students,
                'lecturers': total_lecturers,
                'courses': total_courses,
                'courses_with_lecturers': department_courses.filter(lecturer__isnull=False).count(),
                'courses_without_lecturers': department_courses.filter(lecturer__isnull=True).count(),
            },
            'recent_students': [
                {
                    'id': student.id,
                    'name': student.user.get_full_name(),
                    'matric_number': student.matric_number,
                    'level': student.level,
                    'status': student.status,
                    'admission_date': student.admission_date
                } for student in recent_students
            ],
            'courses_summary': [
                {
                    'id': course.id,
                    'code': course.code,
                    'title': course.title,
                    'credits': course.credits,
                    'lecturer': course.lecturer.user.get_full_name() if course.lecturer else 'Unassigned',
                    'level': course.level,
                    'semester': course.get_semester_display(),
                    'is_elective': course.is_elective
                } for course in department_courses[:10]
            ],
            'current_semester': {
                'id': current_semester.id,
                'session': current_semester.session,
                'semester': current_semester.get_semester_display(),
                'is_registration_active': current_semester.is_registration_active
            } if current_semester else None
        })
    
    @action(detail=False, methods=['get'])
    def students(self, request):
        """Get all students in HOD's department"""
        department, error_response = self.get_department(request)
        if error_response:
            return error_response
        
        students = Student.objects.filter(
            department=department
        ).select_related('user').order_by('matric_number')
        
        # Apply filters
        level = request.query_params.get('level')
        status_filter = request.query_params.get('status')
        search = request.query_params.get('search')
        
        if level:
            students = students.filter(level=level)
        if status_filter:
            students = students.filter(status=status_filter)
        if search:
            students = students.filter(
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(matric_number__icontains=search) |
                Q(user__email__icontains=search)
            )
        
        # Serialize the data
        students_data = [
            {
                'id': student.id,
                'user': {
                    'id': student.user.id,
                    'email': student.user.email,
                    'first_name': student.user.first_name,
                    'last_name': student.user.last_name,
                    'phone': student.user.phone,
                    'is_active': student.user.is_active
                },
                'matric_number': student.matric_number,
                'level': student.level,
                'status': student.status,
                'admission_date': student.admission_date,
                'date_of_birth': student.date_of_birth,
                'guardian_name': student.guardian_name
            }
            for student in students
        ]
        
        # Paginate
        page = self.paginate_queryset(students_data, request)
        if page is not None:
            return self.get_paginated_response(list(page), request)
        
        return Response(students_data)
    
    @action(detail=False, methods=['get'])
    def lecturers(self, request):
        """Get all lecturers in HOD's department"""
        department, error_response = self.get_department(request)
        if error_response:
            return error_response
        
        lecturers = Lecturer.objects.filter(
            department=department
        ).select_related('user').order_by('staff_id')
        
        # Apply filters
        designation = request.query_params.get('designation')
        search = request.query_params.get('search')
        
        if designation:
            lecturers = lecturers.filter(designation=designation)
        if search:
            lecturers = lecturers.filter(
                Q(user__first_name__icontains=search) |
                Q(user__last_name__icontains=search) |
                Q(staff_id__icontains=search) |
                Q(specialization__icontains=search)
            )
        
        # Serialize the data
        lecturers_data = []
        for lecturer in lecturers:
            # Count courses currently assigned to this lecturer
            course_count = Course.objects.filter(
                department=department,
                lecturer=lecturer
            ).count()
            
            lecturers_data.append({
                'id': lecturer.id,
                'user': {
                    'id': lecturer.user.id,
                    'email': lecturer.user.email,
                    'first_name': lecturer.user.first_name,
                    'last_name': lecturer.user.last_name,
                    'phone': lecturer.user.phone,
                    'is_active': lecturer.user.is_active
                },
                'staff_id': lecturer.staff_id,
                'designation': lecturer.designation,
                'designation_display': lecturer.get_designation_display(),
                'specialization': lecturer.specialization,
                'qualifications': lecturer.qualifications,
                'office_location': lecturer.office_location,
                'consultation_hours': lecturer.consultation_hours,
                'is_hod': lecturer.is_hod,
                'course_count': course_count
            })
        
        # Paginate
        page = self.paginate_queryset(lecturers_data, request)
        if page is not None:
            return self.get_paginated_response(list(page), request)
        
        return Response(lecturers_data)
    
    @action(detail=False, methods=['get'])
    def courses(self, request):
        """Get all courses in HOD's department"""
        department, error_response = self.get_department(request)
        if error_response:
            return error_response
        
        courses = Course.objects.filter(
            department=department
        ).select_related('lecturer__user', 'department').order_by('code')
        
        # Apply filters
        level = request.query_params.get('level')
        semester = request.query_params.get('semester')
        has_lecturer = request.query_params.get('has_lecturer')
        search = request.query_params.get('search')
        
        if level:
            courses = courses.filter(level=level)
        if semester:
            courses = courses.filter(semester=semester)
        if has_lecturer == 'true':
            courses = courses.filter(lecturer__isnull=False)
        elif has_lecturer == 'false':
            courses = courses.filter(lecturer__isnull=True)
        if search:
            courses = courses.filter(
                Q(code__icontains=search) |
                Q(title__icontains=search) |
                Q(description__icontains=search)
            )
        
        # Serialize the data
        courses_data = []
        for course in courses:
            courses_data.append({
                'id': course.id,
                'code': course.code,
                'title': course.title,
                'description': course.description,
                'credits': course.credits,
                'department': {
                    'id': course.department.id,
                    'name': course.department.name,
                    'code': course.department.code
                },
                'semester': course.semester,
                'semester_display': course.get_semester_display(),
                'level': course.level,
                'level_display': course.get_level_display(),
                'lecturer': {
                    'id': course.lecturer.id,
                    'name': course.lecturer.user.get_full_name(),
                    'staff_id': course.lecturer.staff_id
                } if course.lecturer else None,
                'is_elective': course.is_elective
            })
        
        # Paginate
        page = self.paginate_queryset(courses_data, request)
        if page is not None:
            return self.get_paginated_response(list(page), request)
        
        return Response(courses_data)
    
    @action(detail=True, methods=['post'])
    def assign_course_lecturer(self, request, pk=None):
        """Assign lecturer to a course"""
        department, error_response = self.get_department(request)
        if error_response:
            return error_response
        
        try:
            course = Course.objects.get(id=pk, department=department)
        except Course.DoesNotExist:
            return Response(
                {'error': 'Course not found in your department'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        lecturer_id = request.data.get('lecturer_id')
        if not lecturer_id:
            return Response(
                {'error': 'lecturer_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            lecturer = Lecturer.objects.get(id=lecturer_id, department=department)
            
            # Check if lecturer is already assigned to this course
            if course.lecturer == lecturer:
                return Response(
                    {'error': 'Lecturer is already assigned to this course'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Assign lecturer to course
            course.lecturer = lecturer
            course.save()
            
            # Return updated course data
            course_data = {
                'id': course.id,
                'code': course.code,
                'title': course.title,
                'lecturer': {
                    'id': course.lecturer.id,
                    'name': course.lecturer.user.get_full_name(),
                    'staff_id': course.lecturer.staff_id
                } if course.lecturer else None
            }
            
            return Response({
                'message': f'Successfully assigned {lecturer.user.get_full_name()} to {course.code}',
                'course': course_data
            })
            
        except Lecturer.DoesNotExist:
            return Response(
                {'error': 'Lecturer not found in your department'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['post'])
    def remove_course_lecturer(self, request, pk=None):
        """Remove lecturer from a course"""
        department, error_response = self.get_department(request)
        if error_response:
            return error_response
        
        try:
            course = Course.objects.get(id=pk, department=department)
        except Course.DoesNotExist:
            return Response(
                {'error': 'Course not found in your department'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        if not course.lecturer:
            return Response(
                {'error': 'No lecturer assigned to this course'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_lecturer = course.lecturer
        course.lecturer = None
        course.save()
        
        return Response({
            'message': f'Successfully removed {old_lecturer.user.get_full_name()} from {course.code}',
            'course': {
                'id': course.id,
                'code': course.code,
                'title': course.title,
                'lecturer': None
            }
        })
    
    @action(detail=False, methods=['get'])
    def available_lecturers(self, request):
        """Get available lecturers for course assignment"""
        department, error_response = self.get_department(request)
        if error_response:
            return error_response
        
        # Get all lecturers in the department
        lecturers = Lecturer.objects.filter(
            department=department
        ).select_related('user').order_by('user__last_name')
        
        lecturer_data = []
        for lecturer in lecturers:
            # Count courses currently assigned to this lecturer
            course_count = Course.objects.filter(
                department=department,
                lecturer=lecturer
            ).count()
            
            lecturer_data.append({
                'id': lecturer.id,
                'name': lecturer.user.get_full_name(),
                'staff_id': lecturer.staff_id,
                'designation': lecturer.get_designation_display(),
                'specialization': lecturer.specialization,
                'current_course_count': course_count,
                'is_hod': lecturer.is_hod
            })
        
        return Response(lecturer_data)
    
    @action(detail=False, methods=['get'])
    def student_statistics(self, request):
        """Get detailed student statistics for the department"""
        department, error_response = self.get_department(request)
        if error_response:
            return error_response
        
        # Students by level
        students_by_level = Student.objects.filter(
            department=department
        ).values('level').annotate(
            count=Count('id')
        ).order_by('level')
        
        # Students by status
        students_by_status = Student.objects.filter(
            department=department
        ).values('status').annotate(
            count=Count('id')
        ).order_by('status')
        
        # Recent admissions (last 6 months)
        six_months_ago = timezone.now() - timezone.timedelta(days=180)
        recent_admissions = Student.objects.filter(
            department=department,
            admission_date__gte=six_months_ago
        ).count()
        
        return Response({
            'by_level': [
                {
                    'level': item['level'],
                    'count': item['count'],
                    'level_display': dict(Student.LEVEL_CHOICES).get(item['level'], item['level'])
                } for item in students_by_level
            ],
            'by_status': [
                {
                    'status': item['status'],
                    'count': item['count'],
                    'status_display': dict(Student.STATUS_CHOICES).get(item['status'], item['status'])
                } for item in students_by_status
            ],
            'summary': {
                'total_students': Student.objects.filter(department=department).count(),
                'active_students': Student.objects.filter(department=department, status='active').count(),
                'recent_admissions': recent_admissions,
                'graduated_students': Student.objects.filter(department=department, status='graduated').count(),
            }
        })
    
    @action(detail=False, methods=['post'])
    def bulk_assign_courses(self, request):
        """Bulk assign courses to lecturers"""
        department, error_response = self.get_department(request)
        if error_response:
            return error_response
        
        assignments = request.data.get('assignments', [])
        
        if not assignments:
            return Response(
                {'error': 'assignments array is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        successful = []
        failed = []
        
        for assignment in assignments:
            course_id = assignment.get('course_id')
            lecturer_id = assignment.get('lecturer_id')
            
            if not course_id or not lecturer_id:
                failed.append({
                    'assignment': assignment,
                    'error': 'course_id and lecturer_id are required'
                })
                continue
            
            try:
                course = Course.objects.get(id=course_id, department=department)
                lecturer = Lecturer.objects.get(id=lecturer_id, department=department)
                
                course.lecturer = lecturer
                course.save()
                
                successful.append({
                    'course': f"{course.code} - {course.title}",
                    'lecturer': lecturer.user.get_full_name(),
                    'lecturer_staff_id': lecturer.staff_id
                })
                
            except Course.DoesNotExist:
                failed.append({
                    'assignment': assignment,
                    'error': f'Course {course_id} not found in your department'
                })
            except Lecturer.DoesNotExist:
                failed.append({
                    'assignment': assignment,
                    'error': f'Lecturer {lecturer_id} not found in your department'
                })
            except Exception as e:
                failed.append({
                    'assignment': assignment,
                    'error': str(e)
                })
        
        return Response({
            'successful_assignments': successful,
            'failed_assignments': failed,
            'total_successful': len(successful),
            'total_failed': len(failed)
        })