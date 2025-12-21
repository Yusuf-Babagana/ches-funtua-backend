from rest_framework import serializers
from .models import Grade, Course

class ResultWorkflowActionSerializer(serializers.Serializer):
    """
    Handles approval or rejection actions for results.
    """
    course_id = serializers.IntegerField(required=True)
    action = serializers.ChoiceField(choices=['approve', 'reject'])
    remark = serializers.CharField(required=False, allow_blank=True)

class CourseResultSummarySerializer(serializers.ModelSerializer):
    """
    Displays a high-level summary of a course's results for approvers.
    """
    # ✅ FIX: Explicitly expose course_id to match frontend expectation
    course_id = serializers.IntegerField(source='id', read_only=True)
    
    lecturer_name = serializers.CharField(source='lecturer.user.get_full_name', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    semester_display = serializers.CharField(source='get_semester_display', read_only=True)
    
    # Dynamic fields calculated in the view
    total_students = serializers.IntegerField(read_only=True)
    passed_count = serializers.IntegerField(read_only=True)
    failed_count = serializers.IntegerField(read_only=True)
    average_score = serializers.FloatField(read_only=True)
    status_summary = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = [
            'id', 'course_id', 'code', 'title', 'lecturer_name', 'department_name', 
            'level', 'semester', 'semester_display',
            'total_students', 'passed_count', 'failed_count', 
            'average_score', 'status_summary'
        ]

    def get_status_summary(self, obj):
        # Passed via context or annotation
        return self.context.get('status_summary', 'Pending')

class GradeWorkflowDetailSerializer(serializers.ModelSerializer):
    """
    Detailed view of a single grade for review.
    """
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    matric_number = serializers.CharField(source='student.matric_number', read_only=True)

    class Meta:
        model = Grade
        fields = [
            'id', 'student_name', 'matric_number', 
            'ca_score', 'exam_score', 'score', 
            'grade_letter', 'grade_points', 'status', 'remarks'
        ]