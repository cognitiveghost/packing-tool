# UI refresh phase 5 (Worker selection and SKU mapping on the web tier, and cleanup) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redraw Worker selection and SKU mapping as two full-window web pages, route Packer Mode's *Map SKU* and *Map barcode…* through the new SKU mapping page without losing a scan, delete the two Qt dialogs, and render every screen of the refresh at two sizes in both themes.

**Architecture:** A new web document, the **setup document** (`gui/web/setup.html`), draws both pages in one `QWebEngineView` that is the third widget of `MainWindow.stacked_widget`, beside the shell and Packer Mode. Pure functions and a `MappingEditor` class in `gui/setup_payload.py` decide every card, row and sentence; `gui/setup_bridge.py` (`SetupBridge`) is the `QWebChannel` object; `gui/setup_pages.py` (`SetupPages`, a `QWidget`) owns the view and every read and write to the server; `MainWindow` only switches the stack and replays stray scans.

**Tech Stack:** Python 3.14, PySide6 (Qt widgets, QtWebEngine, QWebChannel), plain HTML/CSS/JS with no build step, pytest with pytest-qt. No new dependency.

**Spec:** `docs/superpowers/specs/2026-10-09-ui-refresh-phase5-setup-pages-design.md`. Read it first, whole. ADRs: `docs/adr/0001-packer-mode-on-the-web-tier.md`, `0002-every-screen-on-the-web-tier.md`, `0003-the-shells-pages-are-one-web-document.md`, `0004-sku-mapping-takes-the-keyboard-from-packer-mode.md`. Mockups: `docs/design/ui-refresh/mockups/Worker Selection.html` and `SKU Mapping.html`; unpack them as `docs/design/ui-refresh/mockups/README.md` describes, into a folder outside the repo, and read each `template.html`.

## Global Constraints

- **Never edit a file under `shared/`.** A hook blocks it and CI diffs the folder. Read `shared/web_page.py`, `shared/web/kit.css`, `shared/web/page.js`; do not change them.
- **Web assets** (`gui/web/*`): colours only as `var(--token)` from `theme_css_vars()` (token `status_success_dot` is `--status-success-dot`), or `currentColor` / `transparent`. No hex, no colour names, no `px` font sizes (only `var(--type-*-size)`), no `transition`, `transform`, `opacity`, gradients. `box-shadow` only as `var(--card-shadow)`, `var(--overlay-shadow)` or `none`. No `style="..."` attribute in HTML. `tests/test_style_literals_guard.py` enforces this.
- **Type scale on the floor profile:** `--type-caption-size` 10pt, `--type-body-size` 12pt, `--type-heading-size` 14pt, `--type-display-size` 17pt, `--type-display-xl-size` 28pt. `--control-height` is 44px; `.btn.compact` is 40px.
- **Text into the page goes through `textContent`,** never `innerHTML`: worker names, barcodes and SKUs come from files and from the keyboard.
- **Qt code:** no colour literals.
- **Month and weekday names are never from `strftime`:** Qt can switch the process locale. Use the tables in `gui/setup_payload.py`.
- **Copy, verbatim** (typographic apostrophes and ellipses as written): "Select your profile", "Choose your worker profile to continue", "Quit", "Back to *name*", "New worker", "Name", "Create", "Cancel", "No workers yet", "Create a worker profile to start packing.", "Couldn’t load the worker list.", "Retry", "Current", "Opening…", "No sessions yet", "Just created", "Not active yet", "Enter a name.", "Use letters, numbers, spaces, dots, hyphens or apostrophes.", "There’s already a worker called *name*. Pick that card, or add a surname.", "SKU mapping", "Map product barcodes to internal SKUs. Changes are saved to the file server and reach every PC.", "Add mapping", "Search barcode or SKU", "Reload from server", "Product barcode", "Internal SKU", "Scan or type barcode", "Add", "Update", "Replace", "This barcode already maps to *SKU*.", " Replace it with *SKU*?", " Enter a SKU to replace it.", "No mappings yet", "Scan or type a product barcode to map it to a SKU.", "No mappings match “*text*”.", "Unsaved: ", "Saved. Every PC now uses these mappings.", "Save", "Delete this mapping?", "Delete", "Reload from server?", "Discard and reload", "Discard unsaved changes?", "Keep editing", "Discard", "Couldn’t save to the file server.", "Try again", "Couldn’t load the mappings.", "Back to packing", "Scanned in Packer Mode. Enter the SKU it should count as.", "Scan or type the barcode for this SKU.", "Not on this order. Pick one of the lines below.", "Not saved. Try again.", "Enter a barcode.", "Enter a SKU."
- **Sizes:** Worker selection: top row 60px, app mark 56px, card 240px wide and at least 168px tall, avatar 44px, grid gap 16px, at most 4 columns. SKU mapping: card 920px wide, 40px above and below, header 60px, footer 68px, body padding 20px 24px with 16px gaps, search 280px, columns `8px 240px 16px minmax(0, 1fr) 96px` with 12px gaps, row 44px, unsaved dot 7px.
- **Git:** `/usr/bin/git`, one plain git command per Bash call (no `&&`, `;`, `$VAR` paths). Commit with `/usr/bin/git commit -F <absolute path to a message file>`; write the message file with the Write tool, outside the repo. Never commit to `main`. Each commit message ends with the attribution lines your session gives you.
- **Tests:** run with `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q <path>`. If a hook refuses that, run the whole suite: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest`. Write test files with Write/Edit, never with shell redirection. If `.venv` is missing in the worktree: `ln -s /home/gloopy/Desktop/Projects/packing-tool/.venv .venv`.
- **Lint:** `.venv/bin/ruff check . --exclude shared` must pass before each commit.
- **QtWebEngine in tests:** `runJavaScript` cannot return a JS array; wrap every result in `JSON.stringify` (the `_eval` helper does). Never mark a Chromium test skip.
- **Production data** in `~/Desktop/production info/` is read-only and never committed or quoted.
- After the last code change of each task, run `graphify update .` (CLAUDE.md).
- Departures from the mockups are the twelve in spec section 11. If you make another, add it to that table in the same commit.
- **The code in this plan was written without running it.** When a test you were told to expect passing fails, find out why and fix the code or the test so the behaviour the spec states holds; do not weaken an assertion to get green.

## Review Focus

Inputs the spec implies that are most likely to bite a packer. Each has a test in the task named.

1. **A stray scan into the SKU field of *Map barcode…*** (the scanner types digits and Enter). Nothing is saved and the page stays (Task 7, `test_a_scan_into_the_sku_field_saves_nothing`).
2. **A worker, barcode or SKU that is markup** (`<img src=x>`). It is shown as text and creates no element (Task 5, `test_markup_in_a_worker_name_is_text` and `test_markup_in_a_sku_is_text`).
3. **A worker record with almost nothing in it** (no `last_active`, no `created_at`, an unparseable date, zero counts). The card builds and nothing raises (Task 1, `test_a_bare_worker_still_makes_a_card`).
4. **Another PC changed the mappings while this page was open.** Save sends only this PC's changes and the other PC's mapping survives (Task 4, `test_a_save_keeps_what_another_pc_mapped_meanwhile`).
5. **Two barcodes that differ only in punctuation or spaces** (`590-123` and `590123`). They are one key to the scan matcher, so the second is refused as already mapped (Task 2, `test_a_barcode_that_normalises_alike_collides`).

## File map

| File | Responsibility | Task |
|---|---|---|
| `packing_tool/profile_manager.py` | `load_sku_mapping(client_id, fresh=False)` | 1 |
| `gui/setup_payload.py` (new) | pure: worker cards and name rules (1); `MappingEditor`, mapping and quick payloads, `order_choices` (2) | 1, 2 |
| `gui/components/sidebar.py` | imports `initials` from `gui/setup_payload.py` | 1 |
| `gui/setup_bridge.py` (new) | `SetupBridge`, `mount_setup_page` | 3 |
| `gui/setup_pages.py` (new) | `SetupPages` | 4 |
| `gui/web/setup.html`, `setup.css`, `setup.js` (new) | skeletons (4); Worker selection, SKU mapping, the quick map, the stray-key listener (5) | 4, 5 |
| `gui/main_window.py` | the stack's third widget, startup, the two sidebar entries, the way back (6); the quick map, stray scans, lock loss (7) | 6, 7 |
| `gui/packer_mode_widget.py` | two `set_focus_to_scanner()` calls become conditional | 7 |
| `gui/sku_mapping_dialog.py`, `gui/worker_selection_dialog.py` | deleted | 6 |
| `scripts/render_args.py`, `scripts/render_setup.py`, `scripts/render_all.py` (new); the four `scripts/render_*.py` | renders | 8 |
| `docs/design/ui-refresh/renders/` | `final/` replaces `phase1` to `phase4` | 8 |
| `CONTEXT.md`, `README.md`, `docs/adr/0003-…md`, `docs/design/ui-refresh/for-shared.md` (new) | documents | 9 |

Names used across tasks:

- A worker is a `packing_tool.worker_manager.WorkerProfile`: attributes `id`, `name`, `created_at`, `total_sessions`, `total_orders`, `last_active` (ISO strings or `None`).
- A mapping is a `dict[str, str]`, barcode → SKU, as `ProfileManager.load_sku_mapping` returns it.
- A **quick** dict is what `quick_payload` returns (Task 2). `{}` means the page was opened from the sidebar.
- `normalize_sku` is `packing_tool.packer_logic.normalize_sku`: letters and digits only, lower case.

---

### Task 1: A fresh mapping read, and the worker cards

**Files:**
- Modify: `packing_tool/profile_manager.py` (`load_sku_mapping`, about line 465)
- Create: `gui/setup_payload.py`
- Modify: `gui/components/sidebar.py:47-49` (the `initials` function)
- Test: `tests/test_profile_manager.py`, `tests/test_setup_payload.py` (new)

**Interfaces:**
- Produces: `ProfileManager.load_sku_mapping(client_id: str, fresh: bool = False) -> dict[str, str]`.
- Produces, in `gui/setup_payload.py`: `initials(name: str) -> str`; `clean_worker_name(name) -> str`; `worker_name_problem(name, names: list[str]) -> str` (`""` when the name is fine); `last_active_text(when: datetime | None, now: datetime, created: datetime | None = None) -> str`; `workers_payload(workers, *, startup: bool, now: datetime, current_id: str = "", current_name: str = "", picked_id: str = "", failure: dict | None = None) -> dict`. `failure` is `{"cause": str, "path": str}`.

- [ ] **Step 1: Write the failing `ProfileManager` test**

Append to `tests/test_profile_manager.py`:

```python
def test_a_fresh_load_skips_the_cache(config_ini):
    pc1 = ProfileManager(config_path=str(config_ini))
    pc2 = ProfileManager(config_path=str(config_ini))
    pc1.create_client_profile("M", "M")
    assert pc2.load_sku_mapping("M") == {}
    pc1.update_sku_mapping("M", {"111": "SKU-1"})

    assert pc2.load_sku_mapping("M") == {}  # the cache, up to 60 s old
    assert pc2.load_sku_mapping("M", fresh=True) == {"111": "SKU-1"}
    assert pc2.load_sku_mapping("M") == {"111": "SKU-1"}  # and the cache was renewed
```

If `ProfileManager` is not already imported at the top of that file, add `from packing_tool.profile_manager import ProfileManager`.

- [ ] **Step 2: Run it and see it fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_profile_manager.py`
Expected: FAIL, `load_sku_mapping() got an unexpected keyword argument 'fresh'`.

- [ ] **Step 3: Add `fresh`**

In `packing_tool/profile_manager.py`, change the signature and the cache check of `load_sku_mapping`, and add one line to its docstring's Args:

```python
    def load_sku_mapping(self, client_id: str, fresh: bool = False) -> dict[str, str]:
```

```python
            fresh: Read the file even if a cached copy is under a minute old.
```

```python
        cache_key = f"sku_{client_id}"
        if not fresh and cache_key in self._sku_cache:
```

Nothing else in the method changes: a fresh read still stores its result in the cache.

- [ ] **Step 4: Run it and see it pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_profile_manager.py`
Expected: PASS.

- [ ] **Step 5: Write the failing worker-payload tests**

Create `tests/test_setup_payload.py`:

```python
"""The setup document's pure payloads: worker cards, name rules, the mapping editor."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from gui.setup_payload import (
    clean_worker_name,
    initials,
    last_active_text,
    worker_name_problem,
    workers_payload,
)

TZ = timezone(timedelta(hours=3))
NOW = datetime(2026, 10, 7, 14, 6, tzinfo=TZ)  # a Wednesday


def worker(worker_id, name, *, sessions=0, orders=0, last=None, created=None):
    return SimpleNamespace(
        id=worker_id, name=name, total_sessions=sessions, total_orders=orders,
        last_active=last, created_at=created,
    )


def ago(**delta) -> str:
    return (NOW - timedelta(**delta)).isoformat()


# --- last active ---------------------------------------------------------------


@pytest.mark.parametrize(
    "delta, expected",
    [
        ({"hours": 6, "minutes": 26}, "Last active Today, 07:40"),
        ({"days": 1}, "Last active Yesterday"),
        ({"days": 2}, "Last active Monday"),
        ({"days": 6}, "Last active Thursday"),
        ({"days": 7}, "Last active Last week"),
        ({"days": 13}, "Last active Last week"),
        ({"days": 14}, "Last active 23 Sep"),
        ({"days": 400}, "Last active 2 Sep 2025"),
    ],
)
def test_last_active_reads_as_the_mockup_writes_it(delta, expected):
    assert last_active_text(NOW - timedelta(**delta), NOW) == expected


def test_a_time_just_after_midnight_yesterday_is_yesterday_not_today():
    when = NOW.replace(hour=0, minute=5) - timedelta(days=1)
    assert last_active_text(when, NOW) == "Last active Yesterday"


def test_a_time_in_another_zone_is_read_in_ours():
    when = datetime(2026, 10, 7, 4, 40, tzinfo=timezone.utc)  # 07:40 at +03:00
    assert last_active_text(when, NOW) == "Last active Today, 07:40"


def test_a_worker_who_never_packed_is_just_created_for_an_hour():
    assert last_active_text(None, NOW, NOW - timedelta(minutes=59)) == "Just created"
    assert last_active_text(None, NOW, NOW - timedelta(minutes=61)) == "Not active yet"
    assert last_active_text(None, NOW) == "Not active yet"


# --- names ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, expected",
    [("Desislava Ilieva", "DI"), ("maria", "M"), ("Ana Maria de Souza", "AM"), ("", "")],
)
def test_initials(name, expected):
    assert initials(name) == expected


def test_a_name_is_trimmed_and_its_inner_spaces_collapsed():
    assert clean_worker_name("  Ana   Maria ") == "Ana Maria"
    assert clean_worker_name(None) == ""


@pytest.mark.parametrize("name", ["", "   ", None])
def test_an_empty_name_is_asked_for(name):
    assert worker_name_problem(name, []) == "Enter a name."


@pytest.mark.parametrize("name", ["Ivan!", "a/b", "<img src=x>", "Mar_ia", "Ana\tMaria@"])
def test_a_name_with_other_characters_says_which_are_allowed(name):
    assert worker_name_problem(name, []) == (
        "Use letters, numbers, spaces, dots, hyphens or apostrophes."
    )


@pytest.mark.parametrize("name", ["Ivan", "Мария", "Jean-Luc", "O'Neil", "J. R. 2", "Ana  Maria"])
def test_a_name_of_letters_digits_and_the_four_marks_passes(name):
    assert worker_name_problem(name, ["Petya"]) == ""


def test_a_duplicate_name_points_at_the_existing_card():
    assert worker_name_problem("  maria ", ["Ivan", "Maria"]) == (
        "There’s already a worker called Maria. Pick that card, or add a surname."
    )


# --- cards ---------------------------------------------------------------------


SIX = [
    worker("worker_002", "Maria", sessions=14, orders=1204, last=ago(days=1)),
    worker("worker_001", "Ivan", sessions=31, orders=2870, last=ago(hours=6, minutes=26)),
    worker("worker_005", "Zora"),
    worker("worker_004", "Elena", sessions=1, orders=1, last=ago(days=25)),
    worker("worker_006", "Boris"),
    worker("worker_003", "Georgi", sessions=22, orders=1951, last=ago(days=2)),
]


def test_cards_are_newest_first_then_the_never_active_by_name():
    payload = workers_payload(SIX, startup=True, now=NOW)
    assert [card["name"] for card in payload["cards"]] == [
        "Ivan", "Maria", "Georgi", "Elena", "Boris", "Zora",
    ]


def test_a_card_carries_its_lines():
    cards = {c["name"]: c for c in workers_payload(SIX, startup=True, now=NOW)["cards"]}
    assert cards["Ivan"] == {
        "id": "worker_001",
        "name": "Ivan",
        "initials": "I",
        "stats": "31 sessions · 2,870 orders",
        "last": "Last active Today, 07:40",
        "badge": "",
        "picked": False,
    }
    assert cards["Elena"]["stats"] == "1 session · 1 order"
    assert cards["Zora"]["stats"] == "No sessions yet"
    assert cards["Zora"]["last"] == "Not active yet"


def test_at_startup_the_way_out_is_quit():
    payload = workers_payload(SIX, startup=True, now=NOW, current_id="worker_001")
    assert payload["context"] == "startup"
    assert payload["leave"] == "Quit"
    assert payload["mode"] == "ready" and payload["error"] == {}
    assert all(card["badge"] == "" for card in payload["cards"])


def test_switching_names_the_worker_to_go_back_to_and_marks_their_card():
    payload = workers_payload(
        SIX, startup=False, now=NOW, current_id="worker_001", current_name="Ivan"
    )
    assert payload["context"] == "switch"
    assert payload["leave"] == "Back to Ivan"
    badges = {card["name"]: card["badge"] for card in payload["cards"]}
    assert badges["Ivan"] == "Current" and badges["Maria"] == ""


def test_the_picked_card_says_opening_even_when_it_is_the_current_one():
    payload = workers_payload(
        SIX, startup=False, now=NOW, current_id="worker_001", current_name="Ivan",
        picked_id="worker_001",
    )
    ivan = next(card for card in payload["cards"] if card["name"] == "Ivan")
    assert ivan["badge"] == "Opening…" and ivan["picked"] is True


def test_no_workers_is_ready_with_no_cards():
    payload = workers_payload([], startup=True, now=NOW)
    assert payload["mode"] == "ready" and payload["cards"] == []


def test_a_failed_load_carries_the_cause_and_the_path():
    payload = workers_payload(
        [], startup=False, now=NOW, current_name="Ivan",
        failure={"cause": "permission denied", "path": r"\\fs01\fulfilment\Workers"},
    )
    assert payload["mode"] == "failed"
    assert payload["cards"] == []
    assert payload["leave"] == "Back to Ivan"
    assert payload["error"] == {
        "title": "Couldn’t load the worker list.",
        "text": "Permission denied.",
        "path": r"\\fs01\fulfilment\Workers",
    }


def test_a_bare_worker_still_makes_a_card():
    bare = SimpleNamespace(
        id="worker_009", name="X", total_sessions=None, total_orders=None,
        last_active="not a date", created_at="",
    )
    card = workers_payload([bare], startup=True, now=NOW)["cards"][0]
    assert card["stats"] == "No sessions yet"
    assert card["last"] == "Not active yet"
```

- [ ] **Step 6: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_setup_payload.py`
Expected: FAIL at import, `No module named 'gui.setup_payload'`.

- [ ] **Step 7: Write `gui/setup_payload.py`**

```python
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
```

- [ ] **Step 8: Run them and see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_setup_payload.py`
Expected: PASS. If `test_a_bare_worker_still_makes_a_card` fails because `parse_timestamp("not a date")` raises something other than `TypeError` or `ValueError`, read `shared/metadata_utils.py:33` and catch what it raises (do not edit `shared/`).

- [ ] **Step 9: Point the sidebar at the moved `initials`**

In `gui/components/sidebar.py` delete the `initials` function (lines 47 to 49) and add this import with the other `gui` imports at the top of the file:

```python
from gui.setup_payload import initials
```

`tests/test_sidebar.py` imports `initials` from `gui.components.sidebar` and keeps working through this import. If ruff reports the import unused-looking (F401), it is not: `set_worker` calls it.

- [ ] **Step 10: Run the suite, lint, commit**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_sidebar.py tests/test_setup_payload.py tests/test_profile_manager.py`
Expected: PASS.
Run: `.venv/bin/ruff check . --exclude shared`
Expected: no findings.
Run: `graphify update .`

Commit `packing_tool/profile_manager.py`, `gui/setup_payload.py`, `gui/components/sidebar.py`, `tests/test_profile_manager.py`, `tests/test_setup_payload.py` with the message "Setup payloads: worker cards and name rules; a fresh mapping read".

---

### Task 2: The mapping editor and its payloads

**Files:**
- Modify: `gui/setup_payload.py` (append)
- Test: `tests/test_setup_payload.py` (append), `tests/test_packer_mode_widget.py` (two tests move out)

**Interfaces:**
- Consumes: `packing_tool.packer_logic.normalize_sku(sku) -> str`.
- Produces, in `gui/setup_payload.py`:
  - `clean_mapping(barcode, sku) -> tuple[str, str]`: barcode with all whitespace removed, SKU trimmed.
  - `class MappingEditor`: `MappingEditor(mapping: dict | None = None)`; attribute `rows: list[dict]` (each `{"id": int, "barcode": str, "sku": str}`); methods `loaded(mapping) -> None`, `add(barcode, sku) -> str`, `update(row_id, barcode, sku) -> str`, `replace(row_id, barcode, sku) -> str`, `delete(row_id) -> None`, `clash(barcode, row_id=0) -> dict | None`, `status(row) -> str`, `counts() -> dict` (`{"added", "edited", "deleted"}`), `summary() -> str`, `changes() -> tuple[dict[str, str], list[str]]`.
  - `mapping_error(kind: str, cause: str, path: str, changes: int = 0) -> dict` with `kind` one of `"save"`, `"load"`, `"quick"`.
  - `mapping_payload(editor, *, client: str, saved: bool = False, error: dict | None = None, quick: dict | None = None, failed: bool = False) -> dict`.
  - `order_choices(order_state) -> list[dict]` (each `{"sku", "label", "key"}`).
  - `quick_payload(kind: str, *, sku: str = "", barcode: str = "", choices=()) -> dict`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_setup_payload.py` (add the names to the import from `gui.setup_payload` at the top: `MappingEditor`, `clean_mapping`, `mapping_error`, `mapping_payload`, `order_choices`, `quick_payload`):

```python
# --- the mapping editor ----------------------------------------------------------


READ = {"222": "SKU-B", "111": "SKU-A", "333": "SKU-C"}


def pairs(editor):
    return [(row["barcode"], row["sku"]) for row in editor.rows]


def row_id(editor, barcode):
    return next(row["id"] for row in editor.rows if row["barcode"] == barcode)


def test_what_was_read_is_listed_by_barcode_and_is_not_a_change():
    editor = MappingEditor(READ)
    assert pairs(editor) == [("111", "SKU-A"), ("222", "SKU-B"), ("333", "SKU-C")]
    assert editor.counts() == {"added": 0, "edited": 0, "deleted": 0}
    assert editor.summary() == ""
    assert editor.changes() == ({}, [])
    assert [editor.status(row) for row in editor.rows] == ["", "", ""]


def test_an_added_row_goes_on_top_and_is_new():
    editor = MappingEditor(READ)
    assert editor.add(" 44 4 ", "  Sku-d ") == ""
    assert pairs(editor)[0] == ("444", "Sku-d")  # barcode loses its spaces; SKU kept as typed
    assert editor.status(editor.rows[0]) == "new"
    assert editor.counts() == {"added": 1, "edited": 0, "deleted": 0}
    assert editor.summary() == "1 added"
    assert editor.changes() == ({"444": "Sku-d"}, [])


def test_ids_are_never_reused():
    editor = MappingEditor(READ)
    editor.add("444", "D")
    first = editor.rows[0]["id"]
    editor.delete(first)
    editor.add("555", "E")
    assert editor.rows[0]["id"] != first


@pytest.mark.parametrize(
    "barcode, sku, sentence",
    [
        ("", "X", "Enter a barcode."),
        (" - ", "X", "Enter a barcode."),
        ("444", "  ", "Enter a SKU."),
        ("111", "X", "This barcode already maps to SKU-A."),
    ],
)
def test_add_says_what_is_wrong_and_changes_nothing(barcode, sku, sentence):
    editor = MappingEditor(READ)
    assert editor.add(barcode, sku) == sentence
    assert len(editor.rows) == 3


def test_a_barcode_that_normalises_alike_collides():
    editor = MappingEditor({"590-123": "SKU-A"})
    assert editor.add("590123", "SKU-B") == "This barcode already maps to SKU-A."
    assert editor.clash("590 123")["sku"] == "SKU-A"
    assert editor.clash("590124") is None


def test_an_edited_sku_is_edited_and_edited_back_is_not():
    editor = MappingEditor(READ)
    target = row_id(editor, "222")
    assert editor.update(target, "222", "SKU-B2") == ""
    assert editor.status(editor.rows[1]) == "edited"
    assert editor.summary() == "1 edited"
    assert editor.changes() == ({"222": "SKU-B2"}, [])
    assert editor.update(target, "222", "SKU-B") == ""
    assert editor.counts() == {"added": 0, "edited": 0, "deleted": 0}


def test_an_edited_barcode_is_one_added_and_one_deleted_and_keeps_its_place():
    editor = MappingEditor(READ)
    assert editor.update(row_id(editor, "222"), "229", "SKU-B") == ""
    assert pairs(editor)[1] == ("229", "SKU-B")
    assert editor.counts() == {"added": 1, "edited": 0, "deleted": 1}
    assert editor.summary() == "1 added, 1 deleted"
    assert editor.changes() == ({"229": "SKU-B"}, ["222"])


def test_update_refuses_a_collision_but_not_with_itself():
    editor = MappingEditor(READ)
    target = row_id(editor, "222")
    assert editor.update(target, "111", "X") == "This barcode already maps to SKU-A."
    assert editor.update(target, "2-22", "SKU-B") == ""  # its own key
    assert editor.update(9999, "888", "X") == "That mapping is no longer in the list."


def test_replace_from_a_new_draft_gives_the_sku_to_the_row_that_has_the_barcode():
    editor = MappingEditor(READ)
    assert editor.replace(0, "111", "SKU-NEW") == ""
    assert pairs(editor)[0] == ("111", "SKU-NEW")
    assert len(editor.rows) == 3
    assert editor.summary() == "1 edited"


def test_replace_from_an_edited_row_removes_that_row():
    editor = MappingEditor(READ)
    assert editor.replace(row_id(editor, "222"), "111", "SKU-B") == ""
    assert pairs(editor) == [("111", "SKU-B"), ("333", "SKU-C")]
    assert editor.summary() == "1 edited, 1 deleted"
    assert editor.changes() == ({"111": "SKU-B"}, ["222"])


def test_replace_with_no_collision_is_an_add_or_an_update():
    editor = MappingEditor(READ)
    assert editor.replace(0, "444", "SKU-D") == ""
    assert pairs(editor)[0] == ("444", "SKU-D")
    assert editor.replace(0, "555", " ") == "Enter a SKU."


def test_delete_and_the_summary_of_all_three():
    editor = MappingEditor(READ)
    editor.add("444", "SKU-D")
    editor.update(row_id(editor, "111"), "111", "SKU-A2")
    editor.delete(row_id(editor, "333"))
    editor.delete(424242)  # not there: nothing happens
    assert editor.summary() == "1 added, 1 edited, 1 deleted"
    assert editor.changes() == ({"444": "SKU-D", "111": "SKU-A2"}, ["333"])


def test_a_new_row_deleted_again_leaves_nothing_to_save():
    editor = MappingEditor(READ)
    editor.add("444", "SKU-D")
    editor.delete(editor.rows[0]["id"])
    assert editor.changes() == ({}, [])


def test_loaded_starts_over():
    editor = MappingEditor(READ)
    editor.add("444", "SKU-D")
    editor.loaded({"9": "Z"})
    assert pairs(editor) == [("9", "Z")]
    assert editor.summary() == ""


def test_clean_mapping():
    assert clean_mapping(" 59 01\t2 ", "  Crm 50 ") == ("59012", "Crm 50")
    assert clean_mapping(None, None) == ("", "")


# --- the mapping page's payload ------------------------------------------------


def test_a_clean_list_is_not_dirty_and_carries_keys():
    payload = mapping_payload(MappingEditor({"590-1": "SKU-A"}), client="ACME")
    assert payload == {
        "client": "ACME",
        "mode": "ready",
        "rows": [{"id": 1, "barcode": "590-1", "sku": "SKU-A", "key": "5901", "status": ""}],
        "dirty": False,
        "changes": 0,
        "summary": "",
        "lost": "",
        "saved": False,
        "error": {},
        "quick": {},
    }


def test_unsaved_changes_are_counted_and_say_what_would_be_lost():
    editor = MappingEditor(READ)
    editor.add("444", "SKU-D")
    editor.add("555", "SKU-E")
    editor.update(row_id(editor, "111"), "111", "SKU-A2")
    payload = mapping_payload(editor, client="ACME", saved=True)
    assert payload["dirty"] is True and payload["changes"] == 3
    assert payload["summary"] == "2 added, 1 edited"
    assert payload["lost"] == "Your 3 unsaved changes (2 added, 1 edited) will be lost."
    assert payload["saved"] is False  # saved is only true with nothing unsaved
    assert [row["status"] for row in payload["rows"]][:2] == ["new", "new"]


def test_one_unsaved_change_is_singular():
    editor = MappingEditor(READ)
    editor.delete(row_id(editor, "111"))
    assert mapping_payload(editor, client="A")["lost"] == (
        "Your 1 unsaved change (1 deleted) will be lost."
    )


def test_saved_shows_while_nothing_is_unsaved():
    assert mapping_payload(MappingEditor(READ), client="A", saved=True)["saved"] is True


def test_a_failed_load_has_no_rows():
    error = mapping_error("load", "Permission denied", r"\\fs01\x\packer_config.json")
    payload = mapping_payload(MappingEditor(), client="A", error=error, failed=True)
    assert payload["mode"] == "failed" and payload["rows"] == []
    assert payload["error"] == {
        "title": "Couldn’t load the mappings.",
        "text": "The list could not be read from the file server.",
        "cause": "Permission denied",
        "path": r"\\fs01\x\packer_config.json",
        "action": "load",
    }


def test_the_save_error_counts_the_changes_it_kept():
    assert mapping_error("save", "c", "p", 3)["text"] == (
        "Your 3 changes are still here and nothing on the server changed."
    )
    assert mapping_error("save", "c", "p", 1)["text"] == (
        "Your 1 change is still here and nothing on the server changed."
    )
    assert mapping_error("save", "c", "p", 3)["title"] == "Couldn’t save to the file server."
    assert mapping_error("save", "c", "p", 3)["action"] == "save"


def test_the_quick_error_has_no_button():
    error = mapping_error("quick", "c", "p")
    assert error["title"] == "Couldn’t save to the file server."
    assert error["text"] == "Nothing on the server changed."
    assert error["action"] == ""


# --- the quick map ---------------------------------------------------------------


def test_the_choices_put_the_lines_that_still_need_scans_first():
    state = [
        {"original_sku": "A-1", "packed": 2, "required": 2},
        {"original_sku": "B-2", "packed": 0, "required": 1},
        {"original_sku": "C-3", "packed": 1, "required": 4},
    ]
    assert order_choices(state) == [
        {"sku": "B-2", "label": "B-2 — 0 / 1 packed", "key": "b2"},
        {"sku": "C-3", "label": "C-3 — 1 / 4 packed", "key": "c3"},
        {"sku": "A-1", "label": "A-1 — 2 / 2 packed", "key": "a1"},
    ]


def test_the_choices_are_empty_when_there_is_no_order():
    assert order_choices(None) == []
    assert order_choices([]) == []


def test_a_quick_map_for_a_known_sku_waits_for_a_barcode():
    assert quick_payload("sku", sku="SER-30ML") == {
        "kind": "sku",
        "sku": "SER-30ML",
        "barcode": "",
        "hint": "Scan or type the barcode for this SKU.",
        "choices": [],
    }


def test_a_quick_map_for_a_known_barcode_offers_the_order_lines():
    choices = [{"sku": "B-2", "label": "B-2 — 0 / 1 packed", "key": "b2"}]
    assert quick_payload("barcode", barcode="5906", choices=choices) == {
        "kind": "barcode",
        "sku": "",
        "barcode": "5906",
        "hint": "Scanned in Packer Mode. Enter the SKU it should count as.",
        "choices": choices,
    }
```

In `tests/test_packer_mode_widget.py`, delete the two tests `test_the_pick_list_puts_the_lines_that_still_need_scans_first` and `test_the_pick_list_is_empty_when_there_is_no_order` (the two above replace them) and change the import on line 8 from `from gui.main_window import _session_seconds, _unmapped_choices` to `from gui.main_window import _session_seconds`. `_unmapped_choices` itself stays in `gui/main_window.py` until Task 7.

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_setup_payload.py`
Expected: FAIL at import, `cannot import name 'MappingEditor'`.

- [ ] **Step 3: Append the editor and the payloads to `gui/setup_payload.py`**

Add `from packing_tool.packer_logic import normalize_sku` to the imports (after `from typing import Any`, before the `shared` import), then append:

```python
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
```

- [ ] **Step 4: Run them and see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_setup_payload.py tests/test_packer_mode_widget.py`
Expected: PASS.

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check . --exclude shared`
Run: `graphify update .`

Commit `gui/setup_payload.py`, `tests/test_setup_payload.py`, `tests/test_packer_mode_widget.py` with the message "Setup payloads: the mapping editor, the mapping page and the quick map".

---

### Task 3: `SetupBridge`

**Files:**
- Create: `gui/setup_bridge.py`
- Test: `tests/test_setup_bridge.py` (new)

**Interfaces:**
- Consumes: `shared.web_page.PageBridge`, `shared.web_page.mount_page(view, bridge, page, channel_name, *, tokens)`, `gui.theme.current_tokens`.
- Produces: `class SetupBridge(PageBridge)`:
  - properties `page: str`, `workers: dict`, `mapping: dict`, with setters `set_page(name)`, `set_workers(payload)`, `set_mapping(payload)`;
  - JS-facing signal `leaveAsked()`;
  - slots and the Python-facing signals they emit: `pickWorker(str)` → `workerPicked(str)`; `retryWorkers()` → `workersRetryRequested()`; `leaveWorkers()` → `workersLeaveRequested()`; `deleteMapping(int)` → `mappingDeleteRequested(int)`; `reloadMappings()` → `mappingReloadRequested()`; `saveMappings()` → `mappingSaveRequested()`; `closeMapping()` → `mappingCloseRequested()`; `strayScan(str)` → `strayScanned(str)`;
  - answering slots, each returning `self.answer(<slot name>, *args)`: `createWorker(str) -> str`, `addMapping(str, str) -> str`, `updateMapping(int, str, str) -> str`, `replaceMapping(int, str, str) -> str`;
  - attribute `answer`: a callable `(name: str, *args) -> str`, by default returning `""`.
- Produces: `mount_setup_page(view: QWebEngineView) -> SetupBridge`; constants `PAGE`, `CHANNEL_NAME = "setup"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_setup_bridge.py`:

```python
"""SetupBridge: what crosses between Python and the setup document."""

from gui.setup_bridge import CHANNEL_NAME, PAGE, SetupBridge


def test_it_starts_drawing_nothing(qapp):
    bridge = SetupBridge()
    assert bridge.page == ""
    assert bridge.workers == {} and bridge.mapping == {}
    assert PAGE.name == "setup.html" and CHANNEL_NAME == "setup"


def test_a_setter_that_changes_something_notifies_and_raises_the_revision(qapp):
    bridge = SetupBridge()
    seen = []
    bridge.pageChanged.connect(lambda: seen.append("page"))
    bridge.workersChanged.connect(lambda: seen.append("workers"))
    bridge.mappingChanged.connect(lambda: seen.append("mapping"))
    before = bridge.revision

    bridge.set_page("workers")
    bridge.set_workers({"mode": "ready"})
    bridge.set_mapping({"client": "ACME"})

    assert seen == ["page", "workers", "mapping"]
    assert bridge.revision == before + 3
    assert bridge.page == "workers"
    assert bridge.workers == {"mode": "ready"} and bridge.mapping == {"client": "ACME"}


def test_a_setter_that_changes_nothing_is_silent(qapp):
    bridge = SetupBridge()
    bridge.set_workers({"mode": "ready"})
    before = bridge.revision
    bridge.set_page("")
    bridge.set_workers({"mode": "ready"})
    bridge.set_mapping({})
    bridge.set_mapping(None)
    assert bridge.revision == before


def test_the_reporting_slots_emit_their_signals(qapp):
    bridge = SetupBridge()
    seen = []
    bridge.workerPicked.connect(lambda worker_id: seen.append(("pick", worker_id)))
    bridge.workersRetryRequested.connect(lambda: seen.append("retry"))
    bridge.workersLeaveRequested.connect(lambda: seen.append("leave"))
    bridge.mappingDeleteRequested.connect(lambda row_id: seen.append(("delete", row_id)))
    bridge.mappingReloadRequested.connect(lambda: seen.append("reload"))
    bridge.mappingSaveRequested.connect(lambda: seen.append("save"))
    bridge.mappingCloseRequested.connect(lambda: seen.append("close"))
    bridge.strayScanned.connect(lambda text: seen.append(("stray", text)))

    bridge.pickWorker("worker_001")
    bridge.retryWorkers()
    bridge.leaveWorkers()
    bridge.deleteMapping(7)
    bridge.reloadMappings()
    bridge.saveMappings()
    bridge.closeMapping()
    bridge.strayScan("4006381333931")

    assert seen == [
        ("pick", "worker_001"), "retry", "leave", ("delete", 7), "reload", "save", "close",
        ("stray", "4006381333931"),
    ]


def test_the_answering_slots_return_what_the_answer_callable_returns(qapp):
    bridge = SetupBridge()
    calls = []

    def answer(name, *args):
        calls.append((name, args))
        return f"said {name}"

    bridge.answer = answer
    assert bridge.createWorker("Ivan") == "said createWorker"
    assert bridge.addMapping("111", "A") == "said addMapping"
    assert bridge.updateMapping(3, "111", "A") == "said updateMapping"
    assert bridge.replaceMapping(0, "111", "A") == "said replaceMapping"
    assert calls == [
        ("createWorker", ("Ivan",)),
        ("addMapping", ("111", "A")),
        ("updateMapping", (3, "111", "A")),
        ("replaceMapping", (0, "111", "A")),
    ]


def test_with_no_answer_set_the_answering_slots_do_nothing(qapp):
    bridge = SetupBridge()
    assert bridge.createWorker("Ivan") == ""
    assert bridge.addMapping("111", "A") == ""
```

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_setup_bridge.py`
Expected: FAIL at import, `No module named 'gui.setup_bridge'`.

- [ ] **Step 3: Write `gui/setup_bridge.py`**

```python
"""The setup document's bridge (ADR 0002, ADR 0004).

