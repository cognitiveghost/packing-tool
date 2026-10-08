"""Offscreen renders of Packer Mode, mockup frames 6a-6j, in both themes.

    .venv/bin/python scripts/render_packer_mode.py [output dir]

Writes <frame>-<theme>.png at 1366x768 and 6b-<theme>-1920.png at 1920x1080,
by default into docs/design/ui-refresh/renders/phase2/. It drives a
PackerModeWidget alone through its public methods: no MainWindow, no server,
and its own QSettings, so it touches neither the file server nor this PC's
saved theme.

The scan flash pulses and clears in the app. Here it is held lit, so the
frames that show a scan show its colour.

Offscreen Qt uses a fallback font for the Qt bar: glyph widths differ a
little from Windows.
"""

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

DEFAULT_OUT = ROOT / "docs" / "design" / "ui-refresh" / "renders" / "phase2"

# The mockup's order, with SPF-50 at 8 units so one row offers Force confirm.
LINES = [
    ("LIP-RED", "Lip balm, red", 2),
    ("CRM-50ML", "Day cream 50 ml", 3),
    ("CLN-200", "Gel cleanser 200 ml", 1),
    ("SPF-50", "Sunscreen SPF 50", 8),
    ("SER-30ML", "Vitamin C serum 30 ml", 1),
]
ITEMS = [
    {"SKU": sku, "Product_Name": name, "Quantity": qty, "Order_Number": "10407"}
    for sku, name, qty in LINES
]
METADATA = {
    "shipping_provider": "DPD",
    "tags": ["Gift wrap"],
    "notes": "Add a sample sachet — customer asked by phone",
    "system_note": "Repeat",
}
HOLD_FLASH = (
    "var s = document.createElement('style');"
    "s.textContent = '.doc-main[data-flash] .pm-flash"
    "{animation: none; border-color: var(--flash);}';"
    "document.head.appendChild(s);"
)
CLEAR_FLASH = "delete document.getElementById('doc-main').dataset.flash;"


def packed_state(packed):
    return [
        {"row": row, "packed": count, "required": LINES[row][2]}
        for row, count in enumerate(packed)
    ]


def main(argv: list[str]) -> int:
    out = Path(argv[0]) if argv else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as raw:
        # Before any QSettings is made: keep this PC's saved theme. Both
        # formats, as tests/conftest.py does.
        for fmt in (QSettings.NativeFormat, QSettings.IniFormat):
            QSettings.setPath(fmt, QSettings.UserScope, str(Path(raw) / "settings"))

        app = QApplication.instance() or QApplication(sys.argv[:1])
        from gui.packer_bridge import session_end_payload
        from gui.packer_mode_widget import PackerModeWidget
        from gui.theme import apply_theme, load_saved_theme

        load_saved_theme(app)
        widget = PackerModeWidget()
        widget.resize(1366, 768)
        widget.show()
        bridge = widget.bridge

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

        def js(code: str) -> None:
            widget.document_view.page().runJavaScript(code)

        def shoot(name: str, width: int = 1366, height: int = 768) -> None:
            for theme in ("light", "dark"):
                apply_theme(app, theme)
                widget.resize(width, height)
                settle()
                target = out / f"{name.format(theme=theme)}.png"
                if not widget.grab().save(str(target)):
                    raise OSError(f"could not write {target}")
                print(target)

        def fresh(orders_done: int = 38) -> None:
            """A session in progress, waiting for an order."""
            widget.reset_for_new_session()
            js(CLEAR_FLASH)
            widget.update_session_progress(orders_done, 120)
            for number in range(10400, 10407):
                widget.add_order_to_history(str(number), "[SKIPPED]" if number == 10403 else "")

        def order(packed=(2, 1, 0, 0, 0)) -> None:
            fresh()
            widget.display_order(ITEMS, packed_state(packed), metadata=METADATA, sku_map={})
            widget.show_notification("Order #10407 · 5 items", "status_info")

        def scanned(row: int, count: int, text: str, raw_scan: str) -> None:
            widget.update_item_row(row, count, count >= LINES[row][2])
            widget.show_notification(text, "status_success")
            widget.update_raw_scan_display(raw_scan)
            widget.flash_scan("green")

        settle()
        js(HOLD_FLASH)

        fresh()
        shoot("6a-{theme}")

        order()
        shoot("6b-{theme}")
        shoot("6b-{theme}-1920", 1920, 1080)

        order()
        scanned(1, 2, "CRM-50ML confirmed — 2 of 3 packed", "CRM-50ML")
        shoot("6c-{theme}")

        order()
        widget.show_extras_panel({"MSCBLK": 1})
        widget.show_notification("Extra item scanned — keep it or remove it", "status_warning")
        widget.update_raw_scan_display("MSC-BLK")
        widget.flash_scan("orange")
        shoot("6d-{theme}")

        order()
        widget.show_unknown_scans(["4006381333931"])
        widget.show_notification(
            "Unknown SKU 4006381333931 — scan again or map it", "status_danger"
        )
        widget.update_raw_scan_display("4006381333931")
        widget.flash_scan("red")
        shoot("6e-{theme}")

        order()
        bridge.forceItem(3)
        shoot("6f-{theme}")

        order(packed=(2, 3, 1, 8, 0))
        scanned(4, 1, "Order #10407 packed. Scan the next order.", "SER-30ML")
        widget.clear_screen_later(600_000)
        shoot("6g-{theme}")

        fresh(orders_done=120)
        widget.show_session_complete(session_end_payload(120, 120, 0, 1290, 11520))
        shoot("6h-{theme}")

        order()
        scanned(1, 2, "CRM-50ML confirmed — 2 of 3 packed", "CRM-50ML")
        widget.set_unsaved(True)
        shoot("6i-{theme}")

        order()
        widget.show_takeover("Georgi Dimitrov", "acme-packing-07-10")
        shoot("6j-{theme}")

        widget.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
