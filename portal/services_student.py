"""
Student-facing business logic for the Django-template frontend.

This is a straight port of the logic already implemented in the DRF layer
(academics/views_student.py, academics/views_registration.py,
academics/views_transcript.py) -- not a rewrite. Each function below cites
the DRF action it mirrors. Ported here as plain functions (rather than
called over HTTP) so the template views can use them directly, per the
migration brief's "reuse existing business logic" principle.

Known, deliberately preserved inconsistency: the registration *status*
display (used on the dashboard/registration page) is level-aware via
AcademicLevelConfiguration, matching StudentDashboardViewSet's behavior;
the actual register_courses()/drop_course() actions use the global
`Semester.objects.filter(is_current=True)` lookup, matching
RegistrationViewSet's behavior. This mirrors exactly what the live system
does today (see college_cms_migration_inventory.md §6.1) -- not something
introduced by this migration.
"""
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from academics.models import (
    AcademicLevelConfiguration, Course, CourseOffering, CourseRegistration,
    Grade, Semester,
)
from finance.models import Invoice


# ---------------------------------------------------------------------------
# Semester resolution (academics/views_student.py: _get_student_semester)
# ---------------------------------------------------------------------------

def get_student_semester(student):
    """Returns (semester_or_None, is_registration_open_for_level_bool)."""
    config = (
        AcademicLevelConfiguration.objects
        .filter(level=student.level)
        .select_related('current_semester')
        .first()
    )
    if config and config.current_semester:
        return config.current_semester, config.is_registration_open

    global_sem = Semester.objects.filter(is_current=True).first()
    if not global_sem:
        global_sem = Semester.objects.last()

    is_active = global_sem.is_registration_active if global_sem else False
    return global_sem, is_active


# ---------------------------------------------------------------------------
# Registration status (academics/views_student.py: registration_status)
# ---------------------------------------------------------------------------

def get_registration_status(student):
    """
    Mirrors StudentDashboardViewSet.registration_status exactly, including
    the 2-course-unpaid / 15-course-paid exception.
    """
    current_semester, is_reg_open_for_level = get_student_semester(student)

    if not current_semester:
        return {
            'has_current_semester': False,
            'message': 'No current semester set',
        }

    registrations = CourseRegistration.objects.filter(
        student=student,
        course_offering__semester=current_semester,
        status='registered',
    )
    pending_registrations = CourseRegistration.objects.filter(
        student=student,
        course_offering__semester=current_semester,
        status__in=['pending', 'approved_lecturer'],
    )

    has_paid_fees = False
    invoice = Invoice.objects.filter(
        student=student,
        session=current_semester.session,
        semester=current_semester.semester,
    ).first()
    if invoice and invoice.status == 'paid':
        has_paid_fees = True

    current_reg_count = registrations.count() + pending_registrations.count()
    can_register_by_limit = (current_reg_count < 15) if has_paid_fees else (current_reg_count < 2)
    can_register = can_register_by_limit and is_reg_open_for_level

    return {
        'has_current_semester': True,
        'current_semester': current_semester,
        'is_registration_active': is_reg_open_for_level,
        'has_paid_fees': has_paid_fees,
        'can_register': can_register,
        'registered_courses': current_reg_count,
        'max_courses': 15 if has_paid_fees else 2,
        'remaining_free_courses': max(0, 2 - current_reg_count) if not has_paid_fees else None,
        'invoice': invoice,
    }


# ---------------------------------------------------------------------------
# Current schedule (academics/views_student.py: current_schedule)
# ---------------------------------------------------------------------------

def get_current_schedule(student):
    current_semester, _ = get_student_semester(student)
    if not current_semester:
        return []

    registrations = CourseRegistration.objects.filter(
        student=student,
        course_offering__semester=current_semester,
        status__in=['registered', 'approved_lecturer', 'approved_exam_officer'],
    ).select_related(
        'course_offering__course',
        'course_offering__course__department',
        'course_offering__lecturer__user',
    )

    grades_map = {}
    for g in Grade.objects.filter(student=student, session=current_semester.session).select_related('course'):
        grades_map[(g.course_id, g.session)] = g

    results = []
    for reg in registrations:
        grade = grades_map.get((reg.course_offering.course_id, current_semester.session))
        grade_data = None
        if grade and grade.status == 'published':
            grade_data = grade
        results.append({
            'registration': reg,
            'course': reg.course_offering.course,
            'lecturer_name': (
                reg.course_offering.lecturer.user.get_full_name()
                if reg.course_offering.lecturer else 'TBA'
            ),
            'grade': grade_data,
        })
    return results


# ---------------------------------------------------------------------------
# Available offerings for the dashboard registration widget
# (academics/views_student.py: available_courses)
# ---------------------------------------------------------------------------

