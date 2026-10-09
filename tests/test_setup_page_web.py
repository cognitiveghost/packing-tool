"""The setup document in a real Chromium: Worker selection and SKU mapping.

Never mark these skip -- a page nobody can run is a page nobody guards.
"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from setup_web import (
    click,
    eval_js,
    mounted,
    press,
    run_js,
    set_value,
    settle,
    shown,
    text,
    until_js,
)

from gui.setup_payload import (
    MappingEditor,
    mapping_error,
    mapping_payload,
    quick_payload,
    workers_payload,
)

NOW = datetime(2026, 10, 7, 14, 6, tzinfo=timezone(timedelta(hours=3)))


def worker(worker_id, name, sessions=0, orders=0, days=None):
    return SimpleNamespace(
        id=worker_id, name=name, total_sessions=sessions, total_orders=orders,
        last_active=(NOW - timedelta(days=days)).isoformat() if days is not None else None,
        created_at=None,
    )


SIX = [
    worker("w1", "Ivan", 31, 2870, 0),
    worker("w2", "Maria", 14, 1204, 1),
    worker("w3", "Georgi", 22, 1951, 2),
    worker("w4", "Petya", 9, 688, 8),
    worker("w5", "Elena", 3, 140, 25),
    worker("w6", "Dimitar", 1, 37, 40),
]
READ = {f"59012345{n:03d}": f"SKU-{n:03d}" for n in range(60)}


@pytest.fixture
def page(qtbot):
    return mounted(qtbot)


def show_workers(page, qtbot, workers=SIX, **kwargs):
    _view, bridge = page
    kwargs.setdefault("startup", True)
    bridge.set_workers(workers_payload(workers, now=NOW, **kwargs))
    bridge.set_page("workers")
    settle(qtbot, bridge)


def show_mapping(page, qtbot, editor=None, **kwargs):
    _view, bridge = page
    editor = editor if editor is not None else MappingEditor(READ)
    kwargs.setdefault("client", "ACME")
    bridge.set_mapping(mapping_payload(editor, **kwargs))
    bridge.set_page("mapping")
    settle(qtbot, bridge)
    return editor


def count(view, qtbot, selector):
    return eval_js(qtbot, view, f"document.querySelectorAll({json.dumps(selector)}).length")


def record(bridge, signal_name):
    seen = []
    getattr(bridge, signal_name).connect(lambda *args: seen.append(args))
    return seen


def answers(bridge, result=""):
    """Record the answering slots' calls and answer them all with `result`."""
    calls = []

    def answer(name, *args):
        calls.append((name, *args))
        return result

    bridge.answer = answer
    return calls


# --- nothing --------------------------------------------------------------------


def test_with_no_page_the_document_draws_no_text(page, qtbot):
    view, bridge = page
    settle(qtbot, bridge)
    assert not shown(view, qtbot, "workers") and not shown(view, qtbot, "mapping")
    assert eval_js(qtbot, view, "document.body.innerText.trim()") == ""


# --- Worker selection -------------------------------------------------------------


def test_six_workers_are_six_cards_and_the_new_card(page, qtbot):
    view, _bridge = page
    show_workers(page, qtbot)
    assert shown(view, qtbot, "workers") and not shown(view, qtbot, "mapping")
    assert count(view, qtbot, "#w-grid [data-worker]") == 6
    assert shown(view, qtbot, "w-new") and not shown(view, qtbot, "w-form")
    assert text(view, qtbot, "w-leave") == "Quit"
    first = eval_js(qtbot, view, "document.querySelector('[data-worker]').innerText")
    assert "Ivan" in first and "31 sessions · 2,870 orders" in first
    assert "Last active Today, 14:06" in first
    assert eval_js(
        qtbot, view,
        "getComputedStyle(document.getElementById('w-grid')).gridTemplateColumns.split(' ').length",
    ) == 4


def test_one_worker_is_two_columns(page, qtbot):
    view, _bridge = page
    show_workers(page, qtbot, SIX[1:2])
    assert count(view, qtbot, "#w-grid [data-worker]") == 1
    assert eval_js(
        qtbot, view,
        "getComputedStyle(document.getElementById('w-grid')).gridTemplateColumns.split(' ').length",
    ) == 2


