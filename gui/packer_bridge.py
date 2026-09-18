"""The bridge: the one object Packer Mode's order document talks to (ADR 0001).

Modelled on shopify-fulfillment-tool's gui/results_bridge.py. Every message is
its own named member, never a generic send(kind, data). State Python owns
crosses as a notify Property, so a page that connects late reads the current
value with no handshake; what JS reports crosses as a Slot. Channel members are
camelCase because JS calls them.

The payload functions below are pure -- no Qt, no I/O -- so the numbers and the
action rules are testable without a browser. They are the only place that
decides an item's state; packer.js renders what they say.

Spec: docs/superpowers/specs/2026-09-18-phase10-bundle4-web-seam-design.md
"""

from pathlib import Path
from typing import Any

from PySide6.QtCore import Property, QObject, Qt, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.theme import current_tokens
from packing_tool.packer_logic import normalize_sku
from shared.theme import on_theme_changed, theme_css_vars

# Force confirm is for quantities nobody wants to scan one at a time. Below
# this it is a foot-gun with no upside, and today's UI already hides it.
FORCE_CONFIRM_MIN_QTY = 5


def _int(value: Any, default: int = 1) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def item_rows(
    items: list[dict[str, Any]],
    order_state: list[dict[str, Any]],
    sku_map: dict[str, str],
) -> list[dict[str, Any]]:
    """One row per order item, with its state and the actions it offers."""
    packed_by_row = {
        _int(s.get("row"), 0): _int(s.get("packed"), 0) for s in order_state or []
    }
    mapped = {normalize_sku(v) for v in (sku_map or {}).values()}

    rows = []
    for index, item in enumerate(items):
        sku = str(item.get("SKU", ""))
        required = max(_int(item.get("Quantity")), 1)
        packed = packed_by_row.get(index, 0)
        if packed >= required:
            state = "complete"
        elif packed > 0:
            state = "partial"
        else:
            state = "pending"
        rows.append(
            {
                "row": index,
                "product": str(item.get("Product_Name", "")),
                "sku": sku,
                "required": required,
                "packed": packed,
                "state": state,
                "just_changed": False,
                "confirm": packed < required,
                "undo": packed > 0,
                "force": required > FORCE_CONFIRM_MIN_QTY and packed < required,
                "map": normalize_sku(sku) not in mapped,
            }
        )
    return rows


def _clean(value: Any) -> str:
    """A metadata value as display text; pandas 'nan' and blanks become ''."""
    text = str(value).strip() if value is not None else ""
    return "" if text.lower() == "nan" else text


def banner_payload(
    order_number: str, metadata: dict[str, Any] | None
) -> dict[str, Any]:
    """The metadata banner: the order number, its chips and its notes."""
    metadata = metadata or {}
    chips = [
        _clean(metadata.get("order_type")),
        _clean(metadata.get("shipping_provider")),
        _clean(metadata.get("destination_country")),
    ]
    box = _clean(metadata.get("order_min_box"))
    if box:
        chips.append(f"Box {box}")
    for tag in list(metadata.get("tags") or []) + list(
        metadata.get("internal_tags") or []
    ):
        chips.append(_clean(tag))
    return {
        "order": str(order_number),
        "chips": [c for c in chips if c],
        "notes": _clean(metadata.get("notes")) or _clean(metadata.get("system_note")),
    }


