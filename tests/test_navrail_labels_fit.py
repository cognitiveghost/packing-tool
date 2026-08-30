"""The rail is 76px wide, so its labels have to actually fit in 76px.

shopify-fulfillment-tool shipped five tab titles verbatim onto a 56px rail and
Qt elided every one of them. packing-tool's labels are longer still --
"Statistics" needs 59px at floor density -- which is why this rail is 76 and
not 56. A middle-elided label is worse than no label.
"""
import pytest
from PySide6.QtGui import QFontMetrics

from gui.main_window import RAIL_ITEMS, RAIL_WIDTH

# QToolButton keeps a few px of padding either side of the label.
TEXT_BUDGET = RAIL_WIDTH - 8

# The "Sans Serif" alias resolves to whatever font is installed on the box
# running the test, so measuring it made the result depend on which fonts a
# given Linux machine happens to have. Pin a widely-available font, and add
# headroom since it is still a Linux proxy for the Inter/Segoe UI the
# production Windows build resolves.
MEASURING_FONT = "DejaVu Sans"
HEADROOM = 0.05

# Both rungs, not just the live one: 8.9 moves packing-tool to floor density,
# and the rail must not need a second widening when it does.
# shared.theme.TYPE_SCALE["caption"] is 9pt at desk, 10pt at floor.
CAPTION_SIZES = (9, 10)


@pytest.mark.parametrize("size_pt", CAPTION_SIZES)
@pytest.mark.parametrize("label", [label for _icon, label, _tip in RAIL_ITEMS])
def test_every_rail_label_fits_without_eliding(qapp, label, size_pt):
    from PySide6.QtGui import QFont

    font = QFont(MEASURING_FONT, size_pt)
    width = QFontMetrics(font).horizontalAdvance(label)
    assert width <= TEXT_BUDGET * (1 - HEADROOM), (
        f"{label!r} is {width}px at {size_pt}pt; the {RAIL_WIDTH}px rail gives "
        f"it {TEXT_BUDGET}px and Qt will elide it to a '...' form"
    )


def test_every_tooltip_leads_with_the_destinations_full_name():
    """"Browse" is short because the rail is narrow, so the tooltip is the
    only place Session Browser's full name still appears."""
    full_names = ("Packing", "Statistics", "Session Browser")
    for (_icon_name, _label, tip), full_name in zip(RAIL_ITEMS, full_names, strict=True):
        assert tip.startswith(f"{full_name} — "), (
            f"{tip!r} should lead with {full_name!r}"
        )