def test_no_workers_says_so_above_the_new_card(page, qtbot):
    view, _bridge = page
    show_workers(page, qtbot, [])
    assert shown(view, qtbot, "w-empty")
    assert "No workers yet" in text(view, qtbot, "w-empty")
    assert "Create a worker profile to start packing." in text(view, qtbot, "w-empty")
    assert shown(view, qtbot, "w-new")


def test_the_switch_context_names_the_way_back_and_marks_the_current_card(page, qtbot):
    view, _bridge = page
    show_workers(page, qtbot, startup=False, current_id="w1", current_name="Ivan")
    assert text(view, qtbot, "w-leave") == "Back to Ivan"
    assert "Current" in eval_js(
        qtbot, view, "document.querySelector('[data-worker=\"w1\"]').innerText")


def test_a_card_click_reaches_pick_worker(page, qtbot):
    view, bridge = page
    show_workers(page, qtbot)
    picked = record(bridge, "workerPicked")
    run_js(qtbot, view, "document.querySelector('[data-worker=\"w3\"]').click()")
    qtbot.waitUntil(lambda: picked == [("w3",)], timeout=3000)


def test_the_picked_card_says_opening(page, qtbot):
    view, _bridge = page
    show_workers(page, qtbot, picked_id="w2")
    assert "Opening…" in eval_js(
        qtbot, view, "document.querySelector('[data-worker=\"w2\"]').innerText")
    assert eval_js(
        qtbot, view, "document.querySelector('[data-worker=\"w2\"]').classList.contains('picked')")


def test_the_leave_button_reaches_leave_workers(page, qtbot):
    view, bridge = page
    show_workers(page, qtbot)
    left = record(bridge, "workersLeaveRequested")
    click(view, qtbot, "w-leave")
    qtbot.waitUntil(lambda: len(left) == 1, timeout=3000)


def test_new_worker_opens_the_form_with_the_focus_in_the_name(page, qtbot):
    view, _bridge = page
    show_workers(page, qtbot)
    click(view, qtbot, "w-new")
    assert shown(view, qtbot, "w-form") and not shown(view, qtbot, "w-new")
    assert eval_js(qtbot, view, "document.activeElement.id") == "w-name"
    assert eval_js(qtbot, view, "document.getElementById('w-name').maxLength") == 24


def test_enter_in_the_name_reaches_create_and_a_sentence_shows_until_typing(page, qtbot):
    view, bridge = page
    show_workers(page, qtbot)
    calls = answers(bridge, "Enter a name.")
    click(view, qtbot, "w-new")
    set_value(view, qtbot, "w-name", "maria")
    press(view, qtbot, "w-name", "Enter")
    qtbot.waitUntil(lambda: calls == [("createWorker", "maria")], timeout=3000)
    until_js(qtbot, view, "!document.getElementById('w-name-error').hidden")
    assert text(view, qtbot, "w-name-error") == "Enter a name."
    assert shown(view, qtbot, "w-form")

    set_value(view, qtbot, "w-name", "maria p")
    assert not shown(view, qtbot, "w-name-error")


def test_a_created_worker_closes_the_form(page, qtbot):
    view, bridge = page
    show_workers(page, qtbot)
    calls = answers(bridge, "")
    click(view, qtbot, "w-new")
    set_value(view, qtbot, "w-name", "Ana")
    click(view, qtbot, "w-create")
    qtbot.waitUntil(lambda: calls == [("createWorker", "Ana")], timeout=3000)
    until_js(qtbot, view, "document.getElementById('w-form').hidden")


def test_escape_and_cancel_close_the_form(page, qtbot):
    view, _bridge = page
    show_workers(page, qtbot)
    click(view, qtbot, "w-new")
    press(view, qtbot, "w-name", "Escape")
    assert not shown(view, qtbot, "w-form") and shown(view, qtbot, "w-new")
    click(view, qtbot, "w-new")
    click(view, qtbot, "w-cancel")
    assert not shown(view, qtbot, "w-form")


def test_a_failed_load_is_the_banner_with_retry_and_no_grid(page, qtbot):
    view, bridge = page
    failure = {"cause": "permission denied", "path": r"\\fs01\fulfilment\Workers"}
    show_workers(page, qtbot, [], failure=failure)
    assert shown(view, qtbot, "w-failed") and not shown(view, qtbot, "w-grid")
    banner = text(view, qtbot, "w-failed")
    assert "Couldn’t load the worker list." in banner
    assert "Permission denied." in banner and r"\\fs01\fulfilment\Workers" in banner
    retried = record(bridge, "workersRetryRequested")
    click(view, qtbot, "w-retry")
    qtbot.waitUntil(lambda: len(retried) == 1, timeout=3000)


