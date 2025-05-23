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

# Initialize webcam - using dictionaries to support multiple cameras
cameras = {}  # Dictionary to store camera objects keyed by index
frame_buffers = {}  # Dictionary to store frames from different cameras
capture_threads = {}  # Dictionary to store camera capture threads
is_capturing = {}  # Dictionary to track which cameras are active
process_this_frame = {}  # Counter for frame processing (FPS control) per camera
should_flip_camera = {}  # Whether each camera should be flipped horizontally (default: true for front, false for back)

# Track last detected faces for continuous display - per camera
last_face_locations = {}  # Camera index -> list of face locations
last_face_names = {}  # Camera index -> list of face names
last_face_times = {}  # Student name -> timestamp of last detection per camera

FACE_DISPLAY_TIMEOUT = 1.0  # How long to keep showing a face after detection (seconds)

# Face recognition settings
FACE_RECOGNITION_THRESHOLD = 0.4  # Distance threshold
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
    global cameras
    
    # Release existing camera with this index if it exists
    if camera_index in cameras and cameras[camera_index] is not None:
        cameras[camera_index].release()
    
    # Initialize new camera
    camera = cv2.VideoCapture(camera_index)
    
    if camera.isOpened():
        # Reduce buffer size to minimize latency
        camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cameras[camera_index] = camera
        # Set flip behavior - front camera (0) flipped, back camera (1) not flipped
        should_flip_camera[camera_index] = (camera_index == 0) 
        logger.info(f"Camera {camera_index} initialized successfully (flip={should_flip_camera[camera_index]})")
        return True
    else:
        logger.error(f"Failed to initialize camera {camera_index}")
        cameras[camera_index] = None
        return False

def release_camera(camera_index=None):
    """Release the camera(s) when the application exits"""
    global cameras, is_capturing
    
    if camera_index is not None:
        # Release specific camera
        if camera_index in cameras and cameras[camera_index] is not None:
            is_capturing[camera_index] = False
            cameras[camera_index].release()
            cameras[camera_index] = None
            logger.info(f"Camera {camera_index} released")
    else:
        # Release all cameras
        for idx in list(cameras.keys()):
            if cameras[idx] is not None:
                is_capturing[idx] = False
                cameras[idx].release()
                cameras[idx] = None
        logger.info("All cameras released")

# Register the camera release function to run on exit
atexit.register(release_camera)

