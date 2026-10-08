"""The app document's bridge and payloads (ADR 0003).

One web document draws the shell's pages: Packing and Statistics now, Sessions
in phase 4. The payload functions below are pure -- no Qt, no I/O -- and are
the only place that decides what the pages say; gui/web/app.js renders them.
The page keeps two pieces of view state of its own: the order rows the packer
toggled, and the SKU table's sort.

Spec: docs/superpowers/specs/2026-10-08-ui-refresh-phase3-packing-statistics-design.md
"""

from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, Signal, Slot
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.packer_bridge import _int, order_label
from gui.theme import current_tokens
from packing_tool.exceptions import PackingListInvalidError, PackingStateUnreadableError
from packing_tool.session_stats import courier_totals, session_totals, sku_summary
from shared.web_page import PageBridge, mount_page

PAGE = Path(__file__).resolve().parent / "web" / "app.html"
CHANNEL_NAME = "app"

# Frame 3b: the steps the code runs (spec section 5), not the mockup's.
STEPS = (
    "Taking the packing list",
    "Reading saved progress",
    "Reading the packing list",
)

_GROUPS = (
    ("in_progress", "In progress"),
    ("not_started", "Not started"),
    ("packed", "Packed"),
)
_LIST_FAILED = "Packing list could not be loaded"
_OPEN_FAILED = "Session could not be opened"


def _item_state(packed: int, required: int) -> str:
    if packed >= required:
        return "complete"
    return "partial" if packed > 0 else "pending"


def packing_payload(
    orders_data: dict[Any, dict], state: dict[str, Any], query: str = ""
) -> dict[str, Any]:
    """The Packing page: totals, and the orders that match `query`, grouped.

    Totals always count the whole list. An order matches when its number, or
    an item's SKU or product name, contains the query; a leading # and case
    are ignored. With a query every listed order is open and the matching
    items are hits; without one only in-progress orders are open.
    """
    state = state or {}
    completed = set(state.get("completed_orders") or [])
    skipped = set(state.get("skipped_orders") or [])
    in_progress = state.get("in_progress") or {}
    typed = str(query or "").strip()
    needle = typed.lstrip("#").strip().lower()
    if not needle:
        typed = ""

    groups: dict[str, list] = {key: [] for key, _label in _GROUPS}
    counts = {key: 0 for key, _label in _GROUPS}
    units = packed_units = skipped_count = hits = 0

    for number, order in (orders_data or {}).items():
        lines = (order or {}).get("items") or []
        entries = in_progress.get(number)
        by_row = {
            _int(entry.get("row"), -1): entry
            for entry in (entries if isinstance(entries, list) else [])
            if isinstance(entry, dict)
        }
        done = number in completed
        is_skipped = number in skipped and not done
        if done:
            key = "packed"
        elif number in in_progress and not is_skipped:
            key = "in_progress"
        else:
            key = "not_started"

        items = []
        order_units = order_packed = 0
        for index, line in enumerate(lines):
            sku = str(line.get("SKU", ""))
            product = str(line.get("Product_Name", ""))
            required = max(_int(line.get("Quantity")), 0)
            packed = required if done else _int((by_row.get(index) or {}).get("packed"), 0)
            order_units += required
            order_packed += packed
            items.append(
                {
                    "sku": sku,
                    "product": product,
                    "packed": packed,
                    "required": required,
                    "state": _item_state(packed, required),
                    "hit": bool(needle)
                    and (needle in sku.lower() or needle in product.lower()),
                }
            )

        counts[key] += 1
        units += order_units
        packed_units += order_packed
        skipped_count += is_skipped

        text = str(number)
        if needle and needle not in text.lstrip("#").lower() and not any(
            item["hit"] for item in items
        ):
            continue
        hits += 1
        noun = "item" if len(items) == 1 else "items"
        names = ", ".join(item["product"] for item in items)
        groups[key].append(
            {
                "number": text,
                "label": order_label(text),
                "summary": f"{len(items)} {noun} · {names}" if names else f"{len(items)} {noun}",
                "packed": order_packed,
                "units": order_units,
                "status": key,
                "courier": str(lines[0].get("Courier", "")) if lines else "",
                "skipped": is_skipped,
                "open": bool(needle) or key == "in_progress",
                "items": items,
            }
        )

    total = len(orders_data or {})
    done_count = counts["packed"]

    def note(key: str) -> str:
        listed = sum(1 for order in groups[key] if order["skipped"])
        return f"{listed} skipped" if listed else ""

    return {
        "totals": {
            "orders": total,
            "done": done_count,
            "units": units,
            "packed": packed_units,
            "skipped": skipped_count,
            "in_progress": counts["in_progress"],
            # int(), as session_stats.session_totals does: the two pages agree.
            "pct": int(done_count / total * 100) if total else 0,
            "complete": total > 0 and done_count == total,
        },
        "query": typed,
        "hits": hits,
        "groups": [
            {
                "key": key,
                "label": label,
                "count": len(groups[key]),
                "note": note(key),
                "orders": groups[key],
            }
            for key, label in _GROUPS
            if groups[key]
        ],
    }


