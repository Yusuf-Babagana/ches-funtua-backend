from django.contrib import admin
from .models import FeeStructure, Invoice, Payment, PaymentReceipt

@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = ['name', 'level', 'department', 'total_fee', 'session', 'is_active']
    list_filter = ['level', 'department', 'session', 'is_active']
    search_fields = ['name', 'description']
    readonly_fields = ['total_fee']

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'student', 'amount', 'amount_paid', 'balance', 'status', 'due_date']
    list_filter = ['status', 'session', 'semester']
    search_fields = ['invoice_number', 'student__username', 'student__matric_number']
    readonly_fields = ['invoice_number', 'balance', 'created_at', 'updated_at']
    raw_id_fields = ['student', 'fee_structure']
    date_hierarchy = 'created_at'

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ['reference_id', 'student', 'amount', 'payment_method', 'status', 'payment_date']
    list_filter = ['status', 'payment_method', 'payment_date']
    search_fields = ['reference_id', 'student__username', 'transaction_reference']
    readonly_fields = ['reference_id', 'created_at', 'updated_at']
    raw_id_fields = ['student', 'invoice', 'verified_by']
    date_hierarchy = 'created_at'

@admin.register(PaymentReceipt)
class PaymentReceiptAdmin(admin.ModelAdmin):
    list_display = ['receipt_number', 'payment', 'issued_date', 'issued_by']
    search_fields = ['receipt_number', 'payment__reference_id']
    readonly_fields = ['receipt_number', 'issued_date']
    raw_id_fields = ['payment', 'issued_by']
    date_hierarchy = 'issued_date'