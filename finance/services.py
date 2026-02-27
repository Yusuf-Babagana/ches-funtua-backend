import logging
import requests
import uuid
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from django.db.models import F
from .models import Payment, PaystackTransaction, PaymentReceipt

# Setup logging to see errors in your terminal
logger = logging.getLogger(__name__)

class FinanceService:
    @staticmethod
    def initialize_paystack_transaction(user, invoice, amount, callback_url):
        try:
            # 1. Check Settings
            if not getattr(settings, 'PAYSTACK_SECRET_KEY', None):
                logger.error("❌ PAYSTACK_SECRET_KEY is missing in settings.py")
                return {'success': False, 'error': 'Server configuration error: Missing Paystack Key'}

            secret_key = settings.PAYSTACK_SECRET_KEY
            base_url = "https://api.paystack.co"
            
            # 2. Create local payment record
            try:
                payment = Payment.objects.create(
                    student=invoice.student,
                    invoice=invoice,
                    amount=amount,
                    payment_method='paystack',
                    description=f"Tuition Payment for {invoice.invoice_number}",
                    status='pending'
                )
            except Exception as db_err:
                logger.error(f"❌ Database error creating payment: {str(db_err)}")
                return {'success': False, 'error': 'Failed to create payment record'}

            # 3. Prepare Paystack Request
            headers = {
                "Authorization": f"Bearer {secret_key}",
                "Content-Type": "application/json",
            }
            
            # Ensure email is set (Paystack requirement)
            email = user.email if user.email else f"student{user.id}@college.edu"

            data = {
                "email": email,
                "amount": int(float(amount) * 100), # Paystack expects kobo (integers)
                "callback_url": callback_url,
                "metadata": {
                    "payment_id": payment.id,
                    "invoice_id": invoice.id,
                    "student_id": invoice.student.id,
                    "custom_fields": [
                        {
                            "display_name": "Invoice Number",
                            "variable_name": "invoice_number",
                            "value": invoice.invoice_number
                        }
                    ]
                }
            }
            
            # 4. Call Paystack API
            try:
                response = requests.post(f"{base_url}/transaction/initialize", headers=headers, json=data)
                response.raise_for_status() # Raise error for 4xx/5xx responses
                res_data = response.json()
            except requests.exceptions.RequestException as req_err:
                error_msg = f"Paystack API Error: {str(req_err)}"
                if response and response.content:
                     error_msg += f" | Response: {response.content.decode('utf-8')}"
                
                logger.error(f"❌ {error_msg}")
                
                payment.status = 'failed'
                payment.remarks = error_msg
                payment.save()
                return {'success': False, 'error': 'Payment gateway unavailable. Please try again.'}

            # 5. Process Success
            if res_data['status']:
                payment.paystack_reference = res_data['data']['reference']
                payment.paystack_access_code = res_data['data']['access_code']
                payment.paystack_authorization_url = res_data['data']['authorization_url']
                payment.save()
                
                return {
                    'success': True,
                    'authorization_url': res_data['data']['authorization_url'],
                    'reference': res_data['data']['reference'],
                    'payment_id': payment.id
                }
            else:
                 # Paystack returned 200 but status false
                 msg = res_data.get('message', 'Unknown Paystack Error')
                 logger.error(f"❌ Paystack Logic Error: {msg}")
                 
                 payment.status = 'failed'
                 payment.remarks = msg
                 payment.save()
                 return {'success': False, 'error': msg}

        except Exception as e:
            # Catch-all for logic errors (e.g. math errors, attribute errors)
            logger.error(f"💥 Critical error in initialize_paystack_transaction: {str(e)}", exc_info=True)
            return {'success': False, 'error': 'Internal system error processing payment'}

    @staticmethod
    def verify_paystack_transaction(reference):
        """
        Verifies a transaction with Paystack and updates the local Payment and Invoice.
        Utilizes atomic transactions and row-level locking to prevent state desync.
        """
        secret_key = settings.PAYSTACK_SECRET_KEY
        base_url = "https://api.paystack.co"
        headers = {"Authorization": f"Bearer {secret_key}"}
        
        try:
            response = requests.get(f"{base_url}/transaction/verify/{reference}", headers=headers)
            response.raise_for_status()
            res_data = response.json()
            
            if res_data['status'] and res_data['data']['status'] == 'success':
                # Use atomic block to ensure all-or-nothing persistence
                with transaction.atomic():
                    # 1. Lock the payment record and check status
                    try:
                        payment = Payment.objects.select_for_update().get(paystack_reference=reference)
                    except Payment.DoesNotExist:
                        return {'success': False, 'error': 'Payment record not found locally'}
                    
                    if payment.status == 'completed':
                        return {'success': True, 'message': 'Payment already verified'}

                    # 2. Update Payment State
                    payment.status = 'completed'
                    payment.payment_date = timezone.now()
                    payment.transaction_reference = str(res_data['data']['id']) 
                    payment.save()
                    
                    # 3. Log Paystack Transaction
                    PaystackTransaction.objects.create(
                        payment=payment,
                        paystack_reference=reference,
                        amount=res_data['data']['amount'] / 100,
                        currency=res_data['data']['currency'],
                        channel=res_data['data']['channel'],
                        ip_address=res_data['data']['ip_address'],
                        paid_at=res_data['data']['paid_at'],
                        paystack_data=res_data['data']
                    )

                    # 4. Atomic Increment of Invoice using F() expressions
                    if payment.invoice:
                        # Lock the invoice to prevent concurrent balance updates
                        invoice = Invoice.objects.select_for_update().get(id=payment.invoice.id)
                        
                        # Avoid manual float math; let the DB handle the addition
                        invoice.amount_paid = F('amount_paid') + payment.amount
                        invoice.save(update_fields=['amount_paid', 'updated_at'])
                        
                        # Refresh from DB to get the new amount_paid value for status logic
                        invoice.refresh_from_db()
                        invoice.update_status() 
                    
                    # 5. Generate Receipt
                    FinanceService.generate_receipt(payment)
                    
                return {'success': True, 'message': 'Payment verified successfully'}
                
            else:
                return {'success': False, 'error': 'Transaction verification failed at gateway'}

        except Exception as e:
            logger.error(f"❌ Verification Error: {str(e)}")
            return {'success': False, 'error': str(e)}

    @staticmethod
    def generate_receipt(payment):
        """
        Generates a payment receipt record.
        """
        PaymentReceipt.objects.get_or_create(payment=payment)