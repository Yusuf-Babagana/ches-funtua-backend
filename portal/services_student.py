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

Registration cap: as of the CHESF Student Portal Digest feature work,
this is a real credit-UNIT ceiling (academics/constants.py), not a
course count -- replaces the old 2-unpaid/15-paid numbers here and in
the underlying DRF views (academics/views_student.py,
views_registration.py) in the same pass, so both layers enforce the
same rule.
"""
from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from academics.constants import MAX_CREDIT_UNITS_PAID, MAX_CREDIT_UNITS_UNPAID
from academics.models import (
    AcademicLevelConfiguration, Course, CourseOffering, CourseRegistration,
    Grade, IndexInformation, PracticalCenter, PracticalCenterSelection, Semester,
)
from finance.models import FeeItem, Invoice


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
    total_credit_units = (registrations | pending_registrations).aggregate(
        total=Sum('course_offering__course__credits')
    )['total'] or 0

    max_units = MAX_CREDIT_UNITS_PAID if has_paid_fees else MAX_CREDIT_UNITS_UNPAID
    can_register_by_limit = total_credit_units < max_units
    can_register = can_register_by_limit and is_reg_open_for_level

    return {
        'has_current_semester': True,
        'current_semester': current_semester,
        'is_registration_active': is_reg_open_for_level,
        'has_paid_fees': has_paid_fees,
        'can_register': can_register,
        'registered_courses': current_reg_count,
        'total_credit_units': total_credit_units,
        'max_credit_units': max_units,
        'remaining_free_units': max(0, max_units - total_credit_units),
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
    Mirrors RegistrationViewSet.register_courses: global current
    semester, instant 'registered' status (self-service path, bypasses the
    lecturer/exam-officer approval chain used elsewhere in the system --
    see college_cms_migration_inventory.md §3.1). Registration ceiling is
    a credit-unit cap (academics/constants.py), not a course count.

    Returns (successful_ids, errors).
    """
    current_semester = Semester.objects.filter(is_current=True).first()
    if not current_semester:
        return [], ['No active semester found.']

    offering_ids = list({int(x) for x in offering_ids})

    existing_credit_units = CourseRegistration.objects.filter(
        student=student,
        course_offering__semester=current_semester,
    ).exclude(status='dropped').aggregate(
        total=Sum('course_offering__course__credits')
    )['total'] or 0

    new_credit_units = CourseOffering.objects.filter(
        id__in=offering_ids
    ).aggregate(total=Sum('course__credits'))['total'] or 0

    has_paid = Invoice.objects.filter(
        student=student, session=current_semester.session, status='paid',
    ).exists()

    max_units = MAX_CREDIT_UNITS_PAID if has_paid else MAX_CREDIT_UNITS_UNPAID

    if existing_credit_units + new_credit_units > max_units:
        return [], [f'Registering these courses would exceed your {max_units}-credit-unit limit for this semester.']

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
# Fee catalog (new for the CHESF Student Portal Digest feature work --
# no DRF equivalent exists yet; this is genuinely new, not a port). Lists
# every active FeeItem priced for the student's current session/semester/
# level, alongside whatever invoice already exists for it so the template
# can show "Pay", "Paid", or "Not yet available" per item.
# ---------------------------------------------------------------------------

def get_fee_catalog(student):
    current_semester, _ = get_student_semester(student)
    if not current_semester:
        return []

    rows = []
    for fee_item in FeeItem.objects.filter(is_active=True).order_by('name'):
        charge = fee_item.current_charge(
            session=current_semester.session,
            semester=current_semester.semester,
            level=student.level,
        )
        invoice = Invoice.objects.filter(
            student=student, fee_item=fee_item, session=current_semester.session,
        ).exclude(status='cancelled').order_by('-created_at').first()

        rows.append({
            'fee_item': fee_item,
            'charge': charge,
            'invoice': invoice,
            'is_paid': bool(invoice and invoice.status == 'paid'),
            'is_priced': bool(charge and charge.amount > 0),
        })
    return rows


# ---------------------------------------------------------------------------
# Carry-over courses (new for the CHESF Student Portal Digest -- no
# separate model needed. A "carry-over" is simply a course whose most
# recent *published* Grade is an F, with no later published attempt that
# passed it (confirmed by exploration: no carry-over/resit concept exists
# anywhere in the codebase today). Retaking it is an ordinary course
# registration -- same credit-unit cap, same CourseOffering machinery,
# via register_courses() above -- plus a per-registration carry-over exam
# fee invoice (Invoice.course_registration, added in Checkpoint 1).
# ---------------------------------------------------------------------------

