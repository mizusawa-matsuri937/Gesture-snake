from __future__ import annotations


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
COLOR_WALL = (108, 116, 148)
COLOR_WALL_BORDER = (180, 190, 225)
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

# Single-player speed
BASE_SPEED = 180
SPEED_INCREASE_PER_APPLE = 8
MAX_SPEED = 420

# Level mode speed and food
LEVEL_BASE_SPEED = 160
LEVEL_SPEED_INCREASE_PER_APPLE = 4
LEVEL_MAX_SPEED = 300
LEVEL_APPLE_SCORE = 10
LEVEL_APPLE_GROWTH = 1
LEVEL_FOOD_GRID_SIZE = 40
LEVEL_CLEAR_DELAY = 1.0

# Gesture tuning
PINCH_THRESHOLD = 0.055
PINCH_COOLDOWN = 0.35
PEACE_COOLDOWN = 0.80
HAND_LOST_PAUSE_DELAY = 0.50
HAND_REACQUIRE_DELAY = 1.00
ACTIVE_HAND_MAX_DISTANCE = 0.28

# Pointer sensitivity scales hand movement around the camera center.
SENSITIVITY_OPTIONS = [
    ("标准", 1.0),
    ("灵敏", 3.0),
    ("高灵敏", 4.0),
    ("超高", 6.0),
]
DEFAULT_SENSITIVITY_INDEX = 2

STATE_MENU = "MENU"
STATE_PLAYING_SINGLE = "PLAYING_SINGLE"
STATE_PLAYING_LEVEL = "PLAYING_LEVEL"
STATE_PAUSED = "PAUSED"
STATE_GAMEOVER = "GAMEOVER"
STATE_COMING_SOON = "COMING_SOON"
STATE_OPTIONS = "OPTIONS"
STATE_LEVEL_CLEAR = "LEVEL_CLEAR"

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

# Wall tuples are relative to the right-side game area: (offset_x, y, width, height).
LEVELS = [
    {"name": "Level 1", "target_score": 50, "walls": []},
    {
        "name": "Level 2",
        "target_score": 80,
        "walls": [
            (260, 330, 520, 36),
        ],
    },
    {
        "name": "Level 3",
        "target_score": 120,
        "walls": [
            (210, 160, 430, 34),
            (420, 590, 430, 34),
        ],
    },
    {
        "name": "Level 4",
        "target_score": 160,
        "walls": [
            (260, 130, 36, 470),
            (520, 260, 36, 470),
            (780, 130, 36, 470),
        ],
    },
    {
        "name": "Level 5",
        "target_score": 220,
        "walls": [
            (190, 150, 36, 500),
            (380, 130, 400, 34),
            (380, 632, 400, 34),
            (820, 230, 36, 390),
            (520, 320, 180, 36),
            (520, 450, 180, 36),
        ],
    },
]
