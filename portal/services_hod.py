"""
HOD-facing business logic for the Django-template frontend. Ports
academics/views_hod.py (department overview, students, lecturers, course
allocation) and the HOD leg of academics/views_result_workflow.py
(result approvals) -- not a rewrite.

Security fix carried over from the migration inventory (§3.3, §6.15):
the original HODDashboardViewSet.courses and .available_lecturers
actions call `Course.objects.all()` / `Lecturer.objects.all()` -- NOT
scoped to the HOD's own department, unlike the equivalent Super Admin
action which does enforce a department match. That's flagged in the
inventory as a bug to close, not reproduce, so both are scoped to
`department` here. assign_course_lecturer/remove_course_lecturer are
likewise given a department-match check they didn't have before,
brought in line with what Super Admin's equivalent action already does.
The HOD's own students/lecturers actions were already correctly scoped
in the original code and are ported as-is.

Also NOT ported: the HOD students page in the old frontend called the
globally-open `/auth/students/` endpoint (no server-side department
scoping at all -- a bigger permission gap flagged in the inventory,
§1.3) and an inline "add student" form hitting the public
`register/student/` endpoint. Matriculating new students is a
Registrar responsibility elsewhere in this system; the HOD student
directory here is the properly department-scoped, read-only
HODDashboardViewSet.students view instead.
"""
from django.db.models import Q

from academics.models import Announcement, Course, CourseOffering, Department, Semester
from users.models import Lecturer, Student


def get_hod_department(lecturer):
    """The department this lecturer heads, or None."""
    return Department.objects.filter(hod=lecturer).first()


def get_dashboard_data(department):
    total_students = Student.objects.filter(department=department).count()
    total_lecturers = Lecturer.objects.filter(department=department).count()
    dept_courses = Course.objects.filter(department=department).select_related('lecturer__user')

    from django.utils import timezone
    thirty_days_ago = timezone.now() - timezone.timedelta(days=30)
    recent_students = Student.objects.filter(
        department=department, created_at__gte=thirty_days_ago,
    ).select_related('user').order_by('-created_at')[:10]

    current_semester = Semester.objects.filter(is_current=True).first()

    return {
        'stats': {
            'students': total_students,
            'lecturers': total_lecturers,
            'courses': dept_courses.count(),
            'courses_with_lecturers': dept_courses.filter(lecturer__isnull=False).count(),
            'courses_without_lecturers': dept_courses.filter(lecturer__isnull=True).count(),
        },
        'recent_students': recent_students,
        'courses_summary': dept_courses[:8],
        'current_semester': current_semester,
    }


def get_department_students(department, level=None, status=None, search=None):
    students = Student.objects.filter(department=department).select_related('user').order_by('matric_number')
    if level:
        students = students.filter(level=level)
    if status:
        students = students.filter(status=status)
    if search:
        students = students.filter(
            Q(user__first_name__icontains=search) | Q(user__last_name__icontains=search) |
            Q(matric_number__icontains=search) | Q(user__email__icontains=search)
        )
    return students


def get_department_lecturers(department, designation=None, search=None):
    lecturers = Lecturer.objects.filter(department=department).select_related('user').order_by('staff_id')
    if designation:
        lecturers = lecturers.filter(designation=designation)
    if search:
        lecturers = lecturers.filter(
            Q(user__first_name__icontains=search) | Q(user__last_name__icontains=search) |
            Q(staff_id__icontains=search) | Q(specialization__icontains=search)
        )
    for lecturer in lecturers:
        lecturer.course_count = Course.objects.filter(lecturer=lecturer).count()
    return lecturers


def get_department_courses(department, level=None, has_lecturer=None, search=None):
    """Department-scoped (see module docstring -- the original wasn't)."""
    courses = Course.objects.filter(department=department).select_related('lecturer__user').order_by('code')
    if level:
        courses = courses.filter(level=level)
    if has_lecturer == 'true':
        courses = courses.filter(lecturer__isnull=False)
    elif has_lecturer == 'false':
        courses = courses.filter(lecturer__isnull=True)
    if search:
        courses = courses.filter(Q(code__icontains=search) | Q(title__icontains=search))
    return courses


