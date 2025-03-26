# import face_recognition
# import os
# import cv2  # OpenCV only if needed for video capturing
# import numpy

# # Load known faces from your 'media/student face/[id].jpg' directory
# known_faces = []
# known_face_ids = []

# # Load images and get encodings
# for student_id in range(1, 6):  # Assuming you have faces for IDs 1 to 5
#     image_path = f"media/student face/{student_id}.jpg"
#     if os.path.exists(image_path):
#         image = face_recognition.load_image_file(image_path)
#         encoding = face_recognition.face_encodings(image)[0]  # Get the first face encoding
#         known_faces.append(encoding)
#         known_face_ids.append(student_id)

# # Initialize the webcam (using OpenCV to capture video)
# video_capture = cv2.VideoCapture(0)

# while True:
#     ret, frame = video_capture.read()
#     if not ret:
#         break

#     # Find faces in the frame
#     face_locations = face_recognition.face_locations(frame)
#     face_encodings = face_recognition.face_encodings(frame, face_locations)

#     # Check if any of the faces match the known faces
#     for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
#         matches = face_recognition.compare_faces(known_faces, face_encoding)

#         name = "Unknown"
#         face_distances = face_recognition.face_distance(known_faces, face_encoding)
#         best_match_index = numpy.argmin(face_distances)
#         if matches[best_match_index]:
#             name = str(known_face_ids[best_match_index])

#         # Draw a box around the face and label it
#         cv2.rectangle(frame, (left, top), (right, bottom), (0, 0, 255), 2)
#         font = cv2.FONT_HERSHEY_DUPLEX
#         cv2.putText(frame, name, (left + 6, bottom - 6), font, 0.5, (255, 255, 255), 1)

#     # Display the resulting frame with the recognized faces
#     cv2.imshow('Video', frame)

#     # Break on 'q' key
#     if cv2.waitKey(1) & 0xFF == ord('q'):
#         break

# video_capture.release()
# cv2.destroyAllWindows()
