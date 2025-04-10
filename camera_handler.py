
import cv2
import numpy as np
import threading
import logging
from typing import Optional, Dict, Any

class CameraMode:
    NORMAL = "normal"
    GRAYSCALE = "grayscale"
    BINARY = "binary"
    EDGE_DETECTION = "edge"
    MOTION_DETECTION = "motion"

class AdvancedCameraHandler:
    def __init__(self):
        self.camera = None
        self.lock = threading.Lock()
        self.frame_buffer = None
        self.processing_frame = None
        self.is_running = False
        self.current_mode = CameraMode.NORMAL
        self.background_subtractor = cv2.createBackgroundSubtractorMOG2()
        self.last_frame = None
        self.detection_settings = {
            'brightness': 1.0,
            'contrast': 1.0,
            'threshold': 127,
            'edge_low': 50,
            'edge_high': 150,
            'motion_sensitivity': 20
        }

    def initialize(self, camera_index: int = 0) -> bool:
        with self.lock:
            if self.camera is None:
                self.camera = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
                if not self.camera.isOpened():
                    logging.error("Camera initialization failed")
                    return False
                self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                self.is_running = True
                return True
            return True

    def set_mode(self, mode: str) -> None:
        if mode in vars(CameraMode).values():
            self.current_mode = mode

    def update_settings(self, settings: Dict[str, Any]) -> None:
        self.detection_settings.update(settings)

    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        if frame is None:
            return None

        # Apply brightness and contrast
        processed = cv2.convertScaleAbs(frame, 
                                      alpha=self.detection_settings['brightness'],
                                      beta=self.detection_settings['contrast'])

        if self.current_mode == CameraMode.GRAYSCALE:
            return cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
        
        elif self.current_mode == CameraMode.BINARY:
            gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
            _, binary = cv2.threshold(gray, 
                                    self.detection_settings['threshold'],
                                    255, 
                                    cv2.THRESH_BINARY)
            return binary
        
        elif self.current_mode == CameraMode.EDGE_DETECTION:
            gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)
            return cv2.Canny(gray, 
                           self.detection_settings['edge_low'],
                           self.detection_settings['edge_high'])
        
        elif self.current_mode == CameraMode.MOTION_DETECTION:
            fgmask = self.background_subtractor.apply(processed)
            motion_threshold = self.detection_settings['motion_sensitivity']
            _, motion_binary = cv2.threshold(fgmask, motion_threshold, 255, cv2.THRESH_BINARY)
            return motion_binary

        return processed

    def get_frame(self) -> bool:
        with self.lock:
            if self.camera and self.camera.isOpened():
                ret, frame = self.camera.read()
                if ret:
                    self.processing_frame = self.process_frame(frame)
                    return True
                logging.error("Failed to capture frame")
            return False

    def update_frame_buffer(self, frame: np.ndarray) -> None:
        with self.lock:
            if frame is not None:
                _, buffer = cv2.imencode('.jpg', frame)
                self.frame_buffer = buffer.tobytes()

    def release(self) -> None:
        with self.lock:
            if self.camera:
                self.camera.release()
                self.camera = None
            self.is_running = False
