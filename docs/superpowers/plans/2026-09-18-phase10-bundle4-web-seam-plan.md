# Phase 10 Bundle 4 — web seam and order document: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Packer Mode's order document out of Qt tables and onto a
`QWebEngineView` fed by a `QWebChannel` bridge, so the whole document — banner,
feedback band, extras, SKU list with per-item actions, and the side column —
renders from the artboard's own CSS, and delete every Qt widget it replaces.

**Architecture:** `PackerModeWidget` keeps its public methods and signals and
becomes the Qt chrome plus the document's model. It pushes that model over
`gui/packer_bridge.py` (one channel object: notify properties out, slots in) to
`gui/web/packer.{html,css,js}`. Payload shaping lives in pure module-level
functions in the bridge module, so the numbers are testable without Qt or
Chromium. `main_window.py` is untouched except where it reached into a deleted
widget.

**Tech Stack:** Python 3.11, PySide6 6.7+ (QtWebEngine via the PySide6
metapackage), pytest + pytest-qt, ruff, PyInstaller (`main.spec`).

**Spec:** `docs/superpowers/specs/2026-09-18-phase10-bundle4-web-seam-design.md`
— read it before Task 1; it carries the four owner decisions (S1–S4) this plan
implements.

## Global Constraints

- **Repo:** packing-tool only. Do not edit anything under `shared/` — it is
  one-way synced from this repo into shopify-fulfillment-tool, and this bundle
  needs no change there.
- **Colour and size:** no hex, no colour name, no `px`/`pt` literal in any new
  `.py`, `.css`, `.html` or `.js` file. Everything comes from
  `theme_css_vars()`'s custom properties: `var(--surface)`, `var(--text)`,
  `var(--spacing-md)`, `var(--type-body-size)`, `var(--row-height)` and so on.
  `tests/test_style_literals_guard.py` already scans `gui/` and will fail
  otherwise.
- **Banned in web assets** (enforced by `shared/style_lint.py`): `box-shadow`,
  gradients, `transition`, `transform`, `scale`/`rotate`/`translate`,
  `opacity`. `animation` and `@keyframes` are allowed (spec S4) as long as the
  properties they animate are not on that list.
- **One mono face:** `var(--font-family-mono)` for SKUs and order numbers only.
- **The artboard is the brief:** `docs/design/phase10/packer-mode.html` (frames
  P2–P7) and `docs/design/phase10/packer-document.css`. Markup, class names and
  copy come from there. Do not invent a different structure.
- **Density:** floor (44px controls, 12pt body). Already the app default via
  `gui/theme.PACKING_DENSITY`; nothing to set.
- **Python entry point for every command below:** `.venv/bin/python` (a bare
  `python` is not on PATH; in a worktree the `.venv` symlink already exists).
- **Tests:** run the suite as
  `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`, exactly that form. A local
  `pytest-guard` hook on this machine refuses anything else for this repo, and
  `tests/conftest.py`'s own `setdefault` is not enough for it.
- **Commit style:** conventional prefix, present tense, one task per commit.
  Never commit to `main`; the branch is `worktree-phase10-bundle4`.

## File structure

| File | Responsibility |
|---|---|
| `gui/packer_bridge.py` (create) | `PackerBridge` (the channel object), `mount_packer_page(view)`, and the pure payload functions `item_rows`, `banner_payload`, `summary_lines`. |
| `gui/web/packer.html` (create) | The document's markup: the artboard's `.doc` subtree, the theme marker, the script tags. |
| `gui/web/packer.css` (create) | `docs/design/phase10/packer-document.css` lifted, plus the `.btn`/`.chip`/`.card`/`.state-panel` rule sets from `artboard.css` and the scan-flash keyframes. |
| `gui/web/packer.js` (create) | The `QWebChannel` bootstrap and one render function per region. No state beyond the last render. |
| `gui/packer_mode_widget.py` (modify) | Qt chrome (scanner, Skip, Exit, sim group) plus the document model; the same public methods and signals as today. |
| `gui/main_window.py` (modify) | `flash_border` targets the bridge instead of `table_frame`. Nothing else. |
| `main.spec` (modify) | `('gui/web', 'gui/web')` in `datas`. |
| `.github/workflows/build-release.yml` (modify) | `QtWebEngineProcess.exe` and `packer.html` join the bundled-asset check. |
| `requirements.txt` (modify) | A comment on why `PySide6` must stay the metapackage. |
| `tests/test_packer_payload.py` (create) | The pure payload functions. No Qt. |
| `tests/test_packer_bridge.py` (create) | The bridge and page over a real Chromium. |
| `tests/test_packer_scanner_focus.py` (create) | The D3 scanner invariant. |
| `tests/test_webengine_available.py` (create) | QtWebEngine stays installed. |

---

### Task 1: The item payload

`item_rows` is the one place that decides an item's state and which actions it
offers. Everything else renders what it says.

**Files:**
- Create: `gui/packer_bridge.py`
- Test: `tests/test_packer_payload.py`

**Interfaces:**
- Consumes: `packing_tool.packer_logic.normalize_sku(sku) -> str` (already
  exists).
- Produces: `item_rows(items, order_state, sku_map) -> list[dict]`.
  `items` is the list of product dicts `PackerLogic.start_order_packing`
  returns (keys `SKU`, `Product_Name`, `Quantity`); `order_state` is
  `PackerLogic.current_order_state` — a list of
  `{original_sku, normalized_sku, required, packed, row}`; `sku_map` is
  `PackerLogic.sku_map`, normalised barcode → SKU. Each returned row is
  `{"row": int, "product": str, "sku": str, "required": int, "packed": int,
  "state": "pending"|"partial"|"complete", "just_changed": False,
  "confirm": bool, "undo": bool, "force": bool, "map": bool}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_packer_payload.py
"""The order document's payload: pure functions, no Qt, no Chromium.

Spec: docs/superpowers/specs/2026-09-18-phase10-bundle4-web-seam-design.md
"""

from gui.packer_bridge import item_rows

ITEMS = [
    {"SKU": "TS-4409-B", "Product_Name": "Wireless Mouse", "Quantity": 3},
    {"SKU": "TS-9002-C", "Product_Name": "Desk Lamp", "Quantity": 2},
    {"SKU": "BX-3311-A", "Product_Name": "Laptop Stand", "Quantity": 8},
]


def _state(*packed):
    return [
        {
            "original_sku": item["SKU"],
            "normalized_sku": item["SKU"].replace("-", "").upper(),
            "required": int(item["Quantity"]),
            "packed": p,
            "row": i,
        }
        for i, (item, p) in enumerate(zip(ITEMS, packed))
    ]


def test_state_follows_packed_against_required():
    rows = item_rows(ITEMS, _state(3, 1, 0), {})
    assert [r["state"] for r in rows] == ["complete", "partial", "pending"]


def test_a_complete_row_offers_undo_and_nothing_else_but_map():
    row = item_rows(ITEMS, _state(3, 0, 0), {})[0]
    assert (row["confirm"], row["undo"], row["force"]) == (False, True, False)


def test_confirm_shows_while_the_row_is_unfinished():
    rows = item_rows(ITEMS, _state(0, 1, 0), {})
    assert [r["confirm"] for r in rows] == [True, True, True]


def test_undo_appears_only_once_something_is_packed():
    rows = item_rows(ITEMS, _state(0, 1, 0), {})
    assert [r["undo"] for r in rows] == [False, True, False]


def test_force_needs_more_than_five_required_and_an_unfinished_row():
    rows = item_rows(ITEMS, _state(0, 0, 0), {})
    assert [r["force"] for r in rows] == [False, False, True]
    finished = item_rows(ITEMS, _state(0, 0, 8), {})
    assert finished[2]["force"] is False


def test_map_shows_only_for_a_sku_no_barcode_maps_to():
    rows = item_rows(ITEMS, _state(0, 0, 0), {"4006381333931": "TS-4409-B"})
    assert [r["map"] for r in rows] == [False, True, True]


def test_an_item_with_no_state_entry_reads_as_nothing_packed():
    rows = item_rows(ITEMS, [], {})
    assert [(r["packed"], r["state"]) for r in rows] == [
        (0, "pending"),
        (0, "pending"),
        (0, "pending"),
    ]


def test_a_non_numeric_quantity_counts_as_one():
    rows = item_rows([{"SKU": "X", "Product_Name": "Odd", "Quantity": ""}], [], {})
    assert rows[0]["required"] == 1


def test_rows_carry_no_just_changed_tint_by_default():
    assert all(r["just_changed"] is False for r in item_rows(ITEMS, _state(1, 1, 1), {}))
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_packer_payload.py -v`
Expected: collection error — `No module named 'gui.packer_bridge'`.

- [ ] **Step 3: Write the module with just this function**

Create `gui/packer_bridge.py`:

