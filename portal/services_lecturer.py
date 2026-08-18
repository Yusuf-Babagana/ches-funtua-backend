"""
Lecturer-facing business logic for the Django-template frontend. Ports the
logic already implemented in academics/views_lecturer.py and
academics/views_lecturer_attendance.py -- not a rewrite.

Grading convention note (see commit message / conversation for the full
finding): academics/views_lecturer.py's bulk_enter_grades sums CA + Exam
unweighted, which the migration inventory flagged as inconsistent with a
"CA 30% / Exam 70%" formula found in views_lecturer_students.py's
update_student_scores. Cross-checking against the real Next.js Gradebook
UI (the only screen actually wired to grade entry) shows CA is capped at
40 and Exam at 60 -- i.e. the two components are already pre-scaled to
sum to 100, so a direct sum is correct and applying 30/70 weighting on
top of it would silently corrupt every score (40+60 capped perfect score
would become 54/100, not 100/100). update_student_scores is not even
registered in academics/urls.py -- confirmed dead code, not a second
live convention. So: ported here as CA(0-40) + Exam(0-60), unweighted,
matching the one actually-live path exactly. The 40/60 caps are enforced
server-side below (the old frontend only enforced them in the browser).
"""
from datetime import date as date_cls

from django.db.models import Q

from academics.models import (
    Attendance, Course, CourseOffering, CourseRegistration, Enrollment,
    Grade, Semester,
)
from users.models import Student

MAX_CA_SCORE = 40
MAX_EXAM_SCORE = 60
ATTENDANCE_THRESHOLD = 75  # academics/views_lecturer_attendance.py: attendance_report


def get_current_semester():
    return Semester.objects.filter(is_current=True).first() or Semester.objects.order_by('-id').first()


# ---------------------------------------------------------------------------
# Dashboard (LecturerDashboardViewSet.overview)
# ---------------------------------------------------------------------------

def get_dashboard_data(lecturer):
    current_semester = get_current_semester()

    if current_semester:
        offerings = CourseOffering.objects.filter(
            lecturer=lecturer, semester=current_semester,
        ).select_related('course', 'course__department')
    else:
        offerings = CourseOffering.objects.none()

    total_students = 0
    if offerings.exists():
        total_students = CourseRegistration.objects.filter(
            course_offering__in=offerings, status='registered',
        ).values('student').distinct().count()

    courses = []
    for offering in offerings:
        student_count = CourseRegistration.objects.filter(
            course_offering=offering, status='registered',
        ).count()
        courses.append({
            'offering': offering,
            'course': offering.course,
            'student_count': student_count,
        })

    return {
        'current_semester': current_semester,
        'courses': courses,
        'stats': {
            'course_count': offerings.count(),
            'total_students': total_students,
        },
    }


# ---------------------------------------------------------------------------
# Course list (LecturerCourseViewSet queryset)
# ---------------------------------------------------------------------------

def get_courses(lecturer):
    current_semester = get_current_semester()
    courses = Course.objects.filter(lecturer=lecturer).select_related('department')

    result = []
    for course in courses:
        enrolled = 0
        if current_semester:
            offering = CourseOffering.objects.filter(course=course, semester=current_semester).first()
            if offering:
                enrolled = CourseRegistration.objects.filter(
                    course_offering=offering, status='registered',
                ).count()
        course.enrolled_students = enrolled
        result.append(course)
    return result


def get_owned_course(lecturer, course_id):
    """Ownership-checked course lookup -- never trust a course id in a URL alone."""
    return Course.objects.filter(id=course_id, lecturer=lecturer).select_related('department').first()


# ---------------------------------------------------------------------------
# Class roster / gradebook (LecturerCourseViewSet.students)
# ---------------------------------------------------------------------------

