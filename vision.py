from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence

import cv2
import mediapipe as mp
import numpy as np
import pygame

import config
from utils import choose_nearest_hand, clamp, distance_sq


@dataclass
class CameraSettings:
    index: int = config.CAMERA_INDEX
    resolution: tuple[int, int] = config.CAMERA_RESOLUTION
    fps: int = config.CAMERA_FPS

    @property
    def width(self) -> int:
        return int(self.resolution[0])

    @property
    def height(self) -> int:
        return int(self.resolution[1])


@dataclass
class VisionResult:
    detected: bool = False
    index_tip_norm: Optional[tuple[float, float]] = None
    pinch_clicked: bool = False
    peace_triggered: bool = False
    frame: Optional[np.ndarray] = None


def should_pause_for_tracking(result: VisionResult, seconds_since_seen: float) -> bool:
    return (not result.detected) and seconds_since_seen > config.HAND_LOST_PAUSE_DELAY


class Smoother:
    def __init__(self, alpha: float = 0.35):
        self.alpha = alpha
        self.value: Optional[pygame.Vector2] = None

    def reset(self) -> None:
        self.value = None

    def update(self, point: tuple[float, float]) -> tuple[float, float]:
        target = pygame.Vector2(point)
        if self.value is None:
            self.value = target
        else:
            self.value = self.value.lerp(target, self.alpha)
        return self.value.x, self.value.y


class GestureTrigger:
    def __init__(self, cooldown: float):
        self.cooldown = cooldown
        self.was_active = False
        self.last_trigger_time = -9999.0

    def update(self, active: bool, now: float) -> bool:
        triggered = False
        if active and not self.was_active:
            if now - self.last_trigger_time >= self.cooldown:
                triggered = True
                self.last_trigger_time = now
        self.was_active = active
        return triggered