def test_markup_in_a_worker_name_is_text(page, qtbot):
    view, _bridge = page
    show_workers(page, qtbot, [worker("w1", "<img src=x id=boom>")])
    assert eval_js(qtbot, view, "document.getElementById('boom') === null")
    assert "<img src=x id=boom>" in eval_js(
        qtbot, view, "document.querySelector('[data-worker]').innerText")


# --- SKU mapping ----------------------------------------------------------------


def test_sixty_mappings_are_listed_with_save_disabled(page, qtbot):
    view, _bridge = page
    show_mapping(page, qtbot)
    assert shown(view, qtbot, "mapping") and not shown(view, qtbot, "workers")
    assert text(view, qtbot, "m-client") == "ACME"
    assert count(view, qtbot, "#m-rows [data-row]") == 60
    assert text(view, qtbot, "m-count") == "60 mappings"
    assert eval_js(qtbot, view, "document.getElementById('m-save').disabled")
    assert text(view, qtbot, "m-cancel") == "Cancel"
    assert not shown(view, qtbot, "m-draft") and not shown(view, qtbot, "m-unsaved")
    assert shown(view, qtbot, "m-add") and shown(view, qtbot, "m-reload")


def test_one_mapping_is_singular(page, qtbot):
    view, _bridge = page
    show_mapping(page, qtbot, MappingEditor({"1": "A"}))
    assert text(view, qtbot, "m-count") == "1 mapping"


def test_no_mappings_is_the_empty_card_and_its_button_opens_the_draft(page, qtbot):
    view, _bridge = page
    show_mapping(page, qtbot, MappingEditor())
    assert shown(view, qtbot, "m-empty") and not shown(view, qtbot, "m-table")
    assert not shown(view, qtbot, "m-add")
    assert "No mappings yet" in text(view, qtbot, "m-empty")
    click(view, qtbot, "m-empty-add")
    assert shown(view, qtbot, "m-table") and shown(view, qtbot, "m-draft")
    assert eval_js(qtbot, view, "document.activeElement.id") == "d-barcode"


def test_the_search_narrows_the_rows_and_the_count(page, qtbot):
    view, _bridge = page
    show_mapping(page, qtbot)
    set_value(view, qtbot, "m-search", "sku-00")
    assert count(view, qtbot, "#m-rows [data-row]:not([hidden])") == 10
    assert text(view, qtbot, "m-count") == "10 of 60 mappings"
    set_value(view, qtbot, "m-search", "nothing-like-this")
    assert shown(view, qtbot, "m-nohits")
    assert text(view, qtbot, "m-nohits") == "No mappings match “nothing-like-this”."


def test_add_mapping_clears_the_search_and_focuses_the_barcode(page, qtbot):
    view, _bridge = page
    show_mapping(page, qtbot)
    set_value(view, qtbot, "m-search", "sku-00")
    click(view, qtbot, "m-add")
    assert shown(view, qtbot, "m-draft")
    assert eval_js(qtbot, view, "document.getElementById('m-search').value") == ""
    assert count(view, qtbot, "#m-rows [data-row]") == 60
    assert eval_js(qtbot, view, "document.activeElement.id") == "d-barcode"
    assert text(view, qtbot, "d-commit") == "Add"
    assert eval_js(qtbot, view, "document.getElementById('d-commit').disabled")


def test_enter_moves_barcode_to_sku_and_then_adds_and_the_draft_stays_open(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot)
    calls = answers(bridge, "")
    click(view, qtbot, "m-add")
    set_value(view, qtbot, "d-barcode", "5906 000 1")
    assert eval_js(qtbot, view, "document.getElementById('d-barcode').value") == "59060001"
    press(view, qtbot, "d-barcode", "Enter")
    assert eval_js(qtbot, view, "document.activeElement.id") == "d-sku"
    assert calls == []

    set_value(view, qtbot, "d-sku", "CRM-50ML")
    press(view, qtbot, "d-sku", "Enter")
    qtbot.waitUntil(lambda: calls == [("addMapping", "59060001", "CRM-50ML")], timeout=3000)
    until_js(qtbot, view, "document.getElementById('d-barcode').value === ''")
    assert eval_js(qtbot, view, "document.getElementById('d-sku').value") == ""
    assert shown(view, qtbot, "m-draft")
    assert eval_js(qtbot, view, "document.activeElement.id") == "d-barcode"


