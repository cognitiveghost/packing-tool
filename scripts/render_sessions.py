"""Offscreen renders of Sessions and Session details, mockup frames 7a-7h and 8a-8f.

    .venv/bin/python scripts/render_sessions.py [output dir]

Writes <frame>-<theme>.png at 1366x768 in both themes, by default into
docs/design/ui-refresh/renders/phase4/. It builds a MainWindow against a
throwaway server with its own QSettings, so it touches neither the file
server nor this PC's saved theme, client or server path. The pages are not
driven through the registry: the bridge is given payloads built by the pure
functions in gui/sessions_payload.py from 40 synthetic sessions at a fixed
"now", so every run draws the same thing. Session details come from files
the script writes, read by the real loader.

Offscreen Qt uses a fallback font for the Qt chrome: glyph widths differ a
little from Windows.
"""

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

DEFAULT_OUT = ROOT / "docs" / "design" / "ui-refresh" / "renders" / "phase4"
# The mockup's moment, in this PC's time zone so the clock times read as drawn.
NOW = datetime(2026, 10, 7, 14, 6, 31).astimezone()
STAMP = "14:06:31"
CLIENT = "Acme Cosmetics (ACME)"
SERVER = r"\\fs01\packer\Sessions\CLIENT_ACME"

MARIA, PETYA, GEORGI, IVAN, DESI = (
    ("W-002", "Maria"), ("W-004", "Petya"), ("W-007", "Georgi"),
    ("W-009", "Ivan"), ("W-011", "Desislava"),
)
CATALOGUE = [
    ("CLN-200", "Gel cleanser 200 ml"), ("TNR-150", "Toner 150 ml"),
    ("SER-30ML", "Vitamin C serum 30 ml"), ("HYA-15ML", "Hyaluronic serum 15 ml"),
    ("DAY-50ML", "Day cream 50 ml"), ("NGT-50ML", "Night cream 50 ml"),
    ("CRM-15ML", "Eye cream 15 ml"), ("SPF-50", "Sunscreen SPF 50"),
    ("LIP-RED", "Lip balm, red"), ("LST-07", "Lipstick, shade 07"),
    ("MSK-5PK", "Sheet mask, 5 pack"), ("OIL-100", "Body oil 100 ml"),
]


def at(days_ago: int, clock: str) -> str:
    """An ISO stamp: `days_ago` days before NOW's date, at HH:MM:SS."""
    hour, minute, second = (int(part) for part in clock.split(":"))
    day = NOW - timedelta(days=days_ago)
    return day.replace(hour=hour, minute=minute, second=second).isoformat()


def session_id(days_ago: int, n: int) -> str:
    return f"{(NOW - timedelta(days=days_ago)).date().isoformat()}_{n}"


def entry(root, days_ago, n, status, list_name, worker, pc, total, done, *, skipped=0,
          items=0, started="08:02:11", touched="11:14:40", duration=None, metrics=None) -> dict:
    """A registry entry for a started session."""
    sid = session_id(days_ago, n)
    return {
        "session_id": sid, "packing_list_name": list_name, "status": status,
        "worker_id": worker[0], "worker_name": worker[1], "pc_name": pc,
        "started_at": at(days_ago, started), "last_updated": at(days_ago, touched),
        "total_orders": total, "completed_orders": done, "skipped_orders": skipped,
        "total_items": items, "duration_seconds": duration, "metrics": metrics,
        "session_path": str(root / sid),
        "work_dir": str(root / sid / "packing" / list_name),
    }


def unstarted(root, days_ago, n, list_name, total, items) -> dict:
    """A registry entry for a list nobody has started."""
    sid = session_id(days_ago, n)
    return {
        "session_id": sid, "packing_list_name": list_name, "status": "not_started",
        "created_at": at(days_ago, "07:40:00"), "total_orders": total,
        "completed_orders": 0, "skipped_orders": 0, "total_items": items, "work_dir": "",
        "session_path": str(root / sid), "metrics": None,
        "packing_list_path": str(root / sid / "packing_lists" / f"{list_name}.json"),
    }


