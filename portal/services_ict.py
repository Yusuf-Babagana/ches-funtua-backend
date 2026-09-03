"""
ICT-facing business logic for the Django-template frontend. Ports
users/views_ict.py (ICTDashboardViewSet, UserManagementViewSet,
StaffAccountCreationViewSet, SystemConfigurationViewSet) -- not a
rewrite, with two deliberate exceptions:

1. Student registration here is a genuinely NEW, properly ICT-gated view
   -- the old Next.js frontend's "Register Student" page called the
   PUBLIC, unauthenticated `/auth/register/student/` endpoint
   (users/views.py, AllowAny), which the migration inventory flags as
   almost certainly unintended (S6 item 15). register_student() below is
   the real replacement: same account-creation shape, reachable only
   through this ICT/super-admin-gated portal view, with the matric
   number generated authoritatively server-side instead of the old
   page's client-side Date.now()-based scheme.

2. reset_user_password/toggle_user_active/create_staff_account all add a
   super-admin protection check that users/views_ict.py's equivalent DRF
   actions were missing (CanManageAllUsers/CanResetPasswords exist in
   users/permissions.py specifically to prevent an ICT officer from
   touching a Super Admin account, but were never wired to any view --
   migration inventory S1.5). That DRF-layer gap has also been closed
   directly in users/views_ict.py in this same phase, so both layers
   agree.

Deliberately NOT ported (per user decision for this phase): "Start New
Session" / "Promote Students" -- the old ICT frontend called these, but
the backing endpoints (academics/views_admin.py:SuperAdminManagementViewSet)
are IsSuperAdmin-only. Left for Phase 11 (Super Admin) rather than widening
that permission boundary as a side effect of this migration phase.

Also NOT ported: the fake/decorative parts of the old ICT surface --
system_logs (hardcoded fake log entries), user_activity's IP/user-agent/
total-logins (hardcoded), account_lockout_status ("suspicious accounts"
heuristic, no real lockout system exists), send_password_reset_links (fake
link, no email actually sent), the dashboard's "pending_requests" (always
0/0/0/0), and the old System Config page's Maintenance Mode toggle / Clear
Cache button (both were dead UI with no backend support). Building real
pages around fabricated data would be worse than not building them.
"""
import secrets
import string
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from academics.constants import MAX_CREDIT_UNITS_PAID
from academics.models import Course, Department, Semester
from users.models import Lecturer, StaffProfile, Student, User

STAFF_ROLES = ['registrar', 'bursar', 'exam-officer', 'desk-officer', 'ict', 'super-admin']
LECTURER_DESIGNATIONS = [
    ('professor', 'Professor'),
    ('associate_professor', 'Associate Professor'),
    ('senior_lecturer', 'Senior Lecturer'),
    ('lecturer_1', 'Lecturer I'),
    ('lecturer_2', 'Lecturer II'),
    ('assistant_lecturer', 'Assistant Lecturer'),
]


def _generate_random_password():
    alphabet = string.ascii_letters + string.digits + '!@#$%^&*'
    return ''.join(secrets.choice(alphabet) for _ in range(12))


def _generate_staff_id(prefix):
    import random
    while True:
        staff_id = f'{prefix}-{random.randint(1000, 9999)}'
        if not Lecturer.objects.filter(staff_id=staff_id).exists() and \
           not StaffProfile.objects.filter(staff_id=staff_id).exists():
            return staff_id


# ---------------------------------------------------------------------------
# Dashboard (ICTDashboardViewSet.overview)
# ---------------------------------------------------------------------------

