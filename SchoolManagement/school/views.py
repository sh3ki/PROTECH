import atexit
import datetime
import logging
import os
import shutil
import uuid
import csv
from functools import wraps

import cv2
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.mail import send_mail
from django.db import IntegrityError
from django.db.models import Max, Q, Sum
from django.http import (HttpResponse, HttpResponseForbidden,
                         HttpResponseRedirect, JsonResponse,
                         StreamingHttpResponse)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.timezone import localtime
import base64

from . import forms, models
from .models import School, CustomUser, Student, Section, Attendance

from .utils import generate_frames
# Import face recognition functions from the new module
from .face_recognition import (
    load_student_face_encodings, webcam_feed, stop_webcam, update_attendance_record
)

# Initialize logging
logger = logging.getLogger(__name__)

# Global variable to store recently recognized students
recently_recognized_students = []

# Add a temporary in-memory storage for face images
face_image_storage = {}  # key: "{student_lrn}-{date}", value: base64 image data

# Add a new function to get recognized students
def get_recognized_students(request):
    """API endpoint that returns all students with attendance records for today"""
    # Get the attendance mode (time-in or time-out)
    mode = request.GET.get('mode', 'time-in')
    
    # Get current date to filter for today's records only
    current_date = localtime().date()
    
    # Query all attendance records for today directly from the database
    today_attendance = Attendance.objects.filter(date=current_date).select_related('student__section')
    
    # Filter based on mode - only include records with the relevant field populated
    if mode == 'time-in':
        today_attendance = today_attendance.exclude(time_in__isnull=True)
    else:  # mode == 'time-out'
        today_attendance = today_attendance.exclude(time_out__isnull=True)
    
    # Sort by time_in or time_out (depending on mode) - most recent first
    if mode == 'time-in':
        today_attendance = today_attendance.order_by('-time_in')
    else:
        today_attendance = today_attendance.order_by('-time_out')
    
    # Format the data for the frontend
    students_list = []
    for attendance in today_attendance:
        student = attendance.student
        
        # Format time values
        time_in = attendance.time_in.strftime("%H:%M:%S") if attendance.time_in else None
        time_out = attendance.time_out.strftime("%H:%M:%S") if attendance.time_out else None
        
        # Generate a unique entry ID
        entry_id = f"{student.lrn}-{current_date}"
        
        # Check for file-based image first
        image_filename = f"{current_date.strftime('%Y-%m-%d')}_{student.lrn}.jpg"
        
        # Determine which folder to look in based on mode
        if mode == 'time-in':
            image_path = os.path.join('student_image_time_in', image_filename)
        else:
            image_path = os.path.join('student_image_time_out', image_filename)
            
        # Check if the file exists in media directory
        full_path = os.path.join(settings.MEDIA_ROOT, image_path)
        
        face_image_b64 = None
        face_image_url = None
        
        if os.path.exists(full_path):
            # File exists, use its URL
            face_image_url = f"/media/{image_path}"
            
            # Also load it as base64 for backward compatibility
            with open(full_path, 'rb') as img_file:
                face_image_b64 = base64.b64encode(img_file.read()).decode('utf-8')
        else:
            # Fall back to in-memory storage
            face_image_b64 = face_image_storage.get(entry_id)
        
        students_list.append({
            "first_name": student.first_name,
            "middle_initial": student.middle_name[0] + "." if student.middle_name else "",
            "last_name": student.last_name,
            "lrn": student.lrn,
            "section_grade": student.section.grade if student.section else "Unknown",
            "section_name": student.section.name if student.section else "Unknown",
            "image_url": student.face_photo.url if student.face_photo else "/static/images/default_user.png",
            "attendance_time_in": time_in,
            "attendance_time_out": time_out,
            "record_date": str(current_date),
            "timestamp": time_in if mode == 'time-in' else time_out,
            "face_image_b64": face_image_b64,  # Keep for backward compatibility
            "face_image_url": face_image_url,  # New field for file-based images
            "entry_id": entry_id
        })
    
    return JsonResponse({'students': students_list})

#-----------------
# ROLE DECORATORS
#-----------------

def supervisor_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_superuser:
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden("You do not have supervisor access.")
    return _wrapped_view

def admin_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_principal or request.user.is_guard:
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden("You do not have admin access.")
    return _wrapped_view

def teacher_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if request.user.is_teacher:
            return view_func(request, *args, **kwargs)
        return HttpResponseForbidden("You do not have teacher access.")
    return _wrapped_view

#----------------
# LANDING & LOGIN
#----------------

