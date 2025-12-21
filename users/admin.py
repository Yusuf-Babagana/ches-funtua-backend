from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Student, Lecturer, StaffProfile


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['email', 'username', 'first_name', 'last_name', 'role', 'is_active', 'created_at']
    list_filter = ['role', 'is_active', 'created_at']
    search_fields = ['email', 'username', 'first_name', 'last_name']
    ordering = ['-created_at']
    
    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'phone', 'profile_picture')}),
        ('Role & Permissions', {'fields': ('role', 'is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important Dates', {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'username', 'password1', 'password2', 'first_name', 'last_name', 'role'),
        }),
    )


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ['matric_number', 'get_full_name', 'level', 'department', 'status', 'admission_date']
    list_filter = ['level', 'status', 'department', 'admission_date']
    search_fields = ['matric_number', 'user__first_name', 'user__last_name', 'user__email']
    raw_id_fields = ['user', 'department']
    date_hierarchy = 'admission_date'
    
    def get_full_name(self, obj):
        return obj.user.get_full_name()
    get_full_name.short_description = 'Full Name'


@admin.register(Lecturer)
class LecturerAdmin(admin.ModelAdmin):
    list_display = ['staff_id', 'get_full_name', 'department', 'designation', 'is_hod']
    list_filter = ['designation', 'is_hod', 'department']
    search_fields = ['staff_id', 'user__first_name', 'user__last_name', 'specialization']
    raw_id_fields = ['user', 'department']
    
    def get_full_name(self, obj):
        return obj.user.get_full_name()
    get_full_name.short_description = 'Full Name'


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ['staff_id', 'get_full_name', 'position', 'department']
    list_filter = ['position', 'department']
    search_fields = ['staff_id', 'user__first_name', 'user__last_name', 'position']
    raw_id_fields = ['user']
    
    def get_full_name(self, obj):
        return obj.user.get_full_name()
    get_full_name.short_description = 'Full Name'