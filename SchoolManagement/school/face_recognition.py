import atexit
import logging
import os
import cv2
import face_recognition
import threading
import time
import numpy as np
from sklearn.neighbors import BallTree
from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse
from django.utils.timezone import localtime
import base64
from datetime import datetime, timedelta
import shutil

from .models import Student, Attendance

# Initialize logging
logger = logging.getLogger(__name__)

# Initialize webcam
cap = None  # Will be initialized in thread
frame_buffer = None  # Latest frame from camera
frame_lock = threading.Lock()  # Thread safety for frame buffer
is_capturing = False  # Flag to control the capture thread
process_this_frame = 0  # Counter for frame processing (FPS control)

# Track last detected faces for continuous display
last_face_locations = []
last_face_names = []
last_face_times = {}  # To track how long to display a face after detection
FACE_DISPLAY_TIMEOUT = 1.0  # How long to keep showing a face after detection (seconds)

# Face recognition settings
FACE_RECOGNITION_THRESHOLD = 0.6  # Distance threshold
FACE_IMAGES_PATH = 'media/student_face/'
FACE_RECOGNITION_MODEL = 'hog'  # Use faster HOG model for video
RESIZE_FACTOR = 0.20  # Resize factor for processing

# New paths for storing captured face images
FACE_TIME_IN_PATH = 'media/student_image_time_in/'
FACE_TIME_OUT_PATH = 'media/student_image_time_out/'

# Image compression parameters
SAVED_IMAGE_QUALITY = 70  # JPEG quality (0-100)
SAVED_IMAGE_SIZE = (120, 120)  # Target size for saved images

# Global variable for student encodings
student_encodings = {}
# Store encodings in numpy array for faster comparison
student_encodings_array = None
student_ids_list = []
# Add BallTree for even faster face matching
face_tree = None

# Add the missing student_names variable (for backward compatibility)
student_names = []  # This will be populated with student IDs when encodings are loaded

# Last error time tracking to reduce logging frequency
last_error_time = 0
ERROR_LOG_INTERVAL = 5  # seconds between error logs

def ensure_directories_exist():
    """Ensure that the necessary directories exist"""
    os.makedirs(FACE_TIME_IN_PATH, exist_ok=True)
    os.makedirs(FACE_TIME_OUT_PATH, exist_ok=True)
    logger.info("Face image directories verified")

def cleanup_old_images():
    """Delete face images from previous days"""
    today = datetime.now().date()
    yesterday = (today - timedelta(days=1)).strftime('%Y-%m-%d')
    
    # Clean up time-in images
    if os.path.exists(FACE_TIME_IN_PATH):
        for filename in os.listdir(FACE_TIME_IN_PATH):
            if filename.startswith(yesterday) or not filename.startswith(today.strftime('%Y-%m-%d')):
                try:
                    os.remove(os.path.join(FACE_TIME_IN_PATH, filename))
                except Exception as e:
                    logger.error(f"Error deleting {filename} from time-in folder: {str(e)}")
    
    # Clean up time-out images
    if os.path.exists(FACE_TIME_OUT_PATH):
        for filename in os.listdir(FACE_TIME_OUT_PATH):
            if filename.startswith(yesterday) or not filename.startswith(today.strftime('%Y-%m-%d')):
                try:
                    os.remove(os.path.join(FACE_TIME_OUT_PATH, filename))
                except Exception as e:
                    logger.error(f"Error deleting {filename} from time-out folder: {str(e)}")
    
    logger.info("Cleaned up old face images")

def initialize_camera(camera_index=0):
    """Initialize the camera with specified index"""
    global cap
    cap = cv2.VideoCapture(camera_index)
    if cap.isOpened():
        # Reduce buffer size to minimize latency
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        logger.info(f"Camera {camera_index} initialized successfully")
    else:
        logger.error(f"Failed to initialize camera {camera_index}")

def release_camera():
    """Release the camera when the application exits"""
    global cap, is_capturing
    is_capturing = False
    if cap and cap.isOpened():
        cap.release()
        logger.info("Camera released successfully")

# Register the camera release function to run on exit
atexit.register(release_camera)

def capture_frames():
    """Background thread to continuously capture frames"""
    global frame_buffer, is_capturing, cap, last_error_time
    
    logger.info("Frame capture thread started")
    
    while is_capturing:
        if cap is None or not cap.isOpened():
            # Try to reinitialize camera if needed
            time.sleep(0.5)
            try:
                initialize_camera()
            except:
                # Avoid spamming logs
                current_time = time.time()
                if current_time - last_error_time > ERROR_LOG_INTERVAL:
                    logger.error("Camera not available")
                    last_error_time = current_time
            continue
            
        success, frame = cap.read()
        if success:
            # Flip horizontally for a mirror effect
            frame = cv2.flip(frame, 1)
            
            # Thread-safe update of the current frame
            with frame_lock:
                frame_buffer = frame
        else:
            # Avoid spamming logs
            current_time = time.time()
            if current_time - last_error_time > ERROR_LOG_INTERVAL:
                logger.error("Failed to read frame from camera")
                last_error_time = current_time
                
        # Slight delay to prevent maxing out CPU
        time.sleep(0.01)
    
    logger.info("Frame capture thread stopped")

