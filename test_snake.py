import os
import random
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import numpy as np

import config
from entities import Food, Snake, Wall
from modes.level_mode import LevelMode
from modes.single_mode import SingleMode, current_speed_for_apples
from ui import Button
from utils import (
    apply_pointer_sensitivity,
    choose_nearest_hand,
    circle_rect_collision,
    distance_sq,
    extend_body_trail,
    find_existing_font_file,
    index_to_game_target,
    load_font,
    move_toward,
    next_sensitivity_index,
    wrap_in_game_area,
)
from vision import CameraSettings, GestureTrigger, VisionResult, should_pause_for_tracking


class FontLoadingTests(unittest.TestCase):
    def test_load_font_falls_back_when_system_font_lookup_fails(self):
        pygame.init()
        try:
            with patch("pygame.font.SysFont", side_effect=TypeError("bad font registry")):
                font = load_font("arial rounded mt bold", 60)

            self.assertIsInstance(font, pygame.font.Font)
            self.assertGreater(font.render("OK", True, (255, 255, 255)).get_width(), 0)
        finally:
            pygame.quit()

    def test_load_font_can_render_chinese_text_with_real_font_file(self):
        pygame.init()
        try:
            font_path = find_existing_font_file(config.CJK_FONT_FILES)
            self.assertIsNotNone(font_path)

            font = load_font(config.CJK_FONTS, 26)
            rendered = font.render("单人模式", True, (255, 255, 255))

            self.assertGreater(rendered.get_width(), 30)
            self.assertGreater(rendered.get_height(), 10)
        finally:
            pygame.quit()


