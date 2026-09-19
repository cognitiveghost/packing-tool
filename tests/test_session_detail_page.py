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
    assert browser.stack.currentWidget() is browser.list_page
