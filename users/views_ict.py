
# users/views_ict.py - FIXED IMPORTS
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from django.db.models import Count, Q, Sum, Case, When, Value, IntegerField
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import update_session_auth_hash
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO
from django.http import HttpResponse
import secrets
import string

# Import from current app (users)
from .models import User, Student, Lecturer, StaffProfile
from .serializers import (
    UserSerializer, UserCreateSerializer, UserUpdateSerializer,
    StudentSerializer, LecturerSerializer, StaffProfileSerializer,
    UserPasswordResetSerializer
)
from .permissions import IsICTOfficer

# Import from other apps
from academics.models import Department, Course, Semester


# ==============================================
# ICT OFFICER DASHBOARD VIEW
# ==============================================

class ICTDashboardViewSet(viewsets.ViewSet):
    """ICT Officer dashboard with system overview"""
    permission_classes = [IsAuthenticated, IsICTOfficer]
    
    @action(detail=False, methods=['get'])
    def overview(self, request):
        """Get ICT officer dashboard overview"""
        # Get system statistics
        system_stats = self._get_system_statistics()
        
        # Get user statistics
        user_stats = self._get_user_statistics()
        
        # Get recent activities
        recent_activities = self._get_recent_activities()
        
        # Get system health
        system_health = self._check_system_health()
        
        # Get pending requests
        pending_requests = self._get_pending_requests()
        
        return Response({
            'system_statistics': system_stats,
            'user_statistics': user_stats,
            'recent_activities': recent_activities,
            'system_health': system_health,
            'pending_requests': pending_requests,
            'quick_actions': [
                {'action': 'create_account', 'label': 'Create Account', 'icon': 'user-plus'},
                {'action': 'reset_password', 'label': 'Reset Password', 'icon': 'key'},
                {'action': 'manage_users', 'label': 'Manage Users', 'icon': 'users'},
                {'action': 'system_config', 'label': 'System Config', 'icon': 'settings'}
            ]
        })
    
    def _get_system_statistics(self):
        """Get overall system statistics"""
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        inactive_users = total_users - active_users
        
        # Users by role
        users_by_role = User.objects.values('role').annotate(
            count=Count('id')
        ).order_by('-count')
        
        # Login statistics (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        recent_logins = User.objects.filter(
            last_login__gte=thirty_days_ago
        ).count()
        
        # Account creation trend (last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        new_users = User.objects.filter(
            created_at__gte=week_ago
        ).count()
        
        return {
            'total_users': total_users,
            'active_users': active_users,
            'inactive_users': inactive_users,
            'users_by_role': list(users_by_role),
            'recent_logins': recent_logins,
            'new_users_last_week': new_users,
            'login_rate': round((recent_logins / active_users * 100), 1) if active_users > 0 else 0
        }
    
    def _get_user_statistics(self):
        """Get detailed user statistics"""
        # Student statistics
        total_students = Student.objects.count()
        active_students = Student.objects.filter(user__is_active=True).count()
        
        # Lecturer statistics
        total_lecturers = Lecturer.objects.count()
        hod_count = Lecturer.objects.filter(is_hod=True).count()
        
        # Staff statistics
        total_staff = StaffProfile.objects.count()
        
        # Department-wise user distribution
        dept_stats = []
        departments = Department.objects.all()
        for dept in departments:
            student_count = Student.objects.filter(department=dept).count()
            lecturer_count = Lecturer.objects.filter(department=dept).count()
            
            if student_count > 0 or lecturer_count > 0:
                dept_stats.append({
                    'department': dept.name,
                    'students': student_count,
                    'lecturers': lecturer_count,
                    'total': student_count + lecturer_count
                })
        
        # Account status issues
        users_without_profiles = User.objects.filter(
            Q(student_profile__isnull=True) &
            Q(lecturer_profile__isnull=True) &
            Q(staff_profile__isnull=True)
        ).exclude(role='super-admin').count()
        
        return {
            'students': {
                'total': total_students,
                'active': active_students,
                'inactive': total_students - active_students
            },
            'lecturers': {
                'total': total_lecturers,
                'hod_count': hod_count,
                'regular': total_lecturers - hod_count
            },
            'staff': {
                'total': total_staff,
                'breakdown': {
                    role: StaffProfile.objects.filter(user__role=role).count()
                    for role in ['registrar', 'bursar', 'desk-officer', 'ict', 'exam-officer']
                }
            },
            'department_distribution': dept_stats,
            'issues': {
                'users_without_profiles': users_without_profiles,
                'inactive_over_30_days': User.objects.filter(
                    is_active=True,
                    last_login__lt=timezone.now() - timedelta(days=30)
                ).count()
            }
        }
    
    def _get_recent_activities(self):
        """Get recent system activities"""
        recent_activities = []
        
        # Recent account creations (last 24 hours)
        day_ago = timezone.now() - timedelta(hours=24)
        new_accounts = User.objects.filter(
            created_at__gte=day_ago
        ).select_related('student_profile', 'lecturer_profile', 'staff_profile')[:10]
        
        for user in new_accounts:
            profile_type = 'Student' if hasattr(user, 'student_profile') else \
                          'Lecturer' if hasattr(user, 'lecturer_profile') else \
                          'Staff' if hasattr(user, 'staff_profile') else 'User'
            
            recent_activities.append({
                'type': 'account_created',
                'title': f'New {profile_type} Account Created',
                'details': f'{user.get_full_name()} ({user.email})',
                'timestamp': user.created_at,
                'user_role': user.role
            })
        
        # Recent password resets (placeholder - implement logging)
        # You would track password reset actions in an AuditLog
        
        return recent_activities[:5]  # Return only 5 most recent
    
    def _check_system_health(self):
        """Check system health status"""
        health_checks = []
        
        # Check for users without profiles
        users_without_profiles = User.objects.filter(
            Q(student_profile__isnull=True) &
            Q(lecturer_profile__isnull=True) &
            Q(staff_profile__isnull=True)
        ).exclude(role='super-admin').count()
        
        if users_without_profiles > 0:
            health_checks.append({
                'check': 'Users without profiles',
                'status': 'warning',
                'message': f'{users_without_profiles} users have no associated profile',
                'action': 'review_users'
            })
        
        # Check for departments without HOD
        depts_without_hod = Department.objects.filter(hod__isnull=True).count()
        if depts_without_hod > 0:
            health_checks.append({
                'check': 'Departments without HOD',
                'status': 'warning',
                'message': f'{depts_without_hod} departments have no HOD assigned',
                'action': 'assign_hod'
            })
        
        # Check for courses without lecturers
        courses_without_lecturers = Course.objects.filter(lecturer__isnull=True).count()
        if courses_without_lecturers > 0:
            health_checks.append({
                'check': 'Courses without lecturers',
                'status': 'info',
                'message': f'{courses_without_lecturers} courses have no lecturer assigned',
                'action': 'assign_lecturers'
            })
        
        # Check for inactive super users
        inactive_super_admins = User.objects.filter(
            role='super-admin',
            is_active=False
        ).count()
        
        if inactive_super_admins > 0:
            health_checks.append({
                'check': 'Inactive super admins',
                'status': 'critical',
                'message': f'{inactive_super_admins} super admin accounts are inactive',
                'action': 'review_admins'
            })
        
        # Overall status
        has_critical = any(check['status'] == 'critical' for check in health_checks)
        has_warnings = any(check['status'] == 'warning' for check in health_checks)
        
        overall_status = 'healthy'
        if has_critical:
            overall_status = 'critical'
        elif has_warnings:
            overall_status = 'warning'
        
        return {
            'overall_status': overall_status,
            'checks': health_checks,
            'timestamp': timezone.now()
        }
    
    def _get_pending_requests(self):
        """Get pending user requests"""
        # Placeholder - implement based on your request system
        # This could include password reset requests, account creation requests, etc.
        return {
            'password_resets': 0,
            'account_creations': 0,
            'access_requests': 0,
            'total': 0
        }


