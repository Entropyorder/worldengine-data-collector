from __future__ import annotations
import os
import threading
import yaml
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox, QLabel, QGroupBox, QStatusBar,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt6.QtGui import QKeySequence, QShortcut

from gui.session_log import SessionLog
from session_manager import SessionManager, SessionState
from pipe_reader import FrameBuffer, PipeServer
from osd_bridge import OsdBridge
from post_processor import process_session
from metadata_collector import collect_and_write


class _Signals(QObject):
    log = pyqtSignal(str)
    stats_updated = pyqtSignal(int, float, str)  # frames, fps, elapsed


class MainWindow(QMainWindow):
    GAMES_CONFIG_DIR = Path(__file__).parent.parent / "config" / "games"
    SETTINGS_PATH    = Path(__file__).parent.parent / "config" / "settings.yaml"

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("WorldEngine Data Collector")
        self.setMinimumSize(640, 480)

        self._sm = SessionManager(str(self.SETTINGS_PATH))
        self._osd = OsdBridge()
        self._frame_buffer: FrameBuffer | None = None
        self._pipe_server: PipeServer | None = None
        self._signals = _Signals()
        self._signals.log.connect(self._on_log)
        self._signals.stats_updated.connect(self._on_stats)
        self._start_time: datetime | None = None

        self._build_ui()
        self._load_game_list()
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._poll_stats)

        # F9 hotkey
        shortcut = QShortcut(QKeySequence("F9"), self)
        shortcut.activated.connect(self._toggle_recording)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Game selector
        game_row = QHBoxLayout()
        game_row.addWidget(QLabel("游戏:"))
        self._game_combo = QComboBox()
        self._game_combo.setMinimumWidth(200)
        game_row.addWidget(self._game_combo)
        game_row.addStretch()
        layout.addLayout(game_row)

        # Stats
        stats_group = QGroupBox("当前状态")
        stats_layout = QHBoxLayout(stats_group)
        self._lbl_frames = QLabel("帧数: 0")
        self._lbl_fps    = QLabel("游戏FPS: --")
        self._lbl_time   = QLabel("时长: 00:00")
        self._lbl_status = QLabel("待机")
        self._lbl_status.setStyleSheet("color: gray; font-weight: bold;")
        for w in [self._lbl_frames, self._lbl_fps, self._lbl_time, self._lbl_status]:
            stats_layout.addWidget(w)
        layout.addWidget(stats_group)

        # Log
        self._log = SessionLog()
        layout.addWidget(self._log)

        # Buttons
        btn_row = QHBoxLayout()
        self._btn_start = QPushButton("开始录制 (F9)")
        self._btn_start.setMinimumHeight(40)
        self._btn_start.clicked.connect(self._toggle_recording)
        btn_row.addWidget(self._btn_start)
        layout.addLayout(btn_row)

        self.setStatusBar(QStatusBar())

    def _load_game_list(self) -> None:
        self._game_combo.clear()
        for yaml_file in sorted(self.GAMES_CONFIG_DIR.glob("*.yaml")):
            with open(yaml_file, encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            self._game_combo.addItem(cfg.get("game_name", yaml_file.stem), str(yaml_file))

    def _toggle_recording(self) -> None:
        if self._sm.state == SessionState.IDLE:
            self._start_recording()
        elif self._sm.state == SessionState.RECORDING:
            self._stop_recording()

    def _start_recording(self) -> None:
        yaml_path = self._game_combo.currentData()
        if not yaml_path:
            self._signals.log.emit("[WARN] 未选择游戏，请先选择游戏配置")
            return
        try:
            self._sm.load_game(yaml_path)
            session_dir = self._sm.start_session()

            raw_path = session_dir / "raw_frames.jsonl"
            self._frame_buffer = FrameBuffer(str(raw_path))
            self._frame_buffer.open()

            self._pipe_server = PipeServer(self._frame_buffer)
            self._pipe_server.start()
        except Exception as e:
            # Clean up any resources that were opened before the failure
            if self._frame_buffer:
                self._frame_buffer.close()
                self._frame_buffer = None
            if self._pipe_server:
                self._pipe_server.stop()
                self._pipe_server = None
            # Reset FSM if session was started
            if self._sm.state == SessionState.RECORDING:
                self._sm.stop_session()
                self._sm.finish_processing()
            self._signals.log.emit(f"[ERROR] 录制启动失败: {e}")
            return

        if self._osd.open():
            self._osd.set_session(session_dir.name, str(session_dir))
            self._osd.set_capture_active(True)
        else:
            self._signals.log.emit("[WARN] 无法连接 dx_capture.dll 共享内存，DLL 是否已加载？")

        self._start_time = datetime.now()
        self._timer.start()
        self._btn_start.setText("停止录制 (F9)")
        self._lbl_status.setText("录制中")
        self._lbl_status.setStyleSheet("color: red; font-weight: bold;")
        self._signals.log.emit(f"[录制开始] {session_dir.name}")

    def _stop_recording(self) -> None:
        self._osd.set_capture_active(False)
        self._osd.close()
        if self._pipe_server:
            self._pipe_server.stop()
        if self._frame_buffer:
            self._frame_buffer.close()
        self._timer.stop()
        self._sm.stop_session()
        self._btn_start.setText("处理中…")
        self._btn_start.setEnabled(False)
        self._lbl_status.setText("处理中")
        self._lbl_status.setStyleSheet("color: orange; font-weight: bold;")
        self._signals.log.emit("[录制停止] 开始后处理…")

        session_dir = str(self._sm.session_dir)
        yaml_path = self._game_combo.currentData()

        def _process():
            try:
                process_session(session_dir)
                collect_and_write(
                    session_dir, yaml_path,
                    str(Path(session_dir) / "raw_frames.jsonl"),
                )
                self._signals.log.emit("[完成] 所有文件已生成")
            except Exception as e:
                self._signals.log.emit(f"[ERROR] 后处理失败: {e}")
            finally:
                self._sm.finish_processing()
                self._signals.stats_updated.emit(0, 0.0, "00:00")

        threading.Thread(target=_process, daemon=True).start()

    def _poll_stats(self) -> None:
        if not self._frame_buffer or not self._start_time:
            return
        frames = self._frame_buffer.frame_count
        fps = self._osd.read_game_fps() if self._osd.is_open else 0.0
        elapsed = datetime.now() - self._start_time
        mins, secs = divmod(int(elapsed.total_seconds()), 60)
        self._signals.stats_updated.emit(frames, fps, f"{mins:02d}:{secs:02d}")

    def _on_log(self, msg: str) -> None:
        self._log.append_line(msg)

    def _on_stats(self, frames: int, fps: float, elapsed: str) -> None:
        if self._sm.state == SessionState.IDLE:
            self._btn_start.setText("开始录制 (F9)")
            self._btn_start.setEnabled(True)
            self._lbl_status.setText("待机")
            self._lbl_status.setStyleSheet("color: gray; font-weight: bold;")
            return
        self._lbl_frames.setText(f"帧数: {frames}")
        self._lbl_fps.setText(f"游戏FPS: {fps:.1f}")
        self._lbl_time.setText(f"时长: {elapsed}")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self._sm.state == SessionState.RECORDING:
            self._stop_recording()
        event.accept()