def get_course_roster(course):
    """
    Returns a list of {student, grade, attendance} dicts for every student
    registered in `course`'s current-semester offering. Mirrors
    LecturerCourseViewSet.students exactly for the grade portion; adds an
    attendance percentage (from views_lecturer_students.py's
    course_students) since both the class-list and gradebook pages need
    student identity + status together.
    """
    current_semester = get_current_semester()
    if not current_semester:
        return [], current_semester

    registrations = CourseRegistration.objects.filter(
        course_offering__course=course,
        course_offering__semester=current_semester,
        status__in=['registered', 'approved_exam_officer'],
    ).select_related('student__user', 'student__department').order_by('student__matric_number')

    roster = []
    for reg in registrations:
        student = reg.student
        grade = Grade.objects.filter(
            student=student, course=course,
            session=current_semester.session, semester=current_semester.semester,
        ).first()

        attendance_qs = Attendance.objects.filter(
            student=student, course=course, date__gte=current_semester.start_date,
        )
        total_classes = attendance_qs.count()
        present_classes = attendance_qs.filter(status='present').count()
        attendance_pct = round((present_classes / total_classes * 100), 1) if total_classes else None

        roster.append({
            'registration': reg,
            'student': student,
            'grade': grade,
            'is_locked': grade.status in ['submitted', 'hod_approved', 'verified', 'published'] if grade else False,
            'attendance_percent': attendance_pct,
        })
    return roster, current_semester


# ---------------------------------------------------------------------------
# Grade entry (LecturerGradeViewSet.bulk_enter_grades)
# ---------------------------------------------------------------------------

def save_grades(lecturer, course, entries, submit=False):
    """
    entries: list of {student_id, ca_score, exam_score, remarks}.
    Returns (successful_matrics, errors). Server-side clamps CA to
    [0, MAX_CA_SCORE] and Exam to [0, MAX_EXAM_SCORE] -- the old frontend
    only enforced this in the browser.
    """
    current_semester = get_current_semester()
    if not current_semester:
        return [], ['No academic session found.']

    target_status = 'submitted' if submit else 'draft'
    successful, errors = [], []

    for entry in entries:
        student_id = entry.get('student_id')
        if not student_id:
            continue
        try:
            ca_score = float(entry.get('ca_score') or 0)
            exam_score = float(entry.get('exam_score') or 0)
        except (TypeError, ValueError):
            errors.append(f"Student ID {student_id}: invalid score value")
            continue

        if not (0 <= ca_score <= MAX_CA_SCORE):
            errors.append(f"Student ID {student_id}: CA score must be between 0 and {MAX_CA_SCORE}")
            continue
        if not (0 <= exam_score <= MAX_EXAM_SCORE):
            errors.append(f"Student ID {student_id}: Exam score must be between 0 and {MAX_EXAM_SCORE}")
            continue

        try:
            student = Student.objects.get(id=student_id)

            existing = Grade.objects.filter(
                student=student, course=course,
                session=current_semester.session, semester=current_semester.semester,
            ).first()
            if existing and existing.status in ['submitted', 'hod_approved', 'verified', 'published']:
                errors.append(f"{student.matric_number}: result is locked and cannot be edited")
                continue

            enrollment, _ = Enrollment.objects.get_or_create(
                student=student, course=course,
                session=current_semester.session, semester=current_semester.semester,
                defaults={'status': 'enrolled'},
            )
            total_score = ca_score + exam_score
            Grade.objects.update_or_create(
                student=student, course=course,
                session=current_semester.session, semester=current_semester.semester,
                defaults={
                    'enrollment': enrollment,
                    'ca_score': ca_score,
                    'exam_score': exam_score,
                    'score': total_score,
                    'uploaded_by': lecturer,
                    'status': target_status,
                    'remarks': entry.get('remarks', ''),
                },
            )
            successful.append(student.matric_number)
        except Student.DoesNotExist:
            errors.append(f"Student ID {student_id}: not found")
        except Exception as e:
            errors.append(f"Student ID {student_id}: {e}")

    return successful, errors


