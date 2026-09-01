"""
Student dashboard pages -- Phase 3 of the Next.js -> Django templates
migration. See college_cms_frontend_inventory.md for the Next.js pages
these replace, and portal/services_student.py for the ported business
logic (all business rules preserved exactly, including the 2-course
unpaid-registration exception).
"""
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from academics.models import CourseRegistration
from finance.models import FeeItem, Invoice, Payment
from finance.services import FinanceService

from . import services_student as svc
from . import services_support as support_svc
from .decorators import role_required
from .roles import get_nav_items

NAV = [
    {'label': 'Dashboard', 'url_name': 'portal:dashboard_student'},
    {'label': 'My Courses', 'url_name': 'portal:student_courses'},
    {'label': 'Registration', 'url_name': 'portal:student_registration'},
    {'label': 'Results', 'url_name': 'portal:student_results'},
    {'label': 'Transcript', 'url_name': 'portal:student_transcript'},
    {'label': 'Exam Card', 'url_name': 'portal:student_exam_card'},
    {'label': 'Fees', 'url_name': 'portal:student_fees'},
    {'label': 'Fee Catalog', 'url_name': 'portal:student_fee_catalog'},
    {'label': 'Carry-Over', 'url_name': 'portal:student_carryover'},
    {'label': 'Support', 'url_name': 'portal:student_support'},
    {'label': 'Payments', 'url_name': 'portal:student_payments'},
    {'label': 'Settings', 'url_name': 'portal:student_settings'},
]


def _nav(active_url_name):
    items = [dict(item) for item in NAV]
    for item in items:
        item['is_active'] = item['url_name'] == active_url_name
    return items


def _ctx(request, active_url_name, **extra):
    ctx = {'nav_items': _nav(active_url_name), 'student': request.user.student_profile}
    ctx.update(extra)
    return ctx


# ---------------------------------------------------------------------------
# Dashboard overview
# ---------------------------------------------------------------------------

@role_required('student')
def dashboard(request):
    student = request.user.student_profile

    reg_status = svc.get_registration_status(student)
    invoice, invoice_error = FinanceService.get_or_create_current_invoice(student)
    schedule = svc.get_current_schedule(student)
    history = svc.get_academic_history(student)
    payments = Payment.objects.filter(student=student).order_by('-created_at')[:5]

    has_paid = reg_status.get('has_paid_fees') or (invoice and invoice.balance <= 0)
    available_offerings = svc.get_available_offerings(student) if reg_status.get('has_current_semester') else []

    return render(request, 'dashboard/student/dashboard.html', _ctx(
        request, 'portal:dashboard_student',
        page_title='Student Dashboard',
        reg_status=reg_status,
        invoice=invoice,
        invoice_error=invoice_error,
        schedule=schedule,
        total_credits=sum(row['course'].credits for row in schedule),
        history=history,
        payments=payments,
        has_paid=has_paid,
        available_offerings=available_offerings[:8],
        available_offerings_count=len(available_offerings),
        program_status=svc.get_program_status(student),
    ))


# ---------------------------------------------------------------------------
# My Courses
# ---------------------------------------------------------------------------

@role_required('student')
def courses(request):
    student = request.user.student_profile
    schedule = svc.get_current_schedule(student)
    return render(request, 'dashboard/student/courses.html', _ctx(
        request, 'portal:student_courses',
        page_title='My Courses',
        schedule=schedule,
        total_credits=sum(row['course'].credits for row in schedule),
    ))


@role_required('student')
@require_POST
def drop_course(request, registration_id):
    student = request.user.student_profile
    ok, error = svc.drop_course(student, registration_id)
    if ok:
        messages.success(request, 'Course dropped successfully.')
    else:
        messages.error(request, error or 'Failed to drop course.')
    return redirect('portal:student_courses')


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@role_required('student')
def registration(request):
    student = request.user.student_profile
    reg_status = svc.get_registration_status(student)

    if request.method == 'POST':
        offering_ids = request.POST.getlist('course_offering_ids')
        if not offering_ids:
            messages.error(request, 'Select at least one course to register.')
        else:
            successful, errors = svc.register_courses(student, offering_ids)
            if successful:
                messages.success(request, f'{len(successful)} course(s) registered successfully.')
            for err in errors:
                messages.error(request, err)
        return redirect('portal:student_registration')

    offerings = svc.get_available_offerings(student) if reg_status.get('has_current_semester') else []

    return render(request, 'dashboard/student/registration.html', _ctx(
        request, 'portal:student_registration',
        page_title='Course Registration',
        reg_status=reg_status,
        offerings=offerings,
    ))


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------

