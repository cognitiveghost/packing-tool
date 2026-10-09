# UI refresh phase 4 (Sessions and Session details on the web tier) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Draw Sessions and Session details as two more pages of the app document, to mockup frames 7a to 7h and 8a to 8f, and delete `gui/session_browser/` and `packing_tool/session_history_manager.py`.

**Architecture:** `gui/web/app.html` gains two pages, a pane and a take-over dialog. `AppBridge` gains three properties (`sessions`, `details`, `confirm`) and twelve slots. Pure functions in `gui/sessions_payload.py` decide every row, sentence and number; `packing_tool/session_details.py` reads a session's files; `gui/sessions_page.py` (`SessionsPage`, a `QObject`) owns the workers, the 2-minute timer, the filter state and the exports, and pushes payloads to the bridge. `AppPages` becomes the view alone, so the view is hidden only under Packer Mode.

**Tech Stack:** Python 3.14, PySide6 (Qt widgets, QtWebEngine, QWebChannel), pandas (already a dependency; Excel export), plain HTML/CSS/JS with no build step, pytest with pytest-qt. No new dependency.

**Spec:** `docs/superpowers/specs/2026-10-08-ui-refresh-phase4-sessions-design.md`. Read it first. ADRs: `docs/adr/0001-packer-mode-on-the-web-tier.md`, `docs/adr/0002-every-screen-on-the-web-tier.md`, `docs/adr/0003-the-shells-pages-are-one-web-document.md`. Mockup: `docs/design/ui-refresh/mockups/Packer App.html` (unpack it as `docs/design/ui-refresh/mockups/README.md` describes, into a folder outside the repo; the Sessions markup is lines 317 to 455 of the unpacked `template.html`, Session details 456 to 588, the take-over dialog 592 to 608, and the state logic is `sessVals()` and `detVals()`).

## Global Constraints

- **Never edit a file under `shared/`.** A hook blocks it and CI diffs the folder. Read `shared/web_page.py`, `shared/web/kit.css`, `shared/web/page.js`; do not change them.
- **Web assets** (`gui/web/*`): colours only as `var(--token)` from `theme_css_vars()` (token `status_success_dot` is `--status-success-dot`), or `currentColor` / `transparent`. No hex, no colour names, no `px` font sizes (only `var(--type-*-size)`), no `transition`, `transform`, `opacity`, gradients. `box-shadow` only as `var(--card-shadow)`, `var(--overlay-shadow)` or `none`. No `style="..."` attribute in HTML. `tests/test_style_literals_guard.py` enforces this.
- **Type scale on the floor profile:** `--type-caption-size` 10pt, `--type-body-size` 12pt, `--type-heading-size` 14pt, `--type-display-size` 17pt, `--type-display-xl-size` 28pt. Every size in the mockup is one of these.
- **Text into the page goes through `textContent`,** never `innerHTML`: list names, workers, PCs and SKUs come from files.
- **Qt code:** no colour literals.
- **Month names are never from `strftime("%b")`:** Qt can switch the process locale. Use the `_MONTHS` table in `gui/sessions_payload.py`.
- **Copy, verbatim:** "Choose a client", "Pick a client in the bar above to see its sessions.", "All", "Open", "Finished", "Abandoned", "Search sessions", "Clear search", "From", "To", "Date range", "Refresh  F5", "Last refreshed", "Refreshing…", "Auto-refresh (2 min)", "Refresh every 2 minutes", "Export the rows shown", "CSV", "Excel", "Status", "Session", "Age", "Packing", "Orders", "Items", "Last touched", "Reading sessions from the server…", "No sessions match", "Clear filters", "No sessions yet", "Sessions appear here once someone starts packing for this client.", "Set by a person", "Inferred by the system", "Set by the system", "Double-click a session for its action", "Refresh failed", "Retry", "Close  Esc", "Orders done", "None skipped", "Worker", "PC", "Duration", "Scan corrections", "Unknown scans", "Start packing", "Resume session", "View details", "Go to Packing", "Or double-click the row", "Take over and resume", "Cancel", "Back to Sessions  Alt+Left", "Sessions", "Export Excel", "The session's files could not be read", "Still packing on", "Every number below is so far and refreshes with the list.", "Reading the session's files…", "Client", "Packing list", "Started", "Completed", "Still packing", "Orders packed", "Items packed", "Orders per hour", "Items per hour", "Skipped orders", "No timing data", "Timing and scan quality", "Only data from completed orders is shown.", "Figures so far.", "Order time", "Item time", "Scan quality", "Average per order", "Fastest", "Slowest", "Average per item", "Average to first scan", "Corrections per order", "Extra scans", "Timing metrics are not available for this session.", "Its files hold no scan times, so durations and rates cannot be worked out. Counts and flags are complete.", "Filter by order number", "Clear filter", "Expand all", "Collapse all", "Order / Item", "Count", "Started / Scanned", "Flags", "No orders match", "No orders were recorded for this session.", "Item details not available", "Forced confirm", "Manual confirm", "Extra", "In progress", "Skipped", "No order data to export". The middle dot is `·`, the dash for "nothing" is `—` (em dash), the loading count is `–` (en dash), the multiplication sign is `×`.
- **Sizes:** page padding 20px 24px, gap 16px; toolbar controls 44px, gap 8px; list head and foot 40px; session row 44px; pane 360px; order row 44px; item row 40px; flag badge 24px; status chip 28px with an 8px dot; list bar 56px by 6px; pane bar 8px; take-over dialog 540px.
- **Git:** `/usr/bin/git`, one plain git command per Bash call (no `&&`, `;`, `$VAR` paths). Commit with `/usr/bin/git commit -F <absolute path to a message file>`; write the message file with the Write tool, outside the repo. Never commit to `main`. Each commit message ends with the attribution lines your session gives you.
- **Tests:** run with `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q <path>`. If a hook refuses that, run the whole suite: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`. Write test files with Write/Edit, never with shell redirection. If `.venv` is missing in the worktree: `ln -s /home/gloopy/Desktop/Projects/packing-tool/.venv .venv`.
- **Lint:** `.venv/bin/ruff check . --exclude shared` must pass before each commit.
- **QtWebEngine in tests:** `runJavaScript` cannot return a JS array; wrap every result in `JSON.stringify` (the `_eval` helper does). Never mark a Chromium test skip.
- After the last code change, run `graphify update .` (CLAUDE.md).
- Departures from the mockup are the 24 in spec section 12. If you make another, add it to that table in the same commit.
- The code in this plan was written without running it. When a test you were told to expect passing fails, find out why and fix the code or the test so the behaviour the spec states holds; do not weaken an assertion to get green.

## Review Focus

Inputs the spec implies that are most likely to bite a packer. Each has a test in the task named.

1. **A registry entry with almost nothing in it** (no worker, no PC, no dates, `None` counts, `metrics: None`). The row and its pane build with dashes and nothing raises (Task 2, `test_a_bare_entry_still_makes_a_row`).
2. **A session's files with odd shapes:** a non-dict in `completed`, an `in_progress` value that is not a list, an integer order number, an order with no `items`. The details build and every order number is a string (Task 3, `test_odd_shapes_in_the_files_do_not_break_the_details`).
3. **A list name, worker or SKU that is markup** (`<img src=x>`). It is shown as text and creates no element (Task 4, `test_markup_in_a_list_name_is_text`; Task 5, `test_markup_in_a_sku_is_text`).
4. **An answer that arrives late:** a refresh for the client just left, or details for a session just closed. It is dropped (Task 6, `test_a_refresh_for_another_client_is_dropped`, `test_details_for_a_closed_session_are_dropped`).
5. **A stale lock that changed while the question was open** (its owner came back). The take-over does not remove it; the page shows frame 3c and no session opens (Task 7, `test_a_take_over_of_a_lock_that_came_back_is_refused`).

## File map

| File | Responsibility | Task |
|---|---|---|
| `packing_tool/session_details.py` (new) | `load_session_details`, `partial_summary`, `SessionFilesError`, `error_cause` | 1 |
| `packing_tool/session_registry_manager.py` | `STALE_HEARTBEAT_SECONDS = 120` | 1 |
| `gui/workers.py` | `RegistryRefreshWorker` (moved, lists the server root first), `SessionDetailsWorker` | 1 |
| `gui/sessions_payload.py` (new) | pure payloads for the list, the pane, the take-over question, details and both exports | 2, 3 |
| `gui/app_bridge.py` | three properties, twelve slots | 4 |
| `gui/web/floor.css` | floor sizes: segmented control, input, menu, dotted badge | 4 |
| `gui/web/app.html`, `app.css`, `app.js` | the Sessions page, the pane, the dialog (4); Session details (5) | 4, 5 |
| `gui/sessions_page.py` (new) | `SessionsPage` | 6 |
| `gui/app_pages.py` | the view alone | 7 |
| `gui/main_window.py` | builds `SessionsPage`, the take-over lock step, loses four message boxes | 7 |
| `tests/conftest.py` | the `main_window` fixture stops the Sessions workers before the window goes | 7 |
| `gui/session_browser/`, `packing_tool/session_history_manager.py` | deleted | 7 |
| `scripts/render_sessions.py` (new) | renders of 7a to 7h and 8a to 8f | 8 |
| `CONTEXT.md`, `docs/adr/0003-…md` | docs | 8 |

Names used across tasks (a session's **key** is `"<session_id>|<packing_list_name>"`, built by `gui.sessions_payload.session_key(entry)`):

- `sessions_payload(entries, *, now=None, tab="all", query="", date_from=None, date_to=None, loaded=True, refreshing=False, stamp="", auto=True, failure=None, open_key="", server_down=False) -> dict`
- `visible_entries(entries, *, now, tab, query, date_from, date_to) -> tuple[list, list, list]` (shown, in the tab, in the dates)
- `default_range(now) -> tuple[str, str]`, `refresh_failure(path, cause, at, previous) -> dict`
- `takeover_payload(entry, lock, now=None) -> dict`
- `details_payload(entry, details=None, *, now=None, client="", error=None, query="", stamp="", open_key="") -> dict`
- `session_export_rows(entries, *, labels) -> list[list]`, `EXPORT_COLUMNS`, `detail_export_rows(details) -> list[dict]`

---

### Task 1: Backend seams (the details loader, the stale threshold, the two workers)

**Files:**
- Create: `packing_tool/session_details.py`
- Modify: `packing_tool/session_registry_manager.py` (the `STALE_HEARTBEAT_SECONDS` constant)
- Modify: `gui/workers.py` (append two classes)
- Test: `tests/test_session_details.py` (new), `tests/test_session_workers.py` (new), `tests/test_session_registry.py`

**Interfaces:**
- Consumes: `packing_tool.packer_logic.compute_order_timing_metrics(orders) -> dict`.
- Produces:
  - `load_session_details(entry: dict) -> dict` with keys `record`, `packing_state`, `session_info`, `session_summary`; raises `SessionFilesError`.
  - `SessionFilesError(path, cause)` with `.path: str`, `.cause: str`.
  - `error_cause(error: Exception) -> str`.
  - `gui.workers.RegistryRefreshWorker(registry_manager, client_id, parent=None)` with `refresh_complete = Signal(str, list)` and `refresh_failed = Signal(str, str)`.
  - `gui.workers.SessionDetailsWorker(key, entry, parent=None)` with `loaded = Signal(str, object)` and `failed = Signal(str, str, str)` (key, path, cause).

`gui/session_browser/` still exists until Task 7 and keeps its own copy of `RegistryRefreshWorker`. Leave it alone here.

- [ ] **Step 1: Write the failing loader tests**

Create `tests/test_session_details.py`:

```python
"""Reading a session's files for Session details (spec section 7.1).

Ported from tests/test_session_detail_page.py, which built a Qt page to reach
the same loader.
"""

import json

import pytest

from packing_tool.session_details import (
    SessionFilesError,
    load_session_details,
    partial_summary,
)


@pytest.fixture
def work_dir(tmp_path):
    path = tmp_path / "2026-09-29_1" / "packing" / "DHL_Orders"
    path.mkdir(parents=True)
    return path


def _entry(work_dir, **over):
    entry = {
        "session_id": "2026-09-29_1",
        "status": "completed",
        "work_dir": str(work_dir),
        "packing_list_name": "Registry_Name",
    }
    entry.update(over)
    return entry


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_a_registry_entry_loads_its_details_from_the_summary(work_dir):
    _write(
        work_dir / "session_summary.json",
        {
            "session_id": "2026-09-29_1",
            "worker_name": "W-004",
            "pc_name": "WH-PC-02",
            "total_orders": 14,
            "completed_orders": 9,
            "total_items": 62,
        },
    )
    record = load_session_details(_entry(work_dir))["record"]
    assert record["worker_name"] == "W-004"
    assert record["pc_name"] == "WH-PC-02"
    assert (record["completed_orders"], record["total_orders"]) == (9, 14)
    assert record["total_items_packed"] == 62


def test_the_list_name_comes_from_the_summary(work_dir):
    _write(
        work_dir / "session_summary.json",
        {"session_id": "2026-09-29_1", "packing_list_name": "DHL_Orders"},
    )
    assert load_session_details(_entry(work_dir))["record"]["packing_list_name"] == "DHL_Orders"


def test_the_list_name_falls_back_to_the_registry(work_dir):
    _write(work_dir / "session_summary.json", {"session_id": "2026-09-29_1"})
    assert load_session_details(_entry(work_dir))["record"]["packing_list_name"] == "Registry_Name"


def test_an_unfinished_list_loads_from_packing_state_alone(work_dir):
    """The Shopify flow writes no per-list session_info.json, so a list still
    being packed has packing_state.json and nothing else."""
    _write(
        work_dir / "packing_state.json",
        {
            "started_at": "2026-09-29T08:10:00",
            "pc_name": "WH-PC-02",
            "progress": {"total_orders": 5},
            "completed": [{"order_number": "1001", "items_count": 2}],
            "in_progress": {},
        },
    )
    details = load_session_details(_entry(work_dir, status="in_progress"))
    record = details["record"]
    assert record["packing_list_name"] == "Registry_Name"
    assert record["start_time"] == "2026-09-29T08:10:00"
    assert record["pc_name"] == "WH-PC-02"
    assert (record["completed_orders"], record["total_orders"]) == (1, 5)
    assert details["session_summary"]["orders"] == [{"order_number": "1001", "items_count": 2}]


def test_a_partial_summary_has_timing_when_the_orders_were_timed():
    state = {
        "started_at": "2026-09-29T08:00:00",
        "last_updated": "2026-09-29T09:00:00",
        "progress": {"total_orders": 4},
        "completed": [
            {"order_number": "1", "duration_seconds": 60, "items_count": 3, "items": []},
            {"order_number": "2", "duration_seconds": 120, "items_count": 1, "items": []},
        ],
        "skipped_orders": ["3"],
        "skipped_orders_timing": {"3": "2026-09-29T08:30:00"},
    }
    summary = partial_summary(state, {})
    assert summary["metrics"]["avg_time_per_order"] == 90
    assert summary["metrics"]["orders_per_hour"] == 2.0
    assert summary["duration_seconds"] == 3600
    assert summary["skipped_orders"] == [
        {"order_number": "3", "skipped_at": "2026-09-29T08:30:00", "status": "skipped"}
    ]


def test_a_partial_summary_without_durations_has_no_metrics():
    state = {"completed": [{"order_number": "1", "items_count": 3}], "skipped_orders": []}
    summary = partial_summary(state, {})
    assert summary["metrics"] == {}
    assert summary["orders"] == [{"order_number": "1", "items_count": 3}]


def test_nothing_completed_means_no_partial_summary():
    assert partial_summary({"completed": [], "skipped_orders": ["3"]}, {}) == {}


