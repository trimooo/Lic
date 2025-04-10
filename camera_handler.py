import cv2
import numpy as np
import threading
import logging
from typing import Optional

class CameraMode:
    NORMAL = "normal"
    GRAYSCALE = "grayscale" 
    BINARY = "binary"
    EDGE = "edge"
    MOTION = "motion"

class CameraHandler:
    def __init__(self):
        self.camera = None
        self.lock = threading.Lock()
        self.frame_buffer = None
        self.processing_frame = None
        self.is_running = False
        self.current_mode = CameraMode.NORMAL
        self.detection_settings = {
            'min_area': 500,
            'min_width': 125,
            'min_height': 30,
            'min_ratio': 2.0,
            'max_ratio': 5.0,
            'debug': False
        }

        # Load Haarcascade files
        self.cascade_files = [
            cv2.CascadeClassifier('haarcascade_russian_plate_number.xml'),
            cv2.CascadeClassifier('haarcascade_european_plate_number.xml')
        ]

        for cascade in self.cascade_files:
            if cascade.empty():
                logging.error("Error loading cascade file")

    def initialize(self, camera_index=0):
        with self.lock:
            if self.camera is None:
                self.camera = cv2.VideoCapture(camera_index)
                if not self.camera.isOpened():
                    logging.error("Failed to initialize camera")
                    return False

                # Set camera properties
                self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                self.camera.set(cv2.CAP_PROP_AUTOFOCUS, 1)
                self.camera.set(cv2.CAP_PROP_BRIGHTNESS, 150)
                self.is_running = True
                return True
            return True

    def get_frame(self):
        with self.lock:
            if self.camera and self.camera.isOpened():
                ret, frame = self.camera.read()
                if ret:
                    # Detect license plates
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    for cascade in self.cascade_files:
                        plates = cascade.detectMultiScale(gray, 1.1, 4)
                        for (x, y, w, h) in plates:
                            cv2.rectangle(frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                            plate_roi = gray[y:y+h, x:x+w]

                    self.processing_frame = frame
                    return True
                logging.error("Failed to capture frame")
            return False

    def update_frame_buffer(self, frame):
        with self.lock:
            if frame is not None:
                _, buffer = cv2.imencode('.jpg', frame)
                self.frame_buffer = buffer.tobytes()

    def release(self):
        with self.lock:
            if self.camera:
                self.camera.release()
                self.camera = None
            self.is_running = False

    def detect_license_plate(self, frame):
        if frame is None:
            return None, None

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        plates = self.plate_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(self.detection_settings['min_width'], self.detection_settings['min_height'])
        )

        best_plate = None
        best_score = 0
        best_coords = None

        for (x, y, w, h) in plates:
            area = w * h
            ratio = float(w) / h

            if (area > self.detection_settings['min_area'] and 
                self.detection_settings['min_ratio'] <= ratio <= self.detection_settings['max_ratio']):

                plate_img = gray[y:y+h, x:x+w]
                score = cv2.mean(plate_img)[0]  # Use brightness as a simple scoring method

                if score > best_score:
                    best_score = score
                    best_plate = plate_img
                    best_coords = (x, y, w, h)

        if best_plate is not None:
            # Additional preprocessing for OCR
            best_plate = cv2.GaussianBlur(best_plate, (5, 5), 0)
            best_plate = cv2.threshold(best_plate, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]

        return best_plate, best_coords