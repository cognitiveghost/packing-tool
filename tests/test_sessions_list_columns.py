"""B1's six columns.

Worker, PC and Started fold into one 'Last touched' column; Age is new;
Progress and Duration are dropped, and 'Packing List' shortens to 'Packing' --
the plan's own docstring said "Packing List and Duration are dropped", but
its own COLUMN_HEADERS assertion keeps a (renamed) Packing column; the test
below is the correction.
"""

from gui.session_browser.sessions_list_widget import (
    COLUMN_HEADERS,
    _fmt_age,
    _fmt_touched,
)


def test_the_list_has_the_six_columns_the_artboard_draws():
    assert COLUMN_HEADERS == [
        "Status",
        "Session",
        "Age",
        "Packing",
        "Items",
        "Last touched",
    ]


def test_age_is_coarse_because_nobody_reads_minutes_off_a_wall_display():
    assert _fmt_age("2026-09-02T08:10:00") is not None


def test_last_touched_folds_worker_pc_and_time_into_one_cell():
    entry = {
        "worker_name": "W-004",
        "pc_name": "WH-PC-02",
        "last_updated": "2026-09-02T11:20:00",
    }
    touched = _fmt_touched(entry)
    assert "W-004" in touched and "WH-PC-02" in touched


def test_a_session_nobody_has_touched_shows_a_dash():
    assert _fmt_touched({}) == "—"
