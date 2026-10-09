"""SetupPages: what the two setup pages read from and write to the server.

A real bridge, a real WorkerManager and ProfileManager over a temp folder.
Nothing here asserts on Chromium: tests/test_setup_page_web.py does.
"""

from datetime import datetime, timedelta, timezone

import pytest

from gui.setup_pages import SetupPages
from gui.setup_payload import quick_payload
from packing_tool.profile_manager import ProfileManager, ProfileManagerError
from packing_tool.worker_manager import WorkerManager

NOW = datetime(2026, 10, 7, 14, 6, tzinfo=timezone(timedelta(hours=3)))
CHOICES = [
    {"sku": "SER-30ML", "label": "SER-30ML — 0 / 2 packed", "key": "ser30ml"},
    {"sku": "CRM-50ML", "label": "CRM-50ML — 1 / 1 packed", "key": "crm50ml"},
]


@pytest.fixture
def workers(profile_manager):
    return WorkerManager(str(profile_manager.base_path))


@pytest.fixture
def pages(profile_manager, workers, qtbot):
    profile_manager.create_client_profile("ACME", "Acme")
    profile_manager.update_sku_mapping("ACME", {"111": "SKU-A", "222": "SKU-B"})
    widget = SetupPages(workers, profile_manager, now=lambda: NOW)
    qtbot.addWidget(widget)
    return widget


def rows(pages):
    return [(row["barcode"], row["sku"]) for row in pages.bridge.mapping["rows"]]


def row_id(pages, barcode):
    return next(r["id"] for r in pages.bridge.mapping["rows"] if r["barcode"] == barcode)


# --- Worker selection ------------------------------------------------------------


def test_show_workers_pushes_the_cards_and_the_page(pages, workers):
    workers.create_worker("Ivan")
    workers.create_worker("Maria")
    pages.show_workers(startup=True)
    assert pages.bridge.page == "workers"
    payload = pages.bridge.workers
    assert payload["context"] == "startup" and payload["leave"] == "Quit"
    assert sorted(card["name"] for card in payload["cards"]) == ["Ivan", "Maria"]


def test_the_switch_context_marks_the_current_worker(pages, workers):
    ivan = workers.create_worker("Ivan")
    pages.show_workers(ivan.id, "Ivan", startup=False)
    payload = pages.bridge.workers
    assert payload["leave"] == "Back to Ivan"
    assert payload["cards"][0]["badge"] == "Current"


def test_an_unreadable_worker_list_is_the_failed_shape_and_retry_recovers(pages, workers):
    workers.workers_file.mkdir()  # open() on a directory raises OSError
    pages.show_workers(startup=True)
    payload = pages.bridge.workers
    assert payload["mode"] == "failed"
    assert payload["error"]["title"] == "Couldn’t load the worker list."
    assert payload["error"]["path"] == str(workers.workers_dir)

    workers.workers_file.rmdir()
    workers.create_worker("Ivan")
    pages.bridge.retryWorkers()
    assert pages.bridge.workers["mode"] == "ready"
    assert [card["name"] for card in pages.bridge.workers["cards"]] == ["Ivan"]


def test_picking_a_card_marks_it_and_then_emits_the_worker(pages, workers, qtbot):
    ivan = workers.create_worker("Ivan")
    pages.show_workers(startup=True)
    with qtbot.waitSignal(pages.workerChosen, timeout=3000) as caught:
        pages.bridge.pickWorker(ivan.id)
        card = pages.bridge.workers["cards"][0]
        assert card["badge"] == "Opening…" and card["picked"] is True
    assert caught.args == [ivan.id, "Ivan"]


def test_picking_an_unknown_id_does_nothing(pages, workers, qtbot):
    workers.create_worker("Ivan")
    pages.show_workers(startup=True)
    with qtbot.assertNotEmitted(pages.workerChosen, wait=400):
        pages.bridge.pickWorker("worker_999")


