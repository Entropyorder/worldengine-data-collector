import sys
import os
import platform

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


if __name__ == "__main__":
    main()