```python
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

from typing import Any

from packing_tool.packer_logic import normalize_sku

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
```

- [ ] **Step 4: Run the tests and the linter**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_packer_payload.py -v && .venv/bin/python -m ruff check gui/packer_bridge.py`
Expected: all PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add gui/packer_bridge.py tests/test_packer_payload.py
git commit -m "feat(packer): the item payload decides state and row actions"
```

---

### Task 2: The banner and summary payloads

**Files:**
- Modify: `gui/packer_bridge.py`
- Test: `tests/test_packer_payload.py`

**Interfaces:**
- Produces:
  - `banner_payload(order_number, metadata) -> dict` —
    `{"order": str, "chips": list[str], "notes": str}`. Chips are bare values in
    the artboard's order: order type, courier, destination country,
    `f"Box {value}"`, then one chip per tag (`tags` followed by
    `internal_tags`). `nan`, `None` and blank values are dropped.
  - `summary_lines(rows) -> dict` — takes Task 1's rows and returns
    `{"items_packed": int, "items_total": int, "skus_packed": int,
    "skus_total": int}`, deduplicating by SKU (a Shopify export can repeat a
    SKU across rows).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_packer_payload.py`:

```python
from gui.packer_bridge import banner_payload, summary_lines

META = {
    "order_type": "Retail",
    "shipping_provider": "DPD",
    "destination_country": "PL",
    "order_min_box": "M",
    "tags": ["repeat customer"],
    "internal_tags": ["checked"],
    "notes": "Fragile -- handle with care",
}


def test_the_banner_carries_bare_values_in_artboard_order():
    assert banner_payload("10429", META) == {
        "order": "10429",
        "chips": ["Retail", "DPD", "PL", "Box M", "repeat customer", "checked"],
        "notes": "Fragile -- handle with care",
    }


def test_pandas_nan_and_blanks_never_reach_a_chip():
    payload = banner_payload("1", {
        "order_type": "nan",
        "shipping_provider": "",
        "destination_country": None,
        "order_min_box": "L",
        "tags": ["nan", "urgent"],
        "notes": "nan",
    })
    assert payload == {"order": "1", "chips": ["Box L", "urgent"], "notes": ""}


def test_a_system_note_stands_in_for_a_missing_note():
    assert banner_payload("1", {"system_note": "Split shipment"})["notes"] == (
        "Split shipment"
    )


def test_no_metadata_still_names_the_order():
    assert banner_payload("10429", None) == {
        "order": "10429",
        "chips": [],
        "notes": "",
    }


def test_the_summary_dedupes_repeated_skus():
    rows = [
        {"sku": "A", "required": 2, "packed": 2},
        {"sku": "A", "required": 1, "packed": 0},
        {"sku": "B", "required": 4, "packed": 4},
    ]
    assert summary_lines(rows) == {
        "items_packed": 6,
        "items_total": 7,
        "skus_packed": 1,
        "skus_total": 2,
    }


def test_an_empty_order_summarises_to_zeroes():
    assert summary_lines([]) == {
        "items_packed": 0,
        "items_total": 0,
        "skus_packed": 0,
        "skus_total": 0,
    }
```

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_packer_payload.py -v`
Expected: FAIL — `cannot import name 'banner_payload'`.

- [ ] **Step 3: Implement both functions**

Append to `gui/packer_bridge.py`:

```python
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
```

- [ ] **Step 4: Run the tests and the linter**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_packer_payload.py -v && .venv/bin/python -m ruff check gui/packer_bridge.py`
Expected: all PASS, ruff clean.

- [ ] **Step 5: Commit**

```bash
git add gui/packer_bridge.py tests/test_packer_payload.py
git commit -m "feat(packer): banner and summary payloads"
```

---

### Task 3: The bridge, the page, and the scanner invariant

The page renders nothing yet but the theme. This task is where the seam — and
the D3 focus rule the whole bundle rests on — gets proven.

**Files:**
- Modify: `gui/packer_bridge.py`
- Create: `gui/web/packer.html`, `gui/web/packer.css`, `gui/web/packer.js`
- Modify: `gui/packer_mode_widget.py`
- Test: `tests/test_packer_bridge.py`, `tests/test_packer_scanner_focus.py`

**Interfaces:**
- Consumes: `shared.theme.theme_css_vars(tokens)`,
  `shared.theme.on_theme_changed(widget, apply)`,
  `gui.theme.current_tokens()` (the app's tokens, which carry the bundled Inter
  family — `shared.theme.current_tokens()` deliberately omits it).
- Produces:
  - `PackerBridge(QObject)` with notify properties `themeCss`, `banner`,
    `feedback`, `items`, `extras`, `history`, `progress`; Python-side setters
    `set_theme_css`, `set_banner`, `set_feedback`, `set_items`, `set_extras`,
    `set_history`, `set_progress`; the JS-facing signal `scanFlashed(str)` and
    the method `flash(role)` that emits it.
  - `mount_packer_page(view) -> PackerBridge` and `deny_focus(view)`.
  - `PAGE`, `THEME_MARKER`, `CHANNEL_NAME` module constants.
  - `PackerModeWidget.document_view` — the `QWebEngineView` — and
    `PackerModeWidget.bridge`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_packer_bridge.py
"""The bridge and the page, driven through a real Chromium (ADR 0001).

CI runs the suite on windows-latest, where QtWebEngine needs no extra runtime
packages. Never mark these skip -- a bridge nobody can run is a bridge nobody
guards.
"""

import time

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from pytestqt.exceptions import TimeoutError as QtBotTimeoutError

from gui.packer_bridge import PAGE, THEME_MARKER, mount_packer_page
from gui.theme import apply_theme
from shared.theme import THEME_DARK, THEME_LIGHT


def _eval(qtbot, view, expr, timeout=5000):
    box = []
    view.page().runJavaScript(expr, 0, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=timeout)
    return box[0]


def _until_js(qtbot, view, expr, timeout_s=20):
    # A cold Chromium spin-up under CI load can outlast one round trip; keep
    # retrying against this function's own deadline.
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


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_packer_page(view)
    view.resize(1366, 700)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


def test_the_page_carries_the_theme_marker_exactly_once():
    assert PAGE.read_text(encoding="utf-8").count(THEME_MARKER) == 1


def test_the_first_paint_is_already_themed(page, qtbot):
    view, _ = page
    assert _eval(qtbot, view, "document.getElementById('theme-vars').textContent") != ""


def test_a_theme_switch_repaints_without_a_reload(page, qtbot, qapp):
    view, _ = page

    def css():
        return _eval(qtbot, view, "document.getElementById('theme-vars').textContent")

    before = css()
    assert "--surface" in before
    apply_theme(qapp, THEME_LIGHT)
    try:
        qtbot.waitUntil(lambda: css() != before, timeout=10000)
    finally:
        apply_theme(qapp, THEME_DARK)


def test_the_view_never_takes_keyboard_focus(page):
    from PySide6.QtCore import Qt

    view, _ = page
    assert view.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert view.focusProxy() is None or (
        view.focusProxy().focusPolicy() == Qt.FocusPolicy.NoFocus
    )
```

```python
# tests/test_packer_scanner_focus.py
"""D3, the scanner invariant: a click inside the web view must not eat scans.

Barcode scanners are keyboard wedges typing into a hidden QLineEdit. A
QWebEngineView takes keyboard focus when clicked, which would swallow every
scan after the packer touches the document once. This test is the gate; the
owner confirms the same with a real scanner on a Windows build.
"""

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from gui.packer_mode_widget import PackerModeWidget


def test_a_scan_still_reaches_the_widget_after_a_click_in_the_document(qtbot):
    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.resize(1366, 700)
    widget.show()
    qtbot.waitExposed(widget)

    seen = []
    widget.barcode_scanned.connect(seen.append)

    view = widget.document_view
    QTest.mouseClick(
        view.focusProxy() or view, Qt.MouseButton.LeftButton, pos=view.rect().center()
    )
    qtbot.wait(100)

    widget.set_focus_to_scanner()
    QTest.keyClicks(widget.scanner_input, "4006381333931")
    QTest.keyClick(widget.scanner_input, Qt.Key.Key_Return)

    assert seen == ["4006381333931"]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_packer_bridge.py tests/test_packer_scanner_focus.py -v`
Expected: FAIL — `cannot import name 'mount_packer_page'` and no
`document_view` attribute.

- [ ] **Step 3: Write the page's markup**

Create `gui/web/packer.html`. Structure and class names come from
`docs/design/phase10/packer-mode.html` frame P3 (read it — it is the brief):

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Packer Mode</title>
<!-- gui/packer_bridge.py writes theme_css_vars() over the marker before the
     page loads, then packer.js keeps it current from the bridge. -->
