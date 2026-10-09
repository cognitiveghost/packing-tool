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

from packing_tool.packer_logic import normalize_sku
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


# --- SKU mapping -----------------------------------------------------------------


def clean_mapping(barcode: Any, sku: Any) -> tuple[str, str]:
    """A barcode with no whitespace at all, and a SKU trimmed but kept as typed."""
    return "".join(str(barcode or "").split()), str(sku or "").strip()


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" + ("" if count == 1 else "s")


class MappingEditor:
    """One PC's unsaved edits to a client's barcode -> SKU mapping.

    `rows` is the working list; each row's `id` lasts until the next
    loaded(). Changes are counted by barcode against the mapping as read,
    which is exactly what a save sends.
    """

    def __init__(self, mapping: dict | None = None) -> None:
        self.rows: list[dict[str, Any]] = []
        self._read: dict[str, str] = {}
        self._next = 1
        self.loaded(mapping or {})

    def loaded(self, mapping: dict) -> None:
        """Start over from a mapping: after a load, a reload or a save."""
        self._read = {str(barcode): str(sku) for barcode, sku in (mapping or {}).items()}
        self.rows = [
            {"id": index, "barcode": barcode, "sku": sku}
            for index, (barcode, sku) in enumerate(sorted(self._read.items()), start=1)
        ]
        self._next = len(self.rows) + 1

    def _row(self, row_id: int) -> dict | None:
        return next((row for row in self.rows if row["id"] == row_id), None)

    def clash(self, barcode: Any, row_id: int = 0) -> dict | None:
        """The other row whose barcode is the same key to the scan matcher."""
        key = normalize_sku("".join(str(barcode or "").split()))
        if not key:
            return None
        return next(
            (
                row
                for row in self.rows
                if row["id"] != row_id and normalize_sku(row["barcode"]) == key
            ),
            None,
        )

    def _problem(self, barcode: str, sku: str, row_id: int) -> str:
        if not normalize_sku(barcode):
            return "Enter a barcode."
        if not sku:
            return "Enter a SKU."
        clash = self.clash(barcode, row_id)
        if clash is not None:
            return f"This barcode already maps to {clash['sku']}."
        return ""

    def add(self, barcode: Any, sku: Any) -> str:
        barcode, sku = clean_mapping(barcode, sku)
        problem = self._problem(barcode, sku, 0)
        if problem:
            return problem
        self.rows.insert(0, {"id": self._next, "barcode": barcode, "sku": sku})
        self._next += 1
        return ""

    def update(self, row_id: int, barcode: Any, sku: Any) -> str:
        row = self._row(row_id)
        if row is None:
            return "That mapping is no longer in the list."
        barcode, sku = clean_mapping(barcode, sku)
        problem = self._problem(barcode, sku, row_id)
        if problem:
            return problem
        row["barcode"], row["sku"] = barcode, sku
        return ""

    def replace(self, row_id: int, barcode: Any, sku: Any) -> str:
        """Give `sku` to the row that already has `barcode`.

        `row_id` is the row being edited, or 0 for the add draft. The edited
        row becomes the row it collided with, so it is removed.
        """
        barcode, sku = clean_mapping(barcode, sku)
        if not sku:
            return "Enter a SKU."
        clash = self.clash(barcode, row_id)
        if clash is None:
            return self.update(row_id, barcode, sku) if row_id else self.add(barcode, sku)
        clash["sku"] = sku
        if row_id:
            self.delete(row_id)
        return ""

    def delete(self, row_id: int) -> None:
        self.rows = [row for row in self.rows if row["id"] != row_id]

    def status(self, row: dict) -> str:
        """ "new", "edited" or "" for a row, against the mapping as read."""
        if row["barcode"] not in self._read:
            return "new"
        return "edited" if self._read[row["barcode"]] != row["sku"] else ""

    def counts(self) -> dict[str, int]:
        now = {row["barcode"] for row in self.rows}
        statuses = [self.status(row) for row in self.rows]
        return {
            "added": statuses.count("new"),
            "edited": statuses.count("edited"),
            "deleted": sum(1 for barcode in self._read if barcode not in now),
        }

    def summary(self) -> str:
        """ "2 added, 1 edited, 1 deleted", zero parts left out."""
        return ", ".join(f"{count} {word}" for word, count in self.counts().items() if count)

    def changes(self) -> tuple[dict[str, str], list[str]]:
        """(add, remove) for ProfileManager.update_sku_mapping."""
        now = {row["barcode"]: row["sku"] for row in self.rows}
        add = {barcode: sku for barcode, sku in now.items() if self._read.get(barcode) != sku}
        remove = [barcode for barcode in self._read if barcode not in now]
        return add, remove


_ERRORS = {
    "save": ("Couldn’t save to the file server.", "save"),
    "load": ("Couldn’t load the mappings.", "load"),
    "quick": ("Couldn’t save to the file server.", ""),
}


def mapping_error(kind: str, cause: str, path: str, changes: int = 0) -> dict[str, str]:
    """The banner over the table (spec sections 6.6 and 7.3)."""
    title, action = _ERRORS[kind]
    if kind == "save":
        kept = "change is" if changes == 1 else "changes are"
        text = f"Your {changes} {kept} still here and nothing on the server changed."
    elif kind == "load":
        text = "The list could not be read from the file server."
    else:
        text = "Nothing on the server changed."
    return {"title": title, "text": text, "cause": str(cause), "path": str(path), "action": action}


def mapping_payload(
    editor: MappingEditor,
    *,
    client: str,
    saved: bool = False,
    error: dict | None = None,
    quick: dict | None = None,
    failed: bool = False,
) -> dict[str, Any]:
    """The SKU mapping page (spec section 6.2)."""
    changes = sum(editor.counts().values())
    summary = editor.summary()
    return {
        "client": str(client),
        "mode": "failed" if failed else "ready",
        "rows": []
        if failed
        else [
            {**row, "key": normalize_sku(row["barcode"]), "status": editor.status(row)}
            for row in editor.rows
        ],
        "dirty": changes > 0,
        "changes": changes,
        "summary": summary,
        "lost": (
            f"Your {_plural(changes, 'unsaved change')} ({summary}) will be lost."
            if changes
            else ""
        ),
        "saved": bool(saved) and not changes,
        "error": dict(error or {}),
        "quick": dict(quick or {}),
    }


def order_choices(order_state) -> list[dict[str, str]]:
    """The open order's lines, the ones still owing scans first.

    An unmatched scan happened while packing this order, so the SKU the
    packer meant is almost always a line that is not finished yet.
    """
    return [
        {
            "sku": line["original_sku"],
            "label": f"{line['original_sku']} — {line['packed']} / {line['required']} packed",
            "key": normalize_sku(line["original_sku"]),
        }
        for line in sorted(order_state or [], key=lambda line: line["packed"] >= line["required"])
    ]


_HINTS = {
    "sku": "Scan or type the barcode for this SKU.",
    "barcode": "Scanned in Packer Mode. Enter the SKU it should count as.",
}


def quick_payload(kind: str, *, sku: str = "", barcode: str = "", choices=()) -> dict[str, Any]:
    """A quick map: SKU mapping opened from Packer Mode for one add (ADR 0004)."""
    return {
        "kind": kind,
        "sku": str(sku),
        "barcode": str(barcode),
        "hint": _HINTS[kind],
        "choices": list(choices),
    }
