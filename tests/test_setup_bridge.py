"""SetupBridge: what crosses between Python and the setup document."""

from gui.setup_bridge import CHANNEL_NAME, PAGE, SetupBridge


def test_it_starts_drawing_nothing(qapp):
    bridge = SetupBridge()
    assert bridge.page == ""
    assert bridge.workers == {} and bridge.mapping == {}
    assert PAGE.name == "setup.html" and CHANNEL_NAME == "setup"


def test_a_setter_that_changes_something_notifies_and_raises_the_revision(qapp):
    bridge = SetupBridge()
    seen = []
    bridge.pageChanged.connect(lambda: seen.append("page"))
    bridge.workersChanged.connect(lambda: seen.append("workers"))
    bridge.mappingChanged.connect(lambda: seen.append("mapping"))
    before = bridge.revision

    bridge.set_page("workers")
    bridge.set_workers({"mode": "ready"})
    bridge.set_mapping({"client": "ACME"})

    assert seen == ["page", "workers", "mapping"]
    assert bridge.revision == before + 3
    assert bridge.page == "workers"
    assert bridge.workers == {"mode": "ready"} and bridge.mapping == {"client": "ACME"}


def test_a_setter_that_changes_nothing_is_silent(qapp):
    bridge = SetupBridge()
    bridge.set_workers({"mode": "ready"})
    before = bridge.revision
    bridge.set_page("")
    bridge.set_workers({"mode": "ready"})
    bridge.set_mapping({})
    bridge.set_mapping(None)
    assert bridge.revision == before


def test_the_reporting_slots_emit_their_signals(qapp):
    bridge = SetupBridge()
    seen = []
    bridge.workerPicked.connect(lambda worker_id: seen.append(("pick", worker_id)))
    bridge.workersRetryRequested.connect(lambda: seen.append("retry"))
    bridge.workersLeaveRequested.connect(lambda: seen.append("leave"))
    bridge.mappingDeleteRequested.connect(lambda row_id: seen.append(("delete", row_id)))
    bridge.mappingReloadRequested.connect(lambda: seen.append("reload"))
    bridge.mappingSaveRequested.connect(lambda: seen.append("save"))
    bridge.mappingCloseRequested.connect(lambda: seen.append("close"))
    bridge.strayScanned.connect(lambda text: seen.append(("stray", text)))

    bridge.pickWorker("worker_001")
    bridge.retryWorkers()
    bridge.leaveWorkers()
    bridge.deleteMapping(7)
    bridge.reloadMappings()
    bridge.saveMappings()
    bridge.closeMapping()
    bridge.strayScan("4006381333931")

    assert seen == [
        ("pick", "worker_001"), "retry", "leave", ("delete", 7), "reload", "save", "close",
        ("stray", "4006381333931"),
    ]


def test_the_answering_slots_return_what_the_answer_callable_returns(qapp):
    bridge = SetupBridge()
    calls = []

    def answer(name, *args):
        calls.append((name, args))
        return f"said {name}"

    bridge.answer = answer
    assert bridge.createWorker("Ivan") == "said createWorker"
    assert bridge.addMapping("111", "A") == "said addMapping"
    assert bridge.updateMapping(3, "111", "A") == "said updateMapping"
    assert bridge.replaceMapping(0, "111", "A") == "said replaceMapping"
    assert calls == [
        ("createWorker", ("Ivan",)),
        ("addMapping", ("111", "A")),
        ("updateMapping", (3, "111", "A")),
        ("replaceMapping", (0, "111", "A")),
    ]


def test_with_no_answer_set_the_answering_slots_do_nothing(qapp):
    bridge = SetupBridge()
    assert bridge.createWorker("Ivan") == ""
    assert bridge.addMapping("111", "A") == ""
