"""
Bursar dashboard pages -- Phase 7 of the Next.js -> Django templates
migration. See portal/services_bursar.py for the ported business logic.
"""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from academics.models import Department

from . import services_bursar as svc
from .decorators import role_required

NAV = [
    {'label': 'Dashboard', 'url_name': 'portal:dashboard_bursar'},
    {'label': 'Invoices', 'url_name': 'portal:bursar_invoices'},
    {'label': 'Verify Payments', 'url_name': 'portal:bursar_verify_payments'},
    {'label': 'Receipts', 'url_name': 'portal:bursar_receipts'},
]


def _nav(active_url_name):
    items = [dict(item) for item in NAV]
    for item in items:
        item['is_active'] = item['url_name'] == active_url_name
    return items


@role_required('bursar')
def dashboard(request):
    data = svc.get_dashboard_data()
    return render(request, 'dashboard/bursar/dashboard.html', {
        'nav_items': _nav('portal:dashboard_bursar'),
        'page_title': 'Bursar Dashboard',
        **data,
    })


@role_required('bursar')
def invoices(request):
    if request.method == 'POST':
        # Bulk generation form submit
        session = request.POST.get('session', '').strip()
        semester = request.POST.get('semester', '').strip()
        level = request.POST.get('level', '').strip()
        department_id = request.POST.get('department_id', 'all')
        amount_raw = request.POST.get('amount', '').strip()
        due_date = request.POST.get('due_date', '').strip()
        description = request.POST.get('description', 'Tuition Fee').strip()

        if not all([session, semester, level, amount_raw, due_date]):
            messages.error(request, 'Session, Semester, Level, Amount, and Due Date are required.')
            return redirect('portal:bursar_invoices')

        try:
            amount = float(amount_raw)
        except ValueError:
            messages.error(request, 'Invalid amount format.')
            return redirect('portal:bursar_invoices')

        created, skipped, error = svc.generate_bulk_invoices(
            session, semester, level, amount, due_date, description, department_id,
        )
        if error:
            messages.error(request, error)
        else:
            messages.success(request, f'Generated {created} invoice(s), skipped {skipped} (already existed).')
        return redirect('portal:bursar_invoices')

    invoice_list = svc.get_invoices(
        status=request.GET.get('status') or None,
        search=request.GET.get('search') or None,
    )
    return render(request, 'dashboard/bursar/invoices.html', {
        'nav_items': _nav('portal:bursar_invoices'),
        'page_title': 'Invoice Management',
        'invoices': invoice_list,
        'departments': Department.objects.all().order_by('name'),
        'filters': request.GET,
    })


@role_required('bursar')
@require_POST
def mark_invoice_paid(request, invoice_id):
    invoice, error = svc.mark_invoice_paid(invoice_id)
    if error:
        messages.error(request, error)
    else:
        messages.success(request, f'Invoice {invoice.invoice_number} marked as PAID.')
    return redirect('portal:bursar_invoices')


@role_required('bursar')
@require_POST
def set_installment(request, invoice_id):
    amount_raw = request.POST.get('min_installment_amount', '').strip()
    if not amount_raw:
        messages.error(request, 'Amount is required.')
        return redirect('portal:bursar_invoices')
    try:
        amount = float(amount_raw)
    except ValueError:
        messages.error(request, 'Invalid amount.')
        return redirect('portal:bursar_invoices')

    invoice, error = svc.set_invoice_installment(invoice_id, amount)
    if error:
        messages.error(request, error)
    else:
        messages.success(request, f'Installment of {amount:,.2f} set for {invoice.invoice_number}.')
    return redirect('portal:bursar_invoices')


@role_required('bursar')
def verify_payments(request):
    pending = svc.get_pending_verifications()
    return render(request, 'dashboard/bursar/verify_payments.html', {
        'nav_items': _nav('portal:bursar_verify_payments'),
        'page_title': 'Manual Payment Verification',
        'pending': pending,
    })


@role_required('bursar')
@require_POST
def verify_payment_action(request, payment_id):
    action = request.POST.get('action')
    remarks = request.POST.get('remarks', '')
    ok, message = svc.verify_payment(payment_id, request.user, action, remarks)
    (messages.success if ok else messages.error)(request, message)
    return redirect('portal:bursar_verify_payments')


@role_required('bursar')
def receipts(request):
    receipt_list = svc.get_recent_receipts()
    return render(request, 'dashboard/bursar/receipts.html', {
        'nav_items': _nav('portal:bursar_receipts'),
        'page_title': 'Receipt History',
        'receipts': receipt_list,
    })


@role_required('bursar')
def export_revenue(request):
    return svc.export_revenue_report()
