# Game Selector UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the startup wizard (gated on `valheim_path`) with a persistent per-game setup panel in the Qt main window, so users can select and configure any of the three supported games (Valheim, Cyberpunk 2077, Skyrim SE) without reconfiguring on every launch.

**Architecture:** `installer.py` gains a generalized `is_valid_game_path()` that understands BepInEx, SKSE, and CET adapter types. `SessionManager` grows per-game install-path persistence under a `game_install_paths` dict in settings.yaml (with backward-compat for the old `valheim_path` key). A new `GameSetupDialog` (QDialog) replaces the per-game setup UI; `MainWindow` adds a Setup button next to the combo and disables Start when the selected game is not configured. `main.py` removes the wizard gate entirely.

**Tech Stack:** Python 3.12, PyQt6, PyYAML, pytest, pathlib.

---

## File Changelist

| File | Action |
|------|--------|
| `control_center/installer.py` | Add `is_valid_game_path(game_config, path)` |
| `control_center/session_manager.py` | Add `get_game_install_path()`, `save_game_install_path()` |
| `control_center/gui/game_setup_dialog.py` | New: `GameSetupDialog` |
| `control_center/gui/main_window.py` | Setup button, start-disable logic, transport-server fix, Tools menu update |
| `control_center/main.py` | Remove `_run_setup_wizard_if_needed` |
| `control_center/tests/test_installer.py` | Add `is_valid_game_path` tests |
| `control_center/tests/test_session_manager.py` | Add per-game path tests |

---

## Phase 1 — Backend

### Task 1: `is_valid_game_path` in installer.py

**Files:**
- Modify: `control_center/installer.py`
- Modify: `control_center/tests/test_installer.py`

- [ ] **Step 1: Write failing tests — append to `test_installer.py`**

```python
from installer import is_valid_game_path


# ── is_valid_game_path ────────────────────────────────────────────────────────

def test_valid_game_path_bepinex_accepts_valid_installation(tmp_path):
    v = tmp_path / "Valheim"
    v.mkdir()
    (v / "valheim.exe").touch()
    (v / "BepInEx" / "core").mkdir(parents=True)
    (v / "BepInEx" / "core" / "BepInEx.dll").touch()
    cfg = {"process_name": "valheim", "adapter_type": "bepinex"}
    assert is_valid_game_path(cfg, v) is True


def test_valid_game_path_bepinex_rejects_missing_bepinex(tmp_path):
    v = tmp_path / "Valheim"
    v.mkdir()
    (v / "valheim.exe").touch()
    cfg = {"process_name": "valheim", "adapter_type": "bepinex"}
    assert is_valid_game_path(cfg, v) is False


def test_valid_game_path_bepinex_rejects_missing_exe(tmp_path):
    v = tmp_path / "Valheim"
    v.mkdir()
    (v / "BepInEx" / "core").mkdir(parents=True)
    (v / "BepInEx" / "core" / "BepInEx.dll").touch()
    cfg = {"process_name": "valheim", "adapter_type": "bepinex"}
    assert is_valid_game_path(cfg, v) is False


def test_valid_game_path_skse_accepts_skyrim_exe_only(tmp_path):
    v = tmp_path / "Skyrim"
    v.mkdir()
    (v / "SkyrimSE.exe").touch()
    cfg = {"process_name": "SkyrimSE", "adapter_type": "skse_cpp"}
    assert is_valid_game_path(cfg, v) is True


def test_valid_game_path_skse_rejects_missing_exe(tmp_path):
    v = tmp_path / "Skyrim"
    v.mkdir()
    cfg = {"process_name": "SkyrimSE", "adapter_type": "skse_cpp"}
    assert is_valid_game_path(cfg, v) is False


def test_valid_game_path_cet_accepts_valid_cp2077(tmp_path):
    v = tmp_path / "CP2077"
    v.mkdir()
    (v / "Cyberpunk2077.exe").touch()
    (v / "bin" / "x64" / "plugins" / "cyber_engine_tweaks").mkdir(parents=True)
    cfg = {"process_name": "Cyberpunk2077", "adapter_type": "cet_lua"}
    assert is_valid_game_path(cfg, v) is True


def test_valid_game_path_cet_rejects_missing_cet_dir(tmp_path):
    v = tmp_path / "CP2077"
    v.mkdir()
    (v / "Cyberpunk2077.exe").touch()
    cfg = {"process_name": "Cyberpunk2077", "adapter_type": "cet_lua"}
    assert is_valid_game_path(cfg, v) is False


def test_valid_game_path_defaults_to_bepinex_when_no_adapter_type(tmp_path):
    v = tmp_path / "Game"
    v.mkdir()
    (v / "mygame.exe").touch()
    (v / "BepInEx" / "core").mkdir(parents=True)
    (v / "BepInEx" / "core" / "BepInEx.dll").touch()
    cfg = {"process_name": "mygame"}  # no adapter_type key
    assert is_valid_game_path(cfg, v) is True


def test_valid_game_path_returns_false_for_nonexistent_dir(tmp_path):
    cfg = {"process_name": "valheim", "adapter_type": "bepinex"}
    assert is_valid_game_path(cfg, tmp_path / "no_such_dir") is False
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /Users/larr/Desktop/EntropyOrder/projects/Gaming-Camera/control_center
python -m pytest tests/test_installer.py::test_valid_game_path_bepinex_accepts_valid_installation -v
```