def front_camera_view(request):
    """Main landing page for the front-camera"""
    # Always set to disabled on GET requests (page load/refresh)
    if request.method == "GET":
        request.session['face_recognition_enabled'] = False
        
    # For POST requests, update based on checkbox
    if request.method == "POST":
        face_recognition_enabled = 'face_recognition' in request.POST
        request.session['face_recognition_enabled'] = face_recognition_enabled
        logger.info(f"Face recognition setting updated: {face_recognition_enabled}")

    # Get current setting
    face_recognition_enabled = request.session.get('face_recognition_enabled', False)
    
    # Only load student face encodings if enabled
    if face_recognition_enabled:
        from .face_recognition import load_student_face_encodings, student_names
        if len(student_names) == 0:
            logger.info("Loading student face encodings from landing page")
            load_student_face_encodings()
        
    return render(request, 'system/front_camera.html', {'face_recognition_enabled': face_recognition_enabled})

def supervisor_login_view(request):
    """Login view for supervisors"""
    # Redirect already logged-in users to their dashboard
    if request.user.is_authenticated:
        return redirect('afterlogin')
    
    error_message = None
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_superuser:  
                login(request, user)
                return HttpResponseRedirect('afterlogin')
            else:
                error_message = "You do not have supervisor access."
        else:
            error_message = "Invalid username or password. Please try again."
    
    context = {
        'title': 'SUPERVISOR',
        'form_action': '/supervisor-login',  # Keep consistent with URL pattern
        'error_message': error_message,
        'show_register': False,
        'next_url': 'supervisor-login'  
    }
    return render(request, 'system/login.html', context)

def admin_login_view(request):
    """Login view for administrators (principals and guards)"""
    # Redirect already logged-in users to their dashboard
    if request.user.is_authenticated:
        return redirect('afterlogin')
    
    error_message = None
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_principal or user.is_guard:
                login(request, user)
                return HttpResponseRedirect('afterlogin')
            else:
                error_message = "You do not have admin access."
        else:
            error_message = "Invalid username or password. Please try again."
    
    context = {
        'title': 'ADMIN',
        'form_action': '/admin-login',
        'error_message': error_message,
        'show_register': True,
        'next_url': 'admin-login'
    }
    return render(request, 'system/login.html', context)

def teacher_login_view(request):
    """Login view for teachers"""
    # Redirect already logged-in users to their dashboard
    if request.user.is_authenticated:
        return redirect('afterlogin')
    
    error_message = None
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            if user.is_teacher:
                login(request, user)
                return HttpResponseRedirect('afterlogin')
            else:
                error_message = "You do not have teacher access."
        else:
            error_message = "Invalid username or password. Please try again."
    
    context = {
        'title': 'TEACHER',
        'form_action': '/teacher-login',
        'error_message': error_message,
        'show_register': True,
        'next_url': 'teacher-login'
    }
    return render(request, 'system/login.html', context)

def logout_view(request):
    """Handle user logout and redirect to landing page"""
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect('/')

@login_required
def afterlogin_view(request):
    """Redirect users to their appropriate dashboard after login"""
    if request.user.is_superuser:
        return redirect('supervisor-dashboard')
    elif request.user.is_principal or request.user.is_guard:
        return redirect('admin-dashboard')
    elif request.user.is_teacher:
        return redirect('teacher-dashboard')
    else:
        logout(request)
        messages.error(request, "You do not have permission to access the system.")
        return redirect('/')

#----------------
# REGISTRATION
#----------------

def register_form_view(request):
    """User registration form view"""
    if request.method == 'POST':
        profile_pic = request.FILES.get('profile_pic')
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        first_name = request.POST.get('first_name')
        middle_name = request.POST.get('middle_name')
        last_name = request.POST.get('last_name')
        role = request.POST.get('role')
        section_id = request.POST.get('section') 
        school = request.POST.get('school')
        next_url = request.POST.get('next')
        
        # Check school
        try:
            school_obj = School.objects.get(name=school)
        except School.DoesNotExist:
            messages.error(request, "The selected school does not exist.")
            return redirect(request.META.get('HTTP_REFERER', 'register-form'))

        # Section handling
        section = None
        if role == 'teacher':
            section_id = request.POST.get('section')
            if not section_id:
                messages.error(request, "Section must be selected for teachers.")
                return redirect(request.META.get('HTTP_REFERER', 'register-form'))
            try:
                section = Section.objects.get(id=section_id)
            except Section.DoesNotExist:
                messages.error(request, "The selected section does not exist.")
                return redirect(request.META.get('HTTP_REFERER', 'register-form'))

        # Password match check
        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return redirect(request.META.get('HTTP_REFERER', 'register-form'))

        try:
            user = CustomUser(
                username=username,
                email=email,
                first_name=first_name,
                middle_name=middle_name,
                last_name=last_name,
                profile_picture=profile_pic,
                school=school_obj,
                section=section,
                is_principal=(role == 'principal'),
                is_guard=(role == 'guard'),
                is_teacher=(role == 'teacher'),
            )
            user.set_password(password)
            user.save()
            messages.success(request, "Registration successful!")
            return redirect(next_url or 'register-form')
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            return redirect(request.META.get('HTTP_REFERER', 'register-form'))

    # GET request - show registration form
    schools = School.objects.all()
    sections = Section.objects.all()
    return render(request, 'system/register_form.html', {'schools': schools, 'sections': sections})

