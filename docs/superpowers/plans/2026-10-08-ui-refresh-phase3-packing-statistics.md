# UI refresh phase 3 (Packing and Statistics on the web tier) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Draw Packing and Statistics as one web document to mockup frames 3a to 3g and 4a to 4c, and delete the Qt order tree, its state panels and `gui/statistics_widget.py`.

**Architecture:** One `QWebEngineView` holds `gui/web/app.html`, the *app document*, and talks to `AppBridge(PageBridge)` through named properties (`page`, `covered`, `shell`, `session`, `packing`, `statistics`). Pure payload functions in `gui/app_bridge.py` decide all data; the page keeps only which rows were toggled and the SKU sort. `AppPages` is a two-page stack (the view, the Qt Session Browser) that speaks the `QTabWidget` calls `MainWindow.session_tabs` already receives. `MainWindow` pushes state only while the shell is showing.

**Tech Stack:** Python 3.14, PySide6 (Qt widgets, QtWebEngine, QWebChannel), pandas (already used by `session_stats`), plain HTML/CSS/JS with no build step, pytest with pytest-qt. No new dependency.

**Spec:** `docs/superpowers/specs/2026-10-08-ui-refresh-phase3-packing-statistics-design.md`. Read it first. ADRs: `docs/adr/0001-packer-mode-on-the-web-tier.md`, `docs/adr/0002-every-screen-on-the-web-tier.md`, `docs/adr/0003-the-shells-pages-are-one-web-document.md`. Mockup: `docs/design/ui-refresh/mockups/Packer App.html` (unpack it as `docs/design/ui-refresh/mockups/README.md` describes, into a folder outside the repo; the Packing and Statistics markup is lines 134 to 316 of the unpacked `template.html`, the state logic is `renderVals()`).

## Global Constraints

- **Never edit a file under `shared/`.** A hook blocks it and CI diffs the folder. Read `shared/web_page.py`, `shared/web/kit.css`, `shared/web/page.js`; do not change them.
- **Web assets** (`gui/web/*`): colours only as `var(--token)` from `theme_css_vars()` (token `status_success_dot` is `--status-success-dot`). No hex, no colour names, no `px` font sizes (`pt` only, and only through `var(--type-*-size)`), no `transition`, `transform`, `opacity`, gradients. `box-shadow` only as `var(--card-shadow)`, `var(--overlay-shadow)` or `none`. `tests/test_style_literals_guard.py` enforces this.
- **Type scale on the floor profile:** `--type-caption-size` 10pt, `--type-body-size` 12pt, `--type-heading-size` 14pt, `--type-display-size` 17pt, `--type-display-xl-size` 28pt. Every size in the mockup is one of these.
- **Text into the page goes through `textContent`,** never `innerHTML`: product names and order numbers come from files.
- **Qt code:** no colour literals; read tokens from `gui.theme.current_tokens()`.
- **Copy, verbatim:** "Choose a client to begin", "Sessions, packing lists and SKU mapping all belong to one client.", "Choose a client", "No session open", "Open a session to see its orders here.", "Open session", "No packing data yet", "Start a session from the Packing tab to see numbers here.", "Go to Packing", "Start packing", "End session", "Active", "Working · step 2 of 3", "Taking the packing list", "Reading saved progress", "Reading the packing list", "Packing list could not be loaded", "Saved progress could not be read", "Session could not be opened", "Retry", "Close", "Orders complete", "Items packed", "Orders skipped", "still Not started", "none", "Progress", "All orders packed", "Packing list complete", "Clear filter", "No orders match", "Order / Item", "Product", "Quantity", "Status", "Courier", "In progress", "Not started", "Packed", "Skipped", "Pending", "Partial", "Complete", "Statistics", "Orders", "Completed", "Items", "Unique SKUs", "By courier", "SKU summary", "SKU", "Total qty", "Left", "All packed", "Every order is packed", "Dismiss". The middle dot is `·`.
- **Sizes:** page padding 20px 24px, gap 16px; order row 52px; item row 44px; table head and group row 40px; SKU row 40px; SKU head 44px; badges 28px (floor.css); controls 44px; progress track 14px; courier track 24px; state card 520px.
- **Git:** `/usr/bin/git`, one plain git command per Bash call (no `&&`, `;`, `$VAR` paths). Commit with `/usr/bin/git commit -F <absolute path to a message file>`; write the message file with the Write tool. Never commit to `main`. Each commit message ends with the attribution lines your session gives you.
- **Tests:** run with `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q <path>`. If a hook refuses that, run the whole suite: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`. Write test files with Write/Edit, never with shell redirection. If `.venv` is missing in the worktree: `ln -s /home/gloopy/Desktop/Projects/packing-tool/.venv .venv`.
- **Lint:** `.venv/bin/ruff check . --exclude shared` must pass before each commit.
- **QtWebEngine in tests:** `runJavaScript` cannot return a JS array; wrap every result in `JSON.stringify` (the `_eval` helper below does). Never mark a Chromium test skip.
- After the last code change, run `graphify update .` (CLAUDE.md).
- Departures from the mockup are the 17 in spec section 11. If you make another, add it to that table in the same commit.

## Review Focus

Inputs the spec implies that are most likely to bite a packer. Each has a test in the task named.

1. **A packing list with no orders** (`load_packing_list_json` returns 0; `orders_data` is `{}`, `processed_df` is `None`). The pages show zeros and no banner, and nothing divides by zero (Task 2, `test_an_empty_list_is_all_zeros_and_not_complete`).
2. **A product name or SKU that is markup** (`<img src=x>`). It is shown as text and creates no element (Task 4, `test_markup_in_a_product_name_is_text`).
3. **A filter of only spaces or only `#`.** It is no filter: every order is listed and the filter line is not drawn (Task 2, `test_a_blank_or_hash_only_query_is_no_filter`).
4. **A restored state with a non-dict item entry, or a non-numeric quantity.** The payload skips the entry and still builds (Task 2, `test_a_malformed_state_entry_does_not_break_the_payload`).
5. **A worker step that arrives after the start has already failed.** 3c stays; the late step does not put 3b back (Task 9, `test_a_late_step_does_not_replace_a_failure`).

## File map

| File | Responsibility | Task |
|---|---|---|
| `packing_tool/exceptions.py` | adds `PackingListInvalidError` | 1 |
| `packing_tool/packer_logic.py` | raises it at the two "missing" checks | 1 |
| `packing_tool/session_stats.py` | `courier_totals` returns `done` | 1 |
| `gui/workers.py` | `SessionStartWorker.step` | 1 |
| `gui/app_bridge.py` (new) | pure payloads, `AppBridge`, `mount_app_page` | 2, 3 |
| `gui/web/app.html`, `app.css`, `app.js` (new) | the app document | 3, 4, 5 |
| `gui/web/floor.css` | toast, state card, strip, track, table rows | 3 |
| `gui/app_pages.py` (new) | `AppPages`: the view and the Session Browser as one stack | 6 |
| `gui/command_bar.py` | `set_complete` | 7 |
| `gui/main_window.py` | pushes state, wires slots, loses the Qt tree | 8, 9, 10 |
| `gui/statistics_widget.py` | deleted | 8 |
| `scripts/render_app_pages.py` (new), `scripts/render_shell.py` | renders | 11 |
| `CONTEXT.md`, `.github/workflows/build-release.yml` | docs, bundle check | 11 |

---

### Task 1: Backend seams (the invalid-list error, courier `done`, worker steps)

**Files:**
- Modify: `packing_tool/exceptions.py` (append), `packing_tool/packer_logic.py:23` and the two raises near lines 1525 and 1566, `packing_tool/session_stats.py` (`courier_totals`), `gui/workers.py` (`SessionStartWorker`)
- Test: `tests/test_packing_list_invalid.py` (new), `tests/test_session_stats.py`, `tests/test_workers_steps.py` (new)

**Interfaces:**
- Produces: `PackingListInvalidError(message, missing: list[str], found: list[str], kind: str)` with attributes `.missing`, `.found`, `.kind` (`"field"` or `"column"`), a `ValueError`. `courier_totals(df, completed_orders=()) -> list[{"courier": str, "orders": int, "done": int}]`. `SessionStartWorker.step: Signal(int)`, emitting 2 then 3.

- [ ] **Step 1: Write the failing tests**

`tests/test_packing_list_invalid.py`:

```python
"""A bad packing list says what is missing and what was found (spec section 5)."""

import json

import pytest

from packing_tool.exceptions import PackingListInvalidError


def test_an_order_with_no_courier_says_what_is_missing_and_what_was_found(
    session_factory, packer_logic_factory
):
    orders = [("#1", "DHL", [{"sku": "A", "quantity": 1, "product_name": "A"}])]
    _session, work_dir, list_path = session_factory(client_id="M", orders=orders)
    data = json.loads(list_path.read_text(encoding="utf-8"))
    del data["orders"][0]["courier"]
    list_path.write_text(json.dumps(data), encoding="utf-8")
    logic = packer_logic_factory("M", work_dir)

    with pytest.raises(PackingListInvalidError) as caught:
        logic.load_packing_list_json(list_path)

    assert caught.value.missing == ["courier"]
    assert caught.value.found == ["items", "order_number"]
    assert caught.value.kind == "field"
    # Still what callers have always caught, with the text they matched.
    assert isinstance(caught.value, ValueError)
    assert "Missing required fields in order data" in str(caught.value)
```

`tests/test_workers_steps.py`:

```python
"""SessionStartWorker names its two steps (spec section 5, frame 3b)."""

from gui.workers import SessionStartWorker


def test_the_start_worker_emits_step_2_then_3(profile_manager, session_factory, qtbot):
    orders = [("#1", "DHL", [{"sku": "A", "quantity": 1, "product_name": "A"}])]
    _session, work_dir, list_path = session_factory(client_id="M", orders=orders)
    worker = SessionStartWorker("M", profile_manager, work_dir, list_path)
    steps = []
    worker.step.connect(steps.append)
    worker.start()
    try:
        assert worker.wait(20000)
        assert worker.error is None
        qtbot.waitUntil(lambda: steps == [2, 3], timeout=5000)
    finally:
        if worker.logic is not None:
            worker.logic.close()
```

In `tests/test_session_stats.py`, replace `test_courier_totals_count_orders_per_courier` with:

```python
def test_courier_totals_count_orders_per_courier():
    assert courier_totals(_df()) == [
        {"courier": "DPD", "orders": 1, "done": 0},
        {"courier": "GLS", "orders": 1, "done": 0},
    ]


def test_courier_totals_count_the_completed_orders():
    df = _df()
    dpd_order = df[df["Courier"] == "DPD"]["Order_Number"].iloc[0]
    totals = {row["courier"]: row for row in courier_totals(df, [dpd_order])}
    assert totals["DPD"]["done"] == 1
    assert totals["GLS"]["done"] == 0
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_packing_list_invalid.py tests/test_workers_steps.py tests/test_session_stats.py`
Expected: FAIL (`ImportError: cannot import name 'PackingListInvalidError'`, no attribute `step`, and the `done` key missing).

- [ ] **Step 3: Implement**

Append to `packing_tool/exceptions.py`:

```python
class PackingListInvalidError(ValueError):
    """A packing list lacks something every order needs.

    A ValueError, unlike the rest of this module: load_packing_list_json has
    always raised ValueError here, and callers and tests catch that.

    Attributes:
        missing: the field or column names that are absent.
        found: the names that are there.
        kind: "field" (an order's JSON key) or "column".
    """

    def __init__(self, message: str, missing, found, kind: str):
        super().__init__(message)
        self.missing = list(missing)
        self.found = list(found)
        self.kind = kind
```

In `packing_tool/packer_logic.py` change the import on line 23 to:

```python
from packing_tool.exceptions import PackingListInvalidError, PackingStateUnreadableError
```

In `load_packing_list_json`, the order-fields check becomes (keep `error_msg` and the `logger.error` line as they are):

```python
                raise PackingListInvalidError(
                    error_msg, missing_fields, sorted(order), "field"
                )
```

and the columns check becomes:

```python
            raise PackingListInvalidError(
                error_msg, missing_cols, list(df.columns), "column"
            )
```

In `packing_tool/session_stats.py` replace `courier_totals` with:

```python
def courier_totals(
    df: pd.DataFrame, completed_orders=()
) -> list[dict[str, Any]]:
    """Orders per courier and how many of them are packed, by courier name."""
    if df is None or df.empty or "Courier" not in df.columns:
        return []

    done = set(completed_orders or ())
    grouped = df.groupby("Courier")["Order_Number"].unique()
    return [
        {
            "courier": courier,
            "orders": len(numbers),
            "done": sum(1 for number in numbers if number in done),
        }
        for courier, numbers in grouped.items()
    ]
```

In `gui/workers.py` change the import to `from PySide6.QtCore import QThread, Signal`, add to `SessionStartWorker`, directly under its docstring:

```python
    # 2: reading saved progress. 3: reading the packing list. Step 1, the
    # lock, is the caller's (it can ask a question, so it is on the UI thread).
    step = Signal(int)
```

and in `run`, emit before each phase:

```python
            self.step.emit(2)
            logic = PackerLogic(
                client_id=self._client_id,
                profile_manager=self._profile_manager,
                work_dir=str(self._work_dir),
            )
            self.step.emit(3)
            order_count, list_name = logic.load_packing_list_json(str(self._packing_list_path))
```

- [ ] **Step 4: Run the tests and the suite**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: PASS. `gui/statistics_widget.py` still calls `courier_totals(df)` and reads `row["orders"]`, which still works.

- [ ] **Step 5: Commit** (`feat: packing-list error carries what is missing; courier done; start worker steps`)

---

### Task 2: Pure payloads in `gui/app_bridge.py`

**Files:**
- Create: `gui/app_bridge.py`
- Test: `tests/test_app_payload.py` (new)

**Interfaces:**
- Consumes: `packing_tool.session_stats.session_totals`, `courier_totals(df, completed)`, `sku_summary`; `gui.packer_bridge.order_label`, `_int`; `PackingListInvalidError`, `PackingStateUnreadableError`.
- Produces:
  - `STEPS: tuple[str, str, str]`
  - `packing_payload(orders_data: dict, state: dict, query: str = "") -> dict` with keys `totals` (`orders`, `done`, `units`, `packed`, `skipped`, `in_progress`, `pct`, `complete`), `query` (trimmed, as typed), `hits` (int), `groups` (list of `{"key", "label", "count", "note", "orders"}`; an order is `{"number", "label", "summary", "packed", "units", "status", "courier", "skipped", "open", "items"}`; an item is `{"sku", "product", "packed", "required", "state", "hit"}`).
  - `statistics_payload(df, state: dict) -> dict` with keys `orders`, `completed`, `items`, `unique_skus`, `pct`, `in_progress`, `packed`, `fully_packed`, `couriers` (`{"name", "done", "total"}`), `skus` (`{"sku", "product", "total", "packed", "left", "state"}`).
  - `session_payload(state="none", *, list_name="", session_id="", step=0, title="", text="", orders=0, couriers=(), complete=False) -> dict` with keys `state`, `list`, `id`, `step`, `stepName`, `title`, `text`, `meta`, `complete`.
  - `start_failure(error: Exception, list_name: str) -> tuple[str, str]` (title, sentence).

- [ ] **Step 1: Write the failing tests**

`tests/test_app_payload.py`:

```python
"""The app document's payloads: pure, so the numbers need no browser."""

import json

import pandas as pd

from gui.app_bridge import (
    STEPS,
    packing_payload,
    session_payload,
    start_failure,
    statistics_payload,
)
from packing_tool.exceptions import PackingListInvalidError, PackingStateUnreadableError


def _line(sku, name, qty, courier="DHL"):
    return {"SKU": sku, "Product_Name": name, "Quantity": str(qty), "Courier": courier}


ORDERS = {
    "#10": {"items": [_line("LIP-RED", "Lip balm, red", 2), _line("CRM-50", "Day cream", 1)]},
    "#11": {"items": [_line("LST-07", "Lipstick, shade 07", 1, "DPD")]},
    "#12": {"items": [_line("LIP-RED", "Lip balm, red", 1, "DPD")]},
    "#13": {"items": [_line("SPF-50", "Sunscreen", 3)]},
}
STATE = {
    "completed_orders": ["#12"],
    "skipped_orders": ["#13"],
    "in_progress": {
        "#10": [
            {"original_sku": "LIP-RED", "packed": 2, "required": 2, "row": 0},
            {"original_sku": "CRM-50", "packed": 0, "required": 1, "row": 1},
        ],
        "#13": [{"original_sku": "SPF-50", "packed": 1, "required": 3, "row": 0}],
    },
}


def _orders(payload, key):
    return [g for g in payload["groups"] if g["key"] == key][0]["orders"]


def test_totals_count_orders_units_and_what_is_packed():
    totals = packing_payload(ORDERS, STATE)["totals"]
    assert totals == {
        "orders": 4, "done": 1, "units": 8, "packed": 4, "skipped": 1,
        "in_progress": 1, "pct": 25, "complete": False,
    }


def test_groups_come_in_progress_then_not_started_then_packed():
    payload = packing_payload(ORDERS, STATE)
    assert [g["key"] for g in payload["groups"]] == ["in_progress", "not_started", "packed"]
    assert [g["label"] for g in payload["groups"]] == ["In progress", "Not started", "Packed"]
    assert [g["count"] for g in payload["groups"]] == [1, 2, 1]


def test_a_skipped_order_is_not_started_even_with_scans_and_keeps_its_count():
    payload = packing_payload(ORDERS, STATE)
    not_started = _orders(payload, "not_started")
    skipped = [o for o in not_started if o["number"] == "#13"][0]
    assert skipped["skipped"] is True
    assert skipped["status"] == "not_started"
    assert (skipped["packed"], skipped["units"]) == (1, 3)
    assert [g for g in payload["groups"] if g["key"] == "not_started"][0]["note"] == "1 skipped"


def test_an_order_row_carries_its_summary_courier_and_items():
    order = _orders(packing_payload(ORDERS, STATE), "in_progress")[0]
    assert order["label"] == "#10"
    assert order["summary"] == "2 items · Lip balm, red, Day cream"
    assert order["courier"] == "DHL"
    assert (order["packed"], order["units"]) == (2, 3)
    assert [(i["sku"], i["packed"], i["required"], i["state"]) for i in order["items"]] == [
        ("LIP-RED", 2, 2, "complete"), ("CRM-50", 0, 1, "pending"),
    ]


def test_a_packed_orders_items_are_all_complete():
    order = _orders(packing_payload(ORDERS, STATE), "packed")[0]
    assert [(i["packed"], i["state"]) for i in order["items"]] == [(1, "complete")]


def test_only_in_progress_orders_are_open_by_default():
    payload = packing_payload(ORDERS, STATE)
    assert all(o["open"] for o in _orders(payload, "in_progress"))
    assert not any(o["open"] for o in _orders(payload, "not_started"))
    assert not any(o["open"] for o in _orders(payload, "packed"))


def test_the_filter_matches_number_sku_and_product_in_any_case():
    by_number = packing_payload(ORDERS, STATE, "#11")
    assert by_number["hits"] == 1 and _orders(by_number, "not_started")[0]["number"] == "#11"

    by_sku = packing_payload(ORDERS, STATE, "lip-red")
    assert by_sku["hits"] == 2
    assert by_sku["query"] == "lip-red"

    by_product = packing_payload(ORDERS, STATE, "SUNSCREEN")
    assert by_product["hits"] == 1


def test_matching_orders_open_and_the_hit_item_is_marked():
    payload = packing_payload(ORDERS, STATE, "LIP-RED")
    listed = [o for g in payload["groups"] for o in g["orders"]]
    assert all(o["open"] for o in listed)
    order_10 = [o for o in listed if o["number"] == "#10"][0]
    assert [i["hit"] for i in order_10["items"]] == [True, False]


def test_an_order_number_match_marks_no_item():
    payload = packing_payload(ORDERS, STATE, "11")
    order = _orders(payload, "not_started")[0]
    assert [i["hit"] for i in order["items"]] == [False]


def test_no_match_keeps_the_totals_and_lists_nothing():
    payload = packing_payload(ORDERS, STATE, "99999")
    assert payload["hits"] == 0
    assert payload["groups"] == []
    assert payload["query"] == "99999"
    assert payload["totals"]["orders"] == 4


def test_a_blank_or_hash_only_query_is_no_filter():
    for query in ("   ", "#", " # "):
        payload = packing_payload(ORDERS, STATE, query)
        assert payload["hits"] == 4
        assert payload["query"] == ""
        assert not any(i["hit"] for g in payload["groups"] for o in g["orders"] for i in o["items"])


def test_complete_means_every_order_packed_not_packed_or_skipped():
    state = {"completed_orders": ["#10", "#11", "#12"], "skipped_orders": ["#13"], "in_progress": {}}
    assert packing_payload(ORDERS, state)["totals"]["complete"] is False
    state["completed_orders"].append("#13")
    state["skipped_orders"] = []
    totals = packing_payload(ORDERS, state)["totals"]
    assert totals["complete"] is True and totals["pct"] == 100


def test_an_empty_list_is_all_zeros_and_not_complete():
    payload = packing_payload({}, {})
    assert payload["totals"] == {
        "orders": 0, "done": 0, "units": 0, "packed": 0, "skipped": 0,
        "in_progress": 0, "pct": 0, "complete": False,
    }
    assert payload["groups"] == []
    stats = statistics_payload(None, {})
    assert stats["orders"] == 0 and stats["pct"] == 0 and stats["skus"] == []


def test_a_malformed_state_entry_does_not_break_the_payload():
    orders = {
        7: {"items": [_line("A", "Alpha", "many")]},  # an int order number, a bad quantity
        "#8": {},  # no items at all
    }
    state = {"in_progress": {7: ["not a dict", {"row": 0, "packed": 1}], "#8": "nope"}}
    payload = packing_payload(orders, state)
    numbers = [o["number"] for g in payload["groups"] for o in g["orders"]]
    assert sorted(numbers) == ["#8", "7"]
    json.dumps(payload)  # everything in it can cross the channel


def _df():
    rows = []
    for number, order in ORDERS.items():
        for item in order["items"]:
            rows.append({"Order_Number": number, **item})
    return pd.DataFrame(rows)


def test_statistics_counts_and_notes_inputs():
    stats = statistics_payload(_df(), STATE)
    assert (stats["orders"], stats["completed"], stats["items"], stats["unique_skus"]) == (4, 1, 8, 4)
    assert stats["pct"] == 25
    assert stats["in_progress"] == 1  # #13 is skipped, so only #10
    assert stats["packed"] == 4       # 2 of #10, 1 of #12, 1 of #13
    assert stats["fully_packed"] == 1  # LIP-RED: 3 of 3


def test_statistics_couriers_carry_done_and_total():
    stats = statistics_payload(_df(), STATE)
    assert stats["couriers"] == [
        {"name": "DHL", "done": 0, "total": 2},
        {"name": "DPD", "done": 1, "total": 2},
    ]


def test_statistics_skus_carry_left_and_state():
    skus = {row["sku"]: row for row in statistics_payload(_df(), STATE)["skus"]}
    assert skus["LIP-RED"] == {
        "sku": "LIP-RED", "product": "Lip balm, red", "total": 3, "packed": 3,
        "left": 0, "state": "packed",
    }
    assert (skus["SPF-50"]["left"], skus["SPF-50"]["state"]) == (2, "partial")
    assert (skus["LST-07"]["left"], skus["LST-07"]["state"]) == (1, "pending")


def test_session_payload_none_and_opening():
    assert session_payload()["state"] == "none"
    opening = session_payload("opening", list_name="DHL_Orders", session_id="2026-10-07_1", step=2)
    assert opening["step"] == 2
    assert opening["stepName"] == STEPS[1] == "Reading saved progress"
    assert (opening["list"], opening["id"]) == ("DHL_Orders", "2026-10-07_1")


def test_session_payload_open_writes_the_meta():
    one = session_payload("open", orders=1, couriers=["DHL"])
    assert one["meta"] == "1 order · DHL"
    many = session_payload("open", orders=120, couriers=["DHL", "DPD", "GLS", "Speedy", "UPS"])
    assert many["meta"] == "120 orders · DHL, DPD, GLS +2"
    assert session_payload("open", orders=3)["meta"] == "3 orders"


def test_start_failure_names_the_missing_field_and_what_was_found():
    error = PackingListInvalidError("x", ["courier"], ["items", "order_number"], "field")
    assert start_failure(error, "DHL_Orders") == (
        "Packing list could not be loaded",
        "DHL_Orders has an order with no courier. Found: items, order_number.",
    )


def test_start_failure_names_a_missing_column():
    error = PackingListInvalidError("x", ["Quantity"], ["Order_Number", "SKU"], "column")
    assert start_failure(error, "DHL_Orders")[1] == (
        "DHL_Orders has no Quantity column. Found: Order_Number, SKU."
    )


def test_start_failure_for_the_other_errors():
    assert start_failure(ValueError("bad JSON at line 3"), "L") == (
        "Packing list could not be loaded", "L could not be read: bad JSON at line 3.",
    )
    assert start_failure(FileNotFoundError("gone"), "L") == (
        "Packing list could not be loaded", "L is no longer in the session's folder.",
    )
    title, text = start_failure(PackingStateUnreadableError("state.json: boom"), "L")
    assert title == "Saved progress could not be read"
    assert text == (
        "The saved progress for L could not be read, so the list was not opened. "
        "Nothing was changed. Check the connection to the server and open it again."
    )
    assert start_failure(RuntimeError("Locked by PACK-02"), "L") == (
        "Session could not be opened", "Locked by PACK-02",
    )
```

- [ ] **Step 2: Run and see it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_payload.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.app_bridge'`.

- [ ] **Step 3: Write `gui/app_bridge.py`** (the bridge class is added in Task 3)

```python
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

from gui.packer_bridge import _int, order_label
from packing_tool.exceptions import PackingListInvalidError, PackingStateUnreadableError
from packing_tool.session_stats import courier_totals, session_totals, sku_summary

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
            f"The saved progress for {list_name} could not be read, so the list was "
            "not opened. Nothing was changed. Check the connection to the server and "
            "open it again.",
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
```

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_payload.py`
Expected: PASS. If `test_statistics_counts_and_notes_inputs` disagrees on `packed`, read `session_stats._packed_by_sku`: it sums in-progress scans by `original_sku` (2 for LIP-RED in #10, 1 for SPF-50 in #13) plus every unit of a completed order (1 for LIP-RED in #12): 4.

- [ ] **Step 5: Commit** (`feat: pure payloads for the app document`)

---

### Task 3: `AppBridge`, the page shell and its states (no client, 3a, 3b, 3c, 4a, covered, toast)

**Files:**
- Modify: `gui/app_bridge.py` (append the bridge), `gui/web/floor.css` (append)
- Create: `gui/web/app.html`, `gui/web/app.css`, `gui/web/app.js`
- Test: `tests/test_app_bridge.py` (new)

**Interfaces:**
- Consumes: `shared.web_page.PageBridge`, `mount_page`; `gui.theme.current_tokens`; Task 2's `session_payload`.
- Produces: `AppBridge` with properties `page`, `covered`, `shell`, `session`, `packing`, `statistics`; setters `set_page(name: str)`, `set_covered(covered: bool)`, `set_shell(*, client: bool, clients: bool, server_down: bool)`, `set_session(payload: dict)`, `set_packing(payload: dict)`, `set_statistics(payload: dict)`; Python-facing signals `openSessionRequested`, `startPackingRequested`, `endSessionRequested`, `retryStartRequested`, `closeFailureRequested`, `clearFilterRequested`, `chooseClientRequested`, `pageRequested(str)`; `mount_app_page(view) -> AppBridge`. In the page: `window.appBridge`, `document.documentElement.dataset.bridge === "ready"`, element ids listed in `app.html` below.

- [ ] **Step 1: Write the failing tests**

`tests/test_app_bridge.py`:

```python
"""The app bridge and its page, driven through a real Chromium (ADR 0003).

Never mark these skip -- a bridge nobody can run is a bridge nobody guards.
"""

import json
import time

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from pytestqt.exceptions import TimeoutError as QtBotTimeoutError

from gui.app_bridge import PAGE, mount_app_page, session_payload
from gui.theme import apply_theme
from shared.theme import THEME_DARK, THEME_LIGHT
from shared.web_page import THEME_MARKER


def _eval(qtbot, view, expr, timeout=5000):
    # runJavaScript cannot marshal a JS array back; route everything through JSON.
    box = []
    view.page().runJavaScript(f"JSON.stringify({expr})", 0, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=timeout)
    return json.loads(box[0])


def _until_js(qtbot, view, expr, timeout_s=20):
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


def _shown(view, qtbot, element_id):
    return _eval(qtbot, view, f"!document.getElementById('{element_id}').hidden")


def _text(view, qtbot, element_id):
    return _eval(qtbot, view, f"document.getElementById('{element_id}').textContent")


def _click(view, qtbot, element_id):
    _eval(qtbot, view, f"(document.getElementById('{element_id}').click(), true)")


@pytest.fixture
def page(qtbot):
    view = QWebEngineView()
    qtbot.addWidget(view)
    bridge = mount_app_page(view)
    view.resize(1166, 708)
    view.show()
    _until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge


def _settle(qtbot, bridge):
    qtbot.waitUntil(lambda: bridge.painted_revision >= bridge.revision, timeout=20000)


OPEN = session_payload(
    "open", list_name="DHL_Orders", session_id="2026-10-07_1", orders=4, couriers=["DHL", "DPD"]
)


def test_the_page_carries_the_theme_marker_exactly_once():
    assert PAGE.read_text(encoding="utf-8").count(THEME_MARKER) == 1


def test_the_page_reports_the_revision_it_painted(page, qtbot):
    _view, bridge = page
    bridge.set_shell(client=True, clients=True, server_down=False)
    _settle(qtbot, bridge)
    assert bridge.painted_revision == bridge.revision


def test_a_theme_switch_repaints_without_a_reload(page, qtbot, qapp):
    view, _ = page
    before = _text(view, qtbot, "theme-vars")
    apply_theme(qapp, THEME_LIGHT)
    try:
        qtbot.waitUntil(lambda: _text(view, qtbot, "theme-vars") != before, timeout=10000)
    finally:
        apply_theme(qapp, THEME_DARK)


def test_with_no_client_the_page_asks_for_one(page, qtbot):
    view, bridge = page
    chosen = []
    bridge.chooseClientRequested.connect(lambda: chosen.append(1))
    bridge.set_shell(client=False, clients=True, server_down=False)
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "no-client")
    assert not _shown(view, qtbot, "no-session")
    assert _text(view, qtbot, "no-client-title") == "Choose a client to begin"
    _click(view, qtbot, "choose-client")
    qtbot.waitUntil(lambda: chosen == [1], timeout=5000)


def test_with_no_clients_at_all_there_is_no_button(page, qtbot):
    view, bridge = page
    bridge.set_shell(client=False, clients=False, server_down=False)
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "no-client")
    assert not _shown(view, qtbot, "choose-client")


def test_3a_no_session_offers_open_session(page, qtbot):
    view, bridge = page
    opened = []
    bridge.openSessionRequested.connect(lambda: opened.append(1))
    bridge.set_shell(client=True, clients=True, server_down=False)
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "no-session")
    assert not _shown(view, qtbot, "head")
    _click(view, qtbot, "open-session")
    qtbot.waitUntil(lambda: opened == [1], timeout=5000)


def test_3a_open_session_is_disabled_while_the_server_is_down(page, qtbot):
    view, bridge = page
    bridge.set_shell(client=True, clients=True, server_down=True)
    _settle(qtbot, bridge)
    assert _eval(qtbot, view, "document.getElementById('open-session').disabled") is True


def test_4a_statistics_with_no_session_points_back_to_packing(page, qtbot):
    view, bridge = page
    asked = []
    bridge.pageRequested.connect(asked.append)
    bridge.set_shell(client=True, clients=True, server_down=False)
    bridge.set_page("statistics")
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "stats-empty")
    assert not _shown(view, qtbot, "no-session")
    _click(view, qtbot, "go-packing")
    qtbot.waitUntil(lambda: asked == ["packing"], timeout=5000)


@pytest.mark.parametrize("step, name", [
    (1, "Taking the packing list"),
    (2, "Reading saved progress"),
    (3, "Reading the packing list"),
])
def test_3b_opening_names_the_step(page, qtbot, step, name):
    view, bridge = page
    bridge.set_shell(client=True, clients=True, server_down=False)
    bridge.set_session(session_payload(
        "opening", list_name="DHL_Orders", session_id="2026-10-07_1", step=step))
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "opening")
    assert _shown(view, qtbot, "head")
    assert _text(view, qtbot, "head-title") == "DHL_Orders"
    assert not _shown(view, qtbot, "head-badge")
    assert not _shown(view, qtbot, "head-start")
    assert _text(view, qtbot, "step-count") == f"Working · step {step} of 3"
    assert _text(view, qtbot, "step-name") == name
    assert _eval(qtbot, view, "document.querySelectorAll('.app-step-bar.done').length") == step


def test_3c_a_failed_start_says_why_and_offers_retry_and_close(page, qtbot):
    view, bridge = page
    said = []
    bridge.retryStartRequested.connect(lambda: said.append("retry"))
    bridge.closeFailureRequested.connect(lambda: said.append("close"))
    bridge.set_shell(client=True, clients=True, server_down=False)
    bridge.set_session(session_payload(
        "failed", list_name="DHL_Orders", title="Packing list could not be loaded",
        text="DHL_Orders has an order with no courier. Found: items, order_number."))
    _settle(qtbot, bridge)
    assert _shown(view, qtbot, "failed")
    assert not _shown(view, qtbot, "opening")
    assert _text(view, qtbot, "failed-title") == "Packing list could not be loaded"
    assert "no courier" in _text(view, qtbot, "failed-text")
    _click(view, qtbot, "failed-retry")
    _click(view, qtbot, "failed-close")
    qtbot.waitUntil(lambda: said == ["retry", "close"], timeout=5000)


def test_an_open_session_shows_the_header_with_its_meta(page, qtbot):
    view, bridge = page
    started = []
    bridge.startPackingRequested.connect(lambda: started.append(1))
    bridge.set_shell(client=True, clients=True, server_down=False)
    bridge.set_session(OPEN)
    _settle(qtbot, bridge)
    assert _text(view, qtbot, "head-title") == "DHL_Orders"
    assert _text(view, qtbot, "head-id") == "2026-10-07_1"
    assert _text(view, qtbot, "head-meta") == "4 orders · DHL, DPD"
    assert _shown(view, qtbot, "head-badge")
    _click(view, qtbot, "head-start")
    qtbot.waitUntil(lambda: started == [1], timeout=5000)


def test_on_statistics_the_header_is_titled_statistics(page, qtbot):
    view, bridge = page
    bridge.set_shell(client=True, clients=True, server_down=False)
    bridge.set_session(OPEN)
    bridge.set_page("statistics")
    _settle(qtbot, bridge)
    assert _text(view, qtbot, "head-title") == "Statistics"
    assert _text(view, qtbot, "head-meta") == "DHL_Orders"
    assert not _shown(view, qtbot, "head-start")
    assert not _shown(view, qtbot, "head-id")


def test_covered_draws_nothing(page, qtbot):
    view, bridge = page
    bridge.set_shell(client=True, clients=True, server_down=False)
    bridge.set_session(OPEN)
    bridge.set_covered(True)
    _settle(qtbot, bridge)
    assert _eval(qtbot, view, "document.body.innerText.trim()") == ""
    bridge.set_covered(False)
    _settle(qtbot, bridge)
    assert "DHL_Orders" in _eval(qtbot, view, "document.body.innerText")


def test_the_page_draws_a_toast_and_dismisses_it(page, qtbot):
    view, bridge = page
    bridge.set_shell(client=True, clients=True, server_down=False)
    _settle(qtbot, bridge)
    bridge.raise_toast("Loaded 4 orders from DHL_Orders.")
    _until_js(qtbot, view, "!document.getElementById('toast').hidden")
    assert _text(view, qtbot, "toast-text") == "Loaded 4 orders from DHL_Orders."
    _click(view, qtbot, "toast-close")
    assert not _shown(view, qtbot, "toast")
```

- [ ] **Step 2: Run and see it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_bridge.py`
Expected: FAIL with `ImportError: cannot import name 'mount_app_page'`.

- [ ] **Step 3: Append the bridge to `gui/app_bridge.py`**

Add to the imports:

```python
from PySide6.QtCore import Property, Signal, Slot
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.theme import current_tokens
from shared.web_page import PageBridge, mount_page
```

Append:

```python
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
```

- [ ] **Step 4: Append to `gui/web/floor.css`**

Replace the comment line "Phases 3 to 5 add table rows, inputs and the toast here when a page first uses them." with "Phase 3 added the toast, the state card, the strip, the track and the table rows; phases 4 and 5 add inputs when a page first uses them." Then append:

