from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pygame

import config
from utils import circle_rect_collision, distance_sq, extend_body_trail, move_toward, wrap_in_game_area


@dataclass
class Food:
    position: pygame.Vector2
    radius: int
    score: int
    growth: int
    color: tuple[int, int, int]
    spawn_time: Optional[float] = None
    duration: Optional[float] = None

    def is_expired(self, now: float) -> bool:
        if self.spawn_time is None or self.duration is None:
            return False
        return now - self.spawn_time > self.duration

    def overlaps(self, position: pygame.Vector2, radius: float) -> bool:
        limit = self.radius + radius
        return distance_sq(self.position, position) < limit * limit

    def remaining(self, now: float) -> float:
        if self.spawn_time is None or self.duration is None:
            return 0.0
        return max(0.0, self.duration - (now - self.spawn_time))


class BigFood(Food):
    pass


@dataclass
class Wall:
    rect: pygame.Rect
    color: tuple[int, int, int] = config.COLOR_WALL

    def collides_circle(self, center: pygame.Vector2, radius: float) -> bool:
        return circle_rect_collision(center.x, center.y, radius, self.rect)


class Snake:
    def __init__(
        self,
        start_pos: Optional[pygame.Vector2] = None,
        start_length: int = config.START_LENGTH,
    ):
        self.start_pos = pygame.Vector2(start_pos) if start_pos else pygame.Vector2(
            config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2,
            config.WINDOW_HEIGHT // 2,
        )
        self.head_pos = pygame.Vector2(self.start_pos)
        self.target_pos = pygame.Vector2(self.start_pos)
        self.direction = pygame.Vector2(1, 0)
        self.target_segments = start_length
        self.body: list[pygame.Vector2] = []
        self.reset(self.start_pos, start_length)

    def reset(
        self,
        start_pos: Optional[pygame.Vector2] = None,
        start_length: int = config.START_LENGTH,
    ) -> None:
        if start_pos is not None:
            self.start_pos = pygame.Vector2(start_pos)
        self.head_pos = pygame.Vector2(self.start_pos)
        self.target_pos = pygame.Vector2(self.start_pos)
        self.direction = pygame.Vector2(1, 0)
        self.target_segments = start_length
        self.body = [
            pygame.Vector2(self.start_pos.x - i * config.BODY_POINT_SPACING, self.start_pos.y)
            for i in range(start_length)
        ]

    def update(self, dt: float, speed: float, wrap: bool = False) -> None:
        previous_head = pygame.Vector2(self.head_pos)
        self.head_pos = move_toward(self.head_pos, self.target_pos, speed * dt)
        movement = self.head_pos - previous_head
        if movement.length_squared() > 0:
            self.direction = movement.normalize()
        if wrap:
            self.head_pos = wrap_in_game_area(self.head_pos)
        extend_body_trail(self.body, previous_head, self.head_pos, self.target_segments)

    def grow(self, amount: int) -> None:
        self.target_segments += amount

    def wrap_head(self) -> None:
        self.head_pos = wrap_in_game_area(self.head_pos)

    def hits_self(self) -> bool:
        if len(self.body) < 20:
            return False
        hit_radius = config.SNAKE_RADIUS * 1.15
        hit_radius_sq = hit_radius * hit_radius
        for part in self.body[15::2]:
            if distance_sq(self.head_pos, part) < hit_radius_sq:
                return True
        return False
