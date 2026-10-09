"""The setup document's pure payloads: worker cards, name rules, the mapping editor."""

from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from gui.setup_payload import (
    clean_worker_name,
    initials,
    last_active_text,
    worker_name_problem,
    workers_payload,
)

TZ = timezone(timedelta(hours=3))
NOW = datetime(2026, 10, 7, 14, 6, tzinfo=TZ)  # a Wednesday


def worker(worker_id, name, *, sessions=0, orders=0, last=None, created=None):
    return SimpleNamespace(
        id=worker_id, name=name, total_sessions=sessions, total_orders=orders,
        last_active=last, created_at=created,
    )


def ago(**delta) -> str:
    return (NOW - timedelta(**delta)).isoformat()


# --- last active ---------------------------------------------------------------


@pytest.mark.parametrize(
    "delta, expected",
    [
        ({"hours": 6, "minutes": 26}, "Last active Today, 07:40"),
        ({"days": 1}, "Last active Yesterday"),
        ({"days": 2}, "Last active Monday"),
        ({"days": 6}, "Last active Thursday"),
        ({"days": 7}, "Last active Last week"),
        ({"days": 13}, "Last active Last week"),
        ({"days": 14}, "Last active 23 Sep"),
        ({"days": 400}, "Last active 2 Sep 2025"),
    ],
)
def test_last_active_reads_as_the_mockup_writes_it(delta, expected):
    assert last_active_text(NOW - timedelta(**delta), NOW) == expected


def test_a_time_just_after_midnight_yesterday_is_yesterday_not_today():
    when = NOW.replace(hour=0, minute=5) - timedelta(days=1)
    assert last_active_text(when, NOW) == "Last active Yesterday"


def test_a_time_in_another_zone_is_read_in_ours():
    when = datetime(2026, 10, 7, 4, 40, tzinfo=UTC)  # 07:40 at +03:00
    assert last_active_text(when, NOW) == "Last active Today, 07:40"


def test_a_worker_who_never_packed_is_just_created_for_an_hour():
    assert last_active_text(None, NOW, NOW - timedelta(minutes=59)) == "Just created"
    assert last_active_text(None, NOW, NOW - timedelta(minutes=61)) == "Not active yet"
    assert last_active_text(None, NOW) == "Not active yet"


# --- names ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, expected",
    [("Desislava Ilieva", "DI"), ("maria", "M"), ("Ana Maria de Souza", "AM"), ("", "")],
)
def test_initials(name, expected):
    assert initials(name) == expected


def test_a_name_is_trimmed_and_its_inner_spaces_collapsed():
    assert clean_worker_name("  Ana   Maria ") == "Ana Maria"
    assert clean_worker_name(None) == ""


@pytest.mark.parametrize("name", ["", "   ", None])
def test_an_empty_name_is_asked_for(name):
    assert worker_name_problem(name, []) == "Enter a name."


@pytest.mark.parametrize("name", ["Ivan!", "a/b", "<img src=x>", "Mar_ia", "Ana\tMaria@"])
def test_a_name_with_other_characters_says_which_are_allowed(name):
    assert worker_name_problem(name, []) == (
        "Use letters, numbers, spaces, dots, hyphens or apostrophes."
    )


@pytest.mark.parametrize("name", ["Ivan", "Мария", "Jean-Luc", "O'Neil", "J. R. 2", "Ana  Maria"])
def test_a_name_of_letters_digits_and_the_four_marks_passes(name):
    assert worker_name_problem(name, ["Petya"]) == ""


def test_a_duplicate_name_points_at_the_existing_card():
    assert worker_name_problem("  maria ", ["Ivan", "Maria"]) == (
        "There’s already a worker called Maria. Pick that card, or add a surname."
    )


# --- cards ---------------------------------------------------------------------


SIX = [
    worker("worker_002", "Maria", sessions=14, orders=1204, last=ago(days=1)),
    worker("worker_001", "Ivan", sessions=31, orders=2870, last=ago(hours=6, minutes=26)),
    worker("worker_005", "Zora"),
    worker("worker_004", "Elena", sessions=1, orders=1, last=ago(days=25)),
    worker("worker_006", "Boris"),
    worker("worker_003", "Georgi", sessions=22, orders=1951, last=ago(days=2)),
]


def test_cards_are_newest_first_then_the_never_active_by_name():
    payload = workers_payload(SIX, startup=True, now=NOW)
    assert [card["name"] for card in payload["cards"]] == [
        "Ivan", "Maria", "Georgi", "Elena", "Boris", "Zora",
    ]


def test_a_card_carries_its_lines():
    cards = {c["name"]: c for c in workers_payload(SIX, startup=True, now=NOW)["cards"]}
    assert cards["Ivan"] == {
        "id": "worker_001",
        "name": "Ivan",
        "initials": "I",
        "stats": "31 sessions · 2,870 orders",
        "last": "Last active Today, 07:40",
        "badge": "",
        "picked": False,
    }
    assert cards["Elena"]["stats"] == "1 session · 1 order"
    assert cards["Zora"]["stats"] == "No sessions yet"
    assert cards["Zora"]["last"] == "Not active yet"


def test_at_startup_the_way_out_is_quit():
    payload = workers_payload(SIX, startup=True, now=NOW, current_id="worker_001")
    assert payload["context"] == "startup"
    assert payload["leave"] == "Quit"
    assert payload["mode"] == "ready" and payload["error"] == {}
    assert all(card["badge"] == "" for card in payload["cards"])


def test_switching_names_the_worker_to_go_back_to_and_marks_their_card():
    payload = workers_payload(
        SIX, startup=False, now=NOW, current_id="worker_001", current_name="Ivan"
    )
    assert payload["context"] == "switch"
    assert payload["leave"] == "Back to Ivan"
    badges = {card["name"]: card["badge"] for card in payload["cards"]}
    assert badges["Ivan"] == "Current" and badges["Maria"] == ""


def test_the_picked_card_says_opening_even_when_it_is_the_current_one():
    payload = workers_payload(
        SIX, startup=False, now=NOW, current_id="worker_001", current_name="Ivan",
        picked_id="worker_001",
    )
    ivan = next(card for card in payload["cards"] if card["name"] == "Ivan")
    assert ivan["badge"] == "Opening…" and ivan["picked"] is True


def test_no_workers_is_ready_with_no_cards():
    payload = workers_payload([], startup=True, now=NOW)
    assert payload["mode"] == "ready" and payload["cards"] == []


def test_a_failed_load_carries_the_cause_and_the_path():
    payload = workers_payload(
        [], startup=False, now=NOW, current_name="Ivan",
        failure={"cause": "permission denied", "path": r"\\fs01\fulfilment\Workers"},
    )
    assert payload["mode"] == "failed"
    assert payload["cards"] == []
    assert payload["leave"] == "Back to Ivan"
    assert payload["error"] == {
        "title": "Couldn’t load the worker list.",
        "text": "Permission denied.",
        "path": r"\\fs01\fulfilment\Workers",
    }


def test_a_bare_worker_still_makes_a_card():
    bare = SimpleNamespace(
        id="worker_009", name="X", total_sessions=None, total_orders=None,
        last_active="not a date", created_at="",
    )
    card = workers_payload([bare], startup=True, now=NOW)["cards"][0]
    assert card["stats"] == "No sessions yet"
    assert card["last"] == "Not active yet"
