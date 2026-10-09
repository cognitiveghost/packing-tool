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
