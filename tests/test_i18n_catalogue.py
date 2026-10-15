"""Every on-screen string has Bulgarian, and no UI text bypasses _() (ADR 0021)."""

import json
from pathlib import Path

from shared import i18n_check as c

ROOT = Path(__file__).resolve().parent.parent
SHARED_BG = ROOT / "shared" / "assets" / "locales" / "bg.json"
APP_BG = ROOT / "locales" / "bg.json"

APP_PY = c.files(ROOT / "gui", "*.py") + [ROOT / "main.py"]
APP_HTML = c.files(ROOT / "gui" / "web", "*.html")
APP_JS = c.files(ROOT / "gui" / "web", "*.js")

# Every Python file is scanned for Qt-call literals. The scanner cannot see text
# kept in dicts; those are wrapped by hand, and the lists below grow as pages move.
GUARDED_PY: list[Path] = [
    ROOT / "gui" / "app_bridge.py",
    ROOT / "gui" / "command_bar.py",
    ROOT / "gui" / "components" / "connection_banner.py",
    ROOT / "gui" / "components" / "sidebar.py",
    ROOT / "gui" / "main_window.py",
    ROOT / "gui" / "packer_bridge.py",
    ROOT / "gui" / "packer_mode_widget.py",
    ROOT / "gui" / "sessions_page.py",
    ROOT / "gui" / "sessions_payload.py",
    ROOT / "gui" / "setup_payload.py",
]
GUARDED_HTML: list[Path] = [
    ROOT / "gui" / "web" / "app.html",
    ROOT / "gui" / "web" / "packer.html",
    ROOT / "gui" / "web" / "setup.html",
]
GUARDED_JS: list[Path] = [
    ROOT / "gui" / "web" / "app.js",
    ROOT / "gui" / "web" / "packer.js",
    ROOT / "gui" / "web" / "setup.js",
]
# Text that is never translated, with the reason.
ALLOW = {
    "Fulfilment Tool",   # brand
    "Packer Assistant",  # brand
    "Shopify",           # brand
    "CSV",               # export file format, named as the file type (exports are not translated)
    "Excel",             # export file format, named as the file type
    ".csv",              # file extension
    ".xlsx",             # file extension
    "Ctrl+S",            # keyboard shortcut, shown as typed
    "Ctrl+E",            # keyboard shortcut, shown as typed
    "{APP_NAME} {__version__}",  # window title: the brand and the version, nothing to translate
}


def _load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def _app_keys():
    keys = c.python_keys(APP_PY)
    keys.update(c.html_keys(APP_HTML))
    keys.update(c.js_keys(APP_JS))
    return keys


def test_every_key_has_bulgarian():
    merged = {**_load(SHARED_BG), **_load(APP_BG)}
    missing = sorted(k for k in _app_keys() if k not in merged)
    assert not missing, f"No BG entry in {APP_BG.name}: {missing}"


def test_no_orphan_entries():
    orphans = sorted(set(_load(APP_BG)) - set(_app_keys()))
    assert not orphans, f"{APP_BG} has entries nothing uses: {orphans}"


def test_entries_are_well_formed():
    used = _app_keys()
    for key, value in _load(APP_BG).items():
        if used.get(key):  # plural
            assert isinstance(value, list) and len(value) == 2, key
            forms = value
        else:
            assert isinstance(value, str) and value.strip(), key
            forms = [value]
        for form in forms:
            assert c.placeholders(form) == c.placeholders(key), key


def test_catalogue_is_sorted_and_formatted():
    text = APP_BG.read_text(encoding="utf-8")
    assert text == json.dumps(json.loads(text), ensure_ascii=False, sort_keys=True, indent=2) + "\n", APP_BG


def test_no_bare_ui_literals():
    found = (c.bare_python_literals(GUARDED_PY, ALLOW)
             + c.bare_html_text(GUARDED_HTML, ALLOW)
             + c.bare_js_literals(GUARDED_JS, ALLOW))
    assert not found, "Wrap these in _() / data-i18n / t():\n" + "\n".join(found)
