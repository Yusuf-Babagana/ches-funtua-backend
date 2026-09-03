"""
Super Admin dashboard pages -- Phase 11 (final role-specific phase) of
the Next.js -> Django templates migration. See portal/services_super_admin.py
for the ported business logic and an important scope note: per the
user's explicit decision for this phase, Super Admin does NOT get its
own duplicate User Management / Department Management pages -- it
already has full working access to Phase 10's ICT pages for both (via
@role_required('ict', 'super-admin') on every portal/views_ict.py view),
and the old Next.js frontend's own dashboard linked to those rather than
rebuilding them. This phase builds only what's genuinely
Super-Admin-exclusive: Courses, Semesters, Level Configuration, and the
two system-wide actions (Start New Session, Promote Students) Phase 10
deferred here.
"""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from academics.models import Department
from users.models import Lecturer

from . import services_super_admin as svc
from .decorators import role_required

NAV = [
    {'label': 'Dashboard', 'url_name': 'portal:dashboard_super_admin'},
    {'label': 'Courses', 'url_name': 'portal:sa_courses'},
    {'label': 'Semesters', 'url_name': 'portal:sa_semesters'},
    {'label': 'Level Config', 'url_name': 'portal:sa_level_config'},
    {'label': 'System Tools', 'url_name': 'portal:sa_system_tools'},
    {'label': 'ICT: Users', 'url_name': 'portal:ict_user_management'},
    {'label': 'ICT: Departments', 'url_name': 'portal:ict_system_config'},
    {'label': 'ICT: Staff Accounts', 'url_name': 'portal:ict_staff_accounts'},
]


def _nav(active_url_name):
    items = [dict(item) for item in NAV]
    for item in items:
        item['is_active'] = item['url_name'] == active_url_name
    return items


@role_required('super-admin')
def dashboard(request):
    return render(request, 'dashboard/super_admin/dashboard.html', {
        'nav_items': _nav('portal:dashboard_super_admin'),
        'page_title': 'Super Admin Dashboard',
        **svc.get_dashboard_data(),
    })


# ---------------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------------

@role_required('super-admin')
def courses(request):
    if request.method == 'POST':
        form = request.POST.get('form')
        if form == 'create':
            course, error = svc.create_course(request.POST)
            if error:
                messages.error(request, error)
            else:
                messages.success(request, f'Course {course.code} created.')
        elif form == 'update':
            course, error = svc.update_course(request.POST.get('course_id'), request.POST)
            if error:
                messages.error(request, error)
            else:
                messages.success(request, f'Course {course.code} updated.')
        elif form == 'delete':
            ok, message = svc.delete_course(request.POST.get('course_id'))
            (messages.success if ok else messages.error)(request, message)
        elif form == 'assign_lecturer':
            course, error = svc.assign_course_lecturer(request.POST.get('course_id'), request.POST.get('lecturer_id'))
            (messages.error if error else messages.success)(
                request, error or f'{course.lecturer.user.get_full_name()} assigned to {course.code}.',
            )
        elif form == 'remove_lecturer':
            course, error = svc.remove_course_lecturer(request.POST.get('course_id'))
            (messages.success if not error else messages.error)(request, error or f'Lecturer removed from {course.code}.')
        return redirect('portal:sa_courses')

    course_list = svc.get_courses(
        department_id=request.GET.get('department') or None,
        level=request.GET.get('level') or None,
        semester=request.GET.get('semester') or None,
        search=request.GET.get('search') or None,
    )
    return render(request, 'dashboard/super_admin/courses.html', {
        'nav_items': _nav('portal:sa_courses'),
        'page_title': 'Course Management',
        'courses': course_list,
        'departments': Department.objects.all().order_by('name'),
        'lecturers': Lecturer.objects.select_related('user', 'department').order_by('user__last_name'),
        'level_choices': svc.LEVEL_CHOICES,
        'semester_choices': svc.SEMESTER_CHOICES,
        'filters': request.GET,
    })


# ---------------------------------------------------------------------------
# Semesters / Sessions
# ---------------------------------------------------------------------------

@role_required('super-admin')
def semesters(request):
    if request.method == 'POST':
        form = request.POST.get('form')
        if form == 'create':
            sem, error = svc.create_semester(request.POST)
            if error:
                messages.error(request, error)
            else:
                messages.success(request, f'{sem} created.')
        elif form == 'update':
            sem, error = svc.update_semester(request.POST.get('semester_id'), request.POST)
            if error:
                messages.error(request, error)
            else:
                messages.success(request, f'{sem} updated.')
        return redirect('portal:sa_semesters')

    return render(request, 'dashboard/super_admin/semesters.html', {
        'nav_items': _nav('portal:sa_semesters'),
        'page_title': 'Semesters & Sessions',
        'semesters': svc.get_semesters(),
    })


# ---------------------------------------------------------------------------
# Level configuration
# ---------------------------------------------------------------------------

@role_required('super-admin')
def level_config(request):
    if request.method == 'POST':
        form = request.POST.get('form')
        if form == 'init_defaults':
            created, error = svc.init_level_config_defaults()
            if error:
                messages.error(request, error)
            elif created:
                messages.success(request, f"Created default config for level(s): {', '.join(created)}.")
            else:
                messages.info(request, 'All levels already have a configuration.')
        elif form == 'update':
            config, error = svc.update_level_config(
                request.POST.get('config_id'), request.POST.get('current_semester_id'),
                request.POST.get('is_registration_open') == 'on',
            )
            if error:
                messages.error(request, error)
            else:
                messages.success(request, f'Level {config.level} configuration updated.')
        return redirect('portal:sa_level_config')

    return render(request, 'dashboard/super_admin/level_config.html', {
        'nav_items': _nav('portal:sa_level_config'),
        'page_title': 'Level Configuration',
        'configs': svc.get_level_configs(),
        'semesters': svc.get_semesters(),
    })


# ---------------------------------------------------------------------------
# System tools (Start New Session, Promote Students)
# ---------------------------------------------------------------------------

@role_required('super-admin')
def system_tools(request):
    return render(request, 'dashboard/super_admin/system_tools.html', {
        'nav_items': _nav('portal:sa_system_tools'),
        'page_title': 'System Tools',
        'current_semester': svc.get_dashboard_data()['current_semester'],
    })


@role_required('super-admin')
@require_POST
def start_new_session(request):
    sem, error = svc.start_new_session(request.POST.get('session'), request.POST.get('start_date'))
    if error:
        messages.error(request, error)
    else:
        messages.success(request, f'{sem} started successfully.')
    return redirect('portal:sa_system_tools')


@role_required('super-admin')
@require_POST
def promote_students(request):
    if request.POST.get('confirm') != 'yes':
        messages.error(request, 'You must confirm this destructive action before it runs.')
        return redirect('portal:sa_system_tools')

    summary = svc.promote_students()
    messages.success(
        request,
        f"Promotion complete: {summary['graduated']} graduated, "
        f"{summary['promoted_to_300']} promoted to 300 level, "
        f"{summary['promoted_to_200']} promoted to 200 level.",
    )
    return redirect('portal:sa_system_tools')