def test_an_unreadable_summary_names_the_file_and_the_cause(work_dir):
    (work_dir / "session_summary.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SessionFilesError) as caught:
        load_session_details(_entry(work_dir))
    assert caught.value.path.endswith("session_summary.json")
    assert "not valid JSON" in caught.value.cause


def test_an_unreadable_state_file_is_an_error_too(work_dir):
    (work_dir / "packing_state.json").write_text("[", encoding="utf-8")
    with pytest.raises(SessionFilesError) as caught:
        load_session_details(_entry(work_dir))
    assert caught.value.path.endswith("packing_state.json")


def test_a_work_dir_with_no_files_says_so(work_dir):
    with pytest.raises(SessionFilesError) as caught:
        load_session_details(_entry(work_dir))
    assert caught.value.path == str(work_dir)
    assert caught.value.cause == "it holds no session files"


def test_an_entry_with_no_work_dir_says_so():
    with pytest.raises(SessionFilesError) as caught:
        load_session_details({"session_id": "2026-09-29_1"})
    assert caught.value.cause == "it has no work folder"


def test_an_unreadable_session_info_is_skipped(work_dir):
    _write(work_dir / "session_summary.json", {"session_id": "2026-09-29_1"})
    (work_dir.parent / "session_info.json").write_text("{", encoding="utf-8")
    assert load_session_details(_entry(work_dir))["session_info"] == {}
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_details.py`
Expected: an import error, `No module named 'packing_tool.session_details'`.

- [ ] **Step 3: Write `packing_tool/session_details.py`**

`partial_summary` is `SessionDetailPage._build_partial_summary` from `gui/session_browser/session_detail_page.py`, moved unchanged apart from its name and the import at the top.

```python
"""Read one session's files for the Session details page. No Qt.

What gui/session_browser/session_detail_page.py did inside a widget. A file
that exists and cannot be read is an error with the file's path and the
cause (frame 8f), where the widget logged it and showed an empty page.

Spec: docs/superpowers/specs/2026-10-08-ui-refresh-phase4-sessions-design.md
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from packing_tool.packer_logic import compute_order_timing_metrics

logger = logging.getLogger(__name__)


class SessionFilesError(Exception):
    """A session's files could not be read: which path, and why."""

    def __init__(self, path, cause: str):
        super().__init__(f"{path}: {cause}")
        self.path = str(path)
        self.cause = cause


def error_cause(error: Exception) -> str:
    """The cause as the end of a sentence: lower case first, no full stop."""
    if isinstance(error, json.JSONDecodeError):
        return f"it is not valid JSON (line {error.lineno})"
    text = (getattr(error, "strerror", None) or str(error) or type(error).__name__).strip()
    return (text[:1].lower() + text[1:]).rstrip(".")


def _read(path: Path, *, required: bool) -> dict:
    """The file's dict; {} when it is absent.

    json.load, not the JSON cache: a refresh must see the file as it is now.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as error:  # json.JSONDecodeError is a ValueError
        if required:
            raise SessionFilesError(path, error_cause(error)) from error
        logger.warning("Could not read %s: %s", path, error)
        return {}
    return data if isinstance(data, dict) else {}


def partial_summary(packing_state: dict, session_info: dict) -> dict:
    """A session_summary-shaped dict for a session that has no summary file.

    The same metrics generate_session_summary() computes, from what
    packing_state.json holds. {} when no order was completed.
    """
    completed_orders = packing_state.get("completed", [])
    if not completed_orders:
        return {}

    orders_with_timing = [
        o for o in completed_orders if isinstance(o, dict) and o.get("duration_seconds")
    ]
    completed_dicts = [o for o in completed_orders if isinstance(o, dict)]
    skipped = packing_state.get("skipped_orders", [])
    total_orders = packing_state.get("progress", {}).get("total_orders", 0)
    started_at = session_info.get("started_at") or packing_state.get("started_at")

    if not orders_with_timing:
        return {
            "metrics": {},
            "orders": completed_dicts,
            "skipped_orders": [
                {"order_number": n, "skipped_at": None, "status": "skipped"} for n in skipped
            ],
            "skipped_orders_count": len(skipped),
            "completed_orders": len(completed_dicts),
            "total_orders": total_orders,
            "started_at": started_at,
            "status": "incomplete",
        }

    timing_metrics = compute_order_timing_metrics(orders_with_timing)

    last_updated = packing_state.get("last_updated")
    duration_seconds = 0
    orders_per_hour = 0
    items_per_hour = 0
    if started_at and last_updated:
        try:
            start_dt = datetime.fromisoformat(started_at)
            end_dt = datetime.fromisoformat(last_updated)
            duration_seconds = max(0, int((end_dt - start_dt).total_seconds()))
            if duration_seconds > 0:
                hours = duration_seconds / 3600.0
                orders_per_hour = round(len(orders_with_timing) / hours, 1)
                total_items_packed = sum(o.get("items_count", 0) for o in orders_with_timing)
                if total_items_packed > 0:
                    items_per_hour = round(total_items_packed / hours, 1)
        except (ValueError, TypeError):
            pass

    in_progress_count = sum(
        1 for k in packing_state.get("in_progress", {}) if not k.startswith("_")
    )
    skipped_timing = packing_state.get("skipped_orders_timing", {})
    return {
        "status": "incomplete",
        "started_at": started_at,
        "completed_at": last_updated,
        "duration_seconds": duration_seconds,
        "total_orders": total_orders,
        "completed_orders": len(completed_dicts),
        "in_progress_orders": in_progress_count,
        "skipped_orders_count": len(skipped),
        "metrics": {
            **timing_metrics,
            "orders_per_hour": orders_per_hour,
            "items_per_hour": items_per_hour,
        },
        "orders": completed_dicts,
        "skipped_orders": [
            {"order_number": n, "skipped_at": skipped_timing.get(n), "status": "skipped"}
            for n in skipped
        ],
    }


def load_session_details(entry: dict) -> dict:
    """{'record', 'packing_state', 'session_info', 'session_summary'} for a registry entry.

    Raises SessionFilesError when the summary or the state file exists and
    cannot be read, or when the session has neither.
    """
    work_dir = entry.get("work_dir") or ""
    session_id = entry.get("session_id", "")
    if not work_dir:
        raise SessionFilesError(session_id, "it has no work folder")
    work = Path(work_dir)

    summary = _read(work / "session_summary.json", required=True)
    state = _read(work / "packing_state.json", required=True)
    info = _read(work.parent / "session_info.json", required=False)
    if not summary and not state:
        raise SessionFilesError(work, "it holds no session files")

    client_id = entry.get("client_id")
    list_name = entry.get("packing_list_name", "")
    if summary:
        record = {
            "session_id": summary.get("session_id", session_id),
            "client_id": summary.get("client_id", client_id),
            "packing_list_path": summary.get("packing_list_path", ""),
            "packing_list_name": summary.get("packing_list_name") or list_name,
            "worker_id": summary.get("worker_id", ""),
            "worker_name": summary.get("worker_name", ""),
            "pc_name": summary.get("pc_name", ""),
            "start_time": summary.get("started_at", ""),
            "end_time": summary.get("completed_at", ""),
            "duration_seconds": summary.get("duration_seconds", 0),
            "total_orders": summary.get("total_orders", 0),
            "completed_orders": summary.get("completed_orders", 0),
            "in_progress_orders": summary.get("in_progress_orders", 0),
            "skipped_orders_count": summary.get("skipped_orders_count", 0),
            "total_items_packed": summary.get("total_items", 0),
        }
    else:
        completed = [o for o in state.get("completed", []) if isinstance(o, dict)]
        record = {
            "session_id": info.get("session_id", session_id),
            "client_id": info.get("client_id", client_id),
            "packing_list_path": info.get("packing_list_path", ""),
            "packing_list_name": info.get("packing_list_name") or list_name,
            "worker_id": info.get("worker_id", ""),
            "worker_name": info.get("worker_name", ""),
            "pc_name": info.get("pc_name") or state.get("pc_name", ""),
            "start_time": info.get("started_at") or state.get("started_at", ""),
            "end_time": None,
            "duration_seconds": 0,
            "total_orders": state.get("progress", {}).get("total_orders", 0),
            "completed_orders": len(completed),
            "in_progress_orders": sum(
                1 for k in state.get("in_progress", {}) if not k.startswith("_")
            ),
            "skipped_orders_count": len(state.get("skipped_orders", [])),
            "total_items_packed": sum(o.get("items_count", 0) for o in completed),
        }
        summary = partial_summary(state, info)

    return {
        "record": record,
        "packing_state": state,
        "session_info": info,
        "session_summary": summary,
    }
```

- [ ] **Step 4: Run the loader tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_details.py`
Expected: 12 passed.

- [ ] **Step 5: The stale threshold. Write the failing test**

Append to `tests/test_session_registry.py`, after `test_a_silent_lock_reads_stale`:

```python
def test_stale_in_the_list_means_the_lock_can_be_taken(registry, tmp_path):
    """One threshold, the lock's: a row reads Stale exactly when Resume can
    take the session over (spec 2026-10-08 phase 4, section 5.5)."""
    entry, work_dir = _entry(tmp_path)
    _lock(work_dir, age_seconds=SessionLockManager.STALE_TIMEOUT + 10)
    assert registry._resolve_status(entry) == "stale"
    _lock(work_dir, age_seconds=SessionLockManager.STALE_TIMEOUT - 30)
    assert registry._resolve_status(entry) == "in_progress"
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_registry.py`
Expected: the new test fails on its first assertion (`'in_progress' == 'stale'`).

- [ ] **Step 6: Align the constant**

In `packing_tool/session_registry_manager.py` replace

```python
# Seconds before an "in_progress" heartbeat is considered stale
STALE_HEARTBEAT_SECONDS = 300  # 5 minutes
```

with

```python
# Seconds before an "in_progress" heartbeat is considered stale. The same as
# SessionLockManager.STALE_TIMEOUT: a session reads Stale in the list exactly
# when its lock can be taken over.
STALE_HEARTBEAT_SECONDS = 120
```

Run the file again. Expected: all pass.

- [ ] **Step 7: The workers. Write the failing tests**

Create `tests/test_session_workers.py`:

```python
"""The two workers behind the Sessions pages (gui/workers.py)."""

import json

from gui.workers import RegistryRefreshWorker, SessionDetailsWorker
from packing_tool.session_registry_manager import SessionRegistryManager


def test_a_refresh_returns_the_clients_entries(qtbot, profile_manager, server_root):
    (server_root / "Sessions" / "CLIENT_TEST").mkdir(parents=True)
    worker = RegistryRefreshWorker(SessionRegistryManager(profile_manager), "TEST")
    with qtbot.waitSignal(worker.refresh_complete, timeout=10000) as caught:
        worker.start()
    worker.wait(10000)
    assert caught.args == ["TEST", []]


def test_a_refresh_with_the_server_away_fails_with_the_cause(qtbot, profile_manager):
    """read_registry answers an unreachable server with an empty registry, so
    the list said "No sessions yet" during an outage."""
    profile_manager.base_path = profile_manager.base_path / "gone"
    worker = RegistryRefreshWorker(SessionRegistryManager(profile_manager), "TEST")
    with qtbot.waitSignal(worker.refresh_failed, timeout=10000) as caught:
        worker.start()
    worker.wait(10000)
    assert caught.args[0] == "TEST"
    assert caught.args[1]  # the OS's own words


def test_details_are_loaded_off_the_ui_thread(qtbot, tmp_path):
    work_dir = tmp_path / "2026-09-29_1" / "packing" / "DHL_Orders"
    work_dir.mkdir(parents=True)
    (work_dir / "session_summary.json").write_text(
        json.dumps({"session_id": "2026-09-29_1", "total_orders": 3}), encoding="utf-8"
    )
    entry = {"session_id": "2026-09-29_1", "packing_list_name": "DHL_Orders", "work_dir": str(work_dir)}
    worker = SessionDetailsWorker("2026-09-29_1|DHL_Orders", entry)
    with qtbot.waitSignal(worker.loaded, timeout=10000) as caught:
        worker.start()
    worker.wait(10000)
    key, details = caught.args
    assert key == "2026-09-29_1|DHL_Orders"
    assert details["record"]["total_orders"] == 3


def test_details_that_cannot_be_read_report_the_file(qtbot, tmp_path):
    work_dir = tmp_path / "2026-09-29_1" / "packing" / "DHL_Orders"
    work_dir.mkdir(parents=True)
    (work_dir / "packing_state.json").write_text("{", encoding="utf-8")
    entry = {"session_id": "2026-09-29_1", "packing_list_name": "DHL_Orders", "work_dir": str(work_dir)}
    worker = SessionDetailsWorker("k", entry)
    with qtbot.waitSignal(worker.failed, timeout=10000) as caught:
        worker.start()
    worker.wait(10000)
    key, path, cause = caught.args
    assert key == "k"
    assert path.endswith("packing_state.json")
    assert "not valid JSON" in cause
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_workers.py`
Expected: an import error for `RegistryRefreshWorker`.

- [ ] **Step 8: Append the workers to `gui/workers.py`**

Add `import os` to the imports at the top of the file, and `from packing_tool.session_details import SessionFilesError, error_cause, load_session_details` after the PySide6 imports. Append at the end of the file:

```python
class RegistryRefreshWorker(QThread):
    """Reads a client's session registry off the UI thread.

    1. ensure_registry(): a one-time scan if the file is missing
    2. refresh_available_lists(): packing lists uploaded since
    3. get_all_entries(): every entry with its status resolved

    Both signals carry the client id, so an answer for a client the packer
    has already left can be dropped.
    """

    refresh_complete = Signal(str, list)  # (client_id, entries)
    refresh_failed = Signal(str, str)  # (client_id, cause)

    def __init__(self, registry_manager, client_id: str, parent=None):
        super().__init__(parent)
        self._registry = registry_manager
        self._client_id = client_id

    def run(self) -> None:
        try:
            # read_registry answers an unreachable server with an empty
            # registry. Listing the server's root first lets the real error
            # out, so the page can say the refresh failed (frame 7f).
            os.listdir(self._registry.profile_manager.base_path)
            self._registry.ensure_registry(self._client_id)
            self._registry.refresh_available_lists(self._client_id)
            entries = self._registry.get_all_entries(self._client_id)
        except Exception as error:
            logger.exception("RegistryRefreshWorker failed")
            self.refresh_failed.emit(self._client_id, error_cause(error))
        else:
            self.refresh_complete.emit(self._client_id, entries)


class SessionDetailsWorker(QThread):
    """Reads one session's files off the UI thread (spec section 7.1)."""

    loaded = Signal(str, object)  # (key, details)
    failed = Signal(str, str, str)  # (key, path, cause)

    def __init__(self, key: str, entry: dict, parent=None):
        super().__init__(parent)
        self._key = key
        self._entry = dict(entry)

    def run(self) -> None:
        try:
            details = load_session_details(self._entry)
        except SessionFilesError as error:
            self.failed.emit(self._key, error.path, error.cause)
        except Exception as error:
            logger.exception("SessionDetailsWorker failed")
            self.failed.emit(self._key, str(self._entry.get("work_dir", "")), error_cause(error))
        else:
            self.loaded.emit(self._key, details)
```

- [ ] **Step 9: Run the worker tests, then the suite and the linter**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_workers.py`
Expected: 4 passed.

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: all pass. A test elsewhere that pinned the 5-minute threshold is updated to the 2-minute one.

Run: `.venv/bin/ruff check . --exclude shared`
Expected: no findings.

- [ ] **Step 10: Commit**

Stage `packing_tool/session_details.py`, `packing_tool/session_registry_manager.py`, `gui/workers.py`, `tests/test_session_details.py`, `tests/test_session_workers.py`, `tests/test_session_registry.py`. Message: `feat: session details loader, refresh and details workers, one stale threshold`.

---

### Task 2: Pure payloads for the list, the pane, the question and the list export

**Files:**
- Create: `gui/sessions_payload.py`
- Test: `tests/test_sessions_payload.py` (new)

**Interfaces:**
- Consumes: `shared.metadata_utils.parse_timestamp(str) -> datetime | None` (aware; a naive stamp is read as UTC).
- Produces: `STATUS`, `TABS`, `status_chip(status) -> dict`, `session_key(entry) -> str`, `row_action(entry, *, open_key="", server_down=False) -> dict` (keys `action`, `actionLabel`, `enabled`, `note`, `warn`), `fmt_age`, `fmt_duration`, `fmt_touched`, `default_range(now)`, `visible_entries(...)`, `sessions_payload(...)`, `refresh_failure(...)`, `takeover_payload(...)`, `EXPORT_COLUMNS`, `session_export_rows(...)`. Signatures are in the file map's list above. Task 3 appends `details_payload` and `detail_export_rows` to the same module and reuses `_n`, `_at`, `_now`, `_day`, `_clock`, `_why`, `plural`, `NOTHING`.

The shape `sessions_payload` returns (Task 4's page reads exactly these keys):

```
mode         "loading" | "ready" | "empty"
refreshing   bool
stamp        "14:06:31" or ""
auto         bool
failed       bool
failure      {} or {"path", "cause", "at", "from"}
tab          "all" | "open" | "finished" | "abandoned"
tabs         [{"key", "label", "count"}]
query        the search as typed
dateFrom     "2026-09-07" or ""        dateTo  likewise
rows         [row]
shown        int      inTab  int
count        "40 sessions" | "12 of 40 sessions" | "–"
noMatch      bool     noMatchText  str
exportTitle  "Export the 40 sessions shown"
```

A row: `key`, `id`, `list`, `status`, `label`, `tone` (`neutral`, `info`, `warning`, `success`, `danger`), `manual`, `age`, `orders`, `pct`, `items`, `touched`, `setBy`, `why`, `ordersNote`, `facts` (`[{"label", "value"}]`, seven of them), `action` (`start`, `resume`, `details`, `show` or `""`), `actionLabel`, `enabled`, `note`, `warn`, `canDetails`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sessions_payload.py`:

```python
"""What the Sessions pages say (spec 2026-10-08 phase 4, sections 5, 6 and 8).

Ported from test_sessions_list_columns.py, test_sessions_list_status.py and
test_sessions_list_empty.py, which asked a Qt table the same questions.
"""

from datetime import UTC, datetime, timedelta

import pytest

from gui.sessions_payload import (
    EXPORT_COLUMNS,
    STATUS,
    default_range,
    fmt_age,
    fmt_duration,
    fmt_touched,
    refresh_failure,
    row_action,
    session_export_rows,
    session_key,
    sessions_payload,
    status_chip,
    takeover_payload,
    visible_entries,
)

NOW = datetime(2026, 10, 7, 14, 6, 31, tzinfo=UTC)


def ago(**delta) -> str:
    return (NOW - timedelta(**delta)).isoformat()


def entry(**over) -> dict:
    base = {
        "session_id": "2026-10-06_2",
        "packing_list_name": "Afternoon_wave",
        "status": "paused",
        "worker_id": "W-002",
        "worker_name": "Maria",
        "pc_name": "WH-PC-02",
        "started_at": "2026-10-06T09:00:00+00:00",
        "last_updated": "2026-10-06T11:20:00+00:00",
        "total_orders": 110,
        "completed_orders": 71,
        "skipped_orders": 2,
        "total_items": 402,
        "work_dir": "/srv/2026-10-06_2/packing/Afternoon_wave",
        "session_path": "/srv/2026-10-06_2",
        "metrics": None,
    }
    base.update(over)
    return base


def rows(entries, **kwargs):
    return sessions_payload(entries, now=NOW, **kwargs)["rows"]


def row(**over):
    kwargs = {k: over.pop(k) for k in ("open_key", "server_down") if k in over}
    return rows([entry(**over)], **kwargs)[0]


# --- the columns ----------------------------------------------------------------


def test_age_is_the_coarsest_unit_that_fits():
    assert fmt_age(ago(minutes=25), NOW) == "25m"
    assert fmt_age(ago(hours=3, minutes=10), NOW) == "3h"
    assert fmt_age(ago(days=13, hours=2), NOW) == "13d"
    assert fmt_age("", NOW) == "—"
    assert fmt_age("not a date", NOW) == "—"


def test_last_touched_folds_worker_pc_and_time_into_one_cell():
    touched = fmt_touched(entry(last_updated="2026-10-07T11:20:00+00:00"), NOW)
    assert touched == "Maria · WH-PC-02 · 11:20"


def test_last_touched_drops_the_clock_once_the_row_is_not_todays():
    """ "09:40" on a thirteen-day-old row reads as this morning."""
    touched = fmt_touched({"worker_name": "W-001", "last_updated": ago(days=13)}, NOW)
    assert touched == "W-001 · 13d ago"


def test_a_session_nobody_has_touched_shows_a_dash():
    assert fmt_touched({}, NOW) == "—"


def test_orders_is_how_far_the_session_got():
    assert row(total_orders=14, completed_orders=9)["orders"] == "9 / 14"
    assert row(total_orders=14, completed_orders=9)["pct"] == 64


def test_a_list_with_no_orders_known_shows_a_dash_not_zero_over_zero():
    bare = row(total_orders=0, completed_orders=0)
    assert bare["orders"] == "—"
    assert bare["pct"] == 0


def test_packing_is_the_lists_name_and_items_the_units_on_it():
    made = row()
    assert made["list"] == "Afternoon_wave"
    assert made["items"] == "402"
    assert row(total_items=0)["items"] == "—"


def test_durations_read_in_two_units():
    assert fmt_duration(None) == "—"
    assert fmt_duration(0) == "—"
    assert fmt_duration(45) == "45s"
    assert fmt_duration(245) == "4m 5s"
    assert fmt_duration(3 * 3600 + 12 * 60 + 9) == "3h 12m"


# --- the status chip ------------------------------------------------------------


def test_only_the_two_states_a_packer_declares_carry_the_solid_dot():
    assert {key for key, chip in STATUS.items() if chip["manual"]} == {"paused", "incomplete"}


def test_the_tones_are_the_mockups():
    assert {key: chip["tone"] for key, chip in STATUS.items()} == {
        "not_started": "neutral",
        "in_progress": "info",
        "paused": "warning",
        "stale": "warning",
        "completed": "success",
        "incomplete": "danger",
        "abandoned": "neutral",
    }


def test_an_unknown_status_still_makes_a_chip():
    assert status_chip("something_new") == {
        "label": "Something new",
        "tone": "neutral",
        "manual": False,
    }


def test_a_row_carries_its_chip():
    made = row(status="in_progress")
    assert (made["label"], made["tone"], made["manual"]) == ("Active", "info", False)
    assert made["setBy"] == "Set by the system"
    assert row()["setBy"] == "Set by a person"


# --- tabs, dates, search, order ---------------------------------------------------


def _mixed():
    return [
        entry(session_id="a", status="not_started"),
        entry(session_id="b", status="in_progress"),
        entry(session_id="c", status="paused"),
        entry(session_id="d", status="stale"),
        entry(session_id="e", status="completed"),
        entry(session_id="f", status="incomplete"),
        entry(session_id="g", status="abandoned"),
        entry(session_id="h", status="something_new"),
    ]


def test_the_tabs_group_the_seven_statuses():
    payload = sessions_payload(_mixed(), now=NOW)
    assert [(tab["key"], tab["label"], tab["count"]) for tab in payload["tabs"]] == [
        ("all", "All", 8),
        ("open", "Open", 4),
        ("finished", "Finished", 2),
        ("abandoned", "Abandoned", 1),
    ]
    assert [r["id"] for r in rows(_mixed(), tab="finished")] == ["e", "f"]
    assert sessions_payload(_mixed(), now=NOW, tab="nonsense")["tab"] == "all"


def test_a_tabs_count_ignores_the_search_but_not_the_dates():
    entries = [entry(session_id="a"), entry(session_id="b", started_at=ago(days=60))]
    payload = sessions_payload(entries, now=NOW, query="zzz")
    assert payload["tabs"][0]["count"] == 1


def test_the_range_starts_as_the_last_thirty_days():
    assert default_range(NOW) == ("2026-09-07", "2026-10-07")
    payload = sessions_payload([], now=NOW)
    assert (payload["dateFrom"], payload["dateTo"]) == ("2026-09-07", "2026-10-07")


def test_a_session_older_than_the_range_is_left_out_until_from_is_emptied():
    old = entry(session_id="old", started_at=ago(days=45))
    assert rows([old]) == []
    assert [r["id"] for r in rows([old], date_from="")] == ["old"]


def test_a_list_nobody_started_is_dated_by_when_it_was_made():
    made = {"session_id": "n", "packing_list_name": "L", "status": "not_started",
            "created_at": ago(days=45), "total_orders": 3}
    assert rows([made]) == []
    assert len(rows([made], date_from="2026-08-01")) == 1


def test_a_session_with_no_readable_date_is_always_listed():
    assert len(rows([entry(started_at="", last_updated="")], date_from="2026-10-07")) == 1


def test_to_is_inclusive():
    assert len(rows([entry()], date_from="2026-10-06", date_to="2026-10-06")) == 1
    assert rows([entry()], date_from="2026-10-01", date_to="2026-10-05") == []


@pytest.mark.parametrize("query", ["afternoon", "2026-10-06", "MARIA", "w-002", "wh-pc"])
def test_the_search_matches_list_id_worker_and_pc(query):
    entries = [entry(), entry(session_id="zzz", packing_list_name="Other", worker_name="Ivan",
                              worker_id="W-009", pc_name="PACK-01")]
    assert [r["id"] for r in rows(entries, query=query)] == ["2026-10-06_2"]


def test_newest_first():
    entries = [
        entry(session_id="old", started_at=ago(days=3)),
        entry(session_id="new", started_at=ago(hours=1)),
        entry(session_id="mid", started_at=ago(days=1)),
    ]
    assert [r["id"] for r in rows(entries)] == ["new", "mid", "old"]


def test_visible_entries_is_what_the_page_shows():
    entries = [entry(session_id="a"), entry(session_id="b", status="completed")]
    shown, in_tab, in_dates = visible_entries(
        entries, now=NOW, tab="finished", query="", date_from="", date_to="")
    assert [e["session_id"] for e in shown] == ["b"]
    assert len(in_tab) == 1 and len(in_dates) == 2


# --- states ---------------------------------------------------------------------


def test_no_sessions_at_all_is_its_own_state():
    payload = sessions_payload([], now=NOW)
    assert payload["mode"] == "empty"
    assert payload["noMatch"] is False
    assert payload["count"] == "0 sessions"


def test_before_the_first_answer_the_page_is_loading():
    payload = sessions_payload([], now=NOW, loaded=False, refreshing=True)
    assert payload["mode"] == "loading"
    assert payload["rows"] == []
    assert payload["count"] == "–"


def test_filters_that_match_nothing_say_so():
    payload = sessions_payload([entry()], now=NOW, tab="open", query="2025-12")
    assert payload["mode"] == "ready"
    assert payload["noMatch"] is True
    assert payload["noMatchText"] == (
        "Nothing in Open between 7 Sep and 7 Oct has “2025-12” in its id, "
        "packing list, worker or PC."
    )
    assert payload["count"] == "0 of 1 sessions"


@pytest.mark.parametrize("kwargs, text", [
    ({"tab": "finished"}, "No finished sessions between 7 Sep and 7 Oct."),
    ({"tab": "all", "date_to": "2026-10-01"}, "No sessions between 7 Sep and 1 Oct."),
    ({"tab": "finished", "date_to": ""}, "No finished sessions since 7 Sep."),
    ({"tab": "finished", "date_from": ""}, "No finished sessions up to 7 Oct."),
    ({"tab": "finished", "date_from": "", "date_to": ""}, "No finished sessions."),
    ({"tab": "all", "query": "zz"},
     "Nothing between 7 Sep and 7 Oct has “zz” in its id, packing list, worker or PC."),
])
def test_the_no_match_sentence_names_the_tab_the_range_and_the_query(kwargs, text):
    assert sessions_payload([entry()], now=NOW, **kwargs)["noMatchText"] == text


def test_the_count_and_the_export_title_follow_what_is_shown():
    payload = sessions_payload([entry(session_id="a"), entry(session_id="b")], now=NOW)
    assert payload["count"] == "2 sessions"
    assert payload["exportTitle"] == "Export the 2 sessions shown"
    one = sessions_payload([entry(session_id="a"), entry(session_id="b")], now=NOW, query="a")
    assert one["shown"] == 1 and one["inTab"] == 2
    assert one["count"] == "1 of 2 sessions"
    assert one["exportTitle"] == "Export the 1 session shown"


def test_a_failed_refresh_keeps_the_list_and_says_where_it_is_from():
    failure = refresh_failure("/srv/Sessions/CLIENT_ACME", "the network path was not found.",
                              "14:08:31", "14:06:31")
    assert failure == {
        "path": "/srv/Sessions/CLIENT_ACME",
        "cause": "the network path was not found",
        "at": "14:08:31",
        "from": "14:06:31",
    }
    payload = sessions_payload([entry()], now=NOW, failure=failure, stamp="14:06:31")
    assert payload["failed"] is True
    assert payload["failure"] == failure
    assert len(payload["rows"]) == 1
    assert sessions_payload([entry()], now=NOW)["failure"] == {}


# --- a row's action (section 5.5) -------------------------------------------------


def test_a_list_nobody_started_starts():
    made = row(status="not_started", work_dir="")
    assert (made["action"], made["actionLabel"], made["enabled"]) == ("start", "Start packing", True)
    assert made["canDetails"] is False


@pytest.mark.parametrize("status", ["paused", "incomplete"])
def test_a_paused_or_incomplete_session_resumes(status):
    made = row(status=status)
    assert (made["action"], made["actionLabel"], made["enabled"]) == ("resume", "Resume session", True)
    assert made["note"] == ""
    assert made["canDetails"] is True


def test_a_stale_session_resumes_with_a_warning():
    made = row(status="stale")
    assert (made["action"], made["enabled"], made["warn"]) == ("resume", True, True)
    assert made["note"] == (
        "WH-PC-02 stopped responding. You will be asked before this PC takes over."
    )


def test_a_session_active_elsewhere_cannot_be_resumed():
    made = row(status="in_progress")
    assert (made["action"], made["actionLabel"], made["enabled"]) == ("resume", "Resume session", False)
    assert made["warn"] is False
    assert made["note"] == (
        "Open on WH-PC-02 right now. It can be taken over once that PC stops responding."
    )


def test_the_session_open_here_goes_to_packing():
    key = session_key(entry())
    made = row(status="in_progress", open_key=key)
    assert (made["action"], made["actionLabel"], made["enabled"]) == ("show", "Go to Packing", True)
    assert made["why"] == "open on this PC"
    assert {"label": "PC", "value": "WH-PC-02 (this PC)"} in made["facts"]


@pytest.mark.parametrize("status", ["completed", "abandoned"])
def test_a_finished_or_abandoned_session_shows_its_details(status):
    made = row(status=status)
    assert (made["action"], made["actionLabel"], made["enabled"]) == ("details", "View details", True)
    assert made["canDetails"] is False  # the primary action already is


@pytest.mark.parametrize("status", ["not_started", "paused", "stale", "in_progress"])
def test_another_session_open_here_disables_start_and_resume(status):
    made = row(status=status, open_key="2026-10-07_1|Morning_wave")
    assert made["enabled"] is False
    assert made["note"] == "2026-10-07_1 is open on this PC. End it before opening another."


def test_details_stay_reachable_with_another_session_open():
    assert row(status="completed", open_key="x|y")["enabled"] is True
    assert row(status="paused", open_key="x|y")["canDetails"] is True


def test_the_server_being_down_disables_start_and_resume():
    made = row(status="paused", server_down=True)
    assert made["enabled"] is False
    assert made["note"] == "Server unreachable. Sessions cannot be opened until it answers."
    assert row(status="completed", server_down=True)["enabled"] is True


def test_an_unknown_status_offers_details_only_when_there_are_files():
    assert row(status="something_new")["action"] == "details"
    bare = row(status="something_new", work_dir="")
    assert (bare["action"], bare["actionLabel"], bare["enabled"]) == ("", "", False)


def test_row_action_is_the_rows_action():
    assert row_action(entry(status="paused")) == {
        "action": "resume", "actionLabel": "Resume session", "enabled": True,
        "note": "", "warn": False,
    }
    assert row_action(entry(status="paused"), server_down=True)["enabled"] is False


# --- the pane (section 5.3) --------------------------------------------------------


def test_the_pane_has_seven_facts():
    made = row(metrics={"total_corrections": 4, "total_unknown_scans": 1},
               duration_seconds=3 * 3600 + 12 * 60)
    assert made["facts"] == [
        {"label": "Worker", "value": "Maria"},
        {"label": "PC", "value": "WH-PC-02"},
        {"label": "Duration", "value": "3h 12m"},
        {"label": "Items", "value": "402"},
        {"label": "Scan corrections", "value": "4"},
        {"label": "Unknown scans", "value": "1"},
        {"label": "Last touched", "value": "6 Oct, 11:20"},
    ]
    assert made["ordersNote"] == "2 skipped"


def test_an_active_sessions_duration_is_so_far():
    made = row(status="in_progress", started_at=ago(hours=3, minutes=12), duration_seconds=None)
    assert {"label": "Duration", "value": "3h 12m so far"} in made["facts"]


def test_a_session_with_no_metrics_shows_dashes():
    made = row(skipped_orders=0)
    assert {"label": "Scan corrections", "value": "—"} in made["facts"]
    assert {"label": "Unknown scans", "value": "—"} in made["facts"]
    assert {"label": "Duration", "value": "—"} in made["facts"]
    assert made["ordersNote"] == "None skipped"


@pytest.mark.parametrize("over, sentence", [
    ({"status": "not_started"}, "no orders packed yet"),
    ({"status": "in_progress"}, "scans arriving from WH-PC-02"),
    ({"status": "paused"}, "paused by Maria, 6 Oct, 11:20"),
    ({"status": "paused", "last_updated": "2026-10-07T11:20:00+00:00"}, "paused by Maria, 11:20"),
    ({"status": "paused", "worker_name": "", "worker_id": ""}, "paused, 6 Oct, 11:20"),
    ({"status": "stale"}, "WH-PC-02 stopped responding, 6 Oct, 11:20"),
    ({"status": "completed"}, "every order packed"),
    ({"status": "incomplete"}, "closed by Maria with 39 orders unpacked"),
    ({"status": "incomplete", "completed_orders": 109}, "closed by Maria with 1 order unpacked"),
    ({"status": "abandoned", "last_updated": "2026-10-02T10:00:00+00:00"}, "untouched for 5 days"),
    ({"status": "something_new"}, ""),
])
def test_the_sentence_after_set_by(over, sentence):
    assert row(**over)["why"] == sentence


def test_a_bare_entry_still_makes_a_row():
    """Review focus 1: an entry with almost nothing in it."""
    made = rows([{"session_id": "x", "status": "paused", "total_orders": None,
                  "completed_orders": None, "metrics": None, "worker_name": None,
                  "pc_name": None, "started_at": None}])[0]
    assert made["key"] == "x|"
    assert made["age"] == "—"
    assert made["touched"] == "—"
    assert made["orders"] == "—"
    assert made["why"] == "paused"
    assert made["facts"][0] == {"label": "Worker", "value": "—"}
    assert made["facts"][1] == {"label": "PC", "value": "—"}
    stale = rows([{"session_id": "x", "status": "stale"}])[0]
    assert stale["note"] == (
        "Another PC stopped responding. You will be asked before this PC takes over."
    )


# --- the take-over question (section 6) --------------------------------------------


def test_the_question_says_who_had_it_and_what_comes_along():
    lock = {"locked_by": "WH-PC-02", "worker_name": "Georgi",
            "heartbeat": "2026-10-07T13:52:10+00:00"}
    made = takeover_payload(entry(session_id="2026-10-07_2", total_orders=96,
                                  completed_orders=52), lock, now=NOW)
    assert made == {
        "key": "2026-10-07_2|Afternoon_wave",
        "id": "2026-10-07_2",
        "body": "WH-PC-02 stopped responding at 13:52 while Georgi was packing. "
                "If it comes back, it is told the session moved here.",
        "carry": "Everything saved so far comes with you: 52 of 96 orders packed.",
    }


def test_the_question_drops_the_words_it_has_nothing_for():
    made = takeover_payload(entry(pc_name=""), {"locked_by": "", "worker_name": None,
                                                "heartbeat": ""}, now=NOW)
    assert made["body"] == (
        "Another PC stopped responding. If it comes back, it is told the session moved here."
    )


# --- the list export (section 8) ----------------------------------------------------


def test_the_export_keeps_todays_columns():
    assert EXPORT_COLUMNS == (
        "Status", "Packing List", "Session ID", "Worker", "PC", "Progress", "Started",
        "Duration (s)", "Total Items", "Total Orders", "Completed Orders", "Skipped Orders",
    )


def test_csv_writes_the_raw_status_and_excel_its_word():
    made = entry(duration_seconds=900)
    assert session_export_rows([made], labels=False) == [[
        "paused", "Afternoon_wave", "2026-10-06_2", "Maria", "WH-PC-02", "71/110",
        "2026-10-06T09:00:00+00:00", 900, 402, 110, 71, 2,
    ]]
    assert session_export_rows([made], labels=True)[0][0] == "Paused"


def test_an_export_row_of_a_bare_entry_has_blanks():
    assert session_export_rows([{"session_id": "x", "status": "not_started"}], labels=False) == [
        ["not_started", "", "x", "", "", "—", "", "", "", "", "", ""]
    ]
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_sessions_payload.py`
Expected: an import error, `No module named 'gui.sessions_payload'`.

- [ ] **Step 3: Write `gui/sessions_payload.py`**

```python
"""What the Sessions pages say (spec 2026-10-08 phase 4, sections 5 to 8).

Pure functions: no Qt objects, no I/O. gui/sessions_page.py feeds them
registry entries and a session's files; gui/web/app.js renders what they
return. `now` is passed in so a test, and the render script, can fix it;
every time is shown in `now`'s timezone.

Spec: docs/superpowers/specs/2026-10-08-ui-refresh-phase4-sessions-design.md
"""

from datetime import date, datetime, timedelta
from typing import Any

from shared.metadata_utils import parse_timestamp

# A status: its word, the badge's tone, and whether a packer declared it (a
# solid dot) or the system inferred it (a hollow one).
STATUS = {
    "not_started": {"label": "Not started", "tone": "neutral", "manual": False},
    "in_progress": {"label": "Active", "tone": "info", "manual": False},
    "paused": {"label": "Paused", "tone": "warning", "manual": True},
    "stale": {"label": "Stale", "tone": "warning", "manual": False},
    "completed": {"label": "Completed", "tone": "success", "manual": False},
    "incomplete": {"label": "Incomplete", "tone": "danger", "manual": True},
    "abandoned": {"label": "Abandoned", "tone": "neutral", "manual": False},
}

# (key, label, the statuses it holds; None is every status)
TABS = (
    ("all", "All", None),
    ("open", "Open", ("not_started", "in_progress", "paused", "stale")),
    ("finished", "Finished", ("completed", "incomplete")),
    ("abandoned", "Abandoned", ("abandoned",)),
)

DEFAULT_DAYS = 30
NOTHING = "—"
EXPORT_COLUMNS = (
    "Status", "Packing List", "Session ID", "Worker", "PC", "Progress", "Started",
    "Duration (s)", "Total Items", "Total Orders", "Completed Orders", "Skipped Orders",
)
_SEARCH_FIELDS = ("packing_list_name", "session_id", "worker_name", "worker_id", "pc_name")
# Not strftime("%b"): Qt can switch the process locale under us.
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_SERVER_DOWN = "Server unreachable. Sessions cannot be opened until it answers."


def _n(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _now(now: datetime | None) -> datetime:
    now = now or datetime.now().astimezone()
    return now if now.tzinfo else now.astimezone()


def _at(stamp: Any, now: datetime) -> datetime | None:
    """An ISO timestamp in `now`'s timezone; None when missing or unreadable."""
    if not stamp or not isinstance(stamp, str):
        return None
    parsed = parse_timestamp(stamp)
    return parsed.astimezone(now.tzinfo) if parsed else None


def _day(day: date) -> str:
    return f"{day.day} {_MONTHS[day.month - 1]}"


def _clock(at: datetime, now: datetime) -> str:
    """ "11:20" today, "6 Oct, 11:20" before that."""
    if at.date() == now.date():
        return f"{at:%H:%M}"
    return f"{_day(at)}, {at:%H:%M}"


def plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def status_chip(status: str) -> dict:
    """The chip for a status, including one the registry invented."""
    known = STATUS.get(status)
    if known:
        return dict(known)
    return {
        "label": str(status or "unknown").replace("_", " ").capitalize(),
        "tone": "neutral",
        "manual": False,
    }


def session_key(entry: dict) -> str:
    """What the page calls a row: a session holds one entry per packing list."""
    return f"{entry.get('session_id', '')}|{entry.get('packing_list_name', '')}"


def fmt_age(stamp: Any, now: datetime) -> str:
    """Since `stamp`, in the coarsest unit that fits: 25m, 3h, 13d."""
    at = _at(stamp, now)
    if at is None:
        return NOTHING
    seconds = max(0.0, (now - at).total_seconds())
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def fmt_duration(seconds: Any) -> str:
    if not seconds:
        return NOTHING
    seconds = float(seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {int(seconds % 60)}s"
    return f"{int(seconds)}s"


def fmt_touched(entry: dict, now: datetime) -> str:
    """Who last worked the session, on which PC, and when, in one cell."""
    worker = entry.get("worker_name") or entry.get("worker_id") or ""
    pc = entry.get("pc_name") or ""
    stamp = entry.get("last_updated") or entry.get("started_at") or entry.get("created_at")
    at = _at(stamp, now)
    when = ""
    if at is not None:
        recent = (now - at).total_seconds() < 86400
        when = f"{at:%H:%M}" if recent else f"{fmt_age(stamp, now)} ago"
    parts = [part for part in (worker, pc, when) if part]
    return " · ".join(parts) if parts else NOTHING


def default_range(now: datetime) -> tuple[str, str]:
    """From and To as the page starts: the last 30 days."""
    today = now.date()
    return (today - timedelta(days=DEFAULT_DAYS)).isoformat(), today.isoformat()


def _parse_day(text: Any) -> date | None:
    try:
        return date.fromisoformat(text) if text else None
    except (TypeError, ValueError):
        return None


def _range_text(start: date | None, end: date | None) -> str:
    if start and end:
        return f"between {_day(start)} and {_day(end)}"
    if start:
        return f"since {_day(start)}"
    if end:
        return f"up to {_day(end)}"
    return ""


def _started(entry: dict) -> Any:
    return entry.get("started_at") or entry.get("created_at")


def visible_entries(
    entries: list[dict], *, now: datetime, tab: str, query: str, date_from: str, date_to: str
) -> tuple[list[dict], list[dict], list[dict]]:
    """(shown, in the tab, in the dates). `shown` is newest first.

    The one filter: the page's rows and the export both come from it.
    """
    start, end = _parse_day(date_from), _parse_day(date_to)

    def in_range(entry: dict) -> bool:
        at = _at(_started(entry), now)
        if at is None:
            return True
        day = at.date()
        return (start is None or day >= start) and (end is None or day <= end)

    statuses = {key: held for key, _label, held in TABS}.get(tab)
    needle = str(query or "").strip().lower()

    def matches(entry: dict) -> bool:
        haystack = " ".join(str(entry.get(field) or "") for field in _SEARCH_FIELDS)
        return needle in haystack.lower()

    def epoch(entry: dict) -> float:
        at = _at(_started(entry), now)
        return at.timestamp() if at else 0.0

    in_dates = [entry for entry in entries if in_range(entry)]
    in_tab = [e for e in in_dates if statuses is None or e.get("status") in statuses]
    shown = sorted((e for e in in_tab if not needle or matches(e)), key=epoch, reverse=True)
    return shown, in_tab, in_dates


def _worker(entry: dict) -> str:
    return entry.get("worker_name") or entry.get("worker_id") or ""


def _why(entry: dict, key: str, now: datetime, open_key: str) -> str:
    """The sentence after "Set by ...": why the session has this status."""
    status = entry.get("status", "")
    worker = _worker(entry)
    pc = entry.get("pc_name") or ""
    at = _at(entry.get("last_updated") or entry.get("started_at"), now)

    def timed(text: str) -> str:
        return f"{text}, {_clock(at, now)}" if at else text

    if status == "not_started":
        return "no orders packed yet"
    if status == "in_progress":
        if open_key and key == open_key:
            return "open on this PC"
        return f"scans arriving from {pc}" if pc else "scans arriving"
    if status == "paused":
        return timed(f"paused by {worker}" if worker else "paused")
    if status == "stale":
        return timed(f"{pc} stopped responding" if pc else "stopped responding")
    if status == "completed":
        return "every order packed"
    if status == "incomplete":
        left = max(_n(entry.get("total_orders")) - _n(entry.get("completed_orders")), 0)
        closed = f"closed by {worker}" if worker else "closed"
        return f"{closed} with {plural(left, 'order', 'orders')} unpacked"
    if status == "abandoned":
        if at is None:
            return "untouched"
        return f"untouched for {plural(int((now - at).total_seconds() // 86400), 'day', 'days')}"
    return ""


def _action(entry: dict, key: str, *, open_key: str, server_down: bool) -> dict:
    """A row's one action, whether it can be taken, and why not (section 5.5)."""
    status = entry.get("status", "")
    has_files = bool(entry.get("work_dir"))

    def made(action, label, enabled=True, note="", warn=False):
        return {"action": action, "actionLabel": label, "enabled": enabled,
                "note": note, "warn": warn}

    if open_key and key == open_key:
        return made("show", "Go to Packing")
    if status in ("completed", "abandoned") or status not in STATUS:
        if has_files or status in STATUS:
            return made("details", "View details")
        return made("", "", enabled=False)

    start = status == "not_started"
    action, label = ("start", "Start packing") if start else ("resume", "Resume session")
    pc = entry.get("pc_name") or "Another PC"
    if open_key:
        open_id = open_key.split("|", 1)[0]
        return made(action, label, False,
                    f"{open_id} is open on this PC. End it before opening another.")
    if server_down:
        return made(action, label, False, _SERVER_DOWN)
    if status == "in_progress":
        where = pc if pc != "Another PC" else "another PC"
        return made(action, label, False,
                    f"Open on {where} right now. It can be taken over once that PC "
                    "stops responding.")
    if status == "stale":
        return made(action, label, True,
                    f"{pc} stopped responding. You will be asked before this PC takes over.",
                    warn=True)
    return made(action, label)


def row_action(entry: dict, *, open_key: str = "", server_down: bool = False) -> dict:
    """A session's action as the page shows it: what gui/sessions_page.py acts on."""
    return _action(entry, session_key(entry), open_key=open_key, server_down=server_down)


def _row(entry: dict, now: datetime, *, open_key: str, server_down: bool) -> dict:
    key = session_key(entry)
    status = entry.get("status", "")
    chip = status_chip(status)
    total = _n(entry.get("total_orders"))
    done = _n(entry.get("completed_orders"))
    skipped = _n(entry.get("skipped_orders"))
    items = _n(entry.get("total_items"))
    metrics = entry.get("metrics") or {}
    live = status == "in_progress"
    here = bool(open_key) and key == open_key

    seconds = entry.get("duration_seconds")
    started = _at(entry.get("started_at"), now)
    if not seconds and live and started:
        seconds = max(0.0, (now - started).total_seconds())
    duration = fmt_duration(seconds)
    if live and seconds:
        duration += " so far"

    pc = entry.get("pc_name") or ""
    touched = _at(entry.get("last_updated") or entry.get("started_at"), now)
    action = _action(entry, key, open_key=open_key, server_down=server_down)
    facts = [
        ("Worker", _worker(entry) or NOTHING),
        ("PC", (pc + (" (this PC)" if here and pc else "")) or NOTHING),
        ("Duration", duration),
        ("Items", str(items) if items else NOTHING),
        ("Scan corrections", str(metrics.get("total_corrections", NOTHING))),
        ("Unknown scans", str(metrics.get("total_unknown_scans", NOTHING))),
        ("Last touched", _clock(touched, now) if touched else NOTHING),
    ]
    return {
        "key": key,
        "id": str(entry.get("session_id", "")),
        "list": str(entry.get("packing_list_name", "")),
        "status": status,
        "label": chip["label"],
        "tone": chip["tone"],
        "manual": chip["manual"],
        "age": fmt_age(_started(entry), now),
        "orders": f"{done} / {total}" if total else NOTHING,
        "pct": int(done / total * 100) if total else 0,
        "items": str(items) if items else NOTHING,
        "touched": fmt_touched(entry, now),
        "setBy": "Set by a person" if chip["manual"] else "Set by the system",
        "why": _why(entry, key, now, open_key),
        "ordersNote": f"{skipped} skipped" if skipped else "None skipped",
        "facts": [{"label": label, "value": value} for label, value in facts],
        **action,
        "canDetails": bool(entry.get("work_dir")) and action["action"] != "details",
    }


def _no_match_text(tab: str, label: str, query: str, start: date | None, end: date | None) -> str:
    span = _range_text(start, end)
    if query:
        parts = ["Nothing", f"in {label}" if tab != "all" else "", span,
                 f"has “{query}” in its id, packing list, worker or PC."]
        return " ".join(part for part in parts if part)
    parts = [f"No {label.lower()} sessions" if tab != "all" else "No sessions", span]
    return " ".join(part for part in parts if part) + "."


def refresh_failure(path: Any, cause: str, at: str, previous: str) -> dict:
    """Frame 7f's banner. `previous` is the stamp of the list still on screen, or ""."""
    return {"path": str(path), "cause": str(cause).rstrip("."), "at": at, "from": previous}


def sessions_payload(
    entries: list[dict],
    *,
    now: datetime | None = None,
    tab: str = "all",
    query: str = "",
    date_from: str | None = None,
    date_to: str | None = None,
    loaded: bool = True,
    refreshing: bool = False,
    stamp: str = "",
    auto: bool = True,
    failure: dict | None = None,
    open_key: str = "",
    server_down: bool = False,
) -> dict[str, Any]:
    """The Sessions page. A date of None is the default; "" is no bound."""
    now = _now(now)
    default_from, default_to = default_range(now)
    date_from = default_from if date_from is None else str(date_from)
    date_to = default_to if date_to is None else str(date_to)
    labels = {key: label for key, label, _held in TABS}
    if tab not in labels:
        tab = "all"
    query = str(query or "")
    typed = query.strip()

    shown, in_tab, in_dates = visible_entries(
        entries, now=now, tab=tab, query=query, date_from=date_from, date_to=date_to
    )
    if not loaded:
        shown = []
    mode = "loading" if not loaded else ("ready" if entries else "empty")

    if not loaded:
        count = "–"
    elif typed:
        count = f"{len(shown)} of {len(in_tab)} sessions"
    else:
        count = plural(len(shown), "session", "sessions")

    return {
        "mode": mode,
        "refreshing": bool(refreshing),
        "stamp": str(stamp),
        "auto": bool(auto),
        "failed": bool(failure),
        "failure": dict(failure or {}),
        "tab": tab,
        "tabs": [
            {
                "key": key,
                "label": label,
                "count": sum(1 for e in in_dates if held is None or e.get("status") in held),
            }
            for key, label, held in TABS
        ],
        "query": query,
        "dateFrom": date_from,
        "dateTo": date_to,
        "rows": [_row(e, now, open_key=open_key, server_down=server_down) for e in shown],
        "shown": len(shown),
        "inTab": len(in_tab),
        "count": count,
        "noMatch": mode == "ready" and not shown,
        "noMatchText": _no_match_text(
            tab, labels[tab], typed, _parse_day(date_from), _parse_day(date_to)
        ),
        "exportTitle": f"Export the {plural(len(shown), 'session', 'sessions')} shown",
    }


def takeover_payload(entry: dict, lock: dict, now: datetime | None = None) -> dict:
    """Frame 7c: who had the session, since when, and what comes along."""
    now = _now(now)
    pc = lock.get("locked_by") or entry.get("pc_name") or "Another PC"
    worker = lock.get("worker_name") or ""
    at = _at(lock.get("heartbeat"), now)
    when = f" at {_clock(at, now)}" if at else ""
    who = f" while {worker} was packing" if worker else ""
    done = _n(entry.get("completed_orders"))
    total = _n(entry.get("total_orders"))
    return {
        "key": session_key(entry),
        "id": str(entry.get("session_id", "")),
        "body": f"{pc} stopped responding{when}{who}. If it comes back, it is told the "
                "session moved here.",
        "carry": f"Everything saved so far comes with you: {done} of {total} orders packed.",
    }


def _blank(value: Any) -> Any:
    return "" if value is None else value


def session_export_rows(entries: list[dict], *, labels: bool) -> list[list]:
    """One row per entry under EXPORT_COLUMNS. CSV writes the raw status
    (labels=False), Excel its word, as the Qt list did."""
    rows = []
    for entry in entries:
        status = entry.get("status", "")
        total = _n(entry.get("total_orders"))
        rows.append([
            status_chip(status)["label"] if labels else status,
            entry.get("packing_list_name", ""),
            entry.get("session_id", ""),
            _worker(entry),
            entry.get("pc_name") or "",
            f"{_n(entry.get('completed_orders'))}/{total}" if total else NOTHING,
            _started(entry) or "",
            _blank(entry.get("duration_seconds")),
            _blank(entry.get("total_items")),
            _blank(entry.get("total_orders")),
            _blank(entry.get("completed_orders")),
            _blank(entry.get("skipped_orders")),
        ])
    return rows
```

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_sessions_payload.py`
Expected: all pass. Two to read closely if one fails: `test_the_pane_has_seven_facts` (the `metrics` values are numbers and are shown as strings) and `test_an_unknown_status_offers_details_only_when_there_are_files`.

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check . --exclude shared`. Stage `gui/sessions_payload.py` and `tests/test_sessions_payload.py`. Message: `feat: pure payloads for the Sessions list, pane, take-over question and export`.

---

### Task 3: Pure payloads for Session details and its export

**Files:**
- Modify: `gui/sessions_payload.py` (one import, then append)
- Test: `tests/test_session_details_payload.py` (new)
- Delete: nothing yet (`tests/test_confirmation_methods.py` is repointed in Task 7)

**Interfaces:**
- Consumes: from Task 2, `_n`, `_now`, `_at`, `_day`, `_why`, `plural`, `fmt_duration`, `status_chip`, `session_key`, `NOTHING`. From Task 1, the dict `load_session_details` returns. `gui.packer_bridge.order_label(number) -> str` (adds a leading `#` when missing).
- Produces: `details_payload(entry, details=None, *, now=None, client="", error=None, query="", stamp="", open_key="") -> dict`, `detail_export_rows(details) -> list[dict]`, `fmt_time(seconds) -> str`.

`details=None` with `error=None` is the loading shape. `error` is `{"path", "cause"}`.

The shape (Task 5's page reads exactly these keys):

```
key, id, list, status, label, tone, manual, setBy, why     as a list row
state        "loading" | "ready" | "error"
error        {} or {"path", "cause"}
active       bool         pc  str        stamp  "14:06:31"
facts        [{"label", "value"}]  seven
canExport    bool
query        the filter as typed
-- only when state is "ready" --
cards        [{"value", "of", "label", "note"}]  five
timing       bool
metricsNote  str
groups       [{"title", "tiles": [{"value", "label"}]}]   two, or [] without timing
scan         [{"value", "label"}]  four
orders       [order]      total  int     showing  str
noMatch      bool         needle str
```

An order: `number`, `label`, `kind` (`packed`, `in_progress`, `skipped`), `duration`, `count`, `started`, `completed`, `flags` (`[{"label", "tone"}]`), `items`. An item: `sku`, `name`, `offset`, `count`, `time`, `flags`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_session_details_payload.py`:

```python
"""What Session details says (spec 2026-10-08 phase 4, section 7).

The flag tests are ported from tests/test_confirmation_methods.py, which read
them off a QTreeWidget.
"""

from datetime import UTC, datetime

import pytest

from gui.sessions_payload import detail_export_rows, details_payload, fmt_time

NOW = datetime(2026, 10, 7, 14, 6, 31, tzinfo=UTC)

ORDER_A = {
    "order_number": "#10407",
    "started_at": "2026-10-06T08:14:02+00:00",
    "completed_at": "2026-10-06T08:16:16+00:00",
    "duration_seconds": 134,
    "items_count": 5,
    "corrections": 1,
    "extra_scans_count": 2,
    "unknown_scans_count": 1,
    "items": [
        {"sku": "LST-07", "title": "Lipstick, shade 07", "quantity": 1, "row": 0,
         "scanned_at": "2026-10-06T08:14:14+00:00", "time_from_order_start_seconds": 12,
         "confirmation_method": "scanned"},
        {"sku": "LST-07", "title": "Lipstick, shade 07", "quantity": 1, "row": 0,
         "scanned_at": "2026-10-06T08:14:20+00:00", "time_from_order_start_seconds": 18,
         "confirmation_method": "scanned"},
        {"sku": "CRM-15ML", "title": "Eye cream 15 ml", "quantity": 3, "row": 1,
         "scanned_at": "2026-10-06T08:15:00+00:00", "time_from_order_start_seconds": 58,
         "confirmation_method": "force_confirmed"},
    ],
}
ORDER_B = {
    "order_number": "10408",
    "started_at": "2026-10-06T08:17:00+00:00",
    "completed_at": "2026-10-06T08:18:00+00:00",
    "duration_seconds": 60,
    "items_count": 1,
    "items": [
        {"sku": "A", "title": "A", "quantity": 1, "row": 0,
         "scanned_at": "2026-10-06T08:17:30+00:00", "time_from_order_start_seconds": 30,
         "confirmation_method": "manual"},
    ],
}
METRICS = {
    "avg_time_per_order": 97,
    "fastest_order_seconds": 60,
    "slowest_order_seconds": 134,
    "avg_time_per_item": 16.2,
    "avg_time_to_first_scan": 9.5,
    "orders_per_hour": 12.44,
    "items_per_hour": 148.6,
}


def entry(**over) -> dict:
    base = {
        "session_id": "2026-10-06_1",
        "packing_list_name": "Morning_wave",
        "status": "incomplete",
        "worker_id": "W-004",
        "worker_name": "Petya",
        "pc_name": "WH-PC-01",
        "started_at": "2026-10-06T08:02:11+00:00",
        "last_updated": "2026-10-06T11:14:40+00:00",
        "total_orders": 4,
        "completed_orders": 2,
        "skipped_orders": 1,
        "total_items": 402,
        "work_dir": "/srv/2026-10-06_1/packing/Morning_wave",
    }
    base.update(over)
    return base


def details(**over) -> dict:
    made = {
        "record": {
            "session_id": "2026-10-06_1",
            "packing_list_name": "Morning_wave",
            "worker_id": "W-004",
            "worker_name": "Petya",
            "pc_name": "WH-PC-01",
            "start_time": "2026-10-06T08:02:11+00:00",
            "end_time": "2026-10-06T11:14:40+00:00",
            "duration_seconds": 11549,
            "total_orders": 4,
            "completed_orders": 2,
        },
        "packing_state": {
            "in_progress": {
                "#10410": [
                    {"original_sku": "SPF-50", "required": 2, "packed": 1, "row": 0},
                    {"original_sku": "OIL-100", "required": 3, "packed": 2, "row": 1},
                ],
                "_timing_by_order": {"#10410": {}},
            },
        },
        "session_info": {},
        "session_summary": {
            "metrics": dict(METRICS),
            "orders": [ORDER_A, ORDER_B],
            "skipped_orders": [
                {"order_number": "#10409", "skipped_at": "2026-10-06T09:00:00+00:00",
                 "status": "skipped"}
            ],
        },
    }
    made.update(over)
    return made


def ready(entry_over=None, **kwargs) -> dict:
    return details_payload(entry(**(entry_over or {})), details(), now=NOW,
                           client="Acme Cosmetics (ACME)", **kwargs)


def test_times_read_to_a_tenth_under_a_minute():
    assert fmt_time(None) == "—"
    assert fmt_time(0) == "—"
    assert fmt_time(9.5) == "9.5s"
    assert fmt_time(45) == "45s"
    assert fmt_time(134) == "2m 14s"
    assert fmt_time(3725) == "1h 2m"


def test_the_head_is_the_list_rows():
    made = ready()
    assert (made["key"], made["id"], made["list"]) == (
        "2026-10-06_1|Morning_wave", "2026-10-06_1", "Morning_wave")
    assert (made["label"], made["tone"], made["manual"]) == ("Incomplete", "danger", True)
    assert made["setBy"] == "Set by a person"
    assert made["why"] == "closed by Petya with 2 orders unpacked"
    assert made["state"] == "ready"
    assert made["active"] is False


def test_the_seven_facts():
    assert ready()["facts"] == [
        {"label": "Client", "value": "Acme Cosmetics (ACME)"},
        {"label": "Packing list", "value": "Morning_wave"},
        {"label": "Worker", "value": "Petya (W-004)"},
        {"label": "PC", "value": "WH-PC-01"},
        {"label": "Started", "value": "6 Oct, 08:02:11"},
        {"label": "Completed", "value": "6 Oct, 11:14:40"},
        {"label": "Duration", "value": "3h 12m"},
    ]


def test_an_active_session_is_still_packing_and_so_far():
    made = details_payload(
        entry(status="in_progress", started_at="2026-10-07T11:00:00+00:00"),
        details(record={"start_time": "2026-10-07T11:00:00+00:00", "end_time": None,
                        "duration_seconds": 0, "total_orders": 4, "completed_orders": 2}),
        now=NOW, stamp="14:06:31",
    )
    facts = {fact["label"]: fact["value"] for fact in made["facts"]}
    assert made["active"] is True
    assert made["pc"] == "WH-PC-01"
    assert made["stamp"] == "14:06:31"
    assert facts["Completed"] == "Still packing"
    assert facts["Duration"] == "3h 6m so far"
    assert [card["note"] for card in made["cards"][:4]] == ["so far"] * 4
    assert made["metricsNote"] == "Only data from completed orders is shown. Figures so far."
    assert [group["title"] for group in made["groups"]] == ["Order time so far", "Item time so far"]


def test_the_five_stat_cards():
    assert ready()["cards"] == [
        {"value": "2", "of": "of 4", "label": "Orders packed", "note": "2 not packed"},
        {"value": "6", "of": "of 402", "label": "Items packed", "note": ""},
        {"value": "12.4", "of": "", "label": "Orders per hour", "note": ""},
        {"value": "149", "of": "", "label": "Items per hour", "note": ""},
        {"value": "1", "of": "", "label": "Skipped orders", "note": "not packed"},
    ]


def test_timing_names_the_fastest_and_the_slowest_order():
    made = ready()
    assert made["timing"] is True
    assert made["metricsNote"] == "Only data from completed orders is shown."
    assert made["groups"] == [
        {"title": "Order time", "tiles": [
            {"value": "1m 37s", "label": "Average per order"},
            {"value": "1m 0s", "label": "Fastest · #10408"},
            {"value": "2m 14s", "label": "Slowest · #10407"},
        ]},
        {"title": "Item time", "tiles": [
            {"value": "16.2s", "label": "Average per item"},
            {"value": "9.5s", "label": "Average to first scan"},
        ]},
    ]
    assert made["scan"] == [
        {"value": "1", "label": "Scan corrections"},
        {"value": "0.50", "label": "Corrections per order"},
        {"value": "1", "label": "Unknown scans"},
        {"value": "2", "label": "Extra scans"},
    ]


def test_without_timing_the_rates_dash_out_and_scan_quality_stays():
    made = details_payload(
        entry(),
        details(session_summary={"metrics": {}, "orders": [ORDER_A, ORDER_B],
                                 "skipped_orders": []}),
        now=NOW,
    )
    assert made["timing"] is False
    assert made["groups"] == []
    assert [(card["value"], card["note"]) for card in made["cards"][2:4]] == [
        ("—", "No timing data"), ("—", "No timing data")]
    assert made["scan"][0] == {"value": "1", "label": "Scan corrections"}


def test_orders_come_packed_then_in_progress_then_skipped():
    made = ready()
    assert [(order["label"], order["kind"]) for order in made["orders"]] == [
        ("#10407", "packed"), ("#10408", "packed"),
        ("#10410", "in_progress"), ("#10409", "skipped"),
    ]
    assert made["total"] == 4
    assert made["showing"] == "Showing 4 of 4 recorded orders"
    assert made["noMatch"] is False


def test_a_packed_order_row():
    order = ready()["orders"][0]
    assert {k: order[k] for k in ("number", "duration", "count", "started", "completed")} == {
        "number": "#10407", "duration": "2m 14s", "count": "5 items",
        "started": "08:14:02", "completed": "08:16:16",
    }
    assert order["flags"] == [
        {"label": "Forced confirm", "tone": "danger"},
        {"label": "2 extra", "tone": "warning"},
        {"label": "1 correction", "tone": "info"},
        {"label": "1 unknown", "tone": "neutral"},
    ]


def test_scans_are_grouped_by_line_and_extras_get_their_own_rows():
    assert ready()["orders"][0]["items"] == [
        {"sku": "LST-07", "name": "Lipstick, shade 07", "offset": "+12s", "count": "×2",
         "time": "08:14:14", "flags": []},
        {"sku": "CRM-15ML", "name": "Eye cream 15 ml", "offset": "+58s", "count": "×3",
         "time": "08:15:00", "flags": [{"label": "Forced confirm", "tone": "danger"}]},
        {"sku": "", "name": "2 extra scans · not in this order", "offset": "", "count": "2",
         "time": "", "flags": [{"label": "Extra", "tone": "warning"}]},
        {"sku": "", "name": "1 unknown scan · barcode not recognised", "offset": "",
         "count": "1", "time": "", "flags": [{"label": "1 unknown", "tone": "neutral"}]},
    ]


def test_each_item_row_names_how_it_was_packed():
    """Ported: a Confirm click ("manual") and Force ("force_confirmed") are not scans."""
    order = {
        "order_number": "#1001", "duration_seconds": 40, "items_count": 5,
        "items": [
            {"sku": "A", "quantity": 1},  # an older record: no method means scanned
            {"sku": "B", "quantity": 1, "confirmation_method": "manual"},
            {"sku": "C", "quantity": 3, "confirmation_method": "force_confirmed"},
        ],
    }
    made = details_payload(
        entry(), details(session_summary={"orders": [order], "skipped_orders": []}), now=NOW)
    row = made["orders"][0]
    assert [[flag["label"] for flag in item["flags"]] for item in row["items"]] == [
        [], ["Manual confirm"], ["Forced confirm"]]
    assert [flag["label"] for flag in row["flags"]] == ["Forced confirm", "Manual confirm"]
    assert [item["count"] for item in row["items"]] == ["×1", "×1", "×3"]


def test_a_title_that_only_repeats_the_sku_is_not_shown_twice():
    assert ready()["orders"][1]["items"][0]["name"] == ""


def test_an_in_progress_order_shows_how_far_it_got():
    order = ready()["orders"][2]
    assert order["count"] == "3 / 5 items"
    assert (order["duration"], order["started"], order["completed"]) == ("—", "—", "—")
    assert order["flags"] == [{"label": "In progress", "tone": "info"}]
    assert [(item["sku"], item["count"]) for item in order["items"]] == [
        ("SPF-50", "1 / 2"), ("OIL-100", "2 / 3")]


def test_a_skipped_order_has_no_items():
    order = ready()["orders"][3]
    assert order["started"] == "09:00:00"
    assert order["count"] == "—"
    assert order["flags"] == [{"label": "Skipped", "tone": "warning"}]
    assert order["items"] == []


def test_an_order_in_progress_and_skipped_is_listed_once_as_skipped():
    made = details_payload(
        entry(),
        details(session_summary={"orders": [], "skipped_orders": [
            {"order_number": "#10410", "skipped_at": None, "status": "skipped"}]}),
        now=NOW,
    )
    assert [(order["label"], order["kind"]) for order in made["orders"]] == [
        ("#10410", "skipped")]


def test_a_session_with_only_a_state_file_lists_its_skipped_orders():
    made = details_payload(
        entry(status="paused"),
        {"record": {}, "session_info": {}, "session_summary": {},
         "packing_state": {"completed": [], "skipped_orders": ["#7"],
                           "skipped_orders_timing": {"#7": "2026-10-06T09:30:00+00:00"},
                           "in_progress": {}}},
        now=NOW,
    )
    assert [(o["label"], o["kind"], o["started"]) for o in made["orders"]] == [
        ("#7", "skipped", "09:30:00")]
    assert made["canExport"] is False


@pytest.mark.parametrize("query", ["10407", "#10407", "  10407 "])
def test_the_filter_matches_the_order_number_with_or_without_the_hash(query):
    made = ready(query=query)
    assert [order["label"] for order in made["orders"]] == ["#10407"]
    assert made["showing"] == "Showing 1 of 4 recorded orders"
    assert made["query"] == query


def test_a_filter_that_matches_nothing_echoes_the_query():
    made = ready(query="#10999")
    assert made["orders"] == []
    assert made["noMatch"] is True
    assert made["needle"] == "10999"
    assert made["showing"] == "Showing 0 of 4 recorded orders"


def test_while_the_files_are_read_the_page_has_the_lists_facts():
    made = details_payload(entry(), None, now=NOW, client="Acme Cosmetics (ACME)")
    assert made["state"] == "loading"
    assert made["canExport"] is False
    facts = {fact["label"]: fact["value"] for fact in made["facts"]}
    assert facts["Worker"] == "Petya (W-004)"
    assert facts["Started"] == "6 Oct, 08:02:11"
    assert facts["Completed"] == "—"
    assert "cards" not in made


def test_files_that_could_not_be_read_name_the_file_and_the_cause():
    made = details_payload(
        entry(), None, now=NOW,
        error={"path": "/srv/x/packing_state.json", "cause": "permission denied."})
    assert made["state"] == "error"
    assert made["error"] == {"path": "/srv/x/packing_state.json", "cause": "permission denied"}
    assert made["canExport"] is False


def test_the_export_is_one_row_per_scan_of_the_packed_orders():
    rows = detail_export_rows(details())
    assert len(rows) == 4
    assert rows[0] == {
        "Order Number": "#10407",
        "Order Started": "2026-10-06T08:14:02+00:00",
        "Order Completed": "2026-10-06T08:16:16+00:00",
        "Order Duration (s)": 134,
        "SKU": "LST-07",
        "Quantity": 1,
        "Scanned At": "2026-10-06T08:14:14+00:00",
        "Time from Start (s)": 12,
    }
    assert ready()["canExport"] is True
    assert detail_export_rows(None) == []


def test_odd_shapes_in_the_files_do_not_break_the_details():
    """Review focus 2."""
    made = details_payload(
        entry(),
        {
            "record": {"total_orders": "4", "completed_orders": None},
            "session_info": {},
            "session_summary": {
                "metrics": None,
                "orders": ["junk", {"order_number": 1001}, {"order_number": "#2", "items": None}],
                "skipped_orders": ["junk", {"order_number": 55}],
            },
            "packing_state": {"in_progress": {"9": "junk", "8": ["junk", {"packed": "x"}]}},
        },
        now=NOW,
    )
    assert [(o["number"], o["label"], o["kind"]) for o in made["orders"]] == [
        ("1001", "#1001", "packed"), ("#2", "#2", "packed"),
        ("8", "#8", "in_progress"), ("55", "#55", "skipped"),
    ]
    assert made["orders"][0]["items"] == [
        {"sku": "", "name": "Item details not available", "offset": "", "count": "",
         "time": "", "flags": []}]
    assert made["orders"][2]["count"] == "0 / 0 items"
    assert made["cards"][0]["value"] == "2"
    assert all(isinstance(order["number"], str) for order in made["orders"])
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_details_payload.py`
Expected: an import error for `detail_export_rows`.

- [ ] **Step 3: Append to `gui/sessions_payload.py`**

Add to the imports, between `from typing import Any` and `from shared.metadata_utils import parse_timestamp`:

```python
from gui.packer_bridge import order_label
```

Append at the end of the file:

```python
# --- Session details (spec section 7) --------------------------------------------

# How an item was packed when it was not a scan: the Confirm button writes
# "manual" (one unit a click), Force writes "force_confirmed" (the rest of
# the line). Anything else is a scan.
_METHOD_FLAGS = (
    ("force_confirmed", "Forced confirm", "danger"),
    ("manual", "Manual confirm", "neutral"),
)


def fmt_time(seconds: Any) -> str:
    """A measured time: 9.5s, 45s, 2m 14s, 1h 2m."""
    if not seconds:
        return NOTHING
    if float(seconds) < 60:
        return f"{round(float(seconds), 1):g}s"
    return fmt_duration(seconds)


def _stamp(at: datetime | None) -> str:
    return f"{_day(at)}, {at:%H:%M:%S}" if at else NOTHING


def _hms(stamp: Any, now: datetime) -> str:
    at = _at(stamp, now)
    return f"{at:%H:%M:%S}" if at else NOTHING


def _flag(label: str, tone: str) -> dict:
    return {"label": label, "tone": tone}


def _method_flags(methods) -> list[dict]:
    return [_flag(label, tone) for method, label, tone in _METHOD_FLAGS if method in methods]


def _note_row(name: str, count: str = "", flags: list | None = None) -> dict:
    """An item row that is a sentence, not a line of the order."""
    return {"sku": "", "name": name, "offset": "", "count": count, "time": "",
            "flags": flags or []}


def _packed_order(order: dict, now: datetime) -> dict:
    number = str(order.get("order_number", "Unknown"))
    scans = [scan for scan in order.get("items") or [] if isinstance(scan, dict)]
    corrections = _n(order.get("corrections"))
    extra = _n(order.get("extra_scans_count"))
    unknown = _n(order.get("unknown_scans_count"))

    # One row per list line: its scans share `row` (older records: the SKU).
    lines: dict[Any, dict] = {}
    for scan in scans:
        sku = str(scan.get("sku", ""))
        line_key = scan.get("row") if scan.get("row") is not None else sku
        line = lines.setdefault(
            line_key,
            {"sku": sku, "name": str(scan.get("title") or ""), "units": 0,
             "first": scan, "methods": set()},
        )
        line["units"] += _n(scan.get("quantity"), 1)
        line["methods"].add(scan.get("confirmation_method"))

    items = []
    for line in lines.values():
        first = line["first"]
        offset = _n(first.get("time_from_order_start_seconds"))
        items.append({
            "sku": line["sku"],
            "name": "" if line["name"] == line["sku"] else line["name"],
            "offset": f"+{offset}s" if offset else "",
            "count": f"×{line['units']}",
            "time": _hms(first.get("scanned_at"), now),
            "flags": _method_flags(line["methods"]),
        })
    if not scans:
        items.append(_note_row("Item details not available"))
    if extra:
        items.append(_note_row(
            f"{plural(extra, 'extra scan', 'extra scans')} · not in this order",
            str(extra), [_flag("Extra", "warning")]))
    if unknown:
        items.append(_note_row(
            f"{plural(unknown, 'unknown scan', 'unknown scans')} · barcode not recognised",
            str(unknown), [_flag(f"{unknown} unknown", "neutral")]))

    flags = _method_flags({scan.get("confirmation_method") for scan in scans})
    if extra:
        flags.append(_flag(f"{extra} extra", "warning"))
    if corrections:
        flags.append(_flag(plural(corrections, "correction", "corrections"), "info"))
    if unknown:
        flags.append(_flag(f"{unknown} unknown", "neutral"))

    units = _n(order.get("items_count")) or sum(line["units"] for line in lines.values())
    return {
        "number": number,
        "label": order_label(number),
        "kind": "packed",
        "duration": fmt_time(order.get("duration_seconds")),
        "count": plural(units, "item", "items"),
        "started": _hms(order.get("started_at"), now),
        "completed": _hms(order.get("completed_at"), now),
        "flags": flags,
        "items": items,
    }


def _open_order(number: str, entries: list) -> dict:
    lines = [line for line in entries if isinstance(line, dict)]
    packed = sum(_n(line.get("packed")) for line in lines)
    required = sum(_n(line.get("required")) for line in lines)
    return {
        "number": number,
        "label": order_label(number),
        "kind": "in_progress",
        "duration": NOTHING,
        "count": f"{packed} / {required} items",
        "started": NOTHING,
        "completed": NOTHING,
        "flags": [_flag("In progress", "info")],
        "items": [
            {
                "sku": str(line.get("original_sku") or line.get("normalized_sku") or ""),
                "name": "",
                "offset": "",
                "count": f"{_n(line.get('packed'))} / {_n(line.get('required'))}",
                "time": "",
                "flags": [],
            }
            for line in lines
        ],
    }


def _skipped_order(skip: dict, now: datetime) -> dict:
    number = str(skip.get("order_number", "Unknown"))
    return {
        "number": number,
        "label": order_label(number),
        "kind": "skipped",
        "duration": NOTHING,
        "count": NOTHING,
        "started": _hms(skip.get("skipped_at"), now),
        "completed": NOTHING,
        "flags": [_flag("Skipped", "warning")],
        "items": [],
    }


def _packed_orders(details: dict) -> list[dict]:
    """The packed orders' records: the summary's, else the state file's."""
    summary = details.get("session_summary") or {}
    state = details.get("packing_state") or {}
    orders = summary.get("orders") or state.get("completed") or []
    return [order for order in orders if isinstance(order, dict)]


def _order_rows(details: dict, now: datetime) -> list[dict]:
    """Packed in the order they were packed, then in progress, then skipped.

    An order both in progress and skipped is listed once, as skipped.
    """
    summary = details.get("session_summary") or {}
    state = details.get("packing_state") or {}
    packed = _packed_orders(details)

    skipped = summary.get("skipped_orders")
    if skipped is None:
        timing = state.get("skipped_orders_timing") or {}
        skipped = [
            {"order_number": number, "skipped_at": timing.get(number)}
            for number in state.get("skipped_orders") or []
        ]
    skipped = [skip for skip in skipped if isinstance(skip, dict)]

    taken = {str(order.get("order_number")) for order in packed}
    taken |= {str(skip.get("order_number")) for skip in skipped}
    in_progress = state.get("in_progress")
    open_orders = [
        (str(number), entries)
        for number, entries in (in_progress.items() if isinstance(in_progress, dict) else ())
        if not str(number).startswith("_") and str(number) not in taken
        and isinstance(entries, list)
    ]
    return (
        [_packed_order(order, now) for order in packed]
        + [_open_order(number, entries) for number, entries in open_orders]
        + [_skipped_order(skip, now) for skip in skipped]
    )


def detail_export_rows(details: dict | None) -> list[dict]:
    """One row per item scan of the packed orders: the Excel export's sheet."""
    rows = []
    for order in _packed_orders(details or {}):
        for item in order.get("items") or []:
            if not isinstance(item, dict):
                continue
            rows.append({
                "Order Number": order.get("order_number", ""),
                "Order Started": order.get("started_at", ""),
                "Order Completed": order.get("completed_at", ""),
                "Order Duration (s)": order.get("duration_seconds", 0),
                "SKU": item.get("sku", ""),
                "Quantity": item.get("quantity", 1),
                "Scanned At": item.get("scanned_at", ""),
                "Time from Start (s)": item.get("time_from_order_start_seconds", 0),
            })
    return rows


def details_payload(
    entry: dict,
    details: dict | None = None,
    *,
    now: datetime | None = None,
    client: str = "",
    error: dict | None = None,
    query: str = "",
    stamp: str = "",
    open_key: str = "",
) -> dict[str, Any]:
    """The Session details page. `details` None is loading; `error` is frame 8f."""
    now = _now(now)
    key = session_key(entry)
    status = entry.get("status", "")
    chip = status_chip(status)
    live = status == "in_progress"
    details = details or {}
    record = details.get("record") or {}
    summary = details.get("session_summary") or {}

    name = record.get("packing_list_name") or entry.get("packing_list_name") or ""
    worker_name = record.get("worker_name") or entry.get("worker_name") or ""
    worker_id = record.get("worker_id") or entry.get("worker_id") or ""
    if worker_name and worker_id and worker_name != worker_id:
        worker = f"{worker_name} ({worker_id})"
    else:
        worker = worker_name or worker_id or NOTHING
    pc = record.get("pc_name") or entry.get("pc_name") or ""
    started = _at(record.get("start_time") or entry.get("started_at"), now)
    ended = _at(record.get("end_time"), now)
    seconds = (
        record.get("duration_seconds")
        or summary.get("duration_seconds")
        or entry.get("duration_seconds")
    )
    if not seconds and live and started:
        seconds = max(0.0, (now - started).total_seconds())
    duration = fmt_duration(seconds) + (" so far" if live and seconds else "")

    facts = [
        ("Client", client or NOTHING),
        ("Packing list", name or NOTHING),
        ("Worker", worker),
        ("PC", pc or NOTHING),
        ("Started", _stamp(started)),
        ("Completed", "Still packing" if live else _stamp(ended)),
        ("Duration", duration),
    ]
    payload: dict[str, Any] = {
        "key": key,
        "id": str(entry.get("session_id", "")),
        "list": str(name),
        "status": status,
        "label": chip["label"],
        "tone": chip["tone"],
        "manual": chip["manual"],
        "setBy": "Set by a person" if chip["manual"] else "Set by the system",
        "why": _why(entry, key, now, open_key),
        "state": "loading",
        "error": {},
        "active": live,
        "pc": pc or "another PC",
        "stamp": str(stamp),
        "facts": [{"label": label, "value": value} for label, value in facts],
        "canExport": False,
        "query": str(query or ""),
    }
    if error:
        payload["state"] = "error"
        payload["error"] = {
            "path": str(error.get("path", "")),
            "cause": str(error.get("cause", "")).rstrip("."),
        }
        return payload
    if not details:
        return payload

    packed = _packed_orders(details)
    rows = _order_rows(details, now)
    metrics = summary.get("metrics") or {}
    timing = bool(metrics.get("avg_time_per_order"))
    total = _n(record.get("total_orders")) or _n(entry.get("total_orders"))
    done = _n(record.get("completed_orders"), len(packed))
    units = sum(_n(order.get("items_count")) for order in packed)
    list_units = _n(entry.get("total_items"))
    skipped = sum(1 for row in rows if row["kind"] == "skipped")
    so_far = "so far" if live else ""
    rate_note = so_far if timing else "No timing data"
    per_hour = metrics.get("orders_per_hour") or 0
    items_hour = metrics.get("items_per_hour") or 0

    def named(label: str, seconds: Any) -> str:
        """ "Fastest · #10408": the order whose time this is."""
        for order in packed:
            if seconds and order.get("duration_seconds") == seconds:
                return f"{label} · {order_label(str(order.get('order_number', '')))}"
        return label

    suffix = " so far" if live else ""
    fastest = metrics.get("fastest_order_seconds")
    slowest = metrics.get("slowest_order_seconds")
    groups = [] if not timing else [
        {"title": "Order time" + suffix, "tiles": [
            {"value": fmt_time(metrics.get("avg_time_per_order")), "label": "Average per order"},
            {"value": fmt_time(fastest), "label": named("Fastest", fastest)},
            {"value": fmt_time(slowest), "label": named("Slowest", slowest)},
        ]},
        {"title": "Item time" + suffix, "tiles": [
            {"value": fmt_time(metrics.get("avg_time_per_item")), "label": "Average per item"},
            {"value": fmt_time(metrics.get("avg_time_to_first_scan")),
             "label": "Average to first scan"},
        ]},
    ]

    corrections = sum(_n(order.get("corrections")) for order in packed)
    extra = sum(_n(order.get("extra_scans_count")) for order in packed)
    unknown = sum(_n(order.get("unknown_scans_count")) for order in packed)

    typed = str(query or "").strip().lstrip("#").strip()
    needle = typed.lower()
    listed = [row for row in rows if not needle or needle in row["number"].lstrip("#").lower()]

    payload.update({
        "state": "ready",
        "canExport": bool(detail_export_rows(details)),
        "cards": [
            {"value": str(done), "of": f"of {total}" if total else "", "label": "Orders packed",
             "note": so_far or (f"{total - done} not packed" if total > done else "")},
            {"value": str(units), "of": f"of {list_units}" if list_units else "",
             "label": "Items packed", "note": so_far},
            {"value": f"{per_hour:.1f}" if timing and per_hour else NOTHING, "of": "",
             "label": "Orders per hour", "note": rate_note},
            {"value": str(round(items_hour)) if timing and items_hour else NOTHING, "of": "",
             "label": "Items per hour", "note": rate_note},
            {"value": str(skipped), "of": "", "label": "Skipped orders",
             "note": "not packed" if skipped else ""},
        ],
        "timing": timing,
        "metricsNote": "Only data from completed orders is shown."
                       + (" Figures so far." if live else ""),
        "groups": groups,
        "scan": [
            {"value": str(corrections), "label": "Scan corrections"},
            {"value": f"{corrections / len(packed):.2f}" if packed else NOTHING,
             "label": "Corrections per order"},
            {"value": str(unknown), "label": "Unknown scans"},
            {"value": str(extra), "label": "Extra scans"},
        ],
        "orders": listed,
        "total": len(rows),
        "showing": f"Showing {len(listed)} of {len(rows)} recorded orders",
        "noMatch": bool(needle) and not listed,
        "needle": typed,
    })
    return payload
```

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_details_payload.py tests/test_sessions_payload.py`
Expected: all pass.

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check . --exclude shared`. Stage `gui/sessions_payload.py` and `tests/test_session_details_payload.py`. Message: `feat: pure payload for Session details and its export`.

---

### Task 4: The bridge, the floor kit, and the Sessions page (7a to 7h, the pane, 7c)

**Files:**
- Modify: `gui/app_bridge.py` (the `AppBridge` class)
- Modify: `gui/web/floor.css` (append), `gui/web/app.html`, `gui/web/app.css` (append), `gui/web/app.js`
- Test: `tests/test_app_sessions_page.py` (new)

**Interfaces:**
- Consumes: `sessions_payload`, `takeover_payload`, `refresh_failure` (Task 2).
- Produces, on `AppBridge`:
  - properties `sessions`, `details`, `confirm` (maps) with setters `set_sessions(dict)`, `set_details(dict)`, `set_confirm(dict)`;
  - `page` now also takes `"sessions"` and `"details"`;
  - slots and the Python-facing signals they emit:

| Slot (called by the page) | Signal |
|---|---|
| `setSessionsFilter(tab, query, dateFrom, dateTo)` | `sessionsFilterChanged(str, str, str, str)` |
| `clearSessionsFilter()` | `sessionsFilterCleared()` |
| `refreshSessions()` | `refreshSessionsRequested()` |
| `setAutoRefresh(bool)` | `autoRefreshChanged(bool)` |
| `sessionAction(key)` | `sessionActionRequested(str)` |
| `sessionDetails(key)` | `sessionDetailsRequested(str)` |
| `exportSessions(format)` | `exportSessionsRequested(str)` (`"csv"` or `"xlsx"`) |
| `closeDetails()` | `closeDetailsRequested()` |
| `setDetailsFilter(text)` | `detailsFilterChanged(str)` |
| `retryDetails()` | `retryDetailsRequested()` |
| `exportDetails()` | `exportDetailsRequested()` |
| `answerTakeOver(bool)` | `takeOverAnswered(bool)` |

The page's own state lives in `view`: `sel` (the selected row's key), `tab`, `exportOpen`, and for Task 5 `detailsKey` and `dOpen`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_app_sessions_page.py`:

```python
"""The Sessions page in a real Chromium: frames 7a to 7h, the pane, 7c.

Never mark these skip -- a page nobody can run is a page nobody guards.
"""

import json
import time
from datetime import UTC, datetime

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from pytestqt.exceptions import TimeoutError as QtBotTimeoutError

from gui.app_bridge import mount_app_page
from gui.sessions_payload import refresh_failure, sessions_payload, takeover_payload

NOW = datetime(2026, 10, 7, 14, 6, 31, tzinfo=UTC)


def _eval(qtbot, view, expr, timeout=5000):
    # runJavaScript cannot marshal a JS array back; route everything through JSON.
    box = []
    view.page().runJavaScript(f"JSON.stringify({expr})", 0, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=timeout)
    return json.loads(box[0])


def _until_js(qtbot, view, expr, timeout_s=20):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        remaining = max(int((deadline - time.monotonic()) * 1000), 50)
        try:
            if _eval(qtbot, view, expr, timeout=min(remaining, 5000)) is True:
                return
        except QtBotTimeoutError:
            continue
        qtbot.wait(50)
    pytest.fail(f"never became true in the page: {expr}")


def _js(qtbot, view, code):
    """Run statements in the page."""
    return _eval(qtbot, view, f"(function () {{ {code}; return true; }})()")


def _shown(view, qtbot, element_id):
    return _eval(qtbot, view, f"!document.getElementById('{element_id}').hidden")


def _text(view, qtbot, element_id):
    return _eval(qtbot, view, f"document.getElementById('{element_id}').textContent")


def _click(view, qtbot, element_id):
    _js(qtbot, view, f"document.getElementById('{element_id}').click()")


def _row_js(key):
    return ("Array.from(document.querySelectorAll('[data-session]'))"
            f".find(function (n) {{ return n.dataset.session === {json.dumps(key)}; }})")


def _select(view, qtbot, key):
    _js(qtbot, view, f"{_row_js(key)}.click()")


def _settle(qtbot, bridge):
    qtbot.waitUntil(lambda: bridge.painted_revision >= bridge.revision, timeout=20000)


def entry(session_id, status, **over):
    base = {
        "session_id": session_id,
        "packing_list_name": "Afternoon_wave",
        "status": status,
        "worker_id": "W-002",
        "worker_name": "Maria",
        "pc_name": "WH-PC-02",
        "started_at": f"{session_id[:10]}T09:00:00+00:00",
        "last_updated": f"{session_id[:10]}T11:20:00+00:00",
        "total_orders": 110,
        "completed_orders": 71,
        "skipped_orders": 2,
        "total_items": 402,
        "work_dir": f"/srv/{session_id}/packing/Afternoon_wave",
        "session_path": f"/srv/{session_id}",
        "metrics": None,
    }
    base.update(over)
    return base


ENTRIES = [
    entry("2026-10-07_2", "stale"),
    entry("2026-10-07_1", "in_progress"),
    entry("2026-10-06_2", "paused"),
    entry("2026-10-06_1", "completed"),
    entry("2026-10-05_1", "not_started", work_dir=""),
]
PAUSED = "2026-10-06_2|Afternoon_wave"
ACTIVE = "2026-10-07_1|Afternoon_wave"
STALE = "2026-10-07_2|Afternoon_wave"


def payload(entries=ENTRIES, **kwargs):
    kwargs.setdefault("stamp", "14:06:31")
    return sessions_payload(entries, now=NOW, **kwargs)


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_app_page(view)
    view.resize(1166, 708)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    bridge.set_shell(client=True, clients=True, server_down=False)
    bridge.set_page("sessions")
    return view, bridge


@pytest.fixture
def listed(page, qtbot):
    view, bridge = page
    bridge.set_sessions(payload())
    _settle(qtbot, bridge)
    return view, bridge


def test_7h_with_no_client_the_card_speaks_for_sessions(page, qtbot):
    view, bridge = page
    bridge.set_shell(client=False, clients=True, server_down=False)
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "no-client")
    assert not _shown(view, qtbot, "sessions")
    assert _text(view, qtbot, "no-client-title") == "Choose a client"
    assert _text(view, qtbot, "no-client-text") == (
        "Pick a client in the bar above to see its sessions.")


def test_7e_the_first_load_shows_dashes_and_skeleton_rows(page, qtbot):
    view, bridge = page
    bridge.set_sessions(payload([], loaded=False, refreshing=True, stamp=""))
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "sessions")
    assert _shown(view, qtbot, "s-loading")
    assert _eval(qtbot, view, "document.querySelectorAll('#s-skeleton .app-skel').length") == 12
    assert _eval(qtbot, view,
                 "Array.from(document.querySelectorAll('#s-tabs .segment-count'))"
                 ".map(function (n) { return n.textContent; })") == ["–"] * 4
    assert _text(view, qtbot, "s-count") == "–"
    assert _text(view, qtbot, "s-stamp-label") == "Refreshing…"
    assert _eval(qtbot, view, "document.getElementById('s-refresh').disabled") is True
    assert not _shown(view, qtbot, "s-empty")


def test_7a_the_toolbar_the_rows_and_the_foot(listed, qtbot):
    view, _bridge = listed
    assert _eval(qtbot, view,
                 "Array.from(document.querySelectorAll('#s-tabs .segment'))"
                 ".map(function (n) { return n.textContent; })") == [
        "All5", "Open4", "Finished1", "Abandoned0"]
    assert _eval(qtbot, view,
                 "document.querySelector('#s-tabs [aria-checked=\"true\"]').dataset.tab") == "all"
    assert _eval(qtbot, view,
                 "Array.from(document.querySelectorAll('[data-session] .app-s-id'))"
                 ".map(function (n) { return n.textContent; })") == [
        "2026-10-07_2", "2026-10-07_1", "2026-10-06_2", "2026-10-06_1", "2026-10-05_1"]
    assert _text(view, qtbot, "s-count") == "5 sessions"
    assert _text(view, qtbot, "s-stamp") == "14:06:31"
    assert _eval(qtbot, view, "document.getElementById('s-from').value") == "2026-09-07"
    assert not _shown(view, qtbot, "s-pane")
    assert not _shown(view, qtbot, "s-loading")
    # A solid dot for the status a packer set, a hollow one otherwise.
    assert _eval(qtbot, view, f"!!{_row_js(PAUSED)}.querySelector('.dot.solid')") is True
    assert _eval(qtbot, view, f"!!{_row_js(ACTIVE)}.querySelector('.dot.solid')") is False
    assert _eval(qtbot, view, f"{_row_js(PAUSED)}.title") == "Double-click: Resume session"


def test_selecting_a_row_opens_the_pane_and_folds_two_columns(listed, qtbot):
    view, _bridge = listed
    _select(view, qtbot, PAUSED)
    assert _shown(view, qtbot, "s-pane")
    assert _eval(qtbot, view,
                 "document.getElementById('s-main').classList.contains('pane-open')") is True
    assert _eval(qtbot, view, f"{_row_js(PAUSED)}.getAttribute('aria-pressed')") == "true"
    assert _text(view, qtbot, "p-id") == "2026-10-06_2"
    assert _text(view, qtbot, "p-list") == "Afternoon_wave"
    assert _text(view, qtbot, "p-why") == "Set by a person · paused by Maria, 6 Oct, 11:20"
    assert _text(view, qtbot, "p-orders") == "71 / 110"
    assert _text(view, qtbot, "p-orders-note") == "2 skipped"
    assert _eval(qtbot, view, "document.querySelectorAll('#p-facts .app-p-fact').length") == 7
    assert _text(view, qtbot, "p-action") == "Resume session"
    assert _shown(view, qtbot, "p-details")
    assert not _shown(view, qtbot, "p-note")
    # The folded columns are not laid out.
    assert _eval(qtbot, view,
                 f"{_row_js(PAUSED)}.querySelector('.app-s-touched').offsetParent === null") is True


def test_the_panes_action_reaches_python(listed, qtbot):
    view, bridge = listed
    asked = []
    bridge.sessionActionRequested.connect(asked.append)
    _select(view, qtbot, PAUSED)
    _click(view, qtbot, "p-action")
    qtbot.waitUntil(lambda: asked == [PAUSED], timeout=5000)


def test_a_double_click_runs_the_rows_action(listed, qtbot):
    view, bridge = listed
    asked = []
    bridge.sessionActionRequested.connect(asked.append)
    _js(qtbot, view,
        f"{_row_js(PAUSED)}.dispatchEvent(new MouseEvent('dblclick', {{bubbles: true}}))")
    qtbot.waitUntil(lambda: asked == [PAUSED], timeout=5000)


def test_a_disabled_action_says_why_and_does_nothing(listed, qtbot):
    view, bridge = listed
    asked = []
    bridge.sessionActionRequested.connect(asked.append)
    _select(view, qtbot, ACTIVE)
    assert _eval(qtbot, view, "document.getElementById('p-action').disabled") is True
    assert _text(view, qtbot, "p-note-text") == (
        "Open on WH-PC-02 right now. It can be taken over once that PC stops responding.")
    assert _eval(qtbot, view,
                 "document.getElementById('p-note').classList.contains('warn')") is False
    _click(view, qtbot, "p-action")
    _js(qtbot, view,
        f"{_row_js(ACTIVE)}.dispatchEvent(new MouseEvent('dblclick', {{bubbles: true}}))")
    qtbot.wait(300)
    assert asked == []


def test_a_stale_session_warns_before_it_is_resumed(listed, qtbot):
    view, _bridge = listed
    _select(view, qtbot, STALE)
    assert _shown(view, qtbot, "p-note")
    assert _eval(qtbot, view,
                 "document.getElementById('p-note').classList.contains('warn')") is True
    assert _eval(qtbot, view, "document.getElementById('p-action').disabled") is False


def test_view_details_reaches_python(listed, qtbot):
    view, bridge = listed
    asked = []
    bridge.sessionDetailsRequested.connect(asked.append)
    _select(view, qtbot, PAUSED)
    _click(view, qtbot, "p-details")
    qtbot.waitUntil(lambda: asked == [PAUSED], timeout=5000)


def test_a_session_with_no_files_offers_no_details(listed, qtbot):
    view, _bridge = listed
    _select(view, qtbot, "2026-10-05_1|Afternoon_wave")
    assert _text(view, qtbot, "p-action") == "Start packing"
    assert not _shown(view, qtbot, "p-details")


def test_a_tab_the_search_and_a_date_reach_python(listed, qtbot):
    view, bridge = listed
    got = []
    bridge.sessionsFilterChanged.connect(lambda *args: got.append(args))
    _js(qtbot, view, "document.querySelector('[data-tab=\"open\"]').click()")
    qtbot.waitUntil(lambda: got == [("open", "", "2026-09-07", "2026-10-07")], timeout=5000)

    _js(qtbot, view,
        "var q = document.getElementById('s-query'); q.focus(); q.value = 'maria';"
        "q.dispatchEvent(new Event('input', {bubbles: true}))")
    qtbot.waitUntil(lambda: got[-1] == ("all", "maria", "2026-09-07", "2026-10-07"), timeout=5000)

    _js(qtbot, view,
        "var f = document.getElementById('s-from'); f.value = '2026-10-01';"
        "f.dispatchEvent(new Event('change', {bubbles: true}))")
    qtbot.waitUntil(lambda: got[-1] == ("all", "maria", "2026-10-01", "2026-10-07"), timeout=5000)


def test_a_push_does_not_overwrite_the_input_being_typed_in(listed, qtbot):
    view, bridge = listed
    _js(qtbot, view, "var q = document.getElementById('s-query'); q.focus(); q.value = 'mar'")
    bridge.set_sessions(payload(query="ma"))
    _settle(qtbot, bridge)
    assert _eval(qtbot, view, "document.getElementById('s-query').value") == "mar"
    _js(qtbot, view, "document.getElementById('s-query').blur()")
    bridge.set_sessions(payload(query="m"))
    _settle(qtbot, bridge)
    assert _eval(qtbot, view, "document.getElementById('s-query').value") == "m"
    assert _shown(view, qtbot, "s-query-clear")


def test_changing_tab_drops_the_selection(listed, qtbot):
    view, bridge = listed
    _select(view, qtbot, PAUSED)
    bridge.set_sessions(payload(tab="open"))
    _settle(qtbot, bridge)
    assert not _shown(view, qtbot, "s-pane")


def test_a_refresh_keeps_the_selection(listed, qtbot):
    view, bridge = listed
    _select(view, qtbot, PAUSED)
    bridge.set_sessions(payload(stamp="14:08:31"))
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "s-pane")
    assert _text(view, qtbot, "p-id") == "2026-10-06_2"


def test_7d_nothing_matches_and_clear_filters(listed, qtbot):
    view, bridge = listed
    cleared = []
    bridge.sessionsFilterCleared.connect(lambda: cleared.append(1))
    bridge.set_sessions(payload(tab="open", query="2025-12"))
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "s-no-match")
    assert _text(view, qtbot, "s-no-match-text") == (
        "Nothing in Open between 7 Sep and 7 Oct has “2025-12” in its id, "
        "packing list, worker or PC.")
    assert _text(view, qtbot, "s-count") == "0 of 4 sessions"
    assert _eval(qtbot, view, "document.getElementById('s-export').disabled") is True
    _js(qtbot, view, "document.querySelector('#s-no-match .btn').click()")
    qtbot.waitUntil(lambda: cleared == [1], timeout=5000)


def test_7f_a_failed_refresh_keeps_the_list_and_offers_retry(listed, qtbot):
    view, bridge = listed
    asked = []
    bridge.refreshSessionsRequested.connect(lambda: asked.append(1))
    failure = refresh_failure("/srv/Sessions/CLIENT_ACME", "the network path was not found",
                              "14:08:31", "14:06:31")
    bridge.set_sessions(payload(failure=failure))
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "s-failed")
    assert _text(view, qtbot, "s-failed-path") == "/srv/Sessions/CLIENT_ACME"
    assert _text(view, qtbot, "s-failed-cause") == "the network path was not found"
    assert _shown(view, qtbot, "s-failed-from-line")
    assert _eval(qtbot, view,
                 "document.getElementById('s-stamp-line').classList.contains('failed')") is True
    assert _eval(qtbot, view, "document.querySelectorAll('[data-session]').length") == 5
    _click(view, qtbot, "s-failed-retry")
    qtbot.waitUntil(lambda: asked == [1], timeout=5000)

    first = refresh_failure("/srv/Sessions/CLIENT_ACME", "x", "14:08:31", "")
    bridge.set_sessions(payload([], failure=first, stamp=""))
    _settle(qtbot, bridge)
    assert not _shown(view, qtbot, "s-failed-from-line")
    # With the server away, "No sessions yet" would be a guess.
    assert not _shown(view, qtbot, "s-empty")


def test_7g_a_client_with_no_sessions(page, qtbot):
    view, bridge = page
    bridge.set_sessions(payload([]))
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "s-empty")
    assert not _shown(view, qtbot, "s-no-match")
    assert _eval(qtbot, view,
                 "Array.from(document.querySelectorAll('#s-tabs .segment-count'))"
                 ".map(function (n) { return n.textContent; })") == ["0"] * 4


def test_the_switch_the_refresh_button_and_f5_reach_python(listed, qtbot):
    view, bridge = listed
    auto, asked = [], []
    bridge.autoRefreshChanged.connect(auto.append)
    bridge.refreshSessionsRequested.connect(lambda: asked.append(1))
    assert _eval(qtbot, view,
                 "document.getElementById('s-auto').getAttribute('aria-checked')") == "true"
    _click(view, qtbot, "s-auto")
    qtbot.waitUntil(lambda: auto == [False], timeout=5000)
    _click(view, qtbot, "s-refresh")
    qtbot.waitUntil(lambda: asked == [1], timeout=5000)
    _js(qtbot, view,
        "document.dispatchEvent(new KeyboardEvent('keydown', {key: 'F5', bubbles: true}))")
    qtbot.waitUntil(lambda: asked == [1, 1], timeout=5000)


def test_the_export_menu_offers_csv_and_excel(listed, qtbot):
    view, bridge = listed
    asked = []
    bridge.exportSessionsRequested.connect(asked.append)
    assert not _shown(view, qtbot, "s-export-menu")
    _click(view, qtbot, "s-export")
    assert _shown(view, qtbot, "s-export-menu")
    assert _text(view, qtbot, "s-export-title") == "Export the 5 sessions shown"
    _js(qtbot, view, "document.querySelector('[data-action=\"exportCsv\"]').click()")
    qtbot.waitUntil(lambda: asked == ["csv"], timeout=5000)
    assert not _shown(view, qtbot, "s-export-menu")
    _click(view, qtbot, "s-export")
    _js(qtbot, view, "document.querySelector('[data-action=\"exportXlsx\"]').click()")
    qtbot.waitUntil(lambda: asked == ["csv", "xlsx"], timeout=5000)


def test_7c_the_take_over_question_and_both_answers(listed, qtbot):
    view, bridge = listed
    answers = []
    bridge.takeOverAnswered.connect(answers.append)
    lock = {"locked_by": "WH-PC-02", "worker_name": "Georgi",
            "heartbeat": "2026-10-07T13:52:10+00:00"}
    bridge.set_confirm(takeover_payload(ENTRIES[0], lock, now=NOW))
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "confirm")
    assert _text(view, qtbot, "confirm-id") == "2026-10-07_2"
    assert _text(view, qtbot, "confirm-body").startswith("WH-PC-02 stopped responding at 13:52")
    assert _text(view, qtbot, "confirm-carry") == (
        "Everything saved so far comes with you: 71 of 110 orders packed.")
    _click(view, qtbot, "confirm-ok")
    qtbot.waitUntil(lambda: answers == [True], timeout=5000)
    _click(view, qtbot, "confirm-cancel")
    qtbot.waitUntil(lambda: answers == [True, False], timeout=5000)
    bridge.set_confirm({})
    _settle(qtbot, bridge)
    assert not _shown(view, qtbot, "confirm")


def test_escape_answers_the_question_then_closes_the_pane(listed, qtbot):
    view, bridge = listed
    answers = []
    bridge.takeOverAnswered.connect(answers.append)
    _select(view, qtbot, STALE)
    bridge.set_confirm(takeover_payload(ENTRIES[0], {"locked_by": "WH-PC-02"}, now=NOW))
    _settle(qtbot, bridge)
    escape = "document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))"
    _js(qtbot, view, escape)
    qtbot.waitUntil(lambda: answers == [False], timeout=5000)
    assert _shown(view, qtbot, "s-pane")
    bridge.set_confirm({})
    _settle(qtbot, bridge)
    _js(qtbot, view, escape)
    assert not _shown(view, qtbot, "s-pane")


def test_markup_in_a_list_name_is_text(page, qtbot):
    """Review focus 3."""
    view, bridge = page
    nasty = entry("2026-10-06_2", "paused", packing_list_name="<img src=x onerror=alert(1)>",
                  worker_name="<b>Maria</b>")
    bridge.set_sessions(payload([nasty]))
    _settle(qtbot, bridge)
    _select(view, qtbot, "2026-10-06_2|<img src=x onerror=alert(1)>")
    assert _text(view, qtbot, "p-list") == "<img src=x onerror=alert(1)>"
    assert _eval(qtbot, view, "document.querySelectorAll('#sessions img, #sessions b').length") == 0


def test_covered_hides_the_page_and_the_question(listed, qtbot):
    view, bridge = listed
    bridge.set_confirm(takeover_payload(ENTRIES[0], {"locked_by": "WH-PC-02"}, now=NOW))
    bridge.set_covered(True)
    _settle(qtbot, bridge)
    assert not _shown(view, qtbot, "sessions")
    assert not _shown(view, qtbot, "confirm")


def test_packing_still_draws_after_sessions(listed, qtbot):
    view, bridge = listed
    bridge.set_page("packing")
    _settle(qtbot, bridge)
    assert not _shown(view, qtbot, "sessions")
    assert _shown(view, qtbot, "no-session")
    assert _text(view, qtbot, "no-client-title") == "Choose a client to begin"
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_sessions_page.py`
Expected: every test fails, the first with `AttributeError: 'AppBridge' object has no attribute 'set_sessions'`.

- [ ] **Step 3: Extend `AppBridge` in `gui/app_bridge.py`**

Replace the module docstring's first paragraph so it reads:

```python
"""The app document's bridge and payloads (ADR 0003).

One web document draws the shell's pages: Packing, Statistics, Sessions and
Session details. The payload functions below are pure -- no Qt, no I/O -- and
decide what Packing and Statistics say; gui/sessions_payload.py does the same
for the two Sessions pages. gui/web/app.js renders them. The page keeps a
little view state of its own: the order rows the packer toggled, the SKU
table's sort, the selected session and the orders opened in details.
```

(Keep the `Spec:` line that follows, and add under it: `Phase 4: docs/superpowers/specs/2026-10-08-ui-refresh-phase4-sessions-design.md`.)

In the class, after `statisticsChanged = Signal()` add:

```python
    sessionsChanged = Signal()
    detailsChanged = Signal()
    confirmChanged = Signal()
```

After `pageRequested = Signal(str)` add:

```python
    sessionsFilterChanged = Signal(str, str, str, str)  # tab, query, from, to
    sessionsFilterCleared = Signal()
    refreshSessionsRequested = Signal()
    autoRefreshChanged = Signal(bool)
    sessionActionRequested = Signal(str)  # a session's key
    sessionDetailsRequested = Signal(str)
    exportSessionsRequested = Signal(str)  # "csv" or "xlsx"
    closeDetailsRequested = Signal()
    detailsFilterChanged = Signal(str)
    retryDetailsRequested = Signal()
    exportDetailsRequested = Signal()
    takeOverAnswered = Signal(bool)
```

In `__init__`, after `self._statistics: dict = {}` add:

```python
        self._sessions: dict = {}
        self._details: dict = {}
        self._confirm: dict = {}
```

After the `statistics = Property(...)` line add:

```python
    def _get_sessions(self) -> dict:
        return self._sessions

    sessions = Property("QVariantMap", _get_sessions, notify=sessionsChanged)

    def _get_details(self) -> dict:
        return self._details

    details = Property("QVariantMap", _get_details, notify=detailsChanged)

    def _get_confirm(self) -> dict:
        return self._confirm

    confirm = Property("QVariantMap", _get_confirm, notify=confirmChanged)
```

After the `showPage` slot add:

```python
    @Slot(str, str, str, str)
    def setSessionsFilter(self, tab, query, date_from, date_to) -> None:
        self.sessionsFilterChanged.emit(str(tab), str(query), str(date_from), str(date_to))

    @Slot()
    def clearSessionsFilter(self) -> None:
        self.sessionsFilterCleared.emit()

    @Slot()
    def refreshSessions(self) -> None:
        self.refreshSessionsRequested.emit()

    @Slot(bool)
    def setAutoRefresh(self, enabled) -> None:
        self.autoRefreshChanged.emit(bool(enabled))

    @Slot(str)
    def sessionAction(self, key) -> None:
        self.sessionActionRequested.emit(str(key))

    @Slot(str)
    def sessionDetails(self, key) -> None:
        self.sessionDetailsRequested.emit(str(key))

    @Slot(str)
    def exportSessions(self, fmt) -> None:
        self.exportSessionsRequested.emit(str(fmt))

    @Slot()
    def closeDetails(self) -> None:
        self.closeDetailsRequested.emit()

    @Slot(str)
    def setDetailsFilter(self, text) -> None:
        self.detailsFilterChanged.emit(str(text))

    @Slot()
    def retryDetails(self) -> None:
        self.retryDetailsRequested.emit()

    @Slot()
    def exportDetails(self) -> None:
        self.exportDetailsRequested.emit()

    @Slot(bool)
    def answerTakeOver(self, yes) -> None:
        self.takeOverAnswered.emit(bool(yes))
```

After `set_statistics` add:

```python
    def set_sessions(self, payload: dict) -> None:
        payload = dict(payload or {})
        if payload != self._sessions:
            self._sessions = payload
            self.sessionsChanged.emit()

    def set_details(self, payload: dict) -> None:
        payload = dict(payload or {})
        if payload != self._details:
            self._details = payload
            self.detailsChanged.emit()

    def set_confirm(self, payload: dict) -> None:
        payload = dict(payload or {})
        if payload != self._confirm:
            self._confirm = payload
            self.confirmChanged.emit()
```

`PageBridge.__init__` connects every notify signal to the revision by itself; nothing else is needed.

- [ ] **Step 4: Append to `gui/web/floor.css`**

In the header comment replace "phases 4 and 5 add inputs when a page first uses them" with "phase 4 added the segmented control, the input, the menu and the dot". Append:

```css

/* --- segmented control --------------------------------------------------- */

.segmented { align-self: auto; height: var(--control-height); }
.segment { height: 38px; padding: 0 12px; }

/* --- input: a label wrapping a glyph, an <input> and a clear button ------- */

.input { gap: 8px; padding: 0 6px 0 12px; border-color: var(--border-strong); }
.input > .glyph { width: 18px; height: 18px; }

/* --- menu ---------------------------------------------------------------- */

.menu-item { height: 44px; gap: 10px; padding: 0 12px; }
.menu-group { padding: 6px 12px 4px; font-weight: 400; }

/* --- dot: who set a status. Solid, a person; hollow, the system. --------- */

.dot {
  flex: none;
  width: 8px;
  height: 8px;
  box-sizing: border-box;
  border: 2px solid currentColor;
  border-radius: 50%;
}
.dot.solid { background: currentColor; }
.badge > .dot { margin: 0 4px 0 -2px; }
```

- [ ] **Step 5: Edit `gui/web/app.html`**

(a) Replace the body comment `<!-- The app document (ADR 0003): Packing and Statistics. Every string from the bridge goes in through textContent. -->` with the same sentence naming "Packing, Statistics, Sessions and Session details".

(b) In the `no-client` section give the paragraph an id:

```html
    <p class="state-card-text" id="no-client-text">Sessions, packing lists and SKU mapping all belong to one client.</p>
```

(c) Insert after the closing `</div>` of `<div class="app-page" id="statistics" hidden>` and before `<div class="toast-wrap">`:

```html
  <div class="app-page" id="sessions" hidden>
    <div class="banner danger app-s-banner" id="s-failed" hidden>
      <svg class="glyph" viewBox="0 0 24 24"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
      <div class="banner-body">
        <div class="banner-title">Refresh failed</div>
        <div class="banner-text"><span class="mono" id="s-failed-path"></span> could not be read at <span class="mono" id="s-failed-at"></span>: <span id="s-failed-cause"></span>.<span id="s-failed-from-line"> The list below is from <span class="mono" id="s-failed-from"></span>.</span></div>
      </div>
      <button type="button" class="btn secondary" id="s-failed-retry" data-action="refreshSessions">Retry</button>
    </div>

    <div class="app-s-bar">
      <div class="segmented" role="radiogroup" aria-label="Status" id="s-tabs"></div>
      <label class="input app-s-search">
        <svg class="glyph" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        <input type="text" id="s-query" placeholder="Search sessions" autocomplete="off" spellcheck="false">
        <button type="button" class="app-clear" id="s-query-clear" data-action="clearQuery" title="Clear search" aria-label="Clear search" hidden>
          <svg class="glyph" viewBox="0 0 24 24"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
        </button>
      </label>
      <div class="app-s-dates" title="Date range">
        <label><span>From</span><input type="date" id="s-from"></label>
        <span class="app-s-dates-rule"></span>
        <label><span>To</span><input type="date" id="s-to"></label>
      </div>
      <button type="button" class="btn secondary icon" id="s-refresh" data-action="refreshSessions" title="Refresh  F5" aria-label="Refresh">
        <svg class="glyph" viewBox="0 0 24 24"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>
      </button>
      <div class="app-s-stamp">
        <span class="app-s-stamp-line" id="s-stamp-line"><span id="s-stamp-label"></span> <span class="mono" id="s-stamp"></span></span>
        <label class="app-s-auto" title="Refresh every 2 minutes">
          <button type="button" class="switch" role="switch" id="s-auto" data-action="toggleAuto" aria-checked="true"><span class="switch-knob"></span></button>
          Auto-refresh (2 min)
        </label>
      </div>
      <div class="menu-anchor">
        <button type="button" class="btn secondary icon" id="s-export" data-action="toggleExport" title="Export the rows shown" aria-label="Export" aria-haspopup="menu" aria-expanded="false">
          <svg class="glyph" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/></svg>
        </button>
        <div class="menu app-s-menu" id="s-export-menu" role="menu" hidden>
          <div class="menu-group" id="s-export-title"></div>
          <button type="button" class="menu-item" role="menuitem" data-action="exportCsv">CSV<span class="menu-hint mono">.csv</span></button>
          <button type="button" class="menu-item" role="menuitem" data-action="exportXlsx">Excel<span class="menu-hint mono">.xlsx</span></button>
        </div>
      </div>
    </div>

    <div class="app-s-main" id="s-main">
      <section class="card app-s-list">
        <div class="tbl-head">
          <span>Status</span><span>Session</span><span class="app-s-r">Age</span><span>Packing</span><span>Orders</span><span class="app-s-r app-s-wide">Items</span><span class="app-s-wide">Last touched</span>
        </div>
        <div class="app-rows">
          <div class="app-s-loading" id="s-loading" hidden>
            <svg class="glyph" viewBox="0 0 24 24"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>
            <span>Reading sessions from the server…</span>
          </div>
          <div id="s-skeleton" hidden></div>
          <div id="s-rows"></div>
          <div class="app-no-match" id="s-no-match" hidden>
            <svg class="glyph" viewBox="0 0 24 24"><path d="m13.5 8.5-5 5"/><path d="m8.5 8.5 5 5"/><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
            <div class="app-no-match-title">No sessions match</div>
            <div class="app-no-match-text" id="s-no-match-text"></div>
            <button type="button" class="btn secondary" data-action="clearSessionsFilter">Clear filters</button>
          </div>
          <div class="app-no-match" id="s-empty" hidden>
            <svg class="glyph" viewBox="0 0 24 24"><path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>
            <div class="app-no-match-title">No sessions yet</div>
            <div class="app-no-match-text">Sessions appear here once someone starts packing for this client.</div>
          </div>
        </div>
        <div class="app-s-foot">
          <span class="app-s-legend"><span class="dot solid"></span>Set by a person</span>
          <span class="app-s-legend"><span class="dot"></span>Inferred by the system</span>
          <span class="spacer"></span>
          <span>Double-click a session for its action</span>
          <span class="mono app-s-count" id="s-count"></span>
        </div>
      </section>

      <aside class="card app-s-pane" id="s-pane" hidden>
        <div class="app-p-head">
          <div class="app-p-top">
            <span id="p-chip"></span>
            <span class="spacer"></span>
            <button type="button" class="app-clear app-p-close" data-action="closePane" title="Close  Esc" aria-label="Close">
              <svg class="glyph" viewBox="0 0 24 24"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </div>
          <span class="mono app-p-id" id="p-id"></span>
          <span class="app-p-list" id="p-list"></span>
          <span class="app-p-why" id="p-why"></span>
        </div>
        <div class="app-p-body">
          <div class="app-p-orders">
            <div class="app-p-line"><span class="spacer app-p-label">Orders done</span><span class="mono app-strong" id="p-orders"></span></div>
            <div class="track app-p-track"><div class="app-bar-fill" id="p-fill"></div></div>
            <span class="app-p-note" id="p-orders-note"></span>
          </div>
          <div id="p-facts"></div>
        </div>
        <div class="app-p-foot">
          <div class="app-p-warn" id="p-note" hidden>
            <svg class="glyph" viewBox="0 0 24 24"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
            <span id="p-note-text"></span>
          </div>
          <button type="button" class="btn primary" id="p-action" data-action="paneAction"></button>
          <button type="button" class="btn ghost" id="p-details" data-action="paneDetails">View details</button>
          <span class="app-p-hint">Or double-click the row</span>
        </div>
      </aside>
    </div>
  </div>

  <div class="app-details" id="details" hidden></div>

  <div class="scrim" id="confirm" hidden>
    <div class="dialog app-confirm" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title">
      <h2 class="dialog-title" id="confirm-title">
        <svg class="glyph" viewBox="0 0 24 24"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
        <span>Take over <span class="mono" id="confirm-id"></span>?</span>
      </h2>
      <p class="dialog-text" id="confirm-body"></p>
      <p class="dialog-text app-secondary" id="confirm-carry"></p>
      <div class="dialog-actions">
        <button type="button" class="btn secondary" id="confirm-cancel" data-action="cancelTakeOver">Cancel</button>
        <button type="button" class="btn primary" id="confirm-ok" data-action="confirmTakeOver">Take over and resume</button>
      </div>
    </div>
  </div>
```

Task 5 fills `<div class="app-details" id="details">`.

- [ ] **Step 6: Append to `gui/web/app.css`**

In the header comment, after "frames 3a-3g and 4a-4c." add "Phase 4: Sessions (7a-7h) and Session details (8a-8f)." Append:

```css

/* --- Sessions (frames 7a-7h) --------------------------------------------- */

.app-secondary { color: var(--text-secondary); }

/* floor.css lays a banner out as one row with its title stretching. */
.app-s-banner { flex: none; }
.app-s-banner .banner-title { flex: none; }

.app-s-bar { flex: none; display: flex; align-items: center; gap: 8px; min-width: 0; }
.app-s-bar .segmented { flex: none; }
.app-s-search { flex: 1 1 200px; min-width: 130px; }

.app-clear {
  flex: none;
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}
.app-clear > .glyph { width: 18px; height: 18px; }
.app-clear:hover { background: var(--hover); }
.app-clear:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }

.app-s-dates {
  flex: none;
  display: flex;
  align-items: center;
  height: var(--control-height);
  border: 1px solid var(--border-strong);
  border-radius: var(--kit-radius);
  background: var(--surface);
  white-space: nowrap;
}
.app-s-dates label { display: flex; align-items: baseline; gap: 6px; padding: 0 10px; }
.app-s-dates label > span { font-size: var(--type-caption-size); color: var(--text-secondary); }
.app-s-dates input {
  padding: 0;
  border: 0;
  outline: 0;
  background: transparent;
  /* The platform's own date control, drawn for the app's theme. */
  color-scheme: var(--color-scheme);
}
.app-s-dates label:focus-within {
  outline: 2px solid var(--focus-ring);
  outline-offset: -2px;
  border-radius: var(--kit-radius);
}
.app-s-dates-rule { width: 1px; height: 24px; background: var(--border); }

.app-s-stamp {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
  white-space: nowrap;
}
.app-s-stamp-line.failed { color: var(--status-danger); font-weight: 700; }
.app-s-auto { display: flex; align-items: center; gap: 6px; cursor: pointer; }
.app-s-menu { left: auto; right: 0; min-width: 240px; }

.app-s-main { flex: 1; min-height: 0; display: flex; gap: 16px; }

.app-s-list {
  --tbl-cols: 150px 150px 64px minmax(0, 1fr) 170px 76px 230px;
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
/* With the pane open, Items and Last touched fold into it. */
.app-s-main.pane-open .app-s-list { --tbl-cols: 150px 150px 64px minmax(0, 1fr) 170px; }
.app-s-main.pane-open .app-s-wide { display: none; }
.app-s-list > .tbl-head { padding: 0 12px; overflow: hidden; scrollbar-gutter: stable; }
.app-s-list > .tbl-head > span { padding: 0 8px; }
.app-s-list .app-rows { display: flex; flex-direction: column; }
.app-s-r { text-align: right; }

/* A session row is a button: a click selects it, a double-click acts. */
.app-srow {
  flex: none;
  width: 100%;
  height: 44px;
  padding: 0 12px;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
  background: transparent;
  text-align: left;
  cursor: default;
}
.app-srow > span { min-width: 0; padding: 0 8px; }
.app-srow:hover { background: var(--surface-raised); }
.app-srow[aria-pressed="true"] {
  padding-left: 8px;
  border-left: 4px solid var(--selection-border);
  background: var(--selection-bg);
}
.app-srow:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.app-s-id { font-weight: 700; white-space: nowrap; }
.app-s-age { color: var(--text-secondary); white-space: nowrap; }
.app-s-orders { display: flex; align-items: center; gap: 10px; white-space: nowrap; }
.app-s-items.none { color: var(--text-disabled); }
.app-s-touched { color: var(--text-secondary); }

.app-bar {
  flex: none;
  width: 56px;
  height: 6px;
  border-radius: 3px;
  background: var(--border);
  overflow: hidden;
}
.app-bar-fill { display: block; height: 100%; background: var(--text-secondary); }
.app-bar-fill.success { background: var(--status-success-dot); }
.app-bar-fill.danger { background: var(--status-danger-dot); }

/* 7e: one line of status over still skeleton rows. */
.app-s-loading {
  flex: none;
  display: flex;
  align-items: center;
  gap: 10px;
  height: 44px;
  padding: 0 20px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-secondary);
}
.app-s-loading > .glyph { width: 18px; height: 18px; }
.app-skel { padding: 0 12px; }
.app-skel > span { padding: 0 8px; }
.app-skel-bar {
  display: block;
  width: 100px;
  height: 10px;
  border-radius: 5px;
  background: var(--border);
}
.app-skel > span:nth-child(2) .app-skel-bar { width: 110px; }
.app-skel > span:nth-child(3) .app-skel-bar { width: 30px; }
.app-skel > span:nth-child(4) .app-skel-bar { width: 140px; }

.app-s-foot {
  flex: none;
  display: flex;
  align-items: center;
  gap: 16px;
  height: 40px;
  padding: 0 20px;
  border-top: 1px solid var(--border-subtle);
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
  white-space: nowrap;
}
.app-s-legend { display: flex; align-items: center; gap: 6px; }
.app-s-count { color: var(--text); }

/* --- the pane ------------------------------------------------------------ */

.app-s-pane { flex: none; width: 360px; display: flex; flex-direction: column; overflow: hidden; }
.app-p-head {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 12px 16px 20px;
  border-bottom: 1px solid var(--border);
}
.app-p-top { display: flex; align-items: center; gap: 8px; }
.app-p-close { width: 44px; height: 44px; border-radius: var(--kit-radius); }
.app-p-id { font-size: var(--type-display-size); font-weight: 700; }
.app-p-list {
  font-size: var(--type-heading-size);
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.app-p-why { font-size: var(--type-caption-size); color: var(--text-secondary); }
.app-p-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 8px 20px;
  overflow: auto;
}
.app-p-orders {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border-subtle);
}
.app-p-line { display: flex; align-items: baseline; gap: 8px; }
.app-p-label { color: var(--text-secondary); }
.app-p-track { height: 8px; border-radius: 4px; }
.app-p-note { font-size: var(--type-caption-size); color: var(--text-secondary); }
.app-p-fact {
  display: flex;
  align-items: baseline;
  gap: 12px;
  min-height: 40px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-subtle);
}
.app-p-fact > .app-p-label { flex: none; }
.app-p-value {
  flex: 1;
  min-width: 0;
  text-align: right;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.app-p-foot {
  flex: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px 20px;
  border-top: 1px solid var(--border);
}
.app-p-foot .btn { width: 100%; }
/* Why the action is off; amber when it is a warning about taking over. */
.app-p-warn {
  display: flex;
  gap: 8px;
  padding: 8px 10px;
  border-radius: var(--kit-radius);
  background: var(--surface-raised);
  color: var(--text-secondary);
  font-size: var(--type-caption-size);
}
.app-p-warn.warn { background: var(--status-warning-bg); color: var(--status-warning); }
.app-p-warn > .glyph { width: 16px; height: 16px; margin-top: 1px; }
.app-p-hint { font-size: var(--type-caption-size); color: var(--text-secondary); text-align: center; }

/* --- 7c: the take-over question ------------------------------------------ */

.app-confirm { width: 540px; }
.app-confirm .dialog-title .glyph { color: var(--status-warning); }
```

- [ ] **Step 7: Edit `gui/web/app.js`**

(a) Replace the header comment (the first six lines) with:

```js
// The app document: Packing, Statistics, Sessions and Session details (ADR
// 0003). The page renders what the bridge sends. What Packing and Statistics
// say is decided in gui/app_bridge.py, what the Sessions pages say in
// gui/sessions_payload.py; the page keeps only which order rows were toggled,
// how the SKU table is sorted, which session is selected and which orders are
// open in details. Every string from the bridge goes in through textContent.
// Specs: docs/superpowers/specs/2026-10-08-ui-refresh-phase3-packing-statistics-design.md
// and 2026-10-08-ui-refresh-phase4-sessions-design.md
```

(b) In `const view = {...}` add after `toastTimer: 0,`:

```js
  sel: null,             // the selected session's key
  tab: null,
  exportOpen: false,
  detailsKey: "",
  dOpen: Object.create(null),  // order numbers open in Session details
```

(c) In `renderFrame`, replace from `const packing = page === "packing";` down to and including `if (bridge.covered) show(els.toast, false);` with:

```js
  const packing = page === "packing";
  const stats = page === "statistics";
  const work = packing || stats;  // the two pages of the session open here
  const client = !!shell.client;
  const on = function (condition) { return !bridge.covered && condition; };

  show(els.noClient, on(!client));
  show(els.chooseClient, !!shell.clients);
  els.noClientTitle.textContent = work ? "Choose a client to begin" : "Choose a client";
  els.noClientText.textContent = work
    ? "Sessions, packing lists and SKU mapping all belong to one client."
    : "Pick a client in the bar above to see its sessions.";
  show(els.noSession, on(client && state === "none" && packing));
  els.openSession.disabled = !!shell.serverDown;
  show(els.statsEmpty, on(client && state === "none" && stats));
  show(els.head, on(client && work && state !== "none"));
  show(els.opening, on(client && work && state === "opening"));
  show(els.failed, on(client && work && state === "failed"));
  show(els.packing, on(client && state === "open" && packing));
  show(els.statistics, on(client && state === "open" && stats));
  show(els.sessions, on(client && page === "sessions"));
  show(els.details, on(client && page === "details"));
  if (bridge.covered) show(els.toast, false);
  renderConfirm();
```

(The lines above it that read `bridge`, `shell`, `session`, `state` and `page` stay. Delete the old `const client = ...` and `const on = ...` lines so they are declared once.)

(d) Insert this section before the `// --- toast ---` section:

```js
// --- Sessions -----------------------------------------------------------------

// An input shows what Python last said, unless the packer is typing in it.
function setInput(input, value) {
  if (document.activeElement !== input && input.value !== value) input.value = value;
}

// The status chip: the word on its tone, and a dot that is solid when a
// person set the status and hollow when the system inferred it.
function chip(row) {
  const node = el("span", "badge " + (row.tone || "neutral"));
  node.appendChild(el("span", "dot" + (row.manual ? " solid" : "")));
  node.appendChild(document.createTextNode(row.label || ""));
  return node;
}

function fillClass(row) {
  if (row.status === "completed") return "app-bar-fill success";
  if (row.status === "incomplete") return "app-bar-fill danger";
  return "app-bar-fill";
}

function sessionRows() {
  return (view.bridge.sessions || {}).rows || [];
}

function selectedRow() {
  return sessionRows().find(function (row) { return row.key === view.sel; }) || null;
}

function sessionRow(row) {
  const node = el("button", "tbl-row app-srow");
  node.type = "button";
  node.dataset.session = row.key;
  node.title = row.actionLabel ? "Double-click: " + row.actionLabel : "";
  const status = el("span");
  status.appendChild(chip(row));
  node.appendChild(status);
  node.appendChild(el("span", "mono app-s-id", row.id));
  node.appendChild(el("span", "mono app-s-r app-s-age", row.age));
  node.appendChild(cut("", row.list));
  const orders = el("span", "app-s-orders");
  const bar = el("span", "app-bar");
  const fill = el("span", fillClass(row));
  fill.style.width = (row.pct || 0) + "%";
  bar.appendChild(fill);
  orders.appendChild(bar);
  orders.appendChild(el("span", "mono", row.orders));
  node.appendChild(orders);
  node.appendChild(el("span", "mono app-s-r app-s-wide app-s-items" + (row.items === "—" ? " none" : ""), row.items));
  node.appendChild(cut("app-s-wide app-s-touched", row.touched));
  return node;
}

// The pane, the selection mark and the Export menu: the page's own state,
// redrawn without rebuilding the rows (a double-click needs its row to stay).
function renderPane() {
  const row = selectedRow();
  els.sMain.classList.toggle("pane-open", !!row);
  show(els.sPane, !!row);
  show(els.sExportMenu, view.exportOpen);
  els.sExport.setAttribute("aria-expanded", String(view.exportOpen));
  Array.from(els.sRows.children).forEach(function (node) {
    node.setAttribute("aria-pressed", String(node.dataset.session === view.sel));
  });
  if (!row) return;

  els.pChip.replaceChildren(chip(row));
  els.pId.textContent = row.id;
  els.pList.textContent = row.list;
  els.pList.title = row.list;
  els.pWhy.textContent = row.setBy + " · " + row.why;
  els.pOrders.textContent = row.orders;
  els.pFill.className = fillClass(row);
  els.pFill.style.width = (row.pct || 0) + "%";
  els.pOrdersNote.textContent = row.ordersNote;
  els.pFacts.replaceChildren.apply(els.pFacts, (row.facts || []).map(function (fact) {
    const line = el("div", "app-p-fact");
    line.appendChild(el("span", "app-p-label", fact.label));
    const value = el("span", "app-p-value", fact.value);
    value.title = fact.value;
    line.appendChild(value);
    return line;
  }));
  show(els.pNote, !!row.note);
  els.pNote.classList.toggle("warn", !!row.warn);
  els.pNoteText.textContent = row.note || "";
  show(els.pAction, !!row.actionLabel);
  els.pAction.textContent = row.actionLabel || "";
  els.pAction.disabled = !row.enabled;
  show(els.pDetails, !!row.canDetails);
}

function renderSessions() {
  const s = view.bridge.sessions || {};
  const loading = s.mode === "loading";
  const rows = s.rows || [];
  const focused = document.activeElement && document.activeElement.dataset
    ? document.activeElement.dataset : {};
  const focusedTab = focused.tab;
  const focusedSession = focused.session;

  if (s.tab !== view.tab) {
    view.tab = s.tab;
    view.sel = null;
  }
  if (!rows.some(function (row) { return row.key === view.sel; })) view.sel = null;

  els.sTabs.replaceChildren.apply(els.sTabs, (s.tabs || []).map(function (tab) {
    const button = el("button", "segment");
    button.type = "button";
    button.dataset.tab = tab.key;
    button.setAttribute("role", "radio");
    button.setAttribute("aria-checked", String(tab.key === s.tab));
    button.appendChild(document.createTextNode(tab.label));
    button.appendChild(el("span", "segment-count", loading ? "–" : tab.count));
    return button;
  }));
  setInput(els.sQuery, s.query || "");
  setInput(els.sFrom, s.dateFrom || "");
  setInput(els.sTo, s.dateTo || "");
  show(els.sQueryClear, !!s.query);
  els.sRefresh.disabled = !!s.refreshing;
  els.sStampLabel.textContent = s.refreshing ? "Refreshing…" : s.stamp ? "Last refreshed" : "";
  els.sStamp.textContent = s.refreshing ? "" : s.stamp || "";
  els.sStampLine.classList.toggle("failed", !!s.failed);
  els.sAuto.setAttribute("aria-checked", String(!!s.auto));
  els.sExport.disabled = !(s.shown > 0);
  if (els.sExport.disabled) view.exportOpen = false;
  els.sExportTitle.textContent = s.exportTitle || "";

  const failure = s.failure || {};
  show(els.sFailed, !!s.failed);
  els.sFailedPath.textContent = failure.path || "";
  els.sFailedAt.textContent = failure.at || "";
  els.sFailedCause.textContent = failure.cause || "";
  els.sFailedFrom.textContent = failure.from || "";
  show(els.sFailedFromLine, !!failure.from);

  show(els.sLoading, loading);
  show(els.sSkeleton, loading);
  // With the server away an empty list is not a fact about the client.
  show(els.sEmpty, s.mode === "empty" && !s.failed);
  show(els.sNoMatch, !!s.noMatch);
  els.sNoMatchText.textContent = s.noMatchText || "";
  els.sCount.textContent = s.count || "";

  // ponytail: every row is rebuilt on every push. Fine at a few hundred
  // sessions; patch rows in place if a client ever lists thousands.
  const built = document.createDocumentFragment();
  rows.forEach(function (row) { built.appendChild(sessionRow(row)); });
  els.sRows.replaceChildren(built);
  renderPane();

  // The redraw replaced what had the focus: give it back.
  const again = focusedTab
    ? Array.from(els.sTabs.children).find(function (n) { return n.dataset.tab === focusedTab; })
    : focusedSession
      ? Array.from(els.sRows.children).find(function (n) { return n.dataset.session === focusedSession; })
      : null;
  if (again) again.focus();
}

function sendFilter(change) {
  const s = view.bridge.sessions || {};
  const next = Object.assign({
    tab: s.tab || "all",
    query: els.sQuery.value,
    dateFrom: els.sFrom.value,
    dateTo: els.sTo.value,
  }, change || {});
  view.bridge.setSessionsFilter(next.tab, next.query, next.dateFrom, next.dateTo);
}

// 7c. Drawn over whichever page is showing; never under Packer Mode.
function renderConfirm() {
  const confirm = view.bridge.confirm || {};
  const open = !view.bridge.covered && !!confirm.key;
  const was = !els.confirm.hidden;
  show(els.confirm, open);
  els.confirmId.textContent = confirm.id || "";
  els.confirmBody.textContent = confirm.body || "";
  els.confirmCarry.textContent = confirm.carry || "";
  if (open && !was) els.confirmCancel.focus();
}

function onDoubleClick(event) {
  const node = event.target.closest("[data-session]");
  if (!node) return;
  const row = sessionRows().find(function (r) { return r.key === node.dataset.session; });
  if (row && row.enabled && row.action) view.bridge.sessionAction(row.key);
}

// These reach the page only while it has the focus, which a click gives it.
function onKey(event) {
  const bridge = view.bridge;
  const page = bridge.page;
  if (event.key === "Escape") {
    if ((bridge.confirm || {}).key) bridge.answerTakeOver(false);
    else if (view.exportOpen) { view.exportOpen = false; renderPane(); }
    else if (page === "sessions" && view.sel) { view.sel = null; renderPane(); }
    else return;
    event.preventDefault();
  } else if (event.key === "F5" && page === "sessions") {
    event.preventDefault();
    bridge.refreshSessions();
  } else if (event.key === "ArrowLeft" && event.altKey && page === "details") {
    event.preventDefault();
    bridge.closeDetails();
  }
}
```

(e) In `ACTIONS` add after the `clearFilter` entry:

```js
  refreshSessions: function (bridge) { bridge.refreshSessions(); },
  clearSessionsFilter: function (bridge) { bridge.clearSessionsFilter(); },
  clearQuery: function () { els.sQuery.value = ""; sendFilter(); els.sQuery.focus(); },
  toggleAuto: function (bridge) {
    bridge.setAutoRefresh(els.sAuto.getAttribute("aria-checked") !== "true");
  },
  toggleExport: function () { view.exportOpen = !view.exportOpen; renderPane(); },
  exportCsv: function (bridge) { view.exportOpen = false; renderPane(); bridge.exportSessions("csv"); },
  exportXlsx: function (bridge) { view.exportOpen = false; renderPane(); bridge.exportSessions("xlsx"); },
  closePane: function () { view.sel = null; renderPane(); },
  paneAction: function (bridge) { if (view.sel) bridge.sessionAction(view.sel); },
  paneDetails: function (bridge) { if (view.sel) bridge.sessionDetails(view.sel); },
  cancelTakeOver: function (bridge) { bridge.answerTakeOver(false); },
  confirmTakeOver: function (bridge) { bridge.answerTakeOver(true); },
```

(f) Replace `onClick` with:

```js
function onClick(event) {
  // A click anywhere but the Export button and its menu closes the menu.
  if (view.exportOpen && !event.target.closest(".menu-anchor")) {
    view.exportOpen = false;
    renderPane();
  }
  const action = event.target.closest("[data-action]");
  if (action) {
    if (!action.disabled) ACTIONS[action.dataset.action](view.bridge);
    return;
  }
  const order = event.target.closest("[data-order]");
  if (order) {
    toggleOrder(order.dataset.order);
    return;
  }
  const sort = event.target.closest("[data-sort]");
  if (sort) {
    sortBy(sort.dataset.sort);
    return;
  }
  const tab = event.target.closest("[data-tab]");
  if (tab) {
    sendFilter({ tab: tab.dataset.tab });
    return;
  }
  const session = event.target.closest("[data-session]");
  if (session) {
    view.sel = session.dataset.session;
    renderPane();
  }
}
```

(g) In `IDS` change `noClient: "no-client", chooseClient: "choose-client",` to

```js
  noClient: "no-client", noClientTitle: "no-client-title", noClientText: "no-client-text",
  chooseClient: "choose-client",
```

and add before the `toast:` line:

```js
  sessions: "sessions", details: "details",
  sFailed: "s-failed", sFailedPath: "s-failed-path", sFailedAt: "s-failed-at",
  sFailedCause: "s-failed-cause", sFailedFromLine: "s-failed-from-line",
  sFailedFrom: "s-failed-from",
  sTabs: "s-tabs", sQuery: "s-query", sQueryClear: "s-query-clear", sFrom: "s-from",
  sTo: "s-to", sRefresh: "s-refresh", sStampLine: "s-stamp-line",
  sStampLabel: "s-stamp-label", sStamp: "s-stamp", sAuto: "s-auto",
  sExport: "s-export", sExportMenu: "s-export-menu", sExportTitle: "s-export-title",
  sMain: "s-main", sLoading: "s-loading", sSkeleton: "s-skeleton", sRows: "s-rows",
  sNoMatch: "s-no-match", sNoMatchText: "s-no-match-text", sEmpty: "s-empty",
  sCount: "s-count", sPane: "s-pane",
  pChip: "p-chip", pId: "p-id", pList: "p-list", pWhy: "p-why", pOrders: "p-orders",
  pFill: "p-fill", pOrdersNote: "p-orders-note", pFacts: "p-facts", pNote: "p-note",
  pNoteText: "p-note-text", pAction: "p-action", pDetails: "p-details",
  confirm: "confirm", confirmId: "confirm-id", confirmBody: "confirm-body",
  confirmCarry: "confirm-carry", confirmCancel: "confirm-cancel",
```

(If `noClientTitle` is already in `IDS` under another spelling, keep one entry.)

(h) In the `QWebChannel` callback, after `els.sortHeads = ...` add:

```js
  // 7e's skeleton: twelve still rows, built once.
  for (let index = 0; index < 12; index += 1) {
    const row = el("div", "tbl-row app-skel");
    for (let cell = 0; cell < 5; cell += 1) {
      const holder = el("span");
      holder.appendChild(el("span", "app-skel-bar"));
      row.appendChild(holder);
    }
    els.sSkeleton.appendChild(row);
  }
```

and after `renderStatistics();` (the call, in the callback) add:

```js
  bridge.sessionsChanged.connect(renderSessions);
  renderSessions();
  bridge.confirmChanged.connect(renderConfirm);
  els.sQuery.addEventListener("input", function () { sendFilter(); });
  els.sFrom.addEventListener("change", function () { sendFilter(); });
  els.sTo.addEventListener("change", function () { sendFilter(); });
  els.root.addEventListener("dblclick", onDoubleClick);
  document.addEventListener("keydown", onKey);
```

`renderFrame` already runs on `coveredChanged` and now calls `renderConfirm`, so the question hides under Packer Mode.

- [ ] **Step 8: Run the page tests, and phase 3's**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_sessions_page.py tests/test_app_bridge.py`
Expected: all pass. If `test_selecting_a_row_opens_the_pane_and_folds_two_columns` fails on its last line, the `.pane-open .app-s-wide { display: none; }` rule is not reaching the row's cells: check the class is on `#s-main`. If a test times out in `_settle`, a render function threw: open the page's console through `view.page().javaScriptConsoleMessage` or read the error by evaluating `renderSessions()` in `_eval`.

- [ ] **Step 9: The guards, lint, commit**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_style_literals_guard.py`
Expected: pass. (If it objects to `currentColor`, it is reading it as a colour name: it should not, `stroke: currentColor` is already in the kit. Report what it printed rather than changing the guard.)

Run: `.venv/bin/ruff check . --exclude shared`. Stage `gui/app_bridge.py`, `gui/web/floor.css`, `gui/web/app.html`, `gui/web/app.css`, `gui/web/app.js`, `tests/test_app_sessions_page.py`. Message: `feat: the Sessions page, its pane and the take-over question in the app document`.

---

### Task 5: The Session details page (8a to 8f)

**Files:**
- Modify: `gui/web/app.html` (fill `#details`), `gui/web/app.css` (append), `gui/web/app.js`
- Test: `tests/test_app_sessions_page.py` (append)

**Interfaces:**
- Consumes: `details_payload` (Task 3) and its shape; from Task 4 the bridge's `details` property, the slots `closeDetails`, `setDetailsFilter`, `retryDetails`, `exportDetails`, and in `app.js` `chip`, `setInput`, `renderPane`, `glyph`, `cut`, `el`, `show`, `view.detailsKey`, `view.dOpen`, `view.sel`.
- Produces: nothing later tasks call. The element ids `d-*` are used by `scripts/render_sessions.py` (Task 8) only through `[data-dorder]` clicks.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app_sessions_page.py`. Add to its imports `import test_session_details_payload as dp` (the tests folder is on the path, as `from conftest import ...` elsewhere relies on) and extend the `gui.sessions_payload` import with `details_payload`.

```python
# --- Session details (frames 8a to 8f) ----------------------------------------------

DETAIL_KEY = "2026-10-06_1|Morning_wave"


def detail(entry_over=None, files="default", **kwargs):
    files = dp.details() if files == "default" else files
    kwargs.setdefault("client", "Acme Cosmetics (ACME)")
    return details_payload(dp.entry(**(entry_over or {})), files, now=NOW, **kwargs)


@pytest.fixture
def detailed(page, qtbot):
    view, bridge = page
    bridge.set_details(detail())
    bridge.set_page("details")
    _settle(qtbot, bridge)
    return view, bridge


def _count(view, qtbot, selector):
    return _eval(qtbot, view, f"document.querySelectorAll({json.dumps(selector)}).length")


def _order_js(number):
    return ("Array.from(document.querySelectorAll('[data-dorder]'))"
            f".find(function (n) {{ return n.dataset.dorder === {json.dumps(number)}; }})")


def test_8a_a_finished_session(detailed, qtbot):
    view, _bridge = detailed
    assert _shown(view, qtbot, "details")
    assert not _shown(view, qtbot, "sessions")
    assert _text(view, qtbot, "d-id") == "2026-10-06_1"
    assert _text(view, qtbot, "d-why") == (
        "Set by a person · closed by Petya with 2 orders unpacked")
    assert _eval(qtbot, view, "!!document.querySelector('#d-chip .dot.solid')") is True
    assert _eval(qtbot, view,
                 "Array.from(document.querySelectorAll('#d-facts .app-d-fact-value'))"
                 ".map(function (n) { return n.textContent; })") == [
        "Acme Cosmetics (ACME)", "Morning_wave", "Petya (W-004)", "WH-PC-01",
        "6 Oct, 08:02:11", "6 Oct, 11:14:40", "3h 12m"]
    assert _eval(qtbot, view,
                 "Array.from(document.querySelectorAll('#d-cards .strip-value'))"
                 ".map(function (n) { return n.textContent; })") == ["2", "6", "12.4", "149", "1"]
    assert _eval(qtbot, view,
                 "Array.from(document.querySelectorAll('#d-groups .app-d-group-title'))"
                 ".map(function (n) { return n.textContent; })") == [
        "Order time", "Item time", "Scan quality"]
    assert _count(view, qtbot, "#d-groups .app-d-tile") == 9
    assert _text(view, qtbot, "d-showing") == "Showing 4 of 4 recorded orders"
    assert _count(view, qtbot, "#d-rows .app-dorder") == 4
    assert _count(view, qtbot, "#d-rows .app-ditem") == 0
    assert _eval(qtbot, view, "document.getElementById('d-export').disabled") is False
    for hidden in ("d-error", "d-live", "d-loading", "d-no-match", "d-none"):
        assert not _shown(view, qtbot, hidden), hidden


def test_8b_an_active_session_says_it_is_still_packing(page, qtbot):
    view, bridge = page
    bridge.set_details(detail({"status": "in_progress"}, stamp="14:06:31"))
    bridge.set_page("details")
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "d-live")
    assert _text(view, qtbot, "d-live-pc") == "WH-PC-01"
    assert _text(view, qtbot, "d-live-stamp") == "14:06:31"
    assert _text(view, qtbot, "d-metrics-note") == (
        "Only data from completed orders is shown. Figures so far.")
    assert _eval(qtbot, view,
                 "document.querySelector('#d-groups .app-d-group-title').textContent"
                 ) == "Order time so far"


def test_8c_no_timing_gives_one_sentence_and_keeps_scan_quality(page, qtbot):
    view, bridge = page
    files = dp.details(session_summary={"metrics": {}, "orders": [dp.ORDER_A],
                                        "skipped_orders": []})
    bridge.set_details(detail(files=files))
    bridge.set_page("details")
    _settle(qtbot, bridge)
    assert _eval(qtbot, view,
                 "document.querySelector('#d-groups .app-d-notiming').textContent"
                 ).startswith("Timing metrics are not available for this session.")
    assert _eval(qtbot, view,
                 "Array.from(document.querySelectorAll('#d-groups .app-d-group-title'))"
                 ".map(function (n) { return n.textContent; })") == ["Scan quality"]


def test_8d_an_order_opens_to_its_items_extras_and_unknowns(detailed, qtbot):
    view, _bridge = detailed
    _js(qtbot, view, f"{_order_js('#10407')}.click()")
    assert _eval(qtbot, view, f"{_order_js('#10407')}.getAttribute('aria-expanded')") == "true"
    assert _eval(qtbot, view,
                 "Array.from(document.querySelectorAll('#d-rows .app-ditem'))"
                 ".map(function (n) { return n.firstChild.textContent; })") == [
        "LST-07Lipstick, shade 07", "CRM-15MLEye cream 15 ml",
        "2 extra scans · not in this order", "1 unknown scan · barcode not recognised"]
    assert _eval(qtbot, view,
                 "Array.from(document.querySelectorAll('#d-rows .app-ditem .badge'))"
                 ".map(function (n) { return n.textContent; })") == [
        "Forced confirm", "Extra", "1 unknown"]
    assert _eval(qtbot, view,
                 f"Array.from({_order_js('#10407')}.querySelectorAll('.badge'))"
                 ".map(function (n) { return n.textContent; })") == [
        "Forced confirm", "2 extra", "1 correction", "1 unknown"]
    _js(qtbot, view, f"{_order_js('#10407')}.click()")
    assert _count(view, qtbot, "#d-rows .app-ditem") == 0


def test_a_skipped_order_does_not_open(detailed, qtbot):
    view, _bridge = detailed
    assert _count(view, qtbot, "#d-rows button.app-dorder") == 3
    assert _count(view, qtbot, "#d-rows div.app-dorder") == 1


def test_expand_all_and_collapse_all(detailed, qtbot):
    view, _bridge = detailed
    _js(qtbot, view, "document.querySelector('[data-action=\"expandAll\"]').click()")
    assert _count(view, qtbot, "#d-rows .app-ditem") == 7  # 4 + 1 + 2
    _js(qtbot, view, "document.querySelector('[data-action=\"collapseAll\"]').click()")
    assert _count(view, qtbot, "#d-rows .app-ditem") == 0


def test_another_sessions_details_start_closed_and_at_the_top(detailed, qtbot):
    view, bridge = detailed
    _js(qtbot, view, "document.querySelector('[data-action=\"expandAll\"]').click()")
    bridge.set_details(detail({"session_id": "2026-10-05_9"}))
    _settle(qtbot, bridge)
    assert _text(view, qtbot, "d-id") == "2026-10-05_9"
    assert _count(view, qtbot, "#d-rows .app-ditem") == 0
    assert _eval(qtbot, view, "document.getElementById('details').scrollTop") == 0


def test_the_orders_head_sticks_to_the_top_of_the_scroller(detailed, qtbot):
    view, _bridge = detailed
    assert _eval(qtbot, view,
                 "getComputedStyle(document.querySelector('.app-d-head')).position") == "sticky"
    assert _eval(qtbot, view,
                 "getComputedStyle(document.getElementById('details')).overflowY") == "auto"


def test_the_filter_reaches_python_and_8e_offers_to_clear_it(detailed, qtbot):
    view, bridge = detailed
    got = []
    bridge.detailsFilterChanged.connect(got.append)
    _js(qtbot, view,
        "var q = document.getElementById('d-query'); q.focus(); q.value = '10999';"
        "q.dispatchEvent(new Event('input', {bubbles: true}))")
    qtbot.waitUntil(lambda: got == ["10999"], timeout=5000)
    bridge.set_details(detail(query="#10999"))
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "d-no-match")
    assert _text(view, qtbot, "d-no-match-query") == "10999"
    assert _text(view, qtbot, "d-showing") == "Showing 0 of 4 recorded orders"
    assert _count(view, qtbot, "#d-rows .app-dorder") == 0
    _js(qtbot, view, "document.querySelector('#d-no-match .btn').click()")
    qtbot.waitUntil(lambda: got == ["10999", ""], timeout=5000)


def test_8f_unreadable_files_keep_the_facts_and_disable_export(page, qtbot):
    view, bridge = page
    asked = []
    bridge.retryDetailsRequested.connect(lambda: asked.append(1))
    bridge.set_details(detail(files=None, error={
        "path": "/srv/2026-10-06_1/packing/Morning_wave/packing_state.json",
        "cause": "permission denied"}))
    bridge.set_page("details")
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "d-error")
    assert _text(view, qtbot, "d-error-path").endswith("packing_state.json")
    assert _text(view, qtbot, "d-error-cause") == "permission denied"
    assert _count(view, qtbot, "#d-facts .app-d-fact") == 7
    assert not _shown(view, qtbot, "d-ready")
    assert not _shown(view, qtbot, "d-loading")
    assert _eval(qtbot, view, "document.getElementById('d-export').disabled") is True
    _click(view, qtbot, "d-error-retry")
    qtbot.waitUntil(lambda: asked == [1], timeout=5000)


def test_while_the_files_are_read_one_line_says_so(page, qtbot):
    view, bridge = page
    bridge.set_details(detail(files=None))
    bridge.set_page("details")
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "d-loading")
    assert _text(view, qtbot, "d-loading") == "Reading the session's files…"
    assert not _shown(view, qtbot, "d-ready")
    assert _count(view, qtbot, "#d-facts .app-d-fact") == 7


def test_export_back_and_alt_left_reach_python(detailed, qtbot):
    view, bridge = detailed
    exported, closed = [], []
    bridge.exportDetailsRequested.connect(lambda: exported.append(1))
    bridge.closeDetailsRequested.connect(lambda: closed.append(1))
    _click(view, qtbot, "d-export")
    qtbot.waitUntil(lambda: exported == [1], timeout=5000)
    _click(view, qtbot, "d-back")
    qtbot.waitUntil(lambda: closed == [1], timeout=5000)
    _js(qtbot, view,
        "document.dispatchEvent(new KeyboardEvent('keydown',"
        " {key: 'ArrowLeft', altKey: true, bubbles: true}))")
    qtbot.waitUntil(lambda: closed == [1, 1], timeout=5000)


def test_a_session_with_no_packed_orders_cannot_be_exported(page, qtbot):
    view, bridge = page
    files = {"record": {}, "session_info": {}, "session_summary": {},
             "packing_state": {"completed": [], "skipped_orders": [], "in_progress": {}}}
    bridge.set_details(detail(files=files))
    bridge.set_page("details")
    _settle(qtbot, bridge)
    assert _eval(qtbot, view, "document.getElementById('d-export').disabled") is True
    assert _eval(qtbot, view, "document.getElementById('d-export').title") == (
        "No order data to export")
    assert _shown(view, qtbot, "d-none")


def test_closing_details_selects_that_sessions_row(page, qtbot):
    view, bridge = page
    bridge.set_sessions(sessions_payload([dp.entry()], now=NOW))
    bridge.set_details(detail())
    bridge.set_page("details")
    _settle(qtbot, bridge)
    bridge.set_details({})
    bridge.set_page("sessions")
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "s-pane")
    assert _text(view, qtbot, "p-id") == "2026-10-06_1"
    assert _eval(qtbot, view, f"{_row_js(DETAIL_KEY)}.getAttribute('aria-pressed')") == "true"


