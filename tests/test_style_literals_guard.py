"""A guard, not a unit test. Without it the next dialog someone adds reaches
for a hex string and the palette escapes the theme one widget at a time.

The checker's own behaviour is tested in tests/test_style_lint.py; the
build_stylesheet product is checked in tests/test_theme.py. This file only
asserts the repo's own widget code is clean.
"""
from pathlib import Path

from shared.style_lint import find_style_literals

REPO_ROOT = Path(__file__).resolve().parent.parent
# shared/ ships widget code too (server_connection.ConnectionSettingsDialog).
# shared/theme.py is the one file where a colour literal belongs.
SCOPE = [REPO_ROOT / "gui", REPO_ROOT / "packing_tool", REPO_ROOT / "shared"]
EXCLUDE = {REPO_ROOT / "shared" / "theme.py"}


def test_no_style_literals_anywhere_in_src():
    findings = [f for f in find_style_literals(SCOPE)
                if not any(str(x) in f for x in EXCLUDE)]
    assert not findings, (
        "Use a shared.theme token instead of a literal (see "
        "docs/superpowers/specs/2026-08-26-phase8-unified-design-system.md "
        "sections 3 and 4):\n" + "\n".join(findings)
    )


def test_the_guard_can_actually_see_a_literal(tmp_path):
    offender = tmp_path / "offender.py"
    offender.write_text('S = "color: #ff0000;"', encoding="utf-8")
    assert find_style_literals([offender])
