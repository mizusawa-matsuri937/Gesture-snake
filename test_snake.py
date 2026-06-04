import os
import random
import re
import tempfile
import time
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame
import numpy as np

import config
from entities import Food, MovingWall, PortalPair, Snake, Wall
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


class FakeLandmarkPoint:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y


class FakeHandLandmarks:
    def __init__(self, index_x: float, index_y: float = 0.5, thumb_x: Optional[float] = None):
        self.landmark = [FakeLandmarkPoint(index_x, index_y) for _ in range(21)]
        self.landmark[4] = FakeLandmarkPoint(index_x if thumb_x is None else thumb_x, index_y)
        self.landmark[8] = FakeLandmarkPoint(index_x, index_y)
        for index in (0, 5, 9, 13, 17):
            self.landmark[index] = FakeLandmarkPoint(index_x, index_y)


def duo_result(left: Optional[tuple[float, float]] = (0.25, 0.5), right: Optional[tuple[float, float]] = (0.75, 0.5)):
    from vision import DuoPlayerVision, DuoVisionResult

    return DuoVisionResult(
        left=DuoPlayerVision(detected=left is not None, index_tip_norm=left),
        right=DuoPlayerVision(detected=right is not None, index_tip_norm=right),
    )


def wait_until(predicate, timeout: float = 2.0, interval: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class NetworkProtocolTests(unittest.TestCase):
    def test_encode_decode_round_trips_single_json_line_message(self):
        from network.protocol import decode_messages, encode_message

        payload = {"type": "hello", "player_name": "Player 2", "version": 1}

        messages, remainder = decode_messages(encode_message(payload))

        self.assertEqual(messages, [payload])
        self.assertEqual(remainder, b"")

    def test_decode_handles_multiple_messages_in_one_tcp_chunk(self):
        from network.protocol import decode_messages, encode_message

        first = {"type": "ping", "timestamp": 12.5}
        second = {"type": "pong", "timestamp": 12.5}

        messages, remainder = decode_messages(encode_message(first) + encode_message(second))

        self.assertEqual(messages, [first, second])
        self.assertEqual(remainder, b"")

    def test_decode_preserves_partial_message_for_next_recv(self):
        from network.protocol import decode_messages, encode_message

        payload = {"type": "input", "player_id": 1, "target_x": 0.4}
        encoded = encode_message(payload)

        messages, remainder = decode_messages(encoded[:8])
        later_messages, later_remainder = decode_messages(remainder + encoded[8:])

        self.assertEqual(messages, [])
        self.assertEqual(later_messages, [payload])
        self.assertEqual(later_remainder, b"")

    def test_decode_ignores_invalid_json_lines_without_crashing(self):
        from network.protocol import decode_messages, encode_message

        payload = {"type": "state", "tick": 1}

        messages, remainder = decode_messages(b"{bad json}\n[]\n" + encode_message(payload))

        self.assertEqual(messages, [payload])
        self.assertEqual(remainder, b"")


class NetworkServerClientTests(unittest.TestCase):
    def test_server_initial_status_is_waiting_and_not_running(self):
        from network.server import GameServer

        server = GameServer(host="127.0.0.1", port=0)

        status = server.get_status()

        self.assertFalse(status["running"])
        self.assertEqual(status["phase"], "waiting")
        self.assertEqual(status["player_count"], 0)
        self.assertEqual(status["port"], 0)

    def test_server_assigns_two_player_ids_and_rejects_third_client(self):
        from network.client import GameClient
        from network.server import GameServer

        server = GameServer(host="127.0.0.1", port=0, tick_rate=20, state_rate=10)
        clients: list[GameClient] = []
        try:
            server.start()
            self.assertGreater(server.port, 0)

            first = GameClient("127.0.0.1", server.port, "Player 1", timeout=1.0)
            second = GameClient("127.0.0.1", server.port, "Player 2", timeout=1.0)
            clients.extend([first, second])

            self.assertTrue(first.connect())
            self.assertTrue(second.connect())
            self.assertTrue(wait_until(lambda: server.get_status()["player_count"] == 2))
            self.assertEqual(first.player_id, 1)
            self.assertEqual(second.player_id, 2)

            third = GameClient("127.0.0.1", server.port, "Player 3", timeout=1.0)
            clients.append(third)

            self.assertFalse(third.connect())
            self.assertIn("Room is full", third.error_message)
        finally:
            for client in clients:
                client.disconnect()
            server.stop()

    def test_server_keeps_only_latest_input_sequence_per_player(self):
        from network.server import GameServer

        server = GameServer(host="127.0.0.1", port=0)

        server.record_input(
            {
                "type": "input",
                "player_id": 1,
                "detected": True,
                "target_x": 0.2,
                "target_y": 0.3,
                "timestamp": 1.0,
                "seq": 5,
            }
        )
        server.record_input(
            {
                "type": "input",
                "player_id": 1,
                "detected": True,
                "target_x": 0.9,
                "target_y": 0.8,
                "timestamp": 2.0,
                "seq": 4,
            }
        )

        latest = server.get_latest_inputs()[1]

        self.assertEqual(latest.seq, 5)
        self.assertEqual(latest.target_x, 0.2)
        self.assertEqual(latest.target_y, 0.3)

    def test_state_snapshot_contains_snakes_food_scores_and_winner(self):
        from network.server import GameServer

        server = GameServer(host="127.0.0.1", port=0)

        state = server.build_state()

        self.assertEqual(state["type"], "state")
        self.assertIn("1", state["snakes"])
        self.assertIn("2", state["snakes"])
        self.assertIn("score", state["snakes"]["1"])
        self.assertIn("body", state["snakes"]["1"])
        self.assertIn("foods", state)
        self.assertIn("winner", state)
        self.assertEqual(
            state["summary"],
            {
                "time": "0:00",
                "apples": 0,
                "big_apples": 0,
                "max_speed": 0,
                "tracking": "0%",
            },
        )

    def test_lan_render_state_keeps_summary_from_latest_state(self):
        from modes.lan_duo_mode import LanRenderState

        render_state = LanRenderState()
        summary = {
            "time": "1:24",
            "apples": 8,
            "big_apples": 1,
            "max_speed": 244,
            "tracking": "92%",
        }

        render_state.update_from_state({"summary": summary}, now=10.0)

        self.assertEqual(render_state.summary, summary)


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
    def test_performance_tracker_formats_time_stability_and_max_speed(self):
        from summary import PerformanceTracker

        tracker = PerformanceTracker()

        self.assertEqual(tracker.elapsed_label(), "0:00")
        self.assertEqual(tracker.stability_label(), "0%")

        tracker.record_frame(dt=1.0, tracking_ok=True, speed=180)
        tracker.record_frame(dt=2.4, tracking_ok=False, speed=220)
        tracker.record_big_apple()

        self.assertEqual(tracker.elapsed_label(), "0:03")
        self.assertEqual(tracker.stability_label(), "29%")
        self.assertEqual(tracker.max_speed, 220)
        self.assertEqual(tracker.big_apples_eaten, 1)

        tracker.reset()

        self.assertEqual(tracker.elapsed_label(), "0:00")
        self.assertEqual(tracker.stability_label(), "0%")
        self.assertEqual(tracker.big_apples_eaten, 0)
        self.assertEqual(tracker.max_speed, 0)

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

    def test_wrap_position_can_use_snake_radius_as_boundary_margin(self):
        radius = config.SNAKE_RADIUS

        wrapped_right = wrap_in_game_area(
            pygame.Vector2(config.WINDOW_WIDTH - radius + 7, 400),
            margin=radius,
        )
        wrapped_left = wrap_in_game_area(
            pygame.Vector2(config.SIDEBAR_WIDTH + radius - 9, 400),
            margin=radius,
        )
        wrapped_top = wrap_in_game_area(
            pygame.Vector2(config.SIDEBAR_WIDTH + 200, radius - 6),
            margin=radius,
        )

        self.assertEqual(wrapped_right.x, config.SIDEBAR_WIDTH + radius + 7)
        self.assertEqual(wrapped_left.x, config.WINDOW_WIDTH - radius - 9)
        self.assertEqual(wrapped_top.y, config.WINDOW_HEIGHT - radius - 6)

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


class GameFlowTests(unittest.TestCase):
    def test_single_player_opens_endless_challenge_select(self):
        from game import Game

        game = Game(fullscreen=False, use_camera=False)
        try:
            _, single_button = game.menu_buttons[0]

            game._handle_menu(VisionResult(), None, single_button.rect.center, True, now=1.0)

            self.assertEqual(game.state, config.STATE_SINGLE_LEVEL_SELECT)
            self.assertEqual(len(game.single_level_buttons), 5)
        finally:
            game.vision.release()
            pygame.quit()

    def test_level_select_back_returns_to_main_menu(self):
        from game import Game

        game = Game(fullscreen=False, use_camera=False)
        try:
            game.state = config.STATE_SINGLE_LEVEL_SELECT
            _, back_button = game.single_level_select_buttons[0]

            game._handle_single_level_select(
                VisionResult(),
                None,
                back_button.rect.center,
                True,
                now=1.0,
            )

            self.assertEqual(game.state, config.STATE_MENU)
        finally:
            game.vision.release()
            pygame.quit()

    def test_selecting_each_endless_challenge_starts_expected_level(self):
        from game import Game

        game = Game(fullscreen=False, use_camera=False)
        try:
            for index, (_, button) in enumerate(game.single_level_buttons):
                with self.subTest(index=index):
                    game.state = config.STATE_SINGLE_LEVEL_SELECT
                    game._handle_single_level_select(
                        VisionResult(),
                        None,
                        button.rect.center,
                        True,
                        now=2.0,
                    )

                    self.assertEqual(game.state, config.STATE_PLAYING_SINGLE_CHALLENGE)
                    self.assertEqual(game.active_mode_name, "single_challenge")
                    self.assertEqual(game.single_challenge_mode.level_index, index)
        finally:
            game.vision.release()
            pygame.quit()

    def test_gameover_buttons_for_endless_challenge_restart_select_and_menu(self):
        from game import Game

        game = Game(fullscreen=False, use_camera=False)
        try:
            game.start_single_challenge(2, now=1.0)
            game.state = config.STATE_GAMEOVER
            game.active_mode_name = "single_challenge"

            actions = [action for action, _ in game.gameover_buttons_for_active_mode()]

            self.assertEqual(actions, ["restart", "level_select", "menu"])
        finally:
            game.vision.release()
            pygame.quit()

    def test_duo_mode_opens_control_select(self):
        from game import Game

        game = Game(fullscreen=False, use_camera=False)
        try:
            _, duo_button = game.menu_buttons[3]

            game._handle_menu(VisionResult(), None, duo_button.rect.center, True, now=1.0)

            self.assertEqual(game.state, config.STATE_DUO_CONTROL_SELECT)
            self.assertEqual([action for action, _ in game.duo_control_buttons], ["shared", "lan"])
        finally:
            game.vision.release()
            pygame.quit()

    def test_shared_camera_duo_flow_selects_map_and_starts_waiting(self):
        from game import Game

        game = Game(fullscreen=False, use_camera=False)
        try:
            game.state = config.STATE_DUO_CONTROL_SELECT
            shared_button = dict(game.duo_control_buttons)["shared"]

            game._handle_duo_control_select(
                VisionResult(),
                None,
                shared_button.rect.center,
                True,
            )

            self.assertEqual(game.state, config.STATE_DUO_LEVEL_SELECT)
            self.assertEqual(len(game.duo_level_buttons), 5)

            _, map_button = game.duo_level_buttons[2]
            game._handle_duo_level_select(
                VisionResult(),
                None,
                map_button.rect.center,
                True,
                now=2.0,
            )

            self.assertEqual(game.state, config.STATE_DUO_WAITING)
            self.assertEqual(game.active_mode_name, "duo")
            self.assertEqual(game.duo_mode.level_index, 2)
        finally:
            game.vision.release()
            pygame.quit()

    def test_lan_battle_duo_entry_opens_lan_menu(self):
        from game import Game

        game = Game(fullscreen=False, use_camera=False)
        try:
            game.state = config.STATE_DUO_CONTROL_SELECT
            lan_button = dict(game.duo_control_buttons)["lan"]

            game._handle_duo_control_select(
                VisionResult(),
                None,
                lan_button.rect.center,
                True,
            )

            self.assertEqual(game.state, config.STATE_LAN_DUO_MENU)
            self.assertEqual(game.active_mode_name, "lan_duo")
        finally:
            game.lan_duo_mode.cleanup()
            game.vision.release()
            pygame.quit()

    def test_lan_join_page_accepts_ip_keyboard_input(self):
        from game import Game

        game = Game(fullscreen=False, use_camera=False)
        try:
            game.state = config.STATE_LAN_DUO_MENU
            join_button = dict(game.lan_menu_buttons)["join"]

            game._handle_lan_duo_menu(
                VisionResult(),
                None,
                join_button.rect.center,
                True,
                now=1.0,
            )
            game._handle_lan_text_input_event(pygame.event.Event(pygame.TEXTINPUT, text="192.168.1.10"))
            game._handle_lan_key_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE, unicode=""))

            self.assertEqual(game.state, config.STATE_LAN_DUO_JOIN)
            self.assertEqual(game.lan_duo_mode.join_ip, "192.168.1.1")
        finally:
            game.lan_duo_mode.cleanup()
            game.vision.release()
            pygame.quit()

    def test_lan_join_page_accepts_text_input_events(self):
        from game import Game

        game = Game(fullscreen=False, use_camera=False)
        try:
            game.state = config.STATE_LAN_DUO_JOIN

            game._handle_lan_text_input_event(pygame.event.Event(pygame.TEXTINPUT, text="127.0.0.1"))

            self.assertEqual(game.lan_duo_mode.join_ip, "127.0.0.1")
        finally:
            game.lan_duo_mode.cleanup()
            game.vision.release()
            pygame.quit()

    def test_lan_back_from_host_cleans_up_server_and_client(self):
        from game import Game

        game = Game(fullscreen=False, use_camera=False)
        try:
            game.state = config.STATE_LAN_DUO_MENU
            host_button = dict(game.lan_menu_buttons)["host"]

            game._handle_lan_duo_menu(
                VisionResult(),
                None,
                host_button.rect.center,
                True,
                now=1.0,
            )
            self.assertEqual(game.state, config.STATE_LAN_DUO_HOST)
            self.assertIsNotNone(game.lan_duo_mode.server)

            back_button = dict(game.lan_host_buttons)["back"]
            game._handle_lan_duo_host(
                VisionResult(),
                None,
                back_button.rect.center,
                True,
                now=1.2,
            )

            self.assertEqual(game.state, config.STATE_LAN_DUO_MENU)
            self.assertIsNone(game.lan_duo_mode.server)
            self.assertIsNone(game.lan_duo_mode.client)
        finally:
            game.lan_duo_mode.cleanup()
            game.vision.release()
            pygame.quit()

    def test_lan_gameover_back_returns_to_lan_menu(self):
        from game import Game

        game = Game(fullscreen=False, use_camera=False)
        try:
            game.state = config.STATE_LAN_DUO_GAMEOVER
            game.active_mode_name = "lan_duo"
            back_button = dict(game.gameover_lan_buttons)["lan_menu"]

            game._handle_lan_duo_gameover(
                VisionResult(),
                None,
                back_button.rect.center,
                True,
            )

            self.assertEqual(game.state, config.STATE_LAN_DUO_MENU)
            self.assertEqual(game.active_mode_name, "lan_duo")
        finally:
            game.lan_duo_mode.cleanup()
            game.vision.release()
            pygame.quit()

    def test_gameover_buttons_for_duo_restart_select_and_menu(self):
        from game import Game

        game = Game(fullscreen=False, use_camera=False)
        try:
            game.start_duo_mode(1, now=1.0)
            game.state = config.STATE_DUO_GAMEOVER
            game.active_mode_name = "duo"

            actions = [action for action, _ in game.gameover_buttons_for_active_mode()]

            self.assertEqual(actions, ["restart", "level_select", "menu"])
        finally:
            game.vision.release()
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

    def test_gameover_summary_items_include_core_dashboard_metrics(self):
        from ui import GameUI

        pygame.init()
        try:
            screen = pygame.Surface(config.WINDOWED_SIZE)
            ui = GameUI(screen)
            mode = SingleMode(rng=random.Random(30))
            mode.score = 120
            mode.apples_eaten = 9
            mode.summary.record_frame(dt=84.0, tracking_ok=True, speed=252)
            mode.summary.record_big_apple()

            items = ui.summary_items_for("single", mode)

            self.assertEqual(
                items,
                [
                    ("Score", "120"),
                    ("Apples", "9"),
                    ("Big Apples", "1"),
                    ("Time", "1:24"),
                    ("Max Speed", "252 px/s"),
                    ("Tracking", "100%"),
                ],
            )
        finally:
            pygame.quit()

    def test_screenshot_harness_renders_every_ui_state(self):
        from tools.capture_ui_states import REQUIRED_STATES, capture_ui_states

        self.assertIn("single_level_select", REQUIRED_STATES)
        self.assertIn("single_challenge_level_1", REQUIRED_STATES)
        self.assertIn("single_challenge_level_3", REQUIRED_STATES)
        self.assertIn("single_challenge_level_4", REQUIRED_STATES)
        self.assertIn("single_challenge_level_5", REQUIRED_STATES)
        self.assertIn("paused_single_challenge", REQUIRED_STATES)
        self.assertIn("gameover_single_challenge", REQUIRED_STATES)
        self.assertIn("level_big_apple", REQUIRED_STATES)
        self.assertIn("level_3_moving_walls", REQUIRED_STATES)
        self.assertIn("level_4_portals", REQUIRED_STATES)
        self.assertIn("level_5_mixed", REQUIRED_STATES)
        self.assertIn("duo_control_select", REQUIRED_STATES)
        self.assertIn("duo_level_select", REQUIRED_STATES)
        self.assertIn("duo_waiting", REQUIRED_STATES)
        self.assertIn("duo_playing", REQUIRED_STATES)
        self.assertIn("duo_paused", REQUIRED_STATES)
        self.assertIn("duo_gameover", REQUIRED_STATES)
        self.assertIn("lan_duo_menu", REQUIRED_STATES)
        self.assertIn("lan_duo_host", REQUIRED_STATES)
        self.assertIn("lan_duo_join", REQUIRED_STATES)
        self.assertIn("lan_duo_waiting", REQUIRED_STATES)
        self.assertIn("lan_duo_playing", REQUIRED_STATES)
        self.assertIn("lan_duo_gameover", REQUIRED_STATES)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            captures = capture_ui_states(output_dir)

            self.assertEqual(set(captures), set(REQUIRED_STATES))
            for state, path in captures.items():
                with self.subTest(state=state):
                    self.assertTrue(path.exists())
                    image = pygame.image.load(str(path))
                    self.assertEqual(image.get_size(), config.WINDOWED_SIZE)

    def test_level_target_progress_bar_fills_by_score_ratio(self):
        from ui import GameUI

        pygame.init()
        try:
            screen = pygame.Surface(config.WINDOWED_SIZE)
            ui = GameUI(screen)
            mode = type(
                "ModeStub",
                (),
                {"level_score": 50, "target_score": 100, "progress_ratio": 0.5},
            )()
            rect = pygame.Rect(40, 40, 200, 20)

            ui.draw_target_progress_bar(mode, rect)

            self.assertEqual(
                screen.get_at((rect.left + 45, rect.centery))[:3],
                config.COLOR_SUCCESS,
            )
            self.assertNotEqual(
                screen.get_at((rect.left + 155, rect.centery))[:3],
                config.COLOR_SUCCESS,
            )
        finally:
            pygame.quit()

    def test_endless_challenge_sidebar_does_not_draw_target_progress(self):
        from ui import GameUI
        from modes.endless_challenge_mode import EndlessChallengeMode

        pygame.init()
        try:
            screen = pygame.Surface(config.WINDOWED_SIZE)
            ui = GameUI(screen)
            mode = EndlessChallengeMode(level_index=3, rng=random.Random(10))

            ui.draw_sidebar(
                VisionResult(),
                mode,
                "single_challenge",
                now=5.0,
                sensitivity_label="High x4",
                camera_ready=False,
            )

            self.assertFalse(hasattr(mode, "target_score"))
            self.assertFalse(hasattr(mode, "progress_ratio"))
        finally:
            pygame.quit()

    def test_duo_sidebar_draws_scores_without_target_progress(self):
        from ui import GameUI
        from modes.duo_mode import DuoMode

        pygame.init()
        try:
            screen = pygame.Surface(config.WINDOWED_SIZE)
            ui = GameUI(screen)
            mode = DuoMode(level_index=1, rng=random.Random(19))
            mode.green.score = 30
            mode.blue.score = -100

            ui.draw_sidebar(
                duo_result(),
                mode,
                "duo",
                now=5.0,
                sensitivity_label="Duo x8",
                camera_ready=False,
            )

            self.assertFalse(hasattr(mode, "target_score"))
            self.assertFalse(hasattr(mode, "progress_ratio"))
        finally:
            pygame.quit()


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


