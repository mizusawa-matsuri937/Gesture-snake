from __future__ import annotations


class PerformanceTracker:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.control_seconds = 0.0
        self.tracking_seconds = 0.0
        self.big_apples_eaten = 0
        self.max_speed = 0

    def record_frame(self, dt: float, tracking_ok: bool, speed: int) -> None:
        if dt <= 0:
            return
        self.control_seconds += dt
        if tracking_ok:
            self.tracking_seconds += dt
        self.max_speed = max(self.max_speed, int(speed))

    def record_big_apple(self) -> None:
        self.big_apples_eaten += 1

    def elapsed_label(self) -> str:
        total_seconds = max(0, int(self.control_seconds))
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        return f"{minutes}:{seconds:02d}"

    def stability_label(self) -> str:
        if self.control_seconds <= 0:
            return "0%"
        ratio = max(0.0, min(1.0, self.tracking_seconds / self.control_seconds))
        return f"{int(round(ratio * 100))}%"

    def as_payload(self, apples_eaten: int) -> dict[str, int | str]:
        return {
            "time": self.elapsed_label(),
            "apples": int(apples_eaten),
            "big_apples": int(self.big_apples_eaten),
            "max_speed": int(self.max_speed),
            "tracking": self.stability_label(),
        }
