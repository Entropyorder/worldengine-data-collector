from __future__ import annotations
import yaml
from datetime import datetime
from pathlib import Path
from enum import Enum, auto

from pipe_reader import FrameBuffer, PipeServer, TCPServer, TransportServer


class SessionState(Enum):
    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()


class SessionManager:
    """
    Manages the lifecycle of a single recording session.
    """

    def __init__(self, settings_path: str = "config/settings.yaml") -> None:
        self._settings_path = settings_path
        self._settings: dict = {}
        self._state = SessionState.IDLE
        self._session_dir: Path | None = None
        self._game_config: dict = {}

    def _ensure_settings(self) -> None:
        if not self._settings:
            try:
                with open(self._settings_path, encoding="utf-8") as f:
                    loaded = yaml.safe_load(f)
                    self._settings = loaded if isinstance(loaded, dict) else {}
            except FileNotFoundError:
                self._settings = {}

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def session_dir(self) -> Path | None:
        return self._session_dir

    def load_game(self, game_yaml_path: str) -> None:
        with open(game_yaml_path, encoding="utf-8") as f:
            self._game_config = yaml.safe_load(f)

    def start_session(self) -> Path:
        if self._state != SessionState.IDLE:
            raise RuntimeError("Already in a session")
        if not self._game_config:
            raise RuntimeError("Call load_game() first")
        self._ensure_settings()

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = self._game_config["process_name"]
        dir_name = f"session_{ts}_{name}"
        output_root = Path(self._settings.get("output_dir", "sessions"))
        self._session_dir = output_root / dir_name
        self._session_dir.mkdir(parents=True, exist_ok=True)

        self._state = SessionState.RECORDING
        return self._session_dir

    def stop_session(self) -> None:
        if self._state != SessionState.RECORDING:
            raise RuntimeError("stop_session called when not recording")
        self._state = SessionState.PROCESSING

    def finish_processing(self) -> None:
        if self._state != SessionState.PROCESSING:
            raise RuntimeError("finish_processing called when not processing")
        self._state = SessionState.IDLE

    def get_valheim_path(self) -> str | None:
        """Returns the stored Valheim installation path, or None if not configured."""
        self._ensure_settings()
        return self._settings.get("valheim_path")

    def save_valheim_path(self, path: str) -> None:
        """Persists the Valheim installation path to settings.yaml."""
        self._ensure_settings()
        self._settings["valheim_path"] = path
        with open(self._settings_path, "w", encoding="utf-8") as f:
            yaml.dump(self._settings, f, allow_unicode=True)

    def get_game_install_path(self, process_name: str) -> str | None:
        """
        Returns the stored install path for a game, or None if not configured.
        Falls back to the legacy 'valheim_path' key for process_name == 'valheim'.
        """
        self._ensure_settings()
        result = self._settings.get("game_install_paths", {}).get(process_name)
        if result is None and process_name == "valheim":
            result = self._settings.get("valheim_path")
        return result

    def save_game_install_path(self, process_name: str, path: str) -> None:
        """Persists the install path for a game to settings.yaml."""
        self._ensure_settings()
        if "game_install_paths" not in self._settings:
            self._settings["game_install_paths"] = {}
        self._settings["game_install_paths"][process_name] = path
        with open(self._settings_path, "w", encoding="utf-8") as f:
            yaml.dump(self._settings, f, allow_unicode=True)

    def make_transport_server(self, frame_buffer: FrameBuffer) -> TransportServer:
        """
        Returns the correct TransportServer for the loaded game config.
        Call after load_game(). Defaults to PipeServer if 'transport' key absent.
        """
        if not self._game_config:
            raise RuntimeError("Call load_game() first")
        transport = self._game_config.get("transport", "namedpipe")
        if transport == "tcp":
            port = self._game_config.get("tcp_port", 27015)
            return TCPServer(frame_buffer, port=port)
        return PipeServer(frame_buffer)
