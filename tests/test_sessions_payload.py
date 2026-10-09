"""What the Sessions pages say (spec 2026-10-08 phase 4, sections 5, 6 and 8).

Ported from test_sessions_list_columns.py, test_sessions_list_status.py and
test_sessions_list_empty.py, which asked a Qt table the same questions.
"""

from datetime import UTC, datetime, timedelta

import pytest

from gui.sessions_payload import (
    EXPORT_COLUMNS,
    STATUS,
    default_range,
    fmt_age,
    fmt_duration,
    fmt_touched,
    refresh_failure,
    row_action,
    session_export_rows,
    session_key,
    sessions_payload,
    status_chip,
    takeover_payload,
    visible_entries,
)

NOW = datetime(2026, 10, 7, 14, 6, 31, tzinfo=UTC)


def ago(**delta) -> str:
    return (NOW - timedelta(**delta)).isoformat()


def entry(**over) -> dict:
    base = {
        "session_id": "2026-10-06_2",
        "packing_list_name": "Afternoon_wave",
        "status": "paused",
        "worker_id": "W-002",
        "worker_name": "Maria",
        "pc_name": "WH-PC-02",
        "started_at": "2026-10-06T09:00:00+00:00",
        "last_updated": "2026-10-06T11:20:00+00:00",
        "total_orders": 110,
        "completed_orders": 71,
        "skipped_orders": 2,
        "total_items": 402,
        "work_dir": "/srv/2026-10-06_2/packing/Afternoon_wave",
        "session_path": "/srv/2026-10-06_2",
        "metrics": None,
    }
    base.update(over)
    return base


def rows(entries, **kwargs):
    return sessions_payload(entries, now=NOW, **kwargs)["rows"]


def row(**over):
    kwargs = {k: over.pop(k) for k in ("open_key", "server_down") if k in over}
    return rows([entry(**over)], **kwargs)[0]


# --- the columns ----------------------------------------------------------------


def test_age_is_the_coarsest_unit_that_fits():
    assert fmt_age(ago(minutes=25), NOW) == "25m"
    assert fmt_age(ago(hours=3, minutes=10), NOW) == "3h"
    assert fmt_age(ago(days=13, hours=2), NOW) == "13d"
    assert fmt_age("", NOW) == "—"
    assert fmt_age("not a date", NOW) == "—"


def test_last_touched_folds_worker_pc_and_time_into_one_cell():
    touched = fmt_touched(entry(last_updated="2026-10-07T11:20:00+00:00"), NOW)
    assert touched == "Maria · WH-PC-02 · 11:20"


def test_last_touched_drops_the_clock_once_the_row_is_not_todays():
    """ "09:40" on a thirteen-day-old row reads as this morning."""
    touched = fmt_touched({"worker_name": "W-001", "last_updated": ago(days=13)}, NOW)
    assert touched == "W-001 · 13d ago"


def test_a_session_nobody_has_touched_shows_a_dash():
    assert fmt_touched({}, NOW) == "—"


def test_orders_is_how_far_the_session_got():
    assert row(total_orders=14, completed_orders=9)["orders"] == "9 / 14"
    assert row(total_orders=14, completed_orders=9)["pct"] == 64


def test_a_list_with_no_orders_known_shows_a_dash_not_zero_over_zero():
    bare = row(total_orders=0, completed_orders=0)
    assert bare["orders"] == "—"
    assert bare["pct"] == 0


def test_packing_is_the_lists_name_and_items_the_units_on_it():
    made = row()
    assert made["list"] == "Afternoon_wave"
    assert made["items"] == "402"
    assert row(total_items=0)["items"] == "—"


def test_durations_read_in_two_units():
    assert fmt_duration(None) == "—"
    assert fmt_duration(0) == "—"
    assert fmt_duration(45) == "45s"
    assert fmt_duration(245) == "4m 5s"
    assert fmt_duration(3 * 3600 + 12 * 60 + 9) == "3h 12m"


# --- the status chip ------------------------------------------------------------


def test_only_the_two_states_a_packer_declares_carry_the_solid_dot():
    assert {key for key, chip in STATUS.items() if chip["manual"]} == {"paused", "incomplete"}


