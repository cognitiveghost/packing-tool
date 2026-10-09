"""Background QThread workers for slow I/O during session start/end."""
import logging
import os

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication

from packing_tool.session_details import (
    SessionFilesError,
    error_cause,
    load_session_details,
)

logger = logging.getLogger(__name__)


class SessionStartWorker(QThread):
    """
    Background worker for the slow I/O steps when starting a session.

    Performs PackerLogic construction (reads packer_config + packing_state from server)
    and load_packing_list_json (reads + parses the packing list JSON) off the UI thread.

    Lock acquisition and heartbeat setup remain on the main thread because stale-lock
    handling requires a QMessageBox interaction.

    Usage (blocking-with-progress pattern):
        worker = SessionStartWorker(client_id, profile_manager, work_dir, packing_list_path)
        worker.start()
        while not worker.wait(50):
            QApplication.processEvents()
        if worker.error:
            raise worker.error
        self.logic = worker.logic
    """

    # 2: reading saved progress. 3: reading the packing list. Step 1, the
    # lock, is the caller's (it can ask a question, so it is on the UI thread).
    step = Signal(int)

    def __init__(self, client_id, profile_manager, work_dir, packing_list_path, parent=None):
        super().__init__(parent)
        self._client_id = client_id
        self._profile_manager = profile_manager
        self._work_dir = work_dir
        self._packing_list_path = packing_list_path
        # Results (read by main thread after wait())
        self.logic = None
        self.order_count = 0
        self.list_name = ""
        self.error = None  # Exception instance if failed

    def run(self) -> None:
        try:
            from packing_tool.packer_logic import PackerLogic
            self.step.emit(2)
            logic = PackerLogic(
                client_id=self._client_id,
                profile_manager=self._profile_manager,
                work_dir=str(self._work_dir),
            )
            self.step.emit(3)
            order_count, list_name = logic.load_packing_list_json(str(self._packing_list_path))
            # Move Qt object ownership back to the main thread
            logic.moveToThread(QApplication.instance().thread())
            self.logic = logic
            self.order_count = order_count
            self.list_name = list_name
        except Exception as exc:
            self.error = exc


class SessionEndWorker(QThread):
    """
    Background worker for the slow server-write operations at session end.

    Accepts a single callable (write_fn) that captures all necessary context
    via closure, keeping this class generic and the caller readable.

    Usage (blocking-with-progress pattern):
        worker = SessionEndWorker(lambda: _do_all_slow_writes())
        worker.start()
        while not worker.wait(50):
            QApplication.processEvents()
        if worker.error:
            logger.error(...)
        # Proceed with lock release / UI reset
    """

    def __init__(self, write_fn, parent=None):
        super().__init__(parent)
        self._write_fn = write_fn
        self.error = None

    def run(self) -> None:
        try:
            self._write_fn()
        except Exception as exc:
            logger.exception("SessionEndWorker: unexpected error")
            self.error = exc


class RegistryRefreshWorker(QThread):
    """Reads a client's session registry off the UI thread.

    1. ensure_registry(): a one-time scan if the file is missing
    2. refresh_available_lists(): packing lists uploaded since
    3. get_all_entries(): every entry with its status resolved

    Both signals carry the client id, so an answer for a client the packer
    has already left can be dropped.
    """

    refresh_complete = Signal(str, list)  # (client_id, entries)
    refresh_failed = Signal(str, str)  # (client_id, cause)

    def __init__(self, registry_manager, client_id: str, parent=None):
        super().__init__(parent)
        self._registry = registry_manager
        self._client_id = client_id

    def run(self) -> None:
        try:
            # read_registry answers an unreachable server with an empty
            # registry. Listing the server's root first lets the real error
            # out, so the page can say the refresh failed (frame 7f).
            os.listdir(self._registry.profile_manager.base_path)
            self._registry.ensure_registry(self._client_id)
            self._registry.refresh_available_lists(self._client_id)
            entries = self._registry.get_all_entries(self._client_id)
        except Exception as error:
            logger.exception("RegistryRefreshWorker failed")
            self.refresh_failed.emit(self._client_id, error_cause(error))
        else:
            self.refresh_complete.emit(self._client_id, entries)


class SessionDetailsWorker(QThread):
    """Reads one session's files off the UI thread (spec section 7.1)."""

    loaded = Signal(str, object)  # (key, details)
    failed = Signal(str, str, str)  # (key, path, cause)

    def __init__(self, key: str, entry: dict, parent=None):
        super().__init__(parent)
        self._key = key
        self._entry = dict(entry)

    def run(self) -> None:
        try:
            details = load_session_details(self._entry)
        except SessionFilesError as error:
            self.failed.emit(self._key, error.path, error.cause)
        except Exception as error:
            logger.exception("SessionDetailsWorker failed")
            self.failed.emit(self._key, str(self._entry.get("work_dir", "")), error_cause(error))
        else:
            self.loaded.emit(self._key, details)