One web document draws the two full-window pages: Worker selection and SKU
mapping. State Python owns crosses as a notify property; what the page
reports crosses as a slot. Four slots answer, because the page must know
whether to clear what was typed: they return "" when the thing was done,
else the sentence to show beside the field.

Spec: docs/superpowers/specs/2026-10-09-ui-refresh-phase5-setup-pages-design.md
"""

from pathlib import Path

from PySide6.QtCore import Property, Signal, Slot
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.theme import current_tokens
from shared.web_page import PageBridge, mount_page

PAGE = Path(__file__).resolve().parent / "web" / "setup.html"
CHANNEL_NAME = "setup"


class SetupBridge(PageBridge):
    pageChanged = Signal()
    workersChanged = Signal()
    mappingChanged = Signal()

    # JS-facing: raise the "Discard unsaved changes?" question (section 6.6).
    leaveAsked = Signal()

    # Python-facing: what the page reported.
    workerPicked = Signal(str)
    workersRetryRequested = Signal()
    workersLeaveRequested = Signal()
    mappingDeleteRequested = Signal(int)
    mappingReloadRequested = Signal()
    mappingSaveRequested = Signal()
    mappingCloseRequested = Signal()
    strayScanned = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._page = ""
        self._workers: dict = {}
        self._mapping: dict = {}
        # Set by SetupPages: (slot name, *args) -> "" or a sentence.
        self.answer = lambda name, *args: ""

    # --- out: Python -> JS -------------------------------------------------

    def _get_page(self) -> str:
        return self._page

    page = Property(str, _get_page, notify=pageChanged)

    def _get_workers(self) -> dict:
        return self._workers

    workers = Property("QVariantMap", _get_workers, notify=workersChanged)

    def _get_mapping(self) -> dict:
        return self._mapping

    mapping = Property("QVariantMap", _get_mapping, notify=mappingChanged)

    # --- in: JS -> Python --------------------------------------------------

    @Slot(str)
    def pickWorker(self, worker_id) -> None:
        self.workerPicked.emit(str(worker_id))

    @Slot()
    def retryWorkers(self) -> None:
        self.workersRetryRequested.emit()

    @Slot()
    def leaveWorkers(self) -> None:
        self.workersLeaveRequested.emit()

    @Slot(str, result=str)
    def createWorker(self, name) -> str:
        return str(self.answer("createWorker", str(name)))

    @Slot(str, str, result=str)
    def addMapping(self, barcode, sku) -> str:
        return str(self.answer("addMapping", str(barcode), str(sku)))

    @Slot(int, str, str, result=str)
    def updateMapping(self, row_id, barcode, sku) -> str:
        return str(self.answer("updateMapping", int(row_id), str(barcode), str(sku)))

    @Slot(int, str, str, result=str)
    def replaceMapping(self, row_id, barcode, sku) -> str:
        return str(self.answer("replaceMapping", int(row_id), str(barcode), str(sku)))

    @Slot(int)
    def deleteMapping(self, row_id) -> None:
        self.mappingDeleteRequested.emit(int(row_id))

    @Slot()
    def reloadMappings(self) -> None:
        self.mappingReloadRequested.emit()

    @Slot()
    def saveMappings(self) -> None:
        self.mappingSaveRequested.emit()

    @Slot()
    def closeMapping(self) -> None:
        self.mappingCloseRequested.emit()

    @Slot(str)
    def strayScan(self, text) -> None:
        self.strayScanned.emit(str(text))

    # --- Python-facing API -------------------------------------------------
    # A setter that changes nothing emits nothing, so an idle push does not
    # raise the revision.

    def set_page(self, name: str) -> None:
        if name != self._page:
            self._page = str(name)
            self.pageChanged.emit()

    def set_workers(self, payload: dict | None) -> None:
        payload = dict(payload or {})
        if payload != self._workers:
            self._workers = payload
            self.workersChanged.emit()

    def set_mapping(self, payload: dict | None) -> None:
        payload = dict(payload or {})
        if payload != self._mapping:
            self._mapping = payload
            self.mappingChanged.emit()


def mount_setup_page(view: QWebEngineView) -> SetupBridge:
    """Load the setup document into `view` and return the bridge it talks to.

    The view keeps its focus policy: both pages have text fields. Packer
    Mode's view is the one that refuses the keyboard (ADR 0001).
    """
    bridge = SetupBridge(view)
    mount_page(view, bridge, PAGE, CHANNEL_NAME, tokens=current_tokens)
    return bridge
```

- [ ] **Step 4: Run them and see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_setup_bridge.py`
Expected: PASS. `mount_setup_page` is not exercised until Task 4 creates `setup.html`.

- [ ] **Step 5: Lint and commit**

Run: `.venv/bin/ruff check . --exclude shared`
Run: `graphify update .`

Commit `gui/setup_bridge.py`, `tests/test_setup_bridge.py` with the message "SetupBridge: the setup document's channel object".

---

### Task 4: `SetupPages`

**Files:**
- Create: `gui/setup_pages.py`
- Create: `gui/web/setup.html`, `gui/web/setup.css`, `gui/web/setup.js` (skeletons; Task 5 fills them)
- Test: `tests/test_setup_pages.py` (new)

**Interfaces:**
- Consumes: Task 1 to 3's names; `WorkerManager.get_all_workers()`, `.create_worker(name)`, `.workers_dir`; `ProfileManager.load_sku_mapping(client, fresh=True)`, `.update_sku_mapping(client, add, remove)`, `.clients_dir`; `packing_tool.profile_manager.ProfileManagerError`; `packing_tool.session_details.error_cause(error) -> str`; `shared.web_page.when_painted(bridge, callback)`.
- Produces: `class SetupPages(QWidget)`:
  - `SetupPages(worker_manager, profile_manager, parent=None, *, now=None)`; attributes `view`, `bridge`.
  - `show_workers(current_id: str = "", current_name: str = "", *, startup: bool) -> None`
  - `show_mapping(client_id: str, client_label: str, quick: dict | None = None) -> None`
  - `blank() -> None`, `dirty() -> bool`, `ask_leave() -> None`
  - signals `workerChosen(str, str)`, `quitRequested()`, `backRequested()`, `mappingSaved(object)`, `quickMapped(str, str, str, object)` (kind, barcode, SKU, the whole mapping), `strayScanned(str)`.

- [ ] **Step 1: Create the three skeleton web files**

`mount_setup_page` reads `gui/web/setup.html` when a `SetupPages` is built, so the file must exist before any test of this task can run. Task 5 replaces all three.

`gui/web/setup.html`:

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Packer Assistant</title>
<!-- shared/web_page.mount_page writes theme_css_vars() over the marker in the
     style element below before the page loads; setup.js keeps it current. -->
<style id="theme-vars">/* theme-vars */</style>
<link rel="stylesheet" href="../../shared/web/kit.css">
<link rel="stylesheet" href="floor.css">
<link rel="stylesheet" href="setup.css">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="../../shared/web/page.js"></script>
<script src="setup.js" defer></script>
</head>
<body>
<div class="setup" id="setup"></div>
</body>
</html>
```

`gui/web/setup.css`:

```css
/* The setup document's own sheet (UI refresh phase 5): Worker selection and
   SKU mapping. Filled in by the next task. */

.setup { position: relative; height: 100%; overflow: hidden; }
```

`gui/web/setup.js`:

```js
// The setup document: Worker selection and SKU mapping. Filled in by the
// next task; this much connects the bridge and reports paints.
"use strict";

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.setup;
  window.setupBridge = bridge;
  const themeVars = document.getElementById("theme-vars");
  const onTheme = function () { themeVars.textContent = bridge.themeCss; };
  onTheme();
  bridge.themeCssChanged.connect(onTheme);
  reportPaints(bridge);
  document.documentElement.dataset.bridge = "ready";
});
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_setup_pages.py`:

```python
"""SetupPages: what the two setup pages read from and write to the server.

