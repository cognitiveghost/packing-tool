"""The two full-window pages: Worker selection and SKU mapping (ADR 0002).

One QWebEngineView showing the setup document. This widget is everything
the two pages read from or write to the server; MainWindow only switches to
it and away from it. gui/setup_payload.py decides what the pages say.

Spec: docs/superpowers/specs/2026-10-09-ui-refresh-phase5-setup-pages-design.md
"""

import logging
from datetime import datetime

from PySide6.QtCore import Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget

from gui.setup_bridge import mount_setup_page
from gui.setup_payload import (
    MappingEditor,
    clean_mapping,
    clean_worker_name,
    mapping_error,
    mapping_payload,
    worker_name_problem,
    workers_payload,
)
from packing_tool.packer_logic import normalize_sku
from packing_tool.profile_manager import ProfileManagerError
from packing_tool.session_details import error_cause
from shared.web_page import when_painted

logger = logging.getLogger(__name__)


class SetupPages(QWidget):
    workerChosen = Signal(str, str)  # id, name; after "Opening…" has painted
    quitRequested = Signal()
    backRequested = Signal()  # leave, with nothing to report
    mappingSaved = Signal(object)  # the whole mapping, after a Save
    quickMapped = Signal(str, str, str, object)  # kind, barcode, SKU, the whole mapping
    strayScanned = Signal(str)

    def __init__(self, worker_manager, profile_manager, parent=None, *, now=None) -> None:
        super().__init__(parent)
        self._worker_manager = worker_manager
        self._profile_manager = profile_manager
        self._now = now or (lambda: datetime.now().astimezone())

        self.view = QWebEngineView(self)
        self.bridge = mount_setup_page(self.view)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

        # Worker selection
        self._startup = False
        self._current_id = ""
        self._current_name = ""
        self._workers: list = []
        self._picked = ""
        # SKU mapping
        self._client = ""
        self._label = ""
        self._quick: dict = {}
        self._editor = MappingEditor()
        self._failed = False
        self._saved = False
        self._error: dict = {}

        bridge = self.bridge
        bridge.answer = self._answer
        bridge.workerPicked.connect(self._pick)
        bridge.workersRetryRequested.connect(self._load_workers)
        bridge.workersLeaveRequested.connect(self._leave_workers)
        bridge.mappingDeleteRequested.connect(self._delete)
        bridge.mappingReloadRequested.connect(self._reload)
        bridge.mappingSaveRequested.connect(self._save)
        bridge.mappingCloseRequested.connect(self.backRequested.emit)
        bridge.strayScanned.connect(self.strayScanned.emit)

    def _answer(self, name: str, *args) -> str:
        handlers = {
            "createWorker": self._create_worker,
            "addMapping": self._add,
            "updateMapping": self._update,
            "replaceMapping": self._replace,
        }
        return handlers[name](*args)

    def blank(self) -> None:
        """Draw nothing, and forget both pages' state."""
        self.bridge.set_page("")
        self._workers, self._picked = [], ""
        self._quick, self._editor = {}, MappingEditor()
        self._failed, self._saved, self._error = False, False, {}
        self.bridge.set_workers({})
        self.bridge.set_mapping({})

    # --- Worker selection ----------------------------------------------------

    def show_workers(self, current_id: str = "", current_name: str = "", *, startup: bool) -> None:
        self._startup = bool(startup)
        self._current_id, self._current_name = str(current_id or ""), str(current_name or "")
        self._picked = ""
        self._load_workers()
        self.bridge.set_page("workers")

    def _load_workers(self) -> None:
        # ponytail: read on the UI thread, as the dialog did; one small file.
        failure = None
        try:
            self._workers = self._worker_manager.get_all_workers()
        except Exception as error:
            logger.exception("Could not load the worker list")
            self._workers = []
            failure = {
                "cause": error_cause(error),
                "path": str(self._worker_manager.workers_dir),
            }
        self._push_workers(failure)

    def _push_workers(self, failure: dict | None = None) -> None:
        self.bridge.set_workers(
            workers_payload(
                self._workers,
                startup=self._startup,
                now=self._now(),
                current_id=self._current_id,
                current_name=self._current_name,
                picked_id=self._picked,
                failure=failure,
            )
        )

    def _pick(self, worker_id: str) -> None:
        worker = next((w for w in self._workers if w.id == worker_id), None)
        if worker is None or self._picked:
            return
        self._picked = worker.id
        self._push_workers()
        # The packer sees "Opening…" before the page goes (spec section 5.3).
        when_painted(self.bridge, lambda: self.workerChosen.emit(worker.id, worker.name))

    def _create_worker(self, name: str) -> str:
        problem = worker_name_problem(name, [w.name for w in self._workers])
        if problem:
            return problem
        try:
            worker = self._worker_manager.create_worker(clean_worker_name(name))
        except ValueError:
            # Another PC took the name since this list was read.
            self._load_workers()
            return worker_name_problem(name, [w.name for w in self._workers]) or (
                "That name can’t be used."
            )
        except Exception as error:
            logger.exception("Could not create the worker")
            return f"Couldn’t create the worker: {error_cause(error)}."
        self._workers = [*self._workers, worker]
        self._pick(worker.id)
        return ""

    def _leave_workers(self) -> None:
        if self._startup:
            self.quitRequested.emit()
        else:
            self.backRequested.emit()

    # --- SKU mapping -----------------------------------------------------------

    def show_mapping(self, client_id: str, client_label: str, quick: dict | None = None) -> None:
        self._client, self._label = str(client_id), str(client_label)
        self._quick = dict(quick or {})
        self._load_mapping()
        self.bridge.set_page("mapping")

    def dirty(self) -> bool:
        """Whether leaving now would lose unsaved changes."""
        return (
            self.bridge.page == "mapping"
            and not self._quick
            and sum(self._editor.counts().values()) > 0
        )

    def ask_leave(self) -> None:
        self.bridge.leaveAsked.emit()

    def _mapping_path(self) -> str:
        folder = self._profile_manager.clients_dir / f"CLIENT_{self._client}"
        return str(folder / "packer_config.json")

    def _load_mapping(self) -> None:
        # ponytail: read on the UI thread, as the dialog did; one small file.
        self._saved = False
        try:
            mapping = self._profile_manager.load_sku_mapping(self._client, fresh=True)
        except ProfileManagerError as error:
            logger.exception("Could not load the SKU mapping")
            self._editor = MappingEditor()
            self._failed = True
            self._error = mapping_error("load", str(error), self._mapping_path())
        else:
            self._editor = MappingEditor(mapping)
            self._failed = False
            self._error = {}
        self._push_mapping()

    def _push_mapping(self) -> None:
        self.bridge.set_mapping(
            mapping_payload(
                self._editor,
                client=self._label,
                saved=self._saved,
                error=self._error,
                quick=self._quick,
                failed=self._failed,
            )
        )

    def _changed(self, problem: str) -> str:
        if not problem:
            self._saved = False
            self._push_mapping()
        return problem

    def _add(self, barcode: str, sku: str) -> str:
        if self._quick:
            return self._quick_add(barcode, sku, replace=False)
        return self._changed(self._editor.add(barcode, sku))

    def _update(self, row_id: int, barcode: str, sku: str) -> str:
        if self._quick:
            return ""
        return self._changed(self._editor.update(row_id, barcode, sku))

    def _replace(self, row_id: int, barcode: str, sku: str) -> str:
        if self._quick:
            return self._quick_add(barcode, sku, replace=True)
        return self._changed(self._editor.replace(row_id, barcode, sku))

    def _delete(self, row_id: int) -> None:
        if self._quick:
            return
        self._editor.delete(row_id)
        self._changed("")

    def _reload(self) -> None:
        if not self._quick:
            self._load_mapping()

    def _save(self) -> None:
        if self._quick:
            return
        add, remove = self._editor.changes()
        if not add and not remove:
            return
        changes = sum(self._editor.counts().values())
        try:
            mapping = self._profile_manager.update_sku_mapping(self._client, add, remove)
        except ProfileManagerError as error:
            self._error = mapping_error("save", str(error), self._mapping_path(), changes)
            self._push_mapping()
            return
        self._editor.loaded(mapping)
        self._error = {}
        self._saved = True
        self._push_mapping()
        self.mappingSaved.emit(mapping)

    def _quick_add(self, barcode: str, sku: str, *, replace: bool) -> str:
        """The one add of a quick map: written at once (ADR 0004)."""
        quick = self._quick
        barcode, sku = clean_mapping(barcode, sku)
        if quick["kind"] == "sku":
            sku = quick["sku"]
        else:
            barcode = quick["barcode"]
            choice = next(
                (c for c in quick["choices"] if c["key"] == normalize_sku(sku)), None
            )
            if not normalize_sku(sku) or choice is None:
                return "Not on this order. Pick one of the lines below."
            sku = choice["sku"]
        if not normalize_sku(barcode):
            return "Enter a barcode."
        clash = self._editor.clash(barcode)
        remove: list[str] = []
        if clash is not None and normalize_sku(clash["sku"]) != normalize_sku(sku):
            if not replace:
                return f"This barcode already maps to {clash['sku']}."
            if clash["barcode"] != barcode:
                remove = [clash["barcode"]]
        try:
            mapping = self._profile_manager.update_sku_mapping(
                self._client, {barcode: sku}, remove
            )
        except ProfileManagerError as error:
            logger.exception("Could not save the quick mapping")
            self._error = mapping_error("quick", str(error), self._mapping_path())
            self._push_mapping()
            return "Not saved. Try again."
        self.quickMapped.emit(quick["kind"], barcode, sku, mapping)
        return ""