def test_the_tones_are_the_mockups():
    assert {key: chip["tone"] for key, chip in STATUS.items()} == {
        "not_started": "neutral",
        "in_progress": "info",
        "paused": "warning",
        "stale": "warning",
        "completed": "success",
        "incomplete": "danger",
        "abandoned": "neutral",
    }


def test_an_unknown_status_still_makes_a_chip():
    assert status_chip("something_new") == {
        "label": "Something new",
        "tone": "neutral",
        "manual": False,
    }


def test_a_row_carries_its_chip():
    made = row(status="in_progress")
    assert (made["label"], made["tone"], made["manual"]) == ("Active", "info", False)
    assert made["setBy"] == "Set by the system"
    assert row()["setBy"] == "Set by a person"


# --- tabs, dates, search, order ---------------------------------------------------


def _mixed():
    return [
        entry(session_id="a", status="not_started"),
        entry(session_id="b", status="in_progress"),
        entry(session_id="c", status="paused"),
        entry(session_id="d", status="stale"),
        entry(session_id="e", status="completed"),
        entry(session_id="f", status="incomplete"),
        entry(session_id="g", status="abandoned"),
        entry(session_id="h", status="something_new"),
    ]


def test_the_tabs_group_the_seven_statuses():
    payload = sessions_payload(_mixed(), now=NOW)
    assert [(tab["key"], tab["label"], tab["count"]) for tab in payload["tabs"]] == [
        ("all", "All", 8),
        ("open", "Open", 4),
        ("finished", "Finished", 2),
        ("abandoned", "Abandoned", 1),
    ]
    assert [r["id"] for r in rows(_mixed(), tab="finished")] == ["e", "f"]
    assert sessions_payload(_mixed(), now=NOW, tab="nonsense")["tab"] == "all"


def test_a_tabs_count_ignores_the_search_but_not_the_dates():
    entries = [entry(session_id="a"), entry(session_id="b", started_at=ago(days=60))]
    payload = sessions_payload(entries, now=NOW, query="zzz")
    assert payload["tabs"][0]["count"] == 1


def test_the_range_starts_as_the_last_thirty_days():
    assert default_range(NOW) == ("2026-09-07", "2026-10-07")
    payload = sessions_payload([], now=NOW)
    assert (payload["dateFrom"], payload["dateTo"]) == ("2026-09-07", "2026-10-07")


def test_a_session_older_than_the_range_is_left_out_until_from_is_emptied():
    old = entry(session_id="old", started_at=ago(days=45))
    assert rows([old]) == []
    assert [r["id"] for r in rows([old], date_from="")] == ["old"]


def test_a_list_nobody_started_is_dated_by_when_it_was_made():
    made = {"session_id": "n", "packing_list_name": "L", "status": "not_started",
            "created_at": ago(days=45), "total_orders": 3}
    assert rows([made]) == []
    assert len(rows([made], date_from="2026-08-01")) == 1


def test_a_session_with_no_readable_date_is_always_listed():
    assert len(rows([entry(started_at="", last_updated="")], date_from="2026-10-07")) == 1


def test_to_is_inclusive():
    assert len(rows([entry()], date_from="2026-10-06", date_to="2026-10-06")) == 1
    assert rows([entry()], date_from="2026-10-01", date_to="2026-10-05") == []


@pytest.mark.parametrize("query", ["afternoon", "2026-10-06", "MARIA", "w-002", "wh-pc"])
def test_the_search_matches_list_id_worker_and_pc(query):
    entries = [entry(), entry(session_id="zzz", packing_list_name="Other", worker_name="Ivan",
                              worker_id="W-009", pc_name="PACK-01")]
    assert [r["id"] for r in rows(entries, query=query)] == ["2026-10-06_2"]


def test_newest_first():
    entries = [
        entry(session_id="old", started_at=ago(days=3)),
        entry(session_id="new", started_at=ago(hours=1)),
        entry(session_id="mid", started_at=ago(days=1)),
    ]
    assert [r["id"] for r in rows(entries)] == ["new", "mid", "old"]