class DuoVisionTests(unittest.TestCase):
    def test_duo_hands_are_assigned_by_index_tip_half(self):
        from vision import classify_duo_hands

        result = classify_duo_hands(
            [
                FakeHandLandmarks(0.24, 0.45),
                FakeHandLandmarks(0.76, 0.55),
            ]
        )

        self.assertTrue(result.ready)
        self.assertEqual(result.left.index_tip_norm, (0.48, 0.45))
        self.assertEqual(result.right.index_tip_norm, (0.52, 0.55))
        self.assertEqual(result.pause_reason, "")

    def test_duo_hands_report_missing_side_when_both_are_in_one_half(self):
        from vision import classify_duo_hands

        result = classify_duo_hands(
            [
                FakeHandLandmarks(0.20, 0.40),
                FakeHandLandmarks(0.35, 0.60),
            ]
        )

        self.assertFalse(result.ready)
        self.assertTrue(result.left.detected)
        self.assertFalse(result.right.detected)
        self.assertEqual(result.pause_reason, "Right hand lost")

    def test_duo_hand_on_center_line_is_reported_as_crossed(self):
        from vision import classify_duo_hands

        result = classify_duo_hands(
            [
                FakeHandLandmarks(0.50, 0.45),
                FakeHandLandmarks(0.76, 0.55),
            ]
        )

        self.assertFalse(result.ready)
        self.assertTrue(result.crossed_line)
        self.assertEqual(result.pause_reason, "Finger crossed center line")


