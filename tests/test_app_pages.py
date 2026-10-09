"""AppPages: one web view for every page of the shell (ADR 0003)."""

import pytest

from gui.app_pages import PAGE_BROWSER, PAGE_PACKING, PAGE_STATISTICS, AppPages


@pytest.fixture
def pages(qtbot):
    widget = AppPages()
    qtbot.addWidget(widget)
    return widget


def test_it_has_three_pages_and_starts_on_packing(pages):
    assert pages.count() == 3
    assert pages.currentIndex() == PAGE_PACKING
    assert pages.bridge.page == "packing"


def test_every_index_is_the_same_view(pages):
    for index in (PAGE_PACKING, PAGE_STATISTICS, PAGE_BROWSER):
        assert pages.widget(index) is pages.view
    assert not hasattr(pages, "web_is_current")
    assert not hasattr(pages, "browser")


def test_statistics_is_another_page_of_the_document(pages):
    seen = []
    pages.currentChanged.connect(seen.append)
    pages.setCurrentIndex(PAGE_STATISTICS)
    assert seen == [PAGE_STATISTICS]
    assert pages.bridge.page == "statistics"


def test_sessions_is_a_page_of_the_document(pages):
    seen = []
    pages.currentChanged.connect(seen.append)
    pages.setCurrentIndex(PAGE_BROWSER)
    assert seen == [PAGE_BROWSER]
    assert pages.currentIndex() == PAGE_BROWSER
    assert pages.bridge.page == "sessions"
    pages.setCurrentIndex(PAGE_PACKING)
    assert pages.bridge.page == "packing"


def test_sessions_returns_to_the_details_that_were_open(pages):
    pages.setCurrentIndex(PAGE_BROWSER)
    pages.bridge.set_details({"state": "ready"})
    pages.bridge.set_page("details")
    pages.setCurrentIndex(PAGE_PACKING)
    assert pages.bridge.page == "packing"
    pages.setCurrentIndex(PAGE_BROWSER)
    assert pages.bridge.page == "details"

    pages.setCurrentIndex(PAGE_PACKING)
    pages.bridge.set_details({})
    pages.setCurrentIndex(PAGE_BROWSER)
    assert pages.bridge.page == "sessions"


def test_setting_the_current_index_again_says_nothing(pages):
    seen = []
    pages.currentChanged.connect(seen.append)
    pages.setCurrentIndex(PAGE_PACKING)
    pages.setCurrentIndex(7)
    assert seen == []
    assert pages.currentIndex() == PAGE_PACKING