<style id="theme-vars">/* theme-vars */</style>
<link rel="stylesheet" href="packer.css">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="packer.js" defer></script>
</head>
<body>
<div class="doc">
  <div class="doc-main" id="doc-main">
    <div class="doc-banner" id="banner" hidden></div>
    <div class="feedback" id="feedback">
      <span class="feedback__text" id="feedback-text">Scan an order barcode</span>
      <span class="feedback__raw" id="feedback-raw"></span>
    </div>
    <div class="extras" id="extras" hidden>
      <div class="extras-title">Extra items scanned</div>
      <div id="extras-rows"></div>
    </div>
    <div class="sku-list" id="sku-list" hidden></div>
  </div>
  <div class="side">
    <div class="side-block">
      <div class="side-block-title">Session progress</div>
      <div class="progress-track"><div class="progress-fill" id="progress-fill"></div></div>
      <div class="progress-numbers" id="progress-numbers">0 / 0 orders &middot; 0 / 0 items</div>
    </div>
    <div class="side-block history">
      <div class="side-block-title">History</div>
      <div id="history-rows"><div class="history-row"><span class="history-row__order">No orders yet</span></div></div>
    </div>
    <div class="side-block">
      <div class="side-block-title">Summary</div>
      <div class="summary-line"><span>Unique SKUs packed</span><strong id="summary-skus">0 / 0</strong></div>
    </div>
  </div>
</div>
</body>
</html>
```

- [ ] **Step 4: Lift the stylesheet**

```bash
mkdir -p gui/web
cp docs/design/phase10/packer-document.css gui/web/packer.css
```

Then edit `gui/web/packer.css`:

1. Replace the file's opening comment with one naming it as the lifted
   artboard CSS and pointing at the spec and `docs/design/phase10/HANDOFF.md`.
2. Copy these rule sets **verbatim** from `docs/design/phase10/artboard.css`,
   which `HANDOFF.md`'s A3 note requires (they are used inside `.doc` but were
   never copied into `packer-document.css`): `.btn`, `.btn--primary`,
   `.btn--danger`, `.btn--ghost`, `.btn:disabled`, `.chip`, `.chip::before`,
   `.chip--hollow::before`, `.chip--info`, `.chip--success`, `.chip--warning`,
   `.chip--danger`, `.chip--neutral`, the four `.chip--*.chip--tint` rules,
   `.card`, `.state-panel`, `.state-panel-title`, `.state-panel-body`,
   `.state-panel-actions`, `.state-panel-mono`.
3. Replace the `.frame--1920 .doc { --side-width: 380px; }` rule — the
   artboard's frame wrapper does not exist in the app — with the width query
   it stood for:

```css
@media (min-width: 1600px) {
  .doc { --side-width: 380px; }
}
```

4. Add the page-level rules the artboard got from its frame, and S4's flash.
   The document column carries a transparent border at all times so a flash
   shifts no layout:

```css
html, body { height: 100%; margin: 0; }

.doc-main { border: 2px solid transparent; }

/* The scan cue (spec S4). Only border-color animates: transition, transform
   and opacity are banned in a web asset by shared/style_lint.py, animation
   is not. */
@keyframes scan-flash {
  0%, 100% { border-color: transparent; }
  50% { border-color: var(--flash, var(--border)); }
}
.doc-main[data-flash] { animation: scan-flash 300ms ease-out 2; }
.doc-main[data-flash="success"] { --flash: var(--status-success); }
.doc-main[data-flash="warning"] { --flash: var(--status-warning); }
.doc-main[data-flash="danger"] { --flash: var(--status-danger); }

.feedback--success { --role: var(--status-success); background: var(--status-success-bg); }
.feedback--warning { --role: var(--status-warning); background: var(--status-warning-bg); }
```

(`.feedback--success`, `--danger` and `--info` already exist in the lifted file;
`--warning` does not and the app needs it.)

- [ ] **Step 5: Write the page's script**

Create `gui/web/packer.js`:

```javascript
// Packer Mode's order document (Bundle 4). The page renders what the bridge
// sends and decides nothing: item state and row actions are decided in
// gui/packer_bridge.py. Spec:
// docs/superpowers/specs/2026-09-18-phase10-bundle4-web-seam-design.md
"use strict";

const els = {};
const state = { bridge: null };

function onTheme() {
  els.themeVars.textContent = state.bridge.themeCss;
}

function renderFeedback() {
  const fb = state.bridge.feedback || {};
  els.feedbackText.textContent = fb.text || "";
  els.feedbackRaw.textContent = fb.raw || "";
  els.feedback.className = "feedback" + (fb.role ? " feedback--" + fb.role : "");
}

function flash(role) {
  // Remove, force a reflow, re-add: an animation already running would
  // otherwise ignore the new scan.
  delete els.docMain.dataset.flash;
  void els.docMain.offsetWidth;
  els.docMain.dataset.flash = role;
}

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.packer;
  state.bridge = bridge;
  els.themeVars = document.getElementById("theme-vars");
  els.docMain = document.getElementById("doc-main");
  els.feedback = document.getElementById("feedback");
  els.feedbackText = document.getElementById("feedback-text");
  els.feedbackRaw = document.getElementById("feedback-raw");

  onTheme();
  bridge.themeCssChanged.connect(onTheme);
  bridge.feedbackChanged.connect(renderFeedback);
  bridge.scanFlashed.connect(flash);
  els.docMain.addEventListener("animationend", function () {
    delete els.docMain.dataset.flash;
  });

  renderFeedback();
  window.packerBridge = bridge;
  document.documentElement.dataset.bridge = "ready";
});
```

- [ ] **Step 6: Write the bridge and the mount**

Append to `gui/packer_bridge.py` (keep the payload functions above it):

```python
from pathlib import Path

from PySide6.QtCore import Property, QObject, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.theme import current_tokens
from shared.theme import on_theme_changed, theme_css_vars

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
    return bridge
```

Add `Qt` to the `PySide6.QtCore` import line.

- [ ] **Step 7: Put the view in the widget**

In `gui/packer_mode_widget.py`, inside `__init__` after `main_layout` is
created, add the document view as the first thing in the left column — the old
Qt panels stay for now and later tasks delete them region by region:

```python
        from gui.packer_bridge import mount_packer_page

        self.document_view = QWebEngineView(self)
        self.bridge = mount_packer_page(self.document_view)
        left_layout.addWidget(self.document_view, 1)
```

Import `QWebEngineView` from `PySide6.QtWebEngineWidgets` at the top of the
file. Keep `mount_packer_page` a local import inside `__init__`: the module
pulls in Chromium, and `gui/packer_bridge.py` imports from `gui.theme`, so a
top-level import here risks an import cycle.

Then re-assert the focus rule every time the screen appears -- the view's focus
proxy is created lazily, so one call at construction is not enough, and this is
also where today's code already wants the scanner focused:

```python
    def showEvent(self, event):
        """Re-assert the scanner's claim on the keyboard every time we appear."""
        super().showEvent(event)
        from gui.packer_bridge import deny_focus

        deny_focus(self.document_view)
        self.set_focus_to_scanner()
```

- [ ] **Step 8: Run both test files**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_packer_bridge.py tests/test_packer_scanner_focus.py -v`
Expected: all PASS. If Chromium fails to start under `offscreen`, re-run that
file alone — it is the same engine `docs/design/phase10` was rendered with, so
it does work on this VM.

- [ ] **Step 9: Run the whole suite and the style lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q && .venv/bin/python -m ruff check .`
Expected: PASS. `tests/test_style_literals_guard.py` now scans the new web
assets — if it flags one, replace the literal with a `var(--…)`, never add an
allow comment.

- [ ] **Step 10: Commit**

```bash
git add gui/packer_bridge.py gui/web gui/packer_mode_widget.py tests/test_packer_bridge.py tests/test_packer_scanner_focus.py
git commit -m "feat(packer): the web seam, the themed page, and the scanner invariant"
```

---

### Task 4: The feedback band, the raw scan, and the scan flash

This lands before the SKU list on purpose: it is what frees `main_window.py`
from `table_frame`, which Task 5 deletes.

**Files:**
- Modify: `gui/packer_mode_widget.py`, `gui/main_window.py`, `gui/web/packer.js`
- Test: `tests/test_packer_bridge.py`

**Interfaces:**
- Consumes: `PackerBridge.set_feedback(text, role, raw)`,
  `PackerBridge.flash(role)`.
- Produces: `PackerModeWidget.show_notification(text, role)` and
  `.update_raw_scan_display(text)` unchanged in signature, now pushing to the
  bridge; `MainWindow.flash_border(color)` unchanged in signature, now calling
  `bridge.flash(role)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_packer_bridge.py`:

```python
def test_a_notification_reaches_the_band_with_its_role(page, qtbot):
    view, bridge = page
    bridge.set_feedback("ITEM OK", "success", "TS-4409-B")
    _until_js(
        qtbot,
        view,
        "document.getElementById('feedback-text').textContent === 'ITEM OK'",
    )
    assert _eval(qtbot, view, "document.getElementById('feedback').className") == (
        "feedback feedback--success"
    )
    assert _eval(
        qtbot, view, "document.getElementById('feedback-raw').textContent"
    ) == "TS-4409-B"


