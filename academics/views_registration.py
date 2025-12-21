from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from django.db.models import F

from .models import Course, CourseOffering, CourseRegistration, Semester
from finance.models import Invoice # ✅ ADDED IMPORT
from .serializers import CourseOfferingSerializer, CourseRegistrationSerializer, RegistrationRequestSerializer
from users.permissions import IsStudent

class CourseOfferingViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Manages course visibility. 
    """
    permission_classes = [IsAuthenticated]
    serializer_class = CourseOfferingSerializer

    def get_queryset(self):
        return CourseOffering.objects.filter(is_active=True)

    @action(detail=False, methods=['get'])
    def available_courses(self, request):
        """
        Returns courses a student CAN register for.
        """
        if not hasattr(request.user, 'student_profile'):
            return Response({'error': 'Student profile not found'}, status=400)
        
        student = request.user.student_profile
        
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            return Response({'error': 'No active academic session found.'}, status=404)

        # 1. Get IDs of CourseOfferings ALREADY registered/pending
        registered_offering_ids = CourseRegistration.objects.filter(
            student=student,
            course_offering__semester=current_semester
        ).exclude(
            status='dropped' 
        ).values_list('course_offering_id', flat=True)

        # 2. Get Offerings (excluding registered ones)
        available_offerings = CourseOffering.objects.filter(
            semester=current_semester,
            course__level=student.level,
            course__department=student.department,
            is_active=True
        ).exclude(
            id__in=registered_offering_ids
        ).select_related('course', 'lecturer__user')

        # 3. Fallback: If courses exist but no offerings, create them
        if not available_offerings.exists():
            raw_courses = Course.objects.filter(
                level=student.level, 
                department=student.department
            )
            created_new = False
            for course in raw_courses:
                # Check if offering exists (even if registered)
                if not CourseOffering.objects.filter(course=course, semester=current_semester).exists():
                    CourseOffering.objects.create(
                        course=course,
                        semester=current_semester,
                        capacity=1000,
                        is_active=True
                    )
                    created_new = True
            
            if created_new:
                # Re-query
                available_offerings = CourseOffering.objects.filter(
                    semester=current_semester,
                    course__level=student.level,
                    course__department=student.department,
                    is_active=True
                ).exclude(
                    id__in=registered_offering_ids
                ).select_related('course', 'lecturer__user')

        results = []
        for offering in available_offerings:
            results.append({
                'id': offering.id,
                'course_code': offering.course.code,
                'course_title': offering.course.title,
                'course_credits': offering.course.credits,
                'department_name': offering.course.department.name,
                'lecturer_name': offering.lecturer.user.get_full_name() if offering.lecturer else "TBA",
                'available_slots': offering.capacity - offering.enrolled_count,
                'is_registration_open': True,
                'prerequisites': [] 
            })

        return Response(results)


class RegistrationViewSet(viewsets.ModelViewSet):
    """
    Handles Course Registration with Payment Bypass.
    """
    serializer_class = CourseRegistrationSerializer
    permission_classes = [IsAuthenticated, IsStudent]

    def get_queryset(self):
        if hasattr(self.request.user, 'student_profile'):
            return CourseRegistration.objects.filter(student=self.request.user.student_profile)
        return CourseRegistration.objects.none()

    @action(detail=False, methods=['get'])
    def registration_status(self, request):
        """Check eligibility."""
        if not hasattr(request.user, 'student_profile'):
            return Response({'error': 'Student profile not found'}, status=400)

        student = request.user.student_profile
        current_semester = Semester.objects.filter(is_current=True).first()
        
        registered_count = 0
        total_credits = 0

        if current_semester:
            regs = CourseRegistration.objects.filter(
                student=student,
                course_offering__semester=current_semester,
                status='registered'
            ).select_related('course_offering__course')
            
            registered_count = regs.count()
            total_credits = sum(r.course_offering.course.credits for r in regs)

        # --- FEE CHECK LOGIC ---
        has_paid_fees = False
        invoice = Invoice.objects.filter(
            student=student,
            session=current_semester.session,
            semester=current_semester.semester
        ).first()
        
        if invoice and invoice.status == 'paid':
            has_paid_fees = True

        return Response({
            'can_register': has_paid_fees, # Depends on fees
            'has_paid_fees': has_paid_fees,    
            'current_semester': {
                'session': current_semester.session if current_semester else "N/A",
                'semester': current_semester.semester if current_semester else "N/A",
                'registration_deadline': timezone.now().date() + timezone.timedelta(days=30),
                'is_registration_active': True
            },
            'registration_status': {
                'registered_courses': registered_count,
                'total_credits': total_credits,
                'max_courses': 12
            }
        })

    @action(detail=False, methods=['post'])
    def register_courses(self, request):
        """Submit Registration (No Transaction Lock)."""
        student = request.user.student_profile
        offering_ids = request.data.get('course_offering_ids', [])
        
        current_semester = Semester.objects.filter(is_current=True).first()
        
        # --- STRICT PAYMENT CHECK ---
        invoice = Invoice.objects.filter(
            student=student,
            session=current_semester.session,
            semester=current_semester.semester
        ).first()
        
        if not invoice or invoice.status != 'paid':
             return Response(
                {'error': 'Tuition fees must be paid before registration.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Ensure ids are unique integers
        offering_ids = list(set([int(x) for x in offering_ids]))
        
        successful = []
        errors = []

        for off_id in offering_ids:
            try:
                # Simple get
                offering = CourseOffering.objects.get(id=off_id)
                
                # Double check if already registered
                if CourseRegistration.objects.filter(student=student, course_offering=offering).exists():
                    # Check if it was dropped, if so, re-activate
                    existing = CourseRegistration.objects.filter(student=student, course_offering=offering).first()
                    if existing.status == 'dropped':
                         existing.status = 'registered'
                         existing.save()
                         successful.append(existing.id)
                    else:
                         errors.append(f"{offering.course.code}: Already registered")
                    continue

                # Create Registration
                # NOTE: We construct it first, then save, to catch model validation errors
                reg = CourseRegistration(
                    student=student,
                    course_offering=offering,
                    status='registered',
                    is_payment_verified=True, # Verified because we checked Invoice above
                    approved_date=timezone.now()
                )
                
                # Force save logic
                reg.save()
                
                # Update Count
                offering.enrolled_count = F('enrolled_count') + 1
                offering.save()
                
                successful.append(reg.id)

            except CourseOffering.DoesNotExist:
                errors.append(f"ID {off_id}: Course not found")
            except Exception as e:
                # Add this print statement to see the error in your terminal
                print(f"❌ REGISTRATION ERROR for {off_id}: {str(e)}") 
                errors.append(f"Course ID {off_id}: {str(e)}")
                continue

        return Response({
            'message': 'Registration processed', 
            'successful': successful,
            'errors': errors
        })

    @action(detail=True, methods=['post'])
    def drop_course(self, request, pk=None):
        try:
            reg = CourseRegistration.objects.get(id=pk, student=request.user.student_profile)
            offering = reg.course_offering
            
            # Decrease count
            if offering.enrolled_count > 0:
                offering.enrolled_count = F('enrolled_count') - 1
                offering.save()
            
            # Hard delete for cleaner UI flow in demo
            reg.delete() 
            
            return Response({'message': 'Dropped successfully'})
        except Exception as e:
            return Response({'error': str(e)}, status=404)