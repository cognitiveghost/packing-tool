"""Two guards, not unit tests.

The first is the whole point of this track: without it, the next dialog
someone adds reaches for a stock icon and the app drifts back to mixed
iconography one widget at a time. The second catches the failure mode
icon()'s KeyError cannot -- a typo in a rarely-opened dialog that no test
ever constructs.
"""
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GUI_DIR = REPO_ROOT / "gui"
ICONS_DIR = REPO_ROOT / "shared" / "assets" / "icons"

# rglob, not glob: a non-recursive scan would let a package under gui/ escape
# silently.
_PY_FILES = sorted(GUI_DIR.rglob("*.py")) + [REPO_ROOT / "main.py"]

_ICON_CALL = re.compile(r'\bicon\(\s*["\']([a-z0-9-]+)["\']')


def test_no_stock_icons_remain_anywhere_in_the_gui():
    offenders = []
    for path in _PY_FILES:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "QStyle.SP_" in line:
                offenders.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Use shared.icons.icon() instead of OS-native stock icons:\n" + "\n".join(offenders)
    )


def test_every_referenced_icon_name_is_vendored():
    missing = []
    for path in _PY_FILES:
        if path.name == "icons.py":
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for name in _ICON_CALL.findall(line):
                if not (ICONS_DIR / f"{name}.svg").is_file():
                    missing.append(f"{path.name}:{lineno}: {name}")
    assert not missing, (
        "Referenced icons with no vendored SVG (see shared/assets/README.md to "
        "add one):\n" + "\n".join(missing)
    )


def test_rail_items_icons_are_vendored():
    """RAIL_ITEMS holds bare string literals, not icon() calls, so the regex
    guard above cannot see them -- and a typo there blanks a nav-rail
    destination. Packing-tool's equivalent of shopify's _TAB_ICONS guard."""
    from gui.main_window import RAIL_ITEMS

    names = [name for name, _label, _tip in RAIL_ITEMS]
    missing = [n for n in names if not (ICONS_DIR / f"{n}.svg").is_file()]
    assert not missing, f"RAIL_ITEMS references unvendored icons: {missing}"
