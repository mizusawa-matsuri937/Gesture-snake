from __future__ import annotations

from typing import Optional

import cv2
import numpy as np
import pygame

import config
from entities import Food, Snake, Wall
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
        self.font_title = load_font(config.CJK_FONTS, 64, bold=True)
        self.font_big = load_font(config.CJK_FONTS, 48, bold=True)
        self.font_med = load_font(config.CJK_FONTS, 28, bold=True)
        self.font_button = load_font(config.CJK_FONTS, 26, bold=True)
        self.font_small = load_font(config.CJK_FONTS, 18)
        self.font_tiny = load_font(config.CJK_FONTS, 15)
        self.background = self._build_background()
        self.cam_surface: Optional[pygame.Surface] = None

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
        dim = min(h, w)
        cx, cy = w // 2, h // 2
        crop = frame[cy - dim // 2 : cy + dim // 2, cx - dim // 2 : cx + dim // 2]
        crop = cv2.resize(crop, (config.SIDEBAR_WIDTH - 40, config.SIDEBAR_WIDTH - 40))
        crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        self.cam_surface = pygame.surfarray.make_surface(np.transpose(crop_rgb, (1, 0, 2)))

    def draw_world(self, mode, mode_name: str, now: float) -> None:
        if mode_name == "level":
            for wall in mode.walls:
                self.draw_wall(wall)
            self.draw_apple(mode.food)
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

    def draw_wall(self, wall: Wall) -> None:
        pygame.draw.rect(self.screen, wall.color, wall.rect, border_radius=3)
        pygame.draw.rect(self.screen, config.COLOR_WALL_BORDER, wall.rect, 2, border_radius=3)

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

    def draw_snake(self, snake: Snake) -> None:
        for i, pos in enumerate(reversed(snake.body)):
            x, y = int(pos.x), int(pos.y)
            color = config.COLOR_SNAKE_BODY if i % 2 == 0 else config.COLOR_SNAKE_BODY_ALT
            pygame.draw.circle(self.screen, config.COLOR_SNAKE_OUTLINE, (x, y), config.SNAKE_RADIUS + 2)
            pygame.draw.circle(self.screen, color, (x, y), config.SNAKE_RADIUS)

        hx, hy = int(snake.head_pos.x), int(snake.head_pos.y)
        pygame.draw.circle(self.screen, config.COLOR_SNAKE_OUTLINE, (hx, hy), config.SNAKE_RADIUS + 4)
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
        margin = 20
        cam_size = config.SIDEBAR_WIDTH - 40
        pygame.draw.rect(self.screen, (0, 0, 0), (margin, margin, cam_size, cam_size))
        if self.cam_surface:
            self.screen.blit(self.cam_surface, (margin, margin))
        else:
            msg = "摄像头未打开" if not camera_ready else "等待画面..."
            text = self.font_med.render(msg, True, config.COLOR_DANGER)
            self.screen.blit(text, text.get_rect(center=(config.SIDEBAR_WIDTH // 2, margin + cam_size // 2)))

        border_color = config.COLOR_SUCCESS if result.detected else config.COLOR_DANGER
        pygame.draw.rect(self.screen, border_color, (margin, margin, cam_size, cam_size), 3)

        status = "已锁定第一只手" if result.detected else "等待识别手势"
        status_color = config.COLOR_SUCCESS if result.detected else config.COLOR_WARNING
        status_text = self.font_small.render(status, True, status_color)
        self.screen.blit(status_text, (margin, margin + cam_size + 12))

        y = margin + cam_size + 46
        if mode_name == "level":
            self.draw_level_stat_panel(mode, y, sensitivity_label)
            self.draw_level_help_text()
        else:
            self.draw_single_stat_panel(mode, y, now, sensitivity_label)
            self.draw_single_help_text()

    def draw_single_stat_panel(self, mode, y: int, now: float, sensitivity_label: str) -> None:
        labels = [
            ("分数", str(mode.score if mode else 0)),
            ("苹果", str(mode.apples_eaten if mode else 0)),
            ("速度", f"{mode.current_speed if mode else config.BASE_SPEED} px/s"),
            ("灵敏度", sensitivity_label),
        ]
        self._draw_stat_box(y, labels)
        if mode and mode.big_food:
            remain = self.font_tiny.render(
                f"大苹果剩余 {mode.big_food.remaining(now):.1f} 秒",
                True,
                config.COLOR_WARNING,
            )
            self.screen.blit(remain, (38, y + 126))

    def draw_level_stat_panel(self, mode, y: int, sensitivity_label: str) -> None:
        labels = [
            ("关卡", f"{mode.display_level_number} / {len(mode.levels)}"),
            ("本关", str(mode.level_score)),
            ("总分", str(mode.total_score)),
            ("目标", str(mode.target_score)),
            ("速度", f"{mode.current_speed} px/s"),
            ("灵敏度", sensitivity_label),
        ]
        self._draw_stat_box(y, labels, height=202)

    def _draw_stat_box(self, y: int, labels: list[tuple[str, str]], height: int = 150) -> None:
        margin = 20
        pygame.draw.rect(
            self.screen,
            config.COLOR_PANEL,
            (margin, y, config.SIDEBAR_WIDTH - 40, height),
            border_radius=8,
        )
        for i, (label, value) in enumerate(labels):
            base_y = y + 12 + i * 30
            ltxt = self.font_small.render(label, True, config.COLOR_TEXT_MUTED)
            vtxt = self.font_small.render(value, True, config.COLOR_ACCENT)
            self.screen.blit(ltxt, (margin + 18, base_y))
            self.screen.blit(vtxt, (margin + 108, base_y))

    def draw_single_help_text(self) -> None:
        lines = [
            "玩法提示",
            "食指移动：平滑追随",
            "捏合：点击按钮",
            "和平手势：结束后重开",
            "撞墙会从另一侧穿出",
            "只撞到自己才结束",
        ]
        self._draw_help_lines(lines, y=config.WINDOW_HEIGHT - 175)

    def draw_level_help_text(self) -> None:
        lines = [
            "闯关规则",
            "食指移动：平滑追随",
            "撞墙/边界/身体会失败",
            "达到目标分数进入下一关",
            "苹果不会生成在墙内",
            "明显死路不会刷苹果",
        ]
        self._draw_help_lines(lines, y=config.WINDOW_HEIGHT - 175)

    def _draw_help_lines(self, lines: list[str], y: int) -> None:
        for i, line in enumerate(lines):
            font = self.font_small if i else self.font_med
            color = config.COLOR_TEXT if i == 0 else config.COLOR_TEXT_MUTED
            text = font.render(line, True, color)
            self.screen.blit(text, (20, y + i * 26))

    def draw_menu(self, buttons, cursor_pos, mouse_pos) -> None:
        center_x = config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2
        title = self.font_title.render("Gesture Snake", True, config.COLOR_TEXT)
        sub = self.font_med.render("选择模式", True, config.COLOR_TEXT_MUTED)
        self.screen.blit(title, title.get_rect(center=(center_x, 145)))
        self.screen.blit(sub, sub.get_rect(center=(center_x, 205)))
        for _, button in buttons:
            button.draw(self.screen, self.font_button, self.font_small, cursor_pos, mouse_pos)

    def draw_options(self, buttons, cursor_pos, mouse_pos, sensitivity_label: str) -> None:
        center_x = config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2
        title = self.font_big.render("选项设置", True, config.COLOR_TEXT)
        subtitle = self.font_med.render("手势灵敏度", True, config.COLOR_TEXT_MUTED)
        current = self.font_title.render(sensitivity_label, True, config.COLOR_ACCENT)
        hint_lines = [
            "灵敏度越高，手指小范围移动就能覆盖更大的地图范围。",
            "超高灵敏度适合手不想离开摄像头中心区域的玩法。",
        ]

        self.screen.blit(title, title.get_rect(center=(center_x, 165)))
        self.screen.blit(subtitle, subtitle.get_rect(center=(center_x, 235)))
        self.screen.blit(current, current.get_rect(center=(center_x, 330)))
        for i, line in enumerate(hint_lines):
            text = self.font_small.render(line, True, config.COLOR_TEXT_MUTED)
            self.screen.blit(text, text.get_rect(center=(center_x, 485 + i * 28)))
        for _, button in buttons:
            button.draw(self.screen, self.font_button, self.font_small, cursor_pos, mouse_pos)

    def draw_pause(self) -> None:
        self.draw_overlay_panel("追踪丢失", "重新识别到手后会自动继续", config.COLOR_WARNING)

    def draw_gameover(self, buttons, cursor_pos, mouse_pos, mode_name: str, mode) -> None:
        if mode_name == "level":
            subtitle = f"到达关卡 {mode.display_level_number} / 总分 {mode.total_score}"
            hint_text = "重新开始当前关或返回菜单"
        else:
            subtitle = f"分数 {mode.score} / 苹果 {mode.apples_eaten}"
            hint_text = "做和平手势可直接重开"
        self.draw_overlay_panel("游戏结束", subtitle, config.COLOR_DANGER)
        hint = self.font_small.render(hint_text, True, config.COLOR_TEXT_MUTED)
        center_x = config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2
        self.screen.blit(hint, hint.get_rect(center=(center_x, 365)))
        for _, button in buttons:
            button.draw(self.screen, self.font_button, self.font_small, cursor_pos, mouse_pos)

    def draw_level_clear(self, mode) -> None:
        subtitle = f"关卡 {mode.display_level_number} 完成 / 总分 {mode.total_score}"
        self.draw_overlay_panel("关卡完成", subtitle, config.COLOR_SUCCESS)
        center_x = config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2
        hint = self.font_small.render("即将进入下一关...", True, config.COLOR_TEXT_MUTED)
        self.screen.blit(hint, hint.get_rect(center=(center_x, 365)))

    def draw_coming_soon(self, buttons, cursor_pos, mouse_pos) -> None:
        self.draw_overlay_panel("开发中", "Coming Soon", config.COLOR_WARNING)
        for _, button in buttons:
            button.draw(self.screen, self.font_button, self.font_small, cursor_pos, mouse_pos)

    def draw_overlay_panel(self, title: str, subtitle: str, color: tuple[int, int, int]) -> None:
        center_x = config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2
        center_y = config.WINDOW_HEIGHT // 2
        box = pygame.Rect(0, 0, 560, 260)
        box.center = (center_x, center_y - 40)
        overlay = pygame.Surface(box.size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 215))
        self.screen.blit(overlay, box.topleft)
        pygame.draw.rect(self.screen, color, box, 2, border_radius=8)
        title_surf = self.font_big.render(title, True, color)
        sub_surf = self.font_med.render(subtitle, True, config.COLOR_TEXT_MUTED)
        self.screen.blit(title_surf, title_surf.get_rect(center=(center_x, box.y + 78)))
        self.screen.blit(sub_surf, sub_surf.get_rect(center=(center_x, box.y + 130)))

    def draw_small_notice(self, text: str) -> None:
        center_x = config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2
        surf = self.font_med.render(text, True, config.COLOR_SUCCESS)
        self.screen.blit(surf, surf.get_rect(center=(center_x, 90)))