class GameRuleTests(unittest.TestCase):
    def test_display_defaults_to_fullscreen_with_windowed_fallback(self):
        self.assertTrue(config.FULLSCREEN_DEFAULT)
        self.assertEqual(config.WINDOWED_SIZE, (1400, 800))
        self.assertGreaterEqual(config.MIN_LAYOUT_SCALE, 1.0)

    def test_camera_defaults_to_widescreen_capture(self):
        self.assertEqual(config.CAMERA_RESOLUTION, (1280, 720))

    def test_sensitivity_labels_are_english(self):
        labels = [label for label, _ in config.SENSITIVITY_OPTIONS]

        self.assertEqual(labels, ["Normal", "Sensitive", "High", "Ultra"])

    def test_speed_scales_with_apples_and_caps_at_maximum(self):
        self.assertEqual(current_speed_for_apples(0), config.BASE_SPEED)
        self.assertEqual(
            current_speed_for_apples(3),
            config.BASE_SPEED + 3 * config.SPEED_INCREASE_PER_APPLE,
        )
        self.assertEqual(current_speed_for_apples(999), config.MAX_SPEED)

    def test_wrap_position_uses_only_the_right_game_area(self):
        wrapped = wrap_in_game_area(pygame.Vector2(config.WINDOW_WIDTH + 12, -9))

        self.assertEqual(wrapped.x, config.SIDEBAR_WIDTH + 12)
        self.assertEqual(wrapped.y, config.WINDOW_HEIGHT - 9)

    def test_index_tip_maps_to_right_game_area_target(self):
        top_left = index_to_game_target((0.0, 0.0))
        center = index_to_game_target((0.5, 0.5))
        bottom_right = index_to_game_target((1.0, 1.0))

        self.assertEqual(top_left, pygame.Vector2(config.SIDEBAR_WIDTH, 0))
        self.assertEqual(
            center,
            pygame.Vector2(
                config.SIDEBAR_WIDTH + config.GAME_WIDTH / 2,
                config.WINDOW_HEIGHT / 2,
            ),
        )
        self.assertEqual(
            bottom_right, pygame.Vector2(config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        )

    def test_sensitivity_scales_small_finger_movement_around_center(self):
        scaled = apply_pointer_sensitivity((0.55, 0.45), sensitivity=4.0)
        clamped_left = apply_pointer_sensitivity((0.30, 0.50), sensitivity=4.0)
        clamped_right = apply_pointer_sensitivity((0.70, 0.50), sensitivity=4.0)

        self.assertEqual(scaled, (0.7, 0.3))
        self.assertEqual(clamped_left, (0.0, 0.5))
        self.assertEqual(clamped_right, (1.0, 0.5))

    def test_index_tip_target_uses_sensitivity_multiplier(self):
        target = index_to_game_target((0.55, 0.5), sensitivity=4.0)

        self.assertEqual(target.x, config.SIDEBAR_WIDTH + config.GAME_WIDTH * 0.7)
        self.assertEqual(target.y, config.WINDOW_HEIGHT * 0.5)

    def test_sensitivity_option_cycles_within_available_levels(self):
        self.assertEqual(next_sensitivity_index(0, 1), 1)
        self.assertEqual(
            next_sensitivity_index(len(config.SENSITIVITY_OPTIONS) - 1, 1),
            len(config.SENSITIVITY_OPTIONS) - 1,
        )
        self.assertEqual(next_sensitivity_index(0, -1), 0)

    def test_move_toward_target_uses_speed_limit_and_does_not_overshoot(self):
        limited = move_toward(
            pygame.Vector2(100, 100), pygame.Vector2(300, 100), max_distance=50
        )
        close = move_toward(
            pygame.Vector2(100, 100), pygame.Vector2(120, 100), max_distance=50
        )

        self.assertEqual(limited, pygame.Vector2(150, 100))
        self.assertEqual(close, pygame.Vector2(120, 100))

    def test_body_trail_inserts_intermediate_points_for_large_steps(self):
        body = [pygame.Vector2(100, 100)]

        extend_body_trail(
            body,
            previous_head=pygame.Vector2(100, 100),
            new_head=pygame.Vector2(180, 100),
            target_segments=20,
        )

        self.assertGreater(len(body), 2)
        max_gap = max((body[i] - body[i + 1]).length() for i in range(len(body) - 1))
        self.assertLessEqual(max_gap, config.BODY_POINT_SPACING + 0.01)

    def test_apple_growth_is_lightweight(self):
        self.assertEqual(config.NORMAL_GROWTH, 1)
        self.assertEqual(config.BIG_GROWTH, 3)

    def test_peace_gesture_does_not_pause_active_gameplay(self):
        result = VisionResult(detected=True, peace_triggered=True)

        self.assertFalse(should_pause_for_tracking(result, seconds_since_seen=0.0))

    def test_camera_resolution_setting_is_adjustable(self):
        settings = CameraSettings(index=1, resolution=(960, 540), fps=24)

        self.assertEqual(settings.width, 960)
        self.assertEqual(settings.height, 540)
        self.assertEqual(settings.fps, 24)

    def test_timed_big_food_expires_after_duration(self):
        food = Food(
            position=pygame.Vector2(500, 300),
            radius=24,
            score=50,
            growth=config.BIG_GROWTH,
            color=(255, 0, 0),
            spawn_time=10.0,
            duration=5.0,
        )

        self.assertFalse(food.is_expired(14.99))
        self.assertTrue(food.is_expired(15.01))

    def test_food_overlap_uses_squared_distance(self):
        apple = Food(
            position=pygame.Vector2(500, 300),
            radius=14,
            score=10,
            growth=config.NORMAL_GROWTH,
            color=(255, 0, 0),
        )

        self.assertTrue(apple.overlaps(pygame.Vector2(520, 300), 8))
        self.assertFalse(apple.overlaps(pygame.Vector2(540, 300), 8))

    def test_circle_rect_collision_uses_snake_head_radius(self):
        rect = pygame.Rect(500, 300, 60, 40)

        self.assertTrue(circle_rect_collision(490, 320, 12, rect))
        self.assertFalse(circle_rect_collision(470, 320, 12, rect))


class ButtonTests(unittest.TestCase):
    def test_button_accepts_cursor_pinch_and_mouse_clicks(self):
        pygame.init()
        try:
            button = Button(pygame.Rect(100, 100, 160, 60), "Single Player")

            self.assertTrue(button.clicked((140, 120), pinch_clicked=True))
            self.assertFalse(button.clicked((20, 20), pinch_clicked=True))
            self.assertTrue(
                button.clicked(
                    cursor_pos=None,
                    pinch_clicked=False,
                    mouse_pos=(140, 120),
                    mouse_clicked=True,
                )
            )
        finally:
            pygame.quit()


class UILayoutTests(unittest.TestCase):
    def test_camera_preview_preserves_widescreen_aspect_ratio(self):
        from ui import GameUI

        pygame.init()
        try:
            screen = pygame.Surface(config.WINDOWED_SIZE)
            ui = GameUI(screen)
            frame = np.zeros((720, 1280, 3), dtype=np.uint8)

            ui.update_camera_surface(frame)

            self.assertIsNotNone(ui.cam_surface)
            self.assertEqual(ui.cam_surface.get_size(), (310, 174))
            self.assertEqual(ui.camera_preview_rect.size, (310, 174))
        finally:
            pygame.quit()

    def test_visible_game_ui_source_is_english_only(self):
        chinese = re.compile(r"[\u4e00-\u9fff]")
        source_files = ["config.py", "game.py", "ui.py", "vision.py"]

        for path in source_files:
            with self.subTest(path=path):
                text = Path(path).read_text(encoding="utf-8")
                self.assertIsNone(chinese.search(text))

    def test_screenshot_harness_renders_every_ui_state(self):
        from tools.capture_ui_states import REQUIRED_STATES, capture_ui_states

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            captures = capture_ui_states(output_dir)

            self.assertEqual(set(captures), set(REQUIRED_STATES))
            for state, path in captures.items():
                with self.subTest(state=state):
                    self.assertTrue(path.exists())
                    image = pygame.image.load(str(path))
                    self.assertEqual(image.get_size(), config.WINDOWED_SIZE)


class GestureDebouncerTests(unittest.TestCase):
    def test_gesture_trigger_fires_only_on_rising_edge_and_cooldown(self):
        trigger = GestureTrigger(cooldown=0.35)

        self.assertFalse(trigger.update(False, 0.0))
        self.assertTrue(trigger.update(True, 0.10))
        self.assertFalse(trigger.update(True, 0.20))
        self.assertFalse(trigger.update(False, 0.25))
        self.assertFalse(trigger.update(True, 0.30))
        self.assertFalse(trigger.update(True, 0.50))
        self.assertFalse(trigger.update(False, 0.55))
        self.assertTrue(trigger.update(True, 0.90))


class ActiveHandSelectionTests(unittest.TestCase):
    def test_active_hand_stays_with_nearest_candidate_inside_threshold(self):
        previous = (0.25, 0.25)
        hands = [((0.80, 0.80), "second"), ((0.27, 0.26), "active")]

        selected = choose_nearest_hand(hands, previous, max_distance=0.20)

        self.assertEqual(selected[1], "active")

    def test_active_hand_is_not_replaced_when_candidates_are_too_far(self):
        previous = (0.25, 0.25)
        hands = [((0.80, 0.80), "second")]

        self.assertIsNone(choose_nearest_hand(hands, previous, max_distance=0.20))


class LevelModeTests(unittest.TestCase):
    def test_level_config_contains_playable_wall_progression(self):
        self.assertGreaterEqual(len(config.LEVELS), 5)
        self.assertEqual(config.LEVELS[0]["walls"], [])
        self.assertTrue(any(level["walls"] for level in config.LEVELS[1:]))

    def test_level_mode_boundary_collision_is_deadly(self):
        mode = LevelMode(rng=random.Random(1))
        mode.snake.head_pos = pygame.Vector2(config.SIDEBAR_WIDTH - 2, 120)

        self.assertTrue(mode.hits_boundary())

    def test_level_mode_wall_collision_is_deadly(self):
        wall = Wall(pygame.Rect(600, 300, 80, 30))
        mode = LevelMode(levels=[{"name": "Test", "target_score": 10, "walls": [wall.rect]}])
        mode.snake.head_pos = pygame.Vector2(610, 315)

        self.assertTrue(mode.hits_wall())

    def test_single_mode_still_wraps_at_boundaries(self):
        mode = SingleMode(rng=random.Random(2))
        mode.snake.head_pos = pygame.Vector2(config.WINDOW_WIDTH + 12, -9)
        mode.wrap_snake_head()

        self.assertEqual(mode.snake.head_pos.x, config.SIDEBAR_WIDTH + 12)
        self.assertEqual(mode.snake.head_pos.y, config.WINDOW_HEIGHT - 9)

    def test_level_food_does_not_spawn_inside_wall(self):
        wall = Wall(pygame.Rect(config.SIDEBAR_WIDTH + 80, 80, 600, 500))
        mode = LevelMode(
            levels=[{"name": "Wall Test", "target_score": 10, "walls": [wall.rect]}],
            rng=random.Random(3),
        )

        self.assertFalse(wall.rect.collidepoint(mode.food.position))

    def test_level_food_rejects_obvious_dead_end(self):
        mode = LevelMode(
            levels=[
                {
                    "name": "Dead End",
                    "target_score": 10,
                    "walls": [
                        pygame.Rect(config.SIDEBAR_WIDTH + 80, 80, 40, 120),
                        pygame.Rect(config.SIDEBAR_WIDTH + 120, 80, 120, 40),
                        pygame.Rect(config.SIDEBAR_WIDTH + 120, 160, 120, 40),
                    ],
                }
            ],
            rng=random.Random(4),
        )
        dead_end = pygame.Vector2(config.SIDEBAR_WIDTH + 140, 120)

        self.assertFalse(mode.is_safe_food_point(dead_end, require_open_routes=True))

    def test_reaching_target_score_enters_level_clear(self):
        mode = LevelMode(levels=[{"name": "Test", "target_score": 10, "walls": []}])
        mode.level_score = 10

        self.assertTrue(mode.reached_target_score())

    def test_level_clear_advances_to_next_level(self):
        mode = LevelMode(
            levels=[
                {"name": "One", "target_score": 10, "walls": []},
                {"name": "Two", "target_score": 20, "walls": []},
            ]
        )
        mode.advance_level(now=5.0)

        self.assertEqual(mode.level_index, 1)
        self.assertEqual(mode.level_score, 0)
        self.assertEqual(mode.current_level["name"], "Two")

    def test_restart_level_resets_current_level_but_keeps_level_index(self):
        mode = LevelMode(
            levels=[
                {"name": "One", "target_score": 10, "walls": []},
                {"name": "Two", "target_score": 20, "walls": []},
            ]
        )
        mode.level_index = 1
        mode.level_score = 30
        mode.total_score = 50
        mode.restart_level(now=7.0)

        self.assertEqual(mode.level_index, 1)
        self.assertEqual(mode.level_score, 0)
        self.assertEqual(mode.total_score, 50)
        self.assertEqual(mode.current_level["name"], "Two")

    def test_back_to_menu_clears_level_mode_state(self):
        mode = LevelMode()
        mode.level_index = 2
        mode.level_score = 40
        mode.total_score = 90
        mode.back_to_menu()

        self.assertEqual(mode.level_index, 0)
        self.assertEqual(mode.level_score, 0)
        self.assertEqual(mode.total_score, 0)


class SnakeEntityTests(unittest.TestCase):
    def test_snake_moves_smoothly_toward_target_and_tracks_body(self):
        snake = Snake()
        start = pygame.Vector2(snake.head_pos)
        snake.target_pos = start + pygame.Vector2(100, 0)

        snake.update(dt=0.1, speed=200)

        self.assertEqual(snake.head_pos, start + pygame.Vector2(20, 0))
        self.assertGreater(len(snake.body), 1)


if __name__ == "__main__":
    unittest.main()