# ==============================================
# USER ACCOUNT MANAGEMENT
# ==============================================

class UserManagementViewSet(viewsets.ModelViewSet):
    """Comprehensive user management for ICT officer"""
    queryset = User.objects.all().select_related(
        'student_profile', 'lecturer_profile', 'staff_profile'
    )
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsICTOfficer]
    
    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        return UserSerializer
    
    @action(detail=False, methods=['get'])
    def user_statistics(self, request):
        """Get detailed user statistics"""
        # Overall statistics
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        
        # Role distribution
        role_distribution = User.objects.values('role').annotate(
            count=Count('id'),
            active=Count(Case(When(is_active=True, then=1), output_field=IntegerField())),
            inactive=Count(Case(When(is_active=False, then=1), output_field=IntegerField()))
        ).order_by('-count')
        
        # Registration trend (last 30 days)
        thirty_days_ago = timezone.now() - timedelta(days=30)
        registration_trend = []
        
        for i in range(30, -1, -1):
            date = timezone.now() - timedelta(days=i)
            start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = date.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            count = User.objects.filter(
                created_at__range=(start_of_day, end_of_day)
            ).count()
            
            registration_trend.append({
                'date': start_of_day.date(),
                'count': count
            })
        
        # Login activity (last 7 days)
        login_activity = []
        for i in range(6, -1, -1):
            date = timezone.now() - timedelta(days=i)
            start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = date.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            count = User.objects.filter(
                last_login__range=(start_of_day, end_of_day)
            ).count()
            
            login_activity.append({
                'date': start_of_day.date(),
                'count': count
            })
        
        return Response({
            'overall': {
                'total_users': total_users,
                'active_users': active_users,
                'inactive_users': total_users - active_users,
                'active_percentage': round((active_users / total_users * 100), 1) if total_users > 0 else 0
            },
            'role_distribution': list(role_distribution),
            'registration_trend': registration_trend,
            'login_activity': login_activity,
            'account_age_distribution': self._get_account_age_distribution()
        })
    
    def _get_account_age_distribution(self):
        """Get distribution of account ages"""
        now = timezone.now()
        
        distribution = [
            {'range': '0-30 days', 'min_days': 0, 'max_days': 30, 'count': 0},
            {'range': '31-90 days', 'min_days': 31, 'max_days': 90, 'count': 0},
            {'range': '91-180 days', 'min_days': 91, 'max_days': 180, 'count': 0},
            {'range': '181-365 days', 'min_days': 181, 'max_days': 365, 'count': 0},
            {'range': '1+ years', 'min_days': 366, 'max_days': None, 'count': 0}
        ]
        
        for user in User.objects.all():
            account_age = (now - user.created_at).days
            
            for range_data in distribution:
                if range_data['min_days'] <= account_age:
                    if range_data['max_days'] is None or account_age <= range_data['max_days']:
                        range_data['count'] += 1
                        break
        
        return distribution
    
    @action(detail=False, methods=['get'])
    def search_users(self, request):
        """Search users with advanced filters"""
        search_query = request.query_params.get('q', '')
        role_filter = request.query_params.get('role')
        status_filter = request.query_params.get('status')
        department_filter = request.query_params.get('department_id')
        
        queryset = User.objects.all()
        
        if search_query:
            queryset = queryset.filter(
                Q(email__icontains=search_query) |
                Q(first_name__icontains=search_query) |
                Q(last_name__icontains=search_query) |
                Q(username__icontains=search_query) |
                Q(student_profile__matric_number__icontains=search_query) |
                Q(lecturer_profile__staff_id__icontains=search_query) |
                Q(staff_profile__staff_id__icontains=search_query)
            )
        
        if role_filter:
            queryset = queryset.filter(role=role_filter)
        
        if status_filter:
            if status_filter == 'active':
                queryset = queryset.filter(is_active=True)
            elif status_filter == 'inactive':
                queryset = queryset.filter(is_active=False)
        
        if department_filter:
            queryset = queryset.filter(
                Q(student_profile__department_id=department_filter) |
                Q(lecturer_profile__department_id=department_filter)
            )
        
        # Select related for performance
        queryset = queryset.select_related(
            'student_profile', 'lecturer_profile', 'staff_profile'
        )
        
        # Apply pagination
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def reset_password(self, request, pk=None):
        """Reset user password (ICT officer function)"""
        user = self.get_object()
        
        serializer = UserPasswordResetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        new_password = serializer.validated_data['new_password']
        user.set_password(new_password)
        user.save()
        
        # Log the action (you should implement an audit log)
        self._log_password_reset(request.user, user)
        
        return Response({
            'message': f'Password reset successfully for {user.email}',
            'user': UserSerializer(user).data
        })
    
    def _log_password_reset(self, admin_user, target_user):
        """Log password reset action"""
        # Placeholder - implement audit logging
        pass
    
    @action(detail=True, methods=['post'])
    def toggle_active_status(self, request, pk=None):
        """Toggle user active status"""
        user = self.get_object()
        
        # Prevent deactivating yourself
        if user == request.user:
            return Response(
                {'error': 'You cannot deactivate your own account'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user.is_active = not user.is_active
        user.save()
        
        action = 'activated' if user.is_active else 'deactivated'
        
        return Response({
            'message': f'User {user.email} has been {action}',
            'user': UserSerializer(user).data,
            'new_status': user.is_active
        })
    
    @action(detail=True, methods=['get'])
    def user_activity(self, request, pk=None):
        """Get user activity log"""
        user = self.get_object()
        
        # Placeholder - implement activity logging
        # This would retrieve from an AuditLog model
        
        activity_log = [
            {
                'action': 'login',
                'timestamp': user.last_login,
                'ip_address': '127.0.0.1',  # Placeholder
                'user_agent': 'Mozilla/5.0...'  # Placeholder
            },
            {
                'action': 'profile_update',
                'timestamp': user.updated_at,
                'details': 'Profile information updated'
            }
        ]
        
        return Response({
            'user': UserSerializer(user).data,
            'activity_log': activity_log,
            'statistics': {
                'total_logins': 10,  # Placeholder
                'last_login': user.last_login,
                'account_age_days': (timezone.now() - user.created_at).days
            }
        })
    
    @action(detail=False, methods=['post'])
    def bulk_actions(self, request):
        """Perform bulk actions on users"""
        user_ids = request.data.get('user_ids', [])
        action = request.data.get('action')
        
        if not user_ids or not action:
            return Response(
                {'error': 'user_ids and action are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if action not in ['activate', 'deactivate', 'delete']:
            return Response(
                {'error': 'Invalid action. Use activate, deactivate, or delete'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Remove request user from list to prevent self-modification
        if request.user.id in user_ids:
            user_ids.remove(request.user.id)
        
        users = User.objects.filter(id__in=user_ids)
        
        if action == 'activate':
            users.update(is_active=True)
            message = f'{users.count()} users activated'
        elif action == 'deactivate':
            users.update(is_active=False)
            message = f'{users.count()} users deactivated'
        else:  # delete
            count = users.count()
            users.delete()
            message = f'{count} users deleted'
        
        return Response({
            'message': message,
            'action': action,
            'affected_users': len(user_ids)
        })
    
    @action(detail=False, methods=['get'])
    def export_users(self, request):
        """Export users to Excel"""
        queryset = self.filter_queryset(self.get_queryset())
        
        # Prepare data for export
        export_data = []
        for user in queryset:
            profile_info = self._get_profile_info(user)
            
            export_data.append({
                'ID': user.id,
                'Email': user.email,
                'Username': user.username,
                'First Name': user.first_name,
                'Last Name': user.last_name,
                'Role': user.role,
                'Phone': user.phone,
                'Active': 'Yes' if user.is_active else 'No',
                'Last Login': user.last_login.strftime('%Y-%m-%d %H:%M') if user.last_login else 'Never',
                'Created At': user.created_at.strftime('%Y-%m-%d %H:%M'),
                'Profile Type': profile_info['type'],
                'Profile ID': profile_info['id'],
                'Department': profile_info['department']
            })
        
        # Create DataFrame
        df = pd.DataFrame(export_data)
        
        # Create Excel file in memory
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Users', index=False)
            
            # Auto-adjust column widths
            worksheet = writer.sheets['Users']
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = (max_length + 2)
                worksheet.column_dimensions[column_letter].width = adjusted_width
        
        # Prepare response
        output.seek(0)
        response = HttpResponse(
            output.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="users_export.xlsx"'
        
        return response
    
    def _get_profile_info(self, user):
        """Get profile information for a user"""
        if hasattr(user, 'student_profile'):
            return {
                'type': 'student',
                'id': user.student_profile.matric_number,
                'department': user.student_profile.department.name if user.student_profile.department else 'N/A'
            }
        elif hasattr(user, 'lecturer_profile'):
            return {
                'type': 'lecturer',
                'id': user.lecturer_profile.staff_id,
                'department': user.lecturer_profile.department.name if user.lecturer_profile.department else 'N/A'
            }
        elif hasattr(user, 'staff_profile'):
            return {
                'type': 'staff',
                'id': user.staff_profile.staff_id,
                'department': user.staff_profile.department or 'N/A'
            }
        else:
            return {
                'type': 'user',
                'id': 'N/A',
                'department': 'N/A'
            }


# ==============================================
# STAFF ACCOUNT CREATION
# ==============================================

class StaffAccountCreationViewSet(viewsets.ViewSet):
    """Staff account creation for ICT officer"""
    permission_classes = [IsAuthenticated, IsICTOfficer]
    
    @action(detail=False, methods=['get'])
    def account_creation_options(self, request):
        """Get options for creating different types of accounts"""
        # Get departments for dropdown
        departments = Department.objects.all().values('id', 'name', 'code')
        
        # Get designations for lecturers
        designations = [
            {'value': 'professor', 'label': 'Professor'},
            {'value': 'associate_professor', 'label': 'Associate Professor'},
            {'value': 'senior_lecturer', 'label': 'Senior Lecturer'},
            {'value': 'lecturer_1', 'label': 'Lecturer I'},
            {'value': 'lecturer_2', 'label': 'Lecturer II'},
            {'value': 'assistant_lecturer', 'label': 'Assistant Lecturer'}
        ]
        
        # Staff positions
        positions = [
            'Administrative Officer', 'Accountant', 'Secretary',
            'System Administrator', 'Data Entry Officer', 'Clerk'
        ]
        
        return Response({
            'departments': list(departments),
            'lecturer_designations': designations,
            'staff_positions': positions,
            'account_types': [
                {'value': 'lecturer', 'label': 'Lecturer'},
                {'value': 'hod', 'label': 'Head of Department'},
                {'value': 'registrar', 'label': 'Registrar'},
                {'value': 'bursar', 'label': 'Bursar'},
                {'value': 'desk_officer', 'label': 'Desk Officer'},
                {'value': 'exam_officer', 'label': 'Exam Officer'},
                {'value': 'ict', 'label': 'ICT Officer'},
                {'value': 'super_admin', 'label': 'Super Admin'}
            ]
        })
    
    @action(detail=False, methods=['post'])
    def create_lecturer_account(self, request):
        """Create lecturer account"""
        return self._create_staff_account(request, 'lecturer')
    
    @action(detail=False, methods=['post'])
    def create_hod_account(self, request):
        """Create HOD account"""
        return self._create_staff_account(request, 'hod')
    
    @action(detail=False, methods=['post'])
    def create_registrar_account(self, request):
        """Create registrar account"""
        return self._create_staff_account(request, 'registrar')
    
    @action(detail=False, methods=['post'])
    def create_bursar_account(self, request):
        """Create bursar account"""
        return self._create_staff_account(request, 'bursar')
    
    @action(detail=False, methods=['post'])
    def create_exam_officer_account(self, request):
        """Create exam officer account"""
        return self._create_staff_account(request, 'exam-officer')
    
    @action(detail=False, methods=['post'])
    def create_desk_officer_account(self, request):
        """Create desk officer account"""
        return self._create_staff_account(request, 'desk-officer')
    
    @action(detail=False, methods=['post'])
    def create_ict_account(self, request):
        """Create ICT officer account"""
        return self._create_staff_account(request, 'ict')
    
    @action(detail=False, methods=['post'])
    def create_super_admin_account(self, request):
        """Create super admin account"""
        return self._create_staff_account(request, 'super-admin')
    
    def _create_staff_account(self, request, role):
        """Create staff account with the specified role"""
        data = request.data.copy()
        
        # Validate required fields
        required_fields = ['email', 'first_name', 'last_name']
        missing_fields = [field for field in required_fields if not data.get(field)]
        
        if missing_fields:
            return Response(
                {'error': f'Missing required fields: {", ".join(missing_fields)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if email already exists
        if User.objects.filter(email=data['email']).exists():
            return Response(
                {'error': 'Email already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            with transaction.atomic():
                # Generate username from email
                username = data['email'].split('@')[0]
                
                # Generate random password
                password = self._generate_random_password()
                
                # Create user
                user_data = {
                    'email': data['email'],
                    'username': username,
                    'first_name': data['first_name'],
                    'last_name': data['last_name'],
                    'role': role,
                    'phone': data.get('phone', ''),
                    'is_active': True
                }
                
                user = User.objects.create_user(**user_data, password=password)
                
                # Create appropriate profile based on role
                if role in ['lecturer', 'hod']:
                    self._create_lecturer_profile(user, data, role == 'hod')
                elif role in ['registrar', 'bursar', 'desk-officer', 'ict', 'exam-officer', 'super-admin']:
                    self._create_staff_profile(user, data, role)
                
                # Prepare response
                response_data = {
                    'message': f'{role.replace("-", " ").title()} account created successfully',
                    'user': UserSerializer(user).data,
                    'credentials': {
                        'email': user.email,
                        'password': password,
                        'note': 'Please change password on first login'
                    }
                }
                
                # Send welcome email (placeholder)
                self._send_welcome_email(user, password, role)
                
                return Response(response_data, status=status.HTTP_201_CREATED)
                
        except Exception as e:
            return Response(
                {'error': f'Failed to create account: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    def _generate_random_password(self):
        """Generate a random secure password"""
        alphabet = string.ascii_letters + string.digits + '!@#$%^&*'
        password = ''.join(secrets.choice(alphabet) for i in range(12))
        return password
    
    def _create_lecturer_profile(self, user, data, is_hod=False):
        """Create lecturer profile"""
        if is_hod:
            data['is_hod'] = True
        
        lecturer_data = {
            'user': user,
            'staff_id': data.get('staff_id', self._generate_staff_id('LEC')),
            'department_id': data.get('department_id'),
            'designation': data.get('designation', 'lecturer_1'),
            'specialization': data.get('specialization', ''),
            'qualifications': data.get('qualifications', ''),
            'office_location': data.get('office_location', ''),
            'consultation_hours': data.get('consultation_hours', ''),
            'is_hod': is_hod
        }
        
        lecturer = Lecturer.objects.create(**lecturer_data)
        
        # If this lecturer is HOD, assign to department
        if is_hod and data.get('department_id'):
            try:
                department = Department.objects.get(id=data['department_id'])
                department.hod = lecturer
                department.save()
            except Department.DoesNotExist:
                pass
        
        return lecturer
    
    def _create_staff_profile(self, user, data, role):
        """Create staff profile"""
        staff_data = {
            'user': user,
            'staff_id': data.get('staff_id', self._generate_staff_id(role.upper()[:3])),
            'department': data.get('department', ''),
            'position': data.get('position', role.replace('-', ' ').title()),
            'office_location': data.get('office_location', '')
        }
        
        return StaffProfile.objects.create(**staff_data)
    
    def _generate_staff_id(self, prefix):
        """Generate unique staff ID"""
        import random
        while True:
            number = random.randint(1000, 9999)
            staff_id = f'{prefix}-{number}'
            if not Lecturer.objects.filter(staff_id=staff_id).exists() and \
               not StaffProfile.objects.filter(staff_id=staff_id).exists():
                return staff_id
    
    def _send_welcome_email(self, user, password, role):
        """Send welcome email with credentials"""
        # Placeholder - implement email sending
        # Use Django's email system to send welcome email
        pass
    
    @action(detail=False, methods=['post'])
    def bulk_create_accounts(self, request):
        """Bulk create staff accounts from CSV/Excel"""
        accounts_data = request.data.get('accounts', [])
        
        if not accounts_data:
            return Response(
                {'error': 'accounts array is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        successful = []
        failed = []
        
        for account_data in accounts_data:
            try:
                # Validate account data
                if not all(key in account_data for key in ['email', 'first_name', 'last_name', 'role']):
                    failed.append({
                        'account': account_data,
                        'error': 'Missing required fields (email, first_name, last_name, role)'
                    })
                    continue
                
                # Check if email exists
                if User.objects.filter(email=account_data['email']).exists():
                    failed.append({
                        'account': account_data,
                        'error': 'Email already exists'
                    })
                    continue
                
                # Create account
                with transaction.atomic():
                    password = self._generate_random_password()
                    
                    user_data = {
                        'email': account_data['email'],
                        'username': account_data['email'].split('@')[0],
                        'first_name': account_data['first_name'],
                        'last_name': account_data['last_name'],
                        'role': account_data['role'],
                        'phone': account_data.get('phone', ''),
                        'is_active': True
                    }
                    
                    user = User.objects.create_user(**user_data, password=password)
                    
                    # Create profile based on role
                    if account_data['role'] in ['lecturer', 'hod']:
                        self._create_lecturer_profile(user, account_data, account_data['role'] == 'hod')
                    else:
                        self._create_staff_profile(user, account_data, account_data['role'])
                    
                    successful.append({
                        'email': user.email,
                        'name': user.get_full_name(),
                        'role': user.role,
                        'password': password
                    })
                    
            except Exception as e:
                failed.append({
                    'account': account_data,
                    'error': str(e)
                })
        
        return Response({
            'successful': successful,
            'failed': failed,
            'total_successful': len(successful),
            'total_failed': len(failed)
        })


# ==============================================
# PASSWORD & ACCOUNT MANAGEMENT
# ==============================================

class PasswordManagementViewSet(viewsets.ViewSet):
    """Password and account management for ICT officer"""
    permission_classes = [IsAuthenticated, IsICTOfficer]
    
    @action(detail=False, methods=['get'])
    def password_reset_requests(self, request):
        """Get pending password reset requests"""
        # Placeholder - implement password reset request system
        # This would track requests from users who forgot passwords
        
        return Response({
            'pending_requests': [],
            'recently_processed': [],
            'statistics': {
                'requests_today': 0,
                'requests_this_week': 0,
                'average_response_time': '2 hours'
            }
        })
    
    @action(detail=False, methods=['post'])
    def force_password_reset(self, request):
        """Force password reset for multiple users"""
        user_ids = request.data.get('user_ids', [])
        
        if not user_ids:
            return Response(
                {'error': 'user_ids are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        users = User.objects.filter(id__in=user_ids)
        
        reset_results = []
        for user in users:
            try:
                # Generate new password
                new_password = self._generate_random_password()
                user.set_password(new_password)
                user.save()
                
                reset_results.append({
                    'user_id': user.id,
                    'email': user.email,
                    'name': user.get_full_name(),
                    'new_password': new_password,
                    'status': 'success'
                })
                
                # Log the action
                self._log_force_password_reset(request.user, user)
                
            except Exception as e:
                reset_results.append({
                    'user_id': user.id,
                    'email': user.email,
                    'status': 'failed',
                    'error': str(e)
                })
        
        return Response({
            'results': reset_results,
            'total_successful': len([r for r in reset_results if r['status'] == 'success']),
            'total_failed': len([r for r in reset_results if r['status'] == 'failed'])
        })
    
    def _generate_random_password(self):
        """Generate random password"""
        alphabet = string.ascii_letters + string.digits + '!@#$%'
        return ''.join(secrets.choice(alphabet) for _ in range(10))
    
    def _log_force_password_reset(self, admin_user, target_user):
        """Log force password reset action"""
        # Placeholder - implement audit logging
        pass
    
    @action(detail=False, methods=['get'])
    def account_lockout_status(self, request):
        """Get account lockout/security status"""
        # Check for accounts that might be locked out
        # Placeholder - implement based on your authentication system
        
        # Example: Users with many failed login attempts
        suspicious_accounts = User.objects.filter(
            is_active=True,
            last_login__lt=timezone.now() - timedelta(days=30)
        )[:10]
        
        suspicious_data = []
        for user in suspicious_accounts:
            suspicious_data.append({
                'user_id': user.id,
                'email': user.email,
                'name': user.get_full_name(),
                'last_login': user.last_login,
                'days_since_login': (timezone.now() - (user.last_login or user.created_at)).days,
                'risk_level': 'medium' if (timezone.now() - (user.last_login or user.created_at)).days > 60 else 'low'
            })
        
        return Response({
            'suspicious_accounts': suspicious_data,
            'lockout_statistics': {
                'total_locked': 0,  # Placeholder
                'locked_today': 0,
                'auto_unlocked': 0
            },
            'security_recommendations': [
                'Enable two-factor authentication for admin accounts',
                'Review inactive accounts monthly',
                'Implement password expiration policy'
            ]
        })
    
    @action(detail=True, methods=['post'])
    def unlock_account(self, request, pk=None):
        """Unlock a locked user account"""
        try:
            user = User.objects.get(id=pk)
        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # In a real system, you would reset failed login attempts
        # or clear lockout flags in your authentication backend
        
        # For now, just ensure the account is active
        user.is_active = True
        user.save()
        
        return Response({
            'message': f'Account unlocked for {user.email}',
            'user': UserSerializer(user).data
        })
    
    @action(detail=False, methods=['post'])
    def send_password_reset_links(self, request):
        """Send password reset links to users"""
        user_ids = request.data.get('user_ids', [])
        
        if not user_ids:
            return Response(
                {'error': 'user_ids are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        users = User.objects.filter(id__in=user_ids, is_active=True)
        
        results = []
        for user in users:
            try:
                # Generate password reset token/link
                reset_link = self._generate_password_reset_link(user)
                
                # Send email (placeholder)
                self._send_password_reset_email(user, reset_link)
                
                results.append({
                    'user_id': user.id,
                    'email': user.email,
                    'name': user.get_full_name(),
                    'status': 'sent',
                    'reset_link': reset_link  # In production, don't return the actual link
                })
                
            except Exception as e:
                results.append({
                    'user_id': user.id,
                    'email': user.email,
                    'status': 'failed',
                    'error': str(e)
                })
        
        return Response({
            'results': results,
            'total_sent': len([r for r in results if r['status'] == 'sent']),
            'total_failed': len([r for r in results if r['status'] == 'failed'])
        })
    
    def _generate_password_reset_link(self, user):
        """Generate password reset link"""
        # Placeholder - implement using Django's password reset system
        # or JWT tokens
        return f"/auth/password-reset/{user.id}/"
    
    def _send_password_reset_email(self, user, reset_link):
        """Send password reset email"""
        # Placeholder - implement email sending
        pass


# ==============================================
# SYSTEM CONFIGURATION
# ==============================================

class SystemConfigurationViewSet(viewsets.ViewSet):
    """System configuration management"""
    permission_classes = [IsAuthenticated, IsICTOfficer]
    
    @action(detail=False, methods=['get'])
    def current_configuration(self, request):
        """Get current system configuration"""
        # Get current semester
        current_semester = Semester.objects.filter(is_current=True).first()
        
        # Get system settings (you might have a SystemSettings model)
        system_settings = {
            'registration_enabled': current_semester.is_registration_active if current_semester else False,
            'exam_registration_open': True,  # Placeholder
            'result_publication': True,  # Placeholder
            'maintenance_mode': False,
            'allow_new_registrations': True,
            'max_courses_per_semester': 6,
            'min_attendance_percentage': 75,
            'passing_grade': 'D',
            'gpa_calculation_method': '4.0 scale'
        }
        
        # Get academic settings
        academic_settings = {
            'current_academic_year': current_semester.session if current_semester else None,
            'current_semester': current_semester.get_semester_display() if current_semester else None,
            'registration_deadline': current_semester.registration_deadline if current_semester else None,
            'semester_start': current_semester.start_date if current_semester else None,
            'semester_end': current_semester.end_date if current_semester else None
        }
        
        # Get department configuration
        departments = Department.objects.all().values('id', 'name', 'code', 'hod__user__email')
        
        # Get user role configuration
        role_config = {
            'available_roles': dict(User.ROLE_CHOICES),
            'role_permissions': self._get_role_permissions_summary()
        }
        
        return Response({
            'system_settings': system_settings,
            'academic_settings': academic_settings,
            'departments': list(departments),
            'role_configuration': role_config,
            'last_updated': timezone.now()
        })
    
    def _get_role_permissions_summary(self):
        """Get summary of role permissions"""
        # This is a simplified representation
        # In a real system, you'd query your permission system
        
        permissions = {
            'student': ['view_grades', 'register_courses', 'view_schedule', 'pay_fees'],
            'lecturer': ['enter_grades', 'mark_attendance', 'view_students', 'approve_registrations'],
            'hod': ['manage_department', 'approve_results', 'assign_courses', 'view_reports'],
            'registrar': ['manage_admissions', 'assign_matric', 'approve_results', 'process_clearance'],
            'bursar': ['manage_fees', 'verify_payments', 'generate_receipts', 'view_financial_reports'],
            'desk-officer': ['validate_registrations', 'enter_records', 'support_hod'],
            'ict': ['manage_users', 'reset_passwords', 'system_config', 'technical_support'],
            'exam-officer': ['compile_results', 'verify_scores', 'generate_exam_list', 'manage_timetable'],
            'super-admin': ['full_access']
        }
        
        return permissions
    
    @action(detail=False, methods=['post'])
    def update_system_settings(self, request):
        """Update system settings"""
        settings = request.data.get('settings', {})
        
        if not settings:
            return Response(
                {'error': 'settings object is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Update current semester registration status
        if 'registration_enabled' in settings:
            current_semester = Semester.objects.filter(is_current=True).first()
            if current_semester:
                current_semester.is_registration_active = settings['registration_enabled']
                current_semester.save()
        
        # Update other settings (you would save to a SystemSettings model)
        # For now, just return success
        
        return Response({
            'message': 'System settings updated successfully',
            'updated_settings': settings,
            'timestamp': timezone.now()
        })
    
    @action(detail=False, methods=['get'])
    def department_configuration(self, request):
        """Get department configuration"""
        departments = Department.objects.select_related('hod__user').all()
        
        dept_data = []
        for dept in departments:
            # Get statistics
            student_count = Student.objects.filter(department=dept).count()
            lecturer_count = Lecturer.objects.filter(department=dept).count()
            course_count = Course.objects.filter(department=dept).count()
            
            dept_data.append({
                'id': dept.id,
                'name': dept.name,
                'code': dept.code,
                'description': dept.description,
                'hod': {
                    'id': dept.hod.id if dept.hod else None,
                    'name': dept.hod.user.get_full_name() if dept.hod else None,
                    'email': dept.hod.user.email if dept.hod else None
                },
                'statistics': {
                    'students': student_count,
                    'lecturers': lecturer_count,
                    'courses': course_count
                },
                'requires_hod': dept.hod is None
            })
        
        return Response({
            'departments': dept_data,
            'total_departments': len(dept_data),
            'departments_without_hod': len([d for d in dept_data if d['hod']['id'] is None])
        })
    
    @action(detail=False, methods=['post'])
    def update_department(self, request):
        """Update department configuration"""
        department_id = request.data.get('department_id')
        updates = request.data.get('updates', {})
        
        if not department_id or not updates:
            return Response(
                {'error': 'department_id and updates are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            department = Department.objects.get(id=department_id)
            
            # Update department fields
            for field, value in updates.items():
                if hasattr(department, field) and field not in ['id', 'hod']:
                    setattr(department, field, value)
            
            # Handle HOD assignment
            if 'hod_id' in updates:
                try:
                    lecturer = Lecturer.objects.get(id=updates['hod_id'])
                    department.hod = lecturer
                    
                    # Update lecturer's is_hod status
                    lecturer.is_hod = True
                    lecturer.save()
                except Lecturer.DoesNotExist:
                    return Response(
                        {'error': 'Lecturer not found'},
                        status=status.HTTP_404_NOT_FOUND
                    )
            
            department.save()
            
            return Response({
                'message': f'Department {department.name} updated successfully',
                'department': {
                    'id': department.id,
                    'name': department.name,
                    'code': department.code,
                    'hod': department.hod.user.get_full_name() if department.hod else None
                }
            })
            
        except Department.DoesNotExist:
            return Response(
                {'error': 'Department not found'},
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=False, methods=['post'])
    def create_department(self, request):
        """Create new department"""
        name = request.data.get('name')
        code = request.data.get('code')
        
        if not name or not code:
            return Response(
                {'error': 'name and code are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Check if code already exists
        if Department.objects.filter(code=code).exists():
            return Response(
                {'error': f'Department code {code} already exists'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            department = Department.objects.create(
                name=name,
                code=code,
                description=request.data.get('description', '')
            )
            
            return Response({
                'message': f'Department {name} created successfully',
                'department': {
                    'id': department.id,
                    'name': department.name,
                    'code': department.code
                }
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            return Response(
                {'error': f'Failed to create department: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['get'])
    def system_logs(self, request):
        """Get system logs"""
        # Placeholder - implement log retrieval
        # This would query your logging system or AuditLog model
        
        logs = [
            {
                'timestamp': timezone.now() - timedelta(hours=1),
                'level': 'INFO',
                'message': 'System check completed',
                'user': 'system'
            },
            {
                'timestamp': timezone.now() - timedelta(hours=2),
                'level': 'WARNING',
                'message': 'High memory usage detected',
                'user': 'system'
            },
            {
                'timestamp': timezone.now() - timedelta(hours=3),
                'level': 'INFO',
                'message': 'User login: admin@example.com',
                'user': 'admin@example.com'
            }
        ]
        
        return Response({
            'logs': logs,
            'log_statistics': {
                'total_entries': 1000,  # Placeholder
                'errors_today': 2,
                'warnings_today': 5
            }
        })


# ==============================================
# MAIN ICT OFFICER API VIEW
# ==============================================

class ICTOfficerAPIView(APIView):
    """Main API view for ICT officer frontend integration"""
    permission_classes = [IsAuthenticated, IsICTOfficer]
    
    def get(self, request):
        """Get ICT officer's complete data for dashboard"""
        user = request.user
        
        # Get ICT officer profile
        ict_data = {
            'id': user.id,
            'name': user.get_full_name(),
            'email': user.email,
            'role': user.role,
            'phone': user.phone
        }
        
        # Get quick statistics
        quick_stats = {
            'total_users': User.objects.count(),
            'active_users': User.objects.filter(is_active=True).count(),
            'new_users_today': User.objects.filter(
                created_at__date=timezone.now().date()
            ).count(),
            'password_resets_today': 0  # Placeholder
        }
        
        # Get system status
        system_status = {
            'registration_active': Semester.objects.filter(
                is_current=True,
                is_registration_active=True
            ).exists(),
            'maintenance_mode': False,
            'last_backup': timezone.now() - timedelta(days=1)  # Placeholder
        }
        
        return Response({
            'ict_officer': ict_data,
            'quick_stats': quick_stats,
            'system_status': system_status
        })