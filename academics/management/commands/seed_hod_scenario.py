from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from django.db import transaction

from academics.models import Department, Course, Semester
from users.models import Lecturer

User = get_user_model()

class Command(BaseCommand):
    help = 'Seeds data specifically for testing HOD Course Allocation'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.WARNING("👨‍🏫 Seeding HOD Scenario..."))

        with transaction.atomic():
            # 1. Setup Session
            semester, _ = Semester.objects.get_or_create(
                session="2024/2025",
                semester="first",
                defaults={
                    'start_date': timezone.now().date(),
                    'end_date': timezone.now().date() + timedelta(days=120),
                    'registration_deadline': timezone.now().date() + timedelta(days=30),
                    'is_current': True,
                    'is_registration_active': True
                }
            )

            # 2. Department
            dept, _ = Department.objects.get_or_create(name="Computer Science", code="CSC")

            # 3. Create HOD User
            def create_staff(email, first, role, staff_id):
                u, _ = User.objects.get_or_create(
                    email=email,
                    defaults={'username': email.split('@')[0], 'first_name': first, 'last_name': 'Test', 'role': role, 'is_active': True}
                )
                u.set_password('password123')
                u.save()
                return u

            hod_user = create_staff('hod.csc@test.com', 'Dr. HOD', 'hod', 'HOD-CSC-01')
            hod_profile, _ = Lecturer.objects.get_or_create(
                user=hod_user,
                defaults={'staff_id': 'HOD-CSC-01', 'department': dept, 'designation': 'professor', 'is_hod': True}
            )
            dept.hod = hod_profile
            dept.save()

            # 4. Create 3 Lecturers
            lecturers = []
            for i in range(1, 4):
                u = create_staff(f'lec{i}.csc@test.com', f'Lecturer {i}', 'lecturer', f'LEC-CSC-0{i}')
                l, _ = Lecturer.objects.get_or_create(
                    user=u,
                    defaults={'staff_id': f'LEC-CSC-0{i}', 'department': dept, 'designation': 'senior_lecturer'}
                )
                lecturers.append(l)

            # 5. Create Courses (Some assigned, some unassigned)
            courses_data = [
                ("CSC101", "Intro to Computing", "100", None),
                ("CSC102", "Digital Logic", "100", None),
                ("CSC201", "Data Structures", "200", lecturers[0]), # Assigned to Lec 1
                ("CSC202", "Operating Systems", "200", None),
                ("CSC301", "Algorithms", "300", lecturers[1]),      # Assigned to Lec 2
                ("CSC302", "Software Engineering", "300", None),
                ("CSC401", "Compiler Construction", "400", None),
                ("CSC402", "Artificial Intelligence", "400", lecturers[2]), # Assigned to Lec 3
            ]

            for code, title, level, lec in courses_data:
                Course.objects.update_or_create(
                    code=code,
                    defaults={
                        'title': title, 'credits': 3, 'department': dept, 
                        'level': level, 'semester': 'first', 'lecturer': lec
                    }
                )

        self.stdout.write(self.style.SUCCESS("\n✅ HOD Scenario Ready!"))
        self.stdout.write(f"👉 Login as HOD: hod.csc@test.com / password123")
        self.stdout.write(f"👉 Go to: /dashboard/hod/courses")