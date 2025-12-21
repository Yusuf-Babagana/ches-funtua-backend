from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from .models import User, Student, Lecturer, StaffProfile
from academics.models import Department


class UserSerializer(serializers.ModelSerializer):
    """User serializer"""
    full_name = serializers.CharField(source='get_full_name', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name', 
            'full_name', 'role', 'phone', 'profile_picture', 
            'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class UserCreateSerializer(serializers.ModelSerializer):
    """User creation serializer"""
    password = serializers.CharField(write_only=True, min_length=8, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, min_length=8)
    
    class Meta:
        model = User
        fields = [
            'email', 'username', 'password', 'password_confirm',
            'first_name', 'last_name', 'role', 'phone'
        ]
    
    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match"})
        return data
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class StudentCreateSerializer(serializers.ModelSerializer):
    """Student creation with user data"""
    user_data = UserCreateSerializer(write_only=True)
    
    class Meta:
        model = Student
        fields = [
            'user_data', 'matric_number', 'level', 'department', 'status', 
            'admission_date', 'date_of_birth', 'address', 'guardian_name', 'guardian_phone'
        ]
    
    def create(self, validated_data):
        user_data = validated_data.pop('user_data')
        user_data['role'] = 'student'  # Force student role
        user_serializer = UserCreateSerializer(data=user_data)
        user_serializer.is_valid(raise_exception=True)
        user = user_serializer.save()
        
        student = Student.objects.create(user=user, **validated_data)
        return student

# Add this to your users/serializers.py

class UserUpdateSerializer(serializers.ModelSerializer):
    """User update serializer (excludes password)"""
    
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'first_name', 'last_name', 
            'role', 'phone', 'profile_picture', 'is_active'
        ]
        read_only_fields = ['id', 'email']  # Don't allow email changes

class UserPasswordResetSerializer(serializers.Serializer):
    """Password reset serializer"""
    new_password = serializers.CharField(write_only=True, min_length=8, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True, min_length=8)
    
    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match"})
        return data

class LecturerCreateSerializer(serializers.ModelSerializer):
    """Lecturer creation with user data"""
    user_data = UserCreateSerializer(write_only=True)
    
    class Meta:
        model = Lecturer
        fields = [
            'user_data', 'staff_id', 'department', 'designation', 'specialization',
            'qualifications', 'office_location', 'consultation_hours', 'is_hod'
        ]
    
    def create(self, validated_data):
        user_data = validated_data.pop('user_data')
        user_data['role'] = 'lecturer'  # Force lecturer role
        user_serializer = UserCreateSerializer(data=user_data)
        user_serializer.is_valid(raise_exception=True)
        user = user_serializer.save()
        
        lecturer = Lecturer.objects.create(user=user, **validated_data)
        return lecturer


class StaffProfileCreateSerializer(serializers.ModelSerializer):
    """Staff profile creation with user data"""
    user_data = UserCreateSerializer(write_only=True)
    
    class Meta:
        model = StaffProfile
        fields = [
            'user_data', 'staff_id', 'department', 'position', 'office_location'
        ]
    
    def create(self, validated_data):
        user_data = validated_data.pop('user_data')
        # Staff role can be any of the staff roles, so we don't force it here
        user_serializer = UserCreateSerializer(data=user_data)
        user_serializer.is_valid(raise_exception=True)
        user = user_serializer.save()
        
        staff_profile = StaffProfile.objects.create(user=user, **validated_data)
        return staff_profile


