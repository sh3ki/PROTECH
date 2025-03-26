import atexit
import datetime
from urllib import request
from django.shortcuts import render, redirect, reverse
from school.utils import generate_frames
from . import forms, models
from django.db.models import Sum
from django.db.models import Max
from django.contrib.auth.models import Group
from django.http import HttpResponse, HttpResponseRedirect, HttpResponseForbidden
from django.contrib.auth.decorators import login_required, user_passes_test
from django.conf import settings
from django.core.mail import send_mail
from django.contrib.auth import authenticate, login
from functools import wraps
from django.contrib.auth.models import User
from django.contrib import messages
from .models import School, Student, CustomUser, Attendance, Section
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q
from django.db import IntegrityError
import subprocess
from django.core.files.storage import default_storage
import os
import cv2
import numpy as np
from django.http import JsonResponse
from django.contrib.auth.hashers import make_password
from .models import CustomUser
from django.core.exceptions import ValidationError
from django.shortcuts import render
from django.http import JsonResponse
import os
import shutil
import uuid
from django.utils import timezone
import logging

def landing_page_view(request):
    face_recognition_enabled = request.session.get('face_recognition_enabled', False)

    if request.method == "POST":
        face_recognition_enabled = 'face_recognition' in request.POST
        request.session['face_recognition_enabled'] = face_recognition_enabled

    return render(request, 'system/landing_page.html', {'face_recognition_enabled': face_recognition_enabled})

# Supervisor login form
def supervisor_login_view(request):
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
    return render(request, 'system/supervisor_login.html', {'error_message': error_message})

# Admin login form
def admin_login_view(request):
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
    return render(request, 'system/admin_login.html', {'error_message': error_message})

# Teacher login form
def teacher_login_view(request):
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
    return render(request, 'system/teacher_login.html', {'error_message': error_message})

def supervisor_dashboard_view(request):
    total_schools = School.objects.count()
    total_admins = CustomUser.objects.filter(Q(is_principal=True) | Q(is_guard=True)).count()
    total_teachers = CustomUser.objects.filter(is_teacher=True).count()
    total_students = Student.objects.count()
    total_attendance = Attendance.objects.count()

    total = {
        'total_schools': total_schools,
        'total_admins': total_admins,
        'total_teachers': total_teachers,
        'total_students': total_students,
        'total_attendance': total_attendance
    }
    return render(request, 'system/supervisor_dashboard.html', total)

def supervisor_schools_view(request):
    schools = School.objects.all()
    return render(request, 'system/supervisor_schools.html', {'schools': enumerate(schools, start=1)})

def add_school_view(request):
    if request.method == 'POST':
        # Get form data
        school_id = request.POST.get('school_id')
        school_name = request.POST.get('school_name')
        school_address = request.POST.get('school_address')
        school_head = request.POST.get('school_head')
        total_students = request.POST.get('total_students')

        # Save to the database
        new_school = School(
            id=school_id,
            name=school_name,
            address=school_address,
            head=school_head,
            total_students=total_students
        )
        new_school.save()

        # Redirect back to the same page (or any other page you want)
        return redirect('supervisor-schools')  # Or you can return a success message
    
    return render(request, 'supervisor_schools.html')

def add_teacher_view(request):
    if request.method == 'POST':
        first_name = request.POST['first_name']
        middle_name = request.POST.get('middle_name', '')
        last_name = request.POST['last_name']
        school_id = request.POST['school']
        grade = request.POST['grade']
        section_id = request.POST['section']
        email = request.POST['email']
        username = request.POST['username']
        password = request.POST['password']  # Add logic to hash password
        
        school = School.objects.get(id=school_id)
        section = Section.objects.get(id=section_id)
        
        teacher = CustomUser(
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            school=school,
            section=section,
            email=email,
            username=username,
            password=password,  # Ensure password is hashed before saving
            is_teacher=True
        )
        teacher.set_password(password)
        teacher.save()
        
        messages.success(request, 'Teacher added successfully!')
        return redirect('supervisor-teachers')
    return render(request, 'system/supervisor_teachers.html')