def test_a_cleared_notification_leaves_the_band_neutral(page, qtbot):
    view, bridge = page
    bridge.set_feedback("ITEM OK", "success", "X")
    _until_js(qtbot, view, "document.getElementById('feedback').className.includes('success')")
    bridge.set_feedback("", "", "X")
    _until_js(qtbot, view, "document.getElementById('feedback').className === 'feedback'")


def test_a_flash_marks_the_document_column_and_clears_itself(page, qtbot):
    view, bridge = page
    bridge.flash("danger")
    _until_js(
        qtbot,
        view,
        "document.getElementById('doc-main').dataset.flash === 'danger'",
    )
    _until_js(
        qtbot,
        view,
        "document.getElementById('doc-main').dataset.flash === undefined",
    )
```

Add to `tests/test_packer_payload.py`:

```python
from gui.packer_bridge import flash_role


def test_every_flash_colour_names_a_status_role():
    assert flash_role("green") == "success"
    assert flash_role("orange") == "warning"
    assert flash_role("red") == "danger"


def test_an_unknown_flash_colour_raises_rather_than_passing_through():
    import pytest

    with pytest.raises(KeyError):
        flash_role("purple")
```

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_packer_bridge.py tests/test_packer_payload.py -v`
Expected: FAIL — `cannot import name 'flash_role'`, and the band tests fail
because nothing sets the band.

- [ ] **Step 3: Add `flash_role` to the bridge module**

In `gui/packer_bridge.py`, next to the payload functions:

```python
# main_window.flash_border() has always been called with a colour word. The
# document speaks in status roles, so the translation lives here rather than in
# a dict on MainWindow. An unknown word raises: a silently-passed-through value
# would emit a role no CSS rule matches.
_FLASH_ROLES = {"green": "success", "orange": "warning", "red": "danger"}


def flash_role(color: str) -> str:
    """The status role for one of flash_border()'s colour words."""
    return _FLASH_ROLES[color]
```

- [ ] **Step 4: Point the widget's two methods at the bridge**

In `gui/packer_mode_widget.py`, replace the bodies of `show_notification` and
`update_raw_scan_display` (keep the signatures and update the docstrings):

```python
    def show_notification(self, text: str, role: str):
        """Show the scan outcome in the document's feedback band.

        Args:
            text: The message. Empty clears the band.
            role: A shared.theme status role -- "status_success",
                "status_warning", "status_danger", "status_info" -- or
                "transparent" to clear. Both spellings are accepted because
                main_window has called it both ways since before the band
                existed.
        """
        self._feedback_text = text
        self._feedback_role = "" if role == "transparent" or not text else (
            role.removeprefix("status_")
        )
        self._push_feedback()

    def update_raw_scan_display(self, text: str):
        """Show the raw text of the last scan beside the outcome."""
        self._raw_scan = text
        self._push_feedback()

    def _push_feedback(self):
        self.bridge.set_feedback(
            self._feedback_text, self._feedback_role, self._raw_scan
        )
```

In `__init__`, before the view is mounted, seed the three fields:

```python
        self._feedback_text = "Scan an order barcode"
        self._feedback_role = "info"
        self._raw_scan = ""
```

and after `self.bridge = mount_packer_page(...)`, call `self._push_feedback()`.

- [ ] **Step 5: Rewrite `flash_border`**

In `gui/main_window.py`, replace `flash_border`'s body (lines around 993–1010)
and delete `_FLASH_COLORS` and `_FRAME_DEFAULT_STYLE` (around 984–989) along
with the now-unused `QTimer` import there if nothing else uses it — check with
`grep -n "QTimer" gui/main_window.py` first; several other call sites do use
it, so most likely it stays:

```python
    def flash_border(self, color: str):
        """Flash the order document's edge with the scan's outcome.

        Args:
            color (str): "green", "red" or "orange". Anything else raises --
                a silently-passed-through value would emit a role no CSS rule
                matches, and would sail past style_lint.
        """
        self.packer_mode_widget.bridge.flash(flash_role(color))
```

Import it: `from gui.packer_bridge import flash_role`.

- [ ] **Step 6: Delete the Qt feedback widgets**

Remove from `gui/packer_mode_widget.py` the whole `scan_info_frame` block and
everything inside it: `status_label`, `notification_label`, `raw_scan_label`,
the `raw_scan_title` label, `_order_section`, `_feed_section` and `_divider`.
Drop `QFont` from the imports if nothing else uses it, and update the class
docstring's attribute list.

- [ ] **Step 7: Render the band's states in the page**

`renderFeedback` in `gui/web/packer.js` already does this — confirm it maps
`role` to `feedback--<role>` and leaves the class bare when `role` is empty.
Nothing to add unless Step 1's tests say otherwise.

- [ ] **Step 8: Run the suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q && .venv/bin/python -m ruff check .`
Expected: PASS. Nothing outside the widget may still name the deleted labels:
`grep -n "status_label\|notification_label" gui/` should return nothing.

- [ ] **Step 9: Commit**

```bash
git add gui/packer_bridge.py gui/packer_mode_widget.py gui/main_window.py gui/web/packer.js tests/
git commit -m "feat(packer): the feedback band, the raw scan, and the scan flash"
```

---

### Task 5: The SKU list

**Files:**
- Modify: `gui/packer_mode_widget.py`, `gui/web/packer.js`
- Test: `tests/test_packer_bridge.py`

**Interfaces:**
- Consumes: `item_rows`, `summary_lines`, `PackerBridge.set_items`,
  `.set_banner`.
- Produces: `PackerModeWidget.display_order(items, order_state, metadata=None,
  sku_map=None)` and `.update_item_row(row, packed_count, is_complete)`
  unchanged in signature, now driving `self._rows` (Task 1's payload) and the
  bridge. New private attribute `self._rows: list[dict]`.

**Deletes:** `table`, `table_frame`, `FRAME_DEFAULT_STYLE`,
`_make_actions_widget`, `metadata_banner` with its six `_meta_*_lbl` chips and
`_update_metadata_banner`, `main_tabs` (the tab container exists only to hold
the table and the summary — both gone by Task 7), and the `QTableWidget`,
`QTableWidgetItem`, `QHeaderView`, `QAbstractItemView`, `QStyle`, `QSize`,
`QColor`, `QPalette` imports if nothing else in the file still uses them.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_packer_bridge.py`:

```python
ITEMS = [
    {"SKU": "TS-4409-B", "Product_Name": "Wireless Mouse", "Quantity": 3},
    {"SKU": "BX-3311-A", "Product_Name": "Laptop Stand", "Quantity": 8},
]
STATE = [
    {"original_sku": "TS-4409-B", "normalized_sku": "TS4409B", "required": 3,
     "packed": 3, "row": 0},
    {"original_sku": "BX-3311-A", "normalized_sku": "BX3311A", "required": 8,
     "packed": 1, "row": 1},
]


def test_the_list_draws_one_row_per_item_with_its_state(page, qtbot):
    from gui.packer_bridge import item_rows

    view, bridge = page
    bridge.set_items(item_rows(ITEMS, STATE, {}))
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 2")
    assert _eval(
        qtbot, view, "document.querySelectorAll('.sku-row')[0].className"
    ).split() == ["sku-row", "sku-row--complete"]
    assert _eval(
        qtbot, view, "document.querySelectorAll('.sku-row')[1].className"
    ).split() == ["sku-row", "sku-row--partial"]


def test_a_row_shows_product_sku_and_the_packed_count(page, qtbot):
    from gui.packer_bridge import item_rows

    view, bridge = page
    bridge.set_items(item_rows(ITEMS, STATE, {}))
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 2")
    assert _eval(
        qtbot,
        view,
        "document.querySelector('.sku-row__product').textContent",
    ) == "Wireless Mouse"
    assert _eval(
        qtbot, view, "document.querySelector('.sku-row__sku').textContent"
    ) == "TS-4409-B"
    assert _eval(
        qtbot, view, "document.querySelector('.sku-row__qty').textContent"
    ) == "3 / 3"


def test_each_state_carries_the_artboard_s_chip(page, qtbot):
    from gui.packer_bridge import item_rows

    view, bridge = page
    bridge.set_items(item_rows(ITEMS, STATE, {}))
    _until_js(qtbot, view, "document.querySelectorAll('.chip').length === 2")
    assert _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.chip')).map(c => c.textContent)",
    ) == ["Complete", "Partial"]


def test_the_row_a_scan_landed_on_is_tinted(page, qtbot):
    from gui.packer_bridge import item_rows

    view, bridge = page
    rows = item_rows(ITEMS, STATE, {})
    rows[1]["just_changed"] = True
    bridge.set_items(rows)
    _until_js(
        qtbot,
        view,
        "document.querySelectorAll('.sku-row--just-changed').length === 1",
    )


def test_an_empty_list_hides_the_section(page, qtbot):
    view, bridge = page
    bridge.set_items([])
    _until_js(qtbot, view, "document.getElementById('sku-list').hidden === true")
```

