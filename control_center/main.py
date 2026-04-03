import sys
import os
import logging
import traceback
import faulthandler

sys.path.insert(0, os.path.dirname(__file__))

if getattr(sys, "frozen", False):
    _app_dir = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "WorldEngineDataCollector",
    )
    os.makedirs(_app_dir, exist_ok=True)
    SETTINGS_PATH = os.path.join(_app_dir, "settings.yaml")
    _log_path  = os.path.join(_app_dir, "app.log")
    _fault_path = os.path.join(_app_dir, "crash.log")
    # PyInstaller --onefile extracts to _MEIPASS; prepend so Qt finds opengl32sw.dll
    _meipass = getattr(sys, "_MEIPASS", None)
    if _meipass:
        os.environ["PATH"] = _meipass + os.pathsep + os.environ.get("PATH", "")
else:
    _app_dir = os.path.dirname(__file__)
    SETTINGS_PATH = os.path.join(_app_dir, "config", "settings.yaml")
    _log_path  = os.path.join(_app_dir, "app.log")
    _fault_path = os.path.join(_app_dir, "crash.log")

# ── faulthandler: catches native segfault/access violation ────────────────────
_fault_file = open(_fault_path, "a", encoding="utf-8")
faulthandler.enable(_fault_file)

# ── File log ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    filename=_log_path,
    filemode="a",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    encoding="utf-8",
)

# ── Qt verbose environment flags (must be set BEFORE QApplication) ────────────
# QT_DEBUG_PLUGINS=1   → logs every DLL Qt tries to load (plugins, renderers)
# QT_LOGGING_RULES     → enable all Qt debug categories
# QT_QPA_PLATFORM      → nodirectwrite avoids qFatal in DirectWrite font engine
os.environ["QT_DEBUG_PLUGINS"]  = "1"
os.environ["QT_LOGGING_RULES"]  = "*.debug=true"
os.environ.setdefault("QT_QPA_PLATFORM", "windows:nodirectwrite")

logging.info("=== WorldEngine Data Collector starting ===")
logging.info("app_dir=%s  meipass=%s", _app_dir, getattr(sys, "_MEIPASS", None))
logging.info("PATH[0]=%s", os.environ["PATH"].split(os.pathsep)[0])
logging.info("QT_QPA_PLATFORM=%s", os.environ.get("QT_QPA_PLATFORM"))

# Pre-initialize OLE in STA mode before Qt does it, to avoid RegisterDragDrop
# crash on machines where COM isn't set up correctly by the time Qt calls it.
if sys.platform == "win32":
    import ctypes
    hr = ctypes.windll.ole32.OleInitialize(None)
    logging.info("OleInitialize hr=0x%08x", hr & 0xFFFFFFFF)

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
    from gui.main_window import MainWindow
    from session_manager import SessionManager
except Exception:
    logging.critical("Import failed:\n%s", traceback.format_exc())
    raise


# ── Qt message handler: writes EVERY Qt message to disk with fsync ────────────
# Uses direct file I/O + os.fsync so data is on disk before FatalAppExit() fires.
_log_fd = open(_log_path, "a", encoding="utf-8", buffering=1)  # line-buffered

def _qt_log_handler(mode, context, message: str) -> None:
    level = {
        QtMsgType.QtDebugMsg:    "QT_DEBUG",
        QtMsgType.QtInfoMsg:     "QT_INFO",
        QtMsgType.QtWarningMsg:  "QT_WARN",
        QtMsgType.QtCriticalMsg: "QT_CRIT",
        QtMsgType.QtFatalMsg:    "QT_FATAL",
    }.get(mode, "QT_?")
    line = f"{level} [{context.file}:{context.line}]: {message}\n"
    _log_fd.write(line)
    _log_fd.flush()
    os.fsync(_log_fd.fileno())   # physical disk write before abort() fires


def main() -> None:
    logging.info("Creating QApplication")
    app = QApplication(sys.argv)
    qInstallMessageHandler(_qt_log_handler)
    logging.info("QApplication OK")
    app.setApplicationName("WorldEngine Data Collector")

    logging.info("Creating SessionManager")
    sm = SessionManager(SETTINGS_PATH)
    logging.info("SessionManager OK")

    logging.info("Creating MainWindow")
    window = MainWindow(sm=sm)
    logging.info("MainWindow OK — calling show()")
    try:
        window.show()
        logging.info("show() returned — entering event loop")
    except Exception:
        logging.critical("show() raised:\n%s", traceback.format_exc())
        raise
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        logging.critical("Unhandled exception:\n%s", traceback.format_exc())
        raise
