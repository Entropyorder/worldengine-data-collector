# control_center/installer.py
"""
Pure installation logic — no GUI dependencies.
Handles Valheim path detection, validation, and DLL deployment.
"""
from __future__ import annotations
import logging
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Candidate Steam library paths to probe when auto-detecting Valheim.
STEAM_CANDIDATE_PATHS: list[Path] = [
    Path("C:/Program Files (x86)/Steam/steamapps/common/Valheim"),
    Path("C:/Steam/steamapps/common/Valheim"),
    Path("C:/SteamLibrary/steamapps/common/Valheim"),
    Path("D:/Steam/steamapps/common/Valheim"),
    Path("D:/SteamLibrary/steamapps/common/Valheim"),
    Path("E:/Steam/steamapps/common/Valheim"),
    Path("E:/SteamLibrary/steamapps/common/Valheim"),
    Path("F:/Steam/steamapps/common/Valheim"),
    Path("F:/SteamLibrary/steamapps/common/Valheim"),
]


def get_bundle_dir() -> Path:
    """
    Returns the directory where bundled DLLs live.
    - When frozen by PyInstaller: sys._MEIPASS (the temp extraction dir)
    - In development: <repo_root>/bundle_dlls (populated by CI or manually)
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent / "bundle_dlls"


def is_valid_valheim_path(path: Path) -> bool:
    """Returns True if path looks like a BepInEx-modded Valheim installation."""
    return (
        path.is_dir()
        and (path / "valheim.exe").exists()
        and (path / "BepInEx" / "core" / "BepInEx.dll").exists()
    )


def detect_valheim_path() -> Path | None:
    """
    Scans common Steam library locations and returns the first valid
    Valheim installation found, or None if none is detected.
    """
    for candidate in STEAM_CANDIDATE_PATHS:
        if is_valid_valheim_path(candidate):
            logger.info("Auto-detected Valheim at: %s", candidate)
            return candidate
    logger.info("Valheim not found in any candidate path")
    return None


def install_dlls(valheim_path: Path, bundle_dir: Path) -> list[str]:
    """
    Copies bundled DLLs to the correct Valheim subdirectories.

    Returns a list of error strings. An empty list means full success.

    Layout:
      WorldEngineCollector.dll  ->  <valheim>/BepInEx/plugins/
      dx_capture.dll            ->  <valheim>/
      av*.dll, sw*.dll          ->  <valheim>/   (FFmpeg runtime)
    """
    errors: list[str] = []

    # Ensure plugins directory exists (BepInEx won't create it automatically)
    plugins_dir = valheim_path / "BepInEx" / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # BepInEx plugin
    plugin_src = bundle_dir / "WorldEngineCollector.dll"
    if plugin_src.exists():
        shutil.copy2(plugin_src, plugins_dir / plugin_src.name)
        logger.info("Installed %s -> %s", plugin_src.name, plugins_dir)
    else:
        msg = f"WorldEngineCollector.dll not found in package ({bundle_dir})"
        logger.error(msg)
        errors.append(msg)

    # dx_capture.dll + FFmpeg runtime DLLs -> Valheim root (all optional)
    root_dll_candidates = [bundle_dir / "dx_capture.dll"] + [
        f
        for f in bundle_dir.iterdir()
        if f.suffix == ".dll"
        and (f.name.startswith("av") or f.name.startswith("sw"))
    ]
    for src in root_dll_candidates:
        if src.exists():
            shutil.copy2(src, valheim_path / src.name)
            logger.info("Installed %s -> %s", src.name, valheim_path)

    return errors
