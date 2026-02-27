from django.db import models
from users.models import User, Student  # Added Student import
from academics.models import Semester
import uuid
from django.db.models.expressions import CombinedExpression

class FeeStructure(models.Model):
    """Fee structure for different levels and departments"""
    
    LEVEL_CHOICES = [
        ('100', 'Level 1'),
        ('200', 'Level 2'),
        ('300', 'Level 3'),
    ]
    
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES)
    department = models.ForeignKey('academics.Department', on_delete=models.CASCADE, related_name='fee_structures')
    tuition_fee = models.DecimalField(max_digits=10, decimal_places=2)
    library_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    lab_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sports_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    medical_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    other_fees = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    session = models.CharField(max_length=9)  # e.g., 2024/2025
    semester = models.CharField(max_length=10, choices=[
        ('first', 'First Semester'),
        ('second', 'Second Semester')
    ],
     default='first'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['level', 'department', 'session', 'semester']
        verbose_name = 'Fee Structure'
        verbose_name_plural = 'Fee Structures'
    
    def __str__(self):
        return f"{self.name} - {self.session} {self.semester}"
    
    @property
    def total_fee(self):
        fees = [
            self.tuition_fee, self.library_fee, self.lab_fee,
            self.sports_fee, self.medical_fee, self.other_fees
        ]
        return sum(fee if fee is not None else 0 for fee in fees)


class Invoice(models.Model):
    """Invoice generation for students"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('partially_paid', 'Partially Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]
    
    invoice_number = models.CharField(max_length=50, unique=True, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='invoices')  # Changed back to Student
    fee_structure = models.ForeignKey(FeeStructure, on_delete=models.SET_NULL, null=True)
    session = models.CharField(max_length=9)
    semester = models.CharField(max_length=10)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    due_date = models.DateField()
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'
    
    def __str__(self):
        return f"{self.invoice_number} - {self.student.matric_number}"  # Changed back to matric_number
    
    @property
    def balance(self):
        amount = self.amount or 0
        paid = self.amount_paid or 0
        return amount - paid

    def save(self, *args, **kwargs):
        # ✅ FIX: Skip auto-status update if F() expressions are used
        # Python cannot compare F() expressions to integers
        if not isinstance(self.amount_paid, (CombinedExpression)) and \
           not isinstance(self.amount, (CombinedExpression)):
            if self.balance <= 0:
                self.status = 'paid'
            elif self.amount_paid > 0:
                self.status = 'partially_paid'
            else:
                self.status = 'pending'
        super().save(*args, **kwargs)

    def update_status(self):
        """Update invoice status based on payment"""
        if self.amount is None or self.amount_paid is None:
            self.status = 'pending'
        elif self.amount_paid >= self.amount:
            self.status = 'paid'
        elif self.amount_paid > 0:
            self.status = 'partially_paid'
        else:
            self.status = 'pending'
        self.save(update_fields=['status', 'amount_paid', 'updated_at'])
    
    def is_tuition_paid(self):
        """Check if tuition fee is fully paid"""
        if self.status == 'paid' and self.amount_paid >= self.amount:
            return True
        return False


class Payment(models.Model):
    """Payment transactions with Paystack integration"""
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('reversed', 'Reversed'),
    ]
    
    PAYMENT_METHOD_CHOICES = [
        ('paystack', 'Paystack'),
        ('bank_transfer', 'Bank Transfer'),
        ('card', 'Card'),
        ('cash', 'Cash'),
        ('pos', 'POS'),
    ]
    
    reference_id = models.CharField(max_length=50, unique=True, editable=False)
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='payments')  # Changed back to Student
    invoice = models.ForeignKey(Invoice, on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='paystack')
    description = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Paystack fields
    paystack_reference = models.CharField(max_length=100, blank=True)
    paystack_access_code = models.CharField(max_length=100, blank=True)
    paystack_authorization_url = models.TextField(blank=True)
    
    transaction_reference = models.CharField(max_length=100, blank=True)
    payment_date = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_payments')
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
    
    def __str__(self):
        return f"{self.reference_id} - {self.student.matric_number} - ₦{self.amount}"  # Changed back to matric_number
    
    def save(self, *args, **kwargs):
        if not self.reference_id:
            self.reference_id = f"PAY-{uuid.uuid4().hex[:10].upper()}"
            
        # Set default amount if not provided
        if self.amount is None and self.invoice:
            self.amount = self.invoice.balance
            
        super().save(*args, **kwargs)


class PaystackTransaction(models.Model):
    """Store Paystack transaction details"""
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='paystack_details')
    paystack_reference = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='NGN')
    channel = models.CharField(max_length=50, blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    paystack_data = models.JSONField(default=dict)  # Store full Paystack response
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Paystack Transaction'
        verbose_name_plural = 'Paystack Transactions'
    
    def __str__(self):
        return f"Paystack: {self.paystack_reference}"


class PaymentReceipt(models.Model):
    """Payment receipts"""
    
    receipt_number = models.CharField(max_length=50, unique=True, editable=False)
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name='receipt')
    issued_date = models.DateTimeField(auto_now_add=True)
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='issued_receipts')
    receipt_file = models.FileField(upload_to='receipts/', null=True, blank=True)
    
    class Meta:
        ordering = ['-issued_date']
        verbose_name = 'Payment Receipt'
        verbose_name_plural = 'Payment Receipts'
    
    def __str__(self):
        return f"{self.receipt_number} - {self.payment.reference_id}"
    
    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = f"REC-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)