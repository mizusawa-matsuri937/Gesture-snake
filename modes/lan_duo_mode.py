from __future__ import annotations

from dataclasses import dataclass
import socket
import threading
import time
from typing import Any, Optional

import pygame

import config
from entities import Food, Snake
from network.client import GameClient
from network.server import GameServer
from utils import clamp
from vision import VisionResult


@dataclass
class LanRenderPlayer:
    key: str
    label: str
    snake: Snake
    body_color: tuple[int, int, int]
    body_alt_color: tuple[int, int, int]
    outline_color: tuple[int, int, int]
    score: int = 0
    portal_cooldown_until: float = 0.0


class LanRenderState:
    def __init__(self):
        self.walls = []
        self.moving_walls = []
        self.portals = []
        self.green = LanRenderPlayer(
            "green",
            "Player 1",
            Snake(pygame.Vector2(config.SIDEBAR_WIDTH + config.GAME_WIDTH * 0.25, config.WINDOW_HEIGHT / 2)),
            config.COLOR_SNAKE_BODY,
            config.COLOR_SNAKE_BODY_ALT,
            config.COLOR_SNAKE_OUTLINE,
        )
        self.blue = LanRenderPlayer(
            "blue",
            "Player 2",
            Snake(pygame.Vector2(config.SIDEBAR_WIDTH + config.GAME_WIDTH * 0.75, config.WINDOW_HEIGHT / 2)),
            config.COLOR_BLUE_SNAKE_BODY,
            config.COLOR_BLUE_SNAKE_BODY_ALT,
            config.COLOR_BLUE_SNAKE_OUTLINE,
        )
        self.normal_food = Food(
            pygame.Vector2(config.SIDEBAR_WIDTH + config.GAME_WIDTH / 2, config.WINDOW_HEIGHT / 2),
            14,
            config.NORMAL_FOOD_SCORE,
            config.NORMAL_GROWTH,
            config.COLOR_FOOD,
        )
        self.big_food: Optional[Food] = None
        self.remaining_seconds = config.DUO_MATCH_SECONDS
        self.status = "waiting"
        self.pause_reason = "Waiting for host"
        self.winner = None
        self.result_label = "Waiting"
        self.display_level_number = 1
        self.challenge_name = "Classic"
        self.challenge_tags = ("LAN", "Classic")
        self.summary = {
            "time": "0:00",
            "apples": 0,
            "big_apples": 0,
            "max_speed": 0,
            "tracking": "0%",
        }

    def update_from_state(self, state: dict[str, Any], now: float) -> None:
        self.status = str(state.get("status", state.get("phase", "waiting")))
        self.pause_reason = str(state.get("message", ""))
        self.remaining_seconds = float(state.get("time_left", config.DUO_MATCH_SECONDS))
        self.winner = state.get("winner")
        self.result_label = self._result_label()

        snakes = state.get("snakes", {})
        self._update_player(self.green, snakes.get("1", {}))
        self._update_player(self.blue, snakes.get("2", {}))

        foods = state.get("foods", [])
        if foods:
            self.normal_food = self._food_from_state(foods[0], "normal", now)
        big_food = state.get("big_food")
        self.big_food = self._food_from_state(big_food, "big", now) if big_food else None
        if isinstance(state.get("summary"), dict):
            self.summary = dict(state["summary"])

    def _update_player(self, player: LanRenderPlayer, data: dict[str, Any]) -> None:
        player.score = int(data.get("score", player.score))
        body_points = data.get("body", [])
        if body_points:
            body = [pygame.Vector2(point[0], point[1]) for point in body_points]
        else:
            head = data.get("head", [player.snake.head_pos.x, player.snake.head_pos.y])
            body = [pygame.Vector2(head[0], head[1])]
        player.snake.body = body
        player.snake.head_pos = pygame.Vector2(body[0])
        player.snake.target_segments = len(body)
        if len(body) > 1:
            direction = body[0] - body[1]
            if direction.length_squared() > 0:
                player.snake.direction = direction.normalize()

    def _food_from_state(self, data: dict[str, Any], kind: str, now: float) -> Food:
        pos = data.get("pos", [config.SIDEBAR_WIDTH + config.GAME_WIDTH / 2, config.WINDOW_HEIGHT / 2])
        radius = int(data.get("radius", 25 if kind == "big" else 14))
        score = int(data.get("score", config.BIG_FOOD_SCORE if kind == "big" else config.NORMAL_FOOD_SCORE))
        growth = int(data.get("growth", config.BIG_GROWTH if kind == "big" else config.NORMAL_GROWTH))
        color = config.COLOR_BIG_FOOD if kind == "big" else config.COLOR_FOOD
        duration = config.BIG_FOOD_DURATION if kind == "big" else None
        return Food(pygame.Vector2(pos[0], pos[1]), radius, score, growth, color, now, duration)

    def _result_label(self) -> str:
        if self.winner == "1":
            return "Winner: Player 1"
        if self.winner == "2":
            return "Winner: Player 2"
        if self.winner == "draw":
            return "Winner: Draw"
        if self.status == "gameover":
            return "Game Over"
        return self.status.title()


