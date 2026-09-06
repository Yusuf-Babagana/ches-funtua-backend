"""
Single source of truth for the role <-> dashboard URL mapping used by the
Django-rendered frontend, and small helpers for resolving a user's profile
object by role.

This mirrors the roleDashboardMap that used to live in the Next.js frontend
(contexts/auth-context.tsx, components/protected-route.tsx) and the 9-role
roster defined on users.User.ROLE_CHOICES. Keeping it here (once) means the
login redirect, the role-required decorator's "wrong role, go home" redirect,
and the sidebar all agree with each other by construction.
"""

# role value -> name of the URL pattern (see portal/urls.py) for that role's
# dashboard landing page.
ROLE_DASHBOARD_URL_NAME = {
    'student': 'portal:dashboard_student',
    'lecturer': 'portal:dashboard_lecturer',
    'hod': 'portal:dashboard_hod',
    'registrar': 'portal:dashboard_registrar',
    'bursar': 'portal:dashboard_bursar',
    'desk-officer': 'portal:dashboard_desk_officer',
    'ict': 'portal:dashboard_ict',
    'exam-officer': 'portal:dashboard_exam_officer',
    'super-admin': 'portal:dashboard_super_admin',
}


ROLE_DISPLAY_NAME = {
    'student': 'Student Portal',
    'lecturer': 'Lecturer Portal',
    'hod': 'HOD Portal',
    'registrar': 'Registrar Portal',
    'bursar': 'Bursar Portal',
    'desk-officer': 'Desk Officer Portal',
    'ict': 'ICT Portal',
    'exam-officer': 'Exam Officer Portal',
    'super-admin': 'Super Admin Portal',
}


def get_nav_items(role, active_url_name=None):
    """
    Sidebar nav items for a role's dashboard. Only the dashboard landing
    page exists so far (foundation phase); each migration phase appends
    that role's real sub-pages here as they're built, so the shared
    dashboard/base.html shell never needs to change.
    """
    dashboard_url = ROLE_DASHBOARD_URL_NAME.get(role)
    items = [
        {'label': 'Dashboard', 'url_name': dashboard_url},
    ]
    for item in items:
        item['is_active'] = item['url_name'] == active_url_name
    return items


def get_role_profile(user):
    """
    Return the role-appropriate profile object for `user`, or None.

    Mirrors the profile-by-role lookup already implemented server-side in
    users.views.AuthViewSet.me() (student -> Student, lecturer/hod ->
    Lecturer, everything else -> StaffProfile) -- kept as one shared helper
    so every template view resolves "who is this user, really" the same way
    the existing /api/auth/me/ endpoint does.
    """
    role = getattr(user, 'role', None)
    if role == 'student':
        return getattr(user, 'student_profile', None)
    if role in ('lecturer', 'hod'):
        return getattr(user, 'lecturer_profile', None)
    # registrar, bursar, desk-officer, ict, exam-officer, super-admin
    return getattr(user, 'staff_profile', None)
