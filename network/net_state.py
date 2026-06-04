from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pygame

import config
from entities import Food
from utils import clamp
from vision import DuoPlayerVision, DuoVisionResult


@dataclass(frozen=True)
class NetworkInput:
    player_id: int
    detected: bool = False
    target_x: float = 0.5
    target_y: float = 0.5
    pinch_clicked: bool = False
    peace_gesture: bool = False
    timestamp: float = 0.0
    seq: int = 0

    @classmethod
    def from_message(cls, data: dict[str, Any]) -> Optional["NetworkInput"]:
        try:
            player_id = int(data.get("player_id", 0))
        except (TypeError, ValueError):
            return None
        if player_id not in {1, 2}:
            return None
        try:
            target_x = float(data.get("target_x", 0.5))
            target_y = float(data.get("target_y", 0.5))
            timestamp = float(data.get("timestamp", 0.0))
            seq = int(data.get("seq", 0))
        except (TypeError, ValueError):
            return None
        return cls(
            player_id=player_id,
            detected=bool(data.get("detected", False)),
            target_x=round(clamp(target_x, 0.0, 1.0), 6),
            target_y=round(clamp(target_y, 0.0, 1.0), 6),
            pinch_clicked=bool(data.get("pinch_clicked", False)),
            peace_gesture=bool(data.get("peace_gesture", False)),
            timestamp=timestamp,
            seq=seq,
        )


def default_inputs() -> dict[int, NetworkInput]:
    return {
        1: NetworkInput(player_id=1),
        2: NetworkInput(player_id=2),
    }


def inputs_to_duo_result(inputs: dict[int, NetworkInput]) -> DuoVisionResult:
    first = inputs.get(1, NetworkInput(player_id=1))
    second = inputs.get(2, NetworkInput(player_id=2))
    return DuoVisionResult(
        left=_player_vision(first),
        right=_player_vision(second),
        pause_reason=_pause_reason(first, second),
    )


def serialize_duo_mode(
    mode,
    tick: int,
    phase: str,
    map_id: int = 0,
    message: str = "",
) -> dict[str, Any]:
    winner = _winner_for(mode.winner)
    state = {
        "type": "state",
        "tick": tick,
        "phase": phase,
        "status": str(getattr(mode, "status", phase)),
        "time_left": round(float(mode.remaining_seconds), 3),
        "map_id": map_id,
        "snakes": {
            "1": _snake_state(mode.green, phase, winner),
            "2": _snake_state(mode.blue, phase, winner),
        },
        "foods": [_food_state(mode.normal_food, "normal")] if getattr(mode, "normal_food", None) else [],
        "big_food": _food_state(mode.big_food, "big") if getattr(mode, "big_food", None) else None,
        "winner": winner,
        "message": message,
        "summary": _summary_state(mode),
    }
    return state


def _summary_state(mode) -> dict[str, Any]:
    summary = getattr(mode, "summary", None)
    apples_eaten = int(getattr(mode, "apples_eaten", 0))
    if summary is None:
        return {
            "time": "0:00",
            "apples": apples_eaten,
            "big_apples": 0,
            "max_speed": 0,
            "tracking": "0%",
        }
    return summary.as_payload(apples_eaten)


def _player_vision(network_input: NetworkInput) -> DuoPlayerVision:
    point = (network_input.target_x, network_input.target_y) if network_input.detected else None
    return DuoPlayerVision(
        detected=network_input.detected,
        index_tip_norm=point,
        raw_index_tip_norm=point,
        pinch_clicked=network_input.pinch_clicked,
    )


def _pause_reason(first: NetworkInput, second: NetworkInput) -> str:
    if not first.detected:
        return "Player 1 hand lost"
    if not second.detected:
        return "Player 2 hand lost"
    return ""


def _snake_state(player, phase: str, winner: Optional[str]) -> dict[str, Any]:
    player_id = "1" if player.key == "green" else "2"
    alive = phase != "gameover" or winner in {None, "draw", player_id}
    return {
        "alive": alive,
        "score": int(player.score),
        "head": _point(player.snake.head_pos),
        "body": [_point(part) for part in player.snake.body],
        "color": player.key,
    }


def _food_state(food: Food, kind: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "pos": _point(food.position),
        "score": int(food.score),
        "growth": int(food.growth),
        "radius": int(food.radius),
    }


def _winner_for(mode_winner: str) -> Optional[str]:
    if mode_winner == "green":
        return "1"
    if mode_winner == "blue":
        return "2"
    if mode_winner == "draw":
        return "draw"
    return None


def _point(point: pygame.Vector2) -> list[int]:
    return [int(round(point.x)), int(round(point.y))]
