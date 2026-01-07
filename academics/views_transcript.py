from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Sum, F
from django.utils import timezone

# ✅ Fixed: Import Student from users.models
from users.models import Student
from .models import Grade, Semester
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
            status='published' 
        ).select_related('course').order_by('session', 'semester', 'course__code')

        # Student Info Wrapper
        student_data = {
            "name": student.user.get_full_name(),
            "matric_number": student.matric_number,
            "department": student.department.name if student.department else "N/A",
            "level": student.level,
            "admission_year": student.admission_date.year if student.admission_date else "N/A",
            "generated_at": timezone.now().isoformat()
        }

        if not grades.exists():
            return {
                "student": student_data,
                "transcript": [],
                "summary": {
                    "cgpa": 0.0, 
                    "total_credits_earned": 0, 
                    "class_of_degree": "N/A"
                }
            }

        # 2. Group by Session -> Semester
        transcript_map = {}
        # Helper for sorting: First semester = 1, Second = 2
        sem_order = {'first': 1, 'second': 2}
        
        for grade in grades:
            # Create a unique key for grouping
            key = (grade.session, grade.semester)
            
            if key not in transcript_map:
                transcript_map[key] = {
                    "session": grade.session,
                    "semester": grade.semester,
                    # Store sort key internally
                    "_sort_order": sem_order.get(grade.semester.lower(), 3),
                    "courses": [],
                    # raw totals for calculation
                    "_total_points": 0.0,
                    "_total_units": 0
                }
            
            # Add Course Info
            transcript_map[key]["courses"].append({
                "code": grade.course.code,
                "title": grade.course.title,
                "unit": grade.course.credits,
                "score": float(grade.score),
                "grade": grade.grade_letter,
                "points": float(grade.grade_points)
            })

            # Aggregate
            points = float(grade.grade_points) * grade.course.credits
            transcript_map[key]["_total_points"] += points
            transcript_map[key]["_total_units"] += grade.course.credits

        # 3. Format Output List & Calculate Cumulative
        transcript_list = []
        cumulative_points = 0.0
        cumulative_units = 0

        # Sort by Session (String sort works for YYYY/YYYY) then Semester Order
        sorted_keys = sorted(transcript_map.keys(), key=lambda k: (k[0], transcript_map[k]["_sort_order"]))

        for key in sorted_keys:
            data = transcript_map[key]
            
            sem_units = data["_total_units"]
            sem_points = data["_total_points"]
            
            # Semester GPA
            sem_gpa = sem_points / sem_units if sem_units > 0 else 0.0
            
            # Update Cumulative
            cumulative_points += sem_points
            cumulative_units += sem_units

            # Format for frontend
            transcript_list.append({
                "session": data["session"],
                "semester": data["semester"].capitalize(),
                "courses": data["courses"],
                "semester_stats": {
                    "gpa": round(sem_gpa, 2),
                    "total_units": sem_units,
                    "total_points": round(sem_points, 2)
                }
            })

        # 4. Final Summary
        cgpa = cumulative_points / cumulative_units if cumulative_units > 0 else 0.0

        return {
            "student": student_data,
            "transcript": transcript_list,
            "summary": {
                "cgpa": round(cgpa, 2),
                "cumulative_gpa": round(cgpa, 2), 
                "total_credits_completed": cumulative_units,
                "total_credits_earned": cumulative_units, # For compatibility
                "total_points_earned": round(cumulative_points, 2),
                "class_of_degree": self._get_degree_class(cgpa),
                "degree_class": self._get_degree_class(cgpa) # For compatibility
            }
        }

    def _get_degree_class(self, cgpa):
        if cgpa >= 4.50: return "First Class"
        if cgpa >= 3.50: return "Second Class Upper"
        if cgpa >= 2.40: return "Second Class Lower"
        if cgpa >= 1.50: return "Third Class"
        return "Pass"

    @action(detail=False, methods=['get'])
    def my_transcript(self, request):
        """
        Endpoint for students to view their own transcript.
        URL: /api/academics/transcripts/my_transcript/
        """
        if not hasattr(request.user, 'student_profile'):
            return Response({"error": "Student profile not found"}, status=400)
        
        data = self._generate_transcript_data(request.user.student_profile)
        return Response(data)

    @action(detail=False, methods=['get'])
    def generate(self, request):
        """
        Endpoint for Admins (Registrar/HOD) to view any student's transcript.
        URL: /api/academics/transcripts/generate/?student_id=123
        """
        student_id = request.query_params.get('student_id')
        if not student_id:
            return Response({"error": "student_id is required"}, status=400)

        student = get_object_or_404(Student, id=student_id)
        
        # HOD Permission Check
        if request.user.role == 'hod' and hasattr(request.user, 'lecturer_profile'):
            hod_dept = request.user.lecturer_profile.department
            if student.department != hod_dept:
                return Response({"error": "You can only view transcripts for your department."}, status=403)

        data = self._generate_transcript_data(student)
        return Response(data)