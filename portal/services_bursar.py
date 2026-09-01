"""
Bursar-facing business logic for the Django-template frontend. Ports
finance/views_bursar.py (BursarDashboardViewSet, PaymentVerificationViewSet,
InvoiceManagementViewSet, ReceiptManagementViewSet, FinancialReportsViewSet)
-- not a rewrite. Row-locking (select_for_update) and F()-expression
balance increments are preserved exactly as in the original, matching
the same discipline already verified for the Paystack path in Phase 3.
"""
from datetime import timedelta
from io import BytesIO

import pandas as pd
from django.db import transaction
from django.db.models import F, Sum
from django.http import HttpResponse
from django.utils import timezone

from academics.models import Semester
from finance.models import FeeItem, FeeItemCharge, Invoice, Payment, PaymentReceipt
from users.models import Student


# ---------------------------------------------------------------------------
# Dashboard (BursarDashboardViewSet.overview / revenue_trend)
# ---------------------------------------------------------------------------

def get_dashboard_data():
    current_semester = Semester.objects.filter(is_current=True).first()

    total_revenue = Payment.objects.filter(status='completed').aggregate(Sum('amount'))['amount__sum'] or 0
    pending_payments_count = Payment.objects.filter(status='pending').count()

    cleared_students_count = 0
    if current_semester:
        cleared_students_count = Invoice.objects.filter(
            session=current_semester.session, status='paid',
        ).values('student').distinct().count()

    recent_payments = Payment.objects.select_related('student__user').order_by('-created_at')[:5]

    return {
        'current_semester': current_semester,
        'stats': {
            'total_revenue': total_revenue,
            'pending_payments': pending_payments_count,
            'cleared_students': cleared_students_count,
            'total_invoices': Invoice.objects.count(),
        },
        'recent_payments': recent_payments,
    }


def get_revenue_trend():
    six_months_ago = timezone.now() - timedelta(days=180)
    payments = Payment.objects.filter(
        status='completed', payment_date__gte=six_months_ago,
    ).order_by('payment_date')

    trend_map = {}
    for payment in payments:
        if not payment.payment_date:
            continue
        key = payment.payment_date.strftime('%B %Y')
        trend_map.setdefault(key, {'amount': 0, 'count': 0})
        trend_map[key]['amount'] += float(payment.amount)
        trend_map[key]['count'] += 1
    return [{'period': k, **v} for k, v in trend_map.items()]


# ---------------------------------------------------------------------------
# Manual payment verification (PaymentVerificationViewSet)
# ---------------------------------------------------------------------------

def get_pending_verifications():
    return Payment.objects.filter(status='pending').select_related('student__user', 'invoice').order_by('-created_at')


def verify_payment(payment_id, verifier, action, remarks=''):
    """
    Mirrors PaymentVerificationViewSet.verify_payment exactly: row-locks
    the Payment (and the Invoice, if linked) inside one atomic
    transaction, F()-expression balance increment, same convergence
    point the Paystack path uses (invoice.update_status()).
    Returns (ok, message).
    """
    with transaction.atomic():
        try:
            payment = Payment.objects.select_for_update().get(id=payment_id, status='pending')
        except Payment.DoesNotExist:
            return False, 'Payment not found or already processed.'

        if action == 'verify':
            payment.status = 'completed'
            payment.verified_by = verifier
            payment.payment_date = timezone.now()
            payment.save()

            if payment.invoice:
                invoice = Invoice.objects.select_for_update().get(id=payment.invoice.id)
                invoice.amount_paid = F('amount_paid') + payment.amount
                invoice.save(update_fields=['amount_paid', 'updated_at'])
                invoice.refresh_from_db()
                invoice.update_status()

                from finance.services import FinanceService
                FinanceService.generate_receipt(payment)

            return True, 'Payment verified successfully.'

        elif action == 'reject':
            payment.status = 'failed'
            payment.verified_by = verifier
            payment.remarks = remarks or 'Rejected by bursar'
            payment.save()
            return True, 'Payment rejected.'

        return False, 'Invalid action.'


# ---------------------------------------------------------------------------
# Invoice management (InvoiceManagementViewSet)
# ---------------------------------------------------------------------------