def get_dashboard_data():
    total_users = User.objects.count()
    active_users = User.objects.filter(is_active=True).count()

    thirty_days_ago = timezone.now() - timedelta(days=30)
    week_ago = timezone.now() - timedelta(days=7)

    system_statistics = {
        'total_users': total_users,
        'active_users': active_users,
        'inactive_users': total_users - active_users,
        'users_by_role': list(User.objects.values('role').annotate(count=Count('id')).order_by('-count')),
        'recent_logins': User.objects.filter(last_login__gte=thirty_days_ago).count(),
        'new_users_last_week': User.objects.filter(created_at__gte=week_ago).count(),
    }

    dept_stats = []
    for dept in Department.objects.all():
        student_count = Student.objects.filter(department=dept).count()
        lecturer_count = Lecturer.objects.filter(department=dept).count()
        if student_count or lecturer_count:
            dept_stats.append({'department': dept.name, 'students': student_count, 'lecturers': lecturer_count})

    user_statistics = {
        'students': Student.objects.count(),
        'lecturers': Lecturer.objects.count(),
        'hod_count': Lecturer.objects.filter(is_hod=True).count(),
        'staff': StaffProfile.objects.count(),
        'department_distribution': dept_stats,
        'users_without_profiles': User.objects.filter(
            Q(student_profile__isnull=True) & Q(lecturer_profile__isnull=True) & Q(staff_profile__isnull=True),
        ).exclude(role='super-admin').count(),
    }

    day_ago = timezone.now() - timedelta(hours=24)
    recent_activities = []
    for user in User.objects.filter(created_at__gte=day_ago).select_related(
        'student_profile', 'lecturer_profile', 'staff_profile',
    )[:5]:
        profile_type = 'Student' if hasattr(user, 'student_profile') else \
            'Lecturer' if hasattr(user, 'lecturer_profile') else \
            'Staff' if hasattr(user, 'staff_profile') else 'User'
        recent_activities.append({
            'title': f'New {profile_type} Account Created',
            'details': f'{user.get_full_name()} ({user.email})',
            'timestamp': user.created_at,
        })

    health_checks = []
    users_without_profiles = user_statistics['users_without_profiles']
    if users_without_profiles:
        health_checks.append({'status': 'warning', 'message': f'{users_without_profiles} user(s) have no associated profile.'})
    depts_without_hod = Department.objects.filter(hod__isnull=True).count()
    if depts_without_hod:
        health_checks.append({'status': 'warning', 'message': f'{depts_without_hod} department(s) have no HOD assigned.'})
    courses_without_lecturers = Course.objects.filter(lecturer__isnull=True).count()
    if courses_without_lecturers:
        health_checks.append({'status': 'info', 'message': f'{courses_without_lecturers} course(s) have no lecturer assigned.'})
    inactive_super_admins = User.objects.filter(role='super-admin', is_active=False).count()
    if inactive_super_admins:
        health_checks.append({'status': 'critical', 'message': f'{inactive_super_admins} Super Admin account(s) are inactive.'})

    overall_status = 'healthy'
    if any(c['status'] == 'critical' for c in health_checks):
        overall_status = 'critical'
    elif any(c['status'] == 'warning' for c in health_checks):
        overall_status = 'warning'

    return {
        'system_statistics': system_statistics,
        'user_statistics': user_statistics,
        'recent_activities': recent_activities,
        'system_health': {'overall_status': overall_status, 'checks': health_checks},
    }


# ---------------------------------------------------------------------------
# User management (UserManagementViewSet)
# ---------------------------------------------------------------------------

def search_users(query=None, role=None, active=None):
    users = User.objects.select_related('student_profile', 'lecturer_profile', 'staff_profile')
    if query:
        users = users.filter(
            Q(email__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query) |
            Q(username__icontains=query) | Q(student_profile__matric_number__icontains=query) |
            Q(lecturer_profile__staff_id__icontains=query) | Q(staff_profile__staff_id__icontains=query)
        )
    if role:
        users = users.filter(role=role)
    if active == 'active':
        users = users.filter(is_active=True)
    elif active == 'inactive':
        users = users.filter(is_active=False)
    return users.order_by('-created_at')[:100]


