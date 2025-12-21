from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from academics.models import Department, Course, Semester, CourseOffering, CourseRegistration, Grade, Enrollment
from users.models import Student, Lecturer

User = get_user_model()

class Command(BaseCommand):
    help = 'Wipes academic data and rebuilds a perfect single-flow loop'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("⚠️ WIPING ACADEMIC DATA..."))

        # 1. DELETE EVERYTHING (To fix ID mismatches)
        CourseRegistration.objects.all().delete()
        Grade.objects.all().delete()
        Enrollment.objects.all().delete()
        CourseOffering.objects.all().delete()
        Course.objects.all().delete()
        Semester.objects.all().delete()
        # We keep Users/Departments to avoid breaking auth, but we reset their links
        
        self.stdout.write(self.style.SUCCESS("✅ Data Wiped."))

        # 2. CREATE ONE SEMESTER
        current_semester = Semester.objects.create(
            session="2024/2025",
            semester="first",
            start_date=timezone.now().date(),
            end_date=timezone.now().date() + timedelta(days=90),
            registration_deadline=timezone.now().date() + timedelta(days=30),
            is_current=True,
            is_registration_active=True
        )
        self.stdout.write(f"✅ Created Semester: {current_semester}")

        # 3. GET/CREATE DEPARTMENT
        dept, _ = Department.objects.get_or_create(name="Computer Science", code="CSC")

        # 4. SETUP LECTURER (Dr. Smith)
        # Ensure user exists
        lec_user, created = User.objects.get_or_create(
            email="dr.smith@college.edu",
            defaults={
                'username': 'dr_smith', 'first_name': 'Doctor', 'last_name': 'Smith', 
                'role': 'lecturer', 'is_active': True
            }
        )
        if created: lec_user.set_password('password123'); lec_user.save()
        
        lecturer, _ = Lecturer.objects.get_or_create(user=lec_user)
        lecturer.department = dept
        lecturer.save()
        self.stdout.write(f"✅ Setup Lecturer: {lec_user.email}")

        # 5. SETUP STUDENT (John Doe)
        std_user, created = User.objects.get_or_create(
            email="john.doe@college.edu",
            defaults={
                'username': 'john_doe', 'first_name': 'John', 'last_name': 'Doe', 
                'role': 'student', 'is_active': True
            }
        )
        if created: std_user.set_password('password123'); std_user.save()

        student, _ = Student.objects.get_or_create(user=std_user)
        student.department = dept
        student.level = "100"
        student.matric_number = "CSC/24/001"
        student.save()
        self.stdout.write(f"✅ Setup Student: {std_user.email}")

        # 6. CREATE COURSE & OFFERING
        course = Course.objects.create(
            code="CSC101",
            title="Introduction to Python",
            credits=3,
            department=dept,
            level="100",
            semester="first",
            lecturer=lecturer
        )
        
        offering = CourseOffering.objects.create(
            course=course,
            semester=current_semester,
            capacity=100,
            is_active=True,
            lecturer=lecturer
        )
        self.stdout.write(f"✅ Created Course & Offering: {course.code}")

        # 7. REGISTER STUDENT (The crucial link)
        CourseRegistration.objects.create(
            student=student,
            course_offering=offering,
            status='registered',
            is_payment_verified=True,
            approved_date=timezone.now()
        )
        
        # Update enrolled count
        offering.enrolled_count = 1
        offering.save()
        
        self.stdout.write(self.style.SUCCESS("✅ Registered John Doe for CSC101"))
        self.stdout.write(self.style.SUCCESS("------------------------------------------------"))
        self.stdout.write(self.style.SUCCESS(f"LOGIN AS LECTURER: {lec_user.email} / password123"))
        self.stdout.write(self.style.SUCCESS(f"THEN CLICK COURSE: {course.title}"))