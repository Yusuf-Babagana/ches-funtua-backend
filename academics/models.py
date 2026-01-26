from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from users.models import User, Student, Lecturer

class Department(models.Model):
    """Academic departments"""
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=10, unique=True)
    description = models.TextField(blank=True)
    hod = models.ForeignKey('users.Lecturer', on_delete=models.SET_NULL, null=True, blank=True, related_name='department_headed')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Department'
        verbose_name_plural = 'Departments'
    
    def __str__(self):
        return f"{self.code} - {self.name}"


class Course(models.Model):
    """Course model"""
    SEMESTER_CHOICES = [
        ('first', 'First Semester'),
        ('second', 'Second Semester'),
    ]
    
    LEVEL_CHOICES = [
        ('100', 'Level 1'),
        ('200', 'Level 2'),
        ('300', 'Level 3'),
    ]
    
    code = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    credits = models.IntegerField()
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name='courses')
    semester = models.CharField(max_length=10, choices=SEMESTER_CHOICES)
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES)
    lecturer = models.ForeignKey('users.Lecturer', on_delete=models.SET_NULL, null=True, blank=True, related_name='courses_taught')
    is_elective = models.BooleanField(default=False)
    prerequisites = models.ManyToManyField('self', symmetrical=False, blank=True, related_name='prerequisite_for')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['code']
        verbose_name = 'Course'
        verbose_name_plural = 'Courses'
    
    def __str__(self):
        return f"{self.code} - {self.title}"


class Semester(models.Model):
    """Academic semester/session management"""
    SEMESTER_CHOICES = [
        ('first', 'First Semester'),
        ('second', 'Second Semester'),
    ]
    
    session = models.CharField(max_length=9)  # e.g., 2024/2025
    semester = models.CharField(max_length=10, choices=SEMESTER_CHOICES)
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False)
    registration_deadline = models.DateField()
    is_registration_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-start_date']
        unique_together = ['session', 'semester']
        verbose_name = 'Semester'
        verbose_name_plural = 'Semesters'
    
    def __str__(self):
        return f"{self.session} - {self.get_semester_display()} Semester"
    
    def clean(self):
        # Ensure only one current semester exists
        if self.is_current:
            Semester.objects.filter(is_current=True).exclude(id=self.id).update(is_current=False)
            
    def save(self, *args, **kwargs):
        if self.is_current:
            Semester.objects.filter(is_current=True).exclude(id=self.id).update(is_current=False)
        super().save(*args, **kwargs)

# ✅ NEW MODEL: Handles Level-Specific Calendars
class AcademicLevelConfiguration(models.Model):
    LEVEL_CHOICES = [
        ('100', '100'),
        ('200', '200'),
        ('300', '300'),
    ]
    
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES, unique=True)
    current_semester = models.ForeignKey(Semester, on_delete=models.CASCADE, related_name='level_configs')
    is_registration_open = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['level']
        
    def __str__(self):
        return f"Level {self.level} Config ({self.current_semester})"


class CourseOffering(models.Model):
    """Courses offered in specific semesters"""
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='offerings')
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE, related_name='course_offerings')
    lecturer = models.ForeignKey('users.Lecturer', on_delete=models.SET_NULL, null=True, blank=True)
    capacity = models.IntegerField(default=50)
    enrolled_count = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['course', 'semester']
        verbose_name = 'Course Offering'
        verbose_name_plural = 'Course Offerings'
    
    def __str__(self):
        return f"{self.course.code} - {self.semester}"


class Enrollment(models.Model):
    """Student course enrollment (Finalized Record)"""
    STATUS_CHOICES = [
        ('enrolled', 'Enrolled'),
        ('completed', 'Completed'),
        ('dropped', 'Dropped'),
        ('failed', 'Failed'),
    ]

    student = models.ForeignKey('users.Student', on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    session = models.CharField(max_length=9)  # e.g., 2024/2025
    semester = models.CharField(max_length=10)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='enrolled')
    enrollment_date = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        unique_together = ['student', 'course', 'session', 'semester']
        verbose_name = 'Enrollment'
        verbose_name_plural = 'Enrollments'
    
    def __str__(self):
        return f"{self.student.matric_number} - {self.course.code}"


