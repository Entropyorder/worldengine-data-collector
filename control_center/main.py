import sys
import os
import logging
import traceback

sys.path.insert(0, os.path.dirname(__file__))

if getattr(sys, "frozen", False):
    _app_dir = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "WorldEngineDataCollector",
    )
    os.makedirs(_app_dir, exist_ok=True)
    SETTINGS_PATH = os.path.join(_app_dir, "settings.yaml")
    _log_path = os.path.join(_app_dir, "app.log")
else:
    _app_dir = os.path.dirname(__file__)
    SETTINGS_PATH = os.path.join(_app_dir, "config", "settings.yaml")
    _log_path = os.path.join(_app_dir, "app.log")

# File log — captures startup crashes that the GUI never gets to show
logging.basicConfig(
    filename=_log_path,
    filemode="a",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    encoding="utf-8",
)
logging.info("=== WorldEngine Data Collector starting ===")

try:
    from PyQt6.QtWidgets import QApplication
    from gui.main_window import MainWindow
    from session_manager import SessionManager
except Exception:
    logging.critical("Import failed — likely missing VC++ runtime or Qt DLL:\n%s",
                     traceback.format_exc())
    raise


def main() -> None:
    logging.info("Creating QApplication")
    app = QApplication(sys.argv)
    logging.info("QApplication created OK")
    app.setApplicationName("WorldEngine Data Collector")

    logging.info("Creating SessionManager")
    sm = SessionManager(SETTINGS_PATH)
    logging.info("SessionManager OK")

    logging.info("Creating MainWindow")
    window = MainWindow(sm=sm)
    logging.info("MainWindow OK — calling show()")
    window.show()
    logging.info("show() returned — entering event loop")
    sys.exit(app.exec())


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        logging.critical("Unhandled exception:\n%s", traceback.format_exc())
        raise