And a widget-level test in the same file:

```python
def test_display_order_then_a_scan_updates_only_that_row(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.display_order(ITEMS, STATE, metadata={"shipping_provider": "DPD"})
    widget.update_item_row(1, 2, False)

    rows = widget.bridge.items
    assert [(r["packed"], r["state"]) for r in rows] == [(3, "complete"), (2, "partial")]
    assert [r["just_changed"] for r in rows] == [False, True]
    assert widget.bridge.banner["chips"] == ["DPD"]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_packer_bridge.py -v`
Expected: FAIL — no `.sku-row` in the page, and `display_order` still builds a
table.

- [ ] **Step 3: Render the list in the page**

Add to `gui/web/packer.js`:

```javascript
const CHIP = {
  complete: { text: "Complete", cls: "chip chip--success chip--hollow" },
  partial: { text: "Partial", cls: "chip chip--warning chip--tint chip--hollow" },
  pending: { text: "Pending", cls: "chip chip--neutral chip--hollow" },
};

function span(cls, text) {
  const el = document.createElement("span");
  el.className = cls;
  el.textContent = text;
  return el;
}

function actionButton(label, action, row, sku) {
  const btn = document.createElement("button");
  btn.className = "btn btn--ghost";
  btn.type = "button";
  btn.textContent = label;
  btn.dataset.action = action;
  btn.dataset.row = row;
  btn.dataset.sku = sku;
  return btn;
}

function renderItems() {
  const rows = state.bridge.items || [];
  els.skuList.textContent = "";
  els.skuList.hidden = rows.length === 0;
  rows.forEach(function (r) {
    const row = document.createElement("div");
    row.className =
      "sku-row sku-row--" + r.state + (r.just_changed ? " sku-row--just-changed" : "");
    row.appendChild(span("sku-row__product", r.product));
    row.appendChild(span("sku-row__sku", r.sku));
    row.appendChild(span("sku-row__qty", r.packed + " / " + r.required));
    const chip = CHIP[r.state];
    row.appendChild(span(chip.cls, chip.text));
    const actions = document.createElement("span");
    actions.className = "row-actions";
    // Label "Force", not "Force confirm": three buttons have to share the
    // row's 190px actions slot (spec S2).
    if (r.confirm) actions.appendChild(actionButton("Confirm", "confirm", r.row, r.sku));
    if (r.undo) actions.appendChild(actionButton("Undo", "undo", r.row, r.sku));
    if (r.force) actions.appendChild(actionButton("Force", "force", r.row, r.sku));
    if (r.map) actions.appendChild(actionButton("Map SKU", "map", r.row, r.sku));
    row.appendChild(actions);
    els.skuList.appendChild(row);
  });
}

function renderBanner() {
  const b = state.bridge.banner || {};
  const chips = b.chips || [];
  els.banner.textContent = "";
  els.banner.hidden = !b.order && chips.length === 0 && !b.notes;
  if (b.order) els.banner.appendChild(span("doc-banner-order", "#" + b.order));
  chips.forEach(function (c) {
    els.banner.appendChild(span("doc-banner-tag", c));
  });
  if (b.notes) els.banner.appendChild(span("doc-banner-notes", b.notes));
}
```

In the channel callback, add the element lookups and connections:

```javascript
  els.skuList = document.getElementById("sku-list");
  els.banner = document.getElementById("banner");
  bridge.itemsChanged.connect(renderItems);
  bridge.bannerChanged.connect(renderBanner);
  renderItems();
  renderBanner();
```

- [ ] **Step 4: Rewrite the widget's two display methods**

In `gui/packer_mode_widget.py`, replace `display_order` and `update_item_row`:

```python
    def display_order(
        self,
        items: list[dict[str, Any]],
        order_state: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
        sku_map: dict[str, str] | None = None,
    ):
        """Show one order in the document.

        Args:
            items: The order's product dicts, as PackerLogic returns them.
            order_state: PackerLogic.current_order_state for this order.
            metadata: Order-level metadata for the banner.
            sku_map: Normalised barcode -> SKU, for the Map SKU action.
        """
        self._items = list(items)
        self._sku_map = dict(sku_map or {})
        self._rows = item_rows(self._items, order_state, self._sku_map)
        order_number = items[0].get(
            "Order_Number", items[0].get("order_number", "")
        ) if items else ""
        self.bridge.set_banner(banner_payload(order_number, metadata))
        self._push_rows()
        self.skip_order_button.setEnabled(True)
        self.set_focus_to_scanner()

    def update_item_row(self, row: int, packed_count: int, is_complete: bool):
        """Update one item's packed count after a scan or a manual action.

        Args:
            row: The item's index, as PackerLogic reports it.
            packed_count: The item's new packed count.
            is_complete: Whether this item is now fully packed. Kept in the
                signature because every existing call site passes it; the row's
                state is derived from packed against required, so the two can
                never disagree.
        """
        if not 0 <= row < len(self._rows):
            logger.warning("Cannot update row %s: no such item in this order", row)
            return
        target = self._rows[row]
        target["packed"] = packed_count
        for candidate in self._rows:
            candidate["just_changed"] = candidate is target
        self._rows = item_rows(
            self._items,
            [
                {"row": r["row"], "packed": r["packed"]}
                for r in self._rows
            ],
            self._sku_map,
        )
        self._rows[row]["just_changed"] = True
        self._push_rows()

    def _push_rows(self):
        """Send the item rows and the numbers derived from them."""
        self.bridge.set_items(self._rows)
        self._push_progress()
```

Add to `__init__`, before the mount: `self._items = []`, `self._rows = []`,
`self._sku_map = {}`. Import the payload functions at the top of the file:
`from gui.packer_bridge import banner_payload, item_rows, summary_lines`.

`_push_progress` arrives in Task 7 — for now define it as a one-line method
that does nothing but is called, and Task 7 fills it in:

```python
    def _push_progress(self):
        """The side column's numbers. Task 7 fills this in."""
```

- [ ] **Step 5: Delete the table**

Remove from `gui/packer_mode_widget.py`: the `table_frame`/`table` construction
block, `FRAME_DEFAULT_STYLE`, `_make_actions_widget`, the `metadata_banner`
block with its six `_meta_*_lbl` chips and the `_update_metadata_banner` method
(`banner_payload` replaces it), and `main_tabs` (add `summary_frame` straight
to `left_layout` for now; Task 7 deletes it). Update the class docstring's
attribute list to drop what is gone.

- [ ] **Step 6: Run the suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q && .venv/bin/python -m ruff check .`
Expected: PASS. If ruff reports an unused import in
`gui/packer_mode_widget.py`, remove it — but re-check afterwards: this sandbox
runs a formatter that strips an import added in one edit before its use is
added in the next, so add an import and its usage in the same edit.

- [ ] **Step 7: Commit**

```bash
git add gui/packer_mode_widget.py gui/web/packer.js tests/test_packer_bridge.py
git commit -m "feat(packer): the SKU list replaces the items table"
```

---

### Task 6: The row actions

**Files:**
- Modify: `gui/packer_mode_widget.py`, `gui/web/packer.js`
- Test: `tests/test_packer_bridge.py`

**Interfaces:**
- Consumes: `PackerBridge.confirmRequested(int)`, `.undoRequested(int)`,
  `.forceRequested(int)`, `.mapRequested(str)`.
- Produces: the widget's existing signals, unchanged —
  `barcode_scanned(str)` (manual confirm re-emits the row's SKU, exactly as
  today's Confirm button did), `cancel_item_requested(int)`,
  `force_confirm_requested(int)`, `map_sku_requested(str)`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_packer_bridge.py`:

