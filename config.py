from __future__ import annotations


# Window layout
WINDOWED_SIZE = (1400, 800)
FULLSCREEN_DEFAULT = True
MIN_LAYOUT_SCALE = 1.0
BASE_WINDOW_WIDTH = 1400
BASE_WINDOW_HEIGHT = 800
BASE_SIDEBAR_WIDTH = 350
WINDOW_WIDTH = WINDOWED_SIZE[0]
WINDOW_HEIGHT = WINDOWED_SIZE[1]
SIDEBAR_WIDTH = BASE_SIDEBAR_WIDTH
GAME_WIDTH = WINDOW_WIDTH - SIDEBAR_WIDTH
LAYOUT_SCALE = 1.0

# Camera settings
CAMERA_INDEX = 0
CAMERA_RESOLUTION = (1280, 720)
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
COLOR_BLUE_SNAKE_BODY = (52, 152, 219)
COLOR_BLUE_SNAKE_BODY_ALT = (41, 128, 185)
COLOR_BLUE_SNAKE_OUTLINE = (30, 86, 140)
COLOR_FOOD = (231, 76, 60)
COLOR_BIG_FOOD = (255, 45, 45)
COLOR_WALL = (108, 116, 148)
COLOR_WALL_BORDER = (180, 190, 225)
COLOR_MOVING_WALL = (128, 148, 210)
COLOR_MOVING_WALL_TRACK = (52, 60, 82)
COLOR_PORTAL_BLUE = (80, 180, 255)
COLOR_PORTAL_PURPLE = (190, 110, 255)
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
BIG_FOOD_SCORE = 30
BIG_FOOD_EVERY = 5
BIG_FOOD_DURATION = 10.0
INVINCIBLE_SECONDS = 3.0

# Single-player speed
BASE_SPEED = 180
SPEED_INCREASE_PER_APPLE = 8
MAX_SPEED = 420

# Duo mode
DUO_MATCH_SECONDS = 180.0
DUO_SENSITIVITY = 8.0
DUO_READY_HOLD_SECONDS = 0.5
DUO_DEATH_PENALTY = 100

# LAN battle
LAN_PROTOCOL_VERSION = 1
LAN_DEFAULT_PORT = 50007
LAN_TICK_RATE = 30
LAN_STATE_RATE = 20
LAN_CONNECT_TIMEOUT = 1.5

# Level mode speed and food
LEVEL_BASE_SPEED = 160
LEVEL_SPEED_INCREASE_PER_APPLE = 4
LEVEL_MAX_SPEED = 300
LEVEL_APPLE_SCORE = 10
LEVEL_APPLE_GROWTH = 1
LEVEL_FOOD_GRID_SIZE = 40
LEVEL_CLEAR_DELAY = 1.0
PORTAL_COOLDOWN = 0.6

# Gesture tuning
PINCH_THRESHOLD = 0.055
PINCH_COOLDOWN = 0.35
PEACE_COOLDOWN = 0.80
HAND_LOST_PAUSE_DELAY = 0.50
HAND_REACQUIRE_DELAY = 1.00
ACTIVE_HAND_MAX_DISTANCE = 0.28

# Pointer sensitivity scales hand movement around the camera center.
SENSITIVITY_OPTIONS = [
    ("Normal", 1.0),
    ("Sensitive", 3.0),
    ("High", 4.0),
    ("Ultra", 6.0),
]
DEFAULT_SENSITIVITY_INDEX = 2

STATE_MENU = "MENU"
STATE_PLAYING_SINGLE = "PLAYING_SINGLE"
STATE_SINGLE_LEVEL_SELECT = "SINGLE_LEVEL_SELECT"
STATE_PLAYING_SINGLE_CHALLENGE = "PLAYING_SINGLE_CHALLENGE"
STATE_PLAYING_LEVEL = "PLAYING_LEVEL"
STATE_PAUSED = "PAUSED"
STATE_GAMEOVER = "GAMEOVER"
STATE_COMING_SOON = "COMING_SOON"
STATE_OPTIONS = "OPTIONS"
STATE_LEVEL_CLEAR = "LEVEL_CLEAR"
STATE_DUO_CONTROL_SELECT = "DUO_CONTROL_SELECT"
STATE_DUO_LEVEL_SELECT = "DUO_LEVEL_SELECT"
STATE_DUO_WAITING = "DUO_WAITING"
STATE_PLAYING_DUO = "PLAYING_DUO"
STATE_DUO_GAMEOVER = "DUO_GAMEOVER"
STATE_LAN_DUO_MENU = "LAN_DUO_MENU"
STATE_LAN_DUO_HOST = "LAN_DUO_HOST"
STATE_LAN_DUO_JOIN = "LAN_DUO_JOIN"
STATE_LAN_DUO_WAITING = "LAN_DUO_WAITING"
STATE_PLAYING_LAN_DUO = "PLAYING_LAN_DUO"
STATE_LAN_DUO_GAMEOVER = "LAN_DUO_GAMEOVER"

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