Expected: `FAILED` with `ImportError: cannot import name 'is_valid_game_path'`

- [ ] **Step 3: Add `is_valid_game_path` to `installer.py`**

Add after the `is_valid_valheim_path` function (after line 45):

```python
def is_valid_game_path(game_config: dict, path: Path) -> bool:
    """
    Returns True if path is a valid installation directory for the given game.
    Dispatch logic is based on game_config['adapter_type']:
      'cet_lua'  → exe + CET directory
      'skse_cpp' → exe only (SKSE itself is a soft prerequisite)
      default    → exe + BepInEx/core/BepInEx.dll  (Valheim / BepInEx)
    """
    if not path.is_dir():
        return False
    process_name = game_config.get("process_name", "")
    adapter_type = game_config.get("adapter_type", "")
    exe = path / f"{process_name}.exe"

    if adapter_type == "cet_lua":
        return (
            exe.exists()
            and (path / "bin" / "x64" / "plugins" / "cyber_engine_tweaks").is_dir()
        )
    elif adapter_type == "skse_cpp":
        return exe.exists()
    else:  # bepinex (default)
        return exe.exists() and (path / "BepInEx" / "core" / "BepInEx.dll").exists()
```

- [ ] **Step 4: Run all installer tests**

```bash
cd /Users/larr/Desktop/EntropyOrder/projects/Gaming-Camera/control_center
python -m pytest tests/test_installer.py -v
```

Expected: all PASS (including the 9 new tests + the existing ones).

- [ ] **Step 5: Commit**

```bash
git add control_center/installer.py control_center/tests/test_installer.py
git commit -m "feat: add is_valid_game_path — supports bepinex/skse_cpp/cet_lua adapter types"
```

---

### Task 2: Per-game install paths in SessionManager

**Files:**
- Modify: `control_center/session_manager.py`
- Modify: `control_center/tests/test_session_manager.py`

- [ ] **Step 1: Write failing tests — append to `test_session_manager.py`**

