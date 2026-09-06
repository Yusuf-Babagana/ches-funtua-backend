from django.contrib import admin
from .models import (Department, Semester, Course, Enrollment, CourseRegistration,
CourseOffering, Grade, AcademicLevelConfiguration,
Program, Announcement, PracticalCenter, PracticalCenterSelection, IndexInformation)

admin.site.register(Department)
admin.site.register(Semester)
admin.site.register(Course)
admin.site.register(Enrollment)
admin.site.register(CourseRegistration)
admin.site.register(CourseOffering)
admin.site.register(Grade)
admin.site.register(AcademicLevelConfiguration)


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'program_type', 'duration_semesters', 'is_active']
    list_filter = ['program_type', 'is_active']
    search_fields = ['name', 'code']


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ['title', 'posted_by', 'department', 'level', 'is_pinned', 'created_at']
    list_filter = ['is_pinned', 'department', 'level']
    search_fields = ['title', 'body']
    raw_id_fields = ['posted_by']
    date_hierarchy = 'created_at'


@admin.register(PracticalCenter)
class PracticalCenterAdmin(admin.ModelAdmin):
    list_display = ['name', 'location', 'is_active']
    search_fields = ['name', 'location']


@admin.register(PracticalCenterSelection)
class PracticalCenterSelectionAdmin(admin.ModelAdmin):
    list_display = ['student', 'center', 'session', 'created_at']
    raw_id_fields = ['student']
    search_fields = ['student__matric_number']


@admin.register(IndexInformation)
class IndexInformationAdmin(admin.ModelAdmin):
    list_display = ['student', 'state_of_origin', 'submitted_at']
    raw_id_fields = ['student']
    search_fields = ['student__matric_number']


admin.site.site_header = "College CMS Admin"
admin.site.site_title = "College CMS Admin Portal"