class StudentSerializer(serializers.ModelSerializer):
    """Student profile serializer"""
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source='user',
        write_only=True,
        required=False
    )
    department_name = serializers.CharField(source='department.name', read_only=True)
    
    class Meta:
        model = Student
        fields = [
            'id', 'user', 'user_id', 'matric_number', 'level', 
            'department', 'department_name', 'status', 'admission_date',
            'date_of_birth', 'address', 'guardian_name', 'guardian_phone',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class LecturerSerializer(serializers.ModelSerializer):
    """Lecturer profile serializer"""
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source='user',
        write_only=True,
        required=False
    )
    department_name = serializers.CharField(source='department.name', read_only=True)
    
    class Meta:
        model = Lecturer
        fields = [
            'id', 'user', 'user_id', 'staff_id', 'department', 
            'department_name', 'designation', 'specialization',
            'qualifications', 'office_location', 'consultation_hours',
            'is_hod', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class StaffProfileSerializer(serializers.ModelSerializer):
    """Staff profile serializer"""
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source='user',
        write_only=True,
        required=False
    )
    
    class Meta:
        model = StaffProfile
        fields = [
            'id', 'user', 'user_id', 'staff_id', 'department',
            'position', 'office_location', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class LoginSerializer(serializers.Serializer):
    """Login serializer"""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    
    def validate(self, data):
        email = data.get('email')
        password = data.get('password')
        
        if email and password:
            user = authenticate(username=email, password=password)
            if user:
                if not user.is_active:
                    raise serializers.ValidationError("User account is disabled")
                data['user'] = user
            else:
                raise serializers.ValidationError("Invalid email or password")
        else:
            raise serializers.ValidationError("Must include email and password")
        
        return data


class HODUserCreateSerializer(serializers.ModelSerializer):
    """User creation serializer specifically for HOD registration"""
    password = serializers.CharField(write_only=True, min_length=8, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True, min_length=8)
    
    class Meta:
        model = User
        fields = [
            'email', 'username', 'password', 'password_confirm',
            'first_name', 'last_name', 'phone'
        ]
        # Note: role is NOT included here - it will be set by HODCreateSerializer
    
    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match"})
        return data
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        
        # Set role to lecturer initially (will be updated to hod)
        validated_data['role'] = 'lecturer'
        
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


# Update HODCreateSerializer to use HODUserCreateSerializer
class HODCreateSerializer(serializers.ModelSerializer):
    """HOD creation with department assignment"""
    user_data = HODUserCreateSerializer(write_only=True)  # Use custom serializer
    department_id = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.all(),
        source='department',
        write_only=True
    )
    
    class Meta:
        model = Lecturer
        fields = [
            'user_data', 'staff_id', 'department_id', 'designation',
            'specialization', 'qualifications', 'office_location',
            'consultation_hours'
        ]
    
    def create(self, validated_data):
        user_data = validated_data.pop('user_data')
        department = validated_data.pop('department')
        
        # Create user with HODUserCreateSerializer
        user_serializer = HODUserCreateSerializer(data=user_data)
        user_serializer.is_valid(raise_exception=True)
        user = user_serializer.save()  # This creates user with 'lecturer' role
        
        # Create lecturer profile
        lecturer = Lecturer.objects.create(
            user=user, 
            department=department, 
            **validated_data
        )
        
        # Assign as HOD to the department
        department.hod = lecturer
        department.save()
        
        # Update lecturer's is_hod status
        lecturer.is_hod = True
        lecturer.save()
        
        # Update user role to 'hod'
        user.role = 'hod'
        user.save()
        
        return lecturer


class StaffRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for registering staff members.
    Handles the User creation part, while the View handles Profile creation.
    """
    password = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    password_confirm = serializers.CharField(write_only=True, required=True, style={'input_type': 'password'})
    
    # Extra fields that are not on User model but needed for Profile
    staff_id = serializers.CharField(required=False, allow_blank=True)
    position = serializers.CharField(required=False, allow_blank=True)
    department = serializers.CharField(required=False, allow_blank=True) # Just to accept it in payload

    class Meta:
        model = User
        fields = [
            'email', 'username', 'first_name', 'last_name', 'phone', 
            'role', 'password', 'password_confirm',
            'staff_id', 'position', 'department'
        ]
        extra_kwargs = {
            'role': {'required': True}
        }

    def validate(self, attrs):
        if attrs.get('password') != attrs.get('password_confirm'):
            raise serializers.ValidationError({"password": "Passwords do not match."})
        return attrs

    def create(self, validated_data):
        # Remove fields that belong to the profile, not the user
        validated_data.pop('password_confirm')
        
        # Pop these if they exist, as they are not fields on the User model
        # (The view accesses them via request.data, so we don't need them here for User creation)
        for field in ['staff_id', 'position', 'department']:
            if field in validated_data:
                validated_data.pop(field)
        
        # Create the user instance
        user = User.objects.create_user(**validated_data)
        return user


class HODCreateSerializer(serializers.ModelSerializer):
    """
    Serializer specifically for creating an HOD.
    Creates User + Lecturer Profile + Assigns Department.
    """
    # Nested user data
    user_data = serializers.DictField(write_only=True)
    department_id = serializers.IntegerField(write_only=True)
    staff_id = serializers.CharField(required=True)
    designation = serializers.ChoiceField(choices=Lecturer.DESIGNATION_CHOICES)
    
    class Meta:
        model = Lecturer
        fields = ['user_data', 'department_id', 'staff_id', 'designation', 'is_hod']

    def create(self, validated_data):
        user_data = validated_data.pop('user_data')
        department_id = validated_data.pop('department_id')
        
        # 1. Create User
        password = user_data.pop('password')
        user_data.pop('password_confirm', None)
        user = User.objects.create_user(**user_data, password=password)
        
        # 2. Get Department
        try:
            department = Department.objects.get(id=department_id)
        except Department.DoesNotExist:
            user.delete()
            raise serializers.ValidationError("Department not found")

        # 3. Create Lecturer Profile
        lecturer = Lecturer.objects.create(
            user=user,
            department=department,
            is_hod=True,  # Force HOD status
            **validated_data
        )
        
        # 4. Update Department HOD link
        department.hod = lecturer
        department.save()
        
        return lecturer


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for password change by authenticated user.
    """
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True, validators=[validate_password])
    confirm_password = serializers.CharField(required=True)

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({"confirm_password": "New passwords do not match."})
        return data

        