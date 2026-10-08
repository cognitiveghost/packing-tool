# UI refresh phase 2 (Packer Mode to the mockup, floor web kit) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Packer Mode's page onto the shared page base and kit, restyle it to mockup frames 6a to 6j, and leave `gui/web/floor.css` behind for phases 3 to 5.

**Architecture:** `PackerBridge` extends `shared.web_page.PageBridge` and keeps its named properties, plus three new ones (`unsaved`, `question`, `takeover`). `PackerModeWidget` owns one rule for whether the scanner is on. The page (`packer.html`, `packer.js`, `packer.css`) is rewritten over `shared/web/kit.css` and the new `gui/web/floor.css`. `MainWindow` leaves Packer Mode only after the cleared page has painted.

**Tech Stack:** Python 3.14, PySide6 (Qt widgets, QtWebEngine, QWebChannel), plain HTML/CSS/JS with no build step, pytest with pytest-qt. No new dependency.

**Spec:** `docs/superpowers/specs/2026-10-08-ui-refresh-phase2-packer-mode-design.md`. Read it first. ADRs: `docs/adr/0001-packer-mode-on-the-web-tier.md`, `docs/adr/0002-every-screen-on-the-web-tier.md`. Mockup: `docs/design/ui-refresh/mockups/Packer Mode.html` (unpack it as `docs/design/ui-refresh/mockups/README.md` describes, into a folder outside the repo).

## Global Constraints

- **Never edit a file under `shared/`.** A hook blocks it and CI diffs the folder. `shared/web_page.py`, `shared/web/kit.css` and `shared/web/page.js` are already there; read them, do not change them.
- **Scanner invariant (ADR 0001).** The page holds no `input`, `textarea`, `select` or `contenteditable`. The web view and its focus proxy are `NoFocus`. Every Qt button in the bar is `NoFocus`. `tests/test_packer_scanner_focus.py` must pass unchanged.
- **Web assets** (`gui/web/*`): colours only as `var(--token)` from `theme_css_vars()` (token `status_success_dot` is `--status-success-dot`). No hex, no colour names, no `px` font sizes (`pt` only), no `transition`, `transform`, `opacity`, gradients. `box-shadow` only as `var(--card-shadow)`, `var(--overlay-shadow)` or `none`. `@keyframes` may animate `border-color`. `tests/test_style_literals_guard.py` enforces this.
- **Qt code:** no colour literals; read tokens from `gui.theme.current_tokens()`. A widget's stylesheet is re-run on every theme change.
- **Text into the page goes through `textContent`,** never `innerHTML`: product names and barcodes come from files.
- **Copy, verbatim:** "Scan an order barcode", "No order open", "Scanned", "Confirm", "Force confirm", "Undo", "Map SKU", "Map barcode…", "Keep", "Remove", "Extra items scanned", "Extra", "No match", "Not a SKU or barcode this client knows", "Pending", "Partial", "Complete", "Packed", "Skipped", "Session progress", "History", "Items by SKU", "Summary", "Unique SKUs packed", "Session complete", "End session", "Exit packing", "Skip order", "Ready to scan", "Scanner disabled", "Order number or SKU", "Progress not saved — check the network", "Scanning continues", "This list is open on another PC", "Cancel". The ellipsis is the single character `…`, the dash is `—`.
- **Sizes:** side column 248px; list rows 64px; list head 36px; row buttons 40px; other controls 44px; badges 28px; numerals 26pt; band sentence 30pt; raw scan 20pt; order number in the bar 24pt; scanner field 280px by 44px; flash frame 10px.
- **Git:** `/usr/bin/git`, one plain git command per Bash call (no `&&`, `;`, `$VAR` paths). Commit with `/usr/bin/git commit -F <absolute path to a message file>`; write the message file with the Write tool. Never commit to `main`. Each commit message ends with the attribution lines your session gives you.
- **Tests:** run with `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q <path>`. If a hook refuses that, run the whole suite: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`. Write test files with Write/Edit, never with shell redirection. If `.venv` is missing in the worktree: `ln -s /home/gloopy/Desktop/Projects/packing-tool/.venv .venv`.
- **Lint:** `.venv/bin/ruff check . --exclude shared` must pass before each commit.
- After the last code change, run `graphify update .` (CLAUDE.md).
- Departures from the mockup are the 19 in spec section 9. If you make another, add it to that table in the same commit.

## Review Focus

Failure modes the spec implies that are most likely to bite a packer. Each has a test in the task named.

1. **The lock is taken while the Force confirm question is open.** The takeover panel replaces the question; the question does not come back (Task 3, `test_a_takeover_closes_an_open_question`).
2. **Exit packing is pressed while the question is open.** On the next entry there is no question and the scanner is on (Task 3, `test_leaving_with_a_question_open_drops_it`).
3. **A very long sentence or barcode in the band.** It wraps or is cut inside the band; the band never grows wider than the column (Task 4, `test_a_long_sentence_stays_inside_the_band`).
4. **The page's render process dies mid-shift.** The page is loaded again and the view still refuses the keyboard (Task 2, `test_a_reloaded_page_still_refuses_the_keyboard`).
5. **The heartbeat reports the lost lock again while the panel is up.** One panel, no second teardown: the heartbeat is stopped (Task 5, `test_a_lost_lock_in_packer_mode_shows_the_panel_and_waits_for_exit`).

## File map

| File | Responsibility | Task |
|---|---|---|
| `gui/packer_mode_widget.py` | the bar, the scanner's on/off rule, what the widget pushes to the bridge | 1, 3 |
| `gui/main_window.py` | calls into the widget; lock loss; leaving Packer Mode | 1, 5 |
| `gui/packer_bridge.py` | payload functions, `PackerBridge`, `mount_packer_page` | 2 |
| `main.spec`, `.github/workflows/*.yml` | bundle `shared/web` and check it shipped | 2 |
| `gui/web/floor.css` | floor density over the kit, no page in it | 4 |
| `gui/web/packer.html`, `packer.js`, `packer.css` | the page | 4 |
| `scripts/render_packer_mode.py` | offscreen renders of 6a to 6j | 6 |
| `CONTEXT.md` | glossary | 6 |
| `tests/test_packer_payload.py`, `test_packer_bridge.py`, `test_packer_mode_widget.py`, `test_packer_mainwindow_seam.py`, `test_session_lock_loss.py` | tests | 1 to 5 |

---

### Task 1: A finished order's reset no longer closes the order opened after it

**Files:**
- Modify: `gui/packer_mode_widget.py`, `gui/main_window.py` (`_handle_order_completion`, near line 2006)
- Test: `tests/test_packer_mainwindow_seam.py`

**Interfaces:**
- Produces: `PackerModeWidget.clear_screen_later(ms: int) -> None`; module constant `gui.main_window.ORDER_CLEAR_MS = 3000`.

- [ ] **Step 1: Write the failing test.** Append to `tests/test_packer_mainwindow_seam.py`:

```python
def test_a_finished_orders_reset_does_not_close_the_order_opened_after_it(window, qtbot):
    """_handle_order_completion schedules a reset 3 s out. An order opened in
    the meantime (the simulator, a replayed scan, leaving and coming back) was
    wiped from the screen while PackerLogic still held it open."""
    window.logic = StubLogic("ORDER_COMPLETE")
    widget = window.packer_mode_widget

    window._handle_order_completion("1001")
    widget.display_order(
        [{"SKU": "A", "Product_Name": "A", "Quantity": 1, "Order_Number": "1002"}], []
    )
    qtbot.wait(3200)

    assert [r["sku"] for r in widget.bridge.items] == ["A"]
    assert widget._order_label.text() == "#1002"
    assert widget.scanner_input.isEnabled()
```

- [ ] **Step 2: Run it and see it fail.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_packer_mainwindow_seam.py`
Expected: FAIL on `assert [] == ['A']` (the timer cleared the new order).

- [ ] **Step 3: Give the widget the timer.** In `gui/packer_mode_widget.py`:

Change the import `from PySide6.QtCore import Qt, Signal` to `from PySide6.QtCore import Qt, QTimer, Signal`.

In `__init__`, after `self._unsaved = False`:

```python
        # The reset that follows a finished order. Here, not in MainWindow:
        # showing an order and clearing the screen are what it races with.
        self._clear_timer = QTimer(self)
        self._clear_timer.setSingleShot(True)
        self._clear_timer.timeout.connect(self.clear_screen)
```

Add this method above `clear_screen`:

```python
    def clear_screen_later(self, ms: int):
        """Hold the finished order on screen, scanner off, then reset.

        Showing another order or clearing the screen before then cancels it.
        """
        self.scanner_input.setEnabled(False)
        self._clear_timer.start(ms)
```

In `display_order`, make these the first two lines of the body:

```python
        self._clear_timer.stop()
        self.scanner_input.setEnabled(True)
```

In `clear_screen`, make this the first line of the body, before `if self._session_over:`:

```python
        self._clear_timer.stop()
```

- [ ] **Step 4: Use it from MainWindow.** In `gui/main_window.py`, add a module constant near the other module-level constants (search for `PAGE_PACKING` to find them):

```python
# How long a finished order stays on screen before Packer Mode resets.
ORDER_CLEAR_MS = 3000
```

In `_handle_order_completion`, replace

```python
        self.packer_mode_widget.scanner_input.setEnabled(False)
        QTimer.singleShot(3000, self.packer_mode_widget.clear_screen)
```

with

```python
        self.packer_mode_widget.clear_screen_later(ORDER_CLEAR_MS)
```

- [ ] **Step 5: Run the test, see it pass, then make it fast.** Run the command from Step 2. Expected: PASS (about 3 s). Then change the test's signature to `(window, qtbot, monkeypatch)`, add `monkeypatch.setattr("gui.main_window.ORDER_CLEAR_MS", 40)` as its first line, and change `qtbot.wait(3200)` to `qtbot.wait(200)`. Run again. Expected: PASS.

- [ ] **Step 6: Run the whole suite and lint.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` then `.venv/bin/ruff check . --exclude shared`
Expected: all pass.

- [ ] **Step 7: Commit** `gui/packer_mode_widget.py`, `gui/main_window.py`, `tests/test_packer_mainwindow_seam.py` with the message `fix: a finished order's reset no longer closes the order opened after it`.

---

### Task 2: The bridge on the shared page base

**Files:**
- Modify: `gui/packer_bridge.py`, `main.spec`, the workflow under `.github/workflows/` that has the step "Verify bundled assets shipped"
- Test: `tests/test_packer_payload.py`, `tests/test_packer_bridge.py`

**Interfaces:**
- Consumes: `shared.web_page.PageBridge` (properties `revision`, `themeCss`; attribute `painted_revision`; signal `painted(int)`), `shared.web_page.mount_page(view, bridge, page, channel_name, *, tokens)`.
- Produces:
  - `item_rows()` rows gain `"force_slot": bool` and lose `"multi"`; `unknown_rows()` rows the same.
  - `force_question(row: dict) -> dict` with keys `row`, `sku`, `product`, `remaining`, `required`.
  - `PackerBridge(PageBridge)` with new properties `unsaved` (bool), `question` (map), `takeover` (map); setters `set_unsaved(bool)`, `set_question(dict)`, `set_takeover(dict)`; slot `answerQuestion(bool)`; signal `questionAnswered(bool)`.
  - `mount_packer_page(view) -> PackerBridge`, unchanged signature.

- [ ] **Step 1: Write the failing payload tests.** In `tests/test_packer_payload.py`, delete `test_multi_flags_a_line_that_needs_more_than_one_scan` and `test_a_single_unit_line_is_never_multi`, add `force_question` to the import from `gui.packer_bridge`, and append:

```python
def test_force_has_a_slot_only_above_the_threshold():
    rows = item_rows(
        [{"SKU": "A", "Quantity": 5}, {"SKU": "B", "Quantity": 6}],
        [{"row": 1, "packed": 6, "required": 6}],
        {},
    )
    # A 5-unit line never offers Force. A finished 6-unit line keeps the slot
    # and loses the act.
    assert [(r["force_slot"], r["force"]) for r in rows] == [(False, False), (True, False)]


def test_no_row_carries_the_old_multi_flag():
    assert "multi" not in item_rows([{"SKU": "A", "Quantity": 3}], [], {})[0]
    assert "multi" not in unknown_rows(["4006381333931"])[0]


def test_the_force_question_counts_what_is_left():
    row = item_rows(
        [{"SKU": "SPF-50", "Product_Name": "Sunscreen SPF 50", "Quantity": 8}],
        [{"row": 0, "packed": 3, "required": 8}],
        {},
    )[0]
    assert force_question(row) == {
        "row": 0,
        "sku": "SPF-50",
        "product": "Sunscreen SPF 50",
        "remaining": 5,
        "required": 8,
    }
```

If `unknown_rows` is not yet imported in that file, add it to the import.

- [ ] **Step 2: Write the failing bridge tests.** In `tests/test_packer_bridge.py`:

Change the imports: remove `THEME_MARKER` from the `gui.packer_bridge` import and add `from shared.web_page import THEME_MARKER, PageBridge`. Add `from PySide6.QtWebEngineCore import QWebEnginePage`.

Delete `test_the_quantity_cell_warns_while_a_multi_unit_line_is_unfinished` and `test_a_finished_multi_unit_line_drops_the_warning`.

Append:

```python
def test_the_bridge_is_a_page_bridge_and_counts_its_changes(page):
    _view, bridge = page
    assert isinstance(bridge, PageBridge)
    before = bridge.revision
    bridge.set_items([])
    bridge.set_unsaved(True)
    assert bridge.revision == before + 2


def test_the_three_new_states_start_empty_and_round_trip(page):
    _view, bridge = page
    assert (bridge.unsaved, bridge.question, bridge.takeover) == (False, {}, {})
    bridge.set_unsaved(True)
    bridge.set_question({"row": 1, "sku": "A"})
    bridge.set_takeover({"holder": "PC-2", "list": "DHL"})
    assert bridge.unsaved is True
    assert bridge.question == {"row": 1, "sku": "A"}
    assert bridge.takeover == {"holder": "PC-2", "list": "DHL"}


def test_an_answer_reaches_python(page, qtbot):
    _view, bridge = page
    with qtbot.waitSignal(bridge.questionAnswered, timeout=1000) as caught:
        bridge.answerQuestion(True)
    assert caught.args == [True]


def test_a_reloaded_page_still_refuses_the_keyboard(page, qtbot):
    """mount_page loads the page again when its render process dies. The new
    document gets a new focus proxy, and it must refuse focus like the first."""
    view, _bridge = page
    with qtbot.waitSignal(view.page().loadFinished, timeout=20000):
        view.page().renderProcessTerminated.emit(
            QWebEnginePage.RenderProcessTerminationStatus.CrashedTerminationStatus, 1
        )
    qtbot.waitUntil(
        lambda: view.focusProxy() is not None
        and view.focusProxy().focusPolicy() == Qt.FocusPolicy.NoFocus,
        timeout=5000,
    )
    assert view.focusPolicy() == Qt.FocusPolicy.NoFocus
```

`Qt` is already imported in that file for `test_the_view_never_takes_keyboard_focus`; if it is imported inside that function, move the import to the top of the file.

- [ ] **Step 3: Run and see them fail.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_packer_payload.py tests/test_packer_bridge.py`
Expected: FAIL with `ImportError: cannot import name 'force_question'`.

- [ ] **Step 4: Change the payloads.** In `gui/packer_bridge.py`:

In `item_rows`, in the row dict, replace the line `"multi": required > 1 and packed < required,` with

```python
                # Whether Force confirm has a slot on this row at all. `force`
                # says whether it can be pressed now.
                "force_slot": required > FORCE_CONFIRM_MIN_QTY,
```

In `unknown_rows`, replace `"multi": False,` with `"force_slot": False,`.

Add after `unknown_rows`:

```python
def force_question(row: dict[str, Any]) -> dict[str, Any]:
    """What the Force confirm question says about one of item_rows()' rows."""
    return {
        "row": row["row"],
        "sku": row["sku"],
        "product": row["product"],
        "remaining": row["required"] - row["packed"],
        "required": row["required"],
    }
```

- [ ] **Step 5: Move the bridge onto `PageBridge`.** In `gui/packer_bridge.py`:

Replace the imports

```python
from PySide6.QtCore import Property, QObject, Qt, QUrl, Signal, Slot
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.theme import current_tokens
from packing_tool.packer_logic import normalize_sku
from shared.theme import on_theme_changed, theme_css_vars
```

with

```python
from PySide6.QtCore import Property, Qt, Signal, Slot
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.theme import current_tokens
from packing_tool.packer_logic import normalize_sku
from shared.web_page import PageBridge, mount_page
```

Delete the line `THEME_MARKER = "/* theme-vars */"`.

