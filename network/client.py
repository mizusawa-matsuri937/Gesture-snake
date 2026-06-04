from __future__ import annotations

import socket
import threading
import time
from typing import Any, Optional

import config
from network.protocol import decode_messages, encode_message


class GameClient:
    def __init__(
        self,
        host: str,
        port: int = config.LAN_DEFAULT_PORT,
        player_name: str = "Player",
        timeout: float = config.LAN_CONNECT_TIMEOUT,
    ):
        self.host = host
        self.port = port
        self.player_name = player_name
        self.timeout = timeout
        self.player_id: Optional[int] = None
        self.error_message = ""
        self.connected = False
        self._sock: Optional[socket.socket] = None
        self._recv_thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._send_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._latest_state: Optional[dict[str, Any]] = None
        self._seq = 0

    def connect(self) -> bool:
        if self.connected:
            return True
        self.error_message = ""
        self._stop.clear()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.host, self.port))
            sock.sendall(
                encode_message(
                    {
                        "type": "hello",
                        "player_name": self.player_name,
                        "version": config.LAN_PROTOCOL_VERSION,
                    }
                )
            )
            if not self._wait_for_welcome(sock):
                sock.close()
                return False
        except OSError as exc:
            self.error_message = str(exc)
            try:
                sock.close()
            except OSError:
                pass
            return False

        sock.settimeout(0.2)
        self._sock = sock
        self.connected = True
        self._recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._recv_thread.start()
        return True

    def disconnect(self) -> None:
        self._stop.set()
        sock = self._sock
        if sock is not None:
            try:
                if self.connected:
                    sock.sendall(encode_message({"type": "disconnect"}))
            except OSError:
                pass
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        self.connected = False
        self._sock = None
        if self._recv_thread and self._recv_thread.is_alive() and threading.current_thread() is not self._recv_thread:
            self._recv_thread.join(timeout=0.4)
        self._recv_thread = None

    def send_input(
        self,
        detected: bool,
        target_x: float = 0.5,
        target_y: float = 0.5,
        pinch_clicked: bool = False,
        peace_gesture: bool = False,
        timestamp: Optional[float] = None,
        seq: Optional[int] = None,
    ) -> bool:
        if seq is None:
            self._seq += 1
            seq = self._seq
        return self._send(
            {
                "type": "input",
                "player_id": self.player_id or 0,
                "detected": bool(detected),
                "target_x": float(target_x),
                "target_y": float(target_y),
                "pinch_clicked": bool(pinch_clicked),
                "peace_gesture": bool(peace_gesture),
                "timestamp": time.monotonic() if timestamp is None else float(timestamp),
                "seq": int(seq),
            }
        )

    def send_start_match(self, map_id: int = 0) -> bool:
        return self._send({"type": "start_match", "map_id": int(map_id)})

    def get_latest_state(self) -> Optional[dict[str, Any]]:
        with self._state_lock:
            return dict(self._latest_state) if self._latest_state is not None else None

    def get_connection_status(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "player_id": self.player_id,
            "error_message": self.error_message,
        }

    def _wait_for_welcome(self, sock: socket.socket) -> bool:
        buffer = b""
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            try:
                chunk = sock.recv(8192)
            except socket.timeout:
                continue
            if not chunk:
                self.error_message = "Connection closed"
                return False
            messages, buffer = decode_messages(buffer + chunk)
            for message in messages:
                if message.get("type") == "welcome":
                    self.player_id = int(message["player_id"])
                    return True
                if message.get("type") == "error":
                    self.error_message = str(message.get("message", "Connection error"))
                    return False
                self._handle_message(message)
        self.error_message = "Connection timed out"
        return False

    def _recv_loop(self) -> None:
        buffer = b""
        while not self._stop.is_set():
            sock = self._sock
            if sock is None:
                break
            try:
                chunk = sock.recv(8192)
            except socket.timeout:
                continue
            except OSError as exc:
                self.error_message = str(exc)
                break
            if not chunk:
                self.error_message = "Connection Lost"
                break
            messages, buffer = decode_messages(buffer + chunk)
            for message in messages:
                self._handle_message(message)
        self.connected = False

    def _handle_message(self, message: dict[str, Any]) -> None:
        message_type = message.get("type")
        if message_type == "state":
            with self._state_lock:
                self._latest_state = dict(message)
        elif message_type == "error":
            self.error_message = str(message.get("message", "Connection error"))
            self.connected = False
        elif message_type == "ping":
            self._send({"type": "pong", "timestamp": message.get("timestamp", time.monotonic())})

    def _send(self, message: dict[str, Any]) -> bool:
        if not self.connected or self._sock is None:
            return False
        try:
            payload = encode_message(message)
            with self._send_lock:
                self._sock.sendall(payload)
            return True
        except OSError as exc:
            self.error_message = str(exc)
            self.connected = False
            return False