```python
import yaml as _yaml


def _settings_file(tmp_path, extra: dict | None = None) -> str:
    cfg = {"output_dir": str(tmp_path / "out"), "ffmpeg_path": "ffmpeg"}
    if extra:
        cfg.update(extra)
    p = tmp_path / "settings.yaml"
    p.write_text(_yaml.dump(cfg), encoding="utf-8")
    return str(p)


def test_get_game_install_path_returns_none_when_not_set(tmp_path):
    sm = SessionManager(_settings_file(tmp_path))
    assert sm.get_game_install_path("valheim") is None


def test_save_and_get_game_install_path_roundtrip(tmp_path):
    sm = SessionManager(_settings_file(tmp_path))
    sm.save_game_install_path("valheim", "/games/valheim")
    assert sm.get_game_install_path("valheim") == "/games/valheim"


def test_get_game_install_path_backward_compat_valheim(tmp_path):
    """Old settings.yaml with valheim_path key still works for process_name 'valheim'."""
    sm = SessionManager(_settings_file(tmp_path, {"valheim_path": "/old/valheim"}))
    assert sm.get_game_install_path("valheim") == "/old/valheim"


def test_save_game_install_path_multiple_games(tmp_path):
    sm = SessionManager(_settings_file(tmp_path))
    sm.save_game_install_path("valheim", "/games/valheim")
    sm.save_game_install_path("SkyrimSE", "/games/skyrim")
    sm.save_game_install_path("Cyberpunk2077", "/games/cp2077")
    assert sm.get_game_install_path("valheim") == "/games/valheim"
    assert sm.get_game_install_path("SkyrimSE") == "/games/skyrim"
    assert sm.get_game_install_path("Cyberpunk2077") == "/games/cp2077"


def test_save_game_install_path_persists_to_yaml(tmp_path):
    sp = _settings_file(tmp_path)
    sm = SessionManager(sp)
    sm.save_game_install_path("valheim", "/games/valheim")

    # Create a fresh SessionManager reading the same file
    sm2 = SessionManager(sp)
    assert sm2.get_game_install_path("valheim") == "/games/valheim"


def test_new_game_path_does_not_overwrite_other_games(tmp_path):
    sp = _settings_file(tmp_path)
    sm = SessionManager(sp)
    sm.save_game_install_path("valheim", "/games/valheim")
    sm.save_game_install_path("SkyrimSE", "/games/skyrim")

    # Save a third without losing the first two
    sm.save_game_install_path("Cyberpunk2077", "/games/cp")
    assert sm.get_game_install_path("valheim") == "/games/valheim"
    assert sm.get_game_install_path("SkyrimSE") == "/games/skyrim"
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /Users/larr/Desktop/EntropyOrder/projects/Gaming-Camera/control_center
python -m pytest tests/test_session_manager.py::test_get_game_install_path_returns_none_when_not_set -v
```

Expected: `FAILED` with `AttributeError: 'SessionManager' object has no attribute 'get_game_install_path'`

- [ ] **Step 3: Add the two methods to `session_manager.py`**

Add after the `save_valheim_path` method (after line 86):

```python
def get_game_install_path(self, process_name: str) -> str | None:
    """
    Returns the stored install path for a game, or None if not configured.
    Falls back to the legacy 'valheim_path' key for process_name == 'valheim'.
    """
    self._ensure_settings()
    result = self._settings.get("game_install_paths", {}).get(process_name)
    if result is None and process_name == "valheim":
        result = self._settings.get("valheim_path")
    return result or None

def save_game_install_path(self, process_name: str, path: str) -> None:
    """Persists the install path for a game to settings.yaml."""
    self._ensure_settings()
    if "game_install_paths" not in self._settings:
        self._settings["game_install_paths"] = {}
    self._settings["game_install_paths"][process_name] = path
    with open(self._settings_path, "w", encoding="utf-8") as f:
        yaml.dump(self._settings, f, allow_unicode=True)
```

- [ ] **Step 4: Run all session manager tests**

```bash
cd /Users/larr/Desktop/EntropyOrder/projects/Gaming-Camera/control_center
python -m pytest tests/test_session_manager.py -v
```

Expected: all PASS.

- [ ] **Step 5: Run full test suite**

```bash
cd /Users/larr/Desktop/EntropyOrder/projects/Gaming-Camera/control_center
python -m pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add control_center/session_manager.py control_center/tests/test_session_manager.py
git commit -m "feat: SessionManager per-game install paths — get/save_game_install_path with valheim backward compat"
```

---

## Phase 2 — UI

### Task 3: `GameSetupDialog`

**Files:**
- Create: `control_center/gui/game_setup_dialog.py`

No automated unit tests — Qt widget tests require a QApplication and a display, which is fragile in CI. Manual smoke test described in Step 3.

- [ ] **Step 1: Create `control_center/gui/game_setup_dialog.py`**

