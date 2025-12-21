from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from academics.models import Department, Course, Semester, CourseOffering, CourseRegistration
from users.models import Student, Lecturer

User = get_user_model()

class Command(BaseCommand):
    help = 'Sets up a fresh Lecturer/Student pair for Gradebook testing'

    def handle(self, *args, **kwargs):
        self.stdout.write("🧪 Setting up Test Data...")

        # 1. Ensure Department
        dept, _ = Department.objects.get_or_create(name="Testing Dept", code="TST")

        # 2. Ensure Active Semester
        semester = Semester.objects.filter(is_current=True).first()
        if not semester:
            semester = Semester.objects.create(
                session="2024/2025",
                semester="first",
                start_date=timezone.now().date(),
                end_date=timezone.now().date() + timedelta(days=90),
                registration_deadline=timezone.now().date() + timedelta(days=30),
                is_current=True,
                is_registration_active=True
            )

        # 3. Create Lecturer User
        email_lec = "dr.test@college.edu"
        user_lec, created = User.objects.get_or_create(
            email=email_lec,
            defaults={
                'username': 'dr_test', 'first_name': 'Doctor', 'last_name': 'Test', 
                'role': 'lecturer', 'is_active': True
            }
        )
        if created:
            user_lec.set_password('password123')
            user_lec.save()
        
        lecturer, _ = Lecturer.objects.get_or_create(
            user=user_lec, 
            defaults={'department': dept, 'staff_id': 'L-TEST'}
        )

        # 4. Create Student User
        email_std = "student.test@college.edu"
        user_std, created = User.objects.get_or_create(
            email=email_std,
            defaults={
                'username': 'student_test', 'first_name': 'Student', 'last_name': 'Test', 
                'role': 'student', 'is_active': True
            }
        )
        if created:
            user_std.set_password('password123')
            user_std.save()

        # ✅ FIX: Added admission_date here
        student, _ = Student.objects.get_or_create(
            user=user_std, 
            defaults={
                'department': dept, 
                'matric_number': 'TST/24/001', 
                'level': '100',
                'admission_date': timezone.now().date()  # <--- REQUIRED FIELD ADDED
            }
        )

        # 5. Create Course
        course, _ = Course.objects.get_or_create(
            code="TEST101",
            defaults={
                'title': "Testing Methodology",
                'credits': 3,
                'department': dept,
                'level': "100",
                'semester': "first",
                'lecturer': lecturer
            }
        )
        # Force assign lecturer
        course.lecturer = lecturer
        course.save()

        # 6. Create Offering (The bridge)
        offering, _ = CourseOffering.objects.get_or_create(
            course=course,
            semester=semester,
            defaults={'capacity': 50, 'is_active': True, 'lecturer': lecturer}
        )

        # 7. Register Student
        reg, created = CourseRegistration.objects.get_or_create(
            student=student,
            course_offering=offering,
            defaults={
                'status': 'registered',
                'is_payment_verified': True,
                'approved_date': timezone.now()
            }
        )

        self.stdout.write(self.style.SUCCESS("\n✅ TEST DATA CREATED SUCCESSFULLY!"))
        self.stdout.write("="*50)
        self.stdout.write(f" LEC👨‍🏫TURER LOGIN:")
        self.stdout.write(f"   Email:    {email_lec}")
        self.stdout.write(f"   Password: password123")
        self.stdout.write("-" * 50)
        self.stdout.write(f"🎓 STUDENT LOGIN:")
        self.stdout.write(f"   Email:    {email_std}")
        self.stdout.write(f"   Password: password123")
        self.stdout.write("="*50)
        