from django.core.management.base import BaseCommand
from django.utils import timezone
from academics.models import Course, CourseOffering, CourseRegistration, Semester
from users.models import Student, Lecturer

class Command(BaseCommand):
    help = 'Force enrolls students into lecturer courses for testing'

    def handle(self, *args, **kwargs):
        self.stdout.write("🔧 Force Enrolling Students...")

        # 1. Get the Lecturer (Dr. Smith)
        try:
            lecturer = Lecturer.objects.get(user__email='dr.smith@college.edu')
        except Lecturer.DoesNotExist:
            self.stdout.write(self.style.ERROR("❌ Lecturer Dr. Smith not found. Run 'repair_data' first."))
            return

        # 2. Get the Courses assigned to this Lecturer
        courses = Course.objects.filter(lecturer=lecturer)
        if not courses.exists():
             self.stdout.write(self.style.ERROR("❌ No courses found for Dr. Smith."))
             return

        # 3. Get Active Students
        students = Student.objects.all()
        if not students.exists():
            self.stdout.write(self.style.ERROR("❌ No students found."))
            return

        # 4. Get or Create Semester
        semester = Semester.objects.filter(is_current=True).first()
        if not semester:
            semester = Semester.objects.last()

        count = 0
        for course in courses:
            # Ensure Offering Exists
            offering, _ = CourseOffering.objects.get_or_create(
                course=course,
                semester=semester,
                defaults={'capacity': 100, 'is_active': True, 'lecturer': lecturer}
            )

            # Register Every Student
            for student in students:
                # Check if already exists to avoid error
                if not CourseRegistration.objects.filter(student=student, course_offering=offering).exists():
                    CourseRegistration.objects.create(
                        student=student,
                        course_offering=offering,
                        status='registered', # Force Registered
                        is_payment_verified=True,
                        approved_date=timezone.now()
                    )
                    count += 1
                    self.stdout.write(f"   -> Enrolled {student.user.get_full_name()} in {course.code}")

        self.stdout.write(self.style.SUCCESS(f"\n✅ Successfully enrolled {count} students into {courses.count()} courses."))
        self.stdout.write("👉 Refresh your Gradebook page now.")