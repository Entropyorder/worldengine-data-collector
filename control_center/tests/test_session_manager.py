# control_center/tests/test_session_manager.py
import sys
import yaml
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from session_manager import SessionManager


def _make_settings(tmp_path: Path, extra: Optional[dict] = None) -> Path:
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


def _sm_settings(tmp_path, extra: Optional[dict] = None) -> str:
    cfg = {"output_dir": str(tmp_path / "out"), "ffmpeg_path": "ffmpeg"}
    if extra:
        cfg.update(extra)
    p = tmp_path / "settings.yaml"
    p.write_text(_yaml_mod.dump(cfg), encoding="utf-8")
    return str(p)


def test_get_game_install_path_returns_none_when_not_set(tmp_path):
    sm = SessionManager(_sm_settings(tmp_path))
    assert sm.get_game_install_path("valheim") is None


def test_save_and_get_game_install_path_roundtrip(tmp_path):
    sm = SessionManager(_sm_settings(tmp_path))
    sm.save_game_install_path("valheim", "/games/valheim")
    assert sm.get_game_install_path("valheim") == "/games/valheim"


def test_get_game_install_path_backward_compat_valheim(tmp_path):
    """Old settings.yaml with valheim_path key still works for process_name 'valheim'."""
    sm = SessionManager(_sm_settings(tmp_path, {"valheim_path": "/old/valheim"}))
    assert sm.get_game_install_path("valheim") == "/old/valheim"


def test_save_game_install_path_multiple_games(tmp_path):
    sm = SessionManager(_sm_settings(tmp_path))
    sm.save_game_install_path("valheim", "/games/valheim")
    sm.save_game_install_path("SkyrimSE", "/games/skyrim")
    sm.save_game_install_path("Cyberpunk2077", "/games/cp2077")
    assert sm.get_game_install_path("valheim") == "/games/valheim"
    assert sm.get_game_install_path("SkyrimSE") == "/games/skyrim"
    assert sm.get_game_install_path("Cyberpunk2077") == "/games/cp2077"


def test_save_game_install_path_persists_to_yaml(tmp_path):
    sp = _sm_settings(tmp_path)
    sm = SessionManager(sp)
    sm.save_game_install_path("valheim", "/games/valheim")
    sm2 = SessionManager(sp)
    assert sm2.get_game_install_path("valheim") == "/games/valheim"


def test_save_game_install_path_does_not_overwrite_other_games(tmp_path):
    sp = _sm_settings(tmp_path)
    sm = SessionManager(sp)
    sm.save_game_install_path("valheim", "/games/valheim")
    sm.save_game_install_path("SkyrimSE", "/games/skyrim")
    sm.save_game_install_path("Cyberpunk2077", "/games/cp")
    assert sm.get_game_install_path("valheim") == "/games/valheim"
    assert sm.get_game_install_path("SkyrimSE") == "/games/skyrim"


def test_get_game_install_path_returns_none_for_unknown_game(tmp_path):
    import yaml
    settings = {"output_dir": str(tmp_path / "out"), "ffmpeg_path": "ffmpeg"}
    sp = tmp_path / "settings.yaml"
    sp.write_text(yaml.dump(settings), encoding="utf-8")
    from session_manager import SessionManager
    sm = SessionManager(str(sp))
    assert sm.get_game_install_path("SkyrimSE") is None
    assert sm.get_game_install_path("Cyberpunk2077") is None