def reset_user_password(actor, user_id, new_password):
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return False, 'User not found.'
    if user.role == 'super-admin' and actor.role != 'super-admin':
        return False, 'ICT officers cannot reset a Super Admin account\'s password.'
    if len(new_password or '') < 8:
        return False, 'Password must be at least 8 characters.'
    user.set_password(new_password)
    user.save()
    return True, f'Password reset for {user.email}.'


def toggle_user_active(actor, user_id):
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return False, 'User not found.'
    if user == actor:
        return False, 'You cannot deactivate your own account.'
    if user.role == 'super-admin' and actor.role != 'super-admin':
        return False, 'ICT officers cannot activate/deactivate a Super Admin account.'
    user.is_active = not user.is_active
    user.save()
    return True, f'{user.email} has been {"activated" if user.is_active else "deactivated"}.'


# ---------------------------------------------------------------------------
# Staff account creation (StaffAccountCreationViewSet)
# ---------------------------------------------------------------------------

def create_staff_account(actor, role, data):
    """Mirrors _create_staff_account for every role except student, plus
    the same super-admin guard added to reset_user_password/
    toggle_user_active above -- only a Super Admin can provision another
    Super Admin account."""
    if role == 'super-admin' and actor.role != 'super-admin':
        return None, 'ICT officers cannot create a Super Admin account.'

    email = (data.get('email') or '').strip().lower()
    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    if not all([email, first_name, last_name]):
        return None, 'Email, first name, and last name are required.'
    if User.objects.filter(email=email).exists():
        return None, 'A user with this email already exists.'
    if role in ('lecturer', 'hod') and not data.get('department_id'):
        return None, 'Department is required for lecturer/HOD accounts.'

    password = _generate_random_password()
    try:
        with transaction.atomic():
            username = email.split('@')[0]
            # create_user requires a unique username -- fall back to the
            # generated staff id if the email-derived one collides.
            if User.objects.filter(username=username).exists():
                username = _generate_staff_id(role.upper()[:3])

            user = User.objects.create_user(
                email=email, username=username, first_name=first_name, last_name=last_name,
                role=role, phone=data.get('phone', ''), is_active=True, password=password,
            )

            if role in ('lecturer', 'hod'):
                lecturer = Lecturer.objects.create(
                    user=user,
                    staff_id=data.get('staff_id') or _generate_staff_id('LEC'),
                    department_id=data.get('department_id'),
                    designation=data.get('designation') or 'lecturer_1',
                    is_hod=(role == 'hod'),
                )
                if role == 'hod' and data.get('department_id'):
                    Department.objects.filter(id=data['department_id']).update(hod=lecturer)
            else:
                StaffProfile.objects.create(
                    user=user,
                    staff_id=data.get('staff_id') or _generate_staff_id(role.upper()[:3]),
                    department=data.get('department', ''),
                    position=data.get('position') or role.replace('-', ' ').title(),
                )
    except Exception as e:
        return None, f'Failed to create account: {e}'

    # _send_welcome_email in the original was a no-op stub -- not
    # reproduced here either; the generated password is returned below
    # for the ICT officer to relay manually, same as the original did.
    return {'user': user, 'password': password}, None


# ---------------------------------------------------------------------------
# Student registration -- NEW, properly ICT-gated (see module docstring)
# ---------------------------------------------------------------------------

def _generate_ict_matric_number(department, level, session):
    """Authoritative server-side matric number, replacing the old ICT
    frontend's client-side Date.now()-based scheme. Same
    dept/session/sequence shape as Registrar's suggest_matric_number()
    (portal/services_registrar.py), adapted to use `level` instead of a
    programme code since ICT's direct-registration path has no
    Application to read a programme_type from."""
    dept_code = department.code
    session_year = session.split('/')[0][-2:] if session else timezone.now().strftime('%y')
    prefix = f"{dept_code}/{session_year}/{level}"

    last_matric = Student.objects.filter(
        matric_number__startswith=prefix,
    ).order_by('-matric_number').values_list('matric_number', flat=True).first()

    next_seq = 1
    if last_matric:
        try:
            next_seq = int(last_matric.split('/')[-1]) + 1
        except (ValueError, IndexError):
            next_seq = 1
    return f"{prefix}/{next_seq:03d}"


