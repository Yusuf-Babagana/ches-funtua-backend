"""
Lecturer dashboard pages -- Phase 4 of the Next.js -> Django templates
migration. See portal/services_lecturer.py for the ported business logic.
"""
from datetime import date as date_cls, datetime

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import services_lecturer as svc
from .decorators import role_required

NAV = [
    {'label': 'Dashboard', 'url_name': 'portal:dashboard_lecturer'},
    {'label': 'My Courses', 'url_name': 'portal:lecturer_courses'},
    {'label': 'Attendance', 'url_name': 'portal:lecturer_attendance'},
]


def _nav(active_url_name):
    items = [dict(item) for item in NAV]
    for item in items:
        item['is_active'] = item['url_name'] == active_url_name
    return items


def _get_owned_course_or_404(request, course_id):
    course = svc.get_owned_course(request.user.lecturer_profile, course_id)
    if not course:
        raise Http404('Course not found or not assigned to you.')
    return course


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@role_required('lecturer')
def dashboard(request):
    lecturer = request.user.lecturer_profile
    data = svc.get_dashboard_data(lecturer)
    return render(request, 'dashboard/lecturer/dashboard.html', {
        'nav_items': _nav('portal:dashboard_lecturer'),
        'page_title': 'Lecturer Dashboard',
        'lecturer': lecturer,
        **data,
    })


# ---------------------------------------------------------------------------
# Course list
# ---------------------------------------------------------------------------

@role_required('lecturer')
def courses(request):
    lecturer = request.user.lecturer_profile
    course_list = svc.get_courses(lecturer)
    return render(request, 'dashboard/lecturer/courses.html', {
        'nav_items': _nav('portal:lecturer_courses'),
        'page_title': 'My Courses',
        'courses': course_list,
    })


# ---------------------------------------------------------------------------
# Class roster
# ---------------------------------------------------------------------------

@role_required('lecturer')
def course_students(request, course_id):
    lecturer = request.user.lecturer_profile
    course = _get_owned_course_or_404(request, course_id)
    roster, current_semester = svc.get_course_roster(course)
    return render(request, 'dashboard/lecturer/course_students.html', {
        'nav_items': _nav('portal:lecturer_courses'),
        'page_title': 'Enrolled Students',
        'course': course,
        'roster': roster,
        'current_semester': current_semester,
    })


# ---------------------------------------------------------------------------
# Gradebook
# ---------------------------------------------------------------------------

@role_required('lecturer')
def gradebook(request, course_id):
    lecturer = request.user.lecturer_profile
    course = _get_owned_course_or_404(request, course_id)

    if request.method == 'POST':
        submit = request.POST.get('action') == 'submit'
        roster, _ = svc.get_course_roster(course)
        entries = []
        for row in roster:
            sid = row['student'].id
            ca_raw = request.POST.get(f'ca_{sid}', '').strip()
            exam_raw = request.POST.get(f'exam_{sid}', '').strip()
            if ca_raw == '' and exam_raw == '':
                continue  # skip untouched rows
            entries.append({
                'student_id': sid,
                'ca_score': ca_raw or 0,
                'exam_score': exam_raw or 0,
            })

        if not entries:
            messages.info(request, 'No scores to save.')
        else:
            successful, errors = svc.save_grades(lecturer, course, entries, submit=submit)
            if successful:
                verb = 'submitted to HOD' if submit else 'saved as draft'
                messages.success(request, f'{len(successful)} grade(s) {verb}.')
            for err in errors:
                messages.error(request, err)
        return redirect('portal:lecturer_gradebook', course_id=course.id)

    roster, current_semester = svc.get_course_roster(course)
    return render(request, 'dashboard/lecturer/gradebook.html', {
        'nav_items': _nav('portal:lecturer_courses'),
        'page_title': 'Gradebook',
        'course': course,
        'roster': roster,
        'current_semester': current_semester,
        'max_ca': svc.MAX_CA_SCORE,
        'max_exam': svc.MAX_EXAM_SCORE,
    })


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

@role_required('lecturer')
def attendance(request):
    lecturer = request.user.lecturer_profile
    attendance_courses = svc.get_attendance_courses(lecturer)

    course = None
    roster = []
    report = []
    total_classes = 0
    mark_date = date_cls.today()

    course_id = request.GET.get('course_id')
    if course_id:
        course = _get_owned_course_or_404(request, course_id)
        date_str = request.GET.get('date')
        if date_str:
            try:
                mark_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                mark_date = date_cls.today()
        roster = svc.get_attendance_roster_for_date(course, mark_date)

        current_semester = svc.get_current_semester()
        start = current_semester.start_date if current_semester else mark_date
        report, total_classes = svc.get_attendance_report(course, start, date_cls.today())

    return render(request, 'dashboard/lecturer/attendance.html', {
        'nav_items': _nav('portal:lecturer_attendance'),
        'page_title': 'Attendance',
        'attendance_courses': attendance_courses,
        'course': course,
        'roster': roster,
        'mark_date': mark_date,
        'report': report,
        'total_classes': total_classes,
        'today': date_cls.today().isoformat(),
    })


@role_required('lecturer')
@require_POST
def mark_attendance(request, course_id):
    lecturer = request.user.lecturer_profile
    course = _get_owned_course_or_404(request, course_id)

    attendance_url = reverse('portal:lecturer_attendance')
    date_str = request.POST.get('date')
    try:
        mark_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        messages.error(request, 'Invalid date.')
        return redirect(f"{attendance_url}?course_id={course.id}")

    roster = svc.get_attendance_roster_for_date(course, mark_date)
    entries = []
    for row in roster:
        sid = row['student'].id
        status_value = request.POST.get(f'status_{sid}')
        if status_value:
            entries.append({'student_id': sid, 'status': status_value})

    marked, errors = svc.mark_attendance(lecturer, course, mark_date, entries)
    if marked:
        messages.success(request, f'Attendance marked for {len(marked)} student(s).')
    for err in errors:
        messages.error(request, err)

    return redirect(f"{attendance_url}?course_id={course.id}&date={mark_date.isoformat()}")
