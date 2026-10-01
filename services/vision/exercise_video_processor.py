import os
import cv2
import av
import numpy as np
import mediapipe as mp
import streamlit as st
import threading
from streamlit_webrtc import VideoProcessorBase
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from detectors.squat import SquatDetector
from detectors.pushup import PushUpDetector
from detectors.biceps_curl import BicepsCurlDetector
from detectors.shoulder_press import ShoulderPressDetector
from detectors.lunges import LungesDetector
from services.config.workout_config import POSE_CONNECTIONS
from services.ui.scoreboard import exercise_colors

SKELETON_COLOR = (255, 255, 255)
LABEL_COLOR = (255, 255, 255)
LABEL_BACKGROUND_COLOR = (58, 21, 23)  # ink #17153A in BGR


def _label(status):
    text = str(status)
    return text[:1].upper() + text[1:].lower()


@st.cache_data(show_spinner="Preparing pose detection...")
def load_pose_model(model_path):
    with open(model_path, "rb") as model_file:
        return model_file.read()


def create_pose_landmarker(model_path):
    base_option = python.BaseOptions(model_asset_buffer=load_pose_model(model_path))
    options = vision.PoseLandmarkerOptions(
        base_options=base_option,
        running_mode=vision.RunningMode.VIDEO,
        min_pose_detection_confidence=0.7,
        min_pose_presence_confidence=0.7,
        min_tracking_confidence=0.7,
        output_segmentation_masks=False
    )
    return vision.PoseLandmarker.create_from_options(options)


def warm_up_pose_model():
    model_path = os.path.join(os.getcwd(), "ml_models", "pose_landmarker_full.task")
    load_pose_model(model_path)


class VideoProcessorClass(VideoProcessorBase):
    def __init__(self):
        self._lock = threading.Lock()
        self._latest_metrics = None
        self._exercise_type = "Squats"

        model_path = os.path.join(os.getcwd(), "ml_models", "pose_landmarker_full.task")
        self._landmarker = create_pose_landmarker(model_path)

        self._detectors = {
            "Squats": SquatDetector(),
            "Push-ups": PushUpDetector(),
            "Biceps Curls (Dumbbell)": BicepsCurlDetector(),
            "Shoulder Press": ShoulderPressDetector(),
            "Lunges": LungesDetector(),
        }

        self._frame_timestamps_ms = 0
    
    def set_latest_metrics(self, metrics):
        with self._lock:
            self._latest_metrics = metrics.copy()

    def get_latest_metrics(self):
        with self._lock:
            return None if self._latest_metrics is None else self._latest_metrics.copy()
        
    def set_exercise(self, exercise_type):
        with self._lock:
            self._exercise_type = exercise_type

    def get_exercise(self):
        with self._lock:
            return self._exercise_type
        
    def _joint_color(self):
        fill = exercise_colors(self.get_exercise())[0].lstrip("#")
        r, g, b = (int(fill[i:i + 2], 16) for i in (0, 2, 4))
        return (b, g, r)

    def _put_label(self, img, text, org):
        """Draw text on a solid ink tag so it stays readable on any background."""
        (text_w, text_h), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.8, 2)
        x, y = org
        pad = 10
        cv2.rectangle(
            img,
            (x - pad, y - text_h - pad),
            (x + text_w + pad, y + baseline + pad // 2),
            LABEL_BACKGROUND_COLOR,
            -1,
        )
        cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, 0.8, LABEL_COLOR, 2, cv2.LINE_AA)

    def _draw_skeleton(self, img, landmarks):
        h, w = img.shape[:2]
        joint_color = self._joint_color()

        for start_idx, end_idx in POSE_CONNECTIONS:
            p1 = landmarks[start_idx]
            p2 = landmarks[end_idx]

            if p1.visibility > 0.7 and p2.visibility > 0.7:
                cv2.line(
                    img,
                    (int(p1.x * w), int(p1.y * h)),
                    (int(p2.x * w), int(p2.y * h)),
                    SKELETON_COLOR,
                    4,
                    cv2.LINE_AA,
                )
        
        for lm in landmarks:
            if lm.visibility > 0.7:
                cv2.circle(
                    img, 
                    (int(lm.x * w), int(lm.y * h)),
                    7,
                    joint_color,
                    -1,
                    cv2.LINE_AA,
                )
            
    def _draw_no_pose_warnings(self, img):
        self._put_label(img, "No pose detected", (30, 50))

        self._put_label(img, "Step back and face the camera", (30, 95))

    def _draw_overlays(self, img, metrics, ex_type):
        if ex_type == "Squats":
            self._draw_squats_overlays(img, metrics)
        elif ex_type == "Push-ups":
            self._draw_pushup_overlays(img, metrics)
        elif ex_type == "Biceps Curls (Dumbbell)":
            self._draw_curl_overlays(img, metrics)
        elif ex_type == "Shoulder Press":
            self._draw_press_overlays(img, metrics)
        elif ex_type == "Lunges":
            self._draw_lunge_overlays(img, metrics)


    def _draw_squats_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        self._put_label(img, f"Depth: {_label(metrics['depth_status'])}", (24, h - 24))
    
    def _draw_pushup_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        self._put_label(img, f"Body: {_label(metrics['body_alignment'])}   Hips: {_label(metrics['hip_status'])}", (24, h - 24))

    def _draw_curl_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        self._put_label(img, f"Swing: {_label(metrics['swing_status'])}", (24, h - 24))

    def _draw_press_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        self._put_label(img, f"Arms: {_label(metrics['extension_status'])}   Back: {_label(metrics['back_arch_status'])}", (24, h - 24))

    def _draw_lunge_overlays(self, img, metrics):
        h, _ = img.shape[:2]

        self._put_label(img, f"Balance: {_label(metrics['balance_status'])}", (24, h - 24))

    def recv(self, frame):
        image = np.asarray(
            cv2.flip(frame.to_ndarray(format="bgr24"), 1),
            dtype=np.uint8
        )

        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
        )

        self._frame_timestamps_ms += 30
        result = self._landmarker.detect_for_video(mp_image, self._frame_timestamps_ms)

        if result.pose_landmarks:
            landmarks = result.pose_landmarks[0]

            self._draw_skeleton(image, landmarks)

            ex_type = self.get_exercise()

            detector = self._detectors.get(ex_type)

            if detector:
                metrics = detector.process(landmarks)

                metrics["pose_detected"] = True

                self._draw_overlays(image, metrics, ex_type)

                self.set_latest_metrics(metrics)
        else:
            self._draw_no_pose_warnings(image)
            
            with self._lock:
                if self._latest_metrics is not None:
                    self._latest_metrics["pose_detected"] = False
                else:
                    self._latest_metrics = {"pose_detected": False}

        return av.VideoFrame.from_ndarray(image, format="bgr24")
    