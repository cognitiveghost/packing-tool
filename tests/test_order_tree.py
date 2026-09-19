"""T1's order rows: a chip in the Status column, and the 40px floor rung."""

from gui.main_window import ORDER_STATUS_CHIP


def test_the_three_order_states_each_have_a_chip():
    assert set(ORDER_STATUS_CHIP) == {"in_progress", "packed", "not_started"}


def test_an_order_being_packed_is_live_and_packer_driven():
    role, text, live, manual = ORDER_STATUS_CHIP["in_progress"]
    assert (text, live, manual) == ("In progress", True, True)


def test_a_finished_order_is_neither_live_nor_packer_declared():
    role, text, live, manual = ORDER_STATUS_CHIP["packed"]
    assert (text, live, manual) == ("Packed", False, False)
