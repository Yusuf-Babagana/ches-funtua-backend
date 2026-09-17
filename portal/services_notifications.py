"""
Notification business logic, shared across every role. Generates
`Notification` rows for two events: an Announcement being posted
(services_hod.py / services_lecturer.py) and an AssignedTask being created
(services_super_admin.py). Consumed by portal/context_processors.py (bell
badge + dropdown) and portal/views.py (the "view all" page).
"""
from academics.constants import STAFF_ROLES
from academics.models import Notification
from users.models import Student, User


def _resolve_announcement_recipients(announcement):
    """Same audience an Announcement is visible to (see context_processors.
    announcements()): department/level-scoped students, and/or every staff
    user, depending on `announcement.audience`."""
    recipients = []

    if announcement.audience in ('everyone', 'students'):
        student_qs = Student.objects.select_related('user')
        if announcement.department_id:
            student_qs = student_qs.filter(department_id=announcement.department_id)
        if announcement.level:
            student_qs = student_qs.filter(level=announcement.level)
        recipients.extend(s.user for s in student_qs)

    if announcement.audience in ('everyone', 'staff'):
        recipients.extend(User.objects.filter(role__in=STAFF_ROLES))

    return recipients


def create_notifications_for_announcement(announcement, exclude_user=None):
    recipients = _resolve_announcement_recipients(announcement)
    Notification.objects.bulk_create([
        Notification(recipient=user, title=announcement.title, body=announcement.body)
        for user in recipients
        if not exclude_user or user.id != exclude_user.id
    ])


def create_notification_for_task(task):
    Notification.objects.create(
        recipient=task.assigned_to,
        title='New task assigned',
        body=task.title,
        link_name='portal:my_tasks',
    )


def get_unread_count(user):
    return Notification.objects.filter(recipient=user, is_read=False).count()


def get_recent(user, limit=8):
    return Notification.objects.filter(recipient=user)[:limit]


def mark_all_read(user):
    Notification.objects.filter(recipient=user, is_read=False).update(is_read=True)
