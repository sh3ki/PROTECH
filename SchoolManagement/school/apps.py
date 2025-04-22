from django.apps import AppConfig
import os
import logging

logger = logging.getLogger(__name__)

class SchoolConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'school'

    def ready(self):
        """Run initialization code when Django starts"""
        # Import here to avoid circular imports
        from .face_recognition import ensure_directories_exist, cleanup_old_images
        
        # Create necessary directories
        ensure_directories_exist()
        
        # Clean up old images from previous days
        try:
            cleanup_old_images()
            logger.info("Startup cleanup completed successfully")
        except Exception as e:
            logger.error(f"Error during startup cleanup: {str(e)}")