def register_student(data):
    email = (data.get('email') or '').strip().lower()
    first_name = (data.get('first_name') or '').strip()
    last_name = (data.get('last_name') or '').strip()
    department_id = data.get('department_id')
    level = data.get('level') or '100'

    if not all([email, first_name, last_name, department_id]):
        return None, 'Email, first name, last name, and department are required.'
    if User.objects.filter(email=email).exists():
        return None, 'A user with this email already exists.'
    try:
        department = Department.objects.get(id=department_id)
    except Department.DoesNotExist:
        return None, 'Department not found.'

    current_semester = Semester.objects.filter(is_current=True).first()
    if not current_semester:
        return None, 'No active semester found -- cannot determine the admission session.'

    matric_number = _generate_ict_matric_number(department, level, current_semester.session)
    password = _generate_random_password()

    with transaction.atomic():
        user = User.objects.create_user(
            email=email, username=matric_number, first_name=first_name, last_name=last_name,
            role='student', phone=data.get('phone', ''), is_active=True, password=password,
        )
        student = Student.objects.create(
            user=user, matric_number=matric_number, department=department, level=level,
            status='active', admission_date=timezone.now().date(),
        )

    return {'student': student, 'password': password}, None


# ---------------------------------------------------------------------------
# Bulk result import (academics/views_ict.py: ResultUploadView) -- ported,
# with the same status='draft' fix applied to that DRF endpoint in this
# same phase (see module docstring), plus a score-parsing fix: the
# original's `str(score_val).isdigit()` check silently zeroed out any
# decimal score (e.g. "75.5") since "." isn't a digit -- replaced with a
# real float parse.
# ---------------------------------------------------------------------------

def import_results_csv(csv_file, session):
    import re

    import pandas as pd

    from academics.models import Enrollment, Grade

    students = Student.objects.select_related('user').all()
    student_lookup = {
        frozenset(f"{s.user.first_name} {s.user.last_name}".strip().upper().split()): s
        for s in students
    }

    df = pd.read_csv(csv_file)
    name_col = next((c for c in df.columns if 'NAME' in c.upper()), None)
    course_cols = [c for c in df.columns if re.search(r'[A-Z]{3}\s?\d{3}', c)]
    if not name_col:
        return None, "No 'Name' column found in the file."

    results = {'processed': 0, 'skipped': [], 'errors': []}
    with transaction.atomic():
        for _, row in df.iterrows():
            raw_name = str(row[name_col]).strip().upper()
            student = student_lookup.get(frozenset(raw_name.split()))
            if not student:
                results['skipped'].append(raw_name)
                continue

            for col in course_cols:
                try:
                    score = float(row[col])
                    if pd.isna(score):
                        score = 0
                except (TypeError, ValueError):
                    score = 0
                if score == 0:
                    continue

                match = re.search(r'([A-Z]{3}\s?\d{3})', col)
                course_code = match.group(1)
                try:
                    course = Course.objects.get(code=course_code)
                except Course.DoesNotExist:
                    results['errors'].append(f'Course {course_code} not found.')
                    continue

                digits = re.sub(r'\D', '', course_code)
                semester = 'first' if int(digits[1]) % 2 != 0 else 'second'

                enrollment, _ = Enrollment.objects.get_or_create(
                    student=student, course=course, session=session, semester=semester,
                    defaults={'status': 'completed'},
                )
                Grade.objects.update_or_create(
                    student=student, course=course, session=session, semester=semester,
                    defaults={'enrollment': enrollment, 'score': score, 'status': 'draft'},
                )

            results['processed'] += 1

    return results, None


