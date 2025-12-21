import requests
from django.conf import settings
from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend

# Models
from .models import (
    FeeStructure, 
    Invoice, 
    Payment, 
    PaymentReceipt, 
    PaystackTransaction
)
from academics.models import Semester

# Serializers
from .serializers import (
    FeeStructureSerializer, 
    InvoiceSerializer, 
    PaymentSerializer,
    PaymentCreateSerializer, 
    PaymentReceiptSerializer, 
    PaystackInitializeSerializer,
    StudentFeeSummarySerializer, 
    PaymentSummarySerializer
)

# Permissions, Utils, and Services
from users.permissions import CanManageFinance, IsStudent
from .utils import Paystack
from .services import FinanceService  # ✅ Decoupled Service Logic

class StudentFinanceViewSet(viewsets.ViewSet):
    """
    Simplified Student Finance View for Dashboard
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['get'], url_path='current-invoice')
    def current_invoice(self, request):
        # 1. Validation: Ensure user is a student
        if not hasattr(request.user, 'student_profile'):
            return Response({'error': 'Student profile not found'}, status=400)
        
        student = request.user.student_profile

        # 2. Get Active Semester
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            return Response({'error': 'No active semester found. Contact Admin.'}, status=404)

        # 3. Find Existing Invoice (Prioritize Pending/Partial)
        invoice = Invoice.objects.filter(
            student=student,
            session=current_semester.session,
            semester=current_semester.semester
        ).first()

        # 4. If Invoice Exists, return it
        if invoice:
            return Response(InvoiceSerializer(invoice).data)

        # 5. Fallback: Auto-Generate "Standard Tuition" Invoice if missing
        # This prevents the student dashboard from breaking if the Bursar hasn't run the bulk job yet.
        try:
            # Default amount
            amount = 150000.00 
            
            # Check for FeeStructure
            fee_struct = FeeStructure.objects.filter(
                level=student.level, 
                department=student.department,
                is_active=True
            ).first()
            
            if fee_struct:
                amount = fee_struct.total_fee

            # Create the invoice
            new_invoice = Invoice.objects.create(
                student=student,
                invoice_number=f"INV-{timezone.now().strftime('%y%m%d')}-{student.id}",
                amount=amount,
                amount_paid=0.00,
                status='pending',
                session=current_semester.session,
                semester=current_semester.semester,
                due_date=timezone.now() + timezone.timedelta(days=14),
                description=f"Tuition Fee for {current_semester.session}"
            )
            
            return Response(InvoiceSerializer(new_invoice).data)

        except Exception as e:
            return Response({'error': 'Could not generate invoice'}, status=500)


class PaystackPaymentViewSet(viewsets.ViewSet):
    """
    Dedicated ViewSet for Paystack operations.
    Delegates business logic to FinanceService.
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'])
    def initialize(self, request):
        """
        Initialize payment and return Paystack Checkout URL
        """
        serializer = PaystackInitializeSerializer(
            data=request.data, 
            context={'request': request}
        )
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        data = serializer.validated_data
        invoice = get_object_or_404(Invoice, id=data['invoice_id'])
        
        # Security Check: Invoice ownership
        if request.user.role == 'student':
            if not hasattr(request.user, 'student_profile') or invoice.student != request.user.student_profile:
                return Response({'error': 'Unauthorized access to invoice'}, status=403)

        # ✅ Decoupled Logic: Use Service
        result = FinanceService.initialize_paystack_transaction(
            user=request.user,
            invoice=invoice,
            amount=data['amount'],
            callback_url=data.get('callback_url')
        )

        if result['success']:
            return Response({
                'status': True,
                'authorization_url': result['authorization_url'],
                'reference': result['reference'],
                'payment_id': result['payment_id']
            })
        
        return Response({'error': result.get('error', 'Initialization failed')}, status=400)

    @action(detail=False, methods=['post'])
    def verify(self, request):
        """
        Verify payment after callback from frontend
        """
        reference = request.data.get('reference')
        if not reference:
            return Response({'error': 'Reference is required'}, status=400)

        # ✅ Decoupled Logic: Use Service
        result = FinanceService.verify_paystack_transaction(reference)

        if result['success']:
            return Response({'status': 'success', 'message': result['message']})
        
        return Response({'error': result.get('error', 'Verification failed')}, status=400)

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def paystack_webhook(self, request):
        """
        Handle Paystack server-to-server webhook
        """
        # In production, verify the X-Paystack-Signature header here!
        reference = request.data.get('data', {}).get('reference')
        
        if not reference:
            return Response({'error': 'No reference provided'}, status=400)
        
        # ✅ Decoupled Logic: Use Service
        result = FinanceService.verify_paystack_transaction(reference)
        
        if result['success']:
            return Response({'status': 'success'})
        
        return Response({'error': 'Webhook processing failed'}, status=400)


class FeeStructureViewSet(viewsets.ModelViewSet):
    """Fee structure operations (Admin/Bursar)"""
    queryset = FeeStructure.objects.select_related('department').all()
    serializer_class = FeeStructureSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['level', 'department', 'session', 'is_active']
    search_fields = ['name', 'description']
    ordering_fields = ['created_at', 'session']
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [CanManageFinance()]
        return [IsAuthenticated()]


class FeeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only view for students to see available fee structures.
    """
    queryset = FeeStructure.objects.filter(is_active=True)
    serializer_class = FeeStructureSerializer
    permission_classes = [IsAuthenticated]


class InvoiceViewSet(viewsets.ModelViewSet):
    """Invoice operations"""
    queryset = Invoice.objects.select_related(
        'student__user',
        'fee_structure'
    ).all()
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['student', 'status', 'session', 'semester']
    search_fields = ['invoice_number', 'student__matric_number']
    ordering_fields = ['created_at', 'due_date', 'amount']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        # Students can only see their own invoices
        if user.role == 'student' and hasattr(user, 'student_profile'):
            queryset = queryset.filter(student=user.student_profile)
        
        return queryset
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [CanManageFinance()]
        return [IsAuthenticated()]
    
    @action(detail=False, methods=['get'], permission_classes=[IsStudent])
    def student_invoices(self, request):
        """Get all invoices for the authenticated student"""
        if not hasattr(request.user, 'student_profile'):
            return Response(
                {'error': 'Student profile not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        student = request.user.student_profile
        invoices = self.get_queryset().filter(student=student)
        serializer = self.get_serializer(invoices, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[IsStudent])
    def current_semester_invoice(self, request):
        """Get current semester invoice for student"""
        if not hasattr(request.user, 'student_profile'):
            return Response(
                {'error': 'Student profile not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        student = request.user.student_profile
        current_semester = Semester.objects.filter(is_current=True).first()
        
        if not current_semester:
            return Response(
                {'error': 'No current semester set'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        try:
            invoice = Invoice.objects.get(
                student=student,
                session=current_semester.session,
                semester=current_semester.semester
            )
            serializer = self.get_serializer(invoice)
            return Response(serializer.data)
        except Invoice.DoesNotExist:
            return Response(
                {'error': 'No invoice found for current semester'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['get'], permission_classes=[IsStudent])
    def student_fee_summary(self, request):
        """Get fee summary for authenticated student"""
        if not hasattr(request.user, 'student_profile'):
            return Response(
                {'error': 'Student profile not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        student = request.user.student_profile
        invoices = Invoice.objects.filter(student=student)
        
        total_amount = invoices.aggregate(Sum('amount'))['amount__sum'] or 0
        total_paid = invoices.aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0
        
        # Get current semester invoice
        current_semester = Semester.objects.filter(is_current=True).first()
        current_invoice = None
        if current_semester:
            try:
                current_invoice = Invoice.objects.get(
                    student=student,
                    session=current_semester.session,
                    semester=current_semester.semester
                )
            except Invoice.DoesNotExist:
                pass
        
        summary_data = {
            'total_invoices': invoices.count(),
            'total_amount': total_amount,
            'total_paid': total_paid,
            'total_outstanding': total_amount - total_paid,
            'current_semester_invoice': current_invoice,
            'has_paid_current_fees': current_invoice.is_tuition_paid() if current_invoice else False
        }
        
        serializer = StudentFeeSummarySerializer(summary_data)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get invoice summary"""
        queryset = self.filter_queryset(self.get_queryset())
        
        total_amount = queryset.aggregate(Sum('amount'))['amount__sum'] or 0
        total_paid = queryset.aggregate(Sum('amount_paid'))['amount_paid__sum'] or 0
        
        status_counts = {}
        for status_choice in Invoice.STATUS_CHOICES:
            status_counts[status_choice[0]] = queryset.filter(
                status=status_choice[0]
            ).count()
        
        return Response({
            'total_invoices': queryset.count(),
            'total_amount': total_amount,
            'total_paid': total_paid,
            'total_outstanding': total_amount - total_paid,
            'status_breakdown': status_counts
        })


class PaymentViewSet(viewsets.ModelViewSet):
    """Payment operations"""
    queryset = Payment.objects.select_related(
        'student__user',
        'invoice',
        'verified_by'
    ).all()
    serializer_class = PaymentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['student', 'status', 'payment_method', 'invoice']
    search_fields = ['reference_id', 'student__matric_number', 'transaction_reference']
    ordering_fields = ['created_at', 'payment_date', 'amount']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        # Students can only see their own payments
        if user.role == 'student' and hasattr(user, 'student_profile'):
            queryset = queryset.filter(student=user.student_profile)
        
        return queryset
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update']:
            return [CanManageFinance()]
        return [IsAuthenticated()]
    
    @action(detail=False, methods=['get'], permission_classes=[IsStudent])
    def student_payments(self, request):
        """Get all payments for the authenticated student"""
        if not hasattr(request.user, 'student_profile'):
            return Response(
                {'error': 'Student profile not found'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        student = request.user.student_profile
        payments = self.get_queryset().filter(student=student)
        serializer = self.get_serializer(payments, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get payment summary"""
        queryset = self.filter_queryset(self.get_queryset())
        
        total_amount = queryset.filter(
            status='completed'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        pending_amount = queryset.filter(
            status='pending'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        method_breakdown = {}
        for method in Payment.PAYMENT_METHOD_CHOICES:
            method_breakdown[method[0]] = queryset.filter(
                payment_method=method[0],
                status='completed'
            ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        summary_data = {
            'total_payments': queryset.filter(status='completed').count(),
            'total_amount': total_amount,
            'pending_payments': queryset.filter(status='pending').count(),
            'pending_amount': pending_amount,
            'payment_methods': method_breakdown
        }
        
        serializer = PaymentSummarySerializer(summary_data)
        return Response(serializer.data)


class PaymentReceiptViewSet(viewsets.ModelViewSet):
    """Payment receipt operations"""
    queryset = PaymentReceipt.objects.select_related(
        'payment__student__user',
        'issued_by'
    ).all()
    serializer_class = PaymentReceiptSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['receipt_number', 'payment__reference_id']
    ordering_fields = ['issued_date']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        
        if user.role == 'student' and hasattr(user, 'student_profile'):
            queryset = queryset.filter(payment__student=user.student_profile)
        
        return queryset
    
    def get_permissions(self):
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [CanManageFinance()]
        return [IsAuthenticated()]
    
    def perform_create(self, serializer):
        serializer.save(issued_by=self.request.user)