```css
/* --- toast: bottom centre of the page ------------------------------------ */

.toast-wrap {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 24px;
  z-index: var(--z-toast);
  display: flex;
  justify-content: center;
  pointer-events: none;
}
.toast-wrap .toast {
  position: static;
  min-height: 48px;
  gap: 16px;
  padding: 0 8px 0 16px;
  pointer-events: auto;
}
.toast-wrap .toast-close { width: 36px; height: 36px; }

/* --- state card: a page with nothing to show yet ------------------------- */

.state-card {
  margin: auto;
  width: 100%;
  max-width: 520px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 32px;
  text-align: center;
}
.state-card-title { margin: 0; font-size: var(--type-display-size); font-weight: 700; }
.state-card-text { margin: 0; color: var(--text-secondary); }
.state-card .btn { margin-top: 6px; padding: 0 20px; }

/* --- strip: one card split into cells of a label over a number ----------- */

.strip { flex: none; display: grid; }
.strip-cell {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 12px 20px;
  border-right: 1px solid var(--border);
}
.strip-cell:last-child { border-right: 0; justify-content: center; gap: 6px; }
.strip-label { font-weight: 700; }
.strip-line { display: flex; align-items: baseline; gap: 8px; }
.strip-value { font-size: var(--type-display-xl-size); font-weight: 700; line-height: 1.15; }
.strip-of { color: var(--text-secondary); }
.strip-note {
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* --- track: how far along ------------------------------------------------- */

.track {
  height: 14px;
  border: 1px solid var(--border-strong);
  border-radius: 7px;
  background: var(--surface-raised);
  overflow: hidden;
}
.track.tall { height: 24px; border-radius: 6px; }
.track-fill { height: 100%; background: var(--status-success-dot); }

/* --- table rows. The page sets --tbl-cols on the table's card. ------------ */

.tbl-head, .tbl-row {
  display: grid;
  grid-template-columns: var(--tbl-cols);
  align-items: center;
}
.tbl-head {
  flex: none;
  height: 40px;
  padding: 0 16px;
  background: var(--surface-raised);
  border-bottom: 1px solid var(--border);
  font-size: var(--type-caption-size);
  font-weight: 700;
  color: var(--text-secondary);
}
.tbl-group {
  display: flex;
  align-items: center;
  gap: 10px;
  height: 40px;
  padding: 0 16px;
  background: var(--surface-sunken);
  border-bottom: 1px solid var(--border);
}
.tbl-group-label { font-weight: 700; }
.tbl-group-count { font-family: var(--font-family-mono); color: var(--text-secondary); }
.tbl-group-note { font-size: var(--type-caption-size); color: var(--text-secondary); }
.tbl-row {
  min-height: 44px;
  padding: 0 16px;
  border-bottom: 1px solid var(--border-subtle);
}
```

- [ ] **Step 5: Create `gui/web/app.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Packer Assistant</title>
<!-- shared/web_page.mount_page writes theme_css_vars() over the marker in the
     style element below before the page loads; app.js keeps it current. -->
<style id="theme-vars">/* theme-vars */</style>
<link rel="stylesheet" href="../../shared/web/kit.css">
<link rel="stylesheet" href="floor.css">
<link rel="stylesheet" href="app.css">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="../../shared/web/page.js"></script>
<script src="app.js" defer></script>
</head>
<body>
<!-- The app document (ADR 0003): Packing and Statistics. Every string from
     the bridge goes in through textContent. -->
<div class="app" id="app">

  <section class="card state-card" id="no-client" hidden>
    <h1 class="state-card-title" id="no-client-title">Choose a client to begin</h1>
    <p class="state-card-text">Sessions, packing lists and SKU mapping all belong to one client.</p>
    <button type="button" class="btn primary" id="choose-client" data-action="chooseClient">Choose a client</button>
  </section>

  <section class="card state-card" id="no-session" hidden>
    <h1 class="state-card-title">No session open</h1>
    <p class="state-card-text">Open a session to see its orders here.</p>
    <button type="button" class="btn primary" id="open-session" data-action="openSession">Open session</button>
  </section>

  <section class="card state-card" id="stats-empty" hidden>
    <h1 class="state-card-title">No packing data yet</h1>
    <p class="state-card-text">Start a session from the Packing tab to see numbers here.</p>
    <button type="button" class="btn primary" id="go-packing" data-action="goPacking">Go to Packing</button>
  </section>

  <header class="app-head" id="head" hidden>
    <div class="app-head-text">
      <div class="app-head-line">
        <span class="app-title" id="head-title"></span>
        <span class="badge info" id="head-badge">Active</span>
      </div>
      <div class="app-meta">
        <span class="mono" id="head-id"></span>
        <span id="head-dot">·</span>
        <span id="head-meta"></span>
      </div>
    </div>
    <button type="button" class="btn primary" id="head-start" data-action="startPacking" title="Opens Packer Mode">Start packing</button>
  </header>

  <section class="card app-opening" id="opening" hidden>
    <div class="app-step-count" id="step-count"></div>
    <div class="app-step-name" id="step-name"></div>
    <div class="app-step-detail"><span class="mono" id="step-list"></span> · <span class="mono" id="step-id"></span></div>
    <div class="app-step-bars">
      <span class="app-step-bar"></span><span class="app-step-bar"></span><span class="app-step-bar"></span>
    </div>
  </section>

  <div class="banner danger app-failed" id="failed" hidden>
    <svg class="glyph" viewBox="0 0 24 24"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
    <div class="banner-body">
      <div class="banner-title" id="failed-title"></div>
      <div class="banner-text" id="failed-text"></div>
      <div class="banner-actions">
        <button type="button" class="btn secondary" id="failed-retry" data-action="retryStart">Retry</button>
        <button type="button" class="btn ghost" id="failed-close" data-action="closeFailure">Close</button>
      </div>
    </div>
  </div>

  <div class="app-page" id="packing" hidden></div>
  <div class="app-page" id="statistics" hidden></div>

  <div class="toast-wrap">
    <div class="toast" id="toast" role="status" hidden>
      <span id="toast-text"></span>
      <button type="button" class="toast-close" id="toast-close" title="Dismiss" aria-label="Dismiss">
        <svg class="glyph" viewBox="0 0 24 24"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>
      </button>
    </div>
  </div>
</div>
</body>
</html>
```

- [ ] **Step 6: Create `gui/web/app.css`**

```css
/* The app document's own sheet (UI refresh phase 3, ADR 0003): the layouts of
   Packing and Statistics. Buttons, badges, cards and the banner come from
   shared/web/kit.css; the toast, state card, strip, track and table rows from
   floor.css. Mockup: docs/design/ui-refresh/mockups/Packer App.html, frames
   3a-3g and 4a-4c.
   Spec: docs/superpowers/specs/2026-10-08-ui-refresh-phase3-packing-statistics-design.md
   Web-tier rules (ADR 0001): var(--...) only, type sizes from the scale, one
   mono face, no transition/transform/opacity. */

.app {
  position: relative;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px 24px;
  overflow: hidden;
}

/* --- page header --------------------------------------------------------- */

.app-head { flex: none; display: flex; align-items: center; gap: 16px; }
.app-head-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.app-head-line { display: flex; align-items: center; gap: 12px; min-width: 0; }
.app-title {
  font-size: var(--type-display-size);
  font-weight: 700;
  line-height: 1.25;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.app-meta { display: flex; flex-wrap: wrap; gap: 8px; color: var(--text-secondary); }

/* --- 3b: opening --------------------------------------------------------- */

.app-opening { flex: none; display: flex; flex-direction: column; gap: 4px; padding: 20px 24px; }
.app-step-count { font-size: var(--type-caption-size); color: var(--text-secondary); }
.app-step-name { font-size: var(--type-display-size); font-weight: 700; }
.app-step-detail { color: var(--text-secondary); }
.app-step-bars { display: flex; gap: 4px; margin-top: 8px; }
.app-step-bar { flex: 1; height: 6px; border-radius: 3px; background: var(--border); }
.app-step-bar.done { background: var(--accent-fill); }

/* --- 3c: a failed start. floor.css lays the banner out as one row. -------- */

.app-failed { flex: none; align-items: flex-start; padding: 16px 20px; }
.app-failed > .glyph { margin-top: 2px; }
.app-failed .banner-body { gap: 6px; }
.app-failed .banner-title { flex: none; }
.app-failed .banner-actions { gap: 8px; margin-top: 4px; }

/* --- a page's content ---------------------------------------------------- */

.app-page { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 16px; }
```

- [ ] **Step 7: Create `gui/web/app.js`**

```js
// The app document: Packing and Statistics (ADR 0003). The page renders what
// the bridge sends. Totals, groups, filter hits and failure sentences are
// decided in gui/app_bridge.py; the page keeps only which order rows were
// toggled and how the SKU table is sorted. Every string from the bridge goes
// in through textContent. Spec:
// docs/superpowers/specs/2026-10-08-ui-refresh-phase3-packing-statistics-design.md
"use strict";

const els = {};
const view = {
  bridge: null,
  sessionId: null,
  query: null,
  toggled: {},
  sort: { key: "left", dir: -1 },
  toastTimer: 0,
};

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function show(node, on) {
  node.hidden = !on;
}

function plural(count, one, many) {
  return count + " " + (count === 1 ? one : many);
}

// The page's own state belongs to one session: a new id drops it.
function syncSession() {
  const id = (view.bridge.session || {}).id || "";
  if (id === view.sessionId) return;
  view.sessionId = id;
  view.toggled = {};
  view.sort = { key: "left", dir: -1 };
}

// --- which block shows, the header, 3b and 3c --------------------------------

function renderFrame() {
  syncSession();
  const bridge = view.bridge;
  const shell = bridge.shell || {};
  const session = bridge.session || {};
  const state = session.state || "none";
  const page = bridge.page;
  const packing = page === "packing";
  const client = !!shell.client;
  const on = function (condition) { return !bridge.covered && condition; };

  show(els.noClient, on(!client));
  show(els.chooseClient, !!shell.clients);
  show(els.noSession, on(client && state === "none" && packing));
  els.openSession.disabled = !!shell.serverDown;
  show(els.statsEmpty, on(client && state === "none" && !packing));
  show(els.head, on(client && state !== "none"));
  show(els.opening, on(client && state === "opening"));
  show(els.failed, on(client && state === "failed"));
  show(els.packing, on(client && state === "open" && packing));
  show(els.statistics, on(client && state === "open" && !packing));
  if (bridge.covered) show(els.toast, false);

  const open = state === "open";
  els.headTitle.textContent = packing || !open ? session.list || "" : "Statistics";
  els.headTitle.title = els.headTitle.textContent;
  show(els.headBadge, open);
  show(els.headId, open && packing);
  show(els.headDot, open && packing);
  els.headId.textContent = session.id || "";
  els.headMeta.textContent = !open ? "" : packing ? session.meta || "" : session.list || "";
  show(els.headStart, open && packing);
  els.headStart.disabled = !!session.complete;

  const step = session.step || 0;
  els.stepCount.textContent = "Working · step " + step + " of 3";
  els.stepName.textContent = session.stepName || "";
  els.stepList.textContent = session.list || "";
  els.stepId.textContent = session.id || "";
  els.stepBars.forEach(function (bar, index) {
    bar.classList.toggle("done", index < step);
  });

  els.failedTitle.textContent = session.title || "";
  els.failedText.textContent = session.text || "";
}

// --- toast --------------------------------------------------------------------

function hideToast() {
  clearTimeout(view.toastTimer);
  show(els.toast, false);
}

function toast(message) {
  els.toastText.textContent = message;
  show(els.toast, true);
  clearTimeout(view.toastTimer);
  view.toastTimer = setTimeout(hideToast, 4000);
}

// --- clicks -------------------------------------------------------------------

const ACTIONS = {
  chooseClient: function (bridge) { bridge.chooseClient(); },
  openSession: function (bridge) { bridge.openSession(); },
  goPacking: function (bridge) { bridge.showPage("packing"); },
  startPacking: function (bridge) { bridge.startPacking(); },
  endSession: function (bridge) { bridge.endSession(); },
  retryStart: function (bridge) { bridge.retryStart(); },
  closeFailure: function (bridge) { bridge.closeFailure(); },
  clearFilter: function (bridge) { bridge.clearFilter(); },
};

function onClick(event) {
  const target = event.target.closest("[data-action]");
  if (target && !target.disabled) ACTIONS[target.dataset.action](view.bridge);
}

const IDS = {
  root: "app", themeVars: "theme-vars",
  noClient: "no-client", chooseClient: "choose-client",
  noSession: "no-session", openSession: "open-session", statsEmpty: "stats-empty",
  head: "head", headTitle: "head-title", headBadge: "head-badge", headId: "head-id",
  headDot: "head-dot", headMeta: "head-meta", headStart: "head-start",
  opening: "opening", stepCount: "step-count", stepName: "step-name",
  stepList: "step-list", stepId: "step-id",
  failed: "failed", failedTitle: "failed-title", failedText: "failed-text",
  packing: "packing", statistics: "statistics",
  toast: "toast", toastText: "toast-text", toastClose: "toast-close",
};

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.app;
  view.bridge = bridge;
  // The test harness drives the page through this handle; nothing in the
  // page reads it.
  window.appBridge = bridge;
  Object.keys(IDS).forEach(function (key) {
    els[key] = document.getElementById(IDS[key]);
  });
  els.stepBars = Array.from(document.querySelectorAll(".app-step-bar"));

  const onTheme = function () { els.themeVars.textContent = bridge.themeCss; };
  onTheme();
  bridge.themeCssChanged.connect(onTheme);
  bridge.toastRaised.connect(toast);
  els.toastClose.addEventListener("click", hideToast);

  [bridge.pageChanged, bridge.coveredChanged, bridge.shellChanged, bridge.sessionChanged]
    .forEach(function (signal) { signal.connect(renderFrame); });
  renderFrame();
  els.root.addEventListener("click", onClick);

  // After the first render, so the first report is of a drawn page.
  reportPaints(bridge);
  document.documentElement.dataset.bridge = "ready";
});
```

- [ ] **Step 8: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_bridge.py tests/test_style_literals_guard.py`
Expected: PASS.

- [ ] **Step 9: Commit** (`feat: the app document's bridge, shell states and toast`)

---

### Task 4: The Packing page (3d, 3e, 3f, 3g)

**Files:**
- Modify: `gui/web/app.html` (fill `#packing`), `gui/web/app.css` (append), `gui/web/app.js` (add `renderPacking`)
- Test: `tests/test_app_bridge.py` (append)

