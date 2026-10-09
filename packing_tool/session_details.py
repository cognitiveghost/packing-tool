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


# The 8f cause when a file parses but is not what this app writes.
UNREADABLE_SHAPE = "its files are not in the shape this version reads"


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
    # An ended-then-resumed session still holds the summary its last End wrote:
    # while it is open again, packing_state.json is the newer file.
    resumed = bool(state) and entry.get("status") in ("in_progress", "paused", "stale")
    if summary and not resumed:
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
