"""
Permanent regression coverage for the credit-unit registration cap
(academics/constants.py: MAX_CREDIT_UNITS_UNPAID=8, MAX_CREDIT_UNITS_PAID=24).
This replaced three previously-inconsistent course-COUNT caps across the
DRF API and the desk-officer override path -- the single highest-risk
change of the whole migration, since it touched two already-shipped
phases at once. Covers both the portal (template) layer and the
underlying DRF API, since the whole point of the fix was making sure
they can't drift apart again.
"""
from academics.constants import MAX_CREDIT_UNITS_PAID, MAX_CREDIT_UNITS_UNPAID
from academics.models import Course, CourseOffering
from finance.models import Invoice

from .base import PortalTestCase


class CreditUnitCapTest(PortalTestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # 6 x 4-unit offerings -- enough to cross both the 8-unit and
        # 24-unit boundaries with room to spare.
        cls.offerings = []
        for i in range(6):
            course = Course.objects.create(
                code=f'CAP10{i}', title=f'Cap Test Course {i}', credits=4,
                department=cls.dept, semester='first', level='100',
            )
            offering = CourseOffering.objects.create(
                course=course, lecturer=cls.lecturer, semester=cls.semester, capacity=50, is_active=True,
            )
            cls.offerings.append(offering)

    def _credit_total(self, student):
        from academics.models import CourseRegistration
        regs = CourseRegistration.objects.filter(
            student=student, course_offering__semester=self.semester,
        ).exclude(status='dropped')
        return sum(r.course_offering.course.credits for r in regs)

    # --- Portal (student self-service) ---

    def test_unpaid_student_capped_at_unpaid_threshold(self):
        client = self.login(self.student_user)
        client.post('/dashboard/student/registration/', {
            'course_offering_ids': [self.offerings[0].id, self.offerings[1].id],
        })
        self.assertEqual(self._credit_total(self.student), 8)

        # a 3rd course (12 total) would exceed the unpaid cap -- blocked
        client.post('/dashboard/student/registration/', {'course_offering_ids': [self.offerings[2].id]})
        self.assertEqual(self._credit_total(self.student), 8, "should stay at the unpaid cap, not exceed it")

    def test_paid_student_capped_at_paid_threshold(self):
        Invoice.objects.create(
            student=self.student, fee_structure=self.fee_structure, session=self.semester.session,
            semester=self.semester.semester, amount=1000, amount_paid=1000, due_date=self.today,
        )
        client = self.login(self.student_user)
        client.post('/dashboard/student/registration/', {
            'course_offering_ids': [o.id for o in self.offerings],  # 6 x 4 = 24
        })
        self.assertEqual(self._credit_total(self.student), MAX_CREDIT_UNITS_PAID)

        extra_course = Course.objects.create(code='CAPX', title='Extra', credits=4, department=self.dept, semester='first', level='100')
        extra_offering = CourseOffering.objects.create(course=extra_course, lecturer=self.lecturer, semester=self.semester, capacity=50, is_active=True)
        client.post('/dashboard/student/registration/', {'course_offering_ids': [extra_offering.id]})
        self.assertEqual(self._credit_total(self.student), MAX_CREDIT_UNITS_PAID, "should stay at the paid cap, not exceed it")

    # --- Desk-officer manual override ---

    def test_desk_officer_override_shares_the_same_paid_cap(self):
        client = self.login(self.desk_officer_user)
        resp = client.post('/dashboard/desk-officer/registration/', {
            'student_id': self.student.id,
            'course_offering_ids': [o.id for o in self.offerings],  # 24 units
            'override_payment': 'on',
            'remarks': 'regression test',
        }, follow=True)
        self.assertEqual(self._credit_total(self.student), MAX_CREDIT_UNITS_PAID)

        # a further batch in the SAME request would have exceeded the cap;
        # here we confirm a follow-up single-course submission is blocked too
        extra_course = Course.objects.create(code='CAPY', title='Extra Y', credits=4, department=self.dept, semester='first', level='100')
        extra_offering = CourseOffering.objects.create(course=extra_course, lecturer=self.lecturer, semester=self.semester, capacity=50, is_active=True)
        client.post('/dashboard/desk-officer/registration/', {
            'student_id': self.student.id, 'course_offering_ids': [extra_offering.id],
            'override_payment': 'on', 'remarks': 'should be blocked',
        }, follow=True)
        self.assertEqual(self._credit_total(self.student), MAX_CREDIT_UNITS_PAID)

    # --- DRF API layer (same rule, must not drift from the portal layer) ---

    def test_drf_api_enforces_the_same_unpaid_cap(self):
        from rest_framework.test import APIClient
        api = APIClient()
        api.force_authenticate(user=self.student_user)

        resp = api.get('/api/registrations/registration_status/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['registration_status']['max_credit_units'], MAX_CREDIT_UNITS_UNPAID)

        resp2 = api.post('/api/registrations/register_courses/', {
            'course_offering_ids': [self.offerings[0].id, self.offerings[1].id],
        }, format='json')
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(self._credit_total(self.student), 8)

        resp3 = api.post('/api/registrations/register_courses/', {
            'course_offering_ids': [self.offerings[2].id],
        }, format='json')
        self.assertEqual(resp3.status_code, 400)
        self.assertEqual(self._credit_total(self.student), 8)
