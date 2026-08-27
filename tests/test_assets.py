"""The bundled asset pipeline: a glyph renders, and Inter registers."""
from gui.fonts import load_bundled_fonts
from gui.icons import icon


def test_icon_renders_a_pixmap(qapp):
    pixmap = icon("package").pixmap(16, 16)
    assert not pixmap.isNull()
    assert pixmap.width() == 16


def test_unknown_icon_name_raises(qapp):
    import pytest
    with pytest.raises(KeyError):
        icon("no-such-glyph")


def test_bundled_font_registers(qapp):
    assert load_bundled_fonts() == "Inter"