def get_invoices(status=None, search=None):
    invoices = Invoice.objects.select_related('student__user', 'student__department').order_by('-created_at')
    if status:
        invoices = invoices.filter(status=status)
    if search:
        from django.db.models import Q
        invoices = invoices.filter(
            Q(invoice_number__icontains=search) |
            Q(student__matric_number__icontains=search) |
            Q(student__user__first_name__icontains=search) |
            Q(student__user__last_name__icontains=search)
        )
    return invoices


def generate_bulk_invoices(session, semester, level, amount, due_date, description, department_id=None):
    """Mirrors InvoiceManagementViewSet.generate_bulk exactly, including
    the strictly-inside-the-transaction re-check for race safety."""
    filters = {'level': level, 'status': 'active'}
    if department_id and str(department_id) != 'all':
        filters['department_id'] = department_id

    students = Student.objects.filter(**filters)
    if not students.exists():
        return 0, 0, f'No active students found in level {level}.'

    created_count = 0
    skipped_count = 0
    with transaction.atomic():
        for student in students:
            exists_inside = Invoice.objects.filter(student=student, session=session, semester=semester).exists()
            if exists_inside:
                skipped_count += 1
                continue

            inv_num = f"INV-{timezone.now().strftime('%y%m%d')}-{student.id}-{semester}"
            Invoice.objects.create(
                student=student, invoice_number=inv_num, amount=amount, amount_paid=0.00,
                status='pending', session=session, semester=semester, due_date=due_date,
                description=description,
            )
            created_count += 1

    return created_count, skipped_count, None


def mark_invoice_paid(invoice_id):
    try:
        invoice = Invoice.objects.get(id=invoice_id)
    except Invoice.DoesNotExist:
        return None, 'Invoice not found.'
    invoice.amount_paid = invoice.amount
    invoice.save()
    return invoice, None


def set_invoice_installment(invoice_id, amount):
    try:
        invoice = Invoice.objects.get(id=invoice_id)
    except Invoice.DoesNotExist:
        return None, 'Invoice not found.'
    invoice.min_installment_amount = amount
    invoice.allow_part_payment = True
    invoice.save()
    return invoice, None


# ---------------------------------------------------------------------------
# Fee catalog pricing (new for the CHESF Student Portal Digest feature
# work -- no DRF equivalent exists yet; this is the "Bursar-configurable
# fee catalog" the user chose over hardcoded amounts. Nothing here is
# chargeable to students until a FeeItemCharge is both created AND
# is_active -- see FeeItem.current_charge()).
# ---------------------------------------------------------------------------

def get_fee_items():
    return FeeItem.objects.all().order_by('name')


def get_fee_item_charges(fee_item_id=None):
    charges = FeeItemCharge.objects.select_related('fee_item').order_by('-created_at')
    if fee_item_id:
        charges = charges.filter(fee_item_id=fee_item_id)
    return charges


def upsert_fee_item_charge(fee_item_id, session, semester, level, amount):
    """Creates or updates the (fee_item, session, semester, level) charge
    and activates it -- this is the single moment a fee becomes payable."""
    try:
        fee_item = FeeItem.objects.get(id=fee_item_id)
    except FeeItem.DoesNotExist:
        return None, 'Fee item not found.'

    charge, _ = FeeItemCharge.objects.update_or_create(
        fee_item=fee_item, session=session, semester=semester or None, level=level or None,
        defaults={'amount': amount, 'is_active': True},
    )
    return charge, None


def deactivate_fee_item_charge(charge_id):
    try:
        charge = FeeItemCharge.objects.get(id=charge_id)
    except FeeItemCharge.DoesNotExist:
        return False, 'Charge not found.'
    charge.is_active = False
    charge.save(update_fields=['is_active', 'updated_at'])
    return True, None


# ---------------------------------------------------------------------------
# Receipts (ReceiptManagementViewSet)
# ---------------------------------------------------------------------------

def get_recent_receipts():
    return PaymentReceipt.objects.select_related(
        'payment__student__user', 'issued_by',
    ).order_by('-issued_date')[:50]


# ---------------------------------------------------------------------------
# Financial reports (FinancialReportsViewSet.export_revenue)
# ---------------------------------------------------------------------------

def export_revenue_report():
    payments = Payment.objects.filter(status='completed').select_related('student__user')
    data = [{
        'Reference': p.reference_id,
        'Student': p.student.user.get_full_name(),
        'Amount': p.amount,
        'Date': p.payment_date.strftime('%Y-%m-%d') if p.payment_date else '',
    } for p in payments]

    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Revenue', index=False)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="Revenue_Report.xlsx"'
    return response