def test_visible_entries_is_what_the_page_shows():
    entries = [entry(session_id="a"), entry(session_id="b", status="completed")]
    shown, in_tab, in_dates = visible_entries(
        entries, now=NOW, tab="finished", query="", date_from="", date_to="")
    assert [e["session_id"] for e in shown] == ["b"]
    assert len(in_tab) == 1 and len(in_dates) == 2


# --- states ---------------------------------------------------------------------


def test_no_sessions_at_all_is_its_own_state():
    payload = sessions_payload([], now=NOW)
    assert payload["mode"] == "empty"
    assert payload["noMatch"] is False
    assert payload["count"] == "0 sessions"


def test_before_the_first_answer_the_page_is_loading():
    payload = sessions_payload([], now=NOW, loaded=False, refreshing=True)
    assert payload["mode"] == "loading"
    assert payload["rows"] == []
    assert payload["count"] == "–"


def test_filters_that_match_nothing_say_so():
    payload = sessions_payload([entry()], now=NOW, tab="open", query="2025-12")
    assert payload["mode"] == "ready"
    assert payload["noMatch"] is True
    assert payload["noMatchText"] == (
        "Nothing in Open between 7 Sep and 7 Oct has “2025-12” in its id, "
        "packing list, worker or PC."
    )
    assert payload["count"] == "0 of 1 sessions"


@pytest.mark.parametrize("kwargs, text", [
    ({"tab": "finished"}, "No finished sessions between 7 Sep and 7 Oct."),
    ({"tab": "all", "date_to": "2026-10-01"}, "No sessions between 7 Sep and 1 Oct."),
    ({"tab": "finished", "date_to": ""}, "No finished sessions since 7 Sep."),
    ({"tab": "finished", "date_from": ""}, "No finished sessions up to 7 Oct."),
    ({"tab": "finished", "date_from": "", "date_to": ""}, "No finished sessions."),
    ({"tab": "all", "query": "zz"},
     "Nothing between 7 Sep and 7 Oct has “zz” in its id, packing list, worker or PC."),
])
def test_the_no_match_sentence_names_the_tab_the_range_and_the_query(kwargs, text):
    assert sessions_payload([entry()], now=NOW, **kwargs)["noMatchText"] == text


def test_the_count_and_the_export_title_follow_what_is_shown():
    payload = sessions_payload([entry(session_id="a"), entry(session_id="b")], now=NOW)
    assert payload["count"] == "2 sessions"
    assert payload["exportTitle"] == "Export the 2 sessions shown"
    one = sessions_payload(
        [entry(session_id="a"), entry(session_id="b", packing_list_name="Zed", worker_name="Joe", pc_name="PC9")],
        now=NOW,
        query="afternoon",
    )
    assert one["shown"] == 1 and one["inTab"] == 2
    assert one["count"] == "1 of 2 sessions"
    assert one["exportTitle"] == "Export the 1 session shown"


def test_a_failed_refresh_keeps_the_list_and_says_where_it_is_from():
    failure = refresh_failure("/srv/Sessions/CLIENT_ACME", "the network path was not found.",
                              "14:08:31", "14:06:31")
    assert failure == {
        "path": "/srv/Sessions/CLIENT_ACME",
        "cause": "the network path was not found",
        "at": "14:08:31",
        "from": "14:06:31",
    }
    payload = sessions_payload([entry()], now=NOW, failure=failure, stamp="14:06:31")
    assert payload["failed"] is True
    assert payload["failure"] == failure
    assert len(payload["rows"]) == 1
    assert sessions_payload([entry()], now=NOW)["failure"] == {}


# --- a row's action (section 5.5) -------------------------------------------------


def test_a_list_nobody_started_starts():
    made = row(status="not_started", work_dir="")
    assert (made["action"], made["actionLabel"], made["enabled"]) == ("start", "Start packing", True)
    assert made["canDetails"] is False


@pytest.mark.parametrize("status", ["paused", "incomplete"])
def test_a_paused_or_incomplete_session_resumes(status):
    made = row(status=status)
    assert (made["action"], made["actionLabel"], made["enabled"]) == ("resume", "Resume session", True)
    assert made["note"] == ""
    assert made["canDetails"] is True