def capture_frames(camera_index):
    """Background thread to continuously capture frames from a specific camera"""
    global frame_buffers, is_capturing, cameras, last_error_time
    
    logger.info(f"Frame capture thread started for camera {camera_index}")
    
    # Initialize processor counter for this camera
    process_this_frame[camera_index] = 0
    
    # Initialize face tracking for this camera
    last_face_locations[camera_index] = []
    last_face_names[camera_index] = []
    
    while is_capturing.get(camera_index, False):
        if camera_index not in cameras or cameras[camera_index] is None or not cameras[camera_index].isOpened():
            # Try to reinitialize camera if needed
            time.sleep(0.5)
            try:
                initialize_camera(camera_index)
            except:
                # Avoid spamming logs
                current_time = time.time()
                if current_time - last_error_time > ERROR_LOG_INTERVAL:
                    logger.error(f"Camera {camera_index} not available")
                    last_error_time = current_time
            continue
            
        success, frame = cameras[camera_index].read()
        if success:
            # Flip horizontally for mirror effect only for front camera (index 0)
            if should_flip_camera.get(camera_index, False):
                frame = cv2.flip(frame, 1)
            
            # Thread-safe update of the frame buffer for this camera
            frame_buffers[camera_index] = frame
        else:
            # Avoid spamming logs
            current_time = time.time()
            if current_time - last_error_time > ERROR_LOG_INTERVAL:
                logger.error(f"Failed to read frame from camera {camera_index}")
                last_error_time = current_time
                
        # Slight delay to prevent maxing out CPU
        time.sleep(0.01)
    
    # Clean up when thread stops
    if camera_index in cameras and cameras[camera_index] is not None:
        cameras[camera_index].release()
        cameras[camera_index] = None
    
    logger.info(f"Frame capture thread stopped for camera {camera_index}")

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
    global process_this_frame, frame_buffers, last_face_locations, last_face_names, last_face_times
    
    # Get camera index from the request
    camera_index = int(request.GET.get('camera', 0))
    
    # Get time-in/time-out mode from request
    mode = request.GET.get('mode', 'time-in')
    
    # Initialize processing counter for this camera if needed
    if camera_index not in process_this_frame:
        process_this_frame[camera_index] = 0
    
    # Initialize face tracking lists for this camera if needed
    if camera_index not in last_face_locations:
        last_face_locations[camera_index] = []
    if camera_index not in last_face_names:
        last_face_names[camera_index] = []
    
    while True:
        # Get the latest frame from the buffer for this camera
        if camera_index not in frame_buffers or frame_buffers[camera_index] is None:
            # No frame available yet
            time.sleep(0.01)
            continue
        
        # Make a copy to avoid modifying the buffer
        frame = frame_buffers[camera_index].copy()
        display_frame = frame.copy()  # Create a copy for drawing
        current_time = time.time()
        
        if face_recognition_enabled:
            # Only process every few frames to improve performance
            process_this_frame[camera_index] = (process_this_frame[camera_index] + 1) % 5
            
            if process_this_frame[camera_index] == 0 and len(student_encodings) > 0:
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
                    
                    # Update last seen time for this face
                    if name not in last_face_times:
                        last_face_times[name] = {}
                    last_face_times[name][camera_index] = current_time
                    
                    # Record attendance for recognized faces with the current mode
                    if name != "Unknown":
                        # Crop face image for display
                        face_image = frame[top:bottom, left:right].copy()
                        
                        # Convert to base64 for embedding in HTML
                        _, buffer = cv2.imencode('.jpg', face_image)
                        face_image_b64 = base64.b64encode(buffer).decode('utf-8')
                        
                        # Pass face image along with student data
                        student_data = update_attendance_record(name, request, face_image_b64, face_image)
                
                # Update the face tracking lists for this camera
                last_face_locations[camera_index] = current_face_locations
                last_face_names[camera_index] = current_face_names
            
            # Draw rectangles for all recent faces on every frame
            faces_to_remove = []
            for i, ((top, right, bottom, left), name) in enumerate(zip(
                    last_face_locations[camera_index], 
                    last_face_names[camera_index])):
                
                # Check if this face has timed out
                if (name in last_face_times and 
                    camera_index in last_face_times[name] and 
                    current_time - last_face_times[name][camera_index] > FACE_DISPLAY_TIMEOUT):
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
                if i < len(last_face_locations[camera_index]):
                    del last_face_locations[camera_index][i]
                    del last_face_names[camera_index][i]

        # Convert to JPEG for streaming (with lower quality for better performance)
        ret, jpeg = cv2.imencode('.jpg', display_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        if not ret:
            continue

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n\r\n')

def start_camera_thread(camera_index=0):
    """Start the background thread for camera capture"""
    global is_capturing, capture_threads
    
    # Check if this camera is already capturing
    if camera_index not in is_capturing or not is_capturing[camera_index]:
        # Set up camera
        initialize_camera(camera_index)
        
        # Start capture thread for this camera
        is_capturing[camera_index] = True
        thread = threading.Thread(target=capture_frames, args=(camera_index,), daemon=True)
        capture_threads[camera_index] = thread
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
        face_recognition_enabled = request.session.get('face_recognition_enabled', False)
    else:  # Back camera
        face_recognition_enabled = request.session.get('back_camera_face_recognition_enabled', False)
    
    # Log the current state for debugging
    logger.info(f"Camera {camera_index} face recognition enabled: {face_recognition_enabled}")
    
    # Ensure camera is running in a separate thread
    start_camera_thread(camera_index)
    
    return StreamingHttpResponse(
        generate_frame(face_recognition_enabled, request), 
        content_type='multipart/x-mixed-replace; boundary=frame'
    )

def stop_webcam(request):
    """Stop the webcam feed"""
    # Get camera index from request or default to 0
    camera_index = int(request.GET.get('camera', 0))
    
    # Stop only the requested camera
    release_camera(camera_index)
    
    return JsonResponse({"status": f"Camera {camera_index} released"})

def add_student_face_encoding(student_id):
    """
    Add a single student's face encoding to the existing encodings
    without having to reload all encodings.
    
    Args:
        student_id: The LRN or ID of the student to add
    
    Returns:
        bool: True if successfully added, False otherwise
    """
    global student_encodings, student_encodings_array, student_ids_list, face_tree, student_names
    
    image_path = os.path.join(FACE_IMAGES_PATH, f"{student_id}.jpg")
    
    if not os.path.exists(image_path):
        logger.error(f"Face image for student {student_id} does not exist at {image_path}")
        return False
    
    try:
        # Load and encode the image
        student_image = face_recognition.load_image_file(image_path)
        student_encoding = face_recognition.face_encodings(student_image)
        
        if not student_encoding:
            logger.error(f"Could not find a face in the image for student {student_id}")
            return False
            
        # Add to the dictionary
        student_encodings[student_id] = student_encoding[0]
        
        # Add to the list of IDs
        student_ids_list.append(student_id)
        student_names.append(student_id)  # For backward compatibility
        
        # Add to the numpy array
        if student_encodings_array is None or len(student_encodings_array) == 0:
            student_encodings_array = np.array([student_encoding[0]])
        else:
            student_encodings_array = np.vstack((student_encodings_array, student_encoding[0]))
        
        # Rebuild the BallTree with the updated numpy array
        if student_encodings_array is not None and len(student_encodings_array) > 0:
            face_tree = BallTree(student_encodings_array, leaf_size=2)
            
        logger.info(f"Successfully added face encoding for student {student_id}")
        return True
    except Exception as e:
        logger.error(f"Error adding face encoding for student {student_id}: {str(e)}")
        return False

# Initialize student encodings and BallTree when the module is imported
ensure_directories_exist()
cleanup_old_images()  # Clean up old images at module load time
student_encodings, face_tree = load_student_face_encodings()
