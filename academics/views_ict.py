# academics/views_ict.py
import pandas as pd
import re
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.utils import timezone
from users.models import Student
from users.permissions import IsICTOfficer
from academics.models import Course, Grade, Enrollment

class ResultUploadView(APIView):
    """
    Bulk CSV result import for ICT (e.g. catching up historical/paper
    records). Two fixes vs. the original: (1) this had NO permission
    class at all -- any authenticated user, including a student, could
    POST a CSV and overwrite grades; now ICT/super-admin only. (2) it
    used to set status='published' directly, force-publishing unreviewed
    grades straight to students and completely bypassing the standard
    draft -> submitted -> hod_approved -> verified -> published workflow
    (academics/views_result_workflow.py). It now imports as 'draft' so
    imported grades go through the same HOD/Exam-Officer/Registrar review
    as any lecturer-entered grade -- see college_cms_migration_inventory.md
    S3.9 and S6 item 15 for the original finding.
    """
    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated, IsICTOfficer]

    def post(self, request):
        file = request.FILES.get('file')
        session = request.data.get('session', '2025/2026')
        
        # 1. Pre-load students for matching (Bag of Words)
        students = Student.objects.select_related('user').all()
        student_lookup = {
            frozenset(f"{s.user.first_name} {s.user.last_name}".strip().upper().split()): s 
            for s in students
        }

        try:
            df = pd.read_csv(file)
            # Find the Name column and Course columns
            name_col = next((c for c in df.columns if 'NAME' in c.upper()), None)
            course_cols = [c for c in df.columns if re.search(r'[A-Z]{3}\s?\d{3}', c)]

            if not name_col:
                return Response({"error": "No 'Name' column found in file"}, status=400)

            results = {"processed": 0, "skipped": [], "errors": []}

            with transaction.atomic():
                for _, row in df.iterrows():
                    raw_name = str(row[name_col]).strip().upper()
                    name_words = frozenset(raw_name.split())
                    
                    student = student_lookup.get(name_words)
                    if not student:
                        results["skipped"].append(raw_name)
                        continue

                    for col in course_cols:
                        score_val = row[col]
                        # Clean score
                        try:
                            score = float(score_val) if str(score_val).isdigit() else 0
                        except: score = 0
                        
                        if score == 0: continue

                        course_code = re.search(r'([A-Z]{3}\s?\d{3})', col).group(1)
                        try:
                            course = Course.objects.get(code=course_code)
                            # Determine semester from code (even/odd middle digit)
                            level_digit = course_code.split()[1][0]
                            semester = "first" if int(course_code.split()[1][1]) % 2 != 0 else "second"
                            
                            enrollment, _ = Enrollment.objects.get_or_create(
                                student=student, course=course, session=session, semester=semester,
                                defaults={'status': 'completed'}
                            )

                            Grade.objects.update_or_create(
                                student=student, course=course, session=session, semester=semester,
                                defaults={'enrollment': enrollment, 'score': score, 'status': 'draft'}
                            )
                        except Course.DoesNotExist:
                            results["errors"].append(f"Course {course_code} not found")

                    results["processed"] += 1

            return Response(results)
        except Exception as e:
            return Response({"error": str(e)}, status=500)