class LevelModeTests(unittest.TestCase):
    def test_level_targets_keep_current_balance(self):
        self.assertEqual(config.LEVELS[0]["target_score"], 100)
        self.assertEqual(config.LEVELS[1]["target_score"], 150)
        self.assertEqual(config.BIG_FOOD_SCORE, 30)

    def test_level_config_contains_playable_wall_progression(self):
        self.assertGreaterEqual(len(config.LEVELS), 5)
        self.assertEqual(config.LEVELS[0]["walls"], [])
        self.assertTrue(any(level["walls"] for level in config.LEVELS[1:]))

    def test_level_config_contains_dynamic_and_portal_progression(self):
        self.assertGreaterEqual(len(config.LEVELS[2].get("moving_walls", [])), 2)
        self.assertGreaterEqual(len(config.LEVELS[3].get("portals", [])), 2)
        self.assertGreaterEqual(len(config.LEVELS[4].get("moving_walls", [])), 2)
        self.assertGreaterEqual(len(config.LEVELS[4].get("portals", [])), 1)

    def test_level_two_and_later_static_walls_are_left_right_symmetric(self):
        for level in config.LEVELS[1:]:
            with self.subTest(level=level["name"]):
                self.assertTrue(LevelMode(levels=[level]).static_walls_are_symmetric())

    def test_level_obstacle_layouts_do_not_overlap(self):
        for level in config.LEVELS:
            with self.subTest(level=level["name"]):
                self.assertEqual(LevelMode(levels=[level]).layout_issues(), [])

    def test_moving_wall_ping_pongs_along_track(self):
        wall = MovingWall(
            pygame.Rect(config.SIDEBAR_WIDTH + 100, 120, 80, 30),
            axis="x",
            distance=120,
            speed=60,
        )

        wall.update(0.0)
        self.assertEqual(wall.rect.x, config.SIDEBAR_WIDTH + 100)
        wall.update(2.0)
        self.assertEqual(wall.rect.x, config.SIDEBAR_WIDTH + 220)
        wall.update(4.0)
        self.assertEqual(wall.rect.x, config.SIDEBAR_WIDTH + 100)

    def test_portal_pair_teleports_with_relative_position(self):
        portal = PortalPair(
            pygame.Vector2(config.SIDEBAR_WIDTH + 200, 200),
            pygame.Vector2(config.SIDEBAR_WIDTH + 700, 500),
            radius=34,
            color=(90, 170, 255),
        )
        exit_pos = portal.exit_position_for(pygame.Vector2(config.SIDEBAR_WIDTH + 210, 188))

        self.assertEqual(exit_pos, pygame.Vector2(config.SIDEBAR_WIDTH + 710, 488))

    def test_snake_head_teleport_does_not_insert_cross_map_trail(self):
        snake = Snake(pygame.Vector2(config.SIDEBAR_WIDTH + 200, 200))
        old_body = list(snake.body)
        target = pygame.Vector2(config.SIDEBAR_WIDTH + 700, 500)

        snake.teleport_head(target, pygame.Vector2(1, 0))

        self.assertEqual(snake.head_pos, target)
        self.assertEqual(snake.body[0], target)
        self.assertEqual(snake.body[1:], old_body[:-1])

    def test_level_mode_boundary_collision_is_deadly(self):
        mode = LevelMode(rng=random.Random(1))
        mode.snake.head_pos = pygame.Vector2(config.SIDEBAR_WIDTH - 2, 120)

        self.assertTrue(mode.hits_boundary())

    def test_level_mode_wall_collision_is_deadly(self):
        wall = Wall(pygame.Rect(600, 300, 80, 30))
        mode = LevelMode(levels=[{"name": "Test", "target_score": 10, "walls": [wall.rect]}])
        mode.snake.head_pos = pygame.Vector2(610, 315)

        self.assertTrue(mode.hits_wall())

    def test_level_mode_moving_wall_collision_is_deadly(self):
        mode = LevelMode(
            levels=[
                {
                    "name": "Moving Test",
                    "target_score": 10,
                    "walls": [],
                    "moving_walls": [
                        {
                            "rect": (160, 260, 100, 32),
                            "axis": "x",
                            "distance": 100,
                            "speed": 50,
                        }
                    ],
                }
            ]
        )
        wall = mode.moving_walls[0]
        mode.snake.head_pos = pygame.Vector2(wall.rect.center)

        self.assertTrue(mode.hits_wall())

    def test_single_mode_still_wraps_at_boundaries(self):
        mode = SingleMode(rng=random.Random(2))
        radius = config.SNAKE_RADIUS
        mode.snake.head_pos = pygame.Vector2(config.WINDOW_WIDTH - radius + 12, radius - 9)
        mode.wrap_snake_head()

        self.assertEqual(mode.snake.head_pos.x, config.SIDEBAR_WIDTH + radius + 12)
        self.assertEqual(mode.snake.head_pos.y, config.WINDOW_HEIGHT - radius - 9)

    def test_single_mode_summary_tracks_control_time_and_big_apples(self):
        mode = SingleMode(rng=random.Random(27))

        mode.update(VisionResult(detected=True, index_tip_norm=(0.5, 0.5)), dt=1.0, now=5.0, sensitivity=1.0)

        self.assertEqual(mode.summary.elapsed_label(), "0:01")
        self.assertEqual(mode.summary.stability_label(), "100%")
        self.assertEqual(mode.summary.max_speed, config.BASE_SPEED)

        mode.spawn_big_food(now=6.0)
        mode.big_food.position = pygame.Vector2(mode.snake.head_pos)
        mode.update(VisionResult(detected=False), dt=0.0, now=6.1, sensitivity=1.0)

        self.assertEqual(mode.summary.big_apples_eaten, 1)

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

    def test_level_big_food_spawns_after_fifth_normal_apple(self):
        mode = LevelMode(levels=[{"name": "Big Test", "target_score": 500, "walls": []}])
        mode.food.position = pygame.Vector2(mode.snake.head_pos)
        mode.apples_eaten = config.BIG_FOOD_EVERY - 1

        mode.update(VisionResult(), dt=0.0, now=10.0, sensitivity=1.0)

        self.assertIsNotNone(mode.big_food)
        self.assertEqual(mode.big_food.score, config.BIG_FOOD_SCORE)

    def test_level_big_food_expires_after_duration(self):
        mode = LevelMode(levels=[{"name": "Big Test", "target_score": 500, "walls": []}])
        mode.spawn_big_food(now=10.0)

        mode.update(VisionResult(), dt=0.0, now=10.0 + config.BIG_FOOD_DURATION + 0.1, sensitivity=1.0)

        self.assertIsNone(mode.big_food)

    def test_level_big_food_adds_score_growth_and_can_clear_level(self):
        mode = LevelMode(levels=[{"name": "Big Test", "target_score": 30, "walls": []}])
        starting_segments = mode.snake.target_segments
        mode.spawn_big_food(now=10.0)
        mode.big_food.position = pygame.Vector2(mode.snake.head_pos)

        event = mode.update(VisionResult(), dt=0.0, now=10.5, sensitivity=1.0)

        self.assertEqual(event, "level_clear")
        self.assertEqual(mode.level_score, config.BIG_FOOD_SCORE)
        self.assertEqual(mode.total_score, config.BIG_FOOD_SCORE)
        self.assertEqual(mode.snake.target_segments, starting_segments + config.BIG_GROWTH)
        self.assertEqual(mode.summary.big_apples_eaten, 1)

    def test_level_portal_transports_head_and_uses_cooldown(self):
        mode = LevelMode(
            levels=[
                {
                    "name": "Portal Test",
                    "target_score": 100,
                    "walls": [],
                    "portals": [
                        {
                            "a": (220, 220),
                            "b": (760, 480),
                            "radius": 34,
                            "color": (80, 170, 255),
                        }
                    ],
                }
            ]
        )
        mode.snake.head_pos = pygame.Vector2(mode.portals[0].a_center.x + 8, mode.portals[0].a_center.y - 6)
        mode.snake.target_pos = pygame.Vector2(mode.snake.head_pos)

        mode.apply_portals(now=10.0)
        first_exit = pygame.Vector2(mode.snake.head_pos)
        mode.apply_portals(now=10.1)

        self.assertEqual(first_exit, pygame.Vector2(mode.portals[0].b_center.x + 8, mode.portals[0].b_center.y - 6))
        self.assertEqual(mode.snake.head_pos, first_exit)

    def test_level_progress_ratio_reflects_stage_score_and_caps(self):
        mode = LevelMode(levels=[{"name": "Test", "target_score": 100, "walls": []}])
        mode.level_score = 50

        self.assertEqual(mode.progress_ratio, 0.5)

        mode.level_score = 150
        self.assertEqual(mode.progress_ratio, 1.0)

        mode.level_score = -10
        self.assertEqual(mode.progress_ratio, 0.0)

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
        mode.spawn_big_food(now=2.0)
        mode.back_to_menu()

        self.assertEqual(mode.level_index, 0)
        self.assertEqual(mode.level_score, 0)
        self.assertEqual(mode.total_score, 0)
        self.assertIsNone(mode.big_food)