CARRYOVER_EXAM_FEE_CODES = {'first': 'exam_first_semester', 'second': 'exam_second_semester'}
_SEM_ORDER = {'first': 1, 'second': 2}


def get_failed_courses(student):
    """
    For each course the student has a published Grade for, look only at
    the most recent attempt (by session, then semester) -- if that's an
    F, the course is still outstanding. An earlier F followed by a later
    pass is *not* outstanding.
    """
    grades = Grade.objects.filter(
        student=student, status='published',
    ).select_related('course').order_by('course_id', 'session', 'semester')

    latest_by_course = {}
    for g in grades:
        sort_key = (g.session, _SEM_ORDER.get(g.semester.lower(), 3))
        existing = latest_by_course.get(g.course_id)
        if not existing or sort_key >= existing[0]:
            latest_by_course[g.course_id] = (sort_key, g)

    return [g for (_, g) in latest_by_course.values() if g.grade_letter == 'F']


def get_carryover_status(student):
    current_semester, _ = get_student_semester(student)
    failed_grades = get_failed_courses(student)

    rows = []
    for grade in failed_grades:
        course = grade.course
        registration = None
        if current_semester:
            registration = CourseRegistration.objects.filter(
                student=student, course_offering__course=course,
                course_offering__semester=current_semester,
            ).exclude(status='dropped').first()

        invoice = None
        if registration:
            invoice = Invoice.objects.filter(
                student=student, course_registration=registration,
            ).exclude(status='cancelled').order_by('-created_at').first()

        rows.append({
            'course': course,
            'failed_grade': grade,
            'registration': registration,
            'invoice': invoice,
            'is_registered': bool(registration),
            'is_paid': bool(invoice and invoice.status == 'paid'),
        })
    return {'current_semester': current_semester, 'rows': rows}


def register_carryover_course(student, course_id):
    """
    Registers a failed-and-not-yet-passed course for the current global
    semester (same resolution register_courses() uses), then lazily
    creates its carry-over exam-fee invoice if the Bursar has priced one
    for this session/semester/level. Server-side re-validates the course
    is actually an outstanding carry-over rather than trusting the
    submitted course_id.

    Deliberately re-callable on an already-registered course: the Bursar
    may price the carry-over exam fee *after* the student has already
    registered, and this is also the "check for exam fee" action the
    carry-over page offers for that already-registered-but-unpriced
    state -- it must not bail out early just because a registration
    already exists. Returns (ok, message).
    """
    current_semester = Semester.objects.filter(is_current=True).first()
    if not current_semester:
        return False, 'No active semester found.'

    try:
        course = Course.objects.get(id=course_id)
    except Course.DoesNotExist:
        return False, 'Course not found.'

    failed_course_ids = {g.course_id for g in get_failed_courses(student)}
    if course.id not in failed_course_ids:
        return False, 'That course is not an outstanding carry-over for you.'

    offering, _ = CourseOffering.objects.get_or_create(
        course=course, semester=current_semester,
        defaults={'capacity': 200, 'is_active': True},
    )

    registration = CourseRegistration.objects.filter(
        student=student, course_offering=offering,
    ).exclude(status='dropped').first()

    if registration:
        message = f'{course.code} is already registered.'
    else:
        successful, errors = register_courses(student, [offering.id])
        if not successful:
            return False, errors[0] if errors else 'Registration failed.'
        registration = CourseRegistration.objects.filter(id__in=successful).first()
        message = f'{course.code} registered as a carry-over course.'

    fee_code = CARRYOVER_EXAM_FEE_CODES.get(current_semester.semester)
    fee_item = FeeItem.objects.filter(code=fee_code, is_active=True).first() if fee_code else None
    if fee_item and registration:
        charge = fee_item.current_charge(
            session=current_semester.session, semester=current_semester.semester, level=student.level,
        )
        if charge and charge.amount > 0:
            had_invoice = Invoice.objects.filter(
                student=student, course_registration=registration,
            ).exclude(status='cancelled').exists()
            from finance.services import FinanceService
            FinanceService.get_or_create_carryover_invoice(student, registration, fee_item, charge.amount)
            if not had_invoice:
                message += ' Exam fee invoice generated.'

    return True, message


