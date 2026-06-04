from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Optional

import pygame

import config
from entities import BigFood, Food, Snake
from modes.obstacle_helpers import ObstacleLayoutMixin
from summary import PerformanceTracker
from utils import index_to_game_target
from vision import VisionResult


def level_speed_for_apples(apples_eaten: int) -> int:
    return min(
        config.LEVEL_BASE_SPEED + apples_eaten * config.LEVEL_SPEED_INCREASE_PER_APPLE,
        config.LEVEL_MAX_SPEED,
    )


class LevelMode(ObstacleLayoutMixin):
    def __init__(
        self,
        levels: Optional[Sequence[dict]] = None,
        rng: Optional[random.Random] = None,
    ):
        self.levels = list(levels) if levels is not None else list(config.LEVELS)
        self.rng = rng or random.Random()
        self.level_index = 0
        self.level_score = 0
        self.total_score = 0
        self.apples_eaten = 0
        self.summary = PerformanceTracker()
        self.clear_started_at: Optional[float] = None
        self.invincible_until = 0.0
        self.portal_cooldown_until = 0.0
        self.snake = Snake(self.spawn_point())
        self.walls: list[Wall] = []
        self.moving_walls: list[MovingWall] = []
        self.portals: list[PortalPair] = []
        self.food: Food = Food(
            self.spawn_point(),
            14,
            config.LEVEL_APPLE_SCORE,
            config.LEVEL_APPLE_GROWTH,
            config.COLOR_FOOD,
        )
        self.big_food: Optional[Food] = None
        self.reset_level(now=0.0, keep_total=True)

    @property
    def current_level(self) -> dict:
        return self.levels[min(self.level_index, len(self.levels) - 1)]

    @property
    def current_speed(self) -> int:
        return level_speed_for_apples(self.apples_eaten)

    @property
    def target_score(self) -> int:
        return int(self.current_level["target_score"])

    @property
    def progress_ratio(self) -> float:
        if self.target_score <= 0:
            return 0.0
        return max(0.0, min(1.0, self.level_score / self.target_score))

    @property
    def display_level_number(self) -> int:
        return self.level_index + 1

    def spawn_point(self) -> pygame.Vector2:
        spawn = self.current_level.get("spawn")
        if spawn:
            return pygame.Vector2(config.SIDEBAR_WIDTH + spawn[0], spawn[1])
        return pygame.Vector2(config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2, config.WINDOW_HEIGHT // 2)

    def restart_level(self, now: float) -> None:
        self.reset_level(now, keep_total=True)

    def back_to_menu(self) -> None:
        self.level_index = 0
        self.level_score = 0
        self.total_score = 0
        self.apples_eaten = 0
        self.summary.reset()
        self.clear_started_at = None
        self.portal_cooldown_until = 0.0
        self.reset_level(0.0, keep_total=True, reset_summary=True)

    def advance_level(self, now: float) -> None:
        if self.level_index < len(self.levels) - 1:
            self.level_index += 1
        self.reset_level(now, keep_total=True, reset_summary=False)

    def reset_level(self, now: float, keep_total: bool = True, reset_summary: bool = True) -> None:
        total = self.total_score if keep_total else 0
        self.level_score = 0
        self.apples_eaten = 0
        if reset_summary:
            self.summary.reset()
        self.total_score = total
        self.clear_started_at = None
        self.walls = self._make_walls(self.current_level.get("walls", []))
        self.moving_walls = self._make_moving_walls(self.current_level.get("moving_walls", []))
        self.portals = self._make_portals(self.current_level.get("portals", []))
        self.snake.reset(self.spawn_point())
        self.invincible_until = now + config.INVINCIBLE_SECONDS
        self.portal_cooldown_until = 0.0
        self.big_food = None
        self.update_moving_walls(now)
        self.food = self.spawn_food()

    def update(
        self,
        result: VisionResult,
        dt: float,
        now: float,
        sensitivity: float,
    ) -> Optional[str]:
        self.summary.record_frame(dt, result.detected, self.current_speed)
        self.update_moving_walls(now)
        if self.big_food and self.big_food.is_expired(now):
            self.big_food = None

        if result.detected and result.index_tip_norm is not None:
            self.snake.target_pos = index_to_game_target(result.index_tip_norm, sensitivity)

        self.snake.update(dt, self.current_speed, wrap=False)
        self.apply_portals(now)

        if self.hits_boundary() or self.hits_wall():
            return "gameover"
        if now > self.invincible_until and self.snake.hits_self():
            return "gameover"

        if self.food.overlaps(self.snake.head_pos, config.SNAKE_RADIUS):
            self.level_score += self.food.score
            self.total_score += self.food.score
            self.apples_eaten += 1
            self.snake.grow(self.food.growth)
            if self.reached_target_score():
                self.clear_started_at = now
                return "level_clear"
            self.food = self.spawn_food(avoid=[self.big_food] if self.big_food else [])
            if self.apples_eaten % config.BIG_FOOD_EVERY == 0 and self.big_food is None:
                self.spawn_big_food(now)

        if self.big_food and self.big_food.overlaps(self.snake.head_pos, config.SNAKE_RADIUS):
            self.level_score += self.big_food.score
            self.total_score += self.big_food.score
            self.snake.grow(self.big_food.growth)
            self.summary.record_big_apple()
            self.big_food = None
            if self.reached_target_score():
                self.clear_started_at = now
                return "level_clear"

        return None

    def reached_target_score(self) -> bool:
        return self.level_score >= self.target_score

    def should_auto_advance(self, now: float) -> bool:
        return (
            self.clear_started_at is not None
            and now - self.clear_started_at >= config.LEVEL_CLEAR_DELAY
        )

    def hits_boundary(self) -> bool:
        head = self.snake.head_pos
        radius = config.SNAKE_RADIUS
        return (
            head.x - radius < config.SIDEBAR_WIDTH
            or head.x + radius > config.WINDOW_WIDTH
            or head.y - radius < 0
            or head.y + radius > config.WINDOW_HEIGHT
        )

    def hits_wall(self) -> bool:
        return any(wall.collides_circle(self.snake.head_pos, config.SNAKE_RADIUS) for wall in self.walls) or any(
            wall.collides_circle(self.snake.head_pos, config.SNAKE_RADIUS) for wall in self.moving_walls
        )

    def spawn_food(self, avoid: Sequence[Optional[Food]] = ()) -> Food:
        return self._spawn_food(
            radius=14,
            score=config.LEVEL_APPLE_SCORE,
            growth=config.LEVEL_APPLE_GROWTH,
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
            avoid=[self.food],
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
        if candidates:
            pos = self.rng.choice(candidates)
        else:
            pos = self.spawn_point()
        food_class = BigFood if big else Food
        return food_class(
            pygame.Vector2(pos),
            radius,
            score,
            growth,
            color,
            now,
            duration,
        )