def test_a_stale_session_resumes_with_a_warning():
    made = row(status="stale")
    assert (made["action"], made["enabled"], made["warn"]) == ("resume", True, True)
    assert made["note"] == (
        "WH-PC-02 stopped responding. You will be asked before this PC takes over."
    )


def test_a_session_active_elsewhere_cannot_be_resumed():
    made = row(status="in_progress")
    assert (made["action"], made["actionLabel"], made["enabled"]) == ("resume", "Resume session", False)
    assert made["warn"] is False
    assert made["note"] == (
        "Open on WH-PC-02 right now. It can be taken over once that PC stops responding."
    )


def test_the_session_open_here_goes_to_packing():
    key = session_key(entry())
    made = row(status="in_progress", open_key=key)
    assert (made["action"], made["actionLabel"], made["enabled"]) == ("show", "Go to Packing", True)
    assert made["why"] == "open on this PC"
    assert {"label": "PC", "value": "WH-PC-02 (this PC)"} in made["facts"]


@pytest.mark.parametrize("status", ["completed", "abandoned"])
def test_a_finished_or_abandoned_session_shows_its_details(status):
    made = row(status=status)
    assert (made["action"], made["actionLabel"], made["enabled"]) == ("details", "View details", True)
    assert made["canDetails"] is False  # the primary action already is


@pytest.mark.parametrize("status", ["not_started", "paused", "stale", "in_progress"])
def test_another_session_open_here_disables_start_and_resume(status):
    made = row(status=status, open_key="2026-10-07_1|Morning_wave")
    assert made["enabled"] is False
    assert made["note"] == "2026-10-07_1 is open on this PC. End it before opening another."


def test_details_stay_reachable_with_another_session_open():
    assert row(status="completed", open_key="x|y")["enabled"] is True
    assert row(status="paused", open_key="x|y")["canDetails"] is True


def test_the_server_being_down_disables_start_and_resume():
    made = row(status="paused", server_down=True)
    assert made["enabled"] is False
    assert made["note"] == "Server unreachable. Sessions cannot be opened until it answers."
    assert row(status="completed", server_down=True)["enabled"] is True


def test_an_unknown_status_offers_details_only_when_there_are_files():
    assert row(status="something_new")["action"] == "details"
    bare = row(status="something_new", work_dir="")
    assert (bare["action"], bare["actionLabel"], bare["enabled"]) == ("", "", False)


def test_row_action_is_the_rows_action():
    assert row_action(entry(status="paused")) == {
        "action": "resume", "actionLabel": "Resume session", "enabled": True,
        "note": "", "warn": False,
    }
    assert row_action(entry(status="paused"), server_down=True)["enabled"] is False


# --- the pane (section 5.3) --------------------------------------------------------


def test_the_pane_has_seven_facts():
    made = row(metrics={"total_corrections": 4, "total_unknown_scans": 1},
               duration_seconds=3 * 3600 + 12 * 60)
    assert made["facts"] == [
        {"label": "Worker", "value": "Maria"},
        {"label": "PC", "value": "WH-PC-02"},
        {"label": "Duration", "value": "3h 12m"},
        {"label": "Items", "value": "402"},
        {"label": "Scan corrections", "value": "4"},
        {"label": "Unknown scans", "value": "1"},
        {"label": "Last touched", "value": "6 Oct, 11:20"},
    ]
    assert made["ordersNote"] == "2 skipped"


def test_an_active_sessions_duration_is_so_far():
    made = row(status="in_progress", started_at=ago(hours=3, minutes=12), duration_seconds=None)
    assert {"label": "Duration", "value": "3h 12m so far"} in made["facts"]


def test_a_session_with_no_metrics_shows_dashes():
    made = row(skipped_orders=0)
    assert {"label": "Scan corrections", "value": "—"} in made["facts"]
    assert {"label": "Unknown scans", "value": "—"} in made["facts"]
    assert {"label": "Duration", "value": "—"} in made["facts"]
    assert made["ordersNote"] == "None skipped"


