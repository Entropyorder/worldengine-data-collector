# control_center/tests/test_session_manager.py
import sys
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


import yaml as _yaml_mod

def _write_game_yaml(tmp_path, transport: str, port: int = 27015) -> str:
    cfg = {
        "game_name": "TestGame",
        "process_name": "testgame",
        "transport": transport,
        "tcp_port": port,
    }
    p = tmp_path / "game.yaml"
    p.write_text(_yaml_mod.dump(cfg), encoding="utf-8")
    return str(p)


def test_make_transport_server_namedpipe(tmp_path):
    import sys
    sys.path.insert(0, str(tmp_path.parent.parent / "control_center"))
    from pipe_reader import FrameBuffer, PipeServer
    from session_manager import SessionManager
    import yaml

    settings = {"output_dir": str(tmp_path / "out"), "ffmpeg_path": "ffmpeg"}
    sp = tmp_path / "settings.yaml"
    sp.write_text(yaml.dump(settings), encoding="utf-8")

    sm = SessionManager(str(sp))
    game_path = _write_game_yaml(tmp_path, "namedpipe")
    sm.load_game(game_path)
    buf = FrameBuffer(str(tmp_path / "out.jsonl"))
    srv = sm.make_transport_server(buf)
    assert isinstance(srv, PipeServer)


def test_make_transport_server_tcp(tmp_path):
    from pipe_reader import FrameBuffer, TCPServer
    from session_manager import SessionManager
    import yaml

    settings = {"output_dir": str(tmp_path / "out"), "ffmpeg_path": "ffmpeg"}
    sp = tmp_path / "settings.yaml"
    sp.write_text(yaml.dump(settings), encoding="utf-8")

    sm = SessionManager(str(sp))
    game_path = _write_game_yaml(tmp_path, "tcp", port=29999)
    sm.load_game(game_path)
    buf = FrameBuffer(str(tmp_path / "out.jsonl"))
    srv = sm.make_transport_server(buf)
    assert isinstance(srv, TCPServer)


def test_make_transport_server_defaults_to_namedpipe(tmp_path):
    """Games without a transport field default to Named Pipe."""
    from pipe_reader import FrameBuffer, PipeServer
    from session_manager import SessionManager
    import yaml

    settings = {"output_dir": str(tmp_path / "out"), "ffmpeg_path": "ffmpeg"}
    sp = tmp_path / "settings.yaml"
    sp.write_text(yaml.dump(settings), encoding="utf-8")

    cfg = {"game_name": "OldGame", "process_name": "oldgame"}
    gp = tmp_path / "old.yaml"
    gp.write_text(yaml.dump(cfg), encoding="utf-8")

    sm = SessionManager(str(sp))
    sm.load_game(str(gp))
    buf = FrameBuffer(str(tmp_path / "out.jsonl"))
    srv = sm.make_transport_server(buf)
    assert isinstance(srv, PipeServer)
