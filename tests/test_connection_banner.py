"""The page banner an outage raises (spec 2026-10-08 section 6.5, frame 2e)."""

import pytest

from gui.components.connection_banner import ConnectionBanner
from shared import theme as shared_theme
from shared.theme import current_theme_name, current_tokens, set_current


@pytest.fixture
def banner(qapp):
    widget = ConnectionBanner()
    yield widget
    widget.deleteLater()


def test_it_says_which_server_since_when_and_what_is_blocked(banner):
    banner.set_outage(r"\\fs01\packer", "14:02")
    assert banner.title_label.text() == "Server unreachable"
    text = banner.message_label.text()
    assert r"\\fs01\packer" in text
    assert "stopped answering at" in text and "14:02" in text
    assert "Sessions cannot be opened or ended until it answers." in text


def test_a_path_with_markup_characters_is_shown_literally(banner):
    banner.set_outage(r"\\fs01\<share>&co", "09:00")
    assert "&lt;share&gt;&amp;co" in banner.message_label.text()


def test_retry_emits(banner, qtbot):
    with qtbot.waitSignal(banner.retryRequested, timeout=500):
        banner.retry_button.click()
    assert banner.retry_button.text() == "Retry"
    assert banner.retry_button.height() == 44


def test_it_wears_the_danger_plane_in_both_themes(banner):
    before = current_theme_name()
    set_current("dark" if before == "light" else "light")
    try:
        tokens = current_tokens()
        assert tokens.status_danger_bg in banner.styleSheet()
        assert tokens.status_danger_border in banner.styleSheet()
    finally:
        shared_theme._current = before
