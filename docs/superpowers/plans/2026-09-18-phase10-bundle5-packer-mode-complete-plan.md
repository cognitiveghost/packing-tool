# Phase 10 Bundle 5 — Packer Mode complete: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Packer Mode — the Qt chrome moves into a 60px command bar with a visible scanner field, a finished session says so in place of a modal, unmatched scans get rows you can map, and the copy becomes the artboard's.

**Architecture:** Bundle 4's seam, extended by one bridge property (`sessionEnd`), two slots (`endSession`, `exitPacking`) and two payload functions. `PackerModeWidget` swaps its left/right split for a bar-over-document column. `MainWindow` keeps every public call it makes today and gains the P8 payload and the reverse map-SKU dialog.

**Tech Stack:** PySide6 6.11.2 (QtWidgets + QtWebEngineWidgets + QtWebChannel), pytest + pytest-qt, vanilla ES5-style JS in `gui/web/`.

**Spec:** `docs/superpowers/specs/2026-09-18-phase10-bundle5-packer-mode-complete-design.md`
**Predecessor spec (read its S1 for why Bundle 5 is this shape):** `docs/superpowers/specs/2026-09-18-phase10-bundle4-web-seam-design.md`
**Mockup (the brief):** `docs/design/phase10/packer-mode.html` frames P2–P8

## Global Constraints

- **The only accepted test command in this repo is
  `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`.** A `PreToolUse` hook
  refuses `python -m pytest` and refuses *any* bash command whose text
  mentions the test runner — so if you need a heredoc or a script whose prose
  mentions it, write the file to `$CLAUDE_JOB_DIR/tmp` and run the file.
- `.venv` in this worktree is a symlink to the main checkout's. It works; do
  not recreate it.
- **Commit from the worktree with `git commit -F <file>`**, message written to
  a file first. A `cd X && git commit -F - <<EOF` form is refused as too
  complex to verify.
- **Never hand-edit `shared/`** — it is one-way synced from `../packing-tool`'s
  sibling. This bundle touches none of it.
- **No hex colours or px font sizes in `gui/web/`.** Colour and spacing come
  from `theme_css_vars()` tokens only. `tests/test_style_literals_guard.py`
  and `tests/test_style_lint.py` enforce it. `transition`, `transform`,
  `scale/rotate/translate`, `opacity`, gradients and `box-shadow` are banned
  on the web tier; `animation` / `@keyframes` are allowed (ADR 0001, amended).
- **No hardcoded colours in Qt stylesheets** — `gui/theme.current_tokens()`.
- **An auto-formatter runs on edit and strips an import whose usage has not
  landed yet.** Add an import and its first usage in the same edit.
- **Array assertions in `tests/test_packer_bridge.py` must go through that
  file's `_eval()` helper** — this build's `runJavaScript` returns `''` for a
  JS array.
- **Copy is sentence case**, says what happened then what to do, and an action
  keeps one name through a flow. No shouted capitals.
- `PackerModeWidget`'s existing public methods and signals keep their names and
  payloads. `MainWindow` call sites do not change except where this plan says.
- Run `graphify update .` after the last task.

---

### Task 1: `item_rows` trusts the saved state's `required`, and flags multi-unit lines

Two changes to one function: the D7 precedence fix and S4's cue flag.

**Files:**
- Modify: `gui/packer_bridge.py:39-79` (`item_rows`)
- Test: `tests/test_packer_payload.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `item_rows(items, order_state, sku_map) -> list[dict]` — each row
  gains `"multi": bool` and `"mapBarcode": False`, and `required` now prefers
  `order_state`'s own `required`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_packer_payload.py`:

```python
def test_the_saved_state_decides_required_not_the_packing_list():
    # PackerLogic decides completion from order_state['required']
    # (packer_logic.py:1027, 1038, 1096). On a resumed session whose saved
    # state disagrees with the packing list, the document has to agree with
    # the logic or it lies about which lines are done.
    state = _state(2, 0, 0)
    state[0]["required"] = 2
    rows = item_rows(ITEMS, state, {})
    assert rows[0]["required"] == 2
    assert rows[0]["state"] == "complete"


def test_a_state_entry_with_no_required_falls_back_to_the_packing_list():
    # packer_logic.py:440 writes required=0 when a restored entry has none.
    state = _state(0, 0, 0)
    state[0]["required"] = 0
    rows = item_rows(ITEMS, state, {})
    assert rows[0]["required"] == 3


def test_multi_flags_a_line_that_needs_more_than_one_scan():
    rows = item_rows(ITEMS, _state(0, 2, 8), {})
    # Desk Lamp is 2/2 and Laptop Stand 8/8 -- done, so the cue is spent.
    assert [r["multi"] for r in rows] == [True, False, False]


def test_a_single_unit_line_is_never_multi():
    rows = item_rows([{"SKU": "A", "Product_Name": "A", "Quantity": 1}], [], {})
    assert rows[0]["multi"] is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_payload.py`
Expected: FAIL — `KeyError: 'multi'` on the multi tests, and
`assert 3 == 2` on the precedence test.

- [ ] **Step 3: Rewrite the loop's state lookup**

In `gui/packer_bridge.py`, replace the `packed_by_row` block and the loop body's
`required`/`packed` lines. The dict now holds the whole state entry, not just
the packed count:

```python
    state_by_row = {_int(s.get("row"), -1): s for s in order_state or []}
    # A state entry with no usable row is dropped rather than mis-attributed to
    # row 0, which would credit another item's scans to the first line.
    state_by_row.pop(-1, None)
    mapped = {normalize_sku(v) for v in (sku_map or {}).values()}

    rows = []
    for index, item in enumerate(items):
        entry = state_by_row.get(index) or {}
        sku = str(item.get("SKU", ""))
        # PackerLogic decides completion from the state's own `required`, so
        # the document reads it first or it disagrees with the logic on a
        # resumed session. A restored entry can carry 0 for "not recorded"
        # (packer_logic.py:440), which falls through to the packing list.
        required = max(
            _int(entry.get("required"), 0) or _int(item.get("Quantity")), 1
        )
        packed = _int(entry.get("packed"), 0)
```

Then in the appended dict, add the two keys beside the existing flags:

```python
                "multi": required > 1 and packed < required,
                "map": normalize_sku(sku) not in mapped,
                "mapBarcode": False,
```

- [ ] **Step 4: Run the whole payload suite to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_payload.py`
Expected: PASS, all tests including Bundle 4's.

- [ ] **Step 5: Commit**

```bash
git add gui/packer_bridge.py tests/test_packer_payload.py
git commit -F <message file>
```

Message: `fix(packer): the saved state's required wins, and multi-unit lines are flagged`

---

### Task 2: `unknown_rows` — an unmatched scan becomes a row

**Files:**
- Modify: `gui/packer_bridge.py` (add after `item_rows`)
- Test: `tests/test_packer_payload.py`

**Interfaces:**
- Consumes: `item_rows`'s row shape from Task 1.
- Produces: `unknown_rows(scans: list[str]) -> list[dict]`, rows in the same
  shape `item_rows` emits, with `state="unknown"`, `row=-1`,
  `mapBarcode=True`.

- [ ] **Step 1: Write the failing tests**

