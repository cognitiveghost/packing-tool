from datetime import datetime

from gui.main_window import _packing_start_time


def test_session_info_wins_when_it_has_a_start():
    got = _packing_start_time({"started_at": "2026-09-24T08:00:00+03:00"}, "2026-09-24T09:00:00+03:00")
    assert got == datetime.fromisoformat("2026-09-24T08:00:00+03:00")


def test_a_shopify_session_falls_back_to_the_packing_state():
    """Spec C1: the Shopify path never writes session_info's start, so the
    duration was None and worker time accrued 0."""
    got = _packing_start_time(None, "2026-09-24T09:00:00+03:00")
    assert got == datetime.fromisoformat("2026-09-24T09:00:00+03:00")


def test_a_naive_stamp_is_read_as_local_time():
    assert _packing_start_time(None, "2026-09-24T09:00:00").tzinfo is not None


def test_nothing_usable_gives_none():
    assert _packing_start_time({"started_at": "garbage"}, None) is None
