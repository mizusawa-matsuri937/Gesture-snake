from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
import pygame

import config
from entities import Food, MovingWall, PortalPair, Snake, Wall
from utils import load_font


class Button:
    def __init__(
        self,
        rect: pygame.Rect,
        text: str,
        subtitle: str = "",
        accent: tuple[int, int, int] = config.COLOR_ACCENT,
    ):
        self.rect = rect
        self.text = text
        self.subtitle = subtitle
        self.accent = accent

    def hovered(self, point: Optional[tuple[int, int]]) -> bool:
        return point is not None and self.rect.collidepoint(point)

    def clicked(
        self,
        cursor_pos: Optional[tuple[int, int]],
        pinch_clicked: bool,
        mouse_pos: Optional[tuple[int, int]] = None,
        mouse_clicked: bool = False,
    ) -> bool:
        return (pinch_clicked and self.hovered(cursor_pos)) or (
            mouse_clicked and self.hovered(mouse_pos)
        )

    def draw(
        self,
        screen: pygame.Surface,
        font: pygame.font.Font,
        small_font: pygame.font.Font,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: Optional[tuple[int, int]] = None,
    ) -> None:
        is_hovered = self.hovered(cursor_pos) or self.hovered(mouse_pos)
        fill = (38, 44, 62) if not is_hovered else (52, 65, 92)
        border = self.accent if is_hovered else (80, 90, 112)

        pygame.draw.rect(screen, fill, self.rect, border_radius=8)
        pygame.draw.rect(screen, border, self.rect, 2, border_radius=8)

        label = font.render(self.text, True, config.COLOR_TEXT)
        screen.blit(label, label.get_rect(center=(self.rect.centerx, self.rect.centery - 8)))
        if self.subtitle:
            sub = small_font.render(self.subtitle, True, config.COLOR_TEXT_MUTED)
            screen.blit(sub, sub.get_rect(center=(self.rect.centerx, self.rect.centery + 22)))


