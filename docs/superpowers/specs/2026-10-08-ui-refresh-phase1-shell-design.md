# UI refresh phase 1: design inputs, ADR 0002, shared sync, floor shell

- **Date:** 2026-10-08. dev-runner run 66, Todoist task "UI refresh phase 1" (1 of 5).
- **Mockup followed:** `docs/design/ui-refresh/mockups/Packer App.html`, frames 2a to 2e (the shell), and
  `docs/design/ui-refresh/mockups/Floor Components.html`, frames 1a and 1b (sizes and control states).
  Frame ids are defined in `Packer Screens.html`.
- **ADR:** `docs/adr/0002-every-screen-on-the-web-tier.md`, written with this spec.

## 1. Goal

A packer opens the app and sees the approved shell: a 200px sidebar that collapses to a 56px rail, a 60px
command bar, no status bar. The three pages inside it are still the Qt pages of today, in the new palette.
They move to the web tier in phases 3 to 5.

**Done when:** offscreen renders of 2a to 2e in both themes are in the PR, every departure from the mockup
is listed in the PR, and the test suite passes.

## 2. Owner decisions (2026-10-08)

| Question | Answer |
|---|---|
| What drives the connection card? | The server is checked on Retry and after a failed session action. No background probe. |
| Server unreachable at startup | Unchanged: path-recovery prompt, then exit. Phase 5 may change it with Worker selection. |
| When does the app start on "Choose a client"? | Only when no client is remembered and two or more exist. A remembered client is restored; a single client is selected. |
| Design | Approved as presented, with the sync taken from Fulfilment `main` after PR #372. |

## 3. Facts the design rests on

- Fulfilment's `origin/main` is `387efef` (PR #372, merged 2026-10-08). Against the current pin, `shared/`
  changes in `theme.py` (new palette, 12 new tokens), `navrail.py` (sidebar mode behind `expanded_width`),
  `icons.py` (a disabled pixmap), `style_lint.py` (shadow tokens allowed), six new icons (`circle-alert`,
  `moon`, `panel-left-close`, `panel-left-open`, `server`, `sun`) and three new files this phase does not
  use: `web_page.py`, `web/kit.css`, `web/page.js`.
- With that `shared/` in place, 536 tests pass and 18 fail. All 18 are in `tests/test_theme.py` and pin
  values of the old palette.
- The current pin, `ffec57b`, is not on Fulfilment's `main`: it was the head of a PR branch that was
  squash-merged as `553b7e1`. The two have an identical `shared/`. `scripts/sync_shared.py` refuses a source
  whose HEAD does not contain the pin, so this one sync needs `--force`.
- The owner's Fulfilment checkout is behind `origin/main` and must not be touched. The sync runs against a
  fresh clone.
- Nothing checks the server after startup today. `ProfileManager` probes once in its constructor.
- The first client in the list is selected at startup today, so "no client" only occurs when no client
  exists.
- The status bar holds four facts: the session id, the worker, "38 of 120 orders complete" and "12 of 40
  sessions". It holds no connection state and no message line. Confirmations are already toasts.
- `NavRail`'s sidebar mode fixes its items at 184×32 (expanded) and 40×32 (collapsed). The mockup's are 44px
  tall.

## 4. Design inputs in the repo

Copied into `docs/design/ui-refresh/`, file names unchanged because `Packer Screens.html` imports the others
by name and later phases cite its frame ids:

| Into | From |
|---|---|
| `mockups/*.html` (six bundles) | `~/Obsidian/Claude/packer-ui-refresh/ready mockups/` |
| `prompts.md`, `current/*.png` | the main checkout's untracked `docs/design/ui-refresh/` |
| `mockups/README.md` | written for this repo after Fulfilment's: the file table, how to view, the unpack script |

`prompts.md` loses its "Draft, not yet reviewed" line and gains one saying the mockups were approved on
2026-10-08.

## 5. `shared/` sync

