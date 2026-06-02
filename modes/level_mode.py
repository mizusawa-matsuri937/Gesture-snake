from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Optional

import pygame

import config
from entities import Food, Snake, Wall
from utils import (
    circle_rect_collision,
    index_to_game_target,
    inside_game_area,
    point_too_close_to_walls,
    wall_spec_to_rect,
)
from vision import VisionResult


def level_speed_for_apples(apples_eaten: int) -> int:
    return min(
        config.LEVEL_BASE_SPEED + apples_eaten * config.LEVEL_SPEED_INCREASE_PER_APPLE,
        config.LEVEL_MAX_SPEED,
    )


class LevelMode:
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
        self.clear_started_at: Optional[float] = None
        self.invincible_until = 0.0
        self.snake = Snake(self.spawn_point())
        self.walls: list[Wall] = []
        self.food: Food = Food(
            self.spawn_point(),
            14,
            config.LEVEL_APPLE_SCORE,
            config.LEVEL_APPLE_GROWTH,
            config.COLOR_FOOD,
        )
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
    def display_level_number(self) -> int:
        return self.level_index + 1

    def spawn_point(self) -> pygame.Vector2:
        return pygame.Vector2(
            config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2,
            config.WINDOW_HEIGHT // 2,
        )

    def restart_level(self, now: float) -> None:
        self.reset_level(now, keep_total=True)

    def back_to_menu(self) -> None:
        self.level_index = 0
        self.level_score = 0
        self.total_score = 0
        self.apples_eaten = 0
        self.clear_started_at = None
        self.reset_level(0.0, keep_total=True)

    def advance_level(self, now: float) -> None:
        if self.level_index < len(self.levels) - 1:
            self.level_index += 1
        self.reset_level(now, keep_total=True)

    def reset_level(self, now: float, keep_total: bool = True) -> None:
        total = self.total_score if keep_total else 0
        self.level_score = 0
        self.apples_eaten = 0
        self.total_score = total
        self.clear_started_at = None
        self.walls = self._make_walls(self.current_level.get("walls", []))
        self.snake.reset(self.spawn_point())
        self.invincible_until = now + config.INVINCIBLE_SECONDS
        self.food = self.spawn_food()

    def _make_walls(self, specs: Sequence[pygame.Rect | tuple[int, int, int, int]]) -> list[Wall]:
        return [Wall(wall_spec_to_rect(spec)) for spec in specs]

    def update(
        self,
        result: VisionResult,
        dt: float,
        now: float,
        sensitivity: float,
    ) -> Optional[str]:
        if result.detected and result.index_tip_norm is not None:
            self.snake.target_pos = index_to_game_target(result.index_tip_norm, sensitivity)

        self.snake.update(dt, self.current_speed, wrap=False)

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
            self.food = self.spawn_food()

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
        return any(wall.collides_circle(self.snake.head_pos, config.SNAKE_RADIUS) for wall in self.walls)

    def spawn_food(self) -> Food:
        safe_candidates = self.safe_food_candidates(require_open_routes=True)
        candidates = safe_candidates or self.safe_food_candidates(require_open_routes=False)
        if candidates:
            pos = self.rng.choice(candidates)
        else:
            pos = self.spawn_point()
        return Food(
            pygame.Vector2(pos),
            14,
            config.LEVEL_APPLE_SCORE,
            config.LEVEL_APPLE_GROWTH,
            config.COLOR_FOOD,
        )

    def safe_food_candidates(self, require_open_routes: bool) -> list[pygame.Vector2]:
        points: list[pygame.Vector2] = []
        grid = config.LEVEL_FOOD_GRID_SIZE
        margin = config.SNAKE_RADIUS + 18
        start_x = config.SIDEBAR_WIDTH + margin
        end_x = config.WINDOW_WIDTH - margin
        start_y = margin
        end_y = config.WINDOW_HEIGHT - margin
        x = start_x
        wall_rects = [wall.rect for wall in self.walls]
        while x <= end_x:
            y = start_y
            while y <= end_y:
                point = pygame.Vector2(x, y)
                if self.is_safe_food_point(
                    point,
                    require_open_routes=require_open_routes,
                    wall_rects=wall_rects,
                ):
                    points.append(point)
                y += grid
            x += grid
        return points

    def is_safe_food_point(
        self,
        point: pygame.Vector2,
        require_open_routes: bool,
        wall_rects: Optional[Sequence[pygame.Rect]] = None,
    ) -> bool:
        walls = list(wall_rects) if wall_rects is not None else [wall.rect for wall in self.walls]
        food_clearance = config.SNAKE_RADIUS + 8
        if not inside_game_area(point, margin=food_clearance):
            return False
        if point_too_close_to_walls(point, walls, food_clearance):
            return False
        if self.food_too_close_to_snake(point):
            return False
        if require_open_routes:
            return self.open_route_count(point, walls) >= 2
        return True

    def food_too_close_to_snake(self, point: pygame.Vector2) -> bool:
        head_limit = (config.SNAKE_RADIUS + 55) ** 2
        if (point - self.snake.head_pos).length_squared() < head_limit:
            return True
        body_limit = (config.SNAKE_RADIUS + 20) ** 2
        return any((point - part).length_squared() < body_limit for part in self.snake.body[::3])

    def open_route_count(self, point: pygame.Vector2, walls: Sequence[pygame.Rect]) -> int:
        grid = config.LEVEL_FOOD_GRID_SIZE
        clearance = config.SNAKE_RADIUS + 8
        route_count = 0
        for delta in (
            pygame.Vector2(0, -grid),
            pygame.Vector2(0, grid),
            pygame.Vector2(-grid, 0),
            pygame.Vector2(grid, 0),
        ):
            neighbor = point + delta
            if not inside_game_area(neighbor, margin=clearance):
                continue
            if point_too_close_to_walls(neighbor, walls, clearance):
                continue
            route_count += 1
        return route_count
