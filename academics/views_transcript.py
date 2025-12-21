from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Sum, F
from django.utils import timezone

from .models import Grade, Student, Semester
# Ensure these permissions exist in your users/permissions.py
from users.permissions import IsStudent, IsRegistrar, IsHOD, IsSuperAdmin, IsAdminStaff

class TranscriptViewSet(viewsets.ViewSet):
    """
    Manages Student Transcripts (Academic History).
    """
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.action == 'my_transcript':
            return [IsAuthenticated(), IsStudent()]
        return [IsAuthenticated(), IsAdminStaff()]

    def _generate_transcript_data(self, student):
        """
        Internal method to build the transcript structure dynamically 
        from published grades.
        """
        # 1. Fetch all PUBLISHED grades for the student
        grades = Grade.objects.filter(
            student=student, 
            status='published' # Using status='published' based on previous context
        ).select_related('course').order_by('session', 'semester', 'course__code')

        if not grades.exists():
            return {
                "student_info": self._get_student_info(student),
                "academic_history": [],
                "summary": {"cumulative_gpa": 0.0, "total_credits": 0, "degree_class": "N/A"}
            }

        # 2. Group by Session -> Semester
        history = {}
        
        # Helper for Semester Ordering
        sem_order = {'first': 1, 'second': 2}
        
        for grade in grades:
            key = (grade.session, grade.semester)
            if key not in history:
                history[key] = {
                    "session": grade.session,
                    "semester": grade.semester,
                    "semester_order": sem_order.get(grade.semester.lower(), 3),
                    "courses": [],
                    "total_points": 0.0,
                    "total_credits": 0
                }
            
            # Add Course Info
            history[key]["courses"].append({
                "code": grade.course.code,
                "title": grade.course.title,
                "credit_unit": grade.course.credits,
                "score": grade.score,
                "grade": grade.grade_letter,
                "points": grade.grade_points
            })

            # Aggregate for GPA
            # Points for a course = Grade Point * Credit Unit
            points_earned = float(grade.grade_points) * grade.course.credits
            history[key]["total_points"] += points_earned
            history[key]["total_credits"] += grade.course.credits

        # 3. Calculate GPAs and Format Output
        sorted_history = []
        cumulative_points = 0.0
        cumulative_credits = 0

        # Sort by Session (String comparison usually works for YYYY/YYYY) then Semester
        sorted_keys = sorted(history.keys(), key=lambda x: (x[0], sem_order.get(x[1].lower(), 3)))

        for key in sorted_keys:
            data = history[key]
            
            # Semester GPA
            sem_gpa = 0.0
            if data["total_credits"] > 0:
                sem_gpa = data["total_points"] / data["total_credits"]
            
            # Update Cumulative Stats
            cumulative_points += data["total_points"]
            cumulative_credits += data["total_credits"]
            
            # Current CGPA
            curr_cgpa = 0.0
            if cumulative_credits > 0:
                curr_cgpa = cumulative_points / cumulative_credits

            sorted_history.append({
                "session": data["session"],
                "semester": data["semester"],
                "courses": data["courses"],
                "stats": {
                    "total_credits_registered": data["total_credits"],
                    "total_points_earned": round(data["total_points"], 2),
                    "gpa": round(sem_gpa, 2),
                    "cgpa": round(curr_cgpa, 2) # CGPA at the end of this semester
                }
            })

        # 4. Final Summary
        final_cgpa = 0.0
        if cumulative_credits > 0:
            final_cgpa = cumulative_points / cumulative_credits

        return {
            "student_info": self._get_student_info(student),
            "academic_history": sorted_history,
            "summary": {
                "cumulative_gpa": round(final_cgpa, 2),
                "total_credits_completed": cumulative_credits,
                "total_points_earned": round(cumulative_points, 2),
                "degree_class": self._get_degree_class(final_cgpa)
            }
        }

    def _get_student_info(self, student):
        return {
            "full_name": student.user.get_full_name(),
            "matric_number": student.matric_number,
            "department": student.department.name if student.department else "N/A",
            "level": student.level,
            "passport_url": student.user.profile_picture.url if student.user.profile_picture else None,
            "generated_at": timezone.now().isoformat()
        }

    def _get_degree_class(self, cgpa):
        if cgpa >= 4.50: return "First Class"
        elif cgpa >= 3.50: return "Second Class Upper"
        elif cgpa >= 2.40: return "Second Class Lower"
        elif cgpa >= 1.50: return "Third Class"
        else: return "Fail / Withdraw"

    @action(detail=False, methods=['get'])
    def my_transcript(self, request):
        """
        Endpoint for students to view their own transcript.
        """
        if not hasattr(request.user, 'student_profile'):
            return Response({"error": "Student profile not found"}, status=400)
        
        data = self._generate_transcript_data(request.user.student_profile)
        return Response(data)

    @action(detail=False, methods=['get'])
    def view_student_transcript(self, request):
        """
        Endpoint for Admins (Registrar/HOD) to view any student's transcript.
        """
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response({"error": "student_id is required"}, status=400)

        student = get_object_or_404(Student, id=student_id)
        
        # HOD Permission Check (Can only view own department)
        if request.user.role == 'hod' and hasattr(request.user, 'lecturer_profile'):
            hod_dept = request.user.lecturer_profile.department
            if student.department != hod_dept:
                return Response({"error": "You can only view transcripts for your department."}, status=403)

        data = self._generate_transcript_data(student)
        return Response(data)