"""
Session Browser Widget — client-first session browser.

Architecture (v2.0):
    ┌─────────────────────────────────────────────────────────────────────┐
    │  Client: M  ·  12 entries  ·  3 active  ·  2 stale                  │
    │  ─────────────────────────────────────────────────────────────────  │
    │  [Status ▾] [From] [To] [Search…]                                   │
    │  ─────────────────────────────────────────────────────────────────  │
    │  Status | Packing List | Session | Worker | …                       │
    │  rows…                                                              │
    │  Preview panel (on row select)                                      │
    │  [Export CSV] [Export Excel] [↻ Refresh]                            │
    └─────────────────────────────────────────────────────────────────────┘

The client comes from the command bar's picker (Bundle 6) -- this widget no
longer carries a client selector of its own; `load_client` is how it learns
which client's sessions to show.

Session data is loaded from per-client registry_index.json (1 file read),
not from scanning the directory tree.  Load time: < 1 second.

Migration: on first open for a client, if no registry file exists, a one-time
directory scan builds the registry.  Shown as "Building session index…".
"""

import logging
import time

from PySide6.QtCore import QSettings, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .session_detail_page import SessionDetailPage
from .sessions_list_widget import SessionsListWidget

logger = logging.getLogger(__name__)

# Auto-refresh interval in milliseconds (2 minutes — cheap with registry)
_AUTO_REFRESH_MS = 120_000


class SessionBrowserWidget(QWidget):
    """
    Main Session Browser container widget.

    Signals:
        resume_session_requested(dict): Forwarded from SessionsListWidget.
                dict keys: session_path, client_id, packing_list_name, work_dir, session_id
        start_packing_requested(dict):  Forwarded from SessionsListWidget.
                dict keys: session_path, client_id, packing_list_name, list_file
    """

    resume_session_requested = Signal(dict)
    start_packing_requested = Signal(dict)
    sessions_shown = Signal(int, int)  # (shown, total) -- forwarded for the status bar

    def __init__(
        self,
        profile_manager,
        session_lock_manager,
        session_history_manager,
        worker_manager,
        registry_manager=None,
        parent=None,
    ):
        super().__init__(parent)

        self.profile_manager = profile_manager
        self.session_lock_manager = session_lock_manager
        self.session_history_manager = session_history_manager
        self.worker_manager = worker_manager
        self.registry_manager = registry_manager

        self.settings = QSettings("PackingTool", "SessionBrowser")
        self._auto_refresh_enabled = self.settings.value(
            "auto_refresh_enabled", True, type=bool
        )

        self._init_ui()
        self._connect_signals()
        self._setup_auto_refresh()

        logger.info("SessionBrowserWidget (v2) initialized")

    def load_client(self, client_id: str) -> None:
        """The only way this widget learns its client (Bundle 6): the command
        bar's picker is the single client selector, and pushes changes here.

        The registry read behind this runs on RegistryRefreshWorker, and it
        must keep doing so: on a warehouse UNC path a synchronous read here
        is startup latency for a page most shifts never open.
        """
        self.sessions_list.load_client(client_id)

    # ------------------------------------------------------------------ #
    #  UI                                                                  #
    # ------------------------------------------------------------------ #

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Top controls
        top_bar = QHBoxLayout()
        self._auto_refresh_cb = QCheckBox("Auto-refresh (2 min)")
        self._auto_refresh_cb.setChecked(self._auto_refresh_enabled)
        self._auto_refresh_cb.stateChanged.connect(self._on_auto_refresh_toggled)
        top_bar.addWidget(self._auto_refresh_cb)
        top_bar.addStretch()
        root.addLayout(top_bar)

        self.sessions_list = SessionsListWidget(
            registry_manager=self.registry_manager,
            session_history_manager=self.session_history_manager,
        )
        self.detail_page = None

        self.stack = QStackedWidget()
        self.stack.addWidget(self.sessions_list)
        root.addWidget(self.stack)

    def show_detail(self, session_data: dict) -> None:
        """Show one session's detail page, replacing the list in the stack."""
        if self.detail_page is not None:
            self.stack.removeWidget(self.detail_page)
            self.detail_page.deleteLater()

        self.detail_page = SessionDetailPage(
            session_data,
            session_history_manager=self.session_history_manager,
            parent=self,
        )
        self.detail_page.back_requested.connect(self.show_list)
        self.stack.addWidget(self.detail_page)
        self.stack.setCurrentWidget(self.detail_page)

    def show_list(self) -> None:
        """Return to the session list."""
        self.stack.setCurrentWidget(self.sessions_list)

    def _connect_signals(self):
        self.sessions_list.resume_session_requested.connect(
            self.resume_session_requested
        )
        self.sessions_list.start_packing_requested.connect(self.start_packing_requested)
        self.sessions_list.session_details_requested.connect(self.show_detail)
        self.sessions_list.sessions_shown.connect(self.sessions_shown)

    # ------------------------------------------------------------------ #
    #  Auto-refresh                                                        #
    # ------------------------------------------------------------------ #

    def _setup_auto_refresh(self):
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._on_auto_refresh)

        if self._auto_refresh_enabled:
            last = self.settings.value("last_refresh_time", 0.0, type=float)
            elapsed_ms = int((time.time() - last) * 1000)
            remaining_ms = max(0, _AUTO_REFRESH_MS - elapsed_ms)
            self._refresh_timer.start(remaining_ms or _AUTO_REFRESH_MS)

    def _on_auto_refresh(self):
        if not self._auto_refresh_enabled:
            return
        # As a dialog this widget died on close and took its timer with it. As
        # a permanent page it outlives every visit, so refreshing while the
        # user is on the Packing page would put a registry rescan on the
        # warehouse UNC share in the middle of a scan. Keep the timer armed --
        # the next tick after the page is looked at again does the work.
        if self.isVisible():
            self.sessions_list.refresh()
            self.settings.setValue("last_refresh_time", time.time())
        self._refresh_timer.start(_AUTO_REFRESH_MS)

    def _on_auto_refresh_toggled(self, state):
        self._auto_refresh_enabled = bool(state)
        self.settings.setValue("auto_refresh_enabled", self._auto_refresh_enabled)
        if self._auto_refresh_enabled:
            self._refresh_timer.start(_AUTO_REFRESH_MS)
        else:
            self._refresh_timer.stop()