def statistics_payload(df, state: dict[str, Any]) -> dict[str, Any]:
    """The Statistics page, from packing_tool.session_stats."""
    state = state or {}
    completed = state.get("completed_orders") or []
    skipped = set(state.get("skipped_orders") or [])
    totals = session_totals(df, completed)
    skus = [
        {
            "sku": str(row["sku"]),
            "product": str(row["product"]),
            "total": row["required"],
            "packed": row["packed"],
            "left": max(row["required"] - row["packed"], 0),
            "state": row["state"],
        }
        for row in sku_summary(df, state)
    ]
    return {
        "orders": totals["orders"],
        "completed": totals["completed"],
        "items": totals["items"],
        "unique_skus": totals["unique_skus"],
        "pct": totals["progress_pct"],
        "in_progress": sum(
            1
            for number in (state.get("in_progress") or {})
            if number not in skipped and number not in completed
        ),
        "packed": sum(row["packed"] for row in skus),
        "fully_packed": sum(1 for row in skus if row["state"] == "packed"),
        "couriers": [
            {"name": str(row["courier"]), "done": row["done"], "total": row["orders"]}
            for row in courier_totals(df, completed)
        ],
        "skus": skus,
    }


def session_payload(
    state: str = "none",
    *,
    list_name: str = "",
    session_id: str = "",
    step: int = 0,
    title: str = "",
    text: str = "",
    orders: int = 0,
    couriers=(),
    complete: bool = False,
) -> dict[str, Any]:
    """What the document knows about the session: none, opening, failed or open."""
    names = [str(name) for name in couriers]
    meta = f"{orders} {'order' if orders == 1 else 'orders'}"
    if names:
        meta += " · " + ", ".join(names[:3])
        if len(names) > 3:
            meta += f" +{len(names) - 3}"
    return {
        "state": state,
        "list": str(list_name),
        "id": str(session_id),
        "step": int(step),
        "stepName": STEPS[step - 1] if 1 <= step <= len(STEPS) else "",
        "title": str(title),
        "text": str(text),
        "meta": meta if state == "open" else "",
        "complete": bool(complete),
    }


def start_failure(error: Exception, list_name: str) -> tuple[str, str]:
    """Frame 3c's title and sentence for a session start that failed."""
    if isinstance(error, PackingStateUnreadableError):
        return (
            "Saved progress could not be read",
            (
                f"The saved progress for {list_name} could not be read, so the list was "
                "not opened. Nothing was changed. Check the connection to the server and "
                "open it again."
            ),
        )
    if isinstance(error, PackingListInvalidError):
        missing = ", ".join(error.missing)
        found = ", ".join(error.found) or "nothing"
        if error.kind == "column":
            return _LIST_FAILED, f"{list_name} has no {missing} column. Found: {found}."
        return _LIST_FAILED, f"{list_name} has an order with no {missing}. Found: {found}."
    if isinstance(error, FileNotFoundError):
        return _LIST_FAILED, f"{list_name} is no longer in the session's folder."
    if isinstance(error, ValueError):  # json.JSONDecodeError is one
        return _LIST_FAILED, f"{list_name} could not be read: {error}."
    return _OPEN_FAILED, str(error)


