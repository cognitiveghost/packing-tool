"""shared.theme is where the live theme lives, and where a change is announced.

Before 8.6 each app tracked the applied theme privately and neither emitted
anything, so a shared widget could not restyle itself on a toggle. NavRail is
the first widget that has to.
"""
import pytest

import shared.theme as theme_module
from shared.theme import (
    THEME_DARK,
    THEME_LIGHT,
    current_theme_name,
    current_tokens,
    get_theme,
    set_current,
    theme_notifier,
)


@pytest.fixture
def emissions():
    """Record every `changed` emission for the duration of one test.

    shared.theme's module state is process-global, so the fixture also
    restores whatever theme was live when the test started -- otherwise the
    first test to switch to light leaves every later test in light. That
    "before" state can itself be None (no app has applied a theme yet in
    this process), which set_current() cannot express -- so restore it by
    writing the module global directly rather than skipping the restore.
    """
    seen = []
    theme_notifier.changed.connect(seen.append)
    before = current_theme_name()
    yield seen
    theme_notifier.changed.disconnect(seen.append)
    if before is not None:
        set_current(before)
    else:
        theme_module._current = None


def test_set_current_announces_a_real_change(emissions):
    set_current(THEME_LIGHT)
    assert emissions == [THEME_LIGHT]


def test_reapplying_the_same_theme_announces_nothing(emissions):
    set_current(THEME_LIGHT)
    set_current(THEME_LIGHT)
    set_current(THEME_LIGHT)
    assert emissions == [THEME_LIGHT]


def test_current_tokens_follow_the_live_theme(emissions):
    set_current(THEME_LIGHT)
    assert current_tokens() == get_theme(THEME_LIGHT)
    set_current(THEME_DARK)
    assert current_tokens() == get_theme(THEME_DARK)


def test_gui_theme_apply_routes_through_shared(qapp, emissions):
    """packing-tool's own apply path is the write path -- not a second one."""
    from gui.theme import apply_theme

    apply_theme(qapp, THEME_LIGHT)
    assert current_theme_name() == THEME_LIGHT
    assert emissions == [THEME_LIGHT]
