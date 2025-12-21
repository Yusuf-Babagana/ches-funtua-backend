from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Avg, Case, When, IntegerField
from django.db import transaction
from django.utils import timezone

from .models import Grade, Course, Semester, Department, StudentAcademicRecord
from .serializers_results import (
    ResultWorkflowActionSerializer, 
    CourseResultSummarySerializer, 
    GradeWorkflowDetailSerializer
)
from users.permissions import IsHOD, IsExamOfficer, IsRegistrar, IsSuperAdmin

class BaseResultWorkflowViewSet(viewsets.ViewSet):
    """
    Base helper class for result workflow logic.
    """
    
    def _get_current_semester(self):
        semester = Semester.objects.filter(is_current=True).first()
        if not semester:
            semester = Semester.objects.last() # Fallback for testing
        return semester

    def _get_course_stats(self, courses, status_filter):
        """
        Annotates courses with grade statistics for the specific status.
        """
        semester = self._get_current_semester()
        
        if not semester:
            return []

        # We manually aggregate because simple annotations usually fail with distinct Grade filtering logic
        course_ids = [c.id for c in courses]
        
        grades = Grade.objects.filter(
            course_id__in=course_ids,
            session=semester.session,
            semester=semester.semester,
            status=status_filter
        )

        stats = {}
        for grade in grades:
            cid = grade.course_id
            if cid not in stats:
                stats[cid] = {'total': 0, 'passed': 0, 'failed': 0, 'scores': []}
            
            stats[cid]['total'] += 1
            stats[cid]['scores'].append(grade.score)
            
            if grade.grade_letter == 'F':
                stats[cid]['failed'] += 1
            else:
                stats[cid]['passed'] += 1

        results = []
        for course in courses:
            data = stats.get(course.id, {'total': 0, 'passed': 0, 'failed': 0, 'scores': []})
            if data['total'] > 0:
                avg = sum(data['scores']) / data['total']
                
                # Create a serializer instance with context
                serializer = CourseResultSummarySerializer(course, context={'status_summary': status_filter})
                serialized_data = serializer.data
                
                # Inject calculated stats
                serialized_data['total_students'] = data['total']
                serialized_data['passed_count'] = data['passed']
                serialized_data['failed_count'] = data['failed']
                serialized_data['average_score'] = round(avg, 2)
                
                results.append(serialized_data)
                
        return results

    def _update_student_academic_records(self, course, semester):
        """
        Updates or creates StudentAcademicRecord for all students in the course.
        Calculates GPA based on all PUBLISHED grades for the student in this semester.
        """
        # Find all students who have a grade in this course for this semester
        grades = Grade.objects.filter(
            course=course,
            session=semester.session,
            semester=semester.semester,
            status='published'
        ).select_related('student')

        students_to_update = set(grade.student for grade in grades)

        for student in students_to_update:
            # Recalculate GPA for this student/semester
            student_grades = Grade.objects.filter(
                student=student,
                session=semester.session,
                semester=semester.semester,
                status='published'
            )

            total_points = 0
            total_credits = 0

            for g in student_grades:
                credits = g.course.credits
                points = float(g.grade_points)
                total_points += (points * credits)
                total_credits += credits
            
            gpa = round(total_points / total_credits, 2) if total_credits > 0 else 0.0

            # Update or Create Record
            record, created = StudentAcademicRecord.objects.get_or_create(
                student=student,
                session=semester.session,
                semester=semester.semester,
                defaults={
                    'level': student.level,
                    'total_credits': total_credits,
                    'total_grade_points': total_points,
                    'gpa': gpa,
                    'cgpa': 0.0 # Placeholder, usually calculated sequentially
                }
            )

            if not created:
                record.total_credits = total_credits
                record.total_grade_points = total_points
                record.gpa = gpa
                record.save()
            
            # Simple CGPA calculation (Average of all semester GPAs - simplified)
            # In a real system, you'd sum all historical points / all historical credits
            all_records = StudentAcademicRecord.objects.filter(student=student)
            if all_records.exists():
                cumulative_points = sum(r.total_grade_points for r in all_records)
                cumulative_credits = sum(r.total_credits for r in all_records)
                cgpa = round(cumulative_points / cumulative_credits, 2) if cumulative_credits > 0 else 0.0
                
                # Update current record's CGPA
                record.cgpa = cgpa
                record.save()