class Grade(models.Model):
    """Student grades with 4.0 GPA scale"""
    GRADE_CHOICES = [
        ('A', 'A (4.0)'),
        ('B', 'B (3.0)'),
        ('C', 'C (2.0)'),
        ('D', 'D (1.0)'),
        ('E', 'E'),
        ('F', 'F (0.0)'),
    ]

    # 5-Step Workflow Status
    RESULT_STATUS = [
        ('draft', 'Draft (Lecturer Only)'),
        ('submitted', 'Submitted (Waiting for HOD)'),
        ('hod_approved', 'Approved (Waiting for Exam Officer)'),
        ('verified', 'Verified (Waiting for Registrar)'),
        ('published', 'Published (Visible to Student)'),
    ]
    
    student = models.ForeignKey('users.Student', on_delete=models.CASCADE, related_name='grades')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='grades')
    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name='grade', null=True)
    
    # Score Components
    ca_score = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    exam_score = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    score = models.DecimalField(max_digits=5, decimal_places=2) # Total
    
    grade_letter = models.CharField(max_length=2, choices=GRADE_CHOICES)
    grade_points = models.DecimalField(max_digits=4, decimal_places=2, default=0.00)
    
    # Metadata
    session = models.CharField(max_length=20)
    semester = models.CharField(max_length=10)
    
    # Workflow
    uploaded_by = models.ForeignKey('users.Lecturer', on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=RESULT_STATUS, default='draft')
    
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['student', 'course', 'session', 'semester']
        verbose_name = 'Grade'
        verbose_name_plural = 'Grades'
    
    def __str__(self):
        return f"{self.student.matric_number} - {self.course.code}: {self.grade_letter}"
    
    def calculate_grade_points(self):
        """Calculate grade points based on 4.0 scale"""
        grade_point_map = {
            'A': 4.0, 'B': 3.0, 'C': 2.0, 'D': 1.0, 'E': 0.5, 'F': 0.0
        }
        return grade_point_map.get(self.grade_letter, 0.0)
    
    def calculate_grade_letter(self):
        """Calculate grade letter based on score"""
        if self.score >= 70: return 'A'
        elif self.score >= 60: return 'B'
        elif self.score >= 50: return 'C'
        elif self.score >= 45: return 'D'
        elif self.score >= 40: return 'E'
        else: return 'F'
    
    def save(self, *args, **kwargs):
        # Auto-calculate letter and points
        total = float(self.score)
        self.grade_letter = self.calculate_grade_letter()
        self.grade_points = self.calculate_grade_points()
        super().save(*args, **kwargs)


