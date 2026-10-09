"""What the setup document says (ADR 0002, ADR 0004).

The setup document draws the two full-window pages, Worker selection and SKU
mapping. The functions here are pure -- no widgets, no I/O -- and decide every
card, row and sentence; gui/web/setup.js renders them and gui/setup_pages.py
reads and writes the server.

Spec: docs/superpowers/specs/2026-10-09-ui-refresh-phase5-setup-pages-design.md
"""

import re
from datetime import datetime, timedelta
from typing import Any

from shared.metadata_utils import parse_timestamp

# Never strftime: Qt can switch the process locale under us.
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_DAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

# A letter or a digit in any script, or one of four marks.
_NAME = re.compile(r"(?:[^\W_]|[ .'\-])+")


def initials(name: str) -> str:
    """The first letters of the first two words: "Desislava Ilieva" -> "DI"."""
    return "".join(word[0] for word in str(name or "").split()[:2]).upper()


def clean_worker_name(name: Any) -> str:
    """Trimmed, with inner runs of whitespace collapsed to one space."""
    return " ".join(str(name or "").split())


def worker_name_problem(name: Any, names: list[str]) -> str:
    """Why `name` cannot be a new worker's, as a sentence; "" when it can."""
    text = clean_worker_name(name)
    if not text:
        return "Enter a name."
    if not _NAME.fullmatch(text):
        return "Use letters, numbers, spaces, dots, hyphens or apostrophes."
    for existing in names:
        if existing.lower() == text.lower():
            return (
                f"There’s already a worker called {existing}. "
                "Pick that card, or add a surname."
            )
    return ""


def last_active_text(when: datetime | None, now: datetime, created: datetime | None = None) -> str:
    """A card's second line (spec section 5.2). `when` and `now` are aware."""
    if when is None:
        if created is not None and now - created < timedelta(hours=1):
            return "Just created"
        return "Not active yet"
    local = when.astimezone(now.tzinfo)
    days = (now.date() - local.date()).days
    if days <= 0:
        return f"Last active Today, {local.hour:02d}:{local.minute:02d}"
    if days == 1:
        return "Last active Yesterday"
    if days < 7:
        return f"Last active {_DAYS[local.weekday()]}"
    if days < 14:
        return "Last active Last week"
    day = f"{local.day} {_MONTHS[local.month - 1]}"
    return f"Last active {day}" if local.year == now.year else f"Last active {day} {local.year}"


def _when(stamp: Any) -> datetime | None:
    try:
        return parse_timestamp(stamp) if stamp else None
    except (TypeError, ValueError):
        return None


def _count(number: int, noun: str) -> str:
    return f"{number:,} {noun}" + ("" if number == 1 else "s")


def workers_payload(
    workers,
    *,
    startup: bool,
    now: datetime,
    current_id: str = "",
    current_name: str = "",
    picked_id: str = "",
    failure: dict | None = None,
) -> dict[str, Any]:
    """The Worker selection page (spec section 5.2).

    `workers` are WorkerProfiles (or anything with their attributes).
    `failure` is {"cause", "path"} when the list could not be read.
    """
    payload: dict[str, Any] = {
        "context": "startup" if startup else "switch",
        "leave": "Quit" if startup else (f"Back to {current_name}" if current_name else "Back"),
        "mode": "ready",
        "error": {},
        "cards": [],
    }
    if failure:
        cause = str(failure.get("cause") or "it could not be read")
        payload["mode"] = "failed"
        payload["error"] = {
            "title": "Couldn’t load the worker list.",
            "text": cause[:1].upper() + cause[1:] + ".",
            "path": str(failure.get("path") or ""),
        }
        return payload

    def order(item):
        _worker, when = item
        if when is None:
            return (1, 0.0, str(_worker.name).lower())
        return (0, -when.timestamp(), "")

    for profile, when in sorted(((w, _when(w.last_active)) for w in workers), key=order):
        sessions = int(profile.total_sessions or 0)
        orders = int(profile.total_orders or 0)
        picked = bool(picked_id) and profile.id == picked_id
        if picked:
            badge = "Opening…"
        elif not startup and profile.id == current_id:
            badge = "Current"
        else:
            badge = ""
        payload["cards"].append(
            {
                "id": str(profile.id),
                "name": str(profile.name),
                "initials": initials(profile.name),
                "stats": (
                    f"{_count(sessions, 'session')} · {_count(orders, 'order')}"
                    if sessions or orders
                    else "No sessions yet"
                ),
                "last": last_active_text(when, now, _when(profile.created_at)),
                "badge": badge,
                "picked": picked,
            }
        )
    return payload