def test_a_second_pick_while_one_is_opening_is_ignored(pages, workers, qtbot):
    ivan = workers.create_worker("Ivan")
    maria = workers.create_worker("Maria")
    pages.show_workers(startup=True)
    chosen = []
    pages.workerChosen.connect(lambda worker_id, name: chosen.append(name))
    pages.bridge.pickWorker(ivan.id)
    pages.bridge.pickWorker(maria.id)
    qtbot.waitUntil(lambda: bool(chosen), timeout=3000)
    qtbot.wait(300)
    assert chosen == ["Ivan"]


@pytest.mark.parametrize(
    "name, sentence",
    [
        ("  ", "Enter a name."),
        ("Ivan!", "Use letters, numbers, spaces, dots, hyphens or apostrophes."),
        ("ivan", "There’s already a worker called Ivan. Pick that card, or add a surname."),
    ],
)
def test_create_returns_the_sentence_and_creates_nothing(pages, workers, name, sentence):
    workers.create_worker("Ivan")
    pages.show_workers(startup=True)
    assert pages.bridge.createWorker(name) == sentence
    assert len(workers.get_all_workers()) == 1


def test_create_makes_the_worker_and_signs_them_in(pages, workers, qtbot):
    pages.show_workers(startup=True)
    with qtbot.waitSignal(pages.workerChosen, timeout=3000) as caught:
        assert pages.bridge.createWorker("  Ana   Maria ") == ""
    created = workers.get_all_workers()
    assert [w.name for w in created] == ["Ana Maria"]
    assert caught.args == [created[0].id, "Ana Maria"]
    card = pages.bridge.workers["cards"][0]
    assert card["name"] == "Ana Maria" and card["badge"] == "Opening…"


def test_a_name_another_pc_took_meanwhile_gets_the_duplicate_sentence(pages, workers):
    pages.show_workers(startup=True)  # an empty list is on screen
    workers.create_worker("Ivan")  # another PC
    assert pages.bridge.createWorker("Ivan") == (
        "There’s already a worker called Ivan. Pick that card, or add a surname."
    )
    assert [card["name"] for card in pages.bridge.workers["cards"]] == ["Ivan"]


def test_a_server_error_on_create_is_said(pages, workers, monkeypatch):
    pages.show_workers(startup=True)

    def boom(name):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(workers, "create_worker", boom)
    assert pages.bridge.createWorker("Ivan") == "Couldn’t create the worker: input/output error."


def test_leave_is_quit_at_startup_and_back_otherwise(pages, qtbot):
    pages.show_workers(startup=True)
    with qtbot.waitSignal(pages.quitRequested, timeout=1000):
        pages.bridge.leaveWorkers()
    pages.show_workers("worker_001", "Ivan", startup=False)
    with qtbot.waitSignal(pages.backRequested, timeout=1000):
        pages.bridge.leaveWorkers()


# --- SKU mapping -------------------------------------------------------------------


def test_show_mapping_pushes_the_rows_and_the_page(pages):
    pages.show_mapping("ACME", "Acme")
    assert pages.bridge.page == "mapping"
    payload = pages.bridge.mapping
    assert payload["client"] == "Acme" and payload["mode"] == "ready"
    assert rows(pages) == [("111", "SKU-A"), ("222", "SKU-B")]
    assert payload["dirty"] is False and payload["quick"] == {}
    assert pages.dirty() is False


def test_show_mapping_reads_the_server_not_the_cache(pages, profile_manager, config_ini):
    profile_manager.load_sku_mapping("ACME")  # cached
    ProfileManager(config_path=str(config_ini)).update_sku_mapping("ACME", {"333": "SKU-C"})
    pages.show_mapping("ACME", "Acme")
    assert ("333", "SKU-C") in rows(pages)


def test_the_slots_edit_the_list_without_touching_the_server(pages, profile_manager):
    pages.show_mapping("ACME", "Acme")
    bridge = pages.bridge
    assert bridge.addMapping("444", "SKU-D") == ""
    assert bridge.updateMapping(row_id(pages, "111"), "111", "SKU-A2") == ""
    bridge.deleteMapping(row_id(pages, "222"))
    assert rows(pages) == [("444", "SKU-D"), ("111", "SKU-A2")]
    assert bridge.mapping["summary"] == "1 added, 1 edited, 1 deleted"
    assert pages.dirty() is True
    assert profile_manager.load_sku_mapping("ACME", fresh=True) == {"111": "SKU-A", "222": "SKU-B"}


