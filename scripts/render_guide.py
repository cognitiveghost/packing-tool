"""Screenshots for the Packing Tool user guide, taken through the real flows.

    .venv/bin/python scripts/render_guide.py --server <dir> --lang en|bg [--out <dir>] [--size WIDTHxHEIGHT]

<dir> is a folder from Fulfilment's scripts/build_guide_server.py, under the system temp dir. The script copies it
to a temp dir first and drives MainWindow(config_path=...) against that copy: worker selection, client choice,
starting a list from the Sessions page, scanning, the statistics, the sessions and their details, the SKU mapping
page, and a quick map from Packer Mode. Nothing is injected except one quantity in the copy, see FORCE_QTY.

Writes <name>.png into <out> (default docs/user-guide/img/<lang>), light theme, whole window. The names are the
ones the guide links to.
"""

import argparse
import json
import os
import shutil
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

from shared import i18n

CLIENT = "ALMA"
WORKER_ID, WORKER_NAME = "worker_001", "Desislava"
SERVER_LABEL = r"\\fs01\packer"  # the path the connection card shows, as in render_shell.py
# The seeded lines are one or two units, and Force confirm needs more than five. The first unmapped line of the
# first order is raised to this count in the temp copy, so that a real order row offers Force confirm.
FORCE_QTY = 8


def packing_lists(server: Path) -> list[tuple[Path, Path, dict]]:
    """Every ALMA list in the server, oldest session first: (session dir, list file, document)."""
    found = []
    for session in sorted((server / "Sessions" / f"CLIENT_{CLIENT}").iterdir()):
        if not (session / "packing_lists").is_dir():
            continue
        for list_file in sorted((session / "packing_lists").glob("*.json")):
            found.append((session, list_file, json.loads(list_file.read_text(encoding="utf-8"))))
    return found


def server_root(path: str) -> Path:
    server = Path(path).resolve()
    if not server.is_relative_to(Path(tempfile.gettempdir()).resolve()):
        raise SystemExit(f"refusing {server}: the guide server must be a folder under the temp dir")
    return server


