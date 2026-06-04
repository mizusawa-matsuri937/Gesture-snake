from __future__ import annotations

from dataclasses import dataclass, field
import ipaddress
import socket
import threading
import time
from typing import Any, Optional

import config
from modes.duo_mode import DuoMode
from network.net_state import NetworkInput, default_inputs, inputs_to_duo_result, serialize_duo_mode
from network.protocol import decode_messages, encode_message


@dataclass
class _ClientPeer:
    player_id: int
    sock: socket.socket
    address: tuple[str, int]
    send_lock: threading.Lock = field(default_factory=threading.Lock)

    def send(self, data: dict[str, Any]) -> bool:
        try:
            payload = encode_message(data)
            with self.send_lock:
                self.sock.sendall(payload)
            return True
        except OSError:
            return False

    def close(self) -> None:
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class GameServer:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = config.LAN_DEFAULT_PORT,
        tick_rate: int = config.LAN_TICK_RATE,
        state_rate: int = config.LAN_STATE_RATE,
    ):
        self.host = host
        self.port = port
        self.tick_rate = tick_rate
        self.state_rate = state_rate
        self.running = False
        self.phase = "waiting"
        self.message = "Waiting for Player 2"
        self.tick = 0
        self.mode = DuoMode(level_index=0)
        self.latest_inputs = default_inputs()
        self._lock = threading.Lock()
        self._server_sock: Optional[socket.socket] = None
        self._clients: dict[int, _ClientPeer] = {}
        self._accept_thread: Optional[threading.Thread] = None
        self._game_thread: Optional[threading.Thread] = None
        self._client_threads: list[threading.Thread] = []

    def start(self) -> None:
        if self.running:
            return
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_sock.bind((self.host, self.port))
        server_sock.listen(4)
        server_sock.settimeout(0.2)
        self.port = int(server_sock.getsockname()[1])
        self._server_sock = server_sock
        self.running = True
        self._accept_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._game_thread = threading.Thread(target=self._game_loop, daemon=True)
        self._accept_thread.start()
        self._game_thread.start()

    def stop(self) -> None:
        self.running = False
        if self._server_sock is not None:
            try:
                self._server_sock.close()
            except OSError:
                pass
            self._server_sock = None
        with self._lock:
            peers = list(self._clients.values())
            self._clients.clear()
        for peer in peers:
            peer.close()
        for thread in (self._accept_thread, self._game_thread):
            if thread and thread.is_alive():
                thread.join(timeout=0.5)
        for thread in list(self._client_threads):
            if thread.is_alive():
                thread.join(timeout=0.2)
        self._accept_thread = None
        self._game_thread = None
        self._client_threads = []

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": self.running,
                "phase": self.phase,
                "player_count": len(self._clients),
                "players": sorted(self._clients),
                "host": self.host,
                "port": self.port,
                "message": self.message,
            }

    def get_latest_inputs(self) -> dict[int, NetworkInput]:
        with self._lock:
            return dict(self.latest_inputs)

    def record_input(self, data: dict[str, Any]) -> None:
        parsed = NetworkInput.from_message(data)
        if parsed is None:
            return
        with self._lock:
            current = self.latest_inputs.get(parsed.player_id)
            if current is None or parsed.seq >= current.seq:
                self.latest_inputs[parsed.player_id] = parsed

    def start_match(self, map_id: int = 0) -> None:
        now = time.monotonic()
        with self._lock:
            self.mode.select_level(map_id, now)
            self.mode.started = True
            self.mode.status = "playing"
            self.mode.pause_reason = ""
            self.mode.invincible_until = now + config.INVINCIBLE_SECONDS
            self.phase = "playing"
            self.message = ""

    def build_state(self) -> dict[str, Any]:
        with self._lock:
            return serialize_duo_mode(self.mode, self.tick, self.phase, 0, self.message)

    def broadcast_state(self) -> None:
        state = self.build_state()
        self._broadcast(state)

    def _accept_loop(self) -> None:
        while self.running:
            server_sock = self._server_sock
            if server_sock is None:
                return
            try:
                client_sock, address = server_sock.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            thread = threading.Thread(target=self._client_loop, args=(client_sock, address), daemon=True)
            self._client_threads.append(thread)
            thread.start()

    def _client_loop(self, client_sock: socket.socket, address: tuple[str, int]) -> None:
        client_sock.settimeout(0.2)
        peer: Optional[_ClientPeer] = None
        buffer = b""
        try:
            peer = self._handshake(client_sock, address, buffer)
            if peer is None:
                return
            buffer = b""
            while self.running:
                try:
                    chunk = client_sock.recv(8192)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if not chunk:
                    break
                messages, buffer = decode_messages(buffer + chunk)
                for message in messages:
                    if not self._handle_client_message(peer, message):
                        return
        finally:
            if peer is not None:
                self._remove_peer(peer.player_id)
            try:
                client_sock.close()
            except OSError:
                pass

    def _handshake(
        self,
        client_sock: socket.socket,
        address: tuple[str, int],
        buffer: bytes,
    ) -> Optional[_ClientPeer]:
        deadline = time.monotonic() + 3.0
        while self.running and time.monotonic() < deadline:
            try:
                chunk = client_sock.recv(8192)
            except socket.timeout:
                continue
            except OSError:
                return None
            if not chunk:
                return None
            messages, buffer = decode_messages(buffer + chunk)
            for message in messages:
                if message.get("type") != "hello":
                    continue
                peer = self._register_peer(client_sock, address)
                if peer is None:
                    try:
                        client_sock.sendall(encode_message({"type": "error", "message": "Room is full"}))
                    except OSError:
                        pass
                    return None
                peer.send(
                    {
                        "type": "welcome",
                        "player_id": peer.player_id,
                        "match_id": "local",
                        "server_time": time.monotonic(),
                    }
                )
                self.broadcast_state()
                return peer
        return None

    def _register_peer(self, client_sock: socket.socket, address: tuple[str, int]) -> Optional[_ClientPeer]:
        with self._lock:
            loopback = self._is_loopback_address(address[0])
            if loopback and 1 not in self._clients:
                player_id = 1
            elif 2 not in self._clients:
                player_id = 2
            elif 1 not in self._clients:
                player_id = 1
            else:
                return None
            peer = _ClientPeer(player_id, client_sock, address)
            self._clients[player_id] = peer
            self.message = "Ready to start" if len(self._clients) == 2 else "Waiting for Player 2"
            return peer

    def _is_loopback_address(self, host: str) -> bool:
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return host == "localhost"

    def _remove_peer(self, player_id: int) -> None:
        with self._lock:
            self._clients.pop(player_id, None)
            if self.running and self.phase == "playing":
                self.phase = "gameover"
                self.message = "Connection Lost"
            elif self.running and self.phase == "waiting":
                self.message = "Waiting for Player 2"
        if self.running:
            self.broadcast_state()

    def _handle_client_message(self, peer: _ClientPeer, message: dict[str, Any]) -> bool:
        message_type = message.get("type")
        if message_type == "input":
            data = dict(message)
            data["player_id"] = peer.player_id
            self.record_input(data)
        elif message_type == "start_match":
            if peer.player_id == 1 and self.get_status()["player_count"] >= 2:
                self.start_match(int(message.get("map_id", 0)))
        elif message_type == "ping":
            peer.send({"type": "pong", "timestamp": message.get("timestamp", time.monotonic())})
        elif message_type == "disconnect":
            return False
        return True

    def _game_loop(self) -> None:
        last = time.monotonic()
        state_interval = 1.0 / max(1, self.state_rate)
        tick_interval = 1.0 / max(1, self.tick_rate)
        next_state_at = last
        while self.running:
            now = time.monotonic()
            if now - last >= tick_interval:
                dt = min(now - last, 0.1)
                last = now
                self._update_game(dt, now)
            if now >= next_state_at:
                self.broadcast_state()
                next_state_at = now + state_interval
            time.sleep(0.005)

    def _update_game(self, dt: float, now: float) -> None:
        with self._lock:
            if self.phase != "playing":
                return
            result = inputs_to_duo_result(self.latest_inputs)
            event = self.mode.update(result, dt, now, target_sensitivity=1.0)
            self.tick += 1
            if event == "gameover":
                self.phase = "gameover"
                self.message = self.mode.result_label
            else:
                self.message = self.mode.pause_reason

    def _broadcast(self, data: dict[str, Any]) -> None:
        with self._lock:
            peers = list(self._clients.values())
        lost: list[int] = []
        for peer in peers:
            if not peer.send(data):
                lost.append(peer.player_id)
        for player_id in lost:
            self._remove_peer(player_id)