@role_required('student')
def results(request):
    student = request.user.student_profile
    history = svc.get_academic_history(student)
    return render(request, 'dashboard/student/results.html', _ctx(
        request, 'portal:student_results',
        page_title='My Results',
        history=history,
    ))


# ---------------------------------------------------------------------------
# Transcript
# ---------------------------------------------------------------------------

@role_required('student')
def transcript(request):
    student = request.user.student_profile
    data = svc.get_transcript_data(student)
    return render(request, 'dashboard/student/transcript.html', _ctx(
        request, 'portal:student_transcript',
        page_title='Academic Transcript',
        student_profile=student,
        transcript=data['transcript'],
        summary=data['summary'],
    ))


# ---------------------------------------------------------------------------
# Exam card
# ---------------------------------------------------------------------------

@role_required('student')
def exam_card(request):
    student = request.user.student_profile
    data, error = svc.get_exam_card_data(student)
    return render(request, 'dashboard/student/exam_card.html', _ctx(
        request, 'portal:student_exam_card',
        page_title='Exam Card',
        student_profile=student,
        data=data,
        error=error,
    ))


# ---------------------------------------------------------------------------
# Fees (invoices + fee summary + pay)
# ---------------------------------------------------------------------------

@role_required('student')
def fees(request):
    student = request.user.student_profile
    invoices = student.invoices.all().order_by('-created_at')
    current_invoice, invoice_error = FinanceService.get_or_create_current_invoice(student)

    total_amount = sum(i.amount for i in invoices)
    total_paid = sum(i.amount_paid for i in invoices)

    return render(request, 'dashboard/student/fees.html', _ctx(
        request, 'portal:student_fees',
        page_title='Tuition & Fees',
        invoices=invoices,
        current_invoice=current_invoice,
        invoice_error=invoice_error,
        total_amount=total_amount,
        total_paid=total_paid,
        total_outstanding=total_amount - total_paid,
    ))


@role_required('student')
@require_POST
def pay_invoice(request, invoice_id):
    """
    Initializes a Paystack transaction for one invoice and redirects the
    browser straight to Paystack's hosted checkout -- server-side
    equivalent of the old frontend's financeAPI.initializePayment() +
    window.location.href = authorization_url.
    """
    student = request.user.student_profile
    invoice = get_object_or_404(student.invoices, id=invoice_id)

    amount_raw = request.POST.get('amount', '').strip()
    try:
        amount = float(amount_raw) if amount_raw else float(invoice.balance)
    except ValueError:
        messages.error(request, 'Invalid payment amount.')
        return redirect('portal:student_fees')

    if amount <= 0 or amount > float(invoice.balance):
        messages.error(request, 'Payment amount must be greater than zero and not exceed the balance due.')
        return redirect('portal:student_fees')

    callback_url = request.build_absolute_uri(reverse('portal:student_payment_verify'))
    result = FinanceService.initialize_paystack_transaction(
        user=request.user, invoice=invoice, amount=amount, callback_url=callback_url,
    )

    if result['success']:
        return redirect(result['authorization_url'])

    messages.error(request, result.get('error', 'Payment initialization failed.'))
    return redirect('portal:student_fees')