def main(argv: list[str]) -> int:
    extra = argparse.ArgumentParser(add_help=False)
    extra.add_argument("--server", required=True)
    extra.add_argument("--out", type=Path)
    known, rest = extra.parse_known_args(argv)
    _unused, width, height, lang = parse_args(rest)
    out = known.out or ROOT / "docs" / "user-guide" / "img" / lang
    source = server_root(known.server)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        # Before any QSettings is made: keep this PC's saved theme, client and
        # server path. Both formats, as tests/conftest.py does.
        for fmt in (QSettings.NativeFormat, QSettings.IniFormat):
            QSettings.setPath(fmt, QSettings.UserScope, str(tmp / "settings"))
        os.environ.pop("FULFILLMENT_SERVER_PATH", None)

        server = tmp / "server"
        shutil.copytree(source, server)
        config = tmp / "config.ini"
        config.write_text(
            "[Network]\n"
            f"FileServerPath = {server}\n"
            "ConnectionTimeout = 5\n"
            f"LocalCachePath = {tmp / 'cache'}\n"
            "[Logging]\nLogLevel = WARNING\nLogRetentionDays = 30\nMaxLogSizeMB = 10\n",
            encoding="utf-8",
        )

        lists = packing_lists(server)
        newest_session, newest_file, newest_doc = lists[-1]
        smallest = min(lists, key=lambda entry: len(entry[2]["orders"]))
        quick = next(entry for entry in lists if entry is not lists[-1] and entry is not smallest)
        sku_map = json.loads(
            (server / "Clients" / f"CLIENT_{CLIENT}" / "packer_config.json").read_text(encoding="utf-8")
        )["sku_mapping"]
        barcode_for = {sku: barcode for barcode, sku in sku_map.items()}
        first = newest_doc["orders"][0]
        forced = next(item for item in first["items"] if item["sku"] not in barcode_for)
        forced["quantity"] = FORCE_QTY
        newest_file.write_text(json.dumps(newest_doc, ensure_ascii=False, indent=2), encoding="utf-8")

        app = QApplication.instance() or QApplication(sys.argv[:1])
        from gui.app_pages import PAGE_PACKING, PAGE_STATISTICS
        from gui.main_window import MainWindow
        from gui.sessions_payload import session_key
        from gui.theme import apply_theme, load_saved_theme
        from packing_tool.packer_logic import normalize_sku

        load_saved_theme(app)
        i18n.set_language(lang, i18n.catalogue_files(ROOT, lang))
        window = MainWindow(config_path=str(config))
        base = Path(window.profile_manager.base_path).resolve()
        if not base.is_relative_to(tmp.resolve()):
            raise RuntimeError(f"refusing to render against {base}: not the temp server")
        real_set = window.sidebar.set_connection
        window.sidebar.set_connection = lambda state, _path: real_set(state, SERVER_LABEL)
        real_outage = window.connection_banner.set_outage
        window.connection_banner.set_outage = lambda _path, since: real_outage(SERVER_LABEL, since)
        window._set_connection_state("ok")  # the card was drawn before the patch
        window.resize(width, height)
        window.show()
        apply_theme(app, "light")

        def pump(seconds: float) -> None:
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                app.processEvents()
                time.sleep(0.01)

        def visible_bridge():
            current = window.stacked_widget.currentWidget()
            if current is window.setup_pages:
                return window.setup_pages.bridge
            if current is window.packer_mode_widget:
                return window.packer_mode_widget.bridge
            return window.session_tabs.bridge

        def settle() -> None:
            # The pages are web documents: grab only after the visible one has drawn what it was last sent.
            deadline = time.monotonic() + 20
            while True:
                bridge = visible_bridge()
                if bridge.painted_revision >= bridge.revision:
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError("the page never painted; is QtWebEngine working?")
                app.processEvents()
                time.sleep(0.01)
            pump(0.2)

        def until(condition, what: str) -> None:
            deadline = time.monotonic() + 20
            while not condition():
                if time.monotonic() > deadline:
                    raise RuntimeError(f"timed out waiting for {what}")
                app.processEvents()
                time.sleep(0.01)
            settle()

        def sessions_loaded() -> None:
            window.sessions.wait()
            pump(0.2)
            settle()

        def shoot(name: str) -> None:
            settle()
            target = out / f"{name}.png"
            if not window.grab().save(str(target)):
                raise OSError(f"could not write {target}")
            print(target)

        def start_list(session: Path, list_file: Path) -> None:
            window._handle_start_packing_from_browser({
                "session_path": str(session),
                "client_id": CLIENT,
                "packing_list_name": list_file.stem,
                "list_file": str(list_file),
            })

        def packer_mode() -> None:
            window.switch_to_packer_mode()
            until(lambda: window.stacked_widget.currentWidget() is window.packer_mode_widget, "Packer Mode")

        def shell() -> None:
            window._leave_packer_mode()
            until(lambda: window.stacked_widget.currentWidget() is window.session_widget, "the shell")

        def end_run() -> None:
            # The "Session ended" toast carries the report path, which is in the temp copy. It is shown for 4 s, so
            # the frames wait for it to clear.
            window.end_session()
            pump(4.5)

        def scan(text: str) -> None:
            window.on_scanner_input(text)

        def scan_sku(sku: str) -> None:
            scan(barcode_for.get(sku, sku))

        def pack_order(order: dict) -> None:
            scan(order["order_number"])
            for item in order["items"]:
                for _ in range(item["quantity"]):
                    scan_sku(item["sku"])

        # workers: the first thing a packer sees.
        settle()
        shoot("workers")
        window._on_worker_chosen(WORKER_ID, WORKER_NAME)
        until(lambda: window.stacked_widget.currentWidget() is window.session_widget, "the shell")

        # packing: the client, and its seeded lists.
        window.client_combo.setCurrentIndex(window.client_combo.findData(CLIENT))
        sessions_loaded()
        shoot("packing")

        # packer-start, then the first order's barcode and two of its lines.
        start_list(newest_session, newest_file)
        packer_mode()
        shoot("packer-start")

        first_mapped = [item["sku"] for item in first["items"] if item["sku"] in barcode_for][:2]
        scan(first["order_number"])
        for sku in first_mapped:
            scan_sku(sku)
        shoot("packer-scanning")

        # packer-extra: a line already fully packed, scanned again. Removed afterwards, as a packer would.
        scan_sku(first_mapped[0])
        shoot("packer-extra")
        window._on_extra_removed(normalize_sku(first_mapped[0]))

        # packer-nomatch: a barcode that is in no list.
        scan("0000000000000")
        shoot("packer-nomatch")
        window.logic.unknown_scans.clear()
        window.packer_mode_widget.show_unknown_scans([])

        # statistics: drawn while a list is open.
        shell()
        window.session_tabs.setCurrentIndex(PAGE_STATISTICS)
        shoot("statistics")

        # packer-force: the forced line of the same order, asked through its own row.
        window.session_tabs.setCurrentIndex(PAGE_PACKING)
        packer_mode()  # the order is still open from packer-scanning
        # The notice and the scanned text clear on the next scan in the app; no scan is sent here.
        window.packer_mode_widget.show_notification("", "transparent")
        window.packer_mode_widget.update_raw_scan_display("")
        row = next(s["row"] for s in window.logic.current_order_state
                   if s["normalized_sku"] == normalize_sku(forced["sku"]))
        window.packer_mode_widget.bridge.forceItem(row)
        shoot("packer-force")
        # The run stays partly packed: it is the in-progress run on the Sessions page.
        end_run()

        # packer-complete: the smallest list, every order in full.
        small_session, small_file, small_doc = smallest
        start_list(small_session, small_file)
        packer_mode()
        for order in small_doc["orders"]:
            pack_order(order)
        pump(0.5)  # the session-complete panel is deferred to the next event-loop tick
        shoot("packer-complete")
        end_run()

        # sessions: the completed run and the one left in progress.
        window.open_session_browser()
        window.sessions.refresh()
        sessions_loaded()
        shoot("sessions")

        # session-details: the completed run.
        window.sessions.open_details(session_key({
            "session_id": small_session.name, "packing_list_name": small_file.stem,
        }))
        sessions_loaded()
        shoot("session-details")

        # sku-mapping: the setup page for the client, with the seeded pairs.
        window.open_sku_mapping()
        until(lambda: window.stacked_widget.currentWidget() is window.setup_pages, "the SKU mapping page")
        shoot("sku-mapping")
        window._leave_setup()
        until(lambda: window.stacked_widget.currentWidget() is window.session_widget, "the shell")

        # quick-map: an order open in Packer Mode, and one of its SKUs without a barcode.
        quick_session, quick_file, quick_doc = quick
        start_list(quick_session, quick_file)
        packer_mode()
        quick_order = quick_doc["orders"][0]
        scan(quick_order["order_number"])
        unmapped = next(item["sku"] for item in quick_order["items"] if item["sku"] not in barcode_for)
        window._on_map_sku_from_packer(unmapped)
        until(lambda: window.stacked_widget.currentWidget() is window.setup_pages, "the quick map")
        shoot("quick-map")
        window._leave_setup()

        window.close()
    return 0


if __name__ == "__main__":
    code = main(sys.argv[1:])
    sys.stdout.flush()
    os._exit(code)