```python
# control_center/gui/game_setup_dialog.py
"""
GameSetupDialog — per-game path configuration and adapter installation.

For BepInEx games (Valheim): automated DLL install.
For CET/SKSE games: path picker + manual install instructions.
"""
from __future__ import annotations
import threading
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFileDialog, QTextEdit,
)
from PyQt6.QtCore import pyqtSignal, QObject

from installer import is_valid_game_path, install_dlls, get_bundle_dir
from session_manager import SessionManager

_DARK_STYLE = """
QDialog       { background: #1e1e1e; color: #e0e0e0; }
QLabel        { color: #e0e0e0; }
QPushButton   { background: #3a3a3a; color: #e0e0e0; border: 1px solid #555;
                padding: 6px 14px; border-radius: 4px; }
QPushButton:hover    { background: #4a4a4a; }
QPushButton:disabled { color: #666; }
QPushButton#primary  { background: #1e6fbf; border-color: #2a8ae0; }
QPushButton#primary:hover { background: #2a8ae0; }
QLineEdit     { background: #2d2d2d; color: #e0e0e0; border: 1px solid #555;
                padding: 4px; border-radius: 3px; }
QTextEdit     { background: #2d2d2d; color: #e0e0e0; border: 1px solid #555; }
"""

_MANUAL_INSTRUCTIONS: dict[str, str] = {
    "cet_lua": (
        "Cyber Engine Tweaks (CET) mod — 手动安装步骤：\n\n"
        "1. 将 WorldEngineCollector_CP2077.zip 解压\n"
        "2. 将 bin/ 文件夹合并到 Cyberpunk 2077 安装目录\n"
        "   目标路径：<Cyberpunk2077>/bin/x64/plugins/cyber_engine_tweaks/mods/WorldEngineCollector/\n"
        "     init.lua\n"
        "     metadata.json\n\n"
        "前提条件：Cyber Engine Tweaks 已安装。\n\n"
        "完成后选择游戏安装目录并点击「保存路径」。"
    ),
    "skse_cpp": (
        "SKSE 插件 — 手动安装步骤：\n\n"
        "1. 将 WorldEngineCollector_Skyrim.zip 解压\n"
        "2. 将 Data/ 文件夹合并到 Skyrim SE 安装目录\n"
        "   目标路径：<SkyrimSE>/Data/SKSE/Plugins/WorldEngineCollector.dll\n\n"
        "前提条件：SKSE64 已安装。\n\n"
        "完成后选择游戏安装目录并点击「保存路径」。"
    ),
}


class _Signals(QObject):
    install_done = pyqtSignal(list)  # list[str] errors; empty = success


class GameSetupDialog(QDialog):
    """
    Per-game setup dialog: set install path and (for BepInEx games) install the adapter.

    Usage:
        dlg = GameSetupDialog(game_config=cfg, sm=session_manager, parent=self)
        dlg.exec()  # blocks; path is saved to settings on success
    """

    def __init__(self, game_config: dict, sm: SessionManager, parent=None) -> None:
        super().__init__(parent)
        self._cfg = game_config
        self._sm = sm
        self._adapter_type = game_config.get("adapter_type", "")
        self._process_name = game_config.get("process_name", "")
        self._game_name = game_config.get("game_name", "Unknown Game")

        self.setWindowTitle(f"{self._game_name} — 游戏配置")
        self.setMinimumSize(540, 400)
        self.setStyleSheet(_DARK_STYLE)

        self._signals = _Signals()
        self._signals.install_done.connect(self._on_install_done)

        self._build_ui()

        # Pre-fill path from saved settings
        saved = sm.get_game_install_path(self._process_name)
        if saved:
            self._path_edit.setText(saved)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        title = QLabel(self._game_name)
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        layout.addWidget(QLabel("游戏安装目录："))

        path_row = QHBoxLayout()
        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("请选择游戏安装目录…")
        self._path_edit.textChanged.connect(self._on_path_changed)
        path_row.addWidget(self._path_edit)
        browse_btn = QPushButton("浏览…")
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(browse_btn)
        layout.addLayout(path_row)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        if self._adapter_type in _MANUAL_INSTRUCTIONS:
            instructions = QTextEdit()
            instructions.setReadOnly(True)
            instructions.setPlainText(_MANUAL_INSTRUCTIONS[self._adapter_type])
            instructions.setMaximumHeight(160)
            layout.addWidget(instructions)
        else:
            self._install_result = QTextEdit()
            self._install_result.setReadOnly(True)
            self._install_result.setMaximumHeight(80)
            self._install_result.hide()
            layout.addWidget(self._install_result)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        if self._adapter_type in _MANUAL_INSTRUCTIONS:
            self._action_btn = QPushButton("保存路径")
            self._action_btn.setObjectName("primary")
            self._action_btn.setEnabled(False)
            self._action_btn.clicked.connect(self._save_and_close)
        else:
            self._action_btn = QPushButton("安装 / 更新适配器")
            self._action_btn.setObjectName("primary")
            self._action_btn.setEnabled(False)
            self._action_btn.clicked.connect(self._start_install)

        btn_row.addWidget(self._action_btn)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _browse(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, f"选择 {self._game_name} 安装目录", "C:/"
        )
        if path:
            self._path_edit.setText(path)

    def _on_path_changed(self, text: str) -> None:
        valid = is_valid_game_path(self._cfg, Path(text)) if text else False
        self._action_btn.setEnabled(valid)
        if not text:
            self._status_label.setText("")
            self._status_label.setStyleSheet("")
        elif valid:
            self._status_label.setText("✓ 路径有效")
            self._status_label.setStyleSheet("color: #5fba7d;")
        else:
            self._status_label.setText(self._invalid_hint())
            self._status_label.setStyleSheet("color: #e05555;")

    def _invalid_hint(self) -> str:
        if self._adapter_type == "cet_lua":
            return (
                f"路径无效：需包含 {self._process_name}.exe "
                "和 bin/x64/plugins/cyber_engine_tweaks/ 目录"
            )
        elif self._adapter_type == "skse_cpp":
            return f"路径无效：需包含 {self._process_name}.exe"
        else:
            return (
                f"路径无效：需包含 {self._process_name}.exe "
                "和 BepInEx/core/BepInEx.dll"
            )

    def _save_and_close(self) -> None:
        self._sm.save_game_install_path(self._process_name, self._path_edit.text())
        self.accept()

    def _start_install(self) -> None:
        self._action_btn.setEnabled(False)
        self._action_btn.setText("安装中…")
        game_path = Path(self._path_edit.text())
        bundle_dir = get_bundle_dir()

        def _run():
            errors = install_dlls(game_path, bundle_dir)
            self._signals.install_done.emit(errors)

        threading.Thread(target=_run, daemon=True).start()

    def _on_install_done(self, errors: list) -> None:
        self._install_result.show()
        if not errors:
            self._sm.save_game_install_path(self._process_name, self._path_edit.text())
            self._install_result.setPlainText("✓ 安装成功！")
            self._install_result.setStyleSheet("color: #5fba7d;")
            self._action_btn.setText("重新安装")
            self._action_btn.setEnabled(True)
        else:
            self._install_result.setPlainText("安装遇到问题：\n" + "\n".join(errors))
            self._install_result.setStyleSheet("color: #e05555;")
            self._action_btn.setText("重试")
            self._action_btn.setEnabled(True)
```

