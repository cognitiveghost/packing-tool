"""Packer's Assistant — entry point."""
import sys

from PySide6.QtWidgets import QApplication

from gui.main_window import DEFAULT_CONFIG_PATH, MainWindow
from gui.theme import load_saved_theme

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Packer's Assistant")
    parser.add_argument(
        '--config',
        default=DEFAULT_CONFIG_PATH,
        metavar='PATH',
        help=f'Path to config file (default: {DEFAULT_CONFIG_PATH}). '
             'Use config.dev.ini for local development / mock server.'
    )
    args = parser.parse_args()

    app = QApplication(sys.argv)
    load_saved_theme(app)
    window = MainWindow(config_path=args.config)
    window.show()
    sys.exit(app.exec())
