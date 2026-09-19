# Phase 10 Bundle 6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the five defects the owner found after merging Bundle 5, then rebuild the Session Browser, the Packing table view and the Statistics tab in Qt against their approved artboards.

**Architecture:** Three Qt screens follow `docs/design/phase10/*.html` exactly. Each screen keeps the widget class it has today (`QTableWidget`, `QTreeWidget`) and changes its columns, its chrome and its empty state — no model/view rewrite. The one genuinely new seam is `packing_tool/session_stats.py`, a pure-pandas module that lifts ~145 lines of aggregation out of `MainWindow._update_statistics` so it can be tested without a window. The status chip every screen uses already exists in `shared/theme.py` with all three of its channels; this bundle only passes the keywords.

**Tech Stack:** PySide6 (Qt Widgets), pandas, pytest with `QT_QPA_PLATFORM=offscreen`, vanilla JS + CSS for the Packer Mode web tier over `QWebChannel`.

**Spec:** `docs/superpowers/specs/2026-09-19-phase10-bundle6-browser-stats-design.md`

## Global Constraints

- **Windows is production; Linux is the dev machine.** Never assume a console exists at runtime.
- **Run tests as** `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q` from the worktree root. That exact form is the only accepted one in this repo.
- **Never hardcode a colour.** Every colour and every spacing value comes from the theme tokens (`current_tokens()`, `shared/theme.py`). `style_lint` fails the build on a literal hex. This includes the web tier's CSS, which reads `theme_css_vars`.
- **`shared/` is canonical in this repo.** Editing it here is correct; after editing, it must be synced into shopify-fulfillment-tool (Task 20).
- **No new dependency.** Not one.
- **Floor density:** command bar 60px, rail item 56×64, status bar 40px, row rung 40px, controls 44px, body 12pt.
- **No UI calls from background threads.** Use signals.
- **F5 status channels:** colour is the role, `live=True` tints the ground and means the thing can still be worked, `manual=True` fills the mark and means a person decided it. `StatusChip(role, text, theme, *, live=, manual=)` in `shared/theme.py` already does all of this — do not write a new chip.
- **Copy is sentence case and says what to do next.** Not shouted capitals, not an apology.
- **Every payload function needs a named caller in the same task.** Bundle 5's review found two functions that every test exercised and nothing in `MainWindow` called; the feature shipped unreachable with a green suite. Do not repeat it.
- **Commit after every task.**

---

## File Structure

**Created:**
- `packing_tool/session_stats.py` — pure aggregation over the session DataFrame. No Qt.
- `gui/statistics_widget.py` — the Statistics screen. Consumes `session_stats`, builds `StatCard`s.
- `shared/components/statcard.py` — a big value over a small label, with a small variant.
- `gui/session_browser/session_detail_page.py` — the non-modal detail page (header, tab strip, card grid).
- `tests/test_session_stats.py`, `tests/test_packer_rollup.py`, `tests/test_order_label.py`, `tests/test_excepthook.py`, `tests/test_statistics_widget.py`, `tests/test_session_detail_page.py`.

**Modified:**
- `gui/web/packer.js`, `gui/web/packer.html`, `gui/web/packer.css` — order label, roll-up block, bounded history.
- `gui/packer_bridge.py` — `sku_rollup` payload and property.
- `gui/packer_mode_widget.py` — order label, roll-up push.
- `packing_tool/packer_logic.py` — the extras defect.
- `shared/logger.py` — the excepthook.
- `gui/session_browser/sessions_list_widget.py` — six columns, chips, filter row, state panel.
- `gui/session_browser/session_browser_widget.py` — stacked list/detail, no client sidebar.
- `gui/main_window.py` — order tree, Statistics extraction, rail label, client wiring.

**Deleted:**
- `gui/order_table_model.py`, `gui/custom_filter_proxy_model.py` — dead.
- `gui/session_browser/client_selector_widget.py` — replaced by the command bar's picker.
- `gui/session_browser/session_details_dialog.py` — replaced by the detail page.

---

# Part 1 — The five merge defects (Tasks 1–5)

### Task 1: Order numbers stop rendering as `##`

**Files:**
- Modify: `gui/web/packer.js:108,168`
- Modify: `gui/packer_mode_widget.py:320`
- Test: `tests/test_order_label.py` (create)

**Interfaces:**
- Produces: `order_label(order_number: str) -> str` in `gui/packer_bridge.py`; `orderLabel(order)` in `gui/web/packer.js`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_order_label.py
"""The order marker is added once, never twice.

Real order numbers already carry a '#' (see test_session_metadata_orders.py),
so a display site that prepends one unconditionally renders '##11019512'.
"""
from gui.packer_bridge import order_label


def test_a_number_that_already_has_a_hash_keeps_exactly_one():
    assert order_label("#11019512") == "#11019512"


def test_a_bare_number_gets_the_marker():
    assert order_label("11019512") == "#11019512"


def test_no_order_renders_as_no_order():
    assert order_label("") == "No order"
    assert order_label(None) == "No order"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_order_label.py -q`
Expected: FAIL — `ImportError: cannot import name 'order_label'`.

- [ ] **Step 3: Add the helper to `gui/packer_bridge.py`**

Put it beside the other payload helpers, above `summary_lines`:

```python
def order_label(order_number: str | None) -> str:
    """The order number as it is shown, with exactly one leading marker.

    Order numbers arrive carrying their own '#' from Shopify, but not from
    every client, so the marker is added only when it is missing rather than
    assumed either way.
    """
    if not order_number:
        return "No order"
    text = str(order_number)
    return text if text.startswith("#") else f"#{text}"
```

- [ ] **Step 4: Run it and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_order_label.py -q`
Expected: PASS, 3 tests.

- [ ] **Step 5: Use it in the Qt label**

In `gui/packer_mode_widget.py`, add `order_label` to the existing `from gui.packer_bridge import (…)` block, then replace line 320:

```python
        self._order_label.setText(order_label(order_number))
```

- [ ] **Step 6: Use it on the page**

In `gui/web/packer.js`, add the helper next to `span()`:

```js
function orderLabel(order) {
  const text = String(order == null ? "" : order);
  return text.startsWith("#") ? text : "#" + text;
}
```

Then replace the two sites:

```js
  if (b.order) els.banner.appendChild(span("doc-banner-order", orderLabel(b.order)));
```

```js
    row.appendChild(span("history-row__order", orderLabel(r.order)));
```

- [ ] **Step 7: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Expected: PASS. If a test asserted the doubled text, it encoded the defect — fix the test, and say so in the commit body.

- [ ] **Step 8: Commit**

```bash
git add tests/test_order_label.py gui/packer_bridge.py gui/packer_mode_widget.py gui/web/packer.js
git commit -m "fix(packer): show one # on an order number, not two"
```

---

### Task 2: The extras defect — reproduce before fixing

**Files:**
- Modify: `packing_tool/packer_logic.py:1317-1339`
- Test: `tests/test_packer_logic_scanning.py` (append)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: no new signature. `confirm_keep_extra(normalized_sku) -> tuple[dict, str]` keeps its shape.

**This task is a diagnosis, not a patch.** The hypothesis below is the spec's, and it may be wrong. Do not change behaviour until a test fails for the reason you think it does.

- [ ] **Step 1: Write the test that states the expected behaviour**

Append to `tests/test_packer_logic_scanning.py`. Follow the fixtures already in that file (`loaded_logic`) rather than inventing new ones:

```python
def test_keeping_one_unit_of_a_doubled_extra_leaves_the_other(loaded_logic):
    """Keep and Remove resolve an extra one unit at a time, the same way.

    Keep used to pop the whole count, so a SKU scanned twice vanished from the
    extras block on one click while Remove needed two -- which reads as 'Keep
    did not update the extra'.
    """
    loaded_logic.start_order_packing("#ORDER-001!")
    loaded_logic.process_sku_scan("NOT-IN-THIS-ORDER")
    loaded_logic.process_sku_scan("NOT-IN-THIS-ORDER")
    assert loaded_logic.current_extra_items.get("NOT-IN-THIS-ORDER") == 2

    loaded_logic.confirm_keep_extra("NOT-IN-THIS-ORDER")

    assert loaded_logic.current_extra_items.get("NOT-IN-THIS-ORDER") == 1
```

- [ ] **Step 2: Run it and read the failure carefully**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_packer_logic_scanning.py::test_keeping_one_unit_of_a_doubled_extra_leaves_the_other -q`

Expected if the hypothesis holds: FAIL with the count being `None` — `pop()` took both units.

**If it passes instead, stop.** The defect is elsewhere: the logic is fine and the fault is in the bridge or the page. Write what you observed into the task's commit message, then bisect forward — `show_extras_panel` → `set_extras` → `extrasChanged` → `renderExtras` — and fix what the evidence actually shows. Do not proceed to Step 3 with a passing test.

- [ ] **Step 3: Make Keep symmetric with Remove**

In `packing_tool/packer_logic.py`, replace the body of `confirm_keep_extra`:

```python
    def confirm_keep_extra(self, normalized_sku: str) -> tuple[dict, str]:
        """
        Acknowledges one unit of an extra item as intentionally included.
        Decrements the extra count; removes the key when it reaches 0, then
        checks whether the order can complete.

        One unit per click, like remove_extra_item: a SKU scanned twice takes
        two decisions, because each unit is its own decision.

        Returns: ({}, "ORDER_NOW_COMPLETE"), ({}, "EXTRA_CLEARED") or
        ({}, "EXTRA_PENDING")
        """
        count = self.current_extra_items.get(normalized_sku, 0)
        if count > 1:
            self.current_extra_items[normalized_sku] = count - 1
        else:
            self.current_extra_items.pop(normalized_sku, None)
        return self._maybe_complete_after_extra_resolution()
