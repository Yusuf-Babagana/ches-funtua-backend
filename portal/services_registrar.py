"""
Registrar-facing business logic for the Django-template frontend. Ports
academics/views_registrar.py's dashboard/matric-assignment logic and the
Registrar leg of academics/views_result_workflow.py (the canonical
result pipeline) -- not a rewrite.

Deliberately NOT ported as a separate surface: FinalResultApprovalViewSet
(academics/views_registrar.py). Per the migration inventory (§3.5, §6.8),
this is a second, incomplete result-approval path that duplicates the
canonical verified->published step -- its own HOD-approval check is a
stub that always returns True, and nothing it does is ever persisted as
an approval record (response-only). The inventory explicitly recommends
porting its genuinely useful anomaly-detection heuristics (>50% A's,
>30% F's, average outside 40-85, borderline scores at 59/69/79/89) into
the one real pipeline and dropping the rest -- done below in
get_pending_publications/get_publication_detail, layered on top of
RegistrarResultWorkflowViewSet's actual verified/published queries.

Also not ported as a separate page: the old frontend had two near
-identical pages (approvals/page.tsx and publication/page.tsx) both
showing the same verified-results-pending-publication list against the
same backend action. approvals/page.tsx's reject button was, per its
own inline comment, never actually wired ("Rejection capability
requires API update. Publishing only for this demo."). One page here
covers both, with reject actually implemented against
RegistrarResultWorkflowViewSet.process_result(action='reject').

Also not ported: FINAL_YEAR_LEVEL='400' as a graduating-student filter.
Course/FeeStructure/AcademicLevelConfiguration only define levels
100-300 in this system (see migration inventory §6.16) -- filtering by
level='400' silently returns zero students, which just hid a
broken feature rather than reproducing one. Dropped from the dashboard
stat rather than ported with a value that can't ever match real data.
"""
from django.db.models import Q
from django.utils import timezone

from academics.models import (
    Course, Department, Grade, Semester, Student,
)
from admissions.models import Application


# ---------------------------------------------------------------------------
# Dashboard (RegistrarDashboardViewSet.overview)
# ---------------------------------------------------------------------------

def get_dashboard_data():
    current_semester = Semester.objects.filter(is_current=True).first()

    pending_admissions = Application.objects.filter(status__in=['submitted', 'under_review']).count()
    admitted_without_matric = Application.objects.filter(status='admitted').exclude(
        admission_letter__matric_number__isnull=False,
    ).count()

    pending_publication = get_pending_publications()

    recent_students = Student.objects.select_related('user', 'department').order_by('-created_at')[:5]

    deadlines = []
    if current_semester:
        for title, d, kind in [
            ('Semester Start', current_semester.start_date, 'start'),
            ('Semester End', current_semester.end_date, 'end'),
            ('Registration Deadline', current_semester.registration_deadline, 'registration'),
        ]:
            if d:
                deadlines.append({'title': title, 'date': d, 'kind': kind, 'days_until': (d - timezone.now().date()).days})
        deadlines.sort(key=lambda x: x['date'])

    return {
        'current_semester': current_semester,
        'stats': {
            'total_students': Student.objects.count(),
            'total_departments': Department.objects.count(),
            'total_courses': Course.objects.count(),
            'pending_admissions': pending_admissions,
            'pending_matric_assignments': admitted_without_matric,
            'pending_publications': len(pending_publication),
        },
        'recent_students': recent_students,
        'deadlines': deadlines,
    }


# ---------------------------------------------------------------------------
# Matric assignment (MatricAssignmentViewSet)
# ---------------------------------------------------------------------------

PROGRAMME_CODES = {'nce': 'NCE', 'degree': 'BSC', 'diploma': 'DIP', 'pgd': 'PGD', 'masters': 'MSC'}


def _programme_code(programme_type):
    return PROGRAMME_CODES.get(programme_type, 'GEN')


