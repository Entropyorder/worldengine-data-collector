from __future__ import annotations
import json
from datetime import datetime
from pathlib import Path


def parse_frame_time(time_str: str) -> datetime:
    """Parse 'YYYY-MM-DD HH:MM:SS.fff' -> datetime (microseconds precision)."""
    return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")


def compute_speeds(frames: list[dict]) -> list[dict]:
    """Fill camera_speed and player_speed for each frame via finite difference. Mutates and returns the list."""
    for i, frame in enumerate(frames):
        if i == 0:
            frame["camera_speed"] = [0.0, 0.0, 0.0]
            frame["player_speed"] = [0.0, 0.0, 0.0]
            continue

        dt = (parse_frame_time(frames[i]["time"]) - parse_frame_time(frames[i - 1]["time"])).total_seconds()
        if dt <= 0.0:
            frame["camera_speed"] = [0.0, 0.0, 0.0]
            frame["player_speed"] = [0.0, 0.0, 0.0]
            continue

        cp = frame["camera_position"]
        cp_prev = frames[i - 1]["camera_position"]
        frame["camera_speed"] = [(cp[j] - cp_prev[j]) / dt for j in range(3)]

        pp = frame["player_position"]
        pp_prev = frames[i - 1]["player_position"]
        frame["player_speed"] = [(pp[j] - pp_prev[j]) / dt for j in range(3)]

    return frames


def validate_frames(frames: list[dict]) -> list[str]:
    """Return list of human-readable warning strings for anomalies."""
    warnings: list[str] = []
    for i in range(1, len(frames)):
        expected = frames[i - 1]["frame"] + 1
        actual = frames[i]["frame"]
        if actual != expected:
            warnings.append(
                f"Frame gap between frame {frames[i-1]['frame']} and frame {actual} (expected frame {expected})"
            )
    return warnings


def process_session(session_dir: str) -> None:
    """Read raw_frames.jsonl, compute speeds, validate, write action_camera.json and fps.json."""
    session_path = Path(session_dir)
    raw_path = session_path / "raw_frames.jsonl"

    frames: list[dict] = []
    fps_records: list[dict] = []

    with open(raw_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            fps_records.append({"time": record["time"], "fps": record.pop("_game_fps", 0.0)})
            frames.append(record)

    warnings = validate_frames(frames)
    for w in warnings:
        print(f"[WARN] {w}")

    frames = compute_speeds(frames)

    out_action = session_path / "action_camera.json"
    with open(out_action, "w", encoding="utf-8") as f:
        for frame in frames:
            f.write(json.dumps(frame, ensure_ascii=False) + "\n")

    out_fps = session_path / "fps.json"
    with open(out_fps, "w", encoding="utf-8") as f:
        json.dump(fps_records, f, ensure_ascii=False, indent=2)

    print(f"[OK] Processed {len(frames)} frames -> {out_action}")
    print(f"[OK] FPS log -> {out_fps}")
