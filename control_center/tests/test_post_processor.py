import json
from pathlib import Path
from datetime import datetime
from post_processor import compute_speeds, validate_frames, parse_frame_time, process_session

class TestParseFrameTime:
    def test_parses_milliseconds(self):
        t = parse_frame_time("2026-03-30 14:30:22.033")
        assert t == datetime(2026, 3, 30, 14, 30, 22, 33000)

    def test_parses_zero_ms(self):
        t = parse_frame_time("2026-03-30 00:00:00.000")
        assert t == datetime(2026, 3, 30, 0, 0, 0, 0)


class TestComputeSpeeds:
    def _make_frame(self, time_str, cam_pos, player_pos, frame_idx=0):
        return {
            "frame": frame_idx,
            "time": time_str,
            "camera_position": cam_pos,
            "player_position": player_pos,
            "camera_speed": [0.0, 0.0, 0.0],
            "player_speed": [0.0, 0.0, 0.0],
        }

    def test_first_frame_speed_is_zero(self):
        frames = [self._make_frame("2026-03-30 00:00:00.000", [0.0, 0.0, 0.0], [0.0, 0.0, 0.0])]
        result = compute_speeds(frames)
        assert result[0]["camera_speed"] == [0.0, 0.0, 0.0]
        assert result[0]["player_speed"] == [0.0, 0.0, 0.0]

    def test_camera_speed_computed_correctly(self):
        frames = [
            self._make_frame("2026-03-30 00:00:00.000", [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], 0),
            self._make_frame("2026-03-30 00:00:00.033", [1.0, 0.0, 0.0], [1.0, 0.0, 0.0], 1),
        ]
        result = compute_speeds(frames)
        assert abs(result[1]["camera_speed"][0] - 1.0 / 0.033) < 0.01
        assert result[1]["camera_speed"][1] == 0.0
        assert result[1]["camera_speed"][2] == 0.0

    def test_player_speed_computed_correctly(self):
        frames = [
            self._make_frame("2026-03-30 00:00:00.000", [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], 0),
            self._make_frame("2026-03-30 00:00:00.033", [0.0, 0.0, 0.0], [0.0, 0.0, 3.0], 1),
        ]
        result = compute_speeds(frames)
        assert abs(result[1]["player_speed"][2] - 3.0 / 0.033) < 0.01

    def test_zero_dt_returns_zero_speed(self):
        frames = [
            self._make_frame("2026-03-30 00:00:00.000", [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], 0),
            self._make_frame("2026-03-30 00:00:00.000", [1.0, 0.0, 0.0], [0.0, 0.0, 0.0], 1),
        ]
        result = compute_speeds(frames)
        assert result[1]["camera_speed"] == [0.0, 0.0, 0.0]


class TestValidateFrames:
    def test_empty_returns_no_warnings(self):
        warnings = validate_frames([])
        assert warnings == []

    def test_detects_gap_in_frame_index(self):
        frames = [
            {"frame": 0, "time": "2026-03-30 00:00:00.000"},
            {"frame": 2, "time": "2026-03-30 00:00:00.033"},
        ]
        warnings = validate_frames(frames)
        assert any("gap" in w.lower() or "frame 1" in w for w in warnings)

    def test_contiguous_frames_no_warning(self):
        frames = [
            {"frame": 0, "time": "2026-03-30 00:00:00.000"},
            {"frame": 1, "time": "2026-03-30 00:00:00.033"},
            {"frame": 2, "time": "2026-03-30 00:00:00.066"},
        ]
        warnings = validate_frames(frames)
        assert warnings == []


class TestProcessSession:
    def test_process_session_integration(self, tmp_path):
        raw_path = tmp_path / "raw_frames.jsonl"
        frame0 = {
            "frame": 0,
            "time": "2026-03-30 00:00:00.000",
            "camera_position": [0.0, 0.0, 0.0],
            "player_position": [0.0, 0.0, 0.0],
            "_game_fps": 60.0,
        }
        frame1 = {
            "frame": 1,
            "time": "2026-03-30 00:00:00.033",
            "camera_position": [1.0, 0.0, 0.0],
            "player_position": [1.0, 0.0, 0.0],
            "_game_fps": 59.5,
        }
        raw_path.write_text(
            json.dumps(frame0) + "\n" + json.dumps(frame1) + "\n",
            encoding="utf-8",
        )

        process_session(tmp_path)

        action_path = tmp_path / "action_camera.json"
        assert action_path.exists()
        action_lines = [l for l in action_path.read_text(encoding="utf-8").splitlines() if l.strip()]
        assert len(action_lines) == 2
        for line in action_lines:
            record = json.loads(line)
            assert "_game_fps" not in record

        fps_path = tmp_path / "fps.json"
        assert fps_path.exists()
        fps_records = json.loads(fps_path.read_text(encoding="utf-8"))
        assert len(fps_records) == 2
        assert fps_records[0]["fps"] == 60.0
        assert fps_records[1]["fps"] == 59.5
