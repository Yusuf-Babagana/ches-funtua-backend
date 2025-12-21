from rest_framework import permissions
from .models import Student, Lecturer
from academics.models import Course, Department



class IsStudent(permissions.BasePermission):
    """Permission for students"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'student'


class IsLecturer(permissions.BasePermission):
    """Permission for lecturers"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'lecturer'


class IsHOD(permissions.BasePermission):
    """Permission for HODs - checks both user role and lecturer is_hod flag"""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # Check user role
        if request.user.role != 'hod':
            return False
        
        # Check if user has lecturer profile and is marked as HOD
        if hasattr(request.user, 'lecturer_profile'):
            return request.user.lecturer_profile.is_hod
        
        return False
    
    def has_object_permission(self, request, view, obj):
        """Check if HOD has permission for specific object"""
        if not self.has_permission(request, view):
            return False
        
        # Get HOD's department
        hod_department = request.user.lecturer_profile.department
        
        # Check department-based permissions
        
        # For Student objects
        if isinstance(obj, Student):
            return obj.department == hod_department
        
        # For Lecturer objects
        if isinstance(obj, Lecturer):
            return obj.department == hod_department
        
        # For Course objects
        if isinstance(obj, Course):
            return obj.department == hod_department
        
        # For Department objects
        if isinstance(obj, Department):
            return obj == hod_department
        
        return True

class IsRegistrar(permissions.BasePermission):
    """Permission for registrar"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'registrar'


class IsBursar(permissions.BasePermission):
    """Permission for bursar"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'bursar'


