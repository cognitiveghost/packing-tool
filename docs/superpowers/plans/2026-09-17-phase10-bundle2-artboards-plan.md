# Phase 10 Bundle 2 — Artboards Implementation Plan

> **For agentic workers:** execute task-by-task in this session (the runner
> forbids subagents at Stage B). Steps use checkbox (`- [ ]`) syntax.

**Goal:** Static HTML artboards of Packer Mode, Packing table view, Session
Browser and Statistics under `docs/design/phase10/`, plus a handoff sheet and a
private Artifact preview link.

**Architecture:** One HTML file per screen, each holding several fixed-size
frames. Colour and type come only from generated `tokens.css` (CSS custom
properties from `shared.theme.theme_css_vars`). Web-tier styling for Packer
Mode's order document lives in `packer-document.css` so Bundles 4–5 can lift
it; everything else uses `artboard.css`.

**Tech Stack:** HTML + CSS only (no JS), Python for token generation,
`shared.style_lint` as the check.

**Spec:** `docs/superpowers/specs/2026-09-17-phase10-bundle2-artboards-design.md`
— read it in full first. It holds the frame inventory, layout, copy rules and
the owner's decisions. This plan does not repeat them.

## Global Constraints

- Worktree: `packing-tool/.claude/worktrees/phase10-bundle2`, branch
  `worktree-phase10-bundle2`. Work and commit only there. Never commit to `main`.