```python
from gui.packer_bridge import item_rows, unknown_rows


def test_an_unmatched_scan_becomes_a_row_that_offers_only_mapping():
    rows = unknown_rows(["4006381333931"])
    assert len(rows) == 1
    row = rows[0]
    assert row["sku"] == "4006381333931"
    assert row["product"] == "Unknown SKU"
    assert row["state"] == "unknown"
    assert row["mapBarcode"] is True
    assert not any(row[flag] for flag in ("confirm", "undo", "force", "map"))


def test_the_same_barcode_scanned_twice_is_one_row_to_map():
    rows = unknown_rows(["999", "888", "999", " 999 ", ""])
    assert [r["sku"] for r in rows] == ["999", "888"]


def test_unknown_rows_carry_every_key_an_item_row_does():
    # They ride in the same `items` property, so the page can render both
    # with one function.
    item = item_rows([{"SKU": "A", "Product_Name": "A", "Quantity": 1}], [], {})[0]
    assert set(unknown_rows(["999"])[0]) == set(item)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_payload.py -k unknown`
Expected: FAIL — `ImportError: cannot import name 'unknown_rows'`

- [ ] **Step 3: Write the function**

Add to `gui/packer_bridge.py` after `item_rows`:

```python
def unknown_rows(scans: list[str]) -> list[dict[str, Any]]:
    """One row per unmatched scan, in scan order, each barcode once.

    PackerLogic.unknown_scans appends every scan in this order that matched no
    item and no mapping. The same wrong barcode scanned three times is one
    thing to map, not three. The rows carry item_rows()' shape so the page
    renders both lists with one function -- they ride in the same `items`
    property, and the only action an unmatched scan offers is mapping it.
    """
    seen: list[str] = []
    for scan in scans or []:
        text = str(scan).strip()
        if text and text not in seen:
            seen.append(text)
    return [
        {
            "row": -1,
            "product": "Unknown SKU",
            "sku": text,
            "required": 0,
            "packed": 0,
            "state": "unknown",
            "just_changed": False,
            "multi": False,
            "confirm": False,
            "undo": False,
            "force": False,
            "map": False,
            "mapBarcode": True,
        }
        for text in seen
    ]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_payload.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gui/packer_bridge.py tests/test_packer_payload.py
git commit -F <message file>
```

Message: `feat(packer): an unmatched scan becomes a row in the order document`

---

### Task 3: `session_end_payload` — P8's sentence

**Files:**
- Modify: `gui/packer_bridge.py` (add after `summary_lines`)
- Test: `tests/test_packer_payload.py`

**Interfaces:**
- Produces: `session_end_payload(packed: int, total: int, skipped: int, items: int, seconds: int) -> dict` returning `{"title": str, "body": str}`.

- [ ] **Step 1: Write the failing tests**

```python
from gui.packer_bridge import session_end_payload


def test_the_session_sentence_reads_like_the_artboard():
    payload = session_end_payload(
        packed=12, total=13, skipped=1, items=66, seconds=6480
    )
    assert payload["title"] == "Session complete"
    assert payload["body"] == "12 of 13 orders packed, 1 skipped, 66 items, in 1h 48m."


def test_nothing_skipped_says_nothing_about_skipping():
    body = session_end_payload(13, 13, 0, 66, 6480)["body"]
    assert "skipped" not in body
    assert body == "13 of 13 orders packed, 66 items, in 1h 48m."


def test_a_short_session_drops_the_hours_and_one_item_is_singular():
    assert session_end_payload(1, 1, 0, 1, 95)["body"] == (
        "1 of 1 orders packed, 1 item, in 1m."
    )


def test_an_unknown_start_time_leaves_the_duration_out():
    body = session_end_payload(2, 2, 0, 4, 0)["body"]
    assert body == "2 of 2 orders packed, 4 items."
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_payload.py -k session_end`
Expected: FAIL — `ImportError: cannot import name 'session_end_payload'`

- [ ] **Step 3: Write the functions**

Add to `gui/packer_bridge.py` after `summary_lines`:

```python
def _duration(seconds: int) -> str:
    """A session's length in the largest two units that are not zero."""
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m"
    return f"{secs}s"


def session_end_payload(
    packed: int, total: int, skipped: int, items: int, seconds: int
) -> dict[str, str]:
    """The state panel's title and sentence when the session is over (P8).

    The skipped clause appears only when something was skipped, and the
    duration only when the session's start time is known -- a sentence that
    reports "0 skipped, in 0s" tells the packer about nothing that happened.
    """
    parts = [f"{packed} of {total} orders packed"]
    if skipped:
        parts.append(f"{skipped} skipped")
    parts.append(f"{items} {'item' if items == 1 else 'items'}")
    if seconds:
        parts.append(f"in {_duration(seconds)}")
    return {"title": "Session complete", "body": ", ".join(parts) + "."}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_payload.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gui/packer_bridge.py tests/test_packer_payload.py
git commit -F <message file>
```

Message: `feat(packer): the session-complete sentence, built from the session's counts`

---

### Task 4: the bridge carries `sessionEnd` and the panel's two actions

**Files:**
- Modify: `gui/packer_bridge.py` (the `PackerBridge` class)
- Test: `tests/test_packer_bridge.py`

**Interfaces:**
- Consumes: `session_end_payload` from Task 3.
- Produces: on `PackerBridge` — `sessionEnd` property (`QVariantMap`),
  `set_session_end(payload: dict)`, slots `endSession()` / `exitPacking()`,
  signals `endSessionRequested` / `exitPackingRequested` / `sessionEndChanged`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_packer_bridge.py`:

```python
def test_the_page_reads_the_session_end_payload(qtbot, page):
    view, bridge = page
    assert _eval(qtbot, view, "window.packerBridge.sessionEnd") == {}
    bridge.set_session_end({"title": "Session complete", "body": "2 of 2 orders packed."})
    _until_js(qtbot, view, "window.packerBridge.sessionEnd.title === 'Session complete'")
```

That test needs the page to expose its bridge handle. In `gui/web/packer.js`'s
channel callback, beside `state.bridge = bridge`, add:

```js
  // The test harness drives the page through this handle; nothing in the
  // page reads it.
  window.packerBridge = bridge;
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_bridge.py -k session_end`
Expected: FAIL — `AttributeError: 'PackerBridge' object has no attribute 'set_session_end'`

- [ ] **Step 3: Add the property, the slots and the setter**

In `gui/packer_bridge.py`, in the signal block:

```python
    sessionEndChanged = Signal()
```

and in the Python-facing signal block:

```python
    endSessionRequested = Signal()
    exitPackingRequested = Signal()
```

In `__init__`:

```python
        self._session_end: dict = {}
```

With the other properties:

```python
    def _get_session_end(self) -> dict:
        return self._session_end

    # The eighth property, and the one Bundle 4 declined to add on spec: a
    # finished session is a state the document cannot infer from an empty
    # items list, because waiting for the next order looks exactly the same.
    sessionEnd = Property("QVariantMap", _get_session_end, notify=sessionEndChanged)
```

With the other slots:

```python
    @Slot()
    def endSession(self) -> None:
        self.endSessionRequested.emit()

    @Slot()
    def exitPacking(self) -> None:
        self.exitPackingRequested.emit()
```

With the other setters:

```python
    def set_session_end(self, payload: dict) -> None:
        self._session_end = dict(payload or {})
        self.sessionEndChanged.emit()
