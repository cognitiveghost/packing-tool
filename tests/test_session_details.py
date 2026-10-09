"""Reading a session's files for Session details (spec section 7.1).

Ported from tests/test_session_detail_page.py, which built a Qt page to reach
the same loader.
"""

import json

import pytest

from packing_tool.session_details import (
    SessionFilesError,
    load_session_details,
    partial_summary,
)


@pytest.fixture
def work_dir(tmp_path):
    path = tmp_path / "2026-09-29_1" / "packing" / "DHL_Orders"
    path.mkdir(parents=True)
    return path


def _entry(work_dir, **over):
    entry = {
        "session_id": "2026-09-29_1",
        "status": "completed",
        "work_dir": str(work_dir),
        "packing_list_name": "Registry_Name",
    }
    entry.update(over)
    return entry


def _write(path, data):
    path.write_text(json.dumps(data), encoding="utf-8")


def test_a_registry_entry_loads_its_details_from_the_summary(work_dir):
    _write(
        work_dir / "session_summary.json",
        {
            "session_id": "2026-09-29_1",
            "worker_name": "W-004",
            "pc_name": "WH-PC-02",
            "total_orders": 14,
            "completed_orders": 9,
            "total_items": 62,
        },
    )
    record = load_session_details(_entry(work_dir))["record"]
    assert record["worker_name"] == "W-004"
    assert record["pc_name"] == "WH-PC-02"
    assert (record["completed_orders"], record["total_orders"]) == (9, 14)
    assert record["total_items_packed"] == 62


def test_the_list_name_comes_from_the_summary(work_dir):
    _write(
        work_dir / "session_summary.json",
        {"session_id": "2026-09-29_1", "packing_list_name": "DHL_Orders"},
    )
    assert load_session_details(_entry(work_dir))["record"]["packing_list_name"] == "DHL_Orders"


def test_the_list_name_falls_back_to_the_registry(work_dir):
    _write(work_dir / "session_summary.json", {"session_id": "2026-09-29_1"})
    assert load_session_details(_entry(work_dir))["record"]["packing_list_name"] == "Registry_Name"


def test_an_unfinished_list_loads_from_packing_state_alone(work_dir):
    """The Shopify flow writes no per-list session_info.json, so a list still
    being packed has packing_state.json and nothing else."""
    _write(
        work_dir / "packing_state.json",
        {
            "started_at": "2026-09-29T08:10:00",
            "pc_name": "WH-PC-02",
            "progress": {"total_orders": 5},
            "completed": [{"order_number": "1001", "items_count": 2}],
            "in_progress": {},
        },
    )
    details = load_session_details(_entry(work_dir, status="in_progress"))
    record = details["record"]
    assert record["packing_list_name"] == "Registry_Name"
    assert record["start_time"] == "2026-09-29T08:10:00"
    assert record["pc_name"] == "WH-PC-02"
    assert (record["completed_orders"], record["total_orders"]) == (1, 5)
    assert details["session_summary"]["orders"] == [{"order_number": "1001", "items_count": 2}]


def test_a_partial_summary_has_timing_when_the_orders_were_timed():
    state = {
        "started_at": "2026-09-29T08:00:00",
        "last_updated": "2026-09-29T09:00:00",
        "progress": {"total_orders": 4},
        "completed": [
            {"order_number": "1", "duration_seconds": 60, "items_count": 3, "items": []},
            {"order_number": "2", "duration_seconds": 120, "items_count": 1, "items": []},
        ],
        "skipped_orders": ["3"],
        "skipped_orders_timing": {"3": "2026-09-29T08:30:00"},
    }
    summary = partial_summary(state, {})
    assert summary["metrics"]["avg_time_per_order"] == 90
    assert summary["metrics"]["orders_per_hour"] == 2.0
    assert summary["duration_seconds"] == 3600
    assert summary["skipped_orders"] == [
        {"order_number": "3", "skipped_at": "2026-09-29T08:30:00", "status": "skipped"}
    ]


def test_a_partial_summary_without_durations_has_no_metrics():
    state = {"completed": [{"order_number": "1", "items_count": 3}], "skipped_orders": []}
    summary = partial_summary(state, {})
    assert summary["metrics"] == {}
    assert summary["orders"] == [{"order_number": "1", "items_count": 3}]


def test_nothing_completed_means_no_partial_summary():
    assert partial_summary({"completed": [], "skipped_orders": ["3"]}, {}) == {}


def test_an_unreadable_summary_names_the_file_and_the_cause(work_dir):
    (work_dir / "session_summary.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(SessionFilesError) as caught:
        load_session_details(_entry(work_dir))
    assert caught.value.path.endswith("session_summary.json")
    assert "not valid JSON" in caught.value.cause


def test_an_unreadable_state_file_is_an_error_too(work_dir):
    (work_dir / "packing_state.json").write_text("[", encoding="utf-8")
    with pytest.raises(SessionFilesError) as caught:
        load_session_details(_entry(work_dir))
    assert caught.value.path.endswith("packing_state.json")


def test_a_work_dir_with_no_files_says_so(work_dir):
    with pytest.raises(SessionFilesError) as caught:
        load_session_details(_entry(work_dir))
    assert caught.value.path == str(work_dir)
    assert caught.value.cause == "it holds no session files"


def test_an_entry_with_no_work_dir_says_so():
    with pytest.raises(SessionFilesError) as caught:
        load_session_details({"session_id": "2026-09-29_1"})
    assert caught.value.cause == "it has no work folder"


def test_an_unreadable_session_info_is_skipped(work_dir):
    _write(work_dir / "session_summary.json", {"session_id": "2026-09-29_1"})
    (work_dir.parent / "session_info.json").write_text("{", encoding="utf-8")
    assert load_session_details(_entry(work_dir))["session_info"] == {}
