from __future__ import annotations

import math
import os
import random
import sys
from dataclasses import dataclass
from typing import Any, Iterable, Optional, Sequence

import cv2
import mediapipe as mp
import numpy as np
import pygame


# Window layout
WINDOW_WIDTH = 1400
WINDOW_HEIGHT = 800
SIDEBAR_WIDTH = 350
GAME_WIDTH = WINDOW_WIDTH - SIDEBAR_WIDTH

# Camera settings
CAMERA_INDEX = 0
CAMERA_RESOLUTION = (640, 480)
CAMERA_WIDTH = CAMERA_RESOLUTION[0]
CAMERA_HEIGHT = CAMERA_RESOLUTION[1]
CAMERA_FPS = 30

# Colors
COLOR_BG_GAME = (20, 20, 25)
COLOR_BG_SIDEBAR = (10, 10, 15)
COLOR_PANEL = (28, 30, 42)
COLOR_PANEL_DARK = (18, 20, 28)
COLOR_GRID = (30, 30, 38)
COLOR_SNAKE_BODY = (46, 204, 113)
COLOR_SNAKE_BODY_ALT = (40, 180, 100)
COLOR_SNAKE_OUTLINE = (30, 130, 76)
COLOR_SNAKE_HEAD = (241, 196, 15)
COLOR_FOOD = (231, 76, 60)
COLOR_BIG_FOOD = (255, 45, 45)
COLOR_TEXT = (255, 255, 255)
COLOR_TEXT_MUTED = (170, 176, 190)
COLOR_ACCENT = (52, 152, 219)
COLOR_WARNING = (255, 200, 0)
COLOR_DANGER = (255, 70, 70)
COLOR_SUCCESS = (70, 255, 150)

# Game physics
FPS = 60
SNAKE_RADIUS = 16
BODY_POINT_SPACING = 8
START_LENGTH = 20
NORMAL_GROWTH = 1
BIG_GROWTH = 3
NORMAL_FOOD_SCORE = 10
BIG_FOOD_SCORE = 50
BIG_FOOD_EVERY = 5
BIG_FOOD_DURATION = 5.0
INVINCIBLE_SECONDS = 3.0

# Speed is the snake's maximum follow speed; it is not multiplied by hand movement speed.
BASE_SPEED = 180
SPEED_INCREASE_PER_APPLE = 8
MAX_SPEED = 420

# Gesture tuning
PINCH_THRESHOLD = 0.055
PINCH_COOLDOWN = 0.35
PEACE_COOLDOWN = 0.80
HAND_LOST_PAUSE_DELAY = 0.50
HAND_REACQUIRE_DELAY = 1.00
ACTIVE_HAND_MAX_DISTANCE = 0.28

# Pointer sensitivity scales hand movement around the camera center.
# Higher values mean a smaller physical hand movement controls the full map.
SENSITIVITY_OPTIONS = [
    ("标准", 1.0),
    ("灵敏", 3.0),
    ("高灵敏", 4.0),
    ("超高", 6.0),
]
DEFAULT_SENSITIVITY_INDEX = 2

STATE_MENU = "MENU"
STATE_PLAYING_SINGLE = "PLAYING_SINGLE"
STATE_PAUSED = "PAUSED"
STATE_GAMEOVER = "GAMEOVER"
STATE_COMING_SOON = "COMING_SOON"
STATE_OPTIONS = "OPTIONS"

CJK_FONT_FILES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\NotoSansSC-VF.ttf",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
]
CJK_FONTS = CJK_FONT_FILES + [
    "microsoftyahei",
    "simhei",
    "simsun",
    "notosanssc",
    "arial unicode ms",
    "arial",
]


def load_font(name: str | Sequence[str], size: int, bold: bool = False) -> pygame.font.Font:
    names = [name] if isinstance(name, str) else list(name)
    for candidate in names:
        if os.path.exists(candidate):
            try:
                return pygame.font.Font(candidate, size)
            except (OSError, pygame.error):
                continue
        matched_path = pygame.font.match_font(candidate, bold=bold)
        if matched_path:
            try:
                return pygame.font.Font(matched_path, size)
            except (OSError, pygame.error):
                continue
        try:
            font = pygame.font.SysFont(candidate, size, bold=bold)
        except (TypeError, OSError):
            continue
        if font is not None:
            return font
    return pygame.font.Font(None, size)


def find_existing_font_file(candidates: Sequence[str]) -> Optional[str]:
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def distance_sq(a: tuple[float, float] | pygame.Vector2, b: tuple[float, float] | pygame.Vector2) -> float:
    dx = float(a[0]) - float(b[0])
    dy = float(a[1]) - float(b[1])
    return dx * dx + dy * dy