Change `class PackerBridge(QObject):` to `class PackerBridge(PageBridge):` and its docstring to:

```python
    """The order document's one channel object.

    The theme, the revision and the painted report come from PageBridge
    (shared/web_page.py). Every notify property declared here raises the
    revision on its own.
    """
```

In the class body: delete `themeCssChanged = Signal()`; delete `self._theme_css = ""` from `__init__`; delete `_get_theme_css` and the `themeCss = Property(...)` line; delete `set_theme_css`.

Add to the signal declarations, after `sessionEndChanged = Signal()`:

```python
    unsavedChanged = Signal()
    questionChanged = Signal()
    takeoverChanged = Signal()
```

and after `mapBarcodeRequested = Signal(str)`:

```python
    questionAnswered = Signal(bool)
```

Add to `__init__`, after `self._session_end: dict = {}`:

```python
        self._unsaved = False
        self._question: dict = {}
        self._takeover: dict = {}
```

Add after the `sessionEnd = Property(...)` line:

```python
    def _get_unsaved(self) -> bool:
        return self._unsaved

    # State writes are failing (frame 6i).
    unsaved = Property(bool, _get_unsaved, notify=unsavedChanged)

    def _get_question(self) -> dict:
        return self._question

    # The open Force confirm question, force_question()'s payload; {} for none.
    question = Property("QVariantMap", _get_question, notify=questionChanged)

    def _get_takeover(self) -> dict:
        return self._takeover

    # Another PC holds the list: {"holder", "list"}; {} when this PC does.
    takeover = Property("QVariantMap", _get_takeover, notify=takeoverChanged)
```

Add after the `exitPacking` slot:

```python
    @Slot(bool)
    def answerQuestion(self, confirmed) -> None:
        self.questionAnswered.emit(bool(confirmed))
```

Add after `set_session_end`:

```python
    def set_unsaved(self, unsaved: bool) -> None:
        self._unsaved = bool(unsaved)
        self.unsavedChanged.emit()

    def set_question(self, payload: dict) -> None:
        self._question = dict(payload or {})
        self.questionChanged.emit()

    def set_takeover(self, payload: dict) -> None:
        self._takeover = dict(payload or {})
        self.takeoverChanged.emit()
```

Replace the whole of `mount_packer_page` with:

```python
def mount_packer_page(view: QWebEngineView) -> PackerBridge:
    """Load the order document into `view` and return the bridge it talks to.

    shared.web_page.mount_page writes the theme into the page before it loads,
    keeps it current, and loads the page again if its render process dies. The
    bridge is parented to `view` and dies with it.

    The view never takes keyboard focus (ADR 0001's scanner invariant); see
    deny_focus(). The focus proxy is created lazily with each loaded document,
    a reloaded one included, so it is denied again every time a load finishes.
    """
    bridge = PackerBridge(view)
    deny_focus(view)
    mount_page(view, bridge, PAGE, CHANNEL_NAME, tokens=current_tokens)
    view.page().loadFinished.connect(lambda _ok: deny_focus(view))
    return bridge
```

Update the module docstring's last line (`Spec: ...`) to add a second line: `UI refresh phase 2: docs/superpowers/specs/2026-10-08-ui-refresh-phase2-packer-mode-design.md`.

- [ ] **Step 6: Bundle `shared/web`.** In `main.spec`, add `('shared/web', 'shared/web'),` to `datas` after the `('gui/web', 'gui/web'),` line. In the workflow step "Verify bundled assets shipped", add `"kit.css", "page.js"` to the list of names in the `foreach`, after `"packer.html"`, and add one sentence to the comment above it: `kit.css and page.js are shared/web, which packer.html loads by relative path.`

- [ ] **Step 7: Run the tests.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` then `.venv/bin/ruff check . --exclude shared`
Expected: all pass. The page still runs its old script here; it reads `themeCss` from the inherited property and ignores the new ones.

- [ ] **Step 8: Commit** with the message `refactor: PackerBridge extends the shared PageBridge, with unsaved, question and takeover`.

---

### Task 3: The widget: one rule for the scanner, the question, the banner, the takeover, the bar

**Files:**
- Modify: `gui/packer_mode_widget.py`
- Test: `tests/test_packer_mode_widget.py`, `tests/test_packer_bridge.py`

**Interfaces:**
- Consumes: Task 1's `_clear_timer`; Task 2's `force_question`, `set_unsaved`, `set_question`, `set_takeover`, `questionAnswered`.
- Produces on `PackerModeWidget`: `pause_scanner()`, `resume_scanner()`, `show_takeover(holder: str, list_name: str)`, read-only property `taken_over: bool`. `clear_screen_later(ms)`, `set_unsaved(bool)`, `display_order`, `clear_screen`, `show_session_complete`, `reset_for_new_session` keep their signatures. `force_confirm_requested(int)` is now emitted only after the packer answers *Force confirm*. The module constant `UNSAVED_TEXT` is removed.

- [ ] **Step 1: Write the failing tests.** In `tests/test_packer_mode_widget.py`:

Replace `test_the_scanner_is_visible_and_invites_a_scan` with:

```python
def test_the_scanner_is_visible_and_says_it_is_ready(widget):
    assert widget.scanner_input.placeholderText() == "Order number or SKU"
    assert widget.scanner_input.width() == 280
    assert widget.scanner_input.height() == 44
    assert widget.scanner_input.parent() is widget.packer_bar
    assert widget._scanner_state.text() == "Ready to scan"
```

Replace `test_unsaved_progress_keeps_the_band_red_and_the_outcome_readable` with:

```python
def test_unsaved_progress_is_its_own_state_and_leaves_the_band_alone(widget):
    widget.show_notification("Order #1001 packed. Scan the next order.", "status_success")
    widget.set_unsaved(True)
    assert widget.bridge.unsaved is True
    assert widget.bridge.feedback["role"] == "success"
    assert widget.bridge.feedback["text"] == "Order #1001 packed. Scan the next order."
    assert widget.scanner_input.isEnabled()  # scanning continues

    widget.set_unsaved(False)
    assert widget.bridge.unsaved is False
```

Replace `test_a_new_session_starts_saved` with:

```python
def test_a_new_session_starts_saved(widget):
    widget.set_unsaved(True)
    widget.reset_for_new_session()
    assert widget.bridge.unsaved is False
```

Append:

```python
ORDER = [
    {"SKU": "SPF-50", "Product_Name": "Sunscreen SPF 50", "Quantity": 8, "Order_Number": "10407"},
    {"SKU": "LIP-RED", "Product_Name": "Lip balm, red", "Quantity": 2, "Order_Number": "10407"},
]


def _off(widget):
    return (
        not widget.scanner_input.isEnabled()
        and widget._scanner_state.text() == "Scanner disabled"
        and not widget.skip_order_button.isEnabled()
    )


def test_an_open_order_turns_skip_on_and_no_order_turns_it_off(widget):
    assert not widget.skip_order_button.isEnabled()
    widget.display_order(ORDER, [])
    assert widget.skip_order_button.isEnabled()
    assert widget._scanner_state.text() == "Ready to scan"
    widget.clear_screen()
    assert not widget.skip_order_button.isEnabled()
    assert widget.scanner_input.isEnabled()


def test_a_force_click_asks_first_and_turns_the_scanner_off(qtbot, widget):
    widget.display_order(ORDER, [{"row": 0, "packed": 3, "required": 8}])
    forced = []
    widget.force_confirm_requested.connect(forced.append)

    widget.bridge.forceItem(0)

    assert forced == []
    assert widget.bridge.question == {
        "row": 0, "sku": "SPF-50", "product": "Sunscreen SPF 50", "remaining": 5, "required": 8,
    }
    assert _off(widget)


def test_force_confirm_sends_the_row_and_gives_the_scanner_back(widget):
    widget.display_order(ORDER, [])
    forced = []
    widget.force_confirm_requested.connect(forced.append)
    widget.bridge.forceItem(0)

    widget.bridge.answerQuestion(True)

    assert forced == [0]
    assert widget.bridge.question == {}
    assert widget.scanner_input.isEnabled()
    assert widget.skip_order_button.isEnabled()


def test_cancel_sends_nothing_and_gives_the_scanner_back(widget):
    widget.display_order(ORDER, [])
    forced = []
    widget.force_confirm_requested.connect(forced.append)
    widget.bridge.forceItem(0)

    widget.bridge.answerQuestion(False)

    assert forced == []
    assert widget.bridge.question == {}
    assert widget.scanner_input.isEnabled()


def test_a_force_click_on_a_row_that_is_not_there_asks_nothing(widget):
    widget.display_order(ORDER, [])
    widget.bridge.forceItem(7)
    assert widget.bridge.question == {}
    assert widget.scanner_input.isEnabled()


def test_an_answer_with_no_question_open_does_nothing(widget):
    widget.display_order(ORDER, [])
    forced = []
    widget.force_confirm_requested.connect(forced.append)
    widget.bridge.answerQuestion(True)
    assert forced == []


def test_leaving_with_a_question_open_drops_it(widget):
    widget.display_order(ORDER, [])
    widget.bridge.forceItem(0)
    widget.clear_screen()  # what Exit packing does
    assert widget.bridge.question == {}
    assert widget.scanner_input.isEnabled()


def test_a_takeover_turns_everything_off_until_a_new_session(widget):
    widget.display_order(ORDER, [])
    widget.show_takeover("PC-2", "DHL_Orders")
    assert widget.taken_over is True
    assert widget.bridge.takeover == {"holder": "PC-2", "list": "DHL_Orders"}
    assert _off(widget)

    widget.clear_screen()  # a per-order reset does not give the list back
    assert _off(widget)

    widget.reset_for_new_session()
    assert widget.taken_over is False
    assert widget.bridge.takeover == {}
    assert widget.scanner_input.isEnabled()


