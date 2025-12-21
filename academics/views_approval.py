# academics/views_approval.py
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django.utils import timezone

# ✅ Updated Imports
from .models import CourseRegistration, CourseOffering, Semester
from .serializers_approval import (
    RegistrationApprovalSerializer, 
    RegistrationApprovalActionSerializer,
    RegistrationPaymentVerificationSerializer
)
from users.permissions import IsLecturer, IsStudent, CanManageFinance
from users.models import User
from finance.models import Invoice

class RegistrationApprovalViewSet(viewsets.ViewSet):
    """Registration approval endpoints for lecturers and exam officers"""
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Get registrations based on user role"""
        user = self.request.user
        
        if user.role == 'lecturer':
            # Lecturer sees registrations for their courses
            # ✅ Updated Model
            return CourseRegistration.objects.filter(
                course_offering__lecturer__user=user
            ).select_related(
                'student__user',
                'course_offering__course',
                'course_offering__lecturer__user',
                'approved_by_lecturer',
                'approved_by_exam_officer'
            )
        
        elif user.role == 'exam-officer':
            # Exam officer sees all pending registrations
            return CourseRegistration.objects.filter(
                status='approved_lecturer',
                is_payment_verified=True
            ).select_related(
                'student__user',
                'course_offering__course',
                'course_offering__lecturer__user',
                'approved_by_lecturer',
                'approved_by_exam_officer'
            )
        
        elif user.role == 'bursar' or user.role == 'desk-officer':
            # Finance staff sees registrations needing payment verification
            return CourseRegistration.objects.filter(
                is_payment_verified=False
            ).select_related(
                'student__user',
                'course_offering__course'
            )
        
        return CourseRegistration.objects.none()
    
    @action(detail=False, methods=['get'])
    def pending_approvals(self, request):
        """Get pending approvals for the current user"""
        user = request.user
        registrations = self.get_queryset()
        
        if user.role == 'lecturer':
            registrations = registrations.filter(
                Q(status='pending') | Q(status='approved_lecturer')
            )
        elif user.role == 'exam-officer':
            registrations = registrations.filter(status='approved_lecturer')
        elif user.role in ['bursar', 'desk-officer']:
            registrations = registrations.filter(is_payment_verified=False)
        
        serializer = RegistrationApprovalSerializer(registrations, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def lecturer_approval(self, request, pk=None):
        """Lecturer approval/rejection of registration"""
        if request.user.role != 'lecturer':
            return Response(
                {'error': 'Only lecturers can perform this action'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            # ✅ Updated Model
            registration = CourseRegistration.objects.get(
                id=pk,
                course_offering__lecturer__user=request.user
            )
        except CourseRegistration.DoesNotExist:
            return Response(
                {'error': 'Registration not found or you are not the course lecturer'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = RegistrationApprovalActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        action = serializer.validated_data['action']
        reason = serializer.validated_data.get('reason', '')
        
        if action == 'approve':
            if registration.approve_by_lecturer(request.user.lecturer_profile):
                return Response({
                    'message': 'Registration approved by lecturer',
                    'registration': RegistrationApprovalSerializer(registration).data
                })
            else:
                return Response(
                    {'error': 'Cannot approve this registration'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:  # reject
            if registration.reject_by_lecturer(request.user.lecturer_profile, reason):
                return Response({
                    'message': 'Registration rejected by lecturer',
                    'registration': RegistrationApprovalSerializer(registration).data
                })
            else:
                return Response(
                    {'error': 'Cannot reject this registration'},
                    status=status.HTTP_400_BAD_REQUEST
                )
    
    @action(detail=True, methods=['post'])
    def exam_officer_approval(self, request, pk=None):
        """Exam officer approval/rejection of registration"""
        if request.user.role != 'exam-officer':
            return Response(
                {'error': 'Only exam officers can perform this action'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            # ✅ Updated Model
            registration = CourseRegistration.objects.get(
                id=pk,
                status='approved_lecturer',
                is_payment_verified=True
            )
        except CourseRegistration.DoesNotExist:
            return Response(
                {'error': 'Registration not found or not ready for exam officer approval'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = RegistrationApprovalActionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        action = serializer.validated_data['action']
        reason = serializer.validated_data.get('reason', '')
        
        if action == 'approve':
            if registration.approve_by_exam_officer(request.user):
                return Response({
                    'message': 'Registration approved by exam officer',
                    'registration': RegistrationApprovalSerializer(registration).data
                })
            else:
                return Response(
                    {'error': 'Cannot approve this registration'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:  # reject
            if registration.reject_by_exam_officer(request.user, reason):
                return Response({
                    'message': 'Registration rejected by exam officer',
                    'registration': RegistrationApprovalSerializer(registration).data
                })
            else:
                return Response(
                    {'error': 'Cannot reject this registration'},
                    status=status.HTTP_400_BAD_REQUEST
                )
    
    @action(detail=True, methods=['post'])
    def verify_payment(self, request, pk=None):
        """Verify payment for registration (by bursar/desk officer)"""
        if request.user.role not in ['bursar', 'desk-officer']:
            return Response(
                {'error': 'Only finance staff can verify payments'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        try:
            # ✅ Updated Model
            registration = CourseRegistration.objects.get(
                id=pk,
                is_payment_verified=False
            )
        except CourseRegistration.DoesNotExist:
            return Response(
                {'error': 'Registration not found or payment already verified'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Verify payment by checking invoice directly
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            return Response(
                {'error': 'No current semester set'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Import here to avoid circular import
        from finance.models import Invoice
        
        try:
            invoice = Invoice.objects.get(
                student=registration.student,
                session=current_semester.session,
                semester=current_semester.semester,
                status='paid'
            )
            
            if invoice.is_tuition_paid():
                registration.is_payment_verified = True
                registration.payment_verified_by = request.user
                registration.payment_verified_date = timezone.now()
                registration.save()
                
                return Response({
                    'message': 'Payment verified successfully',
                    'registration': RegistrationApprovalSerializer(registration).data
                })
            else:
                return Response(
                    {'error': 'Invoice exists but tuition not fully paid'},
                    status=status.HTTP_400_BAD_REQUEST
                )
                
        except Invoice.DoesNotExist:
            return Response(
                {'error': 'No paid invoice found for current semester'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['get'])
    def student_registrations(self, request):
        """Get student's own registrations"""
        if request.user.role != 'student' or not hasattr(request.user, 'student_profile'):
            return Response(
                {'error': 'Only students can access this endpoint'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        student = request.user.student_profile
        # ✅ Updated Model
        registrations = CourseRegistration.objects.filter(
            student=student
        ).select_related(
            'course_offering__course',
            'course_offering__lecturer__user',
            'approved_by_lecturer',
            'approved_by_exam_officer'
        )
        
        serializer = RegistrationApprovalSerializer(registrations, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def registration_stats(self, request):
        """Get registration statistics"""
        user = request.user
        current_semester = Semester.objects.filter(is_current=True).first()
        
        if not current_semester:
            return Response({'error': 'No current semester'}, status=status.HTTP_400_BAD_REQUEST)
        
        stats = {}
        
        if user.role == 'lecturer':
            # ✅ Updated Model
            registrations = CourseRegistration.objects.filter(
                course_offering__lecturer__user=user,
                course_offering__semester=current_semester
            )
            
            stats = {
                'total': registrations.count(),
                'pending': registrations.filter(status='pending').count(),
                'approved': registrations.filter(status='approved_lecturer').count(),
                'rejected': registrations.filter(status='rejected_lecturer').count(),
                'registered': registrations.filter(status='registered').count(),
            }
        
        elif user.role == 'exam-officer':
            # ✅ Updated Model
            registrations = CourseRegistration.objects.filter(
                course_offering__semester=current_semester,
                status='approved_lecturer',
                is_payment_verified=True
            )
            
            stats = {
                'awaiting_approval': registrations.count(),
                'approved_today': CourseRegistration.objects.filter( # ✅ Updated
                    course_offering__semester=current_semester,
                    status='registered',
                    approved_date__date=timezone.now().date()
                ).count(),
            }
        
        elif user.role in ['bursar', 'desk-officer']:
            # ✅ Updated Model
            registrations = CourseRegistration.objects.filter(
                course_offering__semester=current_semester,
                is_payment_verified=False
            )
            
            stats = {
                'awaiting_payment_verification': registrations.count(),
                'verified_today': CourseRegistration.objects.filter( # ✅ Updated
                    course_offering__semester=current_semester,
                    payment_verified_date__date=timezone.now().date()
                ).count(),
            }
        
        return Response(stats)