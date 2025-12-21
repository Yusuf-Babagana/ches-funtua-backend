# academics/views_lecturer_students.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Avg, Q
from django.utils import timezone
from datetime import timedelta

# ✅ FIXED IMPORTS: Removed 'Registration', ensure 'CourseRegistration' is used
from academics.models import (
    Course, CourseOffering, CourseRegistration, Student, 
    Semester, Attendance, Grade
)
from users.serializers import StudentSerializer
from academics.serializers import CourseSerializer
from users.permissions import IsLecturer

class LecturerStudentManagementViewSet(viewsets.ViewSet):
    """Student management per course for lecturers"""
    permission_classes = [IsAuthenticated, IsLecturer]
    
    def get_lecturer_profile(self, request):
        if not hasattr(request.user, 'lecturer_profile'):
            return None, Response(
                {'error': 'Lecturer profile not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return request.user.lecturer_profile, None
    
    @action(detail=False, methods=['get'])
    def course_students(self, request):
        """Get students enrolled in a specific course"""
        lecturer, error_response = self.get_lecturer_profile(request)
        if error_response:
            return error_response
        
        course_id = request.query_params.get('course_id')
        if not course_id:
            return Response({'error': 'course_id is required'}, status=400)
        
        try:
            course = Course.objects.get(id=course_id, lecturer=lecturer)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found or not assigned to you'}, status=404)
        
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            return Response({'error': 'No current semester'}, status=400)
        
        try:
            course_offering = CourseOffering.objects.get(
                course=course,
                semester=current_semester
            )
        except CourseOffering.DoesNotExist:
            return Response({'error': 'Course not offered this semester'}, status=404)
        
        # Get registered students
        # ✅ FIXED: Used CourseRegistration
        registrations = CourseRegistration.objects.filter(
            course_offering=course_offering,
            status='registered'
        ).select_related('student__user', 'student__department')
        
        students_data = []
        for registration in registrations:
            student = registration.student
            
            # Get attendance
            attendance = Attendance.objects.filter(
                student=student,
                course=course,
                date__gte=current_semester.start_date
            )
            total_classes = attendance.count()
            present_classes = attendance.filter(status='present').count()
            attendance_percentage = (present_classes / total_classes * 100) if total_classes > 0 else 0
            
            # Get CA and Exam scores if available
            ca_score = None
            exam_score = None
            total_score = None
            
            try:
                grade = Grade.objects.get(
                    student=student,
                    course=course,
                    session=current_semester.session,
                    semester=current_semester.semester
                )
                ca_score = grade.ca_score  # Assuming you have these fields
                exam_score = grade.exam_score
                total_score = grade.score
            except Grade.DoesNotExist:
                pass
            
            students_data.append({
                'registration_id': registration.id,
                'student_id': student.id,
                'matric_number': student.matric_number,
                'full_name': student.user.get_full_name(),
                'level': student.level,
                'department': student.department.name,
                'attendance': {
                    'present': present_classes,
                    'total': total_classes,
                    'percentage': round(attendance_percentage, 1)
                },
                'scores': {
                    'ca': ca_score,
                    'exam': exam_score,
                    'total': total_score
                },
                'has_grades': total_score is not None,
                'registration_date': registration.registration_date
            })
        
        return Response({
            'course': {
                'id': course.id,
                'code': course.code,
                'title': course.title,
                'credits': course.credits
            },
            'semester': current_semester.session + ' ' + current_semester.get_semester_display(),
            'total_students': len(students_data),
            'students': students_data
        })
    
    @action(detail=False, methods=['post'])
    def update_student_scores(self, request):
        """Update CA and Exam scores for students"""
        lecturer, error_response = self.get_lecturer_profile(request)
        if error_response:
            return error_response
        
        course_id = request.data.get('course_id')
        scores_data = request.data.get('scores', [])
        
        if not course_id or not scores_data:
            return Response({'error': 'course_id and scores are required'}, status=400)
        
        try:
            course = Course.objects.get(id=course_id, lecturer=lecturer)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found or not assigned to you'}, status=404)
        
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            return Response({'error': 'No current semester'}, status=400)
        
        results = {
            'successful': [],
            'failed': []
        }
        
        for score_data in scores_data:
            student_id = score_data.get('student_id')
            ca_score = score_data.get('ca_score')
            exam_score = score_data.get('exam_score')
            
            if not student_id or ca_score is None or exam_score is None:
                results['failed'].append({
                    'student_id': student_id,
                    'error': 'Missing required fields'
                })
                continue
            
            try:
                student = Student.objects.get(id=student_id)
                
                # Calculate total score (CA 30%, Exam 70%)
                total_score = (ca_score * 0.3) + (exam_score * 0.7)
                
                # Create or update grade
                grade, created = Grade.objects.update_or_create(
                    student=student,
                    course=course,
                    session=current_semester.session,
                    semester=current_semester.semester,
                    defaults={
                        'ca_score': ca_score,
                        'exam_score': exam_score,
                        'score': total_score,
                        'uploaded_by': lecturer
                    }
                )
                
                results['successful'].append({
                    'student_id': student_id,
                    'matric_number': student.matric_number,
                    'name': student.user.get_full_name(),
                    'ca_score': ca_score,
                    'exam_score': exam_score,
                    'total_score': total_score,
                    'grade_letter': grade.grade_letter
                })
                
            except Student.DoesNotExist:
                results['failed'].append({
                    'student_id': student_id,
                    'error': 'Student not found'
                })
            except Exception as e:
                results['failed'].append({
                    'student_id': student_id,
                    'error': str(e)
                })
        
        return Response({
            'results': results,
            'message': f'Successfully updated {len(results["successful"])} student(s)'
        })