def test_a_takeover_closes_an_open_question(widget):
    widget.display_order(ORDER, [])
    widget.bridge.forceItem(0)
    widget.show_takeover("PC-2", "DHL_Orders")
    assert widget.bridge.question == {}
    widget.bridge.answerQuestion(True)  # a late click on the old question
    assert _off(widget)


def test_pause_and_resume(widget):
    widget.display_order(ORDER, [])
    widget.pause_scanner()
    assert _off(widget)
    widget.resume_scanner()
    assert widget.scanner_input.isEnabled()


def test_a_finished_session_stays_off_through_a_resume(widget):
    widget.show_session_complete({"title": "Session complete", "body": "done."})
    widget.resume_scanner()
    assert _off(widget)


def test_the_held_order_keeps_the_scanner_off_until_the_reset(qtbot, widget):
    widget.display_order(ORDER, [])
    widget.clear_screen_later(40)
    assert _off(widget)
    qtbot.wait(150)
    assert widget.scanner_input.isEnabled()
    assert widget.bridge.items == []


def test_the_simulator_refuses_a_scan_while_the_scanner_is_off(qtbot):
    w = PackerModeWidget(sim_mode=True)
    qtbot.addWidget(w)
    seen = []
    w.barcode_scanned.connect(seen.append)
    w.pause_scanner()
    w.sim_input.setText("10407")
    w._on_sim_scan()
    assert seen == []
    w.resume_scanner()
    w._on_sim_scan()
    assert seen == ["10407"]
```

In `tests/test_packer_bridge.py`, replace the whole of `test_a_force_click_confirms_first` (it monkeypatches `ConfirmDialog`, which is going away) with:

```python
def test_a_force_click_opens_the_question_and_forces_only_on_yes(qtbot):
    widget = PackerModeWidget()
    qtbot.addWidget(widget)
    widget.display_order(ITEMS, STATE)
    seen = []
    widget.force_confirm_requested.connect(seen.append)

    widget.bridge.forceItem(1)
    assert seen == []
    widget.bridge.answerQuestion(False)
    assert seen == []

    widget.bridge.forceItem(1)
    widget.bridge.answerQuestion(True)
    assert seen == [1]
```

Remove any import in that file that this leaves unused (`QDialog`, the `gui.packer_mode_widget` module alias). If `PackerModeWidget` is imported inside test functions there, keep that style.

- [ ] **Step 2: Run and see them fail.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_packer_mode_widget.py tests/test_packer_bridge.py`
Expected: FAIL (`AttributeError: ... '_scanner_state'`, among others).

- [ ] **Step 3: Rewrite the widget's imports and constants.** In `gui/packer_mode_widget.py`, replace the import block and constants from `from PySide6.QtCore import ...` down to `UNSAVED_TEXT = ...` with:

```python
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from gui.command_bar import BAR_HEIGHT, CONTROL_HEIGHT, bar_css
from gui.packer_bridge import (
    banner_payload,
    flash_role,
    force_question,
    item_rows,
    order_label,
    sku_rollup,
    summary_lines,
    unknown_rows,
)
from gui.theme import current_tokens
from shared.theme import font_css, on_theme_changed

logger = logging.getLogger(__name__)

SCANNER_WIDTH = 280
SIM_INPUT_WIDTH = 160
# Mockup frame 6b. The type scale has no rung between 17 and 28pt.
ORDER_NUMBER_PT = 24
```

- [ ] **Step 4: Rewrite `__init__`'s state and bar.** In `__init__`, replace the state block (from `self._feedback_text = ...` through `self._unsaved = False`) with:

```python
        self._feedback_text = "Scan an order barcode"
        self._feedback_role = "info"
        self._raw_scan = ""
        self._items = []
        self._rows = []
        self._unknown = []
        self._sku_map = {}
        self._orders_done = 0
        self._orders_total = 0
        self._history = []
        self._unsaved = False
        # Why the scanner is off, when it is: see _sync_scanner().
        self._order_open = False
        self._session_over = False
        self._taken_over = False
        self._paused = False
        self._question: dict = {}
```

After the line `self.bridge.exitPackingRequested.connect(self.exit_packing_mode.emit)` add:

```python
        self.bridge.questionAnswered.connect(self._on_question_answered)
```

Replace the bar's order label and scanner block (from `self._order_label = QLabel("No order")` through `bar.addWidget(self.scanner_input)`) with:

```python
        self._order_label = QLabel("No order")
        self._order_label.setObjectName("packerOrder")
        self._order_label.setMinimumWidth(120)
        bar.addWidget(self._order_label)

        # The scanner field: the one widget on this screen that takes keys.
        # Fixed height, because the 2px edge below would add to the global
        # sheet's min-height.
        self.scanner_input = QLineEdit()
        self.scanner_input.setObjectName("packerScanner")
        self.scanner_input.setFixedSize(SCANNER_WIDTH, CONTROL_HEIGHT)
        self.scanner_input.setPlaceholderText("Order number or SKU")
        self.scanner_input.returnPressed.connect(self._on_scan)
        bar.addWidget(self.scanner_input)

        self._scanner_dot = QLabel()
        self._scanner_dot.setObjectName("packerScannerDot")
        self._scanner_dot.setFixedSize(12, 12)
        bar.addWidget(self._scanner_dot)
        self._scanner_state = QLabel("Ready to scan")
        self._scanner_state.setObjectName("packerScannerState")
        bar.addWidget(self._scanner_state)
```

Replace the last line of `__init__`, `on_theme_changed(self, self._apply_bar_theme)`, with:

```python
        on_theme_changed(self, self._restyle)
        self._sync_scanner()
```

- [ ] **Step 5: Replace `_apply_bar_theme` with `_restyle` and add `_sync_scanner`.** Delete `_apply_bar_theme` and put in its place:

```python
    def _restyle(self, _tokens=None) -> None:
        """The bar's sheet, for the current theme and the scanner's state.

        gui.theme's tokens, not the argument on_theme_changed passes: only
        those carry the bundled font family.
        """
        tokens = current_tokens()
        off = not self.scanner_input.isEnabled()
        if self._order_open and not self._session_over:
            order = (
                f"font-size: {ORDER_NUMBER_PT}pt; font-weight: bold;"
                f" font-family: {tokens.font_family_mono}; color: {tokens.text};"
            )
        else:
            order = f"{font_css('display', bold=True)} color: {tokens.text_secondary};"
        dot = tokens.text_disabled if off else tokens.status_success_dot
        state = tokens.text_secondary if off else tokens.status_success
        self.setStyleSheet(
            bar_css(tokens, "QWidget#PackerBar")
            + f" QLabel#packerOrder {{ {order} background: transparent; }}"
            f" QLineEdit#packerScanner {{ {font_css('heading', bold=False)}"
            f" font-family: {tokens.font_family_mono}; }}"
            f" QLineEdit#packerScanner:enabled {{ border: 2px solid {tokens.selection_border}; }}"
            f" QLabel#packerScannerDot {{ background: {dot}; border-radius: 6px; }}"
            f" QLabel#packerScannerState {{ {font_css('body', bold=True)} color: {state};"
            " background: transparent; }"
            f" QWidget#SimGroup {{ border: 1px dashed {tokens.status_warning};"
            f" border-radius: {tokens.radius}px; }}"
            f" QLabel#SimGroupLabel {{ color: {tokens.status_warning};"
            f" {font_css('caption', bold=True)} }}"
        )

    def _sync_scanner(self) -> None:
        """The one place that decides whether the scanner is on.

        Off when the session is over, another PC took the list, a question is
        open, or the widget is paused (a finished order held on screen, or the
        window about to leave Packer Mode). Skip order follows it, and needs
        an order.
        """
        off = (
            self._session_over or self._taken_over or bool(self._question) or self._paused
        )
        self.scanner_input.setEnabled(not off)
        self._scanner_state.setText("Scanner disabled" if off else "Ready to scan")
        self.skip_order_button.setEnabled(self._order_open and not off)
        self._restyle()
        if not off:
            self.set_focus_to_scanner()

    @property
    def taken_over(self) -> bool:
        """Another PC holds this list's lock (see show_takeover)."""
        return self._taken_over

    def pause_scanner(self) -> None:
        self._paused = True
        self._sync_scanner()

    def resume_scanner(self) -> None:
        self._paused = False
        self._sync_scanner()
```

- [ ] **Step 6: Rewrite the methods that set scanner state.**

`_on_sim_scan`: change `if text:` to `if text and self.scanner_input.isEnabled():`.

Replace `_on_force_confirm` with:

```python
    def _on_force_confirm(self, row: int):
        """Open the Force confirm question for one item (frame 6f).

        The page draws it. The scanner is off until it is answered, so a scan
        cannot answer it by accident.
        """
        if not 0 <= row < len(self._rows):
            return
        self._question = force_question(self._rows[row])
        self.bridge.set_question(self._question)
        self._sync_scanner()

    def _on_question_answered(self, confirmed: bool):
        """Cancel or Force confirm. Forcing is not undoable."""
        question, self._question = self._question, {}
        self.bridge.set_question({})
        self._sync_scanner()
        if confirmed and question:
            self.force_confirm_requested.emit(question["row"])
```

`display_order`: replace the two lines Task 1 added at the top of the body with

```python
        self._clear_timer.stop()
        self._paused = False
        self._order_open = True
```

and replace its last two lines (`self.skip_order_button.setEnabled(True)` and `self.set_focus_to_scanner()`) with `self._sync_scanner()`.

Replace `clear_screen_later` with:

```python
    def clear_screen_later(self, ms: int):
        """Hold the finished order on screen, scanner off, then reset.

        Showing another order or clearing the screen before then cancels it.
        """
        self._paused = True
        self._sync_scanner()
        self._clear_timer.start(ms)
```

Replace the body of `clear_screen` (keep its docstring) with:

```python
        self._clear_timer.stop()
        if self._session_over:
            return
        self._items = []
        self._rows = []
        self._unknown = []
        self._sku_map = {}
        self._order_open = False
        self._paused = False
        self._question = {}
        self.bridge.set_question({})
        self.bridge.set_banner(banner_payload("", None))
        self.bridge.set_extras([])
        self.bridge.set_sku_rollup([])
        self._order_label.setText("No order")
        self.scanner_input.clear()
        self._raw_scan = ""
        self.show_notification("Scan an order barcode", "status_info")
        self._push_rows()
        self._sync_scanner()
```

Replace the body of `show_session_complete` (keep its docstring) with:

```python
        self._session_over = True
        self.bridge.set_session_end(payload)
        self._order_label.setText("Session complete")
        self._sync_scanner()
```

Replace the body of `reset_for_new_session` (keep its docstring) with:

```python
        self._session_over = False
        self.bridge.set_session_end({})
        self._taken_over = False
        self.bridge.set_takeover({})
        self._history = []
        self.bridge.set_history([])
        self._orders_done = 0
        self._orders_total = 0
        self._unsaved = False
        self.bridge.set_unsaved(False)
        self.clear_screen()  # pushes progress through _push_rows()
```

Add after `reset_for_new_session`:

```python
    def show_takeover(self, holder: str, list_name: str):
        """Another PC took this list's lock: block the screen (frame 6j).

        Nothing on the page works after this but Exit packing. Only
        reset_for_new_session() takes it down.
        """
        self._taken_over = True
        self._question = {}
        self.bridge.set_question({})
        self.bridge.set_takeover({"holder": str(holder), "list": str(list_name)})
        self._sync_scanner()
```

Replace `set_unsaved` and `_push_feedback` with:

```python
    def set_unsaved(self, unsaved: bool):
        """Show, or clear, that the packing state is not reaching disk.

        A banner above the band (frame 6i), not part of it: scanning
        continues and the band keeps reporting each scan.
        """
        self._unsaved = bool(unsaved)
        self.bridge.set_unsaved(self._unsaved)

    def _push_feedback(self):
        self.bridge.set_feedback(self._feedback_text, self._feedback_role, self._raw_scan)
```

In the class docstring, nothing needs to change. Delete the now-unused `QDialog` and `ConfirmDialog` references if any remain (`rg -n "ConfirmDialog|QDialog|UNSAVED_TEXT" gui/packer_mode_widget.py` must print nothing).

- [ ] **Step 7: Run the tests.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` then `.venv/bin/ruff check . --exclude shared`
Expected: all pass. If an older test asserts `placeholderText() == "Scanner disabled"`, change it to assert `widget._scanner_state.text() == "Scanner disabled"`.

- [ ] **Step 8: Commit** with the message `feat: Packer Mode's bar and scanner state to the mockup; Force confirm asks in the page`.

---

### Task 4: The page: floor.css, and Packer Mode to frames 6a to 6j

**Files:**
- Create: `gui/web/floor.css`
- Rewrite: `gui/web/packer.html`, `gui/web/packer.js`, `gui/web/packer.css`
- Test: `tests/test_packer_bridge.py`

