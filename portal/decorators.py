"""
Server-side role enforcement for the Django-rendered frontend.

Per the migration brief: "Do not rely only on hiding menu items." A student
who manually types /dashboard/bursar/ must get a real 403, not just a
missing sidebar link. This mirrors the role checks already implemented (as
DRF permission classes) in users/permissions.py, but as view decorators for
plain Django views instead of DRF ViewSets.
"""
import functools

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect

from .roles import ROLE_DASHBOARD_URL_NAME


def role_required(*allowed_roles):
    """
    Restrict a view to users whose `request.user.role` is in `allowed_roles`.

    Always implies @login_required (redirects anonymous users to LOGIN_URL
    with a ?next= back to the page they wanted). An authenticated user whose
    role isn't allowed gets a real 403 (rendered via templates/errors/403.html)
    -- never a silent redirect to their own dashboard, so the failure is
    visible during testing rather than looking like a successful page load.
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        @login_required
        def wrapped(request, *args, **kwargs):
            if request.user.role not in allowed_roles:
                raise PermissionDenied(
                    f"This page requires role(s): {', '.join(allowed_roles)}."
                )
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def redirect_to_own_dashboard(user):
    """Resolve the URL name for `user`'s own dashboard landing page."""
    url_name = ROLE_DASHBOARD_URL_NAME.get(user.role, 'portal:dashboard_root')
    return redirect(url_name)
