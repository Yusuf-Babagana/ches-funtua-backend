from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from rest_framework.views import APIView
from datetime import timedelta
from django.db.models import Sum

# ✅ Updated Imports
from .models import (
    Semester, CourseOffering, CourseRegistration, 
    Grade, StudentAcademicRecord, AcademicLevelConfiguration,
    Course
)
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
    
    def _get_student_semester(self, student):
        """
        Helper to get the correct semester for the student's specific level.
        Prioritizes AcademicLevelConfiguration, falls back to Global Current Semester.
        Returns: (semester_object, is_registration_open_boolean)
        """
        # 1. Check if there is a specific configuration for this level
        config = AcademicLevelConfiguration.objects.filter(level=student.level).select_related('current_semester').first()
        
        if config and config.current_semester:
            return config.current_semester, config.is_registration_open
            
        # 2. Fallback: Global Current Semester
        global_sem = Semester.objects.filter(is_current=True).first()
        
        # 3. Last Resort: Last created semester (prevents crashes if no active semester)
        if not global_sem:
            global_sem = Semester.objects.last()
            
        is_active = global_sem.is_registration_active if global_sem else False
        return global_sem, is_active

    @action(detail=False, methods=['get'])
    def current_semester(self, request):
        """Get current semester applicable to the logged-in student"""
        if not hasattr(request.user, 'student_profile'):
            return Response({'error': 'Student profile not found'}, status=400)
            
        student = request.user.student_profile
        semester, _ = self._get_student_semester(student)
        
        if semester:
            serializer = SemesterSerializer(semester)
            return Response(serializer.data)
            
        return Response(
            {'error': 'No active academic session found for your level.'},
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
        
        # ✅ USE HELPER: Get Level-Specific Semester
        current_semester, is_reg_open_for_level = self._get_student_semester(student)
        
        if not current_semester:
            return Response({
                'has_current_semester': False,
                'message': 'No current semester set'
            })
        
        # Count existing registrations for this specific semester
        registrations = CourseRegistration.objects.filter(
            student=student,
            course_offering__semester=current_semester,
            status='registered'
        )

        pending_registrations = CourseRegistration.objects.filter(
            student=student,
            course_offering__semester=current_semester,
            status__in=['pending', 'approved_lecturer']
        )
        
        # --- FEE PAYMENT CHECK (ALLOWS 2 COURSES IF UNPAID) ---
        has_paid_fees = False
        # Check for invoice matching this specific semester/session
        invoice = Invoice.objects.filter(
            student=student,
            session=current_semester.session,
            semester=current_semester.semester
        ).first()
        
        if invoice and invoice.status == 'paid':
            has_paid_fees = True

        # Count total registrations (active + pending)
        current_reg_count = registrations.count() + pending_registrations.count()
        
        # --- DEADLINE CHECK ---
        registration_deadline = current_semester.registration_deadline
        
        # ELIGIBILITY LOGIC:
        # 1. Paid students: Can register up to 15 courses
        # 2. Unpaid students: Can register up to 2 courses
        can_register_by_limit = (current_reg_count < 15) if has_paid_fees else (current_reg_count < 2)

        can_register = (
            can_register_by_limit and 
            is_reg_open_for_level
        )
        
        return Response({
            'has_current_semester': True,
            'current_semester': {
                'id': current_semester.id,
                'session': current_semester.session,
                'semester': current_semester.semester,
                'is_registration_active': is_reg_open_for_level,
                'registration_deadline': registration_deadline,
                'start_date': current_semester.start_date,
                'end_date': current_semester.end_date,
            },
            'registration_status': {
                'has_paid_fees': has_paid_fees,
                'can_register': can_register,
                'registered_courses': current_reg_count,
                'max_courses': 15 if has_paid_fees else 2, 
                'total_credits': sum(
                    r.course_offering.course.credits for r in (registrations | pending_registrations)
                ) if (registrations | pending_registrations).exists() else 0
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
        
        # ✅ USE HELPER
        current_semester, _ = self._get_student_semester(student)
        
        if not current_semester:
            return Response([])
        
        registrations = CourseRegistration.objects.filter(
            student=student,
            course_offering__semester=current_semester,
            status__in=['registered', 'approved_lecturer', 'approved_exam_officer']
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

            # Only show scores if published
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
                'grade': grade_data, 
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
        
        # ✅ USE HELPER
        current_semester, _ = self._get_student_semester(student)
        
        if not current_semester:
            return Response([])
        
        # Exclude already registered
        current_registrations = CourseRegistration.objects.filter(
            student=student,
            course_offering__semester=current_semester
        ).exclude(status='dropped').values_list('course_offering_id', flat=True)
        
        # ✅ SYNCHRONIZE OFFERINGS: Ensure ALL active courses have an offering for the current semester
        # This addresses the user requirement to "see all create courses... no matter from which department"
        
        # 1. Get IDs of all active Courses
        all_course_ids = set(Course.objects.values_list('id', flat=True))
        
        # 2. Get IDs of Courses that already have an offering for this semester
        existing_offering_course_ids = set(CourseOffering.objects.filter(
            semester=current_semester
        ).values_list('course_id', flat=True))
        
        # 3. Identify missing courses
        missing_course_ids = all_course_ids - existing_offering_course_ids
        
        # 4. Create missing offerings in bulk (optimization)
        if missing_course_ids:
            new_offerings = []
            for course_id in missing_course_ids:
                new_offerings.append(CourseOffering(
                    course_id=course_id,
                    semester=current_semester,
                    capacity=200, # Default capacity
                    is_active=True
                ))
            CourseOffering.objects.bulk_create(new_offerings)
        
        # Get available offerings
        # ✅ USER REQUEST: See ALL created courses regardless of department/semester/session
        # We fetch ALL active offerings in the system.
        available_offerings = CourseOffering.objects.filter(
            is_active=True
            # Removed: semester=current_semester (shows global pool if desired, or strictly current)
            # PROPOSAL: We should probably focus on current_semester offerings + others?
            # User said "no matter it is from which ... semester". 
            # However, typically you register for the CURRENT session. 
            # Showing offerings from 2020 for the *same* course alongside 2024 is confusing.
            # But since we just auto-generated current semester offerings for EVERYTHING, 
            # filtering by `semester=current_semester` is actually safer to ensure they register for the RIGHT instance.
            # BUT, the user explicitly said "no matter it is from which ... semester".
            # So I will leave the semester filter OFF, but order by semester desc so current ones are top?
            # Or reliance on the auto-gen ensures at least one current option exists.
        ).exclude(
            id__in=current_registrations
        ).select_related(
            'course',
            'course__department',
            'lecturer__user'
        ).order_by('-semester__start_date', 'course__code')
        
        # Filter by capacity
        available_offerings = [
            offering for offering in available_offerings 
            if offering.enrolled_count < offering.capacity
        ]
        
        serializer = CourseOfferingSerializer(available_offerings, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def academic_history(self, request):
        """Get complete academic history grouped by semester"""
        if not hasattr(request.user, 'student_profile'):
            return Response({'error': 'Student profile not found'}, status=400)

        student = request.user.student_profile
        
        # Fetch all PUBLISHED grades directly 
        grades = Grade.objects.filter(
            student=student,
            status='published'
        ).select_related('course').order_by('-session', '-semester') 

        history_map = {}
        
        for grade in grades:
            key = f"{grade.session}_{grade.semester}"
            if key not in history_map:
                history_map[key] = {
                    'session': grade.session,
                    'semester': grade.semester, 
                    'courses': [],
                    'total_units': 0,
                    'total_points': 0.0
                }
            
            history_map[key]['courses'].append({
                'course_code': grade.course.code,
                'course_title': grade.course.title,
                'credits': grade.course.credits,
                'score': float(grade.score),
                'grade': grade.grade_letter,
                'points': float(grade.grade_points)
            })
            
            history_map[key]['total_units'] += grade.course.credits
            history_map[key]['total_points'] += float(grade.grade_points) * grade.course.credits

        history_list = []
        cumulative_points = 0.0
        cumulative_units = 0
        
        for key in history_map:
            data = history_map[key]
            
            gpa = 0.0
            if data['total_units'] > 0:
                gpa = data['total_points'] / data['total_units']
            
            cumulative_points += data['total_points']
            cumulative_units += data['total_units']
            
            history_list.append({
                'session': data['session'],
                'semester': data['semester'].capitalize(), 
                'gpa': round(gpa, 2),
                'total_units': data['total_units'],
                'courses': data['courses']
            })

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
        
    @action(detail=False, methods=['get'])
    def exam_card(self, request):
        """Generate Exam Card Data"""
        if not hasattr(request.user, 'student_profile'):
            return Response({'error': 'Student profile not found'}, status=400)
        
        student = request.user.student_profile
        
        # ✅ USE HELPER
        current_semester, _ = self._get_student_semester(student)
        
        if not current_semester:
            return Response({'error': 'No active semester for exam card.'}, status=400)
            
        # 1. Check if Fees Paid (Strict)
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
            status__in=['registered', 'approved_exam_officer']
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
        """Get current semester (Generic/Global view, or customized per user if possible)"""
        # This generic endpoint usually returns the global current semester
        # But if you want it level-aware for a logged in user, you can inject logic here.
        # For now, keeping it global to match admin expectations, but Dashboard handles specifics.
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
        
        # ✅ Re-implement logic from ViewSet or just use ViewSet method directly?
        # Better to duplicate logic here slightly for the dedicated APIView structure
        # logic: 
        
        # 1. Check Level Config
        config = AcademicLevelConfiguration.objects.filter(level=student.level).first()
        if config and config.current_semester:
            current_semester = config.current_semester
            is_reg_open = config.is_registration_open
        else:
            current_semester = Semester.objects.filter(is_current=True).first()
            is_reg_open = current_semester.is_registration_active if current_semester else False
        
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

        registration_deadline = current_semester.registration_deadline
        
        can_register = has_paid_fees and is_reg_open
        
        return Response({
            'has_current_semester': True,
            'current_semester': {
                'id': current_semester.id,
                'session': current_semester.session,
                'semester': current_semester.semester,
                'is_registration_active': is_reg_open,
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