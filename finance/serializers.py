
# finance/serializers.py
from rest_framework import serializers
from .models import (
    FeeStructure, Invoice, Payment, 
    PaymentReceipt, PaystackTransaction
)

class FeeStructureSerializer(serializers.ModelSerializer):
    """Fee structure serializer"""
    department_name = serializers.CharField(source='department.name', read_only=True)
    total_fee = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = FeeStructure
        fields = [
            'id', 'name', 'description', 'level', 'department', 
            'department_name', 'tuition_fee', 'library_fee', 'lab_fee',
            'sports_fee', 'medical_fee', 'other_fees', 'total_fee',
            'session', 'semester', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class InvoiceSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    matric_number = serializers.CharField(source='student.matric_number', read_only=True)
    department_name = serializers.CharField(source='student.department.name', read_only=True)
    level = serializers.CharField(source='student.level', read_only=True)
    
    # ✅ FIX: Handle case where Fee Structure is None
    fee_structure_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Invoice
        fields = [
            'id', 'invoice_number', 'student', 'student_name', 'matric_number',
            'department_name', 'level', 'fee_structure_name', 
            'session', 'semester', 'amount', 'amount_paid', 'balance', 'status', 
            'due_date', 'description', 'created_at'
        ]

    def get_fee_structure_name(self, obj):
        # Safely return name or a default string
        if obj.fee_structure:
            return obj.fee_structure.name
        return "Standard Tuition"


        

class PaystackTransactionSerializer(serializers.ModelSerializer):
    """Paystack transaction serializer"""
    class Meta:
        model = PaystackTransaction
        fields = [
            'id', 'paystack_reference', 'amount', 'currency', 'channel',
            'ip_address', 'paid_at', 'created_at', 'paystack_data'
        ]
        read_only_fields = ['id']


class PaymentSerializer(serializers.ModelSerializer):
    """Payment serializer with Paystack details"""
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    matric_number = serializers.CharField(source='student.matric_number', read_only=True)
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    verified_by_name = serializers.SerializerMethodField()
    # If PaystackTransaction is related via payment, we can include it if needed
    # paystack_details = PaystackTransactionSerializer(read_only=True) 
    
    class Meta:
        model = Payment
        fields = [
            'id', 'reference_id', 'student', 'student_name', 'matric_number',
            'invoice', 'invoice_number', 'amount', 'payment_method',
            'description', 'status', 'paystack_reference', 'paystack_access_code',
            'paystack_authorization_url', 'transaction_reference',
            'payment_date', 'verified_by', 'verified_by_name', 'remarks',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'reference_id', 'created_at', 'updated_at']
    
    def get_verified_by_name(self, obj):
        return obj.verified_by.get_full_name() if obj.verified_by else None


class PaymentCreateSerializer(serializers.ModelSerializer):
    """Payment creation serializer"""
    
    class Meta:
        model = Payment
        fields = [
            'student', 'invoice', 'amount', 'payment_method',
            'description', 'transaction_reference', 'remarks'
        ]
    
    def validate(self, data):
        # Validate payment amount
        if data.get('invoice'):
            invoice = data['invoice']
            if data['amount'] > invoice.balance:
                raise serializers.ValidationError(
                    "Payment amount cannot exceed invoice balance"
                )
        return data


class PaystackInitializeSerializer(serializers.Serializer):
    """Serializer for initializing Paystack payment"""
    invoice_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    email = serializers.EmailField()
    callback_url = serializers.URLField(required=False)
    
    def validate(self, data):
        try:
            from .models import Invoice
            invoice = Invoice.objects.get(id=data['invoice_id'])
            
            # Check if amount exceeds invoice balance
            if data['amount'] > invoice.balance:
                raise serializers.ValidationError("Amount exceeds invoice balance")
            
            # Check if invoice belongs to the student
            # Note: Context 'request' is needed here, usually passed from view
            if self.context.get('request'):
                user = self.context['request'].user
                if hasattr(user, 'student_profile') and invoice.student != user.student_profile:
                    raise serializers.ValidationError("Invoice does not belong to student")
                
        except Invoice.DoesNotExist:
            raise serializers.ValidationError("Invoice not found")
        return data


class PaystackWebhookSerializer(serializers.Serializer):
    """Serializer for Paystack webhook data"""
    event = serializers.CharField()
    data = serializers.DictField()
    
    def validate(self, data):
        if data['event'] != 'charge.success':
            raise serializers.ValidationError("Unsupported webhook event")
        return data


class PaymentReceiptSerializer(serializers.ModelSerializer):
    """Payment receipt serializer"""
    payment_details = PaymentSerializer(source='payment', read_only=True)
    issued_by_name = serializers.SerializerMethodField()
    student_name = serializers.CharField(source='payment.student.user.get_full_name', read_only=True)
    amount = serializers.DecimalField(source='payment.amount', max_digits=10, decimal_places=2, read_only=True)
    payment_reference = serializers.CharField(source='payment.reference_id', read_only=True)
    
    class Meta:
        model = PaymentReceipt
        fields = [
            'id', 'receipt_number', 'payment', 'payment_details', 'payment_reference',
            'student_name', 'amount', 'issued_date', 'issued_by', 'issued_by_name', 
            'receipt_file'
        ]
        read_only_fields = ['id', 'receipt_number', 'issued_date']
    
    def get_issued_by_name(self, obj):
        return obj.issued_by.get_full_name() if obj.issued_by else None


class StudentFeeSummarySerializer(serializers.Serializer):
    """Student fee summary serializer"""
    total_invoices = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_paid = serializers.DecimalField(max_digits=10, decimal_places=2)
    total_outstanding = serializers.DecimalField(max_digits=10, decimal_places=2)
    # Use the safe InvoiceSerializer here
    current_semester_invoice = InvoiceSerializer(read_only=True)
    has_paid_current_fees = serializers.BooleanField()


class PaymentSummarySerializer(serializers.Serializer):
    """Payment summary serializer"""
    total_payments = serializers.IntegerField()
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    pending_payments = serializers.IntegerField()
    pending_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    payment_methods = serializers.DictField()