```python
def test_a_confirm_click_re_emits_the_row_s_sku_as_a_scan(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.display_order(ITEMS, STATE)
    seen = []
    widget.barcode_scanned.connect(seen.append)
    widget.bridge.confirmItem(1)
    assert seen == ["BX-3311-A"]


def test_an_undo_click_asks_nothing_and_reaches_the_cancel_signal(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.display_order(ITEMS, STATE)
    seen = []
    widget.cancel_item_requested.connect(seen.append)
    widget.bridge.undoItem(1)
    assert seen == [1]


def test_a_force_click_confirms_first(qtbot, monkeypatch):
    from PySide6.QtWidgets import QDialog

    from gui import packer_mode_widget as module
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.display_order(ITEMS, STATE)
    seen = []
    widget.force_confirm_requested.connect(seen.append)

    monkeypatch.setattr(
        module.ConfirmDialog, "exec", lambda self: QDialog.DialogCode.Rejected
    )
    widget.bridge.forceItem(1)
    assert seen == []

    monkeypatch.setattr(
        module.ConfirmDialog, "exec", lambda self: QDialog.DialogCode.Accepted
    )
    widget.bridge.forceItem(1)
    assert seen == [1]


def test_a_map_click_carries_the_original_sku(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.display_order(ITEMS, STATE)
    seen = []
    widget.map_sku_requested.connect(seen.append)
    widget.bridge.mapSku("BX-3311-A")
    assert seen == ["BX-3311-A"]


def test_clicking_a_row_action_in_the_page_calls_its_slot(page, qtbot):
    from gui.packer_bridge import item_rows

    view, bridge = page
    calls = []
    bridge.confirmRequested.connect(calls.append)
    bridge.set_items(item_rows(ITEMS, STATE, {}))
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 2")
    view.page().runJavaScript(
        "document.querySelector('[data-action=\"confirm\"]').click()"
    )
    qtbot.waitUntil(lambda: calls == [1], timeout=5000)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_packer_bridge.py -v`
Expected: FAIL — no bridge connections in the widget, no click handler in the
page.

- [ ] **Step 3: Delegate the clicks in the page**

Add to `gui/web/packer.js`, inside the channel callback:

```javascript
  els.skuList.addEventListener("click", function (event) {
    const btn = event.target.closest("[data-action]");
    if (!btn) return;
    const row = Number(btn.dataset.row);
    if (btn.dataset.action === "confirm") bridge.confirmItem(row);
    else if (btn.dataset.action === "undo") bridge.undoItem(row);
    else if (btn.dataset.action === "force") bridge.forceItem(row);
    else if (btn.dataset.action === "map") bridge.mapSku(btn.dataset.sku);
  });
```

- [ ] **Step 4: Wire the bridge to the widget's handlers**

In `gui/packer_mode_widget.py`, after the mount:

```python
        self.bridge.confirmRequested.connect(self._on_manual_confirm)
        self.bridge.undoRequested.connect(self._on_cancel_item)
        self.bridge.forceRequested.connect(self._on_force_confirm)
        self.bridge.mapRequested.connect(self._on_map_sku_requested)
```

Replace the three handlers (`_on_manual_confirm` now takes a row, since the
page reports rows):

```python
    def _on_manual_confirm(self, row: int):
        """Confirm one item by hand -- the same as scanning its SKU."""
        if 0 <= row < len(self._rows):
            self.barcode_scanned.emit(self._rows[row]["sku"])
        self.set_focus_to_scanner()

    def _on_cancel_item(self, row: int):
        """Undo the last scan for one item.

        No confirmation: undoing a scan is undone by scanning again, and a
        confirm is for acts Undo cannot reach (shared.components.ConfirmDialog).
        """
        self.cancel_item_requested.emit(row)
        self.set_focus_to_scanner()

    def _on_force_confirm(self, row: int):
        """Force-confirm every remaining unit of one item. Not undoable."""
        if not 0 <= row < len(self._rows):
            return
        item = self._rows[row]
        remaining = item["required"] - item["packed"]
        dialog = ConfirmDialog(
            self,
            title="Force confirm this item?",
            body=(
                f"{item['product']} ({item['sku']}): {remaining} of "
                f"{item['required']} still unscanned. Forcing marks them packed "
                "without a scan, and cannot be undone."
            ),
            verb="Force confirm",
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.force_confirm_requested.emit(row)
        self.set_focus_to_scanner()
```

Import `from shared.components.confirm_dialog import ConfirmDialog` and add
`QDialog` to the `PySide6.QtWidgets` imports; drop `QMessageBox` if nothing
else in the file uses it.

- [ ] **Step 5: Run the suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q && .venv/bin/python -m ruff check .`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gui/packer_mode_widget.py gui/web/packer.js tests/test_packer_bridge.py
git commit -m "feat(packer): row actions cross the bridge"
```

---

### Task 7: The side column — progress, history, summary

**Files:**
- Modify: `gui/packer_mode_widget.py`, `gui/web/packer.js`
- Test: `tests/test_packer_bridge.py`

**Interfaces:**
- Consumes: `summary_lines(rows)`, `PackerBridge.set_progress`,
  `.set_history`.
- Produces: `PackerModeWidget.update_session_progress(completed, total)` and
  `.add_order_to_history(order_number, status="")` unchanged in signature;
  `_push_progress` filled in. Progress payload:
  `{"orders_done", "orders_total", "items_packed", "items_total",
  "skus_packed", "skus_total"}`. History rows:
  `{"order": str, "status": "complete"|"skipped"}`, newest first.

**Deletes:** `session_progress_bar`, `packed_stat_label`, `items_stat_label`,
`history_table`, `summary_frame`, `summary_table`, `_update_summary_panel`,
`_refresh_summary_from_table`, and the whole right-hand `stats_row`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_packer_bridge.py`:

```python
def test_the_side_column_shows_orders_items_and_unique_skus(page, qtbot):
    view, bridge = page
    bridge.set_progress(
        {
            "orders_done": 8,
            "orders_total": 13,
            "items_packed": 41,
            "items_total": 66,
            "skus_packed": 19,
            "skus_total": 34,
        }
    )
    _until_js(
        qtbot,
        view,
        "document.getElementById('progress-numbers').textContent.includes('8 / 13')",
    )
    assert _eval(
        qtbot, view, "document.getElementById('progress-numbers').textContent"
    ) == "8 / 13 orders · 41 / 66 items"
    assert _eval(
        qtbot, view, "document.getElementById('summary-skus').textContent"
    ) == "19 / 34"
    assert _eval(
        qtbot, view, "document.getElementById('progress-fill').style.width"
    ) == "61.5385%"


def test_no_orders_yet_leaves_the_bar_empty_and_says_so(page, qtbot):
    view, bridge = page
    bridge.set_progress({"orders_done": 0, "orders_total": 0})
    _until_js(qtbot, view, "document.getElementById('progress-fill').style.width === '0%'")
    assert _eval(
        qtbot, view, "document.getElementById('history-rows').textContent"
    ).strip() == "No orders yet"


def test_history_lists_newest_first_with_a_status_chip(page, qtbot):
    view, bridge = page
    bridge.set_history(
        [{"order": "10429", "status": "complete"}, {"order": "10428", "status": "skipped"}]
    )
    _until_js(qtbot, view, "document.querySelectorAll('.history-row').length === 2")
    assert _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.history-row__order'))"
        ".map(e => e.textContent)",
    ) == ["#10429", "#10428"]
    assert _eval(
        qtbot, view, "document.querySelectorAll('.history-row .chip')[1].textContent"
    ) == "Skipped"


