"""The setup document's bridge (ADR 0002, ADR 0004).

One web document draws the two full-window pages: Worker selection and SKU
mapping. State Python owns crosses as a notify property; what the page
reports crosses as a slot. Four slots answer, because the page must know
whether to clear what was typed: they return "" when the thing was done,
else the sentence to show beside the field.

Spec: docs/superpowers/specs/2026-10-09-ui-refresh-phase5-setup-pages-design.md
"""

from pathlib import Path

from PySide6.QtCore import Property, Signal, Slot
from PySide6.QtWebEngineWidgets import QWebEngineView

from gui.theme import current_tokens
from shared.web_page import PageBridge, mount_page

PAGE = Path(__file__).resolve().parent / "web" / "setup.html"
CHANNEL_NAME = "setup"


class SetupBridge(PageBridge):
    pageChanged = Signal()
    workersChanged = Signal()
    mappingChanged = Signal()

    # JS-facing: raise the "Discard unsaved changes?" question (section 6.6).
    leaveAsked = Signal()

    # Python-facing: what the page reported.
    workerPicked = Signal(str)
    workersRetryRequested = Signal()
    workersLeaveRequested = Signal()
    mappingDeleteRequested = Signal(int)
    mappingReloadRequested = Signal()
    mappingSaveRequested = Signal()
    mappingCloseRequested = Signal()
    strayScanned = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._page = ""
        self._workers: dict = {}
        self._mapping: dict = {}
        # Set by SetupPages: (slot name, *args) -> "" or a sentence.
        self.answer = lambda name, *args: ""

    # --- out: Python -> JS -------------------------------------------------

    def _get_page(self) -> str:
        return self._page

    page = Property(str, _get_page, notify=pageChanged)

    def _get_workers(self) -> dict:
        return self._workers

    workers = Property("QVariantMap", _get_workers, notify=workersChanged)

    def _get_mapping(self) -> dict:
        return self._mapping

    mapping = Property("QVariantMap", _get_mapping, notify=mappingChanged)

    # --- in: JS -> Python --------------------------------------------------

    @Slot(str)
    def pickWorker(self, worker_id) -> None:
        self.workerPicked.emit(str(worker_id))

    @Slot()
    def retryWorkers(self) -> None:
        self.workersRetryRequested.emit()

    @Slot()
    def leaveWorkers(self) -> None:
        self.workersLeaveRequested.emit()

    @Slot(str, result=str)
    def createWorker(self, name) -> str:
        return str(self.answer("createWorker", str(name)))

    @Slot(str, str, result=str)
    def addMapping(self, barcode, sku) -> str:
        return str(self.answer("addMapping", str(barcode), str(sku)))

    @Slot(int, str, str, result=str)
    def updateMapping(self, row_id, barcode, sku) -> str:
        return str(self.answer("updateMapping", int(row_id), str(barcode), str(sku)))

    @Slot(int, str, str, result=str)
    def replaceMapping(self, row_id, barcode, sku) -> str:
        return str(self.answer("replaceMapping", int(row_id), str(barcode), str(sku)))

    @Slot(int)
    def deleteMapping(self, row_id) -> None:
        self.mappingDeleteRequested.emit(int(row_id))

    @Slot()
    def reloadMappings(self) -> None:
        self.mappingReloadRequested.emit()

    @Slot()
    def saveMappings(self) -> None:
        self.mappingSaveRequested.emit()

    @Slot()
    def closeMapping(self) -> None:
        self.mappingCloseRequested.emit()

    @Slot(str)
    def strayScan(self, text) -> None:
        self.strayScanned.emit(str(text))

    # --- Python-facing API -------------------------------------------------
    # A setter that changes nothing emits nothing, so an idle push does not
    # raise the revision.

    def set_page(self, name: str) -> None:
        if name != self._page:
            self._page = str(name)
            self.pageChanged.emit()

    def set_workers(self, payload: dict | None) -> None:
        payload = dict(payload or {})
        if payload != self._workers:
            self._workers = payload
            self.workersChanged.emit()

    def set_mapping(self, payload: dict | None) -> None:
        payload = dict(payload or {})
        if payload != self._mapping:
            self._mapping = payload
            self.mappingChanged.emit()


def mount_setup_page(view: QWebEngineView) -> SetupBridge:
    """Load the setup document into `view` and return the bridge it talks to.

    The view keeps its focus policy: both pages have text fields. Packer
    Mode's view is the one that refuses the keyboard (ADR 0001).
    """
    bridge = SetupBridge(view)
    mount_page(view, bridge, PAGE, CHANNEL_NAME, tokens=current_tokens)
    return bridge
