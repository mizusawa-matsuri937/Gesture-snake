# Gesture Snake

Gesture Snake is a Python, pygame, OpenCV, and MediaPipe game where the snake follows your index finger. The snake moves smoothly toward the detected fingertip target instead of snapping instantly, which keeps control stable when the hand shakes or moves quickly.

## Features

- Fullscreen English UI by default, with `F11` to toggle windowed mode.
- Widescreen camera capture request and uncropped sidebar preview.
- Pinch gesture for clicking menu and overlay buttons.
- Peace gesture to restart after Game Over.
- Single-hand lock, so the first detected hand keeps control.
- `Single Player` opens `Endless Challenges`, a five-card level-select screen.
- Endless challenges reuse the five level maps but do not use target scores, target bars, or Level Clear.
- Classic endless play and Endless Challenges wrap at map edges as soon as the snake head reaches the boundary.
- `Duo Mode` supports a shared-camera battle where the left half controls the green snake and the right half controls the blue snake.
- `Level Mode` keeps target scores, a horizontal target progress bar, Level Clear, moving walls, portals, and timed big apples.

## Run

Install dependencies:

```bash
pip install -r requirements.txt
```

Run with the project virtual environment on Windows:

```bash
.\.venv\Scripts\python.exe snake.py
```

Or run with a system Python 3 interpreter:

```bash
python snake.py
```

Press `ESC` to quit.

## Controls

| Action | Effect |
| --- | --- |
| Move index finger | Move the snake target |
| Pinch index finger and thumb | Click buttons |
| Peace gesture on Game Over | Restart the current mode |
| Mouse click | Fallback button input |
| `Options` | Change gesture sensitivity |
| Shared camera left half | Control the green snake in Duo Mode |
| Shared camera right half | Control the blue snake in Duo Mode |
| `F11` | Toggle fullscreen/windowed |
| `ESC` | Quit |

## Modes

### Endless Challenges

Click `Single Player` to open `Endless Challenges`. The five selectable endless challenges are:

1. `Classic`: no obstacles, wrapping edges.
2. `Symmetry`: centered wall layout, wrapping edges.
3. `Moving Walls`: symmetric moving walls, wrapping edges.
4. `Portals`: paired portals, wrapping edges.
5. `Mixed`: walls, moving walls, and portals, wrapping edges.

Endless challenges use the single-player scoring and speed rules:

- Normal apple: +10 score, +1 growth.
- Big apple: appears every 5 normal apples, +30 score, +3 growth.
- Big apple duration: controlled by `BIG_FOOD_DURATION` in `config.py`.
- Base speed: 180 px/s.
- Speed gain: +8 px/s per normal apple.
- Max speed: 420 px/s.

There is no target score, no target progress bar, and no Level Clear in endless challenges. Static walls and moving walls are deadly, self-collision is deadly after spawn protection, portals teleport the snake head, and map edges still wrap from the opposite side when the snake head reaches the boundary.

### Duo Mode

`Duo Mode` starts with a control setup screen:

- `Shared Camera`: playable in this version.
- `Separate Cameras`: visible as Coming Soon.

Shared camera battles use the same five endless maps. The camera preview is split into left and right halves:

- Left half controls the green snake.
- Right half controls the blue snake.
- Both players must be detected in their own half for 0.5 seconds before the match starts.
- Tracking loss or a finger crossing the center line pauses the match and freezes the timer.
- Duo sensitivity is fixed at x8.

Duo battle rules:

- Match time: 3 minutes of active play.
- Shared normal apples and big apples use the endless scoring and growth rules.
- Big apples appear every 5 normal apples eaten by either player.
- Map edges wrap, portals teleport, and portal cooldowns are tracked per snake.
- Walls, moving walls, self-collision, opponent body collision, and head-on collisions are deadly.
- A snake death subtracts 100 points and immediately ends the match.
- Head-on collision subtracts 100 points from both players.
- Highest score wins; tied scores show Draw.

### Level Mode

`Level Mode` is the staged progression mode:

- Level targets: 100 / 150 / 200 / 300 / 500.
- The sidebar shows a horizontal target progress bar.
- Boundary collision, wall collision, moving-wall collision, and self-collision cause Game Over.
- Big apples appear every 5 normal apples.
- Level Clear starts automatically after the target score is reached.

## Project Structure

```text
snake.py                  # Entry point
config.py                 # Layout, colors, speeds, states, level data
utils.py                  # Font, geometry, mapping, wrapping helpers
vision.py                 # Camera and MediaPipe gesture input
entities.py               # Snake, Food, Wall, MovingWall, PortalPair
ui.py                     # Drawing and buttons
game.py                   # Main loop and state machine
modes/
  single_mode.py          # Classic endless mode logic
  endless_challenge_mode.py
  duo_mode.py               # Shared-camera two-player battle mode
  obstacle_helpers.py     # Shared wall, portal, and safe food helpers
  level_mode.py           # Target-based level mode
tools/capture_ui_states.py
test_snake.py
```

## Tests

Compile check:

```bash
.\.venv\Scripts\python.exe -m py_compile snake.py game.py vision.py ui.py entities.py utils.py config.py modes/single_mode.py modes/endless_challenge_mode.py modes/obstacle_helpers.py modes/level_mode.py tools/capture_ui_states.py
```

Unit tests:

```bash
.\.venv\Scripts\python.exe -m unittest discover
```

Generate UI screenshots:

```bash
.\.venv\Scripts\python.exe tools\capture_ui_states.py --out artifacts\ui-screenshots
```

Generated screenshots are for visual QA and are not meant to be committed.
