from rest_framework import viewsets, status, generics, serializers
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.tokens import RefreshToken
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters
import logging
import django.db.models as models
import uuid
from rest_framework import viewsets, status, permissions
from django.db import transaction


from .models import User, Student, Lecturer, StaffProfile
from .serializers import (
    UserSerializer, UserCreateSerializer, StudentSerializer, StudentCreateSerializer,
    LecturerSerializer, LecturerCreateSerializer, StaffProfileSerializer, 
    StaffProfileCreateSerializer, LoginSerializer, UserUpdateSerializer, UserPasswordResetSerializer,
    StaffRegistrationSerializer, HODCreateSerializer, ChangePasswordSerializer
)
from .permissions import IsAdminStaff, IsSuperAdmin, CanManageUsers

logger = logging.getLogger(__name__)

class AuthViewSet(viewsets.GenericViewSet):
    """Authentication endpoints"""
    permission_classes = [AllowAny]
    serializer_class = UserSerializer
    
    @action(detail=False, methods=['post'])
    def login(self, request):
        """User login with comprehensive debug logging"""
        logger.info("🎯 LOGIN ACTION CALLED")
        try:
            serializer = LoginSerializer(data=request.data)
            if not serializer.is_valid():
                logger.error(f"❌ Login validation failed: {serializer.errors}")
                return Response(
                    {'detail': 'Invalid login credentials', 'errors': serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            user = serializer.validated_data['user']
            if not user.is_active:
                return Response(
                    {'detail': 'User account is inactive'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            refresh = RefreshToken.for_user(user)
            
            # Get user profile based on role
            profile_data = None
            if user.role == 'student' and hasattr(user, 'student_profile'):
                profile_data = StudentSerializer(user.student_profile).data
            elif (user.role == 'lecturer' or user.role == 'hod') and hasattr(user, 'lecturer_profile'):
                profile_data = LecturerSerializer(user.lecturer_profile).data
            elif hasattr(user, 'staff_profile'):
                profile_data = StaffProfileSerializer(user.staff_profile).data
                
            response_data = {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': UserSerializer(user).data,
                'profile': profile_data
            }
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"💥 UNEXPECTED ERROR in login: {str(e)}", exc_info=True)
            return Response(
                {'detail': 'Login failed due to server error'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['get', 'post'], url_path='register/staff', permission_classes=[permissions.IsAdminUser])
    def register_staff(self, request):
        """
        Register a new staff member (Lecturer, Bursar, Registrar, etc.)
        Handles both GET (Form Schema) and POST (Creation)
        """
        # --- GET REQUEST: Return Form Schema ---
        if request.method == 'GET':
            return Response({
                'message': 'Staff Registration',
                'required_fields': {
                    'user_data': {
                        'email': 'string', 'username': 'string', 'first_name': 'string',
                        'last_name': 'string', 'role': 'bursar|registrar|etc',
                        'password': 'string', 'password_confirm': 'string'
                    },
                    'staff_id': 'string',
                    'position': 'string'
                },
                'optional_fields': {'department': 'string', 'office_location': 'string'}
            })

        # --- POST REQUEST: Process Registration ---
        serializer = StaffRegistrationSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                # 1. Create User
                user = serializer.save()
                role = request.data.get('role')
                staff_id = request.data.get('staff_id', '')
                
                # 2. Create Specific Profile
                if role == 'lecturer':
                    if not hasattr(user, 'lecturer_profile'):
                        Lecturer.objects.create(
                            user=user, 
                            staff_id=staff_id,
                            department_id=request.data.get('department') # Assuming ID is passed
                        )
                
                elif role in ['bursar', 'registrar', 'exam-officer', 'desk-officer', 'ict', 'super-admin']:
                    if not hasattr(user, 'staff_profile'):
                        StaffProfile.objects.create(
                            user=user,
                            staff_id=staff_id,
                            position=request.data.get('position', role.replace('-', ' ').title()),
                            department=request.data.get('department', 'Administration')
                        )

                # 3. Return Success Response
                return Response({
                    'message': f'{role.capitalize()} account created successfully',
                    'user': UserSerializer(user).data
                }, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Registration error: {str(e)}")
            return Response(
                {'error': str(e), 'detail': 'An error occurred during registration.'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    # In your AuthViewSet class, update the register_hod method:

    @action(detail=False, methods=['get', 'post'], url_path='register/hod')
    def register_hod(self, request):
        """HOD registration with department assignment"""
        if request.method == 'GET':
            from academics.models import Department
            # Get departments that don't have an HOD yet
            departments = Department.objects.filter(hod__isnull=True)
            departments_data = [{
                'id': d.id, 
                'name': d.name, 
                'code': d.code,
                'hod_name': d.hod.user.get_full_name() if d.hod else None
            } for d in departments]
            
            return Response({
                'message': 'HOD Registration',
                'available_departments': departments_data,
                'schema': {
                    'required_fields': {
                        'user_data': {
                            'email': 'string', 'username': 'string', 
                            'first_name': 'string', 'last_name': 'string',
                            'password': 'string', 'password_confirm': 'string'
                        },
                        'staff_id': 'string',
                        'department_id': 'integer (Department ID)',
                        'designation': 'string'
                    },
                    'optional_fields': {
                        'specialization': 'string',
                        'qualifications': 'string',
                        'office_location': 'string',
                        'consultation_hours': 'string'
                    }
                }
            })
        
        # POST Request
        try:
            with transaction.atomic():
                data = request.data.copy()
                
                # 1. Extract user data and force role to 'hod'
                user_data = data.get('user_data', {})
                user_data['role'] = 'hod'  # Force role to 'hod'
                
                # 2. Create the user with HOD role
                from .serializers import UserCreateSerializer
                user_serializer = UserCreateSerializer(data=user_data)
                user_serializer.is_valid(raise_exception=True)
                user = user_serializer.save()
                
                # 3. Create the lecturer profile
                department_id = data.get('department_id')
                try:
                    from academics.models import Department
                    department = Department.objects.get(id=department_id)
                except Department.DoesNotExist:
                    raise serializers.ValidationError("Selected department does not exist")
                
                # Check if department already has an HOD
                if department.hod:
                    raise serializers.ValidationError(f"Department {department.name} already has an HOD")
                
                # Create lecturer profile with is_hod=True
                lecturer = Lecturer.objects.create(
                    user=user,
                    staff_id=data.get('staff_id'),
                    department=department,
                    designation=data.get('designation', 'Professor'),
                    specialization=data.get('specialization', ''),
                    qualifications=data.get('qualifications', ''),
                    office_location=data.get('office_location', ''),
                    consultation_hours=data.get('consultation_hours', ''),
                    is_hod=True  # Mark as HOD in Lecturer table
                )
                
                # 4. Update the department to point to this HOD
                department.hod = lecturer
                department.save()
                
                # Generate tokens
                refresh = RefreshToken.for_user(user)
                
                return Response({
                    'access': str(refresh.access_token),
                    'refresh': str(refresh),
                    'user': UserSerializer(user).data,
                    'profile': LecturerSerializer(lecturer).data,
                    'department': {
                        'id': department.id,
                        'name': department.name,
                        'code': department.code
                    },
                    'message': f'HOD successfully created for {department.name}'
                }, status=status.HTTP_201_CREATED)
                
        except serializers.ValidationError as e:
            return Response({'error': e.detail}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"HOD registration error: {str(e)}", exc_info=True)
            return Response(
                {'error': 'Registration failed. Please try again.'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @action(detail=False, methods=['get', 'post'], url_path='register/lecturer')
    def register_lecturer(self, request):
        """Lecturer registration with user data"""
        if request.method == 'GET':
            from academics.models import Department
            departments = Department.objects.all()
            departments_data = [{'id': d.id, 'name': d.name, 'code': d.code} for d in departments]
            return Response({
                'message': 'Lecturer Registration',
                'departments': departments_data,
                'schema': {
                    'required_fields': {
                        'user_data': {
                            'email': 'string', 'username': 'string', 
                            'first_name': 'string', 'last_name': 'string',
                            'password': 'string', 'password_confirm': 'string'
                        },
                        'staff_id': 'string',
                        'department': 'integer (Department ID)'
                    },
                    'optional_fields': {
                        'designation': 'string',
                        'specialization': 'string',
                        'qualifications': 'string',
                        'office_location': 'string',
                        'consultation_hours': 'string'
                    }
                }
            })
        
        serializer = LecturerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        lecturer = serializer.save()
        refresh = RefreshToken.for_user(lecturer.user)
        
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(lecturer.user).data,
            'profile': LecturerSerializer(lecturer).data,
            'message': 'Lecturer account created successfully'
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get', 'post'])
    def register_student(self, request):
        """Student registration"""
        if request.method == 'GET':
            return Response({'message': 'Student Registration Schema'})
        
        serializer = StudentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        student = serializer.save()
        refresh = RefreshToken.for_user(student.user)
        
        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': UserSerializer(student.user).data,
            'profile': StudentSerializer(student).data
        }, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """Get current user profile"""
        try:
            user = request.user
            profile_data = None
            
            if user.role == 'student' and hasattr(user, 'student_profile'):
                profile_data = StudentSerializer(user.student_profile).data
            elif (user.role == 'lecturer' or user.role == 'hod') and hasattr(user, 'lecturer_profile'):
                profile_data = LecturerSerializer(user.lecturer_profile).data
            elif user.role in ['registrar', 'bursar', 'desk-officer', 'ict', 'exam-officer', 'super-admin']:
                if hasattr(user, 'staff_profile'):
                    profile_data = StaffProfileSerializer(user.staff_profile).data
                else:
                    # Auto-fix for super admins missing profile
                    try:
                        staff_id = f"ADMIN-{uuid.uuid4().hex[:6].upper()}"
                        StaffProfile.objects.create(
                            user=user, staff_id=staff_id, position="System Admin"
                        )
                        user.refresh_from_db()
                        profile_data = StaffProfileSerializer(user.staff_profile).data
                    except Exception:
                        pass

            return Response({
                'user': UserSerializer(user).data,
                'profile': profile_data
            })
        except Exception as e:
            return Response(
                {'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    # ✅ NEW ACTION: Change Password
    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated], url_path='change-password')
    def change_password(self, request):
        """Allow logged-in user to change their password"""
        user = request.user
        serializer = ChangePasswordSerializer(data=request.data)

        if serializer.is_valid():
            old_password = serializer.validated_data['old_password']
            new_password = serializer.validated_data['new_password']

            # Verify old password
            if not user.check_password(old_password):
                return Response(
                    {'error': 'Incorrect old password'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Set new password
            user.set_password(new_password)
            user.save()
            
            # Update session hash to prevent logout (if using session auth, though we use JWT)
            # For JWT, the token remains valid until expiry, but this is good practice
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, user)

            logger.info(f"🔒 Password changed for user: {user.email}")
            return Response({'message': 'Password updated successfully'})

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserViewSet(viewsets.ModelViewSet):
    """User CRUD operations with enhanced user management"""
    queryset = User.objects.all().select_related(
        'student_profile', 'lecturer_profile', 'staff_profile'
    )
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, CanManageUsers]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['role', 'is_active', 'created_at']
    search_fields = ['email', 'first_name', 'last_name', 'username']
    ordering_fields = ['created_at', 'email', 'first_name', 'last_name']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserSerializer
    
    def get_queryset(self):
        """Enhanced queryset with filtering"""
        queryset = super().get_queryset()
        
        # Additional filtering based on query params
        role = self.request.query_params.get('role')
        is_active = self.request.query_params.get('is_active')
        search = self.request.query_params.get('search')
        
        if role:
            queryset = queryset.filter(role=role)
        if is_active:
            is_active_bool = is_active.lower() == 'true'
            queryset = queryset.filter(is_active=is_active_bool)
        if search:
            queryset = queryset.filter(
                models.Q(email__icontains=search) |
                models.Q(first_name__icontains=search) |
                models.Q(last_name__icontains=search) |
                models.Q(username__icontains=search)
            )
        
        return queryset
    
    @action(detail=False, methods=['get'])
    def students(self, request):
        """List all students"""
        students = User.objects.filter(role='student')
        page = self.paginate_queryset(students)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def lecturers(self, request):
        """List all lecturers"""
        lecturers = User.objects.filter(role='lecturer')
        page = self.paginate_queryset(lecturers)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def staff(self, request):
        """List all staff (non-lecturer staff)"""
        staff_roles = ['hod', 'registrar', 'bursar', 'desk-officer', 'ict', 'exam-officer', 'super-admin']
        staff = User.objects.filter(role__in=staff_roles)
        page = self.paginate_queryset(staff)
        serializer = self.get_serializer(page, many=True)
        return self.get_paginated_response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def activate(self, request, pk=None):
        """Activate a user account"""
        user = self.get_object()
        user.is_active = True
        user.save()
        
        logger.info(f"✅ User activated: {user.email} by {request.user.email}")
        return Response({
            'message': f'User {user.email} has been activated successfully',
            'user': UserSerializer(user).data
        })
    
    @action(detail=True, methods=['post'])
    def deactivate(self, request, pk=None):
        """Deactivate a user account"""
        user = self.get_object()
        
        # Prevent deactivating yourself
        if user == request.user:
            return Response(
                {'error': 'You cannot deactivate your own account'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user.is_active = False
        user.save()
        
        logger.info(f"✅ User deactivated: {user.email} by {request.user.email}")
        return Response({
            'message': f'User {user.email} has been deactivated successfully',
            'user': UserSerializer(user).data
        })
    
    @action(detail=True, methods=['post'])
    def reset_password(self, request, pk=None):
        """Reset user password (admin function)"""
        user = self.get_object()
        serializer = UserPasswordResetSerializer(data=request.data)
        
        if serializer.is_valid():
            new_password = serializer.validated_data['new_password']
            user.set_password(new_password)
            user.save()
            
            logger.info(f"✅ Password reset for: {user.email} by {request.user.email}")
            return Response({
                'message': f'Password for {user.email} has been reset successfully'
            })
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get user statistics"""
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        students_count = User.objects.filter(role='student').count()
        lecturers_count = User.objects.filter(role='lecturer').count()
        staff_count = User.objects.filter(role__in=[
            'hod', 'registrar', 'bursar', 'desk-officer', 'ict', 'exam-officer', 'super-admin'
        ]).count()
        
        role_distribution = User.objects.values('role').annotate(
            count=models.Count('id')
        ).order_by('-count')
        
        return Response({
            'total_users': total_users,
            'active_users': active_users,
            'inactive_users': total_users - active_users,
            'role_breakdown': {
                'students': students_count,
                'lecturers': lecturers_count,
                'staff': staff_count,
            },
            'role_distribution': list(role_distribution)
        })
    
    @action(detail=False, methods=['post'])
    def bulk_actions(self, request):
        """Bulk user actions (activate, deactivate, delete)"""
        user_ids = request.data.get('user_ids', [])
        action_type = request.data.get('action')
        
        if not user_ids or not action_type:
            return Response(
                {'error': 'user_ids and action are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        users = User.objects.filter(id__in=user_ids)
        
        # Prevent self-modification in bulk actions
        if request.user.id in user_ids and action_type in ['deactivate', 'delete']:
            return Response(
                {'error': 'You cannot perform this action on your own account'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if action_type == 'activate':
            users.update(is_active=True)
            message = f'{users.count()} users activated successfully'
        elif action_type == 'deactivate':
            users.update(is_active=False)
            message = f'{users.count()} users deactivated successfully'
        elif action_type == 'delete':
            count = users.count()
            users.delete()
            message = f'{count} users deleted successfully'
        else:
            return Response(
                {'error': 'Invalid action type'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        logger.info(f"✅ Bulk action '{action_type}' performed on {users.count()} users by {request.user.email}")
        return Response({'message': message})
    
    @action(detail=False, methods=['get'])
    def super_admin_stats(self, request):
        """Comprehensive statistics for super admin dashboard"""
        from django.db.models import Count, Q
        from academics.models import Department, Course
        from finance.models import Invoice
        from admissions.models import Application
        
        # User statistics
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        inactive_users = total_users - active_users
        
        # Role breakdown
        role_distribution = User.objects.values('role').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Recent users (last 7 days)
        from django.utils import timezone
        from datetime import timedelta
        last_week = timezone.now() - timedelta(days=7)
        recent_users = User.objects.filter(created_at__gte=last_week).count()
        
        # Academic statistics
        total_departments = Department.objects.count()
        departments_with_hod = Department.objects.filter(hod__isnull=False).count()
        
        total_courses = Course.objects.count()
        courses_with_lecturers = Course.objects.filter(lecturer__isnull=False).count()
        
        # Student specific stats
        students = User.objects.filter(role='student')
        total_students = students.count()
        active_students = students.filter(is_active=True).count()
        
        # Lecturer specific stats
        lecturers = User.objects.filter(role='lecturer')
        total_lecturers = lecturers.count()
        hod_count = Lecturer.objects.filter(is_hod=True).count()
        
        # Staff statistics (excluding lecturers)
        staff_roles = ['hod', 'registrar', 'bursar', 'desk-officer', 'ict', 'exam-officer', 'super-admin']
        total_staff = User.objects.filter(role__in=staff_roles).count()
        
        # Finance statistics (if finance app exists)
        try:
            total_invoices = Invoice.objects.count()
            paid_invoices = Invoice.objects.filter(status='paid').count()
            pending_invoices = Invoice.objects.filter(status='pending').count()
        except:
            total_invoices = 0
            paid_invoices = 0
            pending_invoices = 0
        
        # Admissions statistics (if admissions app exists)
        try:
            total_applications = Application.objects.count()
            pending_applications = Application.objects.filter(status='pending').count()
            approved_applications = Application.objects.filter(status='approved').count()
        except:
            total_applications = 0
            pending_applications = 0
            approved_applications = 0
        
        return Response({
            'users': {
                'total': total_users,
                'active': active_users,
                'inactive': inactive_users,
                'recent_week': recent_users,
                'role_distribution': list(role_distribution),
            },
            'students': {
                'total': total_students,
                'active': active_students,
                'inactive': total_students - active_students,
            },
            'lecturers': {
                'total': total_lecturers,
                'hod_count': hod_count,
                'with_courses': courses_with_lecturers,
            },
            'staff': {
                'total': total_staff,
                'breakdown': {
                    role: User.objects.filter(role=role).count()
                    for role in staff_roles
                }
            },
            'academics': {
                'departments': {
                    'total': total_departments,
                    'with_hod': departments_with_hod,
                    'without_hod': total_departments - departments_with_hod,
                },
                'courses': {
                    'total': total_courses,
                    'with_lecturers': courses_with_lecturers,
                    'without_lecturers': total_courses - courses_with_lecturers,
                }
            },
            'finance': {
                'total_invoices': total_invoices,
                'paid_invoices': paid_invoices,
                'pending_invoices': pending_invoices,
                'revenue_rate': (paid_invoices / total_invoices * 100) if total_invoices > 0 else 0,
            },
            'admissions': {
                'total_applications': total_applications,
                'pending_applications': pending_applications,
                'approved_applications': approved_applications,
                'approval_rate': (approved_applications / total_applications * 100) if total_applications > 0 else 0,
            },
            'system': {
                'timestamp': timezone.now().isoformat(),
                'data_freshness': 'live'
            }
        })
    
    def perform_destroy(self, instance):
        """Override delete to prevent self-deletion"""
        if instance == self.request.user:
            raise serializers.ValidationError("You cannot delete your own account")
        
        logger.info(f"✅ User deleted: {instance.email} by {self.request.user.email}")
        instance.delete()


class StudentViewSet(viewsets.ModelViewSet):
    """Student profile operations"""
    queryset = Student.objects.select_related('user', 'department').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['level', 'status', 'department']
    search_fields = ['matric_number', 'user__first_name', 'user__last_name', 'user__email']
    ordering_fields = ['created_at', 'matric_number']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return StudentCreateSerializer
        return StudentSerializer


class LecturerViewSet(viewsets.ModelViewSet):
    """Lecturer profile operations"""
    queryset = Lecturer.objects.select_related('user', 'department').all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['department', 'designation', 'is_hod']
    search_fields = ['staff_id', 'user__first_name', 'user__last_name', 'specialization']
    ordering_fields = ['created_at', 'staff_id']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return LecturerCreateSerializer
        return LecturerSerializer


class StaffProfileViewSet(viewsets.ModelViewSet):
    """Staff profile operations"""
    queryset = StaffProfile.objects.select_related('user').all()
    permission_classes = [IsAuthenticated, IsAdminStaff]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['department', 'position']
    search_fields = ['staff_id', 'user__first_name', 'user__last_name', 'position']
    ordering_fields = ['created_at', 'staff_id']
    
    def get_serializer_class(self):
        if self.action == 'create':
            return StaffProfileCreateSerializer
        return StaffProfileSerializer