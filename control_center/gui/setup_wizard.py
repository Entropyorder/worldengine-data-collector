# control_center/gui/setup_wizard.py
"""
SetupWizard — first-launch installer dialog.

Shows automatically when valheim_path is not in settings.yaml.
Can also be triggered manually from the main window menu.
"""
from __future__ import annotations
import logging
import threading
from pathlib import Path

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFileDialog, QStackedWidget, QWidget, QTextEdit,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

from installer import (
    detect_valheim_path,
    is_valid_valheim_path,
    install_dlls,
    get_bundle_dir,
)

logger = logging.getLogger(__name__)

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


class _Signals(QObject):
    install_done = pyqtSignal(list)  # list[str] of errors; empty = success


class SetupWizard(QDialog):
    """
    Multi-page install wizard.  Call exec() to show it modally.
    After exec(), check wizard.valheim_path (str | None) to get the
    path the user confirmed, or None if they cancelled.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("WorldEngine Data Collector — 初始安装")
        self.setMinimumSize(520, 360)
        self.setStyleSheet(_DARK_STYLE)

        self.valheim_path: str | None = None  # set on successful install

        self._signals = _Signals()
        self._signals.install_done.connect(self._on_install_done)

        self._stack = QStackedWidget()
        layout = QVBoxLayout(self)
        layout.addWidget(self._stack)

        self._stack.addWidget(self._build_welcome_page())    # 0
        self._stack.addWidget(self._build_detect_page())     # 1
        self._stack.addWidget(self._build_installing_page()) # 2
        self._stack.addWidget(self._build_result_page())     # 3

    # ── Page builders ─────────────────────────────────────────────────────

    def _build_welcome_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(16)

        title = QLabel("欢迎使用 WorldEngine Data Collector")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        body = QLabel(
            "本向导将自动把录制组件安装到你的 Valheim 目录中。\n\n"
            "安装内容：\n"
            "  • WorldEngineCollector.dll  →  BepInEx/plugins/\n"
            "  • dx_capture.dll            →  Valheim 根目录\n"
            "  • FFmpeg 运行库 (av*.dll / sw*.dll)  →  Valheim 根目录\n\n"
            "前提条件：Valheim 已安装且 BepInEx 5.4.x 已安装。"
        )
        body.setWordWrap(True)
        layout.addWidget(body)
        layout.addStretch()

        btn_next = QPushButton("下一步 →")
        btn_next.setObjectName("primary")
        btn_next.clicked.connect(lambda: self._go_to_detect())
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn_next)
        layout.addLayout(btn_row)
        return page

    def _build_detect_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        layout.addWidget(QLabel("Valheim 安装路径"))

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("自动检测中…")
        self._path_edit.textChanged.connect(self._on_path_changed)
        layout.addWidget(self._path_edit)

        self._detect_label = QLabel("")
        self._detect_label.setWordWrap(True)
        layout.addWidget(self._detect_label)

        browse_btn = QPushButton("浏览…")
        browse_btn.clicked.connect(self._browse_path)

        self._install_btn = QPushButton("安装")
        self._install_btn.setObjectName("primary")
        self._install_btn.setEnabled(False)
        self._install_btn.clicked.connect(self._start_install)

        btn_row = QHBoxLayout()
        btn_row.addWidget(browse_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._install_btn)
        layout.addLayout(btn_row)
        layout.addStretch()
        return page

    def _build_installing_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._installing_label = QLabel("正在安装…")
        self._installing_label.setStyleSheet("font-size: 14px;")
        layout.addWidget(self._installing_label)
        return page

    def _build_result_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        self._result_title = QLabel("")
        self._result_title.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(self._result_title)

        self._result_detail = QTextEdit()
        self._result_detail.setReadOnly(True)
        self._result_detail.setMaximumHeight(120)
        layout.addWidget(self._result_detail)
        layout.addStretch()

        self._finish_btn = QPushButton("完成")
        self._finish_btn.setObjectName("primary")
        self._finish_btn.clicked.connect(self.accept)

        self._retry_btn = QPushButton("重试")
        self._retry_btn.clicked.connect(lambda: self._stack.setCurrentIndex(1))
        self._retry_btn.hide()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self._retry_btn)
        btn_row.addWidget(self._finish_btn)
        layout.addLayout(btn_row)
        return page

    # ── Logic ─────────────────────────────────────────────────────────────

    def _go_to_detect(self) -> None:
        self._stack.setCurrentIndex(1)
        def _detect():
            found = detect_valheim_path()
            if found:
                self._path_edit.setText(str(found))
                self._detect_label.setText("✓ 自动检测到 Valheim")
                self._detect_label.setStyleSheet("color: #5fba7d;")
            else:
                self._detect_label.setText(
                    '未能自动检测到 Valheim，请点击\u201c浏览\u201d手动选择安装目录'
                )
                self._detect_label.setStyleSheet("color: #f0a04b;")

        threading.Thread(target=_detect, daemon=True).start()

    def _browse_path(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self, "选择 Valheim 安装目录", "C:/"
        )
        if path:
            self._path_edit.setText(path)

    def _on_path_changed(self, text: str) -> None:
        valid = is_valid_valheim_path(Path(text)) if text else False
        self._install_btn.setEnabled(valid)
        if text and not valid:
            self._detect_label.setText(
                "路径无效：需包含 valheim.exe 和 BepInEx/core/BepInEx.dll"
            )
            self._detect_label.setStyleSheet("color: #e05555;")
        elif valid:
            self._detect_label.setText("✓ 路径有效")
            self._detect_label.setStyleSheet("color: #5fba7d;")

    def _start_install(self) -> None:
        valheim_path = Path(self._path_edit.text())
        bundle_dir = get_bundle_dir()
        self._stack.setCurrentIndex(2)

        def _run():
            logger.info("Installing DLLs: valheim=%s bundle=%s", valheim_path, bundle_dir)
            errors = install_dlls(valheim_path, bundle_dir)
            self._signals.install_done.emit(errors)

        threading.Thread(target=_run, daemon=True).start()

    def _on_install_done(self, errors: list) -> None:
        self._stack.setCurrentIndex(3)
        if not errors:
            self.valheim_path = self._path_edit.text()
            self._result_title.setText("✓ 安装成功！")
            self._result_title.setStyleSheet(
                "font-size: 15px; font-weight: bold; color: #5fba7d;"
            )
            self._result_detail.setText(
                "所有组件已安装完毕。\n"
                "现在启动 Valheim，等待 BepInEx 控制台显示：\n"
                "  [WorldEngine] dx_capture.dll loaded\n"
                "然后返回本界面按 F9 开始录制。"
            )
            self._retry_btn.hide()
            self._finish_btn.setText("开始使用 →")
        else:
            self._result_title.setText("✗ 安装遇到问题")
            self._result_title.setStyleSheet(
                "font-size: 15px; font-weight: bold; color: #e05555;"
            )
            self._result_detail.setText("\n".join(errors))
            self._retry_btn.show()
            self._finish_btn.setText("忽略并继续")
