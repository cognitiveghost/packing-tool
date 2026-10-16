"""The app's language is read at startup and shown in the sidebar (ADR 0021, ADR 0022)."""

from PySide6.QtCore import QSettings

import main
from shared import i18n, relaunch, update_flow
from shared.theme import current_tokens


def test_saved_language_is_applied():
    QSettings("PackingTool", "Language").setValue("language", "bg")
    assert main.apply_saved_language() == "bg"
    assert i18n._("Restart now") == "Рестартирай сега"


def test_default_is_english():
    QSettings("PackingTool", "Language").remove("language")
    assert main.apply_saved_language() == "en"


def _sidebar(qtbot):
    from gui.components.sidebar import Sidebar

    bar = Sidebar()
    qtbot.addWidget(bar)
    bar.show()
    return bar


def test_sidebar_mark_is_the_packer_assistant_glyph(qtbot, monkeypatch):
    from gui.components import sidebar as sidebar_module

    real_icon = sidebar_module.icon
    requested = []

    def recorder(name, **kwargs):
        requested.append(name)
        return real_icon(name, **kwargs)

    monkeypatch.setattr(sidebar_module, "icon", recorder)
    bar = _sidebar(qtbot)
    requested.clear()
    bar._apply_theme(current_tokens())
    assert "scan-barcode" in requested
    assert "package" not in requested


def test_sidebar_language_segment_shows_the_saved_choice_and_forwards_clicks(qtbot):
    bar = _sidebar(qtbot)
    assert bar.language_segment.buttons["en"].isChecked()
    with qtbot.waitSignal(bar.languageRequested) as blocker:
        bar.language_segment.buttons["bg"].click()
    assert blocker.args == ["bg"]


def test_sidebar_update_button_is_hidden_until_there_is_an_update(qtbot):
    bar = _sidebar(qtbot)
    assert bar.update_button.objectName() == "UpdateButton"
    assert bar.update_button.isHidden()


def test_collapsed_sidebar_hides_the_language_segment(qtbot):
    bar = _sidebar(qtbot)
    bar.set_expanded(False)
    assert bar.language_segment.isHidden()
    bar.set_expanded(True)
    assert not bar.language_segment.isHidden()


def test_main_window_has_an_update_flow_and_an_overflow_item(main_window):
    assert main_window.update_flow is not None
    texts = [action.text() for action in main_window.command_bar.overflow.actions()]
    assert "Check for updates…" in texts


def test_a_vetoed_language_restart_is_cancelled(main_window, monkeypatch):
    started = []
    monkeypatch.setattr(relaunch, "_start", lambda argv, update: started.append(argv))
    monkeypatch.setattr(update_flow, "ask", lambda *args, **kwargs: True)
    # A start in progress makes closeEvent ignore the close: the veto.
    main_window._starting = True
    try:
        main_window.sidebar.languageRequested.emit("bg")
    finally:
        main_window._starting = False
        QSettings("PackingTool", "Language").remove("language")
    assert relaunch.pending() is None  # cancelled: a later close must not restart
    assert started == []


def test_a_long_bulgarian_connection_state_is_elided_inside_the_card(qtbot):
    from PySide6.QtGui import QFontMetrics

    from gui.components.sidebar import _PATH_WIDTH

    i18n.set_language("bg", i18n.catalogue_files(main.APP_ROOT, "bg"))
    bar = _sidebar(qtbot)
    bar.set_connection("down", r"\\fs01\packer")
    bar.connection_label.ensurePolished()
    # The full state stays one hover away on the card.
    assert "Няма връзка със сървъра" in bar.connection_box.toolTip()
    assert QFontMetrics(bar.connection_label.font()).horizontalAdvance(bar.connection_label.text()) <= _PATH_WIDTH
