from __future__ import annotations

import random
from collections.abc import Iterable
from typing import Optional

import pygame

import config
from entities import BigFood, Food, Snake
from utils import index_to_game_target, wrap_in_game_area
from vision import VisionResult


def current_speed_for_apples(apples_eaten: int) -> int:
    return min(
        config.BASE_SPEED + apples_eaten * config.SPEED_INCREASE_PER_APPLE,
        config.MAX_SPEED,
    )


class SingleMode:
    def __init__(self, rng: Optional[random.Random] = None):
        self.rng = rng or random.Random()
        self.snake = Snake()
        self.score = 0
        self.apples_eaten = 0
        self.invincible_until = 0.0
        self.normal_food: Food = self._spawn_food(
            radius=14,
            score=config.NORMAL_FOOD_SCORE,
            growth=config.NORMAL_GROWTH,
            color=config.COLOR_FOOD,
        )
        self.big_food: Optional[Food] = None
        self.reset(0.0)

    def reset(self, now: float) -> None:
        self.snake.reset()
        self.score = 0
        self.apples_eaten = 0
        self.invincible_until = now + config.INVINCIBLE_SECONDS
        self.normal_food = self._spawn_food(
            radius=14,
            score=config.NORMAL_FOOD_SCORE,
            growth=config.NORMAL_GROWTH,
            color=config.COLOR_FOOD,
        )
        self.big_food = None

    @property
    def current_speed(self) -> int:
        return current_speed_for_apples(self.apples_eaten)

    def wrap_snake_head(self) -> None:
        self.snake.head_pos = wrap_in_game_area(self.snake.head_pos)

    def update(
        self,
        result: VisionResult,
        dt: float,
        now: float,
        sensitivity: float,
    ) -> Optional[str]:
        if result.detected and result.index_tip_norm is not None:
            self.snake.target_pos = index_to_game_target(result.index_tip_norm, sensitivity)

        self.snake.update(dt, self.current_speed, wrap=True)

        if self.big_food and self.big_food.is_expired(now):
            self.big_food = None

        if self.normal_food.overlaps(self.snake.head_pos, config.SNAKE_RADIUS):
            self.score += self.normal_food.score
            self.snake.grow(self.normal_food.growth)
            self.apples_eaten += 1
            self.normal_food = self._spawn_food(
                radius=14,
                score=config.NORMAL_FOOD_SCORE,
                growth=config.NORMAL_GROWTH,
                color=config.COLOR_FOOD,
                avoid=[self.big_food] if self.big_food else [],
            )
            if self.apples_eaten % config.BIG_FOOD_EVERY == 0 and self.big_food is None:
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

        if self.big_food and self.big_food.overlaps(self.snake.head_pos, config.SNAKE_RADIUS):
            self.score += self.big_food.score
            self.snake.grow(self.big_food.growth)
            self.big_food = None

        if now > self.invincible_until and self.snake.hits_self():
            return "gameover"
        return None

    def _spawn_food(
        self,
        radius: int,
        score: int,
        growth: int,
        color: tuple[int, int, int],
        now: Optional[float] = None,
        duration: Optional[float] = None,
        avoid: Iterable[Optional[Food]] = (),
        big: bool = False,
    ) -> Food:
        pad = radius + 25
        avoid_list = [item for item in avoid if item is not None]
        last_pos = pygame.Vector2(config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2, config.WINDOW_HEIGHT // 2)
        for _ in range(200):
            pos = pygame.Vector2(
                self.rng.randint(config.SIDEBAR_WIDTH + pad, config.WINDOW_WIDTH - pad),
                self.rng.randint(pad, config.WINDOW_HEIGHT - pad),
            )
            last_pos = pos
            if not any(item.overlaps(pos, radius + 20) for item in avoid_list):
                food_class = BigFood if big else Food
                return food_class(pos, radius, score, growth, color, now, duration)
        food_class = BigFood if big else Food
        return food_class(last_pos, radius, score, growth, color, now, duration)