**Interfaces:**
- Consumes: the bridge of Task 2 (properties `banner`, `feedback`, `items`, `extras`, `skuRollup`, `history`, `progress`, `sessionEnd`, `unsaved`, `question`, `takeover`, `themeCss`, `revision`; signal `scanFlashed(role)`; slots `confirmItem`, `undoItem`, `forceItem`, `mapSku`, `mapBarcode`, `keepExtra`, `removeExtra`, `endSession`, `exitPacking`, `answerQuestion`, `paintedRevision`), and `reportPaints(bridge)` from `shared/web/page.js`.
- Produces: the DOM ids and classes the tests below name. Kept from before: `#doc-main` (with `data-flash` and class `doc-state`), `#feedback`, `#feedback-text`, `#feedback-raw`, `#banner`, `#sku-list`, `.sku-row`, `.sku-row--<state>`, `.sku-row--just-changed`, `#extras`, `#extras-rows`, `.extras-row`, `.history-row`, `.history-row__order`, `#progress-fill`, `#progress-numbers`, `#summary-skus`, `.state-panel`, `.state-panel-title`, `.state-panel-body`, `.state-panel-actions`, `[data-action]`.

- [ ] **Step 1: Write the new failing tests.** Append to `tests/test_packer_bridge.py`:

```python
def _row(**over):
    row = {
        "row": 0, "product": "Sunscreen SPF 50", "sku": "SPF-50", "required": 8, "packed": 3,
        "state": "partial", "just_changed": False, "confirm": True, "undo": True,
        "force": True, "force_slot": True, "map": True, "mapBarcode": False,
    }
    row.update(over)
    return row


def test_the_page_has_nothing_that_could_take_the_keyboard(page, qtbot):
    view, _bridge = page
    assert _eval(
        qtbot, view,
        "document.querySelectorAll('input, textarea, select, [contenteditable]').length",
    ) == 0


def test_the_page_reports_the_revision_it_painted(page, qtbot):
    _view, bridge = page
    bridge.set_items([_row()])
    qtbot.waitUntil(lambda: bridge.painted_revision >= bridge.revision, timeout=20000)


def test_the_kit_and_the_floor_sheet_are_loaded(page, qtbot):
    view, bridge = page
    bridge.set_items([_row()])
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 1")
    style = "getComputedStyle(document.querySelector('.sku-row %s')).%s"
    assert _eval(qtbot, view, style % (".badge", "height")) == "28px"   # floor.css
    assert _eval(qtbot, view, style % (".btn", "height")) == "40px"     # floor.css compact
    assert _eval(qtbot, view, style % (".btn", "display")) == "inline-flex"  # kit.css
    assert _eval(qtbot, view, "getComputedStyle(document.querySelector('.sku-row')).minHeight") == "64px"


def test_6a_waiting_shows_the_info_band_and_an_empty_list(page, qtbot):
    view, bridge = page
    bridge.set_feedback("Scan an order barcode", "info", "")
    _until_js(qtbot, view, "document.getElementById('feedback').className === 'feedback feedback--info'")
    assert _eval(qtbot, view, "document.getElementById('list-empty').hidden") is False
    assert _eval(qtbot, view, "document.getElementById('list-empty').textContent") == "No order open"
    assert _eval(qtbot, view, "document.getElementById('list-head').hidden") is True
    assert _eval(qtbot, view, "document.getElementById('banner').hidden") is True
    assert _eval(qtbot, view, "document.getElementById('feedback-raw-box').hidden") is True


def test_6b_a_row_reads_sku_product_numeral_badge(page, qtbot):
    view, bridge = page
    bridge.set_items([_row()])
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 1")
    cell = "document.querySelector('.sku-row %s').textContent"
    assert _eval(qtbot, view, cell % ".sku-row__sku") == "SPF-50"
    assert _eval(qtbot, view, cell % ".sku-row__product") == "Sunscreen SPF 50"
    assert _eval(qtbot, view, cell % ".sku-row__num") == "3"
    assert _eval(qtbot, view, cell % ".sku-row__of") == "of 8"
    assert _eval(qtbot, view, "document.querySelector('.sku-row .badge').className") == "badge info"
    assert _eval(qtbot, view, "document.getElementById('list-head').hidden") is False
    assert _eval(
        qtbot, view,
        "Array.from(document.querySelectorAll('#list-head span')).map(e => e.textContent)",
    ) == ["SKU", "Product", "Packed", "Status", ""]


def test_6b_the_four_slots_are_always_there_in_the_same_order(page, qtbot):
    view, bridge = page
    bridge.set_items([
        _row(row=0),
        # complete: Confirm and Force are disabled, not gone
        _row(row=1, state="complete", packed=8, confirm=False, force=False),
        # a 2-unit, mapped line at zero: Force and Map SKU have no slot, Undo is disabled
        _row(row=2, state="pending", required=2, packed=0, undo=False,
             force=False, force_slot=False, map=False),
    ])
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row').length === 3")
    slots = _eval(
        qtbot, view,
        "Array.from(document.querySelectorAll('.sku-row')).map(r =>"
        " Array.from(r.querySelectorAll('.row-actions .btn')).map(b =>"
        " [b.textContent, b.disabled, 'absent' in b.dataset]))",
    )
    labels = ["Confirm", "Force confirm", "Undo", "Map SKU"]
    assert [[s[0] for s in row] for row in slots] == [labels, labels, labels]
    assert [(s[1], s[2]) for s in slots[0]] == [(False, False)] * 4
    assert [(s[1], s[2]) for s in slots[1]] == [(True, False), (True, False), (False, False), (False, False)]
    assert [(s[1], s[2]) for s in slots[2]] == [(False, False), (True, True), (True, False), (True, True)]
    assert _eval(
        qtbot, view,
        "getComputedStyle(document.querySelector('.btn[data-absent]')).visibility",
    ) == "hidden"


def test_6c_the_scanned_row_and_the_raw_scan(page, qtbot):
    view, bridge = page
    bridge.set_items([_row(just_changed=True)])
    bridge.set_feedback("SPF-50 confirmed — 3 of 8 packed", "success", "SPF-50")
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row--just-changed').length === 1")
    assert _eval(qtbot, view, "document.getElementById('feedback').className") == "feedback feedback--success"
    assert _eval(qtbot, view, "document.getElementById('feedback-raw-box').hidden") is False
    assert _eval(qtbot, view, "document.getElementById('feedback-raw').textContent") == "SPF-50"
    assert _eval(
        qtbot, view,
        "getComputedStyle(document.querySelector('.sku-row--just-changed')).borderLeftWidth",
    ) == "6px"


def test_the_flash_frame_is_ten_pixels_on_the_main_column(page, qtbot):
    view, _bridge = page
    assert _eval(
        qtbot, view, "document.getElementById('flash').parentElement.id"
    ) == "doc-main"
    assert _eval(
        qtbot, view, "getComputedStyle(document.getElementById('flash')).borderTopWidth"
    ) == "10px"


def test_6d_extras_sit_below_the_items_inside_the_list(page, qtbot):
    view, bridge = page
    bridge.set_items([_row()])
    bridge.set_extras([{"sku": "MSCBLK", "count": 2}])
    _until_js(qtbot, view, "document.querySelectorAll('.extras-row').length === 1")
    assert _eval(
        qtbot, view,
        "document.getElementById('sku-list').compareDocumentPosition("
        "document.getElementById('extras')) & Node.DOCUMENT_POSITION_FOLLOWING",
    ) != 0
    assert _eval(qtbot, view, "document.getElementById('list-scroll').contains(document.getElementById('extras'))") is True
    assert _eval(qtbot, view, "document.querySelector('.extras-row .badge').textContent") == "Extra"
    assert _eval(qtbot, view, "document.querySelector('.extras-row .sku-row__num').textContent") == "× 2"


def test_6e_an_unmatched_scan_is_a_no_match_row_that_only_maps(page, qtbot):
    view, bridge = page
    bridge.set_items([_row()] + unknown_rows(["4006381333931"]))
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row--unknown').length === 1")
    row = "document.querySelector('.sku-row--unknown %s').textContent"
    assert _eval(qtbot, view, row % ".badge") == "No match"
    assert _eval(qtbot, view, row % ".sku-row__code") == "4006381333931"
    assert _eval(qtbot, view, row % ".sku-row__why") == "Not a SKU or barcode this client knows"
    assert _eval(
        qtbot, view,
        "Array.from(document.querySelectorAll('.sku-row--unknown .btn')).map(b => b.textContent)",
    ) == ["Map barcode…"]
    with qtbot.waitSignal(bridge.mapBarcodeRequested, timeout=5000) as caught:
        view.page().runJavaScript("document.querySelector('.sku-row--unknown .btn').click()")
    assert caught.args == ["4006381333931"]


def test_6f_the_question_shows_and_each_button_answers(page, qtbot):
    view, bridge = page
    assert _eval(qtbot, view, "document.getElementById('question').hidden") is True
    bridge.set_question(
        {"row": 0, "sku": "SPF-50", "product": "Sunscreen SPF 50", "remaining": 5, "required": 8}
    )
    _until_js(qtbot, view, "document.getElementById('question').hidden === false")
    assert _eval(qtbot, view, "document.querySelector('#question .dialog-title').textContent") == (
        "Force confirm SPF-50?"
    )
    assert _eval(qtbot, view, "document.querySelector('#question .dialog-text').textContent") == (
        "Marks the remaining 5 of 8 × Sunscreen SPF 50 as packed without scanning."
        " This cannot be undone."
    )
    assert _eval(
        qtbot, view,
        "Array.from(document.querySelectorAll('#question .btn')).map(b => b.textContent)",
    ) == ["Cancel", "Force confirm"]
    with qtbot.waitSignal(bridge.questionAnswered, timeout=5000) as caught:
        view.page().runJavaScript("document.querySelector('[data-action=\"answerYes\"]').click()")
    assert caught.args == [True]
    with qtbot.waitSignal(bridge.questionAnswered, timeout=5000) as caught:
        view.page().runJavaScript("document.querySelector('[data-action=\"answerNo\"]').click()")
    assert caught.args == [False]
    bridge.set_question({})
    _until_js(qtbot, view, "document.getElementById('question').hidden === true")


def test_6g_a_complete_row_goes_quiet(page, qtbot):
    view, bridge = page
    bridge.set_items([_row(state="complete", packed=8, confirm=False, force=False)])
    _until_js(qtbot, view, "document.querySelectorAll('.sku-row--complete').length === 1")
    assert _eval(qtbot, view, "document.querySelector('.sku-row .badge').className") == "badge success"
    assert _eval(
        qtbot, view, "getComputedStyle(document.querySelector('.sku-row__num')).fontWeight"
    ) == "400"


def test_6i_the_unsaved_banner_follows_its_own_state(page, qtbot):
    view, bridge = page
    bridge.set_feedback("SPF-50 confirmed — 3 of 8 packed", "success", "SPF-50")
    assert _eval(qtbot, view, "document.getElementById('unsaved').hidden") is True
    bridge.set_unsaved(True)
    _until_js(qtbot, view, "document.getElementById('unsaved').hidden === false")
    assert "Progress not saved — check the network" in _eval(
        qtbot, view, "document.getElementById('unsaved').textContent"
    )
    assert _eval(qtbot, view, "document.getElementById('feedback').className") == "feedback feedback--success"
    bridge.set_unsaved(False)
    _until_js(qtbot, view, "document.getElementById('unsaved').hidden === true")


def test_6j_the_takeover_panel_names_the_holder_and_only_exits(page, qtbot):
    view, bridge = page
    assert _eval(qtbot, view, "document.getElementById('takeover').hidden") is True
    bridge.set_takeover({"holder": "Georgi Dimitrov", "list": "acme-packing-07-10"})
    _until_js(qtbot, view, "document.getElementById('takeover').hidden === false")
    assert _eval(qtbot, view, "document.querySelector('#takeover .dialog-title').textContent.trim()") == (
        "This list is open on another PC"
    )
    text = _eval(qtbot, view, "document.querySelector('#takeover .dialog-text').textContent")
    assert text.startswith("Georgi Dimitrov has taken over acme-packing-07-10. This PC has stopped packing it")
    assert _eval(
        qtbot, view,
        "Array.from(document.querySelectorAll('#takeover .btn')).map(b => b.textContent)",
    ) == ["Exit packing"]
    with qtbot.waitSignal(bridge.exitPackingRequested, timeout=5000):
        view.page().runJavaScript("document.querySelector('#takeover .btn').click()")


def test_a_long_sentence_stays_inside_the_band(page, qtbot):
    view, bridge = page
    bridge.set_feedback("Unknown SKU " + "9" * 90 + " — scan again or map it", "danger", "9" * 90)
    _until_js(qtbot, view, "document.getElementById('feedback-text').textContent.length > 90")
    assert _eval(
        qtbot, view,
        "document.getElementById('feedback').scrollWidth <= document.getElementById('feedback').clientWidth",
    ) is True
    assert _eval(
        qtbot, view,
        "document.getElementById('doc-main').scrollWidth <= document.getElementById('doc-main').clientWidth",
    ) is True


def test_the_side_column_is_248_pixels_and_lists_skus_with_a_dot(page, qtbot):
    view, bridge = page
    bridge.set_sku_rollup([
        {"sku": "CRM-50ML", "product": "", "packed": 1, "required": 3, "state": "partial"},
        {"sku": "LIP-RED", "product": "", "packed": 2, "required": 2, "state": "complete"},
    ])
    _until_js(qtbot, view, "document.querySelectorAll('.rollup-row').length === 2")
    assert _eval(qtbot, view, "document.querySelector('.side').getBoundingClientRect().width") == 248
    assert _eval(
        qtbot, view,
        "Array.from(document.querySelectorAll('.rollup-row .dot')).map(d => d.className)",
    ) == ["dot dot--partial", "dot dot--complete"]
    assert _eval(
        qtbot, view,
        "Array.from(document.querySelectorAll('.rollup-row__qty')).map(e => e.textContent)",
    ) == ["1 / 3", "2 / 2"]
```