# ---------------------------------------------------------------------------
# Attendance (LecturerAttendanceViewSet: attendance_sessions, mark_attendance,
# attendance_report) -- the old frontend's attendance page called
# nonexistent local Next.js API routes (/api/courses, /api/attendance) and
# never actually worked; this ports the real, working backend feature.
# ---------------------------------------------------------------------------

def get_attendance_courses(lecturer):
    """Courses with a current-semester offering, for the course picker."""
    current_semester = get_current_semester()
    if not current_semester:
        return []

    courses = Course.objects.filter(lecturer=lecturer).select_related('department')
    result = []
    for course in courses:
        offering = CourseOffering.objects.filter(
            course=course, semester=current_semester, is_active=True,
        ).first()
        if not offering:
            continue
        last_attendance = Attendance.objects.filter(
            course=course, marked_by=lecturer,
        ).order_by('-date').first()
        result.append({
            'course': course,
            'enrolled_students': CourseRegistration.objects.filter(
                course_offering=offering, status='registered',
            ).count(),
            'last_attendance_date': last_attendance.date if last_attendance else None,
        })
    return result


def get_attendance_roster_for_date(course, mark_date):
    """
    Registered + enrolled students for `course`, each with their existing
    attendance status for `mark_date` (if any) pre-filled, for the mark
    -attendance form.
    """
    current_semester = get_current_semester()
    if not current_semester:
        return []

    registrations = CourseRegistration.objects.filter(
        course_offering__course=course,
        course_offering__semester=current_semester,
        status='registered',
    ).select_related('student__user').order_by('student__matric_number')

    existing = {
        a.student_id: a
        for a in Attendance.objects.filter(course=course, date=mark_date)
    }

    roster = []
    for reg in registrations:
        roster.append({
            'student': reg.student,
            'existing': existing.get(reg.student_id),
        })
    return roster


def mark_attendance(lecturer, course, mark_date, entries):
    """
    entries: list of {student_id, status, remarks}. Mirrors
    LecturerAttendanceViewSet.mark_attendance (future-date guard,
    enrollment check, idempotent per-day update_or_create).
    """
    if mark_date > date_cls.today():
        return [], ['Cannot mark attendance for future dates.']

    marked, errors = [], []
    for entry in entries:
        student_id = entry.get('student_id')
        status_value = entry.get('status')
        if not student_id or not status_value:
            continue
        try:
            student = Student.objects.get(id=student_id)
            if not Enrollment.objects.filter(student=student, course=course, status='enrolled').exists():
                errors.append(f"{student.matric_number}: not enrolled in this course")
                continue
            Attendance.objects.update_or_create(
                student=student, course=course, date=mark_date,
                defaults={
                    'status': status_value,
                    'remarks': entry.get('remarks', ''),
                    'marked_by': lecturer,
                },
            )
            marked.append(student.matric_number)
        except Student.DoesNotExist:
            errors.append(f"Student ID {student_id}: not found")
    return marked, errors


def get_attendance_report(course, start_date, end_date):
    """Mirrors attendance_report exactly, including the 75% threshold."""
    records = Attendance.objects.filter(
        course=course, date__range=[start_date, end_date],
    ).select_related('student__user')

    total_classes = records.values('date').distinct().count()

    by_student = {}
    for r in records:
        by_student.setdefault(r.student_id, {'student': r.student, 'records': []})
        by_student[r.student_id]['records'].append(r)

    report = []
    for data in by_student.values():
        recs = data['records']
        present = sum(1 for r in recs if r.status == 'present')
        pct = round((present / total_classes * 100), 1) if total_classes else 0
        report.append({
            'student': data['student'],
            'present_count': present,
            'absent_count': sum(1 for r in recs if r.status == 'absent'),
            'late_count': sum(1 for r in recs if r.status == 'late'),
            'total_marked': len(recs),
            'percentage': pct,
            'below_threshold': pct < ATTENDANCE_THRESHOLD,
        })
    report.sort(key=lambda x: x['percentage'])
    return report, total_classes
