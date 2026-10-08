"""Offscreen renders of Packing and Statistics, mockup frames 3a-3g, 4a-4c, 5a, 5b.

    .venv/bin/python scripts/render_app_pages.py [output dir]

Writes <frame>-<theme>.png, by default into
docs/design/ui-refresh/renders/phase3/: 3a-3g and 4a-4c at 1366x768, 5a and 5b
at 1920x1080, in both themes. It builds a MainWindow against a throwaway
server with a synthetic 120-order list, and its own QSettings, so it touches
neither the file server nor this PC's saved theme, client or server path.

Offscreen Qt uses a fallback font for the Qt chrome: glyph widths differ a
little from Windows.
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

DEFAULT_OUT = ROOT / "docs" / "design" / "ui-refresh" / "renders" / "phase3"
SESSION_ID = "2026-10-07_1"
LIST_NAME = "Morning_wave"

CATALOGUE = [
    ("CLN-200", "Gel cleanser 200 ml"), ("TNR-150", "Toner 150 ml"),
    ("SER-30ML", "Vitamin C serum 30 ml"), ("HYA-15ML", "Hyaluronic serum 15 ml"),
    ("DAY-50ML", "Day cream 50 ml"), ("NGT-50ML", "Night cream 50 ml"),
    ("CRM-15ML", "Eye cream 15 ml"), ("SPF-50", "Sunscreen SPF 50"),
    ("LIP-RED", "Lip balm, red"), ("LIP-MNT", "Lip balm, mint"),
    ("LST-07", "Lipstick, shade 07"), ("LST-11", "Lipstick, shade 11"),
    ("NPL-04", "Nail polish, shade 04"), ("MSK-5PK", "Sheet mask, 5 pack"),
    ("OIL-100", "Body oil 100 ml"), ("BDL-400", "Body lotion 400 ml"),
    ("HND-75", "Hand cream 75 ml"), ("SHM-500", "Shampoo 500 ml"),
    ("CND-500", "Conditioner 500 ml"), ("EDT-FIG", "Fragrance mist, fig"),
    ("PAL-NUD", "Eyeshadow palette, nude"), ("GFT-L", "Gift box, large"),
    ("BRS-FND", "Brush, foundation"), ("MSC-BLK", "Mascara, black"),
]
COURIERS = ["DHL", "DPD", "Speedy"]


def synthetic_orders() -> list[dict]:
    """120 orders of 1 to 4 lines, the same every run."""
    orders = []
    for index in range(120):
        lines = 1 + (index * 7) % 4
        items = []
        for line in range(lines):
            sku, name = CATALOGUE[(index * 5 + line * 3) % len(CATALOGUE)]
            if any(item["sku"] == sku for item in items):
                continue
            items.append(
                {"sku": sku, "product_name": name, "quantity": 1 + (index + line) % 3 // 2}
            )
        orders.append(
            {
                "order_number": f"#{10400 + index}",
                "courier": COURIERS[index % 3],
                "items": items,
            }
        )
    return orders


def main(argv: list[str]) -> int:
    out = Path(argv[0]) if argv else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        # Before any QSettings is made, and both formats, as tests/conftest.py
        # does: QSettings(org, app) is NativeFormat, and a saved server path
        # outranks config.ini.
        for fmt in (QSettings.NativeFormat, QSettings.IniFormat):
            QSettings.setPath(fmt, QSettings.UserScope, str(tmp / "settings"))
        os.environ.pop("FULFILLMENT_SERVER_PATH", None)

        app = QApplication.instance() or QApplication(sys.argv[:1])
        from gui.app_bridge import session_payload, start_failure
        from gui.main_window import PAGE_PACKING, PAGE_STATISTICS, MainWindow
        from gui.theme import apply_theme, load_saved_theme
        from packing_tool.exceptions import PackingListInvalidError
        from packing_tool.packer_logic import PackerLogic
        from packing_tool.profile_manager import ProfileManager

        load_saved_theme(app)

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

        session_dir = server / "Sessions" / "CLIENT_ACME" / SESSION_ID
        (session_dir / "packing_lists").mkdir(parents=True)
        work_dir = session_dir / "packing" / LIST_NAME
        work_dir.mkdir(parents=True)
        list_path = session_dir / "packing_lists" / f"{LIST_NAME}.json"
        list_path.write_text(
            json.dumps(
                {
                    "list_name": LIST_NAME,
                    "created_at": "2026-10-07T08:00:00+00:00",
                    "orders": synthetic_orders(),
                }
            ),
            encoding="utf-8",
        )

        window = MainWindow(skip_worker_selection=True, config_path=str(config))
        base = Path(window.profile_manager.base_path).resolve()
        if not base.is_relative_to(tmp.resolve()):
            raise RuntimeError(f"refusing to render against {base}: not the temp server")
        window.current_worker_name = "Desislava Ilieva"
        window.sidebar.set_worker(window.current_worker_name)
        # The connection card shows the mockup's path, not the temp folder.
        real_set = window.sidebar.set_connection
        window.sidebar.set_connection = lambda state, _path: real_set(state, r"\\fs01\packer")
        window._set_connection_state("ok")
        window.resize(1366, 768)
        window.show()
        pages = window.session_tabs
        bridge = pages.bridge

        def settle() -> None:
            deadline = time.monotonic() + 20
            while bridge.painted_revision < bridge.revision:
                if time.monotonic() > deadline:
                    raise RuntimeError("the page never painted; is QtWebEngine working?")
                app.processEvents()
                time.sleep(0.01)
            for _ in range(10):
                app.processEvents()
                time.sleep(0.02)

        def shoot(name: str, width: int = 1366, height: int = 768) -> None:
            for theme in ("light", "dark"):
                apply_theme(app, theme)
                window.resize(width, height)
                settle()
                target = out / f"{name}-{theme}.png"
                if not window.grab().save(str(target)):
                    raise OSError(f"could not write {target}")
                print(target)

        def open_session(complete: bool = False) -> PackerLogic:
            logic = PackerLogic(
                client_id="ACME", profile_manager=window.profile_manager,
                work_dir=str(work_dir),
            )
            logic.load_packing_list_json(list_path)
            numbers = list(logic.orders_data)
            state = logic.session_packing_state
            if complete:
                state["completed_orders"] = list(numbers)
            else:
                state["completed_orders"] = numbers[:38]
                state["skipped_orders"] = [numbers[44], numbers[57], numbers[71]]
                for number in (numbers[40], numbers[41]):
                    entries = logic._fresh_order_state(logic.orders_data[number]["items"])
                    entries[0]["packed"] = entries[0]["required"]
                    state["in_progress"][number] = entries
            window.logic = logic
            window.current_session_path = str(session_dir)
            window.current_packing_list = LIST_NAME
            window.enable_packing_mode()
            return logic

        def close_session(logic: PackerLogic) -> None:
            logic.close()
            window.logic = None
            window.current_session_path = None
            window.current_packing_list = None
            window._show_session(None)
            window.search_input.clear()
            bridge.set_session(session_payload())
            window._push_pages()

        window.client_combo.setCurrentIndex(window.client_combo.findData("ACME"))
        settle()

        # 3a, 4a: no session.
        pages.setCurrentIndex(PAGE_PACKING)
        shoot("3a")
        pages.setCurrentIndex(PAGE_STATISTICS)
        shoot("4a")
        pages.setCurrentIndex(PAGE_PACKING)

        # 3b: opening, step 2 of 3.
        bridge.set_session(
            session_payload("opening", list_name=LIST_NAME, session_id=SESSION_ID, step=2)
        )
        shoot("3b")

        # 3c: the packing list failed.
        title, text = start_failure(
            PackingListInvalidError("", ["courier"], ["items", "order_number"], "field"),
            LIST_NAME,
        )
        window._show_start_failure(title, text, LIST_NAME)
        shoot("3c")
        window._close_failure()

        # 3d to 3f, 4b, 5a, 5b: in progress.
        logic = open_session()
        shoot("3d")
        shoot("5a", 1920, 1080)
        window.search_input.setText("LST-07")
        shoot("3e")
        window.search_input.setText("99999")
        shoot("3f")
        window.search_input.clear()
        pages.setCurrentIndex(PAGE_STATISTICS)
        shoot("4b")
        shoot("5b", 1920, 1080)
        pages.setCurrentIndex(PAGE_PACKING)
        close_session(logic)

        # 3g, 4c: complete.
        logic = open_session(complete=True)
        shoot("3g")
        pages.setCurrentIndex(PAGE_STATISTICS)
        shoot("4c")
        close_session(logic)

        window.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
