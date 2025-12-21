from rest_framework import serializers
from .models import (
    Department, 
    Course, 
    Enrollment, 
    Grade, 
    Attendance, 
    Semester, 
    CourseOffering, 
    CourseRegistration, # ✅ Renamed from Registration
    StudentAcademicRecord
)

class DepartmentSerializer(serializers.ModelSerializer):
    """Department serializer with dynamic counts"""
    hod_name = serializers.SerializerMethodField()
    student_count = serializers.IntegerField(read_only=True)
    lecturer_count = serializers.IntegerField(read_only=True)
    course_count = serializers.IntegerField(read_only=True)
    
    class Meta:
        model = Department
        fields = [
            'id', 'name', 'code', 'description', 'hod', 'hod_name',
            'student_count', 'lecturer_count', 'course_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_hod_name(self, obj):
        return obj.hod.user.get_full_name() if obj.hod else None


class CourseSerializer(serializers.ModelSerializer):
    """Course serializer"""
    department_name = serializers.CharField(source='department.name', read_only=True)
    lecturer_name = serializers.SerializerMethodField()
    enrolled_students = serializers.SerializerMethodField()
    
    class Meta:
        model = Course
        fields = [
            'id', 'code', 'title', 'description', 'credits', 
            'department', 'department_name', 'semester', 'level',
            'lecturer', 'lecturer_name', 'is_elective', 'prerequisites',
            'enrolled_students', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_lecturer_name(self, obj):
        return obj.lecturer.user.get_full_name() if obj.lecturer else None
    
    def get_enrolled_students(self, obj):
        # Using the related name from Enrollment model
        return obj.enrollments.filter(status='enrolled').count()


class CourseDetailSerializer(CourseSerializer):
    """Extended course serializer with lecturer details"""
    lecturer_details = serializers.SerializerMethodField()
    department_details = serializers.SerializerMethodField()
    
    class Meta(CourseSerializer.Meta):
        fields = CourseSerializer.Meta.fields + ['lecturer_details', 'department_details']
    
    def get_lecturer_details(self, obj):
        if obj.lecturer:
            return {
                'id': obj.lecturer.id,
                'name': obj.lecturer.user.get_full_name(),
                'staff_id': obj.lecturer.staff_id,
                'designation': obj.lecturer.designation
            }
        return None
    
    def get_department_details(self, obj):
        return {
            'id': obj.department.id,
            'name': obj.department.name,
            'code': obj.department.code
        }


class CourseOfferingSerializer(serializers.ModelSerializer):
    """Course offering serializer"""
    course_code = serializers.CharField(source='course.code', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_credits = serializers.IntegerField(source='course.credits', read_only=True)
    lecturer_name = serializers.SerializerMethodField()
    department_name = serializers.CharField(source='course.department.name', read_only=True)
    available_slots = serializers.SerializerMethodField()
    is_registration_open = serializers.SerializerMethodField()
    
    class Meta:
        model = CourseOffering
        fields = [
            'id', 'course', 'course_code', 'course_title', 'course_credits',
            'semester', 'lecturer', 'lecturer_name', 'department_name',
            'capacity', 'enrolled_count', 'available_slots', 'is_active',
            'is_registration_open', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_lecturer_name(self, obj):
        return obj.lecturer.user.get_full_name() if obj.lecturer else "Not Assigned"
    
    def get_available_slots(self, obj):
        return max(0, obj.capacity - obj.enrolled_count)
    
    def get_is_registration_open(self, obj):
        return (
            obj.is_active and 
            obj.semester.is_registration_active and
            obj.semester.is_current
        )


# ✅ RENAMED FROM RegistrationSerializer
class CourseRegistrationSerializer(serializers.ModelSerializer):
    """Course Registration serializer"""
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    matric_number = serializers.CharField(source='student.matric_number', read_only=True)
    course_code = serializers.CharField(source='course_offering.course.code', read_only=True)
    course_title = serializers.CharField(source='course_offering.course.title', read_only=True)
    course_credits = serializers.IntegerField(source='course_offering.course.credits', read_only=True)
    semester_info = serializers.CharField(source='course_offering.semester', read_only=True)
    lecturer_name = serializers.CharField(source='course_offering.lecturer.user.get_full_name', read_only=True)
    
    # Approval Details
    payment_verified_by_name = serializers.CharField(source='payment_verified_by.get_full_name', read_only=True)
    approved_by_lecturer_name = serializers.CharField(source='approved_by_lecturer.user.get_full_name', read_only=True)
    approved_by_exam_officer_name = serializers.CharField(source='approved_by_exam_officer.get_full_name', read_only=True)

    class Meta:
        model = CourseRegistration # ✅ Updated Model
        fields = [
            'id', 'student', 'student_name', 'matric_number',
            'course_offering', 'course_code', 'course_title', 'course_credits',
            'semester_info', 'lecturer_name', 'registration_date', 'status',
            'is_payment_verified', 'payment_verified_by_name',
            'approved_by_lecturer_name', 'approved_by_exam_officer_name',
            'rejection_reason',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'registration_date', 'created_at', 'updated_at', 'is_payment_verified', 'status']


class EnrollmentSerializer(serializers.ModelSerializer):
    """Enrollment serializer"""
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    matric_number = serializers.CharField(source='student.matric_number', read_only=True)
    course_code = serializers.CharField(source='course.code', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_credits = serializers.IntegerField(source='course.credits', read_only=True)
    
    class Meta:
        model = Enrollment
        fields = [
            'id', 'student', 'student_name', 'matric_number',
            'course', 'course_code', 'course_title', 'course_credits',
            'session', 'semester', 'status', 'enrollment_date',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'enrollment_date', 'created_at', 'updated_at']


class GradeSerializer(serializers.ModelSerializer):
    """Grade serializer with 4.0 GPA scale"""
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    matric_number = serializers.CharField(source='student.matric_number', read_only=True)
    course_code = serializers.CharField(source='course.code', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    course_credits = serializers.IntegerField(source='course.credits', read_only=True)
    uploaded_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Grade
        fields = [
            'id', 'student', 'student_name', 'matric_number',
            'course', 'course_code', 'course_title', 'course_credits',
            'enrollment', 'score', 'grade_letter', 'grade_points', 'semester', 'session',
            'uploaded_by', 'uploaded_by_name', 'remarks',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'grade_letter', 'grade_points', 'created_at', 'updated_at']
    
    def get_uploaded_by_name(self, obj):
        return obj.uploaded_by.user.get_full_name() if obj.uploaded_by else None


class StudentAcademicRecordSerializer(serializers.ModelSerializer):
    """Student academic record serializer"""
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    matric_number = serializers.CharField(source='student.matric_number', read_only=True)
    department_name = serializers.CharField(source='student.department.name', read_only=True)
    
    class Meta:
        model = StudentAcademicRecord
        fields = [
            'id', 'student', 'student_name', 'matric_number', 'department_name',
            'level', 'session', 'semester', 'total_credits', 'total_grade_points',
            'gpa', 'cgpa', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AttendanceSerializer(serializers.ModelSerializer):
    """Attendance serializer"""
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    matric_number = serializers.CharField(source='student.matric_number', read_only=True)
    course_code = serializers.CharField(source='course.code', read_only=True)
    course_title = serializers.CharField(source='course.title', read_only=True)
    marked_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Attendance
        fields = [
            'id', 'student', 'student_name', 'matric_number',
            'course', 'course_code', 'course_title', 'date', 'status',
            'marked_by', 'marked_by_name', 'remarks',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_marked_by_name(self, obj):
        return obj.marked_by.user.get_full_name() if obj.marked_by else None


class SemesterSerializer(serializers.ModelSerializer):
    """Semester serializer"""
    is_registration_active = serializers.BooleanField(read_only=True)
    
    class Meta:
        model = Semester
        fields = [
            'id', 'session', 'semester', 'start_date', 'end_date',
            'is_current', 'is_registration_active', 'registration_deadline', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class StudentTranscriptSerializer(serializers.Serializer):
    """Serializer for student transcript"""
    student = serializers.CharField(source='student.matric_number')
    student_name = serializers.CharField(source='student.user.get_full_name')
    level = serializers.CharField(source='student.level')
    department = serializers.CharField(source='student.department.name')
    grades = GradeSerializer(many=True, source='student.grades')
    gpa = serializers.DecimalField(max_digits=4, decimal_places=2)
    cgpa = serializers.DecimalField(max_digits=4, decimal_places=2)


class RegistrationRequestSerializer(serializers.Serializer):
    """Serializer for registration requests"""
    course_offering_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        max_length=6  # Maximum courses per semester
    )
    
    def validate_course_offering_ids(self, value):
        # Check if courses exist and are active
        course_offerings = CourseOffering.objects.filter(
            id__in=value,
            is_active=True
        )
        if len(course_offerings) != len(value):
            raise serializers.ValidationError("One or more courses are not available")
        return value


class StudentRegistrationStatusSerializer(serializers.Serializer):
    """Student registration status serializer"""
    has_paid_fees = serializers.BooleanField()
    current_semester = serializers.CharField()
    registration_deadline = serializers.DateField()
    is_registration_active = serializers.BooleanField()
    registered_courses = serializers.IntegerField()
    max_courses = serializers.IntegerField(default=6)
    can_register = serializers.BooleanField()
    total_credits_registered = serializers.IntegerField(default=0)


class CourseRegistrationSummarySerializer(serializers.Serializer):
    """Course registration summary for student dashboard"""
    total_courses_available = serializers.IntegerField()
    courses_registered = serializers.IntegerField()
    max_courses_allowed = serializers.IntegerField()
    registration_deadline = serializers.DateField()
    has_paid_fees = serializers.BooleanField()
    can_register = serializers.BooleanField()
    current_semester = serializers.CharField()


# ✅ COMPREHENSIVE SERIALIZER FOR GATEKEEPER FLOW
class RegistrationEligibilitySerializer(serializers.Serializer):
    can_register = serializers.BooleanField()
    has_paid_fees = serializers.BooleanField()
    is_registration_active = serializers.BooleanField()
    registration_deadline = serializers.DateTimeField(allow_null=True)
    current_semester = serializers.CharField()
    reason = serializers.CharField()
    registered_courses = serializers.IntegerField()
    max_courses = serializers.IntegerField()
    total_credits_registered = serializers.IntegerField()