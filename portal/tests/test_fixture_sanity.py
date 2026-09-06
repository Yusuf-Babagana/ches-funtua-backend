"""Quick sanity check that the shared fixture roster (base.PortalTestCase)
builds cleanly and every role can reach their own dashboard."""
from django.urls import reverse

from .base import PortalTestCase


class FixtureSanityTest(PortalTestCase):
    def test_fixture_roster_is_internally_consistent(self):
        self.assertEqual(self.dept.hod, self.hod_lecturer)
        self.assertTrue(self.semester.is_current)
        self.assertEqual(self.student.department, self.dept)
        self.assertEqual(self.course1.department, self.dept)

    def test_every_role_reaches_its_own_dashboard(self):
        role_to_url = {
            self.student_user: 'portal:dashboard_student',
            self.lecturer_user: 'portal:dashboard_lecturer',
            self.hod_user: 'portal:dashboard_hod',
            self.registrar_user: 'portal:dashboard_registrar',
            self.bursar_user: 'portal:dashboard_bursar',
            self.exam_officer_user: 'portal:dashboard_exam_officer',
            self.desk_officer_user: 'portal:dashboard_desk_officer',
            self.ict_user: 'portal:dashboard_ict',
            self.super_admin_user: 'portal:dashboard_super_admin',
        }
        for user, url_name in role_to_url.items():
            with self.subTest(role=user.role):
                client = self.login(user)
                resp = client.get(reverse(url_name))
                self.assertEqual(resp.status_code, 200, f"{user.role} dashboard did not render 200")
