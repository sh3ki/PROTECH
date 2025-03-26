from django.contrib import admin
from django.urls import path, include
from school import views
from django.contrib.auth.views import LoginView,LogoutView
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('admin/', admin.site.urls),
    path('',views.landing_page_view,name=''),
    path('/',views.landing_page_view,name='/'),
    path('school/', include('school.urls')),
   
    path('supervisor-login', views.supervisor_login_view),
    path('admin-login', views.admin_login_view, name='admin-login'),
    path('teacher-login', views.teacher_login_view, name='teacher-login'),
    path('register-form', views.register_form_view, name='register-form'),

    path('adminlogin', LoginView.as_view(template_name='school/adminlogin.html')),
    path('studentlogin', LoginView.as_view(template_name='school/studentlogin.html')),
    path('teacherlogin', LoginView.as_view(template_name='school/teacherlogin.html')),
    
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
    # path('edit-admin/<int:id>/', views.edit_admin_view, name='edit-admin'),
    # path('delete-admin/<int:id>/', views.delete_admin_view, name='delete-admin'),
    # path('edit-teacher/<int:id>/', views.edit_teacher_view, name='edit-teacher'),
    # path('delete-teacher/<int:id>/', views.delete_teacher_view, name='delete-teacher'),
    path('supervisor-attendance', views.supervisor_attendance_view, name='supervisor-attendance'),
    path('add-attendance/', views.add_attendance, name='add-attendance'),
    path('supervisor-settings', views.supervisor_settings_view, name='supervisor-settings'),

    path('admin-dashboard', views.admin_dashboard_view, name='admin-dashboard'),
    path('admin-teachers', views.admin_teachers_view, name='admin-teachers'),
    path('admin-students', views.admin_students_view, name='admin-students'),
    path('admin-attendance', views.admin_attendance_view, name='admin-attendance'),
    path('teacher-dashboard', views.teacher_dashboard_view, name='teacher-dashboard'),

    path('afterlogin', views.afterlogin_view,name='afterlogin'),
    path('logout', LogoutView.as_view(template_name='system/landing_page.html'),name='logout'),


]  + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
