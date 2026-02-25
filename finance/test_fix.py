from django.test import TestCase, Client
from django.urls import reverse
from users.models import User, Student
from academics.models import Semester, Department
from finance.models import Invoice, Payment
from django.utils import timezone
from decimal import Decimal

class PaymentFixTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='teststudent', password='password', role='student')
        self.dept = Department.objects.create(name='Test Dept', code='TD')
        self.student = Student.objects.create(
            user=self.user, 
            level='100', 
            department=self.dept, 
            matric_number='TEST001',
            admission_date=timezone.now().date()
        )
        self.semester = Semester.objects.create(
            session='2024/2025', 
            semester='first', 
            is_current=True,
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timezone.timedelta(days=30),
            registration_deadline=timezone.now().date() + timezone.timedelta(days=15)
        )
        self.invoice = Invoice.objects.create(
            student=self.student,
            invoice_number='INV-TEST-001',
            amount=Decimal('1000.00'),
            amount_paid=Decimal('0.00'),
            session='2024/2025',
            semester='first',
            due_date=timezone.now().date() + timezone.timedelta(days=7),
            description='Test Invoice'
        )

    def test_invoice_status_auto_calc(self):
        """Test that invoice status updates correctly on save"""
        self.invoice.amount_paid = Decimal('500.00')
        self.invoice.save()
        self.assertEqual(self.invoice.status, 'partially_paid')
        
        self.invoice.amount_paid = Decimal('1000.00')
        self.invoice.save()
        self.assertEqual(self.invoice.status, 'paid')

    def test_invoice_update_status_persistence(self):
        """Test that update_status persists amount_paid (The bug fix)"""
        self.invoice.amount_paid = Decimal('1000.00')
        self.invoice.update_status()
        
        # Refresh from DB
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal('1000.00'))
        self.assertEqual(self.invoice.status, 'paid')

    def test_paystack_verify_get_method(self):
        """Test that Paystack verify accepts GET method"""
        self.client.login(username='teststudent', password='password')
        url = reverse('paystack-verify')
        response = self.client.get(url, {'reference': 'TEST_REF'})
        # Should NOT be 405. Since reference doesn't exist, it should likely be 400 from the logic
        self.assertNotEqual(response.status_code, 405)
        self.assertEqual(response.status_code, 400) # Reference not found in service