def supervisor_admins_view(request):
    admins = CustomUser.objects.filter(Q(is_principal=True) | Q(is_guard=True))
    schools = School.objects.all() 
    return render(request, 'system/supervisor_admins.html', {
        'admins': admins,
        'schools': schools,
    })

def supervisor_teachers_view(request):
    teachers = CustomUser.objects.filter(is_teacher=True)
    grades = range(7, 13)  # Grades 7 to 12
    sections = Section.objects.all()  # Fetch all sections
    students = Student.objects.all()  # Fetch all students
    schools = School.objects.all()  # Fetch all schools
    return render(request, 'system/supervisor_teachers.html', {
        'teachers': teachers,
        'grades': grades,
        'sections': sections,
        'students': students,
        'schools': schools  # Pass schools to the template
    })

def supervisor_students_view(request):
    grades = range(7, 13)  # Grades 7 to 12
    sections = Section.objects.all()  # Fetch all sections
    students = Student.objects.all()  # Fetch all students
    schools = School.objects.all()  # Fetch all schools
    return render(request, 'system/supervisor_students.html', {
        'grades': grades,
        'sections': sections,
        'students': students,
        'schools': schools  # Pass schools to the template
    })

def add_admin_view(request):
    if request.method == 'POST':
        first_name = request.POST['first_name']
        middle_name = request.POST.get('middle_name', '')
        last_name = request.POST['last_name']
        school_id = request.POST['school']
        role = request.POST.get('role')
        email = request.POST['email']
        username = request.POST['username']
        password = request.POST['password']  # Add logic to hash password
        
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
   

def add_student_view(request):
    if request.method == "POST":
        # Fetch form data from the request
        student_lrn = request.POST.get('student_lrn')
        first_name = request.POST.get('first_name')
        middle_name = request.POST.get('middle_name', '')  
        last_name = request.POST.get('last_name')
        grade = request.POST.get('grade')

        # ✅ Corrected: Assign the section_id directly from POST data
        section_id = request.POST.get('section')
        guardian = request.POST.get('guardian')
        guardian_phone = request.POST.get('guardian_phone')
        guardian_email = request.POST.get('guardian_email')
        face_photo = request.FILES.get('face_photo')

        # ✅ Ensure section ID is provided before querying the database
        if section_id:
            try:
                section = Section.objects.get(id=section_id)
            except Section.DoesNotExist:
                return HttpResponse("Invalid section selected.", status=400)
        else:
            return HttpResponse("Section is required.", status=400)

        # ✅ Create the student object using the section instance
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

        # Move the photo from student_temp to student_face
        temp_folder = os.path.join(settings.MEDIA_ROOT, 'student_temp')
        final_folder = os.path.join(settings.MEDIA_ROOT, 'student_face')
        temp_path = os.path.join(temp_folder, f'{student_lrn}.jpg')
        final_path = os.path.join(final_folder, f'{student_lrn}.jpg')

        if os.path.exists(temp_path):
            os.makedirs(final_folder, exist_ok=True)
            shutil.move(temp_path, final_path)

        global student_encodings
        student_encodings = load_student_face_encodings()

        messages.success(request, 'Student added successfully!')
        return redirect('supervisor-students')

    return render(request, 'system/supervisor-students.html')

def edit_student_view(request, lrn):
    student = get_object_or_404(Student, lrn=lrn)
    
    if request.method == 'POST':
        student.first_name = request.POST.get('first_name')
        student.middle_name = request.POST.get('middle_name')
        student.last_name = request.POST.get('last_name')
        student.guardian_email = request.POST.get('email')
        student.section = request.POST.get('section')
        student.section.school = request.POST.get('school')
        
        
        student.save()
        
        messages.success(request, 'Student updated successfully!')
        return redirect('supervisor-students')
    
    return render(request, 'system/edit_student.html', {'student': student})

# Handle the temporary photo upload
def upload_temp_photo(request):
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

