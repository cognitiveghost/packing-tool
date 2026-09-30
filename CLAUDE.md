# CLAUDE.md — Packer Assistant

## Project Overview
Desktop PySide6 app for the warehouse-floor stage of order fulfillment: scans barcodes to verify
packed items against packing lists created by the sibling **shopify-fulfillment-tool** repo.
Windows-only in production; development happens on Linux.

---

## Run & Test Commands

```bash
# Run application (production, uses config.ini)
python main.py

# Run against a local dev server — requires shopify-fulfillment-tool's
# run_dev.py to have been run first to create ../shopify-fulfillment-tool/dev-server
python run_dev.py

# Run test suite
python -m pytest
```

---

## Shared Module (`shared/`)

`shared/` (theme, components, icons, fonts, navrail, logger, stats, file locking, atomic writes,
session IDs) is used identically by this repo and `../shopify-fulfillment-tool`. **That repo's copy is
the canonical source** (its `docs/adr/0017-fulfilment-owns-shared.md`); this one is a pinned mirror.

- **Never hand-edit files under `shared/`**. The next sync overwrites them, CI fails the PR, and a
  hook blocks the edit.
- To change shared behavior: edit it in `shopify-fulfillment-tool`, commit and push, then from this
  repo run `python scripts/sync_shared.py [/path/to/shopify-fulfillment-tool]` (the path is needed from
  a worktree). It mirrors `shared/` and writes the commit to `scripts/shared_synced_from.txt`.
- This repo may lag behind on purpose: sync when Packing Tool is ready for what changed. CI checks
  `shared/` against the pinned commit, not against the other repo's `main`.
- The `shared/` unit tests live in shopify-fulfillment-tool. The tests here cover this app's use of it.

---

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- **Always run `graphify update .` right after modifying code** — a stale graph gives wrong answers about `shared/` ownership silently, with no error. `shared/` changes land here via `scripts/sync_shared.py`, which graphify cannot see until you re-run it.

---

## Releases

The git tag is the version. In the repo `packing_tool/__init__.py` holds `__version__ = "dev"`; the release build
stamps the tag into it (`scripts/release_version.py`). Never hand-edit `__version__` or write a version into docs.
To release: Actions → Test, Build and Release → Run workflow on `main` → pick the bump. Never create a release in
the GitHub UI — nothing builds for it.

---

## DO NOT

- **No direct commits to `main`** — this repo is PR-only, with no exception for "trivial"
  docs-only changes. A cleanup commit (e.g. removing shipped plan/spec docs) that lands
  directly on local `main` never reaches `origin` and has to be un-done later. Always branch
  + PR, even for a one-file docs change.

---

## Tooling

- **Use the `context7` MCP server** for PySide6/pytest/pandas API questions instead of answering from memory.
- **Use the `github` MCP server** for PR/issue/branch operations on this repo instead of shelling out to `gh` when a tool covers it.

---

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `cognitiveghost/packing-tool` (uses the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Domain docs

Single-context: `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

Doc paths cited in code comments that no longer exist (shipped specs, plans, audits, mockups) are in git history:
`git log --all -- <path>`.

---

## Working on this repo as an agent

**UI work: the mockup is the brief.** When a task names an approved mockup (a path under `docs/design/` or a Claude
Design artifact URL), read it first and follow it exactly. `frontend-design` decides only what the mockup leaves free:
copy, empty and error states, focus and keyboard affordances, spacing rhythm, small window sizes. This is a PySide6
desktop app:
- colours, spacing and type come from `shared/theme.py` (a new token goes there, never a hardcoded hex), and both
  themes must work;
- reuse `gui/components/` before adding a widget, and say which component you reused;
- web framing (hero sections, scroll reveals) does not apply.

Verify visuals by rendering: `QT_QPA_PLATFORM=offscreen` plus `widget.render(QImage)` saved to a PNG, then look at it.
A spec states which mockup it followed and every departure from it.

**Tooling on the dev VM:**
- Use `/usr/bin/git`, one plain git command per Bash call. The worktree guard refuses compound commands, `$VAR`
  paths, xargs/find -exec, and any git command chained with `;` or `&&`. `rtk git` is refused.
- Commit with `git commit -F <absolute path to a message file>`.
- Local `main` is stale: branch from, and review against, `origin/main`.
- `gh pr edit` fails (Projects classic). Use `gh api -X PATCH repos/<owner>/<repo>/pulls/N -F body=@file`.
- A worktree's `.venv` may be missing: `ln -s <main checkout>/.venv .venv`.
- The pytest-guard hook blocks Bash text containing "pytest" other than the plain run form, so write test files with
  Write/Edit.
- Production data in `~/Desktop/production info/` is read-only and never committed or quoted. Copy what you need to a
  temp dir first.