class EndlessChallengeModeTests(unittest.TestCase):
    def test_challenge_config_exposes_five_named_cards(self):
        self.assertEqual(
            [challenge["name"] for challenge in config.ENDLESS_CHALLENGES],
            ["Classic", "Symmetry", "Moving Walls", "Portals", "Mixed"],
        )
        self.assertEqual(config.ENDLESS_CHALLENGES[0]["tags"], ("No Obstacles", "Wrap"))
        self.assertEqual(len(config.ENDLESS_CHALLENGES), 5)

    def test_endless_challenge_reuses_level_obstacles(self):
        from modes.endless_challenge_mode import EndlessChallengeMode

        level_one = EndlessChallengeMode(level_index=0, rng=random.Random(11))
        level_three = EndlessChallengeMode(level_index=2, rng=random.Random(12))
        level_four = EndlessChallengeMode(level_index=3, rng=random.Random(13))
        level_five = EndlessChallengeMode(level_index=4, rng=random.Random(14))

        self.assertEqual(level_one.walls, [])
        self.assertGreaterEqual(len(level_three.moving_walls), 2)
        self.assertGreaterEqual(len(level_four.portals), 2)
        self.assertGreaterEqual(len(level_five.moving_walls), 2)
        self.assertGreaterEqual(len(level_five.portals), 1)

    def test_endless_challenge_wraps_boundaries_but_walls_are_deadly(self):
        from modes.endless_challenge_mode import EndlessChallengeMode

        mode = EndlessChallengeMode(level_index=1, rng=random.Random(15))
        radius = config.SNAKE_RADIUS
        mode.snake.head_pos = pygame.Vector2(config.WINDOW_WIDTH - radius + 12, radius - 9)
        mode.wrap_snake_head()

        self.assertEqual(mode.snake.head_pos.x, config.SIDEBAR_WIDTH + radius + 12)
        self.assertEqual(mode.snake.head_pos.y, config.WINDOW_HEIGHT - radius - 9)

        wall = mode.walls[0]
        mode.snake.head_pos = pygame.Vector2(wall.rect.center)

        self.assertTrue(mode.hits_wall())

    def test_endless_challenge_big_food_uses_current_duration(self):
        from modes.endless_challenge_mode import EndlessChallengeMode

        mode = EndlessChallengeMode(level_index=0, rng=random.Random(16))
        mode.normal_food.position = pygame.Vector2(mode.snake.head_pos)
        mode.apples_eaten = config.BIG_FOOD_EVERY - 1

        mode.update(VisionResult(), dt=0.0, now=10.0, sensitivity=1.0)

        self.assertIsNotNone(mode.big_food)
        self.assertEqual(mode.big_food.duration, config.BIG_FOOD_DURATION)
        self.assertEqual(mode.summary.big_apples_eaten, 0)

    def test_endless_challenge_summary_tracks_big_apple_eaten(self):
        from modes.endless_challenge_mode import EndlessChallengeMode

        mode = EndlessChallengeMode(level_index=0, rng=random.Random(28))
        mode.spawn_big_food(now=5.0)
        mode.big_food.position = pygame.Vector2(mode.snake.head_pos)

        mode.update(VisionResult(detected=True, index_tip_norm=(0.5, 0.5)), dt=0.5, now=5.2, sensitivity=1.0)

        self.assertEqual(mode.summary.big_apples_eaten, 1)
        self.assertEqual(mode.summary.elapsed_label(), "0:00")
        self.assertEqual(mode.summary.stability_label(), "100%")

    def test_endless_challenge_food_avoids_obstacles_and_portals(self):
        from modes.endless_challenge_mode import EndlessChallengeMode

        mode = EndlessChallengeMode(level_index=4, rng=random.Random(17))
        blocking_rects = mode.food_blocking_rects()

        self.assertTrue(
            mode.is_safe_food_point(
                mode.normal_food.position,
                require_open_routes=True,
                wall_rects=blocking_rects,
                radius=mode.normal_food.radius,
            )
        )

        if mode.big_food is None:
            mode.spawn_big_food(now=5.0)

        self.assertTrue(
            mode.is_safe_food_point(
                mode.big_food.position,
                require_open_routes=True,
                wall_rects=blocking_rects,
                radius=mode.big_food.radius,
                avoid=[mode.normal_food],
            )
        )

    def test_endless_challenge_portal_transports_head_with_cooldown(self):
        from modes.endless_challenge_mode import EndlessChallengeMode

        mode = EndlessChallengeMode(level_index=3, rng=random.Random(18))
        portal = mode.portals[0]
        mode.snake.head_pos = pygame.Vector2(portal.a_center.x + 6, portal.a_center.y - 4)
        mode.snake.target_pos = pygame.Vector2(mode.snake.head_pos)

        mode.apply_portals(now=10.0)
        first_exit = pygame.Vector2(mode.snake.head_pos)
        mode.apply_portals(now=10.1)

        self.assertEqual(first_exit, pygame.Vector2(portal.b_center.x + 6, portal.b_center.y - 4))
        self.assertEqual(mode.snake.head_pos, first_exit)