# Move the image to the final folder after the form is submitted
def move_temp_to_final(lrn):
    temp_folder = 'temp/student-photos'
    final_folder = 'media/student-photos'
    temp_path = os.path.join(temp_folder, f'{lrn}.png')
    final_path = os.path.join(final_folder, f'{lrn}.png')

    if os.path.exists(temp_path):
        shutil.move(temp_path, final_path)
        os.remove(temp_path)

def delete_student_view(request, lrn):
    student = get_object_or_404(Student, lrn=lrn)
    student.delete()
    return redirect('supervisor-students') 

def edit_school_view(request, id):
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

def delete_school_view(request, id):
    school = get_object_or_404(School, id=id)
    school.delete()
    return redirect('supervisor-schools')

def supervisor_attendance_view(request):
    # Fetch all attendance records
    attendances = Attendance.objects.select_related('student__section__school').all()
    
    # Fetch all students for the add attendance form
    students = Student.objects.all()

    if request.method == "POST":
        student_id = request.POST.get("student")
        time_in = request.POST.get("time_in")
        time_out = request.POST.get("time_out")
        status = request.POST.get("status")

        # Ensure a student is selected
        if not student_id:
            messages.error(request, "Please select a student.")
            return redirect('supervisor-attendance')

        student = Student.objects.get(id=student_id)

        # Create and save attendance record
        Attendance.objects.create(
            student=student,
            time_in=time_in,
            time_out=time_out,
            status=status
        )
        messages.success(request, "Attendance record added successfully.")
        return redirect('supervisor-attendance')

    return render(request, "system/supervisor_attendance.html", {
        "attendances": attendances,
        "students": students
    })

def add_attendance(request):
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
        time_in = datetime.strptime(time_in, "%H:%M").time()
        time_out = datetime.strptime(time_out, "%H:%M").time() if time_out else None

        # Create and save attendance record
        attendance = Attendance.objects.create(
            student=student,
            time_in=time_in,
            time_out=time_out,
            status=status,
        )

        messages.success(request, "Attendance added successfully!")
        return redirect("supervisor-attendance")

    students = Student.objects.all()
    return render(request, "supervisor/attendance.html", {"students": students})

def supervisor_settings_view(request):
    return render(request, 'system/supervisor_settings.html')

def admin_dashboard_view(request):
    total_schools = School.objects.count()
    total_admins = CustomUser.objects.filter(Q(is_principal=True) | Q(is_guard=True)).count()
    total_teachers = CustomUser.objects.filter(is_teacher=True).count()
    total_students = Student.objects.count()
    total_attendance = Attendance.objects.count()

    total = {
        'total_schools': total_schools,
        'total_admins': total_admins,
        'total_teachers': total_teachers,
        'total_students': total_students,
        'total_attendance': total_attendance
    }

    return render(request, 'system/admin_dashboard.html', total)


def admin_teachers_view(request):
    teachers = CustomUser.objects.filter(is_teacher=True)
    grades = range(7, 13)  # Grades 7 to 12
    sections = Section.objects.all()  # Fetch all sections
    students = Student.objects.all()  # Fetch all students
    schools = School.objects.all()  # Fetch all schools
    return render(request, 'system/admin_teachers.html', {
        'teachers': teachers,
        'grades': grades,
        'sections': sections,
        'students': students,
        'schools': schools  # Pass schools to the template
    })

def admin_students_view(request):
    grades = range(7, 13)  # Grades 7 to 12
    sections = Section.objects.all()  # Fetch all sections
    students = Student.objects.all()  # Fetch all students
    schools = School.objects.all()  # Fetch all schools
    return render(request, 'system/admin_students.html', {
        'grades': grades,
        'sections': sections,
        'students': students,
        'schools': schools  # Pass schools to the template
    })

