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


# ==============================================
# FEE CATALOG (CHESF Student Portal Digest)
# ==============================================

class FeeItem(models.Model):
    """
    An ad-hoc, named fee a student can optionally or mandatorily pay
    (accommodation, index, practical, uniform, etc.) -- distinct from the
    fixed 6-component FeeStructure (tuition/library/lab/sports/medical/
    other), which stays exactly as-is. Actual amounts live in
    FeeItemCharge, set by the Bursar; nothing here is chargeable until a
    matching active FeeItemCharge exists.
    """
    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    is_optional = models.BooleanField(default=True, help_text="Optional fees (accommodation, uniform, etc.) vs. mandatory ones.")
    requires_selection = models.BooleanField(
        default=False,
        help_text="If true, paying this fee redirects the student to an additional step (e.g. Practical Fee -> center selection)."
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Fee Item'
        verbose_name_plural = 'Fee Items'

    def __str__(self):
        return self.name

    def current_charge(self, session, semester=None, level=None):
        """The most specific active FeeItemCharge for the given scope, or None."""
        qs = self.charges.filter(session=session, is_active=True)
        specific = qs.filter(semester=semester, level=level).first() if (semester or level) else None
        return specific or qs.filter(semester__isnull=True, level__isnull=True).first()


class FeeItemCharge(models.Model):
    """Bursar-set price for a FeeItem in a given session (optionally
    scoped to a semester and/or level)."""
    fee_item = models.ForeignKey(FeeItem, on_delete=models.CASCADE, related_name='charges')
    session = models.CharField(max_length=9)
    semester = models.CharField(max_length=10, choices=[('first', 'First Semester'), ('second', 'Second Semester')], null=True, blank=True)
    level = models.CharField(max_length=10, choices=FeeStructure.LEVEL_CHOICES, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_active = models.BooleanField(default=False, help_text="Nothing is chargeable until the Bursar activates a real price.")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['fee_item__name', '-session']
        unique_together = ['fee_item', 'session', 'semester', 'level']
        verbose_name = 'Fee Item Charge'
        verbose_name_plural = 'Fee Item Charges'

    def __str__(self):
        return f"{self.fee_item.name} - {self.session} - ₦{self.amount}"


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
    fee_item = models.ForeignKey(
        'finance.FeeItem', on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices',
        help_text="Set when this invoice is for an ad-hoc fee item (accommodation, index, practical, etc.) rather than tuition."
    )
    course_registration = models.ForeignKey(
        'academics.CourseRegistration', on_delete=models.SET_NULL, null=True, blank=True, related_name='fee_invoices',
        help_text="Set when this invoice is a carry-over exam fee tied to a specific re-registration."
    )
    session = models.CharField(max_length=9)
    semester = models.CharField(max_length=10)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    due_date = models.DateField()
    description = models.TextField()
    allow_part_payment = models.BooleanField(default=False, help_text="Is this invoice eligible for part-payment?")
    min_installment_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Minimum partial payment amount if part payment is allowed")
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