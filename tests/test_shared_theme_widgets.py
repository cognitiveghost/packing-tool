"""StatusDot / StatusChip resolve tokens by name, never by hex string."""
import pytest

from shared.theme import DARK_THEME, LIGHT_THEME, StatusDot


def test_status_dot_resolves_role_from_tokens(qapp):
    dot = StatusDot("status_success", DARK_THEME)
    assert dot.color().name().upper() == DARK_THEME.status_success.upper()
    assert dot.width() == 10 and dot.height() == 10


def test_status_dot_accepts_any_token_field_not_only_status_roles(qapp):
    # STATUS_CONFIG maps "not_started" to text_secondary, which is not a status role.
    dot = StatusDot("text_secondary", DARK_THEME)
    assert dot.color().name().upper() == DARK_THEME.text_secondary.upper()


def test_status_dot_rejects_a_typo_at_construction(qapp):
    with pytest.raises(AttributeError):
        StatusDot("status_sucess", DARK_THEME)


def test_status_dot_set_role_reresolves_against_the_given_theme(qapp):
    dot = StatusDot("status_danger", DARK_THEME)
    dot.set_role("status_danger", LIGHT_THEME)
    assert dot.color().name().upper() == LIGHT_THEME.status_danger.upper()


def test_status_dot_no_longer_accepts_a_hex_string(qapp):
    with pytest.raises(AttributeError):
        StatusDot("#FF0000", DARK_THEME)
