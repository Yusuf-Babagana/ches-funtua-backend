from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from .forms import LoginForm
from .roles import ROLE_DASHBOARD_URL_NAME


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


# _placeholder_dashboard (and the per-role dashboard_* views that used
# it) has been fully retired -- Phase 11 (Super Admin) was the last role
# still on the placeholder stub; every one of the 9 roles now has a
# real, data-backed dashboard (see views_student.py, views_lecturer.py,
# views_hod.py, views_registrar.py, views_bursar.py,
# views_exam_officer.py, views_desk_officer.py, views_ict.py,
# views_super_admin.py).