`python scripts/sync_shared.py <fresh clone of shopify-fulfillment-tool at origin/main> --force`. The new pin
must be a commit on Fulfilment's `main`. Then:

- The 18 failing cases in `tests/test_theme.py` (11 test functions) assert a value or a relation of the old
  palette ("hover is the overlay plane", "the accent fills are theme-independent"). Palette values are
  `shared/`'s own tests, which live in Fulfilment, so seven functions are deleted. Four have a part that
  holds for any palette and are cut down to it: the two tuple tripwires (`_SURFACE_PLANES`,
  `_ACCENT_FILLS`), "a fill that fails only on hover is rejected" (with a fill that fails against the new
  `on_accent`), and "a selected row is a ring" (it keeps the `selection_bg` and `selection_border` checks;
  `accent_fill` now equals `text`, so "no accent fill in the rule" can no longer be asserted).
- No app code changes for the sync alone: the suite is otherwise green.
- `shared/web_page.py` and `shared/web/` arrive unused. Adopting them, and adding `shared/web` to
  `main.spec`'s `datas`, is phase 2.

## 6. The shell

### 6.1 Layout

```
┌──────────┬──────────────────────────────────────────────┐
│ header   │ command bar                              60px │
│ 60px     ├──────────────────────────────────────────────┤
│ nav      │ [connection banner, only when unreachable]   │
│          │                                              │
│ (stretch)│ page: Packing / Statistics / Sessions (Qt)   │
│          │   or the "Choose a client" state panel       │
│ footer   │                                              │
└──────────┴──────────────────────────────────────────────┘
 200 / 56px
```

Packer Mode still replaces the whole shell (the outer `QStackedWidget` is unchanged).

### 6.2 Sidebar: `gui/components/sidebar.py` (new)

Modelled on Fulfilment's `gui/components/sidebar.py`, at floor sizes. It owns no application state:
`MainWindow` tells it the worker, the theme, the connection state and whether a client is chosen, and
listens to its signals.

| Part | Expanded (200px) | Collapsed (56px) |
|---|---|---|
| Header, 60px, bottom hairline | 32px mark (`accent_fill` plane, radius 8, `package` glyph in `on_accent`) and "Packer Assistant" in 12pt bold | the mark, centred |
| Destinations | Packing (`clipboard-list`), Statistics (`table`), Sessions (`folder-open`): 184×44, 20px icon, label beside it. The current one is a `surface` plane with a hairline edge and a bold label | 40×44, icon only, tooltip |
| SKU mapping | same shape as a destination, not checkable, `tag` glyph | icon only, tooltip "SKU mapping…" |
| Worker | card, min 56px, `surface` plane with a `border` edge: a 32px round avatar with the initials, the name in 12pt bold (elided), and *Switch worker…* as an underlined 10pt link | the avatar in a 44px row; tooltip "<name> · Switch worker…"; a click switches worker |
| Theme | 44px segmented control, Light (`sun`) and Dark (`moon`), 10pt | one 44px button showing the theme it switches to |
| Connection | card, min 52px: a 10px dot, the state in 10pt bold, the server path in 10pt mono (elided in the middle, full path in the tooltip), and *Retry* (44px, full width) when unreachable | `server` glyph in a 44px row with the dot at its bottom right; a click retries when unreachable |

- Destinations are `NavRail(expanded_width=200)` through `FloorNavRail`, a subclass in the same file that
  overrides two private methods: `_shape` (44px items, 20px icons) and `_apply_theme` (appends one rule so a
  disabled item that is still checked shows no plane). A test pins the 44px height, so a sync that renames
  either method fails loudly instead of quietly shrinking the items.
- Tooltips name the shortcut: "Packing  Ctrl+1", "Statistics  Ctrl+2", "Sessions  Ctrl+3". The three
  shortcuts are new, and do nothing while no client is chosen.
- With no client chosen the three destinations and SKU mapping are disabled.
- Initials are the first letters of the first two words of the worker's name, upper-cased ("Desislava
  Ilieva" gives "DI", "Maria" gives "M").
