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
            self._signals.install_done.connect(self._on_install_done)

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
            try:
                errors = install_dlls(game_path, bundle_dir)
            except Exception as exc:
                errors = [f"安装异常: {exc}"]
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
