"""The Sessions pages' controller (spec 2026-10-08 phase 4, sections 4.5, 6 and 8).

What gui/session_browser/ was, without the widgets: it owns the registry
refresh, the reading of one session's files, the 2-minute timer, the filter
the packer set, the take-over question and the exports, and tells the app
document what to draw through AppBridge. gui/sessions_payload.py decides
every word; gui/web/app.js draws it.
"""

import csv
import logging
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from PySide6.QtCore import QObject, QSettings, QTimer, Signal
from PySide6.QtWidgets import QFileDialog, QMessageBox

from gui.sessions_payload import (
    EXPORT_COLUMNS,
    default_range,
    detail_export_rows,
    details_payload,
    plural,
    refresh_failure,
    row_action,
    session_export_rows,
    session_key,
    sessions_payload,
    takeover_payload,
    visible_entries,
)
from gui.workers import RegistryRefreshWorker, SessionDetailsWorker
from packing_tool.session_details import UNREADABLE_SHAPE

logger = logging.getLogger(__name__)

# Cheap with the registry: one file read per client.
AUTO_REFRESH_MS = 120_000


def _now() -> datetime:
    return datetime.now().astimezone()


class SessionsPage(QObject):
    """Drives the Sessions and Session details pages of the app document."""

    startRequested = Signal(object)
    resumeRequested = Signal(object)
    showPackingRequested = Signal()

    def __init__(
        self,
        bridge,
        registry_manager,
        lock_manager,
        *,
        window=None,
        is_showing=lambda: True,
        client_label=lambda: "",
        toast=lambda message: None,
        parent=None,
    ):
        super().__init__(parent)
        self._bridge = bridge
        self._registry = registry_manager
        self._locks = lock_manager
        self._window = window
        self._is_showing = is_showing
        self._client_label = client_label
        self._toast = toast

        self._client_id: str | None = None
        self._entries: list[dict] = []
        self._loaded = False
        self._refreshing = False
        self._stamp = ""
        self._failure: dict | None = None
        self._tab = "all"
        self._query = ""
        # None: the default range, worked out at each push so it moves with
        # the day. A pair once the packer has changed a date.
        self._dates: tuple[str, str] | None = None
        self._open_key = ""
        self._server_down = False
        self._refresh_worker: RegistryRefreshWorker | None = None
        self._refresh_client: str | None = None

        self._detail_key = ""
        self._detail_entry: dict | None = None
        self._details: dict | None = None
        self._detail_error: dict | None = None
        self._detail_query = ""
        self._detail_worker: SessionDetailsWorker | None = None

        # (resume payload, the stale lock) while frame 7c is open.
        self._pending: tuple[dict, dict] | None = None

        self._settings = QSettings("PackingTool", "SessionBrowser")
        self._auto = self._settings.value("auto_refresh_enabled", True, type=bool)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        if self._auto:
            last = self._settings.value("last_refresh_time", 0.0, type=float)
            remaining = max(0, AUTO_REFRESH_MS - int((time.time() - last) * 1000))
            self._timer.start(remaining or AUTO_REFRESH_MS)

        bridge.sessionsFilterChanged.connect(self._on_filter)
        bridge.sessionsFilterCleared.connect(self._on_filter_cleared)
        bridge.refreshSessionsRequested.connect(self.refresh)
        bridge.autoRefreshChanged.connect(self._on_auto)
        bridge.sessionActionRequested.connect(self._on_action)
        bridge.sessionDetailsRequested.connect(self.open_details)
        bridge.exportSessionsRequested.connect(self._export_sessions)
        bridge.closeDetailsRequested.connect(self.close_details)
        bridge.detailsFilterChanged.connect(self._on_details_filter)
        bridge.retryDetailsRequested.connect(lambda: self._load_details())
        bridge.exportDetailsRequested.connect(self._export_details)
        bridge.takeOverAnswered.connect(self._on_take_over)

    # --- what MainWindow calls ------------------------------------------------

    def load_client(self, client_id: str) -> None:
        """Show this client's sessions. The command bar's picker is the only
        client selector, and pushes its changes here."""
        self._client_id = client_id
        self._entries = []
        self._loaded = False
        self._stamp = ""
        self._failure = None
        self._pending = None
        self._bridge.set_confirm({})
        self.close_details()
        self.refresh()

    def refresh(self) -> None:
        """Read the registry on a worker. On a warehouse UNC path a read on
        the UI thread is latency for a page most shifts never open."""
        if not self._client_id:
            return
        worker = self._refresh_worker
        if worker is not None and worker.isRunning() and self._refresh_client == self._client_id:
            return  # that answer is the one being asked for
        self._refreshing = True
        self._push()
        worker = RegistryRefreshWorker(self._registry, self._client_id, parent=self)
        worker.refresh_complete.connect(self._on_refreshed)
        worker.refresh_failed.connect(self._on_refresh_failed)
        worker.finished.connect(self._on_worker_finished)
        self._refresh_worker = worker
        self._refresh_client = self._client_id
        worker.start()

    def page_shown(self) -> None:
        """The Sessions page came on screen: what it shows should be now."""
        self.refresh()

    def set_context(self, open_key: str, server_down: bool) -> None:
        """Which session is open on this PC, and whether the server answers."""
        context = (str(open_key or ""), bool(server_down))
        if context == (self._open_key, self._server_down):
            return
        self._open_key, self._server_down = context
        self._push()
        self._push_details()

    def show_entries(self, entries: list) -> None:
        """Display these entries as a finished refresh would. The refresh's
        own path, and the seam for tests and the render script."""
        self._entries = list(entries)
        self._loaded = True
        self._refreshing = False
        self._failure = None
        self._stamp = _now().strftime("%H:%M:%S")
        self._push()
        if not self._detail_key:
            return
        entry = self._entry(self._detail_key)
        if entry is None:
            return
        was_live = (self._detail_entry or {}).get("status") == "in_progress"
        self._detail_entry = entry
        if was_live or entry.get("status") == "in_progress":
            # Frame 8b: an Active session's numbers refresh with the list,
            # and once more when it finishes, so the final figures are shown.
            self._load_details(keep=True)
        else:
            self._push_details()

    def wait(self, timeout_ms: int = 10000) -> None:
        """Block until the workers are done. Their answers are queued: the
        caller still has to let the event loop run."""
        for worker in (self._refresh_worker, self._detail_worker):
            if worker is not None:
                worker.wait(timeout_ms)

    def shutdown(self) -> None:
        self._timer.stop()
        self.wait()

    # --- the list ---------------------------------------------------------------

    def _entry(self, key: str) -> dict | None:
        return next((e for e in self._entries if session_key(e) == key), None)

    def _push(self) -> None:
        date_from, date_to = self._dates or (None, None)
        self._bridge.set_sessions(
            sessions_payload(
                self._entries,
                tab=self._tab,
                query=self._query,
                date_from=date_from,
                date_to=date_to,
                loaded=self._loaded,
                refreshing=self._refreshing,
                stamp=self._stamp,
                auto=self._auto,
                failure=self._failure,
                open_key=self._open_key,
                server_down=self._server_down,
            )
        )

    def _on_worker_finished(self) -> None:
        # A bound slot, so it runs on this object's thread, after the worker's
        # answer (both are queued, in the order they were emitted).
        worker = self.sender()
        if worker is None:
            return
        if self._refresh_worker is worker:
            self._refresh_worker = None
        if self._detail_worker is worker:
            self._detail_worker = None
        worker.deleteLater()

    def _on_refreshed(self, client_id: str, entries: list) -> None:
        # An answer for a client the packer has already left is dropped.
        if client_id != self._client_id:
            return
        self.show_entries(entries)

    def _on_refresh_failed(self, client_id: str, cause: str) -> None:
        if client_id != self._client_id:
            return
        logger.error("Sessions refresh failed for %s: %s", client_id, cause)
        folder = Path(self._registry.profile_manager.get_sessions_root()) / f"CLIENT_{client_id}"
        self._failure = refresh_failure(folder, cause, _now().strftime("%H:%M:%S"), self._stamp)
        self._loaded = True
        self._refreshing = False
        self._push()

    def _on_filter(self, tab: str, query: str, date_from: str, date_to: str) -> None:
        self._tab = tab
        self._query = query
        # The page sends back the dates it was given. While they are still the
        # default they stay the default, so tomorrow the range is tomorrow's.
        dates = (date_from, date_to)
        self._dates = None if dates == default_range(_now()) else dates
        self._push()

    def _on_filter_cleared(self) -> None:
        self._query = ""
        self._dates = None
        self._push()

    def _on_auto(self, enabled: bool) -> None:
        self._auto = bool(enabled)
        self._settings.setValue("auto_refresh_enabled", self._auto)
        if self._auto:
            self._timer.start(AUTO_REFRESH_MS)
        else:
            self._timer.stop()
        self._push()

    def _on_tick(self) -> None:
        # Not while the page is out of sight: that would put a registry read
        # on the warehouse share in the middle of a scan. The timer stays
        # armed, and the next tick after the page is looked at does the work.
        if self._auto and self._is_showing():
            self.refresh()
            self._settings.setValue("last_refresh_time", time.time())
        self._timer.start(AUTO_REFRESH_MS)

    # --- start, resume, take over -------------------------------------------------

    def _on_action(self, key: str) -> None:
        entry = self._entry(key)
        if entry is None:
            return
        action = row_action(entry, open_key=self._open_key, server_down=self._server_down)
        if not action["enabled"]:
            return
        kind = action["action"]
        if kind == "details":
            self.open_details(key)
        elif kind == "show":
            self.showPackingRequested.emit()
        elif kind == "start":
            self.startRequested.emit({
                "session_path": entry.get("session_path", ""),
                "client_id": self._client_id,
                "packing_list_name": entry.get("packing_list_name", ""),
                "list_file": entry.get("packing_list_path", ""),
            })
        elif kind == "resume":
            info = {
                "session_path": entry.get("session_path", ""),
                "client_id": self._client_id,
                "packing_list_name": entry.get("packing_list_name", ""),
                "work_dir": entry.get("work_dir", ""),
                "session_id": entry.get("session_id", ""),
                "take_over": None,
            }
            stale = self._stale_lock(entry.get("work_dir", ""))
            if stale is not None:
                # Frame 7c: who had it and what comes along, before anything starts.
                self._pending = (info, stale)
                self._bridge.set_confirm(takeover_payload(entry, stale))
                return
            self.resumeRequested.emit(info)

    def _stale_lock(self, work_dir: str) -> dict | None:
        """The lock another process left on this session, if it can be taken.

        A live lock, our own lock and no lock are all None: the start itself
        deals with those.
        """
        if not work_dir:
            return None
        try:
            locked, lock = self._locks.is_locked(Path(work_dir))
        except OSError:
            return None
        if not locked or not lock:
            return None
        ours = (
            lock.get("locked_by") == self._locks.hostname
            and lock.get("process_id") == self._locks.process_id
        )
        if ours or not self._locks.is_lock_stale(lock):
            return None
        return lock

    def _on_take_over(self, yes: bool) -> None:
        pending, self._pending = self._pending, None
        self._bridge.set_confirm({})
        if yes and pending is not None:
            info, stale = pending
            self.resumeRequested.emit({**info, "take_over": stale})

    # --- Session details ------------------------------------------------------------

    def open_details(self, key: str) -> None:
        entry = self._entry(key)
        if entry is None:
            return
        self._detail_key = key
        self._detail_entry = entry
        self._detail_query = ""
        self._load_details()
        if self._bridge.page == "sessions":
            self._bridge.set_page("details")

    def close_details(self) -> None:
        self._detail_key = ""
        self._detail_entry = None
        self._details = None
        self._detail_error = None
        self._bridge.set_details({})
        if self._bridge.page == "details":
            self._bridge.set_page("sessions")

    def _load_details(self, keep: bool = False) -> None:
        """Read the open session's files on a worker. `keep` leaves what is
        shown in place until the new answer lands."""
        if not self._detail_key or self._detail_entry is None:
            return
        if not keep:
            self._details = None
            self._detail_error = None
        self._push_details()
        worker = SessionDetailsWorker(self._detail_key, self._detail_entry, parent=self)
        worker.loaded.connect(self._on_details)
        worker.failed.connect(self._on_details_failed)
        worker.finished.connect(self._on_worker_finished)
        self._detail_worker = worker
        worker.start()

    def _on_details(self, key: str, details: dict) -> None:
        if key != self._detail_key:
            return  # that session's details were closed meanwhile
        self._details = details
        self._detail_error = None
        self._push_details()

    def _on_details_failed(self, key: str, path: str, cause: str) -> None:
        if key != self._detail_key:
            return
        self._details = None
        self._detail_error = {"path": path, "cause": cause}
        self._push_details()

    def _on_details_filter(self, text: str) -> None:
        self._detail_query = text
        self._push_details()

    def _push_details(self) -> None:
        if not self._detail_key or self._detail_entry is None:
            return
        def build():
            return details_payload(
                self._detail_entry,
                self._details,
                client=self._client_label(),
                error=self._detail_error,
                query=self._detail_query,
                stamp=self._stamp,
                open_key=self._open_key,
            )

        try:
            payload = build()
        except Exception:
            # Files that parse but are not the shape this version writes: frame 8f.
            logger.exception("Session details could not be built")
            self._details = None
            self._detail_error = {
                "path": str(self._detail_entry.get("work_dir", "")),
                "cause": UNREADABLE_SHAPE,
            }
            payload = build()
        self._bridge.set_details(payload)

    # --- exports -----------------------------------------------------------------------

    def _export_sessions(self, fmt: str) -> None:
        now = _now()
        date_from, date_to = self._dates or default_range(now)
        shown, _in_tab, _in_dates = visible_entries(
            self._entries, now=now, tab=self._tab, query=self._query,
            date_from=date_from, date_to=date_to,
        )
        if not shown or not self._client_id:
            return
        excel = fmt == "xlsx"
        path, _selected = QFileDialog.getSaveFileName(
            self._window,
            "Save Excel" if excel else "Save CSV",
            f"sessions_{self._client_id}.{'xlsx' if excel else 'csv'}",
            "Excel files (*.xlsx)" if excel else "CSV files (*.csv)",
        )
        if not path:
            return
        rows = session_export_rows(shown, labels=excel)
        try:
            if excel:
                pd.DataFrame(rows, columns=list(EXPORT_COLUMNS)).to_excel(path, index=False)
            else:
                with open(path, "w", newline="", encoding="utf-8") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(EXPORT_COLUMNS)
                    writer.writerows(rows)
        except Exception as error:
            logger.exception("Sessions export failed")
            QMessageBox.critical(self._window, "Export Failed", str(error))
            return
        self._toast(
            f"Exported {plural(len(rows), 'session', 'sessions')} to {Path(path).name}"
        )

    def _export_details(self) -> None:
        rows = detail_export_rows(self._details)
        if not rows or self._detail_entry is None:
            return
        session_id = self._detail_entry.get("session_id", "session")
        path, _selected = QFileDialog.getSaveFileName(
            self._window,
            "Export Session Details",
            f"session_{session_id}.xlsx",
            "Excel Files (*.xlsx)",
        )
        if not path:
            return
        try:
            pd.DataFrame(rows).to_excel(path, index=False, sheet_name="Session Details")
        except Exception as error:
            logger.exception("Session details export failed")
            QMessageBox.critical(
                self._window, "Export Failed", f"Failed to export session details:\n{error}"
            )
            return
        self._toast(f"Exported {session_id} to {Path(path).name}")
