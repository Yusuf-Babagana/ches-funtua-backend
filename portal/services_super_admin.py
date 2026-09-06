"""
Super-Admin-facing business logic for the Django-template frontend.
Ports academics/views_admin.py (SuperAdminCourseViewSet,
SuperAdminSemesterViewSet, LevelConfigurationViewSet,
SuperAdminManagementViewSet.start_new_session/promote_students) -- not
a rewrite.

Per the user's explicit scope decision for this phase: Super Admin
already has full working access to everything Phase 10 (ICT) built --
user search/reset/deactivate, staff-account creation (including other
super-admin accounts), and department create/update/HOD-assignment --
via the @role_required('ict', 'super-admin') gate already on every
portal/views_ict.py view. Rather than duplicating those into a second,
divergent implementation (which is literally what happened in the old
Next.js frontend -- its main dashboard did department CRUD through one
endpoint while its dedicated Departments page used a different one for
the same operation), this phase links to those existing ICT pages
instead and builds only what's genuinely Super-Admin-exclusive: Course
management, Semester/Session management, Level Configuration, and the
two system-wide actions (Start New Session, Promote Students) that
Phase 10 explicitly deferred here.

promote_students() is ported with NO CGPA/credit/clearance eligibility
gate -- confirmed by user decision to preserve the exact current
behavior (an unconditional, confirm-gated bulk administrative action),
matching this migration's standing rule not to change business rules
unnecessarily.

Deliberately NOT built: a real Audit Logs page or the signal-based
logging infrastructure behind it (per user decision -- the old
frontend's Audit Logs page was already 100% non-functional, no backend
endpoint ever existed for it, and this would be new functionality, not
a migration of anything currently working). Also NOT ported:
academics/views_super_admin.py (an orphaned, never-routed file with
fabricated system_uptime/last_backup/recent_activities and a
role='super_admin' (underscore) bug that would never match the real
'super-admin' role even if it were wired up) and SystemHealthViewSet's
detailed/test_endpoints actions (one references an unimported `django`
and runs PostgreSQL-only SQL that would crash on this project's actual
SQLite database; the other doesn't test anything, just returns a
hardcoded status list).
"""
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import Q

from academics.models import AcademicLevelConfiguration, Course, Department, Semester
from users.models import Lecturer, Student

LEVEL_CHOICES = [('100', '100 Level'), ('200', '200 Level'), ('300', '300 Level')]
SEMESTER_CHOICES = [('first', 'First Semester'), ('second', 'Second Semester')]


# ---------------------------------------------------------------------------
# Dashboard -- deliberately lighter than ICT's (users/health checks live
# there, already reachable to Super Admin); focused on the academic
# structure this phase actually manages.
# ---------------------------------------------------------------------------

def get_dashboard_data():
    current_semester = Semester.objects.filter(is_current=True).first()
    return {
        'current_semester': current_semester,
        'department_count': Department.objects.count(),
        'departments_without_hod': Department.objects.filter(hod__isnull=True).count(),
        'course_count': Course.objects.count(),
        'courses_without_lecturer': Course.objects.filter(lecturer__isnull=True).count(),
        'semester_count': Semester.objects.count(),
        'level_config_count': AcademicLevelConfiguration.objects.count(),
    }


# ---------------------------------------------------------------------------
# Course management (SuperAdminCourseViewSet)
# ---------------------------------------------------------------------------

def get_courses(department_id=None, level=None, semester=None, search=None):
    courses = Course.objects.select_related('department', 'lecturer__user').order_by('code')
    if department_id:
        courses = courses.filter(department_id=department_id)
    if level:
        courses = courses.filter(level=level)
    if semester:
        courses = courses.filter(semester=semester)
    if search:
        courses = courses.filter(Q(code__icontains=search) | Q(title__icontains=search))
    return courses


def create_course(data):
    code = (data.get('code') or '').strip().upper()
    title = (data.get('title') or '').strip()
    if not code or not title or not data.get('department_id'):
        return None, 'Code, title, and department are required.'
    if Course.objects.filter(code=code).exists():
        return None, f'Course code {code} already exists.'
    try:
        credits = int(data.get('credits') or 0)
    except (TypeError, ValueError):
        return None, 'Credits must be a whole number.'
    if credits <= 0:
        return None, 'Credits must be greater than zero.'

    try:
        course = Course.objects.create(
            code=code, title=title, description=data.get('description', ''),
            credits=credits, department_id=data['department_id'],
            semester=data.get('semester') or 'first', level=data.get('level') or '100',
            is_elective=bool(data.get('is_elective')),
        )
    except Exception as e:
        return None, f'Failed to create course: {e}'
    return course, None


def update_course(course_id, data):
    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        return None, 'Course not found.'

    code = (data.get('code') or '').strip().upper()
    if code and code != course.code and Course.objects.filter(code=code).exclude(id=course.id).exists():
        return None, f'Course code {code} already exists.'

    try:
        credits = int(data.get('credits') or course.credits)
    except (TypeError, ValueError):
        return None, 'Credits must be a whole number.'

    course.code = code or course.code
    course.title = (data.get('title') or course.title).strip()
    course.description = data.get('description', course.description)
    course.credits = credits
    course.department_id = data.get('department_id') or course.department_id
    course.semester = data.get('semester') or course.semester
    course.level = data.get('level') or course.level
    course.is_elective = bool(data.get('is_elective'))
    course.save()
    return course, None


