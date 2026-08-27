# CLAUDE.md — Packer's Assistant

## Project Overview
Desktop PySide6 app for the warehouse-floor stage of order fulfillment: scans barcodes to verify
packed items against packing lists created by the sibling **shopify-fulfillment-tool** repo.
Windows-only in production; development happens on Linux. Version per `README.md:3` (currently 1.3.2.0, pre-release).

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

`shared/` (theme, logger, stats, file locking, atomic writes, session IDs) is used identically by
this repo and `../shopify-fulfillment-tool`. **This copy is the canonical source** — see
`docs/superpowers/specs/2026-07-25-shared-unification-design.md`.

- Edit shared behavior **here**, directly.
- After editing, propagate it: run `python scripts/sync_shared.py` from `../shopify-fulfillment-tool` (it one-way-copies from `../packing-tool/shared/` into itself).
- Do not assume `shopify-fulfillment-tool/shared/` is safe to edit — it's a synced copy and gets overwritten on the next sync.

---

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- **Always run `graphify update .` right after modifying code** — a stale graph gives wrong answers about `shared/` ownership silently, with no error. Since this repo is the canonical source for `shared/`, a stale graph here is also what feeds wrong assumptions on the shopify-fulfillment-tool side.

---

## DO NOT

- **No direct commits to `main`** — this repo is PR-only, with no exception for "trivial"
  docs-only changes. A cleanup commit (e.g. removing shipped plan/spec docs) that lands
  directly on local `main` never reaches `origin` and has to be un-done later. Always branch
  + PR, even for a one-file docs change.

---

## Tooling

- **Ponytail is active by default** — climb the ladder before writing code; don't ask permission to apply it.
- **Use `superpowers` skills** (brainstorming, systematic-debugging, writing-plans, test-driven-development, etc.) for their matching task shape — e.g. systematic-debugging before proposing a bug fix, brainstorming before new features.
- **Use the `context7` MCP server** for PySide6/pytest/pandas API questions instead of answering from memory.
- **Use the `github` MCP server** for PR/issue/branch operations on this repo instead of shelling out to `gh` when a tool covers it.
