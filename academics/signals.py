# academics/signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import CourseRegistration, Enrollment, CourseOffering

@receiver(post_save, sender=CourseRegistration, dispatch_uid='course_registration_post_save')
def manage_course_registration_save(sender, instance, created, **kwargs):
    """
    Combined handler for CourseRegistration post_save:
    1. Auto-create Enrollment record when finalized (registered)
    2. Always update course offering enrolled count
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

    # Always update the offering count (handles status changes)
    update_offering_count(instance.course_offering)

@receiver(post_delete, sender=CourseRegistration, dispatch_uid='course_registration_post_delete')
def update_count_on_delete(sender, instance, **kwargs):
    """Update count when a registration is deleted"""
    update_offering_count(instance.course_offering)

def update_offering_count(offering):
    """Helper to recalculate enrolled count"""
    count = CourseRegistration.objects.filter(
        course_offering=offering, 
        status='registered'
    ).count()
    
    # Avoid infinite recursion by using update() instead of save()
    CourseOffering.objects.filter(id=offering.id).update(enrolled_count=count)

