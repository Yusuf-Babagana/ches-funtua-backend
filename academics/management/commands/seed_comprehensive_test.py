import random
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from django.core.management import call_command

from academics.models import (
    Department, Course, Semester, CourseOffering, 
    CourseRegistration, Grade, Enrollment
)
from users.models import Student, Lecturer, StaffProfile

User = get_user_model()

class Command(BaseCommand):
    help = 'Generates a comprehensive test environment with 10 courses, 5 students, and varied workflow states.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Reset the database before seeding',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("🚀 Starting Comprehensive System Seed..."))
        
        reset_db = options['reset']
        
        if reset_db:
            self.stdout.write("🔄 Resetting database...")
            call_command('flush', '--no-input')
            
            # Create superuser
            self.stdout.write("👑 Creating superuser...")
            User.objects.create_superuser(
                username='admin',
                email='admin@example.com',
                password='admin123'
            )
            self.stdout.write("✅ Database reset complete")
        else:
            self.stdout.write("🧹 Cleaning up test data only...")
            self._cleanup_test_data()
        
        with transaction.atomic():
            # ==========================================
            # 1. SETUP ACADEMIC SESSION & DEPT
            # ==========================================
            semester = Semester.objects.create(
                session="2024/2025",
                semester="first",
                start_date=timezone.now().date(),
                end_date=timezone.now().date() + timedelta(days=120),
                registration_deadline=timezone.now().date() + timedelta(days=30),
                is_current=True,
                is_registration_active=True
            )

            # Get or create department
            dept, _ = Department.objects.get_or_create(
                code="SWE",
                defaults={'name': 'Software Engineering'}
            )
            
            self.stdout.write(f"✅ Session: {semester} | Dept: {dept}")

            # ==========================================
            # 2. CREATE STAFF (The Approvers)
            # ==========================================
            def create_staff(role, email, first, last, staff_id):
                # Create user
                u = User.objects.create(
                    username=email.split('@')[0],
                    email=email,
                    first_name=first,
                    last_name=last,
                    role=role,
                    is_active=True
                )
                u.set_password('password123')
                u.save()
                
                # Create profile based on role
                if role == 'hod':
                    lecturer = Lecturer.objects.create(
                        user=u,
                        staff_id=staff_id,
                        department=dept,
                        designation='professor',
                        is_hod=True
                    )
                    dept.hod = lecturer
                    dept.save()
                elif role == 'lecturer':
                    Lecturer.objects.create(
                        user=u,
                        staff_id=staff_id,
                        department=dept,
                        designation='senior_lecturer'
                    )
                else:
                    # Registrar, Exam Officer
                    StaffProfile.objects.create(
                        user=u,
                        staff_id=staff_id,
                        department='Registry',
                        position=role.title().replace('-', ' ')
                    )
                
                self.stdout.write(f"   Created {role}: {email}")
                return u

            self.stdout.write("👥 Creating staff users...")
            hod_user = create_staff('hod', 'hod@test.com', 'Dr. Sarah', 'Connor', 'HOD-001')
            eo_user = create_staff('exam-officer', 'eo@test.com', 'Mr. Mike', 'Ross', 'EO-001')
            reg_user = create_staff('registrar', 'reg@test.com', 'Ms. Jessica', 'Pearson', 'REG-001')

            # Create 5 Lecturers
            lecturers = []
            for i in range(1, 6):
                l_user = create_staff('lecturer', f'lec{i}@test.com', f'Lecturer', f'{i}', f'LEC-00{i}')
                lecturers.append(Lecturer.objects.get(user=l_user))

            # ==========================================
            # 3. CREATE STUDENTS
            # ==========================================
            self.stdout.write("🎓 Creating students...")
            students = []
            
            for i in range(1, 6):
                # Create student user
                s_user = User.objects.create(
                    username=f'std{i}',
                    email=f'student{i}@test.com',
                    first_name='Student',
                    last_name=f'{i}',
                    role='student',
                    is_active=True
                )
                s_user.set_password('password123')
                s_user.save()
                
                # Create student profile
                student = Student.objects.create(
                    user=s_user,
                    matric_number=f'SWE/24/00{i}',
                    level='100',
                    department=dept,
                    admission_date=timezone.now().date()
                )
                students.append(student)
                self.stdout.write(f"   Created student {i}: {s_user.email} (matric: {student.matric_number})")

            # ==========================================
            # 4. CREATE COURSES & SIMULATE WORKFLOW
            # ==========================================
            self.stdout.write("📚 Creating courses and simulating workflow...")
            
            workflow_states = [
                ('draft', 'Draft (Lecturer Only)'),       # Courses 1-2
                ('draft', 'Draft (Lecturer Only)'),
                ('submitted', 'Submitted (Waiting HOD)'), # Courses 3-4
                ('submitted', 'Submitted (Waiting HOD)'),
                ('hod_approved', 'Approved (Waiting EO)'),# Courses 5-6
                ('hod_approved', 'Approved (Waiting EO)'),
                ('verified', 'Verified (Waiting Reg)'),   # Courses 7-8
                ('verified', 'Verified (Waiting Reg)'),
                ('published', 'Published (Visible)'),     # Courses 9-10
                ('published', 'Published (Visible)'),
            ]

            for i, (status, desc) in enumerate(workflow_states, 1):
                # Assign to lecturers cyclically
                lecturer = lecturers[(i-1) % 5]
                
                # Create course
                course = Course.objects.create(
                    code=f"SWE{100+i}",
                    title=f"Software Engineering {i}",
                    credits=3,
                    department=dept,
                    level='100',
                    semester='first',
                    lecturer=lecturer
                )
                
                # Create course offering
                offering = CourseOffering.objects.create(
                    course=course,
                    semester=semester,
                    lecturer=lecturer,
                    capacity=50,
                    is_active=True,
                    enrolled_count=5  # All 5 students enrolled
                )
                
                self.stdout.write(f"  🔹 Course {course.code}: Status -> {status.upper()} ({desc})")

                # Register and Grade all 5 students
                for student in students:
                    # 1. Create CourseRegistration
                    CourseRegistration.objects.create(
                        student=student,
                        course_offering=offering,
                        status='registered',
                        is_payment_verified=True,
                        approved_date=timezone.now()
                    )
                    
                    # 2. Create Enrollment (Required for Grade)
                    # Note: The enrollment field might not be required in your Grade model
                    # If it is, we need to create it. If not, skip this.
                    try:
                        enrollment, created = Enrollment.objects.get_or_create(
                            student=student,
                            course=course,
                            session=semester.session,
                            semester=semester.semester,
                            defaults={'status': 'enrolled'}
                        )
                    except Exception as e:
                        self.stdout.write(f"     ⚠️ Enrollment creation skipped: {e}")
                        enrollment = None
                    
                    # 3. Create Grade - check what fields your Grade model actually has
                    ca = random.randint(20, 30)
                    exam = random.randint(40, 60)
                    total = ca + exam
                    
                    # Determine grade letter
                    if total >= 70:
                        letter = 'A'
                        points = 4.0
                    elif total >= 60:
                        letter = 'B'
                        points = 3.5
                    elif total >= 50:
                        letter = 'C'
                        points = 3.0
                    elif total >= 45:
                        letter = 'D'
                        points = 2.0
                    else:
                        letter = 'F'
                        points = 0.0
                    
                    # Create grade with available fields
                    grade_data = {
                        'student': student,
                        'course': course,
                        'session': semester.session,
                        'semester': semester.semester,
                        'ca_score': ca,
                        'exam_score': exam,
                        'score': total,
                        'grade_letter': letter,
                        'grade_points': points,
                        'uploaded_by': lecturer,
                        'status': status,
                        'remarks': 'Seeded data for testing'
                    }
                    
                    # Add enrollment only if it exists and is required
                    if enrollment:
                        grade_data['enrollment'] = enrollment
                    
                    Grade.objects.create(**grade_data)

        # ==========================================
        # 5. PRINT LOGIN TABLE
        # ==========================================
        self.stdout.write("\n" + "="*90)
        self.stdout.write(f"{'ROLE':<15} | {'EMAIL (Login)':<30} | {'PASSWORD':<12} | {'WHAT TO TEST'}")
        self.stdout.write("="*90)
        
        if reset_db:
            self.stdout.write(f"{'Admin':<15} | {'admin@example.com':<30} | {'admin123':<12} | {'Superuser access'}")
        
        self.stdout.write(f"{'Lecturer 1':<15} | {'lec1@test.com':<30} | {'password123':<12} | {'SWE101 (Draft), SWE106 (HOD Appr)'}")
        self.stdout.write(f"{'Lecturer 3':<15} | {'lec3@test.com':<30} | {'password123':<12} | {'SWE103 (Submitted)'}")
        self.stdout.write("-" * 90)
        self.stdout.write(f"{'HOD':<15} | {'hod@test.com':<30} | {'password123':<12} | {'Approve SWE103, SWE104 (Submitted)'}")
        self.stdout.write(f"{'Exam Officer':<15} | {'eo@test.com':<30}  | {'password123':<12} | {'Verify SWE105, SWE106 (Approved)'}")
        self.stdout.write(f"{'Registrar':<15} | {'reg@test.com':<30} | {'password123':<12} | {'Publish SWE107, SWE108 (Verified)'}")
        self.stdout.write("-" * 90)
        self.stdout.write(f"{'Student':<15} | {'student1@test.com':<30} | {'password123':<12} | {'Check Results (SWE109, SWE110 Visible)'}")
        self.stdout.write("="*90)
        
        # ==========================================
        # 6. SUMMARY STATISTICS
        # ==========================================
        self.stdout.write("\n" + "="*90)
        self.stdout.write("📊 SEEDING COMPLETED - SUMMARY")
        self.stdout.write("="*90)
        self.stdout.write(f"• Total Users: {User.objects.count()}")
        self.stdout.write(f"• Students: {Student.objects.count()}")
        self.stdout.write(f"• Lecturers: {Lecturer.objects.count()}")
        self.stdout.write(f"• Courses: {Course.objects.count()}")
        self.stdout.write(f"• Course Offerings: {CourseOffering.objects.count()}")
        self.stdout.write(f"• Course Registrations: {CourseRegistration.objects.count()}")
        self.stdout.write(f"• Enrollments: {Enrollment.objects.count()}")
        self.stdout.write(f"• Grades: {Grade.objects.count()}")
        self.stdout.write("="*90)
        self.stdout.write(self.style.SUCCESS("✅ Database seeding completed successfully!"))

    def _cleanup_test_data(self):
        """Clean up only test data"""
        with transaction.atomic():
            # Delete test users and related data
            test_emails = [
                'hod@test.com', 'eo@test.com', 'reg@test.com',
                'lec1@test.com', 'lec2@test.com', 'lec3@test.com', 'lec4@test.com', 'lec5@test.com',
                'student1@test.com', 'student2@test.com', 'student3@test.com', 'student4@test.com', 'student5@test.com'
            ]
            
            # Delete in reverse order to avoid foreign key constraints
            Grade.objects.filter(remarks='Seeded data for testing').delete()
            CourseRegistration.objects.filter(student__user__email__in=test_emails).delete()
            Enrollment.objects.filter(student__user__email__in=test_emails).delete()
            CourseOffering.objects.filter(course__code__startswith='SWE1').delete()
            Course.objects.filter(code__startswith='SWE1').delete()
            
            # Delete students
            Student.objects.filter(user__email__in=test_emails).delete()
            
            # Delete lecturers
            Lecturer.objects.filter(user__email__in=test_emails).delete()
            
            # Delete staff profiles
            StaffProfile.objects.filter(user__email__in=test_emails).delete()
            
            # Delete users
            User.objects.filter(email__in=test_emails).delete()
            
            # Delete semester
            Semester.objects.filter(session="2024/2025", semester="first").delete()