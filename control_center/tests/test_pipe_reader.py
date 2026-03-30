import json
import pytest
from unittest.mock import patch, mock_open
from pipe_reader import FrameBuffer


class TestFrameBuffer:
    def test_empty_on_init(self):
        buf = FrameBuffer(output_path="dummy.jsonl")
        assert buf.frame_count == 0

    def test_ingest_increments_count(self):
        buf = FrameBuffer(output_path="dummy.jsonl")
        with patch("builtins.open", mock_open()):
            buf.ingest('{"frame":0,"time":"2026-03-30 00:00:00.000"}\n')
            assert buf.frame_count == 1

    def test_ingest_ignores_blank_lines(self):
        buf = FrameBuffer(output_path="dummy.jsonl")
        with patch("builtins.open", mock_open()):
            buf.ingest("")
            buf.ingest("   \n")
            assert buf.frame_count == 0

    def test_ingest_invalid_json_raises(self):
        buf = FrameBuffer(output_path="dummy.jsonl")
        with pytest.raises(json.JSONDecodeError):
            buf.ingest("not json\n")