#----------------------
# SUPERVISOR VIEWS
#----------------------

@login_required
@supervisor_required
def supervisor_dashboard_view(request):
    """Dashboard view for supervisors"""
    total_schools = School.objects.count()
    total_admins = CustomUser.objects.filter(Q(is_principal=True) | Q(is_guard=True)).count()
    total_teachers = CustomUser.objects.filter(is_teacher=True).count()
    total_students = Student.objects.count()
    total_attendance = Attendance.objects.count()

    context = {
        'user_role': 'supervisor',
        'total_schools': total_schools,
        'total_admins': total_admins,
        'total_teachers': total_teachers,
        'total_students': total_students,
        'total_attendance': total_attendance
    }
    return render(request, 'system/dashboard.html', context)

@login_required
@supervisor_required
def supervisor_schools_view(request):
    """View for supervisors to manage schools"""
    schools = School.objects.all()
    return render(request, 'system/supervisor_schools.html', {'schools': enumerate(schools, start=1)})

@login_required
@supervisor_required
def add_school_view(request):
    """View to add a new school"""
    if request.method == 'POST':
        school_id = request.POST.get('school_id')
        school_name = request.POST.get('school_name')
        school_address = request.POST.get('school_address')
        school_head = request.POST.get('school_head')
        total_students = request.POST.get('total_students')

        new_school = School(
            id=school_id,
            name=school_name,
            address=school_address,
            head=school_head,
            total_students=total_students
        )
        new_school.save()
        return redirect('supervisor-schools')
    
    return render(request, 'supervisor_schools.html')

@login_required
@supervisor_required
def edit_school_view(request, id):
    """View to edit an existing school"""
    school = get_object_or_404(School, id=id)
    
    if request.method == 'POST':
        school.name = request.POST.get('school_name')
        school.address = request.POST.get('school_address')
        school.head = request.POST.get('school_head')
        school.total_students = request.POST.get('total_students')
        school.save()
        
        messages.success(request, 'School updated successfully!')
        return redirect('supervisor-schools')
    
    return render(request, 'system/supervisor_schools.html', {'school': school})

@login_required
@supervisor_required
def delete_school_view(request, id):
    """View to delete a school"""
    school = get_object_or_404(School, id=id)
    school.delete()
    return redirect('supervisor-schools')

@login_required
@supervisor_required
def supervisor_admins_view(request):
    """View for supervisors to manage administrators"""
    admins = CustomUser.objects.filter(Q(is_principal=True) | Q(is_guard=True))
    schools = School.objects.all() 
    return render(request, 'system/supervisor_admins.html', {
        'admins': admins,
        'schools': schools,
    })

@login_required
@supervisor_required
def add_admin_view(request):
    """View to add a new administrator"""
    if request.method == 'POST':
        first_name = request.POST['first_name']
        middle_name = request.POST.get('middle_name', '')
        last_name = request.POST['last_name']
        school_id = request.POST['school']
        role = request.POST.get('role')
        email = request.POST['email']
        username = request.POST['username']
        password = request.POST['password']
        
        is_principal = role == 'principal'
        is_guard = role == 'guard'
        school = School.objects.get(id=school_id)
        
        admin = CustomUser(
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            school=school,
            email=email,
            username=username,
            is_principal=is_principal,
            is_guard=is_guard
        )
        admin.set_password(password)
        admin.save()
        
        messages.success(request, 'Admin added successfully!')
        return redirect('supervisor-admins')

    return render(request, 'system/supervisor-admins.html')

@login_required
@supervisor_required
def supervisor_teachers_view(request):
    """View for supervisors to manage teachers"""
    teachers = CustomUser.objects.filter(is_teacher=True)
    grades = range(7, 13)  # Grades 7 to 12
    sections = Section.objects.all()
    students = Student.objects.all()
    schools = School.objects.all()
    return render(request, 'system/teachers.html', {
        'user_role': 'supervisor',
        'teachers': teachers,
        'grades': grades,
        'sections': sections,
        'students': students,
        'schools': schools
    })

