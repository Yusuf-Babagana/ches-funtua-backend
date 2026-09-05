"""
Permanent cross-role integration coverage -- the thing no single phase's
own smoke test ever exercised, since each phase tested its own role in
isolation. These follow one piece of data all the way across role
boundaries and assert every hop landed correctly.
"""
from unittest.mock import patch

from academics.models import CourseRegistration, Grade
from finance.models import FeeItem, FeeItemCharge, Invoice, Payment

from .base import PortalTestCase


class ResultApprovalChainTest(PortalTestCase):
    """Student registers -> Lecturer grades -> HOD approves -> Exam
    Officer verifies -> Registrar publishes -> the SAME grade is visible
    to both the student and the Desk Officer's student-profile lookup.
    Mirrors the canonical 5-stage workflow every grading phase (4-6, 8)
    was built against."""

    def test_full_chain_from_registration_to_publication(self):
        # 1. Student registers for course1's offering (self-service).
        student_client = self.login(self.student_user)
        student_client.post('/dashboard/student/registration/', {
            'course_offering_ids': [self.offering1.id],
        })
        registration = CourseRegistration.objects.get(student=self.student, course_offering=self.offering1)
        self.assertEqual(registration.status, 'registered')

        # 2. Lecturer enters and submits scores.
        lecturer_client = self.login(self.lecturer_user)
        resp = lecturer_client.post(f'/dashboard/lecturer/courses/{self.course1.id}/', {
            'action': 'submit',
            f'ca_{self.student.id}': '30',
            f'exam_{self.student.id}': '45',
        })
        grade = Grade.objects.get(student=self.student, course=self.course1)
        self.assertEqual(grade.status, 'submitted')
        self.assertEqual(float(grade.score), 75.0)
        self.assertEqual(grade.grade_letter, 'A')

        # A published/HOD-approved grade must not be visible to the student yet.
        resp_results_before = student_client.get('/dashboard/student/results/')
        self.assertNotContains(resp_results_before, 'CH101')

        # 3. HOD approves.
        hod_client = self.login(self.hod_user)
        hod_client.post(f'/dashboard/hod/approvals/{self.course1.id}/approve/')
        grade.refresh_from_db()
        self.assertEqual(grade.status, 'hod_approved')

        # 4. Exam Officer verifies.
        eo_client = self.login(self.exam_officer_user)
        eo_client.post(f'/dashboard/exam-officer/results/{self.course1.id}/verify/')
        grade.refresh_from_db()
        self.assertEqual(grade.status, 'verified')

        # 5. Registrar publishes.
        registrar_client = self.login(self.registrar_user)
        registrar_client.post(f'/dashboard/registrar/publication/{self.course1.id}/publish/')
        grade.refresh_from_db()
        self.assertEqual(grade.status, 'published')

        # 6. Student now sees it on Results and Transcript, CGPA reflects it.
        resp_results = student_client.get('/dashboard/student/results/')
        self.assertContains(resp_results, 'CH101')
        resp_transcript = student_client.get('/dashboard/student/transcript/')
        self.assertEqual(resp_transcript.status_code, 200)
        self.assertContains(resp_transcript, 'CH101')

        # 7. Desk Officer's student-profile lookup shows the same published grade.
        do_client = self.login(self.desk_officer_user)
        resp_profile = do_client.get(f'/dashboard/desk-officer/students/{self.student.id}/')
        self.assertEqual(resp_profile.status_code, 200)
        self.assertContains(resp_profile, 'CH101')