def test_enter_in_an_empty_barcode_goes_nowhere(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot)
    calls = answers(bridge, "")
    click(view, qtbot, "m-add")
    press(view, qtbot, "d-barcode", "Enter")
    assert eval_js(qtbot, view, "document.activeElement.id") == "d-barcode"
    assert calls == []


def test_a_refused_add_keeps_what_was_typed_and_shows_the_sentence(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot)
    answers(bridge, "Enter a SKU.")
    click(view, qtbot, "m-add")
    set_value(view, qtbot, "d-barcode", "777")
    set_value(view, qtbot, "d-sku", "X")
    click(view, qtbot, "d-commit")
    until_js(qtbot, view, "!document.getElementById('d-problem').hidden")
    assert text(view, qtbot, "d-problem") == "Enter a SKU."
    assert eval_js(qtbot, view, "document.getElementById('d-barcode').value") == "777"
    set_value(view, qtbot, "d-sku", "XY")
    assert not shown(view, qtbot, "d-problem")


def test_an_already_mapped_barcode_offers_replace(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot)
    calls = answers(bridge, "")
    click(view, qtbot, "m-add")
    set_value(view, qtbot, "d-barcode", "590-12345003")  # normalises like 59012345003
    assert shown(view, qtbot, "d-clash")
    assert text(view, qtbot, "d-clash-text") == (
        "This barcode already maps to SKU-003. Enter a SKU to replace it."
    )
    assert eval_js(qtbot, view, "document.getElementById('d-replace').disabled")
    assert eval_js(qtbot, view, "document.getElementById('d-commit').disabled")
    assert count(view, qtbot, "#m-rows .clash") == 1
    press(view, qtbot, "d-barcode", "Enter")  # does not move on
    assert eval_js(qtbot, view, "document.activeElement.id") == "d-barcode"

    set_value(view, qtbot, "d-sku", "CLN-250")
    assert text(view, qtbot, "d-clash-text") == (
        "This barcode already maps to SKU-003. Replace it with CLN-250?"
    )
    press(view, qtbot, "d-sku", "Enter")  # Enter never replaces
    qtbot.wait(150)
    assert calls == []
    click(view, qtbot, "d-replace")
    qtbot.waitUntil(
        lambda: calls == [("replaceMapping", 0, "590-12345003", "CLN-250")], timeout=3000)


def test_edit_turns_the_row_into_fields_and_update_reaches_the_slot(page, qtbot):
    view, bridge = page
    editor = show_mapping(page, qtbot)
    target = editor.rows[4]
    calls = answers(bridge, "")
    run_js(
        qtbot, view,
        f"document.querySelector('[data-row-action=\"edit\"][data-id=\"{target['id']}\"]').click()",
    )
    assert shown(view, qtbot, "m-draft")
    assert eval_js(qtbot, view, "document.getElementById('d-barcode').value") == target["barcode"]
    assert eval_js(qtbot, view, "document.activeElement.id") == "d-sku"
    assert text(view, qtbot, "d-commit") == "Update"
    # The draft sits where the row was, and the row itself is hidden.
    assert eval_js(
        qtbot, view,
        f"document.getElementById('m-draft').nextElementSibling.dataset.row === '{target['id']}'",
    )
    set_value(view, qtbot, "d-sku", "NEW-SKU")
    press(view, qtbot, "d-sku", "Enter")
    qtbot.waitUntil(
        lambda: calls == [("updateMapping", target["id"], target["barcode"], "NEW-SKU")],
        timeout=3000,
    )
    until_js(qtbot, view, "document.getElementById('m-draft').hidden")


def test_escape_closes_the_draft_before_it_leaves_the_page(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot)
    closed = record(bridge, "mappingCloseRequested")
    click(view, qtbot, "m-add")
    press(view, qtbot, "d-barcode", "Escape")
    assert not shown(view, qtbot, "m-draft")
    assert closed == []
    press(view, qtbot, "", "Escape")
    qtbot.waitUntil(lambda: len(closed) == 1, timeout=3000)


