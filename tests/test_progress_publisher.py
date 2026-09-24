from packing_tool.progress_publisher import ProgressPublisher


class FakeSessionManager:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def update_session_metadata(self, session_path, packing_list_name, status, completed_orders=None):
        if self.fail:
            raise OSError("share unavailable")
        self.calls.append((session_path, packing_list_name, status, completed_orders))


class FakeRegistry:
    def __init__(self):
        self.calls = []

    def update_session_progress(self, client_id, session_id, packing_list_name, completed_orders, skipped_orders):
        self.calls.append((client_id, session_id, packing_list_name, completed_orders, skipped_orders))
        return True


def _publisher(sm, reg):
    return ProgressPublisher(sm, reg, "M", "/srv/Sessions/CLIENT_M/2026-09-24_1", "DHL_Orders", sync_mode=True)


def test_publishing_tells_shopify_and_the_registry():
    sm, reg = FakeSessionManager(), FakeRegistry()
    _publisher(sm, reg).publish(["1001", "1002"], 1)
    assert sm.calls == [("/srv/Sessions/CLIENT_M/2026-09-24_1", "DHL_Orders", "in_progress", ["1001", "1002"])]
    assert reg.calls == [("M", "2026-09-24_1", "DHL_Orders", 2, 1)]


def test_a_failing_session_info_write_still_reaches_the_registry():
    sm, reg = FakeSessionManager(fail=True), FakeRegistry()
    _publisher(sm, reg).publish(["1001"], 0)
    assert reg.calls == [("M", "2026-09-24_1", "DHL_Orders", 1, 0)]


def test_close_flushes_the_last_publish_before_returning():
    sm, reg = FakeSessionManager(), FakeRegistry()
    publisher = ProgressPublisher(sm, reg, "M", "/s/2026-09-24_1", "DHL_Orders")  # real thread
    publisher.publish(["1001"], 0)
    publisher.close()
    assert sm.calls[-1][3] == ["1001"]


def test_stop_drops_what_is_pending_so_a_lost_lock_writes_nothing():
    sm, reg = FakeSessionManager(), FakeRegistry()
    publisher = _publisher(sm, reg)
    publisher.stop()
    publisher.publish(["1001"], 0)
    assert sm.calls == [] and reg.calls == []
