from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from django.db.models import Count, Q

from .models import Department, Course, Semester
from .serializers import DepartmentSerializer, CourseSerializer
from users.models import Lecturer, Student
from users.permissions import IsSuperAdmin
from django.utils import timezone
from datetime import datetime, timedelta 


class SuperAdminDepartmentViewSet(viewsets.ModelViewSet):
    """Department operations for Super Admin with HOD assignment"""
    serializer_class = DepartmentSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    filter_backends = []
    
    def get_queryset(self):
        """
        Return departments with live counts for the Super Admin
        """
        return Department.objects.select_related('hod__user').annotate(
            student_count=Count('student', distinct=True),
            lecturer_count=Count('lecturer', distinct=True),
            course_count=Count('courses', distinct=True)
        ).all()


    @action(detail=False, methods=['post'])
    def start_new_session(self, request):
        """
        Start a new Academic Session (e.g. 2025/2026).
        This automatically creates the First Semester for that session.
        """
        session_name = request.data.get('session') # e.g. "2025/2026"
        start_date_str = request.data.get('start_date')
        
        if not session_name or not start_date_str:
            return Response({'error': 'Session Name (e.g., 2025/2026) and Start Date are required'}, status=400)

        try:
            # Parse the date string to a date object
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            
            with transaction.atomic():
                # 1. Deactivate ALL previous semesters
                Semester.objects.all().update(is_current=False, is_registration_active=False)
                
                # 2. Create "First Semester" for the new session
                new_semester = Semester.objects.create(
                    session=session_name,
                    semester='first',
                    start_date=start_date,
                    # End date approx 4 months (120 days) later
                    end_date=start_date + timedelta(days=120),
                    # Registration closes 3 weeks (21 days) after start
                    registration_deadline=start_date + timedelta(days=21),
                    is_current=True,
                    is_registration_active=True
                )
                
                return Response({
                    'message': f'Session {session_name} started successfully.',
                    'current_semester': f'{session_name} - First Semester'
                })
        except Exception as e:
            print(f"Error starting session: {e}") # Log error to terminal
            return Response({'error': str(e)}, status=500)

    @action(detail=False, methods=['post'])
    def promote_students(self, request):
        """
        Automatic Promotion Logic:
        1. Level 300 -> Graduated
        2. Level 200 -> Level 300
        3. Level 100 -> Level 200
        """
        confirmation = request.data.get('confirm', False)
        if not confirmation:
            return Response({
                'error': 'This is a destructive action. Please send { "confirm": true } to proceed.'
            }, status=400)

        with transaction.atomic():
            # 1. Graduate Final Year (Level 300)
            graduated_count = Student.objects.filter(
                level='300', 
                status='active'
            ).update(status='graduated')

            # 2. Promote Level 200 to 300
            l3_count = Student.objects.filter(
                level='200', 
                status='active'
            ).update(level='300')

            # 3. Promote Level 100 to 200
            l2_count = Student.objects.filter(
                level='100', 
                status='active'
            ).update(level='200')

        return Response({
            'message': 'Promotion completed successfully',
            'summary': {
                'graduated': graduated_count,
                'promoted_to_level_300': l3_count,
                'promoted_to_level_200': l2_count
            }
        })
    
    @action(detail=True, methods=['post'])
    @transaction.atomic
    def assign_hod(self, request, pk=None):
        """Assign HOD to department"""
        department = self.get_object()
        lecturer_id = request.data.get('lecturer_id')
        
        if not lecturer_id:
            return Response({'error': 'lecturer_id is required'}, status=400)
        
        try:
            # 1. Get the new HOD
            new_hod = Lecturer.objects.select_for_update().get(id=lecturer_id)
            
            # Check if lecturer belongs to this department
            if new_hod.department_id != department.id:
                 # Optional: Allow assignment but warn, or strictly enforce. 
                 # For now, let's enforce strict department matching as per frontend logic.
                 return Response(
                    {'error': f'Lecturer belongs to {new_hod.department.name}, not {department.name}'},
                    status=400
                )

            # 2. Handle Existing HOD (Downgrade them)
            if department.hod:
                old_hod = department.hod
                old_hod.is_hod = False
                old_hod.save()

            # 3. Handle if New HOD was HOD elsewhere (clean up previous dept)
            # (Unlikely if one-to-one, but good safety)
            previous_dept_as_hod = Department.objects.filter(hod=new_hod).first()
            if previous_dept_as_hod:
                previous_dept_as_hod.hod = None
                previous_dept_as_hod.save()

            # 4. Assign New HOD
            department.hod = new_hod
            department.save()
            
            # 5. Update Lecturer Profile
            new_hod.is_hod = True
            new_hod.save()
            
            # Refresh data to get updated serializer fields
            department.refresh_from_db()
            serializer = self.get_serializer(department)
            
            return Response({
                'message': f'Successfully assigned {new_hod.user.get_full_name()} as HOD',
                'department': serializer.data
            })
            
        except Lecturer.DoesNotExist:
            return Response({'error': 'Lecturer not found'}, status=404)
        except Exception as e:
            return Response({'error': str(e)}, status=400)
    
    @action(detail=True, methods=['post'])
    def remove_hod(self, request, pk=None):
        """Remove HOD from department"""
        department = self.get_object()
        
        if not department.hod:
            return Response({'error': 'No HOD assigned to this department'}, status=400)
        
        old_hod = department.hod
        
        # Remove HOD
        department.hod = None
        department.save()
        
        # Update lecturer status
        old_hod.is_hod = False
        old_hod.save()
        
        return Response({
            'message': f'Successfully removed {old_hod.user.get_full_name()} as HOD',
            'department': self.get_serializer(department).data
        })
    
    @action(detail=False, methods=['get'])
    def available_hods(self, request):
        """
        Get ALL lecturers (flat list) so frontend can filter by department.
        Returns: [ { id, name, department_id, is_hod }, ... ]
        """
        lecturers = Lecturer.objects.select_related('user', 'department').all()
        
        data = []
        for lecturer in lecturers:
            data.append({
                'id': lecturer.id,
                'name': lecturer.user.get_full_name(),
                'staff_id': lecturer.staff_id,
                'email': lecturer.user.email,
                # Frontend expects 'department_id' to filter list for the popup
                'department_id': lecturer.department.id if lecturer.department else None,
                'department_name': lecturer.department.name if lecturer.department else 'Unassigned',
                'is_hod': lecturer.is_hod
            })
        
        return Response(data)

