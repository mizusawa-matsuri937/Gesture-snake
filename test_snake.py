import os
import unittest
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

import snake


class FontLoadingTests(unittest.TestCase):
    def test_load_font_falls_back_when_system_font_lookup_fails(self):
        pygame.init()
        try:
            with patch("pygame.font.SysFont", side_effect=TypeError("bad font registry")):
                font = snake.load_font("arial rounded mt bold", 60)

            self.assertIsInstance(font, pygame.font.Font)
            self.assertGreater(font.render("OK", True, (255, 255, 255)).get_width(), 0)
        finally:
            pygame.quit()

    def test_load_font_can_render_chinese_text_with_real_font_file(self):
        pygame.init()
        try:
            font_path = snake.find_existing_font_file(snake.CJK_FONT_FILES)
            self.assertIsNotNone(font_path)

            font = snake.load_font(snake.CJK_FONTS, 26)
            rendered = font.render("单人模式", True, (255, 255, 255))

            self.assertGreater(rendered.get_width(), 30)
            self.assertGreater(rendered.get_height(), 10)
        finally:
            pygame.quit()


class GameRuleTests(unittest.TestCase):
    def test_speed_scales_with_apples_and_caps_at_maximum(self):
        self.assertEqual(snake.current_speed_for_apples(0), snake.BASE_SPEED)
        self.assertEqual(
            snake.current_speed_for_apples(3),
            snake.BASE_SPEED + 3 * snake.SPEED_INCREASE_PER_APPLE,
        )
        self.assertEqual(snake.current_speed_for_apples(999), snake.MAX_SPEED)

    def test_wrap_position_uses_only_the_right_game_area(self):
        wrapped = snake.wrap_in_game_area(
            pygame.Vector2(snake.WINDOW_WIDTH + 12, -9)
        )

        self.assertEqual(wrapped.x, snake.SIDEBAR_WIDTH + 12)
        self.assertEqual(wrapped.y, snake.WINDOW_HEIGHT - 9)

    def test_index_tip_maps_to_right_game_area_target(self):
        top_left = snake.index_to_game_target((0.0, 0.0))
        center = snake.index_to_game_target((0.5, 0.5))
        bottom_right = snake.index_to_game_target((1.0, 1.0))

        self.assertEqual(top_left, pygame.Vector2(snake.SIDEBAR_WIDTH, 0))
        self.assertEqual(
            center,
            pygame.Vector2(snake.SIDEBAR_WIDTH + snake.GAME_WIDTH / 2, snake.WINDOW_HEIGHT / 2),
        )
        self.assertEqual(bottom_right, pygame.Vector2(snake.WINDOW_WIDTH, snake.WINDOW_HEIGHT))

    def test_sensitivity_scales_small_finger_movement_around_center(self):
        scaled = snake.apply_pointer_sensitivity((0.55, 0.45), sensitivity=4.0)
        clamped_left = snake.apply_pointer_sensitivity((0.30, 0.50), sensitivity=4.0)
        clamped_right = snake.apply_pointer_sensitivity((0.70, 0.50), sensitivity=4.0)

        self.assertEqual(scaled, (0.7, 0.3))
        self.assertEqual(clamped_left, (0.0, 0.5))
        self.assertEqual(clamped_right, (1.0, 0.5))

    def test_index_tip_target_uses_sensitivity_multiplier(self):
        target = snake.index_to_game_target((0.55, 0.5), sensitivity=4.0)

        self.assertEqual(target.x, snake.SIDEBAR_WIDTH + snake.GAME_WIDTH * 0.7)
        self.assertEqual(target.y, snake.WINDOW_HEIGHT * 0.5)

    def test_sensitivity_option_cycles_within_available_levels(self):
        self.assertEqual(snake.next_sensitivity_index(0, 1), 1)
        self.assertEqual(
            snake.next_sensitivity_index(len(snake.SENSITIVITY_OPTIONS) - 1, 1),
            len(snake.SENSITIVITY_OPTIONS) - 1,
        )
        self.assertEqual(snake.next_sensitivity_index(0, -1), 0)

    def test_move_toward_target_uses_speed_limit_and_does_not_overshoot(self):
        limited = snake.move_toward(
            pygame.Vector2(100, 100), pygame.Vector2(300, 100), max_distance=50
        )
        close = snake.move_toward(
            pygame.Vector2(100, 100), pygame.Vector2(120, 100), max_distance=50
        )

        self.assertEqual(limited, pygame.Vector2(150, 100))
        self.assertEqual(close, pygame.Vector2(120, 100))

    def test_body_trail_inserts_intermediate_points_for_large_steps(self):
        body = [pygame.Vector2(100, 100)]

        snake.extend_body_trail(
            body,
            previous_head=pygame.Vector2(100, 100),
            new_head=pygame.Vector2(180, 100),
            target_segments=20,
        )

        self.assertGreater(len(body), 2)
        max_gap = max((body[i] - body[i + 1]).length() for i in range(len(body) - 1))
        self.assertLessEqual(max_gap, snake.BODY_POINT_SPACING + 0.01)

    def test_apple_growth_is_lightweight(self):
        self.assertEqual(snake.NORMAL_GROWTH, 1)
        self.assertEqual(snake.BIG_GROWTH, 3)

    def test_peace_gesture_does_not_pause_active_gameplay(self):
        result = snake.VisionResult(detected=True, peace_triggered=True)

        self.assertFalse(snake.should_pause_for_tracking(result, seconds_since_seen=0.0))

    def test_camera_resolution_setting_is_adjustable(self):
        settings = snake.CameraSettings(index=1, resolution=(960, 540), fps=24)

        self.assertEqual(settings.width, 960)
        self.assertEqual(settings.height, 540)
        self.assertEqual(settings.fps, 24)

    def test_timed_big_food_expires_after_duration(self):
        food = snake.Food(
            position=pygame.Vector2(500, 300),
            radius=24,
            score=50,
            growth=snake.BIG_GROWTH,
            color=(255, 0, 0),
            spawn_time=10.0,
            duration=5.0,
        )

        self.assertFalse(food.is_expired(14.99))
        self.assertTrue(food.is_expired(15.01))

    def test_food_overlap_uses_squared_distance(self):
        apple = snake.Food(
            position=pygame.Vector2(500, 300),
            radius=14,
            score=10,
            growth=snake.NORMAL_GROWTH,
            color=(255, 0, 0),
        )

        self.assertTrue(apple.overlaps(pygame.Vector2(520, 300), 8))
        self.assertFalse(apple.overlaps(pygame.Vector2(540, 300), 8))


class ButtonTests(unittest.TestCase):
    def test_button_accepts_cursor_pinch_and_mouse_clicks(self):
        pygame.init()
        try:
            button = snake.Button(pygame.Rect(100, 100, 160, 60), "单人模式")

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


class GestureDebouncerTests(unittest.TestCase):
    def test_gesture_trigger_fires_only_on_rising_edge_and_cooldown(self):
        trigger = snake.GestureTrigger(cooldown=0.35)

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

        selected = snake.choose_nearest_hand(hands, previous, max_distance=0.20)

        self.assertEqual(selected[1], "active")

    def test_active_hand_is_not_replaced_when_candidates_are_too_far(self):
        previous = (0.25, 0.25)
        hands = [((0.80, 0.80), "second")]

        self.assertIsNone(snake.choose_nearest_hand(hands, previous, max_distance=0.20))


if __name__ == "__main__":
    unittest.main()