def test_markup_in_a_sku_is_text(page, qtbot):
    """Review focus 3."""
    view, bridge = page
    nasty = {"order_number": "<i>1</i>", "duration_seconds": 5, "items_count": 1, "items": [
        {"sku": "<img src=x>", "title": "<b>bold</b>", "quantity": 1, "row": 0}]}
    files = dp.details(session_summary={"orders": [nasty], "skipped_orders": []},
                       packing_state={})
    bridge.set_details(detail(files=files))
    bridge.set_page("details")
    _settle(qtbot, bridge)
    _js(qtbot, view, "document.querySelector('[data-dorder]').click()")
    assert _count(view, qtbot, "#details img, #details b, #details i") == 0
    assert _eval(qtbot, view,
                 "document.querySelector('#d-rows .app-ditem').firstChild.textContent"
                 ) == "<img src=x><b>bold</b>"
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_sessions_page.py`
Expected: Task 4's tests pass; the new ones fail (`d-id` is not in the document).

- [ ] **Step 3: Fill `#details` in `gui/web/app.html`**

Replace `<div class="app-details" id="details" hidden></div>` with:

```html
  <div class="app-details" id="details" hidden>
    <div class="app-d-top">
      <button type="button" class="btn secondary" id="d-back" data-action="closeDetails" title="Back to Sessions  Alt+Left">
        <svg class="glyph" viewBox="0 0 24 24"><path d="m15 18-6-6 6-6"/></svg>Sessions
      </button>
      <span class="mono app-d-id" id="d-id"></span>
      <span id="d-chip"></span>
      <span class="app-cut app-d-why" id="d-why"></span>
      <button type="button" class="btn secondary" id="d-export" data-action="exportDetails">
        <svg class="glyph" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/><path d="M12 15V3"/></svg>Export Excel
      </button>
    </div>

    <div class="banner danger app-s-banner" id="d-error" hidden>
      <svg class="glyph" viewBox="0 0 24 24"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
      <div class="banner-body">
        <div class="banner-title">The session's files could not be read</div>
        <div class="banner-text"><span class="mono" id="d-error-path"></span> could not be read: <span id="d-error-cause"></span>. Timings, metrics and orders appear once it can be read; the facts below come from the session list.</div>
      </div>
      <button type="button" class="btn secondary" id="d-error-retry" data-action="retryDetails">Retry</button>
    </div>

    <div class="app-d-live" id="d-live" hidden>
      <svg class="glyph" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>
      <span class="app-d-live-text"><span class="app-strong">Still packing on <span id="d-live-pc"></span>.</span> Every number below is so far and refreshes with the list.</span>
      <span class="app-d-live-stamp">Last refreshed <span class="mono" id="d-live-stamp"></span></span>
    </div>

    <section class="card app-d-facts" id="d-facts"></section>

    <div class="app-d-reading" id="d-loading" hidden>Reading the session's files…</div>

    <div class="app-d-ready" id="d-ready" hidden>
      <section class="card strip app-d-cards" id="d-cards"></section>

      <section class="card app-d-metrics">
        <div class="app-d-metrics-title">
          <span class="app-strong">Timing and scan quality</span>
          <span class="strip-note" id="d-metrics-note"></span>
        </div>
        <div class="app-d-groups" id="d-groups"></div>
      </section>

      <section class="card app-d-orders">
        <div class="app-d-bar">
          <span class="app-strong">Orders</span>
          <label class="input app-d-filter">
            <svg class="glyph" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
            <input type="text" id="d-query" placeholder="Filter by order number" autocomplete="off" spellcheck="false">
            <button type="button" class="app-clear" id="d-query-clear" data-action="clearDetailsFilter" title="Clear filter" aria-label="Clear filter" hidden>
              <svg class="glyph" viewBox="0 0 24 24"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
            </button>
          </label>
          <span class="app-secondary" id="d-showing"></span>
          <span class="spacer"></span>
          <button type="button" class="btn secondary" data-action="expandAll">Expand all</button>
          <button type="button" class="btn secondary" data-action="collapseAll">Collapse all</button>
        </div>
        <div class="tbl-head app-d-head">
          <span class="app-head-first">Order / Item</span><span>Duration</span><span>Count</span><span>Started / Scanned</span><span>Completed</span><span>Flags</span>
        </div>
        <div id="d-rows"></div>
        <div class="app-no-match app-d-no-match" id="d-no-match" hidden>
          <svg class="glyph" viewBox="0 0 24 24"><path d="m13.5 8.5-5 5"/><path d="m8.5 8.5 5 5"/><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
          <div class="app-no-match-title">No orders match</div>
          <div class="app-no-match-text">No order number in this session contains “<span class="mono app-no-match-query" id="d-no-match-query"></span>”.</div>
          <button type="button" class="btn secondary" data-action="clearDetailsFilter">Clear filter</button>
        </div>
        <div class="app-d-none" id="d-none" hidden>No orders were recorded for this session.</div>
      </section>
    </div>
  </div>
```

