from __future__ import annotations

from collections.abc import Sequence
from typing import Optional

import pygame

import config
from entities import Food, MovingWall, PortalPair, Wall
from utils import inside_game_area, point_too_close_to_walls, wall_spec_to_rect


class ObstacleLayoutMixin:
    snake: object
    walls: list[Wall]
    moving_walls: list[MovingWall]
    portals: list[PortalPair]
    portal_cooldown_until: float

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

    def food_blocking_rects(self) -> list[pygame.Rect]:
        return [wall.rect for wall in self.walls] + [wall.track_rect for wall in self.moving_walls]

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
