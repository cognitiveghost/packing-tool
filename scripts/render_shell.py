"""Offscreen renders of the shell, mockup frames 2a-2e, in both themes.

    .venv/bin/python scripts/render_shell.py [output dir] [--size WIDTHxHEIGHT]

Writes <frame>-<theme>.png at the size given (1366x768 by default), by default
into docs/design/ui-refresh/renders/final/<size>/. Runs against a
throwaway server with synthetic data and its own QSettings, so it touches
neither the file server nor this PC's saved theme or client.

Offscreen Qt uses a fallback font, not Segoe UI: glyph widths differ a little
from Windows.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from render_args import parse_args

SERVER_LABEL = r"\\fs01\packer"

ORDERS = [
    (f"#104{n:02d}", courier, [
        {"sku": sku, "quantity": qty, "product_name": name},
        {"sku": "LIP-RED", "quantity": 1, "product_name": "Lip balm, red"},
    ])
    for n, (courier, sku, qty, name) in enumerate([
        ("DHL", "CRM-50ML", 2, "Day cream 50 ml"),
        ("DHL", "SER-30ML", 1, "Vitamin C serum 30 ml"),
        ("DPD", "SPF-50", 3, "Sunscreen SPF 50"),
        ("DPD", "LST-07", 2, "Lipstick, shade 07"),
        ("Speedy", "MSK-5PK", 1, "Sheet mask, 5 pack"),
        ("Speedy", "CLN-200", 1, "Gel cleanser 200 ml"),
    ], start=1)
]


def build(tmp: Path):
    from gui.main_window import MainWindow
    from packing_tool.packer_logic import PackerLogic
    from packing_tool.profile_manager import ProfileManager

    server = tmp / "server"
    server.mkdir()
    config = tmp / "config.ini"
    config.write_text(
        "[Network]\n"
        f"FileServerPath = {server}\n"
        "ConnectionTimeout = 5\n"
        f"LocalCachePath = {tmp / 'cache'}\n"
        "[Logging]\nLogLevel = WARNING\nLogRetentionDays = 30\nMaxLogSizeMB = 10\n",
        encoding="utf-8",
    )
    seed = ProfileManager(config_path=str(config))
    seed.create_client_profile("ACME", "Acme Cosmetics")
    seed.create_client_profile("BOREAL", "Boreal Outdoor")

    session_dir = server / "Sessions" / "CLIENT_ACME" / "2026-10-07_1"
    (session_dir / "packing_lists").mkdir(parents=True)
    work_dir = session_dir / "packing" / "Morning_wave"
    work_dir.mkdir(parents=True)
    list_path = session_dir / "packing_lists" / "Morning_wave.json"
    list_path.write_text(json.dumps({
        "list_name": "Morning_wave",
        "created_at": "2026-10-07T08:00:00+00:00",
        "orders": [
            {"order_number": number, "courier": courier, "items": items}
            for number, courier, items in ORDERS
        ],
    }), encoding="utf-8")

    window = MainWindow(skip_worker_selection=True, config_path=str(config))
    window.current_worker_name = "Desislava Ilieva"
    window.sidebar.set_worker(window.current_worker_name)

    def open_session():
        window.client_combo.setCurrentIndex(window.client_combo.findData("ACME"))
        logic = PackerLogic(
            client_id="ACME", profile_manager=window.profile_manager,
            work_dir=str(work_dir),
        )
        logic.load_packing_list_json(list_path)
        window.logic = logic
        window.current_session_path = session_dir
        window.current_packing_list = "Morning_wave"
        window._push_pages()
        window.enable_packing_mode()
        return logic

    return window, open_session


def main(argv: list[str]) -> int:
    out, width, height = parse_args(argv)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        # Before any QSettings is made: keep this PC's saved theme, client and
        # server path. Both formats, as tests/conftest.py does: QSettings(org,
        # app) is NativeFormat, and a saved server path outranks config.ini.
        for fmt in (QSettings.NativeFormat, QSettings.IniFormat):
            QSettings.setPath(fmt, QSettings.UserScope, str(tmp / "settings"))
        os.environ.pop("FULFILLMENT_SERVER_PATH", None)

        app = QApplication.instance() or QApplication(sys.argv[:1])
        from gui.theme import apply_theme, load_saved_theme

        load_saved_theme(app)
        window, open_session = build(tmp)
        base = Path(window.profile_manager.base_path).resolve()
        if not base.is_relative_to(tmp.resolve()):
            raise RuntimeError(f"refusing to render against {base}: not the temp server")
        window.show()
        # The card and the banner show the mockup's path, not the temp folder.
        real_set = window.sidebar.set_connection
        window.sidebar.set_connection = lambda state, _path: real_set(state, SERVER_LABEL)
        real_outage = window.connection_banner.set_outage
        window.connection_banner.set_outage = (
            lambda _path, since: real_outage(SERVER_LABEL, since)
        )

        bridge = window.session_tabs.bridge

        def settle() -> None:
            # The pages are a web document: grab only after it has drawn what
            # it was last sent.
            deadline = time.monotonic() + 20
            while bridge.painted_revision < bridge.revision:
                if time.monotonic() > deadline:
                    raise RuntimeError("the page never painted; is QtWebEngine working?")
                app.processEvents()
                time.sleep(0.01)
            for _ in range(10):
                app.processEvents()
                time.sleep(0.02)

        def shoot(name: str) -> None:
            for theme in ("light", "dark"):
                apply_theme(app, theme)
                window.resize(width, height)
                settle()
                target = out / f"{name.format(theme=theme)}.png"
                if not window.grab().save(str(target)):
                    raise OSError(f"could not write {target}")
                print(target)

        # 2a: no client.
        window.client_combo.setCurrentIndex(-1)
        window._set_connection_state("ok")
        shoot("2a-{theme}")

        # 2b: session open.
        logic = open_session()
        shoot("2b-{theme}")

        # 2c: collapsed rail.
        window._set_sidebar_expanded(False)
        shoot("2c-{theme}")
        window._set_sidebar_expanded(True)

        # 2d: reconnecting (in the app this shows only while a check runs).
        window._set_connection_state("checking")
        shoot("2d-{theme}")

        # 2e: server unreachable.
        window._connection_down_since = "14:02"
        window._set_connection_state("down")
        shoot("2e-{theme}")

        logic.close()
        window.logic = None
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
