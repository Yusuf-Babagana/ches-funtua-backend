"""
Exam Officer dashboard pages -- Phase 8 of the Next.js -> Django
templates migration. See portal/services_exam_officer.py for the ported
business logic and important notes on what was deliberately NOT ported
(the fake, non-persistent exam timetable; a loose verify path that
could skip HOD approval; and the unused-by-any-page exam list feature).
"""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import services_exam_officer as svc
from .decorators import role_required

NAV = [
    {'label': 'Dashboard', 'url_name': 'portal:dashboard_exam_officer'},
    {'label': 'Registration Approvals', 'url_name': 'portal:eo_registrations'},
    {'label': 'Result Compilation', 'url_name': 'portal:eo_results'},
]


def _nav(active_url_name):
    items = [dict(item) for item in NAV]
    for item in items:
        item['is_active'] = item['url_name'] == active_url_name
    return items


@role_required('exam-officer')
def dashboard(request):
    data = svc.get_dashboard_data()
    return render(request, 'dashboard/exam_officer/dashboard.html', {
        'nav_items': _nav('portal:dashboard_exam_officer'),
        'page_title': 'Examination Office',
        **data,
    })


@role_required('exam-officer')
def registrations(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        reason = request.POST.get('reason', '')
        reg_ids = request.POST.getlist('registration_ids')

        if reg_ids:
            successful, failed = svc.bulk_approve_registrations(reg_ids, request.user, action, reason)
            if successful:
                verb = 'approved' if action == 'approve' else 'rejected'
                messages.success(request, f'{len(successful)} registration(s) {verb}.')
            for reg_id, err in failed:
                messages.error(request, f'Registration {reg_id}: {err}')
        else:
            messages.error(request, 'Select at least one registration.')
        return redirect('portal:eo_registrations')

    pending = svc.get_pending_registration_approvals(
        department_id=request.GET.get('department_id') or None,
        course_id=request.GET.get('course_id') or None,
    )
    return render(request, 'dashboard/exam_officer/registrations.html', {
        'nav_items': _nav('portal:eo_registrations'),
        'page_title': 'Registration Approvals',
        'pending': pending,
    })


@role_required('exam-officer')
@require_POST
def approve_registration(request, registration_id):
    action = request.POST.get('action')
    reason = request.POST.get('reason', '')
    ok, message = svc.approve_registration(registration_id, request.user, action, reason)
    (messages.success if ok else messages.error)(request, message)
    return redirect('portal:eo_registrations')


@role_required('exam-officer')
def results(request):
    pending = svc.get_courses_pending_results()
    return render(request, 'dashboard/exam_officer/results.html', {
        'nav_items': _nav('portal:eo_results'),
        'page_title': 'Result Compilation',
        'pending': pending,
    })


@role_required('exam-officer')
def result_detail(request, course_id):
    detail = svc.get_course_result_detail(course_id)
    if detail is None:
        messages.error(request, 'Course not found.')
        return redirect('portal:eo_results')
    return render(request, 'dashboard/exam_officer/result_detail.html', {
        'nav_items': _nav('portal:eo_results'),
        'page_title': f'Review: {detail["course"].code}',
        **detail,
    })


@role_required('exam-officer')
@require_POST
def verify_results(request, course_id):
    count, error = svc.verify_course_results(course_id)
    if error:
        messages.error(request, error)
        return redirect('portal:eo_result_detail', course_id=course_id)
    messages.success(request, f'Verified {count} grade(s) -- forwarded to the Registrar for publication.')
    return redirect('portal:eo_results')


@role_required('exam-officer')
def master_sheet(request, course_id):
    return svc.generate_master_sheet(course_id)
