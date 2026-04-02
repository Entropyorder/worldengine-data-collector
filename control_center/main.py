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
    _log_path = os.path.join(_app_dir, "app.log")
    _fault_path = os.path.join(_app_dir, "crash.log")
    # PyInstaller --onefile extracts DLLs to _MEIPASS; Qt looks for opengl32sw.dll
    # relative to the EXE, not _MEIPASS — prepend so Qt's dynamic OpenGL fallback works.
    _meipass = getattr(sys, "_MEIPASS", None)
    if _meipass:
        os.environ["PATH"] = _meipass + os.pathsep + os.environ.get("PATH", "")
else:
    _app_dir = os.path.dirname(__file__)
    SETTINGS_PATH = os.path.join(_app_dir, "config", "settings.yaml")
    _log_path = os.path.join(_app_dir, "app.log")
    _fault_path = os.path.join(_app_dir, "crash.log")

# faulthandler catches native segfaults / access violations and writes to crash.log
_fault_file = open(_fault_path, "a", encoding="utf-8")
faulthandler.enable(_fault_file)

# File log — captures startup crashes that the GUI never gets to show
logging.basicConfig(
    filename=_log_path,
    filemode="a",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    encoding="utf-8",
)
logging.info("=== WorldEngine Data Collector starting ===")
logging.info("crash.log: %s", _fault_path)

try:
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import qInstallMessageHandler, QtMsgType
    from gui.main_window import MainWindow
    from session_manager import SessionManager
except Exception:
    logging.critical("Import failed — likely missing VC++ runtime or Qt DLL:\n%s",
                     traceback.format_exc())
    raise


def _qt_log_handler(mode, context, message: str) -> None:
    """Forward all Qt internal messages to the file log before any C-level abort."""
    if mode == QtMsgType.QtFatalMsg:
        logging.critical("Qt FATAL [%s:%s %s]: %s",
                         context.file, context.line, context.function, message)
        logging.shutdown()   # flush to disk before Qt calls abort()
    elif mode == QtMsgType.QtCriticalMsg:
        logging.error("Qt Critical: %s", message)
    elif mode == QtMsgType.QtWarningMsg:
        logging.warning("Qt Warning: %s", message)
    else:
        logging.debug("Qt: %s", message)


def main() -> None:
    logging.info("Creating QApplication")
    app = QApplication(sys.argv)
    # Install handler immediately so all Qt warnings/fatals go to the log file
    qInstallMessageHandler(_qt_log_handler)
    logging.info("QApplication created OK — Qt message handler installed")
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
        logging.critical("show() raised Python exception:\n%s", traceback.format_exc())
        raise
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        logging.critical("Unhandled exception:\n%s", traceback.format_exc())
        raise