- [ ] **Step 2: Verify file syntax**

```bash
cd /Users/larr/Desktop/EntropyOrder/projects/Gaming-Camera/control_center
python -c "import gui.game_setup_dialog; print('OK')"
```

Expected: `OK` (no import errors; Qt widget instantiation not tested here since it requires a display).

- [ ] **Step 3: Commit**

```bash
git add control_center/gui/game_setup_dialog.py
git commit -m "feat: add GameSetupDialog — per-game path picker + adapter install/instructions"
```

---

### Task 4: Update MainWindow

**Files:**
- Modify: `control_center/gui/main_window.py`

This task makes four independent-but-related changes:

1. Fix the transport-server bug (`PipeServer` hardcode → `make_transport_server()`)
2. Add Setup button next to game combo
3. Disable Start when selected game not configured
4. Update Tools menu to open `GameSetupDialog` instead of `SetupWizard`

- [ ] **Step 1: Fix imports at top of `main_window.py`**

Replace:
```python
from pipe_reader import FrameBuffer, PipeServer
```
With:
```python
from pipe_reader import FrameBuffer, TransportServer
from installer import is_valid_game_path
```

- [ ] **Step 2: Fix `__init__` — rename `_pipe_server` to `_transport_server`**

In `__init__`, the class body currently has:
```python
        self._frame_buffer: FrameBuffer | None = None
        self._pipe_server: PipeServer | None = None
```

Change to:
```python
        self._frame_buffer: FrameBuffer | None = None
        self._transport_server: TransportServer | None = None
```

- [ ] **Step 3: Add Setup button and combo-change hook in `_build_ui`**

Replace the game selector block (lines 63–70 in current file):
```python
        # Game selector
        game_row = QHBoxLayout()
        game_row.addWidget(QLabel("游戏:"))
        self._game_combo = QComboBox()
        self._game_combo.setMinimumWidth(200)
        game_row.addWidget(self._game_combo)
        game_row.addStretch()
        layout.addLayout(game_row)
```

