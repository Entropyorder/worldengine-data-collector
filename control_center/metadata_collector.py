from __future__ import annotations
import json
import logging
import math
import platform
import re
import subprocess
from pathlib import Path
from typing import Any

import openpyxl
import yaml


# ---------- OS helpers (Windows-only, stubbed on other platforms) ----------

def get_game_window_rect(process_name: str) -> tuple[int, int, int, int]:
    """Return (left, top, right, bottom) of the game window. Returns (0,0,1920,1080) on failure."""
    if platform.system() != "Windows":
        return (0, 0, 1920, 1080)
    try:
        import ctypes
        import ctypes.wintypes as wt
        user32 = ctypes.WinDLL("user32")
        result = [0, 0, 1920, 1080]

        def _enum_callback(hwnd, _):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if process_name.lower() in buf.value.lower():
                    rect = wt.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    result[0] = rect.left
                    result[1] = rect.top
                    result[2] = rect.right
                    result[3] = rect.bottom
                    return False
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        user32.EnumWindows(WNDENUMPROC(_enum_callback), 0)
        return tuple(result)
    except Exception:
        return (0, 0, 1920, 1080)


def get_system_dpi() -> float:
    """Return system DPI scale factor (1.0 = 100%, 1.5 = 150%)."""
    if platform.system() != "Windows":
        return 1.0
    try:
        import ctypes
        import ctypes.wintypes as wt
        shcore = ctypes.WinDLL("shcore")
        dpi = wt.UINT()
        shcore.GetDpiForMonitor(0, 0, ctypes.byref(dpi), ctypes.byref(wt.UINT()))
        return round(dpi.value / 96.0, 1)
    except Exception:
        return 1.0


def get_process_title(process_name: str) -> str:
    """Return window title of the first window belonging to process_name."""
    if platform.system() != "Windows":
        return process_name
    try:
        safe_name = re.sub(r"[^a-zA-Z0-9_\-]", "", process_name)
        out = subprocess.check_output(
            ["powershell", "-Command",
             f"(Get-Process -Name '{safe_name}' | Select-Object -First 1).MainWindowTitle"],
            text=True, timeout=5
        ).strip()
        return out if out else process_name
    except Exception:
        return process_name


# ---------- Core builders ----------

def build_systeminfo(process_name: str, width: int, height: int) -> dict:
    rect = get_game_window_rect(process_name)
    title = get_process_title(process_name)
    dpi = get_system_dpi()
    return {
        "gameProcessName": title,
        "window_rect": [{"x": rect[0], "y": rect[1]}, {"x": rect[2], "y": rect[3]}],
        "width": width,
        "height": height,
        "recordDpi": round(dpi, 1),
    }


def detect_perspective(camera_follow_offsets: list[list[float]]) -> str:
    """
    Determine first vs third person from sampled follow offsets.
    Average distance < 0.5m -> first person.
    """
    if not camera_follow_offsets:
        return "未知"
    avg_dist = sum(
        math.sqrt(sum(x ** 2 for x in v)) for v in camera_follow_offsets
    ) / len(camera_follow_offsets)
    return "第一人称" if avg_dist < 0.5 else "第三人称"


def build_game_meta_dict(
    game_cfg: dict,
    sample_offsets: list[list[float]],
    width: int,
    height: int,
) -> dict:
    meta_cfg = game_cfg.get("game_meta", {})
    key_map = game_cfg.get("key_mapping", {})
    mouse_cfg = game_cfg.get("mouse_config", {})

    key_rules = "; ".join(str(v) for v in key_map.values()) if key_map else "未配置"

    perspective = detect_perspective(sample_offsets)
    avg_dist = _avg_offset_distance(sample_offsets)
    if perspective == "第一人称":
        cam_desc = f"第一人称，眼睛高度约 {avg_dist:.1f}m"
    else:
        cam_desc = f"第三人称跟随，典型偏移距离约 {avg_dist:.1f}m"

    return {
        "游戏类型描述": meta_cfg.get("game_type_description", ""),
        "视角配置": meta_cfg.get("perspective", perspective),
        "相机位置是否固定": "否",
        "相机位置描述": cam_desc,
        "画面分辨率": f"{width}x{height}",
        "键盘映射规则": key_rules,
        "鼠标对应规则": mouse_cfg.get("description", ""),
    }


def _avg_offset_distance(offsets: list[list[float]]) -> float:
    if not offsets:
        return 0.0
    return sum(math.sqrt(sum(x ** 2 for x in v)) for v in offsets) / len(offsets)


def write_game_meta_xlsx(meta_dict: dict, output_path: str | Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "游戏元信息"
    ws.append(["字段", "内容"])
    for k, v in meta_dict.items():
        ws.append([k, v])
    wb.save(str(output_path))


def collect_and_write(
    session_dir: str | Path,
    game_yaml_path: str | Path,
    raw_frames_path: str | Path,
    width: int = 1920,
    height: int = 1080,
) -> None:
    """Top-level: generate systeminfo.json + game_meta.xlsx for a completed session."""
    session_path = Path(session_dir)

    with open(game_yaml_path, encoding="utf-8") as f:
        game_cfg = yaml.safe_load(f)

    # systeminfo.json
    sysinfo = build_systeminfo(game_cfg["process_name"], width, height)
    with open(session_path / "systeminfo.json", "w", encoding="utf-8") as f:
        json.dump(sysinfo, f, ensure_ascii=False, indent=2)

    # Sample follow offsets from raw frames for perspective detection
    sample_offsets: list[list[float]] = []
    raw_path = Path(raw_frames_path)
    if raw_path.exists():
        with open(raw_path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i >= 300:
                    break
                line = line.strip()
                if line:
                    try:
                        rec = json.loads(line)
                        offset = rec.get("camera_follow_offset")
                        if offset:
                            sample_offsets.append(offset)
                    except json.JSONDecodeError:
                        pass

    meta_dict = build_game_meta_dict(game_cfg, sample_offsets, width, height)
    write_game_meta_xlsx(meta_dict, session_path / "game_meta.xlsx")

    logging.getLogger(__name__).info("Metadata written to %s", session_path)