```

- [ ] **Step 4: Run the bridge suite to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_bridge.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gui/packer_bridge.py gui/web/packer.js tests/test_packer_bridge.py
git commit -F <message file>
```

Message: `feat(packer): the bridge carries a finished session and its two actions`

---

### Task 5: collapse the page's duplicated row and action code

Pure refactor, no behaviour change: the suite must stay green without a new
test. Bundle 4's handoff flagged this and named this bundle as the moment —
the unknown row is the third caller of row construction and the fifth action.

**Files:**
- Modify: `gui/web/packer.js:42-128, 184-198`

**Interfaces:**
- Produces: in `packer.js` — `rowEl(cls, cells, buttons)` and an `ACTIONS`
  table keyed by `dataset.action`, plus one `onActionClick` listener body.
  Later tasks add entries to `ACTIONS` and callers of `rowEl`.

- [ ] **Step 1: Run the bridge suite first, to have a green baseline**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_bridge.py`
Expected: PASS. Note the count; it must not change in step 4.

- [ ] **Step 2: Add `rowEl` and use it in both renderers**

Add after `actionButton`:

```js
function rowEl(cls, cells, buttons) {
  const row = document.createElement("div");
  row.className = cls;
  cells.forEach(function (cell) {
    row.appendChild(span(cell[0], cell[1]));
  });
  const actions = document.createElement("span");
  actions.className = "row-actions";
  buttons.forEach(function (btn) {
    actions.appendChild(btn);
  });
  row.appendChild(actions);
  return row;
}
```

`renderItems`' loop body becomes:

```js
  rows.forEach(function (r) {
    const chip = CHIP[r.state] || CHIP.pending;
    const buttons = [];
    // Label "Force", not "Force confirm": three buttons have to share the
    // row's 190px actions slot (Bundle 4 spec S2).
    if (r.confirm) buttons.push(actionButton("Confirm", "confirm", r.row, r.sku));
    if (r.undo) buttons.push(actionButton("Undo", "undo", r.row, r.sku));
    if (r.force) buttons.push(actionButton("Force", "force", r.row, r.sku));
    if (r.map) buttons.push(actionButton("Map SKU", "map", r.row, r.sku));
    const row = rowEl(
      "sku-row sku-row--" + r.state + (r.just_changed ? " sku-row--just-changed" : ""),
      [
        ["sku-row__product", r.product],
        ["sku-row__sku", r.sku],
        ["sku-row__qty", r.packed + " / " + r.required],
        [chip.cls, chip.text],
      ],
      buttons
    );
    if (r.just_changed) changed = row;
    els.skuList.appendChild(row);
  });
```

`renderExtras`' loop body becomes:

```js
  rows.forEach(function (r) {
    // The extras row reuses the SKU row's grid, but there is no product name
    // for a scan the order does not contain -- current_extra_items is
    // normalised-SKU-to-count. So the SKU spans the product and SKU tracks
    // (see .extras-row .sku-row__sku) and the status cell stays empty (P6).
    els.extrasRows.appendChild(
      rowEl(
        "extras-row",
        [["sku-row__sku", r.sku], ["sku-row__qty", "× " + r.count], ["", ""]],
        [
          actionButton("Keep", "keep", -1, r.sku),
          actionButton("Remove", "remove", -1, r.sku),
        ]
      )
    );
  });
```

- [ ] **Step 3: Replace the two `if/else` cascades with one table**

Add above the `QWebChannel` bootstrap:

```js
// One entry per action a row can offer. Both listeners share it, so a new
// action is one line here rather than a branch in each cascade.
const ACTIONS = {
  confirm: function (btn, bridge) { bridge.confirmItem(Number(btn.dataset.row)); },
  undo: function (btn, bridge) { bridge.undoItem(Number(btn.dataset.row)); },
  force: function (btn, bridge) { bridge.forceItem(Number(btn.dataset.row)); },
  map: function (btn, bridge) { bridge.mapSku(btn.dataset.sku); },
  keep: function (btn, bridge) { bridge.keepExtra(btn.dataset.sku); },
  remove: function (btn, bridge) { bridge.removeExtra(btn.dataset.sku); },
};

function onActionClick(event) {
  const btn = event.target.closest("[data-action]");
  const run = btn && ACTIONS[btn.dataset.action];
  if (run) run(btn, state.bridge);
}
```

and in the bootstrap, both listeners become:

```js
  els.skuList.addEventListener("click", onActionClick);
  els.extrasRows.addEventListener("click", onActionClick);
```

- [ ] **Step 4: Run the bridge suite to verify nothing changed**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_bridge.py`
Expected: PASS, the same test count as step 1.

- [ ] **Step 5: Commit**

```bash
git add gui/web/packer.js
git commit -F <message file>
```

Message: `refactor(packer): one row builder and one action table for the page`

---

### Task 6: the page draws unmatched scans and the multi-unit cue

**Files:**
- Modify: `gui/web/packer.js` (`CHIP`, `renderItems`, `ACTIONS`)
- Modify: `gui/web/packer.css` (one new rule)
- Test: `tests/test_packer_bridge.py`

**Interfaces:**
- Consumes: `rowEl` / `ACTIONS` (Task 5), `unknown_rows`' row shape (Task 2).
- Produces: `.sku-row--unknown` rows with a Map SKU button and
  `.sku-row__qty--multi` on multi-unit quantity cells; on `PackerBridge`, the
  `mapBarcode(str)` slot and its `mapBarcodeRequested(str)` signal, which
  Task 8 connects on the widget.

- [ ] **Step 1: Write the failing tests**

```python
def test_an_unmatched_scan_draws_a_no_match_row_that_only_maps(qtbot, page):
    view, bridge = page
    bridge.set_items(unknown_rows(["4006381333931"]))
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 1")
    assert _eval(qtbot, view, "document.querySelector('.sku-row').className") == (
        "sku-row sku-row--unknown"
    )
    cells = _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.sku-row > span'))"
        ".map(function (e) { return e.textContent; })",
    )
    assert cells[:3] == ["Unknown SKU", "4006381333931", "—"]
    assert "No match" in cells[3]
    assert _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.sku-row .btn'))"
        ".map(function (e) { return e.textContent; })",
    ) == ["Map SKU"]


def test_mapping_an_unmatched_scan_reaches_python_with_the_barcode(qtbot, page):
    view, bridge = page
    bridge.set_items(unknown_rows(["4006381333931"]))
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row .btn').length === 1")
    with qtbot.waitSignal(bridge.mapBarcodeRequested, timeout=5000) as caught:
        view.page().runJavaScript("document.querySelector('.sku-row .btn').click()")
    assert caught.args == ["4006381333931"]


def test_the_quantity_cell_warns_while_a_multi_unit_line_is_unfinished(qtbot, page):
    view, bridge = page
    bridge.set_items(item_rows(ITEMS_FOR_PAGE, [{"row": 0, "packed": 1, "required": 3}], {}))
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 1")
    assert _eval(qtbot, view, "document.querySelector('.sku-row__qty').className") == (
        "sku-row__qty sku-row__qty--multi"
    )


def test_a_finished_multi_unit_line_drops_the_warning(qtbot, page):
    view, bridge = page
    bridge.set_items(item_rows(ITEMS_FOR_PAGE, [{"row": 0, "packed": 3, "required": 3}], {}))
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 1")
    assert _eval(qtbot, view, "document.querySelector('.sku-row__qty').className") == (
        "sku-row__qty"
    )
```