@login_required
@supervisor_required
def supervisor_students_view(request):
    """View for supervisors to manage students"""
    grades = range(7, 13)
    sections = Section.objects.all()
    students = Student.objects.select_related('section__school').all()
    schools = School.objects.all()
    return render(request, 'system/students.html', {
        'user_role': 'supervisor',
        'grades': grades,
        'sections': sections,
        'students': students,
        'schools': schools
    })

@login_required
@supervisor_required
def add_student_view(request):
    """View to add a new student"""
    if request.method == "POST":
        student_lrn = request.POST.get('student_lrn')
        first_name = request.POST.get('first_name')
        middle_name = request.POST.get('middle_name', '')  
        last_name = request.POST.get('last_name')
        grade = request.POST.get('grade')
        section_id = request.POST.get('section')
        guardian = request.POST.get('guardian')
        guardian_phone = request.POST.get('guardian_phone')
        guardian_email = request.POST.get('guardian_email')
        face_photo = request.FILES.get('face_photo')

        if section_id:
            try:
                section = Section.objects.get(id=section_id)
            except Section.DoesNotExist:
                messages.error(request, "Invalid section selected.")
                return redirect('supervisor-students')
        else:
            messages.error(request, "Section is required.")
            return redirect('supervisor-students')

        student = Student.objects.create(
            lrn=student_lrn,
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            section=section,  
            guardian=guardian,
            guardian_phone=guardian_phone,
            guardian_email=guardian_email,
            face_photo=face_photo if face_photo else None
        )

        # Move the photo from temp to final folder
        temp_folder = os.path.join(settings.MEDIA_ROOT, 'student_temp')
        final_folder = os.path.join(settings.MEDIA_ROOT, 'student_face')
        temp_path = os.path.join(temp_folder, f'{student_lrn}.jpg')
        final_path = os.path.join(final_folder, f'{student_lrn}.jpg')

        if os.path.exists(temp_path):
            os.makedirs(final_folder, exist_ok=True)
            shutil.move(temp_path, final_path)
            
            # Add just the new student's face encoding instead of reloading all encodings
            from .face_recognition import add_student_face_encoding
            add_student_face_encoding(student_lrn)
        else:
            # If no face image was provided, just log it
            logger.warning(f"No face image provided for student {student_lrn}")

        messages.success(request, 'Student added successfully!')
        return redirect('supervisor-students')

    return render(request, 'system/supervisor-students.html')

@login_required
@supervisor_required
def edit_student_view(request, lrn):
    """View to edit an existing student"""
    student = get_object_or_404(Student, lrn=lrn)
    
    if request.method == 'POST':
        student.first_name = request.POST.get('first_name')
        student.middle_name = request.POST.get('middle_name')
        student.last_name = request.POST.get('last_name')
        student.guardian_email = request.POST.get('email')
        
        section_id = request.POST.get('section')
        if section_id:
            try:
                section = Section.objects.get(id=section_id)
                student.section = section
            except Section.DoesNotExist:
                messages.error(request, "Invalid section selected.")
                return redirect('supervisor-students')
        
        student.save()
        messages.success(request, 'Student updated successfully!')
        return redirect('supervisor-students')
    
    return render(request, 'system/edit_student.html', {'student': student})

@login_required
@supervisor_required
def delete_student_view(request, lrn):
    """View to delete a student"""
    student = get_object_or_404(Student, lrn=lrn)
    student.delete()
    return redirect('supervisor-students')

def upload_temp_photo(request):
    """Handle the temporary photo upload for students"""
    if request.method == 'POST' and request.FILES.get('face_photo'):
        face_photo = request.FILES['face_photo']
        lrn = request.POST.get('student_lrn')
        filename = f"{lrn}.jpg"
        final_folder = os.path.join(settings.MEDIA_ROOT, 'student_temp')
        final_path = os.path.join(final_folder, filename)

        # Ensure the directory exists
        os.makedirs(final_folder, exist_ok=True)

        with open(final_path, 'wb') as f:
            for chunk in face_photo.chunks():
                f.write(chunk)
        
        return JsonResponse({'message': 'Image uploaded successfully', 'file_path': f"/media/student_temp/{filename}"})
    return JsonResponse({'error': 'No file uploaded'}, status=400)