def synthetic_sessions(root: Path) -> list[dict]:
    """40 sessions, the same every run. The first seven are the ones the
    mockup's frames name."""
    made = [
        entry(root, 0, 2, "stale", "Afternoon_wave", GEORGI, "WH-PC-02", 96, 52,
              items=311, started="12:10:05", touched="13:52:00"),
        entry(root, 0, 1, "in_progress", "Morning_wave", DESI, "WH-PC-03", 120, 38,
              skipped=3, items=402, started="08:05:00", touched="14:05:50"),
        entry(root, 1, 2, "paused", "Afternoon_wave", MARIA, "WH-PC-02", 110, 71,
              skipped=2, items=402, started="08:08:00", touched="11:20:00"),
        entry(root, 1, 1, "completed", "Morning_wave", PETYA, "WH-PC-01", 38, 38,
              items=155, duration=11549,
              metrics={"total_corrections": 1, "total_unknown_scans": 1}),
        unstarted(root, 2, 1, "Express", 24, 61),
        entry(root, 3, 1, "incomplete", "Morning_wave", IVAN, "WH-PC-01", 96, 57,
              skipped=1, items=288, touched="15:31:00", duration=26929),
        entry(root, 23, 1, "completed", "Morning_wave", MARIA, "WH-PC-02", 12, 12,
              items=53),
    ]
    cycle = ["completed", "completed", "incomplete", "completed", "abandoned"]
    workers = [MARIA, PETYA, GEORGI, IVAN]
    lists = ["Morning_wave", "Afternoon_wave", "Express", "Returns_repack"]
    for index in range(33):
        status = cycle[index % 5]
        total = 40 + (index * 17) % 90
        if status == "completed":
            done = total
        elif status == "incomplete":
            done = total - 5 - index % 30
        else:
            done = (index * 3) % 20
        made.append(entry(
            root, 4 + index % 25, 2 + index // 25, status, lists[index % 4],
            workers[index % 4], f"WH-PC-0{1 + index % 3}", total, done,
            skipped=index % 3, items=total * 3 + index,
            started=f"{8 + index % 6:02d}:{(index * 7) % 60:02d}:00",
            touched=f"{15 + index % 3:02d}:{(index * 11) % 60:02d}:00",
            duration=3600 + index * 211 if status != "abandoned" else None,
        ))
    return made


