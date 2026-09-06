"""
Registrar dashboard pages -- Phase 6 of the Next.js -> Django templates
migration. See portal/services_registrar.py for the ported business
logic and important notes on what was deliberately NOT ported
(a redundant/incomplete duplicate approval surface, a level='400' filter
that can never match real data in this system, and a second copy of the
same publication page the old frontend had).
"""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from users.models import Student

from . import services_registrar as svc
from . import services_student as student_svc
from .decorators import role_required

NAV = [
    {'label': 'Dashboard', 'url_name': 'portal:dashboard_registrar'},
    {'label': 'Admissions', 'url_name': 'portal:registrar_applications'},
    {'label': 'Students', 'url_name': 'portal:registrar_students'},
    {'label': 'Result Publication', 'url_name': 'portal:registrar_publication'},
    {'label': 'Transcripts', 'url_name': 'portal:registrar_transcript'},
]


def _nav(active_url_name):
    items = [dict(item) for item in NAV]
    for item in items:
        item['is_active'] = item['url_name'] == active_url_name
    return items


@role_required('registrar')
def dashboard(request):
    data = svc.get_dashboard_data()
    return render(request, 'dashboard/registrar/dashboard.html', {
        'nav_items': _nav('portal:dashboard_registrar'),
        'page_title': 'Registrar Dashboard',
        **data,
    })


@role_required('registrar')
def applications(request):
    if request.method == 'POST':
        application_id = request.POST.get('application_id')
        matric_number = request.POST.get('matric_number', '').strip()
        if not application_id or not matric_number:
            messages.error(request, 'Application and matric number are required.')
        else:
            student, error = svc.assign_matric_number(application_id, matric_number)
            if error:
                messages.error(request, error)
            else:
                messages.success(request, f'{student.user.get_full_name()} matriculated as {student.matric_number}.')
        return redirect('portal:registrar_applications')

    pending = svc.get_pending_matric_assignments()
    return render(request, 'dashboard/registrar/applications.html', {
        'nav_items': _nav('portal:registrar_applications'),
        'page_title': 'Admissions & Matriculation',
        'pending': pending,
    })


@role_required('registrar')
def students(request):
    student_list = svc.get_students(
        search=request.GET.get('search') or None,
        status=request.GET.get('status') or None,
        level=request.GET.get('level') or None,
    )
    return render(request, 'dashboard/registrar/students.html', {
        'nav_items': _nav('portal:registrar_students'),
        'page_title': 'Student Records',
        'students': student_list,
        'filters': request.GET,
    })


@role_required('registrar')
def publication(request):
    pending = svc.get_pending_publications()
    return render(request, 'dashboard/registrar/publication.html', {
        'nav_items': _nav('portal:registrar_publication'),
        'page_title': 'Result Publication',
        'pending': pending,
    })


@role_required('registrar')
def publication_detail(request, course_id):
    course, grades, has_anomalies, flagged = svc.get_publication_detail(course_id)
    if course is None:
        messages.error(request, 'Course not found.')
        return redirect('portal:registrar_publication')
    return render(request, 'dashboard/registrar/publication_detail.html', {
        'nav_items': _nav('portal:registrar_publication'),
        'page_title': f'Publish: {course.code}',
        'course': course,
        'grades': grades,
        'has_anomalies': has_anomalies,
        'flagged_count': len(flagged),
    })


@role_required('registrar')
@require_POST
def publish_results(request, course_id):
    count, error = svc.publish_course_results(course_id)
    if error:
        messages.error(request, error)
    else:
        messages.success(request, f'Published {count} grade(s) -- now visible to students.')
    return redirect('portal:registrar_publication')


@role_required('registrar')
@require_POST
def reject_results(request, course_id):
    remark = request.POST.get('remark', '').strip()
    if not remark:
        messages.error(request, 'Please provide a reason for returning these results to draft.')
        return redirect('portal:registrar_publication_detail', course_id=course_id)
    count, error = svc.reject_course_results(course_id, remark)
    if error:
        messages.error(request, error)
    else:
        messages.success(request, f'Returned {count} grade(s) to draft.')
    return redirect('portal:registrar_publication')


@role_required('registrar')
def transcript(request):
    search = request.GET.get('search', '').strip()
    results = svc.find_students(search) if search else []

    student = None
    data = None
    student_id = request.GET.get('student_id')
    if student_id:
        student = get_object_or_404(Student.objects.select_related('user', 'department'), id=student_id)
        data = student_svc.get_transcript_data(student)

    return render(request, 'dashboard/registrar/transcript.html', {
        'nav_items': _nav('portal:registrar_transcript'),
        'page_title': 'Generate Transcript',
        'search': search,
        'results': results,
        'student': student,
        'data': data,
    })
