"""B1's six columns.

Worker, PC and Started fold into one 'Last touched' column; Age is new; the
Packing List and Duration columns are dropped. 'Packing' is the progress
column -- B1 draws "9 / 14 orders" in it on every row -- not a rename of
Packing List, which survives in the preview panel and both exports.
"""

from gui.session_browser.sessions_list_widget import (
    COLUMN_HEADERS,
    _fmt_age,
    _fmt_packing,
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


def test_packing_is_how_far_the_session_got_not_what_it_is_packing():
    entry = {
        "packing_list_name": "weigh-2026-09-02",
        "total_orders": 14,
        "completed_orders": 9,
    }
    assert _fmt_packing(entry) == "9 / 14 orders"


def test_a_list_nobody_has_started_shows_a_dash_not_a_zero_over_zero():
    assert _fmt_packing({"packing_list_name": "weigh-2026-09-02"}) == "—"


def test_last_touched_drops_the_clock_once_the_row_is_not_todays():
    """B1 writes "13d ago" on an old row; "09:40" there reads as this morning."""
    from datetime import datetime, timedelta, timezone

    old = (datetime.now(timezone.utc) - timedelta(days=13)).isoformat()
    touched = _fmt_touched({"worker_name": "W-001", "last_updated": old})
    assert touched.endswith("13d ago")