def current_speed_for_apples(apples_eaten: int) -> int:
    return min(BASE_SPEED + apples_eaten * SPEED_INCREASE_PER_APPLE, MAX_SPEED)


def wrap_in_game_area(position: pygame.Vector2) -> pygame.Vector2:
    wrapped = pygame.Vector2(position)
    while wrapped.x < SIDEBAR_WIDTH:
        wrapped.x += GAME_WIDTH
    while wrapped.x > WINDOW_WIDTH:
        wrapped.x -= GAME_WIDTH
    while wrapped.y < 0:
        wrapped.y += WINDOW_HEIGHT
    while wrapped.y > WINDOW_HEIGHT:
        wrapped.y -= WINDOW_HEIGHT
    return wrapped


def norm_to_window(norm: tuple[float, float]) -> tuple[int, int]:
    return int(clamp(norm[0], 0.0, 1.0) * WINDOW_WIDTH), int(
        clamp(norm[1], 0.0, 1.0) * WINDOW_HEIGHT
    )


def apply_pointer_sensitivity(
    norm: tuple[float, float], sensitivity: float
) -> tuple[float, float]:
    scaled_x = 0.5 + (clamp(norm[0], 0.0, 1.0) - 0.5) * sensitivity
    scaled_y = 0.5 + (clamp(norm[1], 0.0, 1.0) - 0.5) * sensitivity
    return round(clamp(scaled_x, 0.0, 1.0), 6), round(clamp(scaled_y, 0.0, 1.0), 6)


def index_to_game_target(
    norm: tuple[float, float], sensitivity: float = 1.0
) -> pygame.Vector2:
    target_norm = apply_pointer_sensitivity(norm, sensitivity)
    return pygame.Vector2(
        SIDEBAR_WIDTH + target_norm[0] * GAME_WIDTH,
        target_norm[1] * WINDOW_HEIGHT,
    )


def next_sensitivity_index(current: int, delta: int) -> int:
    return int(clamp(current + delta, 0, len(SENSITIVITY_OPTIONS) - 1))


def move_toward(
    current: pygame.Vector2, target: pygame.Vector2, max_distance: float
) -> pygame.Vector2:
    delta = target - current
    distance = delta.length()
    if distance == 0 or distance <= max_distance:
        return pygame.Vector2(target)
    return pygame.Vector2(current) + delta / distance * max_distance


def extend_body_trail(
    body: list[pygame.Vector2],
    previous_head: pygame.Vector2,
    new_head: pygame.Vector2,
    target_segments: int,
    spacing: float = BODY_POINT_SPACING,
) -> None:
    if not body:
        body.append(pygame.Vector2(new_head))
        return

    movement = new_head - body[0]
    distance = movement.length()
    if distance < spacing:
        return

    steps = max(1, math.floor(distance / spacing))
    samples = [body[0].lerp(new_head, i / steps) for i in range(steps, 0, -1)]
    body[:0] = samples

    while len(body) > target_segments:
        body.pop()


def choose_nearest_hand(
    hands: Sequence[tuple[tuple[float, float], Any]],
    previous_center: tuple[float, float],
    max_distance: float,
) -> Optional[tuple[tuple[float, float], Any]]:
    if not hands:
        return None

    nearest = min(hands, key=lambda item: distance_sq(item[0], previous_center))
    if distance_sq(nearest[0], previous_center) <= max_distance * max_distance:
        return nearest
    return None


@dataclass
class CameraSettings:
    index: int = CAMERA_INDEX
    resolution: tuple[int, int] = CAMERA_RESOLUTION
    fps: int = CAMERA_FPS

    @property
    def width(self) -> int:
        return int(self.resolution[0])

    @property
    def height(self) -> int:
        return int(self.resolution[1])


@dataclass
class Food:
    position: pygame.Vector2
    radius: int
    score: int
    growth: int
    color: tuple[int, int, int]
    spawn_time: Optional[float] = None
    duration: Optional[float] = None

    def is_expired(self, now: float) -> bool:
        if self.spawn_time is None or self.duration is None:
            return False
        return now - self.spawn_time > self.duration

    def overlaps(self, position: pygame.Vector2, radius: float) -> bool:
        limit = self.radius + radius
        return distance_sq(self.position, position) < limit * limit

    def remaining(self, now: float) -> float:
        if self.spawn_time is None or self.duration is None:
            return 0.0
        return max(0.0, self.duration - (now - self.spawn_time))


@dataclass
class VisionResult:
    detected: bool = False
    index_tip_norm: Optional[tuple[float, float]] = None
    pinch_clicked: bool = False
    peace_triggered: bool = False
    frame: Optional[np.ndarray] = None


def should_pause_for_tracking(
    result: VisionResult, seconds_since_seen: float
) -> bool:
    return (not result.detected) and seconds_since_seen > HAND_LOST_PAUSE_DELAY


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


