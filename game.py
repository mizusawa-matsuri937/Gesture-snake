from __future__ import annotations

import sys
from typing import Optional

import pygame

import config
from modes.duo_mode import DuoMode
from modes.endless_challenge_mode import EndlessChallengeMode
from modes.level_mode import LevelMode
from modes.single_mode import SingleMode
from ui import Button, GameUI
from utils import next_sensitivity_index, norm_to_window
from vision import DuoVisionResult, VisionResult, VisionSystem, should_pause_for_tracking


class NullVisionSystem:
    camera_ready = False

    def update(self, now: float) -> VisionResult:
        return VisionResult()

    def update_duo(self, now: float) -> DuoVisionResult:
        return DuoVisionResult()

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
        self.single_challenge_mode = EndlessChallengeMode()
        self.level_mode = LevelMode()
        self.duo_mode = DuoMode()

        self.menu_buttons: list[tuple[str, Button]] = []
        self.single_level_buttons: list[tuple[int, Button]] = []
        self.single_level_select_buttons: list[tuple[str, Button]] = []
        self.duo_control_buttons: list[tuple[str, Button]] = []
        self.duo_control_nav_buttons: list[tuple[str, Button]] = []
        self.duo_level_buttons: list[tuple[int, Button]] = []
        self.duo_level_select_buttons: list[tuple[str, Button]] = []
        self.options_buttons: list[tuple[str, Button]] = []
        self.pause_buttons: list[tuple[str, Button]] = []
        self.pause_challenge_buttons: list[tuple[str, Button]] = []
        self.gameover_buttons: list[tuple[str, Button]] = []
        self.gameover_challenge_buttons: list[tuple[str, Button]] = []
        self.gameover_duo_buttons: list[tuple[str, Button]] = []
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
                    "Battle",
                    config.COLOR_WARNING,
                ),
            ),
        ]
        card_gap = int(22 * scale)
        card_w = min(int(390 * scale), (config.GAME_WIDTH - int(190 * scale) - card_gap) // 2)
        card_h = int(104 * scale)
        grid_w = card_w * 2 + card_gap
        grid_x = center_x - grid_w // 2
        grid_y = int(config.WINDOW_HEIGHT * 0.30)
        self.single_level_buttons = []
        for index, challenge in enumerate(config.ENDLESS_CHALLENGES):
            row = index // 2
            col = index % 2
            rect = pygame.Rect(
                grid_x + col * (card_w + card_gap),
                grid_y + row * (card_h + card_gap),
                card_w,
                card_h,
            )
            tags = " / ".join(challenge["tags"])
            self.single_level_buttons.append(
                (index, Button(rect, f"{index + 1}. {challenge['name']}", tags))
            )
        select_back_y = grid_y + 3 * (card_h + card_gap) + int(10 * scale)
        self.single_level_select_buttons = [
            ("menu", Button(pygame.Rect(center_x - w // 2, select_back_y, w, h), "Back to Menu")),
        ]
        self.duo_level_buttons = []
        for index, challenge in enumerate(config.ENDLESS_CHALLENGES):
            row = index // 2
            col = index % 2
            rect = pygame.Rect(
                grid_x + col * (card_w + card_gap),
                grid_y + row * (card_h + card_gap),
                card_w,
                card_h,
            )
            tags = " / ".join(challenge["tags"])
            self.duo_level_buttons.append(
                (index, Button(rect, f"{index + 1}. {challenge['name']}", tags, config.COLOR_WARNING))
            )
        self.duo_level_select_buttons = [
            ("back", Button(pygame.Rect(center_x - w // 2, select_back_y, w, h), "Back")),
        ]
        control_y = int(config.WINDOW_HEIGHT * 0.38)
        self.duo_control_buttons = [
            (
                "shared",
                Button(
                    pygame.Rect(center_x - w // 2, control_y, w, h),
                    "Shared Camera",
                    "Two hands, one camera",
                    config.COLOR_SUCCESS,
                ),
            ),
            (
                "separate",
                Button(
                    pygame.Rect(center_x - w // 2, control_y + (h + gap), w, h),
                    "Separate Cameras",
                    "Coming Soon",
                    config.COLOR_WARNING,
                ),
            ),
        ]
        self.duo_control_nav_buttons = [
            ("menu", Button(pygame.Rect(center_x - w // 2, control_y + 2 * (h + gap), w, h), "Back to Menu")),
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
        challenge_h = int(52 * scale)
        challenge_gap = int(8 * scale)
        challenge_y = int(config.WINDOW_HEIGHT * 0.66)
        self.pause_challenge_buttons = [
            ("resume", Button(pygame.Rect(center_x - w // 2, challenge_y, w, challenge_h), "Resume")),
            (
                "restart",
                Button(pygame.Rect(center_x - w // 2, challenge_y + (challenge_h + challenge_gap), w, challenge_h), "Restart"),
            ),
            (
                "level_select",
                Button(
                    pygame.Rect(center_x - w // 2, challenge_y + 2 * (challenge_h + challenge_gap), w, challenge_h),
                    "Level Select",
                ),
            ),
            (
                "menu",
                Button(
                    pygame.Rect(center_x - w // 2, challenge_y + 3 * (challenge_h + challenge_gap), w, challenge_h),
                    "Main Menu",
                ),
            ),
        ]
        self.gameover_buttons = [
            ("restart", Button(pygame.Rect(center_x - w // 2, overlay_button_y, w, h), "Restart")),
            ("menu", Button(pygame.Rect(center_x - w // 2, overlay_button_y + (h + gap), w, h), "Back to Menu")),
        ]
        self.gameover_challenge_buttons = [
            ("restart", Button(pygame.Rect(center_x - w // 2, overlay_button_y, w, h), "Restart")),
            (
                "level_select",
                Button(pygame.Rect(center_x - w // 2, overlay_button_y + (h + gap), w, h), "Level Select"),
            ),
            ("menu", Button(pygame.Rect(center_x - w // 2, overlay_button_y + 2 * (h + gap), w, h), "Main Menu")),
        ]
        self.gameover_duo_buttons = [
            ("restart", Button(pygame.Rect(center_x - w // 2, overlay_button_y, w, h), "Restart")),
            (
                "level_select",
                Button(pygame.Rect(center_x - w // 2, overlay_button_y + (h + gap), w, h), "Map Select"),
            ),
            ("menu", Button(pygame.Rect(center_x - w // 2, overlay_button_y + 2 * (h + gap), w, h), "Main Menu")),
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
        if self.active_mode_name == "level":
            return self.level_mode
        if self.active_mode_name == "single_challenge":
            return self.single_challenge_mode
        if self.active_mode_name == "duo":
            return self.duo_mode
        return self.single_mode

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

            if self._uses_duo_vision():
                result = self.vision.update_duo(now)
            else:
                result = self.vision.update(now)
            self.ui.update_camera_surface(result.frame)
            cursor_pos = self._cursor_pos(result)

            if self.state == config.STATE_MENU:
                self._handle_menu(result, cursor_pos, mouse_pos, mouse_clicked, now)
            elif self.state == config.STATE_SINGLE_LEVEL_SELECT:
                self._handle_single_level_select(result, cursor_pos, mouse_pos, mouse_clicked, now)
            elif self.state == config.STATE_DUO_CONTROL_SELECT:
                self._handle_duo_control_select(result, cursor_pos, mouse_pos, mouse_clicked)
            elif self.state == config.STATE_DUO_LEVEL_SELECT:
                self._handle_duo_level_select(result, cursor_pos, mouse_pos, mouse_clicked, now)
            elif self.state == config.STATE_DUO_WAITING:
                self._handle_duo_waiting(result, now)
            elif self.state == config.STATE_PLAYING_SINGLE:
                self._handle_playing_single(result, dt, now)
            elif self.state == config.STATE_PLAYING_SINGLE_CHALLENGE:
                self._handle_playing_single_challenge(result, dt, now)
            elif self.state == config.STATE_PLAYING_LEVEL:
                self._handle_playing_level(result, dt, now)
            elif self.state == config.STATE_PLAYING_DUO:
                self._handle_playing_duo(result, dt, now)
            elif self.state == config.STATE_LEVEL_CLEAR:
                self._handle_level_clear(now)
            elif self.state == config.STATE_PAUSED:
                self._handle_paused(result, cursor_pos, mouse_pos, mouse_clicked, now)
            elif self.state in {config.STATE_GAMEOVER, config.STATE_DUO_GAMEOVER}:
                self._handle_gameover(result, cursor_pos, mouse_pos, mouse_clicked, now)
            elif self.state == config.STATE_COMING_SOON:
                self._handle_coming_soon(result, cursor_pos, mouse_pos, mouse_clicked)
            elif self.state == config.STATE_OPTIONS:
                self._handle_options(result, cursor_pos, mouse_pos, mouse_clicked)

            self.draw(result, cursor_pos, mouse_pos, now)

        self.vision.release()
        pygame.quit()
        sys.exit()

    def _cursor_pos(self, result) -> Optional[tuple[int, int]]:
        if getattr(result, "detected", False) and getattr(result, "index_tip_norm", None) is not None:
            return norm_to_window(result.index_tip_norm)
        return None

    def _uses_duo_vision(self) -> bool:
        return self.state in {
            config.STATE_DUO_CONTROL_SELECT,
            config.STATE_DUO_LEVEL_SELECT,
            config.STATE_DUO_WAITING,
            config.STATE_PLAYING_DUO,
            config.STATE_DUO_GAMEOVER,
        } or (self.state == config.STATE_COMING_SOON and self.active_mode_name == "duo")

    def start_single_mode(self, now: float) -> None:
        self.single_mode.reset(now)
        self.active_mode_name = "single"
        self.state = config.STATE_PLAYING_SINGLE
        self.pause_reason = None

    def start_single_challenge(self, level_index: int, now: float) -> None:
        self.single_challenge_mode.select_level(level_index, now)
        self.active_mode_name = "single_challenge"
        self.state = config.STATE_PLAYING_SINGLE_CHALLENGE
        self.pause_reason = None

    def start_level_mode(self, now: float) -> None:
        self.level_mode = LevelMode()
        self.level_mode.restart_level(now)
        self.active_mode_name = "level"
        self.state = config.STATE_PLAYING_LEVEL
        self.pause_reason = None

    def start_duo_mode(self, level_index: int, now: float) -> None:
        self.duo_mode.select_level(level_index, now)
        self.active_mode_name = "duo"
        self.state = config.STATE_DUO_WAITING
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
                    self.state = config.STATE_SINGLE_LEVEL_SELECT
                    self.active_mode_name = "single"
                elif action == "level":
                    self.start_level_mode(now)
                elif action == "options":
                    self.state = config.STATE_OPTIONS
                elif action == "duo":
                    self.state = config.STATE_DUO_CONTROL_SELECT
                    self.active_mode_name = "duo"
                return

    def _handle_single_level_select(
        self,
        result: VisionResult,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: tuple[int, int],
        mouse_clicked: bool,
        now: float,
    ) -> None:
        for index, button in self.single_level_buttons:
            if button.clicked(cursor_pos, result.pinch_clicked, mouse_pos, mouse_clicked):
                self.start_single_challenge(index, now)
                return
        for action, button in self.single_level_select_buttons:
            if button.clicked(cursor_pos, result.pinch_clicked, mouse_pos, mouse_clicked):
                if action == "menu":
                    self.state = config.STATE_MENU
                    self.active_mode_name = "single"
                return

    def _button_clicked(
        self,
        button: Button,
        result,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: tuple[int, int],
        mouse_clicked: bool,
    ) -> bool:
        if button.clicked(cursor_pos, getattr(result, "pinch_clicked", False), mouse_pos, mouse_clicked):
            return True
        if isinstance(result, DuoVisionResult):
            for player_result in (result.left, result.right):
                if (
                    player_result.pinch_clicked
                    and player_result.raw_index_tip_norm is not None
                    and button.hovered(norm_to_window(player_result.raw_index_tip_norm))
                ):
                    return True
        return False

    def _handle_duo_control_select(
        self,
        result,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: tuple[int, int],
        mouse_clicked: bool,
    ) -> None:
        for action, button in self.duo_control_buttons:
            if self._button_clicked(button, result, cursor_pos, mouse_pos, mouse_clicked):
                if action == "shared":
                    self.state = config.STATE_DUO_LEVEL_SELECT
                    self.active_mode_name = "duo"
                elif action == "separate":
                    self.state = config.STATE_COMING_SOON
                    self.active_mode_name = "duo"
                return
        for action, button in self.duo_control_nav_buttons:
            if self._button_clicked(button, result, cursor_pos, mouse_pos, mouse_clicked):
                if action == "menu":
                    self.state = config.STATE_MENU
                    self.active_mode_name = "single"
                return

    def _handle_duo_level_select(
        self,
        result,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: tuple[int, int],
        mouse_clicked: bool,
        now: float,
    ) -> None:
        for index, button in self.duo_level_buttons:
            if self._button_clicked(button, result, cursor_pos, mouse_pos, mouse_clicked):
                self.start_duo_mode(index, now)
                return
        for action, button in self.duo_level_select_buttons:
            if self._button_clicked(button, result, cursor_pos, mouse_pos, mouse_clicked):
                if action == "back":
                    self.state = config.STATE_DUO_CONTROL_SELECT
                    self.active_mode_name = "duo"
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

    def _handle_playing_single_challenge(self, result: VisionResult, dt: float, now: float) -> None:
        if should_pause_for_tracking(result, self.vision.seconds_since_seen(now)):
            self._pause(config.STATE_PLAYING_SINGLE_CHALLENGE)
            return
        event = self.single_challenge_mode.update(result, dt, now, self.current_sensitivity)
        if event == "gameover":
            self.active_mode_name = "single_challenge"
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

    def _handle_duo_waiting(self, result, now: float) -> None:
        duo_result = result if isinstance(result, DuoVisionResult) else DuoVisionResult()
        self.duo_mode.update(duo_result, dt=0.0, now=now)
        if self.duo_mode.started:
            self.active_mode_name = "duo"
            self.state = config.STATE_PLAYING_DUO

    def _handle_playing_duo(self, result, dt: float, now: float) -> None:
        duo_result = result if isinstance(result, DuoVisionResult) else DuoVisionResult()
        event = self.duo_mode.update(duo_result, dt, now)
        if event == "gameover":
            self.active_mode_name = "duo"
            self.state = config.STATE_DUO_GAMEOVER

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

        for action, button in self.pause_buttons_for_active_state():
            if button.clicked(cursor_pos, result.pinch_clicked, mouse_pos, mouse_clicked):
                if action == "resume":
                    self.state = self.paused_state
                    self.pause_reason = None
                elif action == "restart":
                    if self.paused_state == config.STATE_PLAYING_LEVEL:
                        self.level_mode.restart_level(now)
                        self.active_mode_name = "level"
                        self.state = config.STATE_PLAYING_LEVEL
                    elif self.paused_state == config.STATE_PLAYING_SINGLE_CHALLENGE:
                        self.single_challenge_mode.restart_level(now)
                        self.active_mode_name = "single_challenge"
                        self.state = config.STATE_PLAYING_SINGLE_CHALLENGE
                    else:
                        self.start_single_mode(now)
                elif action == "level_select":
                    self.active_mode_name = "single"
                    self.state = config.STATE_SINGLE_LEVEL_SELECT
                    self.pause_reason = None
                elif action == "menu":
                    self.state = config.STATE_MENU
                    self.active_mode_name = "single"
                    self.pause_reason = None
                return

    def _handle_gameover(
        self,
        result,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: tuple[int, int],
        mouse_clicked: bool,
        now: float,
    ) -> None:
        if getattr(result, "peace_triggered", False):
            self._restart_active_mode(now)
            return

        for action, button in self.gameover_buttons_for_active_mode():
            if self._button_clicked(button, result, cursor_pos, mouse_pos, mouse_clicked):
                if action == "restart":
                    self._restart_active_mode(now)
                elif action == "level_select":
                    if self.active_mode_name == "duo":
                        self.state = config.STATE_DUO_LEVEL_SELECT
                    else:
                        self.active_mode_name = "single"
                        self.state = config.STATE_SINGLE_LEVEL_SELECT
                elif action == "menu":
                    if self.active_mode_name == "level":
                        self.level_mode.back_to_menu()
                    self.active_mode_name = "single"
                    self.state = config.STATE_MENU
                return

    def _restart_active_mode(self, now: float) -> None:
        if self.active_mode_name == "level":
            self.level_mode.restart_level(now)
            self.state = config.STATE_PLAYING_LEVEL
        elif self.active_mode_name == "single_challenge":
            self.single_challenge_mode.restart_level(now)
            self.state = config.STATE_PLAYING_SINGLE_CHALLENGE
        elif self.active_mode_name == "duo":
            self.duo_mode.restart_level(now)
            self.state = config.STATE_DUO_WAITING
        else:
            self.start_single_mode(now)

    def pause_buttons_for_active_state(self) -> list[tuple[str, Button]]:
        if self.paused_state == config.STATE_PLAYING_SINGLE_CHALLENGE:
            return self.pause_challenge_buttons
        return self.pause_buttons

    def gameover_buttons_for_active_mode(self) -> list[tuple[str, Button]]:
        if self.active_mode_name == "duo":
            return self.gameover_duo_buttons
        if self.active_mode_name == "single_challenge":
            return self.gameover_challenge_buttons
        return self.gameover_buttons

    def _handle_coming_soon(
        self,
        result,
        cursor_pos: Optional[tuple[int, int]],
        mouse_pos: tuple[int, int],
        mouse_clicked: bool,
    ) -> None:
        for _, button in self.coming_soon_buttons:
            if self._button_clicked(button, result, cursor_pos, mouse_pos, mouse_clicked):
                if self.active_mode_name == "duo":
                    self.state = config.STATE_DUO_CONTROL_SELECT
                else:
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
            config.STATE_PLAYING_SINGLE_CHALLENGE,
            config.STATE_PLAYING_LEVEL,
            config.STATE_DUO_WAITING,
            config.STATE_PLAYING_DUO,
            config.STATE_PAUSED,
            config.STATE_GAMEOVER,
            config.STATE_DUO_GAMEOVER,
            config.STATE_LEVEL_CLEAR,
        }:
            self.ui.draw_world(draw_mode, draw_mode_name, now)

        sidebar_mode = self.active_mode
        sidebar_mode_name = draw_mode_name or self.active_mode_name
        if self.state == config.STATE_SINGLE_LEVEL_SELECT:
            sidebar_mode = None
            sidebar_mode_name = "single_challenge"
        elif self.state in {config.STATE_DUO_CONTROL_SELECT, config.STATE_DUO_LEVEL_SELECT}:
            sidebar_mode = None
            sidebar_mode_name = "duo"
        self.ui.draw_sidebar(
            result,
            sidebar_mode,
            sidebar_mode_name,
            now,
            self.current_sensitivity_label,
            self.vision.camera_ready,
        )

        if self.state == config.STATE_MENU:
            self.ui.draw_menu(self.menu_buttons, cursor_pos, mouse_pos)
        elif self.state == config.STATE_SINGLE_LEVEL_SELECT:
            self.ui.draw_single_level_select(
                self.single_level_buttons,
                self.single_level_select_buttons,
                cursor_pos,
                mouse_pos,
            )
        elif self.state == config.STATE_DUO_CONTROL_SELECT:
            self.ui.draw_duo_control_select(
                self.duo_control_buttons,
                self.duo_control_nav_buttons,
                cursor_pos,
                mouse_pos,
            )
        elif self.state == config.STATE_DUO_LEVEL_SELECT:
            self.ui.draw_duo_level_select(
                self.duo_level_buttons,
                self.duo_level_select_buttons,
                cursor_pos,
                mouse_pos,
            )
        elif self.state == config.STATE_PAUSED:
            self.ui.draw_pause()
            for _, button in self.pause_buttons_for_active_state():
                button.draw(self.screen, self.ui.font_button, self.ui.font_small, cursor_pos, mouse_pos)
        elif self.state in {config.STATE_GAMEOVER, config.STATE_DUO_GAMEOVER}:
            self.ui.draw_gameover(
                self.gameover_buttons_for_active_mode(),
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
        elif self.state == config.STATE_DUO_WAITING:
            self.ui.draw_small_notice("Waiting for both players...")
        elif self.state == config.STATE_PLAYING_DUO and self.duo_mode.status == "paused":
            self.ui.draw_overlay_panel("Duo Paused", [self.duo_mode.pause_reason], config.COLOR_WARNING)
        elif self.state == config.STATE_PLAYING_SINGLE and now < self.single_mode.invincible_until:
            self.ui.draw_small_notice("Spawn protection...")
        elif (
            self.state == config.STATE_PLAYING_SINGLE_CHALLENGE
            and now < self.single_challenge_mode.invincible_until
        ):
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
        if self.state == config.STATE_PLAYING_SINGLE_CHALLENGE:
            return "single_challenge"
        if self.state in {config.STATE_DUO_WAITING, config.STATE_PLAYING_DUO, config.STATE_DUO_GAMEOVER}:
            return "duo"
        if self.state in {config.STATE_PLAYING_LEVEL, config.STATE_LEVEL_CLEAR}:
            return "level"
        if self.state in {config.STATE_PAUSED, config.STATE_GAMEOVER}:
            return self.active_mode_name
        return None