@login_required
@supervisor_required
def supervisor_attendance_view(request):
    """View for supervisors to manage attendance records"""
    attendances = Attendance.objects.select_related('student__section__school').all()
    students = Student.objects.select_related('section__school').all()

    if request.method == "POST":
        student_id = request.POST.get("student")
        time_in = request.POST.get("time_in")
        time_out = request.POST.get("time_out")
        status = request.POST.get("status")

        if not student_id:
            messages.error(request, "Please select a student.")
            return redirect('supervisor-attendance')

        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            messages.error(request, "Student not found!")
            return redirect("supervisor-attendance")

        # Convert time strings to datetime properly
        try:
            time_in_obj = datetime.datetime.strptime(time_in, "%H:%M").time() if time_in else None
            time_out_obj = datetime.datetime.strptime(time_out, "%H:%M").time() if time_out else None
        except ValueError:
            messages.error(request, "Invalid time format. Use HH:MM format.")
            return redirect("supervisor-attendance")

        # Create attendance record
        attendance = Attendance.objects.create(
            student=student,
            time_in=time_in_obj,
            time_out=time_out_obj,
            status=status,
            date=timezone.now().date()  # Set current date
        )

        messages.success(request, "Attendance record added successfully.")
        return redirect('supervisor-attendance')

    return render(request, "system/attendance.html", {
        'user_role': 'supervisor',
        "attendances": attendances,
        "students": students
    })

@login_required
@supervisor_required
def supervisor_settings_view(request):
    """Settings view for supervisors"""
    face_recognition_enabled = request.session.get('face_recognition_enabled', False)
    return render(request, 'system/settings.html', {
        'user_role': 'supervisor',
        'face_recognition_enabled': face_recognition_enabled
    })

#----------------------
# ADMIN VIEWS
#----------------------

@login_required
@admin_required
def admin_dashboard_view(request):
    """Dashboard view for administrators"""
    total_teachers = CustomUser.objects.filter(is_teacher=True).count()
    total_students = Student.objects.count()
    total_attendance = Attendance.objects.count()

    context = {
        'user_role': 'admin',
        'total_teachers': total_teachers,
        'total_students': total_students,
        'total_attendance': total_attendance
    }
    return render(request, 'system/dashboard.html', context)

@login_required
@admin_required
def admin_teachers_view(request):
    """View for administrators to manage teachers"""
    teachers = CustomUser.objects.filter(is_teacher=True)
    grades = range(7, 13)
    sections = Section.objects.all()
    students = Student.objects.all()
    schools = School.objects.all()
    
    return render(request, 'system/teachers.html', {
        'user_role': 'admin',
        'teachers': teachers,
        'grades': grades,
        'sections': sections,
        'students': students,
        'schools': schools
    })

@login_required
@admin_required
def admin_students_view(request):
    """View for administrators to manage students"""
    grades = range(7, 13)  
    sections = Section.objects.all()
    students = Student.objects.select_related('section__school').all()
    schools = School.objects.all()
    
    return render(request, 'system/students.html', {
        'user_role': 'admin',
        'grades': grades,
        'sections': sections,
        'students': students,
        'schools': schools
    })

@login_required
@admin_required
def admin_attendance_view(request):
    """View for administrators to manage attendance records"""
    attendances = Attendance.objects.select_related('student__section__school').all()
    students = Student.objects.select_related('section').all()

    if request.method == "POST":
        student_id = request.POST.get("student")
        time_in = request.POST.get("time_in")
        time_out = request.POST.get("time_out")
        status = request.POST.get("status")

        if not student_id:
            messages.error(request, "Please select a student.")
            return redirect('admin-attendance')

        try:
            student = Student.objects.get(id=student_id)
            
            # Convert time strings to datetime objects properly
            time_in_obj = datetime.datetime.strptime(time_in, "%H:%M").time() if time_in else None
            time_out_obj = datetime.datetime.strptime(time_out, "%H:%M").time() if time_out else None
            
            # Create attendance record
            attendance = Attendance.objects.create(
                student=student,
                time_in=time_in_obj,
                time_out=time_out_obj,
                status=status,
                date=timezone.now().date()
            )
            
            messages.success(request, "Attendance record added successfully.")
        except Student.DoesNotExist:
            messages.error(request, "Student not found!")
        except ValueError as e:
            messages.error(request, f"Invalid input: {str(e)}")
        
        return redirect('admin-attendance')

    return render(request, "system/attendance.html", {
        'user_role': 'admin',
        "attendances": attendances,
        "students": students
    })

@login_required
@admin_required
def admin_settings_view(request):
    """Settings view for administrators"""
    return render(request, 'system/settings.html', {'user_role': 'admin'})

@login_required
@admin_required
def cleanup_images_view(request):
    """Manually trigger cleanup of old face images"""
    try:
        from .face_recognition import cleanup_old_images
        cleanup_old_images()
        messages.success(request, "Old face images have been successfully cleaned up")
    except Exception as e:
        messages.error(request, f"Error cleaning up old images: {str(e)}")
    
    # Redirect back to previous page or settings
    return redirect(request.META.get('HTTP_REFERER', 'admin-settings'))

