# Phase 10 roadmap — Packer Tool v2

Spec: `docs/superpowers/specs/2026-09-17-phase10-packer-v2-design.md`
Design references: Claude Design artbook `75385f2c-4be2-446c-8e9d-bf90ee063ff7`;
Packing artboards arrive in Bundle 2 under `docs/design/phase10/`.

Mirrored into Todoist Roadmap section `6h8v45ffWwh5W5q3` as parent
**Phase 10 — Packer Tool v2** with one subtask per bundle. The Todoist body is
the brief a run works from; this file is the sequencing. When they disagree,
this file wins.

Each bundle is **one task, one worktree, one PR**, serial, in the order below.
Every bundle inherits the READ FIRST workflow (`6h8v49hR5844MWxV`) and D7:
fix backend bugs found in touched code, with a regression test.

```
2 Artboards → 3 Qt foundation → 4 Web seam + order document → 5 Packer Mode complete
                            ↘ 6 Session Browser + Statistics
```

Worked order: 2, 3, 4, 5, 6 (Bundle 1 was dropped, see below). Bundle 6 depends only on 3.

---

### Bundle 1 — dropped
`shared/` was already in sync and the owner accepted the build size up front
(spec D1, D4). The ADR shipped with this roadmap; the WebEngine dependency, CI
guard and scanner check moved into Bundle 4. **Work starts at Bundle 2.**

### Bundle 2 — Artboards
**Repo:** packing-tool. **Output:** `docs/design/phase10/*.html` (no app code).
Draw at floor density in both themes, with artbook F0 tokens and F5 status:
- **Packer Mode** at 1366×768 and 1920×1080, with the D2 split visible
  (Qt chrome vs web document). States: no session, waiting for order, scanning
  in progress, match, wrong/unknown SKU, extras present, order complete,
  session complete.
- **Session Browser** — list, filters, detail (Shopify D1/D2 as reference).
- **Statistics** — the Qt stat-card layout.
- A handoff sheet mapping each artboard to the widgets it replaces.

**Done when:** the owner approves the artboards on the PR. Bundles 3–6 follow
them exactly (runner rule A4).

### Bundle 3 — Qt foundation
**Repos:** packing-tool (canonical), then sync to Shopify.
1. Move the components Packing Tool needs from Shopify `gui/components/` into
   `shared/` (D6) — at least `Card`, `StatePanel`, `CommandBar`, `Toast`,
   `ConfirmDialog`; Shopify imports switch to `shared`.
2. Packing shell: command bar + rail at floor density per Bundle 2 artboards.
3. In Shopify's `docs/adr/0001-analysis-results-on-the-web-tier.md`, add a note
   pointing at packing-tool ADR 0001 (its "Packing Tool stays entirely Qt"
   line is superseded).

**Done when:** both repos import those components from `shared/`, both test
suites and `style_lint` pass, and the Packing main window renders the new shell
in both themes.

### Bundle 4 — Web seam + order document
**Repo:** packing-tool. **Artboard:** Packer Mode (Bundle 2).
0. Add `PySide6-QtWebEngine` to `requirements.txt` and the
   `QtWebEngineProcess.exe` guard to `.github/workflows/build-release.yml`
   (copy Shopify `build_release.yml`'s step).
1. `QWebChannel` bridge + page skeleton (`gui/web/packer.*`) fed by
   `theme_css_vars`; theme switches repaint the page. Model it on Shopify
   `gui/results_bridge.py` and `gui/webengine_gate.py`; extract the generic part
   into `shared/` only if both bridges use it.
2. Web view is `NoFocus`; regression test for D3.
3. Order document: SKU list with per-item states; manual confirm, cancel,
   force confirm and map-SKU actions go through the bridge into the existing
   `PackerModeWidget` signals.

**Done when:** a full order can be packed with the web document, all four
per-item actions work through the bridge, the D3 test passes, CI's frozen
build contains `QtWebEngineProcess.exe`, and the owner has scanned with a real
scanner on a Windows build after clicking inside the web view.

### Bundle 5 — Packer Mode complete
**Repo:** packing-tool. **Artboard:** Packer Mode (Bundle 2).
1. Scan feedback on the web page: notification, raw scan, match / wrong SKU /
   order complete / session complete.
2. History, extras, summary, progress and the metadata banner on the page.
3. Qt chrome: scanner area resized/repositioned, Skip and Exit placed per
   artboard, dev scan simulator kept working.
4. Delete the old `QTableWidget` pieces and labels in `packer_mode_widget.py`
   and tests that only covered them.

Split into 5a (items 1–2) and 5b (items 3–4) if the plan exceeds ~15 tasks.
**Done when:** no Qt table or feedback label remains in Packer Mode, every
state drawn in Bundle 2 is reachable, and the owner has checked it on Windows.

### Bundle 6 — Session Browser + Statistics
**Repo:** packing-tool. **Artboards:** Session Browser, Statistics (Bundle 2).
1. Session Browser (`gui/session_browser/`) rebuilt in the Shopify Bundle 6
   pattern with shared components, F5 status chips and state panels.
2. Statistics tab (`MainWindow._setup_statistics_tab` / `_update_statistics`)
   rebuilt with cards; logic that belongs in `shared/stats_manager.py` moves
   there.

**Done when:** both screens match their artboards in both themes, and
`main_window.py` no longer builds Statistics widgets inline.