# ---------------------------------------------------------------------------
# System configuration (SystemConfigurationViewSet) -- only the parts
# backed by real, persisted data (see module docstring for what's
# deliberately skipped).
# ---------------------------------------------------------------------------

def get_system_config():
    current_semester = Semester.objects.filter(is_current=True).first()
    return {
        'current_semester': current_semester,
        'registration_enabled': current_semester.is_registration_active if current_semester else False,
        'max_credit_units_paid': MAX_CREDIT_UNITS_PAID,
    }


def set_registration_enabled(enabled):
    current_semester = Semester.objects.filter(is_current=True).first()
    if not current_semester:
        return False, 'No active semester found.'
    current_semester.is_registration_active = enabled
    current_semester.save(update_fields=['is_registration_active', 'updated_at'])
    return True, f"Registration {'enabled' if enabled else 'disabled'} for {current_semester.session}."


def get_department_configuration():
    rows = []
    for dept in Department.objects.select_related('hod__user').all():
        rows.append({
            'department': dept,
            'student_count': Student.objects.filter(department=dept).count(),
            'lecturer_count': Lecturer.objects.filter(department=dept).count(),
            'course_count': Course.objects.filter(department=dept).count(),
            'available_lecturers': Lecturer.objects.filter(department=dept).select_related('user').order_by('user__last_name'),
        })
    return rows


def update_department(department_id, name, code, description, hod_id=None):
    try:
        department = Department.objects.get(id=department_id)
    except Department.DoesNotExist:
        return None, 'Department not found.'

    code = (code or '').strip().upper()
    if code and code != department.code and Department.objects.filter(code=code).exclude(id=department.id).exists():
        return None, f'Department code {code} is already in use.'

    department.name = (name or department.name).strip()
    department.code = code or department.code
    department.description = description if description is not None else department.description

    if hod_id:
        try:
            lecturer = Lecturer.objects.get(id=hod_id, department=department)
        except Lecturer.DoesNotExist:
            return None, 'Lecturer not found in this department.'
        department.hod = lecturer
        lecturer.is_hod = True
        lecturer.save(update_fields=['is_hod', 'updated_at'])
    else:
        department.hod = None

    department.save()
    return department, None


def create_department(name, code, description=''):
    name = (name or '').strip()
    code = (code or '').strip().upper()
    if not name or not code:
        return None, 'Name and code are required.'
    if Department.objects.filter(code=code).exists():
        return None, f'Department code {code} already exists.'
    department = Department.objects.create(name=name, code=code, description=description or '')
    return department, None


def delete_department(department_id):
    """
    Not in the old ICT frontend at all -- added here (Phase 11, Super
    Admin) as the department-management story's missing piece, since
    this phase routes Super Admin's department management through this
    same page rather than building a separate one. Deliberately more
    conservative than the old Next.js Super Admin Departments page,
    which let a department be deleted with just a client-side confirm
    dialog despite Course.department being CASCADE -- silently deleting
    every course in that department along with it. Blocked here
    server-side whenever the department still has any courses, students,
    or lecturers attached, so a destructive cascade can't happen by
    accident; the caller has to clear those out (or reassign them) first.
    """
    try:
        department = Department.objects.get(id=department_id)
    except Department.DoesNotExist:
        return False, 'Department not found.'

    from academics.models import Course
    blockers = []
    student_count = Student.objects.filter(department=department).count()
    lecturer_count = Lecturer.objects.filter(department=department).count()
    course_count = Course.objects.filter(department=department).count()
    if student_count:
        blockers.append(f'{student_count} student(s)')
    if lecturer_count:
        blockers.append(f'{lecturer_count} lecturer(s)')
    if course_count:
        blockers.append(f'{course_count} course(s)')
    if blockers:
        return False, f'Cannot delete {department.name} -- it still has {", ".join(blockers)}. Reassign or remove them first.'

    name = department.name
    department.delete()
    return True, f'Department {name} deleted.'