def get_available_offerings(student):
    current_semester, _ = get_student_semester(student)
    if not current_semester:
        return []

    current_registrations = CourseRegistration.objects.filter(
        student=student,
        course_offering__semester=current_semester,
    ).exclude(status='dropped').values_list('course_offering_id', flat=True)

    # Ensure every active Course has an offering for the current semester
    # (side effect ported verbatim from the DRF action).
    all_course_ids = set(Course.objects.values_list('id', flat=True))
    existing_offering_course_ids = set(
        CourseOffering.objects.filter(semester=current_semester).values_list('course_id', flat=True)
    )
    missing_course_ids = all_course_ids - existing_offering_course_ids
    if missing_course_ids:
        CourseOffering.objects.bulk_create([
            CourseOffering(course_id=cid, semester=current_semester, capacity=200, is_active=True)
            for cid in missing_course_ids
        ])

    available_offerings = CourseOffering.objects.filter(
        is_active=True,
    ).exclude(
        id__in=current_registrations,
    ).select_related(
        'course', 'course__department', 'lecturer__user',
    ).order_by('-semester__start_date', 'course__code')

    result = []
    for o in available_offerings:
        o.available_slots = max(0, o.capacity - o.enrolled_count)  # template-friendly, avoids arithmetic in Django templates
        if o.available_slots > 0:
            result.append(o)
    return result


# ---------------------------------------------------------------------------
# Registration actions (academics/views_registration.py: RegistrationViewSet)
# ---------------------------------------------------------------------------

@transaction.atomic
def register_courses(student, offering_ids):
    """
    Mirrors RegistrationViewSet.register_courses exactly: global current
    semester, instant 'registered' status (self-service path, bypasses the
    lecturer/exam-officer approval chain used elsewhere in the system --
    see college_cms_migration_inventory.md §3.1), 2-course-unpaid exception.

    Returns (successful_ids, errors).
    """
    current_semester = Semester.objects.filter(is_current=True).first()
    if not current_semester:
        return [], ['No active semester found.']

    existing_reg_count = CourseRegistration.objects.filter(
        student=student,
        course_offering__semester=current_semester,
    ).exclude(status='dropped').count()

    has_paid = Invoice.objects.filter(
        student=student, session=current_semester.session, status='paid',
    ).exists()

    if not has_paid and (existing_reg_count + len(offering_ids) > 2):
        return [], ['Tuition fees must be paid before registering more than 2 courses.']

    offering_ids = list({int(x) for x in offering_ids})
    successful, errors = [], []

    for off_id in offering_ids:
        try:
            offering = CourseOffering.objects.get(id=off_id)

            existing = CourseRegistration.objects.filter(student=student, course_offering=offering).first()
            if existing:
                if existing.status == 'dropped':
                    existing.status = 'registered'
                    existing.save()
                    successful.append(existing.id)
                else:
                    errors.append(f"{offering.course.code}: Already registered")
                continue

            reg = CourseRegistration(
                student=student,
                course_offering=offering,
                status='registered',
                is_payment_verified=True,
                approved_date=timezone.now(),
            )
            reg.save()

            offering.enrolled_count = F('enrolled_count') + 1
            offering.save()

            successful.append(reg.id)

        except CourseOffering.DoesNotExist:
            errors.append(f"ID {off_id}: Course not found")
        except Exception as e:
            errors.append(f"Course ID {off_id}: {str(e)}")
            continue

    return successful, errors


def drop_course(student, registration_id):
    """Mirrors RegistrationViewSet.drop_course exactly (hard delete)."""
    try:
        reg = CourseRegistration.objects.get(id=registration_id, student=student)
    except CourseRegistration.DoesNotExist:
        return False, 'Registration not found.'

    offering = reg.course_offering
    if offering.enrolled_count > 0:
        offering.enrolled_count = F('enrolled_count') - 1
        offering.save()
    reg.delete()
    return True, None


# ---------------------------------------------------------------------------
# Academic history (academics/views_student.py: academic_history)
# ---------------------------------------------------------------------------

def get_academic_history(student):
    grades = Grade.objects.filter(
        student=student, status='published',
    ).select_related('course').order_by('-session', '-semester')

    history_map = {}
    for grade in grades:
        key = (grade.session, grade.semester)
        if key not in history_map:
            history_map[key] = {
                'session': grade.session,
                'semester': grade.semester,
                'courses': [],
                'total_units': 0,
                'total_points': 0.0,
            }
        history_map[key]['courses'].append({
            'course_code': grade.course.code,
            'course_title': grade.course.title,
            'credits': grade.course.credits,
            'score': float(grade.score),
            'grade': grade.grade_letter,
            'points': float(grade.grade_points),
        })
        history_map[key]['total_units'] += grade.course.credits
        history_map[key]['total_points'] += float(grade.grade_points) * grade.course.credits

    history_list = []
    cumulative_points = 0.0
    cumulative_units = 0
    for data in history_map.values():
        gpa = data['total_points'] / data['total_units'] if data['total_units'] > 0 else 0.0
        cumulative_points += data['total_points']
        cumulative_units += data['total_units']
        history_list.append({
            'session': data['session'],
            'semester': data['semester'].capitalize(),
            'gpa': round(gpa, 2),
            'total_units': data['total_units'],
            'courses': data['courses'],
        })

    cgpa = cumulative_points / cumulative_units if cumulative_units > 0 else 0.0
    return {
        'current_cgpa': round(cgpa, 2),
        'history': history_list,
    }