# Obstacle coordinates are relative to the right-side game area.
LEVELS = [
    {"name": "Level 1", "target_score": 100, "spawn": (525, 400), "walls": []},
    {
        "name": "Level 2",
        "target_score": 150,
        "spawn": (525, 430),
        "walls": [
            (265, 330, 520, 36),
        ],
    },
    {
        "name": "Level 3",
        "target_score": 200,
        "spawn": (525, 400),
        "walls": [
            (250, 160, 550, 34),
            (250, 606, 550, 34),
        ],
        "moving_walls": [
            {"rect": (180, 340, 120, 30), "axis": "y", "distance": 120, "speed": 55},
            {"rect": (750, 340, 120, 30), "axis": "y", "distance": 120, "speed": 55, "phase": 120},
        ],
    },
    {
        "name": "Level 4",
        "target_score": 300,
        "spawn": (525, 680),
        "walls": [
            (250, 140, 36, 500),
            (764, 140, 36, 500),
            (507, 250, 36, 300),
        ],
        "portals": [
            {"a": (145, 100), "b": (905, 700), "radius": 34, "color": COLOR_PORTAL_BLUE},
            {"a": (905, 100), "b": (145, 700), "radius": 34, "color": COLOR_PORTAL_PURPLE},
        ],
    },
    {
        "name": "Level 5",
        "target_score": 500,
        "spawn": (525, 730),
        "walls": [
            (180, 150, 36, 500),
            (834, 150, 36, 500),
            (360, 150, 330, 34),
            (360, 616, 330, 34),
            (390, 340, 120, 32),
            (540, 340, 120, 32),
        ],
        "moving_walls": [
            {"rect": (250, 260, 95, 30), "axis": "y", "distance": 170, "speed": 70},
            {"rect": (705, 260, 95, 30), "axis": "y", "distance": 170, "speed": 70, "phase": 170},
        ],
        "portals": [
            {"a": (310, 85), "b": (740, 715), "radius": 32, "color": COLOR_PORTAL_BLUE},
        ],
    },
]

ENDLESS_CHALLENGES = [
    {
        "name": "Classic",
        "tags": ("No Obstacles", "Wrap"),
        "level_index": 0,
    },
    {
        "name": "Symmetry",
        "tags": ("Centered Wall", "Wrap"),
        "level_index": 1,
    },
    {
        "name": "Moving Walls",
        "tags": ("Moving Walls", "Wrap"),
        "level_index": 2,
    },
    {
        "name": "Portals",
        "tags": ("Portals", "Wrap"),
        "level_index": 3,
    },
    {
        "name": "Mixed",
        "tags": ("Walls", "Moving", "Portals"),
        "level_index": 4,
    },
]


def configure_layout(size: tuple[int, int]) -> None:
    global WINDOW_WIDTH, WINDOW_HEIGHT, SIDEBAR_WIDTH, GAME_WIDTH, LAYOUT_SCALE

    width = max(int(size[0]), WINDOWED_SIZE[0])
    height = max(int(size[1]), WINDOWED_SIZE[1])
    scale_x = width / BASE_WINDOW_WIDTH
    scale_y = height / BASE_WINDOW_HEIGHT
    LAYOUT_SCALE = max(MIN_LAYOUT_SCALE, min(scale_x, scale_y))
    WINDOW_WIDTH = width
    WINDOW_HEIGHT = height
    SIDEBAR_WIDTH = max(BASE_SIDEBAR_WIDTH, int(BASE_SIDEBAR_WIDTH * LAYOUT_SCALE))
    GAME_WIDTH = WINDOW_WIDTH - SIDEBAR_WIDTH