@pytest.mark.parametrize("over, sentence", [
    ({"status": "not_started"}, "no orders packed yet"),
    ({"status": "in_progress"}, "scans arriving from WH-PC-02"),
    ({"status": "paused"}, "paused by Maria, 6 Oct, 11:20"),
    ({"status": "paused", "last_updated": "2026-10-07T11:20:00+00:00"}, "paused by Maria, 11:20"),
    ({"status": "paused", "worker_name": "", "worker_id": ""}, "paused, 6 Oct, 11:20"),
    ({"status": "stale"}, "WH-PC-02 stopped responding, 6 Oct, 11:20"),
    ({"status": "completed"}, "every order packed"),
    ({"status": "incomplete"}, "closed by Maria with 39 orders unpacked"),
    ({"status": "incomplete", "completed_orders": 109}, "closed by Maria with 1 order unpacked"),
    ({"status": "abandoned", "last_updated": "2026-10-02T10:00:00+00:00"}, "untouched for 5 days"),
    ({"status": "something_new"}, ""),
])
def test_the_sentence_after_set_by(over, sentence):
    assert row(**over)["why"] == sentence


def test_a_bare_entry_still_makes_a_row():
    """Review focus 1: an entry with almost nothing in it."""
    made = rows([{"session_id": "x", "status": "paused", "total_orders": None,
                  "completed_orders": None, "metrics": None, "worker_name": None,
                  "pc_name": None, "started_at": None}])[0]
    assert made["key"] == "x|"
    assert made["age"] == "—"
    assert made["touched"] == "—"
    assert made["orders"] == "—"
    assert made["why"] == "paused"
    assert made["facts"][0] == {"label": "Worker", "value": "—"}
    assert made["facts"][1] == {"label": "PC", "value": "—"}
    stale = rows([{"session_id": "x", "status": "stale"}])[0]
    assert stale["note"] == (
        "Another PC stopped responding. You will be asked before this PC takes over."
    )


# --- the take-over question (section 6) --------------------------------------------


def test_the_question_says_who_had_it_and_what_comes_along():
    lock = {"locked_by": "WH-PC-02", "worker_name": "Georgi",
            "heartbeat": "2026-10-07T13:52:10+00:00"}
    made = takeover_payload(entry(session_id="2026-10-07_2", total_orders=96,
                                  completed_orders=52), lock, now=NOW)
    assert made == {
        "key": "2026-10-07_2|Afternoon_wave",
        "id": "2026-10-07_2",
        "body": "WH-PC-02 stopped responding at 13:52 while Georgi was packing. "
                "If it comes back, it is told the session moved here.",
        "carry": "Everything saved so far comes with you: 52 of 96 orders packed.",
    }


def test_the_question_drops_the_words_it_has_nothing_for():
    made = takeover_payload(entry(pc_name=""), {"locked_by": "", "worker_name": None,
                                                "heartbeat": ""}, now=NOW)
    assert made["body"] == (
        "Another PC stopped responding. If it comes back, it is told the session moved here."
    )


# --- the list export (section 8) ----------------------------------------------------


def test_the_export_keeps_todays_columns():
    assert EXPORT_COLUMNS == (
        "Status", "Packing List", "Session ID", "Worker", "PC", "Progress", "Started",
        "Duration (s)", "Total Items", "Total Orders", "Completed Orders", "Skipped Orders",
    )


def test_csv_writes_the_raw_status_and_excel_its_word():
    made = entry(duration_seconds=900)
    assert session_export_rows([made], labels=False) == [[
        "paused", "Afternoon_wave", "2026-10-06_2", "Maria", "WH-PC-02", "71/110",
        "2026-10-06T09:00:00+00:00", 900, 402, 110, 71, 2,
    ]]
    assert session_export_rows([made], labels=True)[0][0] == "Paused"


def test_an_export_row_of_a_bare_entry_has_blanks():
    assert session_export_rows([{"session_id": "x", "status": "not_started"}], labels=False) == [
        ["not_started", "", "x", "", "", "—", "", "", "", "", "", ""]
    ]