- [ ] **Step 2: Update the older page tests in the same file for the new DOM.** These are the known breaks; fix each as stated:

| Test | Change |
|---|---|
| `test_a_row_shows_product_sku_and_the_packed_count` | the quantity is two spans: assert `.sku-row__num` is the packed count and `.sku-row__of` is `"of N"` |
| `test_each_state_carries_the_artboard_s_chip` | select `.sku-row .badge` instead of `.chip`; the texts stay "Complete", "Partial" (and "Pending") |
| `test_clicking_a_row_action_in_the_page_calls_its_slot` | click `[data-action="confirm"]:not(:disabled)`: the first row is complete and its Confirm is now present but disabled |
| `test_history_lists_newest_first_with_a_status_chip` | select `.history-row__status` instead of `.history-row .chip`; a completed order reads "Packed", a skipped one "Skipped" |
| `test_no_orders_yet_leaves_the_bar_empty_and_says_so` | unchanged text "No orders yet" in `#history-rows`; if it also checks the roll-up's empty text, that is now "No order open" |
| `test_extras_appear_above_the_list_with_keep_and_remove` | rename to `..._in_the_list_...`; its selectors still match |
| `test_a_repeat_only_banner_shows_the_warning_chip_and_no_notes` | assert `document.getElementById('banner-repeat').hidden === false`, its text "Repeat", and `document.getElementById('banner-notes').hidden === true` |
| `test_an_unmatched_scan_draws_a_no_match_row_that_only_maps` and `test_mapping_an_unmatched_scan_reaches_python_with_the_barcode` | delete both; `test_6e_...` above replaces them |
| `test_a_finished_session_replaces_the_document_with_its_panel` | where it reads `getComputedStyle(document.getElementById('sku-list')).display`, read `document.getElementById('list')` instead (the list is now inside a card, and the card is what is hidden) |

Any other test in the file that fails after Step 6 for a selector reason: fix the selector to the new DOM, never the assertion's meaning.

- [ ] **Step 3: Create `gui/web/floor.css`.**

```css
/* Floor density over the shared kit (ADR 0002): what a packer reads and
   presses at arm's length. No page layout and no #id in here.

   Control height (44px), body (12pt) and caption (10pt) already arrive as
   theme_css_vars() in the floor profile, so this sheet holds only what
   shared/web/kit.css sizes for the office. Sizes are from
   docs/design/ui-refresh/mockups/Floor Components.html. Loaded after kit.css
   and before the page's own sheet. Web-tier rules as in kit.css.

   Phases 3 to 5 add table rows, inputs and the toast here when a page first
   uses them. */

/* --- buttons ------------------------------------------------------------- */

.btn { padding: 0 18px; }

/* The floor's smaller button, for a row of actions. Still a 40px target. */
.btn.compact { height: 40px; padding: 0 12px; }

/* A ghost button has no box, so at this distance it needs the underline. */
.btn.ghost { text-decoration: underline; }

/* --- badges -------------------------------------------------------------- */

.badge {
  height: 28px;
  padding: 0 12px;
  border-radius: 14px;
  font-size: var(--type-body-size);
}

/* A neutral word carries a strong border so it reads without colour. */
.badge.neutral { border-color: var(--border-strong); }

/* --- banner -------------------------------------------------------------- */

.banner { align-items: center; gap: 14px; padding: 12px 16px; }
.banner.danger > .glyph { width: 24px; height: 24px; }
.banner.danger .banner-title {
  flex: 1;
  min-width: 0;
  font-size: var(--type-heading-size);
  color: var(--status-danger);
}

/* --- a panel that takes the page over ------------------------------------ */

.scrim {
  position: absolute;
  inset: 0;
  z-index: var(--z-popover);
  display: grid;
  place-items: center;
  background: var(--scrim);
}

.dialog {
  width: 520px;
  max-width: calc(100% - 48px);
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 28px;
  background: var(--surface-overlay);
  border: 1px solid var(--border-strong);
  border-radius: var(--kit-radius-card);
  box-shadow: var(--overlay-shadow);
}
.dialog.danger { width: 600px; border-color: var(--status-danger-border); }

.dialog-title {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0;
  font-size: var(--type-display-size);
  font-weight: 700;
}
.dialog-title .glyph { width: 28px; height: 28px; }
.dialog.danger .dialog-title { color: var(--status-danger); }

.dialog-text { margin: 0; }
.dialog.danger .dialog-text { font-size: var(--type-heading-size); }

.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 8px;
}
```

- [ ] **Step 4: Rewrite `gui/web/packer.html`.** The whole file:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Packer Mode</title>
<!-- shared/web_page.mount_page writes theme_css_vars() over the marker in the
     style element below before the page loads; packer.js keeps it current. -->
<style id="theme-vars">/* theme-vars */</style>
<link rel="stylesheet" href="../../shared/web/kit.css">
<link rel="stylesheet" href="floor.css">
<link rel="stylesheet" href="packer.css">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="../../shared/web/page.js"></script>
<script src="packer.js" defer></script>
</head>
<body>
<!-- No input, textarea, select or contenteditable on this page, ever: the
     scanner types into a Qt field and this view never takes the keyboard
     (ADR 0001). -->
<div class="pm" id="pm">
  <div class="doc-main" id="doc-main">
    <div class="pm-flash" id="flash"></div>

    <div class="banner danger" id="unsaved" hidden>
      <svg class="glyph" viewBox="0 0 24 24"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
      <span class="banner-title">Progress not saved — check the network</span>
      <span class="banner-text">Scanning continues</span>
    </div>

    <div class="card pm-order" id="banner" hidden>
      <span class="pm-order-chips" id="banner-chips"></span>
      <span class="doc-banner-notes" id="banner-notes" hidden>
        <svg class="glyph" viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        <span id="banner-notes-text"></span>
      </span>
      <span class="badge warning" id="banner-repeat" hidden>Repeat</span>
    </div>

    <div class="feedback feedback--info" id="feedback">
      <span class="feedback__text" id="feedback-text">Scan an order barcode</span>
      <span class="feedback__raw" id="feedback-raw-box" hidden>
        <span class="feedback__raw-label">Scanned</span>
        <span class="feedback__raw-code" id="feedback-raw"></span>
      </span>
    </div>

    <div class="card pm-list" id="list">
      <div class="pm-empty" id="list-empty">No order open</div>
      <div class="pm-head" id="list-head" hidden><span>SKU</span><span>Product</span><span>Packed</span><span>Status</span><span></span></div>
      <div class="pm-rows" id="list-scroll" hidden>
        <div id="sku-list" hidden></div>
        <div id="extras" hidden>
          <div class="pm-extras-title">Extra items scanned</div>
          <div id="extras-rows"></div>
        </div>
        <div id="unmatched-rows"></div>
      </div>
    </div>

    <div class="card state-panel" id="state-panel">
      <svg class="glyph" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>
      <p class="state-panel-title" id="state-title"></p>
      <p class="state-panel-body" id="state-body"></p>
      <div class="state-panel-actions">
        <button class="btn primary" type="button" data-action="endSession">End session</button>
        <button class="btn secondary" type="button" data-action="exitPacking">Exit packing</button>
      </div>
    </div>
  </div>

  <aside class="side">
    <div class="side-block">
      <div class="side-block-title">Session progress</div>
      <div class="progress-track"><div class="progress-fill" id="progress-fill"></div></div>
      <div class="progress-numbers" id="progress-numbers">0 / 0 orders &middot; 0 / 0 items</div>
    </div>
    <div class="side-block">
      <div class="side-block-title">History</div>
      <div class="history" id="history-rows"></div>
    </div>
    <div class="side-block">
      <div class="side-block-title">Items by SKU</div>
      <div id="rollup-rows"></div>
    </div>
    <div class="side-block">
      <div class="side-block-title">Summary</div>
      <div class="summary-line"><span>Unique SKUs packed</span><strong id="summary-skus">0 / 0</strong></div>
    </div>
  </aside>

  <div class="scrim" id="question" hidden>
    <section class="dialog">
      <p class="dialog-title"><span>Force confirm <span class="mono" id="question-sku"></span>?</span></p>
      <p class="dialog-text">Marks the remaining <strong id="question-remaining"></strong><span id="question-rest"></span></p>
      <div class="dialog-actions">
        <button class="btn secondary" type="button" data-action="answerNo">Cancel</button>
        <button class="btn critical" type="button" data-action="answerYes">Force confirm</button>
      </div>
    </section>
  </div>

  <div class="scrim" id="takeover" hidden>
    <section class="dialog danger">
      <p class="dialog-title">
        <svg class="glyph" viewBox="0 0 24 24"><rect width="20" height="14" x="2" y="3" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/></svg>
        This list is open on another PC
      </p>
      <p class="dialog-text"><strong id="takeover-holder"></strong> has taken over <span class="mono" id="takeover-list"></span>. This PC has stopped packing it so the two don't overwrite each other's progress. Orders packed here up to now are saved.</p>
      <div class="dialog-actions">
        <button class="btn primary" type="button" data-action="exitPacking">Exit packing</button>
      </div>
    </section>
  </div>
</div>
</body>
</html>
```

The literal text `/* theme-vars */` must appear exactly once in the file (a test counts it), so do not quote it in a comment.

- [ ] **Step 5: Rewrite `gui/web/packer.css`.** The whole file:

```css
/* Packer Mode's own sheet (UI refresh phase 2). Buttons, badges, cards,
   the banner and the taking-over panel come from shared/web/kit.css and
   floor.css; this file is the page's layout and the parts only it has.
   Mockup: docs/design/ui-refresh/mockups/Packer Mode.html, frames 6a-6j.
   Spec: docs/superpowers/specs/2026-10-08-ui-refresh-phase2-packer-mode-design.md
   Web-tier rules (ADR 0001): var(--...) only, pt font sizes, one mono face,
   no transition/transform/opacity. @keyframes over border-color is allowed. */

:root {
  /* Off the type scale, which has no rung between 17 and 28pt: read from
     across a packing bench. */
  --pm-raw-size: 20pt;
  --pm-numeral-size: 26pt;
  --pm-band-size: 30pt;
  /* SKU, product, packed, status, actions. The head and every row share it. */
  --pm-cols: 150px minmax(0, 1fr) 128px 116px 404px;
}

.pm {
  position: relative;
  height: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 248px;
}

.doc-main {
  position: relative;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px 20px 20px;
  overflow: hidden;
}

/* --- scan flash: a frame on the main column's edge ----------------------- */

/* Only border-color animates. It pulses twice and clears: the band holds the
   outcome's colour after that. */
.pm-flash {
  position: absolute;
  inset: 0;
  z-index: var(--z-bar);
  border: 10px solid transparent;
  pointer-events: none;
}
@keyframes scan-flash {
  0%, 28%, 100% { border-color: transparent; }
  10%, 46%, 80% { border-color: var(--flash); }
}
.doc-main[data-flash] .pm-flash { animation: scan-flash 900ms ease-out; }
.doc-main[data-flash="success"] { --flash: var(--status-success-dot); }
.doc-main[data-flash="warning"] { --flash: var(--status-warning); }
.doc-main[data-flash="danger"] { --flash: var(--status-danger-dot); }

/* --- order card ---------------------------------------------------------- */

.pm-order {
  flex: none;
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
  min-height: 56px;
  padding: 8px 20px;
}
.pm-order-chips { display: flex; flex-wrap: wrap; gap: 8px; }
.doc-banner-notes {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
}
.doc-banner-notes .glyph { width: 18px; height: 18px; }
.doc-banner-notes > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#banner-repeat { margin-left: auto; }

/* --- feedback band: a solid status fill, one large sentence -------------- */

.feedback {
  flex: none;
  display: flex;
  align-items: center;
  gap: 24px;
  min-height: 96px;
  padding: 10px 28px;
  border-radius: var(--kit-radius-card);
  background: var(--surface-raised);
  color: var(--text);
}
.feedback--info { background: var(--status-info); color: var(--on-accent); }
.feedback--success { background: var(--status-success); color: var(--on-accent); }
.feedback--warning { background: var(--status-warning); color: var(--on-accent); }
.feedback--danger { background: var(--status-danger); color: var(--on-accent); }

/* Wraps, never cut: a packer acts on this sentence. */
.feedback__text {
  flex: 1;
  min-width: 0;
  font-size: var(--pm-band-size);
  font-weight: 700;
  line-height: 1.15;
  overflow-wrap: anywhere;
}
.feedback__raw {
  flex: none;
  max-width: 40%;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}
