"""The order marker is added once, never twice.

Real order numbers already carry a '#' (see test_session_metadata_orders.py),
so a display site that prepends one unconditionally renders '##11019512'.
"""

from gui.packer_bridge import order_label


def test_a_number_that_already_has_a_hash_keeps_exactly_one():
    assert order_label("#11019512") == "#11019512"


def test_a_bare_number_gets_the_marker():
    assert order_label("11019512") == "#11019512"


def test_no_order_renders_as_no_order():
    assert order_label("") == "No order"
    assert order_label(None) == "No order"