- [ ] **Step 4: Append to `gui/web/app.css`**

```css

/* --- Session details (frames 8a-8f) -------------------------------------- */

/* One scrolling page. The negative margin undoes .app's padding, so the
   scrollbar is at the view's edge. */
.app-details {
  flex: 1;
  min-height: 0;
  margin: -20px -24px;
  padding: 20px 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow: auto;
}
.app-details > * { flex: none; }

.app-d-top { display: flex; align-items: center; gap: 12px; min-width: 0; }
.app-d-top .btn > .glyph { width: 18px; height: 18px; }
.app-d-id {
  padding-left: 4px;
  font-size: var(--type-display-size);
  font-weight: 700;
  white-space: nowrap;
}
.app-d-why {
  flex: 1;
  min-width: 0;
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
}

.app-d-live {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 8px 16px;
  border-radius: var(--kit-radius-card);
  background: var(--status-info-bg);
  color: var(--status-info);
}
.app-d-live > .glyph { width: 20px; height: 20px; }
.app-d-live-text { flex: 1; min-width: 0; }
.app-d-live-stamp { font-size: var(--type-caption-size); white-space: nowrap; }

.app-d-facts { display: grid; grid-template-columns: minmax(0, 1.4fr) repeat(6, minmax(0, 1fr)); }
.app-d-fact {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 20px;
  border-left: 1px solid var(--border);
}
.app-d-fact:first-child { border-left: 0; }
.app-d-fact-label { font-size: var(--type-caption-size); color: var(--text-secondary); }
.app-d-fact-value {
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.app-d-reading { padding: 0 4px; color: var(--text-secondary); }
.app-d-ready { display: flex; flex-direction: column; gap: 16px; }

/* The stat cards: floor.css's strip, with the number first. */
.app-d-cards { grid-template-columns: repeat(5, minmax(0, 1fr)); }
.app-d-cards .strip-cell:last-child { justify-content: flex-start; gap: 2px; }
.app-d-cards .strip-line { white-space: nowrap; }
.app-d-cards .strip-note { min-height: 16px; }

.app-d-metrics { display: flex; flex-direction: column; }
.app-d-metrics-title { display: flex; align-items: baseline; gap: 12px; padding: 12px 20px 0; }
.app-d-groups { display: flex; padding: 8px 0 16px; }
.app-d-group {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px 20px;
  border-left: 1px solid var(--border);
}
.app-d-group:first-child { border-left: 0; }
.app-d-group.n2 { flex: 2 1 0; }
.app-d-group.n3 { flex: 3 1 0; }
.app-d-group.n4 { flex: 4 1 0; }
.app-d-group-title {
  font-size: var(--type-caption-size);
  font-weight: 700;
  color: var(--text-secondary);
}
.app-d-tiles { display: grid; gap: 16px; }
.app-d-group.n2 .app-d-tiles { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.app-d-group.n3 .app-d-tiles { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.app-d-group.n4 .app-d-tiles { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.app-d-tile { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.app-d-tile-value {
  font-size: var(--type-display-size);
  font-weight: 700;
  line-height: 1.2;
  white-space: nowrap;
}
.app-d-tile-label {
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
/* 8c: one sentence where Order time and Item time would be. */
.app-d-notiming {
  flex: 5 1 0;
  min-width: 0;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 8px 20px;
}
.app-d-notiming > .glyph { width: 20px; height: 20px; margin-top: 2px; color: var(--text-secondary); }
.app-d-notiming-text { display: flex; flex-direction: column; gap: 2px; }
.app-d-notiming-note { font-size: var(--type-caption-size); color: var(--text-secondary); }

.app-d-orders {
  --tbl-cols: minmax(0, 1fr) 150px 140px 150px 120px minmax(0, 1.25fr);
  display: flex;
  flex-direction: column;
}
.app-d-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}
.app-d-filter { width: 300px; }
/* The head stays while the page scrolls under it. No ancestor between it and
   .app-details may clip (overflow), or it would stick to that instead. */
.app-d-head { position: sticky; top: 0; z-index: 1; }

.app-dorder {
  width: 100%;
  height: 44px;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
  background: transparent;
  text-align: left;
}
button.app-dorder { cursor: pointer; }
.app-dorder[aria-expanded="true"] { background: var(--surface-raised); }
.app-dorder:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.app-d-nochev { flex: none; width: 20px; }
.app-ditem { min-height: 40px; height: 40px; background: var(--surface-raised); }
.app-ditem-first {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding-left: 30px;
}
.app-ditem-sku { white-space: nowrap; }
.app-ditem-name { color: var(--text-secondary); }
.app-flags { display: flex; gap: 6px; overflow: hidden; }
.app-flag {
  flex: none;
  height: 24px;
  padding: 0 8px;
  border-radius: 12px;
  font-size: var(--type-caption-size);
}
.app-d-no-match { padding: 48px 24px; }
.app-d-none { padding: 24px; text-align: center; color: var(--text-secondary); }
```