class LanDuoMode:
    def __init__(self):
        self.render_state = LanRenderState()
        self.server: Optional[GameServer] = None
        self.client: Optional[GameClient] = None
        self.is_host = False
        self.host_ip = self.local_lan_ip()
        self.join_ip = ""
        self.error_message = ""
        self.info_message = ""
        self.connecting = False
        self.was_connected = False
        self.connection_lost = False
        self.latest_match_phase = "waiting"
        self._connect_thread: Optional[threading.Thread] = None
        self._connect_result: Optional[bool] = None
        self._lock = threading.Lock()

    @property
    def green(self):
        return self.render_state.green

    @property
    def blue(self):
        return self.render_state.blue

    @property
    def walls(self):
        return self.render_state.walls

    @property
    def moving_walls(self):
        return self.render_state.moving_walls

    @property
    def portals(self):
        return self.render_state.portals

    @property
    def normal_food(self):
        return self.render_state.normal_food

    @property
    def big_food(self):
        return self.render_state.big_food

    @property
    def remaining_seconds(self) -> float:
        return self.render_state.remaining_seconds

    @property
    def status(self) -> str:
        if self.connection_lost:
            return "connection lost"
        if self.connecting:
            return "connecting"
        return self.render_state.status

    @property
    def pause_reason(self) -> str:
        if self.connection_lost:
            return "Connection Lost"
        return self.render_state.pause_reason or self.info_message

    @property
    def winner(self):
        return self.render_state.winner

    @property
    def result_label(self) -> str:
        if self.connection_lost:
            return "Connection Lost"
        return self.render_state.result_label

    @property
    def display_level_number(self) -> int:
        return self.render_state.display_level_number

    @property
    def challenge_name(self) -> str:
        return self.render_state.challenge_name

    @property
    def challenge_tags(self) -> tuple[str, ...]:
        return self.render_state.challenge_tags

    @property
    def summary(self) -> dict[str, Any]:
        return self.render_state.summary

    @property
    def player_label(self) -> str:
        player_id = self.client.player_id if self.client else None
        if player_id == 1:
            return "Player 1"
        if player_id == 2:
            return "Player 2"
        return "Not connected"

    @property
    def connection_label(self) -> str:
        if self.connection_lost:
            return "Lost"
        if self.connecting:
            return "Connecting"
        if self.client and self.client.connected:
            return "Good"
        return "Offline"

    def start_host(self) -> None:
        self.cleanup()
        self.is_host = True
        self.host_ip = self.local_lan_ip()
        self.error_message = ""
        self.info_message = "Starting host"
        self.connection_lost = False
        self.latest_match_phase = "waiting"
        self.server = GameServer(host="0.0.0.0", port=config.LAN_DEFAULT_PORT)
        try:
            self.server.start()
        except OSError as exc:
            self.error_message = str(exc)
            self.info_message = "Host failed"
            self.server = None
            return
        self.client = GameClient("127.0.0.1", self.server.port, "Player 1")
        self._connect_async(self.client)

    def start_join_entry(self) -> None:
        self.cleanup()
        self.is_host = False
        self.join_ip = self.join_ip or ""
        self.error_message = ""
        self.info_message = "Enter host IP"
        self.connection_lost = False
        self.latest_match_phase = "waiting"

    def connect_to_host(self) -> None:
        if self.connecting:
            return
        ip = self.join_ip.strip()
        if not ip:
            self.error_message = "Enter a host IP"
            return
        if self.client is not None:
            self.client.disconnect()
        self.error_message = ""
        self.info_message = "Connecting"
        self.connection_lost = False
        self.client = GameClient(ip, config.LAN_DEFAULT_PORT, "Player 2")
        self._connect_async(self.client)

    def start_match(self) -> None:
        if self.client and self.client.connected:
            self.client.send_start_match(map_id=0)

    def can_start_match(self) -> bool:
        if not self.is_host or self.server is None or self.client is None or not self.client.connected:
            return False
        return self.server.get_status()["player_count"] >= 2

    def handle_key_event(self, event: pygame.event.Event) -> bool:
        if event.key == pygame.K_RETURN:
            return True
        if event.key == pygame.K_BACKSPACE:
            self.join_ip = self.join_ip[:-1]
        return False

    def handle_text_input(self, text: str) -> None:
        for char in text:
            if char in "0123456789." and len(self.join_ip) < 15:
                self.join_ip += char

    def update(self, result: VisionResult, now: float) -> None:
        self._poll_connect_result()
        if self.client and self.client.connected:
            self.was_connected = True
            target = result.index_tip_norm if result.detected and result.index_tip_norm else (0.5, 0.5)
            self.client.send_input(
                detected=result.detected,
                target_x=clamp(target[0], 0.0, 1.0),
                target_y=clamp(target[1], 0.0, 1.0),
                pinch_clicked=result.pinch_clicked,
                peace_gesture=result.peace_triggered,
                timestamp=now,
            )
            state = self.client.get_latest_state()
            if state:
                self.latest_match_phase = str(state.get("phase", self.latest_match_phase))
                self.render_state.update_from_state(state, now)
                self.info_message = str(state.get("message", self.info_message))
        elif self.was_connected and not self.connecting:
            self.connection_lost = True
            self.latest_match_phase = "gameover"
            if self.client and self.client.error_message:
                self.error_message = self.client.error_message

    def cleanup(self) -> None:
        if self.client is not None:
            self.client.disconnect()
            self.client = None
        if self.server is not None:
            self.server.stop()
            self.server = None
        self.connecting = False
        self.was_connected = False
        self.connection_lost = False
        self._connect_thread = None
        self._connect_result = None
        self.latest_match_phase = "waiting"
        self.info_message = ""
        self.error_message = ""

    def _connect_async(self, client: GameClient) -> None:
        self.connecting = True
        self._connect_result = None

        def worker() -> None:
            result = client.connect()
            with self._lock:
                self._connect_result = result

        self._connect_thread = threading.Thread(target=worker, daemon=True)
        self._connect_thread.start()

    def _poll_connect_result(self) -> None:
        with self._lock:
            result = self._connect_result
            self._connect_result = None
        if result is None:
            return
        self.connecting = False
        if result:
            self.info_message = f"Connected as {self.player_label}"
            self.error_message = ""
            return
        self.info_message = "Connection failed"
        self.error_message = self.client.error_message if self.client else "Connection failed"

    @staticmethod
    def local_lan_ip() -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(("8.8.8.8", 80))
                return str(probe.getsockname()[0])
        except OSError:
            return "127.0.0.1"