class Button:
    def __init__(
        self,
        rect: pygame.Rect,
        text: str,
        subtitle: str = "",
        accent: tuple[int, int, int] = COLOR_ACCENT,
    ):
        self.rect = rect
        self.text = text
        self.subtitle = subtitle
        self.accent = accent

    def hovered(self, point: Optional[tuple[int, int]]) -> bool:
        return point is not None and self.rect.collidepoint(point)

    def clicked(
        self,
        cursor_pos: Optional[tuple[int, int]],
        pinch_clicked: bool,
        mouse_pos: Optional[tuple[int, int]] = None,
        mouse_clicked: bool = False,
    ) -> bool:
        return (pinch_clicked and self.hovered(cursor_pos)) or (
            mouse_clicked and self.hovered(mouse_pos)
        )

    def draw(
        self,
        screen: pygame.Surface,
        font: pygame.font.Font,
        small_font: pygame.font.Font,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: Optional[tuple[int, int]] = None,
    ) -> None:
        is_hovered = self.hovered(cursor_pos) or self.hovered(mouse_pos)
        fill = (38, 44, 62) if not is_hovered else (52, 65, 92)
        border = self.accent if is_hovered else (80, 90, 112)

        pygame.draw.rect(screen, fill, self.rect, border_radius=8)
        pygame.draw.rect(screen, border, self.rect, 2, border_radius=8)

        label = font.render(self.text, True, COLOR_TEXT)
        screen.blit(label, label.get_rect(center=(self.rect.centerx, self.rect.centery - 8)))
        if self.subtitle:
            sub = small_font.render(self.subtitle, True, COLOR_TEXT_MUTED)
            screen.blit(sub, sub.get_rect(center=(self.rect.centerx, self.rect.centery + 22)))


