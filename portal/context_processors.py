"""
Template context processors for the Django-rendered portal.

New for the CHESF Student Portal Digest feature work: the spec's
"permanent notification banner" -- rather than each dashboard view
fetching announcements itself, this runs on every request so
templates/dashboard/base.html can render the banner on every dashboard
page without every view function remembering to pass it in.
"""


def announcements(request):
    """
    Injects `active_announcements` into every template context. Cheap to
    compute per-request (small table, indexed FKs, capped at 5) and only
    does real work for authenticated dashboard users.
    """
    if not request.user.is_authenticated:
        return {}

    from django.db.models import Q
    from academics.models import Announcement

    qs = Announcement.objects.select_related('department', 'posted_by')

    student = getattr(request.user, 'student_profile', None)
    if student:
        # Scoped to the student's own department (or department-agnostic
        # announcements) and their own level (or level-agnostic ones).
        qs = qs.filter(
            Q(department__isnull=True) | Q(department=student.department)
        ).filter(
            Q(level='') | Q(level=student.level)
        )
    # Staff roles see everything -- department/level scoping only exists
    # to narrow what students see, not to hide announcements from staff.

    return {'active_announcements': qs.order_by('-is_pinned', '-created_at')[:5]}


def support_unread_count(request):
    """
    Injects `support_unread_count` so the persistent Support nav link's
    unread badge (templates/dashboard/base.html) shows up on every
    dashboard page, same reasoning as announcements() above. Only
    students and desk officers participate in support chat, so every
    other role gets 0 without a query.
    """
    if not request.user.is_authenticated:
        return {}

    from . import services_support as svc

    student = getattr(request.user, 'student_profile', None)
    if student:
        return {'support_unread_count': svc.get_student_unread_count(student)}

    if request.user.role == 'desk-officer':
        return {'support_unread_count': svc.get_desk_officer_unread_total()}

    return {'support_unread_count': 0}
