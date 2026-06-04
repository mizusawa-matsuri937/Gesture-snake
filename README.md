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
- `Duo Mode` also includes `LAN Battle`, a first local-network TCP battle mode for two computers.
- `Level Mode` keeps target scores, a horizontal target progress bar, Level Clear, moving walls, portals, and timed big apples.
- Game Over screens show a post-game performance dashboard with score/result, apples, big apples, active time, max speed, and gesture tracking stability.

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
| LAN Battle Host Game | Start a local TCP server as Player 1 |
| LAN Battle Join Game | Connect to the host IP as Player 2 |
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
- `LAN Battle`: playable first-version local network battle.

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

### LAN Battle

`LAN Battle` is available from `Duo Mode` -> `LAN Battle`. It is a first-version TCP mode for two computers on the same local network. The host computer runs the authoritative game server and also connects as Player 1. The joining computer connects to the host IP as Player 2.

How to play:

1. On computer A, open `Duo Mode` -> `LAN Battle` -> `Host Game`.
2. Share the displayed IP and port with computer B.
3. On computer B, open `Duo Mode` -> `LAN Battle` -> `Join Game`.
4. Type the host IP, press `Enter` or click `Connect`, then wait for the host.
5. On computer A, click `Start Match` after Player 2 connects.

LAN Battle uses the Classic map in this version. Each computer uses its own camera and MediaPipe hand tracking locally. The network only sends a small gesture input summary: detected hand state, normalized index-finger target, click gesture, restart gesture, timestamp, and sequence number. Camera video and full MediaPipe landmarks are not sent.

Default port: `50007`.

If Join fails, check that both computers are on the same LAN, the IP is correct, the port is not blocked, and Windows Firewall allows Python. You can also use `ipconfig` on the host to confirm the local IPv4 address.

Current LAN Battle limits:

- Local network TCP only.
- No public internet matchmaking or NAT traversal.
- Classic map only.
- No rematch button in the first version.
- A real two-computer test is still recommended after automated localhost tests pass.

### Post-game Dashboard

Every Game Over screen includes a performance summary for the just-finished run:

- Single, Endless Challenge, and Level Mode show score, apples, big apples, active time, max speed, and hand tracking stability.
- Shared-camera Duo and LAN Battle show the result, shared apple totals, active time, max speed, and overall two-player tracking stability.
- Tracking stability is measured only during active play: single-player modes count frames with a detected hand, while two-player modes count frames where both players are ready.

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
summary.py                # Post-game performance tracking
modes/
  single_mode.py          # Classic endless mode logic
  endless_challenge_mode.py
  duo_mode.py               # Shared-camera two-player battle mode
  lan_duo_mode.py         # LAN TCP two-computer battle flow
  obstacle_helpers.py     # Shared wall, portal, and safe food helpers
  level_mode.py           # Target-based level mode
network/
  protocol.py             # JSON Lines message framing
  net_state.py            # Network input and state serialization helpers
  server.py               # Authoritative LAN GameServer
  client.py               # LAN GameClient
tools/capture_ui_states.py
test_snake.py
```

## Tests

Compile check:

```bash
.\.venv\Scripts\python.exe -m py_compile snake.py game.py vision.py ui.py entities.py utils.py config.py summary.py modes/single_mode.py modes/endless_challenge_mode.py modes/duo_mode.py modes/lan_duo_mode.py modes/obstacle_helpers.py modes/level_mode.py network/protocol.py network/server.py network/client.py network/net_state.py tools/capture_ui_states.py
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