class VisionSystem:
    def __init__(self, camera_settings: CameraSettings = CameraSettings()):
        self.camera_settings = camera_settings
        cv2.setUseOptimized(True)
        self.cap = cv2.VideoCapture(camera_settings.index)
        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera_settings.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_settings.height)
            self.cap.set(cv2.CAP_PROP_FPS, camera_settings.fps)
            if hasattr(cv2, "CAP_PROP_ZOOM"):
                self.cap.set(cv2.CAP_PROP_ZOOM, 0)
        else:
            print("Camera unavailable. Check camera permissions, device connection, or camera index.")

        self.mp_hands = None
        self.drawer = None
        self.hands = None
        if not hasattr(mp, "solutions") or not hasattr(mp.solutions, "hands"):
            print(
                "MediaPipe Hands API is unavailable. Use the project Python 3.10 .venv "
                "or install a mediapipe version that supports mp.solutions.hands."
            )
        else:
            self.mp_hands = mp.solutions.hands
            self.drawer = mp.solutions.drawing_utils
            self.hands = self.mp_hands.Hands(
                max_num_hands=2,
                min_detection_confidence=0.65,
                min_tracking_confidence=0.65,
            )

        self.index_smoother = Smoother(alpha=0.35)
        self.pinch_trigger = GestureTrigger(config.PINCH_COOLDOWN)
        self.peace_trigger = GestureTrigger(config.PEACE_COOLDOWN)

        self.active_hand_locked = False
        self.active_hand_center: Optional[tuple[float, float]] = None
        self.last_seen_time = -9999.0
        self.reacquire_delay = config.HAND_REACQUIRE_DELAY

    @property
    def camera_ready(self) -> bool:
        return self.cap.isOpened()

    def seconds_since_seen(self, now: float) -> float:
        return now - self.last_seen_time

    def update(self, now: float) -> VisionResult:
        if not self.cap.isOpened():
            return VisionResult()

        ret, frame = self.cap.read()
        if not ret:
            return VisionResult()

        if self.hands is None:
            return VisionResult(frame=frame)

        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        results = self.hands.process(rgb)
        rgb.flags.writeable = True

        candidates: list[tuple[tuple[float, float], Any]] = []
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                candidates.append((self._hand_center(hand_landmarks), hand_landmarks))

        active_landmarks = self._select_active_hand(candidates, now)
        detected = active_landmarks is not None
        index_tip_norm = None
        pinch_clicked = False
        peace_triggered = False

        if detected:
            index_tip = active_landmarks.landmark[8]
            thumb_tip = active_landmarks.landmark[4]
            raw_index = (clamp(index_tip.x, 0.0, 1.0), clamp(index_tip.y, 0.0, 1.0))
            index_tip_norm = self.index_smoother.update(raw_index)

            pinch_active = (
                distance_sq((index_tip.x, index_tip.y), (thumb_tip.x, thumb_tip.y))
                < config.PINCH_THRESHOLD * config.PINCH_THRESHOLD
            )
            pinch_clicked = self.pinch_trigger.update(pinch_active, now)

            peace_triggered = self.peace_trigger.update(
                self._is_peace_gesture(active_landmarks), now
            )
        else:
            self.index_smoother.reset()
            self.pinch_trigger.update(False, now)
            self.peace_trigger.update(False, now)

        self._draw_hand_preview(frame, candidates, active_landmarks)
        return VisionResult(detected, index_tip_norm, pinch_clicked, peace_triggered, frame)

    def _select_active_hand(
        self, candidates: Sequence[tuple[tuple[float, float], Any]], now: float
    ) -> Optional[Any]:
        if not candidates:
            if self.active_hand_locked and now - self.last_seen_time > self.reacquire_delay:
                self.active_hand_locked = False
                self.active_hand_center = None
            return None

        if not self.active_hand_locked:
            center, landmarks = candidates[0]
            self.active_hand_locked = True
            self.active_hand_center = center
            self.last_seen_time = now
            return landmarks

        assert self.active_hand_center is not None
        selected = choose_nearest_hand(
            candidates, self.active_hand_center, config.ACTIVE_HAND_MAX_DISTANCE
        )
        if selected is None:
            if now - self.last_seen_time > self.reacquire_delay:
                self.active_hand_locked = False
                self.active_hand_center = None
                center, landmarks = candidates[0]
                self.active_hand_locked = True
                self.active_hand_center = center
                self.last_seen_time = now
                return landmarks
            return None

        self.active_hand_center, landmarks = selected
        self.last_seen_time = now
        return landmarks

    def _hand_center(self, hand_landmarks: Any) -> tuple[float, float]:
        indices = (0, 5, 9, 13, 17)
        x = sum(hand_landmarks.landmark[i].x for i in indices) / len(indices)
        y = sum(hand_landmarks.landmark[i].y for i in indices) / len(indices)
        return x, y

    def _is_peace_gesture(self, hand_landmarks: Any) -> bool:
        index_up = hand_landmarks.landmark[8].y < hand_landmarks.landmark[6].y
        middle_up = hand_landmarks.landmark[12].y < hand_landmarks.landmark[10].y
        ring_down = hand_landmarks.landmark[16].y > hand_landmarks.landmark[14].y
        pinky_down = hand_landmarks.landmark[20].y > hand_landmarks.landmark[18].y
        return index_up and middle_up and ring_down and pinky_down

    def _draw_hand_preview(
        self,
        frame: np.ndarray,
        candidates: Sequence[tuple[tuple[float, float], Any]],
        active_landmarks: Optional[Any],
    ) -> None:
        if self.drawer is None or self.mp_hands is None:
            return
        for _, landmarks in candidates:
            active = landmarks is active_landmarks
            point_color = (0, 255, 0) if active else (110, 110, 110)
            line_color = (255, 255, 255) if active else (80, 80, 80)
            self.drawer.draw_landmarks(
                frame,
                landmarks,
                self.mp_hands.HAND_CONNECTIONS,
                self.drawer.DrawingSpec(color=point_color, thickness=2, circle_radius=2),
                self.drawer.DrawingSpec(color=line_color, thickness=2, circle_radius=2),
            )

    def release(self) -> None:
        if self.cap.isOpened():
            self.cap.release()
        if self.hands is not None:
            self.hands.close()
