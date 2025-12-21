# academics/serializers_approval.py
from rest_framework import serializers
from .models import CourseRegistration  # ✅ Renamed from Registration
from users.models import User, Lecturer
from users.serializers import UserSerializer, LecturerSerializer

class RegistrationApprovalSerializer(serializers.ModelSerializer):
    """Serializer for registration approval"""
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    matric_number = serializers.CharField(source='student.matric_number', read_only=True)
    course_code = serializers.CharField(source='course_offering.course.code', read_only=True)
    course_title = serializers.CharField(source='course_offering.course.title', read_only=True)
    lecturer_name = serializers.CharField(source='course_offering.lecturer.user.get_full_name', read_only=True)
    department_name = serializers.CharField(source='course_offering.course.department.name', read_only=True)
    semester_info = serializers.CharField(source='course_offering.semester', read_only=True)
    payment_verified_by_name = serializers.SerializerMethodField()
    approved_by_lecturer_name = serializers.SerializerMethodField()
    approved_by_exam_officer_name = serializers.SerializerMethodField()
    
    class Meta:
        model = CourseRegistration  # ✅ Updated Model
        fields = [
            'id', 'student', 'student_name', 'matric_number',
            'course_offering', 'course_code', 'course_title',
            'lecturer_name', 'department_name', 'semester_info',
            'status', 'is_payment_verified', 'payment_verified_by',
            'payment_verified_by_name', 'payment_verified_date',
            'approved_by_lecturer', 'approved_by_lecturer_name',
            'approved_by_exam_officer', 'approved_by_exam_officer_name',
            'approved_date', 'rejection_reason', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'is_payment_verified',
            'payment_verified_by', 'payment_verified_date',
            'approved_by_lecturer', 'approved_by_exam_officer',
            'approved_date', 'rejection_reason'
        ]
    
    def get_payment_verified_by_name(self, obj):
        return obj.payment_verified_by.get_full_name() if obj.payment_verified_by else None
    
    def get_approved_by_lecturer_name(self, obj):
        return obj.approved_by_lecturer.user.get_full_name() if obj.approved_by_lecturer else None
    
    def get_approved_by_exam_officer_name(self, obj):
        return obj.approved_by_exam_officer.get_full_name() if obj.approved_by_exam_officer else None

class RegistrationApprovalActionSerializer(serializers.Serializer):
    """Serializer for registration approval actions"""
    action = serializers.ChoiceField(choices=['approve', 'reject'])
    reason = serializers.CharField(required=False, allow_blank=True)
    
    def validate(self, data):
        action = data.get('action')
        reason = data.get('reason', '')
        
        if action == 'reject' and not reason:
            raise serializers.ValidationError("Reason is required for rejection")
        
        return data

class RegistrationPaymentVerificationSerializer(serializers.Serializer):
    """Serializer for payment verification"""
    action = serializers.ChoiceField(choices=['verify', 'unverify'])