"""
Restore Session Dialog - UI for selecting incomplete sessions with lock status.
"""

import logging
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from shared.theme import set_button_role

logger = logging.getLogger(__name__)


class RestoreSessionDialog(QDialog):
    """Dialog for selecting and restoring incomplete sessions with lock status indicators."""

    def __init__(self, client_id: str, profile_manager, lock_manager, parent=None):
        """
        Initialize the restore session dialog.

        Args:
            client_id: Current client identifier
            profile_manager: ProfileManager instance
            lock_manager: SessionLockManager instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.client_id = client_id
        self.profile_manager = profile_manager
        self.lock_manager = lock_manager
        self.selected_session = None

        self.setWindowTitle(f"Restore Session - Client {client_id}")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)

        self._init_ui()
        self._load_sessions()

    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)

        # Header
        header_label = QLabel("Select a session to restore:")
        header_label.setStyleSheet("font-size: 12pt; font-weight: bold;")
        layout.addWidget(header_label)

        # Session list
        self.session_list = QListWidget()
        self.session_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.session_list)

        # Buttons
        button_layout = QHBoxLayout()

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self._load_sessions)
        button_layout.addWidget(self.refresh_button)

        button_layout.addStretch()

        self.restore_button = QPushButton("Restore Selected")
        self.restore_button.setEnabled(False)
        self.restore_button.clicked.connect(self._on_restore)
        set_button_role(self.restore_button, "primary")
        button_layout.addWidget(self.restore_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)

        layout.addLayout(button_layout)

        # Connect selection change
        self.session_list.itemSelectionChanged.connect(self._on_selection_changed)

    def _load_sessions(self):
        """Load incomplete sessions and display with lock status."""
        self.session_list.clear()

        try:
            sessions = self.profile_manager.get_incomplete_sessions(self.client_id)

            if not sessions:
                item = QListWidgetItem("No incomplete sessions found")
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.session_list.addItem(item)
                return

            for session_dir in sessions:
                # Check lock status
                is_locked, lock_info = self.lock_manager.is_locked(session_dir)

                if is_locked:
                    # Check if stale
                    if self.lock_manager.is_lock_stale(lock_info):
                        user_info = lock_info.get('user_name', 'Unknown')
                        pc_info = lock_info.get('locked_by', 'Unknown')
                        status = f"Stale lock - {user_info} on {pc_info}"
                        stale = True
                    else:
                        user_info = lock_info.get('user_name', 'Unknown')
                        pc_info = lock_info.get('locked_by', 'Unknown')
                        status = f"Active - {user_info} on {pc_info}"
                        stale = False
                else:
                    status = "Available"
                    stale = False
                    lock_info = None

                # Format session name with timestamp
                session_name = session_dir.name
                item_text = f"{session_name}  -  {status}"

                item = QListWidgetItem(item_text)
                item.setData(Qt.ItemDataRole.UserRole, {
                    'session_dir': session_dir,
                    'locked': is_locked,
                    'stale': stale,
                    'lock_info': lock_info
                })

                # Disable locked (non-stale) items
                if is_locked and not stale:
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                    item.setForeground(Qt.GlobalColor.gray)

                self.session_list.addItem(item)

            logger.info(f"Loaded {len(sessions)} incomplete sessions for client {self.client_id}")

        except Exception as e:
            logger.exception("Failed to load sessions")
            QMessageBox.warning(
                self,
                "Error",
                f"Failed to load sessions:\n\n{e}"
            )

    def _on_selection_changed(self):
        """Handle selection change in the list."""
        items = self.session_list.selectedItems()
        self.restore_button.setEnabled(len(items) > 0)

    def _on_item_double_clicked(self, item: QListWidgetItem):
        """Handle double-click on a session item."""
        self._on_restore()

    def _on_restore(self):
        """Handle restore button click."""
        items = self.session_list.selectedItems()
        if not items:
            return

        item = items[0]
        data = item.data(Qt.ItemDataRole.UserRole)

        if not data:
            return

        session_dir = data['session_dir']
        is_locked = data['locked']
        is_stale = data['stale']
        lock_info = data['lock_info']

        # If locked but not stale, should not be able to restore
        if is_locked and not is_stale:
            QMessageBox.warning(
                self,
                "Session Locked",
                "This session is currently active on another PC.\n"
                "Please wait or select a different session."
            )
            return

        # If stale, ask for confirmation to force-release
        if is_stale:
            user_name = lock_info.get('user_name', 'Unknown') if lock_info else 'Unknown'
            pc_name = lock_info.get('locked_by', 'Unknown') if lock_info else 'Unknown'

            reply = QMessageBox.question(
                self,
                "Force Release Stale Lock?",
                f"This session has a stale lock from:\n"
                f"User: {user_name}\n"
                f"PC: {pc_name}\n\n"
                f"The application may have crashed.\n\n"
                f"Force-release the lock and restore this session?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )

            if reply == QMessageBox.StandardButton.Yes:
                # Force release
                try:
                    success = self.lock_manager.force_release_lock(session_dir)
                    if not success:
                        QMessageBox.critical(
                            self,
                            "Error",
                            "Failed to release the lock. Please try again."
                        )
                        return
                except Exception as e:
                    logger.exception("Error force-releasing lock")
                    QMessageBox.critical(self, "Error", f"Failed to release lock:\n\n{e}")
                    return
            else:
                return

        # Session is available, set it as selected and accept
        self.selected_session = session_dir
        self.accept()

    def get_selected_session(self) -> Path | None:
        """
        Get the selected session directory.

        Returns:
            Path to the selected session, or None if no session was selected
        """
        return self.selected_session
