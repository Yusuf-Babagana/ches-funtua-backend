from django.contrib import admin
from .models import (Department, Semester, Course, Enrollment, CourseRegistration,
CourseOffering, Grade)

admin.site.register(Department)
admin.site.register(Semester)
admin.site.register(Course)
admin.site.register(Enrollment)
admin.site.register(CourseRegistration)
admin.site.register(CourseOffering)
admin.site.register(Grade)
admin.site.site_header = "College CMS Admin"
admin.site.site_title = "College CMS Admin Portal"
