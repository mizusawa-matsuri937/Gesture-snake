# Codex Project Instructions

## Project Summary

Gesture Snake is a Python pygame game controlled by MediaPipe hand gestures. The current codebase is split into focused modules:

- `snake.py`: entry point.
- `game.py`: pygame setup, main loop, state machine, mode switching.
- `ui.py`: all visible UI drawing and buttons.
- `vision.py`: camera capture, MediaPipe hand tracking, gesture triggers.
- `entities.py`: snake, food, walls, moving walls, portals.
- `summary.py`: post-game performance tracking.
- `modes/single_mode.py`: classic endless logic.
- `modes/endless_challenge_mode.py`: selectable endless challenge maps.
- `modes/duo_mode.py`: shared-camera two-player battle mode.
- `modes/lan_duo_mode.py`: local-network TCP two-computer battle flow.
- `modes/level_mode.py`: target-based level mode.
- `modes/obstacle_helpers.py`: shared wall, portal, layout, and safe food helpers.
- `network/`: JSON Lines protocol, LAN GameServer/GameClient, and network state serialization.

## User Preferences

- Communicate with the user in Chinese unless they ask otherwise.
- Keep all visible in-game UI text in English.
- Preserve the user's local edits. Always inspect `git status --short` and relevant diffs before changing or committing files.
- Do not revert or overwrite user-tuned gameplay values unless explicitly requested.
- If a task changes gameplay or UI behavior, implement tests first when practical.
- After completing requested project changes, run verification, commit, and push to `origin/main` when the user asks to submit or when that pattern is clearly implied by the request history.

## Gameplay Invariants

- `Single Player` opens the `Endless Challenges` select screen.
- Endless challenge levels have no target score, no target progress bar, and no Level Clear.
- Endless challenge levels keep boundary wrapping enabled.
- In endless challenges, static walls and moving walls are deadly, self-collision is deadly after spawn protection, and portals teleport the snake head.
- `Level Mode` remains target-based and keeps the horizontal target progress bar plus Level Clear.
- Big apples appear every 5 normal apples where supported. Preserve the configured `BIG_FOOD_DURATION`.
- Map design should stay visually balanced. Level 2 and later should preserve left-right symmetry where practical.
- Food and big food must avoid walls, moving-wall tracks, portals, snake body, and obvious dead ends.

## UI Rules

- Every visible UI state must be readable at the default windowed size and fullscreen size.
- Avoid text overlap, clipped buttons, or sidebar text running outside the sidebar.
- Use vertical spacing for overlays; title, subtitle, stats, hints, and buttons must not share the same y-space.
- For UI changes, update `tools/capture_ui_states.py` so every new state can be rendered.
- Generate screenshots with:

```bash
.\.venv\Scripts\python.exe tools\capture_ui_states.py --out artifacts\ui-screenshots
```

- Inspect the generated screenshots before claiming UI work is complete.
- Do not commit `artifacts/` screenshots.

## Verification Commands

Run these before committing project changes:

```bash
.\.venv\Scripts\python.exe -m py_compile snake.py game.py vision.py ui.py entities.py utils.py config.py summary.py modes/single_mode.py modes/endless_challenge_mode.py modes/duo_mode.py modes/lan_duo_mode.py modes/obstacle_helpers.py modes/level_mode.py network/protocol.py network/server.py network/client.py network/net_state.py tools/capture_ui_states.py
.\.venv\Scripts\python.exe -m unittest discover
```

For UI/layout changes, also run the screenshot command above and inspect the images.

## Git Notes

- Remote: `origin = https://github.com/mizusawa-matsuri937/Gesture-snake.git`
- Main branch: `main`
- Use scoped safe-directory commands if Git reports dubious ownership:

```bash
git -c safe.directory=D:/Gesture-controlled-snake-game-main status --short
```

- Do not commit `.venv/`, `__pycache__/`, `.pyc`, `.pyo`, `.pytest_cache/`, or `artifacts/`.
- Preferred commit messages:
  - `feat: ...` for gameplay or mode features.
  - `style: ...` for UI-only visual changes.
  - `docs: ...` for documentation or agent instruction changes.

## Documentation

- Keep `README.md` and `开发日志.md` in sync when gameplay, controls, modes, or test workflow change.
- Keep documentation concise and readable. English is acceptable for project docs.
