"""Unit tests for the checker itself. The repo-wide guard lives in
tests/test_style_literals_guard.py; if that one fails these say why."""
import textwrap
from pathlib import Path

from shared.style_lint import find_style_literals


def _scan(tmp_path: Path, source: str) -> list[str]:
    f = tmp_path / "sample.py"
    f.write_text(textwrap.dedent(source), encoding="utf-8")
    return find_style_literals([f])


def test_flags_six_digit_and_three_digit_hex(tmp_path):
    out = _scan(tmp_path, '''
        LABEL = "color: #888888;"
        SHORT = "color: #888;"
    ''')
    assert len(out) == 2
    assert "#888888" in out[0] and "#888" in out[1]


def test_ignores_issue_numbers_in_comments(tmp_path):
    # The literal reason this is an ast checker and not a grep.
    assert _scan(tmp_path, '''
        # correct cleanup pattern learned from commit #216 failures
        X = 1
    ''') == []


def test_ignores_order_numbers_in_docstrings(tmp_path):
    assert _scan(tmp_path, '''
        def strip(order):
            """Normalise an order number: "#1001" -> "1001"."""
            return order
    ''') == []


def test_ignores_four_digit_run_that_merely_starts_like_a_hex(tmp_path):
    assert _scan(tmp_path, 'ORDER = "#1001"') == []


def test_flags_css_colour_keyword_only_in_a_declaration(tmp_path):
    out = _scan(tmp_path, '''
        STYLE = "color: green; font-weight: bold;"
        PROSE = "Status: green means shipped"
    ''')
    assert len(out) == 1 and "green" in out[0]


def test_allows_transparent_and_qt_palette_roles(tmp_path):
    assert _scan(tmp_path, '''
        A = "border-left: 2px solid transparent;"
        B = "QFrame { border: 1px solid palette(mid); }"
    ''') == []


def test_flags_pixel_font_sizes_but_not_points(tmp_path):
    out = _scan(tmp_path, '''
        BAD = "font-size: 13px;"
        OK = "font-size: 10pt;"
    ''')
    assert len(out) == 1 and "px-font" in out[0]


def test_flags_reads_of_frozen_aliases(tmp_path):
    out = _scan(tmp_path, 'S = f"background: {theme.background_elevated};"')
    assert len(out) == 1 and "alias" in out[0]


def test_does_not_mistake_a_method_call_for_an_alias_read(tmp_path):
    # QPalette.background() is a call, not a token read.
    assert _scan(tmp_path, 'c = widget.palette().background()') == []


def test_the_allow_marker_suppresses_one_line(tmp_path):
    assert _scan(tmp_path, 'DEFAULT_TAG = "#9E9E9E"  # style-lint: allow') == []


def test_f_string_fragments_are_scanned(tmp_path):
    out = _scan(tmp_path, 'S = f"color: {x}; background: #ffffff;"')
    assert len(out) == 1 and "#ffffff" in out[0]


def test_a_multiline_string_reports_the_line_the_literal_is_actually_on(tmp_path):
    findings = _scan(tmp_path, '''
        w.setStyleSheet("""
            QLabel { color: red; }
            QFrame { background: #123456; }
        """)
    ''')
    assert [f.split(":")[1] for f in findings] == ["3", "4"]


def test_the_full_css_name_set_is_covered_not_just_the_common_dozen(tmp_path):
    findings = _scan(tmp_path, 'S = "color: forestgreen; background: whitesmoke;"')
    assert len(findings) == 2


def test_rgb_and_hsl_functions_pin_a_value_just_like_a_hex(tmp_path):
    findings = _scan(tmp_path, 'S = "color: rgba(1,2,3,0.5); border: 1px solid hsl(0,0%,0%)"')
    assert len(findings) == 2 and all("css-func" in f for f in findings)


def test_the_font_shorthand_hides_a_pixel_size_too(tmp_path):
    assert _scan(tmp_path, 'S = "font: bold 13px \'Segoe UI\'"')


def test_a_colour_word_in_prose_is_still_not_a_finding(tmp_path):
    assert not _scan(tmp_path, 'S = "Tan leather and peru spice are in stock"')
