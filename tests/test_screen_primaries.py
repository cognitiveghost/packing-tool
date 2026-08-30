"""Every screen and dialog names exactly one primary.

Pins the four call sites the 2026-08-29 default-role flip depends on: with the
bare QPushButton rule no longer painting accent_fill, a primary that loses its
set_button_role call goes silently grey rather than failing loudly.
"""
import inspect

from PySide6.QtWidgets import QPushButton

from gui.restore_session_dialog import RestoreSessionDialog
from gui.sku_mapping_dialog import SKUMappingDialog
from packing_tool.session_lock_manager import SessionLockManager


def _primaries(widget) -> list[str]:
    return [
        b.text() for b in widget.findChildren(QPushButton)
        if b.property("role") == "primary"
    ]


def test_the_packer_mode_button_is_marked_primary():
    from gui import main_window
    source = inspect.getsource(main_window)
    assert 'set_button_role(self.packer_mode_button, "primary")' in source


def test_restore_selected_is_the_restore_dialogs_one_primary(profile_manager, qapp):
    lock_manager = SessionLockManager(profile_manager)
    dialog = RestoreSessionDialog("TEST", profile_manager, lock_manager)
    try:
        assert _primaries(dialog) == ["Restore Selected"]
    finally:
        dialog.deleteLater()


def test_save_and_close_is_the_sku_mapping_dialogs_one_primary(profile_manager, qapp):
    dialog = SKUMappingDialog("TEST", profile_manager)
    try:
        # "Add Mapping" is a row-add, not the dialog's action -- must stay secondary.
        assert _primaries(dialog) == ["Save & Close"]
    finally:
        dialog.deleteLater()


def test_server_connection_save_is_the_dialogs_one_primary(qapp, tmp_path):
    """shared/ was outside the 2026-08-29 audit's gui/-only sweep.

    This dialog is how a warehouse PC gets pointed at the file server; after the
    default flip it had no primary at all until the review caught it.
    """
    from shared.server_connection import ConnectionSettingsDialog

    dialog = ConnectionSettingsDialog(None, "TestOrg", "NO_SUCH_ENV", str(tmp_path))
    try:
        assert _primaries(dialog) == ["Save"]
    finally:
        dialog.deleteLater()