.feedback__raw-label { font-size: var(--type-caption-size); font-weight: 700; }
.feedback__raw-code {
  max-width: 100%;
  font-family: var(--font-family-mono);
  font-size: var(--pm-raw-size);
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* --- the list ------------------------------------------------------------ */

.pm-list {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.pm-empty {
  flex: 1;
  display: grid;
  place-items: center;
  padding: 24px;
  font-size: var(--type-heading-size);
  color: var(--text-secondary);
}
.pm-head {
  flex: none;
  display: grid;
  grid-template-columns: var(--pm-cols);
  column-gap: 12px;
  align-items: center;
  height: 36px;
  padding: 0 16px;
  background: var(--surface-raised);
  border-bottom: 1px solid var(--border);
  font-size: var(--type-caption-size);
  font-weight: 700;
  color: var(--text-secondary);
}
.pm-rows { flex: 1; min-height: 0; overflow-y: auto; }

.sku-row,
.extras-row {
  display: grid;
  grid-template-columns: var(--pm-cols);
  column-gap: 12px;
  align-items: center;
  min-height: 64px;
  padding: 0 16px;
  border-bottom: 1px solid var(--border-subtle);
  font-size: var(--type-heading-size);
}
.sku-row__sku {
  font-family: var(--font-family-mono);
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sku-row__product { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sku-row__qty { display: flex; align-items: baseline; gap: 6px; white-space: nowrap; }
.sku-row__num { font-size: var(--pm-numeral-size); font-weight: 700; line-height: 1; }
.sku-row__of { color: var(--text-secondary); }

/* A finished line goes quiet. */
.sku-row--complete { background: var(--surface-raised); color: var(--text-secondary); }
.sku-row--complete .sku-row__sku,
.sku-row--complete .sku-row__num { font-weight: 400; }

/* The row a scan just landed on. After --complete, so it wins on the last
   scan of a line. The padding gives back the bar's 6px. */
.sku-row--just-changed {
  padding-left: 10px;
  border-left: 6px solid var(--status-success-dot);
  background: var(--status-success-bg);
  color: var(--text);
}
.sku-row--just-changed .sku-row__num { color: var(--status-success); }

.row-actions { display: flex; gap: 6px; justify-content: flex-end; }
/* An act that never applies to this row keeps its slot, so the buttons line
   up down the list. */
.btn[data-absent] { visibility: hidden; }

.pm-extras-title {
  display: flex;
  align-items: center;
  height: 40px;
  margin-top: 8px;
  padding: 0 16px;
  background: var(--status-warning-bg);
  border-top: 1px solid var(--border);
  border-bottom: 1px solid var(--border);
  font-weight: 700;
  color: var(--status-warning);
}

/* An unmatched scan is not an item: a strip of its own under the list. */
.sku-row--unknown {
  display: flex;
  gap: 16px;
  margin-top: 8px;
  background: var(--status-danger-bg);
  border-top: 1px solid var(--status-danger-border);
  border-bottom: 1px solid var(--status-danger-border);
}
.sku-row__code {
  font-family: var(--font-family-mono);
  font-size: var(--type-display-size);
  font-weight: 700;
}
.sku-row__why {
  flex: 1;
  min-width: 0;
  font-size: var(--type-body-size);
  color: var(--status-danger);
}

/* --- session complete: a panel in the main column's place ---------------- */

.state-panel {
  width: 100%;
  max-width: 560px;
  margin: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 40px 32px;
  text-align: center;
}
.state-panel > .glyph { width: 48px; height: 48px; color: var(--status-success-dot); }
.state-panel-title {
  margin: 0;
  font-size: var(--type-display-xl-size);
  font-weight: 700;
  line-height: 1.2;
}
.state-panel-body {
  margin: 0;
  font-size: var(--type-heading-size);
  color: var(--text-secondary);
}
.state-panel-actions { display: flex; gap: 10px; margin-top: 10px; }

/* One class decides the swap. The regions the panel replaces stay in the
   DOM and the bridge keeps filling them; only one of the two paints. */
.doc-main.doc-state > :not(.state-panel) { display: none; }
.doc-main:not(.doc-state) > .state-panel { display: none; }

/* --- side column: 248px, no cards, caption size -------------------------- */

.side {
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  padding: 16px 16px 20px 4px;
  font-size: var(--type-caption-size);
}
.side-block {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 12px 0;
  border-top: 1px solid var(--border);
}
.side-block:first-child { gap: 6px; padding-top: 0; border-top: 0; }
.side-block-title { margin-bottom: 4px; font-weight: 700; color: var(--text-secondary); }
.side-block:first-child .side-block-title { margin-bottom: 0; }

.progress-track {
  height: 8px;
  border-radius: 4px;
  background: var(--border);
  overflow: hidden;
}
.progress-fill { height: 100%; background: var(--status-success-dot); }
.progress-numbers, .side-empty { color: var(--text-secondary); }

/* History scrolls inside its own block: a long session would otherwise push
   Items by SKU off the screen. Every order stays reachable. */
.history { max-height: 200px; overflow-y: auto; }

.history-row, .rollup-row { display: flex; align-items: center; gap: 8px; min-height: 24px; }
.history-row__order, .rollup-row__sku { flex: 1; font-family: var(--font-family-mono); }
.history-row__status { color: var(--text-secondary); }
.history-row__status--skipped { font-weight: 700; color: var(--status-warning); }
.rollup-row__qty { font-family: var(--font-family-mono); color: var(--text-secondary); }

.dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--border-strong);
}
.dot--partial { background: var(--status-info); }
.dot--complete { background: var(--status-success-dot); }

.summary-line { display: flex; align-items: baseline; gap: 8px; }
.summary-line > span { flex: 1; color: var(--text-secondary); }
.summary-line > strong { font-family: var(--font-family-mono); }
```

- [ ] **Step 6: Rewrite `gui/web/packer.js`.** The whole file:

```js
// Packer Mode's order document. The page renders what the bridge sends and
// decides nothing: item state and row actions are decided in
// gui/packer_bridge.py. Every string from the bridge goes in through
// textContent. Spec:
// docs/superpowers/specs/2026-10-08-ui-refresh-phase2-packer-mode-design.md
"use strict";

const els = {};
const state = { bridge: null };

function onTheme() {
  els.themeVars.textContent = state.bridge.themeCss;
}

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function button(label, action, kind) {
  const btn = el("button", "btn compact " + kind, label);
  btn.type = "button";
  btn.dataset.action = action;
  return btn;
}

function renderFeedback() {
  const fb = state.bridge.feedback || {};
  els.feedbackText.textContent = fb.text || "";
  els.feedbackRaw.textContent = fb.raw || "";
  els.feedbackRawBox.hidden = !fb.raw;
  els.feedback.className = "feedback" + (fb.role ? " feedback--" + fb.role : "");
}

function flash(role) {
  // Remove, force a reflow, re-add: an animation already running would
  // otherwise ignore the new scan.
  delete els.docMain.dataset.flash;
  void els.docMain.offsetWidth;
  els.docMain.dataset.flash = role;
}

const BADGE = {
  complete: { text: "Complete", cls: "badge success" },
  partial: { text: "Partial", cls: "badge info" },
  pending: { text: "Pending", cls: "badge neutral" },
};

function orderLabel(order) {
  // Same rule as packer_bridge.order_label, including the empty case.
  const text = String(order == null ? "" : order);
  if (!text) return "No order";
  return text.startsWith("#") ? text : "#" + text;
}

// One of a row's four fixed slots. `present` false: the act never applies to
// this row, and the slot is kept empty so the columns line up. `enabled`
// false: it does not apply right now.
function slot(label, action, r, kind, present, enabled, title) {
  const btn = button(label, action, kind);
  btn.dataset.row = r.row;
  btn.dataset.sku = r.sku;
  btn.disabled = !present || !enabled;
  if (!present) btn.dataset.absent = "";
  else if (title) btn.title = title;
  return btn;
}

function itemRow(r) {
  const row = el(
    "div",
    "sku-row sku-row--" + r.state + (r.just_changed ? " sku-row--just-changed" : "")
  );
  row.appendChild(el("span", "sku-row__sku", r.sku));
  row.appendChild(el("span", "sku-row__product", r.product));
  const qty = el("span", "sku-row__qty");
  qty.appendChild(el("span", "sku-row__num", String(r.packed)));
  qty.appendChild(el("span", "sku-row__of", "of " + r.required));
  row.appendChild(qty);
  const badge = BADGE[r.state] || BADGE.pending;
  const status = el("span", "sku-row__status");
  status.appendChild(el("span", badge.cls, badge.text));
  row.appendChild(status);
  const actions = el("span", "row-actions");
  actions.appendChild(slot("Confirm", "confirm", r, "secondary", true, r.confirm, "Confirm one unit"));
  actions.appendChild(
    slot("Force confirm", "force", r, "secondary", r.force_slot, r.force, "Confirm all remaining units")
  );
  actions.appendChild(slot("Undo", "undo", r, "ghost", true, r.undo, "Take one back"));
  actions.appendChild(slot("Map SKU", "map", r, "ghost", r.map, true, ""));
  row.appendChild(actions);
  return row;
}

function unknownRow(r) {
  const row = el("div", "sku-row sku-row--unknown");
  row.appendChild(el("span", "badge danger", "No match"));
  row.appendChild(el("span", "sku-row__code", r.sku));
  row.appendChild(el("span", "sku-row__why", "Not a SKU or barcode this client knows"));
  const btn = button("Map barcode…", "mapBarcode", "secondary");
  btn.dataset.sku = r.sku;
  row.appendChild(btn);
  return row;
}

// The card says "No order open" until it has a row of any kind.
function syncList() {
  const empty =
    els.skuList.children.length === 0 &&
    els.unmatched.children.length === 0 &&
    els.extras.hidden;
  els.listEmpty.hidden = !empty;
  els.listHead.hidden = empty;
  els.listScroll.hidden = empty;
}

function renderItems() {
  // Unmatched scans ride in the same property with state "unknown"; they are
  // drawn under the extras, not among the items.
  const rows = state.bridge.items || [];
  els.skuList.textContent = "";
  els.unmatched.textContent = "";
  let changed = null;
  rows.forEach(function (r) {
    if (r.state === "unknown") {
      els.unmatched.appendChild(unknownRow(r));
      return;
    }
    const row = itemRow(r);
    if (r.just_changed) changed = row;
    els.skuList.appendChild(row);
  });
  els.skuList.hidden = els.skuList.children.length === 0;
  syncList();
  if (changed) changed.scrollIntoView({ block: "nearest" });
}

function renderExtras() {
  const rows = state.bridge.extras || [];
  els.extrasRows.textContent = "";
  els.extras.hidden = rows.length === 0;
  rows.forEach(function (r) {
    // An extra is a normalised SKU and a count: there is no product name.
    const row = el("div", "extras-row");
    row.appendChild(el("span", "sku-row__sku", r.sku));
    row.appendChild(el("span", "sku-row__product", ""));
    const qty = el("span", "sku-row__qty");
    qty.appendChild(el("span", "sku-row__num", "× " + r.count));
    row.appendChild(qty);
    const status = el("span", "sku-row__status");
    status.appendChild(el("span", "badge warning", "Extra"));
    row.appendChild(status);
    const actions = el("span", "row-actions");
    ["keep", "remove"].forEach(function (action) {
      const btn = button(action === "keep" ? "Keep" : "Remove", action, "secondary");
      btn.dataset.sku = r.sku;
      actions.appendChild(btn);
    });
    row.appendChild(actions);
    els.extrasRows.appendChild(row);
  });
  syncList();
}

function renderBanner() {
  // The order number itself is in the Qt bar above the page.
  const b = state.bridge.banner || {};
  const chips = b.chips || [];
  els.bannerChips.textContent = "";
  chips.forEach(function (c) {
    els.bannerChips.appendChild(el("span", "badge neutral", c));
  });
  els.bannerNotesText.textContent = b.notes || "";
  els.bannerNotes.hidden = !b.notes;
  els.bannerRepeat.hidden = !b.repeat;
  els.banner.hidden = chips.length === 0 && !b.notes && !b.repeat;
}

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

function renderHistory() {
  const rows = state.bridge.history || [];
  els.historyRows.textContent = "";
  if (rows.length === 0) {
    const empty = el("div", "history-row");
    empty.appendChild(el("span", "history-row__order side-empty", "No orders yet"));
    els.historyRows.appendChild(empty);
    return;
  }
  rows.forEach(function (r) {
    const skipped = r.status === "skipped";
    const row = el("div", "history-row");
    row.appendChild(el("span", "history-row__order", orderLabel(r.order)));
    row.appendChild(
      el(
        "span",
        "history-row__status" + (skipped ? " history-row__status--skipped" : ""),
        skipped ? "Skipped" : "Packed"
      )
    );
    els.historyRows.appendChild(row);
  });
}

function renderRollup() {
  const rows = state.bridge.skuRollup || [];
  els.rollupRows.textContent = "";
  if (rows.length === 0) {
    els.rollupRows.appendChild(el("span", "side-empty", "No order open"));
    return;
  }
  rows.forEach(function (r) {
    const row = el("div", "rollup-row");
    row.appendChild(el("span", "dot dot--" + r.state));
    row.appendChild(el("span", "rollup-row__sku", r.sku));
    row.appendChild(el("span", "rollup-row__qty", r.packed + " / " + r.required));
    els.rollupRows.appendChild(row);
  });
}

function renderSessionEnd() {
  const s = state.bridge.sessionEnd || {};
  // One class decides the whole swap; CSS hides the regions the panel
  // replaces, so there is no per-region bookkeeping to get out of step.
  els.docMain.classList.toggle("doc-state", Boolean(s.title));
  els.stateTitle.textContent = s.title || "";
  els.stateBody.textContent = s.body || "";
}

function renderUnsaved() {
  els.unsaved.hidden = !state.bridge.unsaved;
}

function renderQuestion() {
  const q = state.bridge.question || {};
  const open = q.sku !== undefined;
  els.question.hidden = !open;
  els.questionSku.textContent = open ? q.sku : "";
  els.questionRemaining.textContent = open ? String(q.remaining) : "";
  els.questionRest.textContent = open
    ? " of " + q.required + " × " + q.product +
      " as packed without scanning. This cannot be undone."
    : "";
}

function renderTakeover() {
  const t = state.bridge.takeover || {};
  els.takeover.hidden = !t.holder;
  els.takeoverHolder.textContent = t.holder || "";
  els.takeoverList.textContent = t.list || "";
}

// One entry per action a button can ask for.
const ACTIONS = {
  confirm: function (btn, bridge) { bridge.confirmItem(Number(btn.dataset.row)); },
  undo: function (btn, bridge) { bridge.undoItem(Number(btn.dataset.row)); },
  force: function (btn, bridge) { bridge.forceItem(Number(btn.dataset.row)); },
  map: function (btn, bridge) { bridge.mapSku(btn.dataset.sku); },
  mapBarcode: function (btn, bridge) { bridge.mapBarcode(btn.dataset.sku); },
  keep: function (btn, bridge) { bridge.keepExtra(btn.dataset.sku); },
  remove: function (btn, bridge) { bridge.removeExtra(btn.dataset.sku); },
  endSession: function (btn, bridge) { bridge.endSession(); },
  exitPacking: function (btn, bridge) { bridge.exitPacking(); },
  answerYes: function (btn, bridge) { bridge.answerQuestion(true); },
  answerNo: function (btn, bridge) { bridge.answerQuestion(false); },
};

function onActionClick(event) {
  const btn = event.target.closest("[data-action]");
  if (!btn || btn.disabled) return;
  const run = ACTIONS[btn.dataset.action];
  if (run) run(btn, state.bridge);
}

const IDS = {
  themeVars: "theme-vars", root: "pm", docMain: "doc-main",
  feedback: "feedback", feedbackText: "feedback-text",
  feedbackRaw: "feedback-raw", feedbackRawBox: "feedback-raw-box",
  banner: "banner", bannerChips: "banner-chips", bannerNotes: "banner-notes",
  bannerNotesText: "banner-notes-text", bannerRepeat: "banner-repeat",
  listEmpty: "list-empty", listHead: "list-head", listScroll: "list-scroll",
  skuList: "sku-list", extras: "extras", extrasRows: "extras-rows",
  unmatched: "unmatched-rows",
  progressFill: "progress-fill", progressNumbers: "progress-numbers",
  summarySkus: "summary-skus", historyRows: "history-rows", rollupRows: "rollup-rows",
  stateTitle: "state-title", stateBody: "state-body", unsaved: "unsaved",
  question: "question", questionSku: "question-sku",
  questionRemaining: "question-remaining", questionRest: "question-rest",
  takeover: "takeover", takeoverHolder: "takeover-holder", takeoverList: "takeover-list",
};

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.packer;
  state.bridge = bridge;
  // The test harness drives the page through this handle; nothing in the
  // page reads it.
  window.packerBridge = bridge;
  Object.keys(IDS).forEach(function (key) {
    els[key] = document.getElementById(IDS[key]);
  });

  const renders = [
    [bridge.feedbackChanged, renderFeedback],
    [bridge.itemsChanged, renderItems],
    [bridge.extrasChanged, renderExtras],
    [bridge.bannerChanged, renderBanner],
    [bridge.progressChanged, renderProgress],
    [bridge.historyChanged, renderHistory],
    [bridge.skuRollupChanged, renderRollup],
    [bridge.sessionEndChanged, renderSessionEnd],
    [bridge.unsavedChanged, renderUnsaved],
    [bridge.questionChanged, renderQuestion],
    [bridge.takeoverChanged, renderTakeover],
  ];

  onTheme();
  bridge.themeCssChanged.connect(onTheme);
  bridge.scanFlashed.connect(flash);
  renders.forEach(function (pair) {
    pair[0].connect(pair[1]);
    pair[1]();
  });
  // The flash frame's animation ends on a child; the event bubbles here.
  els.docMain.addEventListener("animationend", function () {
    delete els.docMain.dataset.flash;
  });
  // One listener at the root: the row buttons, the panel's buttons and the
  // two taking-over panels are all under it.
  els.root.addEventListener("click", onActionClick);

  // After the first renders, so the first report is of a drawn page.
  reportPaints(bridge);
  document.documentElement.dataset.bridge = "ready";
});
```

- [ ] **Step 7: Run the page tests and fix selector breaks.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_packer_bridge.py tests/test_packer_scanner_focus.py tests/test_style_literals_guard.py`
Expected: all pass. If `test_the_side_column_is_248_pixels...` reads a fractional width, the grid is wrong, not the test. If `test_a_long_sentence_stays_inside_the_band` fails, the fix is in `packer.css` (`min-width: 0` on a flex child), not in the test.