- [ ] **Step 5: Edit `gui/web/app.js`**

(a) Insert this section after the Sessions section (before `// --- toast ---`):

```js
// --- Session details ------------------------------------------------------------

const INFO_GLYPH = "M2 12a10 10 0 1 0 20 0 10 10 0 1 0-20 0M12 16v-4M12 8h.01";

function tilesGroup(title, tiles) {
  const group = el("div", "app-d-group n" + tiles.length);
  group.appendChild(el("span", "app-d-group-title", title));
  const grid = el("div", "app-d-tiles");
  tiles.forEach(function (tile) {
    const node = el("div", "app-d-tile");
    node.appendChild(el("span", "app-d-tile-value", tile.value));
    const label = el("span", "app-d-tile-label", tile.label);
    label.title = tile.label;
    node.appendChild(label);
    grid.appendChild(node);
  });
  group.appendChild(grid);
  return group;
}

function noTiming() {
  const node = el("div", "app-d-notiming");
  node.appendChild(glyph(INFO_GLYPH));
  const text = el("div", "app-d-notiming-text");
  text.appendChild(el("span", "app-strong", "Timing metrics are not available for this session."));
  text.appendChild(el("span", "app-d-notiming-note",
    "Its files hold no scan times, so durations and rates cannot be worked out. Counts and flags are complete."));
  node.appendChild(text);
  return node;
}

function flagBadges(flags) {
  const holder = el("span", "app-flags");
  (flags || []).forEach(function (flag) {
    holder.appendChild(el("span", "badge app-flag " + flag.tone, flag.label));
  });
  return holder;
}

function detailOrderRow(order) {
  // A skipped order has nothing to open: it is a row, not a button.
  const opens = order.items.length > 0;
  const open = opens && !!view.dOpen[order.number];
  const row = el(opens ? "button" : "div", "tbl-row app-dorder");
  if (opens) {
    row.type = "button";
    row.dataset.dorder = order.number;
    row.setAttribute("aria-expanded", String(open));
  }
  const first = el("span", "app-order-no");
  first.appendChild(opens ? glyph(open ? CHEVRON_DOWN : CHEVRON_RIGHT) : el("span", "app-d-nochev"));
  first.appendChild(el("span", "app-order-label", order.label));
  row.appendChild(first);
  row.appendChild(el("span", "mono", order.duration));
  row.appendChild(el("span", "", order.count));
  row.appendChild(el("span", "mono", order.started));
  row.appendChild(el("span", "mono", order.completed));
  row.appendChild(flagBadges(order.flags));
  return row;
}

function detailItemRow(item) {
  const row = el("div", "tbl-row app-ditem");
  const first = el("span", "app-ditem-first");
  if (item.sku) first.appendChild(el("span", "mono app-ditem-sku", item.sku));
  first.appendChild(cut("app-ditem-name", item.name));
  row.appendChild(first);
  row.appendChild(el("span", "mono", item.offset));
  row.appendChild(el("span", "mono", item.count));
  row.appendChild(el("span", "mono", item.time));
  row.appendChild(el("span"));
  row.appendChild(flagBadges(item.flags));
  return row;
}

function renderDetailRows() {
  const d = view.bridge.details || {};
  const built = document.createDocumentFragment();
  (d.orders || []).forEach(function (order) {
    built.appendChild(detailOrderRow(order));
    if (view.dOpen[order.number]) {
      order.items.forEach(function (item) { built.appendChild(detailItemRow(item)); });
    }
  });
  els.dRows.replaceChildren(built);
  show(els.dNoMatch, !!d.noMatch);
  els.dNoMatchQuery.textContent = d.needle || "";
  show(els.dNone, d.state === "ready" && !d.total);
}

function toggleDetailOrder(number) {
  view.dOpen[number] = !view.dOpen[number];
  renderDetailRows();
  // The redraw replaced the row: Enter or Space again must reach the new one.
  const row = Array.from(els.dRows.querySelectorAll("[data-dorder]"))
    .find(function (node) { return node.dataset.dorder === number; });
  if (row) row.focus();
}

function renderDetails() {
  const d = view.bridge.details || {};
  const key = d.key || "";
  if (key !== view.detailsKey) {
    // Back from details: the session it showed is the selected row.
    if (!key && view.detailsKey) {
      view.sel = view.detailsKey;
      renderPane();
    }
    view.detailsKey = key;
    view.dOpen = Object.create(null);
    els.details.scrollTop = 0;
  }
  if (!key) return;

  const ready = d.state === "ready";
  els.dId.textContent = d.id || "";
  els.dChip.replaceChildren(chip(d));
  els.dWhy.textContent = d.setBy + " · " + d.why;
  els.dWhy.title = els.dWhy.textContent;
  els.dExport.disabled = !d.canExport;
  els.dExport.title = ready && !d.canExport ? "No order data to export" : "";

  const error = d.error || {};
  show(els.dError, d.state === "error");
  els.dErrorPath.textContent = error.path || "";
  els.dErrorCause.textContent = error.cause || "";
  show(els.dLive, !!d.active && d.state !== "error");
  els.dLivePc.textContent = d.pc || "";
  els.dLiveStamp.textContent = d.stamp || "";

  els.dFacts.replaceChildren.apply(els.dFacts, (d.facts || []).map(function (fact) {
    const cell = el("div", "app-d-fact");
    cell.appendChild(el("span", "app-d-fact-label", fact.label));
    const value = el("span", "app-d-fact-value", fact.value);
    value.title = fact.value;
    cell.appendChild(value);
    return cell;
  }));

  show(els.dLoading, d.state === "loading");
  show(els.dReady, ready);
  if (!ready) return;

  els.dCards.replaceChildren.apply(els.dCards, (d.cards || []).map(function (card) {
    const cell = el("div", "strip-cell");
    const line = el("span", "strip-line");
    line.appendChild(el("span", "strip-value", card.value));
    line.appendChild(el("span", "strip-of", card.of));
    cell.appendChild(line);
    cell.appendChild(el("span", "", card.label));
    cell.appendChild(el("span", "strip-note", card.note));
    return cell;
  }));

  els.dMetricsNote.textContent = d.metricsNote || "";
  const groups = d.timing
    ? (d.groups || []).map(function (group) { return tilesGroup(group.title, group.tiles); })
    : [noTiming()];
  groups.push(tilesGroup("Scan quality", d.scan || []));
  els.dGroups.replaceChildren.apply(els.dGroups, groups);

  setInput(els.dQuery, d.query || "");
  show(els.dQueryClear, !!d.query);
  els.dShowing.textContent = d.showing || "";
  renderDetailRows();
}
```

