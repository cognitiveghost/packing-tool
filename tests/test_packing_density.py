"""Packing Tool is a scan station: floor density, not Shopify's desk default."""

from gui import theme as packing_theme
from shared import theme as shared_theme


class _MemorySettings:
    def __init__(self, *_args):
        pass

    def value(self, _key, default=None):
        return default

    def setValue(self, _key, _value):
        pass


def test_loading_the_theme_switches_to_floor_density(qapp, monkeypatch):
    monkeypatch.setattr(packing_theme, "QSettings", _MemorySettings)
    before = shared_theme.get_density()
    sheet = qapp.styleSheet()
    shared_theme.set_density("desk")
    try:
        packing_theme.load_saved_theme(qapp)
        assert shared_theme.get_density() == "floor"
    finally:
        shared_theme.set_density(before)
        qapp.setStyleSheet(sheet)


def test_both_bars_share_one_definition_of_the_bar(qapp):
    from gui.command_bar import bar_css
    from gui.theme import current_tokens

    tokens = current_tokens()
    assert "PackerBar" in bar_css(tokens, "QWidget#PackerBar")
    assert bar_css(tokens).startswith("CommandBar {")
