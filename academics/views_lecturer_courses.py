# academics/views_lecturer_courses.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Q
from django.utils import timezone

# ✅ FIXED: Added 'CourseRegistration' import
from academics.models import (
    Course, CourseOffering, Semester, Department, CourseRegistration
)
from academics.serializers import CourseSerializer, CourseDetailSerializer
from users.permissions import IsLecturer

class LecturerCourseAllocationViewSet(viewsets.ViewSet):
    """Course allocation management for lecturers"""
    permission_classes = [IsAuthenticated, IsLecturer]
    
    def get_lecturer_profile(self, request):
        if not hasattr(request.user, 'lecturer_profile'):
            return None, Response(
                {'error': 'Lecturer profile not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return request.user.lecturer_profile, None
    
    @action(detail=False, methods=['get'])
    def allocated_courses(self, request):
        """Get all courses allocated to the lecturer"""
        lecturer, error_response = self.get_lecturer_profile(request)
        if error_response:
            return error_response
        
        current_semester = Semester.objects.filter(is_current=True).first()
        
        # Get all courses allocated to this lecturer
        allocated_courses = Course.objects.filter(
            lecturer=lecturer
        ).select_related('department')
        
        # Get current semester allocations
        current_allocations = []
        if current_semester:
            current_allocations = CourseOffering.objects.filter(
                course__lecturer=lecturer,
                semester=current_semester,
                is_active=True
            ).select_related('course', 'course__department', 'semester')
        
        allocated_data = []
        for course in allocated_courses:
            # Get enrollment stats for current semester
            current_enrollment = 0
            if current_semester:
                try:
                    offering = CourseOffering.objects.get(
                        course=course,
                        semester=current_semester
                    )
                    # ✅ FIXED: Used CourseRegistration
                    current_enrollment = CourseRegistration.objects.filter(
                        course_offering=offering,
                        status='registered'
                    ).count()
                except CourseOffering.DoesNotExist:
                    pass
            
            allocated_data.append({
                'course_id': course.id,
                'code': course.code,
                'title': course.title,
                'credits': course.credits,
                'department': course.department.name,
                'semester': course.semester,
                'level': course.level,
                'is_elective': course.is_elective,
                'total_allocations': CourseOffering.objects.filter(
                    course=course
                ).count(),
                'current_semester_enrollment': current_enrollment,
                'has_current_offering': current_semester and CourseOffering.objects.filter(
                    course=course,
                    semester=current_semester
                ).exists()
            })
        
        return Response({
            'lecturer': {
                'id': lecturer.id,
                'name': lecturer.user.get_full_name(),
                'department': lecturer.department.name
            },
            'allocated_courses': allocated_data,
            'current_semester': {
                'id': current_semester.id if current_semester else None,
                'session': current_semester.session if current_semester else None,
                'semester': current_semester.semester if current_semester else None
            }
        })
    
    @action(detail=False, methods=['get'])
    def course_load_summary(self, request):
        """Get course load summary for lecturer"""
        lecturer, error_response = self.get_lecturer_profile(request)
        if error_response:
            return error_response
        
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            return Response({'error': 'No current semester'}, status=400)
        
        # Get current semester allocations
        current_offerings = CourseOffering.objects.filter(
            course__lecturer=lecturer,
            semester=current_semester,
            is_active=True
        ).select_related('course')
        
        # Calculate workload
        total_credits = sum(offering.course.credits for offering in current_offerings)
        
        # ✅ FIXED: Used CourseRegistration
        total_students = sum(
            CourseRegistration.objects.filter(
                course_offering=offering,
                status='registered'
            ).count() for offering in current_offerings
        )
        
        # Get courses by level
        courses_by_level = {}
        for offering in current_offerings:
            level = offering.course.level
            if level not in courses_by_level:
                courses_by_level[level] = []
            
            # ✅ FIXED: Used CourseRegistration
            enrollment_count = CourseRegistration.objects.filter(
                course_offering=offering,
                status='registered'
            ).count()
            
            courses_by_level[level].append({
                'code': offering.course.code,
                'title': offering.course.title,
                'credits': offering.course.credits,
                'enrollment': enrollment_count
            })
        
        return Response({
            'semester': current_semester.session + ' ' + current_semester.get_semester_display(),
            'total_courses': current_offerings.count(),
            'total_credits': total_credits,
            'total_students': total_students,
            'courses_by_level': courses_by_level,
            'recommended_max_credits': 12,  # Adjust based on your policy
            'is_overloaded': total_credits > 12
        })