- Connection states:

  | State | Label | Dot and label colour | Card |
  |---|---|---|---|
  | `ok` | Server connected | `status_success_dot`, `status_success` | no fill, no edge |
  | `checking` | Reconnecting… | `status_warning` | `status_warning_bg` fill |
  | `down` | Server unreachable | `status_danger_dot`, `status_danger` | `status_danger_bg` fill, `status_danger_border` edge, Retry shown |

- Signals: `skuMappingRequested`, `switchWorkerRequested`, `themeRequested(str)`, `retryRequested`.
  Setters: `set_expanded(bool)`, `set_worker(name)`, `set_theme_name(name)`,
  `set_connection(state, server_path)`, `set_client_chosen(bool)`. The destinations are `sidebar.rail`.
- The collapsed state is remembered per PC: `QSettings("PackingTool", "Shell")`, key `sidebar_expanded`,
  default expanded.

`RAIL_ITEMS` in `gui/main_window.py` now reads Packing, Statistics, Sessions. `RAIL_WIDTH = 76` and the two
tests that existed to make short labels fit it (`tests/test_rail_labels.py`,
`tests/test_navrail_labels_fit.py`) are deleted: a 184px item has room for the full words.

### 6.3 Command bar: `gui/command_bar.py`

Left to right, one 60px row on `surface_sunken` with a bottom hairline:

1. **Sidebar toggle**, 44×44, no edge: `panel-left-close` with tooltip "Collapse sidebar", or
   `panel-left-open` with "Expand sidebar".
2. **Client selector**, 250px. With no client it shows the placeholder "Choose a client".
3. **Session id**, 12pt mono in `text`. Hidden when no session is open, shown on every page when one is.
   Its tooltip is still the packing list's name.
