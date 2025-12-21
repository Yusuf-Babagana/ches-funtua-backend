# academics/utils.py
from django.utils import timezone
from finance.models import Invoice
from .models import Semester

def check_student_payment_status(student):
    """Check if student has paid fees for current semester"""
    current_semester = Semester.objects.filter(is_current=True).first()
    if not current_semester:
        return False, "No current semester set"
    
    try:
        invoice = Invoice.objects.get(
            student=student,
            session=current_semester.session,
            semester=current_semester.semester,
            status='paid'
        )
        
        if invoice.is_tuition_paid():
            return True, "Payment verified"
        else:
            return False, "Tuition not fully paid"
            
    except Invoice.DoesNotExist:
        return False, "No paid invoice found for current semester"