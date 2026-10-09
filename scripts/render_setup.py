"""Offscreen renders of Worker selection and SKU mapping, in both themes.

    .venv/bin/python scripts/render_setup.py [output dir] [--size WIDTHxHEIGHT]

Writes <frame>-<theme>.png at the size given (1366x768 by default), by default
into docs/design/ui-refresh/renders/final/<size>/. The frames are the presets
of docs/design/ui-refresh/mockups/Worker Selection.html (w-*) and
SKU Mapping.html (m-*).

It drives a SetupPages alone: no MainWindow and no server. The bridge is given
payloads built by the pure functions in gui/setup_payload.py at a fixed "now",
so every run draws the same thing, and its own QSettings, so it touches
neither the file server nor this PC's saved theme.
"""

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from render_args import parse_args

NOW = datetime(2026, 10, 7, 14, 6, tzinfo=timezone(timedelta(hours=3)))
WORKERS_PATH = r"\\fs01\fulfilment\Workers"
CONFIG_PATH = r"\\fs01\fulfilment\Clients\CLIENT_ACME\packer_config.json"
SKUS = [
    "CRM-50ML", "CRM-15ML", "SER-30ML", "CLN-200", "TNR-150", "MSK-5PK", "SPF-50", "LIP-RED",
    "OIL-100", "GFT-BOX", "EYE-15ML", "BLM-10G", "SCR-100", "MST-100", "HND-75ML", "BDY-250",
    "SHP-300", "CND-300", "HRM-50ML", "GEL-150",
]
SIXTY = {
    (f"5901234500{n:03d}" if n < 40 else f"4006381333{n - 40:03d}"): SKUS[n % 20]
    for n in range(60)
}
CHOICES = [
    {"sku": "SER-30ML", "label": "SER-30ML — 0 / 1 packed", "key": "ser30ml"},
    {"sku": "CRM-50ML", "label": "CRM-50ML — 2 / 3 packed", "key": "crm50ml"},
    {"sku": "LIP-RED", "label": "LIP-RED — 2 / 2 packed", "key": "lipred"},
]


def worker(worker_id, name, sessions, orders, **ago):
    return SimpleNamespace(
        id=worker_id, name=name, total_sessions=sessions, total_orders=orders,
        last_active=(NOW - timedelta(**ago)).isoformat() if ago else None,
        created_at=(NOW - timedelta(minutes=1)).isoformat(),
    )


SIX = [
    worker("w1", "Ivan", 31, 2870, hours=6, minutes=26),
    worker("w2", "Maria", 14, 1204, days=1),
    worker("w3", "Georgi", 22, 1951, days=2),
    worker("w4", "Petya", 9, 688, days=8),
    worker("w5", "Elena", 3, 140, days=25),
    worker("w6", "Dimitar", 1, 37, days=40),
]