(b) In `ACTIONS` add:

```js
  closeDetails: function (bridge) { bridge.closeDetails(); },
  retryDetails: function (bridge) { bridge.retryDetails(); },
  exportDetails: function (bridge) { bridge.exportDetails(); },
  clearDetailsFilter: function (bridge) { els.dQuery.value = ""; bridge.setDetailsFilter(""); },
  expandAll: function (bridge) {
    ((bridge.details || {}).orders || []).forEach(function (order) {
      if (order.items.length) view.dOpen[order.number] = true;
    });
    renderDetailRows();
  },
  collapseAll: function () { view.dOpen = Object.create(null); renderDetailRows(); },
```

(c) In `onClick`, before the `const tab = ...` block, add:

```js
  const opened = event.target.closest("[data-dorder]");
  if (opened) {
    toggleDetailOrder(opened.dataset.dorder);
    return;
  }
```

(d) In `IDS`, before the `confirm:` line, add:

```js
  dId: "d-id", dChip: "d-chip", dWhy: "d-why", dExport: "d-export",
  dError: "d-error", dErrorPath: "d-error-path", dErrorCause: "d-error-cause",
  dLive: "d-live", dLivePc: "d-live-pc", dLiveStamp: "d-live-stamp",
  dFacts: "d-facts", dLoading: "d-loading", dReady: "d-ready", dCards: "d-cards",
  dMetricsNote: "d-metrics-note", dGroups: "d-groups", dQuery: "d-query",
  dQueryClear: "d-query-clear", dShowing: "d-showing", dRows: "d-rows",
  dNoMatch: "d-no-match", dNoMatchQuery: "d-no-match-query", dNone: "d-none",
```

(e) In the `QWebChannel` callback, after the `bridge.confirmChanged.connect(renderConfirm);` line, add:

```js
  bridge.detailsChanged.connect(renderDetails);
  renderDetails();
  els.dQuery.addEventListener("input", function () { bridge.setDetailsFilter(els.dQuery.value); });
```

- [ ] **Step 6: Run the page tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_sessions_page.py tests/test_app_bridge.py tests/test_style_literals_guard.py`
Expected: all pass. In `test_8d...` the first assertion list reads each item row's first cell: the SKU and the name with nothing between them.

- [ ] **Step 7: Lint and commit**

Run: `.venv/bin/ruff check . --exclude shared`. Stage `gui/web/app.html`, `gui/web/app.css`, `gui/web/app.js`, `tests/test_app_sessions_page.py`. Message: `feat: the Session details page in the app document`.

---

### Task 6: `SessionsPage`, the controller

**Files:**
- Create: `gui/sessions_page.py`
- Test: `tests/test_sessions_page.py` (new)
- Modify: `tests/test_session_selector_packing_lists.py` (rewritten onto `SessionsPage`)

**Interfaces:**
- Consumes: `AppBridge` and its signals (Task 4); `RegistryRefreshWorker`, `SessionDetailsWorker` (Task 1); `sessions_payload`, `visible_entries`, `default_range`, `refresh_failure`, `row_action`, `session_key`, `takeover_payload`, `details_payload`, `detail_export_rows`, `session_export_rows`, `EXPORT_COLUMNS`, `plural` (Tasks 2, 3); `SessionLockManager.is_locked(Path) -> (bool, dict | None)`, `.is_lock_stale(dict) -> bool`, `.hostname`, `.process_id`; `SessionRegistryManager.profile_manager.get_sessions_root() -> Path`.
- Produces:

```python
class SessionsPage(QObject):
    startRequested = Signal(object)    # {"session_path", "client_id", "packing_list_name", "list_file"}
    resumeRequested = Signal(object)   # {"session_path", "client_id", "packing_list_name", "work_dir",
                                       #  "session_id", "take_over": the stale lock dict or None}
    showPackingRequested = Signal()

    def __init__(self, bridge, registry_manager, lock_manager, *, window=None,
                 is_showing=lambda: True, client_label=lambda: "",
                 toast=lambda message: None, parent=None): ...
    def load_client(self, client_id: str) -> None
    def refresh(self) -> None
    def page_shown(self) -> None
    def set_context(self, open_key: str, server_down: bool) -> None
    def show_entries(self, entries: list) -> None
    def open_details(self, key: str) -> None
    def close_details(self) -> None
    def wait(self, timeout_ms: int = 10000) -> None     # block until the workers are done
    def shutdown(self) -> None                          # stop the timer, wait for the workers
```

`window` is the parent for the file dialogs (a `QWidget` or `None`). `is_showing()` says whether the Sessions pages are on screen. `client_label()` is the command bar's text for the client. `toast(message)` raises a toast.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_sessions_page.py`:

```python
"""SessionsPage: the Sessions pages' controller (spec 2026-10-08 phase 4, 4.5 and 6).

A real AppBridge and real managers; no Chromium. Where a test calls
`_on_refreshed`, `_on_details` or `_on_tick`, that is the slot a worker's or
the timer's signal is connected to: the answer arrives as it would.
"""

import csv
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QFileDialog

from gui.app_bridge import AppBridge
from gui.sessions_page import SessionsPage
from gui.sessions_payload import default_range, session_key
from packing_tool.session_lock_manager import SessionLockManager
from packing_tool.session_registry_manager import SessionRegistryManager


def stamp(**ago) -> str:
    return (datetime.now().astimezone() - timedelta(**ago)).isoformat()


# Worked out once: entries made in one test share a start time, so the page
# lists them in the order they were given.
STARTED = stamp(hours=3)
TOUCHED = stamp(hours=1)


def entry(session_id="2026-10-06_2", status="paused", **over) -> dict:
    base = {
        "session_id": session_id,
        "packing_list_name": "Afternoon_wave",
        "status": status,
        "worker_name": "Maria",
        "pc_name": "WH-PC-02",
        "started_at": STARTED,
        "last_updated": TOUCHED,
        "total_orders": 110,
        "completed_orders": 71,
        "skipped_orders": 2,
        "total_items": 402,
        "work_dir": "",
        "session_path": "/srv/2026-10-06_2",
        "metrics": None,
    }
    base.update(over)
    return base


@pytest.fixture
def made(qapp, profile_manager, server_root):
    (server_root / "Sessions" / "CLIENT_TEST").mkdir(parents=True)
    QSettings("PackingTool", "SessionBrowser").clear()
    bridge = AppBridge()
    bridge.set_page("sessions")
    toasts = []
    showing = {"on": True}
    locks = SessionLockManager(profile_manager)
    page = SessionsPage(
        bridge,
        SessionRegistryManager(profile_manager),
        locks,
        is_showing=lambda: showing["on"],
        client_label=lambda: "Test Client (TEST)",
        toast=toasts.append,
    )
    page.load_client("TEST")
    drain(page, qapp)
    started, resumed, shown = [], [], []
    page.startRequested.connect(started.append)
    page.resumeRequested.connect(resumed.append)
    page.showPackingRequested.connect(lambda: shown.append(1))
    yield SimpleNamespace(page=page, bridge=bridge, toasts=toasts, showing=showing,
                          locks=locks, started=started, resumed=resumed, shown=shown,
                          qapp=qapp)
    page.shutdown()


def drain(page, qapp):
    """Let the workers finish and their queued answers arrive."""
    page.wait()
    qapp.processEvents()
    qapp.processEvents()


def rows(made):
    return made.bridge.sessions["rows"]


def work_dir(tmp_path, name="2026-10-06_2"):
    path = tmp_path / name / "packing" / "Afternoon_wave"
    path.mkdir(parents=True, exist_ok=True)
    return path


def lock(path, *, age_seconds, pc="WH-PC-02", pid=1):
    beat = (datetime.now().astimezone() - timedelta(seconds=age_seconds)).isoformat()
    (path / SessionLockManager.LOCK_FILENAME).write_text(
        json.dumps({"locked_by": pc, "user_name": "georgi", "lock_time": beat,
                    "heartbeat": beat, "process_id": pid, "worker_name": "Georgi"}),
        encoding="utf-8",
    )


# --- loading and refreshing --------------------------------------------------------


def test_loading_a_client_shows_the_loading_state_then_its_sessions(
    qapp, profile_manager, server_root
):
    (server_root / "Sessions" / "CLIENT_TEST").mkdir(parents=True)
    QSettings("PackingTool", "SessionBrowser").clear()
    bridge = AppBridge()
    page = SessionsPage(bridge, SessionRegistryManager(profile_manager),
                        SessionLockManager(profile_manager))
    try:
        page.load_client("TEST")
        assert bridge.sessions["mode"] == "loading"
        assert bridge.sessions["refreshing"] is True
        drain(page, qapp)
        assert bridge.sessions["mode"] == "empty"
        assert bridge.sessions["refreshing"] is False
        assert bridge.sessions["stamp"]
    finally:
        page.shutdown()


def test_show_entries_is_a_finished_refresh(made):
    made.page.show_entries([entry("a"), entry("b", "completed")])
    assert [row["id"] for row in rows(made)] == ["a", "b"]
    assert made.bridge.sessions["mode"] == "ready"


def test_a_refresh_for_another_client_is_dropped(made):
    """Review focus 4."""
    made.page.show_entries([entry("mine")])
    made.page._on_refreshed("OTHER", [entry("theirs")])
    made.page._on_refresh_failed("OTHER", "boom")
    assert [row["id"] for row in rows(made)] == ["mine"]
    assert made.bridge.sessions["failed"] is False


def test_a_failed_refresh_keeps_the_list_and_names_the_folder(made, server_root):
    made.page.show_entries([entry("mine")])
    before = made.bridge.sessions["stamp"]
    made.page._on_refresh_failed("TEST", "the network path was not found")
    sessions = made.bridge.sessions
    assert sessions["failed"] is True
    assert sessions["failure"]["path"] == str(server_root / "Sessions" / "CLIENT_TEST")
    assert sessions["failure"]["cause"] == "the network path was not found"
    assert sessions["failure"]["from"] == before
    assert [row["id"] for row in rows(made)] == ["mine"]
    made.page.show_entries([entry("mine")])
    assert made.bridge.sessions["failed"] is False


class RunningWorker(QObject):
    """A refresh that never ends: what a slow share looks like."""

    refresh_complete = Signal(str, list)
    refresh_failed = Signal(str, str)
    finished = Signal()
    started_for: list = []

    def __init__(self, registry, client_id, parent=None):
        super().__init__(parent)
        RunningWorker.started_for.append(client_id)

    def start(self):
        pass

    def isRunning(self):
        return True

    def wait(self, _timeout_ms=0):
        return True


def test_a_refresh_while_one_runs_for_the_same_client_starts_no_second_worker(
    made, monkeypatch
):
    RunningWorker.started_for = []
    monkeypatch.setattr("gui.sessions_page.RegistryRefreshWorker", RunningWorker)
    made.page.refresh()
    made.page.refresh()
    assert RunningWorker.started_for == ["TEST"]
    made.page.load_client("OTHER")  # another client's sessions are another question
    assert RunningWorker.started_for == ["TEST", "OTHER"]


def test_showing_the_page_refreshes(made, monkeypatch):
    calls = []
    monkeypatch.setattr(made.page, "refresh", lambda: calls.append(1))
    made.page.page_shown()
    assert calls == [1]


def test_the_timer_refreshes_only_while_the_page_is_showing(made, monkeypatch):
    calls = []
    monkeypatch.setattr(made.page, "refresh", lambda: calls.append(1))
    made.showing["on"] = False
    made.page._on_tick()
    assert calls == []
    made.showing["on"] = True
    made.page._on_tick()
    assert calls == [1]
    assert made.page._timer.isActive()


def test_the_switch_is_saved_and_stops_the_timer(made):
    assert made.bridge.sessions["auto"] is True
    made.bridge.setAutoRefresh(False)
    assert made.bridge.sessions["auto"] is False
    assert QSettings("PackingTool", "SessionBrowser").value(
        "auto_refresh_enabled", True, type=bool) is False
    assert not made.page._timer.isActive()
    made.bridge.setAutoRefresh(True)
    assert made.page._timer.isActive()


# --- the filter ----------------------------------------------------------------------


def test_the_filter_slots_change_the_rows(made):
    made.page.show_entries([entry("a"), entry("b", "completed", worker_name="Ivan")])
    start, end = default_range(datetime.now().astimezone())
    made.bridge.setSessionsFilter("finished", "", start, end)
    assert [row["id"] for row in rows(made)] == ["b"]
    made.bridge.setSessionsFilter("all", "maria", start, end)
    assert [row["id"] for row in rows(made)] == ["a"]
    assert made.bridge.sessions["query"] == "maria"


def test_the_default_range_keeps_moving_until_a_date_is_changed(made):
    made.page.show_entries([entry("a")])
    start, end = default_range(datetime.now().astimezone())
    made.bridge.setSessionsFilter("all", "x", start, end)
    assert made.page._dates is None  # still the default: tomorrow it is tomorrow's
    made.bridge.setSessionsFilter("all", "x", "2026-01-01", end)
    assert made.bridge.sessions["dateFrom"] == "2026-01-01"
    made.bridge.setSessionsFilter("all", "x", "", "")
    assert (made.bridge.sessions["dateFrom"], made.bridge.sessions["dateTo"]) == ("", "")


def test_clear_filters_empties_the_search_and_puts_the_dates_back(made):
    made.page.show_entries([entry("a")])
    made.bridge.setSessionsFilter("open", "zzz", "2026-01-01", "2026-01-02")
    assert rows(made) == []
    made.bridge.clearSessionsFilter()
    sessions = made.bridge.sessions
    assert (sessions["tab"], sessions["query"]) == ("open", "")
    assert (sessions["dateFrom"], sessions["dateTo"]) == default_range(datetime.now().astimezone())
    assert [row["id"] for row in rows(made)] == ["a"]


def test_the_context_reaches_the_rows(made):
    made.page.show_entries([entry("a")])
    assert rows(made)[0]["enabled"] is True
    made.page.set_context("x|y", False)
    assert rows(made)[0]["enabled"] is False
    made.page.set_context("", True)
    assert rows(made)[0]["note"].startswith("Server unreachable")


# --- start, resume, take over (section 6) ----------------------------------------------


def test_start_packing_asks_main_window_with_todays_payload(made):
    fresh = entry("n", "not_started", packing_list_path="/srv/n/packing_lists/L.json",
                  session_path="/srv/n")
    made.page.show_entries([fresh])
    made.bridge.sessionAction(session_key(fresh))
    assert made.started == [{
        "session_path": "/srv/n",
        "client_id": "TEST",
        "packing_list_name": "Afternoon_wave",
        "list_file": "/srv/n/packing_lists/L.json",
    }]


def test_resume_asks_main_window_with_todays_payload(made, tmp_path):
    path = work_dir(tmp_path)
    paused = entry(work_dir=str(path))
    made.page.show_entries([paused])
    made.bridge.sessionAction(session_key(paused))
    assert made.resumed == [{
        "session_path": "/srv/2026-10-06_2",
        "client_id": "TEST",
        "packing_list_name": "Afternoon_wave",
        "work_dir": str(path),
        "session_id": "2026-10-06_2",
        "take_over": None,
    }]
    assert made.bridge.confirm == {}


def test_a_disabled_action_does_nothing(made):
    active = entry("a", "in_progress")
    made.page.show_entries([active])
    made.bridge.sessionAction(session_key(active))
    made.bridge.sessionAction("no such key")
    assert made.resumed == [] and made.started == []


def test_the_session_open_here_goes_to_packing(made):
    active = entry("a", "in_progress")
    made.page.show_entries([active])
    made.page.set_context(session_key(active), False)
    made.bridge.sessionAction(session_key(active))
    assert made.shown == [1]
    assert made.resumed == []


def test_a_stale_lock_is_asked_about_before_anything_starts(made, tmp_path):
    path = work_dir(tmp_path)
    lock(path, age_seconds=600)
    stale = entry(status="stale", work_dir=str(path))
    made.page.show_entries([stale])

    made.bridge.sessionAction(session_key(stale))
    assert made.resumed == []
    assert made.bridge.confirm["id"] == "2026-10-06_2"
    assert "WH-PC-02 stopped responding" in made.bridge.confirm["body"]
    assert "while Georgi was packing" in made.bridge.confirm["body"]

    made.bridge.answerTakeOver(False)
    assert made.bridge.confirm == {}
    assert made.resumed == []

    made.bridge.sessionAction(session_key(stale))
    made.bridge.answerTakeOver(True)
    assert made.bridge.confirm == {}
    assert len(made.resumed) == 1
    assert made.resumed[0]["take_over"]["locked_by"] == "WH-PC-02"
    assert made.resumed[0]["work_dir"] == str(path)


def test_an_answer_with_no_question_open_does_nothing(made):
    made.bridge.answerTakeOver(True)
    assert made.resumed == []


def test_a_live_lock_is_left_to_the_start_to_refuse(made, tmp_path):
    """The list was behind: it said Paused, another PC has it. Nothing is asked;
    the start refuses it and frame 3c says who has it."""
    path = work_dir(tmp_path)
    lock(path, age_seconds=5)
    paused = entry(work_dir=str(path))
    made.page.show_entries([paused])
    made.bridge.sessionAction(session_key(paused))
    assert made.bridge.confirm == {}
    assert len(made.resumed) == 1 and made.resumed[0]["take_over"] is None


def test_our_own_lock_is_not_asked_about(made, tmp_path):
    path = work_dir(tmp_path)
    lock(path, age_seconds=600, pc=made.locks.hostname, pid=made.locks.process_id)
    paused = entry(work_dir=str(path))
    made.page.show_entries([paused])
    made.bridge.sessionAction(session_key(paused))
    assert made.bridge.confirm == {}
    assert len(made.resumed) == 1


def test_changing_client_drops_an_open_question(made, tmp_path):
    path = work_dir(tmp_path)
    lock(path, age_seconds=600)
    stale = entry(status="stale", work_dir=str(path))
    made.page.show_entries([stale])
    made.bridge.sessionAction(session_key(stale))
    made.page.load_client("OTHER")
    assert made.bridge.confirm == {}
    made.bridge.answerTakeOver(True)
    assert made.resumed == []
    drain(made.page, made.qapp)


# --- details (section 7) ---------------------------------------------------------------


def summary(path, **over):
    data = {
        "session_id": "2026-10-06_2", "packing_list_name": "Afternoon_wave",
        "total_orders": 3, "completed_orders": 1, "metrics": {},
        "orders": [{"order_number": "#1", "duration_seconds": 30, "items_count": 1,
                    "items": [{"sku": "A", "quantity": 1, "row": 0}]}],
        "skipped_orders": [],
    }
    data.update(over)
    (path / "session_summary.json").write_text(json.dumps(data), encoding="utf-8")


def test_details_show_the_lists_facts_then_the_files(made, tmp_path):
    path = work_dir(tmp_path)
    summary(path)
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionDetails(session_key(done))
    assert made.bridge.page == "details"
    assert made.bridge.details["state"] == "loading"
    assert made.bridge.details["facts"][0] == {"label": "Client", "value": "Test Client (TEST)"}
    drain(made.page, made.qapp)
    assert made.bridge.details["state"] == "ready"
    assert [order["label"] for order in made.bridge.details["orders"]] == ["#1"]


def test_view_details_is_also_a_rows_action(made, tmp_path):
    path = work_dir(tmp_path)
    summary(path)
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionAction(session_key(done))
    assert made.bridge.page == "details"
    drain(made.page, made.qapp)


def test_unreadable_files_are_an_error_and_retry_reads_again(made, tmp_path):
    path = work_dir(tmp_path)
    (path / "session_summary.json").write_text("{", encoding="utf-8")
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionDetails(session_key(done))
    drain(made.page, made.qapp)
    assert made.bridge.details["state"] == "error"
    assert made.bridge.details["error"]["path"].endswith("session_summary.json")

    summary(path)
    made.bridge.retryDetails()
    assert made.bridge.details["state"] == "loading"
    drain(made.page, made.qapp)
    assert made.bridge.details["state"] == "ready"


def test_closing_details_returns_to_the_list(made, tmp_path):
    path = work_dir(tmp_path)
    summary(path)
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionDetails(session_key(done))
    drain(made.page, made.qapp)
    made.bridge.closeDetails()
    assert made.bridge.details == {}
    assert made.bridge.page == "sessions"


def test_details_for_a_closed_session_are_dropped(made, tmp_path):
    """Review focus 4."""
    path = work_dir(tmp_path)
    summary(path)
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionDetails(session_key(done))
    made.bridge.closeDetails()
    drain(made.page, made.qapp)
    assert made.bridge.details == {}
    made.page._on_details("some|other", {"record": {}})
    made.page._on_details_failed("some|other", "/x", "y")
    assert made.bridge.details == {}


def test_details_on_another_page_do_not_pull_the_packer_back(made, tmp_path):
    path = work_dir(tmp_path)
    summary(path)
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionDetails(session_key(done))
    drain(made.page, made.qapp)
    made.bridge.set_page("packing")
    made.bridge.closeDetails()
    assert made.bridge.page == "packing"


def test_the_details_filter_reaches_the_payload(made, tmp_path):
    path = work_dir(tmp_path)
    summary(path)
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionDetails(session_key(done))
    drain(made.page, made.qapp)
    made.bridge.setDetailsFilter("999")
    assert made.bridge.details["noMatch"] is True
    assert made.bridge.details["query"] == "999"


def test_a_refresh_re_reads_an_active_sessions_details_without_a_flash(made, tmp_path):
    path = work_dir(tmp_path)
    state = {"started_at": stamp(hours=1), "progress": {"total_orders": 3},
             "completed": [{"order_number": "#1", "items_count": 1}], "in_progress": {}}
    (path / "packing_state.json").write_text(json.dumps(state), encoding="utf-8")
    active = entry("live", "in_progress", work_dir=str(path))
    made.page.show_entries([active])
    made.bridge.sessionDetails(session_key(active))
    drain(made.page, made.qapp)
    assert made.bridge.details["cards"][0]["value"] == "1"

    state["completed"].append({"order_number": "#2", "items_count": 2})
    (path / "packing_state.json").write_text(json.dumps(state), encoding="utf-8")
    made.page.show_entries([active])
    assert made.bridge.details["state"] == "ready"  # the old numbers stay until the new arrive
    drain(made.page, made.qapp)
    assert made.bridge.details["cards"][0]["value"] == "2"


def test_a_refresh_does_not_re_read_a_finished_sessions_details(made, tmp_path, monkeypatch):
    path = work_dir(tmp_path)
    summary(path)
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionDetails(session_key(done))
    drain(made.page, made.qapp)
    reads = []
    monkeypatch.setattr(made.page, "_load_details", lambda **kwargs: reads.append(kwargs))
    made.page.show_entries([done])
    assert reads == []
    assert made.bridge.details["state"] == "ready"


# --- exports (section 8) ---------------------------------------------------------------


def choose(monkeypatch, path):
    asked = []

    def fake(parent, title, name, filters):
        asked.append((title, name, filters))
        return (str(path) if path else "", "")

    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(fake))
    return asked


def test_csv_export_writes_the_rows_shown(made, tmp_path, monkeypatch):
    made.page.show_entries([entry("a"), entry("b", "completed")])
    start, end = default_range(datetime.now().astimezone())
    made.bridge.setSessionsFilter("finished", "", start, end)
    out = tmp_path / "out.csv"
    asked = choose(monkeypatch, out)
    made.bridge.exportSessions("csv")
    assert asked == [("Save CSV", "sessions_TEST.csv", "CSV files (*.csv)")]
    with open(out, newline="", encoding="utf-8") as handle:
        written = list(csv.reader(handle))
    assert written[0][:3] == ["Status", "Packing List", "Session ID"]
    assert [line[2] for line in written[1:]] == ["b"]
    assert written[1][0] == "completed"
    assert made.toasts == ["Exported 1 session to out.csv"]


def test_excel_export_writes_the_status_word(made, tmp_path, monkeypatch):
    made.page.show_entries([entry("a"), entry("b", "completed")])
    out = tmp_path / "out.xlsx"
    asked = choose(monkeypatch, out)
    made.bridge.exportSessions("xlsx")
    assert asked == [("Save Excel", "sessions_TEST.xlsx", "Excel files (*.xlsx)")]
    frame = pd.read_excel(out)
    assert list(frame["Session ID"]) == ["a", "b"]
    assert list(frame["Status"]) == ["Paused", "Completed"]
    assert made.toasts == ["Exported 2 sessions to out.xlsx"]


def test_a_cancelled_export_writes_nothing(made, monkeypatch):
    made.page.show_entries([entry("a")])
    choose(monkeypatch, None)
    made.bridge.exportSessions("csv")
    assert made.toasts == []


def test_an_export_with_no_rows_does_not_ask_for_a_file(made, monkeypatch):
    asked = choose(monkeypatch, None)
    made.bridge.exportSessions("csv")
    assert asked == []


def test_the_details_export_is_one_row_per_scan(made, tmp_path, monkeypatch):
    path = work_dir(tmp_path)
    summary(path)
    done = entry(status="completed", work_dir=str(path))
    made.page.show_entries([done])
    made.bridge.sessionDetails(session_key(done))
    drain(made.page, made.qapp)
    out = tmp_path / "details.xlsx"
    asked = choose(monkeypatch, out)
    made.bridge.exportDetails()
    assert asked == [("Export Session Details", "session_2026-10-06_2.xlsx", "Excel Files (*.xlsx)")]
    frame = pd.read_excel(out, sheet_name="Session Details")
    assert list(frame["Order Number"]) == ["#1"]
    assert list(frame["SKU"]) == ["A"]
    assert made.toasts == ["Exported 2026-10-06_2 to details.xlsx"]


def test_an_export_that_fails_says_so_in_a_dialog(made, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    made.page.show_entries([entry("a")])
    choose(monkeypatch, tmp_path / "no such folder" / "out.csv")
    boxes = []
    monkeypatch.setattr(QMessageBox, "critical",
                        staticmethod(lambda *args: boxes.append(args[1])))
    made.bridge.exportSessions("csv")
    assert boxes == ["Export Failed"]
    assert made.toasts == []
```

