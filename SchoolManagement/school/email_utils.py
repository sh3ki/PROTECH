import logging
from datetime import datetime
from django.conf import settings
from django.core.mail import send_mail
from django.utils.timezone import localtime

logger = logging.getLogger(__name__)

def send_attendance_notification(student, mode, timestamp):
    """
    Send email notification to a student's guardian when attendance is marked.
    
    Args:
        student: Student object with attendance record
        mode: 'time-in' or 'time-out' 
        timestamp: DateTime object of when attendance was recorded
    """
    # Skip if email notifications are disabled globally
    if not getattr(settings, 'ATTENDANCE_EMAIL_ENABLED', True):
        logger.info(f"Email notifications disabled. Skipped notification for {student.lrn}")
        return False
    
    # Skip if student has no guardian email
    if not student.guardian_email:
        logger.info(f"No guardian email for student {student.lrn}. Notification skipped.")
        return False
    
    # Format time nicely for display
    time_str = timestamp.strftime('%I:%M %p')
    date_str = timestamp.strftime('%A, %B %d, %Y')
    
    # Prepare the subject and message based on check-in or check-out
    subject_prefix = getattr(settings, 'MAIL_SUBJECT_PREFIX', '')
    
    if mode == 'time-in':
        subject = f"{subject_prefix}Student Arrival Notification"
        message = f"""Dear Guardian of {student.first_name} {student.last_name},

This is an automated notification to inform you that {student.first_name} has arrived at school and checked in at {time_str} on {date_str}.

Grade: {student.section.grade if student.section else 'N/A'}
Section: {student.section.name if student.section else 'N/A'}

This is an automated message. Please do not reply to this email.

Best regards,
School Attendance System
"""
    else:  # mode == 'time-out'
        subject = f"{subject_prefix}Student Departure Notification"
        message = f"""Dear Guardian of {student.first_name} {student.last_name},

This is an automated notification to inform you that {student.first_name} has left school and checked out at {time_str} on {date_str}.

Grade: {student.section.grade if student.section else 'N/A'}
Section: {student.section.name if student.section else 'N/A'}

This is an automated message. Please do not reply to this email.

Best regards,
School Attendance System
"""

    # Get the sender from settings or use a default
    sender = getattr(settings, 'ATTENDANCE_NOTIFICATION_SENDER', settings.EMAIL_HOST_USER)
    
    try:
        # Send the email
        send_mail(
            subject=subject,
            message=message,
            from_email=sender,
            recipient_list=[student.guardian_email],
            fail_silently=False,
        )
        logger.info(f"Sent {mode} notification email to {student.guardian_email} for student {student.lrn}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email notification: {str(e)}")
        return False
