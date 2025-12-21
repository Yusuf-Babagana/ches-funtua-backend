from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FeeStructureViewSet, 
    InvoiceViewSet,
    PaymentViewSet, 
    PaymentReceiptViewSet,
    StudentFinanceViewSet, 
    PaystackPaymentViewSet, # ✅ Ensure this is imported
    FeeViewSet
)
from .views_bursar import (
    BursarDashboardViewSet,
    PaymentVerificationViewSet,
    InvoiceManagementViewSet,
    ReceiptManagementViewSet,
    FinancialReportsViewSet,
    BursarAPIView
)

router = DefaultRouter()

# --- Core Finance Routes ---
router.register(r'fee-structures', FeeStructureViewSet, basename='fee-structure')
router.register(r'invoices', InvoiceViewSet, basename='invoice')
router.register(r'payments', PaymentViewSet, basename='payment')
router.register(r'receipts', PaymentReceiptViewSet, basename='receipt')

# ✅ Register Paystack ViewSet
router.register(r'paystack', PaystackPaymentViewSet, basename='paystack')

# --- Student Routes ---
router.register(r'student-fees', FeeViewSet, basename='student-fees')
router.register(r'student', StudentFinanceViewSet, basename='student-finance')

# --- Bursar Routes ---
router.register(r'bursar/payment-verifications', PaymentVerificationViewSet, basename='bursar-payment-verifications')
router.register(r'bursar/invoice-management', InvoiceManagementViewSet, basename='bursar-invoice-management')
router.register(r'bursar/receipt-management', ReceiptManagementViewSet, basename='bursar-receipt-management')
router.register(r'bursar/financial-reports', FinancialReportsViewSet, basename='bursar-financial-reports')

urlpatterns = [
    # ✅ PRIORITY: This manual path MUST be first
    path('student/current-invoice/', StudentFinanceViewSet.as_view({'get': 'current_invoice'}), name='student-current-invoice'),

    # Bursar Dashboard
    path('bursar/dashboard/', BursarDashboardViewSet.as_view({'get': 'overview'}), name='bursar-dashboard-overview'),
    path('bursar/profile/', BursarAPIView.as_view(), name='bursar-profile'),

    # Student Manual Overrides
    path('student/invoices/', InvoiceViewSet.as_view({'get': 'student_invoices'}), name='student-invoices'),
    path('student/payments/', PaymentViewSet.as_view({'get': 'student_payments'}), name='student-payments'),
    path('student/fee-summary/', InvoiceViewSet.as_view({'get': 'student_fee_summary'}), name='student-fee-summary'),
    
    # ✅ FIX: Point Paystack URLs to the correct PaystackPaymentViewSet
    path('paystack/initialize/', PaystackPaymentViewSet.as_view({'post': 'initialize'}), name='paystack-initialize'),
    path('paystack/webhook/', PaystackPaymentViewSet.as_view({'post': 'paystack_webhook'}), name='paystack-webhook'),
    path('paystack/verify/', PaystackPaymentViewSet.as_view({'post': 'verify'}), name='paystack-verify'),

    # Admin
    path('invoices/summary/', InvoiceViewSet.as_view({'get': 'summary'}), name='invoice-summary'),
    path('payments/summary/', PaymentViewSet.as_view({'get': 'summary'}), name='payment-summary'),

    path('', include(router.urls)),
]