# Packer Assistant

Windows desktop app (PySide6) for the warehouse floor. Open a session prepared by
[Fulfilment Tool](https://github.com/cognitiveghost/shopify-fulfillment-tool), scan an order's barcode, then scan
its items: the app checks every line is packed. Progress is saved after every scan, a session is locked to one PC
at a time with a heartbeat, and both apps share one file server and one statistics file.

## Download

Take the latest zip from [Releases](https://github.com/cognitiveghost/packing-tool/releases), unzip it and run
`PackerAssistant.exe`. The version is in the window title.

Point it at the file server once in the **⋯** menu → **Server connection…**, or copy `config.ini.example` (shipped in the
zip) to `config.ini` next to the exe and set `FileServerPath`.

To check a download was built by this repo's CI:

```bash
gh attestation verify PackerAssistant-<version>.zip -R cognitiveghost/packing-tool
```

or compare it against the `.sha256` file attached to the same release.

## Run from source

Python 3.14 on the dev machine, in CI and in release builds.

```bash
git clone https://github.com/cognitiveghost/packing-tool.git
cd packing-tool
python -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python main.py                 # uses config.ini (production share)
.venv/bin/python run_dev.py              # uses ../shopify-fulfillment-tool/dev-server
```

`run_dev.py` needs Fulfilment Tool's `run_dev.py` to have been run once first, to create that dev server.

## Test and lint

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest
.venv/bin/ruff check .
```

CI runs both on every PR. Label a PR `windows-build` to also get a frozen Windows build of it as a workflow
artifact.

## Release

Actions → **Test, Build and Release** → **Run workflow** on `main`, then pick `patch`, `minor` or `major`. CI
tests, takes the next version from the tags, builds, attests, and publishes the release with generated notes.

Do not create releases by hand in the GitHub UI: nothing builds for them.

## Layout

- `gui/`: the Qt shell (sidebar, command bar, scanner field) and the bridges; `gui/web/` holds the three web documents every screen is drawn in: the app document (Packing, Statistics, Sessions, Session details), the order document (Packer Mode) and the setup document (Worker selection, SKU mapping)
- `packing_tool/`: sessions, scanning logic, locks, state
- `shared/`: code shared with Fulfilment Tool, mirrored from its canonical copy in shopify-fulfillment-tool by `scripts/sync_shared.py` (see `CLAUDE.md`)
- `docs/adr/`: decisions; `CONTEXT.md`: the domain glossary
- `docs/design/ui-refresh/`: the approved mockups, the final renders of every screen, and `for-shared.md`, what is waiting to move into `shared/`

## Links

- Issues: <https://github.com/cognitiveghost/packing-tool/issues>
- Releases: <https://github.com/cognitiveghost/packing-tool/releases>