Add the imports and the fixture data this file needs at the top of
`tests/test_packer_bridge.py`, in the same edit as their first use:

```python
from gui.packer_bridge import (
    PAGE,
    THEME_MARKER,
    item_rows,
    mount_packer_page,
    unknown_rows,
)

ITEMS_FOR_PAGE = [{"SKU": "TS-4409-B", "Product_Name": "Wireless Mouse", "Quantity": 3}]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_bridge.py -k "unmatched or multi_unit"`
Expected: FAIL — the rows render with `0 / 0` and no `--unknown` class, and
`bridge.mapBarcodeRequested` does not exist yet.

- [ ] **Step 3: Teach the page the two things**

In `gui/web/packer.js`, add the chip:

```js
const CHIP = {
  complete: { text: "Complete", cls: "chip chip--success chip--hollow" },
  partial: { text: "Partial", cls: "chip chip--warning chip--tint chip--hollow" },
  pending: { text: "Pending", cls: "chip chip--neutral chip--hollow" },
  unknown: { text: "No match", cls: "chip chip--danger chip--tint chip--hollow" },
};
```

In `renderItems`' loop, before building the row:

```js
    if (r.mapBarcode) buttons.push(actionButton("Map SKU", "mapBarcode", r.row, r.sku));
```

and the quantity cell becomes — an unmatched scan has no quantity to report,
and a multi-unit line that still owes scans says so:

```js
      [
        ["sku-row__product", r.product],
        ["sku-row__sku", r.sku],
        [
          "sku-row__qty" + (r.multi ? " sku-row__qty--multi" : ""),
          r.state === "unknown" ? "—" : r.packed + " / " + r.required,
        ],
        [chip.cls, chip.text],
      ],
```

Add the action:

```js
  mapBarcode: function (btn, bridge) { bridge.mapBarcode(btn.dataset.sku); },
```

In `gui/packer_bridge.py`, add the slot and its signal beside the others:

```python
    mapBarcodeRequested = Signal(str)
```

```python
    @Slot(str)
    def mapBarcode(self, barcode) -> None:
        self.mapBarcodeRequested.emit(str(barcode))
```

In `gui/web/packer.css`, add after the `.sku-row__qty` rule:

```css
/* [C], carried over from the Qt table it replaced: a line that needs more
   than one scan says so until it is done (Bundle 5 spec S4). */
.sku-row__qty--multi {
  color: var(--status-warning);
  background: var(--status-warning-bg);
  border-radius: var(--radius-sm);
  padding: 0 var(--spacing-xs);
}
```

- [ ] **Step 4: Run the bridge suite and the style guards to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_bridge.py tests/test_style_lint.py tests/test_style_literals_guard.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gui/web/packer.js gui/web/packer.css gui/packer_bridge.py tests/test_packer_bridge.py
git commit -F <message file>
```

Message: `feat(packer): unmatched scans get a row, multi-unit lines get their cue back`

---

### Task 7: the page draws the finished session in place of the document

**Files:**
- Modify: `gui/web/packer.html` (the state panel's markup)
- Modify: `gui/web/packer.js` (`renderSessionEnd`, bootstrap)
- Modify: `gui/web/packer.css` (two rules)
- Test: `tests/test_packer_bridge.py`

**Interfaces:**
- Consumes: `sessionEnd` / `endSession` / `exitPacking` from Task 4.
- Produces: `renderSessionEnd()` toggling `.doc-state` on `.doc-main`; the
  panel's two buttons call `bridge.endSession()` and `bridge.exitPacking()`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_finished_session_replaces_the_document_with_its_panel(qtbot, page):
    view, bridge = page
    bridge.set_items(item_rows(ITEMS_FOR_PAGE, [], {}))
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 1")
    bridge.set_session_end({"title": "Session complete", "body": "2 of 2 orders packed."})
    _until_js(qtbot, view, "document.getElementById('doc-main').classList.contains('doc-state')")
    # The list is still in the DOM -- the bridge keeps filling it -- but the
    # panel has the column.
    assert _eval(qtbot, view, "getComputedStyle(document.getElementById('sku-list')).display") == "none"
    assert _eval(qtbot, view, "document.querySelector('.state-panel-title').textContent") == (
        "Session complete"
    )
    assert _eval(qtbot, view, "document.querySelector('.state-panel-body').textContent") == (
        "2 of 2 orders packed."
    )


def test_clearing_the_session_end_gives_the_document_back(qtbot, page):
    view, bridge = page
    bridge.set_session_end({"title": "Session complete", "body": "done."})
    _until_js(qtbot, view, "document.getElementById('doc-main').classList.contains('doc-state')")
    bridge.set_session_end({})
    _until_js(
        qtbot,
        view,
        "!document.getElementById('doc-main').classList.contains('doc-state')",
    )
    assert _eval(qtbot, view, "getComputedStyle(document.querySelector('.state-panel')).display") == "none"


def test_the_panels_buttons_reach_python(qtbot, page):
    view, bridge = page
    bridge.set_session_end({"title": "Session complete", "body": "done."})
    _until_js(qtbot, view, "document.querySelectorAll('.state-panel-actions .btn').length === 2")
    labels = _eval(
        qtbot,
        view,
        "Array.from(document.querySelectorAll('.state-panel-actions .btn'))"
        ".map(function (e) { return e.textContent; })",
    )
    assert labels == ["End session", "Exit packing"]
    with qtbot.waitSignal(bridge.endSessionRequested, timeout=5000):
        view.page().runJavaScript(
            "document.querySelector('[data-action=\"endSession\"]').click()"
        )
    with qtbot.waitSignal(bridge.exitPackingRequested, timeout=5000):
        view.page().runJavaScript(
            "document.querySelector('[data-action=\"exitPacking\"]').click()"
        )
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_bridge.py -k "finished_session or session_end or panels_buttons"`
Expected: FAIL — there is no `.state-panel` in the page yet.

- [ ] **Step 3: Add the panel, its render function and its CSS**

In `gui/web/packer.html`, as the last child of `.doc-main` (after `.sku-list`):

```html
    <div class="state-panel" id="state-panel">
      <p class="state-panel-title" id="state-title"></p>
      <p class="state-panel-body" id="state-body"></p>
      <div class="state-panel-actions">
        <button class="btn btn--primary" type="button" data-action="endSession">End session</button>
        <button class="btn" type="button" data-action="exitPacking">Exit packing</button>
      </div>
    </div>
```

In `gui/web/packer.js`, add the render function:

```js
function renderSessionEnd() {
  const s = state.bridge.sessionEnd || {};
  const over = Boolean(s.title);
  // One class decides the whole swap; CSS hides the regions the panel
  // replaces, so there is no per-region bookkeeping to get out of step.
  els.docMain.classList.toggle("doc-state", over);
  els.stateTitle.textContent = s.title || "";
  els.stateBody.textContent = s.body || "";
}
```

register the elements and the wiring in the bootstrap:

```js
  els.stateTitle = document.getElementById("state-title");
  els.stateBody = document.getElementById("state-body");
```

```js
  bridge.sessionEndChanged.connect(renderSessionEnd);
```

