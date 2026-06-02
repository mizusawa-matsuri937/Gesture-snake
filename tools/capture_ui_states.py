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
from vision import VisionResult


REQUIRED_STATES = [
    "menu",
    "options",
    "coming_soon",
    "playing_single",
    "playing_level",
    "paused_single",
    "paused_level",
    "gameover_single",
    "gameover_level",
    "level_clear",
]


def capture_ui_states(output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    config.configure_layout(config.WINDOWED_SIZE)
    game = Game(fullscreen=False, use_camera=False)
    result = VisionResult(detected=False)
    mouse_pos = (0, 0)
    now = 8.0
    captures: dict[str, Path] = {}

    state_setup = {
        "menu": lambda: _set_state(game, config.STATE_MENU, "single"),
        "options": lambda: _set_state(game, config.STATE_OPTIONS, "single"),
        "coming_soon": lambda: _set_state(game, config.STATE_COMING_SOON, "single"),
        "playing_single": lambda: _set_state(game, config.STATE_PLAYING_SINGLE, "single"),
        "playing_level": lambda: _set_state(game, config.STATE_PLAYING_LEVEL, "level"),
        "paused_single": lambda: _set_paused(game, config.STATE_PLAYING_SINGLE, "single"),
        "paused_level": lambda: _set_paused(game, config.STATE_PLAYING_LEVEL, "level"),
        "gameover_single": lambda: _set_gameover_single(game),
        "gameover_level": lambda: _set_gameover_level(game),
        "level_clear": lambda: _set_level_clear(game),
    }

    for state in REQUIRED_STATES:
        state_setup[state]()
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


def _set_gameover_level(game: Game) -> None:
    game.level_mode.level_index = 2
    game.level_mode.level_score = 60
    game.level_mode.total_score = 180
    game.state = config.STATE_GAMEOVER
    game.active_mode_name = "level"


def _set_level_clear(game: Game) -> None:
    game.level_mode.level_index = 1
    game.level_mode.level_score = game.level_mode.target_score
    game.level_mode.total_score = 130
    game.level_mode.clear_started_at = 8.0
    game.state = config.STATE_LEVEL_CLEAR
    game.active_mode_name = "level"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("artifacts/ui-screenshots"))
    args = parser.parse_args()
    captures = capture_ui_states(args.out)
    for state, path in captures.items():
        print(f"{state}: {path}")


if __name__ == "__main__":
    main()
