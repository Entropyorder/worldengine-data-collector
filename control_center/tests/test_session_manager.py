# control_center/tests/test_session_manager.py
import sys
import pytest
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from session_manager import SessionManager


def _make_settings(tmp_path: Path, extra: dict | None = None) -> Path:
    cfg = {"output_dir": str(tmp_path / "out"), "ffmpeg_path": "ffmpeg"}
    if extra:
        cfg.update(extra)
    p = tmp_path / "settings.yaml"
    p.write_text(yaml.dump(cfg), encoding="utf-8")
    return p


def test_get_valheim_path_returns_none_when_absent(tmp_path):
    sm = SessionManager(str(_make_settings(tmp_path)))
    assert sm.get_valheim_path() is None


def test_get_valheim_path_returns_stored_value(tmp_path):
    settings = _make_settings(tmp_path, {"valheim_path": "C:/Games/Valheim"})
    sm = SessionManager(str(settings))
    assert sm.get_valheim_path() == "C:/Games/Valheim"


def test_save_valheim_path_persists_to_yaml(tmp_path):
    settings = _make_settings(tmp_path)
    sm = SessionManager(str(settings))
    sm.save_valheim_path("D:/SteamLibrary/Valheim")

    with open(settings, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data["valheim_path"] == "D:/SteamLibrary/Valheim"


def test_save_valheim_path_updates_cached_settings(tmp_path):
    settings = _make_settings(tmp_path)
    sm = SessionManager(str(settings))
    sm.save_valheim_path("D:/SteamLibrary/Valheim")
    assert sm.get_valheim_path() == "D:/SteamLibrary/Valheim"
