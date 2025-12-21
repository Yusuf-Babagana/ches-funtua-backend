from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Avg, Case, When, IntegerField
from django.db import transaction
from django.utils import timezone

from .models import Grade, Course, Semester, Department
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
        
        # Find courses in this department that have 'submitted' grades
        courses = Course.objects.filter(
            department=department,
            grades__status='submitted',
            grades__session=semester.session,
            grades__semester=semester.semester
        ).distinct()
        
        data = self._get_course_stats(courses, 'submitted')
        return Response(data)

    @action(detail=False, methods=['post'])
    @transaction.atomic
    def process_result(self, request):
        """Approve or Reject results for a specific course"""
        serializer = ResultWorkflowActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)
            
        course_id = serializer.validated_data['course_id']
        action = serializer.validated_data['action']
        remark = serializer.validated_data.get('remark', '')
        
        semester = self._get_current_semester()
        
        # Get grades
        grades = Grade.objects.filter(
            course_id=course_id,
            status='submitted',
            session=semester.session,
            semester=semester.semester
        )
        
        if not grades.exists():
            return Response({'error': 'No pending grades found for this course'}, status=404)
            
        count = grades.count()
        
        if action == 'approve':
            grades.update(status='hod_approved', remarks=remark)
            return Response({'message': f'Approved {count} grades for Exam Officer review.'})
        
        elif action == 'reject':
            # Return to lecturer
            grades.update(status='draft', remarks=f"Rejected by HOD: {remark}")
            return Response({'message': f'Rejected {count} grades. Returned to lecturer.'})


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
        
        # Find all courses with hod_approved grades
        courses = Course.objects.filter(
            grades__status='hod_approved',
            grades__session=semester.session,
            grades__semester=semester.semester
        ).distinct()
        
        data = self._get_course_stats(courses, 'hod_approved')
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
            status='hod_approved',
            session=semester.session,
            semester=semester.semester
        )
        
        if not grades.exists():
            return Response({'error': 'No pending grades found for this course'}, status=404)
            
        count = grades.count()
        
        if action == 'approve':
            grades.update(status='verified', remarks=remark)
            return Response({'message': f'Verified {count} grades. Ready for Publication.'})
        
        elif action == 'reject':
            # Hard Reject back to draft (Lecturer has to fix)
            grades.update(status='draft', remarks=f"Rejected by Exam Officer: {remark}")
            return Response({'message': f'Rejected {count} grades. Returned to draft.'})


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
            grades.update(status='published', is_published=True, remarks=remark)
            return Response({'message': f'SUCCESS! {count} grades have been PUBLISHED to students.'})
        
        elif action == 'reject':
            grades.update(status='draft', remarks=f"Rejected by Registrar: {remark}")
            return Response({'message': f'Rejected {count} grades. Returned to draft.'})