def test_the_widget_pushes_orders_and_item_numbers_together(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.display_order(ITEMS, STATE)
    widget.update_session_progress(8, 13)
    progress = widget.bridge.progress
    assert (progress["orders_done"], progress["orders_total"]) == (8, 13)
    assert (progress["items_packed"], progress["items_total"]) == (4, 11)
    assert (progress["skus_packed"], progress["skus_total"]) == (1, 2)


def test_a_skipped_order_is_marked_as_such_in_history(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.add_order_to_history("10428")
    widget.add_order_to_history("10429", "[SKIPPED]")
    assert widget.bridge.history == [
        {"order": "10429", "status": "skipped"},
        {"order": "10428", "status": "complete"},
    ]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_packer_bridge.py -v`
Expected: FAIL — the page never renders progress or history, and the widget
still writes to Qt tables.

- [ ] **Step 3: Render the side column**

Add to `gui/web/packer.js`:

```javascript
function renderProgress() {
  const p = state.bridge.progress || {};
  const done = p.orders_done || 0;
  const total = p.orders_total || 0;
  const pct = total > 0 ? (done / total) * 100 : 0;
  // Trailing zeroes trimmed so a whole percentage reads as "50%".
  els.progressFill.style.width = String(Number(pct.toFixed(4))) + "%";
  els.progressNumbers.textContent =
    done + " / " + total + " orders · " +
    (p.items_packed || 0) + " / " + (p.items_total || 0) + " items";
  els.summarySkus.textContent = (p.skus_packed || 0) + " / " + (p.skus_total || 0);
}

const HISTORY_CHIP = {
  complete: { text: "Complete", cls: "chip chip--success chip--hollow" },
  skipped: { text: "Skipped", cls: "chip chip--danger" },
};

function renderHistory() {
  const rows = state.bridge.history || [];
  els.historyRows.textContent = "";
  if (rows.length === 0) {
    const empty = document.createElement("div");
    empty.className = "history-row";
    empty.appendChild(span("history-row__order", "No orders yet"));
    els.historyRows.appendChild(empty);
    return;
  }
  rows.forEach(function (r) {
    const row = document.createElement("div");
    row.className = "history-row";
    row.appendChild(span("history-row__order", "#" + r.order));
    const chip = HISTORY_CHIP[r.status] || HISTORY_CHIP.complete;
    row.appendChild(span(chip.cls, chip.text));
    els.historyRows.appendChild(row);
  });
}
```

and in the channel callback:

```javascript
  els.progressFill = document.getElementById("progress-fill");
  els.progressNumbers = document.getElementById("progress-numbers");
  els.summarySkus = document.getElementById("summary-skus");
  els.historyRows = document.getElementById("history-rows");
  bridge.progressChanged.connect(renderProgress);
  bridge.historyChanged.connect(renderHistory);
  renderProgress();
  renderHistory();
```

- [ ] **Step 4: Fill in the widget's side**

In `gui/packer_mode_widget.py`:

```python
    def update_session_progress(self, completed: int, total: int):
        """Update the session's order counts in the side column.

        Args:
            completed: Orders finished in this session.
            total: Orders in the session.
        """
        self._orders_done = completed
        self._orders_total = total
        self._push_progress()

    def add_order_to_history(self, order_number: str, status: str = ""):
        """Add an order to the top of the session's history.

        Args:
            order_number: The order that was just scanned.
            status: "[SKIPPED]" for a skipped order; empty for a completed one.
        """
        self._history.insert(
            0,
            {
                "order": str(order_number),
                "status": "skipped" if status == "[SKIPPED]" else "complete",
            },
        )
        self.bridge.set_history(self._history)

    def _push_progress(self):
        """The side column's numbers: orders from the session, items from the rows."""
        self.bridge.set_progress(
            {
                "orders_done": self._orders_done,
                "orders_total": self._orders_total,
                **summary_lines(self._rows),
            }
        )
```

Seed in `__init__`: `self._orders_done = 0`, `self._orders_total = 0`,
`self._history = []`.

- [ ] **Step 5: Delete the Qt side**

Remove `session_progress_bar`, the `stats_row` with `packed_stat_label` and
`items_stat_label`, `history_table` and its container, `summary_frame`,
`summary_table`, `_update_summary_panel`, `_refresh_summary_from_table`, the
`_BOTTOM_ROW_HEIGHT` constant and `_bottom_row`/`_right_bottom` scaffolding
that held them. Update the class docstring. Keep `skip_order_button`,
`exit_button` and the sim group — Bundle 5 places those.

- [ ] **Step 6: Run the suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q && .venv/bin/python -m ruff check .`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add gui/packer_mode_widget.py gui/web/packer.js tests/test_packer_bridge.py
git commit -m "feat(packer): progress, history and summary move to the side column"
```

---

### Task 8: Extras

**Files:**
- Modify: `gui/packer_mode_widget.py`, `gui/web/packer.js`
- Test: `tests/test_packer_bridge.py`

**Interfaces:**
- Consumes: `PackerBridge.set_extras`, `.keepExtraRequested(str)`,
  `.removeExtraRequested(str)`.
- Produces: `PackerModeWidget.show_extras_panel(extras)` unchanged in
  signature — `extras` is `PackerLogic.current_extra_items`, a
  `{normalised_sku: count}` dict. Payload rows:
  `{"sku": str, "count": int}`.

**Deletes:** `extras_panel`, `extras_table`, `_extras_section_title`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_packer_bridge.py`:

```python
def test_extras_appear_above_the_list_with_keep_and_remove(page, qtbot):
    view, bridge = page
    bridge.set_extras([{"sku": "BX-9910-Z", "count": 1}, {"sku": "TS-1200-A", "count": 2}])
    _until_js(qtbot, view, "document.querySelectorAll('.extras-row').length === 2")
    assert _eval(qtbot, view, "document.getElementById('extras').hidden") is False
    assert _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.extras-row .sku-row__qty'))"
        ".map(e => e.textContent)",
    ) == ["× 1", "× 2"]
    assert _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.extras-row .btn'))"
        ".map(b => b.textContent)",
    ) == ["Keep", "Remove", "Keep", "Remove"]


def test_no_extras_hides_the_section(page, qtbot):
    view, bridge = page
    bridge.set_extras([{"sku": "X", "count": 1}])
    _until_js(qtbot, view, "document.getElementById('extras').hidden === false")
    bridge.set_extras([])
    _until_js(qtbot, view, "document.getElementById('extras').hidden === true")


def test_keep_and_remove_carry_the_normalised_sku(page, qtbot):
    view, bridge = page
    kept, removed = [], []
    bridge.keepExtraRequested.connect(kept.append)
    bridge.removeExtraRequested.connect(removed.append)
    bridge.set_extras([{"sku": "BX9910Z", "count": 1}])
    _until_js(qtbot, view, "document.querySelectorAll('.extras-row').length === 1")
    view.page().runJavaScript(
        "document.querySelector('[data-action=\"keep\"]').click()"
    )
    qtbot.waitUntil(lambda: kept == ["BX9910Z"], timeout=5000)
    view.page().runJavaScript(
        "document.querySelector('[data-action=\"remove\"]').click()"
    )
    qtbot.waitUntil(lambda: removed == ["BX9910Z"], timeout=5000)


def test_the_widget_turns_the_extras_dict_into_rows(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.show_extras_panel({"BX9910Z": 1, "TS1200A": 2})
    assert widget.bridge.extras == [
        {"sku": "BX9910Z", "count": 1},
        {"sku": "TS1200A", "count": 2},
    ]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_packer_bridge.py -v`
Expected: FAIL — no `.extras-row` in the page.

- [ ] **Step 3: Render the extras**

Add to `gui/web/packer.js`:

```javascript
function renderExtras() {
  const rows = state.bridge.extras || [];
  els.extrasRows.textContent = "";
  els.extras.hidden = rows.length === 0;
  rows.forEach(function (r) {
    const row = document.createElement("div");
    row.className = "extras-row";
    // The extras row reuses the SKU row's grid, so it needs the same five
    // cells: the product name is unknown for a scan the order does not
    // contain, and the status cell stays empty (artboard P6).
    row.appendChild(span("sku-row__product", ""));
    row.appendChild(span("sku-row__sku", r.sku));
    row.appendChild(span("sku-row__qty", "× " + r.count));
    row.appendChild(span("", ""));
    const actions = document.createElement("span");
    actions.className = "row-actions";
    actions.appendChild(actionButton("Keep", "keep", -1, r.sku));
    actions.appendChild(actionButton("Remove", "remove", -1, r.sku));
    row.appendChild(actions);
    els.extrasRows.appendChild(row);
  });
}
```

and in the channel callback:

```javascript
  els.extras = document.getElementById("extras");
  els.extrasRows = document.getElementById("extras-rows");
  bridge.extrasChanged.connect(renderExtras);
  els.extrasRows.addEventListener("click", function (event) {
    const btn = event.target.closest("[data-action]");
    if (!btn) return;
    if (btn.dataset.action === "keep") bridge.keepExtra(btn.dataset.sku);
    else if (btn.dataset.action === "remove") bridge.removeExtra(btn.dataset.sku);
  });
  renderExtras();
```

- [ ] **Step 4: Rewrite the widget's extras method**

```python
    def show_extras_panel(self, extras: dict[str, int]):
        """Show the items scanned into this order that it does not contain.

        Args:
            extras: PackerLogic.current_extra_items -- normalised SKU to count.
        """
        self.bridge.set_extras(
            [{"sku": sku, "count": count} for sku, count in (extras or {}).items()]
        )
```

Wire the two slots after the mount:

```python
        self.bridge.keepExtraRequested.connect(self._on_extra_confirmed)
        self.bridge.removeExtraRequested.connect(self._on_extra_removed)
```

Delete `extras_panel`, `extras_table` and `_extras_section_title` and their
construction block; update the class docstring.

- [ ] **Step 5: Run the suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q && .venv/bin/python -m ruff check .`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gui/packer_mode_widget.py gui/web/packer.js tests/test_packer_bridge.py
git commit -m "feat(packer): the extras section moves to the document"
```

---

### Task 9: `clear_screen`, and the last of the Qt document

**Files:**
- Modify: `gui/packer_mode_widget.py`
- Test: `tests/test_packer_bridge.py`

**Interfaces:**
- Produces: `PackerModeWidget.clear_screen()` unchanged in signature: it resets
  the document to the waiting state (artboard P2 — the feedback band alone,
  the side column still showing the session) and keeps the history and the
  order counts, which belong to the session and not to the order.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_packer_bridge.py`:

```python
def test_clearing_the_screen_returns_to_waiting_and_keeps_the_session(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.update_session_progress(8, 13)
    widget.add_order_to_history("10428")
    widget.display_order(ITEMS, STATE, metadata={"shipping_provider": "DPD"})
    widget.show_extras_panel({"X": 1})

    widget.clear_screen()

    assert widget.bridge.items == []
    assert widget.bridge.extras == []
    assert widget.bridge.banner == {"order": "", "chips": [], "notes": ""}
    assert widget.bridge.feedback["text"] == "Scan the next order's barcode"
    assert widget.bridge.history == [{"order": "10428", "status": "complete"}]
    assert widget.bridge.progress["orders_done"] == 8


def test_clearing_the_screen_re_enables_the_scanner_and_disables_skip(qtbot):
    from gui.packer_mode_widget import PackerModeWidget

    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.display_order(ITEMS, STATE)
    widget.scanner_input.setEnabled(False)
    widget.clear_screen()
    assert widget.scanner_input.isEnabled() is True
    assert widget.skip_order_button.isEnabled() is False


def test_the_waiting_document_shows_no_list_and_no_banner(page, qtbot):
    view, bridge = page
    bridge.set_items([])
    bridge.set_banner({"order": "", "chips": [], "notes": ""})
    _until_js(qtbot, view, "document.getElementById('sku-list').hidden === true")
    assert _eval(qtbot, view, "document.getElementById('banner').hidden") is True
```

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_packer_bridge.py -v`
Expected: FAIL — `clear_screen` still clears Qt widgets that no longer exist.

- [ ] **Step 3: Rewrite `clear_screen`**

```python
    def clear_screen(self):
        """Reset the document to waiting for the next order.

        The session's history and order counts stay: they belong to the
        session, not to the order that just ended.
        """
        self._items = []
        self._rows = []
        self._sku_map = {}
        self.bridge.set_banner(banner_payload("", None))
        self.bridge.set_extras([])
        self.scanner_input.clear()
        self.scanner_input.setEnabled(True)
        self.skip_order_button.setEnabled(False)
        self._raw_scan = ""
        self.show_notification("Scan the next order's barcode", "status_info")
        self._push_rows()
        self.set_focus_to_scanner()
```

- [ ] **Step 4: Run the suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q && .venv/bin/python -m ruff check .`
Expected: PASS. Every Qt document widget should now be gone — verify:

```bash
grep -n "QTableWidget\|summary_table\|history_table\|notification_label\|metadata_banner\|session_progress_bar" gui/packer_mode_widget.py
```

Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add gui/packer_mode_widget.py tests/test_packer_bridge.py
git commit -m "feat(packer): clear_screen resets the document, not a table"
```

---

### Task 10: Packaging and the build guards

**Files:**
- Modify: `requirements.txt`, `main.spec`,
  `.github/workflows/build-release.yml`
- Create: `tests/test_webengine_available.py`

**Interfaces:**
- Consumes: nothing.
- Produces: a frozen build that contains `gui/web` and
  `QtWebEngineProcess.exe`, and a test that fails if QtWebEngine stops being
  installed.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_webengine_available.py
"""QtWebEngine must stay installed for the order document (ADR 0001).

It arrives via PySide6-Addons, which the PySide6 metapackage depends on --
nothing names it directly, so a well-meaning switch to PySide6-Essentials would
remove it silently and only break the frozen Windows build.

find_spec, not import: this test guards packaging, not runtime. Runtime is
tests/test_packer_bridge.py, which drives a real Chromium.
"""

import importlib.util


def test_qtwebengine_widgets_is_installed():
    assert importlib.util.find_spec("PySide6.QtWebEngineWidgets") is not None, (
        "PySide6.QtWebEngineWidgets is missing -- check that requirements.txt "
        "still installs the PySide6 metapackage and not PySide6-Essentials."
    )
```

- [ ] **Step 2: Run it**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_webengine_available.py -v`
Expected: PASS immediately — the metapackage is already installed. This test
guards a future change, so it passes the day it is written; that is the point.

- [ ] **Step 3: Say why the requirement must stay a metapackage**

In `requirements.txt`, replace the bare `PySide6` line with:

```
PySide6                # Keep the METAPACKAGE, not PySide6-Essentials: QtWebEngine
                       # (Packer Mode's order document, ADR 0001) ships in
                       # PySide6-Addons, which only the metapackage pulls in.
                       # tests/test_webengine_available.py guards this.
```

- [ ] **Step 4: Ship the page in the frozen build**

In `main.spec`, add the web directory to `datas`:

```python
    datas=[
        ('shared/assets', 'shared/assets'),
        ('gui/web', 'gui/web'),
        ('config.ini.example', '.'),
    ],
```

- [ ] **Step 5: Guard the build**

In `.github/workflows/build-release.yml`, extend the "Verify bundled assets
shipped" step's list and its comment:

```yaml
      - name: Verify bundled assets shipped
        # A missing gui/assets does not degrade: icon() raises during
        # MainWindow construction, and --windowed means the user double-clicks
        # an exe that silently never opens.
        #
        # QtWebEngineProcess.exe and packer.html are the same shape of problem
        # for the order document: PyInstaller's hook-PySide6.QtWebEngineCore is
        # supposed to collect the helper process, and if it silently does not,
        # the only symptom is a dead view discovered over RDP after a full
        # build and a several-hundred-MB download. Fail here instead.
        shell: pwsh
        run: |
          foreach ($name in "package.svg", "Inter-Regular.ttf", "QtWebEngineProcess.exe", "packer.html") {
            if (-not (Get-ChildItem -Path "dist\Packers-Assistant" -Recurse -Filter $name)) {
              throw "PyInstaller did not bundle $name -- the app would not start."
            }
          }
```

- [ ] **Step 6: Run the suite and check the spec parses**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q && .venv/bin/python -m ruff check . && .venv/bin/python -c "import ast, pathlib; ast.parse(pathlib.Path('main.spec').read_text())"`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add requirements.txt main.spec .github/workflows/build-release.yml tests/test_webengine_available.py
git commit -m "build(packer): ship the web tier and guard it in CI"
```

---

### Task 11: Verify it end to end, refresh the graph, and hand off

**Files:**
- Modify: whatever the checks below turn up.

- [ ] **Step 1: Run everything**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q
.venv/bin/python -m ruff check .
.venv/bin/python -m py_compile gui/*.py gui/session_browser/*.py packing_tool/*.py shared/*.py main.py
```

Expected: all PASS. Paste the pytest summary line into the commit or PR body —
do not claim a pass you have not seen.

- [ ] **Step 2: Render the document and look at it, in both themes**

Write a throwaway script under `$CLAUDE_JOB_DIR/tmp` (not in the repo) that
builds a `PackerModeWidget`, calls `display_order` with three or four items at
mixed packed counts, `show_extras_panel({"BX9910Z": 1})`,
`update_session_progress(8, 13)`, `add_order_to_history("10428")`,
`show_notification("ITEM OK", "status_success")`, then grabs
`widget.grab()` to a PNG — once per theme via `apply_theme(app, THEME_DARK)`
and `THEME_LIGHT`. Compare against `docs/design/phase10/packer-mode.html`
frames P3 and P6 and fix what does not match.

Two traps this has already cost a run: `MainWindow` needs
`skip_worker_selection=True` or it opens a real dialog and hangs under
`offscreen`; and a `QWebEngineView` needs a `loadFinished` wait plus a short
`app.processEvents()` spin before `grab()` returns anything but blank.

- [ ] **Step 3: Refresh the knowledge graph** (this repo's CLAUDE.md requires it
      right after changing code, not eventually)

```bash
graphify update .
```

- [ ] **Step 4: Commit whatever Step 2 fixed**

```bash
git add -A
git commit -m "fix(packer): match the artboard in both themes"
```

- [ ] **Step 5: Push and stop**

```bash
git push -u origin worktree-phase10-bundle4
```

Do **not** open the PR — that is Stage C's job, after a fresh-context review.
Leave for Stage C, in the handoff notes: the pytest summary, the two
screenshots' paths, and anything in the artboard you could not match and why.

---

## What Stage C must check

- The D3 test is the bundle's gate: `tests/test_packer_scanner_focus.py` must
  pass, and the PR body must ask the owner to scan with a real scanner on a
  Windows build **after clicking inside the web view**. Bundle 4 does not merge
  without that confirmation (spec, roadmap "Done when").
- `tests/test_style_literals_guard.py` covers the new web assets — no hex, no
  literal size, no `# style-lint: allow` added to get past it.
- No `transition`, `transform` or `opacity` anywhere in `gui/web/`:
  `grep -nE "transition|transform|opacity" gui/web/` should return nothing.
- D7: the bundle deleted two text-parsing paths (`update_item_row`'s quantity
  re-parse and `_refresh_summary_from_table`). If the implementer found another
  backend bug in `packing_tool/` along the way, it needs a regression test; if
  it was outside this bundle's code, it should be a GitHub issue, not a silent
  fix.
