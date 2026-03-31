import json
import pytest
from unittest.mock import patch, mock_open
from pipe_reader import FrameBuffer


class TestFrameBuffer:
    def test_empty_on_init(self):
        buf = FrameBuffer(output_path="dummy.jsonl")
        assert buf.frame_count == 0

    def test_ingest_increments_count(self, tmp_path):
        buf = FrameBuffer(output_path=str(tmp_path / "test.jsonl"))
        buf.open()
        try:
            buf.ingest('{"frame":0,"time":"2026-03-30 00:00:00.000"}\n')
            assert buf.frame_count == 1
        finally:
            buf.close()

    def test_ingest_does_not_count_when_closed(self):
        buf = FrameBuffer(output_path="dummy_not_opened.jsonl")
        # buf.open() not called — _file is None
        buf.ingest('{"frame":0}\n')
        assert buf.frame_count == 0

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


import socket
import time


def _find_free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestTCPServer:
    def test_receives_single_json_line(self, tmp_path):
        from pipe_reader import FrameBuffer, TCPServer
        port = _find_free_port()
        buf = FrameBuffer(str(tmp_path / "out.jsonl"))
        buf.open()
        srv = TCPServer(buf, port=port)
        srv.start()
        time.sleep(0.1)  # let server bind

        client = socket.socket()
        client.connect(("127.0.0.1", port))
        client.sendall(b'{"frame":0,"time":"2026-01-01 00:00:00.000"}\n')
        time.sleep(0.15)

        client.close()
        srv.stop()
        buf.close()

        assert buf.frame_count == 1

    def test_receives_multiple_lines_in_one_send(self, tmp_path):
        from pipe_reader import FrameBuffer, TCPServer
        port = _find_free_port()
        buf = FrameBuffer(str(tmp_path / "out.jsonl"))
        buf.open()
        srv = TCPServer(buf, port=port)
        srv.start()
        time.sleep(0.1)

        client = socket.socket()
        client.connect(("127.0.0.1", port))
        payload = (
            b'{"frame":0,"time":"2026-01-01 00:00:00.000"}\n'
            b'{"frame":1,"time":"2026-01-01 00:00:00.033"}\n'
            b'{"frame":2,"time":"2026-01-01 00:00:00.066"}\n'
        )
        client.sendall(payload)
        time.sleep(0.15)

        client.close()
        srv.stop()
        buf.close()

        assert buf.frame_count == 3

    def test_accepts_reconnect_after_client_disconnects(self, tmp_path):
        from pipe_reader import FrameBuffer, TCPServer
        port = _find_free_port()
        buf = FrameBuffer(str(tmp_path / "out.jsonl"))
        buf.open()
        srv = TCPServer(buf, port=port)
        srv.start()
        time.sleep(0.1)

        # First client
        c1 = socket.socket()
        c1.connect(("127.0.0.1", port))
        c1.sendall(b'{"frame":0,"time":"2026-01-01 00:00:00.000"}\n')
        time.sleep(0.1)
        c1.close()
        time.sleep(0.2)  # let server detect disconnect

        # Second client
        c2 = socket.socket()
        c2.connect(("127.0.0.1", port))
        c2.sendall(b'{"frame":1,"time":"2026-01-01 00:00:00.033"}\n')
        time.sleep(0.1)
        c2.close()
        srv.stop()
        buf.close()

        assert buf.frame_count == 2

    def test_stop_is_idempotent(self, tmp_path):
        from pipe_reader import FrameBuffer, TCPServer
        port = _find_free_port()
        buf = FrameBuffer(str(tmp_path / "out.jsonl"))
        srv = TCPServer(buf, port=port)
        srv.start()
        time.sleep(0.05)
        srv.stop()
        srv.stop()  # should not raise