def load_student_face_encodings():
    """Load face encodings for all students from their images and create a BallTree"""
    global student_encodings, student_encodings_array, student_ids_list, student_names, face_tree
    
    encodings = {}
    if os.path.exists(FACE_IMAGES_PATH):
        files_to_process = [f for f in os.listdir(FACE_IMAGES_PATH) if f.endswith('.jpg')]
        logger.info(f"Loading {len(files_to_process)} student face images")
        
        for filename in files_to_process:
            student_id = filename.split('.')[0]
            image_path = os.path.join(FACE_IMAGES_PATH, filename)
            
            try:
                # Load and encode the image
                student_image = face_recognition.load_image_file(image_path)
                # Use CNN model for more accuracy in static images
                student_encoding = face_recognition.face_encodings(student_image)
                
                if student_encoding:
                    encodings[student_id] = student_encoding[0]
            except Exception as e:
                logger.error(f"Error encoding face for {student_id}: {str(e)}")
                
        # Convert to numpy arrays for faster processing
        if encodings:
            student_ids_list = list(encodings.keys())
            student_names = student_ids_list.copy()  # Update student_names for backward compatibility
            student_encodings_array = np.array(list(encodings.values()))
            
            # Create BallTree for much faster face matching if we have encodings
            if len(student_encodings_array) > 0:
                # The leaf_size parameter can be tuned for performance
                face_tree = BallTree(student_encodings_array, leaf_size=2)
                logger.info("Created BallTree for fast face matching")
            else:
                face_tree = None
                
        logger.info(f"Loaded {len(encodings)} student encodings")
    else:
        face_tree = None
    
    student_encodings = encodings
    return encodings, face_tree

def save_face_image(face_image, student_id, mode):
    """Save the face image to the appropriate directory with date-based filename"""
    # Get the current date
    current_date = datetime.now().date().strftime('%Y-%m-%d')
    
    # Determine the appropriate directory based on mode
    if mode == 'time-in':
        directory = FACE_TIME_IN_PATH
    else:  # mode == 'time-out'
        directory = FACE_TIME_OUT_PATH
    
    # Create filename in format [date]_[id].jpg
    filename = f"{current_date}_{student_id}.jpg"
    filepath = os.path.join(directory, filename)
    
    # Check if the file already exists (don't overwrite)
    if os.path.exists(filepath):
        return filepath  # Return existing file path
    
    # Resize image to save space
    resized_face = cv2.resize(face_image, SAVED_IMAGE_SIZE)
    
    # Save image with compression
    cv2.imwrite(filepath, resized_face, [cv2.IMWRITE_JPEG_QUALITY, SAVED_IMAGE_QUALITY])
    logger.info(f"Saved face image for student {student_id} in {mode} mode")
    
    return filepath

def update_attendance_record(student_id, request, face_image_b64=None, face_image=None):
    """Updates attendance when a student is recognized"""
    from .views import update_attendance_record as views_update_attendance
    
    # Get the mode from the request
    mode = request.GET.get('mode', 'time-in')
    
    # If we have a face image, save it to the filesystem
    image_path = None
    if face_image is not None:
        image_path = save_face_image(face_image, student_id, mode)
    
    # Call the original function in views
    return views_update_attendance(student_id, request, face_image_b64, image_path)

def find_closest_face(face_encoding):
    """Find the closest matching face using BallTree for faster queries"""
    global face_tree, student_ids_list
    
    if face_tree is None or len(student_ids_list) == 0:
        return "Unknown"
    
    # Reshape face encoding for BallTree query
    query_face = np.array([face_encoding])
    
    # Find distance and index of the nearest neighbor
    distances, indices = face_tree.query(query_face, k=1)
    
    # Check if it's a close enough match
    if distances[0][0] <= FACE_RECOGNITION_THRESHOLD:
        return student_ids_list[indices[0][0]]
    else:
        return "Unknown"

