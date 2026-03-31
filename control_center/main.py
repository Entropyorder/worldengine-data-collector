import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import QApplication
from gui.main_window import MainWindow
from session_manager import SessionManager

if getattr(sys, "frozen", False):
    _app_dir = os.path.join(
        os.environ.get("APPDATA", os.path.expanduser("~")),
        "WorldEngineDataCollector",
    )
    os.makedirs(_app_dir, exist_ok=True)
    SETTINGS_PATH = os.path.join(_app_dir, "settings.yaml")
else:
    SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "config", "settings.yaml")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("WorldEngine Data Collector")

    sm = SessionManager(SETTINGS_PATH)

    window = MainWindow(sm=sm)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
