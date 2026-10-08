"""T2: no packing list means a state panel, not an empty grid."""


def test_with_no_list_loaded_the_packing_tab_shows_its_state_panel(main_window):
    assert not main_window.packing_state_panel.isHidden()
    assert main_window.order_tree_card.isHidden()


def test_loading_a_list_puts_the_tree_back(main_window_with_list):
    assert not main_window_with_list.order_tree_card.isHidden()
    assert main_window_with_list.packing_state_panel.isHidden()


def test_the_panel_says_what_t2_says_and_its_button_opens_the_browser(main_window):
    """T2's copy, and a button that goes where its label says."""
    panel = main_window.packing_state_panel
    assert panel.button is not None
    panel.button.click()
    from gui.main_window import PAGE_BROWSER

    assert main_window.session_tabs.currentIndex() == PAGE_BROWSER


def test_the_order_summary_sits_above_the_tree(main_window_with_list):
    """The status bar's sentence, on its own page until phase 3's totals strip."""
    window = main_window_with_list
    assert window.packing_summary_label.text() == "2 orders · 0 packed · 0 in progress"
    assert not window.packing_summary_label.isHidden()


def test_no_list_means_no_summary_line(main_window):
    assert main_window.packing_summary_label.isHidden()


def test_the_session_count_sits_in_the_sessions_top_row(main_window):
    browser = main_window.session_browser
    browser.sessions_shown.emit(12, 40)
    assert browser.count_label.text() == "12 of 40 sessions"