@login_required
@admin_required
def export_admin_attendance_csv(request):
    """Export all attendance data as CSV file for administrators"""
    # Admins can see all attendance records
    attendances = Attendance.objects.all().select_related('student__section__school')
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="all_attendance_{timezone.now().strftime("%Y-%m-%d")}.csv"'
    
    # Create CSV writer
    writer = csv.writer(response)
    
    # Write header row
    writer.writerow(['#', 'Student Name', 'LRN', 'School', 'Grade', 'Section', 'Date', 'Time In', 'Time Out', 'Status'])
    
    # Write data rows
    for i, attendance in enumerate(attendances, 1):
        student = attendance.student
        writer.writerow([
            i,
            f"{student.first_name} {student.last_name}",
            student.lrn,
            student.section.school.name,
            student.section.grade,
            student.section.name,
            attendance.date,
            attendance.time_in if attendance.time_in else "N/A",
            attendance.time_out if attendance.time_out else "N/A",
            attendance.status if hasattr(attendance, 'status') else "N/A"  # Check if status field exists
        ])
    
    return response

#----------------------
# TEACHER VIEWS
#----------------------

@login_required
@teacher_required
def teacher_dashboard_view(request):
    """Dashboard view for teachers"""
    # Get only students in the teacher's section
    teacher_section = request.user.section
    total_students = Student.objects.filter(section=teacher_section).count()
    total_attendance = Attendance.objects.filter(student__section=teacher_section).count()
    
    context = {
        'user_role': 'teacher',
        'total_students': total_students,
        'total_attendance': total_attendance
    }
    return render(request, 'system/dashboard.html', context)

@login_required
@teacher_required
def teacher_students_view(request):
    """View for teachers to manage their students"""
    # Get only students in the teacher's section
    teacher_section = request.user.section
    students = Student.objects.filter(section=teacher_section).select_related('section__school')
    grades = [teacher_section.grade]
    sections = [teacher_section]
    schools = [teacher_section.school]
    
    return render(request, 'system/students.html', {
        'user_role': 'teacher',
        'grades': grades,
        'sections': sections,
        'students': students,
        'schools': schools
    })

@login_required
@teacher_required
def teacher_attendance_view(request):
    """View for teachers to manage attendance for their students"""
    teacher_section = request.user.section
    attendances = Attendance.objects.filter(student__section=teacher_section).select_related('student__section__school')
    students = Student.objects.filter(section=teacher_section).select_related('section')

    if request.method == "POST":
        # ...handle POST data...
        pass
        
    return render(request, "system/attendance.html", {
        'user_role': 'teacher',
        "attendances": attendances,
        "students": students
    })

@login_required
@teacher_required
def teacher_settings_view(request):
    """Settings view for teachers"""
    return render(request, 'system/settings.html', {'user_role': 'teacher'})

@login_required
@teacher_required
def export_attendance_csv(request):
    """Export attendance data as CSV file for teachers"""
    # Only allow teachers to export their section's attendance
    teacher_section = request.user.section
    attendances = Attendance.objects.filter(student__section=teacher_section).select_related('student__section__school')
    
    # Create CSV response
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="attendance_{timezone.now().strftime("%Y-%m-%d")}.csv"'
    
    # Create CSV writer
    writer = csv.writer(response)
    
    # Write header row
    writer.writerow(['#', 'Student Name', 'LRN', 'School', 'Grade', 'Section', 'Date', 'Time In', 'Time Out', 'Status'])
    
    # Write data rows
    for i, attendance in enumerate(attendances, 1):
        student = attendance.student
        writer.writerow([
            i,
            f"{student.first_name} {student.last_name}",
            student.lrn,
            student.section.school.name,
            student.section.grade,
            student.section.name,
            attendance.date,
            attendance.time_in if attendance.time_in else "N/A",
            attendance.time_out if attendance.time_out else "N/A",
            attendance.status if hasattr(attendance, 'status') else "N/A"  # Check if status field exists
        ])
    
    return response

#----------------------
# ATTENDANCE VIEWS
#----------------------

@login_required
def attendance_dashboard_view(request):
    """Dashboard for attendance monitoring"""
    return render(request, 'system/attendance_dashboard.html')

@login_required
def add_attendance(request):
    """Add attendance record for a student"""
    if request.method == "POST":
        student_id = request.POST.get("student")
        time_in = request.POST.get("time_in")
        time_out = request.POST.get("time_out", None)
        status = request.POST.get("status")

        # Ensure the student exists
        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            messages.error(request, "Student not found!")
            return redirect("supervisor-attendance")

        # Convert time strings to datetime
        try:
            time_in_obj = datetime.datetime.strptime(time_in, "%H:%M").time() if time_in else None
            time_out_obj = datetime.datetime.strptime(time_out, "%H:%M").time() if time_out else None
        except ValueError:
            messages.error(request, "Invalid time format. Use HH:MM format.")
            return redirect("supervisor-attendance")

        # Create and save attendance record
        attendance = Attendance.objects.create(
            student=student,
            time_in=time_in_obj,
            time_out=time_out_obj,
            status=status,
            date=timezone.now().date()  # Set current date
        )

        messages.success(request, "Attendance added successfully!")
        return redirect("supervisor-attendance")

    students = Student.objects.select_related('section').all()
    return render(request, "system/supervisor_attendance.html", {"students": students})