Replace the whole of `tests/test_session_selector_packing_lists.py` with:

```python
"""Regression test: the Sessions page must see packing lists uploaded to the
file server after registry_index.json was already built.

Asserted against the Qt Session Browser until phase 4 of the UI refresh
deleted it; RegistryRefreshWorker does the work either way.
"""
import json

from conftest import make_packing_list

from gui.app_bridge import AppBridge
from gui.sessions_page import SessionsPage
from packing_tool.session_lock_manager import SessionLockManager
from packing_tool.session_registry_manager import SessionRegistryManager


def test_the_sessions_page_sees_a_packing_list_uploaded_after_the_registry_was_built(
    qapp, server_root, profile_manager
):
    client_dir = server_root / "Sessions" / "CLIENT_TEST"
    client_dir.mkdir(parents=True)

    # The registry is built (empty) *before* the packing list exists on disk,
    # as a registry_index.json that predates a fresh Shopify upload would be.
    registry = SessionRegistryManager(profile_manager)
    registry.ensure_registry("TEST")

    session_dir = client_dir / "2026-07-25_1"
    (session_dir / "analysis").mkdir(parents=True)
    (session_dir / "analysis" / "analysis_data.json").write_text(
        json.dumps({"total_orders": 3}), encoding="utf-8"
    )
    (session_dir / "packing_lists").mkdir(parents=True)
    packing_list = make_packing_list(
        [("ORDER-1", "DHL", []), ("ORDER-2", "DHL", []), ("ORDER-3", "DHL", [])]
    )
    (session_dir / "packing_lists" / "ALL_ORDERS.json").write_text(
        json.dumps(packing_list), encoding="utf-8"
    )

    bridge = AppBridge()
    page = SessionsPage(bridge, registry, SessionLockManager(profile_manager))
    try:
        page.load_client("TEST")
        page.wait()
        qapp.processEvents()
        qapp.processEvents()
        # The list was made on a fixed date long ago: no date bound.
        bridge.setSessionsFilter("all", "", "", "")
        names = [row["list"] for row in bridge.sessions["rows"]]
        assert "ALL_ORDERS" in names, (
            f"Expected the freshly-uploaded packing list to appear, got: {names}"
        )
    finally:
        page.shutdown()
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_sessions_page.py tests/test_session_selector_packing_lists.py`
Expected: an import error, `No module named 'gui.sessions_page'`.

- [ ] **Step 3: Write `gui/sessions_page.py`**

```python
"""The Sessions pages' controller (spec 2026-10-08 phase 4, sections 4.5, 6 and 8).

What gui/session_browser/ was, without the widgets: it owns the registry
refresh, the reading of one session's files, the 2-minute timer, the filter
the packer set, the take-over question and the exports, and tells the app
document what to draw through AppBridge. gui/sessions_payload.py decides
every word; gui/web/app.js draws it.
"""

import csv
import logging
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from PySide6.QtCore import QObject, QSettings, QTimer, Signal
from PySide6.QtWidgets import QFileDialog, QMessageBox

from gui.sessions_payload import (
    EXPORT_COLUMNS,
    default_range,
    detail_export_rows,
    details_payload,
    plural,
    refresh_failure,
    row_action,
    session_export_rows,
    session_key,
    sessions_payload,
    takeover_payload,
    visible_entries,
)
from gui.workers import RegistryRefreshWorker, SessionDetailsWorker

logger = logging.getLogger(__name__)

# Cheap with the registry: one file read per client.
AUTO_REFRESH_MS = 120_000


def _now() -> datetime:
    return datetime.now().astimezone()


class SessionsPage(QObject):
    """Drives the Sessions and Session details pages of the app document."""

    startRequested = Signal(object)
    resumeRequested = Signal(object)
    showPackingRequested = Signal()

    def __init__(
        self,
        bridge,
        registry_manager,
        lock_manager,
        *,
        window=None,
        is_showing=lambda: True,
        client_label=lambda: "",
        toast=lambda message: None,
        parent=None,
    ):
        super().__init__(parent)
        self._bridge = bridge
        self._registry = registry_manager
        self._locks = lock_manager
        self._window = window
        self._is_showing = is_showing
        self._client_label = client_label
        self._toast = toast

        self._client_id: str | None = None
        self._entries: list[dict] = []
        self._loaded = False
        self._refreshing = False
        self._stamp = ""
        self._failure: dict | None = None
        self._tab = "all"
        self._query = ""
        # None: the default range, worked out at each push so it moves with
        # the day. A pair once the packer has changed a date.
        self._dates: tuple[str, str] | None = None
        self._open_key = ""
        self._server_down = False
        self._refresh_worker: RegistryRefreshWorker | None = None
        self._refresh_client: str | None = None

        self._detail_key = ""
        self._detail_entry: dict | None = None
        self._details: dict | None = None
        self._detail_error: dict | None = None
        self._detail_query = ""
        self._detail_worker: SessionDetailsWorker | None = None

        # (resume payload, the stale lock) while frame 7c is open.
        self._pending: tuple[dict, dict] | None = None

        self._settings = QSettings("PackingTool", "SessionBrowser")
        self._auto = self._settings.value("auto_refresh_enabled", True, type=bool)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        if self._auto:
            last = self._settings.value("last_refresh_time", 0.0, type=float)
            remaining = max(0, AUTO_REFRESH_MS - int((time.time() - last) * 1000))
            self._timer.start(remaining or AUTO_REFRESH_MS)

        bridge.sessionsFilterChanged.connect(self._on_filter)
        bridge.sessionsFilterCleared.connect(self._on_filter_cleared)
        bridge.refreshSessionsRequested.connect(self.refresh)
        bridge.autoRefreshChanged.connect(self._on_auto)
        bridge.sessionActionRequested.connect(self._on_action)
        bridge.sessionDetailsRequested.connect(self.open_details)
        bridge.exportSessionsRequested.connect(self._export_sessions)
        bridge.closeDetailsRequested.connect(self.close_details)
        bridge.detailsFilterChanged.connect(self._on_details_filter)
        bridge.retryDetailsRequested.connect(lambda: self._load_details())
        bridge.exportDetailsRequested.connect(self._export_details)
        bridge.takeOverAnswered.connect(self._on_take_over)

    # --- what MainWindow calls ------------------------------------------------

    def load_client(self, client_id: str) -> None:
        """Show this client's sessions. The command bar's picker is the only
        client selector, and pushes its changes here."""
        self._client_id = client_id
        self._entries = []
        self._loaded = False
        self._stamp = ""
        self._failure = None
        self._pending = None
        self._bridge.set_confirm({})
        self.close_details()
        self.refresh()

    def refresh(self) -> None:
        """Read the registry on a worker. On a warehouse UNC path a read on
        the UI thread is latency for a page most shifts never open."""
        if not self._client_id:
            return
        worker = self._refresh_worker
        if worker is not None and worker.isRunning() and self._refresh_client == self._client_id:
            return  # that answer is the one being asked for
        self._refreshing = True
        self._push()
        worker = RegistryRefreshWorker(self._registry, self._client_id, parent=self)
        worker.refresh_complete.connect(self._on_refreshed)
        worker.refresh_failed.connect(self._on_refresh_failed)
        worker.finished.connect(self._on_worker_finished)
        self._refresh_worker = worker
        self._refresh_client = self._client_id
        worker.start()

    def page_shown(self) -> None:
        """The Sessions page came on screen: what it shows should be now."""
        self.refresh()

    def set_context(self, open_key: str, server_down: bool) -> None:
        """Which session is open on this PC, and whether the server answers."""
        context = (str(open_key or ""), bool(server_down))
        if context == (self._open_key, self._server_down):
            return
        self._open_key, self._server_down = context
        self._push()
        self._push_details()

    def show_entries(self, entries: list) -> None:
        """Display these entries as a finished refresh would. The refresh's
        own path, and the seam for tests and the render script."""
        self._entries = list(entries)
        self._loaded = True
        self._refreshing = False
        self._failure = None
        self._stamp = _now().strftime("%H:%M:%S")
        self._push()
        if not self._detail_key:
            return
        entry = self._entry(self._detail_key)
        if entry is None:
            return
        self._detail_entry = entry
        if entry.get("status") == "in_progress":
            # Frame 8b: an Active session's numbers refresh with the list.
            self._load_details(keep=True)
        else:
            self._push_details()

    def wait(self, timeout_ms: int = 10000) -> None:
        """Block until the workers are done. Their answers are queued: the
        caller still has to let the event loop run."""
        for worker in (self._refresh_worker, self._detail_worker):
            if worker is not None:
                worker.wait(timeout_ms)

    def shutdown(self) -> None:
        self._timer.stop()
        self.wait()

    # --- the list ---------------------------------------------------------------

    def _entry(self, key: str) -> dict | None:
        return next((e for e in self._entries if session_key(e) == key), None)

    def _push(self) -> None:
        date_from, date_to = self._dates or (None, None)
        self._bridge.set_sessions(
            sessions_payload(
                self._entries,
                tab=self._tab,
                query=self._query,
                date_from=date_from,
                date_to=date_to,
                loaded=self._loaded,
                refreshing=self._refreshing,
                stamp=self._stamp,
                auto=self._auto,
                failure=self._failure,
                open_key=self._open_key,
                server_down=self._server_down,
            )
        )

    def _on_worker_finished(self) -> None:
        # A bound slot, so it runs on this object's thread, after the worker's
        # answer (both are queued, in the order they were emitted).
        worker = self.sender()
        if worker is None:
            return
        if self._refresh_worker is worker:
            self._refresh_worker = None
        if self._detail_worker is worker:
            self._detail_worker = None
        worker.deleteLater()

    def _on_refreshed(self, client_id: str, entries: list) -> None:
        # An answer for a client the packer has already left is dropped.
        if client_id != self._client_id:
            return
        self.show_entries(entries)

    def _on_refresh_failed(self, client_id: str, cause: str) -> None:
        if client_id != self._client_id:
            return
        logger.error("Sessions refresh failed for %s: %s", client_id, cause)
        folder = Path(self._registry.profile_manager.get_sessions_root()) / f"CLIENT_{client_id}"
        self._failure = refresh_failure(folder, cause, _now().strftime("%H:%M:%S"), self._stamp)
        self._loaded = True
        self._refreshing = False
        self._push()

    def _on_filter(self, tab: str, query: str, date_from: str, date_to: str) -> None:
        self._tab = tab
        self._query = query
        # The page sends back the dates it was given. While they are still the
        # default they stay the default, so tomorrow the range is tomorrow's.
        dates = (date_from, date_to)
        self._dates = None if dates == default_range(_now()) else dates
        self._push()

    def _on_filter_cleared(self) -> None:
        self._query = ""
        self._dates = None
        self._push()

    def _on_auto(self, enabled: bool) -> None:
        self._auto = bool(enabled)
        self._settings.setValue("auto_refresh_enabled", self._auto)
        if self._auto:
            self._timer.start(AUTO_REFRESH_MS)
        else:
            self._timer.stop()
        self._push()

    def _on_tick(self) -> None:
        # Not while the page is out of sight: that would put a registry read
        # on the warehouse share in the middle of a scan. The timer stays
        # armed, and the next tick after the page is looked at does the work.
        if self._auto and self._is_showing():
            self.refresh()
            self._settings.setValue("last_refresh_time", time.time())
        self._timer.start(AUTO_REFRESH_MS)

    # --- start, resume, take over -------------------------------------------------

    def _on_action(self, key: str) -> None:
        entry = self._entry(key)
        if entry is None:
            return
        action = row_action(entry, open_key=self._open_key, server_down=self._server_down)
        if not action["enabled"]:
            return
        kind = action["action"]
        if kind == "details":
            self.open_details(key)
        elif kind == "show":
            self.showPackingRequested.emit()
        elif kind == "start":
            self.startRequested.emit({
                "session_path": entry.get("session_path", ""),
                "client_id": self._client_id,
                "packing_list_name": entry.get("packing_list_name", ""),
                "list_file": entry.get("packing_list_path", ""),
            })
        elif kind == "resume":
            info = {
                "session_path": entry.get("session_path", ""),
                "client_id": self._client_id,
                "packing_list_name": entry.get("packing_list_name", ""),
                "work_dir": entry.get("work_dir", ""),
                "session_id": entry.get("session_id", ""),
                "take_over": None,
            }
            stale = self._stale_lock(entry.get("work_dir", ""))
            if stale is not None:
                # Frame 7c: who had it and what comes along, before anything starts.
                self._pending = (info, stale)
                self._bridge.set_confirm(takeover_payload(entry, stale))
                return
            self.resumeRequested.emit(info)

    def _stale_lock(self, work_dir: str) -> dict | None:
        """The lock another process left on this session, if it can be taken.

        A live lock, our own lock and no lock are all None: the start itself
        deals with those.
        """
        if not work_dir:
            return None
        try:
            locked, lock = self._locks.is_locked(Path(work_dir))
        except OSError:
            return None
        if not locked or not lock:
            return None
        ours = (
            lock.get("locked_by") == self._locks.hostname
            and lock.get("process_id") == self._locks.process_id
        )
        if ours or not self._locks.is_lock_stale(lock):
            return None
        return lock

    def _on_take_over(self, yes: bool) -> None:
        pending, self._pending = self._pending, None
        self._bridge.set_confirm({})
        if yes and pending is not None:
            info, stale = pending
            self.resumeRequested.emit({**info, "take_over": stale})

    # --- Session details ------------------------------------------------------------

    def open_details(self, key: str) -> None:
        entry = self._entry(key)
        if entry is None:
            return
        self._detail_key = key
        self._detail_entry = entry
        self._detail_query = ""
        self._load_details()
        if self._bridge.page == "sessions":
            self._bridge.set_page("details")

    def close_details(self) -> None:
        self._detail_key = ""
        self._detail_entry = None
        self._details = None
        self._detail_error = None
        self._bridge.set_details({})
        if self._bridge.page == "details":
            self._bridge.set_page("sessions")

    def _load_details(self, keep: bool = False) -> None:
        """Read the open session's files on a worker. `keep` leaves what is
        shown in place until the new answer lands."""
        if not self._detail_key or self._detail_entry is None:
            return
        if not keep:
            self._details = None
            self._detail_error = None
        self._push_details()
        worker = SessionDetailsWorker(self._detail_key, self._detail_entry, parent=self)
        worker.loaded.connect(self._on_details)
        worker.failed.connect(self._on_details_failed)
        worker.finished.connect(self._on_worker_finished)
        self._detail_worker = worker
        worker.start()

    def _on_details(self, key: str, details: dict) -> None:
        if key != self._detail_key:
            return  # that session's details were closed meanwhile
        self._details = details
        self._detail_error = None
        self._push_details()

    def _on_details_failed(self, key: str, path: str, cause: str) -> None:
        if key != self._detail_key:
            return
        self._details = None
        self._detail_error = {"path": path, "cause": cause}
        self._push_details()

    def _on_details_filter(self, text: str) -> None:
        self._detail_query = text
        self._push_details()

    def _push_details(self) -> None:
        if not self._detail_key or self._detail_entry is None:
            return
        self._bridge.set_details(
            details_payload(
                self._detail_entry,
                self._details,
                client=self._client_label(),
                error=self._detail_error,
                query=self._detail_query,
                stamp=self._stamp,
                open_key=self._open_key,
            )
        )

    # --- exports -----------------------------------------------------------------------

    def _export_sessions(self, fmt: str) -> None:
        now = _now()
        date_from, date_to = self._dates or default_range(now)
        shown, _in_tab, _in_dates = visible_entries(
            self._entries, now=now, tab=self._tab, query=self._query,
            date_from=date_from, date_to=date_to,
        )
        if not shown or not self._client_id:
            return
        excel = fmt == "xlsx"
        path, _selected = QFileDialog.getSaveFileName(
            self._window,
            "Save Excel" if excel else "Save CSV",
            f"sessions_{self._client_id}.{'xlsx' if excel else 'csv'}",
            "Excel files (*.xlsx)" if excel else "CSV files (*.csv)",
        )
        if not path:
            return
        rows = session_export_rows(shown, labels=excel)
        try:
            if excel:
                pd.DataFrame(rows, columns=list(EXPORT_COLUMNS)).to_excel(path, index=False)
            else:
                with open(path, "w", newline="", encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(EXPORT_COLUMNS)
                    writer.writerows(rows)
        except Exception as error:
            logger.exception("Sessions export failed")
            QMessageBox.critical(self._window, "Export Failed", str(error))
            return
        self._toast(
            f"Exported {plural(len(rows), 'session', 'sessions')} to {Path(path).name}"
        )

    def _export_details(self) -> None:
        rows = detail_export_rows(self._details)
        if not rows or self._detail_entry is None:
            return
        session_id = self._detail_entry.get("session_id", "session")
        path, _selected = QFileDialog.getSaveFileName(
            self._window,
            "Export Session Details",
            f"session_{session_id}.xlsx",
            "Excel Files (*.xlsx)",
        )
        if not path:
            return
        try:
            pd.DataFrame(rows).to_excel(path, index=False, sheet_name="Session Details")
        except Exception as error:
            logger.exception("Session details export failed")
            QMessageBox.critical(
                self._window, "Export Failed", f"Failed to export session details:\n{error}"
            )
            return
        self._toast(f"Exported {session_id} to {Path(path).name}")
```

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_sessions_page.py tests/test_session_selector_packing_lists.py`
Expected: all pass. Notes for a failure:
- `QThread: Destroyed while thread is still running` at teardown means a test left a worker running: it needs `drain(...)` before it ends, or `shutdown()` did not wait.
- `test_excel_export...` reads the file back with pandas, which needs `openpyxl`; it is already installed (the Qt export used it).
- `test_details_show_the_lists_facts_then_the_files` asserts `loading` right after the slot: `_load_details` pushes before the worker starts.

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check . --exclude shared`. Stage `gui/sessions_page.py`, `tests/test_sessions_page.py`, `tests/test_session_selector_packing_lists.py`. Message: `feat: SessionsPage, the controller behind the Sessions pages`.

---

### Task 7: `MainWindow` on `SessionsPage`, the take-over lock step, and the deletion