def test_unsaved_rows_carry_a_dot_and_the_footer_says_what(page, qtbot):
    view, _bridge = page
    editor = MappingEditor(READ)
    editor.add("7001", "NEW-1")
    editor.add("7002", "NEW-2")
    editor.update(editor.rows[5]["id"], editor.rows[5]["barcode"], "EDITED")
    show_mapping(page, qtbot, editor)
    assert count(view, qtbot, "#m-rows .su-undot") == 3
    assert eval_js(
        qtbot, view, "document.querySelector('#m-rows .su-undot').title") == "Added, not saved"
    assert shown(view, qtbot, "m-unsaved")
    assert text(view, qtbot, "m-unsaved") == "Unsaved: 2 added, 1 edited"
    assert not eval_js(qtbot, view, "document.getElementById('m-save').disabled")


def test_save_and_ctrl_s_reach_the_slot_only_with_changes(page, qtbot):
    view, bridge = page
    saved = record(bridge, "mappingSaveRequested")
    show_mapping(page, qtbot)
    press(view, qtbot, "", "s", ctrl=True)
    qtbot.wait(150)
    assert saved == []

    editor = MappingEditor(READ)
    editor.add("7001", "NEW-1")
    show_mapping(page, qtbot, editor)
    click(view, qtbot, "m-save")
    press(view, qtbot, "", "s", ctrl=True)
    qtbot.waitUntil(lambda: len(saved) == 2, timeout=3000)


def test_the_saved_line(page, qtbot):
    view, _bridge = page
    show_mapping(page, qtbot, saved=True)
    assert shown(view, qtbot, "m-saved")
    assert text(view, qtbot, "m-saved").strip() == "Saved. Every PC now uses these mappings."


def test_delete_asks_and_both_answers_work(page, qtbot):
    view, bridge = page
    editor = show_mapping(page, qtbot)
    target = editor.rows[4]
    deleted = record(bridge, "mappingDeleteRequested")
    button = f"document.querySelector('[data-row-action=\"delete\"][data-id=\"{target['id']}\"]')"
    run_js(qtbot, view, f"{button}.click()")
    assert shown(view, qtbot, "m-ask")
    assert text(view, qtbot, "m-ask-title") == "Delete this mapping?"
    assert text(view, qtbot, "m-ask-barcode") == target["barcode"]
    assert text(view, qtbot, "m-ask-text") == (
        "Once you save, scanning this barcode on any PC will no longer count as "
        f"{target['sku']}."
    )
    assert text(view, qtbot, "m-ask-yes") == "Delete"
    click(view, qtbot, "m-ask-no")
    assert not shown(view, qtbot, "m-ask") and deleted == []

    run_js(qtbot, view, f"{button}.click()")
    press(view, qtbot, "", "Enter")  # Enter does not answer a question
    qtbot.wait(150)
    assert deleted == [] and shown(view, qtbot, "m-ask")
    click(view, qtbot, "m-ask-yes")
    qtbot.waitUntil(lambda: deleted == [(target["id"],)], timeout=3000)
    assert not shown(view, qtbot, "m-ask")


def test_deleting_a_row_that_was_never_saved_asks_nothing(page, qtbot):
    view, bridge = page
    editor = MappingEditor(READ)
    editor.add("7001", "NEW-1")
    show_mapping(page, qtbot, editor)
    deleted = record(bridge, "mappingDeleteRequested")
    new_id = editor.rows[0]["id"]
    run_js(
        qtbot, view,
        f"document.querySelector('[data-row-action=\"delete\"][data-id=\"{new_id}\"]').click()",
    )
    qtbot.waitUntil(lambda: deleted == [(new_id,)], timeout=3000)
    assert not shown(view, qtbot, "m-ask")