def update_attendance_record(student_id, request, face_image_b64=None, face_image=None):
    """Updates attendance when a student is recognized"""
    from .email_utils import send_attendance_notification
    
    current_date = localtime().date() 
    current_time = localtime().time()

    try:
        student = Student.objects.get(lrn=student_id)
        
        # Get attendance mode from the request
        mode = request.GET.get('mode', 'time-in')
        
        # Generate the unique entry ID
        entry_id = f"{student.lrn}-{current_date}"
        
        # Find or create attendance record for TODAY only
        attendance_updated = False
        
        if mode == 'time-in':
            # For time-in: Create a new record with time_in set
            attendance_record, created = Attendance.objects.get_or_create(
                student=student, date=current_date,
                defaults={'time_in': current_time, 'time_out': None}
            )
            
            # Only update time_in if it doesn't exist yet
            if not created and not attendance_record.time_in:
                attendance_record.time_in = current_time
                attendance_record.save()
                attendance_updated = True
            elif created:
                attendance_updated = True
                
        else:  # mode == 'time-out'
            # For time-out: Find existing record for today and update time_out
            try:
                # Try to find an existing record for today
                attendance_record = Attendance.objects.get(student=student, date=current_date)
                
                # Only update time_out if it doesn't exist yet
                if not attendance_record.time_out:
                    attendance_record.time_out = current_time
                    attendance_record.save()
                    attendance_updated = True
            except Attendance.DoesNotExist:
                # No attendance record for today yet - this is unusual for time-out
                # but we'll create one with just time_out set
                attendance_record = Attendance.objects.create(
                    student=student, 
                    date=current_date,
                    time_in=None,  # No time_in
                    time_out=current_time  # Only time_out
                )
                attendance_updated = True

        # Send email notification if the attendance was actually updated and student has guardian email
        if attendance_updated and student.guardian_email:
            # Use the correct time for the notification based on mode
            notification_time = localtime().replace(
                hour=current_time.hour, 
                minute=current_time.minute,
                second=current_time.second
            )
            
            # Send the email notification in a new thread to avoid blocking
            import threading
            email_thread = threading.Thread(
                target=send_attendance_notification,
                args=(student, mode, notification_time)
            )
            email_thread.daemon = True
            email_thread.start()

        # If we have a face image, store it for this session (for backward compatibility)
        if face_image_b64:
            face_image_storage[entry_id] = face_image_b64

        # Return student info for display
        section_grade = student.section.grade if student.section else "Unknown"
        section_name = student.section.name if student.section else "Unknown"
        
        # Format times for display
        attendance_time_in = attendance_record.time_in.strftime("%H:%M:%S") if attendance_record.time_in else None
        attendance_time_out = attendance_record.time_out.strftime("%H:%M:%S") if attendance_record.time_out else None

        # Use the face image path if provided (new system)
        image_url = None
        if face_image is not None and 'image_path' in locals():
            # Get the web-accessible URL for the image
            relative_path = os.path.relpath(image_path, settings.MEDIA_ROOT)
            image_url = f"/media/{relative_path}"
            
        return {
            "first_name": student.first_name,
            "middle_initial": student.middle_name[0] + "." if student.middle_name else "",
            "last_name": student.last_name,
            "lrn": student.lrn,
            "section_grade": section_grade,
            "section_name": section_name,
            "image_url": student.face_photo.url if student.face_photo else "/static/images/default_user.png",
            "attendance_time_in": attendance_time_in,
            "attendance_time_out": attendance_time_out,
            "record_date": str(current_date),
            "face_image_b64": face_image_storage.get(entry_id),  # For backward compatibility
            "face_image_url": image_url,  # New field for file-based images
            "entry_id": entry_id
        }

    except Student.DoesNotExist:
        logger.error(f"Student with LRN {student_id} not found.")
        return None

