from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pygame

import config
from game import Game
from vision import DuoPlayerVision, DuoVisionResult, VisionResult


REQUIRED_STATES = [
    "menu",
    "options",
    "coming_soon",
    "single_level_select",
    "playing_single",
    "single_challenge_level_1",
    "single_challenge_level_3",
    "single_challenge_level_4",
    "single_challenge_level_5",
    "playing_level",
    "level_big_apple",
    "level_3_moving_walls",
    "level_4_portals",
    "level_5_mixed",
    "paused_single",
    "paused_single_challenge",
    "paused_level",
    "gameover_single",
    "gameover_single_challenge",
    "gameover_level",
    "level_clear",
    "duo_control_select",
    "duo_level_select",
    "duo_waiting",
    "duo_playing",
    "duo_paused",
    "duo_gameover",
    "duo_separate_coming_soon",
]


def capture_ui_states(output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    config.configure_layout(config.WINDOWED_SIZE)
    game = Game(fullscreen=False, use_camera=False)
    mouse_pos = (0, 0)
    now = 8.0
    captures: dict[str, Path] = {}

    state_setup = {
        "menu": lambda: _set_state(game, config.STATE_MENU, "single"),
        "options": lambda: _set_state(game, config.STATE_OPTIONS, "single"),
        "coming_soon": lambda: _set_state(game, config.STATE_COMING_SOON, "single"),
        "single_level_select": lambda: _set_state(game, config.STATE_SINGLE_LEVEL_SELECT, "single"),
        "playing_single": lambda: _set_state(game, config.STATE_PLAYING_SINGLE, "single"),
        "single_challenge_level_1": lambda: _set_single_challenge_stage(game, 0, now),
        "single_challenge_level_3": lambda: _set_single_challenge_stage(game, 2, now),
        "single_challenge_level_4": lambda: _set_single_challenge_stage(game, 3, now),
        "single_challenge_level_5": lambda: _set_single_challenge_stage(game, 4, now),
        "playing_level": lambda: _set_playing_level(game),
        "level_big_apple": lambda: _set_level_big_apple(game, now),
        "level_3_moving_walls": lambda: _set_level_stage(game, 2, 80, 180, now),
        "level_4_portals": lambda: _set_level_stage(game, 3, 120, 300, now),
        "level_5_mixed": lambda: _set_level_stage(game, 4, 250, 620, now),
        "paused_single": lambda: _set_paused(game, config.STATE_PLAYING_SINGLE, "single"),
        "paused_single_challenge": lambda: _set_paused(
            game, config.STATE_PLAYING_SINGLE_CHALLENGE, "single_challenge"
        ),
        "paused_level": lambda: _set_paused(game, config.STATE_PLAYING_LEVEL, "level"),
        "gameover_single": lambda: _set_gameover_single(game),
        "gameover_single_challenge": lambda: _set_gameover_single_challenge(game),
        "gameover_level": lambda: _set_gameover_level(game),
        "level_clear": lambda: _set_level_clear(game),
        "duo_control_select": lambda: _set_state(game, config.STATE_DUO_CONTROL_SELECT, "duo"),
        "duo_level_select": lambda: _set_state(game, config.STATE_DUO_LEVEL_SELECT, "duo"),
        "duo_waiting": lambda: _set_duo_waiting(game, now),
        "duo_playing": lambda: _set_duo_playing(game, now),
        "duo_paused": lambda: _set_duo_paused(game, now),
        "duo_gameover": lambda: _set_duo_gameover(game, now),
        "duo_separate_coming_soon": lambda: _set_state(game, config.STATE_COMING_SOON, "duo"),
    }

    for state in REQUIRED_STATES:
        state_setup[state]()
        result = _result_for_state(state)
        game.draw(result, None, mouse_pos, now)
        path = output_dir / f"{state}.png"
        pygame.image.save(game.screen, str(path))
        captures[state] = path

    game.vision.release()
    pygame.quit()
    return captures


def _set_state(game: Game, state: str, mode_name: str) -> None:
    game.state = state
    game.active_mode_name = mode_name
    game.pause_reason = None


def _set_paused(game: Game, paused_state: str, mode_name: str) -> None:
    game.state = config.STATE_PAUSED
    game.active_mode_name = mode_name
    game.paused_state = paused_state
    game.pause_reason = "tracking"


def _set_gameover_single(game: Game) -> None:
    game.single_mode.score = 120
    game.single_mode.apples_eaten = 12
    game.state = config.STATE_GAMEOVER
    game.active_mode_name = "single"


def _set_playing_level(game: Game) -> None:
    _set_level_stage(game, 0, 50, 50, 8.0)


def _set_single_challenge_stage(game: Game, level_index: int, now: float) -> None:
    game.single_challenge_mode.select_level(level_index, now)
    game.single_challenge_mode.score = (level_index + 1) * 40
    game.single_challenge_mode.apples_eaten = level_index + 2
    game.single_challenge_mode.update_moving_walls(now)
    game.state = config.STATE_PLAYING_SINGLE_CHALLENGE
    game.active_mode_name = "single_challenge"
    game.pause_reason = None


def _set_level_stage(game: Game, level_index: int, level_score: int, total_score: int, now: float) -> None:
    game.level_mode.level_index = level_index
    game.level_mode.total_score = total_score
    game.level_mode.reset_level(now, keep_total=True)
    game.level_mode.level_score = level_score
    game.level_mode.total_score = total_score
    game.level_mode.update_moving_walls(now)
    game.state = config.STATE_PLAYING_LEVEL
    game.active_mode_name = "level"
    game.pause_reason = None


def _set_level_big_apple(game: Game, now: float) -> None:
    _set_level_stage(game, 0, 40, 40, now)
    game.level_mode.spawn_big_food(now - 1.0)
    game.level_mode.big_food.position = game.level_mode.snake.head_pos + pygame.Vector2(150, -120)


def _set_gameover_level(game: Game) -> None:
    _set_level_stage(game, 2, 60, 180, 8.0)
    game.level_mode.level_score = 60
    game.level_mode.total_score = 180
    game.state = config.STATE_GAMEOVER
    game.active_mode_name = "level"


def _set_gameover_single_challenge(game: Game) -> None:
    _set_single_challenge_stage(game, 4, 8.0)
    game.single_challenge_mode.score = 210
    game.single_challenge_mode.apples_eaten = 15
    game.state = config.STATE_GAMEOVER
    game.active_mode_name = "single_challenge"


def _set_level_clear(game: Game) -> None:
    _set_level_stage(game, 1, 0, 130, 8.0)
    game.level_mode.level_score = game.level_mode.target_score
    game.level_mode.total_score = 130
    game.level_mode.clear_started_at = 8.0
    game.state = config.STATE_LEVEL_CLEAR
    game.active_mode_name = "level"


def _duo_result(ready: bool = True) -> DuoVisionResult:
    if not ready:
        return DuoVisionResult(pause_reason="Right hand lost")
    return DuoVisionResult(
        left=DuoPlayerVision(detected=True, index_tip_norm=(0.35, 0.5), raw_index_tip_norm=(0.175, 0.5)),
        right=DuoPlayerVision(detected=True, index_tip_norm=(0.65, 0.5), raw_index_tip_norm=(0.825, 0.5)),
    )


def _result_for_state(state: str):
    if not state.startswith("duo"):
        return VisionResult(detected=False)
    if state == "duo_paused":
        return _duo_result(ready=False)
    if state in {"duo_waiting", "duo_playing", "duo_gameover"}:
        return _duo_result()
    return DuoVisionResult(pause_reason="Waiting for players")


def _set_duo_waiting(game: Game, now: float) -> None:
    game.duo_mode.select_level(0, now)
    game.duo_mode.pause_reason = "Waiting for both players"
    game.state = config.STATE_DUO_WAITING
    game.active_mode_name = "duo"


def _set_duo_playing(game: Game, now: float) -> None:
    game.duo_mode.select_level(2, now)
    game.duo_mode.started = True
    game.duo_mode.status = "playing"
    game.duo_mode.pause_reason = ""
    game.duo_mode.elapsed_seconds = 45.0
    game.duo_mode.green.score = 80
    game.duo_mode.blue.score = 60
    game.duo_mode.update_moving_walls(now)
    game.state = config.STATE_PLAYING_DUO
    game.active_mode_name = "duo"


def _set_duo_paused(game: Game, now: float) -> None:
    _set_duo_playing(game, now)
    game.duo_mode.status = "paused"
    game.duo_mode.pause_reason = "Right hand lost"


def _set_duo_gameover(game: Game, now: float) -> None:
    _set_duo_playing(game, now)
    game.duo_mode.green.score = 120
    game.duo_mode.blue.score = 90
    game.duo_mode.finish(())
    game.state = config.STATE_DUO_GAMEOVER
    game.active_mode_name = "duo"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts/ui-screenshots"))
    args = parser.parse_args()
    captures = capture_ui_states(args.out)
    for state, path in captures.items():
        print(f"{state}: {path}")


if __name__ == "__main__":
    main()
