# from imutils.video import VideoStream
# from imutils.video import FPS
# import imutils
# import cv2
# import os
# import urllib.request
# import pickle
# import numpy as np
# from django.conf import settings
# from school import extract_embeddings
# from school import train_model

# # Load our serialized face detector model from disk
# protoPath = os.path.sep.join([settings.BASE_DIR, "face_detection_model", "deploy.prototxt"])
# modelPath = os.path.sep.join([settings.BASE_DIR, "face_detection_model", "res10_300x300_ssd_iter_140000.caffemodel"])
# detector = cv2.dnn.readNetFromCaffe(protoPath, modelPath)

# # Load our serialized face embedding model from disk
# embedder = cv2.dnn.readNetFromTorch(os.path.join(settings.BASE_DIR, 'face_detection_model', 'openface_nn4.small2.v1.t7'))

# # Load the actual face recognition model along with the label encoder
# recognizer_path = os.path.sep.join([settings.BASE_DIR, "output", "recognizer.pickle"])
# le_path = os.path.sep.join([settings.BASE_DIR, "output", "le.pickle"])

# # Debugging: Print file paths
# print(f"Recognizer path: {recognizer_path}")
# print(f"Label encoder path: {le_path}")

# # Load the actual face recognition model along with the label encoder
# try:
#     with open(recognizer_path, "rb") as f:
#         recognizer = pickle.load(f)
#     print("Recognizer model loaded successfully.")
# except Exception as e:
#     print(f"Error loading recognizer model: {e}")

# try:
#     with open(le_path, "rb") as f:
#         le = pickle.load(f)
#     print("Label encoder loaded successfully.")
# except Exception as e:
#     print(f"Error loading label encoder: {e}")


# dataset = os.path.sep.join([settings.BASE_DIR, "dataset"])
# user_list = [f.name for f in os.scandir(dataset) if f.is_dir()]

# class FaceDetect(object):
#     def __init__(self):
#         extract_embeddings.embeddings()
#         train_model.model_train()
#         # Initialize the video stream, then allow the camera sensor to warm up
#         self.vs = VideoStream(src=0).start()
#         # Start the FPS throughput estimator
#         self.fps = FPS().start()

#     def __del__(self):
#         cv2.destroyAllWindows()

#     def get_frame(self):
#         # Grab the frame from the threaded video stream
#         frame = self.vs.read()
#         frame = cv2.flip(frame, 1)

#         # Resize the frame to have a width of 600 pixels (while maintaining the aspect ratio), 
#         # and then grab the image dimensions
#         frame = imutils.resize(frame, width=600)
#         (h, w) = frame.shape[:2]

#         # Construct a blob from the image
#         imageBlob = cv2.dnn.blobFromImage(
#             cv2.resize(frame, (300, 300)), 1.0, (300, 300),
#             (104.0, 177.0, 123.0), swapRB=False, crop=False)

#         # Apply OpenCV's deep learning-based face detector to localize faces in the input image
#         detector.setInput(imageBlob)
#         detections = detector.forward()

#         # Loop over the detections
#         for i in range(0, detections.shape[2]):
#             # Extract the confidence (i.e., probability) associated with the prediction
#             confidence = detections[0, 0, i, 2]

#             # Filter out weak detections
#             if confidence > 0.5:
#                 # Compute the (x, y)-coordinates of the bounding box for the face
#                 box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
#                 (startX, startY, endX, endY) = box.astype("int")

#                 # Extract the face ROI
#                 face = frame[startY:endY, startX:endX]
#                 (fH, fW) = face.shape[:2]

#                 # Ensure the face width and height are sufficiently large
#                 if fW < 20 or fH < 20:
#                     continue

#                 # Construct a blob for the face ROI, then pass the blob through our face embedding model to obtain the 128-d quantification of the face
#                 faceBlob = cv2.dnn.blobFromImage(face, 1.0 / 255,
#                     (96, 96), (0, 0, 0), swapRB=True, crop=False)
#                 embedder.setInput(faceBlob)
#                 vec = embedder.forward()

#                 # Perform classification to recognize the face
#                 preds = recognizer.predict_proba(vec)[0]
#                 j = np.argmax(preds)
#                 proba = preds[j]
#                 name = le.classes_[j]

#                 # Draw the bounding box of the face along with the associated probability
#                 text = "{}: {:.2f}%".format(name, proba * 100)
#                 y = startY - 10 if startY - 10 > 10 else startY + 10
#                 cv2.rectangle(frame, (startX, startY), (endX, endY),
#                     (0, 0, 255), 2)
#                 cv2.putText(frame, text, (startX, y),
#                     cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 2)

#         # Update the FPS counter
#         self.fps.update()
#         ret, jpeg = cv2.imencode('.jpg', frame)
#         return jpeg.tobytes()
