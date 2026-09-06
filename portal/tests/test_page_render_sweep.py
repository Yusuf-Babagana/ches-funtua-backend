"""
Broad, mechanical page-render sweep across all 9 roles. Individual
phases verified their own pages in isolation when built; nothing has
ever checked that they ALL still render together, after every later
phase's changes to shared code (context processors, base.html, shared
constants/services). This is what actually catches that class of
regression -- each entry just has to return 200 without blowing up.

Deliberately excludes: POST-only actions (already covered by
test_workflows.py/test_security.py or their own phase's original
coverage), and detail pages keyed to a specific object's workflow state
(e.g. a submitted grade) that would need bespoke setup per entry --
those are covered by test_workflows.py's end-to-end chain instead.
"""
from django.urls import reverse

from .base import PortalTestCase

# (url_name, fixture attribute name for the acting user, kwargs)
PAGES = [
    # Public
    ('portal:landing', None, {}),
    ('portal:login', None, {}),

    # Student
    ('portal:dashboard_student', 'student_user', {}),
    ('portal:student_courses', 'student_user', {}),
    ('portal:student_registration', 'student_user', {}),
    ('portal:student_results', 'student_user', {}),
    ('portal:student_transcript', 'student_user', {}),
    ('portal:student_exam_card', 'student_user', {}),
    ('portal:student_fees', 'student_user', {}),
    ('portal:student_fee_catalog', 'student_user', {}),
    ('portal:student_practical_center', 'student_user', {}),
    ('portal:student_index_info', 'student_user', {}),
    ('portal:student_carryover', 'student_user', {}),
    ('portal:student_support', 'student_user', {}),
    ('portal:student_payments', 'student_user', {}),
    ('portal:student_print_schedule', 'student_user', {}),
    ('portal:student_settings', 'student_user', {}),

    # Lecturer
    ('portal:dashboard_lecturer', 'lecturer_user', {}),
    ('portal:lecturer_courses', 'lecturer_user', {}),
    ('portal:lecturer_attendance', 'lecturer_user', {}),

    # HOD
    ('portal:dashboard_hod', 'hod_user', {}),
    ('portal:hod_students', 'hod_user', {}),
    ('portal:hod_lecturers', 'hod_user', {}),
    ('portal:hod_courses', 'hod_user', {}),
    ('portal:hod_approvals', 'hod_user', {}),

    # Registrar
    ('portal:dashboard_registrar', 'registrar_user', {}),
    ('portal:registrar_applications', 'registrar_user', {}),
    ('portal:registrar_students', 'registrar_user', {}),
    ('portal:registrar_publication', 'registrar_user', {}),
    ('portal:registrar_transcript', 'registrar_user', {}),

    # Bursar
    ('portal:dashboard_bursar', 'bursar_user', {}),
    ('portal:bursar_invoices', 'bursar_user', {}),
    ('portal:bursar_fee_items', 'bursar_user', {}),
    ('portal:bursar_verify_payments', 'bursar_user', {}),
    ('portal:bursar_receipts', 'bursar_user', {}),

    # Exam Officer
    ('portal:dashboard_exam_officer', 'exam_officer_user', {}),
    ('portal:eo_registrations', 'exam_officer_user', {}),
    ('portal:eo_results', 'exam_officer_user', {}),

    # Desk Officer
    ('portal:dashboard_desk_officer', 'desk_officer_user', {}),
    ('portal:do_students', 'desk_officer_user', {}),
    ('portal:do_documents', 'desk_officer_user', {}),
    ('portal:do_queries', 'desk_officer_user', {}),
    ('portal:do_payments', 'desk_officer_user', {}),
    ('portal:do_registration', 'desk_officer_user', {}),
    ('portal:do_support', 'desk_officer_user', {}),

    # ICT
    ('portal:dashboard_ict', 'ict_user', {}),
    ('portal:ict_register_student', 'ict_user', {}),
    ('portal:ict_staff_accounts', 'ict_user', {}),
    ('portal:ict_results_upload', 'ict_user', {}),
    ('portal:ict_system_config', 'ict_user', {}),
    ('portal:ict_user_management', 'ict_user', {}),

    # Super Admin
    ('portal:dashboard_super_admin', 'super_admin_user', {}),
    ('portal:sa_courses', 'super_admin_user', {}),
    ('portal:sa_semesters', 'super_admin_user', {}),
    ('portal:sa_level_config', 'super_admin_user', {}),
    ('portal:sa_system_tools', 'super_admin_user', {}),
]

# Pages keyed to a specific course -- resolved against course1/course2 at
# test time since reverse() needs the pk up front.
COURSE_KEYED_PAGES = [
    ('portal:lecturer_gradebook', 'lecturer_user', 'course1'),
    ('portal:lecturer_course_students', 'lecturer_user', 'course1'),
]


class PageRenderSweepTest(PortalTestCase):
    def test_every_page_renders_200_for_its_role(self):
        failures = []
        for url_name, user_attr, kwargs in PAGES:
            client = self.login(getattr(self, user_attr)) if user_attr else self.client
            try:
                resp = client.get(reverse(url_name, kwargs=kwargs))
            except Exception as e:  # pragma: no cover -- surfaced via failures list below
                failures.append(f'{url_name}: raised {e!r}')
                continue
            if resp.status_code != 200:
                failures.append(f'{url_name}: expected 200, got {resp.status_code}')
        self.assertEqual(failures, [], '\n' + '\n'.join(failures))

    def test_course_keyed_pages_render_200(self):
        failures = []
        for url_name, user_attr, course_attr in COURSE_KEYED_PAGES:
            client = self.login(getattr(self, user_attr))
            course_id = getattr(self, course_attr).id
            try:
                resp = client.get(reverse(url_name, kwargs={'course_id': course_id}))
            except Exception as e:  # pragma: no cover
                failures.append(f'{url_name}: raised {e!r}')
                continue
            if resp.status_code != 200:
                failures.append(f'{url_name}: expected 200, got {resp.status_code}')
        self.assertEqual(failures, [], '\n' + '\n'.join(failures))
