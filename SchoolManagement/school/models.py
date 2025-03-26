from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError

# School Model
class School(models.Model):
    id = models.CharField(max_length=12, primary_key=True)
    name = models.CharField(max_length=255)
    address = models.TextField()
    head = models.CharField(max_length=255)
    total_students = models.IntegerField()

    def __str__(self):
        return self.name

# Section Model
class Section(models.Model):
    grade = models.IntegerField()
    name = models.CharField(max_length=100)
    school = models.ForeignKey(School, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.name} - Grade {self.grade}"

# Custom User Model
class CustomUser(AbstractUser):
    profile_picture = models.ImageField(upload_to='profile_pictures/', blank=True, null=True)
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    is_principal = models.BooleanField(default=False)
    is_guard = models.BooleanField(default=False)
    is_teacher = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    is_pending = models.BooleanField(default=False)
    school = models.ForeignKey('School', on_delete=models.SET_NULL, null=True, blank=True)
    section = models.ForeignKey('Section', on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return self.username

    def get_profile_picture_url(self):
        if self.profile_picture:
            return self.profile_picture.url
        return '/media/default-profile-pic.jpg'

    def clean(self):
        super().clean()
        roles = [self.is_principal, self.is_guard, self.is_teacher]
        if sum(roles) > 1:
            raise ValidationError('Only one role (Principal, Guard, or Teacher) can be True.')
        if self.is_teacher and not self.section:
            raise ValidationError({'section': 'Section must be set for teachers.'})
        if not self.is_teacher and self.section:
            raise ValidationError({'section': 'Section can only be set for teachers.'})
        if any([self.is_principal, self.is_guard, self.is_teacher]) and not self.school:
            raise ValidationError({'school': 'School can only be set for principals, guards, and teachers.'})
        if not any([self.is_principal, self.is_guard, self.is_teacher]) and self.school:
            raise ValidationError({'school': 'School can only be set for principals, guards, and teachers.'})
        if self.is_superuser:
            self.is_principal = False
            self.is_guard = False
            self.is_teacher = False

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

# Student Model
class Student(models.Model):
    lrn = models.CharField(max_length=12, primary_key=True)  
    first_name = models.CharField(max_length=100)
    middle_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    section = models.ForeignKey(Section, on_delete=models.CASCADE)  # Linked to Section
    guardian = models.CharField(max_length=255)
    guardian_phone = models.CharField(max_length=15)
    guardian_email = models.EmailField()
    is_active = models.BooleanField(default=True)
    face_photo = models.ImageField(upload_to='media/student face/', blank=True, null=True)
    fingerprint_data = models.FileField(upload_to='media/student fingerprint/', blank=True, null=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.section.name}, Grade {self.section.grade}"

# Attendance Model
class Attendance(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE)
    date = models.DateField()
    time_in = models.TimeField(null=True)
    time_out = models.TimeField(null=True)

    def __str__(self):
        return f"Attendance for {self.student} on {self.date}"