def test_reload_asks_only_with_unsaved_changes(page, qtbot):
    view, bridge = page
    reloaded = record(bridge, "mappingReloadRequested")
    show_mapping(page, qtbot)
    click(view, qtbot, "m-reload")
    qtbot.waitUntil(lambda: len(reloaded) == 1, timeout=3000)
    assert not shown(view, qtbot, "m-ask")

    editor = MappingEditor(READ)
    editor.add("7001", "NEW-1")
    editor.add("7002", "NEW-2")
    show_mapping(page, qtbot, editor)
    click(view, qtbot, "m-reload")
    assert shown(view, qtbot, "m-ask")
    assert text(view, qtbot, "m-ask-title") == "Reload from server?"
    assert text(view, qtbot, "m-ask-text") == (
        "Your 2 unsaved changes (2 added) will be lost. "
        "The list is replaced with the copy on the file server."
    )
    assert text(view, qtbot, "m-ask-yes") == "Discard and reload"
    press(view, qtbot, "", "Escape")  # Esc closes the question, not the page
    assert not shown(view, qtbot, "m-ask") and len(reloaded) == 1
    click(view, qtbot, "m-reload")
    click(view, qtbot, "m-ask-yes")
    qtbot.waitUntil(lambda: len(reloaded) == 2, timeout=3000)


@pytest.mark.parametrize("way", ["m-close", "m-cancel", "Escape"])
def test_leaving_with_nothing_unsaved_just_leaves(page, qtbot, way):
    view, bridge = page
    show_mapping(page, qtbot)
    closed = record(bridge, "mappingCloseRequested")
    if way == "Escape":
        press(view, qtbot, "", "Escape")
    else:
        click(view, qtbot, way)
    qtbot.waitUntil(lambda: len(closed) == 1, timeout=3000)
    assert not shown(view, qtbot, "m-ask")


def test_leaving_with_unsaved_changes_asks_first(page, qtbot):
    view, bridge = page
    editor = MappingEditor(READ)
    editor.add("7001", "NEW-1")
    show_mapping(page, qtbot, editor)
    closed = record(bridge, "mappingCloseRequested")
    click(view, qtbot, "m-close")
    assert shown(view, qtbot, "m-ask")
    assert text(view, qtbot, "m-ask-title") == "Discard unsaved changes?"
    assert text(view, qtbot, "m-ask-text") == "Your 1 unsaved change (1 added) will be lost."
    assert text(view, qtbot, "m-ask-no") == "Keep editing"
    assert text(view, qtbot, "m-ask-yes") == "Discard"
    click(view, qtbot, "m-ask-no")
    assert closed == []
    click(view, qtbot, "m-cancel")
    click(view, qtbot, "m-ask-yes")
    qtbot.waitUntil(lambda: len(closed) == 1, timeout=3000)


def test_leave_asked_raises_the_question_only_with_unsaved_changes(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot)
    bridge.leaveAsked.emit()
    qtbot.wait(150)
    assert not shown(view, qtbot, "m-ask")

    editor = MappingEditor(READ)
    editor.add("7001", "NEW-1")
    show_mapping(page, qtbot, editor)
    bridge.leaveAsked.emit()
    until_js(qtbot, view, "!document.getElementById('m-ask').hidden")
    assert text(view, qtbot, "m-ask-title") == "Discard unsaved changes?"


def test_a_failed_save_is_the_banner_with_try_again_and_no_unsaved_line(page, qtbot):
    view, bridge = page
    editor = MappingEditor(READ)
    editor.add("7001", "NEW-1")
    error = mapping_error("save", "the cause", r"\\fs01\c\packer_config.json", 1)
    show_mapping(page, qtbot, editor, error=error)
    banner = text(view, qtbot, "m-error")
    assert "Couldn’t save to the file server." in banner
    assert "Your 1 change is still here and nothing on the server changed." in banner
    assert "the cause" in banner and r"\\fs01\c\packer_config.json" in banner
    assert text(view, qtbot, "m-error-action") == "Try again"
    assert not shown(view, qtbot, "m-unsaved")
    assert count(view, qtbot, "#m-rows .su-undot") == 1
    saved = record(bridge, "mappingSaveRequested")
    click(view, qtbot, "m-error-action")
    qtbot.waitUntil(lambda: len(saved) == 1, timeout=3000)


def test_a_failed_load_is_the_banner_with_retry_and_no_table(page, qtbot):
    view, bridge = page
    error = mapping_error("load", "the cause", "p")
    show_mapping(page, qtbot, MappingEditor(), error=error, failed=True)
    assert shown(view, qtbot, "m-error")
    assert not shown(view, qtbot, "m-table") and not shown(view, qtbot, "m-empty")
    assert not shown(view, qtbot, "m-add")
    assert text(view, qtbot, "m-error-action") == "Retry"
    reloaded = record(bridge, "mappingReloadRequested")
    click(view, qtbot, "m-error-action")
    qtbot.waitUntil(lambda: len(reloaded) == 1, timeout=3000)