def get_available_lecturers(department):
    """Department-scoped (see module docstring -- the original wasn't)."""
    lecturers = Lecturer.objects.filter(department=department).select_related('user').order_by('user__last_name')
    for lecturer in lecturers:
        lecturer.current_course_count = Course.objects.filter(lecturer=lecturer).count()
    return lecturers


def assign_course_lecturer(department, course_id, lecturer_id):
    """Returns (ok, message). Enforces department match on both sides."""
    try:
        course = Course.objects.get(id=course_id, department=department)
    except Course.DoesNotExist:
        return False, 'Course not found in your department.'

    try:
        lecturer = Lecturer.objects.get(id=lecturer_id, department=department)
    except Lecturer.DoesNotExist:
        return False, 'Lecturer not found in your department.'

    if course.lecturer == lecturer:
        return False, 'Lecturer is already assigned to this course.'

    course.lecturer = lecturer
    course.save()
    return True, f'Assigned {lecturer.user.get_full_name()} to {course.code}.'


def remove_course_lecturer(department, course_id):
    try:
        course = Course.objects.get(id=course_id, department=department)
    except Course.DoesNotExist:
        return False, 'Course not found in your department.'

    if not course.lecturer:
        return False, 'No lecturer assigned to this course.'

    old_name = course.lecturer.user.get_full_name()
    course.lecturer = None
    course.save()
    return True, f'Removed {old_name} from {course.code}.'


# ---------------------------------------------------------------------------
# Result approvals (academics/views_result_workflow.py: HODResultWorkflowViewSet)
# ---------------------------------------------------------------------------

def get_current_semester():
    return Semester.objects.filter(is_current=True).first() or Semester.objects.last()


def get_pending_result_reviews(department):
    semester = get_current_semester()
    if not semester:
        return []

    from academics.models import Grade
    courses = Course.objects.filter(
        department=department,
        grades__status='submitted',
        grades__session=semester.session,
        grades__semester=semester.semester,
    ).distinct()

    results = []
    for course in courses:
        grades = Grade.objects.filter(
            course=course, status='submitted', session=semester.session, semester=semester.semester,
        )
        total = grades.count()
        failed = grades.filter(grade_letter='F').count()
        results.append({
            'course': course,
            'pending_count': total,
            'failed_count': failed,
            'passed_count': total - failed,
        })
    return results


def get_course_review_details(department, course_id):
    """Ownership-checked (course must belong to this HOD's department)."""
    from academics.models import Grade

    semester = get_current_semester()
    try:
        course = Course.objects.get(id=course_id, department=department)
    except Course.DoesNotExist:
        return None, None

    grades = Grade.objects.filter(
        course=course, status='submitted', session=semester.session, semester=semester.semester,
    ).select_related('student__user').order_by('student__matric_number')
    return course, grades


def approve_course_results(department, course_id):
    from academics.models import Grade
    semester = get_current_semester()
    try:
        course = Course.objects.get(id=course_id, department=department)
    except Course.DoesNotExist:
        return 0, 'Course not found in your department.'

    grades = Grade.objects.filter(
        course=course, status='submitted', session=semester.session, semester=semester.semester,
    )
    count = grades.count()
    if count == 0:
        return 0, 'No pending grades found.'
    grades.update(status='hod_approved')
    return count, None


def reject_course_results(department, course_id, reason):
    from academics.models import Grade
    semester = get_current_semester()
    try:
        course = Course.objects.get(id=course_id, department=department)
    except Course.DoesNotExist:
        return 0, 'Course not found in your department.'

    grades = Grade.objects.filter(
        course=course, status='submitted', session=semester.session, semester=semester.semester,
    )
    count = grades.count()
    grades.update(status='draft', remarks=f"HOD Rejection: {reason}")
    return count, None


# ---------------------------------------------------------------------------
# Announcements (new for the CHESF Student Portal Digest feature work --
# the model-level authoring surface is Django admin; this is the small
# "Post Announcement" action the plan calls for on dashboards that
# already exist. Always scoped to the HOD's own department -- never
# lets an HOD broadcast to the whole college.
# ---------------------------------------------------------------------------

def post_announcement(user, department, title, body, level='', is_pinned=False):
    title = (title or '').strip()
    body = (body or '').strip()
    if not title or not body:
        return None, 'Title and body are required.'

    announcement = Announcement.objects.create(
        title=title, body=body, posted_by=user, department=department,
        level=level or '', is_pinned=is_pinned,
    )
    return announcement, None
