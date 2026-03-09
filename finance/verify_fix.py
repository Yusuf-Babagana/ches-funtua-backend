import os
import django
from decimal import Decimal
from django.utils import timezone

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from finance.models import Invoice
from finance.serializers import InvoiceSerializer
from users.models import User, Student
from academics.models import Department

def test_serializer_date_conversion():
    print("Starting date conversion verification test...")
    
    # Create mock data
    user, _ = User.objects.get_or_create(username='test_verify', defaults={'role': 'student'})
    dept, _ = Department.objects.get_or_create(name='Test Dept', code='TDV')
    student, _ = Student.objects.get_or_create(
        user=user, 
        defaults={
            'level': '100', 
            'department': dept, 
            'matric_number': 'VERIFY001',
            'admission_date': timezone.now().date()
        }
    )
    
    # Create invoice with a datetime in due_date (even though model expects date, 
    # we want to see if serializer handles it if it arrives as datetime from memory or DB)
    dt_now = timezone.now()
    invoice = Invoice.objects.create(
        student=student,
        invoice_number=f'INV-V-{dt_now.strftime("%H%M%S")}',
        amount=Decimal('100.00'),
        session='2024/2025',
        semester='first',
        due_date=dt_now.date(), # Model takes date
        description='Verification Invoice'
    )
    
    # Manually set a datetime to simulate the problematic state if it happens
    invoice.due_date = dt_now 
    
    # Serialize
    serializer = InvoiceSerializer(invoice)
    data = serializer.data
    
    print(f"Serialized date_issued: {data['date_issued']} (Type: {type(data['date_issued'])})")
    print(f"Serialized due_date: {data['due_date']} (Type: {type(data['due_date'])})")
    
    # In DRF, SerializerMethodField usually returns string or the object. 
    # DateField would have formatted it.
    
    assert not isinstance(data['date_issued'], timezone.datetime), "date_issued should not be a datetime object"
    assert not isinstance(data['due_date'], timezone.datetime), "due_date should not be a datetime object"
    
    print("Verification successful: Serializer handled datetime conversion.")

if __name__ == "__main__":
    try:
        test_serializer_date_conversion()
    except Exception as e:
        print(f"Verification failed: {e}")
        import traceback
        traceback.print_exc()