class GameUI:
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        scale = min(config.LAYOUT_SCALE, 1.35)
        self.font_title = load_font(config.CJK_FONTS, int(64 * scale), bold=True)
        self.font_big = load_font(config.CJK_FONTS, int(46 * scale), bold=True)
        self.font_med = load_font(config.CJK_FONTS, int(26 * scale), bold=True)
        self.font_button = load_font(config.CJK_FONTS, int(25 * scale), bold=True)
        self.font_small = load_font(config.CJK_FONTS, int(18 * scale))
        self.font_tiny = load_font(config.CJK_FONTS, int(15 * scale))
        self.background = self._build_background()
        self.cam_surface: Optional[pygame.Surface] = None
        self.camera_preview_rect = pygame.Rect(20, 20, config.SIDEBAR_WIDTH - 40, 0)

    def _build_background(self) -> pygame.Surface:
        surface = pygame.Surface((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        surface.fill(config.COLOR_BG_GAME)
        pygame.draw.rect(
            surface, config.COLOR_BG_SIDEBAR, (0, 0, config.SIDEBAR_WIDTH, config.WINDOW_HEIGHT)
        )
        pygame.draw.line(
            surface,
            (50, 50, 60),
            (config.SIDEBAR_WIDTH, 0),
            (config.SIDEBAR_WIDTH, config.WINDOW_HEIGHT),
            2,
        )
        for x in range(config.SIDEBAR_WIDTH, config.WINDOW_WIDTH, 80):
            pygame.draw.line(surface, config.COLOR_GRID, (x, 0), (x, config.WINDOW_HEIGHT))
        for y in range(0, config.WINDOW_HEIGHT, 80):
            pygame.draw.line(surface, config.COLOR_GRID, (config.SIDEBAR_WIDTH, y), (config.WINDOW_WIDTH, y))
        return surface

    def update_camera_surface(self, frame: Optional[np.ndarray]) -> None:
        if frame is None:
            return
        h, w, _ = frame.shape
        panel = self.camera_panel_rect()
        preview_w = panel.width
        preview_h = max(1, round(panel.width * h / w))
        if preview_h > panel.height:
            preview_h = panel.height
            preview_w = max(1, round(panel.height * w / h))
        resized = cv2.resize(frame, (preview_w, preview_h))
        crop_rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        self.cam_surface = pygame.surfarray.make_surface(np.transpose(crop_rgb, (1, 0, 2)))
        self.camera_preview_rect = self.cam_surface.get_rect(center=panel.center)

    def camera_panel_rect(self) -> pygame.Rect:
        margin = int(20 * config.LAYOUT_SCALE)
        panel_width = config.SIDEBAR_WIDTH - margin * 2
        panel_height = int(panel_width * 9 / 16)
        return pygame.Rect(margin, margin, panel_width, panel_height)

    def draw_world(self, mode, mode_name: str, now: float) -> None:
        if mode_name == "level":
            for wall in mode.moving_walls:
                self.draw_moving_wall_track(wall)
            for wall in mode.walls:
                self.draw_wall(wall)
            for wall in mode.moving_walls:
                self.draw_moving_wall(wall)
            for portal in mode.portals:
                self.draw_portal_pair(portal, now)
            self.draw_apple(mode.food)
            if mode.big_food:
                if int(now * 8) % 2 == 0 or mode.big_food.remaining(now) > 2.0:
                    self.draw_apple(mode.big_food, big=True)
                remaining = self.font_small.render(
                    f"{mode.big_food.remaining(now):.1f}s",
                    True,
                    config.COLOR_WARNING,
                )
                self.screen.blit(
                    remaining,
                    remaining.get_rect(
                        center=(int(mode.big_food.position.x), int(mode.big_food.position.y) - 44)
                    ),
                )
            self.draw_snake(mode.snake)
        elif mode_name == "single_challenge":
            for wall in mode.moving_walls:
                self.draw_moving_wall_track(wall)
            for wall in mode.walls:
                self.draw_wall(wall)
            for wall in mode.moving_walls:
                self.draw_moving_wall(wall)
            for portal in mode.portals:
                self.draw_portal_pair(portal, now)
            self.draw_apple(mode.normal_food)
            if mode.big_food:
                if int(now * 8) % 2 == 0 or mode.big_food.remaining(now) > 2.0:
                    self.draw_apple(mode.big_food, big=True)
                remaining = self.font_small.render(
                    f"{mode.big_food.remaining(now):.1f}s",
                    True,
                    config.COLOR_WARNING,
                )
                self.screen.blit(
                    remaining,
                    remaining.get_rect(
                        center=(int(mode.big_food.position.x), int(mode.big_food.position.y) - 44)
                    ),
                )
            self.draw_snake(mode.snake)
        elif mode_name == "single":
            self.draw_apple(mode.normal_food)
            if mode.big_food:
                if int(now * 8) % 2 == 0 or mode.big_food.remaining(now) > 2.0:
                    self.draw_apple(mode.big_food, big=True)
                remaining = self.font_small.render(
                    f"{mode.big_food.remaining(now):.1f}s", True, config.COLOR_WARNING
                )
                self.screen.blit(
                    remaining,
                    remaining.get_rect(
                        center=(int(mode.big_food.position.x), int(mode.big_food.position.y) - 40)
                    ),
                )
            self.draw_snake(mode.snake)
        elif mode_name == "duo":
            for wall in mode.moving_walls:
                self.draw_moving_wall_track(wall)
            for wall in mode.walls:
                self.draw_wall(wall)
            for wall in mode.moving_walls:
                self.draw_moving_wall(wall)
            for portal in mode.portals:
                self.draw_portal_pair(portal, now)
            self.draw_apple(mode.normal_food)
            if mode.big_food:
                if int(now * 8) % 2 == 0 or mode.big_food.remaining(now) > 2.0:
                    self.draw_apple(mode.big_food, big=True)
                remaining = self.font_small.render(
                    f"{mode.big_food.remaining(now):.1f}s",
                    True,
                    config.COLOR_WARNING,
                )
                self.screen.blit(
                    remaining,
                    remaining.get_rect(
                        center=(int(mode.big_food.position.x), int(mode.big_food.position.y) - 44)
                    ),
                )
            self.draw_snake(
                mode.green.snake,
                mode.green.body_color,
                mode.green.body_alt_color,
                mode.green.outline_color,
            )
            self.draw_snake(
                mode.blue.snake,
                mode.blue.body_color,
                mode.blue.body_alt_color,
                mode.blue.outline_color,
            )

    def draw_wall(self, wall: Wall) -> None:
        pygame.draw.rect(self.screen, wall.color, wall.rect, border_radius=3)
        pygame.draw.rect(self.screen, config.COLOR_WALL_BORDER, wall.rect, 2, border_radius=3)

    def draw_moving_wall_track(self, wall: MovingWall) -> None:
        track = wall.track_rect.inflate(10, 10)
        pygame.draw.rect(self.screen, config.COLOR_MOVING_WALL_TRACK, track, border_radius=8)
        pygame.draw.rect(self.screen, (90, 100, 132), track, 1, border_radius=8)

    def draw_moving_wall(self, wall: MovingWall) -> None:
        pygame.draw.rect(self.screen, wall.color, wall.rect, border_radius=5)
        pygame.draw.rect(self.screen, (210, 220, 255), wall.rect, 2, border_radius=5)
        inner = wall.rect.inflate(-12, -12)
        if inner.width > 0 and inner.height > 0:
            pygame.draw.rect(self.screen, (88, 220, 255), inner, border_radius=4)

    def draw_portal_pair(self, portal: PortalPair, now: float) -> None:
        pulse = 2 + int((now * 4) % 3)
        for center in (portal.a_center, portal.b_center):
            pos = (int(center.x), int(center.y))
            pygame.draw.circle(self.screen, (8, 12, 28), pos, portal.radius + 10)
            pygame.draw.circle(self.screen, portal.color, pos, portal.radius + pulse, 3)
            pygame.draw.circle(self.screen, portal.color, pos, portal.radius - 9, 2)
            pygame.draw.circle(self.screen, (220, 235, 255), pos, 6)

    def draw_apple(self, food: Food, big: bool = False) -> None:
        pos = (int(food.position.x), int(food.position.y))
        pygame.draw.circle(self.screen, (110, 20, 20), pos, food.radius + 3)
        pygame.draw.circle(self.screen, food.color, pos, food.radius)
        highlight = max(5, food.radius // 3)
        pygame.draw.circle(
            self.screen,
            (255, 130, 130),
            (pos[0] - food.radius // 3, pos[1] - food.radius // 3),
            highlight,
        )
        stem_rect = (pos[0] - 3, pos[1] - food.radius - 10, 7, 12)
        pygame.draw.ellipse(self.screen, config.COLOR_SNAKE_BODY, stem_rect)
        if big:
            pygame.draw.circle(self.screen, config.COLOR_WARNING, pos, food.radius + 8, 2)

    def draw_snake(
        self,
        snake: Snake,
        body_color: tuple[int, int, int] = config.COLOR_SNAKE_BODY,
        body_alt_color: tuple[int, int, int] = config.COLOR_SNAKE_BODY_ALT,
        outline_color: tuple[int, int, int] = config.COLOR_SNAKE_OUTLINE,
    ) -> None:
        for i, pos in enumerate(reversed(snake.body)):
            x, y = int(pos.x), int(pos.y)
            color = body_color if i % 2 == 0 else body_alt_color
            pygame.draw.circle(self.screen, outline_color, (x, y), config.SNAKE_RADIUS + 2)
            pygame.draw.circle(self.screen, color, (x, y), config.SNAKE_RADIUS)

        hx, hy = int(snake.head_pos.x), int(snake.head_pos.y)
        pygame.draw.circle(self.screen, outline_color, (hx, hy), config.SNAKE_RADIUS + 4)
        pygame.draw.circle(self.screen, config.COLOR_SNAKE_HEAD, (hx, hy), config.SNAKE_RADIUS + 2)

        facing = snake.direction.normalize() if snake.direction.length_squared() else pygame.Vector2(1, 0)
        side = pygame.Vector2(-facing.y, facing.x)
        for offset in (-6, 6):
            eye = pygame.Vector2(hx, hy) + facing * 8 + side * offset
            pygame.draw.circle(self.screen, (0, 0, 0), (int(eye.x), int(eye.y)), 4)
            pygame.draw.circle(self.screen, config.COLOR_TEXT, (int(eye.x + 1), int(eye.y - 1)), 1)

    def draw_sidebar(
        self,
        result,
        mode,
        mode_name: str,
        now: float,
        sensitivity_label: str,
        camera_ready: bool,
    ) -> None:
        margin = int(20 * config.LAYOUT_SCALE)
        panel = self.camera_panel_rect()
        pygame.draw.rect(self.screen, (0, 0, 0), panel)
        if self.cam_surface:
            self.screen.blit(self.cam_surface, self.camera_preview_rect)
        else:
            msg = "Camera offline" if not camera_ready else "Waiting for camera..."
            text = self.font_med.render(msg, True, config.COLOR_DANGER)
            self.screen.blit(text, text.get_rect(center=panel.center))

        duo_ready = mode_name == "duo" and getattr(result, "ready", False)
        detected = getattr(result, "detected", False)
        border_color = config.COLOR_SUCCESS if (duo_ready or (mode_name != "duo" and detected)) else config.COLOR_DANGER
        pygame.draw.rect(self.screen, border_color, panel, 3)
        if mode_name == "duo":
            pygame.draw.line(
                self.screen,
                config.COLOR_WARNING,
                (panel.centerx, panel.top),
                (panel.centerx, panel.bottom),
                2,
            )

        if mode_name == "duo":
            status = "Both ready" if duo_ready else (getattr(result, "pause_reason", "") or "Waiting for players")
            status_color = config.COLOR_SUCCESS if duo_ready else config.COLOR_WARNING
        else:
            status = "Hand locked" if detected else "Waiting for hand"
            status_color = config.COLOR_SUCCESS if detected else config.COLOR_WARNING
        status_text = self.font_small.render(status, True, status_color)
        self.screen.blit(status_text, (margin, panel.bottom + int(12 * config.LAYOUT_SCALE)))

        y = panel.bottom + int(46 * config.LAYOUT_SCALE)
        if mode_name == "level":
            self.draw_level_stat_panel(mode, y, now, sensitivity_label)
            self.draw_level_help_text()
        elif mode_name == "single_challenge":
            self.draw_single_challenge_stat_panel(mode, y, now, sensitivity_label)
            self.draw_single_challenge_help_text()
        elif mode_name == "duo":
            self.draw_duo_stat_panel(mode, y, now, status)
            self.draw_duo_help_text()
        else:
            self.draw_single_stat_panel(mode, y, now, sensitivity_label)
            self.draw_single_help_text()

    def draw_single_stat_panel(self, mode, y: int, now: float, sensitivity_label: str) -> None:
        labels = [
            ("Score", str(mode.score if mode else 0)),
            ("Apples", str(mode.apples_eaten if mode else 0)),
            ("Speed", f"{mode.current_speed if mode else config.BASE_SPEED} px/s"),
            ("Sensitivity", sensitivity_label),
        ]
        self._draw_stat_box(y, labels)
        if mode and mode.big_food:
            remain = self.font_tiny.render(
                f"Big apple {mode.big_food.remaining(now):.1f}s",
                True,
                config.COLOR_WARNING,
            )
            self.screen.blit(remain, (int(38 * config.LAYOUT_SCALE), y + int(126 * config.LAYOUT_SCALE)))

    def draw_single_challenge_stat_panel(self, mode, y: int, now: float, sensitivity_label: str) -> None:
        title = f"{mode.display_level_number}. {mode.challenge_name}" if mode else "Endless Challenge"
        tags = " / ".join(mode.challenge_tags) if mode else "Select a level"
        labels = [
            ("Challenge", title),
            ("Tags", tags),
            ("Score", str(mode.score if mode else 0)),
            ("Apples", str(mode.apples_eaten if mode else 0)),
            ("Speed", f"{mode.current_speed if mode else config.BASE_SPEED} px/s"),
            ("Sensitivity", sensitivity_label),
        ]
        self._draw_stat_box(y, labels, height=int(220 * config.LAYOUT_SCALE))
        if mode and mode.big_food:
            remain = self.font_tiny.render(
                f"Big apple {mode.big_food.remaining(now):.1f}s",
                True,
                config.COLOR_WARNING,
            )
            self.screen.blit(remain, (int(38 * config.LAYOUT_SCALE), y + int(194 * config.LAYOUT_SCALE)))

    def draw_level_stat_panel(self, mode, y: int, now: float, sensitivity_label: str) -> None:
        margin = int(20 * config.LAYOUT_SCALE)
        panel_width = config.SIDEBAR_WIDTH - 40
        panel_height = int(270 * config.LAYOUT_SCALE)
        row_gap = int(31 * config.LAYOUT_SCALE)
        panel = pygame.Rect(margin, y, panel_width, panel_height)
        pygame.draw.rect(self.screen, config.COLOR_PANEL, panel, border_radius=8)

        self._draw_stat_row(
            panel,
            y + int(12 * config.LAYOUT_SCALE),
            "Level",
            f"{mode.display_level_number} / {len(mode.levels)}",
        )
        self._draw_stat_row(
            panel,
            y + int(12 * config.LAYOUT_SCALE) + row_gap,
            "Stage Score",
            f"{mode.level_score} / {mode.target_score}",
        )

        label_y = y + int(78 * config.LAYOUT_SCALE)
        progress_label = self.font_tiny.render("Target Progress", True, config.COLOR_TEXT_MUTED)
        percent_label = self.font_tiny.render(
            f"{int(mode.progress_ratio * 100)}%",
            True,
            config.COLOR_SUCCESS,
        )
        self.screen.blit(progress_label, (panel.x + int(18 * config.LAYOUT_SCALE), label_y))
        self.screen.blit(
            percent_label,
            percent_label.get_rect(
                topright=(panel.right - int(18 * config.LAYOUT_SCALE), label_y)
            ),
        )

        bar_rect = pygame.Rect(
            panel.x + int(18 * config.LAYOUT_SCALE),
            y + int(105 * config.LAYOUT_SCALE),
            panel.width - int(36 * config.LAYOUT_SCALE),
            int(18 * config.LAYOUT_SCALE),
        )
        self.draw_target_progress_bar(mode, bar_rect)

        lower_y = y + int(141 * config.LAYOUT_SCALE)
        lower_labels = [
            ("Total Score", str(mode.total_score)),
            ("Speed", f"{mode.current_speed} px/s"),
            ("Sensitivity", sensitivity_label),
        ]
        for i, (label, value) in enumerate(lower_labels):
            self._draw_stat_row(panel, lower_y + i * row_gap, label, value)
        if mode.big_food:
            bonus = self.font_tiny.render(
                f"Big Apple {mode.big_food.remaining(now):.1f}s",
                True,
                config.COLOR_WARNING,
            )
            self.screen.blit(bonus, (panel.x + int(18 * config.LAYOUT_SCALE), y + int(235 * config.LAYOUT_SCALE)))

    def draw_duo_stat_panel(self, mode, y: int, now: float, status: str) -> None:
        if mode is None:
            labels = [
                ("Mode", "Duo Battle"),
                ("Camera", status),
                ("Sensitivity", "Fixed x8"),
                ("Maps", "5 choices"),
            ]
            self._draw_stat_box(y, labels, height=int(170 * config.LAYOUT_SCALE))
            return

        minutes = int(mode.remaining_seconds) // 60
        seconds = int(mode.remaining_seconds) % 60
        reason = mode.pause_reason or ("Complete" if mode.status == "finished" else "Active")
        labels = [
            ("Map", f"{mode.display_level_number}. {mode.challenge_name}"),
            ("Time", f"{minutes}:{seconds:02d}"),
            ("Green", str(mode.green.score)),
            ("Blue", str(mode.blue.score)),
            ("Status", mode.status.title()),
            ("Reason", reason),
        ]
        self._draw_stat_box(y, labels, height=int(220 * config.LAYOUT_SCALE))
        if mode.big_food:
            remain = self.font_tiny.render(
                f"Big apple {mode.big_food.remaining(now):.1f}s",
                True,
                config.COLOR_WARNING,
            )
            self.screen.blit(remain, (int(38 * config.LAYOUT_SCALE), y + int(194 * config.LAYOUT_SCALE)))

    def _draw_stat_row(self, panel: pygame.Rect, y: int, label: str, value: str) -> None:
        ltxt = self.font_small.render(label, True, config.COLOR_TEXT_MUTED)
        vtxt = self.font_small.render(value, True, config.COLOR_ACCENT)
        self.screen.blit(ltxt, (panel.x + int(18 * config.LAYOUT_SCALE), y))
        self.screen.blit(vtxt, (panel.x + int(132 * config.LAYOUT_SCALE), y))

    def draw_target_progress_bar(self, mode, rect: pygame.Rect) -> None:
        ratio = getattr(mode, "progress_ratio", 0.0)
        ratio = max(0.0, min(1.0, float(ratio)))
        radius = max(4, rect.height // 2)
        pygame.draw.rect(self.screen, config.COLOR_PANEL_DARK, rect, border_radius=radius)
        fill_width = int(round(rect.width * ratio))
        if fill_width > 0:
            fill_rect = rect.copy()
            fill_rect.width = fill_width
            pygame.draw.rect(self.screen, config.COLOR_SUCCESS, fill_rect, border_radius=radius)
        pygame.draw.rect(self.screen, (82, 90, 114), rect, 2, border_radius=radius)

    def _draw_stat_box(self, y: int, labels: list[tuple[str, str]], height: int = 150) -> None:
        margin = int(20 * config.LAYOUT_SCALE)
        row_gap = int(31 * config.LAYOUT_SCALE)
        pygame.draw.rect(
            self.screen,
            config.COLOR_PANEL,
            (margin, y, config.SIDEBAR_WIDTH - 40, height),
            border_radius=8,
        )
        for i, (label, value) in enumerate(labels):
            base_y = y + int(12 * config.LAYOUT_SCALE) + i * row_gap
            ltxt = self.font_small.render(label, True, config.COLOR_TEXT_MUTED)
            vtxt = self.font_small.render(value, True, config.COLOR_ACCENT)
            self.screen.blit(ltxt, (margin + int(18 * config.LAYOUT_SCALE), base_y))
            self.screen.blit(vtxt, (margin + int(132 * config.LAYOUT_SCALE), base_y))

    def draw_single_help_text(self) -> None:
        lines = [
            "Rules",
            "Index finger: steer target",
            "Pinch: click buttons",
            "Peace sign: restart after Game Over",
            "Walls wrap around in endless mode",
            "Only body collision ends the run",
        ]
        self._draw_help_lines(lines, y=config.WINDOW_HEIGHT - int(175 * config.LAYOUT_SCALE))

    def draw_single_challenge_help_text(self) -> None:
        lines = [
            "Endless Challenge",
            "Obstacles are deadly",
            "Edges still wrap",
            "Portals move the snake head",
            "No target bar in this mode",
            "Peace sign: restart after Game Over",
        ]
        self._draw_help_lines(lines, y=config.WINDOW_HEIGHT - int(175 * config.LAYOUT_SCALE))

    def draw_duo_help_text(self) -> None:
        lines = [
            "Duo Battle",
            "Left half: green snake",
            "Right half: blue snake",
            "Edges wrap, obstacles are deadly",
            "Head hits end the match",
            "Timer pauses when tracking fails",
        ]
        self._draw_help_lines(lines, y=config.WINDOW_HEIGHT - int(175 * config.LAYOUT_SCALE))

    def draw_level_help_text(self) -> None:
        lines = [
            "Level Rules",
            "Index finger: steer target",
            "Walls and moving walls are deadly",
            "Portals move the snake head",
            "Big apples are timed bonuses",
            "Reach the target to advance",
        ]
        self._draw_help_lines(lines, y=config.WINDOW_HEIGHT - int(175 * config.LAYOUT_SCALE))

    def _draw_help_lines(self, lines: list[str], y: int) -> None:
        for i, line in enumerate(lines):
            font = self.font_small if i else self.font_med
            color = config.COLOR_TEXT if i == 0 else config.COLOR_TEXT_MUTED
            text = font.render(line, True, color)
            self.screen.blit(text, (int(20 * config.LAYOUT_SCALE), y + i * int(26 * config.LAYOUT_SCALE)))

    def draw_menu(self, buttons, cursor_pos, mouse_pos) -> None:
        center_x = config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2
        title = self.font_title.render("Gesture Snake", True, config.COLOR_TEXT)
        sub = self.font_med.render("Choose a Mode", True, config.COLOR_TEXT_MUTED)
        self.screen.blit(title, title.get_rect(center=(center_x, int(config.WINDOW_HEIGHT * 0.18))))
        self.screen.blit(sub, sub.get_rect(center=(center_x, int(config.WINDOW_HEIGHT * 0.26))))
        for _, button in buttons:
            button.draw(self.screen, self.font_button, self.font_small, cursor_pos, mouse_pos)

    def draw_single_level_select(self, level_buttons, back_buttons, cursor_pos, mouse_pos) -> None:
        center_x = config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2
        title = self.font_title.render("Endless Challenges", True, config.COLOR_TEXT)
        sub = self.font_med.render("Choose a map. No target bar in endless mode.", True, config.COLOR_TEXT_MUTED)
        self.screen.blit(title, title.get_rect(center=(center_x, int(config.WINDOW_HEIGHT * 0.14))))
        self.screen.blit(sub, sub.get_rect(center=(center_x, int(config.WINDOW_HEIGHT * 0.22))))
        for _, button in level_buttons:
            button.draw(self.screen, self.font_button, self.font_small, cursor_pos, mouse_pos)
        for _, button in back_buttons:
            button.draw(self.screen, self.font_button, self.font_small, cursor_pos, mouse_pos)

    def draw_duo_control_select(self, buttons, nav_buttons, cursor_pos, mouse_pos) -> None:
        center_x = config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2
        title = self.font_title.render("Duo Mode", True, config.COLOR_TEXT)
        sub = self.font_med.render("Choose a control setup", True, config.COLOR_TEXT_MUTED)
        self.screen.blit(title, title.get_rect(center=(center_x, int(config.WINDOW_HEIGHT * 0.17))))
        self.screen.blit(sub, sub.get_rect(center=(center_x, int(config.WINDOW_HEIGHT * 0.26))))
        for _, button in buttons:
            button.draw(self.screen, self.font_button, self.font_small, cursor_pos, mouse_pos)
        for _, button in nav_buttons:
            button.draw(self.screen, self.font_button, self.font_small, cursor_pos, mouse_pos)

    def draw_duo_level_select(self, level_buttons, back_buttons, cursor_pos, mouse_pos) -> None:
        center_x = config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2
        title = self.font_title.render("Duo Maps", True, config.COLOR_TEXT)
        sub = self.font_med.render("Shared camera battle. Pick an endless map.", True, config.COLOR_TEXT_MUTED)
        self.screen.blit(title, title.get_rect(center=(center_x, int(config.WINDOW_HEIGHT * 0.14))))
        self.screen.blit(sub, sub.get_rect(center=(center_x, int(config.WINDOW_HEIGHT * 0.22))))
        for _, button in level_buttons:
            button.draw(self.screen, self.font_button, self.font_small, cursor_pos, mouse_pos)
        for _, button in back_buttons:
            button.draw(self.screen, self.font_button, self.font_small, cursor_pos, mouse_pos)

    def draw_options(self, buttons, cursor_pos, mouse_pos, sensitivity_label: str) -> None:
        center_x = config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2
        title = self.font_big.render("Options", True, config.COLOR_TEXT)
        subtitle = self.font_med.render("Gesture Sensitivity", True, config.COLOR_TEXT_MUTED)
        current = self.font_title.render(sensitivity_label, True, config.COLOR_ACCENT)
        hint_lines = [
            "Higher sensitivity covers more map with less hand movement.",
            "Use High or Ultra if your hand often leaves the camera frame.",
        ]

        self.screen.blit(title, title.get_rect(center=(center_x, int(config.WINDOW_HEIGHT * 0.18))))
        self.screen.blit(subtitle, subtitle.get_rect(center=(center_x, int(config.WINDOW_HEIGHT * 0.28))))
        self.screen.blit(current, current.get_rect(center=(center_x, int(config.WINDOW_HEIGHT * 0.40))))
        for i, line in enumerate(hint_lines):
            text = self.font_small.render(line, True, config.COLOR_TEXT_MUTED)
            self.screen.blit(text, text.get_rect(center=(center_x, int(config.WINDOW_HEIGHT * 0.62) + i * int(28 * config.LAYOUT_SCALE))))
        for _, button in buttons:
            button.draw(self.screen, self.font_button, self.font_small, cursor_pos, mouse_pos)

    def draw_pause(self) -> None:
        self.draw_overlay_panel(
            "Tracking Lost",
            ["Show your hand to resume automatically."],
            config.COLOR_WARNING,
        )

    def draw_gameover(self, buttons, cursor_pos, mouse_pos, mode_name: str, mode) -> None:
        title = "Game Over"
        if mode_name == "level":
            subtitle = f"Reached Level {mode.display_level_number}"
            stats = f"Total Score {mode.total_score}"
            hint_text = "Restart the current level or return to menu."
        elif mode_name == "single_challenge":
            subtitle = f"{mode.challenge_name} Score {mode.score}"
            stats = f"Apples {mode.apples_eaten}"
            hint_text = "Restart, choose another challenge, or return to menu."
        elif mode_name == "duo":
            title = "Duo Result"
            subtitle = mode.result_label
            stats = f"Green {mode.green.score}  Blue {mode.blue.score}"
            hint_text = "Restart, choose another map, or return to menu."
        else:
            subtitle = f"Score {mode.score}"
            stats = f"Apples {mode.apples_eaten}"
            hint_text = "Use the peace sign or press Restart."
        self.draw_overlay_panel(title, [subtitle, stats, hint_text], config.COLOR_DANGER)
        hint = self.font_small.render("", True, config.COLOR_TEXT_MUTED)
        center_x = config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2
        self.screen.blit(hint, hint.get_rect(center=(center_x, 0)))
        for _, button in buttons:
            button.draw(self.screen, self.font_button, self.font_small, cursor_pos, mouse_pos)

    def draw_level_clear(self, mode) -> None:
        self.draw_overlay_panel(
            "Level Clear",
            [
                f"Level {mode.display_level_number} Complete",
                f"Stage Score {mode.level_score}",
                f"Total Score {mode.total_score}",
                "Next level starts automatically...",
            ],
            config.COLOR_SUCCESS,
        )

    def draw_coming_soon(self, buttons, cursor_pos, mouse_pos) -> None:
        self.draw_overlay_panel("Coming Soon", ["This mode is still in development."], config.COLOR_WARNING)
        for _, button in buttons:
            button.draw(self.screen, self.font_button, self.font_small, cursor_pos, mouse_pos)

    def draw_overlay_panel(self, title: str, lines: list[str], color: tuple[int, int, int]) -> None:
        center_x = config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2
        center_y = config.WINDOW_HEIGHT // 2
        dim = pygame.Surface((config.GAME_WIDTH, config.WINDOW_HEIGHT), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 175))
        self.screen.blit(dim, (config.SIDEBAR_WIDTH, 0))
        box_w = min(int(720 * config.LAYOUT_SCALE), config.GAME_WIDTH - int(120 * config.LAYOUT_SCALE))
        box_h = min(int(330 * config.LAYOUT_SCALE), config.WINDOW_HEIGHT - int(120 * config.LAYOUT_SCALE))
        box = pygame.Rect(0, 0, box_w, box_h)
        box.center = (center_x, int(config.WINDOW_HEIGHT * 0.43))
        overlay = pygame.Surface(box.size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 255))
        self.screen.blit(overlay, box.topleft)
        pygame.draw.rect(self.screen, color, box, 2, border_radius=8)
        title_surf = self.font_big.render(title, True, color)
        self.screen.blit(title_surf, title_surf.get_rect(center=(center_x, box.y + int(70 * config.LAYOUT_SCALE))))
        for i, line in enumerate(lines):
            font = self.font_med if i == 0 else self.font_small
            line_color = config.COLOR_TEXT if i == 0 else config.COLOR_TEXT_MUTED
            surf = font.render(line, True, line_color)
            y = box.y + int(132 * config.LAYOUT_SCALE) + i * int(34 * config.LAYOUT_SCALE)
            self.screen.blit(surf, surf.get_rect(center=(center_x, y)))

    def draw_small_notice(self, text: str) -> None:
        center_x = config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2
        surf = self.font_med.render(text, True, config.COLOR_SUCCESS)
        self.screen.blit(surf, surf.get_rect(center=(center_x, 90)))
