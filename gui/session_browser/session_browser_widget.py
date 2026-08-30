"""
Session Browser Widget — client-first session browser.

Architecture (v2.0):
    ┌────────────────┬─────────────────────────────────────────────────────┐
    │  CLIENTS       │  Client: M  ·  12 entries  ·  3 active  ·  2 stale  │
    │  ─────────     │  ──────────────────────────────────────────────────  │
    │  > M           │  [Status ▾] [From] [To] [Search…]                    │
    │    K           │  ──────────────────────────────────────────────────  │
    │    S           │  Status | Packing List | Session | Worker | …        │
    │                │  rows…                                               │
    │  [↻ Refresh]   │  Preview panel (on row select)                       │
    │                │  [Export CSV] [Export Excel] [↻ Refresh]             │
    └────────────────┴─────────────────────────────────────────────────────┘

Session data is loaded from per-client registry_index.json (1 file read),
not from scanning the directory tree.  Load time: < 1 second.

Migration: on first open for a client, if no registry file exists, a one-time
directory scan builds the registry.  Shown as "Building session index…".
"""

import logging
import time

from PySide6.QtCore import QSettings, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .client_selector_widget import ClientSelectorWidget
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
    start_packing_requested  = Signal(dict)

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

        self.profile_manager       = profile_manager
        self.session_lock_manager  = session_lock_manager
        self.session_history_manager = session_history_manager
        self.worker_manager        = worker_manager
        self.registry_manager      = registry_manager

        self.settings = QSettings("PackingTool", "SessionBrowser")
        self._auto_refresh_enabled = self.settings.value(
            "auto_refresh_enabled", True, type=bool
        )

        self._init_ui()
        self._connect_signals()
        self._setup_auto_refresh()

        self._clients_loaded = False

        logger.info("SessionBrowserWidget (v2) initialized")

    def showEvent(self, event):
        """Load clients the first time the page is actually looked at.

        As a dialog this ran in __init__, immediately before exec(). As a page
        constructed at startup it would run on every app launch -- and it does
        not just list directories, it selects a client, which reads that
        client's registry off the file server. On a warehouse UNC path that is
        startup latency for a page most shifts never open.
        """
        super().showEvent(event)
        if not self._clients_loaded:
            self._clients_loaded = True
            self.client_selector.load_clients()

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

        # Horizontal splitter: client list | session table
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

        self.client_selector = ClientSelectorWidget(self.profile_manager)
        splitter.addWidget(self.client_selector)

        self.sessions_list = SessionsListWidget(
            registry_manager=self.registry_manager,
            session_history_manager=self.session_history_manager,
        )
        splitter.addWidget(self.sessions_list)

        splitter.setStretchFactor(0, 0)   # client panel — fixed
        splitter.setStretchFactor(1, 1)   # sessions panel — stretches

        root.addWidget(splitter)

    def _connect_signals(self):
        self.client_selector.client_selected.connect(self.sessions_list.load_client)
        self.sessions_list.resume_session_requested.connect(self.resume_session_requested)
        self.sessions_list.start_packing_requested.connect(self.start_packing_requested)

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
