"""The app's language is read at startup and shown in the sidebar (ADR 0021, ADR 0022)."""

from PySide6.QtCore import QSettings

import main
from shared import i18n


def test_saved_language_is_applied():
    QSettings("PackingTool", "Language").setValue("language", "bg")
    assert main.apply_saved_language() == "bg"
    assert i18n._("Restart now") == "Рестартирай сега"


def test_default_is_english():
    QSettings("PackingTool", "Language").remove("language")
    assert main.apply_saved_language() == "en"
