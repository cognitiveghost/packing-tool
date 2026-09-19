"""An empty screen says which kind of empty it is.

No sessions at all and no sessions matching the filters are different
problems, and the second one has an obvious next action.
"""

import pytest

from gui.session_browser.sessions_list_widget import SessionsListWidget


@pytest.fixture
def widget(qtbot):
    w = SessionsListWidget(registry_manager=None, session_history_manager=None)
    qtbot.addWidget(w)
    return w


def test_a_client_with_no_sessions_shows_the_empty_panel(widget):
    # isHidden(), not isVisible(): the widget is never shown in this test
    # (see test_command_bar.py's note), so isVisible() is False for everything.
    widget.show_entries([])
    assert not widget.state_panel.isHidden()
    assert widget.card.isHidden()


def test_filters_that_match_nothing_say_so_rather_than_showing_a_blank_table(widget):
    widget.show_entries([{"session_id": "2026-09-02_0810", "status": "completed"}])
    widget._search_input.setText("no such session")
    assert not widget.state_panel.isHidden()


def test_clearing_the_filter_brings_the_table_back(widget):
    widget.show_entries([{"session_id": "2026-09-02_0810", "status": "completed"}])
    widget._search_input.setText("no such session")
    widget._search_input.setText("")
    assert not widget.card.isHidden()
    assert widget.state_panel.isHidden()


def test_the_widget_reports_how_many_rows_it_is_showing(widget, qtbot):
    with qtbot.waitSignal(widget.sessions_shown) as caught:
        widget.show_entries(
            [
                {"session_id": "a", "status": "completed"},
                {"session_id": "b", "status": "completed"},
            ]
        )
    assert caught.args == [2, 2]