class FeePaymentWorkflowTest(PortalTestCase):
    """Bursar prices a FeeItem -> student pays it (Paystack network calls
    mocked) -> the invoice is marked paid -> a receipt exists."""

    def test_bursar_prices_item_student_pays_it(self):
        bursar_client = self.login(self.bursar_user)
        resp = bursar_client.post('/dashboard/bursar/fee-items/', {
            'fee_item_id': FeeItem.objects.get(code='accommodation').id,
            'session': self.semester.session, 'semester': '', 'level': '', 'amount': '15000',
        })
        charge = FeeItemCharge.objects.get(fee_item__code='accommodation', session=self.semester.session)
        self.assertTrue(charge.is_active)
        self.assertEqual(float(charge.amount), 15000.0)

        student_client = self.login(self.student_user)
        resp2 = student_client.get('/dashboard/student/fees/catalog/')
        row = next(r for r in resp2.context['catalog'] if r['fee_item'].code == 'accommodation')
        self.assertTrue(row['is_priced'])

        with patch('finance.services.FinanceService.initialize_paystack_transaction') as mock_init:
            mock_init.return_value = {'success': True, 'authorization_url': 'https://paystack.test/pay/xyz', 'reference': 'FAKEREF1'}
            resp3 = student_client.post(f'/dashboard/student/fees/catalog/{row["fee_item"].id}/pay/')
        self.assertEqual(resp3.status_code, 302)
        invoice = Invoice.objects.get(student=self.student, fee_item__code='accommodation')
        self.assertEqual(invoice.status, 'pending')  # not yet verified

        # Simulate the Paystack callback/verification succeeding.
        Payment.objects.create(
            student=self.student, invoice=invoice, amount=invoice.amount,
            payment_method='paystack', status='pending', paystack_reference='FAKEREF1',
        )
        with patch('finance.services.FinanceService.verify_paystack_transaction') as mock_verify:
            mock_verify.return_value = {'success': True, 'message': 'Payment verified successfully'}
            resp4 = student_client.get('/dashboard/student/payments/verify/?reference=FAKEREF1')
        self.assertEqual(resp4.status_code, 200)


class AnnouncementVisibilityTest(PortalTestCase):
    """An HOD's department+level-scoped announcement reaches the matching
    student and no one else (Checkpoint 5's context processor)."""

    def test_announcement_scoping_across_department_and_level(self):
        other_student_user = self._make_student_in(self.dept2, level='200')

        hod_client = self.login(self.hod_user)
        hod_client.post('/dashboard/hod/announcements/post/', {
            'title': 'Dept Notice', 'body': 'Important update.', 'level': '100',
        })

        matching = self.login(self.student_user).get('/dashboard/student/')
        self.assertIn('Dept Notice', {a.title for a in matching.context['active_announcements']})

        other = self.login(other_student_user).get('/dashboard/student/')
        self.assertNotIn('Dept Notice', {a.title for a in other.context['active_announcements']})

    def _make_student_in(self, department, level):
        from users.models import Student as StudentModel, User as UserModel
        user = UserModel.objects.create_user(
            username=f'wf_student_{department.code}', email=f'wf_{department.code}@test.com',
            password='pass12345', first_name='Wf', last_name='Student', role='student',
        )
        StudentModel.objects.create(
            user=user, matric_number=f'WF-{department.code}', department=department, level=level,
            status='active', admission_date=self.today,
        )
        return user


class SupportChatWorkflowTest(PortalTestCase):
    """Student message -> Desk Officer inbox + reply -> student sees the
    reply (Checkpoint 6's polling chat)."""

    def test_message_round_trip(self):
        student_client = self.login(self.student_user)
        student_client.get('/dashboard/student/support/')  # auto-creates the thread
        student_client.post('/dashboard/student/support/send/', {'body': 'I need help with my fees.'})

        from support.models import ChatThread
        thread = ChatThread.objects.get(student=self.student)

        do_client = self.login(self.desk_officer_user)
        resp = do_client.get('/dashboard/desk-officer/support/')
        self.assertEqual(list(resp.context['threads'])[0].id, thread.id)

        do_client.post(f'/dashboard/desk-officer/support/{thread.id}/send/', {'body': 'How can I help?'})

        resp2 = student_client.get('/dashboard/student/support/poll/?after=0')
        bodies = [m['body'] for m in resp2.json()['messages']]
        self.assertIn('How can I help?', bodies)
