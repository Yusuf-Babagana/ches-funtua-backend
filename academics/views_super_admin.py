# users/views_super_admin.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Count, Sum, Avg, Q
from django.utils import timezone
from datetime import datetime, timedelta

from users.models import User, Student, Lecturer, StaffProfile
# ✅ FIXED IMPORTS: Removed 'Registration', ensure 'CourseRegistration' is used
from academics.models import (
    Department, Course, CourseOffering, CourseRegistration, 
    Grade, Semester
)
from finance.models import Invoice, Payment
from admissions.models import Application
from users.permissions import IsSuperAdmin

class SuperAdminDashboardViewSet(viewsets.ViewSet):
    """Super Admin comprehensive dashboard"""
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    
    @action(detail=False, methods=['get'])
    def overview(self, request):
        """System-wide overview dashboard"""
        # User statistics
        total_users = User.objects.count()
        active_users = User.objects.filter(is_active=True).count()
        users_by_role = User.objects.values('role').annotate(count=Count('id')).order_by('-count')
        
        # Academic statistics
        departments = Department.objects.count()
        courses = Course.objects.count()
        students = Student.objects.count()
        lecturers = Lecturer.objects.count()
        
        # Finance statistics
        total_revenue = Payment.objects.filter(status='completed').aggregate(
            total=Sum('amount')
        )['total'] or 0
        
        # Admission statistics
        total_applications = Application.objects.count()
        admitted_students = Application.objects.filter(status='admitted').count()
        
        # System health
        current_semester = Semester.objects.filter(is_current=True).first()
        active_registrations = 0
        if current_semester:
            # ✅ FIXED: Used CourseRegistration
            active_registrations = CourseRegistration.objects.filter(
                course_offering__semester=current_semester,
                status='registered'
            ).count()
        
        return Response({
            'system': {
                'total_users': total_users,
                'active_users': active_users,
                'users_by_role': list(users_by_role),
                'system_uptime': self._get_system_uptime(),
                'last_backup': self._get_last_backup()
            },
            'academic': {
                'departments': departments,
                'courses': courses,
                'students': students,
                'lecturers': lecturers,
                'current_semester': current_semester.session if current_semester else 'Not set',
                'active_registrations': active_registrations
            },
            'finance': {
                'total_revenue': total_revenue,
                'pending_invoices': Invoice.objects.filter(status='pending').count(),
                'completed_payments': Payment.objects.filter(status='completed').count()
            },
            'admissions': {
                'total_applications': total_applications,
                'admitted_students': admitted_students,
                'admission_rate': (admitted_students / total_applications * 100) if total_applications > 0 else 0
            },
            'system_health': self._check_system_health(),
            'recent_activities': self._get_recent_activities()
        })
    
    def _get_system_uptime(self):
        """Get system uptime (simplified)"""
        # In production, use actual uptime monitoring
        return "24 days, 5 hours"
    
    def _get_last_backup(self):
        """Get last backup time"""
        # Implement backup tracking
        return (timezone.now() - timedelta(hours=6)).strftime('%Y-%m-%d %H:%M')
    
    def _check_system_health(self):
        """Check system health status"""
        checks = []
        
        # Check for departments without HOD
        depts_without_hod = Department.objects.filter(hod__isnull=True).count()
        if depts_without_hod > 0:
            checks.append({
                'check': 'Departments without HOD',
                'status': 'warning',
                'message': f'{depts_without_hod} departments have no HOD',
                'action': 'assign_hod'
            })
        
        # Check for courses without lecturers
        courses_without_lecturers = Course.objects.filter(lecturer__isnull=True).count()
        if courses_without_lecturers > 0:
            checks.append({
                'check': 'Courses without lecturers',
                'status': 'warning',
                'message': f'{courses_without_lecturers} courses have no lecturer',
                'action': 'assign_lecturers'
            })
        
        # Check for inactive super admins
        inactive_super_admins = User.objects.filter(
            role='super_admin',
            is_active=False
        ).count()
        if inactive_super_admins > 0:
            checks.append({
                'check': 'Inactive super admins',
                'status': 'warning',
                'message': f'{inactive_super_admins} super admins are inactive',
                'action': 'activate_super_admins'
            })
        
        # Check for departments with no courses
        depts_without_courses = Department.objects.filter(
            course__isnull=True
        ).count()
        if depts_without_courses > 0:
            checks.append({
                'check': 'Departments without courses',
                'status': 'warning',
                'message': f'{depts_without_courses} departments have no courses',
                'action': 'assign_courses'
            })
        
        return checks
    
    def _get_recent_activities(self):
        """Get recent activities (placeholder)"""
        # Ideally fetch from AuditLog
        return [
            {
                'action': 'User Login', 
                'details': 'admin@college.edu logged in', 
                'timestamp': timezone.now() - timedelta(minutes=5)
            },
            {
                'action': 'Course Created', 
                'details': 'CSC101 created by Registrar', 
                'timestamp': timezone.now() - timedelta(hours=2)
            }
        ]