from __future__ import annotations

import json
from typing import Any


def encode_message(data: dict[str, Any]) -> bytes:
    if not isinstance(data, dict):
        raise TypeError("network messages must be dictionaries")
    return (json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")


def decode_messages(buffer: bytes) -> tuple[list[dict[str, Any]], bytes]:
    messages: list[dict[str, Any]] = []
    remaining = buffer
    while b"\n" in remaining:
        line, remaining = remaining.split(b"\n", 1)
        if not line.strip():
            continue
        try:
            decoded = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(decoded, dict):
            messages.append(decoded)
    return messages, remaining
