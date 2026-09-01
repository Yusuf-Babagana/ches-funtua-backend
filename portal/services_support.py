"""
Support chat business logic, shared by the student-facing chat page
(portal/views_student.py) and the desk-officer-facing inbox
(portal/views_desk_officer.py). Genuinely new -- no DRF equivalent exists
for this; it's the "separate live-ish chat feature" the user explicitly
chose over reusing academics.StudentQuery (a single-record ticket, not a
multi-message thread). Polling-based rather than websockets, per the
plan (PythonAnywhere's tiers don't support websockets well) -- the client
re-fetches on an interval via support_poll/support_thread_poll below.

One open ChatThread per student at a time (get_or_create_thread): if a
desk officer closes a thread, the student's next visit opens a fresh one
rather than reusing the closed history.
"""
from django.db.models import Count, F, Q
from django.utils import timezone

from support.models import ChatMessage, ChatThread


def get_or_create_thread(student):
    thread = ChatThread.objects.filter(student=student, is_closed=False).order_by('-updated_at').first()
    if thread:
        return thread
    return ChatThread.objects.create(student=student)


def get_messages(thread, after_id=None):
    qs = thread.messages.select_related('sender')
    if after_id:
        try:
            qs = qs.filter(id__gt=int(after_id))
        except (TypeError, ValueError):
            pass
    return qs


def post_message(thread, sender, body):
    body = (body or '').strip()
    if not body:
        return None, 'Message cannot be empty.'
    message = ChatMessage.objects.create(thread=thread, sender=sender, body=body)
    # updated_at is auto_now -- explicitly touched so the desk-officer
    # inbox's "most recently active" ordering reflects new messages, not
    # just thread creation time.
    thread.save(update_fields=['updated_at'])
    return message, None


def mark_read(thread, reader):
    """Marks every message in this thread NOT sent by `reader` as read --
    called whenever a participant opens/polls a thread they're viewing."""
    thread.messages.filter(read_at__isnull=True).exclude(sender=reader).update(read_at=timezone.now())


def serialize_message(message, viewer):
    return {
        'id': message.id,
        'body': message.body,
        'created_at': message.created_at.strftime('%b %d, %I:%M %p'),
        'is_mine': message.sender_id == viewer.id,
        'sender_name': message.sender.get_full_name() if message.sender else 'Unknown',
    }


# ---------------------------------------------------------------------------
# Student side
# ---------------------------------------------------------------------------

def get_student_unread_count(student):
    return ChatMessage.objects.filter(
        thread__student=student, read_at__isnull=True,
    ).exclude(sender=student.user).count()


# ---------------------------------------------------------------------------
# Desk-officer side (shared inbox -- any desk officer can open any thread)
# ---------------------------------------------------------------------------

def get_desk_officer_inbox():
    """Open threads, most recently active first, each annotated with how
    many of ITS OWN student's messages are still unread -- identifies a
    message as "from the student" by sender == thread.student.user rather
    than by role, so it stays correct even if a thread ever has more than
    one staff participant."""
    return ChatThread.objects.filter(is_closed=False).select_related('student__user').annotate(
        unread_count=Count(
            'messages',
            filter=Q(messages__read_at__isnull=True) & Q(messages__sender=F('student__user')),
        )
    ).order_by('-updated_at')


def get_desk_officer_unread_total():
    return ChatMessage.objects.filter(
        read_at__isnull=True, thread__is_closed=False, sender=F('thread__student__user'),
    ).count()


def close_thread(thread_id):
    try:
        thread = ChatThread.objects.get(id=thread_id)
    except ChatThread.DoesNotExist:
        return False, 'Thread not found.'
    thread.is_closed = True
    thread.save(update_fields=['is_closed', 'updated_at'])
    return True, None