def test_a_refused_add_returns_the_sentence(pages):
    pages.show_mapping("ACME", "Acme")
    assert pages.bridge.addMapping("111", "X") == "This barcode already maps to SKU-A."
    assert pages.bridge.replaceMapping(0, "111", "X") == ""
    assert ("111", "X") in rows(pages)


def test_save_writes_the_changes_and_says_saved(pages, profile_manager, qtbot):
    pages.show_mapping("ACME", "Acme")
    pages.bridge.addMapping("444", "SKU-D")
    pages.bridge.deleteMapping(row_id(pages, "222"))
    with qtbot.waitSignal(pages.mappingSaved, timeout=1000) as caught:
        pages.bridge.saveMappings()
    expected = {"111": "SKU-A", "444": "SKU-D"}
    assert caught.args == [expected]
    assert profile_manager.load_sku_mapping("ACME", fresh=True) == expected
    payload = pages.bridge.mapping
    assert payload["saved"] is True and payload["dirty"] is False
    assert pages.dirty() is False


def test_a_save_keeps_what_another_pc_mapped_meanwhile(pages, profile_manager, config_ini):
    pages.show_mapping("ACME", "Acme")
    pages.bridge.addMapping("444", "SKU-D")
    ProfileManager(config_path=str(config_ini)).update_sku_mapping("ACME", {"999": "SKU-Z"})
    pages.bridge.saveMappings()
    saved = profile_manager.load_sku_mapping("ACME", fresh=True)
    assert saved == {"111": "SKU-A", "222": "SKU-B", "444": "SKU-D", "999": "SKU-Z"}
    assert ("999", "SKU-Z") in rows(pages)  # the page shows what the server holds now


def test_save_with_nothing_unsaved_writes_nothing(pages, profile_manager, monkeypatch):
    pages.show_mapping("ACME", "Acme")
    calls = []
    monkeypatch.setattr(profile_manager, "update_sku_mapping", lambda *a, **k: calls.append(a))
    pages.bridge.saveMappings()
    assert calls == []


def test_a_failed_save_shows_the_banner_and_keeps_the_rows(pages, profile_manager, monkeypatch):
    pages.show_mapping("ACME", "Acme")
    pages.bridge.addMapping("444", "SKU-D")

    def boom(*args, **kwargs):
        raise ProfileManagerError("Could not save the SKU mapping to the file server: boom")

    monkeypatch.setattr(profile_manager, "update_sku_mapping", boom)
    pages.bridge.saveMappings()
    payload = pages.bridge.mapping
    assert payload["error"]["title"] == "Couldn’t save to the file server."
    assert payload["error"]["text"] == (
        "Your 1 change is still here and nothing on the server changed."
    )
    assert payload["error"]["cause"].endswith("boom")
    assert payload["error"]["path"].endswith("packer_config.json")
    assert payload["error"]["action"] == "save"
    assert payload["dirty"] is True and ("444", "SKU-D") in rows(pages)

    monkeypatch.undo()
    pages.bridge.saveMappings()  # Try again
    assert pages.bridge.mapping["error"] == {} and pages.bridge.mapping["saved"] is True


def test_reload_drops_the_edits_and_reads_fresh(pages, profile_manager, config_ini):
    pages.show_mapping("ACME", "Acme")
    pages.bridge.addMapping("444", "SKU-D")
    ProfileManager(config_path=str(config_ini)).update_sku_mapping("ACME", {"999": "SKU-Z"})
    pages.bridge.reloadMappings()
    assert rows(pages) == [("111", "SKU-A"), ("222", "SKU-B"), ("999", "SKU-Z")]
    assert pages.bridge.mapping["dirty"] is False