def admin_attendance_view(request):
    # Fetch all attendance records
    attendances = Attendance.objects.select_related('student__section__school').all()
    
    # Fetch all students for the add attendance form
    students = Student.objects.all()

    if request.method == "POST":
        student_id = request.POST.get("student")
        time_in = request.POST.get("time_in")
        time_out = request.POST.get("time_out")
        status = request.POST.get("status")

        # Ensure a student is selected
        if not student_id:
            messages.error(request, "Please select a student.")
            return redirect('supervisor-attendance')

        student = Student.objects.get(id=student_id)

        # Create and save attendance record
        Attendance.objects.create(
            student=student,
            time_in=time_in,
            time_out=time_out,
            status=status
        )
        messages.success(request, "Attendance record added successfully.")
        return redirect('supervisor-attendance')

    return render(request, "system/admin_attendance.html", {
        "attendances": attendances,
        "students": students
    })

def teacher_dashboard_view(request):
    return render(request, 'system/teacher_dashboard.html')

def attendance_dashboard_view(request):
    return render(request, 'system/attendance_dashboard.html')

def afterlogin_view(request):
    if request.user.is_superuser:
        return redirect('supervisor-dashboard')  # Redirect to supervisor dashboard
    elif request.user.is_principal:
        return redirect('admin-dashboard')  # Redirect to admin dashboard
    elif request.user.is_guard:
        return redirect('attendance-dashboard')  # Redirect to attendance dashboard
    elif request.user.is_teacher:
        return redirect('teacher-dashboard')  # Redirect to teacher dashboard
    else:
        return HttpResponseForbidden("You do not have permission to access the system.")

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
        if request.user.is_principal:
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

def register_form_view(request):
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
                section=section,  # Assigning the object instead of the ID
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

    # If GET, show the form
    schools = School.objects.all()
    sections = Section.objects.all()
    return render(request, 'system/register_form.html', {'schools': schools, 'sections': sections})

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import cv2
import face_recognition
import os
import logging
from django.http import StreamingHttpResponse
from django.shortcuts import render
import numpy as np
from django.utils import timezone
from django.utils.timezone import localtime
from .models import Student, Attendance

# Initialize webcam
cap = cv2.VideoCapture(0)

# Logging setup
logger = logging.getLogger(__name__)

# Face recognition threshold
FACE_RECOGNITION_THRESHOLD = 0.3
# Path to student images
FACE_IMAGES_PATH = 'media/student_face/'
# Load student face encodings
def load_student_face_encodings():
    
    student_encodings = {}
    for filename in os.listdir(FACE_IMAGES_PATH):
        if filename.endswith('.jpg'):
            student_id = filename.split('.')[0]
            image_path = os.path.join(FACE_IMAGES_PATH, filename)
            student_image = face_recognition.load_image_file(image_path)
            student_encoding = face_recognition.face_encodings(student_image)
            if student_encoding:
                student_encodings[student_id] = student_encoding[0]
    print(f"Loaded student encodings: {list(student_encodings.keys())}")
    return student_encodings