- [ ] **Step 8: Run the whole suite and lint.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` then `.venv/bin/ruff check . --exclude shared`
Expected: all pass.

- [ ] **Step 9: Commit** `gui/web/`, `tests/test_packer_bridge.py` with the message `feat: Packer Mode's page on kit.css and floor.css, to mockup frames 6a-6j`.

---

### Task 5: MainWindow: the takeover in the page, leaving after the paint, the band when an order opens

**Files:**
- Modify: `gui/main_window.py` (`_on_lock_lost` near line 1071, `_teardown_session` near 1765, `switch_to_packer_mode` and `switch_to_session_view` near 1850, `on_scanner_input` near 1880)
- Test: `tests/test_session_lock_loss.py`, `tests/test_packer_mainwindow_seam.py`

**Interfaces:**
- Consumes: `PackerModeWidget.show_takeover`, `.taken_over`, `.pause_scanner`, `.resume_scanner` (Task 3); `shared.web_page.when_painted(bridge, callback, timeout_ms=150)`; `gui.packer_bridge.order_label`.
- Produces: `MainWindow._show_session_view()`.

- [ ] **Step 1: Write the failing lock-loss test.** Append to `tests/test_session_lock_loss.py`:

```python
def test_a_lost_lock_in_packer_mode_shows_the_panel_and_waits_for_exit(
    main_window, tmp_path, monkeypatch
):
    """Frame 6j. Writing stops at once; the session is torn down when the
    packer exits, not under them."""
    work_dir = tmp_path / "packing" / "DHL_Orders"
    work_dir.mkdir(parents=True)
    now = datetime.now().astimezone().isoformat()
    (work_dir / SessionLockManager.LOCK_FILENAME).write_text(
        json.dumps({"locked_by": "PC-2", "user_name": "x", "lock_time": now,
                    "heartbeat": now, "process_id": 1}),
        encoding="utf-8",
    )
    logic = LockLossLogic()
    logic.clear_current_order = lambda: None
    main_window.logic = logic
    main_window.current_work_dir = str(work_dir)
    main_window.current_packing_list = "DHL_Orders"
    widget = main_window.packer_mode_widget
    main_window.stacked_widget.setCurrentWidget(widget)
    main_window.heartbeat_timer.start(60000)

    shown = []
    monkeypatch.setattr(
        "gui.main_window.QMessageBox.critical", lambda *a: shown.append(a)
    )

    _heartbeat(main_window)

    assert logic.stopped and not logic.cleaned
    assert main_window.logic is logic
    assert shown == []
    assert widget.taken_over
    assert widget.bridge.takeover == {"holder": "PC-2", "list": "DHL_Orders"}
    assert not widget.scanner_input.isEnabled()
    assert not main_window.heartbeat_timer.isActive()  # it cannot report the loss twice

    widget.exit_packing_mode.emit()

    assert logic.cleaned
    assert main_window.logic is None
    assert not widget.taken_over
    assert main_window.stacked_widget.currentWidget() is main_window.session_widget
    assert (work_dir / SessionLockManager.LOCK_FILENAME).exists()  # not ours to delete
```

If `main_window.heartbeat_timer` does not exist on the fixture's window, create it in the test with `main_window.heartbeat_timer = QTimer(main_window)` (import `QTimer` from `PySide6.QtCore`) before starting it.

- [ ] **Step 2: Write the failing seam tests.** Append to `tests/test_packer_mainwindow_seam.py`:

```python
def test_leaving_packer_mode_waits_for_the_cleared_page(window, qtbot):
    """A hidden web view keeps its last painted frame and shows it on the way
    back in. So the window leaves only once the cleared page has painted, and
    the scanner is off while it waits."""
    window.show()
    qtbot.waitExposed(window)
    window.switch_to_packer_mode()
    widget = window.packer_mode_widget
    qtbot.waitUntil(
        lambda: widget.bridge.painted_revision >= widget.bridge.revision, timeout=20000
    )
    widget.display_order(
        [{"SKU": "A", "Product_Name": "A", "Quantity": 1, "Order_Number": "1002"}], []
    )

    window.switch_to_session_view()

    assert window.stacked_widget.currentWidget() is widget  # not yet
    assert not widget.scanner_input.isEnabled()
    qtbot.waitUntil(
        lambda: window.stacked_widget.currentWidget() is window.session_widget, timeout=2000
    )
    assert widget.bridge.items == []


def test_coming_back_gives_the_scanner_back(window):
    window.packer_mode_widget.pause_scanner()
    window.switch_to_packer_mode()
    assert window.packer_mode_widget.scanner_input.isEnabled()


def test_a_window_that_is_not_showing_leaves_at_once(window):
    window.switch_to_packer_mode()
    window.switch_to_session_view()
    assert window.stacked_widget.currentWidget() is window.session_widget


class OpeningLogic(StubLogic):
    """An order barcode scanned with no order open."""

    def __init__(self):
        super().__init__("ORDER_LOADED")
        self.current_order_number = None
        self.orders_data = {"1002": {"metadata": {}}}
        self.session_packing_state = {"completed_orders": [], "skipped_orders": []}

    def start_order_packing(self, text):
        self.current_order_number = "1002"
        items = [
            {"SKU": "A", "Product_Name": "A", "Quantity": 1, "Order_Number": "1002"},
            {"SKU": "B", "Product_Name": "B", "Quantity": 2, "Order_Number": "1002"},
        ]
        return items, "ORDER_LOADED"


def test_opening_an_order_says_so_in_the_band(window):
    """It used to leave the band empty until the first item scan."""
    window.logic = OpeningLogic()
    window.on_scanner_input("1002")
    feedback = window.packer_mode_widget.bridge.feedback
    assert feedback["text"] == "Order #1002 · 2 items"
    assert feedback["role"] == "info"
```

- [ ] **Step 3: Run and see them fail.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_session_lock_loss.py tests/test_packer_mainwindow_seam.py`
Expected: FAIL (the lock test on `not logic.cleaned`; the leave test on "not yet"; the band test on an empty text).

- [ ] **Step 4: Leave after the paint.** In `gui/main_window.py`, add `from shared.web_page import when_painted` to the imports, and add `order_label` to the existing `from gui.packer_bridge import ...` (if `order_label` is not already imported there).

Replace `switch_to_packer_mode` and `switch_to_session_view` with:

```python
    def switch_to_packer_mode(self):
        """Switches the view to the Packer Mode widget."""
        self.stacked_widget.setCurrentWidget(self.packer_mode_widget)
        self.packer_mode_widget.resume_scanner()
        self.packer_mode_widget.set_focus_to_scanner()

    def switch_to_session_view(self):
        """Switches the view back to the main session widget (tabbed interface)."""
        if self.packer_mode_widget.taken_over:
            # Another PC holds the list (frame 6j): there is no session left
            # here to come back to.
            self._teardown_session()
            return
        if self.logic:
            self.logic.clear_current_order()
        self.packer_mode_widget.clear_screen()
        self._show_session_view()
        self._rebuild_order_tree_if_stale()

    def _show_session_view(self):
        """Leave Packer Mode once its page has painted what it was last sent.

        A hidden QWebEngineView keeps its last painted frame and shows it when
        it comes back, until a new one is ready. So the frame it keeps must be
        the cleared one: callers clear the page first, and this waits for the
        page's report (150 ms at most). The scanner is paused meanwhile, so a
        scan cannot open an order on a page about to be covered;
        switch_to_packer_mode gives it back.
        """
        widget = self.packer_mode_widget

        def switch():
            self.stacked_widget.setCurrentWidget(self.session_widget)

        if self.stacked_widget.currentWidget() is widget and widget.isVisible():
            widget.pause_scanner()
            when_painted(widget.bridge, switch)
        else:
            switch()
```

In `_teardown_session`, replace

```python
        # Return user to session view (avoids leaving a blank packer mode screen)
        if hasattr(self, "stacked_widget") and hasattr(self, "session_widget"):
            self.stacked_widget.setCurrentWidget(self.session_widget)
