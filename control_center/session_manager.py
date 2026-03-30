from __future__ import annotations
import yaml
from datetime import datetime
from pathlib import Path
from enum import Enum, auto


class SessionState(Enum):
    IDLE = auto()
    RECORDING = auto()
    PROCESSING = auto()


class SessionManager:
    """
    Manages the lifecycle of a single recording session.
    """

    def __init__(self, settings_path: str = "config/settings.yaml") -> None:
        with open(settings_path, encoding="utf-8") as f:
            self._settings = yaml.safe_load(f)
        self._state = SessionState.IDLE
        self._session_dir: Path | None = None
        self._game_config: dict = {}

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
        assert self._state == SessionState.IDLE, "Already in a session"
        assert self._game_config, "Call load_game() first"

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = self._game_config["process_name"]
        dir_name = f"session_{ts}_{name}"
        output_root = Path(self._settings["output_dir"])
        self._session_dir = output_root / dir_name
        self._session_dir.mkdir(parents=True, exist_ok=True)

        self._state = SessionState.RECORDING
        return self._session_dir

    def stop_session(self) -> None:
        assert self._state == SessionState.RECORDING
        self._state = SessionState.PROCESSING

    def finish_processing(self) -> None:
        assert self._state == SessionState.PROCESSING
        self._state = SessionState.IDLE
