from rest_framework import serializers
from .models import Application, AdmissionLetter, AdmissionSession

class ApplicationSerializer(serializers.ModelSerializer):
    """Application serializer"""
    full_name = serializers.CharField(read_only=True)
    first_choice_department_name = serializers.CharField(
        source='first_choice_department.name', 
        read_only=True
    )
    second_choice_department_name = serializers.CharField(
        source='second_choice_department.name', 
        read_only=True
    )
    reviewed_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Application
        fields = [
            'id', 'application_number', 'session', 'programme_type',
            'first_choice_department', 'first_choice_department_name',
            'second_choice_department', 'second_choice_department_name',
            'first_name', 'last_name', 'other_names', 'full_name',
            'email', 'phone', 'date_of_birth', 'gender', 'nationality',
            'state_of_origin', 'lga', 'address',
            'guardian_name', 'guardian_phone', 'guardian_email', 'guardian_relationship',
            'olevel_results', 'jamb_score', 'previous_institution',
            'status', 'reviewed_by', 'reviewed_by_name', 'review_date', 'review_remarks',
            'passport_photo', 'birth_certificate', 'olevel_certificate',
            'submitted_date', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'application_number', 'submitted_date', 'created_at', 'updated_at']
    
    def get_reviewed_by_name(self, obj):
        return obj.reviewed_by.get_full_name() if obj.reviewed_by else None


class ApplicationCreateSerializer(serializers.ModelSerializer):
    """Application creation serializer"""
    
    class Meta:
        model = Application
        fields = [
            'session', 'programme_type', 'first_choice_department', 'second_choice_department',
            'first_name', 'last_name', 'other_names', 'email', 'phone',
            'date_of_birth', 'gender', 'nationality', 'state_of_origin', 'lga', 'address',
            'guardian_name', 'guardian_phone', 'guardian_email', 'guardian_relationship',
            'olevel_results', 'jamb_score', 'previous_institution',
            'passport_photo', 'birth_certificate', 'olevel_certificate'
        ]


class ApplicationStatusUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating application status"""
    
    class Meta:
        model = Application
        fields = ['status', 'review_remarks']


class AdmissionLetterSerializer(serializers.ModelSerializer):
    """Admission letter serializer"""
    applicant_name = serializers.CharField(source='application.full_name', read_only=True)
    applicant_email = serializers.CharField(source='application.email', read_only=True)
    department_name = serializers.CharField(source='department.name', read_only=True)
    issued_by_name = serializers.SerializerMethodField()
    
    class Meta:
        model = AdmissionLetter
        fields = [
            'id', 'application', 'applicant_name', 'applicant_email',
            'admission_number', 'matric_number', 'department', 'department_name',
            'level', 'session', 'letter_content', 'issued_date',
            'issued_by', 'issued_by_name', 'is_downloaded', 'download_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'issued_date', 'created_at', 'updated_at']
    
    def get_issued_by_name(self, obj):
        return obj.issued_by.get_full_name() if obj.issued_by else None


class AdmissionSessionSerializer(serializers.ModelSerializer):
    """Admission session serializer"""
    total_applications = serializers.SerializerMethodField()
    applications_admitted = serializers.SerializerMethodField()
    
    class Meta:
        model = AdmissionSession
        fields = [
            'id', 'session', 'start_date', 'end_date', 'application_fee',
            'is_active', 'max_applications', 'total_applications',
            'applications_admitted', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_total_applications(self, obj):
        return Application.objects.filter(session=obj.session).count()
    
    def get_applications_admitted(self, obj):
        return Application.objects.filter(session=obj.session, status='admitted').count()