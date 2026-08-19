"""
Desk Officer-facing business logic for the Django-template frontend.
Ports academics/views_desk_officer.py (DeskOfficerViewSet,
StudentManagementViewSet, DocumentVerificationViewSet,
StudentQueryViewSet, PaymentVerificationViewSet,
ManualRegistrationOverrideViewSet) -- not a rewrite.

Important context this phase differs from every other phase in: the old
Next.js frontend's desk-officer pages are not merely incomplete, they
are non-functional placeholders by their own admission. The dashboard
page's fetch function is literally named to simulate an API call and
comments "Since we don't have specific endpoints yet, we'll use
placeholder data" -- even though every one of those endpoints already
exists and works (DeskOfficerViewSet.dashboard, PaymentVerificationViewSet,
etc.). The payments and registration pages never call any fetch at all;
their state arrays stay permanently empty and their action buttons have
no onClick handlers. Per the same principle already applied in Phase 4
(lecturer attendance) and Phase 6 (registrar student records) -- build
the real, working feature the backend already fully implements, not the
broken placeholder -- every page in this phase is a genuine, working
implementation rather than a reproduction of empty UI shells.

Manual registration override now shares the same credit-unit ceiling as
the student self-service path and the DRF API (see academics/constants.py)
instead of its own flat 6-course cap -- that three-way inconsistency (2
unpaid / 15 paid self-service vs. 6 desk-officer, see migration inventory
S6.1) is exactly what the credit-unit rule change replaces. Since the
desk officer's override path can bypass the payment gate, it enforces
the higher (paid) ceiling regardless of override_payment.
"""
from django.db.models import Count, Q, Sum
from django.utils import timezone

from academics.constants import MAX_CREDIT_UNITS_PAID
from academics.models import (
    Course, CourseOffering, CourseRegistration, Department, Grade,
    Semester, StudentDocument, StudentQuery,
)
from finance.models import Invoice, Payment
from users.models import Student

REQUIRED_DOCS_FOR_REGISTRATION = ['o_level', 'jamb_result', 'medical_report']


def get_current_semester():
    return Semester.objects.filter(is_current=True).first()


# ---------------------------------------------------------------------------
# Dashboard (DeskOfficerViewSet.dashboard)
# ---------------------------------------------------------------------------

def get_dashboard_data(user):
    current_semester = get_current_semester()

    total_registrations = 0
    pending_verifications = 0
    students_without_registration = 0
    todays_registrations = 0
    if current_semester:
        total_registrations = CourseRegistration.objects.filter(
            course_offering__semester=current_semester, status='registered',
        ).count()
        pending_verifications = CourseRegistration.objects.filter(
            course_offering__semester=current_semester, is_payment_verified=False,
        ).count()
        students_without_registration = Student.objects.filter(status='active').exclude(
            registrations__course_offering__semester=current_semester,
            registrations__status='registered',
        ).count()
        todays_registrations = CourseRegistration.objects.filter(
            registration_date__date=timezone.now().date(),
            course_offering__semester=current_semester,
        ).count()

    pending_documents = StudentDocument.objects.filter(status='pending').count()
    open_queries = StudentQuery.objects.filter(status__in=['open', 'in_progress']).count()
    assigned_queries = StudentQuery.objects.filter(
        assigned_to=user, status__in=['open', 'in_progress'],
    ).count()
    pending_payments = Payment.objects.filter(
        status='pending', payment_method__in=['cash', 'bank_transfer'],
    ).count()

    today = timezone.now().date()
    return {
        'current_semester': current_semester,
        'stats': {
            'total_registrations': total_registrations,
            'pending_payment_verifications': pending_verifications,
            'students_without_registration': students_without_registration,
            'pending_documents': pending_documents,
            'open_queries': open_queries,
            'pending_payments': pending_payments,
        },
        'assigned_to_me': {
            'queries': assigned_queries,
            'documents_today': StudentDocument.objects.filter(verified_by=user, verified_at__date=today).count(),
        },
        'today_activities': {
            'registrations': todays_registrations,
            'queries_created': StudentQuery.objects.filter(created_at__date=today).count(),
            'documents_uploaded': StudentDocument.objects.filter(uploaded_at__date=today).count(),
        },
    }


# ---------------------------------------------------------------------------
# Student search / profile (StudentManagementViewSet)
# ---------------------------------------------------------------------------

def search_students(query=None, department_id=None, level=None):
    if not query and not department_id and not level:
        return None  # caller renders the "enter a search term" empty state

    students = Student.objects.select_related('user', 'department')
    if query:
        students = students.filter(
            Q(matric_number__icontains=query) | Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) | Q(user__email__icontains=query) |
            Q(user__phone__icontains=query)
        )
    if department_id:
        students = students.filter(department_id=department_id)
    if level:
        students = students.filter(level=level)

    current_semester = get_current_semester()
    results = []
    for student in students[:50]:
        registration = None
        invoice_paid = False
        if current_semester:
            registration = CourseRegistration.objects.filter(
                student=student, course_offering__semester=current_semester,
            ).first()
            invoice = Invoice.objects.filter(
                student=student, session=current_semester.session, semester=current_semester.semester,
            ).first()
            invoice_paid = bool(invoice and invoice.status == 'paid')

        results.append({
            'student': student,
            'registration_status': registration.status if registration else 'not_registered',
            'payment_status': 'paid' if invoice_paid else 'pending',
            'pending_documents': StudentDocument.objects.filter(student=student, status='pending').count(),
            'open_queries': StudentQuery.objects.filter(student=student, status__in=['open', 'in_progress']).count(),
        })
    return results