def generate_frame(face_recognition_enabled, request):
    """Generate video frames with optional face recognition"""
    global process_this_frame, frame_buffer, last_face_locations, last_face_names, last_face_times
    
    # Frame processing counter
    process_this_frame = 0
    
    while True:
        # Get the latest frame from the buffer
        with frame_lock:
            if frame_buffer is None:
                # No frame available yet
                time.sleep(0.01)
                continue
            
            # Make a copy to avoid modifying the buffer
            frame = frame_buffer.copy()
        
        display_frame = frame.copy()  # Create a copy for drawing
        current_time = time.time()
        
        if face_recognition_enabled:
            # Only process every 3rd frame to improve performance
            process_this_frame = (process_this_frame + 1) % 5
            
            if process_this_frame == 0 and len(student_encodings) > 0:
                # Resize frame for faster processing
                small_frame = cv2.resize(frame, (0, 0), fx=RESIZE_FACTOR, fy=RESIZE_FACTOR)
                rgb_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                
                # Find faces in the frame
                face_locations = face_recognition.face_locations(rgb_frame, model=FACE_RECOGNITION_MODEL)
                face_encodings = face_recognition.face_encodings(rgb_frame, face_locations)
                
                # Reset the arrays for this processing cycle
                current_face_locations = []
                current_face_names = []
                
                for face_encoding, (top, right, bottom, left) in zip(face_encodings, face_locations):
                    # Find closest face using face distance
                    name = find_closest_face(face_encoding)
                    
                    # Scale face coordinates back to original size
                    scale_factor = 1.0 / RESIZE_FACTOR
                    top = int(top * scale_factor)
                    right = int(right * scale_factor)
                    bottom = int(bottom * scale_factor)
                    left = int(left * scale_factor)
                    
                    # Save the face location and name for continuous display
                    current_face_locations.append((top, right, bottom, left))
                    current_face_names.append(name)
                    last_face_times[name] = current_time
                    
                    # Record attendance for recognized faces with the current mode
                    if name != "Unknown":
                        # Crop face image for display
                        face_image = frame[top:bottom, left:right].copy()
                        
                        # Convert to base64 for embedding in HTML
                        _, buffer = cv2.imencode('.jpg', face_image)
                        face_image_b64 = base64.b64encode(buffer).decode('utf-8')
                        
                        # Pass face image along with student data
                        student_data = update_attendance_record(name, request, face_image_b64, face_image)
                
                # Update the face tracking lists
                last_face_locations = current_face_locations
                last_face_names = current_face_names
            
            # Draw rectangles for all recent faces on every frame
            faces_to_remove = []
            for i, ((top, right, bottom, left), name) in enumerate(zip(last_face_locations, last_face_names)):
                # Check if this face has timed out
                if name in last_face_times and current_time - last_face_times[name] > FACE_DISPLAY_TIMEOUT:
                    faces_to_remove.append(i)
                    continue
                    
                # Draw face rectangle and name
                color = (0, 0, 255)  # Red for unknown
                if name != "Unknown":
                    color = (0, 255, 0)  # Green for recognized
                    
                # Draw rectangle and name on display frame
                cv2.rectangle(display_frame, (left, top), (right, bottom), color, 2)
                cv2.putText(display_frame, f"ID: {name}", (left, top - 10), 
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
            
            # Remove any timed out faces (in reverse order to avoid index issues)
            for i in sorted(faces_to_remove, reverse=True):
                if i < len(last_face_locations):
                    del last_face_locations[i]
                    del last_face_names[i]

        # Convert to JPEG for streaming (with lower quality for better performance)
        ret, jpeg = cv2.imencode('.jpg', display_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ret:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')

def start_camera_thread(camera_index=0):
    """Start the background thread for camera capture"""
    global is_capturing
    
    if not is_capturing:
        is_capturing = True
        initialize_camera(camera_index)
        thread = threading.Thread(target=capture_frames, daemon=True)
        thread.start()
        logger.info(f"Camera {camera_index} thread started")
        return True
    return False

def webcam_feed(request):
    """Stream webcam feed to the client"""
    # Get camera index (0 for front camera, 1 for back camera)
    camera_index = int(request.GET.get('camera', 0))
    
    # Check the appropriate session variable based on camera index
    if camera_index == 0:  # Front camera
        face_recognition_enabled = request.session.get('face_recognition_enabled', False) # Changed default to False
    else:  # Back camera
        face_recognition_enabled = request.session.get('back_camera_face_recognition_enabled', False) # Changed default to False
    
    # Log the current state for debugging
    logger.info(f"Camera {camera_index} face recognition enabled: {face_recognition_enabled}")
    
    # Get time-in/time-out mode from request
    mode = request.GET.get('mode', 'time-in')
    
    # Ensure camera is running in a separate thread
    start_camera_thread(camera_index)
    
    return StreamingHttpResponse(
        generate_frame(face_recognition_enabled, request), 
        content_type='multipart/x-mixed-replace; boundary=frame'
    )

def stop_webcam(request):
    """Stop the webcam feed"""
    global is_capturing, cap
    
    is_capturing = False
    if cap and cap.isOpened():
        cap.release()
        cap = None
        logger.info("Camera released")
    
    return JsonResponse({"status": "camera released"})

# Initialize student encodings and BallTree when the module is imported
ensure_directories_exist()
cleanup_old_images()  # Clean up old images at module load time
student_encodings, face_tree = load_student_face_encodings()
