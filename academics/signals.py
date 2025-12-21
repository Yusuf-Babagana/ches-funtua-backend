# academics/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import CourseRegistration, Enrollment, CourseOffering # ✅ Updated import

@receiver(post_save, sender=CourseRegistration) # ✅ Updated sender
def manage_enrollment(sender, instance, created, **kwargs):
    """
    Auto-create Enrollment record when CourseRegistration is finalized (registered)
    """
    if instance.status == 'registered':
        # Create or get the enrollment record
        Enrollment.objects.get_or_create(
            student=instance.student,
            course=instance.course_offering.course,
            session=instance.course_offering.semester.session,
            semester=instance.course_offering.semester.semester,
            defaults={
                'status': 'enrolled'
            }
        )
        
        # Update course offering count
        update_offering_count(instance.course_offering)

@receiver(post_save, sender=CourseRegistration) # ✅ Updated sender
def update_count_on_save(sender, instance, **kwargs):
    """Update count whenever a registration is saved (in case status changed)"""
    update_offering_count(instance.course_offering)

@receiver(post_delete, sender=CourseRegistration) # ✅ Updated sender
def update_count_on_delete(sender, instance, **kwargs):
    """Update count when a registration is deleted"""
    update_offering_count(instance.course_offering)

def update_offering_count(offering):
    """Helper to recalculate enrolled count"""
    count = CourseRegistration.objects.filter( # ✅ Updated Query
        course_offering=offering, 
        status='registered'
    ).count()
    
    # Avoid infinite recursion if save() triggers signals
    CourseOffering.objects.filter(id=offering.id).update(enrolled_count=count)


    