def get_student_profile(student_id):
    student = Student.objects.select_related('user', 'department').filter(id=student_id).first()
    if not student:
        return None

    current_semester = get_current_semester()
    registrations = []
    if current_semester:
        registrations = CourseRegistration.objects.filter(
            student=student, course_offering__semester=current_semester,
        ).select_related('course_offering__course')

    return {
        'student': student,
        'current_semester': current_semester,
        'registrations': registrations,
        'invoices': Invoice.objects.filter(student=student).order_by('-created_at')[:5],
        'payments': Payment.objects.filter(student=student).order_by('-created_at')[:10],
        'documents': StudentDocument.objects.filter(student=student).order_by('-uploaded_at'),
        'queries': StudentQuery.objects.filter(student=student).order_by('-created_at')[:10],
        'academic_history': Grade.objects.filter(student=student).select_related('course').order_by('-session', '-semester')[:10],
    }


# ---------------------------------------------------------------------------
# Document verification (DocumentVerificationViewSet)
# ---------------------------------------------------------------------------

def get_pending_documents():
    return StudentDocument.objects.filter(status='pending').select_related(
        'student__user', 'student__department',
    ).order_by('uploaded_at')


def verify_document(document_id, verifier, action, remarks=''):
    try:
        document = StudentDocument.objects.get(id=document_id, status='pending')
    except StudentDocument.DoesNotExist:
        return False, 'Document not found or already processed.'

    if action not in ['verified', 'rejected', 'requires_update']:
        return False, 'Invalid action.'
    if action in ['rejected', 'requires_update'] and not remarks:
        return False, 'Remarks are required for rejection or update requests.'

    document.status = action
    document.remarks = remarks
    document.verified_by = verifier
    document.verified_at = timezone.now()
    document.save()
    return True, f'Document marked as {document.get_status_display()}.'


# ---------------------------------------------------------------------------
# Student queries (StudentQueryViewSet)
# ---------------------------------------------------------------------------

def get_open_queries():
    return StudentQuery.objects.filter(status__in=['open', 'in_progress']).select_related(
        'student__user', 'student__department', 'assigned_to',
    ).order_by('-priority', 'created_at')


def get_my_queries(user):
    return StudentQuery.objects.filter(
        assigned_to=user, status__in=['open', 'in_progress'],
    ).select_related('student__user', 'student__department').order_by('created_at')


def assign_query_to_me(query_id, user):
    try:
        query = StudentQuery.objects.get(id=query_id)
    except StudentQuery.DoesNotExist:
        return False, 'Query not found.'
    if query.assigned_to and query.assigned_to != user:
        return False, 'Query is already assigned to another officer.'
    query.assigned_to = user
    query.status = 'in_progress'
    query.save()
    return True, 'Query assigned to you.'


def resolve_query(query_id, user, resolution_notes):
    try:
        query = StudentQuery.objects.get(id=query_id, assigned_to=user)
    except StudentQuery.DoesNotExist:
        return False, 'Query not found or not assigned to you.'
    if not resolution_notes:
        return False, 'Resolution notes are required.'
    query.status = 'resolved'
    query.resolution_notes = resolution_notes
    query.resolved_by = user
    query.resolved_at = timezone.now()
    query.save()
    return True, 'Query resolved.'


def create_query_for_student(student_id, query_type, subject, description, priority, officer):
    try:
        student = Student.objects.get(id=student_id)
    except Student.DoesNotExist:
        return None, 'Student not found.'
    query = StudentQuery.objects.create(
        student=student, query_type=query_type, subject=subject, description=description,
        priority=priority, assigned_to=officer, status='in_progress',
    )
    return query, None


# ---------------------------------------------------------------------------
# Manual payment verification (PaymentVerificationViewSet)
# ---------------------------------------------------------------------------

def _check_payment_evidence(payment):
    if payment.payment_method == 'bank_transfer':
        return bool(payment.transaction_reference)
    elif payment.payment_method == 'cash':
        return bool(payment.description and 'cash' in payment.description.lower())
    return False


def get_pending_manual_payments():
    payments = Payment.objects.filter(
        status='pending', payment_method__in=['cash', 'bank_transfer'],
    ).select_related('student__user', 'student__department', 'invoice')
    for p in payments:
        p.has_evidence = _check_payment_evidence(p)
    return payments


