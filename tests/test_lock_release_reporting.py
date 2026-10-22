"""Spec 2026-10-22 section 5b (P#194): a lock that release_lock() could not remove
is logged as a warning, not as released, and leaving the session says so."""

import logging


def _leave_with_lock(main_window, tmp_path, monkeypatch, *, released):
    work_dir = tmp_path / "DHL_Orders"
    work_dir.mkdir()
    main_window.current_work_dir = str(work_dir)
    monkeypatch.setattr(main_window.lock_manager, "release_lock", lambda _work_dir: released)
    toasts = []
    monkeypatch.setattr(
        main_window, "_toast", lambda message, role="success": toasts.append((message, role))
    )
    return toasts


def test_a_failed_release_is_not_logged_as_released(main_window, tmp_path, monkeypatch, caplog):
    _leave_with_lock(main_window, tmp_path, monkeypatch, released=False)

    with caplog.at_level(logging.INFO):
        main_window._teardown_session()

    messages = [record.getMessage() for record in caplog.records]
    assert "Lock released" not in messages
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("not released" in message for message in warnings)


def test_teardown_tells_the_operator_the_lock_stayed(main_window, tmp_path, monkeypatch):
    toasts = _leave_with_lock(main_window, tmp_path, monkeypatch, released=False)

    main_window._teardown_session()

    assert len(toasts) == 1
    message, role = toasts[0]
    assert role == "info"
    assert "DHL_Orders" in message


def test_a_successful_release_still_logs_released(main_window, tmp_path, monkeypatch, caplog):
    toasts = _leave_with_lock(main_window, tmp_path, monkeypatch, released=True)

    with caplog.at_level(logging.INFO):
        main_window._teardown_session()

    assert "Lock released" in [record.getMessage() for record in caplog.records]
    assert toasts == []
