from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from academics.constants import STAFF_ROLES
from academics.models import AssignedTask
from .decorators import role_required
from .forms import LoginForm
from .roles import ROLE_DASHBOARD_URL_NAME

MAX_PROFILE_PICTURE_BYTES = 3 * 1024 * 1024


def landing(request):
    """
    Public marketing/portal landing page -- Django equivalent of the Next.js
    app/page.tsx. Logged-in users land straight on their dashboard instead
    of seeing the marketing page again.
    """
    if request.user.is_authenticated:
        return redirect(ROLE_DASHBOARD_URL_NAME.get(request.user.role, 'portal:dashboard_root'))
    return render(request, 'portal/index.html')


@require_http_methods(['GET', 'POST'])
def login_view(request):
    """
    Session-authenticated login. Mirrors users.views.AuthViewSet.login's
    business rules exactly (authenticate by email, reject inactive users)
    but issues a Django session instead of a JWT pair -- the JWT API at
    /api/auth/login/ is untouched and keeps working for any other client.
    """
    if request.user.is_authenticated:
        return redirect(ROLE_DASHBOARD_URL_NAME.get(request.user.role, 'portal:dashboard_root'))

    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email'].strip().lower()
        password = form.cleaned_data['password']

        user = authenticate(request, username=email, password=password)
        if user is None:
            form.add_error(None, 'Invalid email or password.')
        elif not user.is_active:
            form.add_error(None, 'This account has been deactivated. Contact ICT support.')
        else:
            login(request, user)
            messages.success(request, f'Welcome back, {user.first_name or user.email}.')
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url:
                return redirect(next_url)
            return redirect(ROLE_DASHBOARD_URL_NAME.get(user.role, 'portal:dashboard_root'))

    return render(request, 'registration/login.html', {
        'form': form,
        'next': request.GET.get('next', ''),
    })


@require_http_methods(['GET', 'POST'])
def logout_view(request):
    if request.user.is_authenticated:
        logout(request)
        messages.info(request, 'You have been signed out.')
    return redirect('portal:landing')


@login_required
def dashboard_root(request):
    """/dashboard/ -- redirects to the caller's own role dashboard."""
    url_name = ROLE_DASHBOARD_URL_NAME.get(request.user.role)
    if not url_name:
        messages.error(request, 'Your account has no recognized role. Contact ICT support.')
        return redirect('portal:landing')
    return redirect(url_name)


@login_required
@require_http_methods(['POST'])
def update_profile_picture(request):
    """
    Shared avatar upload for every role -- profile_picture lives on the
    base User model (users/models.py), not per-role, so one endpoint
    serves the sidebar upload widget in templates/dashboard/base.html
    regardless of which dashboard the user is on.
    """
    fallback_url = ROLE_DASHBOARD_URL_NAME.get(request.user.role, 'portal:dashboard_root')
    referer = request.META.get('HTTP_REFERER')
    next_url = referer if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ) else None

    photo = request.FILES.get('profile_picture')
    if not photo:
        messages.error(request, 'No file selected.')
    elif not (photo.content_type or '').startswith('image/'):
        messages.error(request, 'Please upload an image file.')
    elif photo.size > MAX_PROFILE_PICTURE_BYTES:
        messages.error(request, 'Image must be smaller than 3MB.')
    else:
        request.user.profile_picture = photo
        request.user.save(update_fields=['profile_picture', 'updated_at'])
        messages.success(request, 'Profile picture updated.')

    return redirect(next_url) if next_url else redirect(fallback_url)


def _nav_for(request, active_url_name):
    """
    These two pages (notifications, tasks) are role-agnostic, but the
    dashboard shell's sidebar still needs *that role's* nav items so the
    user can navigate back out. Each views_<role>.py already owns its
    own NAV list + _nav() -- reuse those instead of duplicating them.
    """
    from . import (
        views_bursar, views_desk_officer, views_exam_officer, views_hod,
        views_ict, views_lecturer, views_registrar, views_student, views_super_admin,
    )
    resolvers = {
        'student': views_student._nav, 'lecturer': views_lecturer._nav,
        'hod': views_hod._nav, 'registrar': views_registrar._nav,
        'bursar': views_bursar._nav, 'desk-officer': views_desk_officer._nav,
        'ict': views_ict._nav, 'exam-officer': views_exam_officer._nav,
        'super-admin': views_super_admin._nav,
    }
    resolver = resolvers.get(request.user.role)
    return resolver(active_url_name) if resolver else []


@login_required
def notifications_list(request):
    """
    The bell icon's "view all" page -- every role lands here the same
    way, since Notification isn't role-specific. Viewing the list marks
    everything on it read (same UX as the bell dropdown itself).
    """
    from . import services_notifications

    notes = list(services_notifications.get_recent(request.user, limit=50))
    services_notifications.mark_all_read(request.user)
    return render(request, 'portal/notifications.html', {
        'nav_items': _nav_for(request, 'portal:notifications'),
        'page_title': 'Notifications',
        'notifications': notes,
    })


@role_required(*STAFF_ROLES)
def my_tasks(request):
    """Item #18's "Other Assigned Task" page -- one shared view/template
    for every staff role rather than duplicating it per dashboard."""
    tasks = AssignedTask.objects.filter(assigned_to=request.user).select_related('assigned_by')
    return render(request, 'portal/tasks.html', {
        'nav_items': _nav_for(request, 'portal:my_tasks'),
        'page_title': 'My Tasks',
        'tasks': tasks,
    })


@role_required(*STAFF_ROLES)
@require_http_methods(['POST'])
def complete_task(request, task_id):
    task = get_object_or_404(AssignedTask, id=task_id, assigned_to=request.user)
    task.status = 'completed'
    task.save(update_fields=['status', 'updated_at'])
    messages.success(request, 'Task marked complete.')
    return redirect('portal:my_tasks')


# _placeholder_dashboard (and the per-role dashboard_* views that used
# it) has been fully retired -- Phase 11 (Super Admin) was the last role
# still on the placeholder stub; every one of the 9 roles now has a
# real, data-backed dashboard (see views_student.py, views_lecturer.py,
# views_hod.py, views_registrar.py, views_bursar.py,
# views_exam_officer.py, views_desk_officer.py, views_ict.py,
# views_super_admin.py).
