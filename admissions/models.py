from django.db import models
from django.core.validators import RegexValidator
import uuid

class Application(models.Model):
    """Student admission applications"""
    
    STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('under_review', 'Under Review'),
        ('shortlisted', 'Shortlisted'),
        ('admitted', 'Admitted'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
    ]
    
    PROGRAMME_CHOICES = [
        ('nce', 'NCE'),
        ('degree', 'Degree'),
        ('diploma', 'Diploma'),
        ('pgd', 'PGD'),
        ('masters', 'Masters'),
    ]
    
    # Application Details
    application_number = models.CharField(max_length=50, unique=True, editable=False)
    session = models.CharField(max_length=9)  # e.g., 2024/2025
    programme_type = models.CharField(max_length=20, choices=PROGRAMME_CHOICES)
    first_choice_department = models.ForeignKey(
        'academics.Department', 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='first_choice_applications'
    )
    second_choice_department = models.ForeignKey(
        'academics.Department', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='second_choice_applications'
    )
    
    # Personal Information
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    other_names = models.CharField(max_length=100, blank=True)
    email = models.EmailField()
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'."
    )
    phone = models.CharField(validators=[phone_regex], max_length=17)
    date_of_birth = models.DateField()
    gender = models.CharField(max_length=10, choices=[('male', 'Male'), ('female', 'Female')])
    nationality = models.CharField(max_length=100, default='Nigerian')
    state_of_origin = models.CharField(max_length=100)
    lga = models.CharField(max_length=100, verbose_name='LGA')
    address = models.TextField()
    
    # Guardian Information
    guardian_name = models.CharField(max_length=200)
    guardian_phone = models.CharField(validators=[phone_regex], max_length=17)
    guardian_email = models.EmailField(blank=True)
    guardian_relationship = models.CharField(max_length=50)
    
    # Academic Information
    olevel_results = models.JSONField(default=dict)  # Store O'Level results
    jamb_score = models.IntegerField(null=True, blank=True)
    previous_institution = models.CharField(max_length=200, blank=True)
    
    # Application Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')
    reviewed_by = models.ForeignKey(
        'users.User', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='applications_reviewed'
    )
    review_date = models.DateTimeField(null=True, blank=True)
    review_remarks = models.TextField(blank=True)
    
    # Documents
    passport_photo = models.ImageField(upload_to='applications/photos/', null=True, blank=True)
    birth_certificate = models.FileField(upload_to='applications/documents/', null=True, blank=True)
    olevel_certificate = models.FileField(upload_to='applications/documents/', null=True, blank=True)
    
    # Timestamps
    submitted_date = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-submitted_date']
        verbose_name = 'Application'
        verbose_name_plural = 'Applications'
    
    def __str__(self):
        return f"{self.application_number} - {self.first_name} {self.last_name}"
    
    def save(self, *args, **kwargs):
        if not self.application_number:
            self.application_number = f"APP-{uuid.uuid4().hex[:10].upper()}"
        super().save(*args, **kwargs)
    
    @property
    def full_name(self):
        if self.other_names:
            return f"{self.first_name} {self.other_names} {self.last_name}"
        return f"{self.first_name} {self.last_name}"


class AdmissionLetter(models.Model):
    """Admission letters for accepted students"""
    
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name='admission_letter')
    admission_number = models.CharField(max_length=50, unique=True)
    matric_number = models.CharField(max_length=20, unique=True)
    department = models.ForeignKey('academics.Department', on_delete=models.CASCADE)
    level = models.CharField(max_length=10, default='100')
    session = models.CharField(max_length=9)
    letter_content = models.TextField()
    issued_date = models.DateField(auto_now_add=True)
    issued_by = models.ForeignKey('users.User', on_delete=models.SET_NULL, null=True)
    is_downloaded = models.BooleanField(default=False)
    download_count = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-issued_date']
        verbose_name = 'Admission Letter'
        verbose_name_plural = 'Admission Letters'
    
    def __str__(self):
        return f"{self.admission_number} - {self.application.full_name}"


class AdmissionSession(models.Model):
    """Manage admission sessions"""
    
    session = models.CharField(max_length=9, unique=True)  # e.g., 2024/2025
    start_date = models.DateField()
    end_date = models.DateField()
    application_fee = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=False)
    max_applications = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-start_date']
        verbose_name = 'Admission Session'
        verbose_name_plural = 'Admission Sessions'
    
    def __str__(self):
        return f"{self.session} Admission"