```

- [ ] **Step 4: Run it and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_packer_logic_scanning.py -q`
Expected: PASS.

- [ ] **Step 5: Prove the test bites**

Put `pop()` back temporarily, re-run, confirm the new test fails, then restore the fix. A regression test nobody has seen fail is a guess.

- [ ] **Step 6: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Expected: PASS. A test asserting that Keep clears everything encoded the old behaviour — update it and note it in the commit body.

- [ ] **Step 7: Commit**

```bash
git add packing_tool/packer_logic.py tests/test_packer_logic_scanning.py
git commit -m "fix(packer): Keep resolves one unit of an extra, like Remove"
```

---

### Task 3: The scan history stops stretching the page

**Files:**
- Modify: `gui/web/packer.css:242`

**Interfaces:**
- Produces: nothing. CSS only.

- [ ] **Step 1: Bound the block**

`.history` has `overflow-y: auto` and no height to overflow against, so it grows instead of scrolling. Give it one. In `gui/web/packer.css`, replace the `.history` rule:

```css
/* The block scrolls rather than grows: a long session would otherwise push
   the side column past the viewport and take the roll-up below it with it.
   No history is dropped -- every order in the session stays reachable. */
.history {
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  max-height: 280px;
}
```

- [ ] **Step 2: Check it by eye in both themes**

Render Packer Mode with more than a dozen history rows and confirm the block scrolls internally and the side column's total height stops changing. Use the offscreen `QWebEngineView` render used in Bundle 2 (`QT_QPA_PLATFORM=offscreen`), since this VM has no browser.

- [ ] **Step 3: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Expected: PASS, unchanged.

- [ ] **Step 4: Commit**

```bash
git add gui/web/packer.css
git commit -m "fix(packer): the history block scrolls instead of stretching the page"
```

---

### Task 4: The per-SKU roll-up returns to the side column

**Files:**
- Modify: `gui/packer_bridge.py`, `gui/packer_mode_widget.py`, `gui/web/packer.html`, `gui/web/packer.js`, `gui/web/packer.css`
- Test: `tests/test_packer_rollup.py` (create)

**Interfaces:**
- Consumes: `order_label` from Task 1 (not used here, but the same module).
- Produces: `sku_rollup(rows: list[dict]) -> list[dict]` in `gui/packer_bridge.py`, each entry `{"sku": str, "product": str, "packed": int, "required": int, "state": "complete"|"partial"|"pending"}`; bridge property `skuRollup`; `PackerBridge.set_sku_rollup(rows)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_packer_rollup.py
"""One row per distinct SKU, summed across the order's lines.

The SKU list shows one row per line of the order. The roll-up consolidates
them, which is what the four-column summary table did before Bundle 4 replaced
it with a single count.
"""
from gui.packer_bridge import sku_rollup


def _row(sku, product, packed, required):
    return {"sku": sku, "product": product, "packed": packed, "required": required}


def test_two_lines_of_one_sku_become_one_row():
    rows = [_row("A-1", "Mouse", 1, 2), _row("A-1", "Mouse", 0, 3)]
    assert sku_rollup(rows) == [
        {"sku": "A-1", "product": "Mouse", "packed": 1, "required": 5, "state": "partial"}
    ]


def test_state_is_complete_only_when_every_unit_is_packed():
    rows = [_row("A-1", "Mouse", 2, 2), _row("B-2", "Cable", 0, 1)]
    assert [r["state"] for r in sku_rollup(rows)] == ["complete", "pending"]


def test_rows_are_ordered_by_sku_so_the_block_does_not_reshuffle_mid_order():
    rows = [_row("B-2", "Cable", 0, 1), _row("A-1", "Mouse", 0, 1)]
    assert [r["sku"] for r in sku_rollup(rows)] == ["A-1", "B-2"]


def test_no_rows_is_an_empty_roll_up():
    assert sku_rollup([]) == []
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_packer_rollup.py -q`
Expected: FAIL — `ImportError: cannot import name 'sku_rollup'`.

- [ ] **Step 3: Write it, beside `summary_lines` in `gui/packer_bridge.py`**

```python
def sku_rollup(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One entry per distinct SKU, summed across the order's lines.

    The SKU list is per line; this is per SKU. An order that lists the same
    SKU twice is two rows up there and one row here, which is the whole point
    of the block.
    """
    totals: dict[str, dict[str, Any]] = {}
    for row in rows:
        sku = row.get("sku", "")
        entry = totals.setdefault(
            sku,
            {"sku": sku, "product": row.get("product", ""), "packed": 0, "required": 0},
        )
        entry["packed"] += int(row.get("packed", 0) or 0)
        entry["required"] += int(row.get("required", 0) or 0)

    out = []
    for sku in sorted(totals):
        entry = totals[sku]
        if entry["packed"] >= entry["required"]:
            entry["state"] = "complete"
        elif entry["packed"] > 0:
            entry["state"] = "partial"
        else:
            entry["state"] = "pending"
        out.append(entry)
    return out
```

- [ ] **Step 4: Run it and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_packer_rollup.py -q`
Expected: PASS, 4 tests.

- [ ] **Step 5: Carry it over the bridge**

In `gui/packer_bridge.py`, beside the existing `extras` property, add the notify property and its setter. Follow the shape of `set_extras` exactly:

```python
    skuRollupChanged = Signal()
```

```python
        self._sku_rollup: list = []
```

```python
    def _get_sku_rollup(self) -> list:
        return self._sku_rollup

    skuRollup = Property("QVariantList", _get_sku_rollup, notify=skuRollupChanged)
```

```python
    def set_sku_rollup(self, rows: list) -> None:
        self._sku_rollup = list(rows or [])
        self.skuRollupChanged.emit()
```

- [ ] **Step 6: Give it a caller**

This is the step Bundle 5's review caught missing. In `gui/packer_mode_widget.py`, add `sku_rollup` to the `from gui.packer_bridge import (…)` block, and push it everywhere `self._rows` changes — in `_push_rows`, beside the existing `self.bridge.set_items(...)` call:

```python
        self.bridge.set_sku_rollup(sku_rollup(self._rows))
```

Also clear it where `set_extras([])` is cleared (`gui/packer_mode_widget.py:411`):

```python
        self.bridge.set_sku_rollup([])
```

- [ ] **Step 7: Draw the block**

In `gui/web/packer.html`, add the block to the side column, directly after the history block:

```html
      <div class="side-block">
        <div class="side-block-title">Items by SKU</div>
        <div class="rollup" id="rollup-rows"></div>
      </div>
```

In `gui/web/packer.js`, add the renderer, reusing the existing `CHIP` table so the roll-up's chips and the SKU list's chips can never disagree:

```js
function renderRollup() {
  const rows = state.bridge.skuRollup || [];
  els.rollupRows.textContent = "";
  if (rows.length === 0) {
    els.rollupRows.appendChild(span("rollup-row__sku", "No items yet"));
    return;
  }
  rows.forEach(function (r) {
    const row = document.createElement("div");
    row.className = "rollup-row";
    row.appendChild(span("rollup-row__sku", r.sku));
    row.appendChild(span("rollup-row__qty", r.packed + " / " + r.required));
    const chip = CHIP[r.state] || CHIP.pending;
    row.appendChild(span(chip.cls, chip.text));
    els.rollupRows.appendChild(row);
  });
}
```

Wire it into the `QWebChannel` callback beside the others — the element handle, the signal, and the first render:

```js
  els.rollupRows = document.getElementById("rollup-rows");
```
```js
  bridge.skuRollupChanged.connect(renderRollup);
```
```js
  renderRollup();
```

In `gui/web/packer.css`, add the rules beside `.history`. Every value is a token — no literal colour:

```css
/* The roll-up sits where the history block's growth used to go (Task 3). */
.rollup { display: flex; flex-direction: column; max-height: 320px; overflow-y: auto; }
.rollup-row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  align-items: center;
  gap: var(--space-2);
  min-height: 40px;
  border-bottom: 1px solid var(--border);
}
.rollup-row:last-child { border-bottom: none; }
.rollup-row__sku { font-family: var(--font-family-mono); }
.rollup-row__qty { color: var(--text-secondary); }
```

- [ ] **Step 8: Check it renders in both themes**

Render P2 (an order part-packed) offscreen and confirm the block shows one row per SKU, the chips match the SKU list's, and the side column fits at 1366×768.

- [ ] **Step 9: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add gui/packer_bridge.py gui/packer_mode_widget.py gui/web/ tests/test_packer_rollup.py
git commit -m "feat(packer): the per-SKU roll-up returns, in the side column"
```

