"""
HOD dashboard pages -- Phase 5 of the Next.js -> Django templates
migration. See portal/services_hod.py for the ported business logic.
"""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from . import services_hod as svc
from .decorators import role_required

NAV = [
    {'label': 'Overview', 'url_name': 'portal:dashboard_hod'},
    {'label': 'Students', 'url_name': 'portal:hod_students'},
    {'label': 'Faculty', 'url_name': 'portal:hod_lecturers'},
    {'label': 'Courses', 'url_name': 'portal:hod_courses'},
    {'label': 'Result Approvals', 'url_name': 'portal:hod_approvals'},
]


def _nav(active_url_name):
    items = [dict(item) for item in NAV]
    for item in items:
        item['is_active'] = item['url_name'] == active_url_name
    return items


def _get_department_or_error(request):
    """
    Mirrors HODDashboardViewSet.get_department: the HOD role alone isn't
    enough -- the user must actually be the Lecturer a Department points
    to as its `hod`. Renders a clear error page instead of crashing if
    that link is missing (e.g. role flipped to 'hod' without the
    department assignment actually being made yet).
    """
    lecturer = getattr(request.user, 'lecturer_profile', None)
    if not lecturer:
        return None, render(request, 'dashboard/hod/no_department.html', {
            'nav_items': _nav(None), 'page_title': 'HOD Dashboard',
            'reason': 'Your account has no lecturer profile linked.',
        })
    department = svc.get_hod_department(lecturer)
    if not department:
        return None, render(request, 'dashboard/hod/no_department.html', {
            'nav_items': _nav(None), 'page_title': 'HOD Dashboard',
            'reason': "You are not currently assigned as Head of Department for any department.",
        })
    return department, None


@role_required('hod')
def dashboard(request):
    department, error = _get_department_or_error(request)
    if error:
        return error
    data = svc.get_dashboard_data(department)
    return render(request, 'dashboard/hod/dashboard.html', {
        'nav_items': _nav('portal:dashboard_hod'),
        'page_title': f'{department.code} Dashboard',
        'department': department,
        **data,
    })


@role_required('hod')
def students(request):
    department, error = _get_department_or_error(request)
    if error:
        return error
    student_list = svc.get_department_students(
        department,
        level=request.GET.get('level') or None,
        status=request.GET.get('status') or None,
        search=request.GET.get('search') or None,
    )
    return render(request, 'dashboard/hod/students.html', {
        'nav_items': _nav('portal:hod_students'),
        'page_title': 'Student Directory',
        'department': department,
        'students': student_list,
        'filters': request.GET,
    })


@role_required('hod')
def lecturers(request):
    department, error = _get_department_or_error(request)
    if error:
        return error
    lecturer_list = svc.get_department_lecturers(
        department,
        designation=request.GET.get('designation') or None,
        search=request.GET.get('search') or None,
    )
    return render(request, 'dashboard/hod/lecturers.html', {
        'nav_items': _nav('portal:hod_lecturers'),
        'page_title': 'Faculty Directory',
        'department': department,
        'lecturers': lecturer_list,
        'filters': request.GET,
    })


@role_required('hod')
def courses(request):
    department, error = _get_department_or_error(request)
    if error:
        return error
    course_list = svc.get_department_courses(
        department,
        level=request.GET.get('level') or None,
        has_lecturer=request.GET.get('has_lecturer') or None,
        search=request.GET.get('search') or None,
    )
    available_lecturers = svc.get_available_lecturers(department)
    return render(request, 'dashboard/hod/courses.html', {
        'nav_items': _nav('portal:hod_courses'),
        'page_title': 'Course Allocation',
        'department': department,
        'courses': course_list,
        'available_lecturers': available_lecturers,
        'filters': request.GET,
    })


@role_required('hod')
@require_POST
def assign_lecturer(request, course_id):
    department, error = _get_department_or_error(request)
    if error:
        return error
    lecturer_id = request.POST.get('lecturer_id')
    if not lecturer_id or lecturer_id == 'unassigned':
        ok, msg = svc.remove_course_lecturer(department, course_id)
    else:
        ok, msg = svc.assign_course_lecturer(department, course_id, lecturer_id)
    (messages.success if ok else messages.error)(request, msg)
    return redirect('portal:hod_courses')


@role_required('hod')
def approvals(request):
    department, error = _get_department_or_error(request)
    if error:
        return error
    pending = svc.get_pending_result_reviews(department)
    return render(request, 'dashboard/hod/approvals.html', {
        'nav_items': _nav('portal:hod_approvals'),
        'page_title': 'Result Approvals',
        'department': department,
        'pending': pending,
    })


@role_required('hod')
def approval_detail(request, course_id):
    department, error = _get_department_or_error(request)
    if error:
        return error
    course, grades = svc.get_course_review_details(department, course_id)
    if course is None:
        messages.error(request, 'Course not found in your department.')
        return redirect('portal:hod_approvals')
    return render(request, 'dashboard/hod/approval_detail.html', {
        'nav_items': _nav('portal:hod_approvals'),
        'page_title': f'Review: {course.code}',
        'department': department,
        'course': course,
        'grades': grades,
        'failed_count': sum(1 for g in grades if g.grade_letter == 'F'),
        'passed_count': sum(1 for g in grades if g.grade_letter != 'F'),
    })


@role_required('hod')
@require_POST
def approve_results(request, course_id):
    department, error = _get_department_or_error(request)
    if error:
        return error
    count, err = svc.approve_course_results(department, course_id)
    if err:
        messages.error(request, err)
    else:
        messages.success(request, f'Approved {count} grade(s) -- forwarded to the Exam Officer.')
    return redirect('portal:hod_approvals')


@role_required('hod')
@require_POST
def post_announcement(request):
    department, error = _get_department_or_error(request)
    if error:
        return error
    announcement, err = svc.post_announcement(
        request.user, department,
        request.POST.get('title', ''), request.POST.get('body', ''),
        level=request.POST.get('level', ''), is_pinned=bool(request.POST.get('is_pinned')),
    )
    if err:
        messages.error(request, err)
    else:
        messages.success(request, 'Announcement posted.')
    return redirect('portal:dashboard_hod')


@role_required('hod')
@require_POST
def reject_results(request, course_id):
    department, error = _get_department_or_error(request)
    if error:
        return error
    reason = request.POST.get('reason', '').strip()
    if not reason:
        messages.error(request, 'Please provide a reason for rejection.')
        return redirect('portal:hod_approval_detail', course_id=course_id)
    count, err = svc.reject_course_results(department, course_id, reason)
    if err:
        messages.error(request, err)
    else:
        messages.success(request, f'Returned {count} grade(s) to the lecturer for correction.')
    return redirect('portal:hod_approvals')
