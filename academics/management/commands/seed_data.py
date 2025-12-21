import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import get_user_model

# Import Models
from academics.models import Department, Course, Semester, CourseOffering
from users.models import Student, Lecturer, StaffProfile
from finance.models import FeeStructure, Invoice, Payment

User = get_user_model()

class Command(BaseCommand):
    help = 'Populate database with Health College test data'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING('🏥 Starting Health College Database Seed...'))
        
        # 1. Setup Session & Semester
        self.stdout.write('1. Setting up Academic Session (2024/2025)...')
        Semester.objects.all().update(is_current=False)
        
        current_semester, _ = Semester.objects.get_or_create(
            session='2024/2025',
            semester='first',
            defaults={
                'start_date': timezone.now().date(),
                'end_date': timezone.now().date() + timedelta(days=120),
                'registration_deadline': timezone.now().date() + timedelta(days=30),
                'is_current': True,
                'is_registration_active': True
            }
        )
        current_semester.is_current = True
        current_semester.is_registration_active = True
        current_semester.save()

        with transaction.atomic():
            # ==========================================
            # CLEANUP OLD DATA (Prevent Integrity Errors)
            # ==========================================
            usernames_to_wipe = [
                'hod_che', 'lecturer_ehs', 'student_fatima', 'student_musa',
                'bursar', 'registrar', 'exam_officer', 'ict', 'desk_officer', 'super_admin'
            ]
            User.objects.filter(username__in=usernames_to_wipe).delete()

            # ==========================================
            # 2. DEPARTMENTS
            # ==========================================
            self.stdout.write('2. Creating Health Departments...')
            
            dept_che, _ = Department.objects.get_or_create(
                code='CHE', defaults={'name': 'Community Health Extension', 'description': 'Public Health and Community Medicine'}
            )
            
            dept_ehs, _ = Department.objects.get_or_create(
                code='EHS', defaults={'name': 'Environmental Health Sciences', 'description': 'Hygiene, Sanitation and Environment'}
            )

            # ==========================================
            # 3. ACADEMIC STAFF (HOD & Lecturer)
            # ==========================================
            self.stdout.write('3. Creating Academic Staff...')
            
            # --- HOD: Community Health ---
            hod_user = User.objects.create_user(
                email='hod.che@college.edu', username='hod_che', password='password123',
                first_name='Dr. Amina', last_name='Yusuf', role='hod'
            )
            hod_profile = Lecturer.objects.create(
                user=hod_user, staff_id='CHE-HOD-01', department=dept_che,
                designation='principal_lecturer', is_hod=True, specialization='Epidemiology'
            )
            # Link HOD to Dept
            dept_che.hod = hod_profile
            dept_che.save()

            # --- Lecturer: Environmental Health ---
            lec_user = User.objects.create_user(
                email='lecturer.ehs@college.edu', username='lecturer_ehs', password='password123',
                first_name='Mr. John', last_name='Okafor', role='lecturer'
            )
            lecturer = Lecturer.objects.create(
                user=lec_user, staff_id='EHS-LEC-01', department=dept_ehs, 
                designation='senior_lecturer', specialization='Toxicology'
            )

            # ==========================================
            # 4. COURSES (Health Context)
            # ==========================================
            self.stdout.write('4. Creating Health Courses...')
            
            # (Code, Title, Units, Department, Lecturer)
            courses_list = [
                ('CHE101', 'Intro to Community Health', 3, dept_che, hod_profile),
                ('ANA101', 'Human Anatomy & Physiology', 3, dept_che, hod_profile),
                ('BIO101', 'General Biology', 2, dept_che, None),
                ('EHS101', 'Intro to Environmental Health', 2, dept_ehs, lecturer),
                ('EHS102', 'Food Hygiene & Safety', 2, dept_ehs, lecturer),
                ('GST101', 'Use of English', 2, dept_che, None),
            ]

            for code, title, unit, dept, assigned_lec in courses_list:
                course, _ = Course.objects.get_or_create(
                    code=code,
                    defaults={
                        'title': title, 'credits': unit, 'department': dept,
                        'level': '100', 'semester': 'first', 'lecturer': assigned_lec
                    }
                )
                
                # Open Course for Registration
                CourseOffering.objects.get_or_create(
                    course=course, semester=current_semester,
                    defaults={'lecturer': assigned_lec, 'capacity': 100, 'is_active': True}
                )

            # ==========================================
            # 5. STUDENTS
            # ==========================================
            self.stdout.write('5. Creating Students...')
            
            # --- Student 1: Fatima (Community Health) ---
            std1_user = User.objects.create_user(
                email='fatima@college.edu', username='student_fatima', password='password123',
                first_name='Fatima', last_name='Bello', role='student'
            )
            student1 = Student.objects.create(
                user=std1_user, matric_number='CHE/24/001', level='100',
                department=dept_che, status='active', admission_date=timezone.now().date()
            )

            # --- Student 2: Musa (Environmental Health) ---
            std2_user = User.objects.create_user(
                email='musa@college.edu', username='student_musa', password='password123',
                first_name='Musa', last_name='Kabiru', role='student'
            )
            student2 = Student.objects.create(
                user=std2_user, matric_number='EHS/24/005', level='100',
                department=dept_ehs, status='active', admission_date=timezone.now().date()
            )

            # ==========================================
            # 6. FINANCE (Marking Paid)
            # ==========================================
            self.stdout.write('6. Setting up Finance...')
            
            # Fee Structure
            fee_struct, _ = FeeStructure.objects.get_or_create(
                level='100', department=dept_che, session=current_semester.session, semester='first',
                defaults={'name': 'CHE Year 1 Tuition', 'tuition_fee': 120000}
            )

            # Mark Fatima as PAID (So you can test registration immediately)
            Invoice.objects.create(
                student=student1, 
                invoice_number=f'INV-PD-{student1.id}',
                amount=120000,
                amount_paid=120000, # ✅ Paid
                status='paid',     
                fee_structure=fee_struct,
                session=current_semester.session,
                semester='first',
                due_date=timezone.now().date() + timedelta(days=30),
                description='Tuition Fee 2024/2025'
            )

            # Mark Musa as PENDING (So you can test payment flow)
            Invoice.objects.create(
                student=student2, 
                invoice_number=f'INV-UP-{student2.id}',
                amount=115000,
                amount_paid=0,      # ❌ Not Paid
                status='pending',     
                session=current_semester.session,
                semester='first',
                due_date=timezone.now().date() + timedelta(days=30),
                description='Tuition Fee 2024/2025'
            )

            # ==========================================
            # 7. ADMIN STAFF
            # ==========================================
            self.stdout.write('7. Creating Admin Staff...')
            roles = ['bursar', 'registrar', 'exam-officer', 'ict', 'desk-officer', 'super-admin']
            
            for role in roles:
                email = f'{role}@college.edu'
                username = role.replace('-','_')
                
                u = User.objects.create_user(
                    email=email, username=username, password='password123',
                    first_name=role.capitalize().replace('-', ' '), last_name='Staff', role=role
                )
                StaffProfile.objects.create(
                    user=u, staff_id=f'{role[:3].upper()}001', 
                    department='Admin', position=role.capitalize()
                )

        self.stdout.write(self.style.SUCCESS('\n✅ HEALTH COLLEGE DATABASE READY!'))
        self.stdout.write(self.style.SUCCESS('====================================================='))
        self.stdout.write(f"🎓 Student 1 (PAID):   fatima@college.edu     | pass: password123")
        self.stdout.write(f"🎓 Student 2 (UNPAID): musa@college.edu       | pass: password123")
        self.stdout.write(f"👨‍🏫 Lecturer (EHS):    lecturer.ehs@college.edu | pass: password123")
        self.stdout.write(f"🏛️ HOD (CHE):         hod.che@college.edu    | pass: password123")
        self.stdout.write(f"💰 Bursar:             bursar@college.edu     | pass: password123")
        self.stdout.write(f"📜 Registrar:          registrar@college.edu  | pass: password123")
        self.stdout.write(f"📝 Exams:              exam-officer@college.edu | pass: password123")
        self.stdout.write(f"⚡ SuperAdmin:         super-admin@college.edu | pass: password123")
        self.stdout.write(self.style.SUCCESS('====================================================='))