class CourseRegistration(models.Model):
    """Student course registration for specific semesters with approval workflow"""
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved_lecturer', 'Approved by Lecturer'),
        ('approved_exam_officer', 'Approved by Exam Officer'),
        ('registered', 'Registered'),
        ('rejected_lecturer', 'Rejected by Lecturer'),
        ('rejected_exam_officer', 'Rejected by Exam Officer'),
        ('dropped', 'Dropped'),
        ('completed', 'Completed'),
    ]
    
    student = models.ForeignKey('users.Student', on_delete=models.CASCADE, related_name='registrations')
    course_offering = models.ForeignKey(CourseOffering, on_delete=models.CASCADE, related_name='registrations')
    registration_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='pending')
    
    # Approval chain
    approved_by_lecturer = models.ForeignKey('users.Lecturer', on_delete=models.SET_NULL, null=True, blank=True, related_name='lecturer_approvals')
    approved_by_exam_officer = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='exam_officer_approvals')
    approved_date = models.DateTimeField(null=True, blank=True)
    
    # Payment Verification
    is_payment_verified = models.BooleanField(default=False)
    payment_verified_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_registrations')
    payment_verified_date = models.DateTimeField(null=True, blank=True)
    
    remarks = models.TextField(blank=True, null=True)
    rejection_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['student', 'course_offering'] # Prevent double registration for the same offering
        ordering = ['registration_date']
        verbose_name = 'Course Registration'
        verbose_name_plural = 'Course Registrations'
    
    def __str__(self):
        return f"{self.student.matric_number} - {self.course_offering.course.code}"
    
    @property
    def can_be_approved_by_lecturer(self):
        return self.status in ['pending', 'approved_lecturer']
    
    @property
    def can_be_approved_by_exam_officer(self):
        return self.status == 'approved_lecturer' and self.is_payment_verified
    
    def verify_payment(self, user):
        """Verify payment for this registration"""
        current_semester = Semester.objects.filter(is_current=True).first()
        if not current_semester:
            return False
        
        try:
            from finance.models import Invoice
            invoice = Invoice.objects.get(
                student=self.student,
                session=current_semester.session,
                semester=current_semester.semester
            )
            # Check if PAID
            if invoice.status == 'paid':
                self.is_payment_verified = True
                self.payment_verified_by = user
                self.payment_verified_date = timezone.now()
                self.save()
                return True
        except Invoice.DoesNotExist:
            pass
        return False

    def approve_by_lecturer(self, lecturer):
        if self.can_be_approved_by_lecturer:
            self.status = 'approved_lecturer'
            self.approved_by_lecturer = lecturer
            self.save()
            return True
        return False
    
    def reject_by_lecturer(self, user, reason):
        if self.status == 'pending':
            self.status = 'rejected_lecturer'
            self.approved_by_lecturer = user # Still log who rejected
            self.rejection_reason = reason
            self.save()
            return True
        return False

    def approve_by_exam_officer(self, exam_officer):
        if self.can_be_approved_by_exam_officer:
            self.status = 'registered' # Final state
            self.approved_by_exam_officer = exam_officer
            self.approved_date = timezone.now()
            self.save()
            # Update enrolled count
            self.course_offering.enrolled_count = CourseRegistration.objects.filter(
                course_offering=self.course_offering,
                status='registered'
            ).count()
            self.course_offering.save()
            return True
        return False
        
    def reject_by_exam_officer(self, user, reason):
        if self.status == 'approved_lecturer':
            self.status = 'rejected_exam_officer'
            self.approved_by_exam_officer = user
            self.rejection_reason = reason
            self.save()
            return True
        return False

    def clean(self):
        errors = []
        if not self.check_prerequisites():
            errors.append(ValidationError("Prerequisites not met"))
        if self.course_offering.enrolled_count >= self.course_offering.capacity:
            errors.append(ValidationError("Course capacity reached"))
        if errors:
            raise ValidationError(errors)
    
    def check_prerequisites(self):
        course = self.course_offering.course
        prerequisites = course.prerequisites.all()
        if not prerequisites:
            return True
        for prereq in prerequisites:
            passed = Grade.objects.filter(
                student=self.student,
                course=prereq,
                grade_letter__in=['A', 'B', 'C', 'D']
            ).exists()
            if not passed:
                return False
        return True
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


class StudentAcademicRecord(models.Model):
    """Student academic record for GPA calculation"""
    LEVEL_CHOICES = [
        ('100', 'Level 1'),
        ('200', 'Level 2'), 
        ('300', 'Level 3'),
    ]
    
    student = models.ForeignKey('users.Student', on_delete=models.CASCADE, related_name='academic_records')
    level = models.CharField(max_length=10, choices=LEVEL_CHOICES)
    session = models.CharField(max_length=9)
    semester = models.CharField(max_length=20)
    total_credits = models.IntegerField(default=0)
    total_grade_points = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    gpa = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    cgpa = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['student', 'level', 'session', 'semester']
        verbose_name = 'Student Academic Record'
        verbose_name_plural = 'Student Academic Records'
    
    def calculate_gpa(self):
        grades = Grade.objects.filter(
            student=self.student,
            semester=self.semester,
            session=self.session
        )
        total_points = 0
        total_credits = 0
        for grade in grades:
            total_points += float(grade.grade_points) * grade.course.credits
            total_credits += grade.course.credits
        return round(total_points / total_credits, 2) if total_credits > 0 else 0.0
    
    def calculate_cgpa(self):
        all_grades = Grade.objects.filter(
            student=self.student,
            session__lte=self.session
        )
        total_points = 0
        total_credits = 0
        for grade in all_grades:
            total_points += float(grade.grade_points) * grade.course.credits
            total_credits += grade.course.credits
        return round(total_points / total_credits, 2) if total_credits > 0 else 0.0
    
    def save(self, *args, **kwargs):
        self.gpa = self.calculate_gpa()
        self.cgpa = self.calculate_cgpa()
        super().save(*args, **kwargs)


