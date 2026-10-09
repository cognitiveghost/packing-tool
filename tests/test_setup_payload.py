"""The setup document's pure payloads: worker cards, name rules, the mapping editor."""

from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from gui.setup_payload import (
    MappingEditor,
    clean_mapping,
    clean_worker_name,
    initials,
    last_active_text,
    mapping_error,
    mapping_payload,
    order_choices,
    quick_payload,
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


# --- the mapping editor ----------------------------------------------------------


READ = {"222": "SKU-B", "111": "SKU-A", "333": "SKU-C"}


def pairs(editor):
    return [(row["barcode"], row["sku"]) for row in editor.rows]


def row_id(editor, barcode):
    return next(row["id"] for row in editor.rows if row["barcode"] == barcode)


def test_what_was_read_is_listed_by_barcode_and_is_not_a_change():
    editor = MappingEditor(READ)
    assert pairs(editor) == [("111", "SKU-A"), ("222", "SKU-B"), ("333", "SKU-C")]
    assert editor.counts() == {"added": 0, "edited": 0, "deleted": 0}
    assert editor.summary() == ""
    assert editor.changes() == ({}, [])
    assert [editor.status(row) for row in editor.rows] == ["", "", ""]


def test_an_added_row_goes_on_top_and_is_new():
    editor = MappingEditor(READ)
    assert editor.add(" 44 4 ", "  Sku-d ") == ""
    assert pairs(editor)[0] == ("444", "Sku-d")  # barcode loses its spaces; SKU kept as typed
    assert editor.status(editor.rows[0]) == "new"
    assert editor.counts() == {"added": 1, "edited": 0, "deleted": 0}
    assert editor.summary() == "1 added"
    assert editor.changes() == ({"444": "Sku-d"}, [])


def test_ids_are_never_reused():
    editor = MappingEditor(READ)
    editor.add("444", "D")
    first = editor.rows[0]["id"]
    editor.delete(first)
    editor.add("555", "E")
    assert editor.rows[0]["id"] != first


@pytest.mark.parametrize(
    "barcode, sku, sentence",
    [
        ("", "X", "Enter a barcode."),
        (" - ", "X", "Enter a barcode."),
        ("444", "  ", "Enter a SKU."),
        ("111", "X", "This barcode already maps to SKU-A."),
    ],
)
def test_add_says_what_is_wrong_and_changes_nothing(barcode, sku, sentence):
    editor = MappingEditor(READ)
    assert editor.add(barcode, sku) == sentence
    assert len(editor.rows) == 3


def test_a_barcode_that_normalises_alike_collides():
    editor = MappingEditor({"590-123": "SKU-A"})
    assert editor.add("590123", "SKU-B") == "This barcode already maps to SKU-A."
    assert editor.clash("590 123")["sku"] == "SKU-A"
    assert editor.clash("590124") is None


def test_an_edited_sku_is_edited_and_edited_back_is_not():
    editor = MappingEditor(READ)
    target = row_id(editor, "222")
    assert editor.update(target, "222", "SKU-B2") == ""
    assert editor.status(editor.rows[1]) == "edited"
    assert editor.summary() == "1 edited"
    assert editor.changes() == ({"222": "SKU-B2"}, [])
    assert editor.update(target, "222", "SKU-B") == ""
    assert editor.counts() == {"added": 0, "edited": 0, "deleted": 0}


def test_an_edited_barcode_is_one_added_and_one_deleted_and_keeps_its_place():
    editor = MappingEditor(READ)
    assert editor.update(row_id(editor, "222"), "229", "SKU-B") == ""
    assert pairs(editor)[1] == ("229", "SKU-B")
    assert editor.counts() == {"added": 1, "edited": 0, "deleted": 1}
    assert editor.summary() == "1 added, 1 deleted"
    assert editor.changes() == ({"229": "SKU-B"}, ["222"])


def test_update_refuses_a_collision_but_not_with_itself():
    editor = MappingEditor(READ)
    target = row_id(editor, "222")
    assert editor.update(target, "111", "X") == "This barcode already maps to SKU-A."
    assert editor.update(target, "2-22", "SKU-B") == ""  # its own key
    assert editor.update(9999, "888", "X") == "That mapping is no longer in the list."


def test_replace_from_a_new_draft_gives_the_sku_to_the_row_that_has_the_barcode():
    editor = MappingEditor(READ)
    assert editor.replace(0, "111", "SKU-NEW") == ""
    assert pairs(editor)[0] == ("111", "SKU-NEW")
    assert len(editor.rows) == 3
    assert editor.summary() == "1 edited"


def test_replace_from_an_edited_row_removes_that_row():
    editor = MappingEditor(READ)
    assert editor.replace(row_id(editor, "222"), "111", "SKU-B") == ""
    assert pairs(editor) == [("111", "SKU-B"), ("333", "SKU-C")]
    assert editor.summary() == "1 edited, 1 deleted"
    assert editor.changes() == ({"111": "SKU-B"}, ["222"])


def test_replace_with_no_collision_is_an_add_or_an_update():
    editor = MappingEditor(READ)
    assert editor.replace(0, "444", "SKU-D") == ""
    assert pairs(editor)[0] == ("444", "SKU-D")
    assert editor.replace(0, "555", " ") == "Enter a SKU."


def test_delete_and_the_summary_of_all_three():
    editor = MappingEditor(READ)
    editor.add("444", "SKU-D")
    editor.update(row_id(editor, "111"), "111", "SKU-A2")
    editor.delete(row_id(editor, "333"))
    editor.delete(424242)  # not there: nothing happens
    assert editor.summary() == "1 added, 1 edited, 1 deleted"
    assert editor.changes() == ({"444": "SKU-D", "111": "SKU-A2"}, ["333"])


def test_a_new_row_deleted_again_leaves_nothing_to_save():
    editor = MappingEditor(READ)
    editor.add("444", "SKU-D")
    editor.delete(editor.rows[0]["id"])
    assert editor.changes() == ({}, [])


def test_loaded_starts_over():
    editor = MappingEditor(READ)
    editor.add("444", "SKU-D")
    editor.loaded({"9": "Z"})
    assert pairs(editor) == [("9", "Z")]
    assert editor.summary() == ""


def test_clean_mapping():
    assert clean_mapping(" 59 01\t2 ", "  Crm 50 ") == ("59012", "Crm 50")
    assert clean_mapping(None, None) == ("", "")


# --- the mapping page's payload ------------------------------------------------


def test_a_clean_list_is_not_dirty_and_carries_keys():
    payload = mapping_payload(MappingEditor({"590-1": "SKU-A"}), client="ACME")
    assert payload == {
        "client": "ACME",
        "mode": "ready",
        "rows": [{"id": 1, "barcode": "590-1", "sku": "SKU-A", "key": "5901", "status": ""}],
        "dirty": False,
        "changes": 0,
        "summary": "",
        "lost": "",
        "saved": False,
        "error": {},
        "quick": {},
    }


def test_unsaved_changes_are_counted_and_say_what_would_be_lost():
    editor = MappingEditor(READ)
    editor.add("444", "SKU-D")
    editor.add("555", "SKU-E")
    editor.update(row_id(editor, "111"), "111", "SKU-A2")
    payload = mapping_payload(editor, client="ACME", saved=True)
    assert payload["dirty"] is True and payload["changes"] == 3
    assert payload["summary"] == "2 added, 1 edited"
    assert payload["lost"] == "Your 3 unsaved changes (2 added, 1 edited) will be lost."
    assert payload["saved"] is False  # saved is only true with nothing unsaved
    assert [row["status"] for row in payload["rows"]][:2] == ["new", "new"]


def test_one_unsaved_change_is_singular():
    editor = MappingEditor(READ)
    editor.delete(row_id(editor, "111"))
    assert mapping_payload(editor, client="A")["lost"] == (
        "Your 1 unsaved change (1 deleted) will be lost."
    )


def test_saved_shows_while_nothing_is_unsaved():
    assert mapping_payload(MappingEditor(READ), client="A", saved=True)["saved"] is True


def test_a_failed_load_has_no_rows():
    error = mapping_error("load", "Permission denied", r"\\fs01\x\packer_config.json")
    payload = mapping_payload(MappingEditor(), client="A", error=error, failed=True)
    assert payload["mode"] == "failed" and payload["rows"] == []
    assert payload["error"] == {
        "title": "Couldn’t load the mappings.",
        "text": "The list could not be read from the file server.",
        "cause": "Permission denied",
        "path": r"\\fs01\x\packer_config.json",
        "action": "load",
    }


def test_the_save_error_counts_the_changes_it_kept():
    assert mapping_error("save", "c", "p", 3)["text"] == (
        "Your 3 changes are still here and nothing on the server changed."
    )
    assert mapping_error("save", "c", "p", 1)["text"] == (
        "Your 1 change is still here and nothing on the server changed."
    )
    assert mapping_error("save", "c", "p", 3)["title"] == "Couldn’t save to the file server."
    assert mapping_error("save", "c", "p", 3)["action"] == "save"


def test_the_quick_error_has_no_button():
    error = mapping_error("quick", "c", "p")
    assert error["title"] == "Couldn’t save to the file server."
    assert error["text"] == "Nothing on the server changed."
    assert error["action"] == ""


# --- the quick map ---------------------------------------------------------------


def test_the_choices_put_the_lines_that_still_need_scans_first():
    state = [
        {"original_sku": "A-1", "packed": 2, "required": 2},
        {"original_sku": "B-2", "packed": 0, "required": 1},
        {"original_sku": "C-3", "packed": 1, "required": 4},
    ]
    assert order_choices(state) == [
        {"sku": "B-2", "label": "B-2 — 0 / 1 packed", "key": "b2"},
        {"sku": "C-3", "label": "C-3 — 1 / 4 packed", "key": "c3"},
        {"sku": "A-1", "label": "A-1 — 2 / 2 packed", "key": "a1"},
    ]


def test_the_choices_are_empty_when_there_is_no_order():
    assert order_choices(None) == []
    assert order_choices([]) == []


def test_a_quick_map_for_a_known_sku_waits_for_a_barcode():
    assert quick_payload("sku", sku="SER-30ML") == {
        "kind": "sku",
        "sku": "SER-30ML",
        "barcode": "",
        "hint": "Scan or type the barcode for this SKU.",
        "choices": [],
    }


def test_a_quick_map_for_a_known_barcode_offers_the_order_lines():
    choices = [{"sku": "B-2", "label": "B-2 — 0 / 1 packed", "key": "b2"}]
    assert quick_payload("barcode", barcode="5906", choices=choices) == {
        "kind": "barcode",
        "sku": "",
        "barcode": "5906",
        "hint": "Scanned in Packer Mode. Enter the SKU it should count as.",
        "choices": choices,
    }