```js
  els.docMain.addEventListener("click", onActionClick);
```

```js
  renderSessionEnd();
```

(place the `renderSessionEnd()` call beside the other initial renders, and the
`connect` beside the other connects.)

Add the two actions to `ACTIONS`:

```js
  endSession: function (btn, bridge) { bridge.endSession(); },
  exitPacking: function (btn, bridge) { bridge.exitPacking(); },
```

In `gui/web/packer.css`, after the `.state-panel` rules:

```css
/* The panel takes the main column's place. The regions it replaces stay in
   the DOM -- the bridge keeps filling them -- but only one of the two paints,
   so nothing has to be hidden from JS.  */
.doc-main.doc-state > :not(.state-panel) { display: none; }
.doc-main:not(.doc-state) > .state-panel { display: none; }
```

- [ ] **Step 4: Run the bridge suite and the style guards to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_bridge.py tests/test_style_lint.py tests/test_style_literals_guard.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gui/web/packer.html gui/web/packer.js gui/web/packer.css tests/test_packer_bridge.py
git commit -F <message file>
```

Message: `feat(packer): a finished session says so in the document, not in a modal`

---

### Task 8: the widget's session-complete method and its two new signals

**Files:**
- Modify: `gui/packer_mode_widget.py` (docstring, signals, `clear_screen`, new method, bridge connections)
- Test: `tests/test_packer_mode_widget.py` (create)

**Interfaces:**
- Consumes: `set_session_end` (Task 4), `mapBarcodeRequested` (Task 6).
- Produces: `PackerModeWidget.show_session_complete(payload: dict)`;
  signals `end_session_requested` (no args) and
  `map_barcode_requested(str barcode)`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_packer_mode_widget.py`:

```python
"""Packer Mode's Qt side: the bar, and the state the widget pushes.

The document itself is covered by tests/test_packer_bridge.py.
"""

import pytest

from gui.packer_mode_widget import PackerModeWidget


@pytest.fixture
def widget(qtbot):
    w = PackerModeWidget()
    qtbot.addWidget(w)
    return w


def test_a_finished_session_stops_the_scanner_and_names_itself(widget):
    widget.show_session_complete({"title": "Session complete", "body": "done."})
    assert widget.bridge.sessionEnd["body"] == "done."
    assert widget.scanner_input.isEnabled() is False
    assert widget.skip_order_button.isEnabled() is False


def test_clearing_the_screen_gives_the_document_back(widget):
    widget.show_session_complete({"title": "Session complete", "body": "done."})
    widget.clear_screen()
    assert widget.bridge.sessionEnd == {}
    assert widget.scanner_input.isEnabled() is True


def test_the_panels_end_session_button_reaches_the_widgets_signal(qtbot, widget):
    with qtbot.waitSignal(widget.end_session_requested, timeout=1000):
        widget.bridge.endSession()


def test_the_panels_exit_button_reaches_the_existing_exit_signal(qtbot, widget):
    with qtbot.waitSignal(widget.exit_packing_mode, timeout=1000):
        widget.bridge.exitPacking()


def test_mapping_an_unmatched_scan_forwards_the_barcode(qtbot, widget):
    with qtbot.waitSignal(widget.map_barcode_requested, timeout=1000) as caught:
        widget.bridge.mapBarcode("4006381333931")
    assert caught.args == ["4006381333931"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_mode_widget.py`
Expected: FAIL — `AttributeError: 'PackerModeWidget' object has no attribute 'show_session_complete'`

- [ ] **Step 3: Add the signals, the method and the connections**

In `gui/packer_mode_widget.py`, with the other signals:

```python
    end_session_requested = Signal()  # P8's primary action
    map_barcode_requested = Signal(str)  # raw barcode from an unmatched scan
```

and in the class docstring's `Attributes:` list:

```
        end_session_requested (Signal): Emitted when the session-complete panel's
            End session button is pressed.
        map_barcode_requested (Signal[str]): Emitted with the raw barcode of an
            unmatched scan the packer chose to map.
```

Beside the existing bridge connections in `__init__`:

```python
        self.bridge.mapBarcodeRequested.connect(self._on_map_barcode)
        self.bridge.endSessionRequested.connect(self.end_session_requested.emit)
        self.bridge.exitPackingRequested.connect(self.exit_packing_mode.emit)
```

With the other action slots:

```python
    def _on_map_barcode(self, barcode: str):
        """Forward an unmatched scan's barcode; MainWindow owns the dialog."""
        self.map_barcode_requested.emit(barcode)
        self.set_focus_to_scanner()
```

With the other public display methods:

```python
    def show_session_complete(self, payload: dict[str, str]):
        """Show the session's terminal state in place of the order document.

        Args:
            payload: gui.packer_bridge.session_end_payload()'s title and body.
        """
        self.bridge.set_session_end(payload)
        self._order_label.setText("Session complete")
        self.scanner_input.setEnabled(False)
        self.skip_order_button.setEnabled(False)
```

In `clear_screen`, beside the other resets:

```python
        self.bridge.set_session_end({})
```

Note `_order_label` arrives in Task 9. Until then this task's test will fail on
it, so **add the label in this task too**, as a bare `QLabel("No order")` field
on the widget; Task 9 places it in the bar:

```python
        self._order_label = QLabel("No order")
        self._order_label.setObjectName("cmdbarSession")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_mode_widget.py`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add gui/packer_mode_widget.py tests/test_packer_mode_widget.py
git commit -F <message file>
```

Message: `feat(packer): the widget can show a finished session and forward a barcode`

---

### Task 9: the Qt chrome becomes a 60px command bar

**Files:**
- Modify: `gui/command_bar.py` (extract `bar_css`)
- Modify: `gui/packer_mode_widget.py:67-158` (the layout)
- Test: `tests/test_packer_mode_widget.py`

**Interfaces:**
- Consumes: `_order_label` (Task 8).
- Produces: `gui.command_bar.bar_css(tokens, selector="CommandBar") -> str`;
  `PackerModeWidget.packer_bar` (the 60px `QWidget`), with `scanner_input`,
  `skip_order_button` and `exit_button` inside it.

- [ ] **Step 1: Write the failing tests**

```python
from gui.command_bar import BAR_HEIGHT


def test_the_bar_is_the_same_sixty_pixels_the_pages_use(widget):
    assert widget.packer_bar.height() == BAR_HEIGHT


def test_the_scanner_is_visible_and_invites_a_scan(widget):
    # A2: the shipped 1x1 hidden QLineEdit becomes a field the packer can see.
    assert widget.scanner_input.placeholderText() == "Ready to scan"
    assert widget.scanner_input.width() > 100
    assert widget.scanner_input.parent() is widget.packer_bar


def test_the_scanner_still_owns_the_keyboard(qtbot, widget):
    # D3, restated for the bar: the field moved, the invariant did not.
    widget.show()
    qtbot.waitExposed(widget)
    widget.set_focus_to_scanner()
    assert widget.scanner_input.hasFocus()


def test_skip_and_exit_sit_in_the_bar(widget):
    assert widget.skip_order_button.parent() is widget.packer_bar
    assert widget.exit_button.parent() is widget.packer_bar
    assert widget.exit_button.text() == "Exit packing"
    assert widget.skip_order_button.text() == "Skip order"