def suggest_matric_number(application):
    if not application.first_choice_department:
        return None
    dept_code = application.first_choice_department.code
    session_year = application.session.split('/')[0][-2:]
    prog_code = _programme_code(application.programme_type)

    last_matric = Student.objects.filter(
        matric_number__startswith=f"{dept_code}/{session_year}/{prog_code}",
    ).order_by('-matric_number').values_list('matric_number', flat=True).first()

    next_seq = 1
    if last_matric:
        try:
            next_seq = int(last_matric.split('/')[-1]) + 1
        except (ValueError, IndexError):
            next_seq = 1
    return f"{dept_code}/{session_year}/{prog_code}/{next_seq:03d}"


def get_pending_matric_assignments():
    applications = Application.objects.filter(status='admitted').exclude(
        admission_letter__matric_number__isnull=False,
    ).select_related('first_choice_department', 'admission_letter').order_by('submitted_date')

    for app in applications:
        app.suggested_matric = suggest_matric_number(app)
    return applications


def assign_matric_number(application_id, matric_number):
    """Mirrors MatricAssignmentViewSet.assign_matric_numbers's per-item logic exactly."""
    from django.db import transaction

    matric_number = matric_number.strip().upper()
    try:
        with transaction.atomic():
            application = Application.objects.select_related('first_choice_department', 'admission_letter').get(
                id=application_id, status='admitted',
            )

            if Student.objects.filter(matric_number=matric_number).exists():
                return None, f'Matric number {matric_number} already exists.'

            if not hasattr(application, 'admission_letter'):
                return None, 'No admission letter found for this application.'

            admission_letter = application.admission_letter
            admission_letter.matric_number = matric_number
            admission_letter.save()

            student = _create_student_record(application, matric_number)
            return student, None
    except Application.DoesNotExist:
        return None, 'Application not found or not admitted.'
    except Exception as e:
        return None, str(e)


def _create_student_record(application, matric_number):
    import secrets
    import string

    from users.models import User

    password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(12))
    user = User.objects.create_user(
        email=application.email, username=matric_number,
        first_name=application.first_name, last_name=application.last_name,
        role='student', phone=application.phone, is_active=True, password=password,
    )
    student = Student.objects.create(
        user=user, matric_number=matric_number, level='100',
        department=application.first_choice_department, status='active',
        admission_date=application.admission_letter.issued_date,
        date_of_birth=application.date_of_birth, address=application.address,
        guardian_name=application.guardian_name, guardian_phone=application.guardian_phone,
    )
    # Welcome-email-with-credentials is a known gap (migration inventory §1.2,
    # §6.14): the original code generates this password and then silently
    # discards it via a no-op email stub. Not fixed here (implementing real
    # email delivery is new functionality, out of scope for a template
    # migration) -- but flagged rather than silently reproduced.
    return student


# ---------------------------------------------------------------------------
# Student records (the old frontend page never actually fetched data --
# see module docstring; this is a real, working implementation)
# ---------------------------------------------------------------------------

def get_students(search=None, status=None, department_id=None, level=None):
    students = Student.objects.select_related('user', 'department').order_by('matric_number')
    if search:
        students = students.filter(
            Q(user__first_name__icontains=search) | Q(user__last_name__icontains=search) |
            Q(matric_number__icontains=search) | Q(user__email__icontains=search)
        )
    if status:
        students = students.filter(status=status)
    if department_id:
        students = students.filter(department_id=department_id)
    if level:
        students = students.filter(level=level)
    return students


# ---------------------------------------------------------------------------
# Result publication (RegistrarResultWorkflowViewSet, canonical pipeline)
# with the useful anomaly heuristics folded in from FinalResultApprovalViewSet
# ---------------------------------------------------------------------------

def _get_current_semester():
    return Semester.objects.filter(is_current=True).first() or Semester.objects.last()


BORDERLINE_SCORES = {59, 69, 79, 89}