def test_a_load_that_fails_is_the_failed_shape_and_retry_recovers(
    pages, profile_manager, monkeypatch
):
    def boom(client_id, fresh=False):
        raise ProfileManagerError("Could not read the SKU mapping from the file server: boom")

    monkeypatch.setattr(profile_manager, "load_sku_mapping", boom)
    pages.show_mapping("ACME", "Acme")
    payload = pages.bridge.mapping
    assert payload["mode"] == "failed" and payload["rows"] == []
    assert payload["error"]["title"] == "Couldn’t load the mappings."
    assert payload["error"]["action"] == "load"

    monkeypatch.undo()
    pages.bridge.reloadMappings()
    assert pages.bridge.mapping["mode"] == "ready"
    assert rows(pages) == [("111", "SKU-A"), ("222", "SKU-B")]


def test_close_emits_back(pages, qtbot):
    pages.show_mapping("ACME", "Acme")
    with qtbot.waitSignal(pages.backRequested, timeout=1000):
        pages.bridge.closeMapping()


def test_ask_leave_reaches_the_page(pages, qtbot):
    with qtbot.waitSignal(pages.bridge.leaveAsked, timeout=1000):
        pages.ask_leave()


def test_a_stray_scan_is_passed_on(pages, qtbot):
    with qtbot.waitSignal(pages.strayScanned, timeout=1000) as caught:
        pages.bridge.strayScan("4006381333931")
    assert caught.args == ["4006381333931"]


def test_blank_empties_everything(pages):
    pages.show_mapping("ACME", "Acme")
    pages.bridge.addMapping("444", "SKU-D")
    pages.blank()
    assert pages.bridge.page == ""
    assert pages.bridge.mapping == {} and pages.bridge.workers == {}
    assert pages.dirty() is False


# --- the quick map (ADR 0004) --------------------------------------------------------


def test_a_quick_map_for_a_sku_writes_the_scanned_barcode_at_once(
    pages, profile_manager, qtbot
):
    pages.show_mapping("ACME", "Acme", quick_payload("sku", sku="SER-30ML"))
    assert pages.bridge.mapping["quick"]["kind"] == "sku"
    with qtbot.waitSignal(pages.quickMapped, timeout=1000) as caught:
        # Whatever is sent as the SKU is ignored: the SKU is fixed.
        assert pages.bridge.addMapping(" 5906 0001 ", "ignored") == ""
    expected = {"111": "SKU-A", "222": "SKU-B", "59060001": "SER-30ML"}
    assert caught.args == ["sku", "59060001", "SER-30ML", expected]
    assert profile_manager.load_sku_mapping("ACME", fresh=True) == expected
    assert pages.dirty() is False


def test_a_quick_map_for_a_barcode_takes_only_a_sku_on_the_order(
    pages, profile_manager, qtbot
):
    quick = quick_payload("barcode", barcode="5906", choices=CHOICES)
    pages.show_mapping("ACME", "Acme", quick)
    with qtbot.assertNotEmitted(pages.quickMapped):
        # A stray scan: a barcode typed into the SKU field.
        assert pages.bridge.addMapping("5906", "4006381333931") == (
            "Not on this order. Pick one of the lines below."
        )
    assert "5906" not in profile_manager.load_sku_mapping("ACME", fresh=True)

    with qtbot.waitSignal(pages.quickMapped, timeout=1000) as caught:
        # Typed loosely: saved with the order's own spelling.
        assert pages.bridge.addMapping("something else", "ser 30ml") == ""
    assert caught.args[:3] == ["barcode", "5906", "SER-30ML"]
    assert profile_manager.load_sku_mapping("ACME", fresh=True)["5906"] == "SER-30ML"


def test_a_quick_map_onto_a_mapped_barcode_needs_replace(pages, profile_manager, qtbot):
    pages.show_mapping("ACME", "Acme", quick_payload("sku", sku="SER-30ML"))
    with qtbot.assertNotEmitted(pages.quickMapped):
        assert pages.bridge.addMapping("111", "") == "This barcode already maps to SKU-A."
    with qtbot.waitSignal(pages.quickMapped, timeout=1000):
        assert pages.bridge.replaceMapping(0, "111", "") == ""
    assert profile_manager.load_sku_mapping("ACME", fresh=True)["111"] == "SER-30ML"