```

with

```python
        # Return user to session view (avoids leaving a blank packer mode screen)
        if hasattr(self, "stacked_widget") and hasattr(self, "session_widget"):
            self._show_session_view()
```

- [ ] **Step 5: Show the takeover in the page.** Replace `_on_lock_lost` with:

```python
    def _on_lock_lost(self, work_dir: Path):
        """Another PC holds this list's lock: stop writing, then leave it.

        In Packer Mode the page says so and blocks (frame 6j), and the session
        is torn down when the packer exits. On any other page: teardown, then
        a message box, as before.
        """
        _locked, info = self.lock_manager.is_locked(work_dir)
        holder = (info or {}).get("locked_by") or "Another PC"
        list_name = getattr(self, "current_packing_list", None) or work_dir.name
        logger.error(f"Session lock lost to {holder}: {work_dir}")
        self.logic.stop_writing()
        if self._progress_publisher is not None:
            self._progress_publisher.stop()
        if self.stacked_widget.currentWidget() is self.packer_mode_widget:
            # The lock is gone and stays gone: nothing left to renew, and a
            # second report must not land on the panel.
            if hasattr(self, "heartbeat_timer"):
                self.heartbeat_timer.stop()
            self.packer_mode_widget.show_takeover(holder, list_name)
            return
        self._teardown_session()
        QMessageBox.critical(
            self,
            "This list is open on another PC",
            f"{holder} has taken over {list_name}. This PC has stopped packing it "
            "so the two don't overwrite each other's progress. Orders packed here "
            "up to now are saved.",
        )
```

- [ ] **Step 6: Say which order opened.** In `on_scanner_input`, in the `if status == "ORDER_LOADED":` branch, directly after the `self.packer_mode_widget.display_order(...)` call, add:

```python
                count = len(items)
                self.packer_mode_widget.show_notification(
                    f"Order {order_label(order_number_from_scan)} · {count} "
                    f"{'item' if count == 1 else 'items'}",
                    "status_info",
                )
```

- [ ] **Step 7: Run the suite and lint.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` then `.venv/bin/ruff check . --exclude shared`
Expected: all pass. A test elsewhere that shows the window, leaves Packer Mode and asserts the page changed in the same breath now needs `qtbot.waitUntil(lambda: window.stacked_widget.currentWidget() is window.session_widget, timeout=2000)` before that assertion.

- [ ] **Step 8: Commit** with the message `feat: the takeover blocks in the page; Packer Mode leaves after its cleared page has painted`.

---

### Task 6: Renders, glossary, and the last checks

**Files:**
- Create: `scripts/render_packer_mode.py`, `docs/design/ui-refresh/renders/phase2/*.png`
- Modify: `CONTEXT.md`

**Interfaces:**
- Consumes: `PackerModeWidget`'s public methods and `gui.packer_bridge.session_end_payload(packed, total, skipped, items, seconds)`.

- [ ] **Step 1: Write `scripts/render_packer_mode.py`.** The whole file:

```python
"""Offscreen renders of Packer Mode, mockup frames 6a-6j, in both themes.

    .venv/bin/python scripts/render_packer_mode.py [output dir]

Writes <frame>-<theme>.png at 1366x768 and 6b-<theme>-1920.png at 1920x1080,
by default into docs/design/ui-refresh/renders/phase2/. It drives a
PackerModeWidget alone through its public methods: no MainWindow, no server,
and its own QSettings, so it touches neither the file server nor this PC's
saved theme.

The scan flash pulses and clears in the app. Here it is held lit, so the
frames that show a scan show its colour.

Offscreen Qt uses a fallback font for the Qt bar: glyph widths differ a
little from Windows.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

DEFAULT_OUT = ROOT / "docs" / "design" / "ui-refresh" / "renders" / "phase2"

# The mockup's order, with SPF-50 at 8 units so one row offers Force confirm.
LINES = [
    ("LIP-RED", "Lip balm, red", 2),
    ("CRM-50ML", "Day cream 50 ml", 3),
    ("CLN-200", "Gel cleanser 200 ml", 1),
    ("SPF-50", "Sunscreen SPF 50", 8),
    ("SER-30ML", "Vitamin C serum 30 ml", 1),
]
ITEMS = [
    {"SKU": sku, "Product_Name": name, "Quantity": qty, "Order_Number": "10407"}
    for sku, name, qty in LINES
]
METADATA = {
    "shipping_provider": "DPD",
    "tags": ["Gift wrap"],
    "notes": "Add a sample sachet — customer asked by phone",
    "system_note": "Repeat",
}
HOLD_FLASH = (
    "var s = document.createElement('style');"
    "s.textContent = '.doc-main[data-flash] .pm-flash"
    "{animation: none; border-color: var(--flash);}';"
    "document.head.appendChild(s);"
)
CLEAR_FLASH = "delete document.getElementById('doc-main').dataset.flash;"


def packed_state(packed):
    return [
        {"row": row, "packed": count, "required": LINES[row][2]}
        for row, count in enumerate(packed)
    ]


def main(argv: list[str]) -> int:
    out = Path(argv[0]) if argv else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as raw:
        # Before any QSettings is made: keep this PC's saved theme. Both
        # formats, as tests/conftest.py does.
        for fmt in (QSettings.NativeFormat, QSettings.IniFormat):
            QSettings.setPath(fmt, QSettings.UserScope, str(Path(raw) / "settings"))

        app = QApplication.instance() or QApplication(sys.argv[:1])
        from gui.packer_bridge import session_end_payload
        from gui.packer_mode_widget import PackerModeWidget
        from gui.theme import apply_theme, load_saved_theme

        load_saved_theme(app)
        widget = PackerModeWidget()
        widget.resize(1366, 768)
        widget.show()
        bridge = widget.bridge

        def settle() -> None:
            deadline = time.monotonic() + 20
            while bridge.painted_revision < bridge.revision:
                if time.monotonic() > deadline:
                    raise RuntimeError("the page never painted; is QtWebEngine working?")
                app.processEvents()
                time.sleep(0.01)
            for _ in range(10):
                app.processEvents()
                time.sleep(0.02)

        def js(code: str) -> None:
            widget.document_view.page().runJavaScript(code)

        def shoot(name: str, width: int = 1366, height: int = 768) -> None:
            for theme in ("light", "dark"):
                apply_theme(app, theme)
                widget.resize(width, height)
                settle()
                target = out / f"{name.format(theme=theme)}.png"
                if not widget.grab().save(str(target)):
                    raise OSError(f"could not write {target}")
                print(target)

        def fresh(orders_done: int = 38) -> None:
            """A session in progress, waiting for an order."""
            widget.reset_for_new_session()
            js(CLEAR_FLASH)
            widget.update_session_progress(orders_done, 120)
            for number in range(10400, 10407):
                widget.add_order_to_history(str(number), "[SKIPPED]" if number == 10403 else "")

        def order(packed=(2, 1, 0, 0, 0)) -> None:
            fresh()
            widget.display_order(ITEMS, packed_state(packed), metadata=METADATA, sku_map={})
            widget.show_notification("Order #10407 · 5 items", "status_info")

        def scanned(row: int, count: int, text: str, raw_scan: str) -> None:
            widget.update_item_row(row, count, count >= LINES[row][2])
            widget.show_notification(text, "status_success")
            widget.update_raw_scan_display(raw_scan)
            widget.flash_scan("green")

        settle()
        js(HOLD_FLASH)

        fresh()
        shoot("6a-{theme}")

        order()
        shoot("6b-{theme}")
        shoot("6b-{theme}-1920", 1920, 1080)

        order()
        scanned(1, 2, "CRM-50ML confirmed — 2 of 3 packed", "CRM-50ML")
        shoot("6c-{theme}")

        order()
        widget.show_extras_panel({"MSCBLK": 1})
        widget.show_notification("Extra item scanned — keep it or remove it", "status_warning")
        widget.update_raw_scan_display("MSC-BLK")
        widget.flash_scan("orange")
        shoot("6d-{theme}")

        order()
        widget.show_unknown_scans(["4006381333931"])
        widget.show_notification(
            "Unknown SKU 4006381333931 — scan again or map it", "status_danger"
        )
        widget.update_raw_scan_display("4006381333931")
        widget.flash_scan("red")
        shoot("6e-{theme}")

        order()
        bridge.forceItem(3)
        shoot("6f-{theme}")

        order(packed=(2, 3, 1, 8, 0))
        scanned(4, 1, "Order #10407 packed. Scan the next order.", "SER-30ML")
        widget.clear_screen_later(600_000)
        shoot("6g-{theme}")

        fresh(orders_done=120)
        widget.show_session_complete(session_end_payload(120, 120, 0, 1290, 11520))
        shoot("6h-{theme}")

        order()
        scanned(1, 2, "CRM-50ML confirmed — 2 of 3 packed", "CRM-50ML")
        widget.set_unsaved(True)
        shoot("6i-{theme}")

        order()
        widget.show_takeover("Georgi Dimitrov", "acme-packing-07-10")
        shoot("6j-{theme}")

        widget.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 2: Run it.**

Run: `.venv/bin/python scripts/render_packer_mode.py`
Expected: 22 paths printed (ten frames in two themes, plus `6b-light-1920.png` and `6b-dark-1920.png`).

- [ ] **Step 3: Look at every PNG beside its mockup frame.** Open each with the Read tool. To see the mockup frames, open `docs/design/ui-refresh/mockups/Packer Screens.html` in Chrome, or read the unpacked template. Check, per frame:

| Frame | Must show |
|---|---|
| 6a | info band "Scan an order barcode"; "No order open" in the card; "No order" in the bar; Skip order disabled; "Ready to scan" with a green dot |
| 6b | order card with DPD, Gift wrap, the note and Repeat; five 64px rows; "#10407" large in the bar; Force confirm only on SPF-50, the other rows keeping the gap; the buttons in one column down the list |
| 6c | solid success band; "Scanned CRM-50ML" at the right; the CRM row green with a left bar; a 10px green frame on the main column only, not over the side column |
| 6d | warning band and frame; "Extra items scanned" strip with MSCBLK, "× 1", Extra, Keep, Remove |
| 6e | danger band and frame; the No match row with the barcode and Map barcode… |
| 6f | scrim over the whole page; the question with Cancel and Force confirm; "Scanner disabled" in the bar |
| 6g | every row quiet, SER-30ML still green; "Scanner disabled" |
| 6h | the centred panel; side column still there; "Session complete" in the bar |
| 6i | the danger banner above the order card; the band still green |
| 6j | scrim and the danger-edged panel with one button |

Both themes must be legible: band text against its fill, the neutral badge, the disabled buttons. At 1920 the product column widens and nothing else moves. If a PNG's page area is blank, replace `widget.grab()` with a grab after two more `settle()` calls; if it is still blank, stop and report it rather than committing empty renders. Fix what is wrong in `gui/web/` or `gui/packer_mode_widget.py`, re-run the script, and re-run the suite. If the four row buttons do not fit the 404px column in the bundled font, widen the last track of `--pm-cols` to fit and add the change to spec section 9.

- [ ] **Step 4: Update `CONTEXT.md`.** Replace these entries (keep the bold terms):

```markdown
**Order document** — the web-rendered part of Packer Mode: the order card, the feedback band, the SKU list with its extras and unmatched scans, the side column (session progress, history, items by SKU, summary), the unsaved banner, and the two panels that take the page over (the Force confirm question, and "This list is open on another PC").

**Feedback band** — the order document's outcome row: what the last scan did, as one large sentence on a solid fill in its status colour, with the raw scanned text beside it. The unsaved warning is a banner above it, not part of it.

**Scan flash** — the brief colour pulse on a 10px frame around the order document's main column that makes a scan's outcome visible from across the floor.

**Force confirm** — marking the rest of an item's quantity packed at once, without a scan (*force_confirmed*; shown as *forced*). Offered only on lines over 5 units. The order document asks first, with the scanner off until the packer answers; it cannot be undone. The summary's `total_manual_confirms` counts both.
```

Add after **Floor density**:

```markdown
**Floor web kit** — `gui/web/floor.css`: floor density for web pages, loaded between `shared/web/kit.css` and a page's own sheet. It holds sizes and shared parts (buttons, badges, the banner, the scrim and dialog), never a page's layout.
```

- [ ] **Step 5: Final checks.**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`, then `.venv/bin/ruff check . --exclude shared`, then `graphify update .`
Expected: all tests pass, lint clean.

Run: `rg -n "<input|<textarea|<select|contenteditable" gui/web`
Expected: only the comment line in `packer.html` that forbids them.

Run: `/usr/bin/git status --short shared`
Expected: no output.

- [ ] **Step 6: Commit** `scripts/render_packer_mode.py`, `docs/design/ui-refresh/renders/phase2/`, `CONTEXT.md`, any `graphify-out/` changes and any spec edit, with the message `docs: Packer Mode renders for frames 6a-6j, and the glossary`.

The PR description (Stage C) embeds the renders, copies spec section 9 (departures) and section 8 ("For shared/"), and tells the owner to check on a Windows PC with a real scanner: scan after clicking in the page, scan while the Force confirm question is open (nothing happens), and exit and re-enter Packer Mode (no old order flashes).
