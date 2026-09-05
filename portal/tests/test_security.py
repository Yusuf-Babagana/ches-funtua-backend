"""
Permanent regression coverage for cross-role permission boundaries and
the specific security fixes made during Phases 10-11 (ICT and Super
Admin). These are exactly the kind of thing a phase-by-phase migration
can silently regress on later without anyone noticing -- worth locking
down permanently rather than trusting the one-time smoke scripts that
originally caught them.
"""
from django.test import Client
from django.urls import reverse
from rest_framework.test import APIClient

from users.models import StaffProfile, User

from .base import PortalTestCase


class DashboardAccessBoundaryTest(PortalTestCase):
    """Every dashboard requires login; no role can reach another role's
    dashboard (portal/decorators.py:role_required)."""

    def test_anonymous_user_is_redirected_to_login(self):
        client = Client()
        resp = client.get(reverse('portal:dashboard_student'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.headers['Location'])

    def test_student_cannot_reach_staff_dashboards(self):
        client = self.login(self.student_user)
        for url_name in [
            'portal:dashboard_hod', 'portal:dashboard_bursar', 'portal:dashboard_ict',
            'portal:dashboard_super_admin', 'portal:dashboard_desk_officer',
        ]:
            with self.subTest(url_name=url_name):
                resp = client.get(reverse(url_name))
                self.assertEqual(resp.status_code, 403)

    def test_ict_cannot_reach_bursar_dashboard(self):
        client = self.login(self.ict_user)
        resp = client.get(reverse('portal:dashboard_bursar'))
        self.assertEqual(resp.status_code, 403)


class ResultUploadPermissionTest(PortalTestCase):
    """academics/views_ict.py:ResultUploadView had NO permission class at
    all before Phase 10 -- any authenticated user, including a student,
    could overwrite grades via this endpoint."""

    def test_student_cannot_call_the_bulk_result_upload_endpoint(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        api = APIClient()
        api.force_authenticate(user=self.student_user)
        csv_file = SimpleUploadedFile('r.csv', b'Name,CH101\nSAM IBRAHIM,70\n', content_type='text/csv')
        resp = api.post('/api/academics/results/upload/', {'session': self.semester.session, 'file': csv_file})
        self.assertEqual(resp.status_code, 403)

    def test_ict_can_call_the_bulk_result_upload_endpoint(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from academics.models import Course as CourseModel
        # The importer matches course columns against a 3-letter+3-digit
        # code pattern (e.g. "CHE101") -- self.course1's code ("CH101")
        # doesn't fit that shape, so a dedicated course is used here.
        upload_course = CourseModel.objects.create(
            code='CHE101', title='Upload Test Course', credits=3,
            department=self.dept, semester='first', level='100',
        )
        api = APIClient()
        api.force_authenticate(user=self.ict_user)
        csv_file = SimpleUploadedFile('r.csv', b'Name,CHE101\nSAM IBRAHIM,70\n', content_type='text/csv')
        resp = api.post('/api/academics/results/upload/', {'session': self.semester.session, 'file': csv_file})
        self.assertEqual(resp.status_code, 200)
        from academics.models import Grade
        grade = Grade.objects.get(student=self.student, course=upload_course)
        self.assertEqual(grade.status, 'draft', "bulk-imported grades must land as draft, not force-published")


class SuperAdminProtectionTest(PortalTestCase):
    """An ICT officer must never be able to touch a Super Admin account
    through UserManagementViewSet -- reset_password/toggle_active_status/
    bulk_actions/destroy were all fixed in Phase 10-11."""

    def _api_as(self, user):
        api = APIClient()
        api.force_authenticate(user=user)
        return api

    def test_ict_cannot_reset_a_super_admins_password(self):
        api = self._api_as(self.ict_user)
        resp = api.post(
            f'/api/auth/ict/user-management/{self.super_admin_user.id}/reset_password/',
            {'new_password': 'Hacked12345!', 'confirm_password': 'Hacked12345!'},
        )
        self.assertEqual(resp.status_code, 403)
        self.super_admin_user.refresh_from_db()
        self.assertFalse(self.super_admin_user.check_password('Hacked12345!'))

    def test_ict_cannot_toggle_a_super_admins_active_status(self):
        api = self._api_as(self.ict_user)
        resp = api.post(f'/api/auth/ict/user-management/{self.super_admin_user.id}/toggle_active_status/')
        self.assertEqual(resp.status_code, 403)
        self.super_admin_user.refresh_from_db()
        self.assertTrue(self.super_admin_user.is_active)

    def test_ict_cannot_delete_a_super_admin(self):
        api = self._api_as(self.ict_user)
        resp = api.delete(f'/api/auth/ict/user-management/{self.super_admin_user.id}/')
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(User.objects.filter(id=self.super_admin_user.id).exists())

    def test_ict_cannot_bulk_touch_a_super_admin(self):
        api = self._api_as(self.ict_user)
        resp = api.post('/api/auth/ict/user-management/bulk_actions/', {
            'user_ids': [self.super_admin_user.id], 'action': 'deactivate',
        })
        self.super_admin_user.refresh_from_db()
        self.assertTrue(self.super_admin_user.is_active, "super-admin must be excluded from an ICT bulk action")

    def test_a_super_admin_can_manage_another_super_admin(self):
        other_sa = User.objects.create_user(
            username='t_sa2', email='t_sa2@test.com', password='pass12345',
            first_name='Second', last_name='Admin', role='super-admin',
        )
        api = self._api_as(self.super_admin_user)
        resp = api.post(f'/api/auth/ict/user-management/{other_sa.id}/toggle_active_status/')
        self.assertEqual(resp.status_code, 200)


class LastActiveSuperAdminGuardTest(PortalTestCase):
    """UserViewSet must never let the system end up with zero active
    Super Admin accounts (Phase 11)."""

    def test_deactivating_the_only_other_active_admin_is_blocked_for_an_already_deactivated_session(self):
        # Simulate a still-valid session (force_authenticate bypasses the
        # is_active check the same way an unexpired JWT would) whose own
        # account was deactivated moments ago by someone else.
        self.super_admin_user.is_active = False
        self.super_admin_user.save()

        other_sa = User.objects.create_user(
            username='t_sa3', email='t_sa3@test.com', password='pass12345',
            first_name='Third', last_name='Admin', role='super-admin',
        )
        api = APIClient()
        api.force_authenticate(user=self.super_admin_user)
        resp = api.post(f'/api/auth/users/{other_sa.id}/deactivate/')
        self.assertEqual(resp.status_code, 400)
        other_sa.refresh_from_db()
        self.assertTrue(other_sa.is_active, "the last active super-admin must not be deactivated")

    def test_ordinary_deactivation_with_admins_to_spare_still_works(self):
        other_sa = User.objects.create_user(
            username='t_sa4', email='t_sa4@test.com', password='pass12345',
            first_name='Fourth', last_name='Admin', role='super-admin',
        )
        api = APIClient()
        api.force_authenticate(user=self.super_admin_user)  # still active -- 2 active admins total
        resp = api.post(f'/api/auth/users/{other_sa.id}/deactivate/')
        self.assertEqual(resp.status_code, 200)

    def test_bulk_actions_handles_a_real_multi_item_list_without_crashing(self):
        # Regression for the request.data.get('user_ids', []) QueryDict bug
        # (silently collapsed multi-value form fields to their last value)
        # found while building this exact test in Phase 11.
        sa5 = User.objects.create_user(username='t_sa5', email='t_sa5@test.com', password='p', first_name='F', last_name='A', role='super-admin', is_active=False)
        sa6 = User.objects.create_user(username='t_sa6', email='t_sa6@test.com', password='p', first_name='S', last_name='A', role='super-admin', is_active=False)
        api = APIClient()
        api.force_authenticate(user=self.super_admin_user)
        resp = api.post('/api/auth/users/bulk_actions/', {'user_ids': [sa5.id, sa6.id], 'action': 'activate'})
        self.assertEqual(resp.status_code, 200)
        sa5.refresh_from_db(); sa6.refresh_from_db()
        self.assertTrue(sa5.is_active and sa6.is_active)


class DepartmentCourseWritePermissionTest(PortalTestCase):
    """DepartmentViewSet/CourseViewSet write actions were open to ANY
    authenticated user before Phase 11 -- a student could create/update/
    delete departments and courses via the plain (non-admin-prefixed)
    endpoints. list/retrieve must stay exactly as open as before."""

    def test_student_cannot_write_to_the_plain_department_endpoint(self):
        api = APIClient()
        api.force_authenticate(user=self.student_user)
        resp = api.post('/api/academics/departments/', {'name': 'Hacked', 'code': 'HACK'})
        self.assertEqual(resp.status_code, 403)

    def test_student_cannot_write_to_the_plain_course_endpoint(self):
        api = APIClient()
        api.force_authenticate(user=self.student_user)
        resp = api.post('/api/academics/courses/', {
            'code': 'HACK101', 'title': 'Hack', 'credits': 3,
            'department': self.dept.id, 'semester': 'first', 'level': '100',
        })
        self.assertEqual(resp.status_code, 403)

    def test_list_and_retrieve_stay_public(self):
        api = APIClient()  # anonymous
        resp = api.get('/api/academics/departments/')
        self.assertEqual(resp.status_code, 200)

    def test_super_admin_can_still_write_to_the_plain_endpoints(self):
        api = APIClient()
        api.force_authenticate(user=self.super_admin_user)
        resp = api.post('/api/academics/departments/', {'name': 'Legit Dept', 'code': 'LEGIT'})
        self.assertEqual(resp.status_code, 201)


class CarryoverSlipIDORTest(PortalTestCase):
    """A student must never be able to view another student's printable
    carry-over slip by guessing the registration id (Checkpoint 4)."""

    def test_other_student_gets_404_not_someone_elses_slip(self):
        from academics.models import CourseRegistration
        registration = CourseRegistration.objects.create(
            student=self.student, course_offering=self.offering1, status='registered',
        )
        other_user = User.objects.create_user(
            username='t_other_student', email='t_other_student@test.com', password='pass12345',
            first_name='Other', last_name='Student', role='student',
        )
        from users.models import Student as StudentModel
        StudentModel.objects.create(
            user=other_user, matric_number='T-STU-002', department=self.dept, level='100',
            status='active', admission_date=self.today,
        )
        client = self.login(other_user)
        resp = client.get(f'/dashboard/student/carryover/{registration.id}/slip/')
        self.assertEqual(resp.status_code, 404)
