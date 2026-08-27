"""Background QThread workers for slow I/O during session start/end."""
import logging

from PySide6.QtCore import QThread
from PySide6.QtWidgets import QApplication

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
            logic = PackerLogic(
                client_id=self._client_id,
                profile_manager=self._profile_manager,
                work_dir=str(self._work_dir),
            )
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
