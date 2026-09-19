"""T1's order filter, already wired as CommandBar.filter_input / MainWindow._filter_orders.

An order matches on its own number or on any of its SKUs or product names, so
typing a SKU finds the order that contains it -- which is how a packer looks
for one. The plan for this task guessed the names `order_filter` /
`_filter_order_tree`; the feature already existed under `filter_input` /
`_filter_orders` (wired in `_init_ui`), so this task is the regression test
that locks the existing behaviour in, not a new field.
"""


def test_typing_an_order_number_hides_the_other_orders(main_window_with_list):
    window = main_window_with_list
    window.command_bar.filter_input.setText("10429")

    visible = [
        window.order_tree.topLevelItem(i).text(0)
        for i in range(window.order_tree.topLevelItemCount())
        if not window.order_tree.topLevelItem(i).isHidden()
    ]
    assert visible == ["#10429"]


def test_typing_a_sku_finds_the_order_that_contains_it(main_window_with_list):
    window = main_window_with_list
    window.command_bar.filter_input.setText("TS-4409-B")

    visible = [
        window.order_tree.topLevelItem(i)
        for i in range(window.order_tree.topLevelItemCount())
        if not window.order_tree.topLevelItem(i).isHidden()
    ]
    assert len(visible) == 1


def test_clearing_the_filter_brings_every_order_back(main_window_with_list):
    window = main_window_with_list
    window.command_bar.filter_input.setText("10429")
    window.command_bar.filter_input.setText("")

    hidden = [
        i
        for i in range(window.order_tree.topLevelItemCount())
        if window.order_tree.topLevelItem(i).isHidden()
    ]
    assert hidden == []