def summary_lines(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Unique-SKU and item totals over item_rows()' output."""
    required: dict[str, int] = {}
    packed: dict[str, int] = {}
    for row in rows:
        sku = row["sku"]
        required[sku] = required.get(sku, 0) + row["required"]
        packed[sku] = packed.get(sku, 0) + row["packed"]
    return {
        "items_packed": sum(packed.values()),
        "items_total": sum(required.values()),
        "skus_packed": sum(1 for s in required if packed.get(s, 0) >= required[s]),
        "skus_total": len(required),
    }


WEB_DIR = Path(__file__).resolve().parent / "web"
PAGE = WEB_DIR / "packer.html"
THEME_MARKER = "/* theme-vars */"
CHANNEL_NAME = "packer"


class PackerBridge(QObject):
    """The order document's one channel object."""

    themeCssChanged = Signal()
    bannerChanged = Signal()
    feedbackChanged = Signal()
    itemsChanged = Signal()
    extrasChanged = Signal()
    historyChanged = Signal()
    progressChanged = Signal()
    # JS-facing: the scan cue (S4). The page draws it; Qt has no element left
    # on this screen to flash.
    scanFlashed = Signal(str)
    # Python-facing. JS reports through the slots below and never connects to
    # these, so nothing it sends can echo back into the page.
    confirmRequested = Signal(int)
    undoRequested = Signal(int)
    forceRequested = Signal(int)
    mapRequested = Signal(str)
    keepExtraRequested = Signal(str)
    removeExtraRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme_css = ""
        self._banner: dict = {}
        self._feedback: dict = {"text": "", "role": "", "raw": ""}
        self._items: list = []
        self._extras: list = []
        self._history: list = []
        self._progress: dict = {}

    # --- out: Python -> JS -------------------------------------------------

    def _get_theme_css(self) -> str:
        return self._theme_css

    themeCss = Property(str, _get_theme_css, notify=themeCssChanged)

    def _get_banner(self) -> dict:
        return self._banner

    banner = Property("QVariantMap", _get_banner, notify=bannerChanged)

    def _get_feedback(self) -> dict:
        return self._feedback

    feedback = Property("QVariantMap", _get_feedback, notify=feedbackChanged)

    def _get_items(self) -> list:
        return self._items

    items = Property("QVariantList", _get_items, notify=itemsChanged)

    def _get_extras(self) -> list:
        return self._extras

    extras = Property("QVariantList", _get_extras, notify=extrasChanged)

    def _get_history(self) -> list:
        return self._history

    history = Property("QVariantList", _get_history, notify=historyChanged)

    def _get_progress(self) -> dict:
        return self._progress

    progress = Property("QVariantMap", _get_progress, notify=progressChanged)

    # --- in: JS -> Python --------------------------------------------------

    @Slot(int)
    def confirmItem(self, row) -> None:
        self.confirmRequested.emit(int(row))

    @Slot(int)
    def undoItem(self, row) -> None:
        self.undoRequested.emit(int(row))

    @Slot(int)
    def forceItem(self, row) -> None:
        self.forceRequested.emit(int(row))

    @Slot(str)
    def mapSku(self, sku) -> None:
        self.mapRequested.emit(str(sku))

    @Slot(str)
    def keepExtra(self, sku) -> None:
        self.keepExtraRequested.emit(str(sku))

    @Slot(str)
    def removeExtra(self, sku) -> None:
        self.removeExtraRequested.emit(str(sku))

    # --- Python-facing API -------------------------------------------------

    def set_theme_css(self, css: str) -> None:
        if css != self._theme_css:
            self._theme_css = css
            self.themeCssChanged.emit()

    def set_banner(self, payload: dict) -> None:
        self._banner = dict(payload or {})
        self.bannerChanged.emit()

    def set_feedback(self, text: str, role: str, raw: str) -> None:
        self._feedback = {"text": str(text), "role": str(role), "raw": str(raw)}
        self.feedbackChanged.emit()

    def set_items(self, rows: list) -> None:
        self._items = list(rows or [])
        self.itemsChanged.emit()

    def set_extras(self, rows: list) -> None:
        self._extras = list(rows or [])
        self.extrasChanged.emit()

    def set_history(self, rows: list) -> None:
        self._history = list(rows or [])
        self.historyChanged.emit()

    def set_progress(self, payload: dict) -> None:
        self._progress = dict(payload or {})
        self.progressChanged.emit()

    def flash(self, role: str) -> None:
        self.scanFlashed.emit(str(role))


def deny_focus(view: QWebEngineView) -> None:
    """Take the keyboard away from the view and from its focus proxy.

    The scanner invariant (ADR 0001): a QWebEngineView holding keyboard focus
    swallows every scan silently. The policy has to go on the proxy too -- that
    is the child widget a click actually lands on -- and the proxy is created
    lazily with the page, so callers re-assert this on show rather than trusting
    one call at construction.
    """
    view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    proxy = view.focusProxy()
    if proxy is not None:
        proxy.setFocusPolicy(Qt.FocusPolicy.NoFocus)


def mount_packer_page(view: QWebEngineView) -> PackerBridge:
    """Load the order document into `view` and return the bridge it talks to.

    The theme is written into the page before it loads, so the first paint is
    already themed, then pushed through the bridge on every theme or density
    change, so the document repaints without a reload. Both the bridge and the
    channel are parented to `view` and die with it.

    The view never takes keyboard focus (ADR 0001's scanner invariant); see
    deny_focus().
    """
    bridge = PackerBridge(view)
    channel = QWebChannel(view)
    channel.registerObject(CHANNEL_NAME, bridge)
    view.page().setWebChannel(channel)

    deny_focus(view)

    def _push_theme(_tokens) -> None:
        # gui.theme's tokens, not the argument: only those carry the bundled
        # Inter family the Qt tier renders in.
        bridge.set_theme_css(theme_css_vars(current_tokens()))

    on_theme_changed(view, _push_theme)  # runs once now, then on every change

    html = PAGE.read_text(encoding="utf-8").replace(THEME_MARKER, bridge.themeCss)
    view.setHtml(html, QUrl.fromLocalFile(str(WEB_DIR) + "/"))
    # The focus proxy is created lazily -- often only once the view is shown
    # and the page has actually loaded -- so the call above can run before it
    # exists. Re-assert once loading finishes to catch that proxy too.
    view.page().loadFinished.connect(lambda _ok: deny_focus(view))
    return bridge
