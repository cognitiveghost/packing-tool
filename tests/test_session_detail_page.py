"""Session detail is a page, not a modal.

B2 draws the same rail, command bar and status bar as the list, with the page
area swapped -- so it is a page in a stack, and the modal QDialog goes.
"""

import pytest

from gui.session_browser.session_detail_page import SessionDetailPage


@pytest.fixture
def session():
    return {
        "session_id": "2026-09-02_0810",
        "status": "in_progress",
        "client_id": "kaufland-de",
        "worker": "W-004",
        "pc": "WH-PC-02",
    }


def test_the_header_names_the_session_and_shows_its_status(qtbot, session):
    page = SessionDetailPage(session)
    qtbot.addWidget(page)
    assert "2026-09-02_0810" in page.title_label.text()
    assert page.status_chip.text() == "Active"


def test_the_page_carries_the_three_tabs_the_dialog_had(qtbot, session):
    page = SessionDetailPage(session)
    qtbot.addWidget(page)
    assert [page.tabs.tabText(i) for i in range(page.tabs.count())] == [
        "Overview",
        "Orders",
        "Metrics",
    ]


def test_back_asks_the_browser_to_return_to_the_list(qtbot, session):
    page = SessionDetailPage(session)
    qtbot.addWidget(page)
    with qtbot.waitSignal(page.back_requested):
        page.back_button.click()


def test_selecting_a_session_shows_the_detail_page_and_back_returns(qtbot, session):
    from gui.session_browser.session_browser_widget import SessionBrowserWidget

    browser = SessionBrowserWidget(
        profile_manager=None,
        session_lock_manager=None,
        session_history_manager=None,
        worker_manager=None,
        registry_manager=None,
    )
    qtbot.addWidget(browser)

    browser.show_detail(session)
    assert browser.stack.currentWidget() is browser.detail_page

    browser.detail_page.back_requested.emit()
    assert browser.stack.currentWidget() is browser.sessions_list


def test_a_registry_entry_loads_its_details_from_disk(qtbot, tmp_path):
    """The list's own payload must reach the file-reading loader.

    The payload is built by the production call site, not typed out here --
    a hand-copied dict cannot catch the regression this test exists for,
    which was a *new key* in that payload rerouting the page into the
    pre-built-totals loader and rendering the session as Unknown / 0.
    """
    import json

    from gui.session_browser.sessions_list_widget import SessionsListWidget

    work_dir = tmp_path / "2026-09-02_0810" / "work"
    work_dir.mkdir(parents=True)
    (work_dir / "session_summary.json").write_text(
        json.dumps(
            {
                "session_id": "2026-09-02_0810",
                "worker_name": "W-004",
                "pc_name": "WH-PC-02",
                "total_orders": 14,
                "completed_orders": 9,
                "total_items": 62,
            }
        ),
        encoding="utf-8",
    )

    widget = SessionsListWidget(registry_manager=None, session_history_manager=None)
    qtbot.addWidget(widget)
    widget._client_id = "kaufland-de"

    payloads = []
    widget.session_details_requested.connect(payloads.append)
    widget._open_details_for_entry(
        {
            "session_id": "2026-09-02_0810",
            "status": "in_progress",
            "work_dir": str(work_dir),
            "packing_list_name": "weigh-2026-09-02",
        }
    )

    page = SessionDetailPage(payloads[0])
    qtbot.addWidget(page)
    record = page.details["record"]
    assert record["worker_name"] == "W-004"
    assert record["pc_name"] == "WH-PC-02"
    assert (record["completed_orders"], record["total_orders"]) == (9, 14)
    assert record["total_items_packed"] == 62