With:
```python
        # Game selector
        game_row = QHBoxLayout()
        game_row.addWidget(QLabel("游戏:"))
        self._game_combo = QComboBox()
        self._game_combo.setMinimumWidth(200)
        self._game_combo.currentIndexChanged.connect(self._update_start_state)
        game_row.addWidget(self._game_combo)
        self._btn_setup = QPushButton("⚙ 配置")
        self._btn_setup.setFixedWidth(72)
        self._btn_setup.clicked.connect(self._open_setup_dialog)
        game_row.addWidget(self._btn_setup)
        game_row.addStretch()
        layout.addLayout(game_row)
```

- [ ] **Step 4: Add `_update_start_state` and `_open_setup_dialog` methods**

Add these two methods after `_load_game_list` (after line 103):

```python
    def _update_start_state(self) -> None:
        """Enable Start only when the selected game has a valid stored install path."""
        if self._sm.state != SessionState.IDLE:
            return
        yaml_path = self._game_combo.currentData()
        if not yaml_path:
            self._btn_start.setEnabled(False)
            return
        with open(yaml_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        process_name = cfg.get("process_name", "")
        stored = self._sm.get_game_install_path(process_name)
        if stored and is_valid_game_path(cfg, Path(stored)):
            self._btn_start.setEnabled(True)
            self._lbl_status.setText("待机")
            self._lbl_status.setStyleSheet("color: gray; font-weight: bold;")
        else:
            self._btn_start.setEnabled(False)
            self._lbl_status.setText("需要配置游戏路径")
            self._lbl_status.setStyleSheet("color: orange; font-weight: bold;")

    def _open_setup_dialog(self) -> None:
        yaml_path = self._game_combo.currentData()
        if not yaml_path:
            return
        with open(yaml_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        from gui.game_setup_dialog import GameSetupDialog
        dlg = GameSetupDialog(game_config=cfg, sm=self._sm, parent=self)
        dlg.exec()
        self._update_start_state()  # re-check after setup
```

- [ ] **Step 5: Call `_update_start_state` after `_load_game_list` in `__init__`**

Change line in `__init__`:
```python
        self._load_game_list()
```
To:
```python
        self._load_game_list()
        self._update_start_state()
```

- [ ] **Step 6: Fix `_start_recording` — replace hardcoded PipeServer**

Replace:
```python
            self._pipe_server = PipeServer(self._frame_buffer)
            self._pipe_server.start()
```
With:
```python
            transport_server = self._sm.make_transport_server(self._frame_buffer)
            self._transport_server = transport_server
            transport_server.start()
```

Also replace the cleanup block in `_start_recording` exception handler:
```python
            if self._pipe_server:
                self._pipe_server.stop()
                self._pipe_server = None
```
With:
```python
            if self._transport_server:
                self._transport_server.stop()
                self._transport_server = None
```

- [ ] **Step 7: Fix `_stop_recording` — use `_transport_server`**

Replace:
```python
        if self._pipe_server:
            self._pipe_server.stop()
```
With:
```python
        if self._transport_server:
            self._transport_server.stop()
            self._transport_server = None
```

- [ ] **Step 8: Fix `_on_stats` — use `_update_start_state` on IDLE transition**

Replace the IDLE branch in `_on_stats`:
```python
    def _on_stats(self, frames: int, fps: float, elapsed: str) -> None:
        if self._sm.state == SessionState.IDLE:
            self._btn_start.setText("开始录制 (F9)")
            self._btn_start.setEnabled(True)
            self._lbl_status.setText("待机")
            self._lbl_status.setStyleSheet("color: gray; font-weight: bold;")
            return
```
With:
```python
    def _on_stats(self, frames: int, fps: float, elapsed: str) -> None:
        if self._sm.state == SessionState.IDLE:
            self._btn_start.setText("开始录制 (F9)")
            self._update_start_state()  # re-evaluate configured state
            return
```

- [ ] **Step 9: Update `_run_reinstall` in Tools menu to use `GameSetupDialog`**

Replace:
```python
    def _run_reinstall(self) -> None:
        from gui.setup_wizard import SetupWizard
        wizard = SetupWizard(self)
        wizard.exec()
        if wizard.valheim_path:
            self._sm.save_valheim_path(wizard.valheim_path)
            self._signals.log.emit(
                f"[安装] Valheim 路径已更新: {wizard.valheim_path}"
            )
```
With:
```python
    def _run_reinstall(self) -> None:
        self._open_setup_dialog()
```

