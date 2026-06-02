from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Optional

import pygame

import config
from entities import BigFood, Food, MovingWall, PortalPair, Snake, Wall
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
        self.portal_cooldown_until = 0.0
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
        self.moving_walls = self._make_moving_walls(self.current_level.get("moving_walls", []))
        self.portals = self._make_portals(self.current_level.get("portals", []))
        self.snake.reset(self.spawn_point())
        self.invincible_until = now + config.INVINCIBLE_SECONDS
        self.portal_cooldown_until = 0.0
        self.big_food = None
        self.update_moving_walls(now)
        self.food = self.spawn_food()

    def _make_walls(self, specs: Sequence[pygame.Rect | tuple[int, int, int, int]]) -> list[Wall]:
        return [Wall(wall_spec_to_rect(spec)) for spec in specs]

    def _make_moving_walls(self, specs: Sequence[dict]) -> list[MovingWall]:
        walls: list[MovingWall] = []
        for spec in specs:
            walls.append(
                MovingWall(
                    wall_spec_to_rect(spec["rect"]),
                    axis=spec.get("axis", "x"),
                    distance=int(spec.get("distance", 0)),
                    speed=float(spec.get("speed", 0)),
                    phase=float(spec.get("phase", 0.0)),
                    color=spec.get("color", config.COLOR_MOVING_WALL),
                )
            )
        return walls

    def _make_portals(self, specs: Sequence[dict]) -> list[PortalPair]:
        return [
            PortalPair(
                self._relative_point(spec["a"]),
                self._relative_point(spec["b"]),
                int(spec.get("radius", 34)),
                spec.get("color", config.COLOR_PORTAL_BLUE),
            )
            for spec in specs
        ]

    def _relative_point(self, point: tuple[int, int]) -> pygame.Vector2:
        return pygame.Vector2(config.SIDEBAR_WIDTH + point[0], point[1])

    def update(
        self,
        result: VisionResult,
        dt: float,
        now: float,
        sensitivity: float,
    ) -> Optional[str]:
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
            self.big_food = None
            if self.reached_target_score():
                self.clear_started_at = now
                return "level_clear"

        return None

    def update_moving_walls(self, now: float) -> None:
        for wall in self.moving_walls:
            wall.update(now)

    def apply_portals(self, now: float) -> bool:
        if now < self.portal_cooldown_until:
            return False
        for portal in self.portals:
            exit_pos = portal.exit_position_for(self.snake.head_pos)
            if exit_pos is None:
                continue
            direction = self.snake.direction if self.snake.direction.length_squared() else pygame.Vector2(1, 0)
            self.snake.teleport_head(exit_pos, direction)
            self.portal_cooldown_until = now + config.PORTAL_COOLDOWN
            return True
        return False

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

    def safe_food_candidates(
        self,
        require_open_routes: bool,
        radius: int = 14,
        avoid: Sequence[Optional[Food]] = (),
    ) -> list[pygame.Vector2]:
        points: list[pygame.Vector2] = []
        grid = config.LEVEL_FOOD_GRID_SIZE
        margin = radius + config.SNAKE_RADIUS + 8
        start_x = config.SIDEBAR_WIDTH + margin
        end_x = config.WINDOW_WIDTH - margin
        start_y = margin
        end_y = config.WINDOW_HEIGHT - margin
        x = start_x
        wall_rects = self.food_blocking_rects()
        while x <= end_x:
            y = start_y
            while y <= end_y:
                point = pygame.Vector2(x, y)
                if self.is_safe_food_point(
                    point,
                    require_open_routes=require_open_routes,
                    wall_rects=wall_rects,
                    radius=radius,
                    avoid=avoid,
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
        radius: int = 14,
        avoid: Sequence[Optional[Food]] = (),
    ) -> bool:
        walls = list(wall_rects) if wall_rects is not None else self.food_blocking_rects()
        food_clearance = radius + 8
        if not inside_game_area(point, margin=food_clearance):
            return False
        if point_too_close_to_walls(point, walls, food_clearance):
            return False
        if self.point_too_close_to_portals(point, radius + 8):
            return False
        if any(item and item.overlaps(point, radius + 20) for item in avoid):
            return False
        if self.food_too_close_to_snake(point):
            return False
        if require_open_routes:
            return self.open_route_count(point, walls) >= 2
        return True

    def food_blocking_rects(self) -> list[pygame.Rect]:
        return [wall.rect for wall in self.walls] + [wall.track_rect for wall in self.moving_walls]

    def point_too_close_to_portals(self, point: pygame.Vector2, radius: float) -> bool:
        return any(
            (point - portal.a_center).length_squared() < (radius + portal.radius) ** 2
            or (point - portal.b_center).length_squared() < (radius + portal.radius) ** 2
            for portal in self.portals
        )

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

    def static_walls_are_symmetric(self) -> bool:
        wall_rects = [wall.rect for wall in self.walls]
        wall_keys = {self._relative_rect_key(rect) for rect in wall_rects}
        for rect in wall_rects:
            mirrored = pygame.Rect(
                config.WINDOW_WIDTH - (rect.x - config.SIDEBAR_WIDTH) - rect.width,
                rect.y,
                rect.width,
                rect.height,
            )
            if self._relative_rect_key(mirrored) not in wall_keys:
                return False
        return True

    def _relative_rect_key(self, rect: pygame.Rect) -> tuple[int, int, int, int]:
        return (rect.x - config.SIDEBAR_WIDTH, rect.y, rect.width, rect.height)

    def layout_issues(self) -> list[str]:
        issues: list[str] = []
        static_rects = [wall.rect for wall in self.walls]
        moving_tracks = [wall.track_rect for wall in self.moving_walls]
        for i, first in enumerate(static_rects):
            for second in static_rects[i + 1 :]:
                if first.colliderect(second):
                    issues.append("static walls overlap")
        for track in moving_tracks:
            if not inside_game_area(pygame.Vector2(track.left, track.top)) or not inside_game_area(
                pygame.Vector2(track.right, track.bottom)
            ):
                issues.append("moving wall track leaves game area")
            if any(track.colliderect(rect) for rect in static_rects):
                issues.append("moving wall track overlaps static wall")
        for i, first in enumerate(moving_tracks):
            for second in moving_tracks[i + 1 :]:
                if first.colliderect(second):
                    issues.append("moving wall tracks overlap")
        for portal in self.portals:
            for center in (portal.a_center, portal.b_center):
                if not inside_game_area(center, margin=portal.radius):
                    issues.append("portal leaves game area")
            if any(portal.collides_rect(rect, margin=4) for rect in static_rects + moving_tracks):
                issues.append("portal overlaps obstacle")
        return issues
