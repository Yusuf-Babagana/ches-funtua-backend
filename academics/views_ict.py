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
    records). Fixes vs. the original: (1) this had NO permission class at
    all -- any authenticated user, including a student, could POST a CSV
    and overwrite grades; now ICT/super-admin only. (2) it used to set
    status='published' directly, force-publishing unreviewed grades
    straight to students and completely bypassing the standard draft ->
    submitted -> hod_approved -> verified -> published workflow
    (academics/views_result_workflow.py). It now imports as 'draft' so
    imported grades go through the same HOD/Exam-Officer/Registrar review
    as any lecturer-entered grade -- see college_cms_migration_inventory.md
    S3.9 and S6 item 15 for the original finding. (3) the semester-detection
    logic assumed every course-code column header contains a space (e.g.
    "CHE 101") and did `course_code.split()[1]` -- Course.code is actually
    stored without a space throughout this project (e.g. "CHE101"), so any
    real header crashed the whole request with an uncaught IndexError
    (500), found while writing Phase 12's permanent regression suite.
    Replaced with a plain digit extraction that works either way. (4) the
    score parser used `str(score_val).isdigit()`, which is False for any
    decimal score ("75.5") since "." isn't a digit -- silently zeroing out
    real scores; replaced with a real float parse. Both (3) and (4) match
    the equivalent fixes already made in portal/services_ict.py's
    import_results_csv() so the two implementations don't drift apart.
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
                            score = float(score_val)
                            if pd.isna(score):
                                score = 0
                        except (TypeError, ValueError):
                            score = 0

                        if score == 0: continue

                        course_code = re.search(r'([A-Z]{3}\s?\d{3})', col).group(1)
                        try:
                            course = Course.objects.get(code=course_code)
                            # Determine semester from code (even/odd middle digit)
                            digits = re.sub(r'\D', '', course_code)
                            semester = "first" if int(digits[1]) % 2 != 0 else "second"
                            
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