def test_showing_an_order_names_it_in_the_bar(widget):
    widget.display_order(
        [{"SKU": "A", "Product_Name": "A", "Quantity": 1, "Order_Number": "10429"}],
        [],
    )
    assert widget._order_label.text() == "#10429"
    widget.clear_screen()
    assert widget._order_label.text() == "No order"
```

And in `tests/test_packing_density.py`:

```python
def test_both_bars_share_one_definition_of_the_bar(qapp):
    from gui.command_bar import bar_css
    from gui.theme import current_tokens

    tokens = current_tokens()
    assert "PackerBar" in bar_css(tokens, "QWidget#PackerBar")
    assert bar_css(tokens).startswith("CommandBar {")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_mode_widget.py tests/test_packing_density.py`
Expected: FAIL — `AttributeError: 'PackerModeWidget' object has no attribute 'packer_bar'`, and `ImportError` for `bar_css`.

- [ ] **Step 3: Extract `bar_css`, then rebuild the layout**

In `gui/command_bar.py`, add at module level and use it from `_apply_theme`:

```python
def bar_css(tokens, selector: str = "CommandBar") -> str:
    """The 60px bar's ground, its bottom border and its session label.

    Packer Mode builds its own bar rather than becoming a fourth page of this
    one -- it wants none of the client combo, filter or four buttons above, and
    MainWindow aliases every one of them. What the two bars genuinely share is
    this rule set, so it has one definition and takes the selector it paints.
    Type-scoped: a bare rule would repaint every child button.
    """
    return (
        f"{selector} {{ background-color: {tokens.surface_raised};"
        f" border-bottom: 1px solid {tokens.border_subtle}; }}"
        f" QLabel#cmdbarSession {{ {font_css('body')}"
        f" font-family: {tokens.font_family_mono}; color: {tokens.text_secondary}; }}"
    )
```

```python
    def _apply_theme(self, tokens) -> None:
        self.setStyleSheet(bar_css(tokens))