def delete_course(course_id):
    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        return False, 'Course not found.'
    code = course.code
    course.delete()
    return True, f'Course {code} deleted.'


def assign_course_lecturer(course_id, lecturer_id):
    """Mirrors SuperAdminCourseViewSet.assign_lecturer exactly, including
    the department-match enforcement."""
    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        return None, 'Course not found.'
    try:
        lecturer = Lecturer.objects.get(id=lecturer_id)
    except Lecturer.DoesNotExist:
        return None, 'Lecturer not found.'
    if lecturer.department_id != course.department_id:
        return None, f'{lecturer.user.get_full_name()} belongs to {lecturer.department}, not {course.department}.'
    course.lecturer = lecturer
    course.save(update_fields=['lecturer', 'updated_at'])
    return course, None


def remove_course_lecturer(course_id):
    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        return None, 'Course not found.'
    course.lecturer = None
    course.save(update_fields=['lecturer', 'updated_at'])
    return course, None


# ---------------------------------------------------------------------------
# Semester / Session management (SuperAdminSemesterViewSet -- plain CRUD;
# the "only one is_current semester" invariant is enforced authoritatively
# at the model layer, Semester.save(), so nothing extra is needed here)
# ---------------------------------------------------------------------------

def get_semesters():
    return Semester.objects.all().order_by('-start_date')


def create_semester(data):
    session = (data.get('session') or '').strip()
    semester = data.get('semester')
    if not session or semester not in ('first', 'second'):
        return None, 'Session and semester are required.'
    if not all([data.get('start_date'), data.get('end_date'), data.get('registration_deadline')]):
        return None, 'Start date, end date, and registration deadline are required.'
    if Semester.objects.filter(session=session, semester=semester).exists():
        return None, f'{session} ({semester} semester) already exists.'

    try:
        sem = Semester.objects.create(
            session=session, semester=semester,
            start_date=data['start_date'], end_date=data['end_date'],
            registration_deadline=data['registration_deadline'],
            is_current=bool(data.get('is_current')),
            is_registration_active=bool(data.get('is_registration_active')),
        )
    except Exception as e:
        return None, f'Failed to create semester: {e}'
    return sem, None


def update_semester(semester_id, data):
    try:
        sem = Semester.objects.get(id=semester_id)
    except Semester.DoesNotExist:
        return None, 'Semester not found.'

    sem.start_date = data.get('start_date') or sem.start_date
    sem.end_date = data.get('end_date') or sem.end_date
    sem.registration_deadline = data.get('registration_deadline') or sem.registration_deadline
    sem.is_current = bool(data.get('is_current'))
    sem.is_registration_active = bool(data.get('is_registration_active'))
    sem.save()
    return sem, None


# ---------------------------------------------------------------------------
# Level configuration (LevelConfigurationViewSet)
# ---------------------------------------------------------------------------

def get_level_configs():
    return AcademicLevelConfiguration.objects.select_related('current_semester').order_by('level')


def init_level_config_defaults():
    current_sem = Semester.objects.filter(is_current=True).first() or Semester.objects.order_by('-start_date').first()
    if not current_sem:
        return None, 'No semester exists yet -- create one first.'

    created = []
    for level, _ in LEVEL_CHOICES:
        config, was_created = AcademicLevelConfiguration.objects.get_or_create(
            level=level, defaults={'current_semester': current_sem, 'is_registration_open': True},
        )
        if was_created:
            created.append(level)
    return created, None


def update_level_config(config_id, current_semester_id, is_registration_open):
    try:
        config = AcademicLevelConfiguration.objects.get(id=config_id)
    except AcademicLevelConfiguration.DoesNotExist:
        return None, 'Level configuration not found.'
    if current_semester_id:
        try:
            config.current_semester = Semester.objects.get(id=current_semester_id)
        except Semester.DoesNotExist:
            return None, 'Semester not found.'
    config.is_registration_open = bool(is_registration_open)
    config.save()
    return config, None


# ---------------------------------------------------------------------------
# System-wide actions (SuperAdminManagementViewSet.start_new_session /
# promote_students) -- deliberately left for this phase by Phase 10
# (ICT), which is IsSuperAdmin-only on the backend. Ported exactly.
# ---------------------------------------------------------------------------

def start_new_session(session_name, start_date):
    session_name = (session_name or '').strip()
    if not session_name or not start_date:
        return None, 'Session name and start date are required.'
    try:
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
    except ValueError:
        return None, 'Invalid start date.'

    with transaction.atomic():
        Semester.objects.all().update(is_current=False, is_registration_active=False)
        new_semester = Semester.objects.create(
            session=session_name, semester='first', start_date=start_date,
            end_date=start_date + timedelta(days=120),
            registration_deadline=start_date + timedelta(days=21),
            is_current=True, is_registration_active=True,
        )
        AcademicLevelConfiguration.objects.all().update(current_semester=new_semester, is_registration_open=True)

    return new_semester, None


def promote_students():
    """No CGPA/credit/clearance eligibility gate -- see module docstring."""
    with transaction.atomic():
        graduated = Student.objects.filter(level='300', status='active').update(status='graduated')
        to_300 = Student.objects.filter(level='200', status='active').update(level='300')
        to_200 = Student.objects.filter(level='100', status='active').update(level='200')
    return {'graduated': graduated, 'promoted_to_300': to_300, 'promoted_to_200': to_200}
