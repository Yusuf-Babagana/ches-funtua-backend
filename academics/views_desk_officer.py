# academics/views_desk_officer.py - ENHANCED VERSION
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from django.db.models import Count, Q, Sum, Avg, F
from django.db import transaction
from django.utils import timezone
from datetime import datetime, timedelta
from django.shortcuts import get_object_or_404
import pandas as pd
from io import BytesIO
from django.http import HttpResponse

# ✅ FIXED IMPORTS: Removed 'Registration', ensured 'CourseRegistration' is used
from academics.models import (
    CourseOffering, Semester, Department,
    CourseRegistration, Course, Grade  # Assuming Result was meant to be Grade or keep if Result exists
)
from users.models import User, Student
from finance.models import Invoice, Payment, FeeStructure
from users.permissions import IsDeskOfficer, CanOverrideRegistration, CanVerifyDocuments
from django.db import models # Added for the internal models

# ==============================================
# NEW MODELS FOR DESK OFFICER
# ==============================================

# Add these models to your academics/models.py if not present
class StudentDocument(models.Model):
    """Model for student document uploads and verification"""
    DOCUMENT_TYPES = [
        ('birth_certificate', 'Birth Certificate'),
        ('o_level', 'O\'Level Result'),
        ('jamb_result', 'JAMB Result'),
        ('jamb_admission', 'JAMB Admission Letter'),
        ('local_government', 'Local Government Certificate'),
        ('medical_report', 'Medical Report'),
        ('passport_photo', 'Passport Photograph'),
        ('acceptance_fee', 'Acceptance Fee Receipt'),
        ('school_fees', 'School Fees Receipt'),
        ('other', 'Other Document'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
        ('requires_update', 'Requires Update'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
    document_name = models.CharField(max_length=200)
    document_file = models.FileField(upload_to='student_documents/%Y/%m/%d/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    remarks = models.TextField(blank=True, null=True)
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_documents')
    verified_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.student.matric_number} - {self.get_document_type_display()}"


class StudentQuery(models.Model):
    """Model for student queries/complaints"""
    QUERY_TYPES = [
        ('registration', 'Registration Issue'),
        ('payment', 'Payment Issue'),
        ('document', 'Document Upload Issue'),
        ('course', 'Course Registration'),
        ('result', 'Result Issue'),
        ('personal_info', 'Personal Information'),
        ('other', 'Other Issue'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]
    
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='queries')
    query_type = models.CharField(max_length=50, choices=QUERY_TYPES)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    subject = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    resolution_notes = models.TextField(blank=True, null=True)
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_queries')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_queries')
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.student.matric_number} - {self.subject}"


# ==============================================
# DESK OFFICER VIEWSET - ENHANCED
# ==============================================

class DeskOfficerViewSet(viewsets.ViewSet):
    """Enhanced Desk Officer interface for administrative tasks"""
    permission_classes = [IsAuthenticated, IsDeskOfficer]
    
    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """Enhanced Desk Officer dashboard"""
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            return Response({'error': 'No current semester'}, status=400)
        
        # Enhanced statistics
        # ✅ FIXED: Used CourseRegistration
        total_registrations = CourseRegistration.objects.filter(
            course_offering__semester=current_semester,
            status='registered'
        ).count()
        
        # ✅ FIXED: Used CourseRegistration
        pending_verifications = CourseRegistration.objects.filter(
            course_offering__semester=current_semester,
            is_payment_verified=False
        ).count()
        
        students_without_registration = Student.objects.filter(
            status='active'
        ).exclude(
            # ✅ FIXED: Used registrations (related name)
            registrations__course_offering__semester=current_semester,
            registrations__status='registered'
        ).count()
        
        # Document verification stats
        pending_documents = StudentDocument.objects.filter(status='pending').count()
        
        # Student query stats
        open_queries = StudentQuery.objects.filter(status__in=['open', 'in_progress']).count()
        assigned_queries = StudentQuery.objects.filter(
            assigned_to=request.user,
            status__in=['open', 'in_progress']
        ).count()
        
        # Payment verification stats
        pending_payments = Payment.objects.filter(
            status='pending',
            payment_method__in=['cash', 'bank_transfer']
        ).count()
        
        # Today's activities
        today = timezone.now().date()
        # ✅ FIXED: Used CourseRegistration
        todays_registrations = CourseRegistration.objects.filter(
            registration_date__date=today,
            course_offering__semester=current_semester
        ).count()
        
        todays_queries = StudentQuery.objects.filter(created_at__date=today).count()
        todays_documents = StudentDocument.objects.filter(uploaded_at__date=today).count()
        
        return Response({
            'current_semester': {
                'id': current_semester.id,
                'session': current_semester.session,
                'semester': current_semester.get_semester_display(),
                'is_registration_active': current_semester.is_registration_active,
                'registration_deadline': current_semester.registration_deadline
            },
            'statistics': {
                'total_registrations': total_registrations,
                'pending_payment_verifications': pending_verifications,
                'students_without_registration': students_without_registration,
                'total_courses': CourseOffering.objects.filter(
                    semester=current_semester,
                    is_active=True
                ).count(),
                'pending_documents': pending_documents,
                'open_queries': open_queries,
                'pending_payments': pending_payments
            },
            'assigned_to_me': {
                'queries': assigned_queries,
                'documents': StudentDocument.objects.filter(
                    verified_by=request.user,
                    verified_at__date=today
                ).count()
            },
            'today_activities': {
                'registrations': todays_registrations,
                'queries_created': todays_queries,
                'documents_uploaded': todays_documents
            },
            'quick_actions': [
                {'action': 'verify_registrations', 'label': 'Verify Registrations', 'count': pending_verifications},
                {'action': 'verify_documents', 'label': 'Verify Documents', 'count': pending_documents},
                {'action': 'handle_queries', 'label': 'Handle Queries', 'count': open_queries},
                {'action': 'verify_payments', 'label': 'Verify Payments', 'count': pending_payments},
                {'action': 'student_search', 'label': 'Student Search', 'count': 0},
                {'action': 'manual_registration', 'label': 'Manual Registration', 'count': students_without_registration}
            ]
        })
    
    @action(detail=False, methods=['get'])
    def daily_summary(self, request):
        """Get daily summary report"""
        date_str = request.query_params.get('date', timezone.now().date().isoformat())
        
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            date = timezone.now().date()
        
        # Get current semester
        current_semester = Semester.objects.filter(is_current=True).first()
        
        # Get activities for the date
        # ✅ FIXED: Used CourseRegistration
        registrations = CourseRegistration.objects.filter(
            registration_date__date=date,
            course_offering__semester=current_semester
        ) if current_semester else CourseRegistration.objects.none()
        
        queries = StudentQuery.objects.filter(created_at__date=date)
        documents = StudentDocument.objects.filter(uploaded_at__date=date)
        payments = Payment.objects.filter(payment_date__date=date)
        
        return Response({
            'date': date.isoformat(),
            'summary': {
                'registrations': registrations.count(),
                'queries': queries.count(),
                'documents': documents.count(),
                'payments': payments.count()
            },
            'by_department': self._get_department_stats(date, current_semester),
            'top_issues': queries.values('subject').annotate(
                count=Count('id')
            ).order_by('-count')[:5]
        })
    
    def _get_department_stats(self, date, semester):
        """Get statistics by department"""
        departments = Department.objects.all()
        stats = []
        
        for dept in departments:
            dept_stats = {
                'department': dept.name,
                # ✅ FIXED: Used CourseRegistration
                'registrations': CourseRegistration.objects.filter(
                    registration_date__date=date,
                    course_offering__semester=semester,
                    student__department=dept
                ).count() if semester else 0,
                'queries': StudentQuery.objects.filter(
                    created_at__date=date,
                    student__department=dept
                ).count(),
                'students': Student.objects.filter(department=dept, status='active').count()
            }
            stats.append(dept_stats)
        
        return stats


# ==============================================
# STUDENT MANAGEMENT - ENHANCED
# ==============================================

class StudentManagementViewSet(viewsets.ViewSet):
    """Enhanced student management for Desk Officer"""
    permission_classes = [IsAuthenticated, IsDeskOfficer]
    
    @action(detail=False, methods=['get'])
    def student_search(self, request):
        """Enhanced student search with detailed information"""
        search_query = request.query_params.get('q', '')
        department_id = request.query_params.get('department')
        level = request.query_params.get('level')
        registration_status = request.query_params.get('registration_status')
        
        if not search_query and not department_id and not level:
            return Response({'error': 'At least one search parameter is required'}, status=400)
        
        students = Student.objects.select_related('user', 'department')
        
        # Apply search filters
        if search_query:
            students = students.filter(
                Q(matric_number__icontains=search_query) |
                Q(user__first_name__icontains=search_query) |
                Q(user__last_name__icontains=search_query) |
                Q(user__email__icontains=search_query) |
                Q(user__phone__icontains=search_query)
            )
        
        if department_id:
            students = students.filter(department_id=department_id)
        
        if level:
            students = students.filter(level=level)
        
        # Get current semester
        current_semester = Semester.objects.filter(is_current=True).first()
        
        students_data = []
        for student in students[:50]:  # Limit results
            # Get current semester registration status
            registration = None
            if current_semester:
                try:
                    # ✅ FIXED: Used CourseRegistration
                    registration = CourseRegistration.objects.filter(
                        student=student,
                        course_offering__semester=current_semester
                    ).first()
                except:
                    pass
            
            # Get payment status
            invoice_paid = False
            if current_semester:
                try:
                    invoice = Invoice.objects.get(
                        student=student,
                        session=current_semester.session,
                        semester=current_semester.semester
                    )
                    invoice_paid = invoice.status == 'paid'
                except Invoice.DoesNotExist:
                    pass
            
            # Get pending documents
            pending_docs = StudentDocument.objects.filter(
                student=student,
                status='pending'
            ).count()
            
            # Get open queries
            open_queries = StudentQuery.objects.filter(
                student=student,
                status__in=['open', 'in_progress']
            ).count()
            
            students_data.append({
                'id': student.id,
                'matric_number': student.matric_number,
                'full_name': student.user.get_full_name(),
                'email': student.user.email,
                'phone': student.user.phone,
                'department': student.department.name if student.department else None,
                'level': student.level,
                'status': student.status,
                'current_registration': registration.status if registration else 'not_registered',
                'payment_status': 'paid' if invoice_paid else 'pending',
                'pending_documents': pending_docs,
                'open_queries': open_queries,
                'last_login': student.user.last_login,
                'is_active': student.user.is_active
            })
        
        # Apply registration status filter
        if registration_status and current_semester:
            if registration_status == 'registered':
                students_data = [s for s in students_data if s['current_registration'] == 'registered']
            elif registration_status == 'pending':
                students_data = [s for s in students_data if s['current_registration'] in ['pending', 'rejected']]
            elif registration_status == 'not_registered':
                students_data = [s for s in students_data if s['current_registration'] == 'not_registered']
        
        return Response({
            'search_query': search_query,
            'filters': {
                'department': department_id,
                'level': level,
                'registration_status': registration_status
            },
            'total_results': len(students_data),
            'results': students_data
        })
    
    @action(detail=True, methods=['get'])
    def student_profile(self, request, pk=None):
        """Get detailed student profile"""
        student = get_object_or_404(Student, id=pk)
        
        # Get current semester
        current_semester = Semester.objects.filter(is_current=True).first()
        
        # Get registrations for current semester
        current_registrations = []
        if current_semester:
            # ✅ FIXED: Used CourseRegistration
            registrations = CourseRegistration.objects.filter(
                student=student,
                course_offering__semester=current_semester
            ).select_related('course_offering__course')
            
            current_registrations = [{
                'id': reg.id,
                'course_code': reg.course_offering.course.code,
                'course_title': reg.course_offering.course.title,
                'credits': reg.course_offering.course.credits,
                'status': reg.status,
                'is_payment_verified': reg.is_payment_verified,
                'registration_date': reg.registration_date
            } for reg in registrations]
        
        # Get invoices
        invoices = Invoice.objects.filter(student=student).order_by('-created_at')[:5]
        
        # Get payments
        payments = Payment.objects.filter(student=student).order_by('-payment_date')[:10]
        
        # Get documents
        documents = StudentDocument.objects.filter(student=student).order_by('-uploaded_at')[:10]
        
        # Get queries
        queries = StudentQuery.objects.filter(student=student).order_by('-created_at')[:10]
        
        # Get academic history (Using Grade, assuming Result is not used or is same as Grade)
        results = Grade.objects.filter(
            student=student
        ).select_related(
            'course'
        ).order_by('-session', '-semester')[:10]
        
        return Response({
            'student': {
                'id': student.id,
                'matric_number': student.matric_number,
                'full_name': student.user.get_full_name(),
                'email': student.user.email,
                'phone': student.user.phone,
                'department': student.department.name if student.department else None,
                'level': student.level,
                'admission_date': student.admission_date,
                'status': student.status,
                'is_active': student.user.is_active,
                'last_login': student.user.last_login
            },
            'current_semester': {
                'id': current_semester.id if current_semester else None,
                'session': current_semester.session if current_semester else None,
                'semester': current_semester.get_semester_display() if current_semester else None,
            },
            'registrations': current_registrations,
            'invoices': [{
                'id': inv.id,
                'invoice_number': inv.invoice_number,
                'amount': float(inv.amount),
                'amount_paid': float(inv.amount_paid),
                'balance': float(inv.balance),
                'status': inv.status,
                'due_date': inv.due_date,
                'session': inv.session,
                'semester': inv.semester
            } for inv in invoices],
            'recent_payments': [{
                'id': pay.id,
                'reference_id': pay.reference_id,
                'amount': float(pay.amount),
                'payment_method': pay.payment_method,
                'status': pay.status,
                'payment_date': pay.payment_date,
                'verified_by': pay.verified_by.get_full_name() if pay.verified_by else None
            } for pay in payments],
            'documents': [{
                'id': doc.id,
                'document_type': doc.get_document_type_display(),
                'document_name': doc.document_name,
                'status': doc.status,
                'uploaded_at': doc.uploaded_at,
                'verified_by': doc.verified_by.get_full_name() if doc.verified_by else None
            } for doc in documents],
            'queries': [{
                'id': query.id,
                'query_type': query.get_query_type_display(),
                'subject': query.subject,
                'status': query.status,
                'priority': query.priority,
                'created_at': query.created_at,
                'assigned_to': query.assigned_to.get_full_name() if query.assigned_to else None
            } for query in queries],
            'academic_history': [{
                'course_code': res.course.code,
                'course_title': res.course.title,
                'session': res.session,
                'semester': res.semester,
                'grade': res.grade_letter,
                'score': res.score,
                'remarks': res.remarks
            } for res in results]
        })
    
    @action(detail=True, methods=['post'])
    def update_student_info(self, request, pk=None):
        """Update student information manually"""
        student = get_object_or_404(Student, id=pk)
        
        allowed_fields = ['phone', 'email', 'level', 'status']
        update_data = {}
        updates_made = []
        
        # Only allow specific fields to be updated
        for field in allowed_fields:
            if field in request.data:
                update_data[field] = request.data[field]
                updates_made.append(field)
        
        if not update_data:
            return Response(
                {'error': 'No valid fields to update'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update student user info
        if 'phone' in update_data or 'email' in update_data:
            user = student.user
            if 'phone' in update_data:
                user.phone = update_data['phone']
            if 'email' in update_data:
                user.email = update_data['email']
            user.save()
        
        # Update student fields
        if 'level' in update_data:
            student.level = update_data['level']
        
        if 'status' in update_data:
            student.status = update_data['status']
        
        student.save()
        
        # Create audit log entry
        remarks = f"Updated by Desk Officer {request.user.get_full_name()}. Fields: {', '.join(updates_made)}"
        
        return Response({
            'message': 'Student information updated successfully',
            'updated_fields': updates_made,
            'student': {
                'id': student.id,
                'matric_number': student.matric_number,
                'full_name': student.user.get_full_name(),
                'email': student.user.email,
                'phone': student.user.phone,
                'level': student.level,
                'status': student.status
            },
            'remarks': remarks
        })


# ==============================================
# DOCUMENT VERIFICATION
# ==============================================

class DocumentVerificationViewSet(viewsets.ViewSet):
    """Document verification for Desk Officer"""
    permission_classes = [IsAuthenticated, IsDeskOfficer]
    
    @action(detail=False, methods=['get'])
    def pending_documents(self, request):
        """Get all pending documents"""
        documents = StudentDocument.objects.filter(
            status='pending'
        ).select_related('student__user', 'student__department')
        
        # Group by student
        grouped_docs = {}
        for doc in documents:
            student_id = doc.student.id
            if student_id not in grouped_docs:
                grouped_docs[student_id] = {
                    'student': {
                        'id': doc.student.id,
                        'matric_number': doc.student.matric_number,
                        'full_name': doc.student.user.get_full_name(),
                        'level': doc.student.level,
                        'department': doc.student.department.name if doc.student.department else None
                    },
                    'documents': []
                }
            
            grouped_docs[student_id]['documents'].append({
                'id': doc.id,
                'document_type': doc.get_document_type_display(),
                'document_name': doc.document_name,
                'uploaded_at': doc.uploaded_at,
                'days_since_upload': (timezone.now().date() - doc.uploaded_at.date()).days
            })
        
        return Response({
            'total_pending': documents.count(),
            'grouped_documents': list(grouped_docs.values())
        })
    
    @action(detail=True, methods=['post'])
    def verify_document(self, request, pk=None):
        """Verify or reject a document"""
        try:
            document = StudentDocument.objects.get(id=pk, status='pending')
        except StudentDocument.DoesNotExist:
            return Response({'error': 'Document not found or already processed'}, status=404)
        
        action = request.data.get('action')  # 'verify', 'reject', 'requires_update'
        remarks = request.data.get('remarks', '')
        
        if action not in ['verify', 'reject', 'requires_update']:
            return Response({'error': 'Invalid action'}, status=400)
        
        if action in ['reject', 'requires_update'] and not remarks:
            return Response({'error': 'Remarks required for rejection or update request'}, status=400)
        
        document.status = action if action != 'requires_update' else 'requires_update'
        document.remarks = remarks
        document.verified_by = request.user
        document.verified_at = timezone.now()
        document.save()
        
        message = f"Document {action}ed successfully"
        if action == 'requires_update':
            message = "Document marked as requiring update"
        
        return Response({
            'message': message,
            'document': {
                'id': document.id,
                'document_type': document.get_document_type_display(),
                'status': document.status,
                'verified_by': request.user.get_full_name(),
                'verified_at': document.verified_at,
                'remarks': document.remarks
            }
        })
    
    @action(detail=False, methods=['get'])
    def document_stats(self, request):
        """Get document verification statistics"""
        total_docs = StudentDocument.objects.count()
        pending = StudentDocument.objects.filter(status='pending').count()
        verified = StudentDocument.objects.filter(status='verified').count()
        rejected = StudentDocument.objects.filter(status='rejected').count()
        
        # By document type
        by_type = StudentDocument.objects.values('document_type').annotate(
            total=Count('id'),
            pending=Count('id', filter=Q(status='pending')),
            verified=Count('id', filter=Q(status='verified'))
        ).order_by('-total')
        
        # Recent verifications
        recent_verifications = StudentDocument.objects.filter(
            verified_by=request.user,
            verified_at__isnull=False
        ).order_by('-verified_at')[:10]
        
        return Response({
            'summary': {
                'total': total_docs,
                'pending': pending,
                'verified': verified,
                'rejected': rejected,
                'verification_rate': (verified / total_docs * 100) if total_docs > 0 else 0
            },
            'by_document_type': list(by_type),
            'recent_verifications': [{
                'id': doc.id,
                'document_type': doc.get_document_type_display(),
                'student': doc.student.matric_number,
                'status': doc.status,
                'verified_at': doc.verified_at
            } for doc in recent_verifications]
        })


# ==============================================
# STUDENT QUERY MANAGEMENT
# ==============================================

class StudentQueryViewSet(viewsets.ViewSet):
    """Student query management for Desk Officer"""
    permission_classes = [IsAuthenticated, IsDeskOfficer]
    
    @action(detail=False, methods=['get'])
    def open_queries(self, request):
        """Get all open queries"""
        queries = StudentQuery.objects.filter(
            status__in=['open', 'in_progress']
        ).select_related('student__user', 'student__department', 'assigned_to')
        
        # Group by student
        grouped_queries = {}
        for query in queries:
            student_id = query.student.id
            if student_id not in grouped_queries:
                grouped_queries[student_id] = {
                    'student': {
                        'id': query.student.id,
                        'matric_number': query.student.matric_number,
                        'full_name': query.student.user.get_full_name(),
                        'level': query.student.level,
                        'department': query.student.department.name if query.student.department else None
                    },
                    'queries': []
                }
            
            grouped_queries[student_id]['queries'].append({
                'id': query.id,
                'query_type': query.get_query_type_display(),
                'subject': query.subject,
                'priority': query.priority,
                'status': query.status,
                'created_at': query.created_at,
                'assigned_to': query.assigned_to.get_full_name() if query.assigned_to else None,
                'days_open': (timezone.now().date() - query.created_at.date()).days
            })
        
        return Response({
            'total_open': queries.count(),
            'grouped_queries': list(grouped_queries.values())
        })
    
    @action(detail=False, methods=['get'])
    def my_queries(self, request):
        """Get queries assigned to me"""
        queries = StudentQuery.objects.filter(
            assigned_to=request.user,
            status__in=['open', 'in_progress']
        ).select_related('student__user', 'student__department')
        
        queries_data = [{
            'id': query.id,
            'student': {
                'matric_number': query.student.matric_number,
                'full_name': query.student.user.get_full_name(),
                'level': query.student.level,
                'department': query.student.department.name if query.student.department else None
            },
            'query_type': query.get_query_type_display(),
            'subject': query.subject,
            'priority': query.priority,
            'status': query.status,
            'created_at': query.created_at,
            'description': query.description[:100] + '...' if len(query.description) > 100 else query.description
        } for query in queries]
        
        return Response({
            'total_assigned': len(queries_data),
            'queries': queries_data
        })
    
    @action(detail=True, methods=['post'])
    def assign_to_me(self, request, pk=None):
        """Assign query to current desk officer"""
        try:
            query = StudentQuery.objects.get(id=pk)
        except StudentQuery.DoesNotExist:
            return Response({'error': 'Query not found'}, status=404)
        
        if query.assigned_to and query.assigned_to != request.user:
            return Response({'error': 'Query is already assigned to another officer'}, status=400)
        
        query.assigned_to = request.user
        query.status = 'in_progress'
        query.save()
        
        return Response({
            'message': 'Query assigned to you successfully',
            'query': {
                'id': query.id,
                'subject': query.subject,
                'assigned_to': request.user.get_full_name(),
                'status': query.status
            }
        })
    
    @action(detail=True, methods=['post'])
    def resolve_query(self, request, pk=None):
        """Resolve a student query"""
        try:
            query = StudentQuery.objects.get(id=pk, assigned_to=request.user)
        except StudentQuery.DoesNotExist:
            return Response({'error': 'Query not found or not assigned to you'}, status=404)
        
        resolution_notes = request.data.get('resolution_notes', '')
        
        if not resolution_notes:
            return Response({'error': 'Resolution notes are required'}, status=400)
        
        query.status = 'resolved'
        query.resolution_notes = resolution_notes
        query.resolved_by = request.user
        query.resolved_at = timezone.now()
        query.save()
        
        return Response({
            'message': 'Query resolved successfully',
            'query': {
                'id': query.id,
                'subject': query.subject,
                'status': query.status,
                'resolved_by': request.user.get_full_name(),
                'resolved_at': query.resolved_at,
                'resolution_notes': query.resolution_notes
            }
        })
    
    @action(detail=False, methods=['post'])
    def create_query(self, request):
        """Create a query on behalf of a student"""
        student_id = request.data.get('student_id')
        query_type = request.data.get('query_type')
        subject = request.data.get('subject')
        description = request.data.get('description')
        priority = request.data.get('priority', 'medium')
        
        if not all([student_id, query_type, subject, description]):
            return Response({'error': 'Missing required fields'}, status=400)
        
        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            return Response({'error': 'Student not found'}, status=404)
        
        query = StudentQuery.objects.create(
            student=student,
            query_type=query_type,
            subject=subject,
            description=description,
            priority=priority,
            assigned_to=request.user,
            status='in_progress'
        )
        
        return Response({
            'message': 'Query created successfully',
            'query': {
                'id': query.id,
                'student': student.matric_number,
                'subject': query.subject,
                'type': query.get_query_type_display(),
                'priority': query.priority,
                'assigned_to': request.user.get_full_name()
            }
        })


# ==============================================
# PAYMENT VERIFICATION INTEGRATION
# ==============================================

class PaymentVerificationViewSet(viewsets.ViewSet):
    """Payment verification for Desk Officer"""
    permission_classes = [IsAuthenticated, IsDeskOfficer]
    
    @action(detail=False, methods=['get'])
    def pending_payments(self, request):
        """Get payments pending manual verification"""
        payments = Payment.objects.filter(
            status='pending',
            payment_method__in=['cash', 'bank_transfer']
        ).select_related('student__user', 'invoice')
        
        payments_data = []
        for payment in payments:
            # Check for payment evidence
            has_evidence = self._check_payment_evidence(payment)
            
            payments_data.append({
                'id': payment.id,
                'reference_id': payment.reference_id,
                'student': {
                    'id': payment.student.id,
                    'matric_number': payment.student.matric_number,
                    'full_name': payment.student.user.get_full_name(),
                    'level': payment.student.level,
                    'department': payment.student.department.name if payment.student.department else None
                },
                'amount': float(payment.amount),
                'payment_method': payment.payment_method,
                'description': payment.description,
                'transaction_reference': payment.transaction_reference,
                'created_at': payment.created_at,
                'has_evidence': has_evidence,
                'can_verify': has_evidence and payment.transaction_reference,
                'evidence_status': self._get_evidence_status(payment)
            })
        
        return Response({
            'total_pending': len(payments_data),
            'payments': payments_data
        })
    
    def _check_payment_evidence(self, payment):
        """Check if payment has sufficient evidence"""
        if payment.payment_method == 'bank_transfer':
            return bool(payment.transaction_reference)
        elif payment.payment_method == 'cash':
            return payment.description and 'cash' in payment.description.lower()
        return False
    
    def _get_evidence_status(self, payment):
        """Get evidence status description"""
        if payment.payment_method == 'bank_transfer':
            return 'Transaction reference provided' if payment.transaction_reference else 'Missing transaction reference'
        elif payment.payment_method == 'cash':
            return 'Cash payment description provided' if payment.description else 'Missing cash payment description'
        return 'Unknown payment method'
    
    @action(detail=True, methods=['post'])
    def verify_payment(self, request, pk=None):
        """Verify a pending payment"""
        try:
            payment = Payment.objects.get(id=pk, status='pending')
        except Payment.DoesNotExist:
            return Response({'error': 'Payment not found or already processed'}, status=404)
        
        action = request.data.get('action')  # 'verify' or 'reject'
        remarks = request.data.get('remarks', '')
        
        if action not in ['verify', 'reject']:
            return Response({'error': 'Invalid action'}, status=400)
        
        if action == 'verify':
            # Check payment evidence
            if not self._check_payment_evidence(payment):
                return Response({'error': 'Insufficient payment evidence'}, status=400)
            
            payment.status = 'completed'
            payment.verified_by = request.user
            payment.payment_date = timezone.now()
            payment.remarks = f"Verified by Desk Officer {request.user.get_full_name()}. {remarks}"
            payment.save()
            
            message = 'Payment verified successfully'
            
        else:  # reject
            if not remarks:
                return Response({'error': 'Remarks required when rejecting payment'}, status=400)
            
            payment.status = 'failed'
            payment.remarks = f"Rejected by Desk Officer {request.user.get_full_name()}. Reason: {remarks}"
            payment.save()
            
            message = 'Payment rejected'
        
        return Response({
            'message': message,
            'payment': {
                'id': payment.id,
                'reference_id': payment.reference_id,
                'student': payment.student.matric_number,
                'amount': float(payment.amount),
                'status': payment.status,
                'verified_by': request.user.get_full_name() if payment.verified_by else None
            }
        })


# ==============================================
# MANUAL REGISTRATION OVERRIDE - ENHANCED
# ==============================================

class ManualRegistrationOverrideViewSet(viewsets.ViewSet):
    """Enhanced manual registration override"""
    permission_classes = [IsAuthenticated, IsDeskOfficer]
    
    @action(detail=False, methods=['post'])
    def manual_registration(self, request):
        """Enhanced manual course registration for students"""
        student_id = request.data.get('student_id')
        course_offering_ids = request.data.get('course_offering_ids', [])
        override_payment = request.data.get('override_payment', False)
        remarks = request.data.get('remarks', '')
        
        if not student_id or not course_offering_ids:
            return Response({'error': 'student_id and course_offering_ids are required'}, status=400)
        
        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            return Response({'error': 'Student not found'}, status=404)
        
        # Get current semester
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            return Response({'error': 'No current semester'}, status=400)
        
        # Check if student can register
        eligibility = self._check_registration_eligibility(student, current_semester, override_payment)
        if not eligibility['can_register'] and not override_payment:
            return Response({
                'error': 'Student not eligible for registration',
                'issues': eligibility['issues']
            }, status=400)
        
        registrations = []
        errors = []
        
        for course_offering_id in course_offering_ids:
            try:
                course_offering = CourseOffering.objects.get(
                    id=course_offering_id,
                    semester=current_semester
                )
                
                # Check if already registered
                # ✅ FIXED: Used CourseRegistration
                if CourseRegistration.objects.filter(
                    student=student,
                    course_offering=course_offering
                ).exists():
                    errors.append(f"Already registered for {course_offering.course.code}")
                    continue
                
                # Check capacity
                if course_offering.enrolled_count >= course_offering.capacity:
                    errors.append(f"Course {course_offering.course.code} capacity reached")
                    continue
                
                # Check prerequisites
                if not self._check_prerequisites(student, course_offering.course):
                    errors.append(f"Prerequisites not met for {course_offering.course.code}")
                    continue
                
                # Create registration
                # ✅ FIXED: Used CourseRegistration
                registration = CourseRegistration.objects.create(
                    student=student,
                    course_offering=course_offering,
                    status='registered',
                    is_payment_verified=True,  # Override payment verification
                    payment_verified_by=request.user,
                    payment_verified_date=timezone.now(),
                    remarks=f"Manual registration by Desk Officer {request.user.get_full_name()}. {remarks}"
                )
                
                # Update enrollment count
                course_offering.enrolled_count += 1
                course_offering.save()
                
                registrations.append({
                    'id': registration.id,
                    'course_code': course_offering.course.code,
                    'course_title': course_offering.course.title,
                    'credits': course_offering.course.credits
                })
                
            except CourseOffering.DoesNotExist:
                errors.append(f"Course offering {course_offering_id} not found")
            except Exception as e:
                errors.append(str(e))
        
        return Response({
            'message': f'Successfully registered {len(registrations)} courses',
            'registrations': registrations,
            'errors': errors,
            'student': {
                'matric_number': student.matric_number,
                'name': student.user.get_full_name(),
                'level': student.level
            }
        })
    
    def _check_registration_eligibility(self, student, semester, override_payment=False):
        """Check if student is eligible for registration"""
        issues = []
        
        # Check if student is active
        if not student.user.is_active:
            issues.append('Student account is inactive')
        
        # Check if fees are paid (unless override)
        if not override_payment:
            try:
                invoice = Invoice.objects.get(
                    student=student,
                    session=semester.session,
                    semester=semester.semester
                )
                if invoice.status != 'paid':
                    issues.append(f'Fees not paid (Status: {invoice.status})')
            except Invoice.DoesNotExist:
                issues.append('No fee invoice found')
        
        # Check if already registered for maximum courses
        # ✅ FIXED: Used CourseRegistration
        current_reg_count = CourseRegistration.objects.filter(
            student=student,
            course_offering__semester=semester,
            status='registered'
        ).count()
        
        max_courses = 6  # Configurable
        if current_reg_count >= max_courses:
            issues.append(f'Already registered for {current_reg_count} courses (max: {max_courses})')
        
        # Check required documents
        required_docs = ['o_level', 'jamb_result', 'medical_report']
        for doc_type in required_docs:
            if not StudentDocument.objects.filter(
                student=student,
                document_type=doc_type,
                status='verified'
            ).exists():
                issues.append(f'Missing verified {doc_type} document')
        
        return {
            'can_register': len(issues) == 0,
            'issues': issues
        }
    
    def _check_prerequisites(self, student, course):
        """Check if student meets course prerequisites"""
        if not course.prerequisites.exists():
            return True
        
        for prereq in course.prerequisites.all():
            # Check if student has passed the prerequisite course
            # ✅ FIXED: Used Grade model properly
            passed = Grade.objects.filter(
                student=student,
                course=prereq,
                grade_letter__in=['A', 'B', 'C', 'D', 'E']  # Passing grades
            ).exists()
            
            if not passed:
                return False
        
        return True
    
    @action(detail=False, methods=['get'])
    def registration_issues(self, request):
        """Get students with registration issues"""
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            return Response({'error': 'No current semester'}, status=400)
        
        # Students without registration
        # ✅ FIXED: Used registrations (related name)
        students_no_reg = Student.objects.filter(
            status='active'
        ).exclude(
            registrations__course_offering__semester=current_semester
        ).select_related('user', 'department')[:50]
        
        # Students with pending payment verification
        # ✅ FIXED: Used registrations (related name)
        students_pending_payment = Student.objects.filter(
            registrations__course_offering__semester=current_semester,
            registrations__is_payment_verified=False
        ).distinct().select_related('user', 'department')[:50]
        
        # Format results
        no_reg_data = [{
            'id': s.id,
            'matric_number': s.matric_number,
            'name': s.user.get_full_name(),
            'level': s.level,
            'department': s.department.name if s.department else None,
            'issue': 'not_registered',
            'email': s.user.email,
            'phone': s.user.phone
        } for s in students_no_reg]
        
        pending_payment_data = [{
            'id': s.id,
            'matric_number': s.matric_number,
            'name': s.user.get_full_name(),
            'level': s.level,
            'department': s.department.name if s.department else None,
            'issue': 'pending_payment',
            'email': s.user.email,
            'phone': s.user.phone
        } for s in students_pending_payment]
        
        return Response({
            'semester': {
                'id': current_semester.id,
                'session': current_semester.session,
                'semester': current_semester.get_semester_display()
            },
            'issues': {
                'not_registered': {
                    'count': len(no_reg_data),
                    'students': no_reg_data
                },
                'pending_payment': {
                    'count': len(pending_payment_data),
                    'students': pending_payment_data
                }
            }
        })


# ==============================================
# MAIN DESK OFFICER API VIEW
# ==============================================

class DeskOfficerAPIView(APIView):
    """Main API view for Desk Officer"""
    permission_classes = [IsAuthenticated, IsDeskOfficer]
    
    def get(self, request):
        """Get desk officer profile and quick stats"""
        user = request.user
        
        # Get current semester
        current_semester = Semester.objects.filter(is_current=True).first()
        
        # Quick statistics
        quick_stats = {
            'pending_documents': StudentDocument.objects.filter(status='pending').count(),
            'open_queries': StudentQuery.objects.filter(status__in=['open', 'in_progress']).count(),
            'pending_payments': Payment.objects.filter(
                status='pending',
                payment_method__in=['cash', 'bank_transfer']
            ).count(),
            # ✅ FIXED: Used CourseRegistration
            'registrations_today': CourseRegistration.objects.filter(
                registration_date__date=timezone.now().date(),
                course_offering__semester=current_semester
            ).count() if current_semester else 0
        }
        
        # Recent activities
        recent_activities = []
        
        # Recent document verifications
        recent_docs = StudentDocument.objects.filter(
            verified_by=user,
            verified_at__date=timezone.now().date()
        )[:5]
        for doc in recent_docs:
            recent_activities.append({
                'type': 'document_verification',
                'action': f'Verified {doc.get_document_type_display()}',
                'student': doc.student.matric_number,
                'time': doc.verified_at,
                'status': doc.status
            })
        
        # Recent query resolutions
        recent_queries = StudentQuery.objects.filter(
            resolved_by=user,
            resolved_at__date=timezone.now().date()
        )[:5]
        for query in recent_queries:
            recent_activities.append({
                'type': 'query_resolution',
                'action': f'Resolved: {query.subject}',
                'student': query.student.matric_number,
                'time': query.resolved_at,
                'status': query.status
            })
        
        return Response({
            'desk_officer': {
                'id': user.id,
                'name': user.get_full_name(),
                'email': user.email,
                'role': user.role,
                'phone': user.phone,
                'last_login': user.last_login
            },
            'current_semester': {
                'id': current_semester.id if current_semester else None,
                'session': current_semester.session if current_semester else None,
                'semester': current_semester.get_semester_display() if current_semester else None,
            },
            'quick_stats': quick_stats,
            'recent_activities': recent_activities
        })