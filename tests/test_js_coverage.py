"""The pure parts of tests/js_coverage.py, on hand-written V8 results.

V8's Profiler.takePreciseCoverage gives, per script, functions with ranges
{startOffset, endOffset, count}; offsets are UTF-16 code units, and a range
nested in another is more specific than it.
"""

import js_coverage
import pytest
from js_coverage import Collector, executed_units, line_report, ranges_text, utf16_len


def _r(start, end, count):
    return {"startOffset": start, "endOffset": end, "count": count}


def test_a_nested_range_paints_over_its_parent():
    ran = executed_units(10, [{"ranges": [_r(0, 10, 1), _r(4, 6, 0)]}])
    assert ran == [True] * 4 + [False] * 2 + [True] * 4


def test_a_nested_function_listed_before_its_parent_still_nests():
    ran = executed_units(10, [{"ranges": [_r(4, 6, 0)]}, {"ranges": [_r(0, 10, 1)]}])
    assert ran == [True] * 4 + [False] * 2 + [True] * 4


def test_a_never_called_function_misses_every_line_it_spans():
    source = "x = 1;\n\nfunction f() {\n  y();\n}\n"
    start, end = source.index("function"), source.index("}") + 1
    ran = executed_units(utf16_len(source), [
        {"ranges": [_r(0, len(source), 1)]},
        {"ranges": [_r(start, end, 0)]},
    ])
    assert line_report(source, ran) == (4, [3, 4, 5])


def test_a_line_partly_run_counts_as_covered():
    source = "a(); function g() { b(); }\n"
    start = source.index("function")
    ran = executed_units(utf16_len(source), [
        {"ranges": [_r(0, len(source), 1)]},
        {"ranges": [_r(start, len(source) - 1, 0)]},
    ])
    assert line_report(source, ran) == (1, [])


def test_offsets_after_a_character_above_the_bmp_are_utf16_units():
    # The emoji is one Python character and two UTF-16 units, so ";" is at
    # unit 2. Indexing by Python characters would miss line 1.
    source = "\U0001F600;\nz();\n"
    ran = [False] * utf16_len(source)
    ran[2] = True
    assert line_report(source, ran) == (2, [2])


def test_ranges_text_compresses_runs():
    assert ranges_text([1, 2, 3, 7, 9, 10]) == "1-3, 7, 9-10"
    assert ranges_text([]) == ""


def test_two_takes_are_ored_into_one_map():
    collector = Collector()
    url = (js_coverage.WEB_DIR / "setup.js").as_uri()
    collector._fold({"url": url, "functions": [{"ranges": [_r(0, 1, 1)]}]})
    collector._fold({"url": url, "functions": [{"ranges": [_r(5, 6, 1)]}]})
    ran = collector.executed["setup.js"]
    assert ran[0] and ran[5] and not ran[3]


def test_a_script_outside_gui_web_is_not_counted():
    collector = Collector()
    url = (js_coverage.WEB_DIR.parent.parent / "shared" / "web" / "page.js").as_uri()
    collector._fold({"url": url, "functions": [{"ranges": [_r(0, 1, 1)]}]})
    collector._fold({"url": "qrc:///qtwebchannel/qwebchannel.js", "functions": []})
    assert collector.executed == {}


def test_a_file_never_loaded_reports_zero():
    rows, cover = Collector().report()
    assert {name for name, *_ in rows} == {"app.js", "packer.js", "setup.js"}
    assert cover == 0.0
    assert all(missed == lines for _name, lines, missed, _text in rows)


def test_failures_name_each_file_and_the_total_below_the_threshold():
    failures = Collector().failures(80)
    assert len(failures) == 4  # three files and the total, all at 0%


class _SilentSocket:
    def sendTextMessage(self, _text):
        pass


def test_a_page_that_never_answers_is_dropped_after_the_timeout(monkeypatch):
    """Review focus 4: a dead renderer must not hang the suite."""
    monkeypatch.setattr(js_coverage, "TAKE_TIMEOUT_S", 0.2)
    collector = Collector()
    collector._ws = _SilentSocket()
    collector._sessions = {"S1"}
    collector.take()
    assert collector._sessions == set()


def test_devtools_that_never_answers_fails_loudly(qapp):
    """Review focus 5: measuring nothing must not look like passing."""
    with pytest.raises(RuntimeError, match="never answered"):
        Collector._browser_url(qapp, "http://127.0.0.1:9/json/version", timeout_s=0.5)