- Python: `.venv/bin/python` (symlink to the main checkout's venv).
- No app code. No edits under `shared/`, `gui/`, `packing_tool/`, `tests/`.
- No hex, `box-shadow`, gradients, `transition`, `transform`, or px font sizes
  anywhere except `tokens.css`. One mono face: `var(--font-family-mono)`.
  Font sizes come from `var(--type-<role>-size)` (pt).
- Floor density: command bar 60px, rail item 56×64, status bar 40px, rows
  40px, controls 44px, body 12pt, client selector 240px.
- Frames are client area: `1366×768` and `1920×1080`, fixed `width`/`height`
  in px, `overflow: hidden` — if content does not fit, the design is wrong,
  not the frame.
- Files must open straight from disk: no JS, no CDN, no web fonts beyond the
  system stack in the tokens.
- Copy: active voice; action names fixed as "Skip order", "Exit packing",
  "Map SKU", "Force confirm", "Confirm", "Undo", "Keep", "Remove". Plausible
  sample data, never lorem ipsum.
- The lint check, run after every task, must print nothing:
  `.venv/bin/python -m shared.style_lint docs/design/phase10/*.html docs/design/phase10/artboard.css docs/design/phase10/packer-document.css`

## Seams to verify at

There is no pytest here. The two checks are:
1. **Lint** (command above) — proves the web-tier rules hold, so Bundle 4 can
   lift `packer-document.css`.
2. **Render** — open each HTML file in Chrome through the
   `chrome-devtools` MCP (`new_page` with a `file://` URL, then
   `take_screenshot` with `fullPage: true`), look at every frame. Fail if any
   frame clips text, overflows, or shows an unstyled element. Read the
   screenshot; do not skip it.

---

### Task 1: References, tokens, canvas scaffold

**Files:**
- Create: `docs/design/phase10/tokens.css`
- Create: `docs/design/phase10/artboard.css`
- Create: `docs/design/phase10/index.html`

**Produces:** the `[data-theme="dark"|"light"]` scopes, frame classes
`.frame`, `.frame--1366`, `.frame--1920`, and the Qt-tier classes used by
every later task: `.shell` (grid: rail | page, bar on top, status bar
bottom), `.rail`, `.rail-item`, `.rail-item--current`, `.cmdbar`,
`.statusbar`, `.btn`, `.btn--primary`, `.btn--danger`, `.field`,
`.chip` (+ `.chip--success|warning|danger|info|neutral`,
`.chip--hollow` for system marks per F5), `.card`, `.state-panel`,
`.tier-label`.

- [ ] **Step 1: Read the artbook references to text.** For each of
  `F0 Foundation Specimen Sheet.dc.html`, `S Shell and Placement.dc.html`,
  `D Supporting Destinations.dc.html`, `W Setup and Results.dc.html`, call
  `DesignSync` `get_file` with projectId
  `75385f2c-4be2-446c-8e9d-bf90ee063ff7`. The result is too large for context
  and is saved to a file; strip it to text in `$CLAUDE_JOB_DIR/tmp` and read
  the text, not the raw HTML:

```bash
python3 - "$SAVED_RESULT_PATH" "$CLAUDE_JOB_DIR/tmp/F0.txt" <<'EOF'
import json, re, html, sys
c = json.load(open(sys.argv[1]))["content"]
t = re.sub(r"<style.*?</style>", "", c, flags=re.S)
t = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)))
open(sys.argv[2], "w").write(t)
EOF
```

  Extract: F5 status mark rules, the rail/command bar/status bar anatomy, the
  D1/D2 session browser layout, the W results document structure (row,
  chip, drawer). Also skim Shopify's lifted web tier for conventions:
  `../../../../shopify-fulfillment-tool/gui/web/results.css` (read-only).

- [ ] **Step 2: Generate `tokens.css`.**

```bash
.venv/bin/python - <<'EOF'
from shared.theme import theme_css_vars, DARK_THEME, LIGHT_THEME, set_density
set_density("floor")
out = ["/* GENERATED from shared.theme.theme_css_vars(), floor density.",
       "   Regenerate with the snippet in docs/superpowers/plans/",
       "   2026-09-17-phase10-bundle2-artboards-plan.md, Task 1 Step 2. */"]
for name, theme in (("light", LIGHT_THEME), ("dark", DARK_THEME)):
    out.append(theme_css_vars(theme).replace(":root", f'[data-theme="{name}"]', 1))
open("docs/design/phase10/tokens.css", "w").write("\n".join(out) + "\n")
EOF
grep -c "data-theme" docs/design/phase10/tokens.css   # expect 2
```

  Then list the variable names (`grep -o -- '--[a-z0-9-]*' tokens.css | sort -u`)
  and use only those names from here on.

- [ ] **Step 3: Write `artboard.css`.** Canvas background and frame captions
  use tokens (e.g. `--surface-sunken`). Implement every class in
  **Produces** at floor density. `.tier-label` sits outside the frame edge,
  mono, caption size.

- [ ] **Step 4: Write `index.html`.** `<title>Packing Tool artboards</title>`,
  links `tokens.css` then `artboard.css`, a heading, and a table listing all
  25 frames from the spec (frame id, state, file link with `#frame-id`
  anchor). Include one sample frame (empty `.shell` at 1366, dark) to prove
  the scaffold renders.

- [ ] **Step 5: Lint + render.** Run the lint command (must print nothing).
  Render `index.html`; the sample shell shows rail, 60px bar, 40px status bar.

- [ ] **Step 6: Remove the sample frame from `index.html`, commit.**

```bash
git add docs/design/phase10
git commit -m "Phase 10 Bundle 2: artboard tokens and canvas scaffold"
```

---

### Task 2: Packer Mode — the order document and its key states

**Files:**
- Create: `docs/design/phase10/packer-document.css`
- Create: `docs/design/phase10/packer-mode.html`

**Consumes:** Task 1 classes. **Produces:** web-tier classes
`.doc` (grid: main column | side column), `.doc-banner`, `.feedback`
(+ `--success|--danger|--info`, with `.feedback__raw` in mono),
`.extras`, `.sku-list`, `.sku-row` (+ `--complete|--partial|--pending|--unknown`),
`.row-actions`, `.side`, `.progress`, `.history`, `.summary`. Frame ids
`P1`…`P8`, variants suffixed `-L` and `-1920` (e.g. `P3-L`, `P3-1920`).

- [ ] **Step 1: Write `packer-document.css`** per the spec's "Packer Mode
  layout". Rules: only `var(--…)`; sizes in pt for type; the feedback band is
  the largest type on the page (`--type-title-size` or the largest role in
  tokens); rows 40px; action targets 44px; side column fixed width, wider at
  `.frame--1920`; main column rows capped at a readable max width at 1920.

- [ ] **Step 2: Build the Packer Mode frame shell in `packer-mode.html`.**
  Frame = no rail (spec A1); `.cmdbar` 60px with order number, scanner field
  ("Ready to scan", focus ring — spec A2), and right-aligned "Skip order" and
  "Exit packing"; `.doc` below; `.statusbar` 40px (session ID mono, worker,
  client). Add `.tier-label`s: `TIER QT` beside bar and status bar,
  `TIER WEB` beside the document.

- [ ] **Step 3: Draw P3 (scanning in progress) dark 1366.** Banner: order
  number, courier, country, box, tags, notes. SKU list of 5–7 rows with mixed
  states (2 complete, 1 partial, rest pending); each row shows its actions.
  Side column: progress, history (5 orders), summary.

- [ ] **Step 4: Draw P5 (wrong/unknown SKU) and P7 (order complete)** dark 1366,
  reusing P3's order. P5: danger feedback "Unknown SKU 4006381333931 — scan
  again or map it", raw scan shown, "Map SKU" visible on the affected row.
  P7: success feedback, all rows complete, "Scan the next order".

- [ ] **Step 5: Light and 1920 variants** of P3, P5, P7 (`-L` at 1366 light,
  `-1920` dark). P3-1920 also shows the dev scan simulator in the bar
  (dashed warning outline, "Simulate scan" field + button).

- [ ] **Step 6: Lint + render.** Nine frames; check the feedback band is the
  most prominent element, and nothing clips at 1366.

- [ ] **Step 7: Commit.**

```bash
git add docs/design/phase10
git commit -m "Phase 10 Bundle 2: Packer Mode order document, key states"
```

---

### Task 3: Packer Mode — remaining states

**Files:** Modify `docs/design/phase10/packer-mode.html`.
**Consumes:** Task 2 classes; add to `packer-document.css` only if a state
needs a class that does not exist yet.

- [ ] **Step 1: P1 no session** — `.state-panel` in the doc area: "No session
  open", "Start a session from the Packing tab", scanner field disabled,
  "Skip order" disabled, "Exit packing" enabled.
- [ ] **Step 2: P2 waiting for order** — feedback `--info` "Scan an order
  barcode"; no banner or SKU list; side column populated.
- [ ] **Step 3: P4 match** — P3 with success feedback naming the SKU that
  just matched and its new count; that row visibly just changed (tint only,
  no animation).
- [ ] **Step 4: P6 extras present** — `.extras` section above the SKU list
  titled "Extra items scanned", 2 SKUs with count and "Keep" / "Remove".
- [ ] **Step 5: P8 session complete** — `.state-panel` with orders packed,
  items packed, duration; "Exit packing" is `.btn--primary`, scanner disabled.
- [ ] **Step 6: Lint + render; commit.**

```bash
git add docs/design/phase10
git commit -m "Phase 10 Bundle 2: Packer Mode remaining states"
```

---

### Task 4: Packing table view

**Files:** Create `docs/design/phase10/packing-table.html`.
**Before drawing, read** `gui/main_window.py` `_setup_order_tree` (≈ lines
466–646) for the current columns and toolbar (Start Packing, SKU Mapping, End
Session). Frames use the full shell with the rail; "Packing" rail item
current.

- [ ] **Step 1: T1 dark and T1-L light.** Command bar: client selector
  (240px), session ID mono, filter field, "Start packing" (primary),
  "SKU mapping", "End session". Page: `.card` holding a grouped table — order
  rows (order no., item count, courier, F5 status chip) with SKU child rows
  (SKU mono, product, qty) under 2 expanded orders; 40px rows.
- [ ] **Step 2: T2 dark** — no session: `.state-panel` "No session open" with
  "Open session" as the one primary action.
- [ ] **Step 3: Lint + render; commit** (`Phase 10 Bundle 2: Packing table view`).

---

### Task 5: Session Browser

**Files:** Create `docs/design/phase10/session-browser.html`.
**Before drawing, read** `gui/session_browser/sessions_list_widget.py` and
`session_details_dialog.py` for the real columns, filters and detail tabs
(overview, orders, metrics). Follow artbook D1/D2 for the pattern.

- [ ] **Step 1: B1 + B1-L** — list with filters (client, date range, status,
  search), status chips, one row selected.
- [ ] **Step 2: B2 + B2-L** — session detail as drawn in D2 (not a modal
  dialog unless D2 draws one): overview numbers, orders list, metrics.
- [ ] **Step 3: B3 dark** — no matches: `.state-panel` "No sessions match
  these filters" with "Clear filters".
- [ ] **Step 4: Lint + render; commit** (`Phase 10 Bundle 2: Session Browser`).

---

### Task 6: Statistics

**Files:** Create `docs/design/phase10/statistics.html`.
**Before drawing, read** `gui/main_window.py` `_setup_statistics_tab` and
`_update_statistics` (≈ lines 647–760) for every number shown today; draw
each one, nothing invented.

- [ ] **Step 1: S1 + S1-L** — stat cards (`.card`) in a grid, largest number
  per card in the biggest type role, label in secondary text.
- [ ] **Step 2: S2 dark** — "No packing data yet" `.state-panel` pointing at
  the Packing tab.
- [ ] **Step 3: Lint + render; commit** (`Phase 10 Bundle 2: Statistics`).

---

### Task 7: Handoff sheet and index

**Files:** Create `docs/design/phase10/HANDOFF.md`; modify `index.html`.

- [ ] **Step 1: Write `HANDOFF.md`** per the spec's "Files" section: one table
  per screen with columns `Frame region | Replaces (file:attribute) | Bundle |
  Tier | Component`. Packer Mode must account for every widget the spec
  lists as replaced. Component is one of `Card`, `StatePanel`, `CommandBar`,
  `Toast`, `ConfirmDialog`, status chip, or `new` (say what). End with
  "Departures from the artbook" covering spec A1 and A2 and anything else you
  changed while drawing, each with its reason.
- [ ] **Step 2: Check `index.html`** links every frame anchor that now exists
  (25) and links `HANDOFF.md`.
- [ ] **Step 3: Full lint + render of all five HTML files; commit**
  (`Phase 10 Bundle 2: handoff sheet`) and `git push -u origin
  worktree-phase10-bundle2`.

---

### Task 8: Private preview link

- [ ] **Step 1: Publish** with the `Artifact` tool: `file_path`
  `docs/design/phase10/index.html`, `files` map for `tokens.css`,
  `artboard.css`, `packer-document.css`, `packer-mode.html`,
  `packing-table.html`, `session-browser.html`, `statistics.html`,
  favicon `📦`, description "Phase 10 Packing Tool artboards for owner
  review." If supporting `.html` files are refused, publish each screen file
  as its own artifact instead (with `tokens.css` and the two CSS files in its
  `files` map) and collect all URLs.
- [ ] **Step 2: Record the URL(s)** in the runner `state.md` so Stage C puts
  them in the PR body. Do not open the PR — Stage C does.