**Files:**
- Modify: `gui/app_pages.py` (whole file), `gui/main_window.py`
- Modify: `tests/conftest.py` (the `main_window` fixture's teardown)
- Create: `tests/test_sessions_mainwindow_seam.py`
- Modify: `tests/test_app_pages.py` (whole file), `tests/test_shell.py`, `tests/test_session_browser_client.py` (whole file), `tests/test_confirmation_methods.py`, `tests/test_app_mainwindow_seam.py`, `tests/test_app_freshness.py`, `tests/audit/test_02_concurrency_sweep.py`, `tests/test_connection_state.py`, `tests/test_packer_logic_scanning.py` (one comment)
- Delete: `gui/session_browser/` (seven files), `packing_tool/session_history_manager.py`, `tests/test_session_detail_page.py`, `tests/test_sessions_list_columns.py`, `tests/test_sessions_list_status.py`, `tests/test_sessions_list_empty.py`

**Interfaces:**
- Consumes: `SessionsPage` and its three signals (Task 6); `session_key` (Task 2); `AppBridge.details`, `.page`, `.set_page`, `.set_details` (Task 4); `SessionLockManager.acquire_lock(client_id, work_dir, worker_id=, worker_name=) -> (ok, message, lock | None)`, `.is_lock_stale(lock)`, `.force_release_lock(work_dir, expected=lock) -> bool` (unchanged, already in the repo).
- Produces:
  - `AppPages(parent=None)`: no `session_browser` argument, no `browser`, no `web_is_current`. `widget(i)` is `view` for every index.
  - `MainWindow.sessions: SessionsPage`. `MainWindow.session_browser` and `MainWindow.session_history_manager` are gone.
  - `MainWindow._acquire_lock(client_id, work_dir, take_over=None) -> tuple[bool, str | None, str | None]`: `(True, None, None)` taken; `(True, None, "<PC>")` taken over from that PC; `(False, sentence, None)` refused. It replaces `_acquire_lock_with_stale_prompt`.
  - `MainWindow.start_shopify_packing_session(..., take_over=None)` and `MainWindow._start_or_resume_from_browser(client_id, packing_list_name, session_path, packing_list_path, work_dir=None, take_over=None)`. The `resumed` argument is gone.
  - `MainWindow._sync_sessions_context()`.

What does not change: `MainWindow._toast`. It already asks `pages.view.isVisible()`, which is now true on Sessions too.

- [ ] **Step 1: Write the failing tests**

(a) Replace the whole of `tests/test_app_pages.py`:

```python
"""AppPages: one web view for every page of the shell (ADR 0003)."""

import pytest

from gui.app_pages import PAGE_BROWSER, PAGE_PACKING, PAGE_STATISTICS, AppPages


@pytest.fixture
def pages(qtbot):
    widget = AppPages()
    qtbot.addWidget(widget)
    return widget


def test_it_has_three_pages_and_starts_on_packing(pages):
    assert pages.count() == 3
    assert pages.currentIndex() == PAGE_PACKING
    assert pages.bridge.page == "packing"


def test_every_index_is_the_same_view(pages):
    for index in (PAGE_PACKING, PAGE_STATISTICS, PAGE_BROWSER):
        assert pages.widget(index) is pages.view
    assert not hasattr(pages, "web_is_current")
    assert not hasattr(pages, "browser")


def test_statistics_is_another_page_of_the_document(pages):
    seen = []
    pages.currentChanged.connect(seen.append)
    pages.setCurrentIndex(PAGE_STATISTICS)
    assert seen == [PAGE_STATISTICS]
    assert pages.bridge.page == "statistics"


def test_sessions_is_a_page_of_the_document(pages):
    seen = []
    pages.currentChanged.connect(seen.append)
    pages.setCurrentIndex(PAGE_BROWSER)
    assert seen == [PAGE_BROWSER]
    assert pages.currentIndex() == PAGE_BROWSER
    assert pages.bridge.page == "sessions"
    pages.setCurrentIndex(PAGE_PACKING)
    assert pages.bridge.page == "packing"


def test_sessions_returns_to_the_details_that_were_open(pages):
    pages.setCurrentIndex(PAGE_BROWSER)
    pages.bridge.set_details({"state": "ready"})
    pages.bridge.set_page("details")
    pages.setCurrentIndex(PAGE_PACKING)
    assert pages.bridge.page == "packing"
    pages.setCurrentIndex(PAGE_BROWSER)
    assert pages.bridge.page == "details"

    pages.setCurrentIndex(PAGE_PACKING)
    pages.bridge.set_details({})
    pages.setCurrentIndex(PAGE_BROWSER)
    assert pages.bridge.page == "sessions"


def test_setting_the_current_index_again_says_nothing(pages):
    seen = []
    pages.currentChanged.connect(seen.append)
    pages.setCurrentIndex(PAGE_PACKING)
    pages.setCurrentIndex(7)
    assert seen == []
    assert pages.currentIndex() == PAGE_PACKING
```

(b) Create `tests/test_sessions_mainwindow_seam.py`:

```python
"""MainWindow and the Sessions pages: the wiring, and the lock step of a start
(spec 2026-10-08 phase 4, sections 6 and 9)."""

import json
from datetime import datetime, timedelta

import pytest
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QMessageBox

from gui.main_window import PAGE_BROWSER, PAGE_PACKING, PAGE_STATISTICS
from packing_tool.session_lock_manager import SessionLockManager

ORDERS = [("#1", "DHL", [{"sku": "A", "quantity": 1, "product_name": "A"}])]
STALE_SENTENCE = (
    "WH-PC-02 stopped responding while this list was open there. "
    "Resume it from Sessions to take it over."
)


def _stamp(**ago) -> str:
    return (datetime.now().astimezone() - timedelta(**ago)).isoformat()


def _lock(work_dir, *, age_seconds, pc="WH-PC-02", pid=1) -> dict:
    beat = _stamp(seconds=age_seconds)
    lock = {"locked_by": pc, "user_name": "georgi", "lock_time": beat, "heartbeat": beat,
            "process_id": pid, "worker_id": None, "worker_name": "Georgi"}
    (work_dir / SessionLockManager.LOCK_FILENAME).write_text(json.dumps(lock), encoding="utf-8")
    return lock


def _owner(work_dir) -> str:
    text = (work_dir / SessionLockManager.LOCK_FILENAME).read_text(encoding="utf-8")
    return json.loads(text)["locked_by"]


def _entry(session_id, status="paused", list_name="Afternoon_wave") -> dict:
    return {
        "session_id": session_id, "packing_list_name": list_name, "status": status,
        "worker_name": "Maria", "pc_name": "WH-PC-02",
        "started_at": _stamp(hours=3), "last_updated": _stamp(hours=1),
        "total_orders": 10, "completed_orders": 4, "skipped_orders": 0, "total_items": 20,
        "work_dir": "", "session_path": f"/srv/{session_id}", "metrics": None,
    }


def _resume_info(session_dir, work_dir, take_over=None) -> dict:
    return {
        "session_path": str(session_dir), "client_id": "TESTCL",
        "packing_list_name": "DHL_Orders", "work_dir": str(work_dir),
        "session_id": session_dir.name, "take_over": take_over,
    }


def _drain(window, qapp):
    """Let the refresh the client picker started finish and its answer land."""
    window.sessions.wait()
    qapp.processEvents()
    qapp.processEvents()


@pytest.fixture
def no_boxes(monkeypatch):
    """Every message box raised, by kind. A test asserts it stayed empty."""
    boxes = []
    for kind in ("information", "warning", "critical", "question"):
        monkeypatch.setattr(
            QMessageBox, kind, lambda *a, _kind=kind, **k: boxes.append(_kind))
    return boxes


@pytest.fixture
def toasts(main_window, monkeypatch):
    seen = []
    monkeypatch.setattr(
        main_window, "_toast", lambda message, role="success": seen.append(message))
    return seen


# --- the wiring (section 9) -------------------------------------------------------


def test_the_browser_widget_and_the_history_manager_are_gone(main_window):
    assert not hasattr(main_window, "session_browser")
    assert not hasattr(main_window, "session_history_manager")
    assert not hasattr(main_window, "_acquire_lock_with_stale_prompt")
    assert main_window.session_tabs.widget(PAGE_BROWSER) is main_window.session_tabs.view


def test_the_sessions_signals_reach_their_handlers(main_window, monkeypatch):
    called = []
    monkeypatch.setattr(main_window, "_handle_start_packing_from_browser",
                        lambda info: called.append(("start", info)))
    monkeypatch.setattr(main_window, "_handle_resume_session_from_browser",
                        lambda info: called.append(("resume", info)))
    main_window.session_tabs.setCurrentIndex(PAGE_STATISTICS)
    main_window.sessions.startRequested.emit({"a": 1})
    main_window.sessions.resumeRequested.emit({"b": 2})
    main_window.sessions.showPackingRequested.emit()
    assert called == [("start", {"a": 1}), ("resume", {"b": 2})]
    assert main_window.session_tabs.currentIndex() == PAGE_PACKING


def test_showing_sessions_refreshes_it(main_window, monkeypatch):
    calls = []
    monkeypatch.setattr(main_window.sessions, "page_shown", lambda: calls.append(1))
    main_window.session_tabs.setCurrentIndex(PAGE_STATISTICS)
    assert calls == []
    main_window.session_tabs.setCurrentIndex(PAGE_BROWSER)
    assert calls == [1]
    assert main_window.session_tabs.bridge.page == "sessions"


def test_the_open_session_and_the_connection_reach_the_rows(main_window_with_list, qapp):
    window = main_window_with_list
    _drain(window, qapp)
    window.sessions.show_entries([
        _entry("2026-01-01_1", "in_progress", "DHL_Orders"),
        _entry("2026-01-02_1"),
    ])

    def rows():
        return {row["id"]: row for row in window.session_tabs.bridge.sessions["rows"]}

    # The fixture's list has no session folder yet: nothing is "open here".
    assert rows()["2026-01-02_1"]["enabled"] is True

    window.current_session_path = "/sessions/2026-01-01_1"
    window._push_pages()
    assert rows()["2026-01-01_1"]["action"] == "show"
    assert rows()["2026-01-02_1"]["enabled"] is False
    assert rows()["2026-01-02_1"]["note"] == (
        "2026-01-01_1 is open on this PC. End it before opening another.")

    window._teardown_session()
    assert rows()["2026-01-02_1"]["enabled"] is True

    window._set_connection_state("down")
    assert rows()["2026-01-02_1"]["note"].startswith("Server unreachable")
    window._set_connection_state("ok")
    assert rows()["2026-01-02_1"]["enabled"] is True


def test_closing_the_window_stops_the_sessions_timer(main_window):
    main_window.closeEvent(QCloseEvent())
    assert not main_window.sessions._timer.isActive()


# --- the lock step (section 6) -------------------------------------------------------


def test_a_free_list_is_locked(main_window, tmp_path):
    work_dir = tmp_path / "L"
    work_dir.mkdir()
    assert main_window._acquire_lock("TESTCL", work_dir) == (True, None, None)
    main_window.lock_manager.release_lock(work_dir)


def test_a_take_over_releases_that_stale_lock_and_takes_it(main_window, tmp_path):
    work_dir = tmp_path / "L"
    work_dir.mkdir()
    stale = _lock(work_dir, age_seconds=600)
    assert main_window._acquire_lock("TESTCL", work_dir, stale) == (True, None, "WH-PC-02")
    assert _owner(work_dir) == main_window.lock_manager.hostname
    main_window.lock_manager.release_lock(work_dir)


def test_a_stale_lock_nobody_was_asked_about_is_not_taken(main_window, tmp_path):
    """The list was behind, or this is a Retry of frame 3c: no question was
    answered, so nothing is released."""
    work_dir = tmp_path / "L"
    work_dir.mkdir()
    _lock(work_dir, age_seconds=600)
    assert main_window._acquire_lock("TESTCL", work_dir) == (False, STALE_SENTENCE, None)
    assert _owner(work_dir) == "WH-PC-02"


def test_a_live_lock_is_refused_with_the_locks_own_message(main_window, tmp_path):
    work_dir = tmp_path / "L"
    work_dir.mkdir()
    live = _lock(work_dir, age_seconds=5)
    ok, message, taken_from = main_window._acquire_lock("TESTCL", work_dir, live)
    assert (ok, taken_from) == (False, None)
    assert "WH-PC-02" in message and message != STALE_SENTENCE
    assert _owner(work_dir) == "WH-PC-02"


def test_a_stale_lock_with_no_take_over_is_frame_3c(main_window, session_factory, no_boxes):
    session_dir, work_dir, _list_path = session_factory(client_id="TESTCL", orders=ORDERS)
    _lock(work_dir, age_seconds=600)
    main_window._handle_resume_session_from_browser(_resume_info(session_dir, work_dir))
    session = main_window.session_tabs.bridge.session
    assert session["state"] == "failed"
    assert session["title"] == "Session could not be opened"
    assert session["text"] == STALE_SENTENCE
    assert _owner(work_dir) == "WH-PC-02"
    assert main_window.logic is None
    assert no_boxes == []


def test_a_take_over_of_a_lock_that_came_back_is_refused(
    main_window, session_factory, no_boxes
):
    """Review focus 5: the question (7c) was about a stale lock; its PC came
    back before the packer answered. Nothing is removed, nothing opens."""
    session_dir, work_dir, _list_path = session_factory(client_id="TESTCL", orders=ORDERS)
    asked_about = _lock(work_dir, age_seconds=600)
    _lock(work_dir, age_seconds=1)
    main_window._handle_resume_session_from_browser(
        _resume_info(session_dir, work_dir, take_over=asked_about))
    session = main_window.session_tabs.bridge.session
    assert session["state"] == "failed"
    assert session["title"] == "Session could not be opened"
    assert "WH-PC-02" in session["text"]
    assert _owner(work_dir) == "WH-PC-02"
    assert main_window.logic is None
    assert main_window.session_tabs.currentIndex() == PAGE_PACKING
    assert no_boxes == []


# --- a whole start: toasts, no message boxes ------------------------------------------


def test_a_resume_with_a_take_over_opens_the_session_and_says_so(
    main_window, session_factory, no_boxes, toasts
):
    session_dir, work_dir, _list_path = session_factory(client_id="TESTCL", orders=ORDERS)
    stale = _lock(work_dir, age_seconds=600)
    try:
        main_window._handle_resume_session_from_browser(
            _resume_info(session_dir, work_dir, take_over=stale))
        assert main_window.session_tabs.bridge.session["state"] == "open"
        assert _owner(work_dir) == main_window.lock_manager.hostname
        assert toasts[0] == f"Took over {session_dir.name} from WH-PC-02."
        assert no_boxes == []
        assert main_window.session_tabs.currentIndex() == PAGE_PACKING
    finally:
        main_window._teardown_session()


def test_a_start_says_it_loaded_in_a_toast_and_no_box(
    main_window, session_factory, no_boxes, toasts
):
    session_dir, _work_dir, list_path = session_factory(client_id="TESTCL", orders=ORDERS)
    try:
        main_window._handle_start_packing_from_browser({
            "session_path": str(session_dir), "client_id": "TESTCL",
            "packing_list_name": "DHL_Orders", "list_file": str(list_path),
        })
        assert main_window.session_tabs.bridge.session["state"] == "open"
        assert toasts[0] == "Loaded 1 orders from DHL_Orders."
        assert no_boxes == []
    finally:
        main_window._teardown_session()


def test_a_start_with_a_session_open_is_a_toast(
    main_window_with_list, no_boxes, toasts, monkeypatch, tmp_path
):
    window = main_window_with_list
    window.current_session_path = "/sessions/2026-01-01_1"
    started = []
    monkeypatch.setattr(window, "start_shopify_packing_session",
                        lambda **kwargs: started.append(kwargs) or False)
    window._start_or_resume_from_browser(
        "TESTCL", "B", tmp_path, tmp_path / "B.json", work_dir=tmp_path / "B")
    assert started == []
    assert toasts == ["2026-01-01_1 is open. End it before opening another."]
    assert no_boxes == []
```

(c) `tests/test_app_freshness.py`. Replace the import block's first lines with:

```python
import json
from datetime import datetime, timedelta

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from gui.main_window import PAGE_BROWSER, PAGE_PACKING, PAGE_STATISTICS
from gui.sessions_payload import session_key
```

Replace `test_a_page_shown_after_being_hidden_holds_the_current_session_only` (the parametrized test, decorator included) with:

```python
def _cover(window):
    """Packer Mode's widget over the shell: since phase 4 the one thing that
    hides the view (spec phase 4, section 10)."""
    window.stacked_widget.setCurrentWidget(window.packer_mode_widget)


def _uncover(window):
    window.stacked_widget.setCurrentWidget(window.session_widget)


@pytest.mark.parametrize("page, a_text, b_text", [
    (PAGE_PACKING, "#A-1001", "#B-2002"),
    (PAGE_STATISTICS, "SKU-AAA", "SKU-BBB"),
])
def test_a_page_shown_after_being_hidden_holds_the_current_session_only(
    shown, qtbot, session_factory, packer_logic_factory, page, a_text, b_text
):
    window = shown
    pages = window.session_tabs
    view, bridge = pages.view, pages.bridge
    pages.setCurrentIndex(page)
    _open(window, _logic(session_factory, packer_logic_factory, "2026-01-01_1", "A-1001", "SKU-AAA"),
          "2026-01-01_1")
    _settle(qtbot, bridge)
    assert a_text in _eval(qtbot, view, "document.body.textContent")

    _cover(window)                               # the view is hidden
    _open(window, _logic(session_factory, packer_logic_factory, "2026-01-02_1", "B-2002", "SKU-BBB"),
          "2026-01-02_1")                        # session B replaces A underneath
    pushed = bridge.revision

    _uncover(window)                             # shown again
    _settle(qtbot, bridge)
    assert bridge.painted_revision >= pushed
    text = _eval(qtbot, view, "document.body.textContent")
    assert b_text in text
    assert a_text not in text


def _stamp(**ago) -> str:
    return (datetime.now().astimezone() - timedelta(**ago)).isoformat()


def _session(session_id, work_dir="") -> dict:
    return {
        "session_id": session_id, "packing_list_name": "DHL_Orders", "status": "completed",
        "worker_name": "Maria", "pc_name": "WH-PC-02",
        "started_at": _stamp(hours=3), "last_updated": _stamp(hours=1),
        "total_orders": 1, "completed_orders": 1, "skipped_orders": 0, "total_items": 1,
        "work_dir": str(work_dir), "session_path": f"/srv/{session_id}", "metrics": None,
    }


def _files(tmp_path, session_id, order):
    work_dir = tmp_path / session_id / "packing" / "DHL_Orders"
    work_dir.mkdir(parents=True)
    summary = {
        "session_id": session_id, "packing_list_name": "DHL_Orders",
        "total_orders": 1, "completed_orders": 1, "metrics": {},
        "orders": [{"order_number": order, "duration_seconds": 30, "items_count": 1,
                    "items": [{"sku": "A", "quantity": 1, "row": 0}]}],
        "skipped_orders": [],
    }
    (work_dir / "session_summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return work_dir


@pytest.fixture
def sessions(shown, qapp, monkeypatch):
    """The window's Sessions controller on its page, with the registry out of
    the way: what it shows is what the test gives it."""
    page = shown.sessions
    page.wait()
    qapp.processEvents()
    qapp.processEvents()
    monkeypatch.setattr(page, "refresh", lambda: None)
    shown.session_tabs.setCurrentIndex(PAGE_BROWSER)
    return page


def test_sessions_shown_after_being_hidden_holds_the_current_list_only(shown, sessions, qtbot):
    view, bridge = shown.session_tabs.view, shown.session_tabs.bridge
    sessions.show_entries([_session("AAA-111")])
    _settle(qtbot, bridge)
    assert "AAA-111" in _eval(qtbot, view, "document.getElementById('sessions').textContent")

    _cover(shown)
    sessions.show_entries([_session("BBB-222")])
    pushed = bridge.revision

    _uncover(shown)
    _settle(qtbot, bridge)
    assert bridge.painted_revision >= pushed
    text = _eval(qtbot, view, "document.getElementById('sessions').textContent")
    assert "BBB-222" in text
    assert "AAA-111" not in text


def test_details_shown_after_being_hidden_hold_the_current_session_only(
    shown, sessions, qtbot, tmp_path
):
    view, bridge = shown.session_tabs.view, shown.session_tabs.bridge
    a = _session("AAA-111", _files(tmp_path, "AAA-111", "#A-1001"))
    b = _session("BBB-222", _files(tmp_path, "BBB-222", "#B-2002"))
    sessions.show_entries([a, b])

    def open_details(entry):
        sessions.open_details(session_key(entry))
        qtbot.waitUntil(lambda: bridge.details.get("state") == "ready", timeout=10000)

    open_details(a)
    assert bridge.page == "details"
    _settle(qtbot, bridge)
    assert "A-1001" in _eval(qtbot, view, "document.getElementById('details').textContent")

    _cover(shown)
    open_details(b)
    pushed = bridge.revision

    _uncover(shown)
    _settle(qtbot, bridge)
    assert bridge.painted_revision >= pushed
    text = _eval(qtbot, view, "document.getElementById('details').textContent")
    assert "B-2002" in text
    assert "A-1001" not in text
    assert _eval(qtbot, view, "document.getElementById('d-id').textContent") == "BBB-222"
```

The file's other tests (`test_start_packing_waits_…`, `test_a_session_ended_inside_packer_mode_…`, `test_the_shortcuts_still_work_…`) stay as they are.

(d) `tests/test_shell.py`:
- Delete the line `from gui.session_browser.session_browser_widget import SessionBrowserWidget`.
- In the `window` fixture, before `mw.deleteLater()`, add `mw.sessions.shutdown()`.
- Replace `test_session_browser_is_a_page_not_a_dialog` with:

```python
def test_sessions_is_a_page_of_the_document(window):
    assert window.session_tabs.widget(PAGE_BROWSER) is window.session_tabs.view
    assert not hasattr(window, "session_browser")
```

- In `test_open_session_browser_navigates_instead_of_opening_a_dialog` add a last line: `assert window.session_tabs.bridge.page == "sessions"`.
- Replace `test_the_browsers_signals_are_still_wired_to_main_window` with:

```python
def test_the_sessions_signals_are_wired_to_main_window(window):
    for name in ("startRequested", "resumeRequested", "showPackingRequested"):
        assert _is_connected(window.sessions, name)
```

- Replace `test_auto_refresh_is_quiet_while_the_browser_page_is_not_shown` with:

```python
def test_auto_refresh_is_quiet_while_sessions_is_not_shown(window, monkeypatch):
    """A permanent page must not put a registry read on the warehouse share
    while the packer is on another page."""
    refreshes = []
    monkeypatch.setattr(window.sessions, "refresh", lambda: refreshes.append(1))
    window.session_tabs.setCurrentIndex(PAGE_PACKING)
    window.sessions._on_tick()
    assert refreshes == []
    assert window.sessions._timer.isActive()  # still armed for the next visit
```

(e) Replace the whole of `tests/test_session_browser_client.py`:

```python
"""The command bar's client picker is the Sessions page's client picker.

The Qt browser once carried a second, independent one down its left side, so
the shell could be on one client while the browser showed another.
"""


def test_changing_the_client_in_the_command_bar_loads_it_in_sessions(main_window):
    # Start on whichever client isn't the target, so the switch below is a
    # real change and actually fires currentIndexChanged.
    other_index = main_window.client_combo.findData("OTHERCL")
    main_window.client_combo.setCurrentIndex(other_index)

    loaded = []
    main_window.sessions.load_client = loaded.append

    index = main_window.client_combo.findData("TESTCL")
    main_window.client_combo.setCurrentIndex(index)

    assert loaded == ["TESTCL"]
```

(f) `tests/test_confirmation_methods.py`: delete the import of `OrdersTab` and the two tests that build one (`test_each_item_row_names_how_it_was_packed`, `test_the_order_row_flags_both_manual_kinds`); their ports are in `tests/test_session_details_payload.py` (Task 3). Keep `_order()` and `test_manual_confirms_count_confirm_and_force_units`. Replace the docstring with:

```python
"""Confirm clicks ("manual") and Force ("force_confirmed") are not scans.

The metric once knew only manual, so Force was never counted. How Session
details names each kind is in tests/test_session_details_payload.py.
"""
```

(g) `tests/test_app_mainwindow_seam.py`:
- In `test_a_toast_goes_to_the_page_when_it_is_showing`, the last assertion becomes `assert raised == ["Saved.", "On Sessions."]` (Sessions is the same view now).
- In `test_a_start_cannot_be_entered_while_one_is_running`, rename both `_acquire_lock_with_stale_prompt` to `_acquire_lock`.
- In `test_retry_starts_again_with_the_same_arguments`, the call loses `resumed=True`:

```python
    main_window._start_or_resume_from_browser(
        "TESTCL", "DHL_Orders", tmp_path, tmp_path / "DHL_Orders.json",
        work_dir=tmp_path,
    )
```

(h) `tests/audit/test_02_concurrency_sweep.py`. Replace `test_force_release_after_the_prompt_does_not_steal_a_fresh_lock` with:

```python
def test_a_take_over_does_not_steal_a_lock_that_changed_meanwhile(main_window, tmp_path):
    work_dir = tmp_path / "L"
    work_dir.mkdir()
    _lock(work_dir, "PC-OLD", age_seconds=600)  # stale: its PC crashed
    lock_file = work_dir / SessionLockManager.LOCK_FILENAME
    asked_about = json.loads(lock_file.read_text(encoding="utf-8"))

    # The question sat open; meanwhile PC-2 took the list over, then went quiet
    # itself. The answer was about PC-OLD's lock, not this one.
    _lock(work_dir, "PC-2", age_seconds=300, pid=2)
    ok, _message, taken_from = main_window._acquire_lock("M", work_dir, take_over=asked_about)

    assert (ok, taken_from, _lock_owner(work_dir)) == (False, None, "PC-2")
```

In `test_opening_a_second_list_is_refused_while_one_is_packing` delete the line `monkeypatch.setattr("gui.main_window.QMessageBox.warning", lambda *a, **k: None)`: the refusal is a toast now.

(i) `tests/test_connection_state.py`: in `test_starting_from_sessions_is_refused_while_down` delete the line `monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)`. If `QMessageBox` is then unused in the file, delete its import (ruff says).

(j) `tests/test_packer_logic_scanning.py`, the comment near line 302: change `session_browser/orders_tab.py._load_orders() rendered it` to `Session details listed it`.

(k) `tests/conftest.py`, the `main_window` fixture's end:

```python
    window = MainWindow(config_path=str(config_ini))
    yield window
    # The client picker started a registry read on a QThread: let it end
    # before the window goes.
    window.sessions.shutdown()
    window.deleteLater()
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_pages.py tests/test_sessions_mainwindow_seam.py`
Expected: `test_app_pages.py` fails with `TypeError: AppPages.__init__() missing 1 required positional argument: 'session_browser'`; `test_sessions_mainwindow_seam.py` errors in the fixture with `AttributeError: 'MainWindow' object has no attribute 'sessions'`.

- [ ] **Step 3: `gui/app_pages.py`**

Replace the whole file:

```python
"""The shell's pages: one web view (ADR 0003).

Packing, Statistics, Sessions and Session details are pages of one document
in one QWebEngineView. This widget speaks the part of QTabWidget MainWindow's
call sites already use, so they kept `session_tabs` and did not change.
"""

from PySide6.QtCore import Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from gui.app_bridge import mount_app_page

PAGE_PACKING, PAGE_STATISTICS, PAGE_BROWSER = range(3)


class AppPages(QWidget):
    currentChanged = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.view = QWebEngineView(self)
        self.bridge = mount_app_page(self.view)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)
        self._index = PAGE_PACKING

    def count(self) -> int:
        return 3

    def currentIndex(self) -> int:
        return self._index

    def widget(self, index: int) -> QWidget:
        return self.view

    def _page_name(self, index: int) -> str:
        """The bridge's name for the page an index shows."""
        if index == PAGE_BROWSER:
            # Details left for another page are the details come back to.
            return "details" if self.bridge.details else "sessions"
        return "statistics" if index == PAGE_STATISTICS else "packing"

    def setCurrentIndex(self, index: int) -> None:
        if index == self._index or index not in (PAGE_PACKING, PAGE_STATISTICS, PAGE_BROWSER):
            return
        self._index = index
        self.bridge.set_page(self._page_name(index))
        self.currentChanged.emit(index)
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_pages.py`
Expected: 6 passed.

- [ ] **Step 4: `gui/main_window.py`**

Make these edits in order. Line numbers are from before this task and drift as you go: find each by its text.

(a) Imports. Delete:

```python
from gui.session_browser.session_browser_widget import SessionBrowserWidget
```
```python
from packing_tool.session_history_manager import SessionHistoryManager
```

Add, in alphabetical place (after `from gui.packer_mode_widget import PackerModeWidget`):

```python
from gui.sessions_page import SessionsPage
from gui.sessions_payload import session_key
```

(b) `__init__`. Delete these three lines:

```python
        # Initialize SessionHistoryManager
        self.session_history_manager = SessionHistoryManager(self.profile_manager)
        logger.info("SessionHistoryManager initialized successfully")
```

(c) `_init_ui`. Replace everything from the comment `# The Session Browser — a destination now, not a dialog.` down to and including

```python
        if self.current_client_id:
            self.session_browser.load_client(self.current_client_id)
```

with:

```python
        # Packing, Statistics, Sessions and Session details are one web
        # document (ADR 0003). AppPages speaks the QTabWidget calls the code
        # below already makes.
        self.session_tabs = AppPages()
        pages = self.session_tabs.bridge
        pages.openSessionRequested.connect(lambda: self.open_session_browser())
        pages.startPackingRequested.connect(lambda: self.switch_to_packer_mode())
        pages.endSessionRequested.connect(lambda: self.end_session())
        pages.clearFilterRequested.connect(lambda: self.search_input.clear())
        pages.chooseClientRequested.connect(lambda: self.client_combo.showPopup())
        pages.pageRequested.connect(self._show_named_page)
        pages.retryStartRequested.connect(lambda: self._retry_start())
        pages.closeFailureRequested.connect(lambda: self._close_failure())

        # The Sessions pages' controller: the registry refresh, the take-over
        # question and the exports. Lambdas, so a test (or a subclass) that
        # replaces a handler is seen. on_client_changed gives it its client.
        self.sessions = SessionsPage(
            pages,
            self.registry_manager,
            self.lock_manager,
            window=self,
            is_showing=lambda: (
                self._shell_showing()
                and self.session_tabs.currentIndex() == PAGE_BROWSER
            ),
            client_label=lambda: self.client_combo.currentText(),
            toast=lambda message: self._toast(message),
            parent=self,
        )
        self.sessions.startRequested.connect(
            lambda info: self._handle_start_packing_from_browser(info)
        )
        self.sessions.resumeRequested.connect(
            lambda info: self._handle_resume_session_from_browser(info)
        )
        self.sessions.showPackingRequested.connect(
            lambda: self.session_tabs.setCurrentIndex(PAGE_PACKING)
        )
```

(The deleted `if self.current_client_id:` block was dead: `_init_ui()` runs before `load_available_clients()`.)

(d) `_init_ui`, after

```python
        self.session_tabs.currentChanged.connect(
            lambda index: self.command_bar.set_page(PAGES[index])
        )
```

add:

```python
        self.session_tabs.currentChanged.connect(lambda index: self._on_page_changed(index))
```

and add this method after `_show_named_page`:

```python
    def _on_page_changed(self, index: int):
        if index == PAGE_BROWSER:
            # What Sessions shows should be now, not when it was last looked at.
            self.sessions.page_shown()
```

(e) `_push_pages`. Both exits tell Sessions what is open here. The `logic is None` branch becomes:

```python
        if logic is None:
            bridge.set_packing({})
            bridge.set_statistics({})
            self.command_bar.set_complete(False)
            self._sync_sessions_context()
            return
```

and add `self._sync_sessions_context()` as the method's last line, after `self.packer_mode_button.setEnabled(not complete)`.

(f) `_sync_client_state`. Only the comment changes:

```python
        if not chosen:
            # Every page draws "Choose a client"; Packing is the one to be on.
            self.session_tabs.setCurrentIndex(PAGE_PACKING)
```

(g) `_sync_shell`. Add a last line and a new method after it:

```python
    def _sync_shell(self):
        self.session_tabs.bridge.set_shell(
            client=bool(self.current_client_id),
            # With none, the selector's one item is "(No clients available)",
            # whose data is None. Not isEnabled(): an open session disables it.
            clients=self.client_combo.itemData(0) is not None,
            server_down=self._connection_state == "down",
        )
        self._sync_sessions_context()

    def _sync_sessions_context(self):
        """Tell Sessions which session is open on this PC and whether the
        server answers: both decide what a row's action is (section 5.5)."""
        open_key = ""
        if self.logic is not None and self.current_session_path:
            open_key = session_key({
                "session_id": Path(self.current_session_path).name,
                "packing_list_name": self.current_packing_list or "",
            })
        self.sessions.set_context(open_key, self._connection_state == "down")
```

(h) `on_client_changed`. Replace

```python
        # The browser has no picker of its own (Bundle 6): the command bar's
        # is the only one, so it has to push the change.
        if hasattr(self, "session_browser"):
            self.session_browser.load_client(client_id)
```

with

```python
        # Sessions has no picker of its own (Bundle 6): the command bar's is
        # the only one, so it has to push the change.
        self.sessions.load_client(client_id)
```

(i) `closeEvent`. Replace the whole block that starts `# 5. Stop auto-refresh timer in Session Browser if open` (it tests `hasattr(self, "session_browser_dialog")`, which nothing has set for a long time) with:

```python
            # 5. Stop the Sessions timer and let its workers end
            try:
                self.sessions.shutdown()
            except Exception as e:
                logger.warning(f"Failed to stop the Sessions page: {e}")
```

(j) `start_shopify_packing_session`. The signature gains a last argument, and the docstring's `Args:` a line:

```python
        packing_list_name: str,
        take_over: dict | None = None,
    ) -> bool:
```
```
            take_over: The stale lock the packer agreed to take over (frame 7c), or None
```

Step 3 of its body, from `# 3. Acquire lock on work directory (with stale lock handling)` to `raise RuntimeError(error_msg)`, becomes:

```python
            # 3. Acquire the lock on the work directory
            success, error_msg, taken_from = self._acquire_lock(
                client_id, work_dir, take_over
            )
            if not success:
                raise RuntimeError(error_msg)
```

Step 11's first toast, `self._toast(f"Loaded {order_count} orders from {packing_list_name}.")`, becomes:

```python
            if taken_from:
                self._toast(f"Took over {session_path.name} from {taken_from}.")
            else:
                self._toast(f"Loaded {order_count} orders from {packing_list_name}.")
```

(k) `_start_or_resume_from_browser`. Replace the whole method with:

```python
    def _start_or_resume_from_browser(
        self,
        client_id,
        packing_list_name,
        session_path,
        packing_list_path,
        work_dir=None,
        take_over=None,
    ):
        """
        Shared logic for Sessions' "Resume session" and "Start packing".

        If work_dir is None, one is created via SessionManager.get_packing_work_dir()
        (the "start packing" case); otherwise the existing work_dir is reused (resume).
        take_over is the stale lock the packer agreed to take over, or None.
        """
        if self._starting:
            return
        if self._connection_state == "down":
            self._toast(
                "Server unreachable. Sessions cannot be opened until it answers.",
                role="info",
            )
            return

        # One list at a time. is_active() covers only the legacy Excel path;
        # an open Shopify list is self.logic (AUDIT-02-2). The row's action is
        # disabled while one is open, so this is for a start that still arrives.
        if self.logic is not None or (
            self.session_manager and self.session_manager.is_active()
        ):
            logger.warning(
                "Attempted to start/resume packing while a session is already active"
            )
            open_id = (
                Path(self.current_session_path).name
                if self.current_session_path
                else "A session"
            )
            self._toast(f"{open_id} is open. End it before opening another.", role="info")
            return

        self._last_start = {
            "client_id": client_id,
            "packing_list_name": packing_list_name,
            "session_path": session_path,
            "packing_list_path": packing_list_path,
            "work_dir": work_dir,
            "take_over": take_over,
        }

        # The work happens on the Packing page: that is where the opening
        # steps (3b), a failure (3c) and the open list are drawn.
        self.session_tabs.setCurrentIndex(PAGE_PACKING)

        # Set current client if different
        if self.current_client_id != client_id:
            for i in range(self.client_combo.count()):
                if self.client_combo.itemData(i) == client_id:
                    self.client_combo.setCurrentIndex(i)
                    break

        # Create SessionManager for this client if not exists
        if not self.session_manager or self.session_manager.client_id != client_id:
            self.session_manager = SessionManager(
                client_id=client_id,
                profile_manager=self.profile_manager,
                lock_manager=self.lock_manager,
                worker_id=self.current_worker_id,
                worker_name=self.current_worker_name,
            )

        if work_dir is None:
            try:
                work_dir = self.session_manager.get_packing_work_dir(
                    session_path=str(session_path), packing_list_name=packing_list_name
                )
            except OSError as e:
                # The usual way a packer first meets an outage: the work
                # folder cannot be made on a share that has gone away.
                logger.exception("Could not create the packing work directory")
                self._show_start_failure(
                    "Session could not be opened",
                    f"The work folder for {packing_list_name} could not be made: {e}.",
                    packing_list_name,
                )
                self.check_connection()
                return
            logger.info(f"Work directory created: {work_dir}")

        # The start's own toast says what loaded; a failure is frame 3c.
        self.start_shopify_packing_session(
            packing_list_path=packing_list_path,
            work_dir=work_dir,
            session_path=session_path,
            client_id=client_id,
            packing_list_name=packing_list_name,
            take_over=take_over,
        )
```

(l) The two handlers. In `_handle_resume_session_from_browser` the docstring's `Args:` line becomes `session_info: Dict with session_path, client_id, packing_list_name, work_dir, session_id, take_over` and the call becomes:

```python
        self._start_or_resume_from_browser(
            client_id,
            packing_list_name,
            session_path,
            packing_list_path,
            work_dir=work_dir,
            take_over=session_info.get("take_over"),
        )
```

In `_handle_start_packing_from_browser` the call becomes:

```python
        self._start_or_resume_from_browser(
            client_id,
            packing_list_name,
            session_path,
            packing_list_path,
        )
```

(m) Replace the whole of `_acquire_lock_with_stale_prompt` with:

```python
    def _acquire_lock(self, client_id: str, work_dir: Path, take_over: dict | None = None):
        """
        Take the session lock; take over a stale one only when the packer agreed to.

        take_over is the stale lock frame 7c asked about. It is released only
        if it is still that lock and still stale (AUDIT-02-1): while the
        question was open its PC may have come back, or another PC taken it.

        Returns:
            (True, None, None) when the lock was free.
            (True, None, "<PC>") when it was taken over from that PC.
            (False, sentence, None) when it was refused; the sentence is frame 3c's.
        """

        def acquire():
            return self.lock_manager.acquire_lock(
                client_id,
                work_dir,
                worker_id=self.current_worker_id,
                worker_name=self.current_worker_name,
            )

        def stale(lock) -> bool:
            return bool(lock) and self.lock_manager.is_lock_stale(lock)

        success, error_msg, lock = acquire()
        taken_from = None
        if not success and take_over is not None and stale(lock):
            if self.lock_manager.force_release_lock(work_dir, expected=take_over):
                taken_from = take_over.get("locked_by") or "another PC"
            success, error_msg, lock = acquire()
        if success:
            return True, None, taken_from
        if stale(lock):
            # Nobody was asked about this lock: the list was behind, this is a
            # Retry of 3c, or the lock changed while the question was open.
            pc = lock.get("locked_by") or "Another PC"
            return (
                False,
                f"{pc} stopped responding while this list was open there. "
                "Resume it from Sessions to take it over.",
                None,
            )
        return False, error_msg, None
```

(n) `open_session_browser`: the docstring becomes

```python
        """Show the Sessions page.

        The one place that navigation happens: the command bar's Open session
        and the document's own button both come here.
        """
```

and its log line `logger.info("Showing the Sessions page")`.

- [ ] **Step 5: Delete the Qt package and what only served it**

One git command per Bash call:

```
/usr/bin/git rm -r gui/session_browser
/usr/bin/git rm packing_tool/session_history_manager.py
/usr/bin/git rm tests/test_session_detail_page.py tests/test_sessions_list_columns.py tests/test_sessions_list_status.py tests/test_sessions_list_empty.py
```

Then check nothing still names them:

Run: `grep -rn "session_browser\b\|session_history_manager\|SessionHistoryManager\|SessionBrowserWidget\|web_is_current\|_acquire_lock_with_stale_prompt" --include=*.py gui packing_tool tests scripts main.py run_dev.py`
Expected: no line that imports or calls any of them. `open_session_browser` (the method) and `test_session_browser_client.py` (the file name) are fine. If `gui/workers.py` or another module still imports from `gui.session_browser`, Task 1 or 6 missed a move: fix the import there.

- [ ] **Step 6: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: all pass. Notes for a failure:
- `QThread: Destroyed while thread is still running` in a test that builds its own `MainWindow` (not through the `main_window` fixture): it needs `window.sessions.shutdown()` before the window goes, as step 1 (d) and (k) add. The other builders are `tests/test_packer_mainwindow_seam.py`, `tests/test_connection_state.py` (near line 207) and `tests/test_no_client.py`.
- `test_a_resume_with_a_take_over_opens_the_session_and_says_so` and `test_a_start_says_it_loaded_in_a_toast_and_no_box` are the first tests to run a whole start through `MainWindow`. If the start fails, `bridge.session["text"]` says why; fix the cause, do not stub the start out.
- `test_the_open_session_and_the_connection_reach_the_rows`: if a row is missing, the default date range dropped it; `_entry` dates its sessions three hours ago on purpose.
- A freshness test that times out in `_settle`: the page did not report the revision it was last sent. Check that `renderSessions` / `renderDetails` in `app.js` end by reporting the paint as the Packing page's render does (phase 3's `report()` path), also when the page is `covered`.
- In `tests/test_app_freshness.py` the details test waits for `bridge.details["state"] == "ready"`; if it reads `"error"`, print `bridge.details["error"]`: the summary `_files` writes must satisfy `load_session_details`.

- [ ] **Step 7: Lint and commit**

Run: `.venv/bin/ruff check . --exclude shared`. It will name any import the deletions left unused in `gui/main_window.py`; remove them (`QMessageBox` stays: other paths use it).

Stage everything this task touched (`/usr/bin/git add gui/app_pages.py gui/main_window.py tests`). Message: `feat: MainWindow drives the web Sessions pages; the Qt Session Browser is deleted`.

---

### Task 8: The renders, and the docs

**Files:**
- Create: `scripts/render_sessions.py`
- Create: `docs/design/ui-refresh/renders/phase4/*.png` (28 files, written by the script)
- Modify: `CONTEXT.md`, `docs/adr/0003-the-shells-pages-are-one-web-document.md`
- Modify, only if a render shows a difference from the mockup: `gui/web/app.css`, `gui/web/app.js`, `gui/web/app.html`, and section 12 of the spec

**Interfaces:**
- Consumes: `MainWindow.sessions` (`shutdown()`, and `refresh` replaced by a no-op), `AppPages`, `AppBridge.set_sessions / set_details / set_confirm / set_page` (Tasks 4, 7); `sessions_payload`, `details_payload`, `takeover_payload`, `refresh_failure`, `session_key` (Tasks 2, 3); `load_session_details`, `SessionFilesError` (Task 1); in the page, a session row is `[data-session]` with `dataset.session` its key, an order row is `[data-dorder]`, and the ids `d-query` and `d-back` exist (Tasks 4, 5).
- Produces: nothing code calls. The PNGs go in the PR.

- [ ] **Step 1: Write `scripts/render_sessions.py`**

```python
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
              items=97, duration=11549,
              metrics={"total_corrections": 1, "total_unknown_scans": 1}),
        unstarted(root, 2, 1, "Express", 24, 61),
        entry(root, 3, 1, "incomplete", "Morning_wave", IVAN, "WH-PC-01", 96, 57,
              skipped=1, items=288, touched="15:31:00", duration=26929),
        entry(root, 23, 1, "completed", "Morning_wave", MARIA, "WH-PC-02", 12, 12,
              items=30),
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
            js("document.getElementById('d-back').scrollIntoView()")

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
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python scripts/render_sessions.py`
Expected: 28 paths printed, `7a-light.png` to `8f-dark.png`, under `docs/design/ui-refresh/renders/phase4/`. Notes for a failure:
- `failed in the page: …` on a `select`: no `[data-session]` row has that key, so the row is not in the list. Print `[row["id"] for row in bridge.sessions["rows"]]`; a named session outside the default 30-day range of `NOW` is the usual cause.
- `load_session_details` raising for 8a, 8b or 8c: the file `write_session_files` wrote does not satisfy the loader. Fix the script's data, not the loader.
- If `window.client_combo.setCurrentIndex(-1)` leaves the page on Packing, that is `_sync_client_state` doing its job; the `pages.setCurrentIndex(PAGE_BROWSER)` after it is what shows 7h.

- [ ] **Step 3: Look at every render beside its mockup frame**

Unpack the mockup as `docs/design/ui-refresh/mockups/README.md` describes, into a folder outside the repo, and open each PNG with the Read tool. For each of the 14 frames, in both themes, check against the mockup frame of the same id (`Packer Screens.html` is the index; the notes on the 7 and 8 groups are part of the brief):

- 7a: one toolbar row that does not wrap at 1366px (tabs with counts, search, the two dates, Refresh, the stamp over the switch, Export); head 40px; rows 44px; solid dots only on Paused and Incomplete; the foot's legend and "40 sessions".
- 7b: the pane is 360px; the list lost Items and Last touched; the selected row has the tinted ground and the 4px rule; one primary action at full width, *View details* under it.
- 7c: the dialog is centred over a scrim, 540px, *Cancel* then *Take over and resume*.
- 7d, 7g: the centred glyph, title and sentence; 7d has *Clear filters*.
- 7e: the status line, 12 still skeleton rows, counts "–".
- 7f: the danger banner above the toolbar with the path in mono and *Retry*; the stamp red and bold; the list still drawn.
- 7h: the centred card only.
- 8a: head, facts in seven cells, five stat cards, the three groups, the Orders card.
- 8b: the info strip; "so far" on Duration, the cards and the two time groups; Completed reads "Still packing".
- 8c: the one sentence in place of the two time groups; Scan quality still there.
- 8d: item rows on the raised ground, indented; the extra and unknown rows; the badges.
- 8e: "No orders match" under the sticky head; "Showing 0 of 38 recorded orders".
- 8f: the danger banner; the facts row; no cards, timing or orders; *Export Excel* disabled.
- Both themes: nothing unreadable, no light surface left in Dark.

Fix what differs in `gui/web/app.css`, `app.js` or `app.html` (within Global Constraints), re-run the script, and re-run `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_sessions_page.py tests/test_style_literals_guard.py`. A difference you decide to keep is a departure: add a row to section 12 of the spec, with why.

- [ ] **Step 4: `CONTEXT.md`**

Replace each paragraph that starts with the bold term, whole, with:

```markdown
**App document** — the web page that draws the shell's pages: Packing, Statistics, Sessions and Session details. One page in one web view (ADR 0003); Packer Mode's order document is a different page in its own view.
```

```markdown
**App bridge** — the one `QWebChannel` object the app document talks to. It says which of the four pages shows, what the session is (none, opening, failed, open) and each page's data; the page reports clicks through slots.
```

```markdown
**Session Browser** — the Sessions page and the Session details page behind a session: two pages of the app document. Its client picker is the command bar's; it has no picker of its own. Its destination in the sidebar is labelled "Sessions".
```

```markdown
**Status chip** — the pill marking a session's status: its colour is the status's tone, and a solid dot means a person set the status where a hollow dot means the system inferred it.
```

In the **Session lock** paragraph, replace `a lock whose heartbeat stopped is *stale*` with `a lock with no heartbeat for 2 minutes is *stale*, and the Sessions list calls the session *stale* from the same moment`.

Add after the **Status chip** paragraph, each followed by a blank line as the others are:

```markdown
**Session pane** — the 360px column beside the Sessions list while a row is selected: the session's facts and its one action (Start packing, Resume session, View details or Go to Packing). While it is open the list's Items and Last touched columns fold into it.

**Take over** — resuming a session whose lock is stale. The page asks first, saying which PC had it, since when and what comes along; only that lock is released, and only if it is still stale. A session that is live on another PC cannot be taken over.
```

- [ ] **Step 5: ADR 0003**

In `docs/adr/0003-the-shells-pages-are-one-web-document.md`, under Consequences, replace

```markdown
- One view is hidden only under Packer Mode, and, until phase 4, under the Qt Sessions page.
```

with

```markdown
- One view is hidden only under Packer Mode. (Until phase 4 it was also hidden under the Qt Sessions page;
  Sessions and Session details are pages of the document since.)
```

- [ ] **Step 6: The graph, the suite, the commit**

Run: `graphify update .`
Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: all pass.
Run: `.venv/bin/ruff check . --exclude shared`
Expected: no findings.

Stage `scripts/render_sessions.py`, `docs/design/ui-refresh/renders/phase4`, `CONTEXT.md`, `docs/adr/0003-the-shells-pages-are-one-web-document.md`, and whatever step 3 changed. Message: `docs: renders of Sessions and Session details (7a to 7h, 8a to 8f), CONTEXT.md, ADR 0003`.

---

## For the PR

The PR description carries these; none of them is code.

- The 28 renders, embedded, each beside its frame id.
- The departures from the mockup: section 12 of the spec, as it stands after Task 8.
- "For shared/": section 13 of the spec.
- **Needs a check on Windows** before merge, because offscreen Chromium on Linux cannot show it: the native date picker's popup of the two date inputs opens and is usable inside QtWebEngine; a click in the page and then F5, Esc and Alt+Left; Ctrl+1/2/3 after a click in the page; the two save dialogs open over the window.
- Behaviour that changed on purpose: no "Session Loaded" / "Session Resumed" / "Session Active" / "Stale Lock Detected" message boxes (toasts, frame 3c and frame 7c replace them); the list calls a session Stale after 2 minutes, not 5; a failed refresh says so instead of showing "No sessions yet".
