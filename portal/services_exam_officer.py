"""
Exam Officer-facing business logic for the Django-template frontend.
Ports academics/views_exam_officer.py (dashboard, registration approval,
result compilation, exam list) and the Exam Officer leg of
academics/views_result_workflow.py (the canonical result pipeline) --
not a rewrite.

Two things deliberately NOT ported as separate surfaces:

1. ExamTimetableViewSet -- per the migration inventory (§3.4), this is
   entirely non-persistent: no ExamTimetable model exists anywhere in
   the schema. current_timetable() doesn't read anything real, it
   generates a fresh, different fake list on every single call
   (round-robin over courses starting 2 weeks before semester end);
   generate_timetable() runs an in-memory scheduling algorithm and
   returns it without saving; publish_timetable() just echoes back the
   length of whatever you sent it. None of it is real data. Building a
   Django page against this would mean either reproducing fake data
   (against the brief's "do not create fake data" instruction) or
   quietly adding a new ExamTimetable model and migration, which is a
   schema change outside a template migration's scope without explicit
   sign-off. Flagged for a decision rather than silently built either way.

2. ResultCompilationViewSet.verify_course_results as the verify action.
   This view's own detail/anomaly-check UI is genuinely useful and is
   ported below (get_course_result_detail), but its verify action
   accepts grades in status 'submitted' OR 'hod_approved' -- i.e. it can
   skip the HOD-approval step entirely, which conflicts with the
   canonical draft->submitted->hod_approved->verified->published
   pipeline this migration has used consistently for HOD (Phase 5) and
   Registrar (Phase 6). The verify action here (verify_course_results)
   instead uses the same strict rule as
   ExamOfficerResultWorkflowViewSet.verify: only 'hod_approved' grades
   can become 'verified'. The old frontend actually shipped both
   (results/page.tsx used the loose one, verification/page.tsx used the
   strict one, as two separate pages) -- this consolidates them into
   one page using the strict rule throughout, consistent with how HOD's
   and Registrar's own steps in this same pipeline were already built.

Not ported at all (no corresponding frontend page found): ExamListViewSet
(eligible_students/generate_exam_list/download_exam_list) is real,
working, unused-by-any-page functionality -- flagged as available if
wanted, not built speculatively.
"""
from django.db.models import Count

from academics.models import (
    Course, CourseOffering, CourseRegistration, Department, Enrollment,
    Grade, Semester,
)
from users.models import Student

BORDERLINE_SCORES = {59, 69, 79, 89}


def get_current_semester():
    return Semester.objects.filter(is_current=True).first() or Semester.objects.last()


# ---------------------------------------------------------------------------
# Dashboard (ExamOfficerDashboardViewSet.overview)
# ---------------------------------------------------------------------------

def get_dashboard_data():
    current_semester = get_current_semester()
    if not current_semester:
        return {
            'current_semester': None, 'stats': {}, 'exam_statistics': {},
            'deadlines': [], 'recent_activities': [],
        }

    pending_registrations = CourseRegistration.objects.filter(
        status='approved_lecturer', is_payment_verified=True,
        course_offering__semester=current_semester,
    ).count()

    total_courses = Course.objects.filter(
        offerings__semester=current_semester, offerings__is_active=True,
    ).distinct().count()

    courses_with_grades = Course.objects.filter(
        grades__session=current_semester.session, grades__semester=current_semester.semester,
    ).distinct().count()

    total_grades = Grade.objects.filter(
        session=current_semester.session, semester=current_semester.semester,
    ).count()
    passing_grades = Grade.objects.filter(
        session=current_semester.session, semester=current_semester.semester,
        grade_letter__in=['A', 'B', 'C', 'D'],
    ).count()
    pass_rate = round((passing_grades / total_grades * 100), 1) if total_grades else 0

    from django.utils import timezone
    from datetime import timedelta
    deadlines = []
    if current_semester.end_date:
        reg_deadline = current_semester.end_date - timedelta(weeks=6)
        if reg_deadline > timezone.now().date():
            deadlines.append({'title': 'Registration Approval Deadline', 'date': reg_deadline})
        result_deadline = current_semester.end_date + timedelta(weeks=2)
        if result_deadline > timezone.now().date():
            deadlines.append({'title': 'Result Submission Deadline', 'date': result_deadline})

    week_ago = timezone.now() - timedelta(days=7)
    recent_grades = Grade.objects.filter(created_at__gte=week_ago).select_related(
        'course', 'uploaded_by__user',
    ).order_by('-created_at')[:5]

    return {
        'current_semester': current_semester,
        'stats': {
            'total_departments': Department.objects.count(),
            'total_courses': total_courses,
            'total_students': Student.objects.count(),
            'pending_registrations': pending_registrations,
            'courses_pending_results': total_courses,
        },
        'exam_statistics': {
            'completed_courses': courses_with_grades,
            'total_courses': total_courses,
            'completion_rate': round((courses_with_grades / total_courses * 100), 1) if total_courses else 0,
            'pass_rate': pass_rate,
        },
        'deadlines': deadlines,
        'recent_activities': recent_grades,
    }


# ---------------------------------------------------------------------------
# Registration approval (ExamOfficerRegistrationViewSet)
# ---------------------------------------------------------------------------