@role_required('student')
def payment_verify(request):
    """
    Landing page Paystack redirects back to after checkout. Verifies the
    transaction server-side via the same FinanceService used by the JWT
    API and the webhook -- never trusts the client on payment success.

    For the two FeeItems flagged requires_selection (practical, index),
    a successful verification also offers a "next step" link straight to
    the follow-up page -- Practical Fee -> center selection, Index Fee ->
    the index information form -- per the CHESF Student Portal Digest.
    """
    reference = request.GET.get('reference') or request.GET.get('trxref')
    if not reference:
        return render(request, 'dashboard/student/payment_verify.html', _ctx(
            request, 'portal:student_fees',
            page_title='Payment Verification',
            status='error', message='No payment reference found in the URL.',
        ))

    result = FinanceService.verify_paystack_transaction(reference)
    if result['success']:
        next_step = None
        payment = Payment.objects.filter(
            paystack_reference=reference,
        ).select_related('invoice__fee_item').first()
        if payment and payment.invoice and payment.invoice.fee_item:
            fee_code = payment.invoice.fee_item.code
            if fee_code == 'practical':
                next_step = {'label': 'Select Your Practical Center', 'url': reverse('portal:student_practical_center')}
            elif fee_code == 'index':
                next_step = {'label': 'Submit Index Information', 'url': reverse('portal:student_index_info')}

        return render(request, 'dashboard/student/payment_verify.html', _ctx(
            request, 'portal:student_fees',
            page_title='Payment Verification',
            status='success', message=result['message'], next_step=next_step,
        ))

    return render(request, 'dashboard/student/payment_verify.html', _ctx(
        request, 'portal:student_fees',
        page_title='Payment Verification',
        status='error', message=result.get('error', 'Payment verification failed.'),
    ))


# ---------------------------------------------------------------------------
# Fee catalog (16-item named fee list -- CHESF Student Portal Digest)
# ---------------------------------------------------------------------------

@role_required('student')
def fee_catalog(request):
    student = request.user.student_profile
    catalog = svc.get_fee_catalog(student)
    return render(request, 'dashboard/student/fee_catalog.html', _ctx(
        request, 'portal:student_fee_catalog',
        page_title='Fee Catalog',
        catalog=catalog,
    ))


@role_required('student')
@require_POST
def pay_fee_item(request, fee_item_id):
    """
    Same reuse-the-existing-Paystack-pipeline approach as pay_invoice:
    lazily gets or creates the one pending invoice for this
    (student, fee_item, session), then hands off straight to Paystack.
    Fee-item invoices aren't part-payable, so there's no amount field --
    the full current_charge() amount is what gets charged.
    """
    student = request.user.student_profile
    fee_item = get_object_or_404(FeeItem, id=fee_item_id, is_active=True)
    current_semester, _ = svc.get_student_semester(student)

    if not current_semester:
        messages.error(request, 'No active semester found.')
        return redirect('portal:student_fee_catalog')

    charge = fee_item.current_charge(
        session=current_semester.session,
        semester=current_semester.semester,
        level=student.level,
    )
    if not charge or charge.amount <= 0:
        messages.error(request, f'{fee_item.name} is not yet available for payment. Contact the Bursar.')
        return redirect('portal:student_fee_catalog')

    invoice = FinanceService.get_or_create_fee_item_invoice(
        student, fee_item, current_semester.session, current_semester.semester, charge.amount,
    )
    if invoice.status == 'paid':
        messages.info(request, f'{fee_item.name} is already paid.')
        return redirect('portal:student_fee_catalog')

    callback_url = request.build_absolute_uri(reverse('portal:student_payment_verify'))
    result = FinanceService.initialize_paystack_transaction(
        user=request.user, invoice=invoice, amount=float(invoice.balance), callback_url=callback_url,
    )

    if result['success']:
        return redirect(result['authorization_url'])

    messages.error(request, result.get('error', 'Payment initialization failed.'))
    return redirect('portal:student_fee_catalog')


# ---------------------------------------------------------------------------
# Practical center selection + Index information (post-payment follow-ups)
# ---------------------------------------------------------------------------

@role_required('student')
def practical_center(request):
    student = request.user.student_profile
    if request.method == 'POST':
        ok, message = svc.select_practical_center(student, request.POST.get('center_id'))
        (messages.success if ok else messages.error)(request, message)
        return redirect('portal:student_practical_center')

    return render(request, 'dashboard/student/practical_center.html', _ctx(
        request, 'portal:student_practical_center',
        page_title='Practical Center',
        **svc.get_practical_center_status(student),
    ))


@role_required('student')
def index_info(request):
    student = request.user.student_profile
    if request.method == 'POST':
        info, error = svc.save_index_info(student, request.POST, request.FILES.get('passport_photo'))
        (messages.error if error else messages.success)(request, error or 'Index information saved.')
        return redirect('portal:student_index_info')

    return render(request, 'dashboard/student/index_info.html', _ctx(
        request, 'portal:student_index_info',
        page_title='Index Information',
        **svc.get_index_info_status(student),
    ))


# ---------------------------------------------------------------------------
# Carry-over courses
# ---------------------------------------------------------------------------

