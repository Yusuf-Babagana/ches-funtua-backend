from django.contrib.auth import get_user_model
from django.db import transaction
from .models import Student, Lecturer, HOD, StaffProfile
import secrets
import string

User = get_user_model()

class ICTService:
    @staticmethod
    def generate_password():
        """Generates a secure 8-char temporary password"""
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for i in range(8))

    @staticmethod
    @transaction.atomic
    def create_user(data, creator_role):
        """
        Central Logic for creating ANY user.
        Enforces: Role, Department, and Profile creation.
        """
        # Security Check: Only ICT or Super Admin can create
        if creator_role not in ['ict', 'super_admin']:
            raise PermissionError("Only ICT Officers can create users.")

        email = data['email']
        role = data['role']
        dept = data.get('department') # Department Object
        
        # 1. Create Base User
        temp_password = ICTService.generate_password()
        user = User.objects.create_user(
            username=email.split('@')[0], # Generate username from email
            email=email,
            password=temp_password,
            first_name=data['first_name'],
            last_name=data['last_name'],
            role=role,
            department=dept if role != 'student' else None # Students link via profile
        )

        # 2. Create Specific Profile based on Role
        if role == 'student':
            Student.objects.create(
                user=user,
                matric_number=data['matric_number'],
                department=dept,
                level=data['level'],
                admission_date=data['admission_date']
            )
        
        elif role == 'lecturer':
            Lecturer.objects.create(
                user=user,
                staff_id=data['staff_id'],
                department=dept,
                designation="Lecturer"
            )
            
        elif role == 'hod':
            HOD.objects.create(
                user=user,
                staff_id=data['staff_id'],
                department=dept
            )
            
        # For non-academic staff (Bursar, Registrar, etc.)
        elif role in ['registrar', 'bursar', 'ict', 'exam_officer']:
            StaffProfile.objects.create(
                user=user,
                staff_id=data['staff_id'],
                department=dept.name if dept else "Administration",
                position=role.title()
            )

        return user, temp_password