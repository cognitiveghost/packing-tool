"""Packer Assistant — entry point."""
import sys
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from gui.main_window import DEFAULT_CONFIG_PATH, MainWindow
from gui.theme import load_saved_theme
from packing_tool import APP_NAME
from shared import i18n
from shared.icons import brand_icon
from shared.logger import install_crash_logging

APP_ROOT = Path(__file__).resolve().parent


def apply_saved_language() -> str:
    code = str(QSettings("PackingTool", "Language").value("language", i18n.DEFAULT_LANGUAGE))
    i18n.set_language(code, i18n.catalogue_files(APP_ROOT, code))
    return i18n.language()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument(
        '--config',
        default=DEFAULT_CONFIG_PATH,
        metavar='PATH',
        help=f'Path to config file (default: {DEFAULT_CONFIG_PATH}). '
             'Use config.dev.ini for local development / mock server.'
    )
    args = parser.parse_args()

    install_crash_logging()

    app = QApplication(sys.argv)
    apply_saved_language()
    app.setWindowIcon(brand_icon("packer-assistant"))
    load_saved_theme(app)
    window = MainWindow(config_path=args.config)
    window.show()
    sys.exit(app.exec())
