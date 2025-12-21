# academics/views_exam_officer.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.db.models import Count
from django.utils import timezone
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO
from django.http import HttpResponse

# ✅ Use Correct Models
from .models import (
    Course, CourseOffering, CourseRegistration, Grade, 
    Semester, Department, Enrollment
)
from .serializers import (
    CourseSerializer, GradeSerializer, DepartmentSerializer
)
from users.models import Student
from users.permissions import IsExamOfficer


# ==============================================
# EXAM OFFICER DASHBOARD VIEW
# ==============================================

class ExamOfficerDashboardViewSet(viewsets.ViewSet):
    """Exam officer dashboard with comprehensive overview"""
    permission_classes = [IsAuthenticated, IsExamOfficer]

    @action(detail=False, methods=['get'])
    def overview(self, request):
        """Get exam officer dashboard overview"""
        # 1. Robust Semester Fetching
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            current_semester = Semester.objects.last()
        
        if not current_semester:
            # Fallback for empty DB to prevent 400 error
            return Response({
                'current_semester': {},
                'statistics': {},
                'recent_activities': [],
                'stats': {},
                'exam_statistics': {},
                'upcoming_deadlines': [],
                'quick_actions': []
            })
        
        # Get pending registrations
        pending_registrations = CourseRegistration.objects.filter(
            status='approved_lecturer',
            is_payment_verified=True,
            course_offering__semester=current_semester
        ).count()
        
        # Get courses pending result compilation
        courses_pending_results = Course.objects.filter(
            offerings__semester=current_semester,
            offerings__is_active=True
        ).distinct().count()
        
        # Get departments
        departments = Department.objects.all()
        
        # Get exam statistics
        exam_stats = self._get_exam_statistics(current_semester)
        
        # Get upcoming deadlines
        upcoming_deadlines = self._get_upcoming_deadlines(current_semester)
        
        # Get recent activities
        recent_activities = self._get_recent_activities()
        
        return Response({
            'current_semester': {
                'id': current_semester.id,
                'session': current_semester.session,
                'semester': current_semester.get_semester_display(),
                'is_registration_active': current_semester.is_registration_active,
                'start_date': current_semester.start_date,
                'end_date': current_semester.end_date
            },
            'statistics': {
                'total_departments': departments.count(),
                'total_courses': Course.objects.filter(
                    offerings__semester=current_semester,
                    offerings__is_active=True
                ).distinct().count(),
                'total_students': Student.objects.count(),
                'pending_registrations': pending_registrations,
                'courses_pending_results': courses_pending_results,
                'completed_results': exam_stats.get('completed_courses', 0)
            },
            'stats': { # Added for frontend compatibility
                 'results_processed': exam_stats.get('completed_courses', 0),
                 'pending_results': courses_pending_results,
                 'exams_scheduled': 0,
                 'issues_flagged': 0
            },
            'exam_statistics': exam_stats,
            'upcoming_deadlines': upcoming_deadlines,
            'recent_activities': recent_activities,
            'quick_actions': [
                {'action': 'approve_registrations', 'label': 'Approve Registrations', 'count': pending_registrations},
                {'action': 'compile_results', 'label': 'Compile Results', 'count': courses_pending_results},
                {'action': 'generate_exam_list', 'label': 'Generate Exam List', 'count': 0},
                {'action': 'manage_timetable', 'label': 'Manage Timetable', 'count': 0}
            ]
        })
    
    def _get_exam_statistics(self, current_semester):
        """Get exam-related statistics"""
        courses_with_grades = Course.objects.filter(
            grades__session=current_semester.session,
            grades__semester=current_semester.semester
        ).distinct().count()
        
        total_courses = Course.objects.filter(
            offerings__semester=current_semester,
            offerings__is_active=True
        ).distinct().count()
        
        grades_distribution = Grade.objects.filter(
            session=current_semester.session,
            semester=current_semester.semester
        ).values('grade_letter').annotate(
            count=Count('id')
        ).order_by('grade_letter')
        
        total_grades = Grade.objects.filter(
            session=current_semester.session,
            semester=current_semester.semester
        ).count()
        
        passing_grades = Grade.objects.filter(
            session=current_semester.session,
            semester=current_semester.semester,
            grade_letter__in=['A', 'B', 'C', 'D']  # Passing grades
        ).count()
        
        pass_rate = (passing_grades / total_grades * 100) if total_grades > 0 else 0
        
        return {
            'completed_courses': courses_with_grades,
            'total_courses': total_courses,
            'completion_rate': (courses_with_grades / total_courses * 100) if total_courses > 0 else 0,
            'grades_distribution': list(grades_distribution),
            'pass_rate': round(pass_rate, 1)
        }
    
    def _get_upcoming_deadlines(self, current_semester):
        """Get upcoming deadlines for exam officer"""
        deadlines = []
        if current_semester.end_date:
            registration_deadline = current_semester.end_date - timedelta(weeks=6)
            if registration_deadline > timezone.now().date():
                deadlines.append({
                    'title': 'Registration Approval Deadline',
                    'date': registration_deadline,
                    'days_left': (registration_deadline - timezone.now().date()).days,
                    'type': 'registration'
                })
            
            result_deadline = current_semester.end_date + timedelta(weeks=2)
            if result_deadline > timezone.now().date():
                deadlines.append({
                    'title': 'Result Submission Deadline',
                    'date': result_deadline,
                    'days_left': (result_deadline - timezone.now().date()).days,
                    'type': 'results'
                })
        return deadlines
    
    def _get_recent_activities(self):
        """Get recent activities for exam officer"""
        recent_activities = []
        week_ago = timezone.now() - timedelta(days=7)
        
        recent_grades = Grade.objects.filter(
            created_at__gte=week_ago
        ).select_related('course', 'uploaded_by__user')[:5]
        
        for grade in recent_grades:
            recent_activities.append({
                'type': 'grade_upload',
                'title': f'Grades uploaded for {grade.course.code}',
                'details': f'Uploaded by {grade.uploaded_by.user.get_full_name() if grade.uploaded_by else "Unknown"}',
                'timestamp': grade.created_at,
                'course_code': grade.course.code
            })
        
        recent_approvals = CourseRegistration.objects.filter(
            approved_date__gte=week_ago,
            status='registered'
        ).select_related('course_offering__course', 'approved_by_exam_officer')[:5]
        
        for approval in recent_approvals:
            recent_activities.append({
                'type': 'registration_approved',
                'title': f'Registration approved for {approval.course_offering.course.code}',
                'details': f'Approved for student {approval.student.matric_number}',
                'timestamp': approval.approved_date,
                'course_code': approval.course_offering.course.code
            })
        
        return recent_activities