def packed_orders(count: int, days_ago: int, first: str, *, timed: bool = True) -> list[dict]:
    """`count` packed-order records as PackerLogic writes them: one item per scan."""
    orders = []
    cursor = datetime.fromisoformat(at(days_ago, first))
    for index in range(count):
        duration = 60 + (index * 37) % 140
        items, offset = [], 12
        for line in range(1 + (index * 7) % 3):
            sku, title = CATALOGUE[(index * 5 + line * 3) % len(CATALOGUE)]
            for _unit in range(1 + (index + line) % 3):
                scan = {"sku": sku, "title": title, "quantity": 1, "row": line,
                        "confirmation_method": "scanned"}
                if timed:
                    scan["scanned_at"] = (cursor + timedelta(seconds=offset)).isoformat()
                    scan["time_from_order_start_seconds"] = offset
                items.append(scan)
                offset += 6
        order = {
            "order_number": f"#{10400 + index}", "items_count": len(items), "items": items,
            "corrections": 0, "extra_scans_count": 0, "unknown_scans_count": 0,
        }
        if timed:
            order.update(
                started_at=cursor.isoformat(),
                completed_at=(cursor + timedelta(seconds=duration)).isoformat(),
                duration_seconds=duration,
                time_to_first_scan_seconds=12,
            )
        if index == 7:
            # Frame 8d's order: a correction, two extras, an unknown, a forced line.
            order.update(corrections=1, extra_scans_count=2, unknown_scans_count=1)
            items[-1].update(quantity=6, confirmation_method="force_confirmed")
            order["items_count"] = sum(scan["quantity"] for scan in items)
        if index == 12:
            items[0]["confirmation_method"] = "manual"
        orders.append(order)
        cursor += timedelta(seconds=duration + 25)
    return orders


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def write_session_files(by_id: dict) -> None:
    """The files Session details reads, for the four sessions the frames open."""
    from packing_tool.packer_logic import compute_order_timing_metrics

    # 8a, 8d, 8e: a finished session with timing.
    done = by_id[session_id(1, 1)]
    orders = packed_orders(38, 1, "08:14:02")
    metrics = dict(compute_order_timing_metrics(orders))
    hours = done["duration_seconds"] / 3600
    units = sum(order["items_count"] for order in orders)
    metrics["orders_per_hour"] = round(len(orders) / hours, 1)
    metrics["items_per_hour"] = round(units / hours, 1)
    write_json(Path(done["work_dir"]) / "session_summary.json", {
        "session_id": done["session_id"], "client_id": "ACME",
        "packing_list_name": done["packing_list_name"],
        "worker_id": done["worker_id"], "worker_name": done["worker_name"],
        "pc_name": done["pc_name"], "started_at": done["started_at"],
        "completed_at": done["last_updated"], "duration_seconds": done["duration_seconds"],
        "total_orders": 38, "completed_orders": 38, "total_items": units,
        "metrics": metrics, "orders": orders, "skipped_orders": [],
    })

    # 8b: a session still being packed has a state file and no summary.
    live = by_id[session_id(0, 1)]
    work = Path(live["work_dir"])
    write_json(work / "packing_state.json", {
        "started_at": live["started_at"], "last_updated": live["last_updated"],
        "pc_name": live["pc_name"], "progress": {"total_orders": 120},
        "completed": packed_orders(38, 0, "08:06:10"),
        "in_progress": {
            "#10440": [{"original_sku": "SPF-50", "required": 2, "packed": 1, "row": 0},
                       {"original_sku": "OIL-100", "required": 3, "packed": 2, "row": 1}],
            "#10441": [{"original_sku": "LST-07", "required": 1, "packed": 0, "row": 0}],
        },
        "skipped_orders": ["#10444", "#10457", "#10471"],
        "skipped_orders_timing": {
            "#10444": at(0, "10:02:00"), "#10457": at(0, "11:15:30"),
            "#10471": at(0, "12:48:10"),
        },
    })
    write_json(work.parent / "session_info.json", {
        "session_id": live["session_id"], "client_id": "ACME",
        "packing_list_name": live["packing_list_name"],
        "worker_id": live["worker_id"], "worker_name": live["worker_name"],
        "pc_name": live["pc_name"], "started_at": live["started_at"],
    })

    # 8c: an old session whose files hold no scan times.
    old = by_id[session_id(23, 1)]
    untimed = packed_orders(12, 23, "08:14:02", timed=False)
    write_json(Path(old["work_dir"]) / "session_summary.json", {
        "session_id": old["session_id"], "client_id": "ACME",
        "packing_list_name": old["packing_list_name"],
        "worker_id": old["worker_id"], "worker_name": old["worker_name"],
        "pc_name": old["pc_name"], "started_at": old["started_at"],
        "completed_at": old["last_updated"], "duration_seconds": 0,
        "total_orders": 12, "completed_orders": 12,
        "total_items": sum(order["items_count"] for order in untimed),
        "metrics": {}, "orders": untimed, "skipped_orders": [],
    })

    # 8f: a summary that is not JSON.
    broken = by_id[session_id(3, 1)]
    path = Path(broken["work_dir"]) / "session_summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"session_id": "2026-10-04_1", "orders": [', encoding="utf-8")


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
        from gui.main_window import PAGE_BROWSER, MainWindow
        from gui.sessions_payload import (
            details_payload,
            refresh_failure,
            session_key,
            sessions_payload,
            takeover_payload,
        )
        from gui.theme import apply_theme, load_saved_theme
        from packing_tool.profile_manager import ProfileManager
        from packing_tool.session_details import SessionFilesError, load_session_details

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
        root = server / "Sessions" / "CLIENT_ACME"
        root.mkdir(parents=True, exist_ok=True)

        entries = synthetic_sessions(root)
        by_id = {made["session_id"]: made for made in entries}
        write_session_files(by_id)

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

        def js(code: str) -> None:
            """Run statements in the page: a click or a scroll the frame needs."""
            settle()
            done = []
            pages.view.page().runJavaScript(
                f"(function () {{ {code}; return true; }})()", 0, done.append)
            deadline = time.monotonic() + 10
            while not done:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"the page never answered: {code}")
                app.processEvents()
                time.sleep(0.01)
            if done[0] is not True:
                raise RuntimeError(f"failed in the page: {code}")

        def shoot(name: str) -> None:
            for theme in ("light", "dark"):
                apply_theme(app, theme)
                settle()
                target = out / f"{name}-{theme}.png"
                if not window.grab().save(str(target)):
                    raise OSError(f"could not write {target}")
                print(target)

        window.client_combo.setCurrentIndex(window.client_combo.findData("ACME"))
        # The controller stays out of the way: its timer off, the read the
        # client picker started finished, and no new read when the page shows.
        window.sessions.shutdown()
        for _ in range(5):
            app.processEvents()
        window.sessions.refresh = lambda: None
        pages.setCurrentIndex(PAGE_BROWSER)

        def listed(**kwargs) -> None:
            kwargs.setdefault("stamp", STAMP)
            shown = kwargs.pop("entries", entries)
            bridge.set_sessions(sessions_payload(shown, now=NOW, **kwargs))

        def select(sid: str) -> None:
            key = json.dumps(session_key(by_id[sid]))
            js("Array.from(document.querySelectorAll('[data-session]'))"
               f".find(function (n) {{ return n.dataset.session === {key}; }}).click()")

        def details(sid: str, *, read: bool = True, **kwargs) -> None:
            made = by_id[sid]
            files = load_session_details(made) if read else None
            bridge.set_details(
                details_payload(made, files, now=NOW, client=CLIENT, stamp=STAMP, **kwargs))
            bridge.set_page("details")
            js("document.getElementById('details').scrollTop = 0")

        # 7a: the list. 7b: a row selected, the pane open.
        listed()
        shoot("7a")
        select(session_id(1, 2))
        shoot("7b")

        # 7c: the take-over question over a stale session.
        stale = by_id[session_id(0, 2)]
        select(stale["session_id"])
        bridge.set_confirm(takeover_payload(
            stale,
            {"locked_by": "WH-PC-02", "worker_name": "Georgi", "heartbeat": at(0, "13:52:00")},
            now=NOW,
        ))
        shoot("7c")
        bridge.set_confirm({})

        # 7f: a refresh failed; the old list stays, with a row selected.
        select(session_id(0, 1))
        listed(failure=refresh_failure(
            SERVER, "the network path was not found", "14:08:31", STAMP))
        shoot("7f")

        # 7d: nothing matches. 7e: the first load. 7g: no sessions yet.
        listed(query="2025-12")
        shoot("7d")
        listed(entries=[], loaded=False, refreshing=True, stamp="")
        shoot("7e")
        listed(entries=[])
        shoot("7g")

        # 8a: a finished session. 8d: order #10407 opened. 8e: nothing matches.
        listed()
        finished = session_id(1, 1)
        details(finished)
        shoot("8a")
        js("var row = Array.from(document.querySelectorAll('[data-dorder]'))"
           ".find(function (n) { return n.dataset.dorder.indexOf('10407') >= 0; });"
           " row.click(); row.scrollIntoView({block: 'center'})")
        shoot("8d")
        details(finished, query="10999")
        js("document.getElementById('d-query').scrollIntoView()")
        shoot("8e")

        # 8b: still packing. 8c: no timing data.
        details(session_id(0, 1))
        shoot("8b")
        details(session_id(23, 1))
        shoot("8c")

        # 8f: the files could not be read; the cause is the loader's own.
        broken = session_id(3, 1)
        try:
            load_session_details(by_id[broken])
        except SessionFilesError as error:
            cause = error.cause
        else:
            raise RuntimeError("the broken summary was read")
        details(broken, read=False, error={
            "path": SERVER + "\\" + broken + r"\packing\Morning_wave\session_summary.json",
            "cause": cause,
        })
        shoot("8f")

        # 7h: no client. The bar, the sidebar and the page all say so.
        bridge.set_details({})
        window.client_combo.setCurrentIndex(-1)
        pages.setCurrentIndex(PAGE_BROWSER)
        shoot("7h")

        window.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