# ---------------------------------------------------------------------------
# Exam card (academics/views_student.py: exam_card)
# ---------------------------------------------------------------------------

def get_exam_card_data(student):
    """Returns (data_dict_or_None, error_message_or_None)."""
    current_semester, _ = get_student_semester(student)
    if not current_semester:
        return None, 'No active semester for exam card.'

    invoice = Invoice.objects.filter(
        student=student, session=current_semester.session, semester=current_semester.semester,
    ).first()
    if not invoice or invoice.status != 'paid':
        return None, 'Outstanding fees. Cannot generate Exam Card.'

    registrations = CourseRegistration.objects.filter(
        student=student,
        course_offering__semester=current_semester,
        status__in=['registered', 'approved_exam_officer'],
    ).select_related('course_offering__course')

    if not registrations.exists():
        return None, 'No registered courses found for this semester.'

    courses = [{
        'code': reg.course_offering.course.code,
        'title': reg.course_offering.course.title,
        'unit': reg.course_offering.course.credits,
    } for reg in registrations]

    return {
        'semester': current_semester,
        'courses': courses,
        'total_units': sum(c['unit'] for c in courses),
        'generated_at': timezone.now(),
    }, None


# ---------------------------------------------------------------------------
# Transcript (academics/views_transcript.py: TranscriptViewSet)
# ---------------------------------------------------------------------------

DEGREE_CLASS_THRESHOLDS = [
    (4.50, 'First Class'),
    (3.50, 'Second Class Upper'),
    (2.40, 'Second Class Lower'),
    (1.50, 'Third Class'),
]


def _degree_class(cgpa):
    for threshold, label in DEGREE_CLASS_THRESHOLDS:
        if cgpa >= threshold:
            return label
    return 'Pass'


def get_transcript_data(student):
    """
    Mirrors TranscriptViewSet._generate_transcript_data exactly (same
    grouping/ordering/GPA-then-CGPA computation).
    """
    grades = Grade.objects.filter(
        student=student, status='published',
    ).select_related('course').order_by('session', 'semester', 'course__code')

    if not grades.exists():
        return {
            'transcript': [],
            'summary': {'cgpa': 0.0, 'total_credits_completed': 0, 'degree_class': 'N/A'},
        }

    sem_order = {'first': 1, 'second': 2}
    transcript_map = {}
    for grade in grades:
        key = (grade.session, grade.semester)
        if key not in transcript_map:
            transcript_map[key] = {
                'session': grade.session,
                'semester': grade.semester,
                '_sort_order': sem_order.get(grade.semester.lower(), 3),
                'courses': [],
                '_total_points': 0.0,
                '_total_units': 0,
            }
        transcript_map[key]['courses'].append({
            'code': grade.course.code,
            'title': grade.course.title,
            'unit': grade.course.credits,
            'score': float(grade.score),
            'grade': grade.grade_letter,
            'points': float(grade.grade_points),
        })
        points = float(grade.grade_points) * grade.course.credits
        transcript_map[key]['_total_points'] += points
        transcript_map[key]['_total_units'] += grade.course.credits

    transcript_list = []
    cumulative_points = 0.0
    cumulative_units = 0
    sorted_keys = sorted(transcript_map.keys(), key=lambda k: (k[0], transcript_map[k]['_sort_order']))

    for key in sorted_keys:
        data = transcript_map[key]
        sem_units = data['_total_units']
        sem_points = data['_total_points']
        sem_gpa = sem_points / sem_units if sem_units > 0 else 0.0
        cumulative_points += sem_points
        cumulative_units += sem_units
        transcript_list.append({
            'session': data['session'],
            'semester': data['semester'].capitalize(),
            'courses': data['courses'],
            'semester_stats': {
                'gpa': round(sem_gpa, 2),
                'total_units': sem_units,
                'total_points': round(sem_points, 2),
            },
        })

    cgpa = cumulative_points / cumulative_units if cumulative_units > 0 else 0.0
    return {
        'transcript': transcript_list,
        'summary': {
            'cgpa': round(cgpa, 2),
            'total_credits_completed': cumulative_units,
            'total_points_earned': round(cumulative_points, 2),
            'degree_class': _degree_class(cgpa),
        },
    }
