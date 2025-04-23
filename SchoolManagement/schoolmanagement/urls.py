from django.contrib import admin
from django.urls import path
from school import views
from school.face_recognition import webcam_feed, stop_webcam, cleanup_old_images
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('admin/', admin.site.urls),  # Add trailing slash for Django admin
    path('',views.device_selection_view, name='device-selection'),
    path('front-camera/',views.front_camera_view, name='front-camera'),
    path('back-camera/', views.back_camera_view, name='back-camera'),
    path('logout', views.logout_view, name='logout'),
    path('attendance-view',views.attendance_view, name='attendance-view'),
    path('attendance-view-today',views.attendance_view_today, name='attendance-view-today'),
    
    # Authentication routes - all using consistent naming
    path('supervisor-login', views.supervisor_login_view, name='supervisor-login'),
    path('admin-login', views.admin_login_view, name='admin-login'),
    path('teacher-login', views.teacher_login_view, name='teacher-login'),
    path('register-form', views.register_form_view, name='register-form'),

    # Face recognition routes
    path('webcam_feed/', webcam_feed, name='webcam_feed'),
    path('stop_webcam/', stop_webcam, name='stop_webcam'),
    path('upload_temp_photo/', views.upload_temp_photo, name='upload_temp_photo'),
    path('school/upload-temp-photo/', views.upload_temp_photo, name='upload-temp-photo'),
    path('get_recognized_students/', views.get_recognized_students, name='get_recognized_students'),
    path('cleanup_images/', views.cleanup_images_view, name='cleanup_images'),
    
    # Supervisor routes
    path('supervisor-dashboard', views.supervisor_dashboard_view, name='supervisor-dashboard'),
    path('supervisor-schools', views.supervisor_schools_view, name='supervisor-schools'),
    path('add-school', views.add_school_view, name='add-school'),
    path('supervisor-admins', views.supervisor_admins_view, name='supervisor-admins'),
    path('add-admin', views.add_admin_view, name='add-admin'),
    path('supervisor-teachers', views.supervisor_teachers_view, name='supervisor-teachers'),
    path('add-teacher', views.add_teacher_view, name='add-teacher'),
    path('supervisor-students', views.supervisor_students_view, name='supervisor-students'),
    path('add-student', views.add_student_view, name='add-student'),
    path('edit-student/<int:lrn>/', views.edit_student_view, name='edit-student'),
    path('delete-student/<int:lrn>/', views.delete_student_view, name='delete-student'),
    path('edit-school/<int:id>/', views.edit_school_view, name='edit-school'),
    path('delete-school/<int:id>/', views.delete_school_view, name='delete-school'),
    path('supervisor-attendance', views.supervisor_attendance_view, name='supervisor-attendance'),
    path('add-attendance/', views.add_attendance, name='add-attendance'),
    path('supervisor-settings', views.supervisor_settings_view, name='supervisor-settings'),

    # Admin routes
    path('admin-dashboard', views.admin_dashboard_view, name='admin-dashboard'),
    path('admin-teachers', views.admin_teachers_view, name='admin-teachers'),
    path('admin-students', views.admin_students_view, name='admin-students'),
    path('admin-attendance', views.admin_attendance_view, name='admin-attendance'),
    path('admin-settings', views.admin_settings_view, name='admin-settings'),
    
    # Teacher routes
    path('teacher-dashboard', views.teacher_dashboard_view, name='teacher-dashboard'),
    path('teacher-students', views.teacher_students_view, name='teacher-students'),
    path('teacher-attendance', views.teacher_attendance_view, name='teacher-attendance'),
    path('teacher-settings', views.teacher_settings_view, name='teacher-settings'),

    path('afterlogin', views.afterlogin_view, name='afterlogin'),
]  + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
