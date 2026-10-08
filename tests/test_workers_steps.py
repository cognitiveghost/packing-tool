"""SessionStartWorker names its two steps (spec section 5, frame 3b)."""

from gui.workers import SessionStartWorker


def test_the_start_worker_emits_step_2_then_3(profile_manager, session_factory, qtbot):
    orders = [("#1", "DHL", [{"sku": "A", "quantity": 1, "product_name": "A"}])]
    _session, work_dir, list_path = session_factory(client_id="M", orders=orders)
    worker = SessionStartWorker("M", profile_manager, work_dir, list_path)
    steps = []
    worker.step.connect(steps.append)
    worker.start()
    try:
        assert worker.wait(20000)
        assert worker.error is None
        qtbot.waitUntil(lambda: steps == [2, 3], timeout=5000)
    finally:
        if worker.logic is not None:
            worker.logic.close()
