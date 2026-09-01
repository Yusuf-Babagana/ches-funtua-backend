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