@login_required
def add_teacher_view(request):
    """View to add a new teacher"""
    # Check user has proper permissions
    if not (request.user.is_superuser or request.user.is_principal):
        return HttpResponseForbidden("You do not have permission to add teachers.")
    
    if request.method == 'POST':
        first_name = request.POST['first_name']
        middle_name = request.POST.get('middle_name', '')
        last_name = request.POST['last_name']
        school_id = request.POST['school']
        section_id = request.POST['section']
        email = request.POST['email']
        username = request.POST['username']
        password = request.POST['password']
        
        # Get the school and section objects        
        try:
            school = School.objects.get(id=school_id)
            section = Section.objects.get(id=section_id)
            
            # Create the teacher user
            teacher = CustomUser(
                first_name=first_name,
                middle_name=middle_name,
                last_name=last_name,
                school=school,
                section=section,
                email=email,
                username=username,
                is_teacher=True
            )
            teacher.set_password(password)
            teacher.save()
            
            messages.success(request, 'Teacher added successfully!')
            
            # Determine which page to redirect to based on user role
            if request.user.is_superuser:
                return redirect('supervisor-teachers')
            else:
                return redirect('admin-teachers')

        except School.DoesNotExist:
            messages.error(request, "School not found.")
        except Section.DoesNotExist:
            messages.error(request, "Section not found.")
        except Exception as e:
            messages.error(request, f"Error: {str(e)}")
            
    # If not POST or if there's an error, redirect back to the appropriate page
    if request.user.is_superuser:
        return redirect('supervisor-teachers')
    else:
        return redirect('admin-teachers')

def device_selection_view(request):
    """Initial page for device selection"""
    return render(request, 'system/device_selection.html')

def back_camera_view(request):
    """View for back camera (Time-Out)"""
    # Always set to disabled on GET requests (page load/refresh)
    if request.method == "GET":
        request.session['back_camera_face_recognition_enabled'] = False
        
    # For POST requests, update based on checkbox
    if request.method == "POST":
        face_recognition_enabled = 'face_recognition' in request.POST
        request.session['back_camera_face_recognition_enabled'] = face_recognition_enabled
        logger.info(f"Back camera face recognition setting updated: {face_recognition_enabled}")

    # Get current setting
    face_recognition_enabled = request.session.get('back_camera_face_recognition_enabled', False)
    
    # Only load student face encodings if enabled        
    if face_recognition_enabled:
        from .face_recognition import load_student_face_encodings, student_names
        if len(student_names) == 0:
            logger.info("Loading student face encodings from back camera page")
            load_student_face_encodings()
        
    return render(request, 'system/back_camera.html', {'face_recognition_enabled': face_recognition_enabled})

def attendance_view(request):
    """View for administrators to manage attendance records"""
    attendances = Attendance.objects.select_related('student__section__school').all()
    students = Student.objects.select_related('section').all()

    if request.method == "POST":
        student_id = request.POST.get("student")
        time_in = request.POST.get("time_in")
        time_out = request.POST.get("time_out")
        status = request.POST.get("status")

        if not student_id:
            messages.error(request, "Please select a student.")
            return redirect('admin-attendance')

        try:
            student = Student.objects.get(id=student_id)
            
            # Convert time strings to datetime objects properly
            time_in_obj = datetime.datetime.strptime(time_in, "%H:%M").time() if time_in else None
            time_out_obj = datetime.datetime.strptime(time_out, "%H:%M").time() if time_out else None
            
            # Create attendance record
            attendance = Attendance.objects.create(
                student=student,
                time_in=time_in_obj,
                time_out=time_out_obj,
                status=status,
                date=timezone.now().date()
            )
            
            messages.success(request, "Attendance record added successfully.")
        except Student.DoesNotExist:
            messages.error(request, "Student not found!")
        except ValueError as e:
            messages.error(request, f"Invalid input: {str(e)}")
        
        return redirect('admin-attendance')

    return render(request, "system/attendance.html", {
        'user_role': 'admin',
        "attendances": attendances,
        "students": students
    })

def attendance_view_today(request):
    """View for displaying today's attendance records only"""
    # Get current date to filter for today's records only
    current_date = localtime().date()
    
    # Get source parameter to know where to return to
    source = request.GET.get('source', '')
    
    # Set the back URL based on the source
    if source == 'front-camera':
        back_url = '/front-camera/'
        # For front camera, sort by time_in (descending)
        today_attendances = Attendance.objects.filter(date=current_date).select_related('student__section__school').order_by('-time_in')
    elif source == 'back-camera':
        back_url = '/back-camera/'
        # For back camera, sort by time_out (descending)
        today_attendances = Attendance.objects.filter(date=current_date).select_related('student__section__school').order_by('-time_out')
    else:
        back_url = '/'  # Default to home if no source or unknown source
        # Default sorting by date and ID
        today_attendances = Attendance.objects.filter(date=current_date).select_related('student__section__school')
    
    context = {
        'attendances': today_attendances,
        'back_url': back_url,
        'source': source  # Pass source to template for potential UI adjustments
    }
    
    return render(request, 'system/attendance_view_today.html', context)