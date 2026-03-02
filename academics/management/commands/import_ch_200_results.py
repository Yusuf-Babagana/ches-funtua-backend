from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from users.models import Student, User
from academics.models import Course, Grade, Enrollment

class Command(BaseCommand):
    help = 'Imports Community Health Level 200 Results (4th Semester)'

    def handle(self, *args, **options):
        # Session configuration for the 4th Semester
        session = "2025/2026"
        semester_type = "second"
        
        # Results data extracted from "CHE 1 result.xlsx - 4TH SEM..csv"
        # Format: ("Full Name", {"CourseCode": Score})
        results_data = [
            ("HAUWAU ABDULLAHI", {"CHE 221": 45, "CHE 222": 57, "CHE 223": 75, "CHE 224": 50, "CHE 225": 45, "CHE 226": 59, "CHE 227": 45, "CHE 228": 45, "CHE 229": 0}),
            ("BILKISU HASSAN", {"CHE 221": 64, "CHE 222": 63, "CHE 223": 80, "CHE 224": 50, "CHE 225": 50, "CHE 226": 70, "CHE 227": 48, "CHE 228": 45, "CHE 229": 0}),
            ("AMIRA BASHIR SHUAIBU", {"CHE 221": 45, "CHE 222": 69, "CHE 223": 75, "CHE 224": 45, "CHE 225": 53, "CHE 226": 70, "CHE 227": 46, "CHE 228": 45, "CHE 229": 0}),
            ("KHADIJA JAFAR", {"CHE 221": 55, "CHE 222": 50, "CHE 223": 75, "CHE 224": 45, "CHE 225": 50, "CHE 226": 75, "CHE 227": 47, "CHE 228": 45, "CHE 229": 0}),
            ("GADDAFI SADI", {"CHE 221": 45, "CHE 222": 50, "CHE 223": 64, "CHE 224": 45, "CHE 225": 62, "CHE 226": 57, "CHE 227": 45, "CHE 228": 45, "CHE 229": 0}),
            ("HAWAU MUSA", {"CHE 221": 45, "CHE 222": 58, "CHE 223": 70, "CHE 224": 46, "CHE 225": 61, "CHE 226": 50, "CHE 227": 45, "CHE 228": 47, "CHE 229": 0}),
            ("MUNZALI ABDULRAHAMAN", {"CHE 221": 53, "CHE 222": 71, "CHE 223": 85, "CHE 224": 45, "CHE 225": 55, "CHE 226": 72, "CHE 227": 45, "CHE 228": 46, "CHE 229": 0}),
            ("FADILA NANA SAGIR", {"CHE 221": 56, "CHE 222": 56, "CHE 223": 75, "CHE 224": 45, "CHE 225": 50, "CHE 226": 52, "CHE 227": 48, "CHE 228": 45, "CHE 229": 0}),
            ("RUWAIDA ABUBAKAR", {"CHE 221": 54, "CHE 222": 22, "CHE 223": 75, "CHE 224": 45, "CHE 225": 50, "CHE 226": 45, "CHE 227": 48, "CHE 228": 45, "CHE 229": 0}),
            ("NAFIU YUSUF", {"CHE 221": 61, "CHE 222": 50, "CHE 223": 75, "CHE 224": 42, "CHE 225": 50, "CHE 226": 70, "CHE 227": 45, "CHE 228": 45, "CHE 229": 0}),
            ("AMINA NURA", {"CHE 221": 45, "CHE 222": 56, "CHE 223": 65, "CHE 224": 19, "CHE 225": 52, "CHE 226": 65, "CHE 227": 48, "CHE 228": 45, "CHE 229": 0}),
            ("HASSAN MUKTAR", {"CHE 221": 56, "CHE 222": 54, "CHE 223": 80, "CHE 224": 58, "CHE 225": 64, "CHE 226": 45, "CHE 227": 46, "CHE 228": 50, "CHE 229": 0}),
            ("HAFSAT ABUBAKAR", {"CHE 221": 45, "CHE 222": 74, "CHE 223": 70, "CHE 224": 45, "CHE 225": 64, "CHE 226": 45, "CHE 227": 46, "CHE 228": 26, "CHE 229": 0}),
            ("MUBARAK GARBA", {"CHE 221": 64, "CHE 222": 45, "CHE 223": 80, "CHE 224": 59, "CHE 225": 64, "CHE 226": 72, "CHE 227": 50, "CHE 228": 51, "CHE 229": 0}),
            ("RUKAYYA MUSA BATURE", {"CHE 221": 45, "CHE 222": 61, "CHE 223": 65, "CHE 224": 50, "CHE 225": 52, "CHE 226": 24, "CHE 227": 45, "CHE 228": 50, "CHE 229": 0}),
            ("UMMULKHAIR SURAJ YUNUS", {"CHE 221": 51, "CHE 222": 50, "CHE 223": 85, "CHE 224": 50, "CHE 225": 55, "CHE 226": 60, "CHE 227": 46, "CHE 228": 45, "CHE 229": 0}),
            ("ZAINAB ABUBAKAR SALIHU", {"CHE 221": 51, "CHE 222": 81, "CHE 223": 75, "CHE 224": 45, "CHE 225": 53, "CHE 226": 50, "CHE 227": 47, "CHE 228": 45, "CHE 229": 0}),
            ("KABIR HASSAN MUHAMMAD", {"CHE 221": 70, "CHE 222": 45, "CHE 223": 75, "CHE 224": 50, "CHE 225": 52, "CHE 226": 85, "CHE 227": 50, "CHE 228": 63, "CHE 229": 0}),
            ("HALIMATU YUSUF", {"CHE 221": 51, "CHE 222": 53, "CHE 223": 65, "CHE 224": 47, "CHE 225": 45, "CHE 226": 62, "CHE 227": 45, "CHE 228": 45, "CHE 229": 0}),
            ("AISHA YUSUF", {"CHE 221": 51, "CHE 222": 45, "CHE 223": 65, "CHE 224": 50, "CHE 225": 52, "CHE 226": 61, "CHE 227": 45, "CHE 228": 45, "CHE 229": 0}),
            ("LAWIZA MUHAMMED", {"CHE 221": 65, "CHE 222": 53, "CHE 223": 75, "CHE 224": 45, "CHE 225": 56, "CHE 226": 74, "CHE 227": 45, "CHE 228": 45, "CHE 229": 0}),
            ("USAMATU BELLO", {"CHE 221": 86, "CHE 222": 52, "CHE 223": 80, "CHE 224": 57, "CHE 225": 61, "CHE 226": 78, "CHE 227": 46, "CHE 228": 45, "CHE 229": 0}),
            ("MARYAM LAWAL", {"CHE 221": 57, "CHE 222": 55, "CHE 223": 80, "CHE 224": 21, "CHE 225": 50, "CHE 226": 51, "CHE 227": 48, "CHE 228": 45, "CHE 229": 0}),
            ("test3 test3", {"CHE 221": 70, "CHE 222": 70, "CHE 223": 70, "CHE 224": 70, "CHE 225": 70, "CHE 226": 70, "CHE 227": 70, "CHE 228": 70, "CHE 229": 70}),
        ]

        self.stdout.write(self.style.SUCCESS(f"Importing CH Level 200 scores for {session}..."))

        with transaction.atomic():
            for name, scores in results_data:
                try:
                    name_parts = name.split()
                    user = User.objects.get(first_name__iexact=name_parts[0], last_name__iexact=' '.join(name_parts[1:]))
                    student = user.student_profile
                except (User.DoesNotExist, User.MultipleObjectsReturned):
                    self.stdout.write(self.style.WARNING(f"Skipping: '{name}' (Not found or duplicates)."))
                    continue

                for code, score in scores.items():
                    if score == "ABS" or score == "?": score = 0
                    try:
                        course = Course.objects.get(code=code)
                        # Enrollment verification
                        enrollment, _ = Enrollment.objects.get_or_create(
                            student=student, course=course, session=session, semester=semester_type,
                            defaults={'status': 'completed'}
                        )
                        # Grade Persistence
                        Grade.objects.update_or_create(
                            student=student, course=course, session=session, semester=semester_type,
                            defaults={'enrollment': enrollment, 'score': score, 'status': 'published', 'updated_at': timezone.now()}
                        )
                    except Course.DoesNotExist:
                        self.stdout.write(self.style.ERROR(f"Course '{code}' missing."))

        self.stdout.write(self.style.SUCCESS("Import completed."))