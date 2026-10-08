"""AppPages: one web view for Packing and Statistics, the Qt Sessions page beside it."""

import pytest
from PySide6.QtWidgets import QLabel

from gui.app_pages import PAGE_BROWSER, PAGE_PACKING, PAGE_STATISTICS, AppPages


@pytest.fixture
def pages(qtbot):
    browser = QLabel("sessions")
    widget = AppPages(browser)
    qtbot.addWidget(widget)
    return widget


def test_it_has_three_pages_and_starts_on_packing(pages):
    assert pages.count() == 3
    assert pages.currentIndex() == PAGE_PACKING
    assert pages.bridge.page == "packing"
    assert pages.web_is_current()


def test_statistics_is_the_same_view_with_another_page(pages):
    seen = []
    pages.currentChanged.connect(seen.append)
    pages.setCurrentIndex(PAGE_STATISTICS)
    assert seen == [PAGE_STATISTICS]
    assert pages.bridge.page == "statistics"
    assert pages.web_is_current()
    assert pages.widget(PAGE_PACKING) is pages.widget(PAGE_STATISTICS) is pages.view


def test_sessions_is_the_browser_and_leaves_the_page_name_alone(pages):
    pages.setCurrentIndex(PAGE_STATISTICS)
    pages.setCurrentIndex(PAGE_BROWSER)
    assert pages.currentIndex() == PAGE_BROWSER
    assert not pages.web_is_current()
    assert pages.widget(PAGE_BROWSER) is pages.browser
    assert pages.bridge.page == "statistics"
    pages.setCurrentIndex(PAGE_PACKING)
    assert pages.web_is_current() and pages.bridge.page == "packing"


def test_setting_the_current_index_again_says_nothing(pages):
    seen = []
    pages.currentChanged.connect(seen.append)
    pages.setCurrentIndex(PAGE_PACKING)
    pages.setCurrentIndex(7)
    assert seen == []
    assert pages.currentIndex() == PAGE_PACKING
