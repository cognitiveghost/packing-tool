# Minor fixes after 2.0.0 — design

Todoist task "minor fixes 2.0.0" (dev-runner run 15, branch `dr/8-minor-fixes-2-0-0`).
Classified **bounded**: every item changes a flow that already exists. No UI mockup applies: nothing moves on
screen; only a value and two flag labels change.

## 1. Session detail: "Packing list" is always "Unknown"

**Cause.** `OverviewTab._build_session_card` (`gui/session_browser/overview_tab.py:49`) shows only
`Path(record["packing_list_path"]).stem`. The record is built in `SessionDetailPage._load_session_details` from
`session_summary.json`, which `PackerLogic.generate_session_summary` writes with `packing_list_name` and **no**
`packing_list_path`. So every session that has a summary renders "Unknown". In the `session_info` branch
the path is gone as well: the Shopify flow never writes a per-list `session_info.json`.

**Fix (read side, so old sessions display correctly too).**
- `OverviewTab`: show `record["packing_list_name"]`, else the stem of `record["packing_list_path"]`, else "Unknown".
- `SessionDetailPage._load_session_details`: in both record branches (summary, session_info), fill
  `packing_list_name` from the file, falling back to the name the Session Browser passed in
  (`self.session_data["packing_list_name"]`, the registry entry's name).

## 2. Manual confirms show as "scan" in the Orders tab

**Cause.** Packer Mode records two manual `confirmation_method` values on an item record:
- `"manual"` — the row's **Confirm** button (`main_window.py:465` → `process_sku_scan(sku, "manual")`), one unit per click;
- `"force_confirmed"` — **Force** (`PackerLogic.force_confirm_item`), fills the rest of the line in one record.

`OrdersTab` (`gui/session_browser/orders_tab.py`) recognises only `"force_confirmed"`, so every Confirm click reads
"✓ scan". `compute_order_timing_metrics` (`packing_tool/packer_logic.py:127`) has the opposite gap:
`total_manual_confirms` counts only `"manual"`.

**Fix (owner's choice: distinct labels).**
- Item row, Flags column: `"scanned"` (or missing) → `✓ scan`; `"manual"` → `manual`; `"force_confirmed"` → `forced`.
  The `→ ` SKU prefix is for scans only, as it is today for force. Both manual labels keep today's orange (200, 120, 0).
- Order row flags summary: `manual` if any item is `"manual"`, `forced` if any item is `"force_confirmed"`, in that
  order, before the existing ⟲ / + / ? parts. The order-row flag colour check also matches `forced`.
- `total_manual_confirms` counts the quantity of items whose method is `"manual"` **or** `"force_confirmed"`.
  (Nothing in the GUI shows this metric today; it lands in `session_summary.json`.)

The written values stay as they are. Changing them would split old and new session files.

## 3. Question: does the browser show several packing lists from one Shopify session?

**Yes, by design.** Registry entries are keyed `"{session_id}::{packing_list_name}"`
(`SessionRegistryManager._session_key`), locks are per work dir (`<session>/packing/<list>/.session.lock`), so each
list is its own row with its own status and detail page. Nothing pins it, so this task adds a regression test through
the public registry API: two lists started in one session give two entries, and completing one leaves the other live.

## 4. Dependency update, and moving to Python 3.14

**What the update changed.** Dependabot #191 moved the GitHub Actions to new majors (checkout 7, setup-python 7,
upload-artifact 7, download-artifact 8, attest-build-provenance 4); #192 moved ruff to `~=0.16.9`. Runtime libraries
did **not** change: the 1.3.10.2 and 2.0.0 release builds installed the same PySide6 6.11.2, pandas 3.0.6,
numpy 2.4.6, openpyxl 3.1.5, pyinstaller 6.22.3. CI and the 2.0.0 release both passed; warnings dropped from 19 to 1.

**Python 3.14 (owner request, to match shopify-fulfillment-tool #350).** Evidence it works without code changes:
the dev VM runs 3.14.4 and the full suite passes there (805 passed, 1 expected warning). shopify-fulfillment-tool's
Windows release build passed on 3.14 today with the same PySide6/pandas/pyinstaller stack (run 36535912389). 3.11 is
also ageing out: numpy 2.5 already dropped it.

What 3.14 lets the code shed (ruff with `target-version = "py314"`, 19 findings):
- 14 × UP017 `timezone.utc` → `datetime.UTC` (autofix);
- 4 × UP037 quoted annotations, unnecessary under 3.14's deferred annotations (autofix);
- 1 × FURB162 in `shared/metadata_utils.parse_timestamp`: the `except` branch re-tries `fromisoformat` with `Z`
  rewritten, which `fromisoformat` has handled natively since 3.11. The whole fallback is dead. It collapses to
  "log and return None" (manual edit).

Three of those files are in `shared/` (`metadata_utils.py`, `theme.py`, `components/toast.py`). This repo is the
canonical copy; the owner runs `python scripts/sync_shared.py` from shopify-fulfillment-tool after merge. That sync is
out of this task's scope.

**Changes.**
- `.github/workflows/build-release.yml`: `python-version: '3.14'` in all three jobs (verify, version, build).
- `README.md`: "Python 3.14 on the dev machine; CI and release builds use 3.11." → "Python 3.14 on the dev machine, in CI and in release builds."
- `ruff.toml`: `target-version = "py314"` at top level, then apply the 19 fixes.
- Pin with `~=` on today's release versions (owner's choice), so patch releases flow and Dependabot raises every
  minor/major as a CI-tested PR:
  `PySide6~=6.11.2`, `pandas~=3.0.6`, `openpyxl~=3.1.5`; dev (where pyinstaller already lived):
  `pyinstaller~=6.22.3`, `pytest~=9.1.1`, `pytest-qt~=4.5.0`, `ruff~=0.16.9` (unchanged). The PySide6 metapackage comment block stays.
- `tests/test_excepthook.py::test_a_thread_crash_is_logged_too`: filter the `PytestUnhandledThreadExceptionWarning`
  it provokes on purpose (the crash hook chains to pytest's own hook, which warns). That leaves 0 warnings.
- The PR gets the `windows-build` label so the Windows exe is built on 3.14 before merge.

**Not changing.** `ubuntu-latest` moves to Ubuntu 26 on 2026-10-19; CI will show if that breaks and the fix is one
line. PyInstaller's `Hidden import "jinja2" not found` warning is pandas' optional Styler hook and harmless.
`build_from_scan` looks for the lock at session level, not per work dir. It runs once per client, as a
migration, and nothing in this task touches it.

## Testing

- Overview: a detail page built from the Session Browser's own payload shows the summary's `packing_list_name`, and
  falls back to the registry entry's name when the summary has none.
- Orders tab: one order with a scanned, a manual and a forced item shows `✓ scan` / `manual` / `forced` on the item
  rows and `manual  forced` in the order's flags.
- Metric: `total_manual_confirms` sums quantities of both manual methods and ignores scans.
- Registry: two lists in one session → two entries; completing one leaves the other `in_progress`.
- `parse_timestamp`: an unparseable string still returns `None` after the fallback is removed.
- Gate: `ruff check .` clean, full suite passes with 0 warnings, CI green on 3.14, `windows-build` job green.