@role_required('student')
def carryover(request):
    student = request.user.student_profile
    data = svc.get_carryover_status(student)
    return render(request, 'dashboard/student/carryover.html', _ctx(
        request, 'portal:student_carryover',
        page_title='Carry-Over Courses',
        current_semester=data['current_semester'],
        rows=data['rows'],
    ))


@role_required('student')
@require_POST
def register_carryover(request, course_id):
    student = request.user.student_profile
    ok, message = svc.register_carryover_course(student, course_id)
    (messages.success if ok else messages.error)(request, message)
    return redirect('portal:student_carryover')


@role_required('student')
def carryover_slip(request, registration_id):
    student = request.user.student_profile
    # Ownership enforced via student= filter (IDOR prevention), same
    # pattern as receipt() below.
    registration = get_object_or_404(CourseRegistration, id=registration_id, student=student)
    invoice = Invoice.objects.filter(
        student=student, course_registration=registration,
    ).order_by('-created_at').first()
    return render(request, 'dashboard/student/carryover_slip.html', {
        'student': student,
        'registration': registration,
        'invoice': invoice,
    })


# ---------------------------------------------------------------------------
# Support chat
# ---------------------------------------------------------------------------

@role_required('student')
def support(request):
    student = request.user.student_profile
    thread = support_svc.get_or_create_thread(student)
    support_svc.mark_read(thread, request.user)
    return render(request, 'dashboard/student/support.html', _ctx(
        request, 'portal:student_support',
        page_title='Support',
        thread=thread,
        chat_messages=support_svc.get_messages(thread),
    ))


@role_required('student')
def support_poll(request):
    student = request.user.student_profile
    thread = support_svc.get_or_create_thread(student)
    msgs = support_svc.get_messages(thread, after_id=request.GET.get('after'))
    payload = [support_svc.serialize_message(m, request.user) for m in msgs]
    support_svc.mark_read(thread, request.user)
    return JsonResponse({'messages': payload, 'is_closed': thread.is_closed})


@role_required('student')
@require_POST
def support_send(request):
    student = request.user.student_profile
    thread = support_svc.get_or_create_thread(student)
    message, error = support_svc.post_message(thread, request.user, request.POST.get('body', ''))
    if error:
        return JsonResponse({'error': error}, status=400)
    return JsonResponse({'message': support_svc.serialize_message(message, request.user)})


# ---------------------------------------------------------------------------
# Payments (history + receipts)
# ---------------------------------------------------------------------------

@role_required('student')
def payments(request):
    student = request.user.student_profile
    payment_list = Payment.objects.filter(student=student).select_related('invoice').order_by('-created_at')
    return render(request, 'dashboard/student/payments.html', _ctx(
        request, 'portal:student_payments',
        page_title='Payment History',
        payments=payment_list,
    ))


@role_required('student')
def receipt(request, payment_id):
    student = request.user.student_profile
    # Ownership enforced via the student's own related_name -- never trust
    # the URL id alone (IDOR prevention).
    payment = get_object_or_404(Payment, id=payment_id, student=student, status='completed')
    return render(request, 'dashboard/student/receipt.html', {
        'payment': payment,
        'student': student,
    })


# ---------------------------------------------------------------------------
# Print schedule
# ---------------------------------------------------------------------------

@role_required('student')
def print_schedule(request):
    student = request.user.student_profile
    schedule = svc.get_current_schedule(student)
    current_semester, _ = svc.get_student_semester(student)
    return render(request, 'dashboard/student/print_schedule.html', {
        'student': student,
        'schedule': schedule,
        'total_credits': sum(row['course'].credits for row in schedule),
        'current_semester': current_semester,
    })


# ---------------------------------------------------------------------------
# Settings (change password)
# ---------------------------------------------------------------------------

@role_required('student')
def settings_view(request):
    student = request.user.student_profile
    if request.method == 'POST':
        form = PasswordChangeForm(user=request.user, data=request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # keep the student logged in
            messages.success(request, 'Password changed successfully.')
            return redirect('portal:student_settings')
    else:
        form = PasswordChangeForm(user=request.user)

    return render(request, 'dashboard/student/settings.html', _ctx(
        request, 'portal:student_settings',
        page_title='Account Settings',
        form=form,
        program_status=svc.get_program_status(student),
    ))
