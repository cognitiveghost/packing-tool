"""T2: no packing list means a state panel, not an empty grid."""


def test_with_no_list_loaded_the_packing_tab_shows_its_state_panel(main_window):
    assert not main_window.packing_state_panel.isHidden()
    assert main_window.order_tree_card.isHidden()


def test_loading_a_list_puts_the_tree_back(main_window_with_list):
    assert not main_window_with_list.order_tree_card.isHidden()
    assert main_window_with_list.packing_state_panel.isHidden()
