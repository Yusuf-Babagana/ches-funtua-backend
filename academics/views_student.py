from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from rest_framework.views import APIView
from datetime import timedelta
from django.db.models import Sum

# ✅ Updated Imports
from .models import Semester, CourseOffering, CourseRegistration, Grade, StudentAcademicRecord
from users.models import Student
from finance.models import Invoice
from .serializers import (
    SemesterSerializer, 
    CourseOfferingSerializer, 
    CourseRegistrationSerializer,
    GradeSerializer
)
from users.permissions import IsStudent


class StudentDashboardViewSet(viewsets.ViewSet):
    """Student-specific dashboard endpoints"""
    permission_classes = [IsAuthenticated, IsStudent]
    
    @action(detail=False, methods=['get'])
    def current_semester(self, request):
        """Get current semester"""
        try:
            semester = Semester.objects.get(is_current=True)
            serializer = SemesterSerializer(semester)
            return Response(serializer.data)
        except Semester.DoesNotExist:
            return Response(
                {'error': 'No current semester set'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=False, methods=['get'])
    def registration_status(self, request):
        """Get student's registration status"""
        if not hasattr(request.user, 'student_profile'):
            return Response(
                {'error': 'Student profile not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        student = request.user.student_profile
        current_semester = Semester.objects.filter(is_current=True).first()
        
        if not current_semester:
            return Response({
                'has_current_semester': False,
                'message': 'No current semester set'
            })
        
        # ✅ Updated Model Name
        registrations = CourseRegistration.objects.filter(
            student=student,
            course_offering__semester=current_semester,
            status='registered'
        )

        # Count pending registrations too
        pending_registrations = CourseRegistration.objects.filter(
            student=student,
            course_offering__semester=current_semester,
            status__in=['pending', 'approved_lecturer']
        )
        
        # --- FEE PAYMENT CHECK (STRICT) ---
        has_paid_fees = False
        invoice = Invoice.objects.filter(
            student=student,
            session=current_semester.session,
            semester=current_semester.semester
        ).first()
        
        if invoice and invoice.status == 'paid':
            has_paid_fees = True
        
        # --- SEMESTER STATUS CHECK ---
        is_registration_active = current_semester.is_registration_active
        registration_deadline = current_semester.registration_deadline
        
        can_register = (
            has_paid_fees and 
            is_registration_active and 
            # Check course limit (e.g. 12 for testing)
            (registrations.count() + pending_registrations.count()) < 12
        )
        
        return Response({
            'has_current_semester': True,
            'current_semester': {
                'id': current_semester.id,
                'session': current_semester.session,
                'semester': current_semester.semester,
                'is_registration_active': is_registration_active,
                'registration_deadline': registration_deadline,
                'start_date': current_semester.start_date,
                'end_date': current_semester.end_date,
                'real_is_active': current_semester.is_registration_active 
            },
            'registration_status': {
                'has_paid_fees': has_paid_fees,
                'can_register': can_register,
                'registered_courses': registrations.count(),
                'max_courses': 12, # Increased for testing
                'total_credits': sum(
                    r.course_offering.course.credits for r in registrations
                ) if registrations.exists() else 0
            }
        })
    
    @action(detail=False, methods=['get'])
    def current_schedule(self, request):
        """Get student's current semester schedule"""
        if not hasattr(request.user, 'student_profile'):
            return Response(
                {'error': 'Student profile not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        student = request.user.student_profile
        current_semester = Semester.objects.filter(is_current=True).first()
        
        if not current_semester:
            return Response([])
        
        # ✅ Updated Model Name
        registrations = CourseRegistration.objects.filter(
            student=student,
            course_offering__semester=current_semester,
            status__in=['registered', 'approved_lecturer']
        ).select_related(
            'course_offering__course',
            'course_offering__course__department',
            'course_offering__lecturer__user'
        )
        
        results = []
        for reg in registrations:
            grade = Grade.objects.filter(
                student=student,
                course=reg.course_offering.course,
                session=current_semester.session
            ).first()

            # ✅ KEY LOGIC: Only show scores if published
            grade_data = None
            if grade and grade.status == 'published':
                grade_data = {
                    'score': grade.score,
                    'grade_letter': grade.grade_letter,
                    'grade_points': grade.grade_points
                }
            
            results.append({
                'id': reg.id,
                'course_code': reg.course_offering.course.code,
                'course_title': reg.course_offering.course.title,
                'course_credits': reg.course_offering.course.credits,
                'lecturer_name': reg.course_offering.lecturer.user.get_full_name() if reg.course_offering.lecturer else 'TBA',
                'status': reg.status,
                'grade': grade_data, # Will be None if draft/verified
                'registration_date': reg.registration_date
            })
            
        return Response(results)
    
    @action(detail=False, methods=['get'])
    def available_courses(self, request):
        """Get courses available for student registration"""
        if not hasattr(request.user, 'student_profile'):
            return Response(
                {'error': 'Student profile not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        student = request.user.student_profile
        current_semester = Semester.objects.filter(is_current=True).first()
        
        if not current_semester:
            return Response([])
        
        # ✅ Updated Model Name
        current_registrations = CourseRegistration.objects.filter(
            student=student,
            course_offering__semester=current_semester
        ).exclude(status='dropped').values_list('course_offering_id', flat=True)
        
        # Get available course offerings for student's level and department
        available_offerings = CourseOffering.objects.filter(
            semester=current_semester,
            is_active=True,
            course__level=student.level,
            course__department=student.department
        ).exclude(
            id__in=current_registrations
        ).select_related(
            'course',
            'course__department',
            'lecturer__user'
        )
        
        # Check capacity
        available_offerings = [
            offering for offering in available_offerings 
            if offering.enrolled_count < offering.capacity
        ]
        
        serializer = CourseOfferingSerializer(available_offerings, many=True)
        return Response(serializer.data)
    
    # ✅ NEW ACTION FOR TRANSCRIPT/HISTORY
    @action(detail=False, methods=['get'])
    def academic_history(self, request):
        """Get complete academic history grouped by semester"""
        if not hasattr(request.user, 'student_profile'):
            return Response({'error': 'Student profile not found'}, status=400)

        student = request.user.student_profile
        
        # 1. Fetch all PUBLISHED grades directly (More robust than AcademicRecord)
        grades = Grade.objects.filter(
            student=student,
            status='published'
        ).select_related('course').order_by('-session', '-semester') # Latest first

        # 2. Build Response Structure
        history_map = {}
        
        for grade in grades:
            key = f"{grade.session}_{grade.semester}"
            if key not in history_map:
                history_map[key] = {
                    'session': grade.session,
                    'semester': grade.semester, # e.g. 'first'
                    'courses': [],
                    'total_units': 0,
                    'total_points': 0.0
                }
            
            # Add course info
            history_map[key]['courses'].append({
                'course_code': grade.course.code,
                'course_title': grade.course.title,
                'credits': grade.course.credits,
                'score': float(grade.score),
                'grade': grade.grade_letter,
                'points': float(grade.grade_points)
            })
            
            # Aggregate
            history_map[key]['total_units'] += grade.course.credits
            history_map[key]['total_points'] += float(grade.grade_points) * grade.course.credits

        # 3. Calculate GPAs and Format List
        history_list = []
        cumulative_points = 0.0
        cumulative_units = 0
        
        # Sort semesters (Latest first)
        # Assuming format "YYYY/YYYY_semester" can be sorted string-wise roughly correctly, 
        # or relying on the DB order we fetched.
        # Since we iterate a dict, order might be lost in older python, but 3.7+ keeps insertion order.
        # DB sort was: -session, -semester. So keys are inserted latest first.
        
        for key in history_map:
            data = history_map[key]
            
            gpa = 0.0
            if data['total_units'] > 0:
                gpa = data['total_points'] / data['total_units']
            
            cumulative_points += data['total_points']
            cumulative_units += data['total_units']
            
            history_list.append({
                'session': data['session'],
                'semester': data['semester'].capitalize(), # 'First', 'Second'
                'gpa': round(gpa, 2),
                'total_units': data['total_units'],
                'courses': data['courses']
            })

        # Calculate CGPA
        cgpa = 0.0
        if cumulative_units > 0:
            cgpa = cumulative_points / cumulative_units

        return Response({
            'student_info': {
                'name': student.user.get_full_name(),
                'matric': student.matric_number,
                'department': student.department.name if student.department else 'N/A'
            },
            'current_cgpa': round(cgpa, 2),
            'history': history_list
        })
        
    # ✅ NEW ACTION: Exam Card Generation
    @action(detail=False, methods=['get'])
    def exam_card(self, request):
        """Generate Exam Card Data"""
        if not hasattr(request.user, 'student_profile'):
            return Response({'error': 'Student profile not found'}, status=400)
        
        student = request.user.student_profile
        current_semester = Semester.objects.filter(is_current=True).first()
        
        if not current_semester:
            return Response({'error': 'No active semester for exam card.'}, status=400)
            
        # 1. Check if Fees Paid
        invoice = Invoice.objects.filter(
            student=student,
            session=current_semester.session,
            semester=current_semester.semester
        ).first()
        
        if not invoice or invoice.status != 'paid':
             return Response(
                {'error': 'Outstanding fees. Cannot generate Exam Card.'}, 
                status=status.HTTP_402_PAYMENT_REQUIRED
            )

        # 2. Get Registered Courses
        registrations = CourseRegistration.objects.filter(
            student=student,
            course_offering__semester=current_semester,
            status='registered'
        ).select_related('course_offering__course')

        if not registrations.exists():
            return Response(
                {'error': 'No registered courses found for this semester.'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        # 3. Compile Data
        courses = [{
            'code': reg.course_offering.course.code,
            'title': reg.course_offering.course.title,
            'unit': reg.course_offering.course.credits
        } for reg in registrations]
        
        return Response({
            'student': {
                'name': student.user.get_full_name(),
                'matric_number': student.matric_number,
                'department': student.department.name if student.department else 'N/A',
                'level': student.level,
                'passport_url': student.user.profile_picture.url if student.user.profile_picture else None
            },
            'semester': {
                'session': current_semester.session,
                'name': current_semester.get_semester_display()
            },
            'courses': courses,
            'total_units': sum(c['unit'] for c in courses),
            'generated_at': timezone.now()
        })


class CurrentSemesterAPIView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get current semester - accessible to all authenticated users"""
        try:
            semester = Semester.objects.get(is_current=True)
            serializer = SemesterSerializer(semester)
            return Response(serializer.data)
        except Semester.DoesNotExist:
            return Response(
                {'error': 'No current semester set'},
                status=status.HTTP_404_NOT_FOUND
            )

class StudentRegistrationStatusAPIView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]
    
    def get(self, request):
        """Get student's registration status"""
        if not hasattr(request.user, 'student_profile'):
            return Response(
                {'error': 'Student profile not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        student = request.user.student_profile
        current_semester = Semester.objects.filter(is_current=True).first()
        
        if not current_semester:
            return Response({
                'has_current_semester': False,
                'message': 'No current semester set'
            })
        
        # Count existing
        registrations = CourseRegistration.objects.filter(
            student=student,
            course_offering__semester=current_semester,
            status='registered'
        )
        
        # --- FEE CHECK LOGIC ---
        has_paid_fees = False
        invoice = Invoice.objects.filter(
            student=student,
            session=current_semester.session,
            semester=current_semester.semester
        ).first()
        
        if invoice and invoice.status == 'paid':
            has_paid_fees = True

        # Check active status
        is_registration_active = current_semester.is_registration_active
        registration_deadline = current_semester.registration_deadline
        
        can_register = has_paid_fees and is_registration_active
        
        return Response({
            'has_current_semester': True,
            'current_semester': {
                'id': current_semester.id,
                'session': current_semester.session,
                'semester': current_semester.semester,
                'is_registration_active': is_registration_active,
                'registration_deadline': registration_deadline,
                'start_date': current_semester.start_date,
                'end_date': current_semester.end_date,
            },
            'registration_status': {
                'has_paid_fees': has_paid_fees,
                'can_register': can_register,
                'registered_courses': registrations.count(),
                'max_courses': 12,
                'total_credits': sum(
                    r.course_offering.course.credits for r in registrations
                ) if registrations.exists() else 0
            }
        })