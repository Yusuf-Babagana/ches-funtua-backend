from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .decorators import role_required
from .forms import LoginForm
from .roles import ROLE_DASHBOARD_URL_NAME, get_nav_items, get_role_profile


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


def _placeholder_dashboard(request, role, title, url_name):
    """
    Temporary stand-in for a role's dashboard landing page. Phases 3-11
    replace each of these with the real, data-backed dashboard for that
    role; this exists only so the foundation (auth + role gating + shared
    layout) is provably working end-to-end for all 9 roles before any real
    page is built on top of it.
    """
    return render(request, 'dashboard/placeholder.html', {
        'page_title': title,
        'active_role': role,
        'profile': get_role_profile(request.user),
        'nav_items': get_nav_items(role, active_url_name=url_name),
    })


@role_required('hod')
def dashboard_hod(request):
    return _placeholder_dashboard(request, 'hod', 'HOD Dashboard', 'portal:dashboard_hod')


@role_required('registrar')
def dashboard_registrar(request):
    return _placeholder_dashboard(request, 'registrar', 'Registrar Dashboard', 'portal:dashboard_registrar')


@role_required('bursar')
def dashboard_bursar(request):
    return _placeholder_dashboard(request, 'bursar', 'Bursar Dashboard', 'portal:dashboard_bursar')


@role_required('desk-officer')
def dashboard_desk_officer(request):
    return _placeholder_dashboard(request, 'desk-officer', 'Desk Officer Dashboard', 'portal:dashboard_desk_officer')


@role_required('ict', 'super-admin')
def dashboard_ict(request):
    return _placeholder_dashboard(request, 'ict', 'ICT Dashboard', 'portal:dashboard_ict')


@role_required('exam-officer')
def dashboard_exam_officer(request):
    return _placeholder_dashboard(request, 'exam-officer', 'Exam Officer Dashboard', 'portal:dashboard_exam_officer')


@role_required('super-admin')
def dashboard_super_admin(request):
    return _placeholder_dashboard(request, 'super-admin', 'Super Admin Dashboard', 'portal:dashboard_super_admin')