A real bridge, a real WorkerManager and ProfileManager over a temp folder.
Nothing here asserts on Chromium: tests/test_setup_page_web.py does.
"""

from datetime import datetime, timedelta, timezone

import pytest

from gui.setup_pages import SetupPages
from gui.setup_payload import quick_payload
from packing_tool.profile_manager import ProfileManager, ProfileManagerError
from packing_tool.worker_manager import WorkerManager

NOW = datetime(2026, 10, 7, 14, 6, tzinfo=timezone(timedelta(hours=3)))
CHOICES = [
    {"sku": "SER-30ML", "label": "SER-30ML — 0 / 2 packed", "key": "ser30ml"},
    {"sku": "CRM-50ML", "label": "CRM-50ML — 1 / 1 packed", "key": "crm50ml"},
]


@pytest.fixture
def workers(profile_manager):
    return WorkerManager(str(profile_manager.base_path))


@pytest.fixture
def pages(profile_manager, workers, qtbot):
    profile_manager.create_client_profile("ACME", "Acme")
    profile_manager.update_sku_mapping("ACME", {"111": "SKU-A", "222": "SKU-B"})
    widget = SetupPages(workers, profile_manager, now=lambda: NOW)
    qtbot.addWidget(widget)
    return widget


def rows(pages):
    return [(row["barcode"], row["sku"]) for row in pages.bridge.mapping["rows"]]


def row_id(pages, barcode):
    return next(r["id"] for r in pages.bridge.mapping["rows"] if r["barcode"] == barcode)


# --- Worker selection ------------------------------------------------------------


def test_show_workers_pushes_the_cards_and_the_page(pages, workers):
    workers.create_worker("Ivan")
    workers.create_worker("Maria")
    pages.show_workers(startup=True)
    assert pages.bridge.page == "workers"
    payload = pages.bridge.workers
    assert payload["context"] == "startup" and payload["leave"] == "Quit"
    assert sorted(card["name"] for card in payload["cards"]) == ["Ivan", "Maria"]


def test_the_switch_context_marks_the_current_worker(pages, workers):
    ivan = workers.create_worker("Ivan")
    pages.show_workers(ivan.id, "Ivan", startup=False)
    payload = pages.bridge.workers
    assert payload["leave"] == "Back to Ivan"
    assert payload["cards"][0]["badge"] == "Current"


def test_an_unreadable_worker_list_is_the_failed_shape_and_retry_recovers(pages, workers):
    workers.workers_file.mkdir()  # open() on a directory raises OSError
    pages.show_workers(startup=True)
    payload = pages.bridge.workers
    assert payload["mode"] == "failed"
    assert payload["error"]["title"] == "Couldn’t load the worker list."
    assert payload["error"]["path"] == str(workers.workers_dir)

    workers.workers_file.rmdir()
    workers.create_worker("Ivan")
    pages.bridge.retryWorkers()
    assert pages.bridge.workers["mode"] == "ready"
    assert [card["name"] for card in pages.bridge.workers["cards"]] == ["Ivan"]


def test_picking_a_card_marks_it_and_then_emits_the_worker(pages, workers, qtbot):
    ivan = workers.create_worker("Ivan")
    pages.show_workers(startup=True)
    with qtbot.waitSignal(pages.workerChosen, timeout=3000) as caught:
        pages.bridge.pickWorker(ivan.id)
        card = pages.bridge.workers["cards"][0]
        assert card["badge"] == "Opening…" and card["picked"] is True
    assert caught.args == [ivan.id, "Ivan"]


def test_picking_an_unknown_id_does_nothing(pages, workers, qtbot):
    workers.create_worker("Ivan")
    pages.show_workers(startup=True)
    with qtbot.assertNotEmitted(pages.workerChosen, wait=400):
        pages.bridge.pickWorker("worker_999")


def test_a_second_pick_while_one_is_opening_is_ignored(pages, workers, qtbot):
    ivan = workers.create_worker("Ivan")
    maria = workers.create_worker("Maria")
    pages.show_workers(startup=True)
    chosen = []
    pages.workerChosen.connect(lambda worker_id, name: chosen.append(name))
    pages.bridge.pickWorker(ivan.id)
    pages.bridge.pickWorker(maria.id)
    qtbot.waitUntil(lambda: bool(chosen), timeout=3000)
    qtbot.wait(300)
    assert chosen == ["Ivan"]


@pytest.mark.parametrize(
    "name, sentence",
    [
        ("  ", "Enter a name."),
        ("Ivan!", "Use letters, numbers, spaces, dots, hyphens or apostrophes."),
        ("ivan", "There’s already a worker called Ivan. Pick that card, or add a surname."),
    ],
)
def test_create_returns_the_sentence_and_creates_nothing(pages, workers, name, sentence):
    workers.create_worker("Ivan")
    pages.show_workers(startup=True)
    assert pages.bridge.createWorker(name) == sentence
    assert len(workers.get_all_workers()) == 1


def test_create_makes_the_worker_and_signs_them_in(pages, workers, qtbot):
    pages.show_workers(startup=True)
    with qtbot.waitSignal(pages.workerChosen, timeout=3000) as caught:
        assert pages.bridge.createWorker("  Ana   Maria ") == ""
    created = workers.get_all_workers()
    assert [w.name for w in created] == ["Ana Maria"]
    assert caught.args == [created[0].id, "Ana Maria"]
    card = pages.bridge.workers["cards"][0]
    assert card["name"] == "Ana Maria" and card["badge"] == "Opening…"


def test_a_name_another_pc_took_meanwhile_gets_the_duplicate_sentence(pages, workers):
    pages.show_workers(startup=True)  # an empty list is on screen
    workers.create_worker("Ivan")  # another PC
    assert pages.bridge.createWorker("Ivan") == (
        "There’s already a worker called Ivan. Pick that card, or add a surname."
    )
    assert [card["name"] for card in pages.bridge.workers["cards"]] == ["Ivan"]


def test_a_server_error_on_create_is_said(pages, workers, monkeypatch):
    pages.show_workers(startup=True)

    def boom(name):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(workers, "create_worker", boom)
    assert pages.bridge.createWorker("Ivan") == "Couldn’t create the worker: input/output error."


def test_leave_is_quit_at_startup_and_back_otherwise(pages, qtbot):
    pages.show_workers(startup=True)
    with qtbot.waitSignal(pages.quitRequested, timeout=1000):
        pages.bridge.leaveWorkers()
    pages.show_workers("worker_001", "Ivan", startup=False)
    with qtbot.waitSignal(pages.backRequested, timeout=1000):
        pages.bridge.leaveWorkers()


# --- SKU mapping -------------------------------------------------------------------


def test_show_mapping_pushes_the_rows_and_the_page(pages):
    pages.show_mapping("ACME", "Acme")
    assert pages.bridge.page == "mapping"
    payload = pages.bridge.mapping
    assert payload["client"] == "Acme" and payload["mode"] == "ready"
    assert rows(pages) == [("111", "SKU-A"), ("222", "SKU-B")]
    assert payload["dirty"] is False and payload["quick"] == {}
    assert pages.dirty() is False


def test_show_mapping_reads_the_server_not_the_cache(pages, profile_manager, config_ini):
    profile_manager.load_sku_mapping("ACME")  # cached
    ProfileManager(config_path=str(config_ini)).update_sku_mapping("ACME", {"333": "SKU-C"})
    pages.show_mapping("ACME", "Acme")
    assert ("333", "SKU-C") in rows(pages)


def test_the_slots_edit_the_list_without_touching_the_server(pages, profile_manager):
    pages.show_mapping("ACME", "Acme")
    bridge = pages.bridge
    assert bridge.addMapping("444", "SKU-D") == ""
    assert bridge.updateMapping(row_id(pages, "111"), "111", "SKU-A2") == ""
    bridge.deleteMapping(row_id(pages, "222"))
    assert rows(pages) == [("444", "SKU-D"), ("111", "SKU-A2")]
    assert bridge.mapping["summary"] == "1 added, 1 edited, 1 deleted"
    assert pages.dirty() is True
    assert profile_manager.load_sku_mapping("ACME", fresh=True) == {"111": "SKU-A", "222": "SKU-B"}


def test_a_refused_add_returns_the_sentence(pages):
    pages.show_mapping("ACME", "Acme")
    assert pages.bridge.addMapping("111", "X") == "This barcode already maps to SKU-A."
    assert pages.bridge.replaceMapping(0, "111", "X") == ""
    assert ("111", "X") in rows(pages)


def test_save_writes_the_changes_and_says_saved(pages, profile_manager, qtbot):
    pages.show_mapping("ACME", "Acme")
    pages.bridge.addMapping("444", "SKU-D")
    pages.bridge.deleteMapping(row_id(pages, "222"))
    with qtbot.waitSignal(pages.mappingSaved, timeout=1000) as caught:
        pages.bridge.saveMappings()
    expected = {"111": "SKU-A", "444": "SKU-D"}
    assert caught.args == [expected]
    assert profile_manager.load_sku_mapping("ACME", fresh=True) == expected
    payload = pages.bridge.mapping
    assert payload["saved"] is True and payload["dirty"] is False
    assert pages.dirty() is False


def test_a_save_keeps_what_another_pc_mapped_meanwhile(pages, profile_manager, config_ini):
    pages.show_mapping("ACME", "Acme")
    pages.bridge.addMapping("444", "SKU-D")
    ProfileManager(config_path=str(config_ini)).update_sku_mapping("ACME", {"999": "SKU-Z"})
    pages.bridge.saveMappings()
    saved = profile_manager.load_sku_mapping("ACME", fresh=True)
    assert saved == {"111": "SKU-A", "222": "SKU-B", "444": "SKU-D", "999": "SKU-Z"}
    assert ("999", "SKU-Z") in rows(pages)  # the page shows what the server holds now


def test_save_with_nothing_unsaved_writes_nothing(pages, profile_manager, monkeypatch):
    pages.show_mapping("ACME", "Acme")
    calls = []
    monkeypatch.setattr(profile_manager, "update_sku_mapping", lambda *a, **k: calls.append(a))
    pages.bridge.saveMappings()
    assert calls == []


def test_a_failed_save_shows_the_banner_and_keeps_the_rows(pages, profile_manager, monkeypatch):
    pages.show_mapping("ACME", "Acme")
    pages.bridge.addMapping("444", "SKU-D")

    def boom(*args, **kwargs):
        raise ProfileManagerError("Could not save the SKU mapping to the file server: boom")

    monkeypatch.setattr(profile_manager, "update_sku_mapping", boom)
    pages.bridge.saveMappings()
    payload = pages.bridge.mapping
    assert payload["error"]["title"] == "Couldn’t save to the file server."
    assert payload["error"]["text"] == (
        "Your 1 change is still here and nothing on the server changed."
    )
    assert payload["error"]["cause"].endswith("boom")
    assert payload["error"]["path"].endswith("packer_config.json")
    assert payload["error"]["action"] == "save"
    assert payload["dirty"] is True and ("444", "SKU-D") in rows(pages)

    monkeypatch.undo()
    pages.bridge.saveMappings()  # Try again
    assert pages.bridge.mapping["error"] == {} and pages.bridge.mapping["saved"] is True


def test_reload_drops_the_edits_and_reads_fresh(pages, profile_manager, config_ini):
    pages.show_mapping("ACME", "Acme")
    pages.bridge.addMapping("444", "SKU-D")
    ProfileManager(config_path=str(config_ini)).update_sku_mapping("ACME", {"999": "SKU-Z"})
    pages.bridge.reloadMappings()
    assert rows(pages) == [("111", "SKU-A"), ("222", "SKU-B"), ("999", "SKU-Z")]
    assert pages.bridge.mapping["dirty"] is False


def test_a_load_that_fails_is_the_failed_shape_and_retry_recovers(
    pages, profile_manager, monkeypatch
):
    def boom(client_id, fresh=False):
        raise ProfileManagerError("Could not read the SKU mapping from the file server: boom")

    monkeypatch.setattr(profile_manager, "load_sku_mapping", boom)
    pages.show_mapping("ACME", "Acme")
    payload = pages.bridge.mapping
    assert payload["mode"] == "failed" and payload["rows"] == []
    assert payload["error"]["title"] == "Couldn’t load the mappings."
    assert payload["error"]["action"] == "load"

    monkeypatch.undo()
    pages.bridge.reloadMappings()
    assert pages.bridge.mapping["mode"] == "ready"
    assert rows(pages) == [("111", "SKU-A"), ("222", "SKU-B")]


def test_close_emits_back(pages, qtbot):
    pages.show_mapping("ACME", "Acme")
    with qtbot.waitSignal(pages.backRequested, timeout=1000):
        pages.bridge.closeMapping()


def test_ask_leave_reaches_the_page(pages, qtbot):
    with qtbot.waitSignal(pages.bridge.leaveAsked, timeout=1000):
        pages.ask_leave()


def test_a_stray_scan_is_passed_on(pages, qtbot):
    with qtbot.waitSignal(pages.strayScanned, timeout=1000) as caught:
        pages.bridge.strayScan("4006381333931")
    assert caught.args == ["4006381333931"]


def test_blank_empties_everything(pages):
    pages.show_mapping("ACME", "Acme")
    pages.bridge.addMapping("444", "SKU-D")
    pages.blank()
    assert pages.bridge.page == ""
    assert pages.bridge.mapping == {} and pages.bridge.workers == {}
    assert pages.dirty() is False


# --- the quick map (ADR 0004) --------------------------------------------------------


def test_a_quick_map_for_a_sku_writes_the_scanned_barcode_at_once(
    pages, profile_manager, qtbot
):
    pages.show_mapping("ACME", "Acme", quick_payload("sku", sku="SER-30ML"))
    assert pages.bridge.mapping["quick"]["kind"] == "sku"
    with qtbot.waitSignal(pages.quickMapped, timeout=1000) as caught:
        # Whatever is sent as the SKU is ignored: the SKU is fixed.
        assert pages.bridge.addMapping(" 5906 0001 ", "ignored") == ""
    expected = {"111": "SKU-A", "222": "SKU-B", "59060001": "SER-30ML"}
    assert caught.args == ["sku", "59060001", "SER-30ML", expected]
    assert profile_manager.load_sku_mapping("ACME", fresh=True) == expected
    assert pages.dirty() is False


def test_a_quick_map_for_a_barcode_takes_only_a_sku_on_the_order(
    pages, profile_manager, qtbot
):
    quick = quick_payload("barcode", barcode="5906", choices=CHOICES)
    pages.show_mapping("ACME", "Acme", quick)
    with qtbot.assertNotEmitted(pages.quickMapped):
        # A stray scan: a barcode typed into the SKU field.
        assert pages.bridge.addMapping("5906", "4006381333931") == (
            "Not on this order. Pick one of the lines below."
        )
    assert "5906" not in profile_manager.load_sku_mapping("ACME", fresh=True)

    with qtbot.waitSignal(pages.quickMapped, timeout=1000) as caught:
        # Typed loosely: saved with the order's own spelling.
        assert pages.bridge.addMapping("something else", "ser 30ml") == ""
    assert caught.args[:3] == ["barcode", "5906", "SER-30ML"]
    assert profile_manager.load_sku_mapping("ACME", fresh=True)["5906"] == "SER-30ML"


def test_a_quick_map_onto_a_mapped_barcode_needs_replace(pages, profile_manager, qtbot):
    pages.show_mapping("ACME", "Acme", quick_payload("sku", sku="SER-30ML"))
    with qtbot.assertNotEmitted(pages.quickMapped):
        assert pages.bridge.addMapping("111", "") == "This barcode already maps to SKU-A."
    with qtbot.waitSignal(pages.quickMapped, timeout=1000):
        assert pages.bridge.replaceMapping(0, "111", "") == ""
    assert profile_manager.load_sku_mapping("ACME", fresh=True)["111"] == "SER-30ML"


def test_a_quick_replace_of_a_barcode_spelled_differently_removes_the_old_spelling(
    pages, profile_manager
):
    profile_manager.update_sku_mapping("ACME", {"590-1": "OLD"})
    pages.show_mapping("ACME", "Acme", quick_payload("sku", sku="NEW"))
    assert pages.bridge.replaceMapping(0, "5901", "") == ""
    saved = profile_manager.load_sku_mapping("ACME", fresh=True)
    assert saved["5901"] == "NEW" and "590-1" not in saved


def test_a_quick_map_with_no_barcode_is_asked_for_one(pages):
    pages.show_mapping("ACME", "Acme", quick_payload("sku", sku="SER-30ML"))
    assert pages.bridge.addMapping("  ", "") == "Enter a barcode."


def test_a_quick_map_that_cannot_be_saved_says_so_and_stays(
    pages, profile_manager, monkeypatch, qtbot
):
    pages.show_mapping("ACME", "Acme", quick_payload("sku", sku="SER-30ML"))

    def boom(*args, **kwargs):
        raise ProfileManagerError("Could not save the SKU mapping to the file server: boom")

    monkeypatch.setattr(profile_manager, "update_sku_mapping", boom)
    with qtbot.assertNotEmitted(pages.quickMapped):
        assert pages.bridge.addMapping("5906", "") == "Not saved. Try again."
    error = pages.bridge.mapping["error"]
    assert error["title"] == "Couldn’t save to the file server." and error["action"] == ""
    assert pages.bridge.page == "mapping"


def test_a_quick_map_does_nothing_else(pages, profile_manager, monkeypatch):
    pages.show_mapping("ACME", "Acme", quick_payload("sku", sku="SER-30ML"))
    before = rows(pages)
    calls = []
    monkeypatch.setattr(profile_manager, "update_sku_mapping", lambda *a, **k: calls.append(a))
    assert pages.bridge.updateMapping(row_id(pages, "111"), "111", "X") == ""
    pages.bridge.deleteMapping(row_id(pages, "111"))
    pages.bridge.saveMappings()
    assert rows(pages) == before and calls == []
```

- [ ] **Step 3: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_setup_pages.py`
Expected: FAIL at import, `No module named 'gui.setup_pages'`.

- [ ] **Step 4: Write `gui/setup_pages.py`**

```python
"""The two full-window pages: Worker selection and SKU mapping (ADR 0002).

One QWebEngineView showing the setup document. This widget is everything
the two pages read from or write to the server; MainWindow only switches to
it and away from it. gui/setup_payload.py decides what the pages say.

Spec: docs/superpowers/specs/2026-10-09-ui-refresh-phase5-setup-pages-design.md
"""

import logging
from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from gui.setup_bridge import mount_setup_page
from gui.setup_payload import (
    MappingEditor,
    clean_mapping,
    clean_worker_name,
    mapping_error,
    mapping_payload,
    worker_name_problem,
    workers_payload,
)
from packing_tool.packer_logic import normalize_sku
from packing_tool.profile_manager import ProfileManagerError
from packing_tool.session_details import error_cause
from shared.web_page import when_painted

logger = logging.getLogger(__name__)


class SetupPages(QWidget):
    workerChosen = Signal(str, str)  # id, name; after "Opening…" has painted
    quitRequested = Signal()
    backRequested = Signal()  # leave, with nothing to report
    mappingSaved = Signal(object)  # the whole mapping, after a Save
    quickMapped = Signal(str, str, str, object)  # kind, barcode, SKU, the whole mapping
    strayScanned = Signal(str)

    def __init__(self, worker_manager, profile_manager, parent=None, *, now=None) -> None:
        super().__init__(parent)
        self._worker_manager = worker_manager
        self._profile_manager = profile_manager
        self._now = now or (lambda: datetime.now().astimezone())

        self.view = QWebEngineView(self)
        self.bridge = mount_setup_page(self.view)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

        # Worker selection
        self._startup = False
        self._current_id = ""
        self._current_name = ""
        self._workers: list = []
        self._picked = ""
        # SKU mapping
        self._client = ""
        self._label = ""
        self._quick: dict = {}
        self._editor = MappingEditor()
        self._failed = False
        self._saved = False
        self._error: dict = {}

        bridge = self.bridge
        bridge.answer = self._answer
        bridge.workerPicked.connect(self._pick)
        bridge.workersRetryRequested.connect(self._load_workers)
        bridge.workersLeaveRequested.connect(self._leave_workers)
        bridge.mappingDeleteRequested.connect(self._delete)
        bridge.mappingReloadRequested.connect(self._reload)
        bridge.mappingSaveRequested.connect(self._save)
        bridge.mappingCloseRequested.connect(self.backRequested.emit)
        bridge.strayScanned.connect(self.strayScanned.emit)

    def _answer(self, name: str, *args) -> str:
        handlers = {
            "createWorker": self._create_worker,
            "addMapping": self._add,
            "updateMapping": self._update,
            "replaceMapping": self._replace,
        }
        return handlers[name](*args)

    def blank(self) -> None:
        """Draw nothing, and forget both pages' state."""
        self.bridge.set_page("")
        self._workers, self._picked = [], ""
        self._quick, self._editor = {}, MappingEditor()
        self._failed, self._saved, self._error = False, False, {}
        self.bridge.set_workers({})
        self.bridge.set_mapping({})

    # --- Worker selection ----------------------------------------------------

    def show_workers(self, current_id: str = "", current_name: str = "", *, startup: bool) -> None:
        self._startup = bool(startup)
        self._current_id, self._current_name = str(current_id or ""), str(current_name or "")
        self._picked = ""
        self._load_workers()
        self.bridge.set_page("workers")

    def _load_workers(self) -> None:
        # ponytail: read on the UI thread, as the dialog did; one small file.
        failure = None
        try:
            self._workers = self._worker_manager.get_all_workers()
        except Exception as error:
            logger.exception("Could not load the worker list")
            self._workers = []
            failure = {
                "cause": error_cause(error),
                "path": str(self._worker_manager.workers_dir),
            }
        self._push_workers(failure)

    def _push_workers(self, failure: dict | None = None) -> None:
        self.bridge.set_workers(
            workers_payload(
                self._workers,
                startup=self._startup,
                now=self._now(),
                current_id=self._current_id,
                current_name=self._current_name,
                picked_id=self._picked,
                failure=failure,
            )
        )

    def _pick(self, worker_id: str) -> None:
        worker = next((w for w in self._workers if w.id == worker_id), None)
        if worker is None or self._picked:
            return
        self._picked = worker.id
        self._push_workers()
        # The packer sees "Opening…" before the page goes (spec section 5.3).
        when_painted(self.bridge, lambda: self.workerChosen.emit(worker.id, worker.name))

    def _create_worker(self, name: str) -> str:
        problem = worker_name_problem(name, [w.name for w in self._workers])
        if problem:
            return problem
        try:
            worker = self._worker_manager.create_worker(clean_worker_name(name))
        except ValueError:
            # Another PC took the name since this list was read.
            self._load_workers()
            return worker_name_problem(name, [w.name for w in self._workers]) or (
                "That name can’t be used."
            )
        except Exception as error:
            logger.exception("Could not create the worker")
            return f"Couldn’t create the worker: {error_cause(error)}."
        self._workers = [*self._workers, worker]
        self._pick(worker.id)
        return ""

    def _leave_workers(self) -> None:
        if self._startup:
            self.quitRequested.emit()
        else:
            self.backRequested.emit()

    # --- SKU mapping -----------------------------------------------------------

    def show_mapping(self, client_id: str, client_label: str, quick: dict | None = None) -> None:
        self._client, self._label = str(client_id), str(client_label)
        self._quick = dict(quick or {})
        self._load_mapping()
        self.bridge.set_page("mapping")

    def dirty(self) -> bool:
        """Whether leaving now would lose unsaved changes."""
        return (
            self.bridge.page == "mapping"
            and not self._quick
            and sum(self._editor.counts().values()) > 0
        )

    def ask_leave(self) -> None:
        self.bridge.leaveAsked.emit()

    def _mapping_path(self) -> str:
        folder = self._profile_manager.clients_dir / f"CLIENT_{self._client}"
        return str(folder / "packer_config.json")

    def _load_mapping(self) -> None:
        # ponytail: read on the UI thread, as the dialog did; one small file.
        self._saved = False
        try:
            mapping = self._profile_manager.load_sku_mapping(self._client, fresh=True)
        except ProfileManagerError as error:
            logger.exception("Could not load the SKU mapping")
            self._editor = MappingEditor()
            self._failed = True
            self._error = mapping_error("load", str(error), self._mapping_path())
        else:
            self._editor = MappingEditor(mapping)
            self._failed = False
            self._error = {}
        self._push_mapping()

    def _push_mapping(self) -> None:
        self.bridge.set_mapping(
            mapping_payload(
                self._editor,
                client=self._label,
                saved=self._saved,
                error=self._error,
                quick=self._quick,
                failed=self._failed,
            )
        )

    def _changed(self, problem: str) -> str:
        if not problem:
            self._saved = False
            self._push_mapping()
        return problem

    def _add(self, barcode: str, sku: str) -> str:
        if self._quick:
            return self._quick_add(barcode, sku, replace=False)
        return self._changed(self._editor.add(barcode, sku))

    def _update(self, row_id: int, barcode: str, sku: str) -> str:
        if self._quick:
            return ""
        return self._changed(self._editor.update(row_id, barcode, sku))

    def _replace(self, row_id: int, barcode: str, sku: str) -> str:
        if self._quick:
            return self._quick_add(barcode, sku, replace=True)
        return self._changed(self._editor.replace(row_id, barcode, sku))

    def _delete(self, row_id: int) -> None:
        if self._quick:
            return
        self._editor.delete(row_id)
        self._changed("")

    def _reload(self) -> None:
        if not self._quick:
            self._load_mapping()

    def _save(self) -> None:
        if self._quick:
            return
        add, remove = self._editor.changes()
        if not add and not remove:
            return
        changes = sum(self._editor.counts().values())
        try:
            mapping = self._profile_manager.update_sku_mapping(self._client, add, remove)
        except ProfileManagerError as error:
            self._error = mapping_error("save", str(error), self._mapping_path(), changes)
            self._push_mapping()
            return
        self._editor.loaded(mapping)
        self._error = {}
        self._saved = True
        self._push_mapping()
        self.mappingSaved.emit(mapping)

    def _quick_add(self, barcode: str, sku: str, *, replace: bool) -> str:
        """The one add of a quick map: written at once (ADR 0004)."""
        quick = self._quick
        barcode, sku = clean_mapping(barcode, sku)
        if quick["kind"] == "sku":
            sku = quick["sku"]
        else:
            barcode = quick["barcode"]
            choice = next(
                (c for c in quick["choices"] if c["key"] == normalize_sku(sku)), None
            )
            if not normalize_sku(sku) or choice is None:
                return "Not on this order. Pick one of the lines below."
            sku = choice["sku"]
        if not normalize_sku(barcode):
            return "Enter a barcode."
        clash = self._editor.clash(barcode)
        remove: list[str] = []
        if clash is not None and normalize_sku(clash["sku"]) != normalize_sku(sku):
            if not replace:
                return f"This barcode already maps to {clash['sku']}."
            if clash["barcode"] != barcode:
                remove = [clash["barcode"]]
        try:
            mapping = self._profile_manager.update_sku_mapping(
                self._client, {barcode: sku}, remove
            )
        except ProfileManagerError as error:
            logger.exception("Could not save the quick mapping")
            self._error = mapping_error("quick", str(error), self._mapping_path())
            self._push_mapping()
            return "Not saved. Try again."
        self.quickMapped.emit(quick["kind"], barcode, sku, mapping)
        return ""
```

- [ ] **Step 5: Run them and see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_setup_pages.py`
Expected: PASS. Each `workerChosen` test waits out `when_painted`'s 150 ms timeout, because a view that is not shown never paints; the log line "SetupBridge did not report revision …" in those tests is expected.

If `test_a_server_error_on_create_is_said` fails on the wording, read `packing_tool/session_details.py:33` (`error_cause`): it lower-cases the first letter of `strerror` and drops a final full stop. Keep the test's sentence; fix the code path, not the assertion.

- [ ] **Step 6: Lint and commit**

Run: `.venv/bin/ruff check . --exclude shared`
Run: `graphify update .`

Commit `gui/setup_pages.py`, `gui/web/setup.html`, `gui/web/setup.css`, `gui/web/setup.js`, `tests/test_setup_pages.py` with the message "SetupPages: the two setup pages' reads and writes".

---

### Task 5: The setup document

**Files:**
- Replace: `gui/web/setup.html`, `gui/web/setup.css`, `gui/web/setup.js`
- Create: `tests/setup_web.py` (helpers), `tests/test_setup_page_web.py`

**Interfaces:**
- Consumes: `SetupBridge` (Task 3) through the channel object named `setup`; the payload shapes of `workers_payload`, `mapping_payload`, `quick_payload` (Tasks 1 and 2); `reportPaints(bridge)` from `shared/web/page.js`.
- Produces: the page. Element ids other tasks' tests and the render script rely on: `workers`, `mapping`, `w-leave`, `w-grid`, `w-new`, `w-form`, `w-name`, `w-name-error`, `w-failed`, `w-retry`, `w-create`, `w-cancel`, `m-client`, `m-add`, `m-empty-add`, `d-clash-text`, `d-hint`, `m-search`, `m-count`, `m-reload`, `m-rows`, `m-draft`, `d-barcode`, `d-sku`, `d-commit`, `d-replace`, `d-problem`, `d-choices`, `m-save`, `m-cancel`, `m-close`, `m-ask`, `m-ask-yes`, `m-ask-no`, `m-error`, `m-error-action`. Cards carry `data-worker="<id>"`, rows `data-row="<id>"`, row buttons `data-row-action="edit|delete"` with `data-id`, choices `data-choice="<sku>"`. `window.setupBridge` is the bridge, for the test harness. `document.documentElement.dataset.bridge` is `"ready"` after the first render.
- Produces, in `tests/setup_web.py`: `eval_js(qtbot, view, expr, timeout=5000)`, `until_js(qtbot, view, expr, timeout_s=20)`, `run_js(qtbot, view, code)`, `shown(view, qtbot, element_id)`, `text(view, qtbot, element_id)`, `click(view, qtbot, element_id)`, `set_value(view, qtbot, element_id, value)`, `press(view, qtbot, element_id, key, ctrl=False)`, `settle(qtbot, bridge)`, `mounted(qtbot)`.

- [ ] **Step 1: Write the test helpers**

Create `tests/setup_web.py`:

```python
"""Helpers for driving the setup document in a real Chromium."""

import json
import time

import pytest
from PySide6.QtWebEngineWidgets import QWebEngineView
from pytestqt.exceptions import TimeoutError as QtBotTimeoutError

from gui.setup_bridge import mount_setup_page


def eval_js(qtbot, view, expr, timeout=5000):
    # runJavaScript cannot marshal a JS array back; route everything through JSON.
    box = []
    view.page().runJavaScript(f"JSON.stringify({expr})", 0, box.append)
    qtbot.waitUntil(lambda: bool(box), timeout=timeout)
    return json.loads(box[0])


def until_js(qtbot, view, expr, timeout_s=20):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        remaining = max(int((deadline - time.monotonic()) * 1000), 50)
        try:
            if eval_js(qtbot, view, expr, timeout=min(remaining, 5000)) is True:
                return
        except (QtBotTimeoutError, ValueError):
            continue
        qtbot.wait(50)
    pytest.fail(f"never became true in the page: {expr}")


def run_js(qtbot, view, code):
    """Run statements in the page."""
    return eval_js(qtbot, view, f"(function () {{ {code}; return true; }})()")


def shown(view, qtbot, element_id):
    """Visible: neither it nor an ancestor is hidden."""
    return eval_js(
        qtbot, view,
        f"(function () {{ const n = document.getElementById('{element_id}');"
        " return !!n && !n.closest('[hidden]'); })()",
    )


def text(view, qtbot, element_id):
    return eval_js(qtbot, view, f"document.getElementById('{element_id}').textContent")


def click(view, qtbot, element_id):
    run_js(qtbot, view, f"document.getElementById('{element_id}').click()")


def set_value(view, qtbot, element_id, value):
    """Type into an input the way a person does: the value, then an input event."""
    run_js(
        qtbot, view,
        f"const n = document.getElementById('{element_id}'); n.focus();"
        f" n.value = {json.dumps(value)};"
        " n.dispatchEvent(new Event('input', {bubbles: true}))",
    )


def press(view, qtbot, element_id, key, ctrl=False):
    """A keydown on an element ('' for the document body)."""
    target = f"document.getElementById('{element_id}')" if element_id else "document.body"
    run_js(
        qtbot, view,
        f"{target}.dispatchEvent(new KeyboardEvent('keydown',"
        f" {{key: {json.dumps(key)}, ctrlKey: {str(bool(ctrl)).lower()},"
        " bubbles: true, cancelable: true}))",
    )


def settle(qtbot, bridge):
    qtbot.waitUntil(lambda: bridge.painted_revision >= bridge.revision, timeout=20000)


def mounted(qtbot):
    """A shown view with the setup document loaded: (view, bridge)."""
    view = QWebEngineView()
    qtbot.addWidget(view)
    view.resize(1366, 768)
    bridge = mount_setup_page(view)
    view.show()
    qtbot.waitExposed(view)
    until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    return view, bridge
```

- [ ] **Step 2: Write the failing page tests**

Create `tests/test_setup_page_web.py`:

```python
"""The setup document in a real Chromium: Worker selection and SKU mapping.

Never mark these skip -- a page nobody can run is a page nobody guards.
"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from setup_web import (
    click, eval_js, mounted, press, run_js, set_value, settle, shown, text, until_js,
)

from gui.setup_payload import (
    MappingEditor, mapping_error, mapping_payload, quick_payload, workers_payload,
)

NOW = datetime(2026, 10, 7, 14, 6, tzinfo=timezone(timedelta(hours=3)))


def worker(worker_id, name, sessions=0, orders=0, days=None):
    return SimpleNamespace(
        id=worker_id, name=name, total_sessions=sessions, total_orders=orders,
        last_active=(NOW - timedelta(days=days)).isoformat() if days is not None else None,
        created_at=None,
    )


SIX = [
    worker("w1", "Ivan", 31, 2870, 0),
    worker("w2", "Maria", 14, 1204, 1),
    worker("w3", "Georgi", 22, 1951, 2),
    worker("w4", "Petya", 9, 688, 8),
    worker("w5", "Elena", 3, 140, 25),
    worker("w6", "Dimitar", 1, 37, 40),
]
READ = {f"59012345{n:03d}": f"SKU-{n:03d}" for n in range(60)}


@pytest.fixture
def page(qtbot):
    return mounted(qtbot)


def show_workers(page, qtbot, workers=SIX, **kwargs):
    view, bridge = page
    kwargs.setdefault("startup", True)
    bridge.set_workers(workers_payload(workers, now=NOW, **kwargs))
    bridge.set_page("workers")
    settle(qtbot, bridge)


def show_mapping(page, qtbot, editor=None, **kwargs):
    view, bridge = page
    editor = editor if editor is not None else MappingEditor(READ)
    kwargs.setdefault("client", "ACME")
    bridge.set_mapping(mapping_payload(editor, **kwargs))
    bridge.set_page("mapping")
    settle(qtbot, bridge)
    return editor


def count(view, qtbot, selector):
    return eval_js(qtbot, view, f"document.querySelectorAll({json.dumps(selector)}).length")


def record(bridge, signal_name):
    seen = []
    getattr(bridge, signal_name).connect(lambda *args: seen.append(args))
    return seen


def answers(bridge, result=""):
    """Record the answering slots' calls and answer them all with `result`."""
    calls = []

    def answer(name, *args):
        calls.append((name, *args))
        return result

    bridge.answer = answer
    return calls


# --- nothing --------------------------------------------------------------------


def test_with_no_page_the_document_draws_no_text(page, qtbot):
    view, bridge = page
    settle(qtbot, bridge)
    assert not shown(view, qtbot, "workers") and not shown(view, qtbot, "mapping")
    assert eval_js(qtbot, view, "document.body.innerText.trim()") == ""


# --- Worker selection -------------------------------------------------------------


def test_six_workers_are_six_cards_and_the_new_card(page, qtbot):
    view, bridge = page
    show_workers(page, qtbot)
    assert shown(view, qtbot, "workers") and not shown(view, qtbot, "mapping")
    assert count(view, qtbot, "#w-grid [data-worker]") == 6
    assert shown(view, qtbot, "w-new") and not shown(view, qtbot, "w-form")
    assert text(view, qtbot, "w-leave") == "Quit"
    first = eval_js(qtbot, view, "document.querySelector('[data-worker]').innerText")
    assert "Ivan" in first and "31 sessions · 2,870 orders" in first
    assert "Last active Today, 14:06" in first
    assert eval_js(
        qtbot, view,
        "getComputedStyle(document.getElementById('w-grid')).gridTemplateColumns.split(' ').length",
    ) == 4


def test_one_worker_is_two_columns(page, qtbot):
    view, _bridge = page
    show_workers(page, qtbot, SIX[1:2])
    assert count(view, qtbot, "#w-grid [data-worker]") == 1
    assert eval_js(
        qtbot, view,
        "getComputedStyle(document.getElementById('w-grid')).gridTemplateColumns.split(' ').length",
    ) == 2


def test_no_workers_says_so_above_the_new_card(page, qtbot):
    view, _bridge = page
    show_workers(page, qtbot, [])
    assert shown(view, qtbot, "w-empty")
    assert "No workers yet" in text(view, qtbot, "w-empty")
    assert "Create a worker profile to start packing." in text(view, qtbot, "w-empty")
    assert shown(view, qtbot, "w-new")


def test_the_switch_context_names_the_way_back_and_marks_the_current_card(page, qtbot):
    view, _bridge = page
    show_workers(page, qtbot, startup=False, current_id="w1", current_name="Ivan")
    assert text(view, qtbot, "w-leave") == "Back to Ivan"
    assert "Current" in eval_js(
        qtbot, view, "document.querySelector('[data-worker=\"w1\"]').innerText")


def test_a_card_click_reaches_pick_worker(page, qtbot):
    view, bridge = page
    show_workers(page, qtbot)
    picked = record(bridge, "workerPicked")
    run_js(qtbot, view, "document.querySelector('[data-worker=\"w3\"]').click()")
    qtbot.waitUntil(lambda: picked == [("w3",)], timeout=3000)


def test_the_picked_card_says_opening(page, qtbot):
    view, _bridge = page
    show_workers(page, qtbot, picked_id="w2")
    assert "Opening…" in eval_js(
        qtbot, view, "document.querySelector('[data-worker=\"w2\"]').innerText")
    assert eval_js(
        qtbot, view, "document.querySelector('[data-worker=\"w2\"]').classList.contains('picked')")


def test_the_leave_button_reaches_leave_workers(page, qtbot):
    view, bridge = page
    show_workers(page, qtbot)
    left = record(bridge, "workersLeaveRequested")
    click(view, qtbot, "w-leave")
    qtbot.waitUntil(lambda: len(left) == 1, timeout=3000)


def test_new_worker_opens_the_form_with_the_focus_in_the_name(page, qtbot):
    view, _bridge = page
    show_workers(page, qtbot)
    click(view, qtbot, "w-new")
    assert shown(view, qtbot, "w-form") and not shown(view, qtbot, "w-new")
    assert eval_js(qtbot, view, "document.activeElement.id") == "w-name"
    assert eval_js(qtbot, view, "document.getElementById('w-name').maxLength") == 24


def test_enter_in_the_name_reaches_create_and_a_sentence_shows_until_typing(page, qtbot):
    view, bridge = page
    show_workers(page, qtbot)
    calls = answers(bridge, "Enter a name.")
    click(view, qtbot, "w-new")
    set_value(view, qtbot, "w-name", "maria")
    press(view, qtbot, "w-name", "Enter")
    qtbot.waitUntil(lambda: calls == [("createWorker", "maria")], timeout=3000)
    until_js(qtbot, view, "!document.getElementById('w-name-error').hidden")
    assert text(view, qtbot, "w-name-error") == "Enter a name."
    assert shown(view, qtbot, "w-form")

    set_value(view, qtbot, "w-name", "maria p")
    assert not shown(view, qtbot, "w-name-error")


def test_a_created_worker_closes_the_form(page, qtbot):
    view, bridge = page
    show_workers(page, qtbot)
    calls = answers(bridge, "")
    click(view, qtbot, "w-new")
    set_value(view, qtbot, "w-name", "Ana")
    click(view, qtbot, "w-create")
    qtbot.waitUntil(lambda: calls == [("createWorker", "Ana")], timeout=3000)
    until_js(qtbot, view, "document.getElementById('w-form').hidden")


def test_escape_and_cancel_close_the_form(page, qtbot):
    view, _bridge = page
    show_workers(page, qtbot)
    click(view, qtbot, "w-new")
    press(view, qtbot, "w-name", "Escape")
    assert not shown(view, qtbot, "w-form") and shown(view, qtbot, "w-new")
    click(view, qtbot, "w-new")
    click(view, qtbot, "w-cancel")
    assert not shown(view, qtbot, "w-form")


def test_a_failed_load_is_the_banner_with_retry_and_no_grid(page, qtbot):
    view, bridge = page
    failure = {"cause": "permission denied", "path": r"\\fs01\fulfilment\Workers"}
    show_workers(page, qtbot, [], failure=failure)
    assert shown(view, qtbot, "w-failed") and not shown(view, qtbot, "w-grid")
    banner = text(view, qtbot, "w-failed")
    assert "Couldn’t load the worker list." in banner
    assert "Permission denied." in banner and r"\\fs01\fulfilment\Workers" in banner
    retried = record(bridge, "workersRetryRequested")
    click(view, qtbot, "w-retry")
    qtbot.waitUntil(lambda: len(retried) == 1, timeout=3000)


def test_markup_in_a_worker_name_is_text(page, qtbot):
    view, _bridge = page
    show_workers(page, qtbot, [worker("w1", "<img src=x id=boom>")])
    assert eval_js(qtbot, view, "document.getElementById('boom') === null")
    assert "<img src=x id=boom>" in eval_js(
        qtbot, view, "document.querySelector('[data-worker]').innerText")


# --- SKU mapping ----------------------------------------------------------------


def test_sixty_mappings_are_listed_with_save_disabled(page, qtbot):
    view, _bridge = page
    show_mapping(page, qtbot)
    assert shown(view, qtbot, "mapping") and not shown(view, qtbot, "workers")
    assert text(view, qtbot, "m-client") == "ACME"
    assert count(view, qtbot, "#m-rows [data-row]") == 60
    assert text(view, qtbot, "m-count") == "60 mappings"
    assert eval_js(qtbot, view, "document.getElementById('m-save').disabled")
    assert text(view, qtbot, "m-cancel") == "Cancel"
    assert not shown(view, qtbot, "m-draft") and not shown(view, qtbot, "m-unsaved")
    assert shown(view, qtbot, "m-add") and shown(view, qtbot, "m-reload")


def test_one_mapping_is_singular(page, qtbot):
    view, _bridge = page
    show_mapping(page, qtbot, MappingEditor({"1": "A"}))
    assert text(view, qtbot, "m-count") == "1 mapping"


def test_no_mappings_is_the_empty_card_and_its_button_opens_the_draft(page, qtbot):
    view, _bridge = page
    show_mapping(page, qtbot, MappingEditor())
    assert shown(view, qtbot, "m-empty") and not shown(view, qtbot, "m-table")
    assert not shown(view, qtbot, "m-add")
    assert "No mappings yet" in text(view, qtbot, "m-empty")
    click(view, qtbot, "m-empty-add")
    assert shown(view, qtbot, "m-table") and shown(view, qtbot, "m-draft")
    assert eval_js(qtbot, view, "document.activeElement.id") == "d-barcode"


def test_the_search_narrows_the_rows_and_the_count(page, qtbot):
    view, _bridge = page
    show_mapping(page, qtbot)
    set_value(view, qtbot, "m-search", "sku-00")
    assert count(view, qtbot, "#m-rows [data-row]:not([hidden])") == 10
    assert text(view, qtbot, "m-count") == "10 of 60 mappings"
    set_value(view, qtbot, "m-search", "nothing-like-this")
    assert shown(view, qtbot, "m-nohits")
    assert text(view, qtbot, "m-nohits") == "No mappings match “nothing-like-this”."


def test_add_mapping_clears_the_search_and_focuses_the_barcode(page, qtbot):
    view, _bridge = page
    show_mapping(page, qtbot)
    set_value(view, qtbot, "m-search", "sku-00")
    click(view, qtbot, "m-add")
    assert shown(view, qtbot, "m-draft")
    assert eval_js(qtbot, view, "document.getElementById('m-search').value") == ""
    assert count(view, qtbot, "#m-rows [data-row]") == 60
    assert eval_js(qtbot, view, "document.activeElement.id") == "d-barcode"
    assert text(view, qtbot, "d-commit") == "Add"
    assert eval_js(qtbot, view, "document.getElementById('d-commit').disabled")


def test_enter_moves_barcode_to_sku_and_then_adds_and_the_draft_stays_open(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot)
    calls = answers(bridge, "")
    click(view, qtbot, "m-add")
    set_value(view, qtbot, "d-barcode", "5906 000 1")
    assert eval_js(qtbot, view, "document.getElementById('d-barcode').value") == "59060001"
    press(view, qtbot, "d-barcode", "Enter")
    assert eval_js(qtbot, view, "document.activeElement.id") == "d-sku"
    assert calls == []

    set_value(view, qtbot, "d-sku", "CRM-50ML")
    press(view, qtbot, "d-sku", "Enter")
    qtbot.waitUntil(lambda: calls == [("addMapping", "59060001", "CRM-50ML")], timeout=3000)
    until_js(qtbot, view, "document.getElementById('d-barcode').value === ''")
    assert eval_js(qtbot, view, "document.getElementById('d-sku').value") == ""
    assert shown(view, qtbot, "m-draft")
    assert eval_js(qtbot, view, "document.activeElement.id") == "d-barcode"


def test_enter_in_an_empty_barcode_goes_nowhere(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot)
    calls = answers(bridge, "")
    click(view, qtbot, "m-add")
    press(view, qtbot, "d-barcode", "Enter")
    assert eval_js(qtbot, view, "document.activeElement.id") == "d-barcode"
    assert calls == []


def test_a_refused_add_keeps_what_was_typed_and_shows_the_sentence(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot)
    answers(bridge, "Enter a SKU.")
    click(view, qtbot, "m-add")
    set_value(view, qtbot, "d-barcode", "777")
    set_value(view, qtbot, "d-sku", "X")
    click(view, qtbot, "d-commit")
    until_js(qtbot, view, "!document.getElementById('d-problem').hidden")
    assert text(view, qtbot, "d-problem") == "Enter a SKU."
    assert eval_js(qtbot, view, "document.getElementById('d-barcode').value") == "777"
    set_value(view, qtbot, "d-sku", "XY")
    assert not shown(view, qtbot, "d-problem")


def test_an_already_mapped_barcode_offers_replace(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot)
    calls = answers(bridge, "")
    click(view, qtbot, "m-add")
    set_value(view, qtbot, "d-barcode", "590-12345003")  # normalises like 59012345003
    assert shown(view, qtbot, "d-clash")
    assert text(view, qtbot, "d-clash-text") == (
        "This barcode already maps to SKU-003. Enter a SKU to replace it."
    )
    assert eval_js(qtbot, view, "document.getElementById('d-replace').disabled")
    assert eval_js(qtbot, view, "document.getElementById('d-commit').disabled")
    assert count(view, qtbot, "#m-rows .clash") == 1
    press(view, qtbot, "d-barcode", "Enter")  # does not move on
    assert eval_js(qtbot, view, "document.activeElement.id") == "d-barcode"

    set_value(view, qtbot, "d-sku", "CLN-250")
    assert text(view, qtbot, "d-clash-text") == (
        "This barcode already maps to SKU-003. Replace it with CLN-250?"
    )
    press(view, qtbot, "d-sku", "Enter")  # Enter never replaces
    qtbot.wait(150)
    assert calls == []
    click(view, qtbot, "d-replace")
    qtbot.waitUntil(
        lambda: calls == [("replaceMapping", 0, "590-12345003", "CLN-250")], timeout=3000)


def test_edit_turns_the_row_into_fields_and_update_reaches_the_slot(page, qtbot):
    view, bridge = page
    editor = show_mapping(page, qtbot)
    target = editor.rows[4]
    calls = answers(bridge, "")
    run_js(
        qtbot, view,
        f"document.querySelector('[data-row-action=\"edit\"][data-id=\"{target['id']}\"]').click()",
    )
    assert shown(view, qtbot, "m-draft")
    assert eval_js(qtbot, view, "document.getElementById('d-barcode').value") == target["barcode"]
    assert eval_js(qtbot, view, "document.activeElement.id") == "d-sku"
    assert text(view, qtbot, "d-commit") == "Update"
    # The draft sits where the row was, and the row itself is hidden.
    assert eval_js(
        qtbot, view,
        f"document.getElementById('m-draft').nextElementSibling.dataset.row === '{target['id']}'",
    )
    set_value(view, qtbot, "d-sku", "NEW-SKU")
    press(view, qtbot, "d-sku", "Enter")
    qtbot.waitUntil(
        lambda: calls == [("updateMapping", target["id"], target["barcode"], "NEW-SKU")],
        timeout=3000,
    )
    until_js(qtbot, view, "document.getElementById('m-draft').hidden")


def test_escape_closes_the_draft_before_it_leaves_the_page(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot)
    closed = record(bridge, "mappingCloseRequested")
    click(view, qtbot, "m-add")
    press(view, qtbot, "d-barcode", "Escape")
    assert not shown(view, qtbot, "m-draft")
    assert closed == []
    press(view, qtbot, "", "Escape")
    qtbot.waitUntil(lambda: len(closed) == 1, timeout=3000)


def test_unsaved_rows_carry_a_dot_and_the_footer_says_what(page, qtbot):
    view, _bridge = page
    editor = MappingEditor(READ)
    editor.add("7001", "NEW-1")
    editor.add("7002", "NEW-2")
    editor.update(editor.rows[5]["id"], editor.rows[5]["barcode"], "EDITED")
    show_mapping(page, qtbot, editor)
    assert count(view, qtbot, "#m-rows .su-undot") == 3
    assert eval_js(
        qtbot, view, "document.querySelector('#m-rows .su-undot').title") == "Added, not saved"
    assert shown(view, qtbot, "m-unsaved")
    assert text(view, qtbot, "m-unsaved") == "Unsaved: 2 added, 1 edited"
    assert not eval_js(qtbot, view, "document.getElementById('m-save').disabled")


def test_save_and_ctrl_s_reach_the_slot_only_with_changes(page, qtbot):
    view, bridge = page
    saved = record(bridge, "mappingSaveRequested")
    show_mapping(page, qtbot)
    press(view, qtbot, "", "s", ctrl=True)
    qtbot.wait(150)
    assert saved == []

    editor = MappingEditor(READ)
    editor.add("7001", "NEW-1")
    show_mapping(page, qtbot, editor)
    click(view, qtbot, "m-save")
    press(view, qtbot, "", "s", ctrl=True)
    qtbot.waitUntil(lambda: len(saved) == 2, timeout=3000)


def test_the_saved_line(page, qtbot):
    view, _bridge = page
    show_mapping(page, qtbot, saved=True)
    assert shown(view, qtbot, "m-saved")
    assert text(view, qtbot, "m-saved").strip() == "Saved. Every PC now uses these mappings."


def test_delete_asks_and_both_answers_work(page, qtbot):
    view, bridge = page
    editor = show_mapping(page, qtbot)
    target = editor.rows[4]
    deleted = record(bridge, "mappingDeleteRequested")
    button = f"document.querySelector('[data-row-action=\"delete\"][data-id=\"{target['id']}\"]')"
    run_js(qtbot, view, f"{button}.click()")
    assert shown(view, qtbot, "m-ask")
    assert text(view, qtbot, "m-ask-title") == "Delete this mapping?"
    assert text(view, qtbot, "m-ask-barcode") == target["barcode"]
    assert text(view, qtbot, "m-ask-text") == (
        "Once you save, scanning this barcode on any PC will no longer count as "
        f"{target['sku']}."
    )
    assert text(view, qtbot, "m-ask-yes") == "Delete"
    click(view, qtbot, "m-ask-no")
    assert not shown(view, qtbot, "m-ask") and deleted == []

    run_js(qtbot, view, f"{button}.click()")
    press(view, qtbot, "", "Enter")  # Enter does not answer a question
    qtbot.wait(150)
    assert deleted == [] and shown(view, qtbot, "m-ask")
    click(view, qtbot, "m-ask-yes")
    qtbot.waitUntil(lambda: deleted == [(target["id"],)], timeout=3000)
    assert not shown(view, qtbot, "m-ask")


def test_deleting_a_row_that_was_never_saved_asks_nothing(page, qtbot):
    view, bridge = page
    editor = MappingEditor(READ)
    editor.add("7001", "NEW-1")
    show_mapping(page, qtbot, editor)
    deleted = record(bridge, "mappingDeleteRequested")
    new_id = editor.rows[0]["id"]
    run_js(
        qtbot, view,
        f"document.querySelector('[data-row-action=\"delete\"][data-id=\"{new_id}\"]').click()",
    )
    qtbot.waitUntil(lambda: deleted == [(new_id,)], timeout=3000)
    assert not shown(view, qtbot, "m-ask")


def test_reload_asks_only_with_unsaved_changes(page, qtbot):
    view, bridge = page
    reloaded = record(bridge, "mappingReloadRequested")
    show_mapping(page, qtbot)
    click(view, qtbot, "m-reload")
    qtbot.waitUntil(lambda: len(reloaded) == 1, timeout=3000)
    assert not shown(view, qtbot, "m-ask")

    editor = MappingEditor(READ)
    editor.add("7001", "NEW-1")
    editor.add("7002", "NEW-2")
    show_mapping(page, qtbot, editor)
    click(view, qtbot, "m-reload")
    assert shown(view, qtbot, "m-ask")
    assert text(view, qtbot, "m-ask-title") == "Reload from server?"
    assert text(view, qtbot, "m-ask-text") == (
        "Your 2 unsaved changes (2 added) will be lost. "
        "The list is replaced with the copy on the file server."
    )
    assert text(view, qtbot, "m-ask-yes") == "Discard and reload"
    press(view, qtbot, "", "Escape")  # Esc closes the question, not the page
    assert not shown(view, qtbot, "m-ask") and len(reloaded) == 1
    click(view, qtbot, "m-reload")
    click(view, qtbot, "m-ask-yes")
    qtbot.waitUntil(lambda: len(reloaded) == 2, timeout=3000)


@pytest.mark.parametrize("way", ["m-close", "m-cancel", "Escape"])
def test_leaving_with_nothing_unsaved_just_leaves(page, qtbot, way):
    view, bridge = page
    show_mapping(page, qtbot)
    closed = record(bridge, "mappingCloseRequested")
    if way == "Escape":
        press(view, qtbot, "", "Escape")
    else:
        click(view, qtbot, way)
    qtbot.waitUntil(lambda: len(closed) == 1, timeout=3000)
    assert not shown(view, qtbot, "m-ask")


def test_leaving_with_unsaved_changes_asks_first(page, qtbot):
    view, bridge = page
    editor = MappingEditor(READ)
    editor.add("7001", "NEW-1")
    show_mapping(page, qtbot, editor)
    closed = record(bridge, "mappingCloseRequested")
    click(view, qtbot, "m-close")
    assert shown(view, qtbot, "m-ask")
    assert text(view, qtbot, "m-ask-title") == "Discard unsaved changes?"
    assert text(view, qtbot, "m-ask-text") == "Your 1 unsaved change (1 added) will be lost."
    assert text(view, qtbot, "m-ask-no") == "Keep editing"
    assert text(view, qtbot, "m-ask-yes") == "Discard"
    click(view, qtbot, "m-ask-no")
    assert closed == []
    click(view, qtbot, "m-cancel")
    click(view, qtbot, "m-ask-yes")
    qtbot.waitUntil(lambda: len(closed) == 1, timeout=3000)


def test_leave_asked_raises_the_question_only_with_unsaved_changes(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot)
    bridge.leaveAsked.emit()
    qtbot.wait(150)
    assert not shown(view, qtbot, "m-ask")

    editor = MappingEditor(READ)
    editor.add("7001", "NEW-1")
    show_mapping(page, qtbot, editor)
    bridge.leaveAsked.emit()
    until_js(qtbot, view, "!document.getElementById('m-ask').hidden")
    assert text(view, qtbot, "m-ask-title") == "Discard unsaved changes?"


def test_a_failed_save_is_the_banner_with_try_again_and_no_unsaved_line(page, qtbot):
    view, bridge = page
    editor = MappingEditor(READ)
    editor.add("7001", "NEW-1")
    error = mapping_error("save", "the cause", r"\\fs01\c\packer_config.json", 1)
    show_mapping(page, qtbot, editor, error=error)
    banner = text(view, qtbot, "m-error")
    assert "Couldn’t save to the file server." in banner
    assert "Your 1 change is still here and nothing on the server changed." in banner
    assert "the cause" in banner and r"\\fs01\c\packer_config.json" in banner
    assert text(view, qtbot, "m-error-action") == "Try again"
    assert not shown(view, qtbot, "m-unsaved")
    assert count(view, qtbot, "#m-rows .su-undot") == 1
    saved = record(bridge, "mappingSaveRequested")
    click(view, qtbot, "m-error-action")
    qtbot.waitUntil(lambda: len(saved) == 1, timeout=3000)


def test_a_failed_load_is_the_banner_with_retry_and_no_table(page, qtbot):
    view, bridge = page
    error = mapping_error("load", "the cause", "p")
    show_mapping(page, qtbot, MappingEditor(), error=error, failed=True)
    assert shown(view, qtbot, "m-error")
    assert not shown(view, qtbot, "m-table") and not shown(view, qtbot, "m-empty")
    assert not shown(view, qtbot, "m-add")
    assert text(view, qtbot, "m-error-action") == "Retry"
    reloaded = record(bridge, "mappingReloadRequested")
    click(view, qtbot, "m-error-action")
    qtbot.waitUntil(lambda: len(reloaded) == 1, timeout=3000)


def test_markup_in_a_sku_is_text(page, qtbot):
    view, _bridge = page
    show_mapping(page, qtbot, MappingEditor({"1": "<img src=x id=boom>"}))
    assert eval_js(qtbot, view, "document.getElementById('boom') === null")
    assert "<img src=x id=boom>" in text(view, qtbot, "m-rows")


# --- the quick map ----------------------------------------------------------------

CHOICES = [
    {"sku": "SER-30ML", "label": "SER-30ML — 0 / 2 packed", "key": "ser30ml"},
    {"sku": "CRM-50ML", "label": "CRM-50ML — 1 / 1 packed", "key": "crm50ml"},
]


def test_a_quick_map_for_a_barcode_locks_it_and_offers_the_order_lines(page, qtbot):
    view, bridge = page
    quick = quick_payload("barcode", barcode="5906000123456", choices=CHOICES)
    show_mapping(page, qtbot, quick=quick)
    assert shown(view, qtbot, "m-draft")
    assert eval_js(qtbot, view, "document.getElementById('d-barcode').value") == "5906000123456"
    assert eval_js(qtbot, view, "document.getElementById('d-barcode').disabled")
    until_js(qtbot, view, "document.activeElement.id === 'd-sku'")
    assert text(view, qtbot, "d-hint") == (
        "Scanned in Packer Mode. Enter the SKU it should count as."
    )
    assert count(view, qtbot, "#d-choices [data-choice]") == 2
    # Only the one add: nothing else on the page can change a mapping.
    for hidden in ("m-add", "m-reload", "m-save", "d-cancel"):
        assert not shown(view, qtbot, hidden), hidden
    assert count(view, qtbot, "#m-rows [data-row-action]") == 0
    assert text(view, qtbot, "m-cancel") == "Back to packing"
    assert shown(view, qtbot, "m-search")

    calls = answers(bridge, "")
    run_js(qtbot, view, "document.querySelector('[data-choice=\"SER-30ML\"]').click()")
    qtbot.waitUntil(
        lambda: calls == [("addMapping", "5906000123456", "SER-30ML")], timeout=3000)


def test_a_quick_map_shows_the_refusal_and_keeps_the_draft(page, qtbot):
    view, bridge = page
    quick = quick_payload("barcode", barcode="5906000123456", choices=CHOICES)
    show_mapping(page, qtbot, quick=quick)
    answers(bridge, "Not on this order. Pick one of the lines below.")
    set_value(view, qtbot, "d-sku", "4006381333931")
    press(view, qtbot, "d-sku", "Enter")
    until_js(qtbot, view, "!document.getElementById('d-problem').hidden")
    assert text(view, qtbot, "d-problem") == "Not on this order. Pick one of the lines below."
    assert shown(view, qtbot, "m-draft")


def test_a_quick_map_for_a_sku_adds_on_the_barcodes_enter(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot, quick=quick_payload("sku", sku="SER-30ML"))
    assert eval_js(qtbot, view, "document.getElementById('d-sku').value") == "SER-30ML"
    assert eval_js(qtbot, view, "document.getElementById('d-sku').disabled")
    until_js(qtbot, view, "document.activeElement.id === 'd-barcode'")
    assert text(view, qtbot, "d-hint") == "Scan or type the barcode for this SKU."
    assert count(view, qtbot, "#d-choices [data-choice]") == 0
    calls = answers(bridge, "")
    set_value(view, qtbot, "d-barcode", "5906000999")
    press(view, qtbot, "d-barcode", "Enter")
    qtbot.waitUntil(lambda: calls == [("addMapping", "5906000999", "SER-30ML")], timeout=3000)


def test_a_quick_map_onto_a_mapped_barcode_goes_on_only_by_replace(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot, quick=quick_payload("sku", sku="SER-30ML"))
    calls = answers(bridge, "")
    set_value(view, qtbot, "d-barcode", "59012345003")
    press(view, qtbot, "d-barcode", "Enter")
    qtbot.wait(150)
    assert calls == [] and shown(view, qtbot, "d-clash")
    click(view, qtbot, "d-replace")
    qtbot.waitUntil(
        lambda: calls == [("replaceMapping", 0, "59012345003", "SER-30ML")], timeout=3000)


def test_back_to_packing_and_escape_leave_a_quick_map(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot, quick=quick_payload("sku", sku="SER-30ML"))
    closed = record(bridge, "mappingCloseRequested")
    click(view, qtbot, "m-cancel")
    press(view, qtbot, "d-barcode", "Escape")
    qtbot.waitUntil(lambda: len(closed) == 2, timeout=3000)


def test_a_quick_map_takes_the_focus_back_when_it_is_left_on_nothing(page, qtbot):
    view, _bridge = page
    show_mapping(page, qtbot, quick=quick_payload("sku", sku="SER-30ML"))
    until_js(qtbot, view, "document.activeElement.id === 'd-barcode'")
    run_js(qtbot, view, "document.activeElement.blur()")
    until_js(qtbot, view, "document.activeElement.id === 'd-barcode'")


# --- stray scans (ADR 0004) --------------------------------------------------------


def _type_at_body(view, qtbot, chars):
    for char in chars:
        press(view, qtbot, "", char)


def test_keys_that_reach_no_field_are_handed_over_as_one_scan_on_enter(page, qtbot):
    view, bridge = page
    settle(qtbot, bridge)  # page "": nothing has the focus
    strays = record(bridge, "strayScanned")
    _type_at_body(view, qtbot, "4006381333931")
    assert strays == []
    press(view, qtbot, "", "Enter")
    qtbot.waitUntil(lambda: strays == [("4006381333931",)], timeout=3000)
    press(view, qtbot, "", "Enter")  # an Enter alone is not a scan
    qtbot.wait(150)
    assert len(strays) == 1


def test_keys_typed_into_a_field_are_not_a_stray_scan(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot)
    answers(bridge, "")
    strays = record(bridge, "strayScanned")
    click(view, qtbot, "m-add")
    for char in "123":
        press(view, qtbot, "d-barcode", char)
    press(view, qtbot, "d-barcode", "Enter")
    qtbot.wait(150)
    assert strays == []


def test_a_page_change_drops_a_half_typed_stray_scan(page, qtbot):
    view, bridge = page
    settle(qtbot, bridge)
    strays = record(bridge, "strayScanned")
    _type_at_body(view, qtbot, "400")
    show_workers(page, qtbot)
    bridge.set_page("")
    settle(qtbot, bridge)
    _type_at_body(view, qtbot, "777")
    press(view, qtbot, "", "Enter")
    qtbot.waitUntil(lambda: strays == [("777",)], timeout=3000)
```