# ---------------------------------------------------------------------------
# Practical center selection + Index information (new for the CHESF
# Student Portal Digest -- both models are provisional pending the real
# requirements attachment, see academics/models.py. Both are gated on
# having actually PAID the corresponding FeeItem for the current session
# ('practical' / 'index'), server-side -- not just hidden in the UI --
# since these are the two FeeItems flagged requires_selection=True and
# the payment_verify redirect (portal/views_student.py) sends students
# here right after paying, but a student could still navigate here
# directly without having paid.
# ---------------------------------------------------------------------------

def _has_paid_fee_item(student, code, session):
    if not session:
        return False
    fee_item = FeeItem.objects.filter(code=code).first()
    if not fee_item:
        return False
    return Invoice.objects.filter(
        student=student, fee_item=fee_item, session=session, status='paid',
    ).exists()


def get_practical_center_status(student):
    current_semester, _ = get_student_semester(student)
    session = current_semester.session if current_semester else None
    has_paid = _has_paid_fee_item(student, 'practical', session)

    selection = None
    if session:
        selection = PracticalCenterSelection.objects.filter(
            student=student, session=session,
        ).select_related('center').first()

    return {
        'has_paid': has_paid,
        'session': session,
        'selection': selection,
        'centers': PracticalCenter.objects.filter(is_active=True).order_by('name') if has_paid else PracticalCenter.objects.none(),
    }


def select_practical_center(student, center_id):
    current_semester, _ = get_student_semester(student)
    if not current_semester:
        return False, 'No active semester found.'
    session = current_semester.session

    if not _has_paid_fee_item(student, 'practical', session):
        return False, 'You must pay the Practical Fee before selecting a center.'

    try:
        center = PracticalCenter.objects.get(id=center_id, is_active=True)
    except PracticalCenter.DoesNotExist:
        return False, 'Practical center not found.'

    PracticalCenterSelection.objects.update_or_create(
        student=student, session=session, defaults={'center': center},
    )
    return True, f'Practical center set to {center.name}.'


def get_index_info_status(student):
    current_semester, _ = get_student_semester(student)
    session = current_semester.session if current_semester else None
    return {
        'has_paid': _has_paid_fee_item(student, 'index', session),
        'info': IndexInformation.objects.filter(student=student).first(),
    }


def save_index_info(student, data, photo_file=None):
    current_semester, _ = get_student_semester(student)
    if not current_semester:
        return None, 'No active semester found.'

    if not _has_paid_fee_item(student, 'index', current_semester.session):
        return None, 'You must pay the Index Fee before submitting this form.'

    info, _ = IndexInformation.objects.update_or_create(
        student=student,
        defaults={
            'state_of_origin': (data.get('state_of_origin') or '').strip(),
            'lga': (data.get('lga') or '').strip(),
            'next_of_kin_name': (data.get('next_of_kin_name') or '').strip(),
            'next_of_kin_phone': (data.get('next_of_kin_phone') or '').strip(),
            'additional_notes': (data.get('additional_notes') or '').strip(),
        },
    )
    if photo_file:
        info.passport_photo = photo_file
        info.save(update_fields=['passport_photo', 'updated_at'])
    return info, None


# ---------------------------------------------------------------------------
# Program / duration / semester countdown (new for the CHESF Student
# Portal Digest -- Student.program was added in Checkpoint 1; nothing
# reads it yet). "Semesters completed" is defined as the number of
# distinct (session, semester) combinations the student has a
# non-dropped registration in -- the simplest defensible reading of
# "semester countdown" given the spec didn't define graduation/
# completion criteria more precisely; it counts semesters the student
# has been active in, not semesters with published results.
# ---------------------------------------------------------------------------

def get_program_status(student):
    if not student.program:
        return None

    completed_semesters = CourseRegistration.objects.filter(
        student=student,
    ).exclude(status='dropped').values(
        'course_offering__semester__session', 'course_offering__semester__semester',
    ).distinct().count()

    duration = student.program.duration_semesters
    return {
        'program': student.program,
        'duration_semesters': duration,
        'completed_semesters': completed_semesters,
        'remaining_semesters': max(0, duration - completed_semesters),
    }


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
