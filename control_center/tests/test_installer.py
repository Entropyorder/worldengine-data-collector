# control_center/tests/test_installer.py
import sys
import platform
import pytest
from pathlib import Path

# Ensure control_center/ is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from installer import (
    is_valid_valheim_path,
    detect_valheim_path,
    install_dlls,
    get_bundle_dir,
    STEAM_CANDIDATE_PATHS,
)


def _make_valheim(tmp_path: Path) -> Path:
    """Create a minimal fake Valheim installation."""
    v = tmp_path / "Valheim"
    v.mkdir()
    (v / "valheim.exe").touch()
    (v / "BepInEx" / "core").mkdir(parents=True)
    (v / "BepInEx" / "core" / "BepInEx.dll").touch()
    return v


# ── is_valid_valheim_path ─────────────────────────────────────────────────

def test_valid_valheim_path_accepts_complete_installation(tmp_path):
    v = _make_valheim(tmp_path)
    assert is_valid_valheim_path(v) is True


def test_valid_valheim_path_rejects_missing_exe(tmp_path):
    v = tmp_path / "Valheim"
    v.mkdir()
    (v / "BepInEx" / "core").mkdir(parents=True)
    (v / "BepInEx" / "core" / "BepInEx.dll").touch()
    assert is_valid_valheim_path(v) is False


def test_valid_valheim_path_rejects_missing_bepinex(tmp_path):
    v = tmp_path / "Valheim"
    v.mkdir()
    (v / "valheim.exe").touch()
    assert is_valid_valheim_path(v) is False


def test_valid_valheim_path_rejects_nonexistent(tmp_path):
    assert is_valid_valheim_path(tmp_path / "does_not_exist") is False


# ── detect_valheim_path ───────────────────────────────────────────────────

def test_detect_finds_first_valid_candidate(tmp_path, monkeypatch):
    v = _make_valheim(tmp_path)
    monkeypatch.setattr(
        "installer.STEAM_CANDIDATE_PATHS",
        [tmp_path / "missing", v],
    )
    assert detect_valheim_path() == v


def test_detect_returns_none_when_nothing_found(monkeypatch):
    monkeypatch.setattr("installer.STEAM_CANDIDATE_PATHS", [])
    assert detect_valheim_path() is None


# ── install_dlls ──────────────────────────────────────────────────────────

def test_install_copies_plugin_dll(tmp_path):
    v = _make_valheim(tmp_path)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "WorldEngineCollector.dll").touch()

    errors = install_dlls(v, bundle)

    assert errors == []
    assert (v / "BepInEx" / "plugins" / "WorldEngineCollector.dll").exists()


def test_install_copies_dx_capture_to_root(tmp_path):
    v = _make_valheim(tmp_path)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "dx_capture.dll").touch()
    (bundle / "WorldEngineCollector.dll").touch()

    errors = install_dlls(v, bundle)

    assert errors == []
    assert (v / "dx_capture.dll").exists()


def test_install_copies_ffmpeg_dlls_to_root(tmp_path):
    v = _make_valheim(tmp_path)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "WorldEngineCollector.dll").touch()
    (bundle / "avcodec-61.dll").touch()
    (bundle / "swscale-8.dll").touch()

    errors = install_dlls(v, bundle)

    assert errors == []
    assert (v / "avcodec-61.dll").exists()
    assert (v / "swscale-8.dll").exists()


def test_install_reports_error_for_missing_plugin(tmp_path):
    v = _make_valheim(tmp_path)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    # WorldEngineCollector.dll intentionally absent

    errors = install_dlls(v, bundle)

    assert any("WorldEngineCollector.dll" in e for e in errors)


def test_install_creates_plugins_dir_if_absent(tmp_path):
    v = _make_valheim(tmp_path)
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / "WorldEngineCollector.dll").touch()

    install_dlls(v, bundle)

    assert (v / "BepInEx" / "plugins").is_dir()


# ── get_bundle_dir ────────────────────────────────────────────────────────

def test_get_bundle_dir_returns_path():
    result = get_bundle_dir()
    assert isinstance(result, Path)
