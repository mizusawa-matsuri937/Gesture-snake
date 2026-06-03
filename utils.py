from __future__ import annotations

import math
import os
from typing import Any, Optional, Sequence

import pygame

import config


def load_font(name: str | Sequence[str], size: int, bold: bool = False) -> pygame.font.Font:
    names = [name] if isinstance(name, str) else list(name)
    for candidate in names:
        if os.path.exists(candidate):
            try:
                return pygame.font.Font(candidate, size)
            except (OSError, pygame.error):
                continue
        matched_path = pygame.font.match_font(candidate, bold=bold)
        if matched_path:
            try:
                return pygame.font.Font(matched_path, size)
            except (OSError, pygame.error):
                continue
        try:
            font = pygame.font.SysFont(candidate, size, bold=bold)
        except (TypeError, OSError):
            continue
        if font is not None:
            return font
    return pygame.font.Font(None, size)


def find_existing_font_file(candidates: Sequence[str]) -> Optional[str]:
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def distance_sq(
    a: tuple[float, float] | pygame.Vector2, b: tuple[float, float] | pygame.Vector2
) -> float:
    dx = float(a[0]) - float(b[0])
    dy = float(a[1]) - float(b[1])
    return dx * dx + dy * dy


dist_sq = distance_sq


def wrap_in_game_area(position: pygame.Vector2, margin: float = 0.0) -> pygame.Vector2:
    wrapped = pygame.Vector2(position)
    left = config.SIDEBAR_WIDTH + margin
    right = config.WINDOW_WIDTH - margin
    top = margin
    bottom = config.WINDOW_HEIGHT - margin
    width = right - left
    height = bottom - top

    while wrapped.x < left:
        wrapped.x += width
    while wrapped.x > right:
        wrapped.x -= width
    while wrapped.y < top:
        wrapped.y += height
    while wrapped.y > bottom:
        wrapped.y -= height
    return wrapped


def norm_to_window(norm: tuple[float, float]) -> tuple[int, int]:
    return int(clamp(norm[0], 0.0, 1.0) * config.WINDOW_WIDTH), int(
        clamp(norm[1], 0.0, 1.0) * config.WINDOW_HEIGHT
    )


def apply_pointer_sensitivity(
    norm: tuple[float, float], sensitivity: float
) -> tuple[float, float]:
    scaled_x = 0.5 + (clamp(norm[0], 0.0, 1.0) - 0.5) * sensitivity
    scaled_y = 0.5 + (clamp(norm[1], 0.0, 1.0) - 0.5) * sensitivity
    return round(clamp(scaled_x, 0.0, 1.0), 6), round(clamp(scaled_y, 0.0, 1.0), 6)


def index_to_game_target(
    norm: tuple[float, float], sensitivity: float = 1.0
) -> pygame.Vector2:
    target_norm = apply_pointer_sensitivity(norm, sensitivity)
    return pygame.Vector2(
        config.SIDEBAR_WIDTH + target_norm[0] * config.GAME_WIDTH,
        target_norm[1] * config.WINDOW_HEIGHT,
    )


def next_sensitivity_index(current: int, delta: int) -> int:
    return int(clamp(current + delta, 0, len(config.SENSITIVITY_OPTIONS) - 1))


def move_toward(
    current: pygame.Vector2, target: pygame.Vector2, max_distance: float
) -> pygame.Vector2:
    delta = target - current
    distance = delta.length()
    if distance == 0 or distance <= max_distance:
        return pygame.Vector2(target)
    return pygame.Vector2(current) + delta / distance * max_distance


def extend_body_trail(
    body: list[pygame.Vector2],
    previous_head: pygame.Vector2,
    new_head: pygame.Vector2,
    target_segments: int,
    spacing: float = config.BODY_POINT_SPACING,
) -> None:
    if not body:
        body.append(pygame.Vector2(new_head))
        return

    movement = new_head - body[0]
    distance = movement.length()
    if distance < spacing:
        return

    steps = max(1, math.floor(distance / spacing))
    samples = [body[0].lerp(new_head, i / steps) for i in range(steps, 0, -1)]
    body[:0] = samples

    while len(body) > target_segments:
        body.pop()


def choose_nearest_hand(
    hands: Sequence[tuple[tuple[float, float], Any]],
    previous_center: tuple[float, float],
    max_distance: float,
) -> Optional[tuple[tuple[float, float], Any]]:
    if not hands:
        return None

    nearest = min(hands, key=lambda item: distance_sq(item[0], previous_center))
    if distance_sq(nearest[0], previous_center) <= max_distance * max_distance:
        return nearest
    return None


def point_in_rect(point: pygame.Vector2, rect: pygame.Rect) -> bool:
    return rect.collidepoint(point.x, point.y)


def circle_rect_collision(cx: float, cy: float, radius: float, rect: pygame.Rect) -> bool:
    closest_x = max(rect.left, min(cx, rect.right))
    closest_y = max(rect.top, min(cy, rect.bottom))
    dx = cx - closest_x
    dy = cy - closest_y
    return dx * dx + dy * dy <= radius * radius


def inside_game_area(point: pygame.Vector2, margin: float = 0.0) -> bool:
    return (
        config.SIDEBAR_WIDTH + margin <= point.x <= config.WINDOW_WIDTH - margin
        and margin <= point.y <= config.WINDOW_HEIGHT - margin
    )


def map_index_to_game_area(norm: tuple[float, float], sensitivity: float = 1.0) -> pygame.Vector2:
    return index_to_game_target(norm, sensitivity)


def wall_spec_to_rect(spec: pygame.Rect | tuple[int, int, int, int]) -> pygame.Rect:
    if isinstance(spec, pygame.Rect):
        return pygame.Rect(spec)
    offset_x, y, width, height = spec
    return pygame.Rect(config.SIDEBAR_WIDTH + offset_x, y, width, height)


def point_too_close_to_walls(
    point: pygame.Vector2, walls: Sequence[pygame.Rect], radius: float
) -> bool:
    return any(circle_rect_collision(point.x, point.y, radius, wall) for wall in walls)
