"""
Shared fixtures for the portal app's permanent regression suite (Phase 12
-- Testing). Builds one full 9-role roster plus a minimal academic
structure (2 departments, a current semester, 2 courses/offerings) once
per TestCase subclass via setUpTestData, so individual test files can
focus on the behavior they're actually checking instead of re-deriving
"a working system" from scratch every time.

This suite intentionally does not try to re-test every assertion every
phase's own throwaway smoke script already covered -- it exists to catch
regressions across phase boundaries (cross-role workflows, shared
constants/permissions no single phase owns) that nothing else asserts
permanently. See portal/tests/test_workflows.py,
test_registration_cap.py, test_security.py, and
test_page_render_sweep.py for what's actually covered.
"""
from datetime import timedelta

from django.test import Client, TestCase
from django.utils import timezone

from academics.models import (
    AcademicLevelConfiguration, Course, CourseOffering, Department, Program,
    Semester,
)
from finance.models import FeeStructure
from users.models import Lecturer, StaffProfile, Student, User


class PortalTestCase(TestCase):
    """Base class for every portal regression test -- inherit this, not
    plain TestCase, to get the full fixture roster below for free."""

    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.now().date()

        cls.dept = Department.objects.create(name='Community Health', code='CH')
        cls.dept2 = Department.objects.create(name='Environmental Health', code='EH')

        cls.program = Program.objects.create(
            name='National Diploma', code='ND-T', program_type='nd', duration_semesters=4,
        )

        cls.semester = Semester.objects.create(
            session='2090/2091', semester='first', is_current=True,
            start_date=cls.today - timedelta(days=5), end_date=cls.today + timedelta(days=90),
            registration_deadline=cls.today + timedelta(days=30), is_registration_active=True,
        )
        AcademicLevelConfiguration.objects.get_or_create(
            level='100', defaults={'current_semester': cls.semester, 'is_registration_open': True},
        )

        # --- Staff: one of every role, all in `dept` where relevant ---
        cls.lecturer_user = User.objects.create_user(
            username='t_lecturer', email='t_lecturer@test.com', password='pass12345',
            first_name='Lee', last_name='Turner', role='lecturer',
        )
        cls.lecturer = Lecturer.objects.create(
            user=cls.lecturer_user, staff_id='TLEC-001', department=cls.dept, designation='lecturer_1',
        )

        cls.hod_user = User.objects.create_user(
            username='t_hod', email='t_hod@test.com', password='pass12345',
            first_name='Hoda', last_name='Yusuf', role='hod',
        )
        cls.hod_lecturer = Lecturer.objects.create(
            user=cls.hod_user, staff_id='THOD-001', department=cls.dept, designation='senior_lecturer', is_hod=True,
        )
        cls.dept.hod = cls.hod_lecturer
        cls.dept.save()

        cls.registrar_user = cls._make_staff('registrar', 'REG-001')
        cls.bursar_user = cls._make_staff('bursar', 'BUR-001')
        cls.exam_officer_user = cls._make_staff('exam-officer', 'EO-001')
        cls.desk_officer_user = cls._make_staff('desk-officer', 'DO-001')
        cls.ict_user = cls._make_staff('ict', 'ICT-001')
        cls.super_admin_user = cls._make_staff('super-admin', 'SA-001')

        # --- Student ---
        cls.student_user = User.objects.create_user(
            username='t_student', email='t_student@test.com', password='pass12345',
            first_name='Sam', last_name='Ibrahim', role='student',
        )
        cls.student = Student.objects.create(
            user=cls.student_user, matric_number='T-STU-001', department=cls.dept, level='100',
            program=cls.program, status='active', admission_date=cls.today,
        )

        # --- Academic structure: 2 courses with offerings this semester ---
        # `lecturer` is set both here (Course.lecturer -- what
        # get_owned_course()/the lecturer's "My Courses" list use) and on
        # the CourseOffering below (what registration/roster queries use)
        # -- the two are separate FKs in the real schema and this project's
        # data is expected to keep them in sync, so the fixture does too.
        cls.course1 = Course.objects.create(
            code='CH101', title='Intro to Community Health', credits=4,
            department=cls.dept, semester='first', level='100', lecturer=cls.lecturer,
        )
        cls.course2 = Course.objects.create(
            code='CH102', title='Health Statistics', credits=3,
            department=cls.dept, semester='first', level='100', lecturer=cls.lecturer,
        )
        cls.offering1 = CourseOffering.objects.create(
            course=cls.course1, lecturer=cls.lecturer, semester=cls.semester, capacity=50, is_active=True,
        )
        cls.offering2 = CourseOffering.objects.create(
            course=cls.course2, lecturer=cls.lecturer, semester=cls.semester, capacity=50, is_active=True,
        )

        cls.fee_structure = FeeStructure.objects.create(
            name='Standard Tuition', level='100', department=cls.dept,
            tuition_fee=1000, session=cls.semester.session,
        )

    @classmethod
    def _make_staff(cls, role, staff_id):
        user = User.objects.create_user(
            username=f't_{role.replace("-", "_")}', email=f't_{role.replace("-", "_")}@test.com',
            password='pass12345', first_name=role.title(), last_name='Staff', role=role,
        )
        StaffProfile.objects.create(user=user, staff_id=staff_id, position=role.replace('-', ' ').title())
        return user

    def login(self, user):
        """Fresh logged-in Client for `user` -- each test gets its own
        client so cross-role tests in one method never leak session state."""
        client = Client()
        client.force_login(user)
        return client