class DuoModeTests(unittest.TestCase):
    def test_duo_config_exposes_match_rules(self):
        self.assertEqual(config.DUO_MATCH_SECONDS, 180.0)
        self.assertEqual(config.DUO_SENSITIVITY, 8.0)
        self.assertEqual(config.DUO_READY_HOLD_SECONDS, 0.5)
        self.assertEqual(config.DUO_DEATH_PENALTY, 100)

    def test_duo_mode_waits_for_both_players_before_starting(self):
        from modes.duo_mode import DuoMode

        mode = DuoMode(level_index=0, rng=random.Random(20))

        self.assertIsNone(mode.update(duo_result(left=None), dt=0.0, now=1.0))
        self.assertFalse(mode.started)
        self.assertEqual(mode.status, "waiting")

        self.assertIsNone(mode.update(duo_result(), dt=0.0, now=2.0))
        self.assertFalse(mode.started)
        self.assertIsNone(mode.update(duo_result(), dt=0.0, now=2.6))

        self.assertTrue(mode.started)
        self.assertEqual(mode.status, "playing")
        self.assertEqual(mode.remaining_seconds, config.DUO_MATCH_SECONDS)

    def test_duo_pause_freezes_match_timer(self):
        from modes.duo_mode import DuoMode

        mode = DuoMode(level_index=0, rng=random.Random(21))
        mode.update(duo_result(), dt=0.0, now=1.0)
        mode.update(duo_result(), dt=0.0, now=1.6)
        mode.update(duo_result(), dt=1.5, now=3.1)
        elapsed_before_pause = mode.elapsed_seconds

        mode.update(duo_result(right=None), dt=5.0, now=8.1)

        self.assertEqual(mode.status, "paused")
        self.assertEqual(mode.pause_reason, "Right hand lost")
        self.assertEqual(mode.elapsed_seconds, elapsed_before_pause)

    def test_duo_match_finishes_when_timer_expires_and_allows_draw(self):
        from modes.duo_mode import DuoMode

        mode = DuoMode(level_index=0, rng=random.Random(22))
        mode.update(duo_result(), dt=0.0, now=1.0)
        mode.update(duo_result(), dt=0.0, now=1.6)
        mode.elapsed_seconds = config.DUO_MATCH_SECONDS - 0.2

        event = mode.update(duo_result(), dt=0.3, now=2.0)

        self.assertEqual(event, "gameover")
        self.assertEqual(mode.status, "finished")
        self.assertEqual(mode.winner, "draw")
        self.assertEqual(mode.result_label, "Draw")

    def test_duo_shared_food_scores_for_eating_player_and_spawns_big_food_globally(self):
        from modes.duo_mode import DuoMode

        mode = DuoMode(level_index=0, rng=random.Random(23))
        mode.update(duo_result(), dt=0.0, now=1.0)
        mode.update(duo_result(), dt=0.0, now=1.6)
        mode.apples_eaten = config.BIG_FOOD_EVERY - 1
        mode.normal_food.position = pygame.Vector2(mode.green.snake.head_pos)
        old_segments = mode.green.snake.target_segments

        mode.update(duo_result(), dt=0.0, now=2.0)

        self.assertEqual(mode.green.score, config.NORMAL_FOOD_SCORE)
        self.assertEqual(mode.blue.score, 0)
        self.assertEqual(mode.green.snake.target_segments, old_segments + config.NORMAL_GROWTH)
        self.assertEqual(mode.apples_eaten, config.BIG_FOOD_EVERY)
        self.assertIsNotNone(mode.big_food)
        self.assertEqual(mode.big_food.duration, config.BIG_FOOD_DURATION)
        self.assertEqual(mode.summary.big_apples_eaten, 0)

    def test_duo_summary_tracks_ready_time_and_big_apple_eaten(self):
        from modes.duo_mode import DuoMode

        mode = DuoMode(level_index=0, rng=random.Random(29))
        mode.update(duo_result(), dt=0.0, now=1.0)
        mode.update(duo_result(), dt=0.0, now=1.6)
        mode.update(duo_result(), dt=1.0, now=2.6)
        mode.spawn_big_food(now=2.0)
        mode.big_food.position = pygame.Vector2(mode.green.snake.head_pos)

        mode.update(duo_result(), dt=0.0, now=2.7)

        self.assertEqual(mode.summary.elapsed_label(), "0:01")
        self.assertEqual(mode.summary.stability_label(), "100%")
        self.assertEqual(mode.summary.big_apples_eaten, 1)
        self.assertEqual(mode.summary.max_speed, config.BASE_SPEED)

    def test_duo_wall_death_deducts_penalty_and_ends_match(self):
        from modes.duo_mode import DuoMode

        wall = pygame.Rect(config.SIDEBAR_WIDTH + 120, 200, 80, 40)
        mode = DuoMode(
            level_index=0,
            levels=[{"name": "Wall Duel", "target_score": 10, "walls": [wall]}],
            rng=random.Random(24),
        )
        mode.update(duo_result(), dt=0.0, now=1.0)
        mode.update(duo_result(), dt=0.0, now=1.6)
        mode.green.snake.head_pos = pygame.Vector2(wall.center)

        event = mode.update(duo_result(), dt=0.0, now=2.0)

        self.assertEqual(event, "gameover")
        self.assertEqual(mode.green.score, -config.DUO_DEATH_PENALTY)
        self.assertEqual(mode.winner, "blue")

    def test_duo_head_collision_deducts_both_players_and_draws(self):
        from modes.duo_mode import DuoMode

        mode = DuoMode(level_index=0, rng=random.Random(25))
        mode.update(duo_result(), dt=0.0, now=1.0)
        mode.update(duo_result(), dt=0.0, now=1.6)
        center = pygame.Vector2(config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2, config.WINDOW_HEIGHT // 2)
        mode.green.snake.head_pos = center
        mode.blue.snake.head_pos = center + pygame.Vector2(config.SNAKE_RADIUS, 0)

        event = mode.update(duo_result(), dt=0.0, now=2.0)

        self.assertEqual(event, "gameover")
        self.assertEqual(mode.green.score, -config.DUO_DEATH_PENALTY)
        self.assertEqual(mode.blue.score, -config.DUO_DEATH_PENALTY)
        self.assertEqual(mode.winner, "draw")

    def test_duo_portal_cooldown_is_independent_per_snake(self):
        from modes.duo_mode import DuoMode

        mode = DuoMode(level_index=3, rng=random.Random(26))
        portal = mode.portals[0]
        mode.green.snake.head_pos = pygame.Vector2(portal.a_center.x + 5, portal.a_center.y)
        mode.blue.snake.head_pos = pygame.Vector2(portal.a_center.x - 5, portal.a_center.y)

        self.assertTrue(mode.apply_portals_for(mode.green, now=10.0))
        self.assertTrue(mode.apply_portals_for(mode.blue, now=10.1))


class SnakeEntityTests(unittest.TestCase):
    def test_snake_moves_smoothly_toward_target_and_tracks_body(self):
        snake = Snake()
        start = pygame.Vector2(snake.head_pos)
        snake.target_pos = start + pygame.Vector2(100, 0)

        snake.update(dt=0.1, speed=200)

        self.assertEqual(snake.head_pos, start + pygame.Vector2(20, 0))
        self.assertGreater(len(snake.body), 1)

    def test_snake_wraps_by_head_radius_without_cross_map_body_trail(self):
        radius = config.SNAKE_RADIUS
        start = pygame.Vector2(config.WINDOW_WIDTH - radius - 2, 400)
        snake = Snake(start)
        old_body = list(snake.body)
        snake.target_pos = pygame.Vector2(config.WINDOW_WIDTH + 100, 400)

        snake.update(dt=0.1, speed=100, wrap=True)

        self.assertEqual(snake.head_pos, pygame.Vector2(config.SIDEBAR_WIDTH + radius + 8, 400))
        self.assertEqual(snake.body[0], snake.head_pos)
        self.assertEqual(snake.body[1:], old_body[:-1])


if __name__ == "__main__":
    unittest.main()
