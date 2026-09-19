"""T1's order rows: a chip in the Status column, and the 40px floor rung."""

from gui.main_window import ORDER_STATUS_CHIP


def test_the_three_order_states_each_have_a_chip():
    assert set(ORDER_STATUS_CHIP) == {"in_progress", "packed", "not_started"}


def test_an_order_being_packed_is_live_but_not_packer_declared():
    """T1 draws it chip--warning chip--tint chip--hollow: tinted, no mark.

    The mark means a packer declared the state; in-progress is the system's
    reading of the list. STATUS_CONFIG["in_progress"] in the session browser
    says the same, and one state must not render two ways on two screens.
    """
    _role, text, live, manual = ORDER_STATUS_CHIP["in_progress"]
    assert (text, live, manual) == ("In progress", True, False)

    from gui.session_browser.sessions_list_widget import STATUS_CONFIG

    assert STATUS_CONFIG["in_progress"]["manual"] is manual


def test_a_finished_order_is_neither_live_nor_packer_declared():
    _role, text, live, manual = ORDER_STATUS_CHIP["packed"]
    assert (text, live, manual) == ("Packed", False, False)