- [ ] **Step 3: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_setup_page_web.py`
Expected: the first test passes against the skeleton; every other test FAILS (an element id that does not exist yet).

- [ ] **Step 4: Write `gui/web/setup.html`**

Replace the file. Text that a test reads back with `textContent` is kept on one line on purpose: do not reflow those elements.

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Packer Assistant</title>
<!-- shared/web_page.mount_page writes theme_css_vars() over the marker in the
     style element below before the page loads; setup.js keeps it current. -->
<style id="theme-vars">/* theme-vars */</style>
<link rel="stylesheet" href="../../shared/web/kit.css">
<link rel="stylesheet" href="floor.css">
<link rel="stylesheet" href="setup.css">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<script src="../../shared/web/page.js"></script>
<script src="setup.js" defer></script>
</head>
<body>
<!-- The setup document (ADR 0002, ADR 0004): Worker selection and SKU mapping, the two full-window
     pages. Every string from the bridge goes in through textContent. -->
<div class="setup" id="setup">

  <section class="su-workers" id="workers" hidden>
    <div class="su-top">
      <span class="spacer"></span>
      <button type="button" class="btn secondary" id="w-leave" data-action="leaveWorkers"></button>
    </div>
    <div class="su-w-scroll">
      <div class="su-w-head">
        <span class="su-mark"><svg class="glyph" viewBox="0 0 24 24"><path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"/><path d="M12 22V12"/><path d="m3.3 7 7.703 4.734a2 2 0 0 0 1.994 0L20.7 7"/><path d="m7.5 4.27 9 5.15"/></svg></span>
        <h1 class="su-w-title">Select your profile</h1>
        <p class="su-w-sub">Choose your worker profile to continue</p>
      </div>

      <div class="banner danger su-w-banner" id="w-failed" role="alert" hidden>
        <svg class="glyph" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>
        <div class="banner-body">
          <div class="banner-title" id="w-failed-title"></div>
          <div class="banner-text"><span id="w-failed-text"></span> <span class="mono" id="w-failed-path"></span></div>
        </div>
        <button type="button" class="btn secondary compact" id="w-retry" data-action="retryWorkers">Retry</button>
      </div>

      <div class="su-w-empty" id="w-empty" hidden>
        <div class="su-w-empty-title">No workers yet</div>
        <div>Create a worker profile to start packing.</div>
      </div>

      <!-- setup.js inserts one card per worker before #w-new. -->
      <div class="su-grid" id="w-grid" hidden>
        <button type="button" class="su-card su-new" id="w-new" data-action="newWorker">
          <span class="su-new-plus"><svg class="glyph" viewBox="0 0 24 24"><path d="M5 12h14"/><path d="M12 5v14"/></svg></span>
          <span>New worker</span>
        </button>
        <div class="card su-card su-form" id="w-form" hidden>
          <span class="su-form-title">New worker</span>
          <input class="field" id="w-name" type="text" maxlength="24" placeholder="Name" aria-label="Worker name" autocomplete="off" spellcheck="false">
          <span class="su-form-error" id="w-name-error" hidden></span>
          <div class="su-form-actions">
            <button type="button" class="btn primary" id="w-create" data-action="createWorker">Create</button>
            <button type="button" class="btn secondary" id="w-cancel" data-action="cancelWorker">Cancel</button>
          </div>
        </div>
      </div>
    </div>
  </section>

  <section class="su-mapping" id="mapping" hidden>
    <div class="card su-m-card">
      <header class="su-m-head">
        <span class="su-m-title">SKU mapping</span>
        <span class="badge neutral"><span class="dot solid su-ok"></span><span id="m-client"></span></span>
        <span class="spacer"></span>
        <button type="button" class="btn ghost icon su-plain" id="m-close" data-action="leaveMapping" title="Close (Esc)" aria-label="Close"><svg class="glyph" viewBox="0 0 24 24"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg></button>
      </header>

      <main class="su-m-body">
        <div class="su-m-intro">
          <span class="su-m-desc">Map product barcodes to internal SKUs. Changes are saved to the file server and reach every PC.</span>
          <button type="button" class="btn secondary compact" id="m-add" data-action="startAdd"><svg class="glyph" viewBox="0 0 24 24"><path d="M5 12h14"/><path d="M12 5v14"/></svg>Add mapping</button>
        </div>

        <div class="banner danger" id="m-error" role="alert" hidden>
          <svg class="glyph" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>
          <div class="banner-body">
            <div class="banner-title" id="m-error-title"></div>
            <div class="banner-text"><span id="m-error-text"></span> <span class="mono" id="m-error-path"></span></div>
            <div class="su-m-cause" id="m-error-cause"></div>
          </div>
          <button type="button" class="btn secondary compact" id="m-error-action" data-action="errorAction"></button>
        </div>

        <section class="card state-card" id="m-empty" hidden>
          <h1 class="state-card-title">No mappings yet</h1>
          <p class="state-card-text">Scan or type a product barcode to map it to a SKU.</p>
          <button type="button" class="btn primary" id="m-empty-add" data-action="startAdd">Add mapping</button>
        </section>

        <section class="card su-m-table" id="m-table" hidden>
          <div class="su-m-tools">
            <label class="input su-m-search">
              <svg class="glyph" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
              <input id="m-search" type="text" placeholder="Search barcode or SKU" aria-label="Search barcode or SKU" autocomplete="off" spellcheck="false">
            </label>
            <span class="spacer"></span>
            <span class="su-m-count" id="m-count"></span>
            <button type="button" class="btn secondary compact" id="m-reload" data-action="reload" title="Replace this list with the copy on the file server"><svg class="glyph" viewBox="0 0 24 24"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>Reload from server</button>
          </div>
          <div class="tbl-head"><span></span><span>Product barcode</span><span></span><span>Internal SKU</span><span></span></div>
          <div class="su-m-rows" id="m-scroll">
            <!-- One draft for adding and for editing: setup.js moves it to where the edited row was. -->
            <div class="su-draft" id="m-draft" hidden>
              <div class="tbl-row su-draft-row">
                <span></span>
                <input class="field mono" id="d-barcode" type="text" placeholder="Scan or type barcode" aria-label="Product barcode" autocomplete="off" spellcheck="false">
                <svg class="glyph" viewBox="0 0 24 24"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg>
                <input class="field mono" id="d-sku" type="text" placeholder="Internal SKU" aria-label="Internal SKU" autocomplete="off" spellcheck="false">
                <span class="su-row-actions">
                  <button type="button" class="btn primary compact" id="d-commit" data-action="commitDraft" title="Enter">Add</button>
                  <button type="button" class="btn ghost compact icon su-plain" id="d-cancel" data-action="cancelDraft" title="Cancel (Esc)" aria-label="Cancel"><svg class="glyph" viewBox="0 0 24 24"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg></button>
                </span>
              </div>
              <div class="su-draft-line danger" id="d-clash" hidden>
                <svg class="glyph" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/></svg>
                <span id="d-clash-text">This barcode already maps to <b class="mono" id="d-clash-sku"></b>.<span id="d-clash-ask"></span></span>
                <button type="button" class="btn danger compact" id="d-replace" data-action="replaceDraft">Replace</button>
              </div>
              <div class="su-draft-line danger" id="d-problem" hidden></div>
              <div class="su-draft-line" id="d-hint" hidden></div>
              <div class="su-choices" id="d-choices" hidden></div>
            </div>
            <div id="m-rows"></div>
            <div class="su-m-nohits" id="m-nohits" hidden>No mappings match “<span id="m-nohits-q"></span>”.</div>
          </div>
        </section>
      </main>

      <footer class="su-m-foot">
        <span class="su-unsaved" id="m-unsaved" hidden><span class="su-undot"></span>Unsaved: <span id="m-summary"></span></span>
        <span class="su-saved" id="m-saved" hidden><svg class="glyph" viewBox="0 0 24 24"><path d="M20 6 9 17l-5-5"/></svg>Saved. Every PC now uses these mappings.</span>
        <span class="spacer"></span>
        <button type="button" class="btn secondary" id="m-cancel" data-action="leaveMapping">Cancel</button>
        <button type="button" class="btn primary" id="m-save" data-action="save" title="Ctrl+S">Save</button>
      </footer>

      <div class="scrim" id="m-ask" hidden>
        <div class="dialog" role="alertdialog" aria-modal="true" aria-labelledby="m-ask-title">
          <h2 class="dialog-title" id="m-ask-title"></h2>
          <div class="su-pair mono" id="m-ask-pair" hidden><span id="m-ask-barcode"></span><svg class="glyph" viewBox="0 0 24 24"><path d="M5 12h14"/><path d="m12 5 7 7-7 7"/></svg><b id="m-ask-sku"></b></div>
          <p class="dialog-text" id="m-ask-text"></p>
          <div class="dialog-actions">
            <button type="button" class="btn secondary" id="m-ask-no" data-action="askNo"></button>
            <button type="button" class="btn danger" id="m-ask-yes" data-action="askYes"></button>
          </div>
        </div>
      </div>
    </div>
  </section>

</div>
</body>
</html>
```

- [ ] **Step 5: Write `gui/web/setup.css`**

Replace the file:

```css
/* The setup document's own sheet (UI refresh phase 5): the layouts of Worker
   selection and SKU mapping. Buttons, badges, cards, fields and the banner
   come from shared/web/kit.css; the scrim, dialog, state card and table rows
   from floor.css. Mockups: docs/design/ui-refresh/mockups/Worker Selection.html
   and SKU Mapping.html, at floor density (spec section 11).
   Spec: docs/superpowers/specs/2026-10-09-ui-refresh-phase5-setup-pages-design.md
   Web-tier rules (ADR 0001): var(--...) only, type sizes from the scale, one
   mono face, no transition/transform/opacity. */

.setup { position: relative; height: 100%; overflow: hidden; }

/* A bare input in trouble. The kit has this for .input only. */
.setup .field.invalid {
  border-color: var(--status-danger);
  outline: 1px solid var(--status-danger);
  outline-offset: -2px;
}

/* A ghost icon button is a glyph, not a word: no underline to carry. */
.setup .su-plain { text-decoration: none; color: var(--text-secondary); }
.setup .su-plain:hover { color: var(--text); }

/* --- Worker selection ---------------------------------------------------- */

.su-workers { height: 100%; display: flex; flex-direction: column; }
.su-top { flex: none; height: 60px; display: flex; align-items: center; padding: 0 20px; }
.su-w-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 40px 48px;
}
.su-w-head { display: flex; flex-direction: column; align-items: center; gap: 6px; text-align: center; }
.su-mark {
  width: 56px;
  height: 56px;
  margin-bottom: 8px;
  display: grid;
  place-items: center;
  border-radius: var(--radius-lg);
  background: var(--accent-fill);
  color: var(--on-accent);
}
.su-mark .glyph { width: 30px; height: 30px; stroke-width: 1.5; }
.su-w-title { margin: 0; font-size: var(--type-display-size); font-weight: 700; line-height: 1.2; }
.su-w-sub { margin: 0; color: var(--text-secondary); }

.su-w-banner { width: 100%; max-width: 640px; margin-top: 32px; }

.su-w-empty { margin-top: 36px; text-align: center; color: var(--text-secondary); }
.su-w-empty-title { font-size: var(--type-heading-size); font-weight: 700; color: var(--text); }

.su-grid {
  margin-top: 40px;
  display: grid;
  grid-template-columns: repeat(var(--su-cols, 4), 240px);
  gap: 16px;
  justify-content: center;
  align-items: start;
}
.su-grid.lone { margin-top: 20px; }

.su-card {
  width: 240px;
  min-height: 168px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 16px;
  padding: 20px;
  text-align: left;
  cursor: pointer;
}
.su-card:hover { border-color: var(--border-strong); }
.su-card:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
/* The mockup rings these with a shadow; the web tier may not, so an outline. */
.su-card.picked, .su-form { border-color: var(--text); outline: 1px solid var(--text); }

.su-card-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.su-avatar {
  flex: none;
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--surface-raised);
  border: 1px solid var(--border);
  font-size: var(--type-heading-size);
  font-weight: 700;
}
.su-card-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.su-card-name {
  font-size: var(--type-heading-size);
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.su-card-line { color: var(--text-secondary); }

.su-new {
  align-items: center;
  justify-content: center;
  gap: 10px;
  background: transparent;
  border: 1px dashed var(--border-strong);
  border-radius: var(--kit-radius-card);
  color: var(--text-secondary);
  font-size: var(--type-heading-size);
  font-weight: 700;
}
.su-new:hover { color: var(--text); }
.su-new-plus {
  width: 44px;
  height: 44px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  border: 1px dashed var(--border-strong);
}
.su-new-plus .glyph { width: 20px; height: 20px; }

.su-form { cursor: default; justify-content: flex-start; gap: 12px; }
.su-form-title { font-size: var(--type-heading-size); font-weight: 700; }
.su-form .field { width: 100%; border-color: var(--border-strong); }
.su-form-error { font-size: var(--type-caption-size); color: var(--status-danger); }
.su-form-actions { display: flex; gap: 8px; }
.su-form-actions .primary { flex: 1; }

/* --- SKU mapping --------------------------------------------------------- */

.su-mapping { height: 100%; display: flex; justify-content: center; padding: 40px 0; }
.su-m-card {
  position: relative;  /* the question's scrim covers the card */
  width: 920px;
  max-width: calc(100% - 48px);
  height: 100%;
  display: grid;
  grid-template-rows: 60px minmax(0, 1fr) 68px;
  overflow: hidden;
  box-shadow: var(--overlay-shadow);
}

.su-m-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 8px 0 20px;
  border-bottom: 1px solid var(--border-subtle);
}
.su-m-title { font-size: var(--type-heading-size); font-weight: 700; }
.su-ok { color: var(--status-success-dot); }

.su-m-body {
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px 24px;
  background: var(--surface-sunken);
}
.su-m-body > .banner { flex: none; align-items: flex-start; }
.su-m-cause { font-size: var(--type-caption-size); overflow-wrap: anywhere; }
.su-m-intro { flex: none; display: flex; align-items: center; gap: 16px; min-height: 40px; }
.su-m-desc { flex: 1; min-width: 0; color: var(--text-secondary); }

.su-m-table {
  --tbl-cols: 8px 240px 16px minmax(0, 1fr) 96px;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.su-m-table .tbl-head, .su-m-table .tbl-row { column-gap: 12px; }
.su-m-tools { flex: none; display: flex; align-items: center; gap: 12px; padding: 12px 16px; }
.su-m-search { width: 280px; }
.su-m-count { color: var(--text-secondary); }
.su-m-rows { flex: 1; min-height: 0; overflow: auto; }

.su-row:hover { background: var(--surface-raised); }
.su-row.clash { background: var(--status-danger-bg); }
.su-sku { font-weight: 700; }
.su-cut { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.su-row-actions { display: flex; align-items: center; justify-content: flex-end; gap: 2px; }
.su-undot { flex: none; width: 7px; height: 7px; border-radius: 50%; background: var(--text); }

.su-draft {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 0 10px;
  background: var(--surface-raised);
  border-bottom: 1px solid var(--border-subtle);
}
.su-draft-row { border-bottom: 0; }
.su-draft .field { width: 100%; min-width: 0; border-color: var(--border-strong); }
.su-draft-line {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 16px 0 36px;
  font-size: var(--type-caption-size);
  color: var(--text-secondary);
}
.su-draft-line.danger { font-size: var(--type-body-size); color: var(--status-danger); }
.su-choices { display: flex; flex-wrap: wrap; gap: 8px; padding: 0 16px 0 36px; }
.su-m-nohits { padding: 16px; color: var(--text-secondary); }

.su-m-foot {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 16px;
  border-top: 1px solid var(--border-subtle);
}
.su-unsaved, .su-saved { display: inline-flex; align-items: center; gap: 8px; }
.su-unsaved { color: var(--text-secondary); }
.su-unsaved > span:last-child { margin-left: -4px; }
.su-saved { color: var(--status-success); font-weight: 700; }
.su-saved .glyph { width: 18px; height: 18px; stroke-width: 2; }

.su-pair {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 0 12px;
  border: 1px solid var(--border);
  border-radius: var(--kit-radius);
  background: var(--surface-raised);
}
```

- [ ] **Step 6: Write `gui/web/setup.js`**

Replace the file:

```js
// The setup document: Worker selection and SKU mapping, the two full-window
// pages (ADR 0002). The page renders what the bridge sends; what the cards,
// rows and sentences say is decided in gui/setup_payload.py. The page keeps
// only what is being typed, the search text, which row is being edited and
// which question is open. Every string from the bridge goes in through
// textContent.
// Spec: docs/superpowers/specs/2026-10-09-ui-refresh-phase5-setup-pages-design.md
"use strict";

const els = {};
const view = {
  bridge: null,
  creating: false,  // the New worker form is open
  search: "",
  draft: null,      // {id}: 0 for the add draft, else the row being edited
  ask: null,        // {kind: "delete" | "reload" | "leave", id}
  stray: "",        // keys that reached no field (ADR 0004)
};

const SVG_NS = "http://www.w3.org/2000/svg";
const ARROW = "M5 12h14M12 5l7 7-7 7";
const PENCIL = "M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352"
  + "a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z";
const TRASH = "M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2";

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

function glyph(d) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "glyph");
  svg.setAttribute("viewBox", "0 0 24 24");
  const path = document.createElementNS(SVG_NS, "path");
  path.setAttribute("d", d);
  svg.appendChild(path);
  return svg;
}

// Text that an ellipsis may cut keeps its whole self in the tooltip.
function cut(cls, text) {
  const node = el("span", cls, text);
  node.title = text;
  return node;
}

// packer_logic.normalize_sku: letters and digits only, lower case.
function key(text) {
  return String(text).toLowerCase().replace(/[^\p{L}\p{N}]/gu, "");
}

// --- which page -----------------------------------------------------------------

function renderPage() {
  const page = view.bridge.page;
  view.stray = "";
  if (page !== "workers") closeForm();
  if (page !== "mapping") {
    view.search = "";
    els.mSearch.value = "";
    view.draft = null;
    view.ask = null;
  }
  show(els.workers, page === "workers");
  show(els.mapping, page === "mapping");
  renderWorkers();
  renderMapping();
}

// --- Worker selection -------------------------------------------------------------

function workerCard(card) {
  const node = el("button", "card su-card" + (card.picked ? " picked" : ""));
  node.type = "button";
  node.dataset.worker = card.id;
  const top = el("div", "su-card-top");
  top.appendChild(el("span", "su-avatar", card.initials));
  if (card.badge) top.appendChild(el("span", "badge neutral", card.badge));
  const text = el("div", "su-card-text");
  text.appendChild(cut("su-card-name", card.name));
  text.appendChild(el("span", "su-card-line", card.stats));
  text.appendChild(el("span", "su-card-line", card.last));
  node.appendChild(top);
  node.appendChild(text);
  return node;
}

function renderWorkers() {
  const data = view.bridge.workers || {};
  const cards = data.cards || [];
  const failed = data.mode === "failed";
  const error = data.error || {};
  els.wLeave.textContent = data.leave || "";
  show(els.wFailed, failed);
  els.wFailedTitle.textContent = error.title || "";
  els.wFailedText.textContent = error.text || "";
  els.wFailedPath.textContent = error.path || "";
  show(els.wEmpty, !failed && !cards.length);
  show(els.wGrid, !failed);
  els.wGrid.querySelectorAll("[data-worker]").forEach(function (node) { node.remove(); });
  cards.forEach(function (card) { els.wGrid.insertBefore(workerCard(card), els.wNew); });
  els.wGrid.style.setProperty("--su-cols", String(Math.min(4, cards.length + 1)));
  els.wGrid.classList.toggle("lone", !cards.length);
  show(els.wNew, !view.creating);
  show(els.wForm, view.creating);
}

function nameProblem(text) {
  els.wNameError.textContent = text;
  show(els.wNameError, !!text);
  els.wName.classList.toggle("invalid", !!text);
}

function openForm() {
  view.creating = true;
  els.wName.value = "";
  nameProblem("");
  renderWorkers();
  els.wName.focus();
}

function closeForm() {
  view.creating = false;
  els.wName.value = "";
  nameProblem("");
}

function createWorker() {
  view.bridge.createWorker(els.wName.value, function (problem) {
    if (problem) {
      nameProblem(problem);
      els.wName.focus();
    } else {
      closeForm();
      renderWorkers();
    }
  });
}

// --- SKU mapping ------------------------------------------------------------------

function mapping() {
  return view.bridge.mapping || {};
}

// The quick map: the page was opened from Packer Mode for one add (ADR 0004).
function quick() {
  const q = mapping().quick || {};
  return q.kind ? q : null;
}

function rowById(id) {
  return (mapping().rows || []).find(function (row) { return row.id === id; }) || null;
}

// The row the draft's barcode collides with: the same key to the scan matcher.
function clashRow() {
  if (!view.draft) return null;
  const typed = key(els.dBarcode.value);
  if (!typed) return null;
  return (mapping().rows || []).find(function (row) {
    return row.key === typed && row.id !== view.draft.id;
  }) || null;
}

function draftProblem(text) {
  els.dProblem.textContent = text;
  show(els.dProblem, !!text);
}

function iconButton(action, id, label, d) {
  const button = el("button", "btn ghost compact icon su-plain");
  button.type = "button";
  button.dataset.rowAction = action;
  button.dataset.id = id;
  button.title = label;
  button.setAttribute("aria-label", label);
  button.appendChild(glyph(d));
  return button;
}

function mappingRow(row, actions) {
  const node = el("div", "tbl-row su-row");
  node.dataset.row = row.id;
  const dot = el("span", row.status ? "su-undot" : "");
  if (row.status === "new") dot.title = "Added, not saved";
  if (row.status === "edited") dot.title = "Edited, not saved";
  node.appendChild(dot);
  node.appendChild(cut("mono su-cut", row.barcode));
  node.appendChild(glyph(ARROW));
  node.appendChild(cut("mono su-sku su-cut", row.sku));
  const acts = el("span", "su-row-actions");
  if (actions) {
    acts.appendChild(iconButton("edit", row.id, "Edit", PENCIL));
    acts.appendChild(iconButton("delete", row.id, "Delete", TRASH));
  }
  node.appendChild(acts);
  return node;
}

// The draft sits above the rows for an add, and where the row was for an edit.
function placeDraft() {
  const id = view.draft ? view.draft.id : 0;
  const row = id ? els.mRows.querySelector('[data-row="' + id + '"]') : null;
  if (row) {
    row.hidden = true;
    els.mRows.insertBefore(els.mDraft, row);
  } else {
    els.mScroll.insertBefore(els.mDraft, els.mRows);
  }
}

function renderDraft() {
  const open = !!view.draft;
  const q = quick();
  show(els.mDraft, open);
  if (!open) return;
  const hit = clashRow();
  const barcode = els.dBarcode.value.trim();
  const sku = els.dSku.value.trim();
  els.dBarcode.classList.toggle("invalid", !!hit);
  show(els.dClash, !!hit);
  if (hit) {
    els.dClashSku.textContent = hit.sku;
    els.dClashAsk.textContent = sku ? " Replace it with " + sku + "?" : " Enter a SKU to replace it.";
    els.dReplace.disabled = !sku;
  }
  els.mRows.querySelectorAll("[data-row]").forEach(function (node) {
    node.classList.toggle("clash", !!hit && Number(node.dataset.row) === hit.id);
  });
  els.dCommit.textContent = view.draft.id ? "Update" : "Add";
  els.dCommit.disabled = !barcode || !sku || !!hit;
  show(els.dCancel, !q);
  els.dBarcode.disabled = !!q && q.kind === "barcode";
  els.dSku.disabled = !!q && q.kind === "sku";
  els.dHint.textContent = q ? q.hint : "";
  show(els.dHint, !!q && !hit);
  show(els.dChoices, !!q && q.kind === "barcode");
}

function renderRows() {
  const rows = mapping().rows || [];
  const needle = view.search.trim().toLowerCase();
  const focused = document.activeElement;
  // Out of the row list before it is rebuilt, or the draft goes with it.
  els.mScroll.insertBefore(els.mDraft, els.mRows);
  els.mRows.replaceChildren();
  let shownRows = 0;
  // ponytail: every row is drawn; the largest client has under 200 mappings.
  // Window the list if one ever passes a few thousand.
  rows.forEach(function (row) {
    const editing = !!view.draft && view.draft.id === row.id;
    const matches = !needle || row.barcode.toLowerCase().includes(needle)
      || row.sku.toLowerCase().includes(needle);
    if (!matches && !editing) return;
    shownRows += 1;
    els.mRows.appendChild(mappingRow(row, !quick()));
  });
  placeDraft();
  // Moving the draft took the focus off its field.
  if (focused && els.mDraft.contains(focused)) focused.focus();
  const total = plural(rows.length, "mapping", "mappings");
  els.mCount.textContent = needle ? shownRows + " of " + total : total;
  els.mNohitsQ.textContent = view.search.trim();
  show(els.mNohits, !!needle && !shownRows);
  renderDraft();
}

function renderChoices(q) {
  els.dChoices.replaceChildren();
  ((q && q.choices) || []).forEach(function (choice) {
    const button = el("button", "btn secondary compact", choice.label);
    button.type = "button";
    button.dataset.choice = choice.sku;
    els.dChoices.appendChild(button);
  });
}

const ASK = {
  delete: { title: "Delete this mapping?", yes: "Delete", no: "Cancel" },
  reload: { title: "Reload from server?", yes: "Discard and reload", no: "Cancel" },
  leave: { title: "Discard unsaved changes?", yes: "Discard", no: "Keep editing" },
};

function renderAsk() {
  let ask = view.ask;
  const row = ask && ask.kind === "delete" ? rowById(ask.id) : null;
  if (ask && ask.kind === "delete" && !row) ask = view.ask = null;
  show(els.mAsk, !!ask);
  if (!ask) return;
  const copy = ASK[ask.kind];
  els.mAskTitle.textContent = copy.title;
  els.mAskYes.textContent = copy.yes;
  els.mAskNo.textContent = copy.no;
  show(els.mAskPair, !!row);
  if (row) {
    els.mAskBarcode.textContent = row.barcode;
    els.mAskSku.textContent = row.sku;
    els.mAskText.textContent = "Once you save, scanning this barcode on any PC will no longer"
      + " count as " + row.sku + ".";
  } else {
    els.mAskText.textContent = (mapping().lost || "") + (ask.kind === "reload"
      ? " The list is replaced with the copy on the file server." : "");
  }
}

function focusQuick() {
  const q = quick();
  if (!q || view.bridge.page !== "mapping") return;
  (q.kind === "sku" ? els.dBarcode : els.dSku).focus();
}

function renderMapping() {
  const data = mapping();
  const q = quick();
  const rows = data.rows || [];
  const failed = data.mode === "failed";
  const error = data.error || {};

  if (view.draft && view.draft.id && !rowById(view.draft.id)) view.draft = null;
  if (q && !view.draft && view.bridge.page === "mapping") {
    // A quick map is its draft: open, the known side filled. Only while the
    // page shows: Python blanks `page` before it empties this payload, and a
    // draft opened then would outlive the quick map.
    view.draft = { id: 0 };
    els.dBarcode.value = q.barcode || "";
    els.dSku.value = q.sku || "";
    draftProblem("");
  }

  els.mClient.textContent = data.client || "";
  show(els.mError, !!error.title);
  els.mErrorTitle.textContent = error.title || "";
  els.mErrorText.textContent = error.text || "";
  els.mErrorCause.textContent = error.cause || "";
  els.mErrorPath.textContent = error.path || "";
  els.mErrorAction.textContent = error.action === "load" ? "Retry" : "Try again";
  show(els.mErrorAction, !!error.action);

  const empty = !failed && !rows.length && !view.draft;
  show(els.mEmpty, empty);
  show(els.mTable, !failed && !empty);
  show(els.mAdd, !failed && !empty && !q);
  show(els.mReload, !q);
  show(els.mUnsaved, !!data.dirty && !error.title);
  els.mSummary.textContent = data.summary || "";
  show(els.mSaved, !!data.saved);
  show(els.mSave, !q);
  els.mSave.disabled = !data.dirty;
  els.mCancel.textContent = q ? "Back to packing" : "Cancel";

  renderChoices(q);
  renderRows();
  renderAsk();
  if (q && document.activeElement === document.body) focusQuick();
}

function startAdd() {
  view.search = "";
  els.mSearch.value = "";
  view.draft = { id: 0 };
  els.dBarcode.value = "";
  els.dSku.value = "";
  draftProblem("");
  renderMapping();
  els.dBarcode.focus();
}

function startEdit(id) {
  const row = rowById(id);
  if (!row) return;
  view.draft = { id: id };
  els.dBarcode.value = row.barcode;
  els.dSku.value = row.sku;
  draftProblem("");
  renderMapping();
  els.dSku.focus();
}

function leaveMapping() {
  if (mapping().dirty) {
    view.ask = { kind: "leave" };
    renderAsk();
  } else {
    view.bridge.closeMapping();
  }
}

function cancelDraft() {
  if (quick()) {
    leaveMapping();
    return;
  }
  view.draft = null;
  draftProblem("");
  renderMapping();
}

// What a slot answered: "" when the thing was done, else the sentence.
function draftDone(problem) {
  if (problem) {
    draftProblem(problem);
    return;
  }
  if (quick()) return;  // Python is leaving the page
  if (view.draft && !view.draft.id) {
    // The add row stays open for the next one.
    els.dBarcode.value = "";
    els.dSku.value = "";
    draftProblem("");
    renderMapping();
    els.dBarcode.focus();
  } else {
    view.draft = null;
    renderMapping();
  }
}

function commitDraft() {
  if (!view.draft) return;
  const barcode = els.dBarcode.value;
  const sku = els.dSku.value;
  if (!barcode.trim()) { els.dBarcode.focus(); return; }
  if (!sku.trim()) { els.dSku.focus(); return; }
  if (clashRow()) return;  // only Replace goes on from a collision
  if (view.draft.id) view.bridge.updateMapping(view.draft.id, barcode, sku, draftDone);
  else view.bridge.addMapping(barcode, sku, draftDone);
}

function replaceDraft() {
  if (!view.draft || !els.dSku.value.trim()) return;
  view.bridge.replaceMapping(view.draft.id, els.dBarcode.value, els.dSku.value, draftDone);
}

// Enter in the barcode field, which is also how a scan ends.
function barcodeEnter() {
  if (!els.dBarcode.value.trim() || clashRow()) return;
  const q = quick();
  if (q && q.kind === "sku") commitDraft();
  else els.dSku.focus();
}

function deleteRow(id) {
  const row = rowById(id);
  if (!row) return;
  if (row.status === "new") {
    // Never saved: nothing on the server changes, so nothing to ask.
    if (view.draft && view.draft.id === id) view.draft = null;
    view.bridge.deleteMapping(id);
    return;
  }
  view.ask = { kind: "delete", id: id };
  renderAsk();
}

function reload() {
  if (mapping().dirty) {
    view.ask = { kind: "reload" };
    renderAsk();
  } else {
    view.bridge.reloadMappings();
  }
}

function save() {
  if (view.bridge.page === "mapping" && !quick() && mapping().dirty) view.bridge.saveMappings();
}

function askYes() {
  const ask = view.ask;
  view.ask = null;
  renderAsk();
  if (!ask) return;
  if (ask.kind === "delete") {
    if (view.draft && view.draft.id === ask.id) view.draft = null;
    view.bridge.deleteMapping(ask.id);
  } else if (ask.kind === "reload") {
    view.draft = null;
    view.bridge.reloadMappings();
  } else {
    view.bridge.closeMapping();
  }
}

// --- keys and clicks --------------------------------------------------------------

function escapePressed() {
  const page = view.bridge.page;
  if (page === "workers") {
    if (view.creating) {
      closeForm();
      renderWorkers();
    }
    return;
  }
  if (page !== "mapping") return;
  if (view.ask) {
    view.ask = null;
    renderAsk();
  } else if (view.draft && !quick()) {
    cancelDraft();
  } else {
    leaveMapping();
  }
}

function onKey(event) {
  const target = event.target;
  const inField = target instanceof HTMLInputElement && !target.disabled;
  if ((event.ctrlKey || event.metaKey) && String(event.key).toLowerCase() === "s") {
    event.preventDefault();
    save();
    return;
  }
  if (event.ctrlKey || event.altKey || event.metaKey) return;
  if (event.key === "Escape") {
    event.preventDefault();
    escapePressed();
    return;
  }
  if (inField) {
    if (event.key !== "Enter") return;
    event.preventDefault();
    if (target === els.wName) createWorker();
    else if (target === els.dBarcode) barcodeEnter();
    else if (target === els.dSku) commitDraft();
    return;
  }
  // No field has this key, so it is a scan in flight (ADR 0004): buffered,
  // and handed to Python whole when its Enter arrives. An Enter with nothing
  // buffered is a person pressing a focused button, and is left alone.
  // ponytail: the buffer is dropped on a click or a page change, not on a
  // timer; a timer is the upgrade if lone keys ever pollute a scan.
  if (event.key === "Enter") {
    if (!view.stray) return;
    event.preventDefault();
    const text = view.stray;
    view.stray = "";
    view.bridge.strayScan(text);
  } else if (event.key.length === 1) {
    event.preventDefault();
    view.stray += event.key;
  }
}

const ACTIONS = {
  leaveWorkers: function () { view.bridge.leaveWorkers(); },
  retryWorkers: function () { view.bridge.retryWorkers(); },
  newWorker: openForm,
  createWorker: createWorker,
  cancelWorker: function () { closeForm(); renderWorkers(); },
  startAdd: startAdd,
  commitDraft: commitDraft,
  cancelDraft: cancelDraft,
  replaceDraft: replaceDraft,
  reload: reload,
  save: save,
  leaveMapping: leaveMapping,
  errorAction: function () {
    if ((mapping().error || {}).action === "load") view.bridge.reloadMappings();
    else view.bridge.saveMappings();
  },
  askYes: askYes,
  askNo: function () { view.ask = null; renderAsk(); },
};

function onClick(event) {
  view.stray = "";
  const action = event.target.closest("[data-action]");
  if (action) {
    if (!action.disabled) ACTIONS[action.dataset.action]();
    return;
  }
  const rowAction = event.target.closest("[data-row-action]");
  if (rowAction) {
    const id = Number(rowAction.dataset.id);
    if (rowAction.dataset.rowAction === "edit") startEdit(id);
    else deleteRow(id);
    return;
  }
  const choice = event.target.closest("[data-choice]");
  if (choice) {
    els.dSku.value = choice.dataset.choice;
    commitDraft();
    return;
  }
  const worker = event.target.closest("[data-worker]");
  if (worker) view.bridge.pickWorker(worker.dataset.worker);
}

const IDS = {
  root: "setup", themeVars: "theme-vars",
  workers: "workers", wLeave: "w-leave", wFailed: "w-failed", wFailedTitle: "w-failed-title",
  wFailedText: "w-failed-text", wFailedPath: "w-failed-path", wEmpty: "w-empty",
  wGrid: "w-grid", wNew: "w-new", wForm: "w-form", wName: "w-name",
  wNameError: "w-name-error",
  mapping: "mapping", mClient: "m-client", mAdd: "m-add", mError: "m-error",
  mErrorTitle: "m-error-title", mErrorText: "m-error-text", mErrorPath: "m-error-path",
  mErrorCause: "m-error-cause", mErrorAction: "m-error-action",
  mEmpty: "m-empty", mTable: "m-table", mSearch: "m-search", mCount: "m-count",
  mReload: "m-reload", mScroll: "m-scroll", mDraft: "m-draft", mRows: "m-rows",
  mNohits: "m-nohits", mNohitsQ: "m-nohits-q",
  dBarcode: "d-barcode", dSku: "d-sku", dCommit: "d-commit", dCancel: "d-cancel",
  dClash: "d-clash", dClashSku: "d-clash-sku", dClashAsk: "d-clash-ask",
  dReplace: "d-replace", dProblem: "d-problem", dHint: "d-hint", dChoices: "d-choices",
  mUnsaved: "m-unsaved", mSummary: "m-summary", mSaved: "m-saved",
  mCancel: "m-cancel", mSave: "m-save",
  mAsk: "m-ask", mAskTitle: "m-ask-title", mAskPair: "m-ask-pair",
  mAskBarcode: "m-ask-barcode", mAskSku: "m-ask-sku", mAskText: "m-ask-text",
  mAskNo: "m-ask-no", mAskYes: "m-ask-yes",
};

new QWebChannel(qt.webChannelTransport, function (channel) {
  const bridge = channel.objects.setup;
  view.bridge = bridge;
  // The test harness drives the page through this handle; nothing in the
  // page reads it.
  window.setupBridge = bridge;
  Object.keys(IDS).forEach(function (name) {
    els[name] = document.getElementById(IDS[name]);
  });

  const onTheme = function () { els.themeVars.textContent = bridge.themeCss; };
  onTheme();
  bridge.themeCssChanged.connect(onTheme);

  bridge.pageChanged.connect(renderPage);
  bridge.workersChanged.connect(renderWorkers);
  bridge.mappingChanged.connect(renderMapping);
  bridge.leaveAsked.connect(function () {
    if (bridge.page !== "mapping" || !mapping().dirty) return;
    view.ask = { kind: "leave" };
    renderAsk();
  });
  renderPage();

  els.wName.addEventListener("input", function () { nameProblem(""); });
  els.mSearch.addEventListener("input", function () {
    view.search = els.mSearch.value;
    renderRows();
  });
  els.dBarcode.addEventListener("input", function () {
    // A barcode has no spaces, however it was pasted.
    const bare = els.dBarcode.value.replace(/\s/g, "");
    if (bare !== els.dBarcode.value) els.dBarcode.value = bare;
    draftProblem("");
    renderDraft();
  });
  els.dSku.addEventListener("input", function () {
    draftProblem("");
    renderDraft();
  });
  // In a quick map the focus is never left on nothing: a scan must have a
  // field to land in (ADR 0004).
  document.addEventListener("focusout", function () {
    setTimeout(function () {
      if (quick() && !view.ask && document.activeElement === document.body) focusQuick();
    }, 0);
  });
  document.addEventListener("keydown", onKey);
  els.root.addEventListener("click", onClick);

  // After the first render, so the first report is of a drawn page.
  reportPaints(bridge);
  document.documentElement.dataset.bridge = "ready";
});
```

- [ ] **Step 7: Run the page tests and see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_setup_page_web.py`
Expected: PASS. Two things to check first when one fails:

- **An answering slot's callback never runs.** `QWebChannel` passes a slot's return value to a function given as the call's last argument. If `createWorker`/`addMapping` return nothing to the page, check the `@Slot(..., result=str)` decorators in `gui/setup_bridge.py`.
- **`:not([hidden])` or `closest('[hidden]')` disagree with what is on screen.** The page hides with the `hidden` attribute only (`show()`); do not hide anything with a class.

- [ ] **Step 8: Look at both pages**

Write a throwaway script outside the repo that mounts the page as `tests/setup_web.py:mounted` does, sets a payload, and saves `view.grab()` to a PNG at 1366×768 in each theme (`gui.theme.apply_theme(app, "light")`, then `"dark"`). Open the PNGs with the Read tool and compare them with the two mockups: the Worker selection grid (six cards and *New worker*), and SKU mapping with 60 rows, with the draft open, and with the Delete question. Fix what does not match the spec's sections 5.1 and 6.1. Task 8 writes the real render script; this is only to catch a broken layout now. Delete the throwaway script.

- [ ] **Step 9: Run the guards, lint, commit**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_style_literals_guard.py tests/test_setup_page_web.py tests/test_setup_pages.py`
Expected: PASS. A style finding names the file and line: replace the literal with a token.
Run: `.venv/bin/ruff check . --exclude shared`
Run: `graphify update .`

Commit `gui/web/setup.html`, `gui/web/setup.css`, `gui/web/setup.js`, `tests/setup_web.py`, `tests/test_setup_page_web.py` with the message "The setup document: Worker selection and SKU mapping pages".

---

### Task 6: The window: startup, *Switch worker…* and SKU mapping from the sidebar

**Files:**
- Modify: `gui/main_window.py`
- Delete: `gui/sku_mapping_dialog.py`, `gui/worker_selection_dialog.py`
- Test: `tests/test_setup_mainwindow_seam.py` (new); modify `tests/test_shell.py`, `tests/test_screen_primaries.py`

**Interfaces:**
- Consumes: `SetupPages` (Task 4) and its signals; `shared.web_page.when_painted`; `AppBridge.set_covered(bool)`.
- Produces, on `MainWindow`: attribute `setup_pages: SetupPages` (third widget of `stacked_widget`); `_setup_showing() -> bool`; `_open_setup(show: Callable[[], None]) -> None`; `_leave_setup(after: Callable[[], None] | None = None) -> None`; `switch_worker() -> None`; `open_sku_mapping() -> None`; attributes `_setup_return` (the widget to go back to) and `_stray_scans: list[str]`. Module function `gui.main_window._under_pytest() -> bool`.
- `_select_worker` and `open_sku_mapping_dialog` no longer exist.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_setup_mainwindow_seam.py`:

```python
"""MainWindow and the setup pages: the ways in, and the way back (spec section 4.4)."""

import pytest
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from setup_web import eval_js, settle, until_js

import gui.main_window as mw
from gui.main_window import PAGE_STATISTICS
from packing_tool.profile_manager import ProfileManager


def on_setup(window) -> bool:
    return window.stacked_widget.currentWidget() is window.setup_pages


def in_shell(window) -> bool:
    return window.stacked_widget.currentWidget() is window.session_widget


def test_under_test_the_window_starts_on_the_shell_with_the_setup_pages_in_the_stack(main_window):
    assert in_shell(main_window)
    assert main_window.stacked_widget.indexOf(main_window.setup_pages) != -1
    assert main_window.current_worker_name == "Test Worker"
    assert not hasattr(main_window, "_select_worker")
    assert not hasattr(main_window, "open_sku_mapping_dialog")


def test_outside_test_mode_the_window_starts_on_worker_selection(
    config_ini, monkeypatch, qtbot
):
    monkeypatch.setattr(mw, "_under_pytest", lambda: False)
    ProfileManager(config_path=str(config_ini)).create_client_profile("TESTCL", "Test Client")
    window = mw.MainWindow(config_path=str(config_ini))
    try:
        assert on_setup(window)
        bridge = window.setup_pages.bridge
        assert bridge.page == "workers"
        assert bridge.workers["context"] == "startup" and bridge.workers["leave"] == "Quit"
        assert window.current_worker_id is None

        worker = window.worker_manager.create_worker("Ivan")
        bridge.retryWorkers()
        bridge.pickWorker(worker.id)
        qtbot.waitUntil(lambda: in_shell(window), timeout=3000)
        assert window.current_worker_id == worker.id
        assert window.current_worker_name == "Ivan"
        assert window.sidebar.worker_name.toolTip() == "Ivan"
        assert bridge.page == ""
    finally:
        window.sessions.shutdown()
        window.deleteLater()


def test_quit_on_worker_selection_closes_the_window(config_ini, monkeypatch):
    monkeypatch.setattr(mw, "_under_pytest", lambda: False)
    window = mw.MainWindow(config_path=str(config_ini))
    try:
        closed = []
        monkeypatch.setattr(window, "close", lambda: closed.append(1))
        window.setup_pages.bridge.leaveWorkers()
        assert closed == [1]
    finally:
        window.sessions.shutdown()
        window.deleteLater()


def test_switch_worker_opens_the_page_and_back_changes_nothing(main_window, qtbot):
    window = main_window
    window.session_tabs.setCurrentIndex(PAGE_STATISTICS)
    window.sidebar.switchWorkerRequested.emit()
    assert on_setup(window)
    payload = window.setup_pages.bridge.workers
    assert payload["context"] == "switch" and payload["leave"] == "Back to Test Worker"

    window.setup_pages.bridge.leaveWorkers()
    qtbot.waitUntil(lambda: in_shell(window), timeout=3000)
    assert window.current_worker_name == "Test Worker"
    assert window.session_tabs.currentIndex() == PAGE_STATISTICS


def test_switching_to_another_worker_tells_the_sidebar(main_window, qtbot):
    window = main_window
    maria = window.worker_manager.create_worker("Maria")
    window.switch_worker()
    window.setup_pages.bridge.pickWorker(maria.id)
    qtbot.waitUntil(lambda: in_shell(window), timeout=3000)
    assert (window.current_worker_id, window.current_worker_name) == (maria.id, "Maria")
    assert window.sidebar.worker_name.toolTip() == "Maria"


def test_sku_mapping_opens_for_the_current_client_and_close_returns(main_window, qtbot):
    window = main_window
    window.sidebar.skuMappingRequested.emit()
    assert on_setup(window)
    bridge = window.setup_pages.bridge
    assert bridge.page == "mapping"
    assert bridge.mapping["client"] == window.client_combo.currentText()
    assert bridge.mapping["quick"] == {}

    bridge.closeMapping()
    qtbot.waitUntil(lambda: in_shell(window), timeout=3000)
    assert bridge.page == ""


def test_opening_twice_is_one_page(main_window):
    main_window.open_sku_mapping()
    main_window.switch_worker()  # ignored: a setup page is already up
    assert main_window.setup_pages.bridge.page == "mapping"


def test_with_no_client_sku_mapping_does_not_open(main_window):
    main_window.current_client_id = None
    main_window.open_sku_mapping()
    assert in_shell(main_window)


def test_a_saved_mapping_reaches_the_open_session(main_window_with_list, qtbot):
    window = main_window_with_list
    window.open_sku_mapping()
    bridge = window.setup_pages.bridge
    assert bridge.addMapping("5906000123456", "TS-4409-B") == ""
    bridge.saveMappings()
    assert window.logic.sku_map["5906000123456"] == "TS-4409-B"
    assert bridge.mapping["saved"] is True
    assert on_setup(window)  # Save stays on the page


def test_ctrl_e_does_nothing_on_a_setup_page(main_window, monkeypatch):
    window = main_window
    shortcut = next(
        s for s in window.findChildren(QShortcut) if s.key() == QKeySequence("Ctrl+E")
    )
    clicks = []
    monkeypatch.setattr(window.toolbar_end_btn, "click", lambda: clicks.append(1))
    window.open_sku_mapping()
    shortcut.activated.emit()
    assert clicks == []


def test_closing_the_window_with_unsaved_mappings_is_refused_and_asked_about(
    main_window, qtbot
):
    window = main_window
    window.open_sku_mapping()
    window.setup_pages.bridge.addMapping("5906000123456", "X")
    event = QCloseEvent()
    with qtbot.waitSignal(window.setup_pages.bridge.leaveAsked, timeout=1000):
        window.closeEvent(event)
    assert not event.isAccepted()
    assert on_setup(window)


@pytest.fixture
def shown(main_window, qtbot):
    main_window.show()
    qtbot.waitExposed(main_window)
    for view in (main_window.session_tabs.view, main_window.setup_pages.view):
        until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    yield main_window
    main_window.hide()


def test_the_setup_document_has_painted_itself_blank_before_the_shell_returns(shown, qtbot):
    """ADR 0003: a hidden view keeps its last frame, so that frame must be the
    blank one, never the mappings of a page that is gone."""
    window = shown
    view, bridge = window.setup_pages.view, window.setup_pages.bridge
    window.open_sku_mapping()
    qtbot.waitUntil(lambda: on_setup(window), timeout=3000)
    settle(qtbot, bridge)
    assert "SKU mapping" in eval_js(qtbot, view, "document.body.innerText")

    at_switch = []
    window.stacked_widget.currentChanged.connect(
        lambda _index: at_switch.append((bridge.page, bridge.painted_revision >= bridge.revision))
    )
    bridge.closeMapping()
    qtbot.waitUntil(lambda: in_shell(window), timeout=3000)
    assert at_switch == [("", True)]
    assert window.session_tabs.bridge.covered is False
```

In `tests/test_shell.py`, in `test_the_sidebar_footer_reaches_what_the_overflow_used_to`, change the two patched names:

```python
    monkeypatch.setattr(window, "open_sku_mapping", lambda: calls.append("sku"))
    monkeypatch.setattr(window, "switch_worker", lambda: calls.append("worker"))
```

In `tests/test_screen_primaries.py`, delete `test_save_and_close_is_the_sku_mapping_dialogs_one_primary` and the line `from gui.sku_mapping_dialog import SKUMappingDialog`, and change the first paragraph of the module docstring from "Pins the four call sites" to "Pins the call sites" (the count is no longer four).

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_setup_mainwindow_seam.py`
Expected: FAIL, `'MainWindow' object has no attribute 'setup_pages'`.

- [ ] **Step 3: Change `gui/main_window.py`**

All line numbers are as the file is before this task.

**(a) Imports.** Delete lines 56 and 58:

```python
from gui.sku_mapping_dialog import SKUMappingDialog
from gui.worker_selection_dialog import WorkerSelectionDialog
```

and add, in the same block (keep it sorted):

```python
from gui.setup_pages import SetupPages
```

Remove `QDialog` from the `PySide6.QtWidgets` import; ruff will confirm nothing else uses it.

**(b) Test mode.** Above `class MainWindow` (after `_unmapped_choices`), add:

```python
def _under_pytest() -> bool:
    """Whether the suite is running: it must not start on Worker selection."""
    return "pytest" in sys.modules
```

and change line 198 to:

```python
        self._is_test_mode = skip_worker_selection or _under_pytest()
```

**(c) Startup.** Replace the block at lines 284 to 294 (from the comment "Show worker selection BEFORE main window initialization" to the end of its `else`) with:

```python
        if self._is_test_mode:
            # Test mode - use dummy worker
            self.current_worker_id = "test_worker_001"
            self.current_worker_name = "Test Worker"
            logger.info(f"Test mode: Using dummy worker {self.current_worker_name}")
```

and after `self.load_available_clients()` near the end of `__init__`, before the final log line, add:

```python
        if not self._is_test_mode:
            # The first thing a packer sees: who is packing (spec 2026-10-09,
            # section 4.4). The shell is built and waits underneath.
            self._open_setup(lambda: self.setup_pages.show_workers(startup=True))
```

Also update the constructor docstring's `skip_worker_selection` line to "If True, start on the shell with a dummy worker (for tests and render scripts)".

