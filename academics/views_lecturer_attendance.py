# academics/views_lecturer_attendance.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from datetime import datetime, date

# ✅ FIXED IMPORTS: Removed 'Registration', ensure 'CourseRegistration' is used
from academics.models import (
    Course, CourseOffering, CourseRegistration, 
    Attendance, Semester, Enrollment
)
from users.permissions import IsLecturer

class LecturerAttendanceViewSet(viewsets.ViewSet):
    """Attendance marking system for lecturers"""
    permission_classes = [IsAuthenticated, IsLecturer]
    
    def get_lecturer_profile(self, request):
        if not hasattr(request.user, 'lecturer_profile'):
            return None, Response(
                {'error': 'Lecturer profile not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return request.user.lecturer_profile, None
    
    @action(detail=False, methods=['get'])
    def attendance_sessions(self, request):
        """Get courses for attendance marking"""
        lecturer, error_response = self.get_lecturer_profile(request)
        if error_response:
            return error_response
        
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            return Response({'error': 'No current semester'}, status=400)
        
        courses = Course.objects.filter(
            lecturer=lecturer
        ).select_related('department')
        
        courses_data = []
        for course in courses:
            # Check if course has offering in current semester
            try:
                offering = CourseOffering.objects.get(
                    course=course,
                    semester=current_semester,
                    is_active=True
                )
                
                # Get last attendance date
                last_attendance = Attendance.objects.filter(
                    course=course,
                    marked_by=lecturer
                ).order_by('-date').first()
                
                courses_data.append({
                    'course_id': course.id,
                    'code': course.code,
                    'title': course.title,
                    'department': course.department.name,
                    # ✅ FIXED: Used CourseRegistration
                    'enrolled_students': CourseRegistration.objects.filter(
                        course_offering=offering,
                        status='registered'
                    ).count(),
                    'last_attendance_date': last_attendance.date if last_attendance else None,
                    'attendance_count': Attendance.objects.filter(
                        course=course,
                        marked_by=lecturer,
                        date__gte=current_semester.start_date
                    ).count()
                })
            except CourseOffering.DoesNotExist:
                continue
        
        return Response({
            'current_date': date.today(),
            'current_semester': current_semester.session + ' ' + current_semester.get_semester_display(),
            'courses': courses_data
        })
    
    @action(detail=False, methods=['post'])
    def mark_attendance(self, request):
        """Mark attendance for a course"""
        lecturer, error_response = self.get_lecturer_profile(request)
        if error_response:
            return error_response
        
        course_id = request.data.get('course_id')
        attendance_date = request.data.get('date')
        attendance_data = request.data.get('attendance', [])
        
        if not course_id or not attendance_date or not attendance_data:
            return Response({'error': 'course_id, date, and attendance are required'}, status=400)
        
        try:
            course = Course.objects.get(id=course_id, lecturer=lecturer)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found or not assigned to you'}, status=404)
        
        # Parse date
        try:
            attendance_date = datetime.strptime(attendance_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
        
        # Check if date is in the future
        if attendance_date > date.today():
            return Response({'error': 'Cannot mark attendance for future dates'}, status=400)
        
        results = {
            'marked': [],
            'errors': []
        }
        
        for attendance_entry in attendance_data:
            student_id = attendance_entry.get('student_id')
            status_value = attendance_entry.get('status')
            remarks = attendance_entry.get('remarks', '')
            
            if not student_id or not status_value:
                results['errors'].append({
                    'student_id': student_id,
                    'error': 'Missing student_id or status'
                })
                continue
            
            try:
                from academics.models import Student  # Import here to avoid circular
                student = Student.objects.get(id=student_id)
                
                # Check if student is enrolled in this course
                if not Enrollment.objects.filter(
                    student=student,
                    course=course,
                    status='enrolled'
                ).exists():
                    results['errors'].append({
                        'student_id': student_id,
                        'error': 'Student is not enrolled in this course'
                    })
                    continue
                
                # Create or update attendance record
                attendance, created = Attendance.objects.update_or_create(
                    student=student,
                    course=course,
                    date=attendance_date,
                    defaults={
                        'status': status_value,
                        'remarks': remarks,
                        'marked_by': lecturer
                    }
                )
                
                results['marked'].append({
                    'student_id': student_id,
                    'matric_number': student.matric_number,
                    'name': student.user.get_full_name(),
                    'status': status_value,
                    'created': created
                })
                
            except Student.DoesNotExist:
                results['errors'].append({
                    'student_id': student_id,
                    'error': 'Student not found'
                })
            except Exception as e:
                results['errors'].append({
                    'student_id': student_id,
                    'error': str(e)
                })
        
        return Response({
            'results': results,
            'summary': {
                'course': course.code,
                'date': attendance_date,
                'total_marked': len(results['marked']),
                'total_errors': len(results['errors'])
            }
        })
    
    @action(detail=False, methods=['get'])
    def attendance_report(self, request):
        """Generate attendance report for a course"""
        lecturer, error_response = self.get_lecturer_profile(request)
        if error_response:
            return error_response
        
        course_id = request.query_params.get('course_id')
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date', date.today().isoformat())
        
        if not course_id:
            return Response({'error': 'course_id is required'}, status=400)
        
        try:
            course = Course.objects.get(id=course_id, lecturer=lecturer)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found or not assigned to you'}, status=404)
        
        # Parse dates
        try:
            if start_date:
                start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
            else:
                current_semester = Semester.objects.filter(is_current=True).first()
                start_date = current_semester.start_date if current_semester else date.today() - timedelta(days=30)
            
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response({'error': 'Invalid date format. Use YYYY-MM-DD'}, status=400)
        
        # Get all attendance records
        attendance_records = Attendance.objects.filter(
            course=course,
            date__range=[start_date, end_date]
        ).select_related('student__user')
        
        # Group by student
        student_attendance = {}
        for record in attendance_records:
            student_id = record.student.id
            if student_id not in student_attendance:
                student_attendance[student_id] = {
                    'student': {
                        'id': record.student.id,
                        'matric_number': record.student.matric_number,
                        'name': record.student.user.get_full_name()
                    },
                    'attendance': []
                }
            student_attendance[student_id]['attendance'].append({
                'date': record.date,
                'status': record.status,
                'remarks': record.remarks
            })
        
        # Calculate statistics
        report_data = []
        total_classes = attendance_records.values('date').distinct().count()
        
        for student_id, data in student_attendance.items():
            attendance_list = data['attendance']
            present_count = sum(1 for a in attendance_list if a['status'] == 'present')
            attendance_percentage = (present_count / total_classes * 100) if total_classes > 0 else 0
            
            report_data.append({
                **data['student'],
                'attendance_count': len(attendance_list),
                'present_count': present_count,
                'absent_count': sum(1 for a in attendance_list if a['status'] == 'absent'),
                'late_count': sum(1 for a in attendance_list if a['status'] == 'late'),
                'attendance_percentage': round(attendance_percentage, 1),
                'last_attendance': max([a['date'] for a in attendance_list]) if attendance_list else None
            })
        
        # Sort by attendance percentage (lowest first)
        report_data.sort(key=lambda x: x['attendance_percentage'])
        
        return Response({
            'course': {
                'id': course.id,
                'code': course.code,
                'title': course.title
            },
            'date_range': {
                'start': start_date,
                'end': end_date
            },
            'total_classes': total_classes,
            'attendance_threshold': 75,  # Minimum required attendance percentage
            'students_below_threshold': [s for s in report_data if s['attendance_percentage'] < 75],
            'report': report_data
        })