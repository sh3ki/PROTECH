# from sklearn.preprocessing import LabelEncoder
# from sklearn.svm import SVC
# import pickle
# import os
# from django.conf import settings
# import logging

# # Set up logging for better debugging and output management
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# def model_train():
#     try:
#         # Load the face embeddings
#         logger.info("[INFO] loading face embeddings...")
#         embeddings_path = os.path.join(settings.BASE_DIR, "output", "embeddings.pickle")
#         with open(embeddings_path, "rb") as f:
#             data = pickle.load(f)

#         # Encode the labels
#         logger.info("[INFO] encoding labels...")
#         le = LabelEncoder()
#         labels = le.fit_transform(data["names"])

#         # Train the model
#         logger.info("[INFO] training model...")
#         recognizer = SVC(C=1.0, kernel="linear", probability=True)
#         recognizer.fit(data["embeddings"], labels)

#         # Save the trained model to disk
#         recognizer_path = os.path.join(settings.BASE_DIR, "output", "recognizer.pickle")
#         with open(recognizer_path, "wb") as f:
#             pickle.dump(recognizer, f)

#         # Save the label encoder to disk
#         le_path = os.path.join(settings.BASE_DIR, "output", "le.pickle")
#         with open(le_path, "wb") as f:
#             pickle.dump(le, f)

#         logger.info("[INFO] model and label encoder saved successfully.")

#     except Exception as e:
#         logger.error(f"[ERROR] An error occurred while training the model: {e}")