**(d) The stack.** In `_init_ui`, change the two sidebar connections (lines 407 and 408) to:

```python
        self.sidebar.skuMappingRequested.connect(lambda: self.open_sku_mapping())
        self.sidebar.switchWorkerRequested.connect(lambda: self.switch_worker())
```

and replace the stacked-widget block (lines 446 to 450) with:

```python
        # Worker selection and SKU mapping: the setup document, full window
        # (spec 2026-10-09 section 4). Lambdas, so a test that replaces a
        # handler is seen.
        self.setup_pages = SetupPages(self.worker_manager, self.profile_manager)
        self.setup_pages.workerChosen.connect(
            lambda worker_id, name: self._on_worker_chosen(worker_id, name)
        )
        self.setup_pages.quitRequested.connect(lambda: self.close())
        self.setup_pages.backRequested.connect(lambda: self._leave_setup())
        self.setup_pages.mappingSaved.connect(lambda mapping: self._on_mapping_saved(mapping))
        self._setup_return = self.session_widget  # where a setup page goes back to
        self._opening_setup = False
        self._leaving_setup = False
        self._stray_scans: list[str] = []  # see _on_stray_scan()

        # The shell, Packer Mode and the setup pages: one at a time.
        self.stacked_widget = QStackedWidget()
        self.stacked_widget.addWidget(self.session_widget)
        self.stacked_widget.addWidget(self.packer_mode_widget)
        self.stacked_widget.addWidget(self.setup_pages)
        self.setCentralWidget(self.stacked_widget)
```

**(e) Ctrl+E.** In `_init_overflow`, change the shortcut's connection to:

```python
        # Through click(), which is a no-op on the disabled no-session button.
        # Not from a setup page: the session is out of sight there.
        end_shortcut = QShortcut(QKeySequence("Ctrl+E"), self)
        end_shortcut.activated.connect(
            lambda: None if self._setup_showing() else self.toolbar_end_btn.click()
        )
```

**(f) The ways in and the way back.** Replace the whole `_select_worker` method (lines 591 to 626) with:

```python
    # ========================================================================
    # SETUP PAGES: Worker selection and SKU mapping (spec 2026-10-09)
    # ========================================================================

    def _setup_showing(self) -> bool:
        return self.stacked_widget.currentWidget() is self.setup_pages

    def _open_setup(self, show) -> None:
        """Put a setup page over whatever is showing, and remember what that was.

        `show` is one of SetupPages' show_* methods, bound to its arguments.
        From the shell the app document is told to draw nothing first, and the
        switch waits for that paint (ADR 0003). From Packer Mode the switch is
        immediate and its document is left alone: the packer comes back to the
        same order, and a scan must not fall into a gap (ADR 0004).
        """
        if (
            self._setup_showing()
            or self._opening_setup
            or self._entering_packer_mode
            or self._leaving_packer_mode
        ):
            return
        self._setup_return = self.stacked_widget.currentWidget()
        self._stray_scans = []
        show()

        def enter():
            self._opening_setup = False
            self.stacked_widget.setCurrentWidget(self.setup_pages)
            self.setup_pages.view.setFocus()

        pages = self.session_tabs
        if self._setup_return is self.session_widget and pages.view.isVisible():
            self._opening_setup = True
            pages.bridge.set_covered(True)
            when_painted(pages.bridge, enter)
        else:
            enter()

    def _leave_setup(self, after=None) -> None:
        """Go back to where the setup page was opened from.

        The page is blanked and the switch waits for that paint, 150 ms at
        most: a hidden view keeps its last frame (ADR 0003). `after` runs once
        Packer Mode is back and its scanner has the focus, before any stray
        scan is replayed.
        """
        if not self._setup_showing() or self._leaving_setup:
            return
        self._leaving_setup = True
        target = self._setup_return
        self.setup_pages.blank()

        def switch():
            self._leaving_setup = False
            if target is self.packer_mode_widget:
                self.stacked_widget.setCurrentWidget(target)
                target.set_focus_to_scanner()
                if after is not None:
                    after()
                strays, self._stray_scans = self._stray_scans, []
                for text in strays:
                    self.on_scanner_input(text)
                return
            # Before the shell shows: what it shows is current.
            self._push_pages()
            self.session_tabs.bridge.set_covered(False)
            self.stacked_widget.setCurrentWidget(self.session_widget)

        when_painted(self.setup_pages.bridge, switch)

    def switch_worker(self) -> None:
        """The sidebar's Switch worker…"""
        self._open_setup(
            lambda: self.setup_pages.show_workers(
                self.current_worker_id or "", self.current_worker_name or "", startup=False
            )
        )

    def _on_worker_chosen(self, worker_id: str, name: str) -> None:
        self.current_worker_id = worker_id
        self.current_worker_name = name
        self.sidebar.set_worker(name)
        logger.info(f"Logged in as: {name} ({worker_id})")
        self._leave_setup()
```

**(g) SKU mapping.** Replace the whole `open_sku_mapping_dialog` method (lines 819 to 858) with:

```python
    def open_sku_mapping(self) -> None:
        """The sidebar's SKU mapping: the full-window page for the current client."""
        if not self.current_client_id:
            return  # the sidebar's item is disabled until a client is chosen
        client_id = self.current_client_id
        label = self.client_combo.currentText()
        self._open_setup(lambda: self.setup_pages.show_mapping(client_id, label))

    def _on_mapping_saved(self, mapping: dict) -> None:
        """A Save on the mapping page: the open session matches by it at once."""
        if self.logic:
            self.logic.set_sku_map(mapping)
```

**(h) Closing.** In `closeEvent`, directly after the `if self._starting:` block, add:

```python
        if self._setup_showing() and self.setup_pages.dirty():
            # Unsaved mappings: the page asks, and the window stays
            # (spec 2026-10-09 section 6.6).
            event.ignore()
            self.setup_pages.ask_leave()
            return
```

- [ ] **Step 4: Delete the two dialogs**

Run: `/usr/bin/git rm gui/sku_mapping_dialog.py`
Run: `/usr/bin/git rm gui/worker_selection_dialog.py`
Run: `grep -rn "sku_mapping_dialog\|SKUMappingDialog\|worker_selection_dialog\|WorkerSelectionDialog\|_select_worker\|open_sku_mapping_dialog" --include=*.py gui packing_tool tests scripts main.py run_dev.py`
Expected: no output. (`gui/components/sidebar.py` has an object name `WorkerCard` for its footer card; that is a different thing and stays.)

- [ ] **Step 5: Run the tests and see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_setup_mainwindow_seam.py tests/test_shell.py tests/test_screen_primaries.py`
Expected: PASS.

If `test_the_setup_document_has_painted_itself_blank_before_the_shell_returns` records `("", False)`: `when_painted` timed out before the page reported. Check that `setup.js` calls `reportPaints(bridge)` and that `SetupPages.blank()` sets `page` before the two payloads.

- [ ] **Step 6: Run the whole suite, lint, commit**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: PASS. A test elsewhere that still names a deleted method fails here: repoint it at `open_sku_mapping` or `switch_worker`.
Run: `.venv/bin/ruff check . --exclude shared`
Run: `graphify update .`

Commit the changed and deleted files with the message "Worker selection and SKU mapping open as full-window pages; the two dialogs are gone".

---

### Task 7: The quick map from Packer Mode, and stray scans

**Files:**
- Modify: `gui/main_window.py`, `gui/packer_mode_widget.py:353-371`
- Test: `tests/test_setup_scanner.py` (new); modify `tests/audit/test_02_concurrency_sweep.py`

**Interfaces:**
- Consumes: `MainWindow._open_setup`, `_leave_setup(after)`, `_setup_return`, `_stray_scans` (Task 6); `SetupPages.quickMapped(kind, barcode, sku, mapping)` and `strayScanned(text)` (Task 4); `order_choices`, `quick_payload` (Task 2); `PackerModeWidget.map_sku_requested(str)`, `map_barcode_requested(str)`, `show_notification(text, role)`, `show_unknown_scans(list)`, `show_takeover(holder, list_name)`, `set_focus_to_scanner()`, `scanner_input`.
- Produces, on `MainWindow`: `_on_quick_mapped(kind, barcode, sku, mapping)`, `_on_stray_scan(text)`; `_on_map_sku_from_packer(sku)` and `_on_map_barcode_from_packer(barcode)` keep their names and open the quick map. `_save_sku_mapping` and `_unmapped_choices` no longer exist.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_setup_scanner.py`:

```python
"""ADR 0004: SKU mapping takes the keyboard from Packer Mode, and gives it back.

Real key events through a real Chromium, the way a barcode scanner (a
keyboard wedge) sends them. The owner confirms the same on a Windows build
with a real scanner. Never mark these skip.
"""

from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from setup_web import eval_js, until_js

import gui.main_window as mw

UNKNOWN = "9999999999"


def in_packer_mode(window) -> bool:
    return window.stacked_widget.currentWidget() is window.packer_mode_widget


def on_setup(window) -> bool:
    return window.stacked_widget.currentWidget() is window.setup_pages


def scan(text):
    """What a scanner does: types into whatever has the focus, then Enter."""
    target = QApplication.focusWidget()
    QTest.keyClicks(target, text)
    QTest.keyClick(target, Qt.Key.Key_Return)


def saved(window) -> dict:
    return window.profile_manager.load_sku_mapping("TESTCL", fresh=True)


@pytest.fixture
def packing(main_window_with_list, qtbot):
    """A shown window in Packer Mode with order #10429 (one TS-4409-B) open."""
    window = main_window_with_list
    window.show()
    qtbot.waitExposed(window)
    window.activateWindow()
    for view in (
        window.session_tabs.view,
        window.setup_pages.view,
        window.packer_mode_widget.document_view,
    ):
        until_js(qtbot, view, "document.documentElement.dataset.bridge === 'ready'")
    window.stacked_widget.setCurrentWidget(window.packer_mode_widget)
    window.packer_mode_widget.set_focus_to_scanner()
    window.on_scanner_input("#10429")
    assert window.logic.current_order_number is not None
    yield window
    window.hide()


@pytest.fixture
def replayed(packing, monkeypatch):
    """Every text sent to on_scanner_input from here on, still acted on."""
    seen = []
    real = packing.on_scanner_input

    def spy(text, *args, **kwargs):
        seen.append(text)
        return real(text, *args, **kwargs)

    monkeypatch.setattr(packing, "on_scanner_input", spy)
    return seen


def open_quick(window, qtbot, *, sku=None, barcode=None):
    bridge = window.packer_mode_widget.bridge
    if sku is not None:
        bridge.mapSku(sku)
        field = "d-barcode"
    else:
        bridge.mapBarcode(barcode)
        field = "d-sku"
    qtbot.waitUntil(lambda: on_setup(window), timeout=3000)
    view = window.setup_pages.view
    until_js(qtbot, view, f"document.activeElement.id === '{field}'")
    qtbot.waitUntil(
        lambda: QApplication.focusWidget() in (view, view.focusProxy()), timeout=3000
    )
    return view


def test_map_sku_takes_the_scanned_barcode_and_gives_the_scanner_back(packing, qtbot):
    window = packing
    open_quick(window, qtbot, sku="TS-4409-B")
    assert window.setup_pages.bridge.mapping["quick"]["kind"] == "sku"

    scan("5906000123456")  # the packer scans the product

    qtbot.waitUntil(lambda: in_packer_mode(window), timeout=3000)
    assert saved(window)["5906000123456"] == "TS-4409-B"
    assert window.logic.sku_map["5906000123456"] == "TS-4409-B"
    # The scanner field has the focus again...
    assert QApplication.focusWidget() is window.packer_mode_widget.scanner_input
    # ...and the next scan is Packer Mode's.
    seen = []
    window.packer_mode_widget.barcode_scanned.connect(seen.append)
    scan("5906000123456")
    assert seen == ["5906000123456"]


def test_a_scan_into_the_sku_field_saves_nothing(packing, qtbot, monkeypatch):
    """The dangerous one: Map barcode… has the focus on SKU, and a stray scan
    would type a barcode there and press Enter."""
    window = packing
    window.on_scanner_input(UNKNOWN)
    assert window.logic.unknown_scans == [UNKNOWN]
    writes = []
    real = window.profile_manager.update_sku_mapping
    monkeypatch.setattr(
        window.profile_manager, "update_sku_mapping",
        lambda *a, **k: (writes.append(a), real(*a, **k))[1],
    )
    view = open_quick(window, qtbot, barcode=UNKNOWN)

    scan("4006381333931")

    until_js(qtbot, view, "!document.getElementById('d-problem').hidden")
    assert eval_js(qtbot, view, "document.getElementById('d-problem').textContent") == (
        "Not on this order. Pick one of the lines below."
    )
    assert writes == []
    assert on_setup(window)
    assert UNKNOWN not in saved(window)


def test_map_barcode_saves_a_sku_of_the_order_and_replays_the_scan(packing, qtbot, replayed):
    window = packing
    window.on_scanner_input(UNKNOWN)
    replayed.clear()
    view = open_quick(window, qtbot, barcode=UNKNOWN)
    assert eval_js(
        qtbot, view, "document.querySelectorAll('#d-choices [data-choice]').length") == 1

    scan("ts 4409 b")  # typed loosely; a scanned SKU label works the same way

    qtbot.waitUntil(lambda: in_packer_mode(window), timeout=3000)
    assert saved(window)[UNKNOWN] == "TS-4409-B"  # the order's own spelling
    assert replayed == [UNKNOWN]  # the scan that had no match is acted on now
    assert UNKNOWN not in window.logic.unknown_scans
    assert QApplication.focusWidget() is window.packer_mode_widget.scanner_input


def test_a_scan_with_no_field_is_held_and_replayed_after_the_return(
    packing, qtbot, replayed, monkeypatch
):
    window = packing
    view = open_quick(window, qtbot, sku="TS-4409-B")
    # Hold the switch back, so the gap it leaves can be scanned into.
    held = []
    monkeypatch.setattr(mw, "when_painted", lambda bridge, callback, *a: held.append(callback))

    window.setup_pages.bridge.closeMapping()  # Back to packing
    assert len(held) == 1 and on_setup(window)
    until_js(qtbot, view, "document.getElementById('mapping').hidden")

    scan("4006381333931")  # no field has the focus: the page is blank

    qtbot.waitUntil(lambda: window._stray_scans == ["4006381333931"], timeout=3000)
    assert replayed == []  # not acted on yet

    held[0]()  # the paint arrives; the window switches

    assert in_packer_mode(window)
    assert replayed == ["4006381333931"]  # exactly once
    assert window._stray_scans == []
    assert QApplication.focusWidget() is window.packer_mode_widget.scanner_input


def test_back_to_packing_saves_nothing_and_gives_the_scanner_back(packing, qtbot):
    window = packing
    before = saved(window)
    open_quick(window, qtbot, sku="TS-4409-B")
    window.setup_pages.bridge.closeMapping()
    qtbot.waitUntil(lambda: in_packer_mode(window), timeout=3000)
    assert saved(window) == before
    assert QApplication.focusWidget() is window.packer_mode_widget.scanner_input
    seen = []
    window.packer_mode_widget.barcode_scanned.connect(seen.append)
    scan("TS-4409-B")
    assert seen == ["TS-4409-B"]


def test_a_stray_scan_reported_after_the_return_is_still_acted_on(packing, replayed):
    packing._on_stray_scan("4006381333931")  # Packer Mode is already back on top
    assert replayed == ["4006381333931"]


def test_a_stray_scan_on_a_page_opened_from_the_shell_is_dropped(main_window, monkeypatch):
    window = main_window
    seen = []
    monkeypatch.setattr(window, "on_scanner_input", lambda text, *a: seen.append(text))
    window.open_sku_mapping()
    window.setup_pages.bridge.strayScan("4006381333931")
    assert seen == [] and window._stray_scans == []


def test_map_barcode_with_no_open_order_only_refocuses_the_scanner(packing, qtbot):
    window = packing
    window.logic.current_order_state = []
    window.packer_mode_widget.bridge.mapBarcode(UNKNOWN)
    qtbot.wait(200)
    assert in_packer_mode(window)
    assert QApplication.focusWidget() is window.packer_mode_widget.scanner_input


def test_a_lock_lost_during_a_quick_map_lands_on_the_take_over_panel(
    packing, qtbot, monkeypatch
):
    window = packing
    open_quick(window, qtbot, sku="TS-4409-B")
    monkeypatch.setattr(
        window.lock_manager, "is_locked", lambda work_dir: (True, {"locked_by": "WH-PC-02"})
    )
    window._on_lock_lost(Path("/sessions/2026-01-01_1/packing/DHL_Orders"))
    qtbot.waitUntil(lambda: in_packer_mode(window), timeout=3000)
    assert window.packer_mode_widget.taken_over
    assert window.logic is not None  # torn down when the packer exits, as on frame 6j
```

In `tests/audit/test_02_concurrency_sweep.py`, replace `_map_on` (lines 100 to 105) with:

```python
def _map_on(pc: ProfileManager, barcode: str, sku: str) -> None:
    """One mapping from one PC, as a quick map writes it (gui/setup_pages.py)."""
    pc.update_sku_mapping("M", {barcode: sku})
```

and remove the imports that leaves unused in that file (ruff names them; `MainWindow`, `SimpleNamespace` and `Mock` may still be used by other tests there, so remove only what ruff reports).

- [ ] **Step 2: Run them and see them fail**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_setup_scanner.py`
Expected: FAIL. The first test hangs on an input dialog if run as is: `mapSku` still opens `QInputDialog.getText`. Do not wait for it; go on to Step 3 and run the tests after.

- [ ] **Step 3: Change `gui/main_window.py`**

**(a) Imports.** Add:

```python
from gui.setup_payload import order_choices, quick_payload
```

and remove `QInputDialog` from the `PySide6.QtWidgets` import.

**(b)** Delete the module function `_unmapped_choices` (lines 134 to 149). It moved to `gui/setup_payload.order_choices` in Task 2.

**(c) Signals.** In `_init_ui`, after the other `self.setup_pages.…connect` lines added in Task 6, add:

```python
        self.setup_pages.quickMapped.connect(
            lambda kind, barcode, sku, mapping: self._on_quick_mapped(kind, barcode, sku, mapping)
        )
        self.setup_pages.strayScanned.connect(lambda text: self._on_stray_scan(text))
```

**(d) The flows.** Replace `_save_sku_mapping`, `_on_map_sku_from_packer` and `_on_map_barcode_from_packer` (lines 1967 to 2065, three methods in a row) with:

```python
    def _on_map_sku_from_packer(self, sku: str):
        """Map SKU on an item row: the SKU is known, the packer scans the barcode.

        A quick map (ADR 0004): the SKU mapping page, for this one add.
        """
        if not self.current_client_id:
            self.packer_mode_widget.set_focus_to_scanner()
            return
        client_id = self.current_client_id
        label = self.client_combo.currentText()
        quick = quick_payload("sku", sku=sku)
        self._open_setup(lambda: self.setup_pages.show_mapping(client_id, label, quick))

    def _on_map_barcode_from_packer(self, barcode: str):
        """Map barcode… on a No match row: the barcode is known, the SKU is one
        of this order's lines (owner decision, spec 2026-10-09 section 2)."""
        choices = order_choices(self.logic.current_order_state) if self.logic else []
        if not (choices and self.current_client_id):
            self.packer_mode_widget.set_focus_to_scanner()
            return
        client_id = self.current_client_id
        label = self.client_combo.currentText()
        quick = quick_payload("barcode", barcode=barcode, choices=choices)
        self._open_setup(lambda: self.setup_pages.show_mapping(client_id, label, quick))

    def _on_quick_mapped(self, kind: str, barcode: str, sku: str, mapping: dict):
        """A quick map was saved: back to Packer Mode, and say so there.

        For a barcode the scan that had no match is replayed, which packs the
        item in the same gesture: the scan already happened, and making the
        packer scan again to use a mapping they just made is a step with no
        purpose.
        """
        if self.logic:
            self.logic.set_sku_map(mapping)
            logger.info(f"Quick-mapped barcode '{barcode}' → SKU '{sku}'")

        def after():
            self.packer_mode_widget.show_notification(
                f"Mapped: {barcode} → {sku}", "status_success"
            )
            if kind == "barcode" and self.logic:
                # It matches an item now, so its "No match" row goes with the mapping.
                self.logic.unknown_scans = [
                    scan for scan in self.logic.unknown_scans if scan != barcode
                ]
                self.packer_mode_widget.show_unknown_scans(self.logic.unknown_scans)
                self.on_scanner_input(barcode)

        self._leave_setup(after)

    def _on_stray_scan(self, text: str):
        """A complete scan that reached no field of a setup page (ADR 0004).

        Held while a page opened from Packer Mode is up and replayed by
        _leave_setup once the scanner has the focus. One reported just after
        the return is acted on at once. Anywhere else there is nothing to
        scan into, and it is dropped.
        """
        from_packer = self._setup_return is self.packer_mode_widget
        if self._setup_showing():
            if from_packer:
                self._stray_scans.append(text)
        elif self.stacked_widget.currentWidget() is self.packer_mode_widget and self.logic:
            self.on_scanner_input(text)
```

**(e) A lock lost during a quick map.** In `_on_lock_lost`, replace the `if` that guards `show_takeover` and its body (the block that starts at the comment "Not while it is leaving") with:

```python
        # A quick map is Packer Mode with a page over it (ADR 0004): the page
        # goes, and the packer lands on the panel.
        in_quick_map = self._setup_showing() and self._setup_return is widget
        # Not while it is leaving: the panel would paint on a page about to be
        # covered, and the packer would land on a dead session with no word.
        if (
            self.stacked_widget.currentWidget() is widget or in_quick_map
        ) and not self._leaving_packer_mode:
            # The lock is gone and stays gone: nothing left to renew, and a
            # second report must not land on the panel.
            if hasattr(self, "heartbeat_timer"):
                self.heartbeat_timer.stop()
            self.packer_mode_widget.show_takeover(holder, list_name)
            if in_quick_map:
                self._leave_setup()
            return
```

and add one sentence to that method's docstring: "A quick map counts as Packer Mode."

- [ ] **Step 4: Stop Packer Mode taking the focus back from the page it just opened**

In `gui/packer_mode_widget.py`, `_on_map_sku_requested` and `_on_map_barcode` each emit a signal and then call `self.set_focus_to_scanner()`. The signal now switches the window to the setup page before that line runs. Change both methods so the scanner is refocused only if Packer Mode is still on screen:

```python
    def _on_map_sku_requested(self, sku: str):
        """Emit map_sku_requested with the original SKU string."""
        self.map_sku_requested.emit(sku)
        # MainWindow may have put the SKU mapping page over us (ADR 0004).
        if self.isVisible():
            self.set_focus_to_scanner()
```

```python
    def _on_map_barcode(self, barcode: str):
        """Forward an unmatched scan's barcode; MainWindow owns the page."""
        self.map_barcode_requested.emit(barcode)
        if self.isVisible():
            self.set_focus_to_scanner()
```

- [ ] **Step 5: Run the tests and see them pass**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_setup_scanner.py tests/audit/test_02_concurrency_sweep.py tests/test_packer_scanner_focus.py tests/test_packer_mode_widget.py tests/test_packer_bridge.py`
Expected: PASS. What to check when a scanner test fails:

- **`open_quick` never sees the focus in the field.** The page focuses the field when `page` becomes `"mapping"` (`renderMapping` → `focusQuick`). If the view itself lacks the Qt focus, check `_open_setup`'s `enter()` calls `self.setup_pages.view.setFocus()` after `setCurrentWidget`.
- **Keys reach the page but the mapping is not saved.** Read the page's state with `eval_js(qtbot, view, "document.getElementById('d-barcode').value")`: if the text is there, the Enter did not reach `onKey` as `event.key === "Enter"`.
- **`focusWidget()` is not the scanner field after the return.** The field may be disabled (`PackerModeWidget._sync_scanner`): a finished order holds the scanner off until its screen clears. In `test_map_barcode_saves_a_sku_of_the_order_and_replays_the_scan` the replay completes the order, so if that assertion fails for this reason, assert instead that the field has the focus once it is enabled: `qtbot.waitUntil(lambda: QApplication.focusWidget() is window.packer_mode_widget.scanner_input, timeout=5000)`. That is the same promise (ADR 0004 rule 4), with the finished-order pause allowed for. Do not change the other tests' assertions this way.

- [ ] **Step 6: Confirm nothing of the old flows is left**

Run: `grep -rn "QInputDialog\|_save_sku_mapping\|_unmapped_choices\|Overwrite Mapping" --include=*.py gui packing_tool tests scripts`
Expected: no output.

- [ ] **Step 7: Run the whole suite, lint, commit**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: PASS.
Run: `.venv/bin/ruff check . --exclude shared`
Run: `graphify update .`

Commit `gui/main_window.py`, `gui/packer_mode_widget.py`, `tests/test_setup_scanner.py`, `tests/audit/test_02_concurrency_sweep.py` with the message "Map SKU and Map barcode open a quick map; stray scans are replayed (ADR 0004)".

---

### Task 8: Renders, and the final pass over every frame

**Files:**
- Create: `scripts/render_args.py`, `scripts/render_setup.py`, `scripts/render_all.py`
- Modify: `scripts/render_shell.py`, `scripts/render_packer_mode.py`, `scripts/render_app_pages.py`, `scripts/render_sessions.py`
- Delete: `docs/design/ui-refresh/renders/phase1`, `phase2`, `phase3`, `phase4`
- Create: `docs/design/ui-refresh/renders/final/1366x768/*.png`, `final/1920x1080/*.png`
- Test: `tests/test_render_args.py` (new)

**Interfaces:**
- Produces: `scripts/render_args.parse_args(argv: list[str]) -> tuple[Path, int, int]` (output folder, width, height). Usage of every render script: `.venv/bin/python scripts/render_<x>.py [output dir] [--size WIDTHxHEIGHT]`; the default size is `1366x768` and the default folder is `docs/design/ui-refresh/renders/final/<size>/`.

- [ ] **Step 1: Write the failing test for the shared argument parser**

Create `tests/test_render_args.py`:

```python
"""The render scripts' one shared piece: where to write, and at what size."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from render_args import parse_args  # noqa: E402

FINAL = ROOT / "docs" / "design" / "ui-refresh" / "renders" / "final"


def test_the_default_is_the_floor_size_into_its_own_folder():
    assert parse_args([]) == (FINAL / "1366x768", 1366, 768)


def test_a_size_picks_its_folder():
    assert parse_args(["--size", "1920x1080"]) == (FINAL / "1920x1080", 1920, 1080)


def test_an_explicit_folder_wins(tmp_path):
    assert parse_args([str(tmp_path), "--size", "1920X1080"]) == (tmp_path, 1920, 1080)


@pytest.mark.parametrize("size", ["1366", "axb", "0x768", "1366x"])
def test_a_size_that_is_not_two_positive_numbers_is_refused(size):
    with pytest.raises(SystemExit):
        parse_args(["--size", size])
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_render_args.py`
Expected: FAIL, `No module named 'render_args'`.

