from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView 
from django.db.models import Sum
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
import pandas as pd
from io import BytesIO
from django.http import HttpResponse

# Models
from .models import Invoice, Payment, PaymentReceipt
from users.models import Student
from academics.models import Semester, Department # ✅ Added Department

# Serializers
from .serializers import (
    InvoiceSerializer, PaymentSerializer, PaymentReceiptSerializer
)

# Permissions
from users.permissions import IsBursar, CanVerifyPayments, CanGenerateFinancialReports


class BursarDashboardViewSet(viewsets.ViewSet):
    """Bursar dashboard with financial overview"""
    permission_classes = [IsAuthenticated, IsBursar]
    
    @action(detail=False, methods=['get'])
    def overview(self, request):
        current_semester = Semester.objects.filter(is_current=True).first()
        
        total_revenue = Payment.objects.filter(status='completed').aggregate(Sum('amount'))['amount__sum'] or 0
        pending_payments_count = Payment.objects.filter(status='pending').count()
        
        cleared_students_count = 0
        if current_semester:
            cleared_students_count = Invoice.objects.filter(
                session=current_semester.session,
                status='paid'
            ).values('student').distinct().count()
        
        total_invoices = Invoice.objects.count()
        
        recent_payments = Payment.objects.select_related('student__user').order_by('-payment_date')[:5]
        recent_payments_data = []
        for payment in recent_payments:
            recent_payments_data.append({
                'id': payment.id,
                'reference_id': payment.reference_id,
                'amount': payment.amount,
                'student_name': payment.student.user.get_full_name(),
                'payment_method': payment.payment_method,
                'status': payment.status,
                'payment_date': payment.payment_date
            })

        growth_percentage = 0 

        return Response({
            'stats': {
                'total_revenue': total_revenue,
                'pending_payments': pending_payments_count,
                'cleared_students': cleared_students_count,
                'total_invoices': total_invoices,
                'growth_percentage': growth_percentage
            },
            'recent_payments': recent_payments_data,
            'current_semester': {
                'session': current_semester.session if current_semester else 'N/A',
                'semester': current_semester.semester if current_semester else 'N/A'
            }
        })

    @action(detail=False, methods=['get'])
    def revenue_trend(self, request):
        six_months_ago = timezone.now() - timedelta(days=180)
        payments = Payment.objects.filter(status='completed', payment_date__gte=six_months_ago).order_by('payment_date')
        
        trend_map = {}
        for payment in payments:
            if not payment.payment_date:
                continue
            key = payment.payment_date.strftime('%B %Y')
            if key not in trend_map:
                trend_map[key] = {'amount': 0, 'count': 0}
            trend_map[key]['amount'] += float(payment.amount)
            trend_map[key]['count'] += 1
            
        trend_data = [{'period': k, 'amount': v['amount'], 'count': v['count']} for k, v in trend_map.items()]
        return Response({'monthly_trend': trend_data})


class PaymentVerificationViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, CanVerifyPayments]
    
    @action(detail=False, methods=['get'])
    def pending_verifications(self, request):
        pending_payments = Payment.objects.filter(status='pending').select_related('student__user', 'invoice').order_by('-created_at')
        serializer = PaymentSerializer(pending_payments, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def verify_payment(self, request, pk=None):
        try:
            payment = Payment.objects.get(id=pk, status='pending')
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
            
        action = request.data.get('action')
        
        if action == 'verify':
            payment.status = 'completed'
            payment.verified_by = request.user
            payment.payment_date = timezone.now()
            payment.save()
            
            if payment.invoice:
                payment.invoice.amount_paid += payment.amount
                payment.invoice.save() # Built-in save() handles status calculation
                
            return Response({'message': 'Payment verified successfully'})
            
        elif action == 'reject':
            payment.status = 'failed'
            payment.verified_by = request.user
            payment.remarks = request.data.get('remarks', 'Rejected by bursar')
            payment.save()
            return Response({'message': 'Payment rejected'})
            
        return Response({'error': 'Invalid action'}, status=status.HTTP_400_BAD_REQUEST)


class InvoiceManagementViewSet(viewsets.ViewSet):
    """Invoice management operations"""
    permission_classes = [IsAuthenticated, IsBursar]
    
    @action(detail=False, methods=['get'])
    def overdue_invoices(self, request):
        invoices = Invoice.objects.filter(
            status__in=['pending', 'partially_paid'],
            due_date__lt=timezone.now()
        ).select_related('student__user')
        serializer = InvoiceSerializer(invoices, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def generate_bulk(self, request):
        """Generate invoices for all students in a specific level AND optional Department"""
        session = request.data.get('session')
        semester = request.data.get('semester')
        level = request.data.get('level')
        department_id = request.data.get('department_id') # ✅ Optional Department
        
        amount_raw = request.data.get('amount') 
        due_date = request.data.get('due_date')
        description = request.data.get('description', 'Tuition Fee')

        if not all([session, semester, level, amount_raw, due_date]):
            return Response(
                {'error': 'Session, Semester, Level, Amount, and Due Date are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Convert amount to float before using it
            amount = float(amount_raw)
            
            # Get target students
            # ✅ Filter by department if provided
            filters = {'level': level, 'status': 'active'}
            if department_id and str(department_id) != "all":
                filters['department_id'] = department_id
                
            students = Student.objects.filter(**filters)
            
            if not students.exists():
                 return Response(
                    {'error': f'No active students found in level {level} (Dept: {department_id or "All"})'},
                    status=status.HTTP_404_NOT_FOUND
                )

            created_count = 0
            skipped_count = 0

            with transaction.atomic():
                for student in students:
                    # Check for existing invoice to prevent duplicates for SAME session/semester
                    exists = Invoice.objects.filter(
                        student=student,
                        session=session,
                        semester=semester,
                    ).exists()

                    if exists:
                        skipped_count += 1
                        continue
                    
                    inv_num = f"INV-{timezone.now().strftime('%y%m%d')}-{student.id}-{semester}"

                    Invoice.objects.create(
                        student=student,
                        invoice_number=inv_num,
                        amount=amount,
                        amount_paid=0.00,
                        status='pending',
                        session=session,
                        semester=semester,
                        due_date=due_date,
                        description=description
                    )
                    created_count += 1

            return Response({
                'message': 'Bulk generation complete',
                'created': created_count,
                'skipped': skipped_count,
                'total_processed': created_count + skipped_count
            })

        except ValueError:
            return Response(
                {'error': 'Invalid amount format. Please enter a valid number.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            print(f"❌ BULK INVOICE ERROR: {str(e)}") 
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        """Manually mark an invoice as paid (Bursar override)"""
        try:
            invoice = Invoice.objects.get(id=pk)
            invoice.amount_paid = invoice.amount
            invoice.save() # status will be auto-calculated to 'paid'
            return Response({'message': f'Invoice {invoice.invoice_number} marked as PAID.'})
        except Invoice.DoesNotExist:
            return Response({'error': 'Invoice not found'}, status=404)


class ReceiptManagementViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, IsBursar]
    
    @action(detail=False, methods=['get'])
    def history(self, request):
        receipts = PaymentReceipt.objects.all().order_by('-issued_date')[:50]
        serializer = PaymentReceiptSerializer(receipts, many=True)
        return Response(serializer.data)


class FinancialReportsViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated, CanGenerateFinancialReports]
    
    @action(detail=False, methods=['get'])
    def export_revenue(self, request):
        payments = Payment.objects.filter(status='completed')
        data = []
        for p in payments:
            data.append({
                'Reference': p.reference_id,
                'Student': p.student.user.get_full_name(),
                'Amount': p.amount,
                'Date': p.payment_date.strftime('%Y-%m-%d') if p.payment_date else ''
            })
        
        df = pd.DataFrame(data)
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Revenue', index=False)
        output.seek(0)
        
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="Revenue_Report.xlsx"'
        return response


class BursarAPIView(APIView):
    """Main API view for bursar initial data"""
    permission_classes = [IsAuthenticated, IsBursar]
    
    def get(self, request):
        user = request.user
        return Response({
            'bursar': {
                'id': user.id,
                'name': user.get_full_name(),
                'email': user.email,
                'role': user.role
            }
        })