# ==============================================
# REGISTRATION APPROVAL FOR EXAM OFFICER
# ==============================================

class ExamOfficerRegistrationViewSet(viewsets.ViewSet):
    """Registration approval for exam officer"""
    permission_classes = [IsAuthenticated, IsExamOfficer]
    
    @action(detail=False, methods=['get'])
    def pending_approvals(self, request):
        """Get pending registrations for exam officer approval"""
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
             current_semester = Semester.objects.last()
        
        if not current_semester:
             return Response([])
        
        # Get pending registrations
        pending_registrations = CourseRegistration.objects.filter(
            status='approved_lecturer',
            is_payment_verified=True,
            course_offering__semester=current_semester
        ).select_related(
            'student__user',
            'course_offering__course',
            'course_offering__lecturer__user',
            'approved_by_lecturer__user'
        )
        
        # Filter by department if provided
        department_id = request.query_params.get('department_id')
        if department_id:
            pending_registrations = pending_registrations.filter(
                student__department_id=department_id
            )
        
        # Filter by course if provided
        course_id = request.query_params.get('course_id')
        if course_id:
            pending_registrations = pending_registrations.filter(
                course_offering__course_id=course_id
            )
        
        registrations_data = []
        for registration in pending_registrations:
            student = registration.student
            has_holds = False # Placeholder
            
            registrations_data.append({
                'id': registration.id,
                'student': {
                    'id': student.id,
                    'matric_number': student.matric_number,
                    'full_name': student.user.get_full_name(),
                    'level': student.level,
                    'department': student.department.name,
                    'cgpa': 0.0, 
                    'has_holds': has_holds
                },
                'course': {
                    'id': registration.course_offering.course.id,
                    'code': registration.course_offering.course.code,
                    'title': registration.course_offering.course.title,
                    'credits': registration.course_offering.course.credits,
                    'department': registration.course_offering.course.department.name
                },
                'lecturer': {
                    'name': registration.course_offering.lecturer.user.get_full_name() if registration.course_offering.lecturer else 'Not assigned',
                    'staff_id': registration.course_offering.lecturer.staff_id if registration.course_offering.lecturer else None
                },
                'approval_info': {
                    'approved_by_lecturer': registration.approved_by_lecturer.user.get_full_name() if registration.approved_by_lecturer else None,
                    'approval_date': registration.approved_date,
                    'payment_verified': registration.is_payment_verified,
                    'payment_verified_by': registration.payment_verified_by.get_full_name() if registration.payment_verified_by else None,
                    'payment_verified_date': registration.payment_verified_date
                },
                'eligibility': {
                    'has_holds': has_holds,
                    'meets_attendance': True,
                    'meets_prerequisites': registration.check_prerequisites(),
                    'has_paid_fees': registration.is_payment_verified,
                    'is_eligible': not has_holds and registration.check_prerequisites()
                }
            })
        
        return Response({
            'total_pending': len(registrations_data),
            'registrations': registrations_data
        })
    
    @action(detail=True, methods=['post'])
    def approve_registration(self, request, pk=None):
        try:
            registration = CourseRegistration.objects.get(
                id=pk,
                status='approved_lecturer',
                is_payment_verified=True
            )
        except CourseRegistration.DoesNotExist:
            return Response(
                {'error': 'Registration not found or not ready for approval'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        action = request.data.get('action')
        reason = request.data.get('reason', '')
        
        if action == 'approve':
            if registration.approve_by_exam_officer(request.user):
                return Response({'message': 'Registration approved successfully'})
            return Response({'error': 'Cannot approve'}, status=400)
        elif action == 'reject':
            if registration.reject_by_exam_officer(request.user, reason):
                return Response({'message': 'Registration rejected'})
            return Response({'error': 'Cannot reject'}, status=400)
        
        return Response({'error': 'Invalid action'}, status=400)

    @action(detail=False, methods=['post'])
    def bulk_approve_registrations(self, request):
        registration_ids = request.data.get('registration_ids', [])
        action = request.data.get('action')
        reason = request.data.get('reason', '')
        
        if not registration_ids or not action:
            return Response({'error': 'IDs and action required'}, status=400)
            
        successful = []
        failed = []
        
        for reg_id in registration_ids:
            try:
                registration = CourseRegistration.objects.get(
                    id=reg_id,
                    status='approved_lecturer',
                    is_payment_verified=True
                )
                if action == 'approve':
                    registration.approve_by_exam_officer(request.user)
                else:
                    registration.reject_by_exam_officer(request.user, reason)
                successful.append(reg_id)
            except Exception as e:
                failed.append({'id': reg_id, 'error': str(e)})
                
        return Response({
            'successful': successful,
            'failed': failed,
            'message': f'Processed {len(successful)} registrations'
        })


# ==============================================
# RESULT COMPILATION FOR EXAM OFFICER
# ==============================================

class ResultCompilationViewSet(viewsets.ViewSet):
    """Result compilation and verification for exam officer"""
    permission_classes = [IsAuthenticated, IsExamOfficer]
    
    @action(detail=False, methods=['get'])
    def courses_pending_results(self, request):
        """Get courses pending result compilation"""
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
             current_semester = Semester.objects.last()
        
        # ✅ FIX: Return empty list instead of 400 error if DB has no semester info
        if not current_semester: 
            return Response([])
        
        courses = Course.objects.filter(
            offerings__semester=current_semester,
            offerings__is_active=True
        ).distinct().select_related('department', 'lecturer__user')
        
        courses_data = []
        for course in courses:
            enrolled_count = Enrollment.objects.filter(
                course=course,
                session=current_semester.session,
                semester=current_semester.semester,
                status='enrolled'
            ).count()
            
            grades_entered = Grade.objects.filter(
                course=course,
                session=current_semester.session,
                semester=current_semester.semester
            ).count()
            
            completion_percentage = (grades_entered / enrolled_count * 100) if enrolled_count > 0 else 0
            
            courses_data.append({
                'id': course.id,
                'code': course.code,
                'title': course.title,
                'department': course.department.name,
                'lecturer': course.lecturer.user.get_full_name() if course.lecturer else 'Not assigned',
                'enrolled_students': enrolled_count,
                'grades_entered': grades_entered,
                'completion_percentage': round(completion_percentage, 1),
                'status': 'complete' if enrolled_count == grades_entered else 'pending'
            })
        
        return Response(courses_data)

    @action(detail=True, methods=['get'])
    def course_results_detail(self, request, pk=None):
        """Get detailed results for a specific course"""
        try:
            course = Course.objects.get(id=pk)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=404)
        
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
             current_semester = Semester.objects.last()
             if not current_semester:
                 return Response({'error': 'No academic session found'}, status=400)

        # Get grades
        grades = Grade.objects.filter(
            course=course,
            session=current_semester.session,
            semester=current_semester.semester
        ).select_related('student__user', 'uploaded_by__user')
        
        enrolled_students = Enrollment.objects.filter(
            course=course,
            session=current_semester.session,
            semester=current_semester.semester,
            status='enrolled'
        ).select_related('student__user')
        
        enrolled_without_grades = []
        for enrollment in enrolled_students:
            if not grades.filter(student=enrollment.student).exists():
                enrolled_without_grades.append({
                    'student_id': enrollment.student.id,
                    'matric_number': enrollment.student.matric_number,
                    'full_name': enrollment.student.user.get_full_name(),
                    'level': enrollment.student.level
                })
        
        grades_data = []
        scores = []
        for grade in grades:
             scores.append(float(grade.score))
             grades_data.append({
                'id': grade.id,
                'student': {
                    'id': grade.student.id,
                    'matric_number': grade.student.matric_number,
                    'full_name': grade.student.user.get_full_name(),
                    'level': grade.student.level
                },
                'score': grade.score,
                'grade_letter': grade.grade_letter,
                'grade_points': grade.grade_points,
                'uploaded_by': grade.uploaded_by.user.get_full_name() if grade.uploaded_by else None,
                'uploaded_at': grade.created_at,
                'remarks': grade.remarks,
                # Simple logic for needs review
                'needs_review': grade.score > 95 or grade.score < 30
            })

        # Calc stats
        stats = {
             'average_score': round(sum(scores) / len(scores), 2) if scores else 0,
             'highest_score': max(scores) if scores else 0,
             'lowest_score': min(scores) if scores else 0,
             'total_students': len(grades)
        }

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
            'statistics': stats,
            'grades': grades_data,
            'students_without_grades': enrolled_without_grades,
            'total_students': len(grades_data) + len(enrolled_without_grades),
            'completion_rate': (len(grades_data) / (len(grades_data) + len(enrolled_without_grades)) * 100) if (len(grades_data) + len(enrolled_without_grades)) > 0 else 0
        })

    @action(detail=True, methods=['post'])
    def verify_course_results(self, request, pk=None):
        """Verify and approve course results"""
        try:
            course = Course.objects.get(id=pk)
        except Course.DoesNotExist:
            return Response({'error': 'Course not found'}, status=404)
        
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
             current_semester = Semester.objects.last()
             if not current_semester:
                 return Response({'error': 'No academic session found'}, status=400)
        
        # Check if any grades exist at all
        all_grades = Grade.objects.filter(
            course=course,
            session=current_semester.session,
            semester=current_semester.semester
        )
        
        if not all_grades.exists():
             return Response({'error': 'No grades found for this course in the current semester'}, status=400)

        # Check for verify-ready grades
        # HOD approved grades are ready for verification
        # We also allow 'submitted' directly if strict HOD flow isn't enforced or for fallback
        pending_grades = all_grades.filter(
            status__in=['hod_approved', 'submitted']
        )
        
        if not pending_grades.exists():
             # Analyze why
             if all_grades.filter(status='draft').exists():
                 return Response({'error': 'Grades are still in Draft mode. Lecturer/HOD must submit/approve them.'}, status=400)
             if all_grades.filter(status='verified').exists():
                 return Response({'message': 'Grades are already verified.', 'verified_count': all_grades.count()})
             if all_grades.filter(status='published').exists():
                 return Response({'message': 'Grades are already published.', 'verified_count': all_grades.count()})
                 
             return Response({'error': 'No grades pending verification for this course'}, status=400)
             
        # Update status
        count = pending_grades.update(status='verified')
        
        return Response({
            'message': f'Successfully verified {count} grades for {course.code}',
            'verified_count': count
        })

    @action(detail=True, methods=['get'])
    def generate_master_sheet(self, request, pk=None):
        """Generate master sheet for a course"""
        try:
            course = Course.objects.get(id=pk)
        except Course.DoesNotExist:
            return Response(
                {'error': 'Course not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
             current_semester = Semester.objects.last()
             if not current_semester:
                return Response(
                    {'error': 'No current semester set'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        
        # Get all grades for this course
        grades = Grade.objects.filter(
            course=course,
            session=current_semester.session,
            semester=current_semester.semester
        ).select_related('student__user').order_by('student__matric_number')
        
        # Create DataFrame for Excel export
        data = []
        for grade in grades:
            data.append({
                'S/N': len(data) + 1,
                'Matric Number': grade.student.matric_number,
                'Student Name': grade.student.user.get_full_name(),
                'Score': float(grade.score),
                'Grade': grade.grade_letter,
                'Grade Points': float(grade.grade_points),
                'Remarks': grade.remarks or ''
            })
        
        # Create Excel file in memory
        df = pd.DataFrame(data)
        
        # Create a BytesIO buffer
        output = BytesIO()
        
        # Use ExcelWriter to write to buffer
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Master Sheet', index=False)
            
            # Auto-adjust column widths
            worksheet = writer.sheets['Master Sheet']
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
        response['Content-Disposition'] = f'attachment; filename="{course.code}_Master_Sheet_{current_semester.session}.xlsx"'
        
        return response


class ExamListViewSet(viewsets.ViewSet):
    """Exam list generation for eligible students"""
    permission_classes = [IsAuthenticated, IsExamOfficer]
    
    @action(detail=False, methods=['get'])
    def eligible_students(self, request):
        """Get list of eligible students for exams"""
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
             current_semester = Semester.objects.last()
        
        if not current_semester:
            return Response(
                {'error': 'No current semester set'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get all registered students for current semester
        # ✅ Updated Model
        registrations = CourseRegistration.objects.filter(
            course_offering__semester=current_semester,
            status='registered'
        ).select_related('student__user', 'student__department')
        
        # Group by student
        student_courses = {}
        for registration in registrations:
            student_id = registration.student.id
            if student_id not in student_courses:
                student_courses[student_id] = {
                    'student': registration.student,
                    'courses': []
                }
            student_courses[student_id]['courses'].append(registration.course_offering.course)
        
        # Check eligibility for each student
        eligible_students = []
        ineligible_students = []
        
        for student_id, data in student_courses.items():
            student = data['student']
            courses = data['courses']
            
            # Check eligibility criteria
            is_eligible = self._check_exam_eligibility(student, courses, current_semester)
            
            student_data = {
                'id': student.id,
                'matric_number': student.matric_number,
                'full_name': student.user.get_full_name(),
                'level': student.level,
                'department': student.department.name,
                'registered_courses': len(courses),
                'total_credits': sum(c.credits for c in courses)
            }
            
            if is_eligible['eligible']:
                student_data['eligibility_status'] = 'eligible'
                student_data['eligibility_reasons'] = is_eligible['reasons']
                eligible_students.append(student_data)
            else:
                student_data['eligibility_status'] = 'ineligible'
                student_data['eligibility_reasons'] = is_eligible['reasons']
                ineligible_students.append(student_data)
        
        return Response({
            'total_students': len(student_courses),
            'eligible_students': len(eligible_students),
            'ineligible_students': len(ineligible_students),
            'eligible_students_list': eligible_students,
            'ineligible_students_list': ineligible_students
        })
    
    def _check_exam_eligibility(self, student, courses, semester):
        """Check if student is eligible for exams"""
        reasons = []
        
        # Check 1: Minimum course registration (at least 4 courses)
        if len(courses) < 4:
            reasons.append(f'Registered for only {len(courses)} courses (minimum 4 required)')
        
        # Check 2: No outstanding fees (placeholder - integrate with finance system)
        has_outstanding_fees = False  # Implement this check
        if has_outstanding_fees:
            reasons.append('Has outstanding fees')
        
        # Check 3: Attendance requirement (placeholder)
        # Should check attendance for each registered course
        
        # Check 4: No academic probation
        cgpa = self._calculate_student_cgpa(student)
        if cgpa < 1.5:  # Example threshold
            reasons.append(f'CGPA ({cgpa}) below minimum requirement (1.5)')
        
        # Check 5: Course prerequisites met (already checked during registration)
        
        eligible = len(reasons) == 0
        
        return {
            'eligible': eligible,
            'reasons': reasons
        }
    
    def _calculate_student_cgpa(self, student):
        """Calculate student's CGPA"""
        grades = Grade.objects.filter(student=student)
        if not grades.exists():
            return 0.0
        
        total_points = sum(float(g.grade_points) * g.course.credits for g in grades)
        total_credits = sum(g.course.credits for g in grades)
        
        return round(total_points / total_credits, 2) if total_credits > 0 else 0.0
    
    @action(detail=False, methods=['get'])
    def generate_exam_list(self, request):
        """Generate exam list for all eligible students"""
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
             current_semester = Semester.objects.last()
        
        if not current_semester:
            return Response(
                {'error': 'No current semester set'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get department filter
        department_id = request.query_params.get('department_id')
        
        # Get all registered students
        # ✅ Updated Model
        registrations = CourseRegistration.objects.filter(
            course_offering__semester=current_semester,
            status='registered'
        )
        
        if department_id:
            registrations = registrations.filter(
                student__department_id=department_id
            )
        
        registrations = registrations.select_related(
            'student__user', 
            'student__department',
            'course_offering__course'
        )
        
        # Group by student and course
        exam_list = {}
        for registration in registrations:
            student = registration.student
            course = registration.course_offering.course
            
            if student.id not in exam_list:
                exam_list[student.id] = {
                    'student': {
                        'id': student.id,
                        'matric_number': student.matric_number,
                        'full_name': student.user.get_full_name(),
                        'level': student.level,
                        'department': student.department.name
                    },
                    'courses': []
                }
            
            exam_list[student.id]['courses'].append({
                'course_code': course.code,
                'course_title': course.title,
                'credits': course.credits,
                'department': course.department.name
            })
        
        # Convert to list
        exam_list_data = list(exam_list.values())
        
        # Sort by matric number
        exam_list_data.sort(key=lambda x: x['student']['matric_number'])
        
        return Response({
            'semester': {
                'session': current_semester.session,
                'semester': current_semester.get_semester_display()
            },
            'total_students': len(exam_list_data),
            'total_courses_registered': sum(len(s['courses']) for s in exam_list_data),
            'exam_list': exam_list_data
        })
    
    @action(detail=False, methods=['get'])
    def download_exam_list(self, request):
        """Download exam list as Excel file"""
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
             current_semester = Semester.objects.last()
        
        if not current_semester:
            return Response(
                {'error': 'No current semester set'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get exam list data
        response = self.generate_exam_list(request)
        if isinstance(response, Response) and response.status_code != 200:
            return response
        
        exam_list_data = response.data['exam_list']
        
        # Prepare data for Excel
        data = []
        for student_data in exam_list_data:
            student = student_data['student']
            courses = student_data['courses']
            
            for i, course in enumerate(courses):
                data.append({
                    'S/N': len(data) + 1,
                    'Matric Number': student['matric_number'],
                    'Student Name': student['full_name'],
                    'Level': student['level'],
                    'Department': student['department'],
                    'Course Code': course['course_code'],
                    'Course Title': course['course_title'],
                    'Credits': course['credits']
                })
        
        # Create DataFrame
        df = pd.DataFrame(data)
        
        # Create Excel file in memory
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Exam List', index=False)
            
            # Auto-adjust column widths
            worksheet = writer.sheets['Exam List']
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
        response['Content-Disposition'] = f'attachment; filename="Exam_List_{current_semester.session}.xlsx"'
        
        return response

# ==============================================
# EXAM TIMETABLE MANAGEMENT
# ==============================================

class ExamTimetableViewSet(viewsets.ViewSet):
    """Exam timetable management"""
    permission_classes = [IsAuthenticated, IsExamOfficer]
    
    @action(detail=False, methods=['get'])
    def current_timetable(self, request):
        """Get current exam timetable"""
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            return Response(
                {'error': 'No current semester set'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # This would come from your ExamTimetable model
        # For now, return placeholder data
        
        # Get all courses in current semester
        courses = Course.objects.filter(
            offerings__semester=current_semester,
            offerings__is_active=True
        ).distinct().select_related('department')
        
        # Generate placeholder timetable (in real system, this would come from a model)
        timetable = []
        exam_date = current_semester.end_date - timedelta(weeks=2)  # Exams start 2 weeks before semester end
        
        for i, course in enumerate(courses[:10]):  # Limit to 10 courses for example
            exam_date_calc = exam_date + timedelta(days=i)
            timetable.append({
                'id': i + 1,
                'course_code': course.code,
                'course_title': course.title,
                'department': course.department.name,
                'exam_date': exam_date_calc,
                'exam_time': '9:00 AM' if i % 2 == 0 else '2:00 PM',
                'venue': f'Exam Hall {chr(65 + (i % 5))}',  # A, B, C, D, E
                'duration': '3 hours',
                'status': 'scheduled'
            })
        
        return Response({
            'semester': {
                'session': current_semester.session,
                'semester': current_semester.get_semester_display(),
                'exam_period': f'{exam_date} to {exam_date + timedelta(days=len(timetable))}'
            },
            'timetable': timetable,
            'statistics': {
                'total_exams': len(timetable),
                'exams_scheduled': len([t for t in timetable if t['status'] == 'scheduled']),
                'exams_pending': len([t for t in timetable if t['status'] == 'pending']),
                'exam_days': len(set(t['exam_date'] for t in timetable))
            }
        })
    
    @action(detail=False, methods=['post'])
    def generate_timetable(self, request):
        """Generate exam timetable automatically"""
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            return Response(
                {'error': 'No current semester set'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get all courses in current semester
        courses = Course.objects.filter(
            offerings__semester=current_semester,
            offerings__is_active=True
        ).distinct().select_related('department')
        
        # Get exam period parameters
        exam_start_date = request.data.get('exam_start_date')
        exam_end_date = request.data.get('exam_end_date')
        exams_per_day = request.data.get('exams_per_day', 2)  # Morning and afternoon
        
        if not exam_start_date or not exam_end_date:
            return Response(
                {'error': 'exam_start_date and exam_end_date are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            start_date = datetime.strptime(exam_start_date, '%Y-%m-%d').date()
            end_date = datetime.strptime(exam_end_date, '%Y-%m-%d').date()
        except ValueError:
            return Response(
                {'error': 'Dates must be in YYYY-MM-DD format'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Calculate available exam days
        exam_days = []
        current_date = start_date
        while current_date <= end_date:
            # Skip weekends (adjust based on your institution)
            if current_date.weekday() < 5:  # Monday to Friday
                exam_days.append(current_date)
            current_date += timedelta(days=1)
        
        # Check if we have enough days
        total_exam_slots = len(exam_days) * exams_per_day
        if total_exam_slots < courses.count():
            return Response(
                {'error': f'Not enough exam slots. Need {courses.count()} slots but only {total_exam_slots} available'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Generate timetable (simple algorithm - in real system, use more sophisticated scheduling)
        timetable = []
        course_index = 0
        
        for day_index, exam_date in enumerate(exam_days):
            for slot in range(exams_per_day):
                if course_index >= courses.count():
                    break
                
                course = courses[course_index]
                exam_time = '9:00 AM' if slot == 0 else '2:00 PM'
                venue = self._assign_venue(course, day_index, slot)
                
                timetable.append({
                    'course_id': course.id,
                    'course_code': course.code,
                    'course_title': course.title,
                    'department': course.department.name,
                    'exam_date': exam_date,
                    'exam_time': exam_time,
                    'venue': venue,
                    'duration': '3 hours',
                    'status': 'generated'
                })
                
                course_index += 1
        
        return Response({
            'message': f'Generated timetable for {len(timetable)} courses',
            'exam_period': {
                'start_date': start_date,
                'end_date': end_date,
                'total_days': len(exam_days),
                'total_slots': total_exam_slots
            },
            'timetable': timetable
        })
    
    def _assign_venue(self, course, day_index, slot):
        """Assign venue for exam (simplified)"""
        # In real system, consider:
        # 1. Number of students in course
        # 2. Available venues and capacities
        # 3. Department preferences
        # 4. Venue conflicts
        
        # Simple assignment for now
        venues = ['Exam Hall A', 'Exam Hall B', 'Exam Hall C', 'LT 1', 'LT 2']
        venue_index = (day_index + slot) % len(venues)
        return venues[venue_index]
    
    @action(detail=False, methods=['post'])
    def publish_timetable(self, request):
        """Publish exam timetable"""
        timetable_data = request.data.get('timetable', [])
        
        if not timetable_data:
            return Response(
                {'error': 'Timetable data is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # In real system, save to ExamTimetable model
        # For now, just return success
        
        return Response({
            'message': f'Published timetable with {len(timetable_data)} exams',
            'published_date': timezone.now().date(),
            'total_exams': len(timetable_data)
        })


# ==============================================
# MAIN EXAM OFFICER API VIEW
# ==============================================

class ExamOfficerAPIView(APIView):
    """Main API view for exam officer frontend integration"""
    permission_classes = [IsAuthenticated, IsExamOfficer]
    
    def get(self, request):
        """Get exam officer's complete data for dashboard"""
        user = request.user
        
        # Get exam officer profile
        exam_officer_data = {
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
            # ✅ Updated Model
            'pending_registrations': CourseRegistration.objects.filter(
                status='approved_lecturer',
                is_payment_verified=True
            ).count() if current_semester else 0,
            'courses_pending_results': Course.objects.filter(
                offerings__semester=current_semester,
                offerings__is_active=True
            ).distinct().count() if current_semester else 0,
            'total_departments': Department.objects.count(),
            'total_students': Student.objects.count()
        }
        
        return Response({
            'exam_officer': exam_officer_data,
            'current_semester': {
                'id': current_semester.id if current_semester else None,
                'session': current_semester.session if current_semester else None,
                'semester': current_semester.semester if current_semester else None
            },
            'quick_stats': quick_stats
        })