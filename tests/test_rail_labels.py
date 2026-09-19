"""The rail's labels fit its 56px item.

'Statistics' measures ~72px at 10pt against 56px available and has no wrap
point, so the rail says 'Stats'. The tab, the page title and the tooltip keep
the full word.
"""

from gui.main_window import RAIL_ITEMS


def test_no_rail_label_is_longer_than_the_item_can_hold():
    for _icon, label, _tip in RAIL_ITEMS:
        assert len(label) <= 8, f"{label!r} will not fit the 56px rail item"


def test_the_statistics_item_reads_stats():
    assert [label for _i, label, _t in RAIL_ITEMS] == ["Packing", "Stats", "Browse"]


def test_the_tooltip_still_gives_the_full_name():
    tips = {label: tip for _i, label, tip in RAIL_ITEMS}
    assert tips["Stats"].startswith("Statistics")
