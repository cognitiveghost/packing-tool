"""The four-role button hierarchy lives in shared/, so both apps get one copy."""
import pytest
from PySide6.QtWidgets import QPushButton

from shared.theme import (
    BUTTON_ROLES,
    DARK_THEME,
    LIGHT_THEME,
    build_stylesheet,
    set_button_role,
)


def test_the_four_roles_are_the_contract():
    assert BUTTON_ROLES == ("primary", "secondary", "ghost", "danger")


@pytest.mark.parametrize("theme", [DARK_THEME, LIGHT_THEME])
@pytest.mark.parametrize("role", ["primary", "secondary", "ghost", "danger"])
def test_build_stylesheet_emits_every_role_block(theme, role):
    assert f'QPushButton[role="{role}"]' in build_stylesheet(theme)


def test_the_unmarked_button_rule_is_untouched():
    # 112 shopify + 35 packing-tool buttons rely on the default staying accent-filled.
    sheet = build_stylesheet(DARK_THEME)
    plain = sheet.split('QPushButton[role=')[0]
    assert DARK_THEME.accent_fill in plain


def test_danger_is_an_outline_not_a_fill():
    sheet = build_stylesheet(DARK_THEME)
    block = sheet.split('QPushButton[role="danger"] {')[1].split('}')[0]
    assert "transparent" in block
    assert DARK_THEME.status_danger in block


def test_ghost_has_no_border():
    sheet = build_stylesheet(DARK_THEME)
    block = sheet.split('QPushButton[role="ghost"] {')[1].split('}')[0]
    assert "border: none" in block


def test_set_button_role_marks_the_widget(qapp):
    button = QPushButton("Start Packing")
    set_button_role(button, "primary")
    assert button.property("role") == "primary"


def test_set_button_role_rejects_an_unknown_role(qapp):
    button = QPushButton("Cancel")
    with pytest.raises(ValueError):
        set_button_role(button, "tertiary")
