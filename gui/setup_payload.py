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
from shared.i18n import N_, _, _n, month_abbr
from shared.metadata_utils import parse_timestamp

# Never strftime: Qt can switch the process locale under us. Months come from
# shared.i18n.month_abbr for the same reason.
_DAYS = (
    N_("Monday"), N_("Tuesday"), N_("Wednesday"), N_("Thursday"),
    N_("Friday"), N_("Saturday"), N_("Sunday"),
)

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
        return _("Enter a name.")
    if not _NAME.fullmatch(text):
        return _("Use letters, numbers, spaces, dots, hyphens or apostrophes.")
    for existing in names:
        if existing.lower() == text.lower():
            return _(
                "There’s already a worker called {name}. Pick that card, or add a surname.",
                name=existing,
            )
    return ""


def last_active_text(when: datetime | None, now: datetime, created: datetime | None = None) -> str:
    """A card's second line (spec section 5.2). `when` and `now` are aware."""
    if when is None:
        if created is not None and now - created < timedelta(hours=1):
            return _("Just created")
        return _("Not active yet")
    local = when.astimezone(now.tzinfo)
    days = (now.date() - local.date()).days
    if days <= 0:
        return _("Last active Today, {time}", time=f"{local.hour:02d}:{local.minute:02d}")
    if days == 1:
        return _("Last active Yesterday")
    if days < 7:
        return _("Last active {day}", day=_(_DAYS[local.weekday()]))
    if days < 14:
        return _("Last active Last week")
    day = f"{local.day} {month_abbr(local.month)}"
    if local.year == now.year:
        return _("Last active {date}", date=day)
    return _("Last active {date} {year}", date=day, year=local.year)


def _when(stamp: Any) -> datetime | None:
    try:
        return parse_timestamp(stamp) if stamp else None
    except (TypeError, ValueError):
        return None


def _stats(sessions: int, orders: int) -> str:
    """ "3 sessions · 41 orders", each noun as one whole sentence fragment."""
    return _(
        "{sessions} · {orders}",
        sessions=_n("{count} session", "{count} sessions", sessions, count=f"{sessions:,}"),
        orders=_n("{count} order", "{count} orders", orders, count=f"{orders:,}"),
    )


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
    if startup:
        leave = _("Quit")
    elif current_name:
        leave = _("Back to {name}", name=current_name)
    else:
        leave = _("Back")
    payload: dict[str, Any] = {
        "context": "startup" if startup else "switch",
        "leave": leave,
        "mode": "ready",
        "error": {},
        "cards": [],
    }
    if failure:
        cause = str(failure.get("cause") or _("it could not be read"))
        payload["mode"] = "failed"
        payload["error"] = {
            "title": _("Couldn’t load the worker list."),
            # The cause is the backend's English detail (rule 4); only the sentence around it is translated.
            "text": _("{cause}.", cause=cause[:1].upper() + cause[1:]),
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
            badge = _("Opening…")
        elif not startup and profile.id == current_id:
            badge = _("Current")
        else:
            badge = ""
        payload["cards"].append(
            {
                "id": str(profile.id),
                "name": str(profile.name),
                "initials": initials(profile.name),
                "stats": _stats(sessions, orders) if sessions or orders else _("No sessions yet"),
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
            return _("Enter a barcode.")
        if not sku:
            return _("Enter a SKU.")
        clash = self.clash(barcode, row_id)
        if clash is not None:
            return _("This barcode already maps to {sku}.", sku=clash["sku"])
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
            return _("That mapping is no longer in the list.")
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
            return _("Enter a SKU.")
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
        return ", ".join(_count_word(word, count) for word, count in self.counts().items() if count)

    def changes(self) -> tuple[dict[str, str], list[str]]:
        """(add, remove) for ProfileManager.update_sku_mapping."""
        now = {row["barcode"]: row["sku"] for row in self.rows}
        add = {barcode: sku for barcode, sku in now.items() if self._read.get(barcode) != sku}
        remove = [barcode for barcode in self._read if barcode not in now]
        return add, remove


def _count_word(word: str, count: int) -> str:
    """One summary part, "2 added": the word is a logic key, so only its display is translated."""
    if word == "added":
        return _n("{n} added", "{n} added", count)
    if word == "edited":
        return _n("{n} edited", "{n} edited", count)
    return _n("{n} deleted", "{n} deleted", count)


_ERRORS = {
    "save": (N_("Couldn’t save to the file server."), "save"),
    "load": (N_("Couldn’t load the mappings."), "load"),
    "quick": (N_("Couldn’t save to the file server."), ""),
}


def mapping_error(kind: str, cause: str, path: str, changes: int = 0) -> dict[str, str]:
    """The banner over the table (spec sections 6.6 and 7.3)."""
    title, action = _ERRORS[kind]
    if kind == "save":
        text = _n(
            "Your {n} change is still here and nothing on the server changed.",
            "Your {n} changes are still here and nothing on the server changed.",
            changes,
        )
    elif kind == "load":
        text = _("The list could not be read from the file server.")
    else:
        text = _("Nothing on the server changed.")
    return {"title": _(title), "text": text, "cause": str(cause), "path": str(path), "action": action}


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
            _n(
                "Your {n} unsaved change ({summary}) will be lost.",
                "Your {n} unsaved changes ({summary}) will be lost.",
                changes,
                summary=summary,
            )
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
            "label": _(
                "{sku} — {packed} / {required} packed",
                sku=line["original_sku"],
                packed=line["packed"],
                required=line["required"],
            ),
            "key": normalize_sku(line["original_sku"]),
        }
        for line in sorted(order_state or [], key=lambda line: line["packed"] >= line["required"])
    ]


_HINTS = {
    "sku": N_("Scan or type the barcode for this SKU."),
    "barcode": N_("Scanned in Packer Mode. Enter the SKU it should count as."),
}


def quick_payload(kind: str, *, sku: str = "", barcode: str = "", choices=()) -> dict[str, Any]:
    """A quick map: SKU mapping opened from Packer Mode for one add (ADR 0004)."""
    return {
        "kind": kind,
        "sku": str(sku),
        "barcode": str(barcode),
        "hint": _(_HINTS[kind]),
        "choices": list(choices),
    }