class Attendance(models.Model):
    """Attendance tracking"""
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
        ('late', 'Late'),
        ('excused', 'Excused'),
    ]
    
    student = models.ForeignKey('users.Student', on_delete=models.CASCADE, related_name='attendances')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='attendances')
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    marked_by = models.ForeignKey('users.Lecturer', on_delete=models.SET_NULL, null=True)
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date']
        unique_together = ['student', 'course', 'date']
        verbose_name = 'Attendance'
        verbose_name_plural = 'Attendances'
    
    def __str__(self):
        return f"{self.student.matric_number} - {self.course.code} - {self.date}"


# --- NEW MODELS ---

class StudentDocument(models.Model):
    """Model for student document uploads and verification"""
    DOCUMENT_TYPES = [
        ('birth_certificate', 'Birth Certificate'),
        ('o_level', 'O\'Level Result'),
        ('jamb_result', 'JAMB Result'),
        ('jamb_admission', 'JAMB Admission Letter'),
        ('local_government', 'Local Government Certificate'),
        ('medical_report', 'Medical Report'),
        ('passport_photo', 'Passport Photograph'),
        ('acceptance_fee', 'Acceptance Fee Receipt'),
        ('school_fees', 'School Fees Receipt'),
        ('other', 'Other Document'),
    ]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
        ('requires_update', 'Requires Update'),
    ]
    
    student = models.ForeignKey('users.Student', on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=50, choices=DOCUMENT_TYPES)
    document_name = models.CharField(max_length=200)
    document_file = models.FileField(upload_to='student_documents/%Y/%m/%d/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    remarks = models.TextField(blank=True, null=True)
    verified_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_documents')
    verified_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Student Document'
        verbose_name_plural = 'Student Documents'
    
    def __str__(self):
        return f"{self.student.matric_number} - {self.get_document_type_display()}"
    
    def save(self, *args, **kwargs):
        if self.status == 'verified' and not self.verified_at:
            self.verified_at = timezone.now()
        super().save(*args, **kwargs)


class StudentQuery(models.Model):
    """Model for student queries/complaints"""
    QUERY_TYPES = [
        ('registration', 'Registration Issue'),
        ('payment', 'Payment Issue'),
        ('document', 'Document Upload Issue'),
        ('course', 'Course Registration'),
        ('result', 'Result Issue'),
        ('personal_info', 'Personal Information'),
        ('other', 'Other Issue'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]
    
    student = models.ForeignKey('users.Student', on_delete=models.CASCADE, related_name='queries')
    query_type = models.CharField(max_length=50, choices=QUERY_TYPES)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')
    subject = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    resolution_notes = models.TextField(blank=True, null=True)
    assigned_to = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_queries')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_queries')
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Student Query'
        verbose_name_plural = 'Student Queries'
    
    def __str__(self):
        return f"{self.student.matric_number} - {self.subject}"
    
    def save(self, *args, **kwargs):
        if self.status == 'resolved' and not self.resolved_at:
            self.resolved_at = timezone.now()
        super().save(*args, **kwargs)


class EmergencyRegistration(models.Model):
    """Model for emergency/override registrations"""
    student = models.ForeignKey('users.Student', on_delete=models.CASCADE, related_name='emergency_registrations')
    semester = models.ForeignKey(Semester, on_delete=models.CASCADE)
    reason = models.TextField()
    approved_by = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='approved_emergency_regs')
    approved_at = models.DateTimeField(auto_now_add=True)
    is_approved = models.BooleanField(default=False)
    remarks = models.TextField(blank=True, null=True)
    registration_data = models.JSONField(default=dict)
    
    class Meta:
        ordering = ['-approved_at']
        verbose_name = 'Emergency Registration'
        verbose_name_plural = 'Emergency Registrations'
        unique_together = ['student', 'semester']
    
    def __str__(self):
        return f"Emergency Reg - {self.student.matric_number} - {self.semester}"