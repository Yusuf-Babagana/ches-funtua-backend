# apps/admissions/admin.py
from django.contrib import admin
from .models import Application, AdmissionLetter, AdmissionSession

@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ['application_number', 'full_name', 'email', 'programme_type', 'status', 'submitted_date']
    list_filter = ['status', 'programme_type', 'session', 'gender']
    search_fields = ['application_number', 'email', 'first_name', 'last_name', 'phone']
    raw_id_fields = ['first_choice_department', 'second_choice_department', 'reviewed_by']
    date_hierarchy = 'submitted_date'
    readonly_fields = ['application_number', 'submitted_date']

@admin.register(AdmissionLetter)
class AdmissionLetterAdmin(admin.ModelAdmin):
    list_display = ['admission_number', 'matric_number', 'application', 'department', 'session', 'issued_date']
    list_filter = ['session', 'level', 'department']
    search_fields = ['admission_number', 'matric_number', 'application__first_name', 'application__last_name']
    raw_id_fields = ['application', 'department', 'issued_by']
    date_hierarchy = 'issued_date'

@admin.register(AdmissionSession)
class AdmissionSessionAdmin(admin.ModelAdmin):
    list_display = ['session', 'start_date', 'end_date', 'application_fee', 'is_active']
    list_filter = ['is_active']
    date_hierarchy = 'start_date'