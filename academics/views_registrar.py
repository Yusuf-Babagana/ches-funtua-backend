# academics/views_registrar.py
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.db.models import Count, Avg, Q, Sum, F, ExpressionWrapper, FloatField, Max
from django.db import transaction
from django.utils import timezone
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO
from django.http import HttpResponse
from django.core.exceptions import ValidationError

# ✅ Updated Import: Registration -> CourseRegistration
from .models import (
    Course, CourseOffering, CourseRegistration, Grade, 
    Semester, Department, Enrollment,
    StudentAcademicRecord
)
from users.serializers import StudentSerializer
from admissions.models import Application, AdmissionLetter
from finance.models import Invoice, Payment
from users.models import User, Lecturer, Student
from .serializers import (
    CourseSerializer, GradeSerializer,
    DepartmentSerializer, SemesterSerializer, StudentAcademicRecordSerializer
)
from users.permissions import IsRegistrar


# ==============================================
# REGISTRAR DASHBOARD VIEW
# ==============================================

class RegistrarDashboardViewSet(viewsets.ViewSet):
    """Registrar dashboard with comprehensive overview"""
    permission_classes = [IsAuthenticated, IsRegistrar]



    def list(self, request):
        # 1. Global Counts
        total_students = Student.objects.count()
        
        # Students who have registered but not approved by registrar yet
        # Assuming Student model has a 'status' field or similar
        pending_admissions = Student.objects.filter(status='pending').count()
        
        total_departments = Department.objects.count()
        
        # 2. Active Semester Info
        try:
            current_semester = Semester.objects.get(is_current=True)
            semester_info = f"{current_semester.session} - {current_semester.get_semester_display()}"
        except Semester.DoesNotExist:
            semester_info = "No Active Session"

        # 3. Recent Students
        recent_students = Student.objects.select_related('user', 'department').order_by('-created_at')[:5]

        return Response({
            "stats": {
                "total_students": total_students,
                "pending_admissions": pending_admissions,
                "total_departments": total_departments,
                "current_session": semester_info
            },
            "recent_registrations": [
                {
                    "id": s.id,
                    "name": s.user.get_full_name(),
                    "matric": s.matric_number,
                    "department": s.department.code if s.department else "Unassigned",
                    "status": s.status
                } for s in recent_students
            ]
        })
    
    @action(detail=False, methods=['get'])
    def overview(self, request):
        """Get registrar dashboard overview"""
        # Get current semester
        current_semester = Semester.objects.filter(is_current=True).first()
        
        # Get pending admissions
        pending_admissions = Application.objects.filter(
            status__in=['submitted', 'under_review']
        ).count()
        
        # Get pending matric assignments (admitted students without matric)
        admitted_without_matric = Application.objects.filter(
            status='admitted'
        ).exclude(
            admission_letter__matric_number__isnull=False
        ).count()
        
        # Get pending final result approvals
        pending_final_approvals = self._get_pending_final_approvals()
        
        # Get pending clearance applications
        pending_clearance = self._get_pending_clearance()
        
        # Get academic year statistics
        academic_stats = self._get_academic_year_statistics()
        
        # Get upcoming academic deadlines
        upcoming_deadlines = self._get_upcoming_deadlines(current_semester)
        
        return Response({
            'current_semester': {
                'id': current_semester.id if current_semester else None,
                'session': current_semester.session if current_semester else None,
                'semester': current_semester.get_semester_display() if current_semester else None,
                'is_registration_active': current_semester.is_registration_active if current_semester else False,
            },
            'statistics': {
                'total_students': Student.objects.count(),
                'total_departments': Department.objects.count(),
                'total_courses': Course.objects.count(),
                'pending_admissions': pending_admissions,
                'pending_matric_assignments': admitted_without_matric,
                'pending_final_approvals': pending_final_approvals,
                'pending_clearance': pending_clearance,
                'graduating_students': Student.objects.filter(
                    level='400',  # Adjust based on your program
                    status='active'
                ).count()
            },
            'academic_year_statistics': academic_stats,
            'upcoming_deadlines': upcoming_deadlines,
            'quick_actions': [
                {'action': 'manage_admissions', 'label': 'Manage Admissions', 'count': pending_admissions},
                {'action': 'assign_matric', 'label': 'Assign Matric Numbers', 'count': admitted_without_matric},
                {'action': 'approve_results', 'label': 'Approve Results', 'count': pending_final_approvals},
                {'action': 'process_clearance', 'label': 'Process Clearance', 'count': pending_clearance},
                {'action': 'manage_semesters', 'label': 'Manage Semesters', 'count': 0}
            ]
        })
    
    def _get_pending_final_approvals(self):
        """Get count of results pending final approval"""
        # This would check for results approved by HOD but not by Registrar
        # For now, return placeholder
        return 0
    
    def _get_pending_clearance(self):
        """Get count of pending clearance applications"""
        # Placeholder - implement based on your clearance system
        return 0
    
    def _get_academic_year_statistics(self):
        """Get academic year statistics"""
        current_year = timezone.now().year
        sessions = []
        
        # Get last 3 academic sessions
        for year in range(current_year - 1, current_year + 1):
            session = f"{year}/{year + 1}"
            sessions.append(session)
        
        stats = []
        for session in sessions:
            # Get student count for session
            students_in_session = Student.objects.filter(
                admission_date__year=int(session.split('/')[0])
            ).count()
            
            # Get graduation count for session
            graduated_in_session = Student.objects.filter(
                status='graduated',
                updated_at__year=int(session.split('/')[1])
            ).count()
            
            stats.append({
                'session': session,
                'students_admitted': students_in_session,
                'students_graduated': graduated_in_session,
                'graduation_rate': (graduated_in_session / students_in_session * 100) if students_in_session > 0 else 0
            })
        
        return stats
    
    def _get_upcoming_deadlines(self, current_semester):
        """Get upcoming academic deadlines"""
        deadlines = []
        
        if current_semester:
            # Semester start/end deadlines
            deadlines.append({
                'title': 'Semester Start',
                'date': current_semester.start_date,
                'type': 'semester_start',
                'days_until': (current_semester.start_date - timezone.now().date()).days
            })
            
            deadlines.append({
                'title': 'Semester End',
                'date': current_semester.end_date,
                'type': 'semester_end',
                'days_until': (current_semester.end_date - timezone.now().date()).days
            })
            
            # Registration deadline
            if current_semester.registration_deadline:
                deadlines.append({
                    'title': 'Registration Deadline',
                    'date': current_semester.registration_deadline,
                    'type': 'registration',
                    'days_until': (current_semester.registration_deadline - timezone.now().date()).days
                })
        
        # Sort by date
        deadlines.sort(key=lambda x: x['date'])
        
        return deadlines