---

### Task 5: A crash reaches the log

**Files:**
- Modify: `shared/logger.py`
- Modify: `gui_main.py` (or whichever module calls `setup_logging` — find it with `grep -rn "setup_logging(" --include=*.py .`)
- Test: `tests/test_excepthook.py` (create)

**Interfaces:**
- Produces: `install_crash_logging(logger_name: str = "") -> None` in `shared/logger.py`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_excepthook.py
"""An unhandled exception reaches the log.

A frozen Windows GUI build has no console, so anything Python writes to stderr
is discarded. Without a hook, a crash leaves nothing behind at all -- which is
exactly what the owner saw after the Bundle 5 merge.
"""
import logging
import sys
import threading

from shared.logger import install_crash_logging


def test_an_unhandled_exception_is_logged_with_its_traceback(caplog):
    previous = sys.excepthook
    try:
        install_crash_logging()
        with caplog.at_level(logging.CRITICAL):
            try:
                raise ValueError("the thing that went wrong")
            except ValueError:
                sys.excepthook(*sys.exc_info())
    finally:
        sys.excepthook = previous

    assert "the thing that went wrong" in caplog.text
    assert "ValueError" in caplog.text
    assert "Traceback" in caplog.text


def test_the_previous_hook_still_runs(caplog):
    previous = sys.excepthook
    seen = []
    sys.excepthook = lambda *args: seen.append(args[0])
    try:
        install_crash_logging()
        try:
            raise ValueError("chained")
        except ValueError:
            sys.excepthook(*sys.exc_info())
    finally:
        sys.excepthook = previous

    assert seen == [ValueError], "the hook that was there before must still run"


def test_a_thread_crash_is_logged_too(caplog):
    previous = threading.excepthook
    try:
        install_crash_logging()
        with caplog.at_level(logging.CRITICAL):
            def boom():
                raise RuntimeError("in a worker thread")

            thread = threading.Thread(target=boom)
            thread.start()
            thread.join()
    finally:
        threading.excepthook = previous

    assert "in a worker thread" in caplog.text