class VisionSystem:
    def __init__(self, camera_settings: CameraSettings = CameraSettings()):
        self.camera_settings = camera_settings
        cv2.setUseOptimized(True)
        self.cap = cv2.VideoCapture(camera_settings.index)
        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, camera_settings.width)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, camera_settings.height)
            self.cap.set(cv2.CAP_PROP_FPS, camera_settings.fps)
        else:
            print("摄像头无法打开：请检查摄像头权限、设备连接或尝试更换摄像头索引。")

        self.mp_hands = None
        self.drawer = None
        self.hands = None
        if not hasattr(mp, "solutions") or not hasattr(mp.solutions, "hands"):
            print(
                "MediaPipe Hands API 不可用：请使用项目 .venv 的 Python 3.10，"
                "或安装支持 mp.solutions.hands 的 mediapipe 版本。"
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
        self.pinch_trigger = GestureTrigger(PINCH_COOLDOWN)
        self.peace_trigger = GestureTrigger(PEACE_COOLDOWN)

        self.active_hand_locked = False
        self.active_hand_center: Optional[tuple[float, float]] = None
        self.last_seen_time = -9999.0
        self.reacquire_delay = HAND_REACQUIRE_DELAY

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

            # Pinch click logic: only the index/thumb rising edge can click a button.
            pinch_active = (
                distance_sq((index_tip.x, index_tip.y), (thumb_tip.x, thumb_tip.y))
                < PINCH_THRESHOLD * PINCH_THRESHOLD
            )
            pinch_clicked = self.pinch_trigger.update(pinch_active, now)

            # Peace gesture is reserved for Game Over restart, not active pause.
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
            candidates, self.active_hand_center, ACTIVE_HAND_MAX_DISTANCE
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
        # Hand locking uses several stable palm landmarks so a second hand cannot steal control.
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


class SnakeGame:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Gesture Snake")
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.clock = pygame.time.Clock()
        self.vision = VisionSystem()

        self.font_title = load_font(CJK_FONTS, 64, bold=True)
        self.font_big = load_font(CJK_FONTS, 48, bold=True)
        self.font_med = load_font(CJK_FONTS, 28, bold=True)
        self.font_button = load_font(CJK_FONTS, 26, bold=True)
        self.font_small = load_font(CJK_FONTS, 18)
        self.font_tiny = load_font(CJK_FONTS, 15)

        self.state = STATE_MENU
        self.pause_reason: Optional[str] = None
        self.cam_surface: Optional[pygame.Surface] = None
        self.background = self._build_background()

        self.menu_buttons: list[tuple[str, Button]] = []
        self.options_buttons: list[tuple[str, Button]] = []
        self.pause_buttons: list[tuple[str, Button]] = []
        self.gameover_buttons: list[tuple[str, Button]] = []
        self.coming_soon_buttons: list[tuple[str, Button]] = []
        self.sensitivity_index = DEFAULT_SENSITIVITY_INDEX
        self._create_buttons()

        self.reset_game(0.0)

    def _build_background(self) -> pygame.Surface:
        surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
        surface.fill(COLOR_BG_GAME)
        pygame.draw.rect(surface, COLOR_BG_SIDEBAR, (0, 0, SIDEBAR_WIDTH, WINDOW_HEIGHT))
        pygame.draw.line(surface, (50, 50, 60), (SIDEBAR_WIDTH, 0), (SIDEBAR_WIDTH, WINDOW_HEIGHT), 2)
        for x in range(SIDEBAR_WIDTH, WINDOW_WIDTH, 80):
            pygame.draw.line(surface, COLOR_GRID, (x, 0), (x, WINDOW_HEIGHT))
        for y in range(0, WINDOW_HEIGHT, 80):
            pygame.draw.line(surface, COLOR_GRID, (SIDEBAR_WIDTH, y), (WINDOW_WIDTH, y))
        return surface

    def _create_buttons(self) -> None:
        center_x = SIDEBAR_WIDTH + GAME_WIDTH // 2
        w, h = 320, 74
        self.menu_buttons = [
            ("single", Button(pygame.Rect(center_x - w // 2, 270, w, h), "单人模式", "Endless")),
            ("options", Button(pygame.Rect(center_x - w // 2, 356, w, h), "选项设置", "灵敏度")),
            ("level", Button(pygame.Rect(center_x - w // 2, 442, w, h), "闯关模式", "开发中 / Coming Soon", COLOR_WARNING)),
            ("duo", Button(pygame.Rect(center_x - w // 2, 528, w, h), "双人模式", "开发中 / Coming Soon", COLOR_WARNING)),
        ]
        self.options_buttons = [
            ("sensitivity_down", Button(pygame.Rect(center_x - 250, 400, 110, 64), "降低")),
            ("sensitivity_up", Button(pygame.Rect(center_x + 140, 400, 110, 64), "提高")),
            ("menu", Button(pygame.Rect(center_x - w // 2, 540, w, h), "返回菜单")),
        ]
        self.pause_buttons = [
            ("resume", Button(pygame.Rect(center_x - w // 2, 330, w, h), "继续游戏")),
            ("restart", Button(pygame.Rect(center_x - w // 2, 422, w, h), "重新开始")),
            ("menu", Button(pygame.Rect(center_x - w // 2, 514, w, h), "返回菜单")),
        ]
        self.gameover_buttons = [
            ("restart", Button(pygame.Rect(center_x - w // 2, 410, w, h), "重新开始")),
            ("menu", Button(pygame.Rect(center_x - w // 2, 502, w, h), "返回菜单")),
        ]
        self.coming_soon_buttons = [
            ("menu", Button(pygame.Rect(center_x - w // 2, 500, w, h), "返回菜单")),
        ]

    def reset_game(self, now: float) -> None:
        cx = SIDEBAR_WIDTH + GAME_WIDTH // 2
        cy = WINDOW_HEIGHT // 2
        self.head_pos = pygame.Vector2(cx, cy)
        self.target_pos = pygame.Vector2(cx, cy)
        self.direction = pygame.Vector2(1, 0)
        self.target_segments = START_LENGTH
        self.body = [
            pygame.Vector2(cx - i * BODY_POINT_SPACING, cy) for i in range(START_LENGTH)
        ]
        self.score = 0
        self.apples_eaten = 0
        self.invincible_until = now + INVINCIBLE_SECONDS
        self.normal_food = self._spawn_food(
            radius=14,
            score=NORMAL_FOOD_SCORE,
            growth=NORMAL_GROWTH,
            color=COLOR_FOOD,
        )
        self.big_food: Optional[Food] = None

    def _spawn_food(
        self,
        radius: int,
        score: int,
        growth: int,
        color: tuple[int, int, int],
        now: Optional[float] = None,
        duration: Optional[float] = None,
        avoid: Iterable[Food] = (),
    ) -> Food:
        pad = radius + 25
        avoid_list = list(avoid)
        for _ in range(200):
            pos = pygame.Vector2(
                random.randint(SIDEBAR_WIDTH + pad, WINDOW_WIDTH - pad),
                random.randint(pad, WINDOW_HEIGHT - pad),
            )
            candidate = Food(pos, radius, score, growth, color, now, duration)
            if not any(item.overlaps(pos, radius + 20) for item in avoid_list):
                return candidate
        return Food(pos, radius, score, growth, color, now, duration)

    def start_single_mode(self, now: float) -> None:
        self.reset_game(now)
        self.state = STATE_PLAYING_SINGLE
        self.pause_reason = None

    @property
    def current_sensitivity(self) -> float:
        return SENSITIVITY_OPTIONS[self.sensitivity_index][1]

    @property
    def current_sensitivity_label(self) -> str:
        label, value = SENSITIVITY_OPTIONS[self.sensitivity_index]
        return f"{label} x{value:g}"

    def run(self) -> None:
        running = True
        while running:
            dt = min(self.clock.tick(FPS) / 1000.0, 0.05)
            now = pygame.time.get_ticks() / 1000.0
            mouse_clicked = False
            mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mouse_clicked = True

            result = self.vision.update(now)
            self._update_camera_surface(result.frame)
            cursor_pos = self._cursor_pos(result)

            if self.state == STATE_MENU:
                self._handle_menu(result, cursor_pos, mouse_pos, mouse_clicked, now)
            elif self.state == STATE_PLAYING_SINGLE:
                self._handle_playing(result, dt, now)
            elif self.state == STATE_PAUSED:
                self._handle_paused(result, cursor_pos, mouse_pos, mouse_clicked, now)
            elif self.state == STATE_GAMEOVER:
                self._handle_gameover(result, cursor_pos, mouse_pos, mouse_clicked, now)
            elif self.state == STATE_COMING_SOON:
                self._handle_coming_soon(result, cursor_pos, mouse_pos, mouse_clicked)
            elif self.state == STATE_OPTIONS:
                self._handle_options(result, cursor_pos, mouse_pos, mouse_clicked)

            self.draw(result, cursor_pos, mouse_pos, now)

        self.vision.release()
        pygame.quit()
        sys.exit()

    def _cursor_pos(self, result: VisionResult) -> Optional[tuple[int, int]]:
        if result.detected and result.index_tip_norm is not None:
            return norm_to_window(result.index_tip_norm)
        return None

    def _update_camera_surface(self, frame: Optional[np.ndarray]) -> None:
        if frame is None:
            return
        h, w, _ = frame.shape
        dim = min(h, w)
        cx, cy = w // 2, h // 2
        crop = frame[cy - dim // 2 : cy + dim // 2, cx - dim // 2 : cx + dim // 2]
        crop = cv2.resize(crop, (SIDEBAR_WIDTH - 40, SIDEBAR_WIDTH - 40))
        crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        self.cam_surface = pygame.surfarray.make_surface(np.transpose(crop_rgb, (1, 0, 2)))

    def _handle_menu(
        self,
        result: VisionResult,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: tuple[int, int],
        mouse_clicked: bool,
        now: float,
    ) -> None:
        for action, button in self.menu_buttons:
            if button.clicked(cursor_pos, result.pinch_clicked, mouse_pos, mouse_clicked):
                if action == "single":
                    self.start_single_mode(now)
                elif action == "options":
                    self.state = STATE_OPTIONS
                else:
                    self.state = STATE_COMING_SOON
                return

    def _handle_options(
        self,
        result: VisionResult,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: tuple[int, int],
        mouse_clicked: bool,
    ) -> None:
        for action, button in self.options_buttons:
            if button.clicked(cursor_pos, result.pinch_clicked, mouse_pos, mouse_clicked):
                if action == "sensitivity_down":
                    self.sensitivity_index = next_sensitivity_index(self.sensitivity_index, -1)
                elif action == "sensitivity_up":
                    self.sensitivity_index = next_sensitivity_index(self.sensitivity_index, 1)
                elif action == "menu":
                    self.state = STATE_MENU
                return

    def _handle_playing(self, result: VisionResult, dt: float, now: float) -> None:
        if should_pause_for_tracking(result, self.vision.seconds_since_seen(now)):
            self.state = STATE_PAUSED
            self.pause_reason = "tracking"
            return

        if result.detected and result.index_tip_norm is not None:
            self.target_pos = index_to_game_target(
                result.index_tip_norm, self.current_sensitivity
            )

        self._update_physics(dt, now)

    def _handle_paused(
        self,
        result: VisionResult,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: tuple[int, int],
        mouse_clicked: bool,
        now: float,
    ) -> None:
        if self.pause_reason == "tracking" and result.detected:
            self.state = STATE_PLAYING_SINGLE
            self.pause_reason = None
            return

        for action, button in self.pause_buttons:
            if button.clicked(cursor_pos, result.pinch_clicked, mouse_pos, mouse_clicked):
                if action == "resume":
                    self.state = STATE_PLAYING_SINGLE
                    self.pause_reason = None
                elif action == "restart":
                    self.start_single_mode(now)
                elif action == "menu":
                    self.state = STATE_MENU
                    self.pause_reason = None
                return

    def _handle_gameover(
        self,
        result: VisionResult,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: tuple[int, int],
        mouse_clicked: bool,
        now: float,
    ) -> None:
        if result.peace_triggered:
            self.start_single_mode(now)
            return

        for action, button in self.gameover_buttons:
            if button.clicked(cursor_pos, result.pinch_clicked, mouse_pos, mouse_clicked):
                if action == "restart":
                    self.start_single_mode(now)
                elif action == "menu":
                    self.state = STATE_MENU
                return

    def _handle_coming_soon(
        self,
        result: VisionResult,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: tuple[int, int],
        mouse_clicked: bool,
    ) -> None:
        for _, button in self.coming_soon_buttons:
            if button.clicked(cursor_pos, result.pinch_clicked, mouse_pos, mouse_clicked):
                self.state = STATE_MENU
                return

    def _update_physics(self, dt: float, now: float) -> None:
        speed = current_speed_for_apples(self.apples_eaten)
        previous_head = pygame.Vector2(self.head_pos)
        self.head_pos = move_toward(self.head_pos, self.target_pos, speed * dt)
        movement = self.head_pos - previous_head
        if movement.length_squared() > 0:
            self.direction = movement.normalize()
        self.head_pos = wrap_in_game_area(self.head_pos)
        self._update_body_trail(previous_head)

        if self.big_food and self.big_food.is_expired(now):
            self.big_food = None

        if self.normal_food.overlaps(self.head_pos, SNAKE_RADIUS):
            self.score += self.normal_food.score
            self.target_segments += self.normal_food.growth
            self.apples_eaten += 1
            self.normal_food = self._spawn_food(
                radius=14,
                score=NORMAL_FOOD_SCORE,
                growth=NORMAL_GROWTH,
                color=COLOR_FOOD,
                avoid=[self.big_food] if self.big_food else [],
            )
            if self.apples_eaten % BIG_FOOD_EVERY == 0 and self.big_food is None:
                self.big_food = self._spawn_food(
                    radius=25,
                    score=BIG_FOOD_SCORE,
                    growth=BIG_GROWTH,
                    color=COLOR_BIG_FOOD,
                    now=now,
                    duration=BIG_FOOD_DURATION,
                    avoid=[self.normal_food],
                )

        if self.big_food and self.big_food.overlaps(self.head_pos, SNAKE_RADIUS):
            self.score += self.big_food.score
            self.target_segments += self.big_food.growth
            self.big_food = None

        if now > self.invincible_until and self._hits_self():
            self.state = STATE_GAMEOVER

    def _update_body_trail(self, previous_head: pygame.Vector2) -> None:
        extend_body_trail(self.body, previous_head, self.head_pos, self.target_segments)

    def _hits_self(self) -> bool:
        if len(self.body) < 20:
            return False
        hit_radius = SNAKE_RADIUS * 1.15
        hit_radius_sq = hit_radius * hit_radius
        for part in self.body[15::2]:
            if distance_sq(self.head_pos, part) < hit_radius_sq:
                return True
        return False

    def draw(
        self,
        result: VisionResult,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: tuple[int, int],
        now: float,
    ) -> None:
        self.screen.blit(self.background, (0, 0))
        if self.state in {STATE_PLAYING_SINGLE, STATE_PAUSED, STATE_GAMEOVER}:
            self._draw_food(now)
            self._draw_snake()
        self._draw_sidebar(result, now)

        if self.state == STATE_MENU:
            self._draw_menu(cursor_pos, mouse_pos)
        elif self.state == STATE_PAUSED:
            self._draw_pause(cursor_pos, mouse_pos)
        elif self.state == STATE_GAMEOVER:
            self._draw_gameover(cursor_pos, mouse_pos)
        elif self.state == STATE_COMING_SOON:
            self._draw_coming_soon(cursor_pos, mouse_pos)
        elif self.state == STATE_OPTIONS:
            self._draw_options(cursor_pos, mouse_pos)
        elif self.state == STATE_PLAYING_SINGLE and now < self.invincible_until:
            self._draw_small_notice("开局保护中...")

        if cursor_pos:
            pygame.draw.circle(self.screen, COLOR_ACCENT, cursor_pos, 9)
            pygame.draw.circle(self.screen, COLOR_TEXT, cursor_pos, 9, 2)

        pygame.display.flip()

    def _draw_food(self, now: float) -> None:
        self._draw_apple(self.normal_food)
        if self.big_food:
            if int(now * 8) % 2 == 0 or self.big_food.remaining(now) > 2.0:
                self._draw_apple(self.big_food, big=True)
            remaining = self.font_small.render(
                f"{self.big_food.remaining(now):.1f}s", True, COLOR_WARNING
            )
            self.screen.blit(
                remaining,
                remaining.get_rect(
                    center=(int(self.big_food.position.x), int(self.big_food.position.y) - 40)
                ),
            )

    def _draw_apple(self, food: Food, big: bool = False) -> None:
        pos = (int(food.position.x), int(food.position.y))
        pygame.draw.circle(self.screen, (110, 20, 20), pos, food.radius + 3)
        pygame.draw.circle(self.screen, food.color, pos, food.radius)
        highlight = max(5, food.radius // 3)
        pygame.draw.circle(
            self.screen,
            (255, 130, 130),
            (pos[0] - food.radius // 3, pos[1] - food.radius // 3),
            highlight,
        )
        stem_rect = (pos[0] - 3, pos[1] - food.radius - 10, 7, 12)
        pygame.draw.ellipse(self.screen, COLOR_SNAKE_BODY, stem_rect)
        if big:
            pygame.draw.circle(self.screen, COLOR_WARNING, pos, food.radius + 8, 2)

    def _draw_snake(self) -> None:
        for i, pos in enumerate(reversed(self.body)):
            x, y = int(pos.x), int(pos.y)
            color = COLOR_SNAKE_BODY if i % 2 == 0 else COLOR_SNAKE_BODY_ALT
            pygame.draw.circle(self.screen, COLOR_SNAKE_OUTLINE, (x, y), SNAKE_RADIUS + 2)
            pygame.draw.circle(self.screen, color, (x, y), SNAKE_RADIUS)

        hx, hy = int(self.head_pos.x), int(self.head_pos.y)
        pygame.draw.circle(self.screen, COLOR_SNAKE_OUTLINE, (hx, hy), SNAKE_RADIUS + 4)
        pygame.draw.circle(self.screen, COLOR_SNAKE_HEAD, (hx, hy), SNAKE_RADIUS + 2)

        facing = self.direction.normalize() if self.direction.length_squared() else pygame.Vector2(1, 0)
        side = pygame.Vector2(-facing.y, facing.x)
        for offset in (-6, 6):
            eye = pygame.Vector2(hx, hy) + facing * 8 + side * offset
            pygame.draw.circle(self.screen, (0, 0, 0), (int(eye.x), int(eye.y)), 4)
            pygame.draw.circle(self.screen, COLOR_TEXT, (int(eye.x + 1), int(eye.y - 1)), 1)

    def _draw_sidebar(self, result: VisionResult, now: float) -> None:
        margin = 20
        cam_size = SIDEBAR_WIDTH - 40
        pygame.draw.rect(self.screen, (0, 0, 0), (margin, margin, cam_size, cam_size))
        if self.cam_surface:
            self.screen.blit(self.cam_surface, (margin, margin))
        else:
            msg = "摄像头未打开" if not self.vision.camera_ready else "等待画面..."
            text = self.font_med.render(msg, True, COLOR_DANGER)
            self.screen.blit(text, text.get_rect(center=(SIDEBAR_WIDTH // 2, margin + cam_size // 2)))

        border_color = COLOR_SUCCESS if result.detected else COLOR_DANGER
        pygame.draw.rect(self.screen, border_color, (margin, margin, cam_size, cam_size), 3)

        status = "已锁定第一只手" if result.detected else "等待识别手势"
        status_color = COLOR_SUCCESS if result.detected else COLOR_WARNING
        status_text = self.font_small.render(status, True, status_color)
        self.screen.blit(status_text, (margin, margin + cam_size + 12))

        y = margin + cam_size + 46
        self._draw_stat_panel(y, now)
        self._draw_help_text()

    def _draw_stat_panel(self, y: int, now: float) -> None:
        margin = 20
        pygame.draw.rect(
            self.screen,
            COLOR_PANEL,
            (margin, y, SIDEBAR_WIDTH - 40, 150),
            border_radius=8,
        )
        labels = [
            ("分数", str(self.score)),
            ("苹果", str(self.apples_eaten)),
            ("速度", f"{current_speed_for_apples(self.apples_eaten)} px/s"),
            ("灵敏度", self.current_sensitivity_label),
        ]
        for i, (label, value) in enumerate(labels):
            base_y = y + 12 + i * 32
            ltxt = self.font_small.render(label, True, COLOR_TEXT_MUTED)
            vtxt = self.font_small.render(value, True, COLOR_ACCENT)
            self.screen.blit(ltxt, (margin + 18, base_y))
            self.screen.blit(vtxt, (margin + 108, base_y))

        if self.big_food:
            remain = self.font_tiny.render(
                f"大苹果剩余 {self.big_food.remaining(now):.1f} 秒", True, COLOR_WARNING
            )
            self.screen.blit(remain, (margin + 18, y + 126))

    def _draw_help_text(self) -> None:
        lines = [
            "玩法提示",
            "食指移动：平滑追随",
            "捏合：点击按钮",
            "和平手势：结束后重开",
            "撞墙会从另一侧穿出",
            "只撞到自己才结束",
        ]
        y = WINDOW_HEIGHT - 175
        for i, line in enumerate(lines):
            font = self.font_small if i else self.font_med
            color = COLOR_TEXT if i == 0 else COLOR_TEXT_MUTED
            text = font.render(line, True, color)
            self.screen.blit(text, (20, y + i * 26))

    def _draw_menu(self, cursor_pos: Optional[tuple[int, int]], mouse_pos: tuple[int, int]) -> None:
        center_x = SIDEBAR_WIDTH + GAME_WIDTH // 2
        title = self.font_title.render("Gesture Snake", True, COLOR_TEXT)
        sub = self.font_med.render("选择模式", True, COLOR_TEXT_MUTED)
        self.screen.blit(title, title.get_rect(center=(center_x, 145)))
        self.screen.blit(sub, sub.get_rect(center=(center_x, 205)))
        for _, button in self.menu_buttons:
            button.draw(self.screen, self.font_button, self.font_small, cursor_pos, mouse_pos)

    def _draw_options(self, cursor_pos: Optional[tuple[int, int]], mouse_pos: tuple[int, int]) -> None:
        center_x = SIDEBAR_WIDTH + GAME_WIDTH // 2
        title = self.font_big.render("选项设置", True, COLOR_TEXT)
        subtitle = self.font_med.render("手势灵敏度", True, COLOR_TEXT_MUTED)
        current = self.font_title.render(self.current_sensitivity_label, True, COLOR_ACCENT)
        hint_lines = [
            "灵敏度越高，手指小范围移动就能覆盖更大的地图范围。",
            "超高灵敏度适合手不想离开摄像头中心区域的玩法。",
        ]

        self.screen.blit(title, title.get_rect(center=(center_x, 165)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(center_x, 235)))
        self.screen.blit(current, current.get_rect(center=(center_x, 330)))
        for i, line in enumerate(hint_lines):
            text = self.font_small.render(line, True, COLOR_TEXT_MUTED)
            self.screen.blit(text, text.get_rect(center=(center_x, 485 + i * 28)))
        for _, button in self.options_buttons:
            button.draw(self.screen, self.font_button, self.font_small, cursor_pos, mouse_pos)

    def _draw_pause(self, cursor_pos: Optional[tuple[int, int]], mouse_pos: tuple[int, int]) -> None:
        title = "追踪丢失"
        sub = "重新识别到手后会自动继续"
        self._draw_overlay_panel(title, sub, COLOR_WARNING)

    def _draw_gameover(self, cursor_pos: Optional[tuple[int, int]], mouse_pos: tuple[int, int]) -> None:
        self._draw_overlay_panel("游戏结束", f"分数 {self.score} / 苹果 {self.apples_eaten}", COLOR_DANGER)
        hint = self.font_small.render("做和平手势可直接重开", True, COLOR_TEXT_MUTED)
        center_x = SIDEBAR_WIDTH + GAME_WIDTH // 2
        self.screen.blit(hint, hint.get_rect(center=(center_x, 365)))
        for _, button in self.gameover_buttons:
            button.draw(self.screen, self.font_button, self.font_small, cursor_pos, mouse_pos)

    def _draw_coming_soon(self, cursor_pos: Optional[tuple[int, int]], mouse_pos: tuple[int, int]) -> None:
        self._draw_overlay_panel("开发中", "Coming Soon", COLOR_WARNING)
        for _, button in self.coming_soon_buttons:
            button.draw(self.screen, self.font_button, self.font_small, cursor_pos, mouse_pos)

    def _draw_overlay_panel(self, title: str, subtitle: str, color: tuple[int, int, int]) -> None:
        center_x = SIDEBAR_WIDTH + GAME_WIDTH // 2
        center_y = WINDOW_HEIGHT // 2
        box = pygame.Rect(0, 0, 500, 260)
        box.center = (center_x, center_y - 40)
        overlay = pygame.Surface(box.size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 215))
        self.screen.blit(overlay, box.topleft)
        pygame.draw.rect(self.screen, color, box, 2, border_radius=8)
        title_surf = self.font_big.render(title, True, color)
        sub_surf = self.font_med.render(subtitle, True, COLOR_TEXT_MUTED)
        self.screen.blit(title_surf, title_surf.get_rect(center=(center_x, box.y + 78)))
        self.screen.blit(sub_surf, sub_surf.get_rect(center=(center_x, box.y + 130)))

    def _draw_small_notice(self, text: str) -> None:
        center_x = SIDEBAR_WIDTH + GAME_WIDTH // 2
        surf = self.font_med.render(text, True, COLOR_SUCCESS)
        self.screen.blit(surf, surf.get_rect(center=(center_x, 90)))


if __name__ == "__main__":
    game = SnakeGame()
    game.run()