def get_pending_registration_approvals(department_id=None, course_id=None):
    current_semester = get_current_semester()
    if not current_semester:
        return []

    regs = CourseRegistration.objects.filter(
        status='approved_lecturer', is_payment_verified=True,
        course_offering__semester=current_semester,
    ).select_related(
        'student__user', 'student__department', 'course_offering__course',
        'course_offering__lecturer__user', 'approved_by_lecturer__user',
    )
    if department_id:
        regs = regs.filter(student__department_id=department_id)
    if course_id:
        regs = regs.filter(course_offering__course_id=course_id)
    return regs


def approve_registration(registration_id, exam_officer_user, action, reason=''):
    try:
        reg = CourseRegistration.objects.get(
            id=registration_id, status='approved_lecturer', is_payment_verified=True,
        )
    except CourseRegistration.DoesNotExist:
        return False, 'Registration not found or not ready for approval.'

    if action == 'approve':
        ok = reg.approve_by_exam_officer(exam_officer_user)
        return (True, 'Registration approved successfully.') if ok else (False, 'Cannot approve.')
    elif action == 'reject':
        ok = reg.reject_by_exam_officer(exam_officer_user, reason)
        return (True, 'Registration rejected.') if ok else (False, 'Cannot reject.')
    return False, 'Invalid action.'


def bulk_approve_registrations(registration_ids, exam_officer_user, action, reason=''):
    successful, failed = [], []
    for reg_id in registration_ids:
        try:
            reg = CourseRegistration.objects.get(
                id=reg_id, status='approved_lecturer', is_payment_verified=True,
            )
            if action == 'approve':
                reg.approve_by_exam_officer(exam_officer_user)
            else:
                reg.reject_by_exam_officer(exam_officer_user, reason)
            successful.append(reg_id)
        except Exception as e:
            failed.append((reg_id, str(e)))
    return successful, failed


# ---------------------------------------------------------------------------
# Result compilation (ResultCompilationViewSet, minus the loose verify path
# -- see module docstring)
# ---------------------------------------------------------------------------

def get_courses_pending_results():
    current_semester = get_current_semester()
    if not current_semester:
        return []

    courses = Course.objects.filter(
        offerings__semester=current_semester, offerings__is_active=True,
    ).distinct().select_related('department', 'lecturer__user')

    results = []
    for course in courses:
        enrolled_count = Enrollment.objects.filter(
            course=course, session=current_semester.session, semester=current_semester.semester,
            status='enrolled',
        ).count()
        grades_entered = Grade.objects.filter(
            course=course, session=current_semester.session, semester=current_semester.semester,
        ).count()
        hod_approved_count = Grade.objects.filter(
            course=course, session=current_semester.session, semester=current_semester.semester,
            status='hod_approved',
        ).count()
        completion_pct = round((grades_entered / enrolled_count * 100), 1) if enrolled_count else 0
        results.append({
            'course': course,
            'enrolled_count': enrolled_count,
            'grades_entered': grades_entered,
            'completion_percentage': completion_pct,
            'ready_to_verify': hod_approved_count,
        })
    return results


def get_course_result_detail(course_id):
    current_semester = get_current_semester()
    try:
        course = Course.objects.select_related('department', 'lecturer__user').get(id=course_id)
    except Course.DoesNotExist:
        return None

    grades = Grade.objects.filter(
        course=course, session=current_semester.session, semester=current_semester.semester,
    ).select_related('student__user').order_by('student__matric_number')

    scores = [float(g.score) for g in grades]
    stats = {
        'total_students': len(scores),
        'average_score': round(sum(scores) / len(scores), 2) if scores else 0,
        'highest_score': max(scores) if scores else 0,
        'lowest_score': min(scores) if scores else 0,
    }

    anomalies = []
    for g in grades:
        needs_review = int(g.score) in BORDERLINE_SCORES or g.score > 95 or g.score < 30
        g.needs_review = needs_review
        if needs_review:
            anomalies.append(g)

    hod_approved_count = grades.filter(status='hod_approved').count()

    return {
        'course': course,
        'grades': grades,
        'statistics': stats,
        'anomalies': anomalies,
        'can_verify': hod_approved_count > 0,
        'hod_approved_count': hod_approved_count,
    }


def verify_course_results(course_id):
    """
    Strict canonical rule (see module docstring): only 'hod_approved'
    grades become 'verified'. Mirrors
    ExamOfficerResultWorkflowViewSet.verify exactly.
    """
    current_semester = get_current_semester()
    if not current_semester:
        return 0, 'No academic session found.'

    grades = Grade.objects.filter(
        course_id=course_id, status='hod_approved',
        session=current_semester.session, semester=current_semester.semester,
    )
    count = grades.count()
    if count == 0:
        return 0, 'No HOD-approved grades pending verification for this course.'
    grades.update(status='verified')
    return count, None


def generate_master_sheet(course_id):
    """Mirrors ResultCompilationViewSet.generate_master_sheet exactly."""
    import pandas as pd
    from io import BytesIO
    from django.http import HttpResponse

    current_semester = get_current_semester()
    course = Course.objects.get(id=course_id)
    grades = Grade.objects.filter(
        course=course, session=current_semester.session, semester=current_semester.semester,
    ).select_related('student__user').order_by('student__matric_number')

    data = [{
        'S/N': i + 1,
        'Matric Number': g.student.matric_number,
        'Student Name': g.student.user.get_full_name(),
        'Score': float(g.score),
        'Grade': g.grade_letter,
        'Grade Points': float(g.grade_points),
        'Remarks': g.remarks or '',
    } for i, g in enumerate(grades)]

    df = pd.DataFrame(data)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Master Sheet', index=False)
    output.seek(0)

    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{course.code}_Master_Sheet_{current_semester.session}.xlsx"'
    return response
