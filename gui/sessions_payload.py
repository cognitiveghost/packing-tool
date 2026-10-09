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