```

In `gui/packer_mode_widget.py`, replace `__init__`'s layout (the
`main_layout`/`left_widget`/`right_widget` construction, `scan_row`, and the
right column's `addStretch`) with a bar over the document. The model-state
fields, the `mount_packer_page` call and every bridge connection stay exactly
where they are:

```python
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ─── COMMAND BAR (artboard A1: the rail is hidden while packing, and
        # this bar carries the order, the scanner, Skip and Exit) ────────────
        self.packer_bar = QWidget()
        self.packer_bar.setObjectName("PackerBar")
        # A plain QWidget subclass ignores a background rule without this.
        self.packer_bar.setAttribute(Qt.WA_StyledBackground, True)
        self.packer_bar.setFixedHeight(BAR_HEIGHT)
        bar = QHBoxLayout(self.packer_bar)
        bar.setContentsMargins(12, 0, 12, 0)
        bar.setSpacing(8)

        self._order_label = QLabel("No order")
        self._order_label.setObjectName("cmdbarSession")
        bar.addWidget(self._order_label)

        # The scanner field, A2: the shipped 1x1 hidden QLineEdit, grown to a
        # field the packer can see. The global QSS already lands a QLineEdit on
        # control_height, so it needs a width and nothing else -- and because
        # it is still the widget the scanner types into, the visible focus ring
        # and the disabled state are the real thing rather than a copy of it.
        self.scanner_input = QLineEdit()
        self.scanner_input.setFixedWidth(SCANNER_WIDTH)
        self.scanner_input.setPlaceholderText("Ready to scan")
        self.scanner_input.returnPressed.connect(self._on_scan)
        bar.addWidget(self.scanner_input)

        if self._sim_mode or os.environ.get("PACKER_DEV_SIM"):
            bar.addWidget(self._build_sim_group())

        bar.addStretch(1)

        self.skip_order_button = QPushButton("Skip order")
        self.skip_order_button.setFocusPolicy(Qt.NoFocus)
        self.skip_order_button.setEnabled(False)
        self.skip_order_button.clicked.connect(self.skip_order_requested.emit)
        bar.addWidget(self.skip_order_button)

        self.exit_button = QPushButton("Exit packing")
        self.exit_button.setFocusPolicy(Qt.NoFocus)
        self.exit_button.clicked.connect(self.exit_packing_mode.emit)
        bar.addWidget(self.exit_button)

        root.addWidget(self.packer_bar)
        root.addWidget(self.document_view, 1)

        on_theme_changed(self, self._apply_bar_theme)
```

with the sim group lifted into its own method, restyled to the artboard's
`.sim-group`:

```python
    def _build_sim_group(self) -> QGroupBox:
        """The dev scan simulator, inline in the bar (artboard P3-1920).

        Opt-in only: the ScanSimulatorMode config setting (wired through
        main.py) or PACKER_DEV_SIM=1 for a one-off.
        """
        group = QGroupBox("DEV")
        group.setObjectName("SimGroup")
        group.setFixedHeight(BAR_HEIGHT - 16)
        layout = QHBoxLayout(group)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(4)
        self.sim_input = QLineEdit()
        self.sim_input.setFixedWidth(SIM_INPUT_WIDTH)
        self.sim_input.setPlaceholderText("Order number or SKU")
        self.sim_input.returnPressed.connect(self._on_sim_scan)
        button = QPushButton("Simulate scan")
        button.setFocusPolicy(Qt.NoFocus)
        button.clicked.connect(self._on_sim_scan)
        layout.addWidget(self.sim_input)
        layout.addWidget(button)
        return group
```

and the bar's theme, replacing the sim group's inline stylesheet:

```python
    def _apply_bar_theme(self, tokens) -> None:
        self.setStyleSheet(
            bar_css(tokens, "QWidget#PackerBar")
            + f" QGroupBox#SimGroup {{ border: 1px dashed {tokens.status_warning};"
            f" border-radius: {tokens.radius}px; color: {tokens.status_warning};"
            f" {font_css('caption', bold=True)} }}"
            " QGroupBox#SimGroup::title { subcontrol-origin: margin; left: 8px; }"
        )
```

New module constants and imports (add each import in the same edit as its first
use — the formatter strips an unused one):

```python
from PySide6.QtWidgets import QLabel  # with the others

from gui.command_bar import BAR_HEIGHT, bar_css
from shared.theme import font_css, on_theme_changed

SCANNER_WIDTH = 280
SIM_INPUT_WIDTH = 160
```

`gui.theme.current_tokens` was imported only for the sim group's old inline
stylesheet, which `_apply_bar_theme` replaces — drop that import in the same
edit or `ruff` will fail the gate on it.

Then the order label's two writers. In `display_order`, after the banner push:

```python
        self._order_label.setText(f"#{order_number}" if order_number else "No order")
```

and in `clear_screen`, beside the other resets:

```python
        self._order_label.setText("No order")
```

Update the class docstring's `Attributes:` to name `packer_bar` and drop
nothing else.

- [ ] **Step 4: Run the widget, density and focus suites to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_mode_widget.py tests/test_packing_density.py tests/test_packer_scanner_focus.py`
Expected: PASS. The scanner-focus test is D3's guard and moved parents in this
task — if it fails, the bar took the keyboard and the task is not done.

- [ ] **Step 5: Commit**

```bash
git add gui/command_bar.py gui/packer_mode_widget.py tests/test_packer_mode_widget.py tests/test_packing_density.py
git commit -F <message file>
```

Message: `feat(packer): the scanner, Skip and Exit move into a 60px command bar`

---

### Task 10: `MainWindow` shows P8 instead of asking in a modal

**Files:**
- Modify: `gui/main_window.py:2223-2255` (`_on_all_orders_complete`, `_show_all_complete_dialog`)
- Modify: `gui/main_window.py:353-361` (the widget's signal connections)
- Test: `tests/test_packer_mode_widget.py`

**Interfaces:**
- Consumes: `show_session_complete` (Task 8), `session_end_payload` (Task 3).
- Produces: `MainWindow._show_session_complete()`, `_session_seconds(started_at)`.

- [ ] **Step 1: Write the failing test**

```python
from gui.main_window import _session_seconds


def test_a_missing_or_unparseable_start_time_is_no_duration():
    assert _session_seconds(None) == 0
    assert _session_seconds("") == 0
    assert _session_seconds("not a timestamp") == 0


def test_a_start_time_an_hour_ago_is_an_hour():
    from datetime import datetime, timedelta

    started = (datetime.now().astimezone() - timedelta(hours=1)).isoformat()
    assert 3550 <= _session_seconds(started) <= 3650
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_mode_widget.py -k session_seconds`
Expected: FAIL — `ImportError: cannot import name '_session_seconds'`

- [ ] **Step 3: Replace the modal with the panel**

Add at module level in `gui/main_window.py` (`datetime` is already imported at
line 23):

```python
def _session_seconds(started_at) -> int:
    """Seconds since an ISO session start; 0 when it is missing or unreadable.

    A session restored from disk can carry anything in started_at, and a
    sentence that reports "in 0s" is better than one that raises.
    """
    if not started_at:
        return 0
    try:
        start = datetime.fromisoformat(str(started_at))
    except (TypeError, ValueError):
        return 0
    return max(int((datetime.now(start.tzinfo) - start).total_seconds()), 0)
```

Replace `_show_all_complete_dialog` with `_show_session_complete`, keeping
`_on_all_orders_complete`'s deferral exactly as it is — the signal is emitted
inside `process_sku_scan()`, whose frame still holds `self.logic`:

```python
    def _show_session_complete(self):
        """Show the session's terminal state in the document (Bundle 5 spec S2).

        This replaces the "End session now?" QMessageBox. The decision the
        modal asked is now P8's two buttons, so the packer answers it on the
        screen that announced the session was over instead of through a dialog
        over it.
        """
        if not self.logic:
            return
        state = self.logic.session_packing_state
        self.packer_mode_widget.show_session_complete(
            session_end_payload(
                packed=len(state.get("completed_orders", [])),
                total=len(self.logic.orders_data),
                skipped=len(state.get("skipped_orders", [])),
                items=sum(
                    order.get("items_count", 0)
                    for order in (self.logic.completed_orders_metadata or [])
                ),
                seconds=_session_seconds(self.logic.started_at),
            )
        )
```

and repoint the deferral:

```python
        QTimer.singleShot(0, self._show_session_complete)
```

Import `session_end_payload` beside the existing payload imports, in the same
edit as the usage above.

Connect the panel's End session, beside the other `packer_mode_widget`
connections around line 353:

```python
        self.packer_mode_widget.end_session_requested.connect(self.end_session)
```

(`exit_packing_mode` is already connected to `switch_to_session_view`, so P8's
Exit needs no new connection.)

- [ ] **Step 4: Run the test and the full suite to verify they pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Expected: PASS. Any test that asserted on the all-complete `QMessageBox` fails
here and must be updated to assert on the payload instead — that is the point
of the change, not a regression.

- [ ] **Step 5: Commit**

```bash
git add gui/main_window.py tests/test_packer_mode_widget.py
git commit -F <message file>
```

Message: `feat(packer): a finished session is a state panel, not a modal question`

---

### Task 11: mapping an unmatched scan picks one of the order's SKUs

**Files:**
- Modify: `gui/main_window.py:2133-2189` (`_on_map_sku_from_packer`), plus the new handler
- Test: `tests/test_packer_mode_widget.py`

**Interfaces:**
- Consumes: `map_barcode_requested` (Task 8).
- Produces: `MainWindow._save_sku_mapping(barcode: str, sku: str) -> bool` and
  `MainWindow._on_map_barcode_from_packer(barcode: str)`.

- [ ] **Step 1: Extract the save half of today's dialog**

`_on_map_sku_from_packer` currently asks for the barcode and then saves. The
save half — the overwrite confirm, the write, the `logic.sku_map` refresh, the
notification — is what both dialogs need. Pull it out unchanged in behaviour:

```python
    def _save_sku_mapping(self, barcode: str, sku: str) -> bool:
        """Save one barcode → SKU mapping, confirming an overwrite first.

        Shared by both directions of the Map SKU flow: the per-item button
        knows the SKU and asks for the barcode, and the unmatched-scan row
        knows the barcode and asks for the SKU.
        """
        try:
            existing = self.profile_manager.load_sku_mapping(self.current_client_id)
            if barcode in existing and existing[barcode] != sku:
                reply = QMessageBox.question(
                    self,
                    "Overwrite Mapping?",
                    f"Barcode '{barcode}' already maps to '{existing[barcode]}'.\n\n"
                    f"Replace with '{sku}'?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return False

            existing[barcode] = sku
            if not self.profile_manager.save_sku_mapping(
                self.current_client_id, existing
            ):
                QMessageBox.warning(
                    self, "Save Failed", "Could not save mapping to file server."
                )
                return False

            if self.logic:
                self.logic.sku_map = {
                    self.logic._normalize_sku(k): v for k, v in existing.items()
                }
                logger.info(f"Quick-mapped barcode '{barcode}' → SKU '{sku}'")
            self.packer_mode_widget.show_notification(
                f"Mapped: {barcode} → {sku}", "status_success"
            )
            return True
        except Exception as e:
            logger.exception("Failed to save quick SKU mapping")
            QMessageBox.critical(self, "Error", f"Failed to save mapping:\n\n{e}")
            return False
```

and `_on_map_sku_from_packer`'s body after its `QInputDialog` becomes:

```python
        self._save_sku_mapping(barcode.strip(), sku)
        self.packer_mode_widget.set_focus_to_scanner()
```

- [ ] **Step 2: Write the failing test**

```python
def test_the_pick_list_puts_the_lines_that_still_need_scans_first(qtbot):
    from gui.main_window import _unmapped_choices

    state = [
        {"original_sku": "A", "packed": 2, "required": 2},
        {"original_sku": "B", "packed": 0, "required": 1},
        {"original_sku": "C", "packed": 1, "required": 4},
    ]
    assert _unmapped_choices(state) == [
        ("B", "B — 0 / 1 packed"),
        ("C", "C — 1 / 4 packed"),
        ("A", "A — 2 / 2 packed"),
    ]


def test_the_pick_list_is_empty_when_there_is_no_order():
    from gui.main_window import _unmapped_choices

    assert _unmapped_choices(None) == []
    assert _unmapped_choices([]) == []
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q tests/test_packer_mode_widget.py -k pick_list`
Expected: FAIL — `ImportError: cannot import name '_unmapped_choices'`

- [ ] **Step 4: Write the picker**

At module level in `gui/main_window.py`:

```python
def _unmapped_choices(order_state) -> list[tuple[str, str]]:
    """This order's lines as (sku, label), the ones still owing scans first.

    An unmatched scan happened while packing this order, so the SKU the packer
    meant is almost always a line that is not finished yet.
    """
    return [
        (s["original_sku"], f"{s['original_sku']} — {s['packed']} / {s['required']} packed")
        for s in sorted(
            order_state or [],
            key=lambda s: s.get("packed", 0) >= s.get("required", 0),
        )
    ]
```

and the handler:

```python
    def _on_map_barcode_from_packer(self, barcode: str):
        """Map an unmatched scan to one of this order's SKUs, then replay it.

        The reverse of _on_map_sku_from_packer: here the barcode is known and
        the SKU is picked. Replaying the scan afterwards packs the item in the
        same gesture -- the scan already happened, and making the packer scan
        again to use a mapping they just made is a step with no purpose.
        """
        choices = _unmapped_choices(self.logic.current_order_state) if self.logic else []
        if not (choices and self.current_client_id):
            self.packer_mode_widget.set_focus_to_scanner()
            return

        labels = [label for _sku, label in choices]
        picked, ok = QInputDialog.getItem(
            self,
            "Map SKU",
            f"Barcode {barcode}\n\nWhich item did you scan?",
            labels,
            0,
            False,
        )
        if not (ok and picked):
            self.packer_mode_widget.set_focus_to_scanner()
            return

        sku = choices[labels.index(picked)][0]
        if self._save_sku_mapping(barcode, sku):
            self.on_scanner_input(barcode)
        self.packer_mode_widget.set_focus_to_scanner()
```

Connect it beside the other `packer_mode_widget` connections:

```python
        self.packer_mode_widget.map_barcode_requested.connect(
            self._on_map_barcode_from_packer
        )
```

- [ ] **Step 5: Run the full suite to verify it passes**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add gui/main_window.py tests/test_packer_mode_widget.py
git commit -F <message file>
```

Message: `feat(packer): map an unmatched scan by picking the item it was`

---

### Task 12: the copy becomes the artboard's

**Files:**
- Modify: `gui/main_window.py` (nine `show_notification` strings)

**Interfaces:**
- Consumes: nothing. Produces nothing beyond the strings.

- [ ] **Step 1: Replace each string**

The four the artboard draws verbatim, then five in its voice. Line numbers are
from before this bundle's edits — find each by its current text.

| Current | Replacement |
|---|---|
| `"ITEM OK"` (:1987) | `f"{result['sku']} confirmed — {result['packed']} of {result['required']} packed"` |
| `f"INCORRECT ITEM!\n{detail}"` (:1996) | `f"Unknown SKU {text} — scan again or map it"` |
| `f"ORDER {order_number} COMPLETE!"` (:2069) | `f"Order #{order_number} packed. Scan the next order."` |
| `"Scan the next order's barcode"` (`packer_mode_widget.clear_screen`) | `"Scan an order barcode"` |
| `"EXTRA ITEM!"` (:2002) | `"Extra item scanned — keep it or remove it"` |
| `"REVIEW EXTRA ITEMS!"` (:2014, :2123) | `"Review the extra items before this order can close"` |
| `f"ORDER {text} ALREADY COMPLETED"` (:1971) | `f"Order #{text} is already packed"` |
| `"ORDER NOT FOUND"` (:1976) | `f"No order matches {text}"` |
| `"Already at 0!"` (:2105) | `"Nothing packed on that line yet"` |

Two details:

- The `ITEM OK` replacement needs the scanned line's numbers. `result` at that
  call site carries `row` and `packed`; take the SKU and the required count
  from the widget's own row for that index rather than re-deriving them:
  `row = self.packer_mode_widget.row_at(result["row"])`. Add that one-line
  accessor to `PackerModeWidget`:

```python
    def row_at(self, row: int) -> dict[str, Any]:
        """One item row's payload, for a caller writing a message about it."""
        return dict(self._rows[row]) if 0 <= row < len(self._rows) else {}
```

  and use `row.get("sku", "")` / `row.get("required", 0)`, so a stale index
  gives a plain message rather than an IndexError.
- The `\n` and the unknown-scan count in the old `INCORRECT ITEM!` string go
  away with it: the band is one row, and the count is now visible as rows in
  the list. Delete the `unknown_list` / `detail` block above it.

- [ ] **Step 2: Run the full suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Expected: PASS. A test asserting on one of the old shouted strings fails here
and must be updated to the new string.

- [ ] **Step 3: Grep for a shout that got missed**

Run: `rg -n '"[A-Z][A-Z ]{4,}[!"]' gui/main_window.py gui/packer_mode_widget.py`
Expected: no hits inside a `show_notification` call.

- [ ] **Step 4: Commit**

```bash
git add gui/main_window.py gui/packer_mode_widget.py
git commit -F <message file>
```

Message: `feat(packer): the scan feedback says what happened and what to do next`

---

### Task 13: see it, at both sizes and in both themes

The scroll bug Bundle 4 shipped was invisible to every test and to a
four-item screenshot. This task is that lesson.

**Files:**
- Create: `$CLAUDE_JOB_DIR/tmp/render_packer.py` (throwaway, not committed)

- [ ] **Step 1: Render the states that changed**

Write a script that builds a `PackerModeWidget`, drives it through the public
methods, and `grab()`s a PNG per state, in `THEME_DARK` and `THEME_LIGHT`, at
1366×768 and 1920×1080:

1. **Waiting** — `clear_screen()`. Bar reads "No order", field shows "Ready to
   scan".
2. **Scanning, 22 items, 3 unmatched scans** — `display_order(...)` with 22
   items, `set_items(item_rows(...) + unknown_rows([...]))`, a multi-unit line
   part-packed. **Both the SKU list and the unknown rows past the fold must be
   reachable by scrolling, with a visible scrollbar.**
3. **Session complete** — `show_session_complete(session_end_payload(12, 13, 1, 66, 6480))`.
   Panel centred, side column still visible, both buttons present, field
   disabled.
4. **Sim mode** — `PackerModeWidget(sim_mode=True)`, bar with the DEV group.

- [ ] **Step 2: Look at every image**

Against `docs/design/phase10/packer-mode.html` frames P2, P5, P8 and P3-1920.
Check the bar's 60px rhythm, the field's focus ring, the multi-unit tint, the
`No match` chips, and that the 1366 bar with the DEV group is not crushed.

- [ ] **Step 3: Fix what the images show, and note what you chose not to fix**

Any fix needs its own test if it is behaviour rather than spacing.

- [ ] **Step 4: Refresh the graph and run the full gate**

```bash
graphify update .
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Run: `.venv/bin/ruff check .`
Expected: PASS and clean.

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -F <message file>
```

Message: `fix(packer): what the rendered states showed`

---

## Stage C hand-off

Do **not** open the PR — Stage C does. Leave for it:

- The merge gate: the owner scans with a real scanner on a Windows build with
  the visible field in the bar, and ends a session from P8.
- The artboard departures to name in the PR body: **P1 is not built** (spec
  S1 — unreachable), and **P8 has two buttons** where the drawing has one
  (spec S2).
- The review base is `origin/main`. Local `main` on this VM is a stale backup;
  `git diff main...HEAD` shows already-merged bundles.