def test_markup_in_a_sku_is_text(page, qtbot):
    view, _bridge = page
    show_mapping(page, qtbot, MappingEditor({"1": "<img src=x id=boom>"}))
    assert eval_js(qtbot, view, "document.getElementById('boom') === null")
    assert "<img src=x id=boom>" in text(view, qtbot, "m-rows")


# --- the quick map ----------------------------------------------------------------

CHOICES = [
    {"sku": "SER-30ML", "label": "SER-30ML — 0 / 2 packed", "key": "ser30ml"},
    {"sku": "CRM-50ML", "label": "CRM-50ML — 1 / 1 packed", "key": "crm50ml"},
]


def test_a_quick_map_for_a_barcode_locks_it_and_offers_the_order_lines(page, qtbot):
    view, bridge = page
    quick = quick_payload("barcode", barcode="5906000123456", choices=CHOICES)
    show_mapping(page, qtbot, quick=quick)
    assert shown(view, qtbot, "m-draft")
    assert eval_js(qtbot, view, "document.getElementById('d-barcode').value") == "5906000123456"
    assert eval_js(qtbot, view, "document.getElementById('d-barcode').disabled")
    until_js(qtbot, view, "document.activeElement.id === 'd-sku'")
    assert text(view, qtbot, "d-hint") == (
        "Scanned in Packer Mode. Enter the SKU it should count as."
    )
    assert count(view, qtbot, "#d-choices [data-choice]") == 2
    # Only the one add: nothing else on the page can change a mapping.
    for hidden in ("m-add", "m-reload", "m-save", "d-cancel"):
        assert not shown(view, qtbot, hidden), hidden
    assert count(view, qtbot, "#m-rows [data-row-action]") == 0
    assert text(view, qtbot, "m-cancel") == "Back to packing"
    assert shown(view, qtbot, "m-search")

    calls = answers(bridge, "")
    run_js(qtbot, view, "document.querySelector('[data-choice=\"SER-30ML\"]').click()")
    qtbot.waitUntil(
        lambda: calls == [("addMapping", "5906000123456", "SER-30ML")], timeout=3000)


def test_a_quick_map_shows_the_refusal_and_keeps_the_draft(page, qtbot):
    view, bridge = page
    quick = quick_payload("barcode", barcode="5906000123456", choices=CHOICES)
    show_mapping(page, qtbot, quick=quick)
    answers(bridge, "Not on this order. Pick one of the lines below.")
    set_value(view, qtbot, "d-sku", "4006381333931")
    press(view, qtbot, "d-sku", "Enter")
    until_js(qtbot, view, "!document.getElementById('d-problem').hidden")
    assert text(view, qtbot, "d-problem") == "Not on this order. Pick one of the lines below."
    assert shown(view, qtbot, "m-draft")


def test_a_quick_map_for_a_sku_adds_on_the_barcodes_enter(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot, quick=quick_payload("sku", sku="SER-30ML"))
    assert eval_js(qtbot, view, "document.getElementById('d-sku').value") == "SER-30ML"
    assert eval_js(qtbot, view, "document.getElementById('d-sku').disabled")
    until_js(qtbot, view, "document.activeElement.id === 'd-barcode'")
    assert text(view, qtbot, "d-hint") == "Scan or type the barcode for this SKU."
    assert count(view, qtbot, "#d-choices [data-choice]") == 0
    calls = answers(bridge, "")
    set_value(view, qtbot, "d-barcode", "5906000999")
    press(view, qtbot, "d-barcode", "Enter")
    qtbot.waitUntil(lambda: calls == [("addMapping", "5906000999", "SER-30ML")], timeout=3000)


def test_a_quick_map_onto_a_mapped_barcode_goes_on_only_by_replace(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot, quick=quick_payload("sku", sku="SER-30ML"))
    calls = answers(bridge, "")
    set_value(view, qtbot, "d-barcode", "59012345003")
    press(view, qtbot, "d-barcode", "Enter")
    qtbot.wait(150)
    assert calls == [] and shown(view, qtbot, "d-clash")
    click(view, qtbot, "d-replace")
    qtbot.waitUntil(
        lambda: calls == [("replaceMapping", 0, "59012345003", "SER-30ML")], timeout=3000)