class IsAdminStaff(permissions.BasePermission):
    """Permission for administrative staff"""
    admin_roles = ['registrar', 'bursar', 'desk-officer', 'ict', 'exam-officer', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.admin_roles


class IsSuperAdmin(permissions.BasePermission):
    """Permission for super admin only"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'super-admin'


class IsOwnerOrAdminStaff(permissions.BasePermission):
    """Permission for owner or admin staff"""
    admin_roles = ['registrar', 'bursar', 'desk-officer', 'ict', 'exam-officer', 'super-admin']
    
    def has_object_permission(self, request, view, obj):
        if request.user.role in self.admin_roles:
            return True
        # Check if user is the owner
        if hasattr(obj, 'user'):
            return obj.user == request.user
        if hasattr(obj, 'student') and hasattr(request.user, 'student_profile'):
            return obj.student == request.user.student_profile
        return False


class CanManageGrades(permissions.BasePermission):
    """Permission for managing grades"""
    allowed_roles = ['lecturer', 'hod', 'exam-officer', 'registrar', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles


class CanManageFinance(permissions.BasePermission):
    """Permission for managing finance"""
    allowed_roles = ['bursar', 'desk-officer', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles


class CanManageAdmissions(permissions.BasePermission):
    """Permission for managing admissions"""
    allowed_roles = ['registrar', 'desk-officer', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles


class CanManageUsers(permissions.BasePermission):
    """Permission for user management (Super Admin only for full CRUD)"""
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # Super admin has full access to user management
        if request.user.role == 'super-admin':
            return True
        
        # Other admin staff can only list/view users (no create/update/delete)
        admin_roles = ['registrar', 'hod', 'ict']
        if request.user.role in admin_roles:
            # Allow only safe methods (GET, HEAD, OPTIONS)
            if request.method in permissions.SAFE_METHODS:
                return True
        
        return False
    
    def has_object_permission(self, request, view, obj):
        """Object-level permission for user management"""
        if not request.user.is_authenticated:
            return False
        
        # Super admin can manage any user
        if request.user.role == 'super-admin':
            return True
        
        # Prevent users from modifying themselves through user management
        if obj == request.user:
            return False
        
        # Other admin staff can only view users
        admin_roles = ['registrar', 'hod', 'ict']
        if request.user.role in admin_roles and request.method in permissions.SAFE_METHODS:
            return True
        
        return False


# ==============================================
# ADD THESE MISSING PERMISSION CLASSES
# ==============================================

class IsExamOfficer(permissions.BasePermission):
    """Permission for exam officers"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'exam-officer'


import logging

logger = logging.getLogger(__name__)

class IsICTOfficer(permissions.BasePermission):
    """Permission for ICT officers with Debugging"""
    def has_permission(self, request, view):
        # 1. Check if user is authenticated at all
        if not request.user or not request.user.is_authenticated:
            # Check headers even if not authenticated
            auth_header = request.META.get('HTTP_AUTHORIZATION', 'No Authorization Header')
            logger.warning(f"⛔ Permission Denied: User is not authenticated. Headers: {auth_header}")
            return False
        
        # 2. Check Role (Allow ICT and Super Admin)
        if request.user.role in ['ict', 'super-admin']:
            return True
            
        # 3. Log failure reason
        logger.warning(f"⛔ Permission Denied: User '{request.user.email}' has role '{request.user.role}', expected 'ict' or 'super-admin'")
        return False


# users/permissions.py - ADD THESE PERMISSIONS

class IsDeskOfficer(permissions.BasePermission):
    """Check if user is a desk officer"""
    allowed_roles = ['desk-officer', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles


class CanOverrideRegistration(permissions.BasePermission):
    """Permission for overriding registration (Desk Officer + Registrar)"""
    allowed_roles = ['desk-officer', 'registrar', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles


class CanVerifyDocuments(permissions.BasePermission):
    """Permission for document verification"""
    allowed_roles = ['desk-officer', 'registrar', 'hod', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles


class CanHandleStudentQueries(permissions.BasePermission):
    """Permission for handling student queries"""
    allowed_roles = ['desk-officer', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles



class IsBursar(permissions.BasePermission):
    """Permission for bursar"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'bursar'


class IsRegistrar(permissions.BasePermission):
    """Permission for registrar"""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'registrar'


# ==============================================
# ENHANCED PERMISSION CLASSES
# ==============================================

class CanManageSystemConfig(permissions.BasePermission):
    """Permission for managing system configuration (ICT Officer + Super Admin)"""
    allowed_roles = ['ict', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles


class CanManageAdmissions(permissions.BasePermission):
    """Permission for managing admissions (Registrar + Desk Officer + Super Admin)"""
    allowed_roles = ['registrar', 'desk-officer', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles


class CanManageExaminations(permissions.BasePermission):
    """Permission for managing examinations (Exam Officer + HOD + Registrar + Super Admin)"""
    allowed_roles = ['exam-officer', 'hod', 'registrar', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles


class CanViewAcademicRecords(permissions.BasePermission):
    """Permission for viewing academic records (multiple roles)"""
    allowed_roles = [
        'student', 'lecturer', 'hod', 'exam-officer', 
        'registrar', 'desk-officer', 'super-admin'
    ]
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles


class CanGenerateReports(permissions.BasePermission):
    """Permission for generating reports (multiple roles)"""
    allowed_roles = [
        'hod', 'exam-officer', 'registrar', 'bursar', 
        'desk-officer', 'ict', 'super-admin'
    ]
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles


# ==============================================
# DEPARTMENT-SPECIFIC PERMISSIONS
# ==============================================

class IsHODOrDepartmentStaff(permissions.BasePermission):
    """Permission for HOD or staff in the same department"""
    
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        
        # Super admin has full access
        if request.user.role == 'super-admin':
            return True
        
        # Get user's department
        user_department = None
        if hasattr(request.user, 'lecturer_profile'):
            user_department = request.user.lecturer_profile.department
        elif hasattr(request.user, 'staff_profile'):
            user_department = request.user.staff_profile.department
        
        if not user_department:
            return False
        
        # Check if object has department and it matches user's department
        if isinstance(obj, Department):
            return obj == user_department
        elif hasattr(obj, 'department'):
            return obj.department == user_department
        elif hasattr(obj, 'student') and hasattr(obj.student, 'department'):
            return obj.student.department == user_department
        
        return False


# ==============================================
# STUDENT-SPECIFIC PERMISSIONS
# ==============================================

class IsStudentOwner(permissions.BasePermission):
    """Permission for student to access their own data"""
    
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        
        # Super admin and admin staff have access
        admin_roles = ['super-admin', 'registrar', 'hod', 'exam-officer']
        if request.user.role in admin_roles:
            return True
        
        # Students can only access their own data
        if request.user.role == 'student' and hasattr(request.user, 'student_profile'):
            if isinstance(obj, Student):
                return obj == request.user.student_profile
            elif hasattr(obj, 'student'):
                return obj.student == request.user.student_profile
            elif hasattr(obj, 'user'):
                return obj.user == request.user
        
        return False


# ==============================================
# LECTURER-SPECIFIC PERMISSIONS
# ==============================================

class IsLecturerForCourse(permissions.BasePermission):
    """Permission for lecturer assigned to a specific course"""
    
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        
        # Super admin and admin staff have access
        admin_roles = ['super-admin', 'hod', 'exam-officer']
        if request.user.role in admin_roles:
            return True
        
        # Check if user is a lecturer assigned to this course
        if request.user.role == 'lecturer' and hasattr(request.user, 'lecturer_profile'):
            lecturer = request.user.lecturer_profile
            
            if isinstance(obj, Course):
                return obj.lecturer == lecturer
            elif hasattr(obj, 'course'):
                return obj.course.lecturer == lecturer
            elif hasattr(obj, 'course_offering') and hasattr(obj.course_offering, 'course'):
                return obj.course_offering.course.lecturer == lecturer
        
        return False


# ==============================================
# BULK ACTION PERMISSIONS
# ==============================================

class CanPerformBulkActions(permissions.BasePermission):
    """Permission for performing bulk actions"""
    allowed_roles = [
        'super-admin', 'registrar', 'hod', 'exam-officer', 
        'bursar', 'ict', 'desk-officer'
    ]
    
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        # Check if action requires bulk permissions
        if view.action in ['bulk_create', 'bulk_update', 'bulk_delete']:
            return request.user.role in self.allowed_roles
        
        return True


# ==============================================
# AUDIT LOG PERMISSIONS
# ==============================================

class CanViewAuditLogs(permissions.BasePermission):
    """Permission for viewing audit logs"""
    allowed_roles = ['super-admin', 'ict', 'registrar']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles


# ==============================================
# FINANCIAL PERMISSIONS
# ==============================================

class CanApprovePayments(permissions.BasePermission):
    """Permission for approving payments"""
    allowed_roles = ['bursar', 'desk-officer', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles


class CanGenerateFinancialReports(permissions.BasePermission):
    """Permission for generating financial reports"""
    allowed_roles = ['bursar', 'registrar', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles


# ==============================================
# SYSTEM MAINTENANCE PERMISSIONS
# ==============================================

class CanPerformSystemMaintenance(permissions.BasePermission):
    """Permission for system maintenance tasks"""
    allowed_roles = ['ict', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles


# ==============================================
# USER MANAGEMENT PERMISSIONS
# ==============================================

class CanManageAllUsers(permissions.BasePermission):
    """Permission for managing all users (Super Admin + ICT)"""
    allowed_roles = ['super-admin', 'ict']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles
    
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        
        # ICT officers cannot modify super admin accounts
        if request.user.role == 'ict' and obj.role == 'super-admin':
            return False
        
        return request.user.role in self.allowed_roles


class CanResetPasswords(permissions.BasePermission):
    """Permission for resetting user passwords"""
    allowed_roles = ['ict', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles
    
    def has_object_permission(self, request, view, obj):
        if not request.user.is_authenticated:
            return False
        
        # ICT officers cannot reset super admin passwords
        if request.user.role == 'ict' and obj.role == 'super-admin':
            return False
        
        return request.user.role in self.allowed_roles


# ==============================================
# COURSE REGISTRATION PERMISSIONS
# ==============================================

class CanApproveCourseRegistrations(permissions.BasePermission):
    """Permission for approving course registrations"""
    allowed_roles = ['lecturer', 'exam-officer', 'hod', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles


class CanVerifyRegistrationPayments(permissions.BasePermission):
    """Permission for verifying registration payments"""
    allowed_roles = ['bursar', 'desk-officer', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles


    

# ADD THESE TO users/permissions.py if not present

class CanVerifyPayments(permissions.BasePermission):
    """Permission for verifying payments (Bursar + Desk Officer)"""
    allowed_roles = ['bursar', 'desk-officer', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles


class CanGenerateFinancialReports(permissions.BasePermission):
    """Permission for generating financial reports"""
    allowed_roles = ['bursar', 'registrar', 'super-admin']
    
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in self.allowed_roles