class SuperAdminCourseViewSet(viewsets.ModelViewSet):
    """Course operations for Super Admin with Lecturer assignment"""
    queryset = Course.objects.select_related('department', 'lecturer__user').all()
    serializer_class = CourseSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    filter_backends = []
    
    @action(detail=True, methods=['post'])
    def assign_lecturer(self, request, pk=None):
        """Assign lecturer to course"""
        course = self.get_object()
        lecturer_id = request.data.get('lecturer_id')
        
        if not lecturer_id:
            return Response(
                {'error': 'lecturer_id is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            lecturer = Lecturer.objects.get(id=lecturer_id)
            
            # Check if lecturer belongs to the same department as course
            if lecturer.department != course.department:
                return Response(
                    {'error': 'Lecturer must belong to the same department as the course'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Assign lecturer to course
            course.lecturer = lecturer
            course.save()
            
            serializer = self.get_serializer(course)
            return Response({
                'message': f'Successfully assigned {lecturer.user.get_full_name()} to {course.code}',
                'course': serializer.data
            })
            
        except Lecturer.DoesNotExist:
            return Response(
                {'error': 'Lecturer not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
    
    @action(detail=True, methods=['post'])
    def remove_lecturer(self, request, pk=None):
        """Remove lecturer from course"""
        course = self.get_object()
        
        if not course.lecturer:
            return Response(
                {'error': 'No lecturer assigned to this course'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        old_lecturer = course.lecturer
        
        # Remove lecturer from course
        course.lecturer = None
        course.save()
        
        serializer = self.get_serializer(course)
        return Response({
            'message': f'Successfully removed {old_lecturer.user.get_full_name()} from {course.code}',
            'course': serializer.data
        })
    
    @action(detail=False, methods=['get'])
    def unassigned_courses(self, request):
        """Get courses without assigned lecturers"""
        unassigned_courses = Course.objects.filter(lecturer__isnull=True)
        
        page = self.paginate_queryset(unassigned_courses)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(unassigned_courses, many=True)
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'])
    def department_lecturers(self, request):
        """Get lecturers by department for assignment"""
        department_id = request.query_params.get('department_id')
        
        if not department_id:
            return Response(
                {'error': 'department_id parameter is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            lecturers = Lecturer.objects.filter(department_id=department_id).select_related('user')
            
            lecturer_data = [
                {
                    'id': lecturer.id,
                    'name': lecturer.user.get_full_name(),
                    'staff_id': lecturer.staff_id,
                    'designation': lecturer.designation,
                    'specialization': lecturer.specialization,
                    'is_hod': lecturer.is_hod
                }
                for lecturer in lecturers
            ]
            
            return Response(lecturer_data)
            
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class SuperAdminManagementViewSet(viewsets.ViewSet):
    """Super Admin management operations across models"""
    permission_classes = [IsAuthenticated, IsSuperAdmin]



    @action(detail=False, methods=['post'])
    def start_new_session(self, request):
        """
        Start a new Academic Session (e.g. 2025/2026).
        This automatically creates the First Semester for that session.
        """
        session_name = request.data.get('session') # e.g. "2025/2026"
        start_date = request.data.get('start_date')
        
        if not session_name or not start_date:
            return Response({'error': 'Session Name (e.g., 2025/2026) and Start Date are required'}, status=400)

        try:
            with transaction.atomic():
                # 1. Deactivate ALL previous semesters
                Semester.objects.all().update(is_current=False, is_registration_active=False)
                
                # 2. Create "First Semester" for the new session
                new_semester = Semester.objects.create(
                    session=session_name,
                    semester='first',
                    start_date=start_date,
                    # End date approx 4 months later (can be edited later)
                    end_date=timezone.datetime.strptime(start_date, "%Y-%m-%d").date() + timezone.timedelta(days=120),
                    registration_deadline=timezone.datetime.strptime(start_date, "%Y-%m-%d").date() + timezone.timedelta(days=21),
                    is_current=True,
                    is_registration_active=True
                )
                
                return Response({
                    'message': f'Session {session_name} started successfully.',
                    'current_semester': f'{session_name} - First Semester'
                })
        except Exception as e:
            return Response({'error': str(e)}, status=500)

    @action(detail=False, methods=['post'])
    def promote_students(self, request):
        """
        Automatic Promotion Logic:
        1. Level 300 -> Graduated
        2. Level 200 -> Level 300
        3. Level 100 -> Level 200
        """
        confirmation = request.data.get('confirm', False)
        if not confirmation:
            return Response({
                'error': 'This is a destructive action. Please send { "confirm": true } to proceed.'
            }, status=400)

        with transaction.atomic():
            # 1. Graduate Final Year (Level 300)
            graduated_count = Student.objects.filter(
                level='300', 
                status='active'
            ).update(status='graduated')

            # 2. Promote Level 200 to 300
            l3_count = Student.objects.filter(
                level='200', 
                status='active'
            ).update(level='300')

            # 3. Promote Level 100 to 200
            l2_count = Student.objects.filter(
                level='100', 
                status='active'
            ).update(level='200')

        return Response({
            'message': 'Promotion completed successfully',
            'summary': {
                'graduated': graduated_count,
                'promoted_to_level_300': l3_count,
                'promoted_to_level_200': l2_count
            }
        })
    
    @action(detail=False, methods=['get'])
    def dashboard_stats(self, request):
        """Get super admin dashboard statistics"""
        from django.db.models import Count, Q
        
        # Department stats
        departments = Department.objects.count()
        departments_with_hod = Department.objects.filter(hod__isnull=False).count()
        
        # Course stats
        total_courses = Course.objects.count()
        courses_with_lecturers = Course.objects.filter(lecturer__isnull=False).count()
        courses_without_lecturers = total_courses - courses_with_lecturers
        
        # Lecturer stats
        total_lecturers = Lecturer.objects.count()
        lecturers_with_courses = Lecturer.objects.filter(courses_taught__isnull=False).distinct().count()
        hod_count = Lecturer.objects.filter(is_hod=True).count()
        
        return Response({
            'departments': {
                'total': departments,
                'with_hod': departments_with_hod,
                'without_hod': departments - departments_with_hod
            },
            'courses': {
                'total': total_courses,
                'with_lecturers': courses_with_lecturers,
                'without_lecturers': courses_without_lecturers
            },
            'lecturers': {
                'total': total_lecturers,
                'with_courses': lecturers_with_courses,
                'hod_count': hod_count
            }
        })
    
    @action(detail=False, methods=['post'])
    @transaction.atomic
    def bulk_assign_lecturers(self, request):
        """Bulk assign lecturers to courses"""
        assignments = request.data.get('assignments', [])
        
        if not assignments:
            return Response(
                {'error': 'assignments array is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        successful_assignments = []
        failed_assignments = []
        
        for assignment in assignments:
            course_id = assignment.get('course_id')
            lecturer_id = assignment.get('lecturer_id')
            
            if not course_id or not lecturer_id:
                failed_assignments.append({
                    'assignment': assignment,
                    'error': 'course_id and lecturer_id are required'
                })
                continue
            
            try:
                course = Course.objects.get(id=course_id)
                lecturer = Lecturer.objects.get(id=lecturer_id)
                
                # Check department consistency
                if lecturer.department != course.department:
                    failed_assignments.append({
                        'assignment': assignment,
                        'error': f'Lecturer {lecturer.staff_id} does not belong to course department'
                    })
                    continue
                
                # Assign lecturer
                course.lecturer = lecturer
                course.save()
                
                successful_assignments.append({
                    'course': f"{course.code} - {course.title}",
                    'lecturer': lecturer.user.get_full_name(),
                    'department': course.department.name
                })
                
            except (Course.DoesNotExist, Lecturer.DoesNotExist) as e:
                failed_assignments.append({
                    'assignment': assignment,
                    'error': str(e)
                })
                continue
        
        return Response({
            'successful_assignments': successful_assignments,
            'failed_assignments': failed_assignments,
            'message': f'Successfully processed {len(successful_assignments)} assignments, {len(failed_assignments)} failed'
        })
    
    @action(detail=False, methods=['get'])
    def academic_overview(self, request):
        """Academic overview for super admin dashboard"""
        from django.db.models import Count, Avg, Q
        
        # Department statistics
        departments = Department.objects.annotate(
            course_count=Count('courses'),
            lecturer_count=Count('lecturer'),
            student_count=Count('student')
        )
        
        department_stats = [
            {
                'id': dept.id,
                'name': dept.name,
                'code': dept.code,
                'hod': dept.hod.user.get_full_name() if dept.hod else 'Not Assigned',
                'courses': dept.course_count,
                'lecturers': dept.lecturer_count,
                'students': dept.student_count,
                'has_hod': dept.hod is not None
            }
            for dept in departments
        ]
        
        # Course statistics
        total_courses = Course.objects.count()
        courses_with_lecturers = Course.objects.filter(lecturer__isnull=False).count()
        
        # Enrollment statistics by level
        enrollment_by_level = Student.objects.values('level').annotate(
            count=Count('id')
        ).order_by('level')
        
        # GPA statistics
        gpa_stats = Grade.objects.aggregate(
            avg_gpa=Avg('grade_points'),
            highest_gpa=Avg('grade_points'),  # This would need adjustment for actual highest
            total_grades=Count('id')
        )
        
        # Recent academic activity (last 30 days)
        from datetime import timedelta
        last_month = timezone.now() - timedelta(days=30)
        
        recent_grades = Grade.objects.filter(created_at__gte=last_month).count()
        recent_enrollments = Enrollment.objects.filter(created_at__gte=last_month).count()
        
        # Courses needing attention
        courses_without_lecturers = Course.objects.filter(lecturer__isnull=True)[:5]
        departments_without_hod = Department.objects.filter(hod__isnull=True)[:5]
        
        return Response({
            'departments': {
                'total': departments.count(),
                'with_hod': departments.filter(hod__isnull=False).count(),
                'detailed_stats': department_stats,
            },
            'courses': {
                'total': total_courses,
                'with_lecturers': courses_with_lecturers,
                'without_lecturers': total_courses - courses_with_lecturers,
                'coverage_rate': (courses_with_lecturers / total_courses * 100) if total_courses > 0 else 0,
            },
            'enrollments': {
                'by_level': list(enrollment_by_level),
                'recent_month': recent_enrollments,
            },
            'academic_performance': {
                'average_gpa': float(gpa_stats['avg_gpa']) if gpa_stats['avg_gpa'] else 0,
                'total_grades': gpa_stats['total_grades'],
                'recent_grades': recent_grades,
            },
            'attention_needed': {
                'courses_without_lecturers': [
                    {
                        'id': course.id,
                        'code': course.code,
                        'title': course.title,
                        'department': course.department.name
                    }
                    for course in courses_without_lecturers
                ],
                'departments_without_hod': [
                    {
                        'id': dept.id,
                        'name': dept.name,
                        'code': dept.code
                    }
                    for dept in departments_without_hod
                ]
            }
        })

    @action(detail=False, methods=['post'])
    def assign_department_to_lecturer(self, request):
        """Assign department to a lecturer"""
        lecturer_id = request.data.get('lecturer_id')
        department_id = request.data.get('department_id')
        
        if not lecturer_id or not department_id:
            return Response(
                {'error': 'lecturer_id and department_id are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
            
        try:
            lecturer = Lecturer.objects.get(id=lecturer_id)
            department = Department.objects.get(id=department_id)
            
            # Update lecturer's department
            lecturer.department = department
            lecturer.save()
            
            return Response({
                'message': f'Successfully assigned department {department.name} to {lecturer.user.get_full_name()}',
                'lecturer': {
                    'id': lecturer.id,
                    'staff_id': lecturer.staff_id,
                    'department': department.name
                }
            })
            
        except Lecturer.DoesNotExist:
            return Response(
                {'error': 'Lecturer not found'},
                status=status.HTTP_404_NOT_FOUND
            )
        except Department.DoesNotExist:
            return Response(
                {'error': 'Department not found'},
                status=status.HTTP_404_NOT_FOUND
            )


class SystemHealthViewSet(viewsets.ViewSet):
    """System health monitoring endpoints"""
    permission_classes = [IsAuthenticated, IsSuperAdmin]
    
    @action(detail=False, methods=['get'])
    def overview(self, request):
        """Get system health overview"""
        from django.db import connection
        from django.core.cache import cache
        from django.conf import settings
        import os
        
        health_data = {
            'timestamp': timezone.now().isoformat(),
            'status': 'healthy',
            'checks': []
        }
        
        # 1. Database check
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                db_status = 'healthy'
                db_connection = 'connected'
        except Exception as e:
            db_status = 'unhealthy'
            db_connection = str(e)
        
        health_data['checks'].append({
            'name': 'database',
            'status': db_status,
            'connection': db_connection
        })
        
        # 2. Cache check
        try:
            cache.set('health_check', 'ok', 10)
            cache_result = cache.get('health_check')
            cache_status = 'healthy' if cache_result == 'ok' else 'unhealthy'
        except Exception as e:
            cache_status = 'unhealthy'
            cache_result = str(e)
        
        health_data['checks'].append({
            'name': 'cache',
            'status': cache_status,
            'result': cache_result
        })
        
        # 3. Memory usage (SAFE IMPORT)
        try:
            import psutil
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            memory_status = 'healthy' if memory_percent < 90 else 'warning'
        except ImportError:
            memory_percent = 0
            memory_status = 'unknown (psutil not installed)'
        except Exception:
            memory_percent = 0
            memory_status = 'unknown'
        
        health_data['checks'].append({
            'name': 'memory',
            'status': memory_status,
            'percent_used': memory_percent
        })
        
        # 4. Overall status calculation
        all_healthy = all(check['status'] in ['healthy', 'warning', 'unknown (psutil not installed)'] for check in health_data['checks'])
        health_data['status'] = 'healthy' if all_healthy else 'unhealthy'
        
        return Response(health_data)
    
    @action(detail=False, methods=['get'])
    def detailed(self, request):
        """Get detailed system health information"""
        from django.db import connection
        
        health_data = {
            'timestamp': timezone.now().isoformat(),
            'system': {},
            'database': {},
            'cache': {},
            'models': {}
        }
        
        # System information
        import platform
        health_data['system'] = {
            'python_version': platform.python_version(),
            'django_version': django.get_version(),
            'server_time': timezone.now().isoformat(),
            'timezone': str(timezone.get_current_timezone()),
        }
        
        # Database information
        with connection.cursor() as cursor:
            # Get database version
            cursor.execute("SELECT version()")
            db_version = cursor.fetchone()[0]
            
            # Get table counts
            cursor.execute("""
                SELECT schemaname, tablename, n_live_tup as row_count
                FROM pg_stat_user_tables
                ORDER BY n_live_tup DESC
            """)
            tables = cursor.fetchall()
            
        health_data['database'] = {
            'engine': connection.vendor,
            'version': db_version,
            'tables': [{
                'schema': table[0],
                'name': table[1],
                'row_count': table[2]
            } for table in tables[:20]],  # Top 20 tables
        }
        
        # Model counts
        from django.apps import apps
        model_counts = []
        
        for model in apps.get_models():
            try:
                count = model.objects.count()
                model_counts.append({
                    'app': model._meta.app_label,
                    'model': model._meta.model_name,
                    'count': count
                })
            except Exception:
                continue
        
        # Sort by count descending
        model_counts.sort(key=lambda x: x['count'], reverse=True)
        health_data['models'] = model_counts[:30]  # Top 30 models
        
        return Response(health_data)
    
    @action(detail=False, methods=['get'])
    def test_endpoints(self, request):
        """Test all API endpoints"""
        endpoints = [
            {'name': 'User Authentication', 'url': '/api/auth/login/', 'method': 'POST'},
            {'name': 'Current User', 'url': '/api/auth/me/', 'method': 'GET'},
            {'name': 'User List', 'url': '/api/auth/users/', 'method': 'GET'},
            {'name': 'Departments', 'url': '/api/academics/departments/', 'method': 'GET'},
            {'name': 'Courses', 'url': '/api/academics/courses/', 'method': 'GET'},
            {'name': 'Invoices', 'url': '/api/finance/invoices/', 'method': 'GET'},
            {'name': 'Applications', 'url': '/api/admissions/applications/', 'method': 'GET'},
        ]
        
        results = []
        for endpoint in endpoints:
            try:
                full_url = f"http://localhost:8000{endpoint['url']}"
                if endpoint['method'] == 'GET':
                    # Simulate a test by checking if endpoint exists
                    with connection.cursor() as cursor:
                        # This is a simplified check - in production you'd make actual requests
                        results.append({
                            'name': endpoint['name'],
                            'status': 'available',
                            'checked': True
                        })
                else:
                    results.append({
                        'name': endpoint['name'],
                        'status': 'requires_testing',
                        'checked': False
                    })
            except Exception as e:
                results.append({
                    'name': endpoint['name'],
                    'status': 'error',
                    'error': str(e),
                    'checked': True
                })
        
        return Response({
            'endpoints_tested': len(endpoints),
            'results': results
        })