def test_a_choice_for_a_mapped_barcode_arms_replace(page, qtbot):
    """The wrong-mapping case: the scanned barcode maps to a SKU off this order."""
    view, bridge = page
    quick = quick_payload("barcode", barcode="59012345003", choices=CHOICES)
    show_mapping(page, qtbot, quick=quick)
    calls = answers(bridge, "")
    assert shown(view, qtbot, "d-clash")
    assert eval_js(qtbot, view, "document.getElementById('d-replace').disabled")

    run_js(qtbot, view, "document.querySelector('[data-choice=\"SER-30ML\"]').click()")
    until_js(qtbot, view, "!document.getElementById('d-replace').disabled")
    assert text(view, qtbot, "d-clash-ask").strip() == "Replace it with SER-30ML?"
    assert calls == []  # only Replace goes on from a collision
    click(view, qtbot, "d-replace")
    qtbot.waitUntil(
        lambda: calls == [("replaceMapping", 0, "59012345003", "SER-30ML")], timeout=3000)


def test_space_on_a_focused_button_presses_it(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot)
    strays = record(bridge, "strayScanned")
    run_js(qtbot, view, "document.getElementById('m-add').focus()")
    assert eval_js(
        qtbot, view,
        "document.getElementById('m-add').dispatchEvent(new KeyboardEvent('keydown',"
        " {key: ' ', bubbles: true, cancelable: true}))",
    )  # not prevented: the button gets its Space
    press(view, qtbot, "m-add", "Enter")
    qtbot.wait(150)
    assert strays == []


def test_back_to_packing_and_escape_leave_a_quick_map(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot, quick=quick_payload("sku", sku="SER-30ML"))
    closed = record(bridge, "mappingCloseRequested")
    click(view, qtbot, "m-cancel")
    press(view, qtbot, "d-barcode", "Escape")
    qtbot.waitUntil(lambda: len(closed) == 2, timeout=3000)


def test_a_quick_map_takes_the_focus_back_when_it_is_left_on_nothing(page, qtbot):
    view, _bridge = page
    show_mapping(page, qtbot, quick=quick_payload("sku", sku="SER-30ML"))
    until_js(qtbot, view, "document.activeElement.id === 'd-barcode'")
    run_js(qtbot, view, "document.activeElement.blur()")
    until_js(qtbot, view, "document.activeElement.id === 'd-barcode'")


# --- stray scans (ADR 0004) --------------------------------------------------------


def _type_at_body(view, qtbot, chars):
    for char in chars:
        press(view, qtbot, "", char)


def test_keys_that_reach_no_field_are_handed_over_as_one_scan_on_enter(page, qtbot):
    view, bridge = page
    settle(qtbot, bridge)  # page "": nothing has the focus
    strays = record(bridge, "strayScanned")
    _type_at_body(view, qtbot, "4006381333931")
    assert strays == []
    press(view, qtbot, "", "Enter")
    qtbot.waitUntil(lambda: strays == [("4006381333931",)], timeout=3000)
    press(view, qtbot, "", "Enter")  # an Enter alone is not a scan
    qtbot.wait(150)
    assert len(strays) == 1


def test_keys_typed_into_a_field_are_not_a_stray_scan(page, qtbot):
    view, bridge = page
    show_mapping(page, qtbot)
    answers(bridge, "")
    strays = record(bridge, "strayScanned")
    click(view, qtbot, "m-add")
    for char in "123":
        press(view, qtbot, "d-barcode", char)
    press(view, qtbot, "d-barcode", "Enter")
    qtbot.wait(150)
    assert strays == []


def test_a_page_change_drops_a_half_typed_stray_scan(page, qtbot):
    view, bridge = page
    settle(qtbot, bridge)
    strays = record(bridge, "strayScanned")
    _type_at_body(view, qtbot, "400")
    show_workers(page, qtbot)
    bridge.set_page("")
    settle(qtbot, bridge)
    _type_at_body(view, qtbot, "777")
    press(view, qtbot, "", "Enter")
    qtbot.waitUntil(lambda: strays == [("777",)], timeout=3000)