4. **Filter orders**, on Packing only: grows to 300px, never below 170px, disabled without a session.
5. Stretch.
6. **Actions**, on Packing only:
   - no session: *Open session* (primary). Disabled with no client (tooltip "Open session · choose a client
     first") or with the server unreachable ("Open session · server unreachable").
   - session open: *Start packing* (primary, tooltip "Start packing · opens Packer Mode"), then *End
     session* (secondary) with "Ctrl+E" beside the label in 10pt mono. End session is disabled while the
     server is unreachable (tooltip "End session · server unreachable").
7. **Overflow** `…`: *Server connection…*, a separator, *Exit* with "Alt+F4" shown beside it.

The SKU mapping button leaves the bar. *Select worker…*, *SKU mapping…* and the theme toggle leave the
overflow: all three are in the sidebar footer. `bar_css` is still the one definition Packer Mode's bar
shares, so that bar moves to `surface_sunken` too.

New setters: `set_client_chosen(bool)`, `set_server_reachable(bool)`, `set_sidebar_expanded(bool)`. New
signal: `sidebarToggled`.

### 6.4 The status bar is deleted

`_init_status_bar`, `_sync_status_bar_to_page` and the four `sb_*` labels go, and `QMainWindow.statusBar()`
is never called, so no status bar exists.

| Fact | New home |
|---|---|
| Session id | command bar (already there) |
| Worker | sidebar footer |
| "38 of 120 orders complete" | one caption line above the order tree on the Packing page, right-aligned. Interim: phase 3 replaces it with the mockup's totals strip |
| "12 of 40 sessions" | one caption line in the Sessions page's top row, beside *Auto-refresh*. Interim: phase 4 replaces it with the tab counts |

### 6.5 Connection

`MainWindow` holds one state: `ok`, `checking` or `down`.

- `check_connection()` sets `checking`, runs `shared.server_connection.test_path_reachable` on a daemon
  thread and reports back through a queued signal, as the lock heartbeat already does. The result sets `ok`
  or `down`. A second call while one is running does nothing.
- It is called by: *Retry* on the sidebar card, a click on the collapsed connection glyph while `down`,
  *Retry* on the banner, and after a session action fails (any `except` branch of
  `start_shopify_packing_session`, and `end_session`'s). The failure's own dialog is unchanged.
- Entering `down` records the time and shows the **connection banner** above the page:
  "**Server unreachable**: `<path>` stopped answering at `<HH:MM>`. Sessions cannot be opened or ended until
  it answers." with *Retry*. The banner is `gui/components/connection_banner.py` (new): `status_danger_bg`
  plane, `status_danger_border` edge, radius 12, `circle-alert` glyph, a 44px Retry button.
- While `down`: *Open session* (the bar's and the Packing state panel's) and *End session* are disabled, and
  starting or resuming from the Sessions page does nothing but show a toast, "Server unreachable. Sessions
  cannot be opened until it answers." *Start packing* stays live, as the mockup draws it.
- Leaving `down` for `ok` hides the banner and shows the toast "Server connected again · `<path>`". A check
  that ends `ok` without having been `down` shows nothing.
- A failed lock heartbeat stays log-only, as today. With no background probe, an outage that no session
  action runs into is not shown.

### 6.6 No client

- `load_available_clients` restores the remembered client; failing that it selects the only client; failing
  that it leaves the selector on its placeholder (index -1).
- With no client chosen: destinations and SKU mapping are disabled, *Open session* is disabled, and the page
  area shows a state panel in place of the pages: "Choose a client to begin" / "Sessions, packing lists and
  SKU mapping all belong to one client." with *Choose a client* (primary), which opens the selector's list.
  When no client exists at all the selector keeps today's "(No clients available)" and the panel has no
  button.
- Choosing a client enables everything and shows the page that was current.

### 6.7 Window

First-run size 1366×768. Minimum size 1280×680: a maximised window on a 1366×768 screen loses the taskbar
and title bar, so a 1366×768 minimum could not fit the screen it is designed for.

## 7. Departures from the mockup

| # | Mockup | Built | Why |
|---|---|---|---|
| 1 | Toast: inverse plane, bottom centre of the page area, 48px | `shared/`'s toast: overlay plane with a status edge, bottom right | `shared/components/toast.py` cannot be edited here. The web pages draw the mockup's toast from phase 2 on |
| 2 | Mark `package-check`, SKU mapping `scan-barcode`, banner `triangle-alert`, a `search` glyph in the filter | `package`, `tag`, `circle-alert`, no glyph in the filter | not in `shared/assets/icons` |
| 3 | Reconnecting dot `#E8A500` in Light (`status_warning_dot`) | `status_warning` in both themes | the amber is 1.9:1 on `surface_sunken`, under the 3:1 floor for a non-text mark; Dark's value is the same as the mockup's |
| 4 | Frame 2d, Reconnecting, as a standing state | shown only while a check runs | owner decision: no background probe |
| 5 | "stopped answering at 14:02" | the time the failed check finished | the app cannot know when the server stopped |
| 6 | Hairlines in `border_subtle`, control edges in `border`, both lighter than the built values | `shared/theme.py`'s values | contrast floors (Fulfilment ADR 0018) |
| 7 | Destination label inset 12px; current item edged in `border` | 9px; `border_subtle` | `NavRail`'s own sheet |
| 8 | Disabled filter and selector: dashed edge on `control_disabled_bg` | the app sheet's disabled input (solid `border_subtle` edge) | `build_stylesheet` gives the dashed treatment to buttons only |
| 9 | Packing and Statistics content of frames 2a to 2e (page header, totals strip, index table) | today's Qt pages | phases 3 to 5 |
| 10 | End session becomes primary when the list is complete (frame 3g) | stays secondary | belongs to Packing, phase 3 |
| 11 | Destination icon and label 12px apart | about 3px | `NavRail`'s own sheet, as row 7 |
| 12 | Checked Light/Dark segment edged in `border` | `border_subtle` | matches the current destination (row 7), so the two selected states agree |
| 13 | Collapsed connection glyph: the dot sits in a `surface_sunken` ring | no ring | the dot is a child label over a `QToolButton`; a ring is a second widget for 2px, left for the web tier |
| 14 | Banner glyph centred on the two lines | aligned with the title line | reads as the title's icon when the sentence wraps at 1280px |
| 15 | Collapsed theme button shows the current theme's glyph | the glyph of the theme it switches to | section 6.2: a single button is an action, and its tooltip says "Switch to ..." |

## 8. For shared/

To raise on Fulfilment's side; nothing here blocks this phase.

- `NavRail`: an item-height parameter (floor density needs 44px), the icon-to-label gap, and no plane on a
  disabled checked item. Until then `FloorNavRail` overrides `_shape` and `_apply_theme`, and `Sidebar` reads
  `rail._buttons` (to disable destinations) and `rail.layout()` (item spacing): four private touch points.
- `build_stylesheet`: size `QPushButton`, `QComboBox` and `QLineEdit` from the density profile's
  `control_content_height`. Today the command bar sets 44px on its own controls.
- `Toast`: the mockup's inverse variant and a bottom-centre placement.
- Icons: `package-check`, `scan-barcode`, `triangle-alert`, `search`.
- `build_stylesheet`: the dashed disabled treatment for `QLineEdit` and `QComboBox`.
- `status_warning_dot`, if the amber is wanted and a floor for it is agreed.

## 9. Testing

Seams, all through public surfaces:

- **`Sidebar`** alone (`tests/test_sidebar.py`): widths 200 and 56; which parts show in each mode; item
  height 44 in both; `set_worker` gives the initials and the name; `set_connection` for each state sets the
  label, shows Retry only when `down`, and elides a long path while keeping it in the tooltip;
  `set_client_chosen(False)` disables the destinations and SKU mapping; each signal fires from its control;
  a theme switch restyles it.
- **`CommandBar`** alone (`tests/test_command_bar.py`, extended): order of the widgets; placeholder; the
  session id hidden with no session and shown on every page with one; action visibility per page and
  session; each disabled state with its tooltip; `sidebarToggled`; no SKU mapping button.
- **`ConnectionBanner`** alone: the sentence carries the path and the time; Retry emits.
- **`MainWindow`** (`tests/test_shell.py`, updated, and `tests/test_connection_state.py`): no `QStatusBar`
  exists; the overflow holds exactly *Server connection…* and *Exit*; the footer's SKU mapping, Switch
  worker and theme controls reach the same handlers the overflow items did; collapse is written to and read
  from settings; Ctrl+1/2/3 switch pages; the two caption lines carry the order summary and the session
  count; the three client-restore cases of 6.6; and the connection state machine driven by monkeypatching
  `test_path_reachable` (down shows the banner and disables Open/End session; recovery hides it and toasts;
  a failed session start triggers a check; start/resume from Sessions is refused while down).
- `tests/test_packing_empty.py` and `tests/test_packing_density.py` are updated for the removed labels and
  the bar's new ground.

**Renders.** `scripts/render_shell.py` builds a `MainWindow` offscreen against a throwaway server with
synthetic data and writes `docs/design/ui-refresh/renders/phase1/<frame>-<theme>.png` for 2a to 2e in Light
and Dark at 1366×768, plus `2b-<theme>-1920.png` at 1920×1080. The implementer looks at every PNG beside the
mockup frame before the PR, and the PR embeds them.

## 10. Out of scope

- Anything inside the pages beyond the two interim caption lines, and Packer Mode's content.
- Adopting `shared/web_page.py` and `shared/web/kit.css`, and bundling `shared/web` (phase 2).
- Startup with the server unreachable, and Worker selection itself (phase 5).
- Any edit under `shared/`.

## 11. Docs touched

`CONTEXT.md`: add **Sidebar**, **Connection card** and **Connection banner**; rewrite **Command bar** (it
gains the sidebar toggle and loses SKU mapping); note under **Session Browser** that its destination is
labelled "Sessions". `README.md` and `CLAUDE.md` only if they mention the status bar or the 76px rail.