def test_a_keyboard_interrupt_is_not_logged_as_a_crash(caplog):
    previous = sys.excepthook
    try:
        install_crash_logging()
        with caplog.at_level(logging.CRITICAL):
            try:
                raise KeyboardInterrupt()
            except KeyboardInterrupt:
                sys.excepthook(*sys.exc_info())
    finally:
        sys.excepthook = previous

    assert caplog.text == "", "Ctrl-C is a person leaving, not a crash"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_excepthook.py -q`
Expected: FAIL — `ImportError: cannot import name 'install_crash_logging'`.

- [ ] **Step 3: Write it in `shared/logger.py`**

Append below `setup_logging`:

```python
def install_crash_logging(logger_name: str = "") -> None:
    """Send unhandled exceptions to the log instead of to stderr.

    A frozen Windows GUI build has no console, so a traceback printed to
    stderr is discarded and a crash leaves no trace at all. Both hooks are
    installed -- a worker thread's crash is exactly as invisible as the main
    thread's -- and each chains to whatever was there before, so a debugger or
    a test harness that installed its own hook keeps working.

    Safe to call more than once: the second call chains onto the first, which
    logs the same record twice but never loses one.
    """
    crash_logger = logging.getLogger(logger_name)
    previous_hook = sys.excepthook
    previous_thread_hook = threading.excepthook

    def _log_unhandled(exc_type, exc_value, exc_tb):
        # Ctrl-C is a person leaving, not a fault. Logging it at CRITICAL
        # would put a false crash in the file every time the app is closed
        # from a console during development.
        if not issubclass(exc_type, KeyboardInterrupt):
            crash_logger.critical(
                "Unhandled exception", exc_info=(exc_type, exc_value, exc_tb)
            )
        previous_hook(exc_type, exc_value, exc_tb)

    def _log_unhandled_in_thread(args):
        if args.exc_type is not SystemExit:
            crash_logger.critical(
                "Unhandled exception in thread %s",
                getattr(args.thread, "name", "?"),
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
        previous_thread_hook(args)

    sys.excepthook = _log_unhandled
    threading.excepthook = _log_unhandled_in_thread
```

Add `import sys` and `import threading` to the module's imports if they are not already there.

- [ ] **Step 4: Run it and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_excepthook.py -q`
Expected: PASS, 4 tests.

- [ ] **Step 5: Give it a caller**

Find the `setup_logging(...)` call at startup and add the hook immediately after it, so the hook is live before any window is built:

```python
    install_crash_logging()
```

Import it from `shared.logger` alongside `setup_logging`. **Verify by grep that the call exists in the startup path** — a hook nothing installs is the Bundle 5 failure mode.

- [ ] **Step 6: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add shared/logger.py gui_main.py tests/test_excepthook.py
git commit -m "fix(logging): unhandled exceptions reach the log, not a discarded stderr"
```

---

# Part 2 — Statistics (Tasks 6–9)

Statistics comes before the Session Browser because it produces the pure module the tests bind to, and because it is the roadmap's stated "done when".

### Task 6: `packing_tool/session_stats.py` — session totals

**Files:**
- Create: `packing_tool/session_stats.py`
- Test: `tests/test_session_stats.py` (create)

**Interfaces:**
- Produces: `session_totals(df: pd.DataFrame, completed_orders: list[str]) -> dict` with keys `orders`, `completed`, `items`, `unique_skus`, `progress_pct` (all `int`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session_stats.py
"""Session aggregation, with no window in sight.

These three functions carry ~145 lines that used to live inside
MainWindow._update_statistics, where testing them meant building a window.
"""
import pandas as pd

from packing_tool.session_stats import session_totals


def _df():
    return pd.DataFrame(
        [
            {"Order_Number": "#1", "SKU": "A-1", "Product_Name": "Mouse", "Quantity": 2, "Courier": "DPD"},
            {"Order_Number": "#1", "SKU": "B-2", "Product_Name": "Cable", "Quantity": 1, "Courier": "DPD"},
            {"Order_Number": "#2", "SKU": "A-1", "Product_Name": "Mouse", "Quantity": 3, "Courier": "GLS"},
        ]
    )


def test_totals_count_orders_lines_and_distinct_skus():
    totals = session_totals(_df(), [])
    assert totals["orders"] == 2
    assert totals["items"] == 3
    assert totals["unique_skus"] == 2


def test_progress_is_the_share_of_orders_completed():
    assert session_totals(_df(), ["#1"])["progress_pct"] == 50
    assert session_totals(_df(), ["#1", "#2"])["progress_pct"] == 100


def test_an_empty_session_does_not_divide_by_zero():
    empty = pd.DataFrame(columns=["Order_Number", "SKU", "Product_Name", "Quantity", "Courier"])
    totals = session_totals(empty, [])
    assert totals == {"orders": 0, "completed": 0, "items": 0, "unique_skus": 0, "progress_pct": 0}
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_session_stats.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'packing_tool.session_stats'`.

- [ ] **Step 3: Write the module**

```python
"""Live aggregation over the current session's packing list.

Pure pandas, no Qt: the Statistics screen reads these three functions and
builds widgets from what they return.

This is deliberately NOT shared/stats_manager.py. That module is a persisted,
cross-tool event log (record_analysis, record_packing, get_global_stats) that
both tools write to a shared JSON file. What is here is the opposite: a
throwaway aggregation over the DataFrame currently in memory, using Packing
Tool's own column names. Putting it in shared/ would push pandas and those
column names into a module Shopify also receives, for no caller.
"""

from typing import Any

import pandas as pd


def session_totals(df: pd.DataFrame, completed_orders: list[str]) -> dict[str, int]:
    """Orders, completed orders, lines, distinct SKUs and percent complete."""
    if df is None or df.empty:
        return {"orders": 0, "completed": 0, "items": 0, "unique_skus": 0, "progress_pct": 0}

    total_orders = int(df["Order_Number"].nunique())
    completed = len(completed_orders or [])
    return {
        "orders": total_orders,
        "completed": completed,
        "items": int(len(df)),
        "unique_skus": int(df["SKU"].nunique()),
        "progress_pct": int(completed / total_orders * 100) if total_orders else 0,
    }
```

- [ ] **Step 4: Run it and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_session_stats.py -q`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add packing_tool/session_stats.py tests/test_session_stats.py
git commit -m "feat(stats): session totals as a pure function over the DataFrame"
```

---

### Task 7: `session_stats` — courier totals and the SKU summary

**Files:**
- Modify: `packing_tool/session_stats.py`
- Test: `tests/test_session_stats.py` (append)

**Interfaces:**
- Consumes: `session_totals` from Task 6.
- Produces: `courier_totals(df) -> list[dict]` with keys `courier`, `orders`, `items`; `sku_summary(df, session_packing_state) -> list[dict]` with keys `sku`, `product`, `required`, `packed`, `state` (`"packed"|"partial"|"pending"`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_session_stats.py`:

```python
from packing_tool.session_stats import courier_totals, sku_summary


def test_courier_totals_count_orders_and_summed_quantity():
    assert courier_totals(_df()) == [
        {"courier": "DPD", "orders": 1, "items": 3},
        {"courier": "GLS", "orders": 1, "items": 3},
    ]


def test_a_session_with_no_courier_column_has_no_courier_totals():
    assert courier_totals(_df().drop(columns=["Courier"])) == []


def test_sku_summary_sums_quantity_across_orders():
    rows = sku_summary(_df(), {})
    assert [(r["sku"], r["required"]) for r in rows] == [("A-1", 5), ("B-2", 1)]


def test_an_untouched_sku_is_pending():
    assert sku_summary(_df(), {})[0]["state"] == "pending"


def test_a_partly_scanned_sku_is_partial_and_a_finished_one_is_packed():
    state = {"#1": [{"original_sku": "A-1", "packed": 2}, {"original_sku": "B-2", "packed": 1}]}
    by_sku = {r["sku"]: r for r in sku_summary(_df(), state)}
    assert by_sku["A-1"]["state"] == "partial"
    assert by_sku["B-2"]["state"] == "packed"


def test_a_malformed_item_state_is_skipped_rather_than_crashing():
    """A restored session can carry junk; the screen must still draw."""
    state = {"#1": ["not a dict", {"original_sku": "B-2", "packed": 1}]}
    by_sku = {r["sku"]: r for r in sku_summary(_df(), state)}
    assert by_sku["B-2"]["state"] == "packed"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_session_stats.py -q`
Expected: FAIL — `ImportError: cannot import name 'courier_totals'`.

- [ ] **Step 3: Write both functions**

Append to `packing_tool/session_stats.py`. The `itertuples` and vectorised `groupby` below are carried over from `_update_statistics` unchanged — they are deliberate optimisations with their own comments, and this is a move, not a rewrite:

```python
def courier_totals(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Orders and summed quantity per courier, ordered by courier name."""
    if df is None or df.empty or "Courier" not in df.columns:
        return []

    grouped = (
        df.groupby("Courier")
        .agg({"Order_Number": "nunique",
              "Quantity": lambda x: pd.to_numeric(x, errors="coerce").sum()})
        .reset_index()
    )
    # itertuples, not iterrows: 5-10x faster over the same rows.
    return [
        {
            "courier": row.Courier,
            "orders": int(row.Order_Number),
            "items": int(row.Quantity) if pd.notna(row.Quantity) else 0,
        }
        for row in grouped.itertuples(index=False)
    ]


def sku_summary(
    df: pd.DataFrame, session_packing_state: dict[str, Any]
) -> list[dict[str, Any]]:
    """One row per distinct SKU: what the session needs, and what is packed."""
    if df is None or df.empty:
        return []

    totals = (
        df.groupby(["SKU", "Product_Name"])
        .agg({"Quantity": lambda x: pd.to_numeric(x, errors="coerce").sum()})
        .reset_index()
    )

    state = session_packing_state or {}
    packed_by_sku = _packed_by_sku(df, state)

    rows = []
    for row in totals.itertuples(index=False):
        required = int(row.Quantity) if pd.notna(row.Quantity) else 0
        packed = packed_by_sku.get(row.SKU, 0)
        if packed >= required and required > 0:
            sku_state = "packed"
        elif packed > 0:
            sku_state = "partial"
        else:
            sku_state = "pending"
        rows.append(
            {
                "sku": row.SKU,
                "product": row.Product_Name,
                "required": required,
                "packed": packed,
                "state": sku_state,
            }
        )
    return rows


def _packed_by_sku(df: pd.DataFrame, state: dict[str, Any]) -> dict[str, int]:
    """Units packed per SKU: in-progress scans plus everything in a closed order."""
    packed: dict[str, int] = {}

    for order_state in state.get("in_progress", {}).values():
        for item_state in order_state:
            # A restored session can carry a non-dict here. Skip it rather
            # than let one bad entry take the whole screen down.
            if not isinstance(item_state, dict):
                continue
            sku = item_state.get("original_sku")
            if sku:
                packed[sku] = packed.get(sku, 0) + int(item_state.get("packed", 0) or 0)

    completed = state.get("completed_orders", [])
    if completed:
        closed = df[df["Order_Number"].isin(completed)]
        if not closed.empty:
            # Vectorised: O(n) instead of the nested per-order loop this
            # replaced.
            by_sku = (
                closed.groupby("SKU")["Quantity"]
                .apply(lambda x: pd.to_numeric(x, errors="coerce").sum())
                .fillna(0)
                .astype(int)
            )
            for sku, qty in by_sku.items():
                packed[sku] = packed.get(sku, 0) + int(qty)

    return packed
```

- [ ] **Step 4: Run them and watch them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_session_stats.py -q`
Expected: PASS, 9 tests.

- [ ] **Step 5: Commit**

```bash
git add packing_tool/session_stats.py tests/test_session_stats.py
git commit -m "feat(stats): courier totals and SKU summary as pure functions"
```

---

### Task 8: The `StatCard` component

**Files:**
- Create: `shared/components/statcard.py`
- Modify: `shared/components/__init__.py`
- Test: `tests/test_statcard.py` (create)

**Interfaces:**
- Produces: `StatCard(value: str, label: str, *, small: bool = False, parent=None)` with `set_value(value: str) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_statcard.py
"""The stat card: a big number over a small label.

Two hand-rolled copies of this widget exist in main_window.py today -- the
session-totals card and the courier card -- which is why it is a component.
"""
import pytest

from shared.components.statcard import StatCard


@pytest.fixture
def card(qtbot):
    widget = StatCard("14", "Orders")
    qtbot.addWidget(widget)
    return widget


def test_the_card_shows_its_value_and_its_label(card):
    assert card.value_label.text() == "14"
    assert card.label_label.text() == "Orders"


def test_the_value_can_be_replaced_without_rebuilding_the_card(card):
    card.set_value("15")
    assert card.value_label.text() == "15"


def test_the_small_variant_is_the_same_widget_at_a_smaller_scale(qtbot):
    small = StatCard("6", "DPD · orders", small=True)
    qtbot.addWidget(small)
    assert small.value_label.text() == "6"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_statcard.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write the component**

Follow `shared/components/card.py`'s shape: a `Card` subclass is wrong here (the artboard's stat card has its own type scale), so compose one. Read `card.py` and `state_panel.py` first and match how they resolve tokens and re-run on a theme change — `StatePanel` shows the `on_theme_changed` pattern, and a baked colour is ADR 0003's stale-palette bug.

```python
"""A single statistic: a big value over a small label, in a bordered box."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QVBoxLayout, QWidget

from shared.components.card import Card


class StatCard(QWidget):
    """One number and what it counts.

    Attributes:
        value_label: the big number.
        label_label: what it counts.
    """

    def __init__(self, value: str, label: str, *, small: bool = False, parent=None) -> None:
        super().__init__(parent)
        self._card = Card(margins=(12, 8, 12, 8), spacing=2)
        self.value_label = self._card.add_text(value, "caption" if small else "heading")
        self.value_label.setAlignment(Qt.AlignCenter)
        self.label_label = self._card.add_text(label, "caption")
        self.label_label.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._card)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)
```

Adjust the type-scale role names to whatever `Card.add_text` actually accepts — read `TYPE_SCALE` in `shared/theme.py` and use the roles that exist. Export `StatCard` from `shared/components/__init__.py` beside the others.

- [ ] **Step 4: Run it and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_statcard.py -q`
Expected: PASS, 3 tests.

- [ ] **Step 5: Check it against S1 in both themes**

Render the Statistics screen's stat grid offscreen in dark and light and compare with `docs/design/phase10/statistics.html` S1 and S1-L.

- [ ] **Step 6: Commit**

```bash
git add shared/components/statcard.py shared/components/__init__.py tests/test_statcard.py
git commit -m "feat(components): StatCard, the unit the Statistics screen is built from"
```

---

### Task 9: The Statistics screen moves out of `main_window.py`

**Files:**
- Create: `gui/statistics_widget.py`
- Modify: `gui/main_window.py:339-349, 665-905, 1959, 2092, 2105`
- Test: `tests/test_statistics_widget.py` (create)

**Interfaces:**
- Consumes: `session_totals`, `courier_totals`, `sku_summary` (Tasks 6–7); `StatCard` (Task 8).
- Produces: `StatisticsWidget()` with `update_from(df, session_packing_state)` and `show_empty()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_statistics_widget.py
"""The Statistics screen draws what session_stats computes -- and nothing else.

The point of the split is that the arithmetic is tested in
tests/test_session_stats.py without a window. What is tested here is only that
the screen shows what it is given, and shows a state panel when it is given
nothing.
"""
import pandas as pd
import pytest

from gui.statistics_widget import StatisticsWidget


@pytest.fixture
def screen(qtbot):
    widget = StatisticsWidget()
    qtbot.addWidget(widget)
    return widget


def _df():
    return pd.DataFrame(
        [
            {"Order_Number": "#1", "SKU": "A-1", "Product_Name": "Mouse", "Quantity": 2, "Courier": "DPD"},
            {"Order_Number": "#2", "SKU": "B-2", "Product_Name": "Cable", "Quantity": 1, "Courier": "GLS"},
        ]
    )


def test_the_totals_row_shows_the_computed_numbers(screen):
    screen.update_from(_df(), {"completed_orders": ["#1"]})
    assert screen.cards["orders"].value_label.text() == "2"
    assert screen.cards["completed"].value_label.text() == "1"
    assert screen.cards["progress_pct"].value_label.text() == "50%"


def test_one_courier_card_per_courier(screen):
    screen.update_from(_df(), {})
    assert screen.courier_layout.count() == 2


def test_courier_cards_are_replaced_on_refresh_not_appended(screen):
    screen.update_from(_df(), {})
    screen.update_from(_df(), {})
    assert screen.courier_layout.count() == 2


def test_the_sku_table_has_one_row_per_sku(screen):
    screen.update_from(_df(), {})
    assert screen.sku_table.rowCount() == 2


def test_with_no_packing_list_the_screen_shows_its_state_panel(screen):
    screen.show_empty()
    assert screen.state_panel.isVisible()
    assert not screen.content.isVisible()


def test_loading_a_list_replaces_the_state_panel_with_the_content(screen):
    screen.show_empty()
    screen.update_from(_df(), {})
    assert screen.content.isVisible()
    assert not screen.state_panel.isVisible()
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_statistics_widget.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'gui.statistics_widget'`.

- [ ] **Step 3: Write the screen**

Move the *layout* from `main_window.py:665-748` and none of the arithmetic. Structure per S1: a `QStackedWidget` (or a `setVisible` pair) holding `content` and `state_panel`; inside `content`, a scroll area with three sections under `sec-title` headings — Session totals (`StatCard` grid), By courier (`StatCard(small=True)` row), SKU summary (`Card` + `QTableWidget`).

Key points the tests pin:
- `self.cards` is a dict keyed `orders`, `completed`, `items`, `unique_skus`, `progress_pct`.
- `self.courier_layout` is cleared before each refresh — reuse the existing teardown loop from `main_window.py:782-786`.
- `self.sku_table` has four columns: SKU, Product, Total qty, Status.
- The Status cell is a `StatusChip`, not text:

```python
_SKU_CHIP = {
    "packed": ("status_success", "Packed", False, False),
    "partial": ("status_warning", "Partial", True, False),
    "pending": ("text_secondary", "Pending", False, False),
}
```
```python
role, text, live, manual = _SKU_CHIP[row["state"]]
self.sku_table.setCellWidget(
    index, 3, StatusChip(role, text, current_tokens(), live=live, manual=manual)
)
```
- `show_empty()` puts up a `StatePanel`. Copy, per the artboard's S2 and the project's voice — sentence case, says what to do:

```python
StatePanel(
    "No session open",
    "Load a packing list to see this session's totals.",
    action_text="Open a packing list",
)
```
- `update_from(df, session_packing_state)` calls the three `session_stats` functions and fills the widgets. No pandas in this file beyond passing the DataFrame through.

- [ ] **Step 4: Run it and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_statistics_widget.py -q`
Expected: PASS, 6 tests.

- [ ] **Step 5: Wire it into `MainWindow` and delete the inline code**

In `gui/main_window.py`:
- Replace the `stats_tab` block at `:345-349` with `self.statistics_widget = StatisticsWidget()` added as the tab.
- Delete `_setup_statistics_tab` (`:665-748`) and `_update_statistics`' body (`:750-903`) entirely.
- Replace `_update_statistics` with the delegation, keeping the name so its three call sites (`:1959`, `:2092`, `:2105`) need no change:

```python
    def _update_statistics(self):
        """Refresh the Statistics screen from the current session."""
        if not self.logic or getattr(self.logic, "processed_df", None) is None:
            self.statistics_widget.show_empty()
            return
        self.statistics_widget.update_from(
            self.logic.processed_df, self.logic.session_packing_state
        )
```

Note the behaviour change, and that it is deliberate: the old body returned early and left the cards at their last values when there was no session. It now shows the state panel, which is what S2 draws.

- [ ] **Step 6: Prove `main_window.py` builds no Statistics widgets**

Run: `grep -n "stats_total_orders\|courier_stats_layout\|sku_table\|_setup_statistics_tab" gui/main_window.py`
Expected: no output. This is the roadmap's "done when" condition for Statistics.

- [ ] **Step 7: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Expected: PASS. Tests reaching into `main_window.stats_*` attributes must be repointed at `main_window.statistics_widget`.

- [ ] **Step 8: Commit**

```bash
git add gui/statistics_widget.py gui/main_window.py tests/test_statistics_widget.py
git commit -m "refactor(stats): the Statistics screen leaves main_window.py"
```

---

# Part 3 — Session Browser (Tasks 10–14)

### Task 10: One client selector, not two

**Files:**
- Modify: `gui/main_window.py:1004-1018, 352-358`
- Modify: `gui/session_browser/session_browser_widget.py`
- Delete: `gui/session_browser/client_selector_widget.py`
- Test: `tests/test_session_browser_client.py` (create)

**Interfaces:**
- Consumes: nothing.
- Produces: `SessionBrowserWidget.load_client(client_id: str) -> None` becomes the only way the browser learns its client.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session_browser_client.py
"""The command bar's client picker is the browser's client picker.

The browser used to carry a second, independent one down its left side, so the
shell could be on one client while the browser showed another.
"""


def test_changing_the_client_in_the_command_bar_loads_it_in_the_browser(main_window):
    loaded = []
    main_window.session_browser.load_client = loaded.append

    index = main_window.client_combo.findData("test-client")
    main_window.client_combo.setCurrentIndex(index)

    assert loaded == ["test-client"]


def test_the_browser_has_no_client_selector_of_its_own(main_window):
    assert not hasattr(main_window.session_browser, "client_selector")
```

Use whatever `main_window` fixture `tests/` already provides — find it with `grep -rn "def main_window" tests/`. If there is none, build the window in the test the way the existing `MainWindow` tests do, and seed one client.

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_session_browser_client.py -q`
Expected: FAIL — nothing calls `load_client`.

- [ ] **Step 3: Wire the command bar to the browser**

In `gui/main_window.py`, at the end of `on_client_changed` (after `logger.debug(f"Current client set to: {client_id}")`):

```python
        # The browser has no picker of its own (Bundle 6): the command bar's
        # is the only one, so it has to push the change.
        if hasattr(self, "session_browser"):
            self.session_browser.load_client(client_id)
```

- [ ] **Step 4: Remove the sidebar**

In `gui/session_browser/session_browser_widget.py`: drop the `ClientSelectorWidget` import and construction, drop the `QSplitter`, and lay the list widget directly into the layout. `load_client(client_id)` forwards to `SessionsListWidget.load_client` as it does today. Update the module docstring's ASCII diagram — it draws the sidebar that is going away. Then `git rm gui/session_browser/client_selector_widget.py`.

- [ ] **Step 5: Run it and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_session_browser_client.py -q`
Expected: PASS.

- [ ] **Step 6: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Expected: PASS. Delete tests that only covered `ClientSelectorWidget`.

- [ ] **Step 7: Commit**

```bash
git add -A gui/ tests/test_session_browser_client.py
git commit -m "refactor(browser): the command bar's client picker is the only one"
```

---

### Task 11: The session list gets its status chips

**Files:**
- Modify: `gui/session_browser/sessions_list_widget.py:51-59, _make_status_cell`
- Test: `tests/test_sessions_list_status.py` (create)

**Interfaces:**
- Consumes: `StatusChip` from `shared/theme.py` — already complete, do not extend it.
- Produces: `STATUS_CONFIG[key]` gains `live: bool` and `manual: bool`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sessions_list_status.py
"""F5's three channels, one table.

colour = the role; live = the session can still be worked; manual = a person
decided this, rather than the system inferring it.
"""
from gui.session_browser.sessions_list_widget import STATUS_CONFIG


def test_every_status_declares_all_three_channels():
    for key, cfg in STATUS_CONFIG.items():
        assert "role" in cfg and "live" in cfg and "manual" in cfg, key


def test_only_the_two_states_a_packer_declares_carry_the_solid_mark():
    manual = {k for k, cfg in STATUS_CONFIG.items() if cfg["manual"]}
    assert manual == {"paused", "incomplete"}


def test_tint_marks_the_sessions_that_can_still_be_worked():
    live = {k for k, cfg in STATUS_CONFIG.items() if cfg["live"]}
    assert live == {"in_progress", "paused", "stale", "incomplete"}


def test_an_unknown_status_still_renders_a_cell(qtbot):
    from gui.session_browser.sessions_list_widget import SessionsListWidget

    widget = SessionsListWidget(registry_manager=None, session_history_manager=None)
    qtbot.addWidget(widget)
    cell = widget._make_status_cell("something_new")
    assert cell is not None
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_sessions_list_status.py -q`
Expected: FAIL — `KeyError: 'live'`.

- [ ] **Step 3: Extend the table**

Replace `STATUS_CONFIG` (`:51-59`). The values come straight off artboard B1's seven rows:

```python
# F5's three channels per status. `live` tints the ground and means the
# session can still be worked; `manual` fills the mark and means a packer
# declared this state rather than the system inferring it -- which is true of
# exactly two of the seven.
STATUS_CONFIG = {
    "not_started": {"label": "Not started", "role": "text_secondary", "live": False, "manual": False},
    "in_progress": {"label": "Active",      "role": "status_info",    "live": True,  "manual": False},
    "paused":      {"label": "Paused",      "role": "status_warning", "live": True,  "manual": True},
    "stale":       {"label": "Stale",       "role": "status_warning", "live": True,  "manual": False},
    "completed":   {"label": "Completed",   "role": "status_success", "live": False, "manual": False},
    "incomplete":  {"label": "Incomplete",  "role": "status_danger",  "live": True,  "manual": True},
    "abandoned":   {"label": "Abandoned",   "role": "status_danger",  "live": False, "manual": False},
}

_UNKNOWN_STATUS = {"role": "text_secondary", "live": False, "manual": False}
```

- [ ] **Step 4: Replace the dot-and-label cell with one chip**

```python
    def _make_status_cell(self, status: str) -> QWidget:
        cfg = {
            **_UNKNOWN_STATUS,
            "label": status.replace("_", " ").capitalize(),
            **STATUS_CONFIG.get(status, {}),
        }
        cell = QWidget()
        layout = QHBoxLayout(cell)
        layout.setContentsMargins(8, 0, 4, 0)
        layout.addWidget(
            StatusChip(
                cfg["role"], cfg["label"], current_tokens(),
                live=cfg["live"], manual=cfg["manual"],
            )
        )
        layout.addStretch()
        return cell
```

Swap the `StatusDot` import for `StatusChip`. Drop `StatusDot` from the imports if nothing else in the file uses it.

- [ ] **Step 5: Run it and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_sessions_list_status.py -q`
Expected: PASS, 4 tests.

- [ ] **Step 6: Compare against B1 in both themes**

Render the list offscreen with one session in each of the seven states and compare chip for chip with `docs/design/phase10/session-browser.html` B1 and B1-L.

- [ ] **Step 7: Run the whole suite and commit**

```bash
git add gui/session_browser/sessions_list_widget.py tests/test_sessions_list_status.py
git commit -m "feat(browser): session status as an F5 chip, three channels from one table"
```

---

### Task 12: The list's six columns

**Files:**
- Modify: `gui/session_browser/sessions_list_widget.py` — column constants, `_fill_row`, `_apply_filters`, sorting
- Test: `tests/test_sessions_list_columns.py` (create)

**Interfaces:**
- Consumes: Task 11's `STATUS_CONFIG`.
- Produces: `COL_STATUS, COL_SESSION, COL_AGE, COL_PACKING, COL_ITEMS, COL_TOUCHED = range(6)`; `_fmt_age(ts_str) -> str`; `_fmt_touched(entry) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sessions_list_columns.py
"""B1's six columns.

Worker, PC and Started fold into one 'Last touched' column; Age is new;
Packing List and Duration are dropped, as the artboard specifies.
"""
from gui.session_browser.sessions_list_widget import (
    COLUMN_HEADERS,
    _fmt_age,
    _fmt_touched,
)


def test_the_list_has_the_six_columns_the_artboard_draws():
    assert COLUMN_HEADERS == [
        "Status", "Session", "Age", "Packing", "Items", "Last touched",
    ]


def test_age_is_coarse_because_nobody_reads_minutes_off_a_wall_display():
    assert _fmt_age("2026-09-02T08:10:00") is not None


def test_last_touched_folds_worker_pc_and_time_into_one_cell():
    entry = {"worker": "W-004", "pc": "WH-PC-02", "last_activity": "2026-09-02T11:20:00"}
    touched = _fmt_touched(entry)
    assert "W-004" in touched and "WH-PC-02" in touched


def test_a_session_nobody_has_touched_shows_a_dash():
    assert _fmt_touched({}) == "—"
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_sessions_list_columns.py -q`
Expected: FAIL — `ImportError: cannot import name '_fmt_age'`.

- [ ] **Step 3: Rewrite the column set**

Replace the column constants and `COLUMN_HEADERS`, write `_fmt_age` and `_fmt_touched` beside the existing `_fmt_duration` / `_fmt_date` / `_fmt_progress` helpers, and rewrite `_fill_row` to fill six cells. Read the registry entry's real key names first — `grep -n "entry.get" gui/session_browser/sessions_list_widget.py` — and use those, not the names guessed in the test above; fix the test to match the real keys if they differ.

`_fmt_touched` renders `W-004 · WH-PC-02 · 11:20`, with `·` between parts and `—` when there is nothing. `_fmt_age` renders the coarse form B1 draws: `10m`, `3h`, `1d`, `13d`.

Keep the hidden sort-key item at `COL_STATUS` carrying the entry in `Qt.UserRole` — `_apply_filters`, `_get_row_entry` and the selection handler all read it, and losing it breaks all three silently.

- [ ] **Step 4: Run it and watch it pass, then run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Expected: PASS. Tests indexing the old nine columns need repointing at the new six.

- [ ] **Step 5: Commit**

```bash
git add gui/session_browser/sessions_list_widget.py tests/test_sessions_list_columns.py
git commit -m "feat(browser): B1's six columns, with Worker/PC/Started folded into Last touched"
```

---

### Task 13: The list's card, filter row and empty state

**Files:**
- Modify: `gui/session_browser/sessions_list_widget.py:188-282`
- Test: `tests/test_sessions_list_empty.py` (create)

**Interfaces:**
- Consumes: `Card`, `StatePanel` from `shared.components`.
- Produces: `SessionsListWidget.state_panel`, `.card`, and a `sessions_shown` signal carrying `(shown: int, total: int)` for the status bar.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sessions_list_empty.py
"""An empty screen says which kind of empty it is.

No sessions at all and no sessions matching the filters are different
problems, and the second one has an obvious next action.
"""
import pytest

from gui.session_browser.sessions_list_widget import SessionsListWidget


@pytest.fixture
def widget(qtbot):
    w = SessionsListWidget(registry_manager=None, session_history_manager=None)
    qtbot.addWidget(w)
    return w


def test_a_client_with_no_sessions_shows_the_empty_panel(widget):
    widget.show_entries([])
    assert widget.state_panel.isVisible()
    assert not widget.card.isVisible()


def test_filters_that_match_nothing_say_so_rather_than_showing_a_blank_table(widget):
    widget.show_entries([{"session_id": "2026-09-02_0810", "status": "completed"}])
    widget._search_input.setText("no such session")
    assert widget.state_panel.isVisible()


def test_clearing_the_filter_brings_the_table_back(widget):
    widget.show_entries([{"session_id": "2026-09-02_0810", "status": "completed"}])
    widget._search_input.setText("no such session")
    widget._search_input.setText("")
    assert widget.card.isVisible()
    assert not widget.state_panel.isVisible()


def test_the_widget_reports_how_many_rows_it_is_showing(widget, qtbot):
    with qtbot.waitSignal(widget.sessions_shown) as caught:
        widget.show_entries([
            {"session_id": "a", "status": "completed"},
            {"session_id": "b", "status": "completed"},
        ])
    assert caught.args == [2, 2]
```

Use the real loading entry point rather than `show_entries` if the widget has a different one — read `load_client` and `_apply_filters` and name the test's calls after what exists.

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_sessions_list_empty.py -q`
Expected: FAIL — no `state_panel`.

- [ ] **Step 3: Re-lay the widget per B1**

- Put `self._table` inside a `Card(margins=(0, 0, 0, 0))`, held as `self.card`.
- Lay the filter widgets out per B1: a `Status:` label then `_status_combo`, `From:` then `_date_from`, `To:` then `_date_to`, then `_search_input` with placeholder `Search sessions`, then a stretch, then the `Refresh` button. Filter *behaviour* does not change — only the layout and the labels.
- Add `self.state_panel`, shown in the card's place when there is nothing to show. Two messages, because they are two different situations:

```python
_EMPTY_NO_SESSIONS = ("No sessions yet",
                      "Sessions appear here once someone starts packing for this client.")
_EMPTY_NO_MATCHES = ("No sessions match",
                     "Widen the dates or clear the search to see more.")
```

- Emit `sessions_shown(shown, total)` at the end of `_apply_filters`; `MainWindow` puts it in the status bar as `7 of 7 sessions` (Task 14).

- [ ] **Step 4: Run it and watch it pass, then the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 5: Compare against B1 and B3 in both themes, then commit**

```bash
git add gui/session_browser/sessions_list_widget.py tests/test_sessions_list_empty.py
git commit -m "feat(browser): the list in a card, B1's filter row, and a real empty state"
```

---

### Task 14: The detail page replaces the modal dialog

**Files:**
- Create: `gui/session_browser/session_detail_page.py`
- Modify: `gui/session_browser/session_browser_widget.py`
- Modify: `gui/session_browser/overview_tab.py`, `orders_tab.py`, `metrics_tab.py` — card-grid layout
- Modify: `gui/main_window.py` — the `sessions_shown` status-bar wiring from Task 13
- Delete: `gui/session_browser/session_details_dialog.py`
- Test: `tests/test_session_detail_page.py` (create)

**Interfaces:**
- Consumes: `StatusChip`, `Card`, Task 13's `sessions_shown`.
- Produces: `SessionDetailPage(session_data: dict)` with a `back_requested` signal; `SessionBrowserWidget.show_detail(session_data)` and `.show_list()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_session_detail_page.py
"""Session detail is a page, not a modal.

B2 draws the same rail, command bar and status bar as the list, with the page
area swapped -- so it is a page in a stack, and the modal QDialog goes.
"""
import pytest

from gui.session_browser.session_detail_page import SessionDetailPage


@pytest.fixture
def session():
    return {
        "session_id": "2026-09-02_0810",
        "status": "in_progress",
        "client_id": "kaufland-de",
        "worker": "W-004",
        "pc": "WH-PC-02",
    }


def test_the_header_names_the_session_and_shows_its_status(qtbot, session):
    page = SessionDetailPage(session)
    qtbot.addWidget(page)
    assert "2026-09-02_0810" in page.title_label.text()
    assert page.status_chip.text() == "Active"


def test_the_page_carries_the_three_tabs_the_dialog_had(qtbot, session):
    page = SessionDetailPage(session)
    qtbot.addWidget(page)
    assert [page.tabs.tabText(i) for i in range(page.tabs.count())] == [
        "Overview", "Orders", "Metrics",
    ]


def test_back_asks_the_browser_to_return_to_the_list(qtbot, session):
    page = SessionDetailPage(session)
    qtbot.addWidget(page)
    with qtbot.waitSignal(page.back_requested):
        page.back_button.click()


def test_selecting_a_session_shows_the_detail_page_and_back_returns(qtbot, session):
    from gui.session_browser.session_browser_widget import SessionBrowserWidget

    browser = SessionBrowserWidget(
        profile_manager=None, session_lock_manager=None,
        session_history_manager=None, worker_manager=None, registry_manager=None,
    )
    qtbot.addWidget(browser)

    browser.show_detail(session)
    assert browser.stack.currentWidget() is browser.detail_page

    browser.detail_page.back_requested.emit()
    assert browser.stack.currentWidget() is browser.list_page
```

Match the `SessionBrowserWidget` constructor to what it actually takes after Task 10.

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_session_detail_page.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Build the page**

Per B2, top to bottom: a `← Sessions` ghost button, the session id, the `StatusChip` for its status (same `STATUS_CONFIG` as Task 11 — import it, do not restate the mapping), a stretch, and `Export Excel` on the right. Below that a tab strip carrying the three existing tab widgets unchanged. Below that their content, laid into `Card`s of definition-list rows per `.card-grid` / `.dl-row`.

`OverviewTab`, `OrdersTab` and `MetricsTab` keep their files and their data. What changes is that `OverviewTab`'s `addRow` fields become `Card` + label/value rows. Give `Card` a `add_row(label, value, *, mono=False)` helper if one row of that shape is needed more than twice — two hand-rolled copies is the threshold, not one.

- [ ] **Step 4: Stack the browser's two pages**

`SessionBrowserWidget` gains `self.stack = QStackedWidget()` holding `self.list_page` and `self.detail_page`. The list's existing double-click and selection handlers call `show_detail(entry)` instead of opening the dialog; `back_requested` calls `show_list()`. Then `git rm gui/session_browser/session_details_dialog.py`.

- [ ] **Step 5: Put the row count in the status bar**

In `gui/main_window.py`, connect Task 13's signal:

```python
        self.session_browser.sessions_shown.connect(
            lambda shown, total: self.statusBar().showMessage(f"{shown} of {total} sessions")
        )
```

Check how the status bar is set elsewhere in this file and follow that, rather than calling `statusBar()` directly if the window keeps its own handle.

- [ ] **Step 6: Run it and watch it pass, then the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Expected: PASS. Tests opening `SessionDetailsDialog` move to the page.

- [ ] **Step 7: Compare against B2 in both themes, then commit**

```bash
git add -A gui/session_browser/ gui/main_window.py tests/test_session_detail_page.py
git commit -m "feat(browser): session detail becomes a page, and the modal dialog goes"
```

---

# Part 4 — Packing table view and the rail (Tasks 15–18)

### Task 15: Delete the dead models

**Files:**
- Delete: `gui/order_table_model.py`, `gui/custom_filter_proxy_model.py`
- Modify: `gui/main_window.py:158-159`

**Interfaces:**
- Produces: nothing. This is a deletion.

- [ ] **Step 1: Prove they are dead**

Run: `grep -rn "OrderTableModel\|CustomFilterProxyModel\|table_model\|proxy_model" --include=*.py .`
Expected: only the two files themselves and the two docstring lines at `gui/main_window.py:158-159`. **If anything else appears, stop and do not delete.**

- [ ] **Step 2: Delete them and fix the docstring**

```bash
git rm gui/order_table_model.py gui/custom_filter_proxy_model.py
```

Remove the two `table_model` / `proxy_model` lines from `MainWindow`'s class docstring.

- [ ] **Step 3: Run the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: delete OrderTableModel and CustomFilterProxyModel, which nothing built"
```

---

### Task 16: The order tree per T1

**Files:**
- Modify: `gui/main_window.py:458-491` (`_setup_order_tree`), `_populate_order_tree`
- Test: `tests/test_order_tree.py` (create)

**Interfaces:**
- Consumes: `StatusChip`, `Card`.
- Produces: `MainWindow._order_status_chip(status: str) -> StatusChip`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_order_tree.py
"""T1's order rows: a chip in the Status column, and the 40px floor rung."""
from gui.main_window import ORDER_STATUS_CHIP


def test_the_three_order_states_each_have_a_chip():
    assert set(ORDER_STATUS_CHIP) == {"in_progress", "packed", "not_started"}


def test_an_order_being_packed_is_live_and_packer_driven():
    role, text, live, manual = ORDER_STATUS_CHIP["in_progress"]
    assert (text, live, manual) == ("In progress", True, True)


def test_a_finished_order_is_neither_live_nor_packer_declared():
    role, text, live, manual = ORDER_STATUS_CHIP["packed"]
    assert (text, live, manual) == ("Packed", False, False)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_order_tree.py -q`
Expected: FAIL — `ImportError: cannot import name 'ORDER_STATUS_CHIP'`.

- [ ] **Step 3: Rebuild the tree's chrome**

Add the table at module level beside `RAIL_ITEMS`:

```python
# T1's three order states. An order in progress is the one a packer is
# working right now, so it carries the solid mark; the other two are the
# system's reading of the packing list.
ORDER_STATUS_CHIP = {
    "in_progress": ("status_warning", "In progress", True, True),
    "packed": ("status_success", "Packed", False, False),
    "not_started": ("text_secondary", "Not started", False, False),
}
```

In `_setup_order_tree`:
- Delete the hardcoded `setStyleSheet` block at `:486-491`. The 30px row height and 5px padding are replaced by the 40px floor rung from the tokens — set it the way the other screens do, not with a literal.
- Delete the hardcoded `QFont(); font.setPointSize(11)` — body type comes from the theme.
- Put the tree inside a `Card`.

In `_populate_order_tree`, set the Status column with `setItemWidget(item, 3, self._order_status_chip(status))` instead of text. Child SKU rows leave Status and Courier empty, as T1 draws.

- [ ] **Step 4: Run it and watch it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_order_tree.py -q`
Expected: PASS, 3 tests.

- [ ] **Step 5: Prove no colour is hardcoded**

Run the repo's `style_lint` the way CI does — find it with `grep -rn "style_lint" .github/ scripts/`.
Expected: clean.

- [ ] **Step 6: Compare against T1 in both themes, run the suite, commit**

```bash
git add gui/main_window.py tests/test_order_tree.py
git commit -m "feat(packing): the order tree gets T1's card, chips and floor rung"
```

---

### Task 17: Filter the order tree

**Files:**
- Modify: `gui/command_bar.py`, `gui/main_window.py`
- Test: `tests/test_order_tree_filter.py` (create)

**Interfaces:**
- Consumes: Task 16's tree.
- Produces: `CommandBar.order_filter` (a `QLineEdit`); `MainWindow._filter_order_tree(text: str) -> None`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_order_tree_filter.py
"""T1's 'Filter orders' field.

An order matches on its own number or on any of its SKUs or product names, so
typing a SKU finds the order that contains it -- which is how a packer looks
for one.
"""


def test_typing_an_order_number_hides_the_other_orders(main_window_with_list):
    window = main_window_with_list
    window.command_bar.order_filter.setText("10429")

    visible = [
        window.order_tree.topLevelItem(i).text(0)
        for i in range(window.order_tree.topLevelItemCount())
        if not window.order_tree.topLevelItem(i).isHidden()
    ]
    assert visible == ["#10429"]


def test_typing_a_sku_finds_the_order_that_contains_it(main_window_with_list):
    window = main_window_with_list
    window.command_bar.order_filter.setText("TS-4409-B")

    visible = [
        window.order_tree.topLevelItem(i)
        for i in range(window.order_tree.topLevelItemCount())
        if not window.order_tree.topLevelItem(i).isHidden()
    ]
    assert len(visible) == 1


def test_clearing_the_filter_brings_every_order_back(main_window_with_list):
    window = main_window_with_list
    window.command_bar.order_filter.setText("10429")
    window.command_bar.order_filter.setText("")

    hidden = [
        i for i in range(window.order_tree.topLevelItemCount())
        if window.order_tree.topLevelItem(i).isHidden()
    ]
    assert hidden == []
```

Build the `main_window_with_list` fixture from the packing-list fixtures `tests/` already has — `grep -rn "processed_df" tests/ | head` will show how other tests seed one.

- [ ] **Step 2: Run it and watch it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_order_tree_filter.py -q`
Expected: FAIL — `CommandBar` has no `order_filter`.

- [ ] **Step 3: Add the field**

In `gui/command_bar.py`, add the field to the Packing page beside `client_combo`, following how the bar's other per-page widgets are built and shown/hidden by `set_page`:

```python
        self.order_filter = QLineEdit(self)
        self.order_filter.setPlaceholderText("Filter orders")
        self.order_filter.setFixedWidth(220)
```

In `gui/main_window.py`, connect it and write the filter. Hide the order row, not the children — a matching child keeps its parent visible:

```python
    def _filter_order_tree(self, text: str) -> None:
        """Hide orders that match neither the typed text nor any of their items.

        Matching a child keeps its parent visible: a packer searching for a SKU
        is looking for the order that contains it, not the line itself.
        """
        needle = text.strip().lower()
        for i in range(self.order_tree.topLevelItemCount()):
            order = self.order_tree.topLevelItem(i)
            if not needle:
                order.setHidden(False)
                continue
            haystack = [order.text(0).lower(), order.text(1).lower()]
            haystack += [
                order.child(c).text(col).lower()
                for c in range(order.childCount())
                for col in (0, 1)
            ]
            order.setHidden(not any(needle in part for part in haystack))
```

- [ ] **Step 4: Run it and watch it pass, then the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add gui/command_bar.py gui/main_window.py tests/test_order_tree_filter.py
git commit -m "feat(packing): filter orders from the command bar"
```

---

### Task 18: The Packing tab's empty state, and `Stats` on the rail

**Files:**
- Modify: `gui/main_window.py:86-94` (`RAIL_ITEMS`), the packing tab's layout
- Test: `tests/test_packing_empty.py` (create), `tests/test_rail_labels.py` (create)

**Interfaces:**
- Consumes: `StatePanel`.
- Produces: `MainWindow.packing_state_panel`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rail_labels.py
"""The rail's labels fit its 56px item.

'Statistics' measures ~72px at 10pt against 56px available and has no wrap
point, so the rail says 'Stats'. The tab, the page title and the tooltip keep
the full word.
"""
from gui.main_window import RAIL_ITEMS


def test_no_rail_label_is_longer_than_the_item_can_hold():
    for _icon, label, _tip in RAIL_ITEMS:
        assert len(label) <= 8, f"{label!r} will not fit the 56px rail item"


def test_the_statistics_item_reads_stats():
    assert [label for _i, label, _t in RAIL_ITEMS] == ["Packing", "Stats", "Browse"]


def test_the_tooltip_still_gives_the_full_name():
    tips = {label: tip for _i, label, tip in RAIL_ITEMS}
    assert tips["Stats"].startswith("Statistics")
```

```python
# tests/test_packing_empty.py
"""T2: no packing list means a state panel, not an empty grid."""


def test_with_no_list_loaded_the_packing_tab_shows_its_state_panel(main_window):
    assert main_window.packing_state_panel.isVisible()
    assert not main_window.order_tree.isVisible()


def test_loading_a_list_puts_the_tree_back(main_window_with_list):
    assert main_window_with_list.order_tree.isVisible()
    assert not main_window_with_list.packing_state_panel.isVisible()
```

- [ ] **Step 2: Run them and watch them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest tests/test_rail_labels.py tests/test_packing_empty.py -q`
Expected: FAIL — the rail says `Statistics`, and there is no `packing_state_panel`.

- [ ] **Step 3: Shorten the rail label**

```python
    ("table", "Stats", "Statistics — session totals"),
```

- [ ] **Step 4: Add the packing empty state**

Per T2, in place of the tree:

```python
        self.packing_state_panel = StatePanel(
            "No packing list loaded",
            "Choose a client and open a packing list to start a session.",
            action_text="Open a packing list",
        )
```

Swap it for the tree in `_populate_order_tree` — the same early-exit branch that currently clears the tree and blanks `sb_summary_label`.

- [ ] **Step 5: Run them and watch them pass, then the whole suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add gui/main_window.py tests/test_rail_labels.py tests/test_packing_empty.py
git commit -m "feat(packing): T2's empty state, and 'Stats' fits the rail"
```

---

# Part 5 — Finishing (Tasks 19–20)

### Task 19: Prove the seams bite

**Files:** none — this is a verification task.

- [ ] **Step 1: Re-insert each defect and watch its test fail**

One at a time, put the bug back, run that test, confirm **FAIL**, then restore:

| Defect | Restore | Test that must fail |
|---|---|---|
| 1.1 | `"#" + b.order` in `packer.js` | `tests/test_order_label.py` |
| 1.3 | `pop()` in `confirm_keep_extra` | `test_keeping_one_unit_of_a_doubled_extra_leaves_the_other` |
| 1.5 | remove the `install_crash_logging()` call | `tests/test_excepthook.py` |
| Stats | return `0` from `session_totals`' `progress_pct` | `test_progress_is_the_share_of_orders_completed` |
| Chips | set every `manual` to `False` | `test_only_the_two_states_a_packer_declares_carry_the_solid_mark` |

A regression test nobody has seen fail is a guess. Bundle 5's review found a green suite defending a bug.

- [ ] **Step 2: Prove every payload function has a caller**

For each of `order_label`, `sku_rollup`, `set_sku_rollup`, `install_crash_logging`, `session_totals`, `courier_totals`, `sku_summary`: grep for a call outside `tests/`. **Every one must have a non-test caller.** This is the exact failure Bundle 5 shipped twice.

Run: `grep -rn "sku_rollup\|install_crash_logging\|session_totals\|courier_totals\|sku_summary\|order_label" --include=*.py . | grep -v "^./tests/"`

- [ ] **Step 3: Run the full gate**

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q
.venv/bin/ruff check .
```

Plus `style_lint`, however CI invokes it. All three clean.

- [ ] **Step 4: Render all three screens in both themes**

Offscreen, at 1366×768: Session Browser list, Session Browser detail, Session Browser empty, Packing table, Packing table empty, Statistics, Statistics empty. Compare each against its artboard frame. Note any difference that is not in the spec's **Departures** list — an unlisted difference is a defect, not a decision.

- [ ] **Step 5: Commit any fixes the comparison found**

---

### Task 20: Sync `shared/`, update the graph, open the PR

**Files:**
- Modify: `shopify-fulfillment-tool/shared/` via the sync script

- [ ] **Step 1: Sync the shared change into Shopify**

Task 5 changed `shared/logger.py`, and this repo is canonical. From the Shopify repo root:

```bash
python scripts/sync_shared.py /home/gloopy/Desktop/Projects/packing-tool/.claude/worktrees/phase10-bundle6
```

The sibling default resolves wrong from a worktree, so pass the path explicitly.

- [ ] **Step 2: Prove Shopify is still green**

Run its suite the way its CLAUDE.md says: `QT_QPA_PLATFORM=offscreen python -m pytest` from the Shopify root. A `shared/` change that breaks the other tool is not done.

- [ ] **Step 3: Refresh the graph**

```bash
graphify update .
```

- [ ] **Step 4: Update the version in all three places**

`gui_main.py`, `packing_tool/__init__.py`, `README.md` — check this repo's own convention for which files carry it (`grep -rn "__version__" --include=*.py . | head`).

- [ ] **Step 5: Push and open the draft PR**

The PR body must name, explicitly:
- the three **Departures** from the artboards and why each was made;
- that the owner chose one bundle over a 5.1 / 6a / 6b split, and when;
- that `shared/logger.py` changed and has been synced;
- the Windows checks the owner still has to make: all three screens in both themes, a real scanner still scanning in Packer Mode, the roll-up block visible with a long history above it, and a deliberate crash leaving a traceback in the log file.

---

## Self-Review

**Spec coverage.** Part 1's five defects → Tasks 1–5. Part 2's chip → Task 11 (no new code, as corrected). Part 3's Session Browser → Tasks 10–14. Part 4's Packing table → Tasks 15–18. Part 5's Statistics → Tasks 6–9. Part 6's rail label → Task 18. The `shared/` sync and the graph → Task 20.

**Known soft spots, called out rather than hidden.** Three tasks tell the implementer to read the real code before writing the test — Task 12's registry key names, Task 13's loading entry point, Task 17's fixture. That is deliberate: guessing those names in the plan would produce tests that compile against a codebase that does not exist. Every such place names the grep that resolves it.

**Task 2 can invalidate its own fix.** If the extras reproduction passes at Step 2, the hypothesis is wrong and the task becomes a bisect. That branch is written into the task rather than left for the implementer to improvise.
