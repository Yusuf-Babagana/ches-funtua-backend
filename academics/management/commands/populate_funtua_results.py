import re
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from users.models import Student
from academics.models import Course, Grade, Enrollment

class Command(BaseCommand):
    help = 'Bulk imports results by cleaning course titles and matching student data'

    def handle(self, *args, **options):
        # 1. Pre-load students for fast case-insensitive lookup
        # Maps "FIRST LAST" -> Student Object
        student_map = {
            f"{s.user.first_name} {s.user.last_name}".strip().upper(): s 
            for s in Student.objects.select_related('user').all()
        }
        self.stdout.write(self.style.SUCCESS(f"Mapped {len(student_map)} students from system."))

        # 2. Results Data (Add your extracted CSV data here)
        # Format: (Student Name, {Course String: Score})
        results_to_process = [
            ("HAUWAU ABDULLAHI", {"CHE 221 - Clinical Skills": 45, "CHE 111 - Professional Ethics": 60}),
            ("BILKISU HASSAN", {"CHE 222 - Maternal Health": 63, "GNS 111 - Use of English I": 75}),
            ("test3 test3", {"CHE 221 - Clinical Skills": 70, "CHE 222 - Maternal Health": 70}),
            # Continue adding rows from your 10 semester files
        ]

        with transaction.atomic():
            for name, scores in results_to_process:
                lookup_name = name.strip().upper()
                
                if lookup_name not in student_map:
                    self.stdout.write(self.style.WARNING(f"Skipping '{name}': No matching student profile."))
                    continue

                student = student_map[lookup_name]

                for full_title, score in scores.items():
                    # ✅ EXTRACT CODE: Gets 'CHE 111' from 'CHE 111 - Professional Ethics'
                    match = re.search(r'([A-Z]{3}\s\d{3})', full_title)
                    if not match: continue
                    
                    course_code = match.group(1)
                    
                    try:
                        course = Course.objects.get(code=course_code)
                        clean_score = 0 if str(score).upper() in ["ABS", "?", ""] else float(score)

                        # Determine Session/Semester based on Course Code digit
                        # Example: CHE 1xx = 100L, CHE 2xx = 200L
                        level_digit = course_code.split()[1][0]
                        session = "2024/2025" if level_digit == "1" else "2025/2026"
                        semester = "first" if int(course_code.split()[1][1]) % 2 != 0 else "second"

                        # Create Enrollment
                        enrollment, _ = Enrollment.objects.get_or_create(
                            student=student, course=course, session=session, semester=semester,
                            defaults={'status': 'completed'}
                        )

                        # Create Published Grade
                        Grade.objects.update_or_create(
                            student=student, course=course, session=session, semester=semester,
                            defaults={
                                'enrollment': enrollment, 
                                'score': clean_score, 
                                'status': 'published', 
                                'updated_at': timezone.now()
                            }
                        )
                    except Course.DoesNotExist:
                        self.stdout.write(self.style.ERROR(f"Course {course_code} not in DB."))

        self.stdout.write(self.style.SUCCESS("✅ Population Complete."))
