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


def test_each_page_shows_only_its_own_status_bar_sentence(main_window):
    """One label held both the order summary and the session count; whichever
    screen spoke last won, so Packing could read "7 of 7 sessions"."""
    from gui.main_window import PAGE_BROWSER, PAGE_PACKING

    main_window.session_tabs.setCurrentIndex(PAGE_BROWSER)
    assert not main_window.sb_browser_label.isHidden()
    assert main_window.sb_summary_label.isHidden()

    main_window.session_tabs.setCurrentIndex(PAGE_PACKING)
    assert not main_window.sb_summary_label.isHidden()
    assert main_window.sb_browser_label.isHidden()