- [ ] **Step 2: Write `scripts/render_args.py`**

```python
"""What every render script takes: an output folder and a window size.

    .venv/bin/python scripts/render_<x>.py [output dir] [--size WIDTHxHEIGHT]

The default size is 1366x768 (ADR 0002's design size); 1920x1080 is the
check size. Without a folder, the renders go to
docs/design/ui-refresh/renders/final/<size>/.
"""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FINAL = ROOT / "docs" / "design" / "ui-refresh" / "renders" / "final"


def _size(text: str) -> tuple[int, int]:
    try:
        width, height = (int(part) for part in text.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not WIDTHxHEIGHT") from None
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError(f"{text!r} is not WIDTHxHEIGHT")
    return width, height


def parse_args(argv: list[str]) -> tuple[Path, int, int]:
    parser = argparse.ArgumentParser(description="Render frames offscreen.")
    parser.add_argument("out", nargs="?", type=Path, default=None)
    parser.add_argument("--size", type=_size, default=(1366, 768), metavar="WIDTHxHEIGHT")
    args = parser.parse_args(argv)
    width, height = args.size
    return args.out or FINAL / f"{width}x{height}", width, height
```

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests/test_render_args.py`
Expected: PASS.

- [ ] **Step 3: Give the four existing scripts `--size`**

The same four edits in each of `scripts/render_shell.py`, `render_packer_mode.py`, `render_app_pages.py`, `render_sessions.py`:

1. Add `from render_args import parse_args` after the `sys.path.insert(0, str(ROOT))` line (a script's own folder is already on `sys.path` when it is run).
2. Delete the `DEFAULT_OUT = …` constant.
3. In `main`, replace `out = Path(argv[0]) if argv else DEFAULT_OUT` with `out, width, height = parse_args(argv)`.
4. Make `shoot` use that size for every frame, and remove the per-call sizes:
   - `render_shell.py`: `def shoot(name: str) -> None:` with `window.resize(width, height)`; delete the line `shoot("2b-{theme}-1920", 1920, 1080)`.
   - `render_packer_mode.py`: `def shoot(name: str) -> None:` with `widget.resize(width, height)`; change the first `widget.resize(1366, 768)` to `widget.resize(width, height)`; delete the line `shoot("6b-{theme}-1920", 1920, 1080)`.
   - `render_app_pages.py`: `def shoot(name: str) -> None:` with `window.resize(width, height)`; change `window.resize(1366, 768)` to `window.resize(width, height)`; change `shoot("5a", 1920, 1080)` to `shoot("5a")` and `shoot("5b", 1920, 1080)` to `shoot("5b")`.
   - `render_sessions.py`: change `window.resize(1366, 768)` to `window.resize(width, height)`. Its `shoot` takes no size already.

In each script's module docstring, replace the usage line and the sentence about where and at what size it writes with:

```
    .venv/bin/python scripts/render_<name>.py [output dir] [--size WIDTHxHEIGHT]

Writes <frame>-<theme>.png at the size given (1366x768 by default), by default
into docs/design/ui-refresh/renders/final/<size>/.
```

(with the script's real name in place of `<name>`). `render_packer_mode.py` and `render_shell.py` put the theme into the name with `name.format(theme=theme)`; leave that as it is.

- [ ] **Step 4: Write `scripts/render_setup.py`**

```python
"""Offscreen renders of Worker selection and SKU mapping, in both themes.

    .venv/bin/python scripts/render_setup.py [output dir] [--size WIDTHxHEIGHT]

Writes <frame>-<theme>.png at the size given (1366x768 by default), by default
into docs/design/ui-refresh/renders/final/<size>/. The frames are the presets
of docs/design/ui-refresh/mockups/Worker Selection.html (w-*) and
SKU Mapping.html (m-*).

It drives a SetupPages alone: no MainWindow and no server. The bridge is given
payloads built by the pure functions in gui/setup_payload.py at a fixed "now",
so every run draws the same thing, and its own QSettings, so it touches
neither the file server nor this PC's saved theme.
"""

import json
import os
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication
from render_args import parse_args

NOW = datetime(2026, 10, 7, 14, 6, tzinfo=timezone(timedelta(hours=3)))
WORKERS_PATH = r"\\fs01\fulfilment\Workers"
CONFIG_PATH = r"\\fs01\fulfilment\Clients\CLIENT_ACME\packer_config.json"
SKUS = [
    "CRM-50ML", "CRM-15ML", "SER-30ML", "CLN-200", "TNR-150", "MSK-5PK", "SPF-50", "LIP-RED",
    "OIL-100", "GFT-BOX", "EYE-15ML", "BLM-10G", "SCR-100", "MST-100", "HND-75ML", "BDY-250",
    "SHP-300", "CND-300", "HRM-50ML", "GEL-150",
]
SIXTY = {
    (f"5901234500{n:03d}" if n < 40 else f"4006381333{n - 40:03d}"): SKUS[n % 20]
    for n in range(60)
}
CHOICES = [
    {"sku": "SER-30ML", "label": "SER-30ML — 0 / 1 packed", "key": "ser30ml"},
    {"sku": "CRM-50ML", "label": "CRM-50ML — 2 / 3 packed", "key": "crm50ml"},
    {"sku": "LIP-RED", "label": "LIP-RED — 2 / 2 packed", "key": "lipred"},
]


def worker(worker_id, name, sessions, orders, **ago):
    return SimpleNamespace(
        id=worker_id, name=name, total_sessions=sessions, total_orders=orders,
        last_active=(NOW - timedelta(**ago)).isoformat() if ago else None,
        created_at=(NOW - timedelta(minutes=1)).isoformat(),
    )


SIX = [
    worker("w1", "Ivan", 31, 2870, hours=6, minutes=26),
    worker("w2", "Maria", 14, 1204, days=1),
    worker("w3", "Georgi", 22, 1951, days=2),
    worker("w4", "Petya", 9, 688, days=8),
    worker("w5", "Elena", 3, 140, days=25),
    worker("w6", "Dimitar", 1, 37, days=40),
]


def main(argv: list[str]) -> int:
    out, width, height = parse_args(argv)
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as raw:
        # Before any QSettings is made: keep this PC's saved theme. Both
        # formats, as tests/conftest.py does.
        for fmt in (QSettings.NativeFormat, QSettings.IniFormat):
            QSettings.setPath(fmt, QSettings.UserScope, str(Path(raw) / "settings"))

        app = QApplication.instance() or QApplication(sys.argv[:1])
        from gui.setup_pages import SetupPages
        from gui.setup_payload import (
            MappingEditor,
            mapping_error,
            mapping_payload,
            quick_payload,
            workers_payload,
        )
        from gui.theme import apply_theme, load_saved_theme

        load_saved_theme(app)
        # No managers: the payloads below never go through the server.
        pages = SetupPages(None, None, now=lambda: NOW)
        pages.resize(width, height)
        pages.show()
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

        def js(code: str) -> None:
            done = []
            pages.view.page().runJavaScript(
                f"(function () {{ {code}; return true; }})()", 0, done.append
            )
            deadline = time.monotonic() + 10
            while not done:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"never returned from the page: {code}")
                app.processEvents()
                time.sleep(0.01)
            if done[0] is not True:
                raise RuntimeError(f"failed in the page: {code}")

        def typed(element_id: str, text: str) -> None:
            js(
                f"const n = document.getElementById('{element_id}'); n.focus();"
                f" n.value = {json.dumps(text)};"
                " n.dispatchEvent(new Event('input', {bubbles: true}))"
            )

        def shoot(name: str) -> None:
            for theme in ("light", "dark"):
                apply_theme(app, theme)
                pages.resize(width, height)
                settle()
                target = out / f"{name}-{theme}.png"
                if not pages.grab().save(str(target)):
                    raise OSError(f"could not write {target}")
                print(target)

        def workers(people, **kwargs) -> None:
            kwargs.setdefault("startup", True)
            bridge.set_page("")
            bridge.set_workers(workers_payload(people, now=NOW, **kwargs))
            bridge.set_page("workers")
            settle()

        def mapping(editor=None, **kwargs) -> None:
            kwargs.setdefault("client", "ACME")
            bridge.set_page("")
            bridge.set_mapping(
                mapping_payload(editor if editor is not None else MappingEditor(SIXTY), **kwargs)
            )
            bridge.set_page("mapping")
            settle()

        def unsaved() -> MappingEditor:
            """The mockup's dirty list: two added, one edited, one deleted."""
            editor = MappingEditor(SIXTY)
            editor.add("5906000123456", "CRM-50ML")
            editor.add("5906000123463", "SER-30ML")
            editor.update(editor.rows[9]["id"], editor.rows[9]["barcode"], "LIP-NUDE")
            editor.delete(editor.rows[23]["id"])
            return editor

        settle()

        # --- Worker selection ---------------------------------------------
        workers(SIX)
        shoot("w-six")
        workers(SIX, startup=False, current_id="w1", current_name="Ivan")
        shoot("w-six-switch")
        workers(SIX, picked_id="w2")
        shoot("w-opening")
        workers(SIX[1:2])
        shoot("w-one")
        workers([])
        shoot("w-none")
        workers(SIX)
        js("document.getElementById('w-new').click()")
        shoot("w-creating")
        bridge.answer = lambda name, *args: (
            "There’s already a worker called Maria. Pick that card, or add a surname."
        )
        typed("w-name", "maria")
        js("document.getElementById('w-create').click()")
        shoot("w-duplicate")
        workers([], failure={"cause": "the network path was not found", "path": WORKERS_PATH})
        shoot("w-failed")

        # --- SKU mapping ----------------------------------------------------
        mapping()
        shoot("m-60")
        mapping(MappingEditor())
        shoot("m-none")
        added = MappingEditor(SIXTY)
        added.add("5906000123456", "CRM-50ML")
        mapping(added)
        js("document.getElementById('m-add').click()")
        shoot("m-adding")
        mapping()
        js("document.getElementById('m-add').click()")
        typed("d-barcode", "5901234500003")
        typed("d-sku", "CLN-250")
        shoot("m-already-mapped")
        mapping(quick=quick_payload("barcode", barcode="5906000123456", choices=CHOICES))
        shoot("m-from-packer")
        mapping(quick=quick_payload("sku", sku="SER-30ML"))
        shoot("m-from-packer-sku")
        mapping()
        js("document.querySelector('[data-row-action=\"delete\"][data-id=\"5\"]').click()")
        shoot("m-delete")
        mapping(unsaved())
        js("document.getElementById('m-reload').click()")
        shoot("m-reload-unsaved")
        failed = unsaved()
        mapping(failed, error=mapping_error(
            "save",
            "Could not save the SKU mapping to the file server: the network path was not found",
            CONFIG_PATH,
            sum(failed.counts().values()),
        ))
        shoot("m-save-failed")
        mapping(saved=True)
        shoot("m-saved")

        pages.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 5: Write `scripts/render_all.py`**

```python
"""Every frame of the UI refresh, at both sizes, in both themes.

    .venv/bin/python scripts/render_all.py

Runs the five render scripts at 1366x768 and at 1920x1080 into
docs/design/ui-refresh/renders/final/<size>/. Each script is its own process:
each builds its own QApplication and redirects its own QSettings.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = (
    "render_shell.py",        # 2a-2e
    "render_app_pages.py",    # 3a-3g, 4a-4c, 5a, 5b
    "render_packer_mode.py",  # 6a-6j
    "render_sessions.py",     # 7a-7h, 8a-8f
    "render_setup.py",        # w-*, m-*
)
SIZES = ("1366x768", "1920x1080")


def main() -> int:
    for size in SIZES:
        for script in SCRIPTS:
            print(f"--- {script} at {size}", flush=True)
            subprocess.run([sys.executable, str(HERE / script), "--size", size], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Replace the old renders and render everything**

Run: `/usr/bin/git rm -r -q docs/design/ui-refresh/renders/phase1`
Run: `/usr/bin/git rm -r -q docs/design/ui-refresh/renders/phase2`
Run: `/usr/bin/git rm -r -q docs/design/ui-refresh/renders/phase3`
Run: `/usr/bin/git rm -r -q docs/design/ui-refresh/renders/phase4`
Run: `.venv/bin/python scripts/render_all.py`
Expected: it prints one path per PNG and exits 0. Each size's folder then holds, in light and dark: `2a` to `2e`; `3a` to `3g`, `4a` to `4c`, `5a`, `5b`; `6a` to `6j` and `6h-…-unsaved`; `7a` to `7h`, `8a` to `8f`; the eight `w-*` and ten `m-*` frames.

If a script fails at 1920x1080 only, it had a 1366 assumption somewhere in its body (a scroll position, a fixed click point): read the traceback and make that line use `width` and `height`.

- [ ] **Step 7: Look at every frame, and fix what does not match**

Open every PNG of `final/1366x768/` with the Read tool beside its mockup frame, then every PNG of `final/1920x1080/`. For frames `2a` to `8f` the mockup is the frame of that id in `Packer Screens.html` (unpack `Packer App.html` and `Packer Mode.html` as the mockups README describes); for `w-*` and `m-*` it is the matching preset of `Worker Selection.html` and `SKU Mapping.html`.

For each frame, check in this order: nothing is clipped, overlapped or cut by the window edge; nothing that should scroll pushes the layout wider than the window; both themes are legible (no text on a plane of its own colour); the frame's states and copy are the mockup's. At 1920×1080 also check that content which is centred or capped in the mockup (the SKU mapping card at 920px, the worker grid at four columns) stays so, and that tables use the extra width without stretching a fixed column.

A mismatch is one of three things:

1. **A bug in a page or a script.** Fix it, with a test where the behaviour can be asserted (a row count, a hidden element, a text), re-run that script, look again.
2. **A departure already listed** in the spec of the phase that built the screen (phase 1 section 9, phase 2 section 9, phase 3 section 11, phase 4 section 12, phase 5 section 11). Leave it.
3. **A new departure** that cannot or should not be fixed. Add a row to section 11 of this phase's spec saying what and why.

Keep a list of what you fixed in this step and of any row added under 3: the PR body needs both.

- [ ] **Step 8: Run the suite, lint, commit**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Run: `.venv/bin/ruff check . --exclude shared`
Run: `graphify update .`

Commit the scripts, `tests/test_render_args.py`, the deleted `phase1` to `phase4` folders, `docs/design/ui-refresh/renders/final/` and any fixes with the message "Final renders of every frame at 1366x768 and 1920x1080, both themes".

---

### Task 9: Cleanup audit and documents

**Files:**
- Modify: `CONTEXT.md`, `README.md`, `docs/adr/0003-the-shells-pages-are-one-web-document.md`, `docs/design/ui-refresh/README.md` if it exists (it does not at the time of writing; `docs/design/ui-refresh/mockups/README.md` does and is not changed)
- Create: `docs/design/ui-refresh/for-shared.md`
- Modify: whatever the audit of Step 1 finds in `gui/`

**Interfaces:** none.

- [ ] **Step 1: Audit `gui/` for what no screen uses any more**

Write this throwaway script outside the repo and run it with `.venv/bin/python -I <script> "$PWD"` from the worktree root. It lists every name defined in `gui/`, `packing_tool/`, `main.py` or `run_dev.py` that is referenced nowhere outside `tests/`:

```python
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
files = [p for d in ("gui", "packing_tool", "scripts", "tests") for p in (root / d).rglob("*.py")]
files += [root / "main.py", root / "run_dev.py"]
files += list((root / "gui" / "web").glob("*"))
text = {p: p.read_text(encoding="utf-8") for p in files if p.is_file()}
for path in sorted(text):
    if path.suffix != ".py" or "tests" in path.parts or "scripts" in path.parts:
        continue
    for match in re.finditer(r"^\s*(?:def|class) (\w+)|^(\w+) = ", text[path], re.M):
        name = match.group(1) or match.group(2)
        if name.startswith("__") or name == "logger":
            continue
        uses = sum(
            len(re.findall(rf"\b{re.escape(name)}\b", body))
            for other, body in text.items()
            if "tests" not in other.parts
        )
        if uses <= 1:
            print(f"{path.relative_to(root)}: {name}")
```

Read the output this way:

- **Slots and Qt overrides are false alarms**: a camelCase method on `AppBridge`, `PackerBridge` or `SetupBridge` (the page calls it by name over the channel), and `closeEvent`, `showEvent`, `mousePressEvent`, `resizeEvent`. Leave them.
- **Names under `packing_tool/`, `run_dev.py`** are out of scope (spec section 13). Leave them.
- **Anything else under `gui/`** is dead: delete it, and its tests if a test was its only user.

Then look for QSS that styles nothing:

Run: `grep -rn "setObjectName(" gui`
Run: `grep -rnE "#[A-Za-z]+ ?[{,:]|QWidget#|QLabel#|QPushButton#|QToolButton#|QFrame#|QLineEdit#" gui --include=*.py`

Every object name in a stylesheet selector (second command) must be set on a widget (first command). Delete a selector whose name no widget carries. When this plan was written, both checks found nothing beyond what Tasks 6 and 7 delete; if yours find nothing either, that is the expected result, and this step changes no file.

Delete the throwaway script. Run the suite and ruff if you deleted anything.

- [ ] **Step 2: Update `CONTEXT.md`**

Add these four entries after the **App bridge** entry:

```markdown
**Setup document** — the web page that draws the two full-window pages: Worker selection and SKU mapping. One page in its own web view, the third thing the window can show beside the shell and Packer Mode. While it is up the sidebar and the command bar are hidden, and its own buttons are the only ways out.

**Setup bridge** — the one `QWebChannel` object the setup document talks to. It says which of the two pages shows and each page's data. Four of its slots answer: they return an empty string when the thing was done, else the sentence to show beside the field.

**Quick map** — SKU mapping opened from Packer Mode (*Map SKU* on an item, *Map barcode…* on an unmatched scan) for one add. The known side is filled and fixed, the add is written to the file server at once, and the page returns to Packer Mode. Nothing else on the page can change a mapping (ADR 0004).

**Stray scan** — a complete scan (text ended by Enter) that reaches no field while a setup page is up: the moment a quick map is switching in or out. It is held and replayed into Packer Mode once the scanner field has the focus again (ADR 0004). Not an **unmatched scan**, which reached Packer Mode and matched nothing.
```

Then make these edits to existing entries:

- **Scanner capture**: append "A quick map is the one time the scanner types somewhere else, and ADR 0004 says how that is kept safe."
- **Sidebar**: change "a footer with SKU mapping, the worker, Light/Dark and the connection card" to "a footer with SKU mapping and *Switch worker…* (each opens a page of the setup document), Light/Dark and the connection card".
- **Toast**: read the entry against the code. If it still says Packer Mode raises a Qt toast for a saved SKU mapping, remove that clause: a quick map reports in the feedback band, and a Save on the mapping page in the page's footer.
- **Unmatched scan**: append "Its row offers *Map barcode…*, which opens a quick map."

- [ ] **Step 3: Update `README.md`**

In **Download**, replace "Point it at the file server once in **Settings → Server Connection**" with "Point it at the file server once in the **⋯** menu → **Server connection…**".

In **Layout**, replace the `gui/` line with:

```markdown
- `gui/`: the Qt shell (sidebar, command bar, scanner field) and the bridges; `gui/web/` holds the three web documents every screen is drawn in: the app document (Packing, Statistics, Sessions, Session details), the order document (Packer Mode) and the setup document (Worker selection, SKU mapping)
```

and add a line after the `docs/adr/` one:

```markdown
- `docs/design/ui-refresh/`: the approved mockups, the final renders of every screen, and `for-shared.md`, what is waiting to move into `shared/`
```

- [ ] **Step 4: Point ADR 0003 at where the two pages went**

In `docs/adr/0003-the-shells-pages-are-one-web-document.md`, replace the last consequence:

```markdown
- SKU mapping and Worker selection are dialogs, not pages of the shell. Phase 5 decides where they live.
```

with:

```markdown
- SKU mapping and Worker selection are not pages of the shell. Since phase 5 they are the two pages of a
  second document, the setup document, in a view of its own that replaces the whole shell while it shows
  (spec `docs/superpowers/specs/2026-10-09-ui-refresh-phase5-setup-pages-design.md`, section 4.1; ADR 0004).
```

- [ ] **Step 5: Collect the "For shared/" items**

Create `docs/design/ui-refresh/for-shared.md`. First read the "For shared/" section of each phase's spec (`docs/superpowers/specs/2026-10-08-ui-refresh-phase1-shell-design.md` section 8, `…phase2-packer-mode-design.md` section 8, `…phase3-packing-statistics-design.md` section 12, `…phase4-sessions-design.md` section 13, `2026-10-09-ui-refresh-phase5-setup-pages-design.md` section 10) and check every item below against them; add any the list misses and drop none.

```markdown
# For shared/: what the UI refresh left app-side

`shared/` is a pinned mirror of shopify-fulfillment-tool's (its ADR 0017) and is never edited here. Each
item below was built in this repo during the five phases of the UI refresh because `shared/` lacked it.
This list is the brief for one follow-up on Fulfilment's side: move the item into `shared/` there, sync
here with `python scripts/sync_shared.py`, and delete the stand-in named in the last column.

## `shared/navrail.py`

| Item | Phase | Stand-in to delete here |
|---|---|---|
| An item-height parameter (floor density needs 44px), the icon-to-label gap, and no plane on a disabled checked item | 1 | `FloorNavRail` in `gui/components/sidebar.py`, which overrides `_shape` and `_apply_theme`; `Sidebar` reading `rail._buttons` and `rail.layout()` |

## `shared/theme.py`

| Item | Phase | Stand-in to delete here |
|---|---|---|
| `build_stylesheet`: size `QPushButton`, `QComboBox` and `QLineEdit` from the density profile's `control_content_height` | 1 | the 44px the command bar sets on its own controls (`gui/command_bar.py`) |
| `build_stylesheet`: the dashed disabled treatment for `QLineEdit` and `QComboBox` | 1 | none: the fields are plain until it lands |
| `status_warning_dot`, if the amber is wanted and a contrast floor for it is agreed | 1, 2 | the warning flash uses `status_warning` |
| `band_fg`: text on a solid status fill | 2 | the feedback band uses `on_accent` |
| A type rung between 17pt and 28pt | 2 | Packer Mode's 20, 24, 26 and 30pt (`--pm-*` sizes in `gui/web/packer.css`) |

## `shared/icons.py`

| Item | Phase | Stand-in to delete here |
|---|---|---|
| `package-check`, `scan-barcode`, `triangle-alert`, `search` | 1, 2 | the inline glyphs the pages draw |

## `shared/components/`

| Item | Phase | Stand-in to delete here |
|---|---|---|
| `Toast`: the mockup's inverse variant and a bottom-centre placement | 1 | none: the Qt toast keeps its corner |
| `toast.py` cannot be seen over a web view | 3 | `MainWindow._toast`, which asks the app document to draw it instead |
| `card.py` has a comment naming `OverviewTab` and `MetricsTab`, which phase 4 deleted | 4 | none: a comment |
| An initials helper: both apps draw a worker's initials | 5 | `initials` in `gui/setup_payload.py` |

## `shared/web/kit.css`

| Item | Phase | Stand-in to delete here |
|---|---|---|
| Floor density as a kit profile: everything in `gui/web/floor.css` (buttons, badges, banner, toast, state card, strip, track, table rows, segmented control, input, menu) | 2, 3, 4 | `gui/web/floor.css` |
| `.scrim` and `.dialog` as kit components | 2 | their rules in `gui/web/floor.css` |
| A badge with a leading dot (`.badge > .dot`, solid or hollow) | 4 | its rules in `gui/web/floor.css` |
| `.field.invalid`: a danger edge on a bare input (the kit has it for `.input` only) | 5 | its rule in `gui/web/setup.css` |

## `shared/web/page.js`

| Item | Phase | Stand-in to delete here |
|---|---|---|
| A toast script: every page of both apps draws the same toast from `toastRaised` | 3 | the toast section of `gui/web/app.js` |
| The stray-key listener: keys that reach no field, handed over as one scan on Enter (ADR 0004) | 5 | the last branch of `onKey` in `gui/web/setup.js` |
```

- [ ] **Step 6: Run everything one last time, lint, commit**

Run: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q`
Expected: PASS, with no test skipped that was not skipped on `origin/main`.
Run: `.venv/bin/ruff check . --exclude shared`
Run: `graphify update .`
Run: `grep -rn "sku_mapping_dialog\|worker_selection_dialog\|QInputDialog" --include=*.py --include=*.md gui packing_tool tests scripts README.md CONTEXT.md`
Expected: no output.

Commit `CONTEXT.md`, `README.md`, `docs/adr/0003-the-shells-pages-are-one-web-document.md`, `docs/design/ui-refresh/for-shared.md` and anything the audit removed with the message "Phase 5 documents: glossary, README, the For shared/ list".

---

## What the PR must say

The stage that opens the PR writes its body from these, in this order:

1. **What changed**, in three lines: the two pages, the quick map, the cleanup.
2. **Mockups followed**: `Worker Selection.html` and `SKU Mapping.html`, and that neither is in `Packer Screens.html`.
3. **Departures**: the table of spec section 11, including any row Task 8 added, and the list of what Task 8 fixed in other phases' screens.
4. **Renders**: the `w-*` and `m-*` PNGs from `docs/design/ui-refresh/renders/final/1366x768/` embedded, light beside dark; a link to the folder for the rest.
5. **For shared/**: the contents of `docs/design/ui-refresh/for-shared.md`.
6. **The owner's step before a release** (this cannot be done on Linux offscreen): on the frozen Windows build over RDP, with a real scanner,
   - *Map SKU* on an item row, then scan the product: the mapping is saved, Packer Mode returns, and the next scan is taken by the scanner field;
   - *Map barcode…* on a No match row, then scan anything: nothing is saved and the page says "Not on this order"; then pick a line: the item is packed;
   - scan at the moment of clicking *Map SKU* and at the moment the page closes: the scan either lands in the barcode field or is acted on in Packer Mode, and is never lost without a trace;
   - Worker selection at startup, with a new worker created, and once with the server folder unreachable;
   - SKU mapping from the sidebar: add by scanning a barcode into the draft row, Save, and check the mapping on a second PC.
7. Label the PR `windows-build`, so CI attaches the frozen build.

## Self-review notes (for the implementer)

- Spec section → task: 4.1 to 4.3 → Tasks 1 to 4; 4.4 → Tasks 6 and 7; 4.5 and 4.6 → Task 5; 5 → Tasks 1, 4, 5; 6 → Tasks 2, 4, 5; 7 → Tasks 4, 5, 7; 8 → every task's tests; 9 → Task 8; 10 → Task 9; 12 → Tasks 6, 7, 8, 9.
- The five proofs of spec section 7.5 are, in order: `test_map_sku_takes_the_scanned_barcode_and_gives_the_scanner_back` (1 and 4), `test_a_scan_into_the_sku_field_saves_nothing` (2), `test_a_scan_with_no_field_is_held_and_replayed_after_the_return` (3), `test_back_to_packing_saves_nothing_and_gives_the_scanner_back` (5).