def main(argv: list[str]) -> int:
    out, width, height = parse_args(argv)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as raw:
        # Before any QSettings is made: keep this PC's saved theme. Both
        # formats, as tests/conftest.py does.
        for fmt in (QSettings.NativeFormat, QSettings.IniFormat):
            QSettings.setPath(fmt, QSettings.UserScope, str(Path(raw) / "settings"))

        app = QApplication.instance() or QApplication(sys.argv[:1])
        from gui.setup_pages import SetupPages
        from gui.setup_payload import (
            MappingEditor,
            mapping_error,
            mapping_payload,
            quick_payload,
            workers_payload,
        )
        from gui.theme import apply_theme, load_saved_theme

        load_saved_theme(app)
        # No managers: the payloads below never go through the server.
        pages = SetupPages(None, None, now=lambda: NOW)
        pages.resize(width, height)
        pages.show()
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

        def js(code: str) -> None:
            done = []
            pages.view.page().runJavaScript(
                f"(function () {{ {code}; return true; }})()", 0, done.append
            )
            deadline = time.monotonic() + 10
            while not done:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"never returned from the page: {code}")
                app.processEvents()
                time.sleep(0.01)
            if done[0] is not True:
                raise RuntimeError(f"failed in the page: {code}")

        def typed(element_id: str, text: str) -> None:
            js(
                f"const n = document.getElementById('{element_id}'); n.focus();"
                f" n.value = {json.dumps(text)};"
                " n.dispatchEvent(new Event('input', {bubbles: true}))"
            )

        def shoot(name: str) -> None:
            for theme in ("light", "dark"):
                apply_theme(app, theme)
                pages.resize(width, height)
                settle()
                target = out / f"{name}-{theme}.png"
                if not pages.grab().save(str(target)):
                    raise OSError(f"could not write {target}")
                print(target)

        def workers(people, **kwargs) -> None:
            kwargs.setdefault("startup", True)
            bridge.set_page("")
            settle()  # the page sees the blank, as it does between two real pages
            bridge.set_workers(workers_payload(people, now=NOW, **kwargs))
            bridge.set_page("workers")
            settle()

        def mapping(editor=None, **kwargs) -> None:
            kwargs.setdefault("client", "ACME")
            bridge.set_page("")
            settle()  # the page sees the blank, as it does between two real pages
            bridge.set_mapping(
                mapping_payload(editor if editor is not None else MappingEditor(SIXTY), **kwargs)
            )
            bridge.set_page("mapping")
            settle()

        def unsaved() -> MappingEditor:
            """The mockup's dirty list: two added, one edited, one deleted."""
            editor = MappingEditor(SIXTY)
            editor.add("5906000123456", "CRM-50ML")
            editor.add("5906000123463", "SER-30ML")
            editor.update(editor.rows[9]["id"], editor.rows[9]["barcode"], "LIP-NUDE")
            editor.delete(editor.rows[23]["id"])
            return editor

        settle()

        # --- Worker selection ---------------------------------------------
        workers(SIX)
        shoot("w-six")
        workers(SIX, startup=False, current_id="w1", current_name="Ivan")
        shoot("w-six-switch")
        workers(SIX, picked_id="w2")
        shoot("w-opening")
        workers(SIX[1:2])
        shoot("w-one")
        workers([])
        shoot("w-none")
        workers(SIX)
        js("document.getElementById('w-new').click()")
        shoot("w-creating")
        bridge.answer = lambda name, *args: (
            "There’s already a worker called Maria. Pick that card, or add a surname."
        )
        typed("w-name", "maria")
        js("document.getElementById('w-create').click()")
        shoot("w-duplicate")
        workers([], failure={"cause": "the network path was not found", "path": WORKERS_PATH})
        shoot("w-failed")

        # --- SKU mapping ----------------------------------------------------
        mapping()
        shoot("m-60")
        mapping(MappingEditor())
        shoot("m-none")
        added = MappingEditor(SIXTY)
        added.add("5906000123456", "CRM-50ML")
        mapping(added)
        js("document.getElementById('m-add').click()")
        shoot("m-adding")
        mapping()
        js("document.getElementById('m-add').click()")
        typed("d-barcode", "5901234500003")
        typed("d-sku", "CLN-250")
        shoot("m-already-mapped")
        mapping(quick=quick_payload("barcode", barcode="5906000123456", choices=CHOICES))
        shoot("m-from-packer")
        mapping(quick=quick_payload("sku", sku="SER-30ML"))
        shoot("m-from-packer-sku")
        mapping()
        js("document.querySelector('[data-row-action=\"delete\"][data-id=\"5\"]').click()")
        shoot("m-delete")
        mapping(unsaved())
        js("document.getElementById('m-reload').click()")
        shoot("m-reload-unsaved")
        failed = unsaved()
        mapping(failed, error=mapping_error(
            "save",
            "Could not save the SKU mapping to the file server: the network path was not found",
            CONFIG_PATH,
            sum(failed.counts().values()),
        ))
        shoot("m-save-failed")
        mapping(saved=True)
        shoot("m-saved")

        pages.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
