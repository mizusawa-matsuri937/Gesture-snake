from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Optional

import pygame

import config
from entities import BigFood, Food, Snake
from modes.obstacle_helpers import ObstacleLayoutMixin
from modes.single_mode import current_speed_for_apples
from summary import PerformanceTracker
from utils import index_to_game_target
from vision import VisionResult


class EndlessChallengeMode(ObstacleLayoutMixin):
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
        self.score = 0
        self.apples_eaten = 0
        self.summary = PerformanceTracker()
        self.invincible_until = 0.0
        self.portal_cooldown_until = 0.0
        self.snake = Snake(self.spawn_point())
        self.walls = []
        self.moving_walls = []
        self.portals = []
        self.normal_food = Food(
            self.spawn_point(),
            14,
            config.NORMAL_FOOD_SCORE,
            config.NORMAL_GROWTH,
            config.COLOR_FOOD,
        )
        self.big_food: Optional[Food] = None
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

    def spawn_point(self) -> pygame.Vector2:
        spawn = self.current_level.get("spawn")
        if spawn:
            return pygame.Vector2(config.SIDEBAR_WIDTH + spawn[0], spawn[1])
        return pygame.Vector2(config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2, config.WINDOW_HEIGHT // 2)

    def select_level(self, level_index: int, now: float) -> None:
        self.level_index = max(0, min(level_index, len(self.challenges) - 1))
        self.reset(now)

    def restart_level(self, now: float) -> None:
        self.reset(now)

    def reset(self, now: float) -> None:
        self.score = 0
        self.apples_eaten = 0
        self.summary.reset()
        self.walls = self._make_walls(self.current_level.get("walls", []))
        self.moving_walls = self._make_moving_walls(self.current_level.get("moving_walls", []))
        self.portals = self._make_portals(self.current_level.get("portals", []))
        self.snake.reset(self.spawn_point())
        self.invincible_until = now + config.INVINCIBLE_SECONDS
        self.portal_cooldown_until = 0.0
        self.big_food = None
        self.update_moving_walls(now)
        self.normal_food = self.spawn_food()

    def wrap_snake_head(self) -> None:
        self.snake.wrap_head()

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

        self.snake.update(dt, self.current_speed, wrap=True)
        self.apply_portals(now)

        if self.hits_wall():
            return "gameover"
        if now > self.invincible_until and self.snake.hits_self():
            return "gameover"

        if self.normal_food.overlaps(self.snake.head_pos, config.SNAKE_RADIUS):
            self.score += self.normal_food.score
            self.snake.grow(self.normal_food.growth)
            self.apples_eaten += 1
            self.normal_food = self.spawn_food(avoid=[self.big_food] if self.big_food else [])
            if self.apples_eaten % config.BIG_FOOD_EVERY == 0 and self.big_food is None:
                self.spawn_big_food(now)

        if self.big_food and self.big_food.overlaps(self.snake.head_pos, config.SNAKE_RADIUS):
            self.score += self.big_food.score
            self.snake.grow(self.big_food.growth)
            self.summary.record_big_apple()
            self.big_food = None

        return None

    def hits_wall(self) -> bool:
        return any(wall.collides_circle(self.snake.head_pos, config.SNAKE_RADIUS) for wall in self.walls) or any(
            wall.collides_circle(self.snake.head_pos, config.SNAKE_RADIUS) for wall in self.moving_walls
        )

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
        pos = self.rng.choice(candidates) if candidates else self.spawn_point()
        food_class = BigFood if big else Food
        return food_class(pygame.Vector2(pos), radius, score, growth, color, now, duration)