- [ ] **Step 10: Run full test suite**

```bash
cd /Users/larr/Desktop/EntropyOrder/projects/Gaming-Camera/control_center
python -m pytest tests/ -v
```

Expected: all PASS (no GUI tests, but backend tests all pass).

- [ ] **Step 11: Commit**

```bash
git add control_center/gui/main_window.py
git commit -m "feat: MainWindow — Setup button, start-disable when unconfigured, fix transport server, use GameSetupDialog"
```

---

### Task 5: Remove startup wizard gate from main.py

**Files:**
- Modify: `control_center/main.py`

- [ ] **Step 1: Remove `_run_setup_wizard_if_needed` from `main.py`**

The current file has:

```python
def _run_setup_wizard_if_needed(app: QApplication, sm: SessionManager) -> None:
    """Show the install wizard if Valheim path has not been configured yet."""
    if platform.system() != "Windows":
        return
    if sm.get_valheim_path():
        return  # Already configured — skip wizard

    from gui.setup_wizard import SetupWizard
    wizard = SetupWizard()
    wizard.exec()

    if wizard.valheim_path:
        sm.save_valheim_path(wizard.valheim_path)


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("WorldEngine Data Collector")

    sm = SessionManager(SETTINGS_PATH)
    _run_setup_wizard_if_needed(app, sm)

    window = MainWindow(sm=sm)
    window.show()
    sys.exit(app.exec())
```

Replace with:

```python
def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("WorldEngine Data Collector")

    sm = SessionManager(SETTINGS_PATH)

    window = MainWindow(sm=sm)
    window.show()
    sys.exit(app.exec())
```

Also remove the now-unused `import platform` line at the top of `main.py`.

- [ ] **Step 2: Verify `main.py` syntax**

```bash
cd /Users/larr/Desktop/EntropyOrder/projects/Gaming-Camera/control_center
python -c "import main; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run full test suite**

```bash
cd /Users/larr/Desktop/EntropyOrder/projects/Gaming-Camera/control_center
python -m pytest tests/ -v
```

Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add control_center/main.py
git commit -m "refactor: remove startup wizard gate — game setup is now in-window via GameSetupDialog"
```

---

## Self-Review Checklist

**Spec coverage:**

- [x] Startup wizard gate removed from `main.py` — Task 5
- [x] Per-game install path persisted in settings — Task 2 (`game_install_paths` dict)
- [x] Backward compat for old `valheim_path` key — Task 2 `get_game_install_path("valheim")`
- [x] Setup button in MainWindow — Task 4 Step 3
- [x] Start button disabled when not configured — Task 4 Steps 4–5, 8
- [x] Start button re-checks configured state on game combo change — Task 4 Steps 3, 5
- [x] `GameSetupDialog` for all 3 adapter types — Task 3
- [x] BepInEx (Valheim): automated install — Task 3 `_start_install` / `_on_install_done`
- [x] CET/SKSE: manual instructions + path save — Task 3 `_MANUAL_INSTRUCTIONS`, `_save_and_close`
- [x] Transport server bug fixed (`PipeServer` hardcode → `make_transport_server()`) — Task 4 Steps 6–7
- [x] `_on_stats` no longer unconditionally re-enables Start — Task 4 Step 8
- [x] Tools menu "重新安装" now opens `GameSetupDialog` for selected game — Task 4 Step 9
- [x] `is_valid_game_path` covers all 3 adapter types — Task 1

**Type consistency:**

- `is_valid_game_path(game_config: dict, path: Path) -> bool` — defined Task 1, used in Task 3 `_on_path_changed` and Task 4 `_update_start_state` ✓
- `get_game_install_path(process_name: str) -> str | None` — defined Task 2, called in Task 3 `__init__` pre-fill and Task 4 `_update_start_state` ✓
- `save_game_install_path(process_name: str, path: str)` — defined Task 2, called in Task 3 `_save_and_close` and `_on_install_done` ✓
- `GameSetupDialog(game_config: dict, sm: SessionManager, parent=None)` — defined Task 3, instantiated in Task 4 `_open_setup_dialog` ✓
- `_transport_server: TransportServer | None` — defined Task 4 Step 2, assigned in Step 6, stopped in Steps 7 ✓
