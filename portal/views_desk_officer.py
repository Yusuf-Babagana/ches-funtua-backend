"""
Desk Officer dashboard pages -- Phase 9 of the Next.js -> Django
templates migration. See portal/services_desk_officer.py for the ported
business logic and an important note: unlike every other phase, the old
frontend's desk-officer pages were non-functional placeholders (empty
state, no fetch calls, dead buttons), so every page here is a genuine
working implementation of real, already-existing backend functionality
rather than a like-for-like reproduction.
"""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from academics.models import Department
from users.models import Student

from . import services_desk_officer as svc
from .decorators import role_required

NAV = [
    {'label': 'Dashboard', 'url_name': 'portal:dashboard_desk_officer'},
    {'label': 'Student Search', 'url_name': 'portal:do_students'},
    {'label': 'Documents', 'url_name': 'portal:do_documents'},
    {'label': 'Queries', 'url_name': 'portal:do_queries'},
    {'label': 'Payments', 'url_name': 'portal:do_payments'},
    {'label': 'Manual Registration', 'url_name': 'portal:do_registration'},
]


def _nav(active_url_name):
    items = [dict(item) for item in NAV]
    for item in items:
        item['is_active'] = item['url_name'] == active_url_name
    return items


@role_required('desk-officer')
def dashboard(request):
    data = svc.get_dashboard_data(request.user)
    return render(request, 'dashboard/desk_officer/dashboard.html', {
        'nav_items': _nav('portal:dashboard_desk_officer'),
        'page_title': 'Desk Officer Dashboard',
        **data,
    })


@role_required('desk-officer')
def students(request):
    query = request.GET.get('q', '').strip()
    results = svc.search_students(
        query=query or None,
        department_id=request.GET.get('department') or None,
        level=request.GET.get('level') or None,
    )
    return render(request, 'dashboard/desk_officer/students.html', {
        'nav_items': _nav('portal:do_students'),
        'page_title': 'Student Search',
        'query': query,
        'results': results,
        'departments': Department.objects.all().order_by('name'),
        'filters': request.GET,
    })


@role_required('desk-officer')
def student_profile(request, student_id):
    profile = svc.get_student_profile(student_id)
    if profile is None:
        messages.error(request, 'Student not found.')
        return redirect('portal:do_students')
    return render(request, 'dashboard/desk_officer/student_profile.html', {
        'nav_items': _nav('portal:do_students'),
        'page_title': profile['student'].user.get_full_name(),
        **profile,
    })


@role_required('desk-officer')
def documents(request):
    pending = svc.get_pending_documents()
    return render(request, 'dashboard/desk_officer/documents.html', {
        'nav_items': _nav('portal:do_documents'),
        'page_title': 'Document Verification',
        'pending': pending,
    })


@role_required('desk-officer')
@require_POST
def verify_document(request, document_id):
    action = request.POST.get('action')
    remarks = request.POST.get('remarks', '')
    ok, message = svc.verify_document(document_id, request.user, action, remarks)
    (messages.success if ok else messages.error)(request, message)
    return redirect('portal:do_documents')


@role_required('desk-officer')
def queries(request):
    view = request.GET.get('view', 'open')
    query_list = svc.get_my_queries(request.user) if view == 'mine' else svc.get_open_queries()
    return render(request, 'dashboard/desk_officer/queries.html', {
        'nav_items': _nav('portal:do_queries'),
        'page_title': 'Student Queries',
        'queries': query_list,
        'view': view,
    })


@role_required('desk-officer')
@require_POST
def assign_query(request, query_id):
    ok, message = svc.assign_query_to_me(query_id, request.user)
    (messages.success if ok else messages.error)(request, message)
    return redirect('portal:do_queries')


@role_required('desk-officer')
@require_POST
def resolve_query(request, query_id):
    notes = request.POST.get('resolution_notes', '').strip()
    ok, message = svc.resolve_query(query_id, request.user, notes)
    (messages.success if ok else messages.error)(request, message)
    return redirect('portal:do_queries')


@role_required('desk-officer')
def payments(request):
    pending = svc.get_pending_manual_payments()
    return render(request, 'dashboard/desk_officer/payments.html', {
        'nav_items': _nav('portal:do_payments'),
        'page_title': 'Payment Verification',
        'pending': pending,
    })


@role_required('desk-officer')
@require_POST
def verify_payment(request, payment_id):
    action = request.POST.get('action')
    remarks = request.POST.get('remarks', '')
    ok, message = svc.verify_manual_payment(payment_id, request.user, action, remarks)
    (messages.success if ok else messages.error)(request, message)
    return redirect('portal:do_payments')


@role_required('desk-officer')
def registration(request):
    student = None
    offerings = []
    issues = []
    student_id = request.GET.get('student_id')

    if request.method == 'POST':
        student_id = request.POST.get('student_id')
        student = get_object_or_404(Student, id=student_id)
        offering_ids = request.POST.getlist('course_offering_ids')
        override_payment = request.POST.get('override_payment') == 'on'
        remarks = request.POST.get('remarks', '')

        if not offering_ids:
            messages.error(request, 'Select at least one course.')
        else:
            successful, errors = svc.manual_registration(
                student_id, offering_ids, request.user, override_payment, remarks,
            )
            if successful is None:
                for issue in errors:
                    messages.error(request, issue)
            else:
                if successful:
                    messages.success(request, f'Registered {len(successful)} course(s) for {student.user.get_full_name()}.')
                for err in errors:
                    messages.error(request, err)
        return redirect(f"{request.path}?student_id={student_id}")

    search_query = request.GET.get('q', '').strip()
    search_results = None

    if student_id:
        student = get_object_or_404(Student, id=student_id)
        semester = svc.get_current_semester()
        if semester:
            issues = svc.check_registration_eligibility(student, semester)
            offerings = svc.get_available_offerings_for_student(student, semester)
    elif search_query:
        search_results = svc.search_students(query=search_query)

    return render(request, 'dashboard/desk_officer/registration.html', {
        'nav_items': _nav('portal:do_registration'),
        'page_title': 'Manual Course Registration',
        'student': student,
        'search_query': search_query,
        'search_results': search_results,
        'offerings': offerings,
        'issues': issues,
        'max_courses': svc.MAX_MANUAL_COURSES,
    })
