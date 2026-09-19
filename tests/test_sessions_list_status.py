"""F5's three channels, one table.

colour = the role; live = the session can still be worked; manual = a person
decided this, rather than the system inferring it.
"""

from gui.session_browser.sessions_list_widget import STATUS_CONFIG


def test_every_status_declares_all_three_channels():
    for key, cfg in STATUS_CONFIG.items():
        assert "role" in cfg and "live" in cfg and "manual" in cfg, key


def test_only_the_two_states_a_packer_declares_carry_the_solid_mark():
    manual = {k for k, cfg in STATUS_CONFIG.items() if cfg["manual"]}
    assert manual == {"paused", "incomplete"}


def test_tint_marks_the_sessions_that_can_still_be_worked():
    live = {k for k, cfg in STATUS_CONFIG.items() if cfg["live"]}
    assert live == {"in_progress", "paused", "stale", "incomplete"}


def test_an_unknown_status_still_renders_a_cell(qtbot):
    from gui.session_browser.sessions_list_widget import SessionsListWidget

    widget = SessionsListWidget(registry_manager=None, session_history_manager=None)
    qtbot.addWidget(widget)
    cell = widget._make_status_cell("something_new")
    assert cell is not None
