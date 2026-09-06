"""
ICT dashboard pages -- Phase 10 of the Next.js -> Django templates
migration. See portal/services_ict.py for the ported business logic and
an important note: unlike Desk Officer (Phase 9), the old frontend's ICT
pages were mostly genuine, working pages -- the real issues found here
were on the *backend* (a completely unguarded bulk result-upload endpoint
that force-published grades, and a couple of DRF actions missing a
super-admin protection check), both fixed in academics/views_ict.py and
users/views_ict.py in this same phase so the DRF API and this portal
layer enforce the same rules.

Deliberately NOT built here (see services_ict.py's module docstring):
"Start New Session" / "Promote Students" (left for Phase 11 -- Super
Admin, since the backend restricts them to that role) and every
fabricated/placeholder section of the old ICT surface (system logs, user
activity detail, account lockout heuristics, fake password-reset links,
Maintenance Mode toggle, Clear Cache button).
"""
from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from academics.models import Department

from . import services_ict as svc
from .decorators import role_required

NAV = [
    {'label': 'Dashboard', 'url_name': 'portal:dashboard_ict'},
    {'label': 'Register Student', 'url_name': 'portal:ict_register_student'},
    {'label': 'Staff Accounts', 'url_name': 'portal:ict_staff_accounts'},
    {'label': 'Results Upload', 'url_name': 'portal:ict_results_upload'},
    {'label': 'System Config', 'url_name': 'portal:ict_system_config'},
    {'label': 'User Management', 'url_name': 'portal:ict_user_management'},
]


def _nav(active_url_name):
    items = [dict(item) for item in NAV]
    for item in items:
        item['is_active'] = item['url_name'] == active_url_name
    return items


@role_required('ict', 'super-admin')
def dashboard(request):
    data = svc.get_dashboard_data()
    return render(request, 'dashboard/ict/dashboard.html', {
        'nav_items': _nav('portal:dashboard_ict'),
        'page_title': 'ICT Dashboard',
        **data,
    })


# ---------------------------------------------------------------------------
# Student registration
# ---------------------------------------------------------------------------

@role_required('ict', 'super-admin')
def register_student(request):
    credentials = None
    if request.method == 'POST':
        result, error = svc.register_student(request.POST)
        if error:
            messages.error(request, error)
        else:
            credentials = result
            messages.success(request, f"Student account created: {result['student'].matric_number}")

    return render(request, 'dashboard/ict/register_student.html', {
        'nav_items': _nav('portal:ict_register_student'),
        'page_title': 'Register Student',
        'departments': Department.objects.all().order_by('name'),
        'credentials': credentials,
    })


# ---------------------------------------------------------------------------
# Staff account creation
# ---------------------------------------------------------------------------

@role_required('ict', 'super-admin')
def staff_accounts(request):
    credentials = None
    if request.method == 'POST':
        role = request.POST.get('role')
        result, error = svc.create_staff_account(request.user, role, request.POST)
        if error:
            messages.error(request, error)
        else:
            credentials = result
            messages.success(request, f"{role.replace('-', ' ').title()} account created: {result['user'].email}")

    staff_roles = svc.STAFF_ROLES if request.user.role == 'super-admin' else [
        r for r in svc.STAFF_ROLES if r != 'super-admin'
    ]
    return render(request, 'dashboard/ict/staff_accounts.html', {
        'nav_items': _nav('portal:ict_staff_accounts'),
        'page_title': 'Staff Account Creation',
        'departments': Department.objects.all().order_by('name'),
        'designations': svc.LECTURER_DESIGNATIONS,
        'staff_roles': staff_roles,
        'credentials': credentials,
    })


# ---------------------------------------------------------------------------
# Bulk results upload
# ---------------------------------------------------------------------------

@role_required('ict', 'super-admin')
def results_upload(request):
    results = None
    if request.method == 'POST':
        csv_file = request.FILES.get('file')
        session = request.POST.get('session', '').strip()
        if not csv_file or not session:
            messages.error(request, 'A CSV file and session are required.')
        else:
            results, error = svc.import_results_csv(csv_file, session)
            if error:
                messages.error(request, error)
            else:
                messages.success(
                    request,
                    f"Imported {results['processed']} student row(s) as draft grades -- "
                    f"they still need HOD/Exam Officer/Registrar review before publishing.",
                )

    return render(request, 'dashboard/ict/results_upload.html', {
        'nav_items': _nav('portal:ict_results_upload'),
        'page_title': 'Bulk Results Upload',
        'results': results,
    })


# ---------------------------------------------------------------------------
# System configuration
# ---------------------------------------------------------------------------

@role_required('ict', 'super-admin')
def system_config(request):
    if request.method == 'POST':
        form = request.POST.get('form')
        if form == 'registration':
            ok, message = svc.set_registration_enabled(request.POST.get('registration_enabled') == 'on')
            (messages.success if ok else messages.error)(request, message)
        elif form == 'create_department':
            department, error = svc.create_department(
                request.POST.get('name'), request.POST.get('code'), request.POST.get('description', ''),
            )
            if error:
                messages.error(request, error)
            else:
                messages.success(request, f'Department {department.name} created.')
        elif form == 'update_department':
            department, error = svc.update_department(
                request.POST.get('department_id'), request.POST.get('name'),
                request.POST.get('code'), request.POST.get('description'),
                hod_id=request.POST.get('hod_id') or None,
            )
            if error:
                messages.error(request, error)
            else:
                messages.success(request, f'Department {department.name} updated.')
        elif form == 'delete_department':
            # Genuinely destructive (cascades to courses) -- reserved for
            # Super Admin even though ICT can reach every other action on
            # this page, same pattern as create_staff_account's
            # super-admin-only role.
            if request.user.role != 'super-admin':
                messages.error(request, 'Only a Super Admin can delete a department.')
            else:
                ok, message = svc.delete_department(request.POST.get('department_id'))
                (messages.success if ok else messages.error)(request, message)
        return redirect('portal:ict_system_config')

    return render(request, 'dashboard/ict/system_config.html', {
        'nav_items': _nav('portal:ict_system_config'),
        'page_title': 'System Configuration',
        'config': svc.get_system_config(),
        'department_rows': svc.get_department_configuration(),
    })


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------

@role_required('ict', 'super-admin')
def user_management(request):
    query = request.GET.get('q', '').strip()
    users = svc.search_users(
        query=query or None, role=request.GET.get('role') or None, active=request.GET.get('active') or None,
    )
    return render(request, 'dashboard/ict/user_management.html', {
        'nav_items': _nav('portal:ict_user_management'),
        'page_title': 'User Management',
        'users': users,
        'query': query,
        'filters': request.GET,
        'role_choices': request.user.__class__.ROLE_CHOICES,
    })


@role_required('ict', 'super-admin')
@require_POST
def reset_password(request, user_id):
    new_password = request.POST.get('new_password', '')
    ok, message = svc.reset_user_password(request.user, user_id, new_password)
    (messages.success if ok else messages.error)(request, message)
    return redirect('portal:ict_user_management')


@role_required('ict', 'super-admin')
@require_POST
def toggle_active(request, user_id):
    ok, message = svc.toggle_user_active(request.user, user_id)
    (messages.success if ok else messages.error)(request, message)
    return redirect('portal:ict_user_management')