class AppBridge(PageBridge):
    """The app document's one channel object.

    The theme, the toast, the revision and the painted report come from
    PageBridge. State Python owns crosses as a notify property, so a page that
    connects late reads the current value; what the page reports crosses as a
    slot. Every notify property raises the revision on its own.
    """

    pageChanged = Signal()
    coveredChanged = Signal()
    shellChanged = Signal()
    sessionChanged = Signal()
    packingChanged = Signal()
    statisticsChanged = Signal()
    # Python-facing. The page reports through the slots below and never
    # connects to these.
    openSessionRequested = Signal()
    startPackingRequested = Signal()
    endSessionRequested = Signal()
    retryStartRequested = Signal()
    closeFailureRequested = Signal()
    clearFilterRequested = Signal()
    chooseClientRequested = Signal()
    pageRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._page = "packing"
        self._covered = False
        self._shell: dict = {"client": False, "clients": True, "serverDown": False}
        self._session: dict = session_payload()
        self._packing: dict = {}
        self._statistics: dict = {}

    # --- out: Python -> JS -------------------------------------------------

    def _get_page(self) -> str:
        return self._page

    page = Property(str, _get_page, notify=pageChanged)

    def _get_covered(self) -> bool:
        return self._covered

    covered = Property(bool, _get_covered, notify=coveredChanged)

    def _get_shell(self) -> dict:
        return self._shell

    shell = Property("QVariantMap", _get_shell, notify=shellChanged)

    def _get_session(self) -> dict:
        return self._session

    session = Property("QVariantMap", _get_session, notify=sessionChanged)

    def _get_packing(self) -> dict:
        return self._packing

    packing = Property("QVariantMap", _get_packing, notify=packingChanged)

    def _get_statistics(self) -> dict:
        return self._statistics

    statistics = Property("QVariantMap", _get_statistics, notify=statisticsChanged)

    # --- in: JS -> Python --------------------------------------------------

    @Slot()
    def openSession(self) -> None:
        self.openSessionRequested.emit()

    @Slot()
    def startPacking(self) -> None:
        self.startPackingRequested.emit()

    @Slot()
    def endSession(self) -> None:
        self.endSessionRequested.emit()

    @Slot()
    def retryStart(self) -> None:
        self.retryStartRequested.emit()

    @Slot()
    def closeFailure(self) -> None:
        self.closeFailureRequested.emit()

    @Slot()
    def clearFilter(self) -> None:
        self.clearFilterRequested.emit()

    @Slot()
    def chooseClient(self) -> None:
        self.chooseClientRequested.emit()

    @Slot(str)
    def showPage(self, name) -> None:
        self.pageRequested.emit(str(name))

    # --- Python-facing API -------------------------------------------------
    # A setter that changes nothing emits nothing, so an idle push does not
    # raise the revision.

    def set_page(self, name: str) -> None:
        if name != self._page:
            self._page = str(name)
            self.pageChanged.emit()

    def set_covered(self, covered: bool) -> None:
        if bool(covered) != self._covered:
            self._covered = bool(covered)
            self.coveredChanged.emit()

    def set_shell(self, *, client: bool, clients: bool, server_down: bool) -> None:
        shell = {
            "client": bool(client),
            "clients": bool(clients),
            "serverDown": bool(server_down),
        }
        if shell != self._shell:
            self._shell = shell
            self.shellChanged.emit()

    def set_session(self, payload: dict) -> None:
        payload = dict(payload or session_payload())
        if payload != self._session:
            self._session = payload
            self.sessionChanged.emit()

    def set_packing(self, payload: dict) -> None:
        payload = dict(payload or {})
        if payload != self._packing:
            self._packing = payload
            self.packingChanged.emit()

    def set_statistics(self, payload: dict) -> None:
        payload = dict(payload or {})
        if payload != self._statistics:
            self._statistics = payload
            self.statisticsChanged.emit()


def mount_app_page(view: QWebEngineView) -> AppBridge:
    """Load the app document into `view` and return the bridge it talks to.

    The view keeps its focus policy: the page is buttons, and a packer may
    reach them from the keyboard (spec section 9). Packer Mode's view is the
    one that refuses it.
    """
    bridge = AppBridge(view)
    mount_page(view, bridge, PAGE, CHANNEL_NAME, tokens=current_tokens)
    return bridge