student_encodings = load_student_face_encodings()

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def generate_frame(face_recognition_enabled, request):
    channel_layer = get_channel_layer()  # Get WebSocket channel

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Error: Cannot read from webcam")
            break

        frame = cv2.flip(frame, 1)

        if face_recognition_enabled:
            small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
            rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_frame)
            face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

            print(f"Detected {len(face_encodings)} faces.")

            for face_encoding, (top, right, bottom, left) in zip(face_encodings, face_locations):
                matches = face_recognition.compare_faces(list(student_encodings.values()), face_encoding, tolerance=0.4)

                name = "Unknown"
                for student_id, match in zip(student_encodings.keys(), matches):
                    if match:
                        name = student_id
                        break

                top, right, bottom, left = [x * 4 for x in [top, right, bottom, left]]
                cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)
                cv2.putText(frame, f"ID: {name}", (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

                if name != "Unknown":
                    print(f"Recognized Student ID: {name}")
                    student_data = update_attendance_record(name, request)  # Call function to update DB

                    # 🔹 Send WebSocket message to update real-time attendance
                    if student_data:
                        async_to_sync(channel_layer.group_send)(
                            "attendance_updates",  # WebSocket Group
                            {"type": "send_attendance_update", "student": student_data}
                        )

        ret, jpeg = cv2.imencode('.jpg', frame)
        if not ret:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')


# def generate_frame(face_recognition_enabled, request):
#     while True:
#         ret, frame = cap.read()
#         if not ret:
#             print("Error: Cannot read from webcam")
#             break

#         frame = cv2.flip(frame, 1)

#         if face_recognition_enabled:
#             small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
#             rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
#             face_locations = face_recognition.face_locations(rgb_frame)
#             face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)

#             print(f"Detected {len(face_encodings)} faces.")

#             for face_encoding, (top, right, bottom, left) in zip(face_encodings, face_locations):
#                 matches = face_recognition.compare_faces(list(student_encodings.values()), face_encoding, tolerance=0.4)

#                 name = "Unknown"
#                 for student_id, match in zip(student_encodings.keys(), matches):
#                     if match:
#                         name = student_id
#                         break

#                 top, right, bottom, left = [x * 4 for x in [top, right, bottom, left]]
#                 cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)
#                 cv2.putText(frame, f"ID: {name}", (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

#                 if name != "Unknown":
#                     print(f"Recognized Student ID: {name}")
#                     update_attendance_record(name, request)

#         ret, jpeg = cv2.imencode('.jpg', frame)
#         if not ret:
#             continue

#         yield (b'--frame\r\n'
#                b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')

# def update_attendance_record(student_id, request):

#     time_in_active = request.session.get('time_in', True)
#     time_out_active = request.session.get('time_out_active', False)


#     try:
#         student = Student.objects.get(lrn=student_id)
#         print(f"Updating attendance for {student.lrn}.")
#     except Student.DoesNotExist:
#         print(f"Error: Student with LRN {student_id} not found.")
#         return

#     attendance_record, created = Attendance.objects.get_or_create(
#         student=student, date=current_date, defaults={'time_in': current_time}
#     )
#     if not created:
#         if time_out_active and not attendance_record.time_out:  
#             attendance_record.time_out = current_time  # ✅ Set `time_out` only if checkbox is active
#             attendance_record.save()
#             print(f"Marked time-out for {student.lrn}: {attendance_record.time_out}")
#         else:
#             print(f"Student {student.lrn} already has a time-in and time-out OR time-out mode is OFF.")
#     else:
#         print(f"Marked time-in for {student.lrn}: {attendance_record.time_in}")
        

def update_attendance_record(student_id, request):
    """Updates attendance and sends real-time WebSocket updates when a student is recognized."""
    current_date = localtime().date() 
    current_time = localtime().time()

    try:
        student = Student.objects.get(lrn=student_id)
        grade_section = f"{student.grade} - {student.section}"

        attendance_record, created = Attendance.objects.get_or_create(
            student=student, date=current_date, defaults={'time_in': current_time}
        )

        if not created and not attendance_record.time_out:
            attendance_record.time_out = current_time
            attendance_record.save()

        # Prepare student data for WebSocket
        student_data = {
            "first_name": student.first_name,
            "middle_initial": student.middle_name[0] + "." if student.middle_name else "",
            "last_name": student.last_name,
            "lrn": student.lrn,
            "grade_section": grade_section,
            "image_url": student.photo.url if student.photo else "/static/images/default_user.png",
        }

        # Send real-time updates via WebSocket
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "attendance_updates",
            {"type": "send_attendance_update", "student": student_data}
        )

    except Student.DoesNotExist:
        print(f"Error: Student with LRN {student_id} not found.")

def webcam_feed(request):
    if not cap.isOpened():
        cap.open(0)
    face_recognition_enabled = request.session.get('face_recognition_enabled', False)
    return StreamingHttpResponse(
        generate_frame(face_recognition_enabled, request), content_type='multipart/x-mixed-replace; boundary=frame'
    )

def stop_webcam(request):
    global cap
    if cap.isOpened():
        cap.release()
        print("Camera released successfully")
    return JsonResponse({"status": "camera released"})

def release_camera():
    global cap
    if cap.isOpened():
        cap.release()

atexit.register(release_camera)