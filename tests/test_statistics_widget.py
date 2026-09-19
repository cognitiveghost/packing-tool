"""The Statistics screen draws what session_stats computes -- and nothing else.

The point of the split is that the arithmetic is tested in
tests/test_session_stats.py without a window. What is tested here is only that
the screen shows what it is given, and shows a state panel when it is given
nothing.
"""

import pandas as pd
import pytest

from gui.statistics_widget import StatisticsWidget


@pytest.fixture
def screen(qtbot):
    widget = StatisticsWidget()
    qtbot.addWidget(widget)
    return widget


def _df():
    return pd.DataFrame(
        [
            {
                "Order_Number": "#1",
                "SKU": "A-1",
                "Product_Name": "Mouse",
                "Quantity": 2,
                "Courier": "DPD",
            },
            {
                "Order_Number": "#2",
                "SKU": "B-2",
                "Product_Name": "Cable",
                "Quantity": 1,
                "Courier": "GLS",
            },
        ]
    )


def test_the_totals_row_shows_the_computed_numbers(screen):
    screen.update_from(_df(), {"completed_orders": ["#1"]})
    assert screen.cards["orders"].value_label.text() == "2"
    assert screen.cards["completed"].value_label.text() == "1"
    assert screen.cards["progress_pct"].value_label.text() == "50%"


def test_one_courier_card_per_courier(screen):
    screen.update_from(_df(), {})
    assert screen.courier_layout.count() == 2


def test_courier_cards_are_replaced_on_refresh_not_appended(screen):
    screen.update_from(_df(), {})
    screen.update_from(_df(), {})
    assert screen.courier_layout.count() == 2


def test_the_sku_table_has_one_row_per_sku(screen):
    screen.update_from(_df(), {})
    assert screen.sku_table.rowCount() == 2


def test_with_no_packing_list_the_screen_shows_its_state_panel(screen):
    # isHidden(), not isVisible(): the widget is never shown in this test (see
    # test_command_bar.py's note), so isVisible() is False for everything.
    screen.show_empty()
    assert not screen.state_panel.isHidden()
    assert screen.content.isHidden()


def test_loading_a_list_replaces_the_state_panel_with_the_content(screen):
    screen.show_empty()
    screen.update_from(_df(), {})
    assert not screen.content.isHidden()
    assert screen.state_panel.isHidden()
