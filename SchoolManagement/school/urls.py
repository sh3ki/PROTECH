from django.urls import path, include
from school import views

urlpatterns = [
    path('webcam_feed/', views.webcam_feed, name='webcam_feed'),
    path('stop_webcam/', views.stop_webcam, name='stop_webcam'),
    path('upload-temp-photo/', views.upload_temp_photo, name='upload-temp-photo'),
]