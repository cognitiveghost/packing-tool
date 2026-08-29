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


def test_the_unmarked_button_rule_is_secondary():
    # 2026-08-29: the default flipped from accent-filled to secondary -- primary
    # is now something a screen declares, not what every unmarked button gets.
    sheet = build_stylesheet(DARK_THEME)
    plain = sheet.split('QPushButton[role=')[0]
    assert DARK_THEME.accent_fill not in plain


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


def _default_button_block(sheet: str) -> str:
    """The body of the bare `QPushButton {` rule.

    `QPushButton[role="primary"] {` and `QPushButton:hover {` do not match the
    split token, so this finds the unqualified selector and only that one.
    """
    return sheet.split("QPushButton {", 1)[1].split("}", 1)[0]


def test_an_unmarked_button_is_not_primary():
    """The whole point: primary is declared, never defaulted into."""
    for theme in (DARK_THEME, LIGHT_THEME):
        block = _default_button_block(build_stylesheet(theme))
        assert theme.surface_raised in block
        assert theme.accent_fill not in block


def test_marking_a_button_primary_still_fills_it_with_the_accent():
    for theme in (DARK_THEME, LIGHT_THEME):
        sheet = build_stylesheet(theme)
        primary = sheet.split('QPushButton[role="primary"] {', 1)[1].split("}", 1)[0]
        assert theme.accent_fill in primary
