import random
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model
from academics.models import (
    Department, Course, Semester, CourseOffering, 
    CourseRegistration, Grade, Enrollment
)
from users.models import Student, Lecturer, HOD, StaffProfile

User = get_user_model()

class Command(BaseCommand):
    help = 'Populates the DB with a full school structure: 3 Depts, All Roles, Data Flow'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("⚠️  WIPING OLD DATA..."))
        # Wipe in reverse order of dependencies
        Grade.objects.all().delete()
        CourseRegistration.objects.all().delete()
        Enrollment.objects.all().delete()
        CourseOffering.objects.all().delete()
        Course.objects.all().delete()
        HOD.objects.all().delete()
        Lecturer.objects.all().delete()
        Student.objects.all().delete()
        StaffProfile.objects.all().delete()
        Department.objects.all().delete()
        Semester.objects.all().delete()
        User.objects.all().delete() # Clean slate for users
        
        self.stdout.write(self.style.SUCCESS("✅ Data Wiped. Starting Fresh Setup..."))

        # ==========================================
        # 1. SETUP ACADEMIC SESSION
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

        # ==========================================
        # 2. SETUP DEPARTMENTS
        # ==========================================
        depts_data = [
            {'name': 'Computer Science', 'code': 'CSC'},
            {'name': 'Microbiology', 'code': 'MCB'},
            {'name': 'Accounting', 'code': 'ACC'},
        ]
        
        depts = {}
        for d in depts_data:
            dept = Department.objects.create(name=d['name'], code=d['code'])
            depts[d['code']] = dept
            self.stdout.write(f"🏢 Created Department: {d['name']}")

        # ==========================================
        # 3. SETUP ADMIN STAFF (Non-Academic)
        # ==========================================
        self.create_staff_user("registrar@school.edu", "Main", "Registrar", "registrar", "REG001")
        self.create_staff_user("bursar@school.edu", "Chief", "Bursar", "bursar", "BUR001")
        self.create_staff_user("ict@school.edu", "Head", "ICT", "ict", "ICT001")

        # ==========================================
        # 4. SETUP ACADEMIC STAFF & STUDENTS (Per Dept)
        # ==========================================
        
        # --- COMPUTER SCIENCE (CSC) ---
        # HOD
        hod_csc = self.create_hod("hod.csc@school.edu", "Dr.", "HOD-CSC", depts['CSC'])
        
        # Lecturers
        lec_csc1 = self.create_lecturer("dr.python@school.edu", "Dr.", "Python", depts['CSC'], "Senior Lecturer")
        lec_csc2 = self.create_lecturer("mr.java@school.edu", "Mr.", "Java", depts['CSC'], "Lecturer I")
        
        # Courses
        c_csc101 = self.create_course("CSC101", "Intro to Python", 3, depts['CSC'], "100", semester, lec_csc1)
        c_csc102 = self.create_course("CSC102", "Digital Logic", 2, depts['CSC'], "100", semester, lec_csc2)
        c_csc201 = self.create_course("CSC201", "Data Structures", 4, depts['CSC'], "200", semester, lec_csc1)

        # Students
        s_csc1 = self.create_student("std.csc1@school.edu", "John", "Doe", depts['CSC'], "100", "CSC/24/001")
        s_csc2 = self.create_student("std.csc2@school.edu", "Jane", "Tech", depts['CSC'], "200", "CSC/23/045")

        # Register & Grade
        self.register_and_grade(s_csc1, c_csc101, semester, 30, 60, True) # Published A
        self.register_and_grade(s_csc1, c_csc102, semester, 20, 40, False) # Draft B
        self.register_and_grade(s_csc2, c_csc201, semester, 25, 50, True) # Published A

        # --- MICROBIOLOGY (MCB) ---
        # HOD
        hod_mcb = self.create_hod("hod.mcb@school.edu", "Prof.", "HOD-MCB", depts['MCB'])
        
        # Lecturer
        lec_mcb1 = self.create_lecturer("dr.germ@school.edu", "Dr.", "Germ", depts['MCB'], "Professor")
        
        # Course
        c_mcb101 = self.create_course("MCB101", "Intro to Microbes", 3, depts['MCB'], "100", semester, lec_mcb1)
        
        # Student
        s_mcb1 = self.create_student("std.mcb1@school.edu", "Alice", "Bio", depts['MCB'], "100", "MCB/24/009")
        
        # Register
        self.register_and_grade(s_mcb1, c_mcb101, semester, 15, 30, True) # Published D

        # --- ACCOUNTING (ACC) ---
        # HOD
        hod_acc = self.create_hod("hod.acc@school.edu", "Dr.", "HOD-ACC", depts['ACC'])
        
        # Lecturer
        lec_acc1 = self.create_lecturer("mrs.money@school.edu", "Mrs.", "Money", depts['ACC'], "Lecturer II")
        
        # Course
        c_acc101 = self.create_course("ACC101", "Principles of Accounts", 3, depts['ACC'], "100", semester, lec_acc1)
        
        # Student
        s_acc1 = self.create_student("std.acc1@school.edu", "Bob", "Cash", depts['ACC'], "100", "ACC/24/088")
        
        # Register (No Grade yet)
        self.register_student_only(s_acc1, c_acc101, semester)

        # ==========================================
        # 5. OUTPUT TABLE
        # ==========================================
        self.stdout.write("\n" + "="*80)
        self.stdout.write(f"{'ROLE':<15} | {'EMAIL (Login)':<30} | {'PASSWORD':<10} | {'DETAILS'}")
        self.stdout.write("="*80)
        
        # Admin
        self.print_row("Registrar", "registrar@school.edu", "Admin Staff")
        self.print_row("Bursar", "bursar@school.edu", "Finance")
        self.print_row("ICT Officer", "ict@school.edu", "Tech Support")
        self.stdout.write("-" * 80)
        
        # CSC
        self.print_row("HOD (CSC)", "hod.csc@school.edu", "Dept Head")
        self.print_row("Lecturer", "dr.python@school.edu", "CSC101, CSC201")
        self.print_row("Lecturer", "mr.java@school.edu", "CSC102")
        self.print_row("Student", "std.csc1@school.edu", "100L (Has Results)")
        self.print_row("Student", "std.csc2@school.edu", "200L (Has Results)")
        self.stdout.write("-" * 80)
        
        # MCB
        self.print_row("HOD (MCB)", "hod.mcb@school.edu", "Dept Head")
        self.print_row("Lecturer", "dr.germ@school.edu", "MCB101")
        self.print_row("Student", "std.mcb1@school.edu", "100L")
        self.stdout.write("-" * 80)
        
        # ACC
        self.print_row("Lecturer", "mrs.money@school.edu", "ACC101")
        self.print_row("Student", "std.acc1@school.edu", "100L (No Score)")
        
        self.stdout.write("="*80)
        self.stdout.write(self.style.SUCCESS("🎉 SYSTEM READY FOR TESTING!"))

    # --- HELPER FUNCTIONS ---

    def print_row(self, role, email, details):
        self.stdout.write(f"{role:<15} | {email:<30} | password123 | {details}")

    def create_base_user(self, email, first, last, role):
        user = User.objects.create_user(
            username=email.split('@')[0],
            email=email,
            password='password123',
            first_name=first,
            last_name=last,
            role=role,
            phone='+2348000000000'
        )
        return user

    def create_staff_user(self, email, first, last, role, staff_id):
        user = self.create_base_user(email, first, last, role)
        StaffProfile.objects.create(
            user=user,
            staff_id=staff_id,
            position=role.title(),
            department="Administration"
        )

    def create_hod(self, email, first, last, dept):
        user = self.create_base_user(email, first, last, 'hod')
        HOD.objects.create(user=user, department=dept, staff_id=f"HOD-{dept.code}")
        # Also create Lecturer profile if HOD teaches
        Lecturer.objects.create(user=user, department=dept, staff_id=f"LEC-{dept.code}-HOD", designation="Professor", is_hod=True)
        return user

    def create_lecturer(self, email, first, last, dept, rank):
        user = self.create_base_user(email, first, last, 'lecturer')
        lec = Lecturer.objects.create(
            user=user, 
            department=dept, 
            staff_id=f"LEC-{dept.code}-{random.randint(100,999)}", 
            designation=rank
        )
        return lec

    def create_student(self, email, first, last, dept, level, matric):
        user = self.create_base_user(email, first, last, 'student')
        student = Student.objects.create(
            user=user, department=dept, level=level, 
            matric_number=matric, admission_date=timezone.now().date()
        )
        return student

    def create_course(self, code, title, credits, dept, level, semester, lecturer):
        course = Course.objects.create(
            code=code, title=title, credits=credits, department=dept,
            level=level, semester="first", lecturer=lecturer
        )
        CourseOffering.objects.create(
            course=course, semester=semester, capacity=100, 
            is_active=True, lecturer=lecturer, enrolled_count=0
        )
        return course

    def register_student_only(self, student, course, semester):
        offering = CourseOffering.objects.get(course=course, semester=semester)
        CourseRegistration.objects.create(
            student=student, course_offering=offering,
            status='registered', is_payment_verified=True, approved_date=timezone.now()
        )
        offering.enrolled_count += 1
        offering.save()
        return offering

    def register_and_grade(self, student, course, semester, ca, exam, publish):
        offering = self.register_student_only(student, course, semester)
        
        # Create Enrollment (Required for Grade)
        enrollment = Enrollment.objects.create(
            student=student, course=course, session=semester.session, 
            semester=semester.semester, status='enrolled'
        )
        
        total = ca + exam
        letter = 'F'
        if total >= 70: letter = 'A'
        elif total >= 60: letter = 'B'
        elif total >= 50: letter = 'C'
        elif total >= 45: letter = 'D'
        
        Grade.objects.create(
            student=student, course=course, enrollment=enrollment,
            ca_score=ca, exam_score=exam, score=total,
            grade_letter=letter, grade_points=4.0, # Simplified points
            semester=semester.semester, session=semester.session,
            uploaded_by=offering.lecturer, is_published=publish
        )