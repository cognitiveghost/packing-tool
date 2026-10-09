"""Every frame of the UI refresh, at both sizes, in both themes.

    .venv/bin/python scripts/render_all.py

Runs the five render scripts at 1366x768 and at 1920x1080 into
docs/design/ui-refresh/renders/final/<size>/. Each script is its own process:
each builds its own QApplication and redirects its own QSettings.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = (
    "render_shell.py",        # 2a-2e
    "render_app_pages.py",    # 3a-3g, 4a-4c, 5a, 5b
    "render_packer_mode.py",  # 6a-6j
    "render_sessions.py",     # 7a-7h, 8a-8f
    "render_setup.py",        # w-*, m-*
)
SIZES = ("1366x768", "1920x1080")


def main() -> int:
    for size in SIZES:
        for script in SCRIPTS:
            print(f"--- {script} at {size}", flush=True)
            subprocess.run([sys.executable, str(HERE / script), "--size", size], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