def verify_manual_payment(payment_id, officer, action, remarks=''):
    try:
        payment = Payment.objects.get(id=payment_id, status='pending')
    except Payment.DoesNotExist:
        return False, 'Payment not found or already processed.'

    if action == 'verify':
        if not _check_payment_evidence(payment):
            return False, 'Insufficient payment evidence (missing transaction reference or cash description).'
        payment.status = 'completed'
        payment.verified_by = officer
        payment.payment_date = timezone.now()
        payment.remarks = f"Verified by Desk Officer {officer.get_full_name()}. {remarks}".strip()
        payment.save()

        if payment.invoice:
            from django.db.models import F
            invoice = Invoice.objects.select_for_update().get(id=payment.invoice_id)
            invoice.amount_paid = F('amount_paid') + payment.amount
            invoice.save(update_fields=['amount_paid', 'updated_at'])
            invoice.refresh_from_db()
            invoice.update_status()
            from finance.services import FinanceService
            FinanceService.generate_receipt(payment)

        return True, 'Payment verified successfully.'
    elif action == 'reject':
        if not remarks:
            return False, 'Remarks are required when rejecting a payment.'
        payment.status = 'failed'
        payment.remarks = f"Rejected by Desk Officer {officer.get_full_name()}. Reason: {remarks}"
        payment.save()
        return True, 'Payment rejected.'
    return False, 'Invalid action.'


# ---------------------------------------------------------------------------
# Manual registration override (ManualRegistrationOverrideViewSet)
# ---------------------------------------------------------------------------

def check_registration_eligibility(student, semester, override_payment=False):
    issues = []
    if not student.user.is_active:
        issues.append('Student account is inactive.')

    if not override_payment:
        invoice = Invoice.objects.filter(
            student=student, session=semester.session, semester=semester.semester,
        ).first()
        if not invoice:
            issues.append('No fee invoice found.')
        elif invoice.status != 'paid':
            issues.append(f'Fees not paid (status: {invoice.get_status_display()}).')

    current_credit_units = CourseRegistration.objects.filter(
        student=student, course_offering__semester=semester, status='registered',
    ).aggregate(total=Sum('course_offering__course__credits'))['total'] or 0
    if current_credit_units >= MAX_CREDIT_UNITS_PAID:
        issues.append(f'Already registered for {current_credit_units} credit units (max: {MAX_CREDIT_UNITS_PAID}).')

    for doc_type in REQUIRED_DOCS_FOR_REGISTRATION:
        if not StudentDocument.objects.filter(student=student, document_type=doc_type, status='verified').exists():
            issues.append(f'Missing verified {doc_type.replace("_", " ")} document.')

    return issues


def _check_prerequisites(student, course):
    for prereq in course.prerequisites.all():
        if not Grade.objects.filter(
            student=student, course=prereq, grade_letter__in=['A', 'B', 'C', 'D', 'E'],
        ).exists():
            return False
    return True


def manual_registration(student_id, course_offering_ids, officer, override_payment=False, remarks=''):
    try:
        student = Student.objects.get(id=student_id)
    except Student.DoesNotExist:
        return None, ['Student not found.']

    semester = get_current_semester()
    if not semester:
        return None, ['No current semester set.']

    issues = check_registration_eligibility(student, semester, override_payment)
    if issues and not override_payment:
        return None, issues

    running_credit_units = CourseRegistration.objects.filter(
        student=student, course_offering__semester=semester, status='registered',
    ).aggregate(total=Sum('course_offering__course__credits'))['total'] or 0

    successful, errors = [], []
    from django.db import transaction
    with transaction.atomic():
        for offering_id in course_offering_ids:
            try:
                offering = CourseOffering.objects.get(id=offering_id, semester=semester)
            except CourseOffering.DoesNotExist:
                errors.append(f'Course offering {offering_id} not found.')
                continue

            if CourseRegistration.objects.filter(student=student, course_offering=offering).exists():
                errors.append(f'Already registered for {offering.course.code}.')
                continue
            if offering.enrolled_count >= offering.capacity:
                errors.append(f'{offering.course.code}: capacity reached.')
                continue
            if not _check_prerequisites(student, offering.course):
                errors.append(f'{offering.course.code}: prerequisites not met.')
                continue
            if running_credit_units + offering.course.credits > MAX_CREDIT_UNITS_PAID:
                errors.append(f'{offering.course.code}: would exceed the {MAX_CREDIT_UNITS_PAID}-credit-unit limit.')
                continue

            reg = CourseRegistration.objects.create(
                student=student, course_offering=offering, status='registered',
                is_payment_verified=True, payment_verified_by=officer, payment_verified_date=timezone.now(),
                remarks=f"Manual registration by Desk Officer {officer.get_full_name()}. {remarks}".strip(),
            )
            offering.enrolled_count += 1
            offering.save()
            running_credit_units += offering.course.credits
            successful.append(reg)

    return successful, errors


def get_available_offerings_for_student(student, semester):
    """Offerings the student isn't already registered for, for the manual-registration form."""
    existing = CourseRegistration.objects.filter(
        student=student, course_offering__semester=semester,
    ).values_list('course_offering_id', flat=True)
    return CourseOffering.objects.filter(semester=semester, is_active=True).exclude(
        id__in=existing,
    ).select_related('course', 'course__department', 'lecturer__user')