def test_a_quick_replace_of_a_barcode_spelled_differently_removes_the_old_spelling(
    pages, profile_manager
):
    profile_manager.update_sku_mapping("ACME", {"590-1": "OLD"})
    pages.show_mapping("ACME", "Acme", quick_payload("sku", sku="NEW"))
    assert pages.bridge.replaceMapping(0, "5901", "") == ""
    saved = profile_manager.load_sku_mapping("ACME", fresh=True)
    assert saved["5901"] == "NEW" and "590-1" not in saved


def test_a_quick_map_with_no_barcode_is_asked_for_one(pages):
    pages.show_mapping("ACME", "Acme", quick_payload("sku", sku="SER-30ML"))
    assert pages.bridge.addMapping("  ", "") == "Enter a barcode."


def test_a_quick_map_that_cannot_be_saved_says_so_and_stays(
    pages, profile_manager, monkeypatch, qtbot
):
    pages.show_mapping("ACME", "Acme", quick_payload("sku", sku="SER-30ML"))

    def boom(*args, **kwargs):
        raise ProfileManagerError("Could not save the SKU mapping to the file server: boom")

    monkeypatch.setattr(profile_manager, "update_sku_mapping", boom)
    with qtbot.assertNotEmitted(pages.quickMapped):
        assert pages.bridge.addMapping("5906", "") == "Not saved. Try again."
    error = pages.bridge.mapping["error"]
    assert error["title"] == "Couldn’t save to the file server." and error["action"] == ""
    assert pages.bridge.page == "mapping"


def test_retry_works_when_a_quick_map_could_not_load(pages, profile_manager, monkeypatch):
    def boom(client_id, fresh=False):
        raise ProfileManagerError("Could not read the SKU mapping from the file server: boom")

    monkeypatch.setattr(profile_manager, "load_sku_mapping", boom)
    pages.show_mapping("ACME", "Acme", quick_payload("sku", sku="SER-30ML"))
    assert pages.bridge.mapping["mode"] == "failed"

    monkeypatch.undo()
    pages.bridge.reloadMappings()  # the banner's Retry
    assert pages.bridge.mapping["mode"] == "ready"
    assert pages.bridge.mapping["quick"]["kind"] == "sku"
    assert rows(pages) == [("111", "SKU-A"), ("222", "SKU-B")]

    # Once loaded, a quick map reloads nothing.
    monkeypatch.setattr(profile_manager, "load_sku_mapping", boom)
    pages.bridge.reloadMappings()
    assert pages.bridge.mapping["mode"] == "ready"


def test_the_banner_names_the_cause_underneath_not_the_title_again(
    pages, profile_manager, monkeypatch
):
    pages.show_mapping("ACME", "Acme")
    pages.bridge.addMapping("444", "SKU-D")

    def boom(*args, **kwargs):
        try:
            raise OSError("The network path was not found")
        except OSError as error:
            raise ProfileManagerError(
                f"Could not save the SKU mapping to the file server: {error}"
            ) from error

    monkeypatch.setattr(profile_manager, "update_sku_mapping", boom)
    pages.bridge.saveMappings()
    assert pages.bridge.mapping["error"]["cause"] == "The network path was not found"


def test_a_quick_map_does_nothing_else(pages, profile_manager, monkeypatch):
    pages.show_mapping("ACME", "Acme", quick_payload("sku", sku="SER-30ML"))
    before = rows(pages)
    calls = []
    monkeypatch.setattr(profile_manager, "update_sku_mapping", lambda *a, **k: calls.append(a))
    assert pages.bridge.updateMapping(row_id(pages, "111"), "111", "X") == ""
    pages.bridge.deleteMapping(row_id(pages, "111"))
    pages.bridge.saveMappings()
    assert rows(pages) == before and calls == []