# ==============================================
# MATRIC NUMBER ASSIGNMENT
# ==============================================

class MatricAssignmentViewSet(viewsets.ViewSet):
    """Matric number assignment for new students"""
    permission_classes = [IsAuthenticated, IsRegistrar]
    
    @action(detail=False, methods=['get'])
    def pending_assignments(self, request):
        """Get admitted students needing matric numbers"""
        # Get admitted applications without matric numbers
        admitted_applications = Application.objects.filter(
            status='admitted'
        ).exclude(
            admission_letter__matric_number__isnull=False
        ).select_related(
            'first_choice_department',
            'admission_letter'
        ).order_by('submitted_date')
        
        applications_data = []
        for app in admitted_applications:
            # Generate suggested matric number
            suggested_matric = self._generate_suggested_matric(app)
            
            applications_data.append({
                'application_id': app.id,
                'application_number': app.application_number,
                'student_name': app.full_name,
                'email': app.email,
                'phone': app.phone,
                'programme_type': app.get_programme_type_display(),
                'department': app.first_choice_department.name if app.first_choice_department else 'Not assigned',
                'department_code': app.first_choice_department.code if app.first_choice_department else None,
                'admission_number': app.admission_letter.admission_number if hasattr(app, 'admission_letter') else None,
                'suggested_matric': suggested_matric,
                'admission_date': app.admission_letter.issued_date if hasattr(app, 'admission_letter') else None,
                'session': app.session
            })
        
        return Response({
            'total_pending': len(applications_data),
            'applications': applications_data
        })
    
    def _generate_suggested_matric(self, application):
        """Generate suggested matric number"""
        if not application.first_choice_department:
            return None
        
        department_code = application.first_choice_department.code
        session_year = application.session.split('/')[0][-2:]  # Last 2 digits of year
        programme_code = self._get_programme_code(application.programme_type)
        
        # Get the next sequence number for this department/session/programme
        last_matric = Student.objects.filter(
            matric_number__startswith=f"{department_code}/{session_year}/{programme_code}"
        ).aggregate(Max('matric_number'))['matric_number__max']
        
        if last_matric:
            # Extract the sequence number and increment
            try:
                sequence = int(last_matric.split('/')[-1])
                next_sequence = sequence + 1
            except (ValueError, IndexError):
                next_sequence = 1
        else:
            next_sequence = 1
        
        # Format: DEPT/YEAR/PROG/001
        return f"{department_code}/{session_year}/{programme_code}/{next_sequence:03d}"
    
    def _get_programme_code(self, programme_type):
        """Get programme code from programme type"""
        programme_codes = {
            'nce': 'NCE',
            'degree': 'BSC',
            'diploma': 'DIP',
            'pgd': 'PGD',
            'masters': 'MSC'
        }
        return programme_codes.get(programme_type, 'GEN')
    
    @action(detail=False, methods=['post'])
    def assign_matric_numbers(self, request):
        """Assign matric numbers to admitted students"""
        assignments = request.data.get('assignments', [])
        
        if not assignments:
            return Response(
                {'error': 'assignments array is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        successful = []
        failed = []
        
        for assignment in assignments:
            application_id = assignment.get('application_id')
            matric_number = assignment.get('matric_number')
            
            if not application_id or not matric_number:
                failed.append({
                    'assignment': assignment,
                    'error': 'application_id and matric_number are required'
                })
                continue
            
            try:
                with transaction.atomic():
                    application = Application.objects.get(
                        id=application_id,
                        status='admitted'
                    )
                    
                    # Check if matric number is unique
                    if Student.objects.filter(matric_number=matric_number).exists():
                        failed.append({
                            'assignment': assignment,
                            'error': f'Matric number {matric_number} already exists'
                        })
                        continue
                    
                    # Check if admission letter exists
                    if not hasattr(application, 'admission_letter'):
                        failed.append({
                            'assignment': assignment,
                            'error': 'No admission letter found'
                        })
                        continue
                    
                    # Update admission letter with matric number
                    admission_letter = application.admission_letter
                    admission_letter.matric_number = matric_number
                    admission_letter.save()
                    
                    # Create student record
                    student = self._create_student_record(application, matric_number)
                    
                    successful.append({
                        'application_id': application_id,
                        'matric_number': matric_number,
                        'student_id': student.id,
                        'student_name': student.user.get_full_name()
                    })
                    
            except Application.DoesNotExist:
                failed.append({
                    'assignment': assignment,
                    'error': 'Application not found or not admitted'
                })
            except Exception as e:
                failed.append({
                    'assignment': assignment,
                    'error': str(e)
                })
        
        return Response({
            'successful': successful,
            'failed': failed,
            'message': f'Successfully assigned matric numbers to {len(successful)} students, {len(failed)} failed'
        })
    
    def _create_student_record(self, application, matric_number):
        """Create student record from application"""
        # Create user first
        user_data = {
            'email': application.email,
            'username': matric_number,
            'first_name': application.first_name,
            'last_name': application.last_name,
            'role': 'student',
            'phone': application.phone,
            'is_active': True
        }
        
        # Generate temporary password
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits
        password = ''.join(secrets.choice(alphabet) for i in range(12))
        
        user = User.objects.create_user(
            **user_data,
            password=password
        )
        
        # Create student profile
        student = Student.objects.create(
            user=user,
            matric_number=matric_number,
            level='100',  # Starting level
            department=application.first_choice_department,
            status='active',
            admission_date=application.admission_letter.issued_date,
            date_of_birth=application.date_of_birth,
            address=application.address,
            guardian_name=application.guardian_name,
            guardian_phone=application.guardian_phone
        )
        
        # Send welcome email with credentials (implement email sending)
        self._send_welcome_email(user, matric_number, password)
        
        return student
    
    def _send_welcome_email(self, user, matric_number, password):
        """Send welcome email to new student"""
        # Placeholder - implement email sending
        # In production, use Django's email system
        pass
    
    @action(detail=False, methods=['get'])
    def matric_number_patterns(self, request):
        """Get matric number patterns for different programmes"""
        departments = Department.objects.all()
        
        patterns = []
        for dept in departments:
            for programme_type in Application.PROGRAMME_CHOICES:
                programme_code = self._get_programme_code(programme_type[0])
                current_year = timezone.now().year
                session_year = str(current_year)[-2:]
                
                # Get example
                last_matric = Student.objects.filter(
                    matric_number__startswith=f"{dept.code}/{session_year}/{programme_code}/"
                ).order_by('-matric_number').first()
                
                if last_matric:
                    # Increment the last matric number for example
                    try:
                        parts = last_matric.matric_number.split('/')
                        sequence = int(parts[-1])
                        example = f"{dept.code}/{session_year}/{programme_code}/{sequence + 1:03d}"
                    except:
                        example = f"{dept.code}/{session_year}/{programme_code}/001"
                else:
                    example = f"{dept.code}/{session_year}/{programme_code}/001"
                
                patterns.append({
                    'department': dept.name,
                    'department_code': dept.code,
                    'programme': programme_type[1],
                    'programme_code': programme_code,
                    'pattern': f"{dept.code}/YY/{programme_code}/XXX",
                    'example': example,
                    'description': f"{dept.code} - Department code, YY - Year, {programme_code} - Programme code, XXX - Sequence"
                })
        
        return Response(patterns)


# ==============================================
# ACADEMIC SESSION/SEMESTER MANAGEMENT
# ==============================================

class AcademicSessionViewSet(viewsets.ViewSet):
    """
    Manages Academic Sessions and Semesters.
    Note: 'current_academic_year' is public for all authenticated users.
    Management actions are restricted to Registrar.
    """
    permission_classes = [IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def current_academic_year(self, request):
        """
        Returns the active semester/session info.
        Used by: Student Dashboard, Course Registration
        """
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            return Response({
                'session': 'N/A', 
                'semester': 'None', 
                'is_registration_active': False
            })
            
        return Response({
            'id': current_semester.id,
            'session': current_semester.session,
            'semester': current_semester.semester,
            'is_current': True,
            'is_registration_active': current_semester.is_registration_active,
            'registration_deadline': current_semester.registration_deadline,
            'start_date': current_semester.start_date,
            'end_date': current_semester.end_date
        })
    
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated, IsRegistrar])
    def create_academic_year(self, request):
        """Create new academic year with both semesters"""
        session = request.data.get('session')  # e.g., "2024/2025"
        first_semester_start = request.data.get('first_semester_start')
        first_semester_end = request.data.get('first_semester_end')
        
        if not all([session, first_semester_start, first_semester_end]):
            return Response(
                {'error': 'session, first_semester_start, and first_semester_end are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            # Parse dates
            first_start = datetime.strptime(first_semester_start, '%Y-%m-%d').date()
            first_end = datetime.strptime(first_semester_end, '%Y-%m-%d').date()
            
            # Calculate second semester dates (typically starts 1 week after first semester ends)
            second_start = first_end + timedelta(weeks=1)
            second_end = second_start + timedelta(days=(first_end - first_start).days)
            
            with transaction.atomic():
                # Deactivate current semesters
                Semester.objects.filter(is_current=True).update(is_current=False)
                
                # Create first semester
                first_semester = Semester.objects.create(
                    session=session,
                    semester='first',
                    start_date=first_start,
                    end_date=first_end,
                    is_current=True,
                    registration_deadline=first_start + timedelta(weeks=2),  # 2 weeks for registration
                    is_registration_active=True
                )
                
                # Create second semester
                second_semester = Semester.objects.create(
                    session=session,
                    semester='second',
                    start_date=second_start,
                    end_date=second_end,
                    is_current=False,
                    registration_deadline=second_start + timedelta(weeks=2),
                    is_registration_active=False
                )
            
            return Response({
                'message': f'Academic year {session} created successfully',
                'first_semester': SemesterSerializer(first_semester).data,
                'second_semester': SemesterSerializer(second_semester).data
            })
            
        except ValueError:
            return Response(
                {'error': 'Dates must be in YYYY-MM-DD format'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsRegistrar])
    def current_academic_year_detailed(self, request):
        """Get current academic year overview (detailed, for registrar only)"""
        current_semester = Semester.objects.filter(is_current=True).first()
        
        if not current_semester:
            return Response({
                'has_current_semester': False,
                'message': 'No current semester set'
            })
        
        # Get both semesters for current session
        semesters = Semester.objects.filter(
            session=current_semester.session
        ).order_by('semester')
        
        # Get academic calendar events
        academic_calendar = self._get_academic_calendar(current_semester.session)
        
        # Get enrollment statistics
        enrollment_stats = self._get_enrollment_statistics(current_semester.session)
        
        return Response({
            'has_current_semester': True,
            'academic_year': current_semester.session,
            'semesters': SemesterSerializer(semesters, many=True).data,
            'academic_calendar': academic_calendar,
            'enrollment_statistics': enrollment_stats,
            'current_semester': {
                'id': current_semester.id,
                'semester': current_semester.get_semester_display(),
                'is_current': current_semester.is_current,
                'is_registration_active': current_semester.is_registration_active,
                'start_date': current_semester.start_date,
                'end_date': current_semester.end_date,
                'registration_deadline': current_semester.registration_deadline
            }
        })
    
    def _get_academic_calendar(self, session):
        """Get academic calendar for session"""
        semesters = Semester.objects.filter(session=session)
        
        calendar_events = []
        for semester in semesters:
            # Add semester events
            calendar_events.append({
                'title': f'{semester.get_semester_display()} Begins',
                'date': semester.start_date,
                'type': 'semester_start',
                'semester': semester.semester
            })
            
            calendar_events.append({
                'title': f'{semester.get_semester_display()} Registration Deadline',
                'date': semester.registration_deadline,
                'type': 'registration_deadline',
                'semester': semester.semester
            })
            
            # Add exam period (2 weeks before semester end)
            exam_start = semester.end_date - timedelta(weeks=2)
            calendar_events.append({
                'title': f'{semester.get_semester_display()} Exams Begin',
                'date': exam_start,
                'type': 'exams_start',
                'semester': semester.semester
            })
            
            calendar_events.append({
                'title': f'{semester.get_semester_display()} Ends',
                'date': semester.end_date,
                'type': 'semester_end',
                'semester': semester.semester
            })
        
        # Sort by date
        calendar_events.sort(key=lambda x: x['date'])
        
        return calendar_events
    
    def _get_enrollment_statistics(self, session):
        """Get enrollment statistics for academic year"""
        # Get total enrollments by level
        enrollments_by_level = Enrollment.objects.filter(
            session=session
        ).values('student__level').annotate(
            count=Count('id')
        ).order_by('student__level')
        
        # Get enrollment by department
        enrollments_by_department = Enrollment.objects.filter(
            session=session
        ).values('course__department__name').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Get new students for this session
        new_students = Student.objects.filter(
            admission_date__year=int(session.split('/')[0])
        ).count()
        
        return {
            'total_enrollments': Enrollment.objects.filter(session=session).count(),
            'enrollments_by_level': list(enrollments_by_level),
            'enrollments_by_department': list(enrollments_by_department),
            'new_students': new_students
        }
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsRegistrar])
    def activate_semester(self, request, pk=None):
        """Activate a semester as current"""
        try:
            semester = Semester.objects.get(id=pk)
            
            with transaction.atomic():
                # Deactivate all semesters
                Semester.objects.filter(is_current=True).update(is_current=False)
                
                # Activate this semester
                semester.is_current = True
                semester.save()
            
            return Response({
                'message': f'{semester.get_semester_display()} {semester.session} activated as current semester',
                'semester': SemesterSerializer(semester).data
            })
            
        except Semester.DoesNotExist:
            return Response(
                {'error': 'Semester not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsRegistrar])
    def toggle_registration(self, request, pk=None):
        """Toggle registration activity for a semester"""
        try:
            semester = Semester.objects.get(id=pk)
            
            semester.is_registration_active = not semester.is_registration_active
            semester.save()
            
            action = 'activated' if semester.is_registration_active else 'deactivated'
            
            return Response({
                'message': f'Registration {action} for {semester.get_semester_display()} {semester.session}',
                'semester': SemesterSerializer(semester).data
            })
            
        except Semester.DoesNotExist:
            return Response(
                {'error': 'Semester not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated, IsRegistrar])
    def academic_calendar(self, request):
        """Get complete academic calendar"""
        # Get all future semesters
        today = timezone.now().date()
        future_semesters = Semester.objects.filter(
            start_date__gte=today
        ).order_by('start_date')
        
        # Get all academic events
        calendar_events = []
        for semester in future_semesters:
            # Add semester events
            events = self._get_semester_events(semester)
            calendar_events.extend(events)
        
        # Add admission deadlines (assuming AdmissionSession model exists)
        try:
            from admissions.models import AdmissionSession
            admission_sessions = AdmissionSession.objects.filter(
                end_date__gte=today
            )
            for session in admission_sessions:
                calendar_events.append({
                    'title': f'{session.session} Admissions Close',
                    'date': session.end_date,
                    'type': 'admission_deadline',
                    'description': 'Last day to submit admission applications'
                })
        except ImportError:
            pass
        
        # Sort by date
        calendar_events.sort(key=lambda x: x['date'])
        
        return Response(calendar_events)
    
    def _get_semester_events(self, semester):
        """Get all events for a semester"""
        events = []
        
        # Semester start
        events.append({
            'title': f'{semester.get_semester_display()} Begins',
            'date': semester.start_date,
            'type': 'semester_start',
            'semester': semester.semester,
            'session': semester.session
        })
        
        # Registration deadline
        events.append({
            'title': f'{semester.get_semester_display()} Registration Deadline',
            'date': semester.registration_deadline,
            'type': 'registration_deadline',
            'semester': semester.semester,
            'session': semester.session
        })
        
        # Mid-semester break (assume 1 week at midpoint)
        midpoint = semester.start_date + (semester.end_date - semester.start_date) / 2
        break_start = midpoint - timedelta(days=3)
        break_end = midpoint + timedelta(days=3)
        
        events.append({
            'title': f'{semester.get_semester_display()} Mid-Semester Break',
            'date': break_start,
            'type': 'break_start',
            'semester': semester.semester,
            'session': semester.session,
            'end_date': break_end
        })
        
        # Exams start (2 weeks before semester end)
        exam_start = semester.end_date - timedelta(weeks=2)
        events.append({
            'title': f'{semester.get_semester_display()} Exams Begin',
            'date': exam_start,
            'type': 'exams_start',
            'semester': semester.semester,
            'session': semester.session
        })
        
        # Semester end
        events.append({
            'title': f'{semester.get_semester_display()} Ends',
            'date': semester.end_date,
            'type': 'semester_end',
            'semester': semester.semester,
            'session': semester.session
        })
        
        return events


# ==============================================
# FINAL RESULT APPROVAL
# ==============================================

class FinalResultApprovalViewSet(viewsets.ViewSet):
    """Final result approval by registrar"""
    permission_classes = [IsAuthenticated, IsRegistrar]
    
    @action(detail=False, methods=['get'])
    def pending_approvals(self, request):
        """Get results pending final approval"""
        # Get current semester
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            return Response(
                {'error': 'No current semester set'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get courses with grades that need final approval
        # In your system, you might have a field like 'requires_registrar_approval'
        # For now, we'll get all courses with grades in current semester
        
        courses = Course.objects.filter(
            grades__session=current_semester.session,
            grades__semester=current_semester.semester
        ).distinct().select_related('department')
        
        pending_courses = []
        for course in courses:
            # Get grade statistics
            grades = Grade.objects.filter(
                course=course,
                session=current_semester.session,
                semester=current_semester.semester
            )
            
            # Check if HOD has approved (placeholder - implement your approval workflow)
            hod_approved = self._check_hod_approval(course, current_semester)
            
            # Check for anomalies
            has_anomalies = self._check_result_anomalies(grades)
            
            pending_courses.append({
                'course_id': course.id,
                'course_code': course.code,
                'course_title': course.title,
                'department': course.department.name,
                'lecturer': course.lecturer.user.get_full_name() if course.lecturer else 'Not assigned',
                'total_students': grades.count(),
                'hod_approved': hod_approved,
                'has_anomalies': has_anomalies,
                'average_score': self._calculate_average(grades),
                'pass_rate': self._calculate_pass_rate(grades),
                'submission_date': grades.latest('created_at').created_at if grades.exists() else None
            })
        
        return Response({
            'total_pending': len(pending_courses),
            'courses': pending_courses
        })
    
    def _check_hod_approval(self, course, semester):
        """Check if HOD has approved results"""
        # Placeholder - implement based on your approval workflow
        # This could check an approval model or status field
        return True
    
    def _check_result_anomalies(self, grades):
        """Check for result anomalies"""
        if not grades.exists():
            return False
        
        total = grades.count()
        
        # Check for grade distribution anomalies
        a_count = grades.filter(grade_letter='A').count()
        f_count = grades.filter(grade_letter='F').count()
        
        # Flag if more than 50% got A or more than 30% failed
        if (a_count / total > 0.5) or (f_count / total > 0.3):
            return True
        
        # Check for score anomalies
        avg_score = self._calculate_average(grades)
        if avg_score > 85 or avg_score < 40:
            return True
        
        return False
    
    def _calculate_average(self, grades):
        """Calculate average score"""
        if not grades.exists():
            return 0
        
        total = sum(float(g.score) for g in grades)
        return round(total / grades.count(), 2)
    
    def _calculate_pass_rate(self, grades):
        """Calculate pass rate"""
        if not grades.exists():
            return 0
        
        passing = grades.filter(grade_letter__in=['A', 'B', 'C', 'D']).count()
        return round((passing / grades.count()) * 100, 1)
    
    @action(detail=True, methods=['get'])
    def course_result_details(self, request, pk=None):
        """Get detailed results for a course"""
        try:
            course = Course.objects.get(id=pk)
        except Course.DoesNotExist:
            return Response(
                {'error': 'Course not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            return Response(
                {'error': 'No current semester set'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get all grades
        grades = Grade.objects.filter(
            course=course,
            session=current_semester.session,
            semester=current_semester.semester
        ).select_related('student__user').order_by('student__matric_number')
        
        # Prepare result details
        result_details = []
        for grade in grades:
            # Get student's academic record
            academic_record = StudentAcademicRecord.objects.filter(
                student=grade.student,
                session=current_semester.session,
                semester=current_semester.semester
            ).first()
            
            result_details.append({
                'student_id': grade.student.id,
                'matric_number': grade.student.matric_number,
                'full_name': grade.student.user.get_full_name(),
                'level': grade.student.level,
                'score': float(grade.score),
                'grade_letter': grade.grade_letter,
                'grade_points': float(grade.grade_points),
                'gpa': academic_record.gpa if academic_record else 0,
                'cgpa': academic_record.cgpa if academic_record else 0,
                'remarks': grade.remarks,
                'needs_review': self._check_grade_needs_review(grade)
            })
        
        # Calculate statistics
        statistics = self._calculate_course_statistics(grades)
        
        # Get approval history (placeholder)
        approval_history = self._get_approval_history(course, current_semester)
        
        return Response({
            'course': {
                'id': course.id,
                'code': course.code,
                'title': course.title,
                'credits': course.credits,
                'department': course.department.name,
                'lecturer': course.lecturer.user.get_full_name() if course.lecturer else 'Not assigned',
                'semester': current_semester.get_semester_display(),
                'session': current_semester.session
            },
            'statistics': statistics,
            'results': result_details,
            'approval_history': approval_history,
            'anomalies': self._identify_anomalies(grades)
        })
    
    def _check_grade_needs_review(self, grade):
        """Check if a grade needs manual review"""
        borderlines = [59, 69, 79, 89]
        
        if int(grade.score) in borderlines:
            return True
        if grade.score > 95 or grade.score < 30:
            return True
        
        return False
    
    def _calculate_course_statistics(self, grades):
        """Calculate course statistics"""
        if not grades.exists():
            return {}
        
        scores = [float(g.score) for g in grades]
        avg_score = sum(scores) / len(scores)
        
        # Grade distribution
        distribution = {}
        for grade_choice in Grade.GRADE_CHOICES:
            grade_letter = grade_choice[0]
            count = grades.filter(grade_letter=grade_letter).count()
            distribution[grade_letter] = {
                'count': count,
                'percentage': round((count / len(grades)) * 100, 1) if len(grades) > 0 else 0
            }
        
        return {
            'total_students': len(grades),
            'average_score': round(avg_score, 2),
            'highest_score': max(scores),
            'lowest_score': min(scores),
            'standard_deviation': round(self._calculate_standard_deviation(scores), 2),
            'grade_distribution': distribution,
            'pass_rate': self._calculate_pass_rate(grades)
        }
    
    def _calculate_standard_deviation(self, scores):
        """Calculate standard deviation"""
        import statistics
        try:
            return statistics.stdev(scores)
        except statistics.StatisticsError:
            return 0
    
    def _get_approval_history(self, course, semester):
        """Get approval history for course results"""
        # Placeholder - implement based on your approval tracking
        return [
            {
                'action': 'submitted',
                'by': course.lecturer.user.get_full_name() if course.lecturer else 'Unknown',
                'date': semester.start_date + timedelta(days=60),  # Placeholder
                'remarks': 'Results submitted by lecturer'
            },
            {
                'action': 'approved',
                'by': 'HOD',  # Placeholder
                'date': semester.start_date + timedelta(days=65),
                'remarks': 'Approved by Head of Department'
            }
        ]
    
    def _identify_anomalies(self, grades):
        """Identify result anomalies"""
        anomalies = []
        
        for grade in grades:
            if self._check_grade_needs_review(grade):
                anomalies.append({
                    'student': grade.student.matric_number,
                    'score': grade.score,
                    'grade': grade.grade_letter,
                    'reason': 'Borderline score' if int(grade.score) in [59, 69, 79, 89] else 'Extreme score',
                    'needs_action': True
                })
        
        return anomalies
    
    @action(detail=True, methods=['post'])
    def approve_course_results(self, request, pk=None):
        """Approve final results for a course"""
        try:
            course = Course.objects.get(id=pk)
        except Course.DoesNotExist:
            return Response(
                {'error': 'Course not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            return Response(
                {'error': 'No current semester set'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        action = request.data.get('action')  # 'approve' or 'reject'
        remarks = request.data.get('remarks', '')
        
        if action not in ['approve', 'reject']:
            return Response(
                {'error': 'Action must be either "approve" or "reject"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if action == 'reject' and not remarks:
            return Response(
                {'error': 'Remarks are required when rejecting results'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if HOD has approved
        if not self._check_hod_approval(course, current_semester):
            return Response(
                {'error': 'Results must be approved by HOD first'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check for anomalies
        grades = Grade.objects.filter(
            course=course,
            session=current_semester.session,
            semester=current_semester.semester
        )
        
        anomalies = self._identify_anomalies(grades)
        has_critical_anomalies = any(a['needs_action'] for a in anomalies)
        
        if has_critical_anomalies and not request.data.get('override_anomalies', False):
            return Response({
                'has_anomalies': True,
                'anomalies': anomalies,
                'message': 'Critical anomalies detected. Review or override to proceed.'
            })
        
        # Perform approval/rejection
        if action == 'approve':
            # Update grades status to approved
            # In your system, you might update a field or create approval record
            message = f'Results for {course.code} approved successfully'
            
            # Update student academic records
            self._update_student_records(course, current_semester)
            
        else:
            # Reject results
            message = f'Results for {course.code} rejected'
            # You might notify the lecturer/HOD here
        
        # Create approval record (placeholder)
        approval_record = {
            'course': course.code,
            'action': action,
            'by': request.user.get_full_name(),
            'date': timezone.now(),
            'remarks': remarks,
            'anomalies_overridden': request.data.get('override_anomalies', False)
        }
        
        return Response({
            'message': message,
            'approval_record': approval_record,
            'anomalies_reviewed': len(anomalies)
        })
    
    def _update_student_records(self, course, semester):
        """Update student academic records after result approval"""
        grades = Grade.objects.filter(
            course=course,
            session=semester.session,
            semester=semester.semester
        ).select_related('student')
        
        for grade in grades:
            # Get or create academic record
            record, created = StudentAcademicRecord.objects.get_or_create(
                student=grade.student,
                level=grade.student.level,
                session=semester.session,
                semester=semester.semester,
                defaults={
                    'total_credits': 0,
                    'total_grade_points': 0
                }
            )
            
            # Update credits and grade points
            record.total_credits += course.credits
            record.total_grade_points += float(grade.grade_points) * course.credits
            record.save()  # This will trigger GPA/CGPA calculation
    
    @action(detail=False, methods=['get'])
    def approval_history(self, request):
        """Get history of result approvals"""
        # Placeholder - implement based on your approval tracking
        # This would return records from an Approval model
        
        return Response({
            'approvals': [],
            'message': 'Approval history tracking will be implemented'
        })


# ==============================================
# STUDENT CLEARANCE MANAGEMENT
# ==============================================

class StudentClearanceViewSet(viewsets.ViewSet):
    """Student clearance for graduation"""
    permission_classes = [IsAuthenticated, IsRegistrar]
    
    @action(detail=False, methods=['get'])
    def clearance_criteria(self, request):
        """Get clearance criteria for graduation"""
        criteria = {
            'academic': [
                {'id': 'gpa', 'name': 'Minimum CGPA', 'value': '1.50', 'required': True},
                {'id': 'credits', 'name': 'Total Credits Completed', 'value': '120', 'required': True},
                {'id': 'core_courses', 'name': 'Core Courses Passed', 'value': 'All', 'required': True},
                {'id': 'electives', 'name': 'Elective Credits', 'value': '30', 'required': True},
            ],
            'financial': [
                {'id': 'fees', 'name': 'All Fees Paid', 'value': 'Yes', 'required': True},
                {'id': 'library', 'name': 'Library Dues Cleared', 'value': 'Yes', 'required': True},
                {'id': 'other_dues', 'name': 'Other Dues', 'value': 'Cleared', 'required': True},
            ],
            'administrative': [
                {'id': 'id_card', 'name': 'ID Card Returned', 'value': 'Yes', 'required': False},
                {'id': 'library_books', 'name': 'Library Books Returned', 'value': 'All', 'required': True},
                {'id': 'project_report', 'name': 'Project Report Submitted', 'value': 'Yes', 'required': True},
            ]
        }
        
        return Response(criteria)
    
    @action(detail=False, methods=['get'])
    def pending_clearance(self, request):
        """Get students pending clearance"""
        # Get final year students (adjust based on your program)
        final_year_students = Student.objects.filter(
            level='400',  # Adjust level for your program
            status='active'
        ).select_related('user', 'department')
        
        pending_clearance = []
        for student in final_year_students:
            # Check clearance status
            clearance_status = self._check_clearance_status(student)
            
            if not clearance_status['cleared']:
                pending_clearance.append({
                    'student_id': student.id,
                    'matric_number': student.matric_number,
                    'full_name': student.user.get_full_name(),
                    'department': student.department.name,
                    'level': student.level,
                    'admission_date': student.admission_date,
                    'cgpa': self._calculate_student_cgpa(student),
                    'clearance_status': clearance_status,
                    'last_updated': timezone.now()  # Placeholder
                })
        
        return Response({
            'total_pending': len(pending_clearance),
            'students': pending_clearance
        })
    
    def _check_clearance_status(self, student):
        """Check student's clearance status"""
        status = {
            'cleared': True,
            'requirements': []
        }
        
        # Academic requirements
        cgpa = self._calculate_student_cgpa(student)
        if cgpa < 1.5:  # Example threshold
            status['cleared'] = False
            status['requirements'].append({
                'category': 'academic',
                'name': 'Minimum CGPA',
                'status': 'failed',
                'actual': f'{cgpa:.2f}',
                'required': '1.50',
                'description': f'CGPA of {cgpa:.2f} is below minimum requirement'
            })
        else:
            status['requirements'].append({
                'category': 'academic',
                'name': 'Minimum CGPA',
                'status': 'passed',
                'actual': f'{cgpa:.2f}',
                'required': '1.50'
            })
        
        # Check total credits
        total_credits = self._calculate_total_credits(student)
        if total_credits < 120:  # Example requirement
            status['cleared'] = False
            status['requirements'].append({
                'category': 'academic',
                'name': 'Total Credits',
                'status': 'failed',
                'actual': str(total_credits),
                'required': '120',
                'description': f'Only {total_credits} credits completed'
            })
        else:
            status['requirements'].append({
                'category': 'academic',
                'name': 'Total Credits',
                'status': 'passed',
                'actual': str(total_credits),
                'required': '120'
            })
        
        # Financial clearance
        financial_cleared = self._check_financial_clearance(student)
        if not financial_cleared:
            status['cleared'] = False
            status['requirements'].append({
                'category': 'financial',
                'name': 'Financial Dues',
                'status': 'failed',
                'description': 'Outstanding financial dues'
            })
        else:
            status['requirements'].append({
                'category': 'financial',
                'name': 'Financial Dues',
                'status': 'passed'
            })
        
        # Library clearance
        library_cleared = self._check_library_clearance(student)
        if not library_cleared:
            status['cleared'] = False
            status['requirements'].append({
                'category': 'administrative',
                'name': 'Library Clearance',
                'status': 'failed',
                'description': 'Library books not returned or dues outstanding'
            })
        else:
            status['requirements'].append({
                'category': 'administrative',
                'name': 'Library Clearance',
                'status': 'passed'
            })
        
        return status
    
    def _calculate_student_cgpa(self, student):
        """Calculate student's CGPA"""
        grades = Grade.objects.filter(student=student)
        if not grades.exists():
            return 0.0
        
        total_points = sum(float(g.grade_points) * g.course.credits for g in grades)
        total_credits = sum(g.course.credits for g in grades)
        
        return round(total_points / total_credits, 2) if total_credits > 0 else 0.0
    
    def _calculate_total_credits(self, student):
        """Calculate total credits completed by student"""
        grades = Grade.objects.filter(student=student)
        return sum(g.course.credits for g in grades)
    
    def _check_financial_clearance(self, student):
        """Check if student has cleared all financial obligations"""
        # Check for unpaid invoices
        unpaid_invoices = Invoice.objects.filter(
            student=student,
            status__in=['pending', 'partially_paid']
        ).exists()
        
        return not unpaid_invoices
    
    def _check_library_clearance(self, student):
        """Check library clearance"""
        # Placeholder - implement based on your library system
        return True
    
    @action(detail=True, methods=['get'])
    def student_clearance_detail(self, request, pk=None):
        """Get detailed clearance information for a student"""
        try:
            student = Student.objects.get(id=pk)
        except Student.DoesNotExist:
            return Response(
                {'error': 'Student not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Get clearance status
        clearance_status = self._check_clearance_status(student)
        
        # Get academic summary
        academic_summary = self._get_academic_summary(student)
        
        # Get financial status
        financial_status = self._get_financial_status(student)
        
        # Get clearance history
        clearance_history = self._get_clearance_history(student)
        
        return Response({
            'student': {
                'id': student.id,
                'matric_number': student.matric_number,
                'full_name': student.user.get_full_name(),
                'department': student.department.name,
                'level': student.level,
                'admission_date': student.admission_date,
                'status': student.status
            },
            'clearance_status': clearance_status,
            'academic_summary': academic_summary,
            'financial_status': financial_status,
            'clearance_history': clearance_history
        })
    
    def _get_academic_summary(self, student):
        """Get academic summary for student"""
        grades = Grade.objects.filter(student=student).select_related('course')
        
        total_credits = sum(g.course.credits for g in grades)
        cgpa = self._calculate_student_cgpa(student)
        
        # Get grade distribution
        grade_distribution = {}
        for grade_choice in Grade.GRADE_CHOICES:
            grade_letter = grade_choice[0]
            count = grades.filter(grade_letter=grade_letter).count()
            if count > 0:
                grade_distribution[grade_letter] = count
        
        # Get failed courses
        failed_courses = grades.filter(grade_letter='F').values_list('course__code', flat=True)
        
        return {
            'total_courses': grades.count(),
            'total_credits': total_credits,
            'cgpa': cgpa,
            'grade_distribution': grade_distribution,
            'failed_courses': list(failed_courses),
            'has_failed_courses': len(failed_courses) > 0
        }
    
    def _get_financial_status(self, student):
        """Get financial status for student"""
        invoices = Invoice.objects.filter(student=student)
        
        total_amount = invoices.aggregate(Sum('amount'))['amount__sum'] or 0
        total_paid = invoices.aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0
        balance = total_amount - total_paid
        
        # Get unpaid invoices
        unpaid_invoices = invoices.filter(
            status__in=['pending', 'partially_paid']
        ).values('invoice_number', 'amount', 'amount_paid', 'due_date', 'status')
        
        return {
            'total_amount': float(total_amount),
            'total_paid': float(total_paid),
            'balance': float(balance),
            'is_cleared': balance <= 0,
            'unpaid_invoices': list(unpaid_invoices)
        }
    
    def _get_clearance_history(self, student):
        """Get clearance history for student"""
        # Placeholder - implement based on your clearance tracking
        return []
    
    @action(detail=True, methods=['post'])
    def process_clearance(self, request, pk=None):
        """Process student clearance"""
        try:
            student = Student.objects.get(id=pk)
        except Student.DoesNotExist:
            return Response(
                {'error': 'Student not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        action = request.data.get('action')  # 'approve' or 'reject'
        remarks = request.data.get('remarks', '')
        
        if action not in ['approve', 'reject']:
            return Response(
                {'error': 'Action must be either "approve" or "reject"'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check clearance status
        clearance_status = self._check_clearance_status(student)
        
        if action == 'approve':
            if not clearance_status['cleared']:
                # Allow override with justification
                override = request.data.get('override', False)
                justification = request.data.get('justification', '')
                
                if not override:
                    return Response({
                        'can_approve': False,
                        'clearance_status': clearance_status,
                        'message': 'Student does not meet all clearance requirements'
                    })
                
                if not justification:
                    return Response(
                        {'error': 'Justification is required when overriding clearance requirements'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            
            # Approve clearance
            student.status = 'graduated'
            student.save()
            
            # Create clearance record
            clearance_record = {
                'student': student.matric_number,
                'action': 'approved',
                'by': request.user.get_full_name(),
                'date': timezone.now(),
                'remarks': remarks,
                'overridden': not clearance_status['cleared'],
                'justification': request.data.get('justification', '') if not clearance_status['cleared'] else ''
            }
            
            message = f'Clearance approved for {student.matric_number}'
            
        else:
            # Reject clearance
            clearance_record = {
                'student': student.matric_number,
                'action': 'rejected',
                'by': request.user.get_full_name(),
                'date': timezone.now(),
                'remarks': remarks,
                'requirements_missing': [r['name'] for r in clearance_status['requirements'] if r['status'] == 'failed']
            }
            
            message = f'Clearance rejected for {student.matric_number}'
        
        return Response({
            'message': message,
            'clearance_record': clearance_record,
            'student_status': student.status
        })
    
    @action(detail=False, methods=['get'])
    def clearance_report(self, request):
        """Generate clearance report"""
        # Get filter parameters
        department_id = request.query_params.get('department_id')
        status_filter = request.query_params.get('status')
        
        # Get students
        students = Student.objects.all()
        
        if department_id:
            students = students.filter(department_id=department_id)
        
        if status_filter:
            students = students.filter(status=status_filter)
        
        students = students.select_related('user', 'department')
        
        # Generate report data
        report_data = []
        for student in students:
            clearance_status = self._check_clearance_status(student)
            
            report_data.append({
                'matric_number': student.matric_number,
                'student_name': student.user.get_full_name(),
                'department': student.department.name,
                'level': student.level,
                'admission_date': student.admission_date,
                'status': student.status,
                'clearance_status': clearance_status['cleared'],
                'failed_requirements': [
                    r['name'] for r in clearance_status['requirements'] 
                    if r['status'] == 'failed'
                ],
                'cgpa': self._calculate_student_cgpa(student)
            })
        
        # Generate Excel report
        df = pd.DataFrame(report_data)
        
        # Create Excel file in memory
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Clearance Report', index=False)
            
            # Auto-adjust column widths
            worksheet = writer.sheets['Clearance Report']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = (max_length + 2)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        # Prepare response
        output.seek(0)
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="Clearance_Report.xlsx"'
        
        return response


# ==============================================
# MAIN REGISTRAR API VIEW
# ==============================================

class RegistrarAPIView(APIView):
    """Main API view for registrar frontend integration"""
    permission_classes = [IsAuthenticated, IsRegistrar]
    
    def get(self, request):
        """Get registrar's complete data for dashboard"""
        user = request.user
        
        # Get registrar profile
        registrar_data = {
            'id': user.id,
            'name': user.get_full_name(),
            'email': user.email,
            'role': user.role,
            'phone': user.phone
        }
        
        # Get current semester
        current_semester = Semester.objects.filter(is_current=True).first()
        
        # Get quick statistics
        quick_stats = {
            'total_students': Student.objects.count(),
            'total_departments': Department.objects.count(),
            'pending_admissions': Application.objects.filter(
                status__in=['submitted', 'under_review']
            ).count(),
            'pending_matric_assignments': Application.objects.filter(
                status='admitted'
            ).exclude(
                admission_letter__matric_number__isnull=False
            ).count()
        }
        
        return Response({
            'registrar': registrar_data,
            'current_semester': {
                'id': current_semester.id if current_semester else None,
                'session': current_semester.session if current_semester else None,
                'semester': current_semester.semester if current_semester else None
            },
            'quick_stats': quick_stats
        })