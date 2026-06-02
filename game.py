from __future__ import annotations

import sys
from typing import Optional

import pygame

import config
from modes.level_mode import LevelMode
from modes.single_mode import SingleMode
from ui import Button, GameUI
from utils import next_sensitivity_index, norm_to_window
from vision import VisionResult, VisionSystem, should_pause_for_tracking


class NullVisionSystem:
    camera_ready = False

    def update(self, now: float) -> VisionResult:
        return VisionResult()

    def seconds_since_seen(self, now: float) -> float:
        return now

    def release(self) -> None:
        return None


class Game:
    def __init__(
        self,
        fullscreen: Optional[bool] = None,
        windowed_size: tuple[int, int] = config.WINDOWED_SIZE,
        use_camera: bool = True,
    ):
        pygame.init()
        pygame.display.set_caption("Gesture Snake")
        self.fullscreen = config.FULLSCREEN_DEFAULT if fullscreen is None else fullscreen
        self.windowed_size = windowed_size
        self.screen = self._create_display(self.fullscreen)
        self.clock = pygame.time.Clock()
        self.vision = VisionSystem() if use_camera else NullVisionSystem()
        self.ui = GameUI(self.screen)

        self.state = config.STATE_MENU
        self.active_mode_name = "single"
        self.paused_state = config.STATE_PLAYING_SINGLE
        self.pause_reason: Optional[str] = None
        self.sensitivity_index = config.DEFAULT_SENSITIVITY_INDEX

        self.single_mode = SingleMode()
        self.level_mode = LevelMode()

        self.menu_buttons: list[tuple[str, Button]] = []
        self.options_buttons: list[tuple[str, Button]] = []
        self.pause_buttons: list[tuple[str, Button]] = []
        self.gameover_buttons: list[tuple[str, Button]] = []
        self.coming_soon_buttons: list[tuple[str, Button]] = []
        self._create_buttons()

    def _create_display(self, fullscreen: bool) -> pygame.Surface:
        flags = pygame.FULLSCREEN if fullscreen else 0
        size = (0, 0) if fullscreen else self.windowed_size
        screen = pygame.display.set_mode(size, flags)
        actual_size = screen.get_size()
        if actual_size[0] < config.WINDOWED_SIZE[0] or actual_size[1] < config.WINDOWED_SIZE[1]:
            screen = pygame.display.set_mode(config.WINDOWED_SIZE)
            self.fullscreen = False
            actual_size = screen.get_size()
        config.configure_layout(actual_size)
        return screen

    def toggle_fullscreen(self) -> None:
        self.fullscreen = not self.fullscreen
        self.screen = self._create_display(self.fullscreen)
        self.ui = GameUI(self.screen)
        self._create_buttons()

    def _create_buttons(self) -> None:
        center_x = config.SIDEBAR_WIDTH + config.GAME_WIDTH // 2
        scale = config.LAYOUT_SCALE
        w, h = int(340 * scale), int(76 * scale)
        gap = int(16 * scale)
        menu_start = int(config.WINDOW_HEIGHT * 0.34)
        self.menu_buttons = [
            ("single", Button(pygame.Rect(center_x - w // 2, menu_start, w, h), "Single Player", "Endless")),
            ("level", Button(pygame.Rect(center_x - w // 2, menu_start + (h + gap), w, h), "Level Mode", "Stages")),
            ("options", Button(pygame.Rect(center_x - w // 2, menu_start + 2 * (h + gap), w, h), "Options", "Sensitivity")),
            (
                "duo",
                Button(
                    pygame.Rect(center_x - w // 2, menu_start + 3 * (h + gap), w, h),
                    "Duo Mode",
                    "Coming Soon",
                    config.COLOR_WARNING,
                ),
            ),
        ]
        option_y = int(config.WINDOW_HEIGHT * 0.50)
        self.options_buttons = [
            ("sensitivity_down", Button(pygame.Rect(center_x - int(250 * scale), option_y, int(130 * scale), int(64 * scale)), "Lower")),
            ("sensitivity_up", Button(pygame.Rect(center_x + int(120 * scale), option_y, int(130 * scale), int(64 * scale)), "Higher")),
            ("menu", Button(pygame.Rect(center_x - w // 2, option_y + int(150 * scale), w, h), "Back to Menu")),
        ]
        overlay_button_y = int(config.WINDOW_HEIGHT * 0.66)
        self.pause_buttons = [
            ("resume", Button(pygame.Rect(center_x - w // 2, overlay_button_y, w, h), "Resume")),
            ("restart", Button(pygame.Rect(center_x - w // 2, overlay_button_y + (h + gap), w, h), "Restart")),
            ("menu", Button(pygame.Rect(center_x - w // 2, overlay_button_y + 2 * (h + gap), w, h), "Back to Menu")),
        ]
        self.gameover_buttons = [
            ("restart", Button(pygame.Rect(center_x - w // 2, overlay_button_y, w, h), "Restart")),
            ("menu", Button(pygame.Rect(center_x - w // 2, overlay_button_y + (h + gap), w, h), "Back to Menu")),
        ]
        self.coming_soon_buttons = [
            ("menu", Button(pygame.Rect(center_x - w // 2, overlay_button_y, w, h), "Back to Menu")),
        ]

    @property
    def current_sensitivity(self) -> float:
        return config.SENSITIVITY_OPTIONS[self.sensitivity_index][1]

    @property
    def current_sensitivity_label(self) -> str:
        label, value = config.SENSITIVITY_OPTIONS[self.sensitivity_index]
        return f"{label} x{value:g}"

    @property
    def active_mode(self):
        return self.level_mode if self.active_mode_name == "level" else self.single_mode

    def run(self) -> None:
        running = True
        while running:
            dt = min(self.clock.tick(config.FPS) / 1000.0, 0.05)
            now = pygame.time.get_ticks() / 1000.0
            mouse_clicked = False
            mouse_pos = pygame.mouse.get_pos()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                    self.toggle_fullscreen()
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    mouse_clicked = True

            result = self.vision.update(now)
            self.ui.update_camera_surface(result.frame)
            cursor_pos = self._cursor_pos(result)

            if self.state == config.STATE_MENU:
                self._handle_menu(result, cursor_pos, mouse_pos, mouse_clicked, now)
            elif self.state == config.STATE_PLAYING_SINGLE:
                self._handle_playing_single(result, dt, now)
            elif self.state == config.STATE_PLAYING_LEVEL:
                self._handle_playing_level(result, dt, now)
            elif self.state == config.STATE_LEVEL_CLEAR:
                self._handle_level_clear(now)
            elif self.state == config.STATE_PAUSED:
                self._handle_paused(result, cursor_pos, mouse_pos, mouse_clicked, now)
            elif self.state == config.STATE_GAMEOVER:
                self._handle_gameover(result, cursor_pos, mouse_pos, mouse_clicked, now)
            elif self.state == config.STATE_COMING_SOON:
                self._handle_coming_soon(result, cursor_pos, mouse_pos, mouse_clicked)
            elif self.state == config.STATE_OPTIONS:
                self._handle_options(result, cursor_pos, mouse_pos, mouse_clicked)

            self.draw(result, cursor_pos, mouse_pos, now)

        self.vision.release()
        pygame.quit()
        sys.exit()

    def _cursor_pos(self, result: VisionResult) -> Optional[tuple[int, int]]:
        if result.detected and result.index_tip_norm is not None:
            return norm_to_window(result.index_tip_norm)
        return None

    def start_single_mode(self, now: float) -> None:
        self.single_mode.reset(now)
        self.active_mode_name = "single"
        self.state = config.STATE_PLAYING_SINGLE
        self.pause_reason = None

    def start_level_mode(self, now: float) -> None:
        self.level_mode = LevelMode()
        self.level_mode.restart_level(now)
        self.active_mode_name = "level"
        self.state = config.STATE_PLAYING_LEVEL
        self.pause_reason = None

    def _handle_menu(
        self,
        result: VisionResult,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: tuple[int, int],
        mouse_clicked: bool,
        now: float,
    ) -> None:
        for action, button in self.menu_buttons:
            if button.clicked(cursor_pos, result.pinch_clicked, mouse_pos, mouse_clicked):
                if action == "single":
                    self.start_single_mode(now)
                elif action == "level":
                    self.start_level_mode(now)
                elif action == "options":
                    self.state = config.STATE_OPTIONS
                elif action == "duo":
                    self.state = config.STATE_COMING_SOON
                return

    def _handle_options(
        self,
        result: VisionResult,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: tuple[int, int],
        mouse_clicked: bool,
    ) -> None:
        for action, button in self.options_buttons:
            if button.clicked(cursor_pos, result.pinch_clicked, mouse_pos, mouse_clicked):
                if action == "sensitivity_down":
                    self.sensitivity_index = next_sensitivity_index(self.sensitivity_index, -1)
                elif action == "sensitivity_up":
                    self.sensitivity_index = next_sensitivity_index(self.sensitivity_index, 1)
                elif action == "menu":
                    self.state = config.STATE_MENU
                return

    def _handle_playing_single(self, result: VisionResult, dt: float, now: float) -> None:
        if should_pause_for_tracking(result, self.vision.seconds_since_seen(now)):
            self._pause(config.STATE_PLAYING_SINGLE)
            return
        event = self.single_mode.update(result, dt, now, self.current_sensitivity)
        if event == "gameover":
            self.active_mode_name = "single"
            self.state = config.STATE_GAMEOVER

    def _handle_playing_level(self, result: VisionResult, dt: float, now: float) -> None:
        if should_pause_for_tracking(result, self.vision.seconds_since_seen(now)):
            self._pause(config.STATE_PLAYING_LEVEL)
            return
        event = self.level_mode.update(result, dt, now, self.current_sensitivity)
        if event == "gameover":
            self.active_mode_name = "level"
            self.state = config.STATE_GAMEOVER
        elif event == "level_clear":
            self.active_mode_name = "level"
            self.state = config.STATE_LEVEL_CLEAR

    def _handle_level_clear(self, now: float) -> None:
        if self.level_mode.should_auto_advance(now):
            self.level_mode.advance_level(now)
            self.active_mode_name = "level"
            self.state = config.STATE_PLAYING_LEVEL

    def _pause(self, paused_state: str) -> None:
        self.paused_state = paused_state
        self.state = config.STATE_PAUSED
        self.pause_reason = "tracking"

    def _handle_paused(
        self,
        result: VisionResult,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: tuple[int, int],
        mouse_clicked: bool,
        now: float,
    ) -> None:
        if self.pause_reason == "tracking" and result.detected:
            self.state = self.paused_state
            self.pause_reason = None
            return

        for action, button in self.pause_buttons:
            if button.clicked(cursor_pos, result.pinch_clicked, mouse_pos, mouse_clicked):
                if action == "resume":
                    self.state = self.paused_state
                    self.pause_reason = None
                elif action == "restart":
                    if self.paused_state == config.STATE_PLAYING_LEVEL:
                        self.level_mode.restart_level(now)
                        self.active_mode_name = "level"
                        self.state = config.STATE_PLAYING_LEVEL
                    else:
                        self.start_single_mode(now)
                elif action == "menu":
                    self.state = config.STATE_MENU
                    self.pause_reason = None
                return

    def _handle_gameover(
        self,
        result: VisionResult,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: tuple[int, int],
        mouse_clicked: bool,
        now: float,
    ) -> None:
        if result.peace_triggered:
            self._restart_active_mode(now)
            return

        for action, button in self.gameover_buttons:
            if button.clicked(cursor_pos, result.pinch_clicked, mouse_pos, mouse_clicked):
                if action == "restart":
                    self._restart_active_mode(now)
                elif action == "menu":
                    if self.active_mode_name == "level":
                        self.level_mode.back_to_menu()
                    self.state = config.STATE_MENU
                return

    def _restart_active_mode(self, now: float) -> None:
        if self.active_mode_name == "level":
            self.level_mode.restart_level(now)
            self.state = config.STATE_PLAYING_LEVEL
        else:
            self.start_single_mode(now)

    def _handle_coming_soon(
        self,
        result: VisionResult,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: tuple[int, int],
        mouse_clicked: bool,
    ) -> None:
        for _, button in self.coming_soon_buttons:
            if button.clicked(cursor_pos, result.pinch_clicked, mouse_pos, mouse_clicked):
                self.state = config.STATE_MENU
                return

    def draw(
        self,
        result: VisionResult,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: tuple[int, int],
        now: float,
    ) -> None:
        self.screen.blit(self.ui.background, (0, 0))
        draw_mode_name = self._draw_mode_name()
        draw_mode = self.active_mode if draw_mode_name else None
        if draw_mode_name and self.state in {
            config.STATE_PLAYING_SINGLE,
            config.STATE_PLAYING_LEVEL,
            config.STATE_PAUSED,
            config.STATE_GAMEOVER,
            config.STATE_LEVEL_CLEAR,
        }:
            self.ui.draw_world(draw_mode, draw_mode_name, now)

        sidebar_mode_name = draw_mode_name or self.active_mode_name
        self.ui.draw_sidebar(
            result,
            self.active_mode,
            sidebar_mode_name,
            now,
            self.current_sensitivity_label,
            self.vision.camera_ready,
        )

        if self.state == config.STATE_MENU:
            self.ui.draw_menu(self.menu_buttons, cursor_pos, mouse_pos)
        elif self.state == config.STATE_PAUSED:
            self.ui.draw_pause()
            for _, button in self.pause_buttons:
                button.draw(self.screen, self.ui.font_button, self.ui.font_small, cursor_pos, mouse_pos)
        elif self.state == config.STATE_GAMEOVER:
            self.ui.draw_gameover(
                self.gameover_buttons,
                cursor_pos,
                mouse_pos,
                self.active_mode_name,
                self.active_mode,
            )
        elif self.state == config.STATE_COMING_SOON:
            self.ui.draw_coming_soon(self.coming_soon_buttons, cursor_pos, mouse_pos)
        elif self.state == config.STATE_OPTIONS:
            self.ui.draw_options(
                self.options_buttons,
                cursor_pos,
                mouse_pos,
                self.current_sensitivity_label,
            )
        elif self.state == config.STATE_LEVEL_CLEAR:
            self.ui.draw_level_clear(self.level_mode)
        elif self.state == config.STATE_PLAYING_SINGLE and now < self.single_mode.invincible_until:
            self.ui.draw_small_notice("Spawn protection...")
        elif self.state == config.STATE_PLAYING_LEVEL and now < self.level_mode.invincible_until:
            self.ui.draw_small_notice("Spawn protection...")

        if cursor_pos:
            pygame.draw.circle(self.screen, config.COLOR_ACCENT, cursor_pos, 9)
            pygame.draw.circle(self.screen, config.COLOR_TEXT, cursor_pos, 9, 2)

        pygame.display.flip()

    def _draw_mode_name(self) -> Optional[str]:
        if self.state == config.STATE_PLAYING_SINGLE:
            return "single"
        if self.state in {config.STATE_PLAYING_LEVEL, config.STATE_LEVEL_CLEAR}:
            return "level"
        if self.state in {config.STATE_PAUSED, config.STATE_GAMEOVER}:
            return self.active_mode_name
        return None