def _detect_anomalies(grades):
    """Ported from FinalResultApprovalViewSet._check_result_anomalies /
    _identify_anomalies -- the one part of that file worth keeping."""
    total = grades.count()
    if total == 0:
        return False, []

    a_count = grades.filter(grade_letter='A').count()
    f_count = grades.filter(grade_letter='F').count()
    avg_score = sum(float(g.score) for g in grades) / total

    flagged = (a_count / total > 0.5) or (f_count / total > 0.3) or avg_score > 85 or avg_score < 40

    borderline_students = []
    for g in grades:
        if int(g.score) in BORDERLINE_SCORES or g.score > 95 or g.score < 30:
            borderline_students.append(g)

    return flagged or bool(borderline_students), borderline_students


def get_pending_publications():
    semester = _get_current_semester()
    if not semester:
        return []

    courses = Course.objects.filter(
        grades__status='verified', grades__session=semester.session, grades__semester=semester.semester,
    ).distinct().select_related('department', 'lecturer__user')

    results = []
    for course in courses:
        grades = Grade.objects.filter(
            course=course, status='verified', session=semester.session, semester=semester.semester,
        )
        total = grades.count()
        failed = grades.filter(grade_letter='F').count()
        has_anomalies, _ = _detect_anomalies(grades)
        avg_score = round(sum(float(g.score) for g in grades) / total, 1) if total else 0
        results.append({
            'course': course,
            'total_students': total,
            'passed_count': total - failed,
            'failed_count': failed,
            'average_score': avg_score,
            'has_anomalies': has_anomalies,
        })
    return results


def get_publication_detail(course_id):
    semester = _get_current_semester()
    try:
        course = Course.objects.select_related('department', 'lecturer__user').get(id=course_id)
    except Course.DoesNotExist:
        return None, None, False, []

    grades = Grade.objects.filter(
        course=course, status='verified', session=semester.session, semester=semester.semester,
    ).select_related('student__user').order_by('student__matric_number')

    has_anomalies, flagged_grades = _detect_anomalies(grades)
    flagged_ids = {g.id for g in flagged_grades}
    for g in grades:
        g.is_flagged = g.id in flagged_ids

    return course, grades, has_anomalies, flagged_grades


def publish_course_results(course_id):
    """Mirrors RegistrarResultWorkflowViewSet.publish exactly, including
    the GPA/CGPA recompute trigger."""
    from academics.views_result_workflow import BaseResultWorkflowViewSet

    semester = _get_current_semester()
    if not semester:
        return 0, 'No current semester set.'

    grades = Grade.objects.filter(
        course_id=course_id, status='verified', session=semester.session, semester=semester.semester,
    )
    if not grades.exists():
        return 0, 'No verified grades found.'

    count = grades.count()
    grades.update(status='published')

    course = Course.objects.get(id=course_id)
    BaseResultWorkflowViewSet()._update_student_academic_records(course, semester)
    return count, None


def reject_course_results(course_id, remark):
    """Mirrors RegistrarResultWorkflowViewSet.process_result(action='reject')."""
    semester = _get_current_semester()
    if not semester:
        return 0, 'No current semester set.'

    grades = Grade.objects.filter(
        course_id=course_id, status='verified', session=semester.session, semester=semester.semester,
    )
    if not grades.exists():
        return 0, 'No verifiable grades found for this course.'

    count = grades.count()
    grades.update(status='draft', remarks=f"Rejected by Registrar: {remark}")
    return count, None


# ---------------------------------------------------------------------------
# Transcript generation for any student (TranscriptViewSet.generate, ported
# via portal/services_student.get_transcript_data -- registrar has no
# department restriction, unlike the HOD caller of the same endpoint)
# ---------------------------------------------------------------------------

def find_students(search):
    if not search:
        return Student.objects.none()
    return Student.objects.filter(
        Q(user__first_name__icontains=search) | Q(user__last_name__icontains=search) |
        Q(matric_number__icontains=search) | Q(user__email__icontains=search)
    ).select_related('user', 'department')[:20]
