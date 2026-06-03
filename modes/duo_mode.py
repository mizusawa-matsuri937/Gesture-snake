from __future__ import annotations

import random
from dataclasses import dataclass
from collections.abc import Sequence
from typing import Optional

import pygame

import config
from entities import BigFood, Food, Snake
from modes.obstacle_helpers import ObstacleLayoutMixin
from modes.single_mode import current_speed_for_apples
from utils import distance_sq, index_to_game_target, inside_game_area, point_too_close_to_walls
from vision import DuoVisionResult


@dataclass
class DuoPlayer:
    key: str
    label: str
    snake: Snake
    body_color: tuple[int, int, int]
    body_alt_color: tuple[int, int, int]
    outline_color: tuple[int, int, int]
    score: int = 0
    portal_cooldown_until: float = 0.0


class DuoMode(ObstacleLayoutMixin):
    def __init__(
        self,
        level_index: int = 0,
        levels: Optional[Sequence[dict]] = None,
        challenges: Optional[Sequence[dict]] = None,
        rng: Optional[random.Random] = None,
    ):
        self.levels = list(levels) if levels is not None else list(config.LEVELS)
        self.challenges = list(challenges) if challenges is not None else list(config.ENDLESS_CHALLENGES)
        self.rng = rng or random.Random()
        self.level_index = max(0, min(level_index, len(self.challenges) - 1))
        self.walls = []
        self.moving_walls = []
        self.portals = []
        start = pygame.Vector2(config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2, config.WINDOW_HEIGHT // 2)
        self.green = DuoPlayer(
            "green",
            "Green",
            Snake(start),
            config.COLOR_SNAKE_BODY,
            config.COLOR_SNAKE_BODY_ALT,
            config.COLOR_SNAKE_OUTLINE,
        )
        self.blue = DuoPlayer(
            "blue",
            "Blue",
            Snake(start),
            config.COLOR_BLUE_SNAKE_BODY,
            config.COLOR_BLUE_SNAKE_BODY_ALT,
            config.COLOR_BLUE_SNAKE_OUTLINE,
        )
        self.normal_food = Food(start, 14, config.NORMAL_FOOD_SCORE, config.NORMAL_GROWTH, config.COLOR_FOOD)
        self.big_food: Optional[Food] = None
        self.apples_eaten = 0
        self.elapsed_seconds = 0.0
        self.started = False
        self.status = "waiting"
        self.ready_since: Optional[float] = None
        self.pause_reason = "Waiting for both players"
        self.invincible_until = 0.0
        self.winner = "draw"
        self.result_label = "Draw"
        self.reset(0.0)

    @property
    def current_challenge(self) -> dict:
        return self.challenges[min(self.level_index, len(self.challenges) - 1)]

    @property
    def current_level(self) -> dict:
        source_index = int(self.current_challenge.get("level_index", self.level_index))
        return self.levels[min(source_index, len(self.levels) - 1)]

    @property
    def display_level_number(self) -> int:
        return self.level_index + 1

    @property
    def challenge_name(self) -> str:
        return str(self.current_challenge["name"])

    @property
    def challenge_tags(self) -> tuple[str, ...]:
        return tuple(self.current_challenge.get("tags", ()))

    @property
    def current_speed(self) -> int:
        return current_speed_for_apples(self.apples_eaten)

    @property
    def remaining_seconds(self) -> float:
        return max(0.0, config.DUO_MATCH_SECONDS - self.elapsed_seconds)

    def select_level(self, level_index: int, now: float) -> None:
        self.level_index = max(0, min(level_index, len(self.challenges) - 1))
        self.reset(now)

    def restart_level(self, now: float) -> None:
        self.reset(now)

    def reset(self, now: float) -> None:
        self.walls = self._make_walls(self.current_level.get("walls", []))
        self.moving_walls = self._make_moving_walls(self.current_level.get("moving_walls", []))
        self.portals = self._make_portals(self.current_level.get("portals", []))
        green_spawn, blue_spawn = self.spawn_points()
        self._reset_player(self.green, green_spawn, pygame.Vector2(1, 0))
        self._reset_player(self.blue, blue_spawn, pygame.Vector2(-1, 0))
        self.green.score = 0
        self.blue.score = 0
        self.green.portal_cooldown_until = 0.0
        self.blue.portal_cooldown_until = 0.0
        self.apples_eaten = 0
        self.elapsed_seconds = 0.0
        self.started = False
        self.status = "waiting"
        self.ready_since = None
        self.pause_reason = "Waiting for both players"
        self.invincible_until = now + config.INVINCIBLE_SECONDS
        self.winner = "draw"
        self.result_label = "Draw"
        self.big_food = None
        self.update_moving_walls(now)
        self.normal_food = self.spawn_food()

    def _reset_player(self, player: DuoPlayer, position: pygame.Vector2, direction: pygame.Vector2) -> None:
        player.snake.reset(position)
        player.snake.direction = pygame.Vector2(direction).normalize()
        player.snake.target_pos = pygame.Vector2(position) + player.snake.direction * 70
        spacing_direction = -player.snake.direction
        player.snake.body = [
            pygame.Vector2(position) + spacing_direction * i * config.BODY_POINT_SPACING
            for i in range(config.START_LENGTH)
        ]

    def spawn_points(self) -> tuple[pygame.Vector2, pygame.Vector2]:
        y = int(self.current_level.get("spawn", (0, config.WINDOW_HEIGHT // 2))[1])
        green = self._nearest_safe_spawn(
            pygame.Vector2(config.SIDEBAR_WIDTH + config.GAME_WIDTH * 0.25, y),
            left_side=True,
        )
        blue = self._nearest_safe_spawn(
            pygame.Vector2(config.SIDEBAR_WIDTH + config.GAME_WIDTH * 0.75, y),
            left_side=False,
            avoid=green,
        )
        return green, blue

    def _nearest_safe_spawn(
        self,
        desired: pygame.Vector2,
        left_side: bool,
        avoid: Optional[pygame.Vector2] = None,
    ) -> pygame.Vector2:
        margin = config.SNAKE_RADIUS + 18
        mid_x = config.SIDEBAR_WIDTH + config.GAME_WIDTH / 2
        candidates: list[pygame.Vector2] = []
        x = config.SIDEBAR_WIDTH + margin
        while x <= config.WINDOW_WIDTH - margin:
            if (x < mid_x) != left_side:
                x += config.LEVEL_FOOD_GRID_SIZE
                continue
            y = margin
            while y <= config.WINDOW_HEIGHT - margin:
                point = pygame.Vector2(x, y)
                if self._safe_spawn_point(point, margin, avoid):
                    candidates.append(point)
                y += config.LEVEL_FOOD_GRID_SIZE
            x += config.LEVEL_FOOD_GRID_SIZE
        if not candidates:
            return pygame.Vector2(desired)
        return min(candidates, key=lambda point: (point - desired).length_squared())

    def _safe_spawn_point(
        self,
        point: pygame.Vector2,
        margin: float,
        avoid: Optional[pygame.Vector2],
    ) -> bool:
        if not inside_game_area(point, margin=margin):
            return False
        if point_too_close_to_walls(point, self.food_blocking_rects(), margin):
            return False
        if self.point_too_close_to_portals(point, margin):
            return False
        return avoid is None or (point - avoid).length_squared() >= 180 * 180

    def update(self, result: DuoVisionResult, dt: float, now: float) -> Optional[str]:
        self.update_moving_walls(now)
        if self.big_food and self.big_food.is_expired(now):
            self.big_food = None

        if self.status == "finished":
            return None

        if not result.ready:
            self.ready_since = None
            self.pause_reason = result.pause_reason or self._pause_reason_for(result)
            self.status = "paused" if self.started else "waiting"
            return None

        if not self.started:
            if self.ready_since is None:
                self.ready_since = now
                self.pause_reason = ""
                return None
            if now - self.ready_since < config.DUO_READY_HOLD_SECONDS:
                self.pause_reason = ""
                return None
            self.started = True
            self.invincible_until = now + config.INVINCIBLE_SECONDS

        self.status = "playing"
        self.pause_reason = ""
        self._apply_targets(result)

        self.green.snake.update(dt, self.current_speed, wrap=True)
        self.blue.snake.update(dt, self.current_speed, wrap=True)
        self.apply_portals_for(self.green, now)
        self.apply_portals_for(self.blue, now)

        dead_players = self.dead_players(now)
        if dead_players:
            self.finish(dead_players)
            return "gameover"

        self.handle_food(now)
        self.elapsed_seconds = min(config.DUO_MATCH_SECONDS, self.elapsed_seconds + dt)
        if self.elapsed_seconds >= config.DUO_MATCH_SECONDS:
            self.finish(())
            return "gameover"
        return None

    def _pause_reason_for(self, result: DuoVisionResult) -> str:
        if result.crossed_line:
            return "Finger crossed center line"
        if not result.left.detected:
            return "Left hand lost"
        if not result.right.detected:
            return "Right hand lost"
        return "Waiting for both players"

    def _apply_targets(self, result: DuoVisionResult) -> None:
        if result.left.index_tip_norm is not None:
            self.green.snake.target_pos = index_to_game_target(
                result.left.index_tip_norm,
                config.DUO_SENSITIVITY,
            )
        if result.right.index_tip_norm is not None:
            self.blue.snake.target_pos = index_to_game_target(
                result.right.index_tip_norm,
                config.DUO_SENSITIVITY,
            )

    def handle_food(self, now: float) -> None:
        for player in (self.green, self.blue):
            if self.normal_food.overlaps(player.snake.head_pos, config.SNAKE_RADIUS):
                player.score += self.normal_food.score
                player.snake.grow(self.normal_food.growth)
                self.apples_eaten += 1
                self.normal_food = self.spawn_food(avoid=[self.big_food] if self.big_food else [])
                if self.apples_eaten % config.BIG_FOOD_EVERY == 0 and self.big_food is None:
                    self.spawn_big_food(now)
                break

        if self.big_food is None:
            return
        for player in (self.green, self.blue):
            if self.big_food.overlaps(player.snake.head_pos, config.SNAKE_RADIUS):
                player.score += self.big_food.score
                player.snake.grow(self.big_food.growth)
                self.big_food = None
                break

    def dead_players(self, now: float) -> tuple[DuoPlayer, ...]:
        dead: list[DuoPlayer] = []
        head_limit = (config.SNAKE_RADIUS * 2) ** 2
        if distance_sq(self.green.snake.head_pos, self.blue.snake.head_pos) <= head_limit:
            return (self.green, self.blue)

        for player, opponent in ((self.green, self.blue), (self.blue, self.green)):
            if self.hits_wall(player):
                dead.append(player)
                continue
            if self.hits_opponent_body(player, opponent):
                dead.append(player)
                continue
            if now > self.invincible_until and player.snake.hits_self():
                dead.append(player)
        return tuple(dead)

    def hits_wall(self, player: DuoPlayer) -> bool:
        return any(wall.collides_circle(player.snake.head_pos, config.SNAKE_RADIUS) for wall in self.walls) or any(
            wall.collides_circle(player.snake.head_pos, config.SNAKE_RADIUS) for wall in self.moving_walls
        )

    def hits_opponent_body(self, player: DuoPlayer, opponent: DuoPlayer) -> bool:
        hit_radius = config.SNAKE_RADIUS * 1.15
        hit_radius_sq = hit_radius * hit_radius
        return any(
            distance_sq(player.snake.head_pos, part) < hit_radius_sq
            for part in opponent.snake.body[5::2]
        )

    def finish(self, dead_players: Sequence[DuoPlayer]) -> None:
        for player in dead_players:
            player.score -= config.DUO_DEATH_PENALTY
        self.status = "finished"
        self.pause_reason = ""
        if self.green.score > self.blue.score:
            self.winner = "green"
            self.result_label = "Green Wins"
        elif self.blue.score > self.green.score:
            self.winner = "blue"
            self.result_label = "Blue Wins"
        else:
            self.winner = "draw"
            self.result_label = "Draw"

    def apply_portals_for(self, player: DuoPlayer, now: float) -> bool:
        if now < player.portal_cooldown_until:
            return False
        for portal in self.portals:
            exit_pos = portal.exit_position_for(player.snake.head_pos)
            if exit_pos is None:
                continue
            direction = player.snake.direction if player.snake.direction.length_squared() else pygame.Vector2(1, 0)
            player.snake.teleport_head(exit_pos, direction)
            player.portal_cooldown_until = now + config.PORTAL_COOLDOWN
            return True
        return False

    def spawn_food(self, avoid: Sequence[Optional[Food]] = ()) -> Food:
        return self._spawn_food(
            radius=14,
            score=config.NORMAL_FOOD_SCORE,
            growth=config.NORMAL_GROWTH,
            color=config.COLOR_FOOD,
            avoid=avoid,
        )

    def spawn_big_food(self, now: float) -> Food:
        self.big_food = self._spawn_food(
            radius=25,
            score=config.BIG_FOOD_SCORE,
            growth=config.BIG_GROWTH,
            color=config.COLOR_BIG_FOOD,
            now=now,
            duration=config.BIG_FOOD_DURATION,
            avoid=[self.normal_food],
            big=True,
        )
        return self.big_food

    def _spawn_food(
        self,
        radius: int,
        score: int,
        growth: int,
        color: tuple[int, int, int],
        now: Optional[float] = None,
        duration: Optional[float] = None,
        avoid: Sequence[Optional[Food]] = (),
        big: bool = False,
    ) -> Food:
        safe_candidates = self.safe_food_candidates(require_open_routes=True, radius=radius, avoid=avoid)
        candidates = safe_candidates or self.safe_food_candidates(
            require_open_routes=False,
            radius=radius,
            avoid=avoid,
        )
        pos = self.rng.choice(candidates) if candidates else self.spawn_points()[0]
        food_class = BigFood if big else Food
        return food_class(pygame.Vector2(pos), radius, score, growth, color, now, duration)

    def food_too_close_to_snake(self, point: pygame.Vector2) -> bool:
        head_limit = (config.SNAKE_RADIUS + 55) ** 2
        for player in (self.green, self.blue):
            if (point - player.snake.head_pos).length_squared() < head_limit:
                return True
        body_limit = (config.SNAKE_RADIUS + 20) ** 2
        for player in (self.green, self.blue):
            if any((point - part).length_squared() < body_limit for part in player.snake.body[::3]):
                return True
        return False