**Interfaces:**
- Consumes: `bridge.packing` (Task 2's `packing_payload` shape), `bridge.session.complete`.
- Produces: element ids `tot-done`, `tot-orders`, `tot-packed`, `tot-units`, `tot-skipped`, `tot-skipped-note`, `tot-pct`, `tot-fill`, `tot-left`, `complete`, `complete-text`, `complete-end`, `filter-line`, `filter-text`, `filter-query`, `filter-clear`, `no-match`, `no-match-query`, `no-match-clear`, `rows`; row classes `.tbl-group`, `.app-order` (a `button` with `data-order` and `aria-expanded`), `.app-item` (`.hit` when it matches).

- [ ] **Step 1: Append the failing tests to `tests/test_app_bridge.py`**

```python
# Add packing_payload to the `from gui.app_bridge import ...` line at the top of the file.


def _line(sku, name, qty, courier="DHL"):
    return {"SKU": sku, "Product_Name": name, "Quantity": str(qty), "Courier": courier}


ORDERS = {
    "#10": {"items": [_line("LIP-RED", "Lip balm, red", 2), _line("CRM-50", "Day cream", 1)]},
    "#11": {"items": [_line("LST-07", "Lipstick, shade 07", 1, "DPD")]},
    "#12": {"items": [_line("LIP-RED", "Lip balm, red", 1, "DPD")]},
    "#13": {"items": [_line("SPF-50", "Sunscreen", 3)]},
}
STATE = {
    "completed_orders": ["#12"],
    "skipped_orders": ["#13"],
    "in_progress": {"#10": [
        {"original_sku": "LIP-RED", "packed": 2, "required": 2, "row": 0},
        {"original_sku": "CRM-50", "packed": 0, "required": 1, "row": 1},
    ]},
}


def _open_packing(bridge, qtbot, orders=ORDERS, state=STATE, query=""):
    payload = packing_payload(orders, state, query)
    bridge.set_shell(client=True, clients=True, server_down=False)
    bridge.set_session(session_payload(
        "open", list_name="DHL_Orders", session_id="2026-10-07_1",
        orders=payload["totals"]["orders"], couriers=["DHL", "DPD"],
        complete=payload["totals"]["complete"]))
    bridge.set_packing(payload)
    _settle(qtbot, bridge)


def _all(view, qtbot, selector, expr="e.textContent"):
    return _eval(
        qtbot, view,
        f"Array.from(document.querySelectorAll('{selector}')).map(e => {expr})",
    )


def test_3d_the_totals_strip(page, qtbot):
    view, bridge = page
    _open_packing(bridge, qtbot)
    assert _shown(view, qtbot, "packing")
    assert _text(view, qtbot, "tot-done") == "1"
    assert _text(view, qtbot, "tot-orders") == "of 4"
    assert _text(view, qtbot, "tot-packed") == "3"
    assert _text(view, qtbot, "tot-units") == "of 8"
    assert _text(view, qtbot, "tot-skipped") == "1"
    assert _text(view, qtbot, "tot-skipped-note") == "still Not started"
    assert _text(view, qtbot, "tot-pct") == "25%"
    assert _eval(qtbot, view, "document.getElementById('tot-fill').style.width") == "25%"
    assert _text(view, qtbot, "tot-left") == "3 orders left · 1 in progress"


def test_3d_groups_in_order_with_counts(page, qtbot):
    view, bridge = page
    _open_packing(bridge, qtbot)
    assert _all(view, qtbot, ".tbl-group-label") == ["In progress", "Not started", "Packed"]
    assert _all(view, qtbot, ".tbl-group-count") == ["1", "2", "1"]
    assert _all(view, qtbot, ".tbl-group-note") == ["", "1 skipped", ""]


def test_3d_in_progress_orders_are_open_and_the_rest_closed(page, qtbot):
    view, bridge = page
    _open_packing(bridge, qtbot)
    assert _all(view, qtbot, ".app-order", "[e.dataset.order, e.getAttribute('aria-expanded')]") == [
        ["#10", "true"], ["#11", "false"], ["#13", "false"], ["#12", "false"],
    ]
    assert _all(view, qtbot, ".app-item .app-item-sku") == ["LIP-RED", "CRM-50"]
    assert _all(view, qtbot, ".app-item .badge") == ["Complete", "Pending"]
    assert _eval(qtbot, view, "document.querySelectorAll('input').length") == 0


def test_3d_an_order_row_says_what_it_holds(page, qtbot):
    view, bridge = page
    _open_packing(bridge, qtbot)
    row = "document.querySelector('.app-order[data-order=\"#13\"]')"
    assert _eval(qtbot, view, f"{row}.querySelector('.app-order-label').textContent") == "#13"
    assert _eval(qtbot, view, f"{row}.querySelector('.badge.warning').textContent") == "Skipped"
    assert _eval(qtbot, view, f"{row}.querySelector('.app-order-summary').textContent") == "1 item · Sunscreen"
    assert _eval(qtbot, view, f"{row}.querySelector('.app-qty').textContent") == "0 / 3"
    assert _eval(qtbot, view, f"{row}.querySelector('.app-status .badge').textContent") == "Not started"
    assert _eval(qtbot, view, f"{row}.querySelector('.app-courier').textContent") == "DHL"


def test_3d_a_click_opens_a_row_and_a_second_closes_it(page, qtbot):
    view, bridge = page
    _open_packing(bridge, qtbot)
    row = "document.querySelector('.app-order[data-order=\"#11\"]')"
    _eval(qtbot, view, f"({row}.click(), true)")
    assert _eval(qtbot, view, f"{row}.getAttribute('aria-expanded')") == "true"
    assert "LST-07" in _all(view, qtbot, ".app-item .app-item-sku")
    # A new push keeps what the packer opened.
    _open_packing(bridge, qtbot, state={**STATE, "completed_orders": ["#12", "#13"]})
    assert _eval(qtbot, view, f"{row}.getAttribute('aria-expanded')") == "true"
    _eval(qtbot, view, f"({row}.click(), true)")
    assert _eval(qtbot, view, f"{row}.getAttribute('aria-expanded')") == "false"


def test_3e_a_filter_opens_the_matches_and_marks_the_hit(page, qtbot):
    view, bridge = page
    cleared = []
    bridge.clearFilterRequested.connect(lambda: cleared.append(1))
    _open_packing(bridge, qtbot, query="lip-red")
    assert _all(view, qtbot, ".app-order", "e.dataset.order") == ["#10", "#12"]
    assert _all(view, qtbot, ".app-order", "e.getAttribute('aria-expanded')") == ["true", "true"]
    assert _all(view, qtbot, ".app-item.hit .app-item-sku") == ["LIP-RED", "LIP-RED"]
    assert _shown(view, qtbot, "filter-line")
    assert _text(view, qtbot, "filter-text") == "2 of 4 orders contain "
    assert _text(view, qtbot, "filter-query") == "lip-red"
    assert not _shown(view, qtbot, "no-match")
    _click(view, qtbot, "filter-clear")
    qtbot.waitUntil(lambda: cleared == [1], timeout=5000)


def test_3f_no_match_echoes_the_query_and_offers_clear(page, qtbot):
    view, bridge = page
    cleared = []
    bridge.clearFilterRequested.connect(lambda: cleared.append(1))
    _open_packing(bridge, qtbot, query="99999")
    assert _shown(view, qtbot, "no-match")
    assert not _shown(view, qtbot, "filter-line")
    assert not _shown(view, qtbot, "rows")
    assert _text(view, qtbot, "no-match-query") == "99999"
    _click(view, qtbot, "no-match-clear")
    qtbot.waitUntil(lambda: cleared == [1], timeout=5000)


def test_3g_complete_shows_the_banner_and_disables_start_packing(page, qtbot):
    view, bridge = page
    ended = []
    bridge.endSessionRequested.connect(lambda: ended.append(1))
    done = {"completed_orders": list(ORDERS), "skipped_orders": [], "in_progress": {}}
    _open_packing(bridge, qtbot, state=done)
    assert _shown(view, qtbot, "complete")
    assert _text(view, qtbot, "complete-text") == "4 of 4 orders packed."
    assert _text(view, qtbot, "tot-left") == "All orders packed"
    assert _text(view, qtbot, "tot-skipped-note") == "none"
    assert _eval(qtbot, view, "document.getElementById('head-start').disabled") is True
    _click(view, qtbot, "complete-end")
    qtbot.waitUntil(lambda: ended == [1], timeout=5000)


def test_an_unfinished_list_has_no_complete_banner(page, qtbot):
    view, bridge = page
    _open_packing(bridge, qtbot)
    assert not _shown(view, qtbot, "complete")
    assert _eval(qtbot, view, "document.getElementById('head-start').disabled") is False


def test_markup_in_a_product_name_is_text(page, qtbot):
    view, bridge = page
    orders = {"#1": {"items": [_line("<b>X</b>", "<img src=x onerror=alert(1)>", 1)]}}
    state = {"in_progress": {"#1": [{"row": 0, "packed": 0, "required": 1}]}}
    _open_packing(bridge, qtbot, orders=orders, state=state)
    assert _all(view, qtbot, ".app-item .app-item-sku") == ["<b>X</b>"]
    assert _eval(qtbot, view, "document.querySelectorAll('#rows img, #rows b').length") == 0


def test_a_new_session_drops_what_the_packer_toggled(page, qtbot):
    view, bridge = page
    _open_packing(bridge, qtbot)
    row = "document.querySelector('.app-order[data-order=\"#11\"]')"
    _eval(qtbot, view, f"({row}.click(), true)")
    bridge.set_session(session_payload("open", list_name="Other", session_id="2026-10-08_1", orders=4))
    bridge.set_packing(packing_payload(ORDERS, {}))
    _settle(qtbot, bridge)
    assert _eval(qtbot, view, f"{row}.getAttribute('aria-expanded')") == "false"
```

- [ ] **Step 2: Run and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_bridge.py`
Expected: the new tests FAIL (`tot-done` is null).

- [ ] **Step 3: Fill `#packing` in `gui/web/app.html`**

Replace `<div class="app-page" id="packing" hidden></div>` with:

```html
  <div class="app-page" id="packing" hidden>
    <section class="card strip app-strip-packing">
      <div class="strip-cell">
        <span class="strip-label">Orders complete</span>
        <span class="strip-line"><span class="strip-value" id="tot-done"></span><span class="strip-of" id="tot-orders"></span></span>
      </div>
      <div class="strip-cell">
        <span class="strip-label">Items packed</span>
        <span class="strip-line"><span class="strip-value" id="tot-packed"></span><span class="strip-of" id="tot-units"></span></span>
      </div>
      <div class="strip-cell">
        <span class="strip-label">Orders skipped</span>
        <span class="strip-line"><span class="strip-value" id="tot-skipped"></span><span class="strip-of" id="tot-skipped-note"></span></span>
      </div>
      <div class="strip-cell">
        <span class="strip-line"><span class="strip-label spacer">Progress</span><span class="app-pct" id="tot-pct"></span></span>
        <div class="track"><div class="track-fill" id="tot-fill"></div></div>
        <span class="strip-note" id="tot-left"></span>
      </div>
    </section>

    <section class="app-complete" id="complete" hidden>
      <svg class="glyph" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/></svg>
      <div class="app-complete-body">
        <div class="app-complete-title">Packing list complete</div>
        <div id="complete-text"></div>
      </div>
      <button type="button" class="btn primary" id="complete-end" data-action="endSession">End session</button>
    </section>

    <div class="app-filter-line" id="filter-line" hidden>
      <span><span id="filter-text"></span><span class="mono app-strong" id="filter-query"></span></span>
      <button type="button" class="btn ghost" id="filter-clear" data-action="clearFilter">Clear filter</button>
    </div>

    <section class="card app-index">
      <div class="tbl-head">
        <span class="app-head-first">Order / Item</span><span>Product</span><span class="app-qty">Quantity</span><span>Status</span><span>Courier</span>
      </div>
      <div class="app-no-match" id="no-match" hidden>
        <svg class="glyph" viewBox="0 0 24 24"><path d="m13.5 8.5-5 5"/><path d="m8.5 8.5 5 5"/><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
        <div class="app-no-match-title">No orders match</div>
        <div class="app-no-match-text">Nothing in this packing list contains “<span class="mono app-no-match-query" id="no-match-query"></span>”.</div>
        <button type="button" class="btn secondary" id="no-match-clear" data-action="clearFilter">Clear filter</button>
      </div>
      <div class="app-rows" id="rows"></div>
    </section>
  </div>
```

- [ ] **Step 4: Append to `gui/web/app.css`**

```css
/* --- Packing: totals strip, complete banner, filter line, index ---------- */

.app-strip-packing { grid-template-columns: repeat(3, minmax(0, 1fr)) minmax(0, 1.6fr); }
.app-pct { font-size: var(--type-display-size); font-weight: 700; }
.app-strong { font-weight: 700; }

.app-complete {
  flex: none;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 20px;
  border: 1px solid var(--card-border);
  border-radius: var(--kit-radius-card);
  background: var(--status-success-bg);
}
.app-complete > .glyph { width: 32px; height: 32px; color: var(--status-success); }
.app-complete-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.app-complete-title {
  font-size: var(--type-display-size);
  font-weight: 700;
  color: var(--status-success);
}
.app-complete .btn { padding: 0 20px; }

.app-filter-line { flex: none; display: flex; align-items: center; gap: 12px; min-height: 44px; }

.app-index {
  --tbl-cols: minmax(200px, 1.1fr) minmax(0, 2fr) 120px 170px 110px;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.app-head-first { padding-left: 30px; }
.app-rows { flex: 1; min-height: 0; overflow: auto; }

/* An order row is a button: it opens and closes its items. */
.app-order {
  width: 100%;
  height: 52px;
  border: 0;
  border-bottom: 1px solid var(--border-subtle);
  background: transparent;
  text-align: left;
  cursor: pointer;
}
.app-order[aria-expanded="true"] { background: var(--surface-raised); }
.app-order:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
.app-order-no { display: flex; align-items: center; gap: 10px; min-width: 0; }
.app-order-no > .glyph { width: 20px; height: 20px; color: var(--text-secondary); }
.app-order-label { font-family: var(--font-family-mono); font-weight: 700; }
.app-cut {
  padding-right: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.app-order-summary { color: var(--text-secondary); }
.app-qty { padding-right: 24px; text-align: right; font-family: var(--font-family-mono); }
.tbl-head .app-qty { font-family: inherit; }

.app-item { background: var(--surface-raised); }
.app-item.hit {
  padding-left: 12px;
  border-left: 4px solid var(--selection-border);
  background: var(--selection-bg);
}
.app-item-sku { padding-left: 30px; font-family: var(--font-family-mono); }

.app-no-match {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 24px;
  text-align: center;
}
.app-no-match > .glyph { width: 32px; height: 32px; color: var(--text-secondary); stroke-width: 1.5; }
.app-no-match-title { font-size: var(--type-display-size); font-weight: 700; }
.app-no-match-text { color: var(--text-secondary); }
.app-no-match-query { color: var(--text); }
.app-no-match .btn { margin-top: 4px; padding: 0 20px; }
```

- [ ] **Step 5: Add `renderPacking` to `gui/web/app.js`**

Insert after the `renderFrame` function:

```js
// --- Packing ------------------------------------------------------------------

const ORDER_BADGE = {
  packed: ["Packed", "badge success"],
  in_progress: ["In progress", "badge info"],
  not_started: ["Not started", "badge neutral"],
};
const ITEM_BADGE = {
  complete: ["Complete", "badge success"],
  partial: ["Partial", "badge info"],
  pending: ["Pending", "badge neutral"],
};
const SVG_NS = "http://www.w3.org/2000/svg";
const CHEVRON_DOWN = "m6 9 6 6 6-6";
const CHEVRON_RIGHT = "m9 18 6-6-6-6";

function glyph(d) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "glyph");
  svg.setAttribute("viewBox", "0 0 24 24");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", d);
  svg.appendChild(path);
  return svg;
}

function badge(pair) {
  return el("span", pair[1], pair[0]);
}

// Text that an ellipsis may cut keeps its whole self in the tooltip.
function cut(cls, text) {
  const node = el("span", "app-cut " + cls, text);
  node.title = text;
  return node;
}

function isOpen(order) {
  return order.number in view.toggled ? view.toggled[order.number] : !!order.open;
}

function orderRow(order) {
  const open = isOpen(order);
  const row = el("button", "tbl-row app-order");
  row.type = "button";
  row.dataset.order = order.number;
  row.setAttribute("aria-expanded", String(open));

  const first = el("span", "app-order-no");
  first.appendChild(glyph(open ? CHEVRON_DOWN : CHEVRON_RIGHT));
  first.appendChild(el("span", "app-order-label", order.label));
  if (order.skipped) first.appendChild(el("span", "badge warning", "Skipped"));
  row.appendChild(first);

  row.appendChild(cut("app-order-summary", order.summary));
  row.appendChild(el("span", "app-qty", order.packed + " / " + order.units));
  const status = el("span", "app-status");
  status.appendChild(badge(ORDER_BADGE[order.status] || ORDER_BADGE.not_started));
  row.appendChild(status);
  row.appendChild(el("span", "app-courier", order.courier));
  return row;
}

function itemRow(item) {
  const row = el("div", "tbl-row app-item" + (item.hit ? " hit" : ""));
  row.appendChild(cut("app-item-sku", item.sku));
  row.appendChild(cut("", item.product));
  row.appendChild(el("span", "app-qty", item.packed + " / " + item.required));
  const status = el("span", "app-status");
  status.appendChild(badge(ITEM_BADGE[item.state] || ITEM_BADGE.pending));
  row.appendChild(status);
  row.appendChild(el("span"));
  return row;
}

function renderPacking() {
  syncSession();
  const packing = view.bridge.packing || {};
  const totals = packing.totals || {};
  const query = packing.query || "";
  // What the packer opened by hand belongs to one filter text.
  if (query !== view.query) {
    view.query = query;
    view.toggled = {};
  }
  const orders = totals.orders || 0;
  const done = totals.done || 0;
  const pct = totals.pct || 0;

  els.totDone.textContent = done;
  els.totOrders.textContent = "of " + orders;
  els.totPacked.textContent = totals.packed || 0;
  els.totUnits.textContent = "of " + (totals.units || 0);
  els.totSkipped.textContent = totals.skipped || 0;
  els.totSkippedNote.textContent = totals.skipped ? "still Not started" : "none";
  els.totPct.textContent = pct + "%";
  els.totFill.style.width = pct + "%";
  els.totLeft.textContent = totals.complete
    ? "All orders packed"
    : plural(orders - done, "order", "orders") + " left · " + (totals.in_progress || 0) + " in progress";

  show(els.complete, !!totals.complete);
  els.completeText.textContent = done + " of " + orders + " orders packed.";

  const hits = packing.hits || 0;
  show(els.filterLine, !!query && hits > 0);
  els.filterText.textContent = hits + " of " + orders + " orders contain ";
  els.filterQuery.textContent = query;
  show(els.noMatch, !!query && hits === 0);
  els.noMatchQuery.textContent = query;
  show(els.rows, !(query && hits === 0));

  // ponytail: the whole index is rebuilt on every push. Fine at a few hundred
  // orders; patch rows in place if a list ever reaches thousands.
  const rows = document.createDocumentFragment();
  (packing.groups || []).forEach(function (group) {
    const head = el("div", "tbl-group");
    head.appendChild(el("span", "tbl-group-label", group.label));
    head.appendChild(el("span", "tbl-group-count", group.count));
    head.appendChild(el("span", "tbl-group-note", group.note));
    rows.appendChild(head);
    group.orders.forEach(function (order) {
      rows.appendChild(orderRow(order));
      if (isOpen(order)) order.items.forEach(function (item) { rows.appendChild(itemRow(item)); });
    });
  });
  els.rows.replaceChildren(rows);
}

function toggleOrder(number) {
  const current = (view.bridge.packing.groups || [])
    .flatMap(function (group) { return group.orders; })
    .find(function (order) { return order.number === number; });
  if (!current) return;
  view.toggled[number] = !isOpen(current);
  renderPacking();
}
```

Replace `onClick` with:

```js
function onClick(event) {
  const action = event.target.closest("[data-action]");
  if (action) {
    if (!action.disabled) ACTIONS[action.dataset.action](view.bridge);
    return;
  }
  const order = event.target.closest("[data-order]");
  if (order) toggleOrder(order.dataset.order);
}
```

Add to `IDS`:

```js
  totDone: "tot-done", totOrders: "tot-orders", totPacked: "tot-packed", totUnits: "tot-units",
  totSkipped: "tot-skipped", totSkippedNote: "tot-skipped-note", totPct: "tot-pct",
  totFill: "tot-fill", totLeft: "tot-left",
  complete: "complete", completeText: "complete-text",
  filterLine: "filter-line", filterText: "filter-text", filterQuery: "filter-query",
  noMatch: "no-match", noMatchQuery: "no-match-query", rows: "rows",
```

In the channel callback, after `renderFrame();` add:

```js
  bridge.packingChanged.connect(renderPacking);
  renderPacking();
```

- [ ] **Step 6: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_bridge.py tests/test_style_literals_guard.py`
Expected: PASS.

- [ ] **Step 7: Commit** (`feat: the Packing page in the app document (3d to 3g)`)

---

### Task 5: The Statistics page (4b, 4c, sorting)

**Files:**
- Modify: `gui/web/app.html` (fill `#statistics`), `gui/web/app.css` (append), `gui/web/app.js` (add `renderStatistics`)
- Test: `tests/test_app_bridge.py` (append)

**Interfaces:**
- Consumes: `bridge.statistics` (Task 2's `statistics_payload` shape).
- Produces: element ids `kpi-orders`, `kpi-orders-note`, `kpi-completed`, `kpi-completed-note`, `kpi-items`, `kpi-items-note`, `kpi-skus`, `kpi-skus-note`, `kpi-pct`, `kpi-fill`, `kpi-pct-note`, `couriers`, `sku-meta`, `sku-rows`; sort buttons `.app-sort[data-sort]` inside `[role=columnheader]` cells carrying `aria-sort`; rows `.app-sku`.

- [ ] **Step 1: Append the failing tests to `tests/test_app_bridge.py`**

```python
STATS = {
    "orders": 4, "completed": 1, "items": 7, "unique_skus": 4, "pct": 25,
    "in_progress": 1, "packed": 3, "fully_packed": 1,
    "couriers": [
        {"name": "DHL", "done": 0, "total": 2},
        {"name": "DPD", "done": 2, "total": 2},
    ],
    "skus": [
        {"sku": "CRM-50", "product": "Day cream", "total": 1, "packed": 0, "left": 1, "state": "pending"},
        {"sku": "LIP-RED", "product": "Lip balm, red", "total": 3, "packed": 3, "left": 0, "state": "packed"},
        {"sku": "LST-07", "product": "Lipstick, shade 07", "total": 1, "packed": 0, "left": 1, "state": "pending"},
        {"sku": "SPF-50", "product": "Sunscreen", "total": 3, "packed": 1, "left": 2, "state": "partial"},
    ],
}


def _open_statistics(bridge, qtbot, stats=STATS):
    bridge.set_shell(client=True, clients=True, server_down=False)
    bridge.set_session(session_payload(
        "open", list_name="DHL_Orders", session_id="2026-10-07_1", orders=stats["orders"]))
    bridge.set_statistics(stats)
    bridge.set_page("statistics")
    _settle(qtbot, bridge)


def _sku_order(view, qtbot):
    return _all(view, qtbot, ".app-sku .app-sku-code")


def test_4b_the_kpi_strip(page, qtbot):
    view, bridge = page
    _open_statistics(bridge, qtbot)
    assert _shown(view, qtbot, "statistics")
    assert (_text(view, qtbot, "kpi-orders"), _text(view, qtbot, "kpi-orders-note")) == ("4", "2 couriers")
    assert (_text(view, qtbot, "kpi-completed"), _text(view, qtbot, "kpi-completed-note")) == ("1", "1 in progress")
    assert (_text(view, qtbot, "kpi-items"), _text(view, qtbot, "kpi-items-note")) == ("7", "3 packed")
    assert (_text(view, qtbot, "kpi-skus"), _text(view, qtbot, "kpi-skus-note")) == ("4", "1 fully packed")
    assert _text(view, qtbot, "kpi-pct") == "25%"
    assert _text(view, qtbot, "kpi-pct-note") == "1 of 4 orders complete"


def test_4b_couriers_are_bars(page, qtbot):
    view, bridge = page
    _open_statistics(bridge, qtbot)
    assert _all(view, qtbot, ".app-courier-name") == ["DHL", "DPD"]
    assert _all(view, qtbot, ".app-courier .track-fill", "e.style.width") == ["0%", "100%"]
    assert _all(view, qtbot, ".app-courier-left") == ["2 orders left", "All packed"]
    assert _all(view, qtbot, ".app-courier-done") == ["0 done", "2 done"]


def test_4b_the_sku_table_is_sorted_by_left_most_first(page, qtbot):
    view, bridge = page
    _open_statistics(bridge, qtbot)
    assert _sku_order(view, qtbot) == ["SPF-50", "CRM-50", "LST-07", "LIP-RED"]
    assert _text(view, qtbot, "sku-meta") == "4 SKUs · sorted by Left, most first"
    assert _eval(
        qtbot, view,
        "document.querySelector('[data-col=\"left\"]').getAttribute('aria-sort')",
    ) == "descending"
    assert _all(view, qtbot, ".app-sku .badge") == ["Partial", "Pending", "Pending", "Packed"]
    assert _all(view, qtbot, ".app-left.zero") == ["0"]


def test_a_header_click_sorts_and_a_second_click_reverses(page, qtbot):
    view, bridge = page
    _open_statistics(bridge, qtbot)
    sort = "document.querySelector('.app-sort[data-sort=\"sku\"]')"
    _eval(qtbot, view, f"({sort}.click(), true)")
    assert _sku_order(view, qtbot) == ["CRM-50", "LIP-RED", "LST-07", "SPF-50"]
    assert _text(view, qtbot, "sku-meta") == "4 SKUs · sorted by SKU"
    _eval(qtbot, view, f"({sort}.click(), true)")
    assert _sku_order(view, qtbot) == ["SPF-50", "LST-07", "LIP-RED", "CRM-50"]
    # A push keeps the sort the packer chose.
    bridge.set_statistics({**STATS, "completed": 2})
    _settle(qtbot, bridge)
    assert _sku_order(view, qtbot) == ["SPF-50", "LST-07", "LIP-RED", "CRM-50"]


def test_sorting_by_status_goes_pending_partial_packed(page, qtbot):
    view, bridge = page
    _open_statistics(bridge, qtbot)
    _eval(qtbot, view, "(document.querySelector('.app-sort[data-sort=\"state\"]').click(), true)")
    assert _all(view, qtbot, ".app-sku .badge") == ["Pending", "Pending", "Partial", "Packed"]


def test_4c_complete_is_full_bars_and_grey_left(page, qtbot):
    view, bridge = page
    done = {
        **STATS, "completed": 4, "pct": 100, "in_progress": 0, "packed": 7, "fully_packed": 4,
        "couriers": [{"name": "DHL", "done": 2, "total": 2}, {"name": "DPD", "done": 2, "total": 2}],
        "skus": [{**row, "packed": row["total"], "left": 0, "state": "packed"} for row in STATS["skus"]],
    }
    _open_statistics(bridge, qtbot, stats=done)
    assert _all(view, qtbot, ".app-courier .track-fill", "e.style.width") == ["100%", "100%"]
    assert _text(view, qtbot, "kpi-completed-note") == "none in progress"
    assert _eval(qtbot, view, "document.querySelectorAll('.app-left.zero').length") == 4
    assert _eval(qtbot, view, "document.getElementById('kpi-fill').style.width") == "100%"


def test_statistics_keeps_nothing_of_an_ended_session(page, qtbot):
    view, bridge = page
    _open_statistics(bridge, qtbot)
    bridge.set_session(session_payload())
    bridge.set_statistics({})
    _settle(qtbot, bridge)
    assert _eval(qtbot, view, "document.querySelectorAll('.app-sku, .app-courier').length") == 0
    assert _shown(view, qtbot, "stats-empty")
```

- [ ] **Step 2: Run and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_bridge.py`
Expected: the new tests FAIL (`kpi-orders` is null).

- [ ] **Step 3: Fill `#statistics` in `gui/web/app.html`**

Replace `<div class="app-page" id="statistics" hidden></div>` with:

```html
  <div class="app-page" id="statistics" hidden>
    <section class="card strip app-strip-stats">
      <div class="strip-cell"><span class="strip-label">Orders</span><span class="strip-value" id="kpi-orders"></span><span class="strip-note" id="kpi-orders-note"></span></div>
      <div class="strip-cell"><span class="strip-label">Completed</span><span class="strip-value" id="kpi-completed"></span><span class="strip-note" id="kpi-completed-note"></span></div>
      <div class="strip-cell"><span class="strip-label">Items</span><span class="strip-value" id="kpi-items"></span><span class="strip-note" id="kpi-items-note"></span></div>
      <div class="strip-cell"><span class="strip-label">Unique SKUs</span><span class="strip-value" id="kpi-skus"></span><span class="strip-note" id="kpi-skus-note"></span></div>
      <div class="strip-cell">
        <span class="strip-line"><span class="strip-label spacer">Progress</span><span class="strip-value" id="kpi-pct"></span></span>
        <div class="track"><div class="track-fill" id="kpi-fill"></div></div>
        <span class="strip-note" id="kpi-pct-note"></span>
      </div>
    </section>

    <div class="app-stats-row">
      <section class="card app-couriers">
        <div class="app-strong">By courier</div>
        <div class="app-courier-list" id="couriers"></div>
      </section>

      <section class="card app-skus">
        <div class="app-skus-title">
          <span class="app-strong spacer">SKU summary</span>
          <span class="strip-note" id="sku-meta"></span>
        </div>
        <div class="tbl-head" role="row">
          <span role="columnheader" data-col="sku"><button type="button" class="app-sort" data-sort="sku" title="Sort by SKU">SKU</button></span>
          <span role="columnheader" data-col="product"><button type="button" class="app-sort" data-sort="product" title="Sort by Product">Product</button></span>
          <span role="columnheader" data-col="total"><button type="button" class="app-sort num" data-sort="total" title="Sort by Total qty">Total qty</button></span>
          <span role="columnheader" data-col="packed"><button type="button" class="app-sort num" data-sort="packed" title="Sort by Packed">Packed</button></span>
          <span role="columnheader" data-col="left"><button type="button" class="app-sort num" data-sort="left" title="Sort by Left">Left</button></span>
          <span role="columnheader" data-col="state"><button type="button" class="app-sort" data-sort="state" title="Sort by Status">Status</button></span>
        </div>
        <div class="app-rows" id="sku-rows"></div>
      </section>
    </div>
  </div>
```

- [ ] **Step 4: Append to `gui/web/app.css`**

```css
/* --- Statistics: KPI strip, By courier, SKU summary ---------------------- */

.app-strip-stats { grid-template-columns: repeat(4, minmax(0, 1fr)) minmax(0, 1.5fr); }

.app-stats-row {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(300px, 0.75fr) minmax(0, 2fr);
  gap: 16px;
}

.app-couriers {
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 16px 20px;
  overflow: auto;
}
.app-courier-list { display: flex; flex-direction: column; gap: 18px; }
.app-courier { display: flex; flex-direction: column; gap: 6px; }
.app-courier-line { display: flex; align-items: baseline; gap: 8px; }
.app-courier-name { flex: 1; min-width: 0; font-size: var(--type-heading-size); font-weight: 700; }
.app-courier-of { color: var(--text-secondary); }
.app-courier-left { font-size: var(--type-caption-size); color: var(--text-secondary); }

.app-skus {
  --tbl-cols: 130px minmax(0, 1fr) 84px 84px 84px 120px;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.app-skus-title {
  flex: none;
  display: flex;
  align-items: center;
  gap: 12px;
  height: 48px;
  padding: 0 20px;
  border-bottom: 1px solid var(--border);
}
.app-skus .tbl-head { height: 44px; padding: 0 12px; align-items: stretch; }
.app-skus [role="columnheader"] { display: flex; }

.app-sort {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-size: var(--type-caption-size);
  font-weight: 700;
  white-space: nowrap;
  cursor: pointer;
}
.app-sort.num { justify-content: flex-end; }
.app-sort:hover { background: var(--hover); }
.app-sort:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
[aria-sort="ascending"] > .app-sort,
[aria-sort="descending"] > .app-sort { color: var(--text); }

.app-sku { min-height: 40px; height: 40px; padding: 0 12px; }
.app-sku > span { padding: 0 8px; }
.app-sku-code { font-family: var(--font-family-mono); white-space: nowrap; }
.app-num { text-align: right; font-family: var(--font-family-mono); }
.app-left { font-weight: 700; }
.app-left.zero { font-weight: 400; color: var(--text-secondary); }
```

- [ ] **Step 5: Add `renderStatistics` to `gui/web/app.js`**

Insert after `toggleOrder`:

```js
// --- Statistics ---------------------------------------------------------------

// Column: its label and the direction a first click sorts it.
const SORT = {
  sku: ["SKU", 1],
  product: ["Product", 1],
  total: ["Total qty", -1],
  packed: ["Packed", -1],
  left: ["Left", -1],
  state: ["Status", 1],
};
const STATE_ORDER = { pending: 0, partial: 1, packed: 2 };
const SKU_BADGE = {
  packed: ["Packed", "badge success"],
  partial: ["Partial", "badge info"],
  pending: ["Pending", "badge neutral"],
};

function sortedSkus(skus) {
  const key = view.sort.key;
  const dir = view.sort.dir;
  const value = function (row) { return key === "state" ? STATE_ORDER[row.state] : row[key]; };
  return skus.slice().sort(function (a, b) {
    const va = value(a);
    const vb = value(b);
    const order = typeof va === "string" ? va.localeCompare(vb) : va - vb;
    return order * dir || a.sku.localeCompare(b.sku);
  });
}

function percent(done, total) {
  return (total ? Math.round(done / total * 100) : 0) + "%";
}

function courierBlock(courier) {
  const left = courier.total - courier.done;
  const block = el("div", "app-courier");
  const line = el("div", "app-courier-line");
  line.appendChild(el("span", "app-courier-name", courier.name));
  line.appendChild(el("span", "app-courier-done", courier.done + " done"));
  line.appendChild(el("span", "app-courier-of", "of " + courier.total));
  block.appendChild(line);
  const track = el("div", "track tall");
  const fill = el("div", "track-fill");
  fill.style.width = percent(courier.done, courier.total);
  track.appendChild(fill);
  block.appendChild(track);
  block.appendChild(el("span", "app-courier-left",
    left ? plural(left, "order", "orders") + " left" : "All packed"));
  return block;
}

function skuRow(sku) {
  const row = el("div", "tbl-row app-sku");
  row.appendChild(el("span", "app-sku-code", sku.sku));
  row.appendChild(cut("", sku.product));
  row.appendChild(el("span", "app-num", sku.total));
  row.appendChild(el("span", "app-num", sku.packed));
  row.appendChild(el("span", "app-num app-left" + (sku.left ? "" : " zero"), sku.left));
  const status = el("span");
  status.appendChild(badge(SKU_BADGE[sku.state] || SKU_BADGE.pending));
  row.appendChild(status);
  return row;
}

function renderStatistics() {
  syncSession();
  const stats = view.bridge.statistics || {};
  const couriers = stats.couriers || [];
  const skus = stats.skus || [];
  const pct = stats.pct || 0;

  els.kpiOrders.textContent = stats.orders || 0;
  els.kpiOrdersNote.textContent = plural(couriers.length, "courier", "couriers");
  els.kpiCompleted.textContent = stats.completed || 0;
  els.kpiCompletedNote.textContent = (stats.in_progress || "none") + " in progress";
  els.kpiItems.textContent = stats.items || 0;
  els.kpiItemsNote.textContent = (stats.packed || 0) + " packed";
  els.kpiSkus.textContent = stats.unique_skus || 0;
  els.kpiSkusNote.textContent = (stats.fully_packed || 0) + " fully packed";
  els.kpiPct.textContent = pct + "%";
  els.kpiFill.style.width = pct + "%";
  els.kpiPctNote.textContent = (stats.completed || 0) + " of " + (stats.orders || 0) + " orders complete";

  els.couriers.replaceChildren.apply(els.couriers, couriers.map(courierBlock));

  const key = view.sort.key;
  const dir = view.sort.dir;
  els.skuMeta.textContent = plural(skus.length, "SKU", "SKUs") + " · sorted by " + SORT[key][0]
    + (dir === -1 ? ", most first" : "");
  els.sortHeads.forEach(function (head) {
    const on = head.dataset.col === key;
    if (on) head.setAttribute("aria-sort", dir === 1 ? "ascending" : "descending");
    else head.removeAttribute("aria-sort");
    const button = head.firstElementChild;
    button.textContent = SORT[head.dataset.col][0] + (on ? (dir === 1 ? " ↑" : " ↓") : "");
  });
  els.skuRows.replaceChildren.apply(els.skuRows, sortedSkus(skus).map(skuRow));
}

function sortBy(key) {
  view.sort = { key: key, dir: view.sort.key === key ? -view.sort.dir : SORT[key][1] };
  renderStatistics();
}
```

In `onClick`, add after the `order` branch:

```js
  const sort = event.target.closest("[data-sort]");
  if (sort) sortBy(sort.dataset.sort);
```

(and make the `order` branch `return` after toggling, so the three branches read alike). Add to `IDS`:

```js
  kpiOrders: "kpi-orders", kpiOrdersNote: "kpi-orders-note",
  kpiCompleted: "kpi-completed", kpiCompletedNote: "kpi-completed-note",
  kpiItems: "kpi-items", kpiItemsNote: "kpi-items-note",
  kpiSkus: "kpi-skus", kpiSkusNote: "kpi-skus-note",
  kpiPct: "kpi-pct", kpiFill: "kpi-fill", kpiPctNote: "kpi-pct-note",
  couriers: "couriers", skuMeta: "sku-meta", skuRows: "sku-rows",
```

In the channel callback, next to `els.stepBars`:

```js
  els.sortHeads = Array.from(document.querySelectorAll("[role=columnheader]"));
```

and after the `renderPacking();` line:

```js
  bridge.statisticsChanged.connect(renderStatistics);
  renderStatistics();
```

- [ ] **Step 6: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_bridge.py tests/test_style_literals_guard.py`
Expected: PASS. If the guard rejects `var(--hover)`, it is a token `shared/web/kit.css` already uses (`.btn.secondary:hover`), so the name is right; check for a typo.

- [ ] **Step 7: Commit** (`feat: the Statistics page in the app document (4b, 4c)`)

---

### Task 6: `AppPages`

**Files:**
- Create: `gui/app_pages.py`
- Test: `tests/test_app_pages.py` (new)

**Interfaces:**
- Consumes: `mount_app_page(view) -> AppBridge`.
- Produces: `PAGE_PACKING = 0`, `PAGE_STATISTICS = 1`, `PAGE_BROWSER = 2`; `AppPages(session_browser: QWidget, parent=None)` with `view: QWebEngineView`, `bridge: AppBridge`, `browser`, `currentChanged: Signal(int)`, `setCurrentIndex(index: int)`, `currentIndex() -> int`, `count() -> int`, `widget(index: int) -> QWidget`, `web_is_current() -> bool`.

- [ ] **Step 1: Write the failing test**

`tests/test_app_pages.py`:

```python
"""AppPages: one web view for Packing and Statistics, the Qt Sessions page beside it."""

import pytest
from PySide6.QtWidgets import QLabel

from gui.app_pages import PAGE_BROWSER, PAGE_PACKING, PAGE_STATISTICS, AppPages


@pytest.fixture
def pages(qtbot):
    browser = QLabel("sessions")
    widget = AppPages(browser)
    qtbot.addWidget(widget)
    return widget


def test_it_has_three_pages_and_starts_on_packing(pages):
    assert pages.count() == 3
    assert pages.currentIndex() == PAGE_PACKING
    assert pages.bridge.page == "packing"
    assert pages.web_is_current()


def test_statistics_is_the_same_view_with_another_page(pages):
    seen = []
    pages.currentChanged.connect(seen.append)
    pages.setCurrentIndex(PAGE_STATISTICS)
    assert seen == [PAGE_STATISTICS]
    assert pages.bridge.page == "statistics"
    assert pages.web_is_current()
    assert pages.widget(PAGE_PACKING) is pages.widget(PAGE_STATISTICS) is pages.view


def test_sessions_is_the_browser_and_leaves_the_page_name_alone(pages):
    pages.setCurrentIndex(PAGE_STATISTICS)
    pages.setCurrentIndex(PAGE_BROWSER)
    assert pages.currentIndex() == PAGE_BROWSER
    assert not pages.web_is_current()
    assert pages.widget(PAGE_BROWSER) is pages.browser
    assert pages.bridge.page == "statistics"
    pages.setCurrentIndex(PAGE_PACKING)
    assert pages.web_is_current() and pages.bridge.page == "packing"


def test_setting_the_current_index_again_says_nothing(pages):
    seen = []
    pages.currentChanged.connect(seen.append)
    pages.setCurrentIndex(PAGE_PACKING)
    pages.setCurrentIndex(7)
    assert seen == []
    assert pages.currentIndex() == PAGE_PACKING
```

- [ ] **Step 2: Run and see it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_pages.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'gui.app_pages'`.

- [ ] **Step 3: Write `gui/app_pages.py`**

```python
"""The shell's pages: one web view, and the Qt Sessions page beside it (ADR 0003).

Packing and Statistics are two pages of one document in one QWebEngineView;
Sessions joins it in phase 4 and is the Qt SessionBrowserWidget until then.
This widget speaks the part of QTabWidget MainWindow's call sites already
use, so they kept `session_tabs` and did not change.
"""

from PySide6.QtCore import Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout, QWidget

from gui.app_bridge import mount_app_page

PAGE_PACKING, PAGE_STATISTICS, PAGE_BROWSER = range(3)
# The bridge's name for each page the document draws.
_WEB_PAGES = {PAGE_PACKING: "packing", PAGE_STATISTICS: "statistics"}


class AppPages(QWidget):
    currentChanged = Signal(int)

    def __init__(self, session_browser: QWidget, parent=None) -> None:
        super().__init__(parent)
        self.view = QWebEngineView(self)
        self.bridge = mount_app_page(self.view)
        self.browser = session_browser

        self._stack = QStackedWidget(self)
        self._stack.addWidget(self.view)
        self._stack.addWidget(session_browser)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)
        self._index = PAGE_PACKING

    def count(self) -> int:
        return 3

    def currentIndex(self) -> int:
        return self._index

    def widget(self, index: int) -> QWidget:
        return self.browser if index == PAGE_BROWSER else self.view

    def web_is_current(self) -> bool:
        return self._stack.currentWidget() is self.view

    def setCurrentIndex(self, index: int) -> None:
        if index == self._index or index not in (PAGE_PACKING, PAGE_STATISTICS, PAGE_BROWSER):
            return
        self._index = index
        if index in _WEB_PAGES:
            self.bridge.set_page(_WEB_PAGES[index])
        self._stack.setCurrentWidget(self.widget(index))
        self.currentChanged.emit(index)
```

- [ ] **Step 4: Run the test**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_pages.py`
Expected: PASS.

- [ ] **Step 5: Commit** (`feat: AppPages, the shell's page stack`)

---

### Task 7: `CommandBar.set_complete`

**Files:**
- Modify: `gui/command_bar.py`
- Test: `tests/test_command_bar.py` (append)

**Interfaces:**
- Produces: `CommandBar.set_complete(complete: bool) -> None`. When true: *End session* has role `primary`, *Start packing*'s tooltip is "Every order is packed". It does not enable or disable *Start packing*: `MainWindow` owns that.

- [ ] **Step 1: Append the failing test**

```python
def test_a_complete_list_makes_end_session_primary(bar):
    bar.set_session("2026-10-07_1")
    assert bar.end_session_button.property("role") == "secondary"
    assert bar.start_packing_button.toolTip() == "Start packing · opens Packer Mode"
    bar.set_complete(True)
    assert bar.end_session_button.property("role") == "primary"
    assert bar.start_packing_button.toolTip() == "Every order is packed"
    bar.set_complete(False)
    assert bar.end_session_button.property("role") == "secondary"
    assert bar.start_packing_button.toolTip() == "Start packing · opens Packer Mode"
```

- [ ] **Step 2: Run and see it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_command_bar.py`
Expected: FAIL with `AttributeError: 'CommandBar' object has no attribute 'set_complete'`.

- [ ] **Step 3: Implement**

In `gui/command_bar.py`, add `_START_TIP = "Start packing · opens Packer Mode"` beside `_END_TIP`, use it where the tooltip is first set (`self.start_packing_button.setToolTip(_START_TIP)`), add `self._complete = False` beside `self._reachable = True`, and add:

```python
    def set_complete(self, complete: bool) -> None:
        """Every order is packed (frame 3g): ending the session is the next step."""
        if complete == self._complete:
            return
        self._complete = complete
        set_button_role(self.end_session_button, "primary" if complete else "secondary")
        self.start_packing_button.setToolTip(
            "Every order is packed" if complete else _START_TIP
        )
        self._paint_hint()
```

In `_paint_hint`, the shortcut must read on the primary fill:

```python
    def _paint_hint(self) -> None:
        tokens = self._tokens
        if not self.end_session_button.isEnabled():
            colour = tokens.text_disabled
        elif self._complete:
            colour = tokens.on_accent
        else:
            colour = tokens.text_secondary
        self.end_shortcut_label.setStyleSheet(f"color: {colour};")
```

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_command_bar.py`
Expected: PASS.

- [ ] **Step 5: Commit** (`feat: the bar promotes End session when the list is complete`)

---

### Task 8: `MainWindow` on the app document; the Qt tree and statistics widget go

**Files:**
- Modify: `gui/main_window.py`, `tests/conftest.py`, `tests/test_shell.py`, `tests/test_no_client.py`, `tests/test_connection_state.py`, `tests/audit/test_02_concurrency_sweep.py`, `scripts/render_shell.py`
- Delete: `gui/statistics_widget.py`, `tests/test_statistics_widget.py`, `tests/test_order_tree.py`, `tests/test_order_tree_filter.py`, `tests/test_packing_empty.py`
- Test: `tests/test_app_mainwindow_seam.py` (new)

**Interfaces:**
- Consumes: `AppPages`, `PAGE_*` (Task 6); `packing_payload`, `statistics_payload`, `session_payload` (Task 2); `AppBridge` setters and signals (Task 3); `CommandBar.set_complete` (Task 7); `shared.web_page.switch_theme`.
- Produces on `MainWindow`: `session_tabs: AppPages`; `_push_pages() -> None`; `_refresh_pages() -> None`; `_shell_showing() -> bool`; `_toast(message: str, role: str = "success") -> None`; `_pages_stale: bool`. `from gui.main_window import PAGE_PACKING, PAGE_STATISTICS, PAGE_BROWSER` keeps working.

- [ ] **Step 1: Write the failing tests**

`tests/test_app_mainwindow_seam.py`:

```python
"""MainWindow and the app document: what crosses, and when (spec sections 7 and 8)."""

import pytest
from PySide6.QtWidgets import QTabWidget, QTreeWidget

from gui.main_window import PAGE_BROWSER, PAGE_PACKING, PAGE_STATISTICS
from shared.components.toast import Toast


def _bridge(window):
    return window.session_tabs.bridge


def test_the_qt_tree_tabs_and_statistics_widget_are_gone(main_window):
    assert not main_window.findChildren(QTreeWidget)
    assert not main_window.findChildren(QTabWidget)
    for name in ("order_tree", "statistics_widget", "packing_state_panel",
                 "packing_summary_label", "no_client_panel"):
        assert not hasattr(main_window, name), name


def test_with_no_session_the_document_is_told_so(main_window):
    bridge = _bridge(main_window)
    assert bridge.session["state"] == "none"
    assert bridge.packing == {} and bridge.statistics == {}
    assert bridge.shell == {"client": True, "clients": True, "serverDown": False}


def test_a_loaded_list_reaches_both_pages(main_window_with_list):
    window = main_window_with_list
    bridge = _bridge(window)
    assert bridge.session["state"] == "open"
    assert bridge.session["list"] == "DHL_Orders"
    assert bridge.session["meta"] == "2 orders · DHL"
    assert bridge.packing["totals"]["orders"] == 2
    assert bridge.statistics["orders"] == 2
    assert [c["name"] for c in bridge.statistics["couriers"]] == ["DHL"]


def test_the_filter_field_drives_the_packing_payload(main_window_with_list):
    window = main_window_with_list
    window.search_input.setText("SKU-OTHER")
    packing = _bridge(window).packing
    assert packing["query"] == "SKU-OTHER" and packing["hits"] == 1
    _bridge(window).clearFilter()
    assert window.search_input.text() == ""
    assert _bridge(window).packing["hits"] == 2


def test_the_pages_slots_reach_their_handlers(main_window_with_list, monkeypatch):
    window = main_window_with_list
    called = []
    monkeypatch.setattr(window, "switch_to_packer_mode", lambda: called.append("start"))
    monkeypatch.setattr(window, "end_session", lambda: called.append("end"))
    monkeypatch.setattr(window.client_combo, "showPopup", lambda: called.append("client"))
    bridge = _bridge(window)
    bridge.startPacking()
    bridge.endSession()
    bridge.chooseClient()
    assert called == ["start", "end", "client"]

    window.session_tabs.setCurrentIndex(PAGE_STATISTICS)
    bridge.showPage("packing")
    assert window.session_tabs.currentIndex() == PAGE_PACKING
    bridge.openSession()
    assert window.session_tabs.currentIndex() == PAGE_BROWSER


def test_a_scan_in_packer_mode_pushes_nothing_and_leaving_pushes_once(
    main_window_with_list, monkeypatch
):
    window = main_window_with_list
    window.logic.item_packed.connect(window._on_item_packed)
    window.switch_to_packer_mode()
    pushes = []
    real = window._push_pages
    monkeypatch.setattr(window, "_push_pages", lambda: (pushes.append(1), real())[1])
    window.on_scanner_input("#10429")
    window.logic.current_order_state[0]["required"] = 2  # so the scan is not the last one
    window.on_scanner_input("TS-4409-B")
    assert pushes == []
    assert window._pages_stale is True
    window.switch_to_session_view()
    assert pushes == [1]
    assert window._pages_stale is False
    assert _bridge(window).packing["totals"]["packed"] == 1


def test_a_complete_list_reaches_the_bar_and_disables_start_packing(main_window_with_list):
    window = main_window_with_list
    state = window.logic.session_packing_state
    state["completed_orders"] = ["#10429", "#10430"]
    window._push_pages()
    assert _bridge(window).session["complete"] is True
    assert window.toolbar_end_btn.property("role") == "primary"
    assert not window.packer_mode_button.isEnabled()
    state["completed_orders"] = ["#10429"]
    window._push_pages()
    assert window.toolbar_end_btn.property("role") == "secondary"
    assert window.packer_mode_button.isEnabled()


def test_ending_a_session_empties_the_document(main_window_with_list):
    window = main_window_with_list
    window._teardown_session()
    bridge = _bridge(window)
    assert bridge.session["state"] == "none"
    assert bridge.packing == {} and bridge.statistics == {}
    assert window.toolbar_end_btn.property("role") == "secondary"


def test_a_toast_goes_to_qt_while_the_page_is_not_on_screen(main_window):
    raised = []
    _bridge(main_window).toastRaised.connect(lambda message, _undo: raised.append(message))
    main_window._toast("Saved.")
    assert raised == []
    assert Toast.for_window(main_window).text() == "Saved."


def test_a_toast_goes_to_the_page_when_it_is_showing(main_window, qtbot):
    raised = []
    _bridge(main_window).toastRaised.connect(lambda message, _undo: raised.append(message))
    main_window.show()
    qtbot.waitExposed(main_window)
    try:
        main_window._toast("Saved.")
        assert raised == ["Saved."]
        main_window.session_tabs.setCurrentIndex(PAGE_BROWSER)
        main_window._toast("On Sessions.")
        assert raised == ["Saved."]
    finally:
        main_window.hide()
```

- [ ] **Step 2: Run and see it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_mainwindow_seam.py`
Expected: FAIL (`AttributeError: 'QTabWidget' object has no attribute 'bridge'`).

- [ ] **Step 3: Rewire `gui/main_window.py`**

Work top to bottom. Line numbers are from before any edit.

**Imports.** Keep `QProgressDialog`: session end still uses it. Remove from the `PySide6.QtWidgets` import: `QLabel`, `QTabWidget`, `QTreeWidget`, `QTreeWidgetItem`. Remove `QFont` from `PySide6.QtGui`. Remove `from gui.statistics_widget import StatisticsWidget`, `from shared.components.card import Card`, `from shared.components.state_panel import StatePanel`. From `shared.theme` remove `StatusChip`, `font_css`, `get_density_profile`, `on_theme_changed` if nothing else in the file uses them (run ruff; it tells you). Add:

```python
from gui.app_bridge import packing_payload, session_payload, statistics_payload
from gui.app_pages import PAGE_BROWSER, PAGE_PACKING, PAGE_STATISTICS, AppPages
from shared.fonts import load_bundled_fonts
from shared.theme import themed_tokens
from shared.web_page import switch_theme, when_painted
```

(`when_painted` is already imported; merge the line.) Delete the line `PAGE_PACKING, PAGE_STATISTICS, PAGE_BROWSER = range(len(RAIL_ITEMS))`, the `ORDER_STATUS_CHIP` dict with its comment, and the `order_summary` function.

**`__init__`.** Replace `self._order_tree_stale = False` with `self._pages_stale = False`.

**`_init_ui`.** Delete from the comment `# Create tab widget for session views.` down to and including `self.session_tabs.addTab(self.session_browser, "Session Browser")`, except the `SessionBrowserWidget(...)` construction and its two `connect` calls, which stay. After those, build the pages:

```python
        # Packing and Statistics are one web document; Sessions is the Qt
        # page beside it until phase 4 (ADR 0003). AppPages speaks the
        # QTabWidget calls the code below already makes.
        self.session_tabs = AppPages(self.session_browser)
        pages = self.session_tabs.bridge
        pages.openSessionRequested.connect(lambda: self.open_session_browser())
        pages.startPackingRequested.connect(lambda: self.switch_to_packer_mode())
        pages.endSessionRequested.connect(lambda: self.end_session())
        pages.clearFilterRequested.connect(lambda: self.search_input.clear())
        pages.chooseClientRequested.connect(lambda: self.client_combo.showPopup())
        pages.pageRequested.connect(self._show_named_page)
```

(Lambdas, so a test that replaces the handler is seen, as the sidebar connections below already do.) Keep the `if self.current_client_id: self.session_browser.load_client(...)` block. Delete the line `self.session_tabs.currentChanged.connect(self._rebuild_order_tree_if_stale)`. Delete the whole `# Frame 2a: with no client chosen the pages give way to this.` block that builds `self.no_client_panel` and its `main_layout.addWidget(self.no_client_panel, 1)`; keep `main_layout.addWidget(self.session_tabs, 1)`.

Add the method:

```python
    def _show_named_page(self, name: str):
        """The document asks for a page by the name the bridge uses."""
        index = {"packing": PAGE_PACKING, "statistics": PAGE_STATISTICS}.get(name)
        if index is not None:
            self.session_tabs.setCurrentIndex(index)
```

**`_switch_theme`** becomes:

```python
    def _switch_theme(self, name: str):
        """Light or Dark, from the sidebar's segment or its collapsed toggle.

        Through switch_theme, so the Qt chrome turns over with the visible web
        page instead of a frame ahead of it.
        """
        switch_theme(
            name,
            current_name=lambda: current_tokens().name,
            tokens_for=lambda theme: themed_tokens(theme, load_bundled_fonts()),
            set_theme=lambda theme: apply_theme(QApplication.instance(), theme),
        )
```

**Delete these methods whole:** `_setup_order_tree`, `_order_status_chip`, `_populate_order_tree`, `_refresh_order_tree`, `_rebuild_order_tree_if_stale`, `_update_statistics`, `setup_order_table`, `update_order_status`.

**`_filter_orders`** becomes:

```python
    def _filter_orders(self, text: str):
        """The bar's Filter orders field: the document redraws the index."""
        if self.logic is not None:
            self.session_tabs.bridge.set_packing(
                packing_payload(
                    self.logic.orders_data, self.logic.session_packing_state, text
                )
            )
```

**Add, where `_update_statistics` was:**

```python
    def _shell_showing(self) -> bool:
        return self.stacked_widget.currentWidget() is self.session_widget

    def _push_pages(self):
        """Send the document what Packing and Statistics show now.

        With no list open it empties both pages and leaves `session` alone:
        whoever closed, failed or is opening the session has said which.
        """
        self._pages_stale = False
        bridge = self.session_tabs.bridge
        logic = self.logic
        if logic is None:
            bridge.set_packing({})
            bridge.set_statistics({})
            self.command_bar.set_complete(False)
            return

        state = logic.session_packing_state
        packing = packing_payload(logic.orders_data, state, self.search_input.text())
        statistics = statistics_payload(getattr(logic, "processed_df", None), state)
        complete = packing["totals"]["complete"]
        bridge.set_session(
            session_payload(
                "open",
                list_name=self.current_packing_list or "",
                session_id=(
                    Path(self.current_session_path).name
                    if self.current_session_path
                    else ""
                ),
                orders=packing["totals"]["orders"],
                couriers=[courier["name"] for courier in statistics["couriers"]],
                complete=complete,
            )
        )
        bridge.set_packing(packing)
        bridge.set_statistics(statistics)
        self.command_bar.set_complete(complete)
        # Frame 3g: with every order packed there is nothing left to scan.
        self.packer_mode_button.setEnabled(not complete)

    def _refresh_pages(self):
        """Push now if the shell is on screen, else when it next is.

        A push is every order and line; during packing the pages sit under
        Packer Mode where nobody is looking (AUDIT-02-7).
        """
        if self._shell_showing():
            self._push_pages()
        else:
            self._pages_stale = True

    def _toast(self, message: str, role: str = "success"):
        """A toast where it can be seen: a Qt child cannot paint over a web
        view, so the app document draws its own while it is on screen."""
        pages = self.session_tabs
        if pages.view.isVisible():
            pages.bridge.raise_toast(message)
        else:
            toast(self, message, role=role)
```

**Replace every `toast(self, ...)` call** (six of them: `_on_connection_checked`, `open_sku_mapping_dialog`, two in `start_shopify_packing_session`, `end_session`, `_start_or_resume_from_browser`) with `self._toast(...)`, keeping the message and any `role=` argument.

**`_sync_client_state`** becomes:

```python
    def _sync_client_state(self):
        """Enable or disable what needs a client (spec 2026-10-08 section 6.6)."""
        chosen = bool(self.current_client_id)
        self.sidebar.set_client_chosen(chosen)
        self.command_bar.set_client_chosen(chosen)
        if not chosen:
            # The document draws "Choose a client"; Sessions is still Qt.
            self.session_tabs.setCurrentIndex(PAGE_PACKING)
        self._sync_shell()

    def _sync_shell(self):
        self.session_tabs.bridge.set_shell(
            client=bool(self.current_client_id),
            # With none, the selector's one item is "(No clients available)",
            # whose data is None. Not isEnabled(): an open session disables it.
            clients=self.client_combo.itemData(0) is not None,
            server_down=self._connection_state == "down",
        )
```

`_sync_client_state` runs from `load_available_clients`, which `__init__` calls after `_init_ui`, so `session_tabs` exists. In `on_client_changed`, where the client is locked because `self.logic is not None`, nothing changes.

**`_set_connection_state`:** replace its last line (`self.packing_state_panel.button.setEnabled(not down)`) with `self._sync_shell()`. This method is first called at the end of `_init_ui`, where `session_tabs` already exists.

**`_teardown_session`:** replace

```python
        if hasattr(self, "order_tree"):
            self.order_tree.clear()
        self.packing_summary_label.setText("")
        self.packing_summary_label.setVisible(False)
```

with

```python
        # Pushed even under Packer Mode: nothing of an ended session stays in
        # the document.
        self.session_tabs.bridge.set_session(session_payload())
        self._push_pages()
```

**`start_shopify_packing_session`:** replace the `# 10. Setup order table` line `self.setup_order_table()` with `self._push_pages()`.

**`enable_packing_mode`:** delete the line `self.packer_mode_button.setEnabled(True)`: `_push_pages` decides it and has already run. Then make the fixture path work too by calling `self._push_pages()` as the method's first statement after the log line (a fixture sets `logic` and calls this without a session start).

**`switch_to_session_view`:** delete its last line `self._rebuild_order_tree_if_stale()`.

**`_leave_packer_mode`:** in the nested `switch()`:

```python
        def switch():
            self._leaving_packer_mode = False
            # Before the shell shows: what it shows is current (spec section 8).
            self._push_pages()
            self.stacked_widget.setCurrentWidget(self.session_widget)
```

**`_on_item_packed`:** its two refresh lines become `self._refresh_pages()`.

**`on_scanner_input`** (near line 1951): `self.update_order_status(order_number_from_scan, "In Progress")` becomes `self._refresh_pages()`. **`_handle_order_completion`** (near line 2069): `self.update_order_status(order_number, "Completed")` becomes `self._refresh_pages()`.

Search the file for any remaining `order_tree`, `statistics_widget`, `packing_state_panel`, `packing_summary_label`, `no_client_panel`, `_order_tree_stale` and remove the reference. Update the class docstring's `orders_table` attribute line: delete it.

- [ ] **Step 4: Delete what the Qt widgets left behind**

Delete `gui/statistics_widget.py`, `tests/test_statistics_widget.py`, `tests/test_order_tree.py`, `tests/test_order_tree_filter.py`, `tests/test_packing_empty.py` (with `/usr/bin/git rm <path>`, one call each).

- [ ] **Step 5: Update the fixtures and the tests that named the old widgets**

`tests/conftest.py`, `main_window_with_list`: change its docstring's "populated into order_tree -- for tests of the tree's chrome, filter, and empty state" to "pushed to the app document", and replace `main_window._populate_order_tree()` with:

```python
    main_window.current_packing_list = "DHL_Orders"
    main_window._push_pages()
```

`tests/test_shell.py`:
- Remove `QTabWidget` and `order_summary` from the imports; delete `test_order_summary` with its `parametrize`.
- Replace `test_the_tab_bar_is_hidden_but_the_tab_widget_survives` with:

```python
def test_the_pages_are_one_web_view_and_the_session_browser(window):
    """ADR 0003: Packing and Statistics are two pages of one document."""
    from gui.app_pages import AppPages

    assert isinstance(window.session_tabs, AppPages)
    assert window.session_tabs.widget(PAGE_PACKING) is window.session_tabs.widget(PAGE_STATISTICS)
```

- Read the rest of the file for any use of `packing_summary_label`, `order_tree` or `statistics_widget` and delete those tests: what they checked is in `tests/test_app_mainwindow_seam.py` and `tests/test_app_bridge.py`.

`tests/test_no_client.py`:
- `_assert_no_client`: replace the two panel lines with

```python
    assert window.session_tabs.bridge.shell["client"] is False
    assert window.session_tabs.currentIndex() == PAGE_PACKING
```

- `_assert_client`: replace the two panel lines with `assert window.session_tabs.bridge.shell["client"] is True`.
- `test_two_clients_and_nothing_remembered_starts_on_choose_a_client`: delete the two lines about `panel`, and add `assert window.session_tabs.bridge.shell["clients"] is True`.
- `test_no_clients_at_all_shows_the_panel_without_a_button`: replace its two panel assertions with `assert window.session_tabs.bridge.shell == {"client": False, "clients": False, "serverDown": False}`.
- `test_the_panels_button_opens_the_selector`: replace `window.no_client_panel.button.click()` with `window.session_tabs.bridge.chooseClient()`.

`tests/test_connection_state.py`: replace both `main_window.packing_state_panel.button.isEnabled()` assertions: the first (`not ...`) with `assert main_window.session_tabs.bridge.shell["serverDown"] is True`, the second with `assert main_window.session_tabs.bridge.shell["serverDown"] is False`.

`tests/audit/test_02_concurrency_sweep.py`: delete `test_a_scan_does_not_rebuild_the_order_tree` (its replacement is `test_a_scan_in_packer_mode_pushes_nothing_and_leaving_pushes_once`), and change the section comment above it to `# AUDIT-02-7  Every scan rebuilt the whole (hidden) order tree: now tests/test_app_mainwindow_seam.py`.

`scripts/render_shell.py`: in `open_session`, replace `window._populate_order_tree()` with `window._push_pages()`.

- [ ] **Step 6: Run the suite and lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` then `.venv/bin/ruff check . --exclude shared`
Expected: PASS, no lint errors. A failure naming a deleted attribute in a test this step did not list means that test checked the old widget: move its intent onto the bridge (`window.session_tabs.bridge.<property>`) or delete it if `tests/test_app_bridge.py` already covers it, and say which in the commit message.

- [ ] **Step 7: Commit** (`feat: Packing and Statistics run on the app document; the Qt tree and statistics widget are deleted`)

---

### Task 9: Session start in the page (3b steps, 3c failures)

**Files:**
- Modify: `gui/main_window.py` (`start_shopify_packing_session`, `_start_or_resume_from_browser`, `on_client_changed`)
- Test: `tests/test_app_mainwindow_seam.py` (append), `tests/test_connection_state.py` (one test updated)

**Interfaces:**
- Consumes: `start_failure(error, list_name)`, `session_payload`, `SessionStartWorker.step`, `AppBridge.retryStartRequested`, `closeFailureRequested`.
- Produces on `MainWindow`: `_last_start: dict | None` (the keyword arguments of the last `_start_or_resume_from_browser` call); `_on_start_step(step: int)`; `_show_start_failure(title: str, text: str, list_name: str)`; `_retry_start()`; `_close_failure()`.

- [ ] **Step 1: Append the failing tests to `tests/test_app_mainwindow_seam.py`**

```python
import json

from PySide6.QtWidgets import QMessageBox

from gui.app_bridge import session_payload


def _broken_list(session_factory):
    orders = [("#1", "DHL", [{"sku": "A", "quantity": 1, "product_name": "A"}])]
    session_dir, work_dir, list_path = session_factory(client_id="TESTCL", orders=orders)
    data = json.loads(list_path.read_text(encoding="utf-8"))
    del data["orders"][0]["courier"]
    list_path.write_text(json.dumps(data), encoding="utf-8")
    return session_dir, work_dir, list_path


def test_a_failed_start_is_shown_in_the_page_and_not_in_a_message_box(
    main_window, session_factory, monkeypatch
):
    boxes = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: boxes.append(a))
    session_dir, work_dir, list_path = _broken_list(session_factory)
    seen = []
    bridge = _bridge(main_window)
    bridge.sessionChanged.connect(lambda: seen.append(bridge.session["state"]))

    started = main_window.start_shopify_packing_session(
        packing_list_path=list_path, work_dir=work_dir, session_path=session_dir,
        client_id="TESTCL", packing_list_name="DHL_Orders",
    )

    assert started is False
    assert boxes == []
    assert seen[0] == "opening" and seen[-1] == "failed"
    session = bridge.session
    assert session["title"] == "Packing list could not be loaded"
    assert session["text"] == "DHL_Orders has an order with no courier. Found: items, order_number."
    assert session["list"] == "DHL_Orders"
    assert main_window.logic is None
    assert main_window.current_work_dir is None
    assert not main_window.command_bar.open_session_button.isHidden()


def test_the_worker_steps_reach_the_page(main_window):
    bridge = _bridge(main_window)
    bridge.set_session(session_payload("opening", list_name="L", session_id="S", step=1))
    main_window._on_start_step(2)
    assert (bridge.session["step"], bridge.session["stepName"]) == (2, "Reading saved progress")
    assert (bridge.session["list"], bridge.session["id"]) == ("L", "S")


def test_a_late_step_does_not_replace_a_failure(main_window):
    bridge = _bridge(main_window)
    main_window._show_start_failure("Session could not be opened", "Locked by PACK-02", "L")
    main_window._on_start_step(3)
    assert bridge.session["state"] == "failed"


def test_close_returns_to_no_session(main_window):
    bridge = _bridge(main_window)
    main_window._show_start_failure("Session could not be opened", "Locked by PACK-02", "L")
    bridge.closeFailure()
    assert bridge.session["state"] == "none"


def test_retry_starts_again_with_the_same_arguments(main_window, monkeypatch, tmp_path):
    started = []
    monkeypatch.setattr(
        main_window, "start_shopify_packing_session",
        lambda **kwargs: started.append(kwargs) or False,
    )
    main_window._start_or_resume_from_browser(
        "TESTCL", "DHL_Orders", tmp_path, tmp_path / "DHL_Orders.json",
        work_dir=tmp_path, resumed=True,
    )
    assert len(started) == 1
    _bridge(main_window).retryStart()
    assert len(started) == 2
    assert started[1] == started[0]


def test_retry_with_nothing_to_retry_does_nothing(main_window):
    main_window._last_start = None
    _bridge(main_window).retryStart()  # must not raise
    assert _bridge(main_window).session["state"] == "none"


def test_changing_client_drops_a_failure(main_window):
    main_window._show_start_failure("Session could not be opened", "Locked by PACK-02", "L")
    other = main_window.client_combo.findData("OTHERCL")
    main_window.client_combo.setCurrentIndex(other)
    assert _bridge(main_window).session["state"] == "none"


def test_a_failed_start_leaves_the_packing_page_showing(main_window):
    main_window.session_tabs.setCurrentIndex(PAGE_STATISTICS)
    main_window._show_start_failure("Session could not be opened", "x", "L")
    assert main_window.session_tabs.currentIndex() == PAGE_PACKING
```

In `tests/test_connection_state.py`, `test_a_work_folder_that_cannot_be_made_reports_and_checks`: replace the `said` list and the `QMessageBox.critical` monkeypatch with nothing, and its `assert len(said) == 1 and "share is gone" in said[0][1]` with:

```python
    session = main_window.session_tabs.bridge.session
    assert session["state"] == "failed"
    assert session["title"] == "Session could not be opened"
    assert session["text"] == "The work folder for DHL_Orders could not be made: share is gone."
```

- [ ] **Step 2: Run and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_mainwindow_seam.py tests/test_connection_state.py`
Expected: the new tests FAIL (`_on_start_step` missing; a message box is raised).

- [ ] **Step 3: Implement in `gui/main_window.py`**

Add `start_failure` to the `gui.app_bridge` import. Remove `QProgressDialog` from the imports only if session end no longer uses it (it does: keep it). In `__init__`, beside `self._pages_stale`, add `self._last_start = None`. In `_init_ui`, with the other bridge connections:

```python
        pages.retryStartRequested.connect(lambda: self._retry_start())
        pages.closeFailureRequested.connect(lambda: self._close_failure())
```

Add the methods (next to `_cleanup_failed_session_start`):

```python
    def _on_start_step(self, step: int):
        """Frame 3b: the worker says which step it is on.

        The signal is queued from the worker's thread, so it can arrive after
        the start has already ended. Only an opening session takes a step.
        """
        bridge = self.session_tabs.bridge
        session = bridge.session
        if session.get("state") == "opening":
            bridge.set_session(
                session_payload(
                    "opening",
                    list_name=session.get("list", ""),
                    session_id=session.get("id", ""),
                    step=step,
                )
            )

    def _show_start_failure(self, title: str, text: str, list_name: str):
        """Frame 3c: a session that did not open says why, on the Packing page."""
        self.session_tabs.bridge.set_session(
            session_payload("failed", list_name=list_name, title=title, text=text)
        )
        self._push_pages()
        self.session_tabs.setCurrentIndex(PAGE_PACKING)

    def _retry_start(self):
        if self._last_start is not None:
            self._start_or_resume_from_browser(**self._last_start)

    def _close_failure(self):
        if self.session_tabs.bridge.session.get("state") == "failed":
            self.session_tabs.bridge.set_session(session_payload())
```

In `start_shopify_packing_session`:

- Directly after the three `logger.info` lines at the top of the `try`, show step 1:

```python
            pages = self.session_tabs.bridge
            pages.set_session(
                session_payload(
                    "opening",
                    list_name=packing_list_name,
                    session_id=session_path.name,
                    step=1,
                )
            )
            # The lock is taken on this thread: let the page hear about step 1.
            QApplication.processEvents()
```

- Where the user declines the stale lock (`if error_msg is None:` … `return False`), set the page back first:

```python
                if error_msg is None:
                    # User chose not to force-release: not a failure.
                    pages.set_session(session_payload())
                    return False
```

- Delete the `QProgressDialog` block (from `progress = QProgressDialog("Loading packing list…", None, 0, 0, self)` through `QApplication.processEvents()`), delete `progress.close()`, and connect the worker's steps before it starts:

```python
            start_worker.step.connect(self._on_start_step)
            start_worker.start()
            while not start_worker.wait(50):
                QApplication.processEvents()
```

Update the comment above the worker to "so the UI stays responsive and the page names the step it is on (frame 3b)".

- Replace all six `except` branches (`PackingStateUnreadableError`, `FileNotFoundError`, `json.JSONDecodeError`, `ValueError`, `RuntimeError`, `Exception`) with one:

```python
        except Exception as e:
            # Every failed start is frame 3c, with its own sentence
            # (gui.app_bridge.start_failure); no message box.
            logger.exception("Session start failed")
            self._cleanup_failed_session_start()
            title, text = start_failure(e, packing_list_name)
            self._show_start_failure(title, text, packing_list_name)
            return False
```

Remove the `PackingStateUnreadableError` import from `gui/main_window.py` if ruff now reports it unused, and `import json` likewise. Update the method's docstring: delete its `Raises:` section (it raises nothing; it returns False).

In `_start_or_resume_from_browser`, directly after the "Session Active" guard returns (before `self.session_tabs.setCurrentIndex(PAGE_PACKING)`), record the call:

```python
        self._last_start = {
            "client_id": client_id,
            "packing_list_name": packing_list_name,
            "session_path": session_path,
            "packing_list_path": packing_list_path,
            "work_dir": work_dir,
            "resumed": resumed,
        }
```

and replace the work-folder `except OSError` body's `QMessageBox.critical(...)` call with:

```python
                self._show_start_failure(
                    "Session could not be opened",
                    f"The work folder for {packing_list_name} could not be made: {e}.",
                    packing_list_name,
                )
```

(keep the `logger.exception`, `self.check_connection()` and `return`).

In `on_client_changed`, directly after `self.current_client_id = client_id` in the path that accepts the new client, add `self._close_failure()`.

- [ ] **Step 4: Run the suite and lint**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q` then `.venv/bin/ruff check . --exclude shared`
Expected: PASS. If another test monkeypatched `QMessageBox.critical` to observe a failed start, point it at `window.session_tabs.bridge.session` as above.

- [ ] **Step 5: Commit** (`feat: a session start names its steps and fails in the page`)

---

### Task 10: The kept frame, the freshness tests and the keyboard

**Files:**
- Modify: `gui/main_window.py` (`switch_to_packer_mode`, `_leave_packer_mode`, `__init__`)
- Test: `tests/test_app_freshness.py` (new)

**Interfaces:**
- Consumes: `AppBridge.set_covered`, `when_painted`, `AppPages.web_is_current`, `_push_pages`.
- Produces: `MainWindow._entering_packer_mode: bool`. `switch_to_packer_mode()` on a visible window switches only after the covered document has painted (150 ms cap); on a window that is not visible it switches at once.

- [ ] **Step 1: Write the failing tests**

`tests/test_app_freshness.py`:

```python
"""What the pages show after they were hidden (spec section 8), in a real Chromium."""

import json

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from gui.main_window import PAGE_BROWSER, PAGE_PACKING, PAGE_STATISTICS


def _eval(qtbot, view, expr, timeout=5000):
    box = []
    view.page().runJavaScript(f"JSON.stringify({expr})", 0, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=timeout)
    return json.loads(box[0])


def _settle(qtbot, bridge):
    qtbot.waitUntil(lambda: bridge.painted_revision >= bridge.revision, timeout=20000)


def _logic(session_factory, packer_logic_factory, session_id, order, sku):
    orders = [(order, "DHL", [{"sku": sku, "quantity": 1, "product_name": f"Product {sku}"}])]
    _session, work_dir, list_path = session_factory(
        client_id="TESTCL", session_id=session_id, orders=orders)
    logic = packer_logic_factory("TESTCL", work_dir)
    logic.load_packing_list_json(list_path)
    return logic


def _open(window, logic, session_id):
    window.logic = logic
    window.current_packing_list = "DHL_Orders"
    window.current_session_path = f"/sessions/{session_id}"
    window.enable_packing_mode()


@pytest.fixture
def shown(main_window, qtbot):
    main_window.show()
    qtbot.waitExposed(main_window)
    view = main_window.session_tabs.view
    qtbot.waitUntil(
        lambda: _eval(qtbot, view, "document.documentElement.dataset.bridge") == "ready",
        timeout=20000,
    )
    yield main_window
    main_window.hide()


@pytest.mark.parametrize("page, a_text, b_text", [
    (PAGE_PACKING, "#A-1001", "#B-2002"),
    (PAGE_STATISTICS, "SKU-AAA", "SKU-BBB"),
])
def test_a_page_shown_after_being_hidden_holds_the_current_session_only(
    shown, qtbot, session_factory, packer_logic_factory, page, a_text, b_text
):
    window = shown
    pages = window.session_tabs
    view, bridge = pages.view, pages.bridge
    pages.setCurrentIndex(page)
    _open(window, _logic(session_factory, packer_logic_factory, "2026-01-01_1", "A-1001", "SKU-AAA"),
          "2026-01-01_1")
    _settle(qtbot, bridge)
    assert a_text in _eval(qtbot, view, "document.body.textContent")

    pages.setCurrentIndex(PAGE_BROWSER)          # the view is hidden
    window._teardown_session()                   # session A ends
    _open(window, _logic(session_factory, packer_logic_factory, "2026-01-02_1", "B-2002", "SKU-BBB"),
          "2026-01-02_1")
    pushed = bridge.revision

    pages.setCurrentIndex(page)                  # shown again
    _settle(qtbot, bridge)
    assert bridge.painted_revision >= pushed
    text = _eval(qtbot, view, "document.body.textContent")
    assert b_text in text
    assert a_text not in text


def test_start_packing_waits_for_the_covered_page_to_paint(
    shown, qtbot, session_factory, packer_logic_factory
):
    window = shown
    bridge = window.session_tabs.bridge
    _open(window, _logic(session_factory, packer_logic_factory, "2026-01-01_1", "A-1001", "SKU-AAA"),
          "2026-01-01_1")
    _settle(qtbot, bridge)

    window.switch_to_packer_mode()
    assert bridge.covered is True
    # Not yet: the page has not reported the covered revision.
    assert window.stacked_widget.currentWidget() is window.session_widget
    window.switch_to_packer_mode()  # a second click while waiting is ignored
    qtbot.waitUntil(
        lambda: window.stacked_widget.currentWidget() is window.packer_mode_widget,
        timeout=5000,
    )

    window.switch_to_session_view()
    qtbot.waitUntil(
        lambda: window.stacked_widget.currentWidget() is window.session_widget,
        timeout=5000,
    )
    assert bridge.covered is False


def test_a_session_ended_inside_packer_mode_leaves_no_trace_in_the_page(
    shown, qtbot, session_factory, packer_logic_factory
):
    window = shown
    view, bridge = window.session_tabs.view, window.session_tabs.bridge
    _open(window, _logic(session_factory, packer_logic_factory, "2026-01-01_1", "A-1001", "SKU-AAA"),
          "2026-01-01_1")
    _settle(qtbot, bridge)
    window.switch_to_packer_mode()
    qtbot.waitUntil(
        lambda: window.stacked_widget.currentWidget() is window.packer_mode_widget,
        timeout=5000,
    )
    window._teardown_session()
    qtbot.waitUntil(
        lambda: window.stacked_widget.currentWidget() is window.session_widget,
        timeout=5000,
    )
    _settle(qtbot, bridge)
    assert "#A-1001" not in _eval(qtbot, view, "document.body.textContent")
    assert _eval(qtbot, view, "!document.getElementById('no-session').hidden") is True


def test_the_shortcuts_still_work_after_a_click_in_the_page(
    shown, qtbot, session_factory, packer_logic_factory, monkeypatch
):
    window = shown
    pages = window.session_tabs
    _open(window, _logic(session_factory, packer_logic_factory, "2026-01-01_1", "A-1001", "SKU-AAA"),
          "2026-01-01_1")
    _settle(qtbot, pages.bridge)
    ended = []
    monkeypatch.setattr(window, "end_session", lambda: ended.append(1))
    window.toolbar_end_btn.clicked.disconnect()
    window.toolbar_end_btn.clicked.connect(lambda: window.end_session())

    target = pages.view.focusProxy() or pages.view
    QTest.mouseClick(target, Qt.MouseButton.LeftButton, pos=target.rect().center())
    QTest.keyClick(window.windowHandle(), Qt.Key.Key_2, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: pages.currentIndex() == PAGE_STATISTICS, timeout=3000)
    QTest.keyClick(window.windowHandle(), Qt.Key.Key_1, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: pages.currentIndex() == PAGE_PACKING, timeout=3000)
    QTest.keyClick(window.windowHandle(), Qt.Key.Key_E, Qt.KeyboardModifier.ControlModifier)
    qtbot.waitUntil(lambda: ended == [1], timeout=3000)
```

- [ ] **Step 2: Run and see which fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_freshness.py`
Expected: `test_start_packing_waits_for_the_covered_page_to_paint` FAILS (`covered` is False). The two freshness cases should already pass on Task 8's work; if one fails, the push or the page is wrong, not the test: fix that.

- [ ] **Step 3: Implement**

In `MainWindow.__init__`, beside `self._leaving_packer_mode = False`, add `self._entering_packer_mode = False  # see switch_to_packer_mode()`.

Replace `switch_to_packer_mode`:

```python
    def switch_to_packer_mode(self):
        """Enter Packer Mode once the app document has painted itself empty.

        A hidden QWebEngineView keeps its last frame and shows it when it
        comes back. So the frame it keeps is the covered one, never orders
        that may be gone by then (ADR 0003): the document is told to draw
        nothing, and this waits for that paint, 150 ms at most.
        """
        if self._entering_packer_mode:
            return
        pages = self.session_tabs

        def enter():
            self._entering_packer_mode = False
            self.stacked_widget.setCurrentWidget(self.packer_mode_widget)
            self.packer_mode_widget.resume_scanner()
            self.packer_mode_widget.set_focus_to_scanner()

        if pages.view.isVisible():
            self._entering_packer_mode = True
            pages.bridge.set_covered(True)
            when_painted(pages.bridge, enter)
        else:
            enter()
```

In `_leave_packer_mode`'s `switch()`, uncover with the push:

```python
        def switch():
            self._leaving_packer_mode = False
            # Before the shell shows: what it shows is current (spec section 8).
            self._push_pages()
            self.session_tabs.bridge.set_covered(False)
            self.stacked_widget.setCurrentWidget(self.session_widget)
```

- [ ] **Step 4: Run the tests**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_app_freshness.py`
Expected: PASS.

If `test_the_shortcuts_still_work_after_a_click_in_the_page` fails because the web view swallows the keys (and not because the offscreen window never became active: check `window.isActiveWindow()` first, and call `window.activateWindow()` plus `qtbot.waitActive(window)` in the test if it is not), apply the spec's fallback (section 9): in `mount_app_page`, import `deny_focus` from `gui.packer_bridge`, call `deny_focus(view)` before `mount_page` and connect `view.page().loadFinished.connect(lambda _ok: deny_focus(view))`; change the docstring to say the view refuses the keyboard so the window's shortcuts always work; add row 18 to the spec's departures table ("order rows and sort heads are keyboard-reachable | mouse only | the web view would take the window's shortcuts"); and state it in the commit message. The test then passes unchanged.

- [ ] **Step 5: Run the suite and lint, then commit** (`feat: Packer Mode covers an emptied page; freshness and keyboard tests`)

---

### Task 11: Renders, docs and the bundle check

**Files:**
- Create: `scripts/render_app_pages.py`, `docs/design/ui-refresh/renders/phase3/*.png`
- Modify: `CONTEXT.md`, `.github/workflows/build-release.yml`

- [ ] **Step 1: Write `scripts/render_app_pages.py`**

```python
"""Offscreen renders of Packing and Statistics, mockup frames 3a-3g, 4a-4c, 5a, 5b.

    .venv/bin/python scripts/render_app_pages.py [output dir]

Writes <frame>-<theme>.png, by default into
docs/design/ui-refresh/renders/phase3/: 3a-3g and 4a-4c at 1366x768, 5a and 5b
at 1920x1080, in both themes. It builds a MainWindow against a throwaway
server with a synthetic 120-order list, and its own QSettings, so it touches
neither the file server nor this PC's saved theme, client or server path.

Offscreen Qt uses a fallback font for the Qt chrome: glyph widths differ a
little from Windows.
"""

import json
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

DEFAULT_OUT = ROOT / "docs" / "design" / "ui-refresh" / "renders" / "phase3"
SESSION_ID = "2026-10-07_1"
LIST_NAME = "Morning_wave"

CATALOGUE = [
    ("CLN-200", "Gel cleanser 200 ml"), ("TNR-150", "Toner 150 ml"),
    ("SER-30ML", "Vitamin C serum 30 ml"), ("HYA-15ML", "Hyaluronic serum 15 ml"),
    ("DAY-50ML", "Day cream 50 ml"), ("NGT-50ML", "Night cream 50 ml"),
    ("CRM-15ML", "Eye cream 15 ml"), ("SPF-50", "Sunscreen SPF 50"),
    ("LIP-RED", "Lip balm, red"), ("LIP-MNT", "Lip balm, mint"),
    ("LST-07", "Lipstick, shade 07"), ("LST-11", "Lipstick, shade 11"),
    ("NPL-04", "Nail polish, shade 04"), ("MSK-5PK", "Sheet mask, 5 pack"),
    ("OIL-100", "Body oil 100 ml"), ("BDL-400", "Body lotion 400 ml"),
    ("HND-75", "Hand cream 75 ml"), ("SHM-500", "Shampoo 500 ml"),
    ("CND-500", "Conditioner 500 ml"), ("EDT-FIG", "Fragrance mist, fig"),
    ("PAL-NUD", "Eyeshadow palette, nude"), ("GFT-L", "Gift box, large"),
    ("BRS-FND", "Brush, foundation"), ("MSC-BLK", "Mascara, black"),
]
COURIERS = ["DHL", "DPD", "Speedy"]


def synthetic_orders() -> list[dict]:
    """120 orders of 1 to 4 lines, the same every run."""
    orders = []
    for index in range(120):
        lines = 1 + (index * 7) % 4
        items = []
        for line in range(lines):
            sku, name = CATALOGUE[(index * 5 + line * 3) % len(CATALOGUE)]
            if any(item["sku"] == sku for item in items):
                continue
            items.append(
                {"sku": sku, "product_name": name, "quantity": 1 + (index + line) % 3 // 2}
            )
        orders.append(
            {
                "order_number": f"#{10400 + index}",
                "courier": COURIERS[index % 3],
                "items": items,
            }
        )
    return orders


def main(argv: list[str]) -> int:
    out = Path(argv[0]) if argv else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        # Before any QSettings is made, and both formats, as tests/conftest.py
        # does: QSettings(org, app) is NativeFormat, and a saved server path
        # outranks config.ini.
        for fmt in (QSettings.NativeFormat, QSettings.IniFormat):
            QSettings.setPath(fmt, QSettings.UserScope, str(tmp / "settings"))
        os.environ.pop("FULFILLMENT_SERVER_PATH", None)

        app = QApplication.instance() or QApplication(sys.argv[:1])
        from gui.app_bridge import session_payload, start_failure
        from gui.main_window import PAGE_PACKING, PAGE_STATISTICS, MainWindow
        from gui.theme import apply_theme, load_saved_theme
        from packing_tool.exceptions import PackingListInvalidError
        from packing_tool.packer_logic import PackerLogic
        from packing_tool.profile_manager import ProfileManager

        load_saved_theme(app)

        server = tmp / "server"
        server.mkdir()
        config = tmp / "config.ini"
        config.write_text(
            "[Network]\n"
            f"FileServerPath = {server}\n"
            "ConnectionTimeout = 5\n"
            f"LocalCachePath = {tmp / 'cache'}\n"
            "[Logging]\nLogLevel = WARNING\nLogRetentionDays = 30\nMaxLogSizeMB = 10\n",
            encoding="utf-8",
        )
        seed = ProfileManager(config_path=str(config))
        seed.create_client_profile("ACME", "Acme Cosmetics")

        session_dir = server / "Sessions" / "CLIENT_ACME" / SESSION_ID
        (session_dir / "packing_lists").mkdir(parents=True)
        work_dir = session_dir / "packing" / LIST_NAME
        work_dir.mkdir(parents=True)
        list_path = session_dir / "packing_lists" / f"{LIST_NAME}.json"
        list_path.write_text(
            json.dumps(
                {
                    "list_name": LIST_NAME,
                    "created_at": "2026-10-07T08:00:00+00:00",
                    "orders": synthetic_orders(),
                }
            ),
            encoding="utf-8",
        )

        window = MainWindow(skip_worker_selection=True, config_path=str(config))
        base = Path(window.profile_manager.base_path).resolve()
        if not base.is_relative_to(tmp.resolve()):
            raise RuntimeError(f"refusing to render against {base}: not the temp server")
        window.current_worker_name = "Desislava Ilieva"
        window.sidebar.set_worker(window.current_worker_name)
        # The connection card shows the mockup's path, not the temp folder.
        real_set = window.sidebar.set_connection
        window.sidebar.set_connection = lambda state, _path: real_set(state, r"\\fs01\packer")
        window._set_connection_state("ok")
        window.resize(1366, 768)
        window.show()
        pages = window.session_tabs
        bridge = pages.bridge

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

        def shoot(name: str, width: int = 1366, height: int = 768) -> None:
            for theme in ("light", "dark"):
                apply_theme(app, theme)
                window.resize(width, height)
                settle()
                target = out / f"{name}-{theme}.png"
                if not window.grab().save(str(target)):
                    raise OSError(f"could not write {target}")
                print(target)

        def open_session(complete: bool = False) -> PackerLogic:
            logic = PackerLogic(
                client_id="ACME", profile_manager=window.profile_manager,
                work_dir=str(work_dir),
            )
            logic.load_packing_list_json(list_path)
            numbers = list(logic.orders_data)
            state = logic.session_packing_state
            if complete:
                state["completed_orders"] = list(numbers)
            else:
                state["completed_orders"] = numbers[:38]
                state["skipped_orders"] = [numbers[44], numbers[57], numbers[71]]
                for number in (numbers[40], numbers[41]):
                    entries = logic._fresh_order_state(logic.orders_data[number]["items"])
                    entries[0]["packed"] = entries[0]["required"]
                    state["in_progress"][number] = entries
            window.logic = logic
            window.current_session_path = str(session_dir)
            window.current_packing_list = LIST_NAME
            window.enable_packing_mode()
            return logic

        def close_session(logic: PackerLogic) -> None:
            logic.close()
            window.logic = None
            window.current_session_path = None
            window.current_packing_list = None
            window._show_session(None)
            window.search_input.clear()
            bridge.set_session(session_payload())
            window._push_pages()

        window.client_combo.setCurrentIndex(window.client_combo.findData("ACME"))
        settle()

        # 3a, 4a: no session.
        pages.setCurrentIndex(PAGE_PACKING)
        shoot("3a")
        pages.setCurrentIndex(PAGE_STATISTICS)
        shoot("4a")
        pages.setCurrentIndex(PAGE_PACKING)

        # 3b: opening, step 2 of 3.
        bridge.set_session(
            session_payload("opening", list_name=LIST_NAME, session_id=SESSION_ID, step=2)
        )
        shoot("3b")

        # 3c: the packing list failed.
        title, text = start_failure(
            PackingListInvalidError("", ["courier"], ["items", "order_number"], "field"),
            LIST_NAME,
        )
        window._show_start_failure(title, text, LIST_NAME)
        shoot("3c")
        window._close_failure()

        # 3d to 3f, 4b, 5a, 5b: in progress.
        logic = open_session()
        shoot("3d")
        shoot("5a", 1920, 1080)
        window.search_input.setText("LST-07")
        shoot("3e")
        window.search_input.setText("99999")
        shoot("3f")
        window.search_input.clear()
        pages.setCurrentIndex(PAGE_STATISTICS)
        shoot("4b")
        shoot("5b", 1920, 1080)
        pages.setCurrentIndex(PAGE_PACKING)
        close_session(logic)

        # 3g, 4c: complete.
        logic = open_session(complete=True)
        shoot("3g")
        pages.setCurrentIndex(PAGE_STATISTICS)
        shoot("4c")
        close_session(logic)

        window.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 2: Render and look**

Run: `.venv/bin/python scripts/render_app_pages.py`
Expected: 24 PNGs in `docs/design/ui-refresh/renders/phase3/` (12 frames, two themes).

Open every PNG with the Read tool beside its mockup frame (open `docs/design/ui-refresh/mockups/Packer Screens.html` in Chrome if a browser tool is available; otherwise read the unpacked template). Check, in each theme: the strip's four or five cells and their rules; group rows in order; open rows on `surface_raised`; the hit row's blue rule in 3e; 3f's centred message; 3g's green banner and the primary *End session* in the bar; bars and the *Left* column in 4b and 4c; nothing clipped at 1366×768; the extra width going to the Product columns at 1920. Fix what differs and is not in the spec's departures table (section 11), re-render, and look again. If a difference has to stay, add it to that table.

- [ ] **Step 3: Docs**

`CONTEXT.md`:

- Add after **Packer bridge**:

```markdown
**App document** — the web page that draws the shell's pages: Packing and Statistics, and from phase 4 Sessions. One page in one web view (ADR 0003); Packer Mode's order document is a different page in its own view.

**App bridge** — the one `QWebChannel` object the app document talks to. It says which page shows, what the session is (none, opening, failed, open) and each page's numbers; the page reports clicks through slots.
```

- Replace the **Packing table view** entry with:

```markdown
**Order index** — the Packing page's table: orders grouped In progress, Not started, Packed, each row opening to its items. *Filter orders* narrows it by order number, SKU or product name and marks the item that matched.
```

- Replace the **Stat card** entry with:

```markdown
**KPI strip** — one card split into cells, each a label over a large number: Packing's totals strip and Statistics' KPI strip.
```

- **State panel**: append "On a web page it is a centred card drawn by the page."
- **Toast**: replace the entry's last clause so it reads: "A transient, non-blocking message for an outcome that needs no decision; failures are shown in the page or in a dialog. While the app document is on screen it draws the toast itself, bottom centre; elsewhere it is the Qt toast at the window's bottom right."
- **SKU roll-up**: leave as is (it already points at the SKU summary).

`.github/workflows/build-release.yml`: in the bundle check's list add `"app.html"` after `"packer.html"`, and extend the comment above it: "app.html is the same for the pages' document."

- [ ] **Step 4: Final checks**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`, then `.venv/bin/ruff check . --exclude shared`, then `graphify update .`
Expected: all pass.

Search for leftovers: `rg -n "order_tree|statistics_widget|StatisticsWidget|packing_state_panel|packing_summary_label|no_client_panel|order_summary|_populate_order_tree" --glob '!docs/**' --glob '!graphify-out/**'` returns nothing.

- [ ] **Step 5: Commit** (`docs: phase 3 renders, glossary and bundle check`), with the PNGs.

---

## For the PR (Stage C writes it; this is its content)

- Embed the 24 renders, each beside its frame id.
- Copy the departures table from spec section 11, with any row added during implementation.
- "For shared/": spec section 12.
- Needs a Windows check: a toast drawn by the page; Ctrl+1/2/3 and Ctrl+E after a click in the page; *Start packing* on a slow PC (the 150 ms cap).
