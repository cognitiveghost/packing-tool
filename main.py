"""Packer Assistant — entry point."""
import sys

from PySide6.QtWidgets import QApplication

from gui.main_window import DEFAULT_CONFIG_PATH, MainWindow
from gui.theme import load_saved_theme
from packing_tool import APP_NAME
from shared.icons import brand_icon
from shared.logger import install_crash_logging

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
    app.setWindowIcon(brand_icon("packer-assistant"))
    load_saved_theme(app)
    window = MainWindow(config_path=args.config)
    window.show()
    sys.exit(app.exec())