# ==========================================
# 1. HOD VIEWSET
# ==========================================
class HODResultWorkflowViewSet(BaseResultWorkflowViewSet):
    """
    HODs see grades that are 'submitted'.
    Actions: Approve (-> hod_approved) or Reject (-> draft).
    """
    permission_classes = [IsAuthenticated, IsHOD]

    def list(self, request):
        """
        Handle GET requests to the root endpoint (e.g. /api/.../results/)
        Maps directly to pending_reviews logic.
        """
        return self.pending_reviews(request)

    @action(detail=False, methods=['get'])
    def pending_reviews(self, request):
        """List courses waiting for HOD approval"""
        if not hasattr(request.user, 'lecturer_profile'):
            return Response({'error': 'Not an HOD'}, status=403)
            
        department = request.user.lecturer_profile.department
        semester = self._get_current_semester()
        
        if not semester:
             return Response([])

        # Find courses in this department that have 'submitted' grades
        courses = Course.objects.filter(
            department=department,
            grades__status='submitted',
            grades__session=semester.session,
            grades__semester=semester.semester
        ).distinct()
        
        data = self._get_course_stats(courses, 'submitted')
        return Response(data)
    
    @action(detail=True, methods=['get'])
    def course_details(self, request, pk=None):
        """Get detailed grade list for review popup"""
        semester = self._get_current_semester()
        try:
            course = Course.objects.get(pk=pk)
            grades = Grade.objects.filter(
                course=course,
                status='submitted',
                session=semester.session,
                semester=semester.semester
            ).select_related('student__user')
            
            # Manually serialize for the popup table
            grades_data = []
            for g in grades:
                grades_data.append({
                    'grade_id': g.id,
                    'student_name': g.student.user.get_full_name(),
                    'matric': g.student.matric_number,
                    'total': g.score,
                    'grade': g.grade_letter,
                    'remarks': g.remarks
                })
                
            return Response({
                'course_code': course.code,
                'grades': grades_data
            })
        except Course.DoesNotExist:
             return Response({'error': 'Course not found'}, status=404)


    @action(detail=False, methods=['post'])
    @transaction.atomic
    def approve(self, request):
        """Approve results for a specific course"""
        course_id = request.data.get('course_id')
        if not course_id:
             return Response({'error': 'course_id required'}, status=400)

        semester = self._get_current_semester()
        
        grades = Grade.objects.filter(
            course_id=course_id,
            status='submitted',
            session=semester.session,
            semester=semester.semester
        )
        
        count = grades.count()
        if count == 0:
            return Response({'message': 'No pending grades found'}, status=404)
            
        grades.update(status='hod_approved')
        return Response({'message': f'Approved {count} grades'})

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def reject(self, request):
        """Reject results"""
        course_id = request.data.get('course_id')
        reason = request.data.get('reason', 'Rejected by HOD')
        
        semester = self._get_current_semester()
        
        grades = Grade.objects.filter(
            course_id=course_id,
            status='submitted',
            session=semester.session,
            semester=semester.semester
        )
        
        count = grades.count()
        grades.update(status='draft', remarks=f"HOD Rejection: {reason}")
        
        return Response({'message': f'Rejected {count} grades'})


# ==========================================
# 2. EXAM OFFICER VIEWSET
# ==========================================
class ExamOfficerResultWorkflowViewSet(BaseResultWorkflowViewSet):
    """
    Exam Officers see grades that are 'hod_approved'.
    Actions: Verify (-> verified) or Reject (-> draft).
    """
    permission_classes = [IsAuthenticated, IsExamOfficer]

    def list(self, request):
        """Handle GET requests to root endpoint"""
        return self.pending_verification(request)

    @action(detail=False, methods=['get'])
    def pending_verification(self, request):
        """List courses waiting for verification"""
        semester = self._get_current_semester()
        if not semester: return Response([])
        
        courses = Course.objects.filter(
            grades__status='hod_approved',
            grades__session=semester.session,
            grades__semester=semester.semester
        ).distinct()
        
        data = self._get_course_stats(courses, 'hod_approved')
        return Response(data)

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def verify(self, request):
        course_id = request.data.get('course_id')
        semester = self._get_current_semester()
        
        grades = Grade.objects.filter(
            course_id=course_id,
            status='hod_approved',
            session=semester.session,
            semester=semester.semester
        )
        
        grades.update(status='verified')
        return Response({'message': 'Verified grades successfully'})


# ==========================================
# 3. REGISTRAR VIEWSET
# ==========================================
class RegistrarResultWorkflowViewSet(BaseResultWorkflowViewSet):
    """
    Registrar sees grades that are 'verified'.
    Actions: Publish (-> published, is_published=True).
    """
    permission_classes = [IsAuthenticated, IsRegistrar]

    def list(self, request):
        """Handle GET requests to root endpoint"""
        return self.pending_publication(request)

    @action(detail=False, methods=['get'])
    def pending_publication(self, request):
        """List courses ready to be published"""
        semester = self._get_current_semester()
        if not semester: return Response([])
        
        courses = Course.objects.filter(
            grades__status='verified',
            grades__session=semester.session,
            grades__semester=semester.semester
        ).distinct()
        
        data = self._get_course_stats(courses, 'verified')
        return Response(data)

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def process_result(self, request):
        serializer = ResultWorkflowActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
            
        course_id = serializer.validated_data['course_id']
        action = serializer.validated_data['action']
        remark = serializer.validated_data.get('remark', '')
        
        semester = self._get_current_semester()
        
        grades = Grade.objects.filter(
            course_id=course_id,
            status='verified',
            session=semester.session,
            semester=semester.semester
        )
        
        if not grades.exists():
            return Response({'error': 'No verifiable grades found for this course'}, status=404)
            
        count = grades.count()
        
        if action == 'approve':
            # THIS IS THE FINAL STEP
            grades.update(status='published', remarks=remark)
            
            # ✅ TRIGGER GPA CALCULATION
            course = Course.objects.get(id=course_id)
            self._update_student_academic_records(course, semester)
            
            return Response({'message': f'SUCCESS! {count} grades have been PUBLISHED to students.'})
        
        elif action == 'reject':
            grades.update(status='draft', remarks=f"Rejected by Registrar: {remark}")
            return Response({'message': f'Rejected {count} grades. Returned to draft.'})
    
    @action(detail=False, methods=['post'])
    @transaction.atomic
    def publish(self, request):
        """
        Simplified publish action matching frontend workflowAPI call
        """
        course_id = request.data.get('course_id')
        if not course_id:
            return Response({'error': 'course_id required'}, status=400)

        semester = self._get_current_semester()
        
        grades = Grade.objects.filter(
            course_id=course_id,
            status='verified',
            session=semester.session,
            semester=semester.semester
        )
        
        if not grades.exists():
             return Response({'error': 'No verified grades found'}, status=404)

        # FINAL STEP: visible to student
        grades.update(status='published')
        
        # ✅ TRIGGER GPA CALCULATION
        course = Course.objects.get(id=course_id)
        self._update_student_academic_records(course, semester)
        
        return Response({'message': 'Published grades to students'})