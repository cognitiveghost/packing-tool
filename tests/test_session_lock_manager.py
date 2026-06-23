"""
Comprehensive tests for SessionLockManager.

This test suite provides 80%+ coverage of session_lock_manager.py, testing:
- Lock acquisition and release
- Heartbeat mechanism
- Stale lock detection
- Crash recovery scenarios
- Error handling
"""
import pytest
import json
import os
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from session_lock_manager import SessionLockManager


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def temp_session_dir(tmp_path):
    """Create temporary session directory."""
    session_dir = tmp_path / "Session_2025-01-15_120000"
    session_dir.mkdir(parents=True)
    return session_dir


@pytest.fixture
def mock_profile_manager():
    """Create mock ProfileManager."""
    pm = MagicMock()
    pm.list_clients.return_value = ['M', 'R', 'TEST']
    pm.get_incomplete_sessions.return_value = []
    return pm


@pytest.fixture
def lock_manager(mock_profile_manager):
    """Create SessionLockManager instance with mock profile manager."""
    with patch('session_lock_manager.socket.gethostname', return_value='TEST-PC'):
        with patch('session_lock_manager.os.getlogin', return_value='TestUser'):
            manager = SessionLockManager(mock_profile_manager)
            # Mock msvcrt for non-Windows systems
            if not hasattr(manager, '_msvcrt_available'):
                manager._msvcrt_available = False
    return manager


@pytest.fixture
def lock_manager_windows(mock_profile_manager):
    """Create SessionLockManager with Windows file locking mocked."""
    with patch('session_lock_manager.socket.gethostname', return_value='WIN-PC'):
        with patch('session_lock_manager.os.getlogin', return_value='WinUser'):
            with patch('session_lock_manager.WINDOWS_LOCKING_AVAILABLE', True):
                with patch('session_lock_manager.msvcrt'):
                    manager = SessionLockManager(mock_profile_manager)
    return manager


@pytest.fixture
def another_lock_manager(mock_profile_manager):
    """Create second SessionLockManager instance simulating another PC."""
    with patch('session_lock_manager.socket.gethostname', return_value='OTHER-PC'):
        with patch('session_lock_manager.os.getlogin', return_value='OtherUser'):
            manager = SessionLockManager(mock_profile_manager)
    return manager


# ============================================================================
# A. LOCK ACQUISITION & RELEASE TESTS
# ============================================================================

def test_acquire_lock_success(lock_manager, temp_session_dir):
    """Test acquiring lock on free session."""
    # Acquire lock
    success, error_msg, _ = lock_manager.acquire_lock("M", temp_session_dir)

    # Verify success
    assert success is True
    assert error_msg is None

    # Verify lock file was created
    lock_path = temp_session_dir / SessionLockManager.LOCK_FILENAME
    assert lock_path.exists()

    # Verify lock file contents
    with open(lock_path, 'r', encoding='utf-8') as f:
        lock_data = json.load(f)

    assert lock_data['locked_by'] == 'TEST-PC'
    assert lock_data['user_name'] == 'TestUser'
    assert 'lock_time' in lock_data
    assert 'heartbeat' in lock_data
    assert 'process_id' in lock_data
    assert lock_data['process_id'] == os.getpid()


def test_acquire_lock_already_locked(lock_manager, another_lock_manager, temp_session_dir):
    """Test acquiring lock when already locked by another PC."""
    # First PC acquires lock
    success, _, _ = lock_manager.acquire_lock("M", temp_session_dir)
    assert success is True

    # Second PC tries to acquire lock
    success, error_msg, _ = another_lock_manager.acquire_lock("M", temp_session_dir)

    # Should fail with error message
    assert success is False
    assert error_msg is not None
    assert "currently active" in error_msg.lower() or "locked" in error_msg.lower()
    assert "OTHER-PC" not in error_msg  # Should mention the locker, not the requester


def test_release_lock(lock_manager, temp_session_dir):
    """Test releasing lock."""
    # Acquire lock first
    success, _, _ = lock_manager.acquire_lock("M", temp_session_dir)
    assert success is True

    lock_path = temp_session_dir / SessionLockManager.LOCK_FILENAME
    assert lock_path.exists()

    # Release lock
    result = lock_manager.release_lock(temp_session_dir)

    # Verify success
    assert result is True
    assert not lock_path.exists()


def test_lock_file_structure(lock_manager, temp_session_dir):
    """Test .session.lock file contains correct data."""
    # Acquire lock
    lock_manager.acquire_lock("M", temp_session_dir)

    # Read lock file
    lock_path = temp_session_dir / SessionLockManager.LOCK_FILENAME
    with open(lock_path, 'r', encoding='utf-8') as f:
        lock_data = json.load(f)

    # Verify all required fields
    required_fields = ['locked_by', 'user_name', 'lock_time', 'heartbeat', 'process_id', 'app_version']
    for field in required_fields:
        assert field in lock_data, f"Missing required field: {field}"

    # Verify PC name
    assert lock_data['locked_by'] == 'TEST-PC'

    # Verify user name
    assert lock_data['user_name'] == 'TestUser'

    # Verify timestamp format
    datetime.fromisoformat(lock_data['lock_time'])  # Should not raise
    datetime.fromisoformat(lock_data['heartbeat'])  # Should not raise

    # Verify process ID
    assert isinstance(lock_data['process_id'], int)
    assert lock_data['process_id'] > 0


# ============================================================================
# B. HEARTBEAT MECHANISM TESTS
# ============================================================================

def test_heartbeat_updates(lock_manager, temp_session_dir):
    """Test heartbeat updates lock file."""
    # Acquire lock
    lock_manager.acquire_lock("M", temp_session_dir)

    # Read initial heartbeat
    lock_path = temp_session_dir / SessionLockManager.LOCK_FILENAME
    with open(lock_path, 'r', encoding='utf-8') as f:
        initial_data = json.load(f)
    initial_heartbeat = initial_data['heartbeat']

    # Wait a bit
    time.sleep(0.1)

    # Update heartbeat
    result = lock_manager.update_heartbeat(temp_session_dir)
    assert result is True

    # Read updated heartbeat
    with open(lock_path, 'r', encoding='utf-8') as f:
        updated_data = json.load(f)
    updated_heartbeat = updated_data['heartbeat']

    # Verify heartbeat was updated
    assert updated_heartbeat != initial_heartbeat

    # Verify other fields unchanged
    assert updated_data['locked_by'] == initial_data['locked_by']
    assert updated_data['user_name'] == initial_data['user_name']
    assert updated_data['lock_time'] == initial_data['lock_time']


def test_heartbeat_timer_starts(lock_manager, temp_session_dir):
    """Test heartbeat timer starts automatically.

    Note: This tests the mechanism is available, not the automatic timer itself.
    The actual timer would be managed by the application.
    """
    # Acquire lock
    success, _, _ = lock_manager.acquire_lock("M", temp_session_dir)
    assert success is True

    # Verify heartbeat can be updated
    result = lock_manager.update_heartbeat(temp_session_dir)
    assert result is True

    # Verify heartbeat timestamp is recent (within last few seconds)
    lock_path = temp_session_dir / SessionLockManager.LOCK_FILENAME
    with open(lock_path, 'r', encoding='utf-8') as f:
        lock_data = json.load(f)

    heartbeat_time = datetime.fromisoformat(lock_data['heartbeat'])
    now = datetime.now().astimezone()
    time_diff = (now - heartbeat_time).total_seconds()

    assert time_diff < 5  # Heartbeat should be very recent


def test_heartbeat_stops_on_release(lock_manager, temp_session_dir):
    """Test heartbeat stops when lock released."""
    # Acquire lock
    lock_manager.acquire_lock("M", temp_session_dir)

    # Release lock
    lock_manager.release_lock(temp_session_dir)

    # Attempt to update heartbeat should fail (no lock file)
    result = lock_manager.update_heartbeat(temp_session_dir)
    assert result is False


# ============================================================================
# C. STALE LOCK DETECTION TESTS
# ============================================================================

def test_detect_stale_lock(lock_manager, temp_session_dir):
    """Test detection of stale lock (>2 min)."""
    # Create lock with old heartbeat
    old_time = datetime.now().astimezone() - timedelta(minutes=5)
    lock_data = {
        'locked_by': 'OLD-PC',
        'user_name': 'OldUser',
        'lock_time': old_time.isoformat(),
        'heartbeat': old_time.isoformat(),
        'process_id': 12345,
        'app_version': '1.0.0'
    }

    lock_path = temp_session_dir / SessionLockManager.LOCK_FILENAME
    with open(lock_path, 'w', encoding='utf-8') as f:
        json.dump(lock_data, f)

    # Check if lock is stale
    is_locked, lock_info = lock_manager.is_locked(temp_session_dir)
    assert is_locked is True

    is_stale = lock_manager.is_lock_stale(lock_info)
    assert is_stale is True


def test_force_release_stale_lock(lock_manager, temp_session_dir):
    """Test force-releasing stale lock."""
    # Create stale lock
    old_time = datetime.now().astimezone() - timedelta(minutes=5)
    lock_data = {
        'locked_by': 'OLD-PC',
        'user_name': 'OldUser',
        'lock_time': old_time.isoformat(),
        'heartbeat': old_time.isoformat(),
        'process_id': 12345,
        'app_version': '1.0.0'
    }

    lock_path = temp_session_dir / SessionLockManager.LOCK_FILENAME
    with open(lock_path, 'w', encoding='utf-8') as f:
        json.dump(lock_data, f)

    # Verify lock exists and is stale
    is_locked, lock_info = lock_manager.is_locked(temp_session_dir)
    assert is_locked is True
    assert lock_manager.is_lock_stale(lock_info) is True

    # Force-release lock
    result = lock_manager.force_release_lock(temp_session_dir)
    assert result is True

    # Verify lock is gone
    assert not lock_path.exists()

    # Should be able to acquire lock now
    success, _, _ = lock_manager.acquire_lock("M", temp_session_dir)
    assert success is True


def test_fresh_lock_not_stale(lock_manager, temp_session_dir):
    """Test recent lock not detected as stale."""
    # Acquire fresh lock
    lock_manager.acquire_lock("M", temp_session_dir)

    # Check if lock is stale
    is_locked, lock_info = lock_manager.is_locked(temp_session_dir)
    assert is_locked is True

    is_stale = lock_manager.is_lock_stale(lock_info)
    assert is_stale is False


# ============================================================================
# D. CRASH RECOVERY TESTS
# ============================================================================

def test_crash_recovery_scenario(lock_manager, temp_session_dir):
    """Test complete crash recovery workflow."""
    # Step 1: Acquire lock
    success, _, _ = lock_manager.acquire_lock("M", temp_session_dir)
    assert success is True

    # Step 2: Simulate crash - manually set heartbeat to old time
    lock_path = temp_session_dir / SessionLockManager.LOCK_FILENAME
    with open(lock_path, 'r+', encoding='utf-8') as f:
        lock_data = json.load(f)
        # Set heartbeat to 5 minutes ago (simulate crash)
        old_time = datetime.now().astimezone() - timedelta(minutes=5)
        lock_data['heartbeat'] = old_time.isoformat()
        f.seek(0)
        f.truncate()
        json.dump(lock_data, f)

    # Step 3: Verify lock is detected as stale
    is_locked, lock_info = lock_manager.is_locked(temp_session_dir)
    assert is_locked is True
    assert lock_manager.is_lock_stale(lock_info) is True

    # Step 4: Force-release stale lock
    result = lock_manager.force_release_lock(temp_session_dir)
    assert result is True
    assert not lock_path.exists()

    # Step 5: Reacquire lock (recovery complete)
    success, _, _ = lock_manager.acquire_lock("M", temp_session_dir)
    assert success is True
    assert lock_path.exists()


def test_lock_metadata_preserved(lock_manager, temp_session_dir):
    """Test lock metadata available after crash."""
    # Create lock with specific metadata
    old_time = datetime.now().astimezone() - timedelta(minutes=5)
    lock_data = {
        'locked_by': 'CRASHED-PC',
        'user_name': 'CrashedUser',
        'lock_time': old_time.isoformat(),
        'heartbeat': old_time.isoformat(),
        'process_id': 99999,
        'app_version': '1.1.0'
    }

    lock_path = temp_session_dir / SessionLockManager.LOCK_FILENAME
    with open(lock_path, 'w', encoding='utf-8') as f:
        json.dump(lock_data, f)

    # Read lock info
    is_locked, lock_info = lock_manager.is_locked(temp_session_dir)
    assert is_locked is True

    # Verify metadata is preserved
    assert lock_info['locked_by'] == 'CRASHED-PC'
    assert lock_info['user_name'] == 'CrashedUser'
    assert lock_info['process_id'] == 99999
    assert lock_info['app_version'] == '1.1.0'

    # Verify we can get display info for user notification
    display_info = lock_manager.get_lock_display_info(lock_info)
    assert 'CrashedUser' in display_info
    assert 'CRASHED-PC' in display_info


# ============================================================================
# E. ERROR HANDLING TESTS
# ============================================================================

def test_lock_on_read_only_directory(lock_manager, temp_session_dir):
    """Test error when directory is read-only.

    Note: This test is skipped when running as root since root can write
    to read-only directories on Linux.
    """
    # Skip on Windows - different permission model
    if sys.platform == 'win32':
        pytest.skip("Read-only directory test not applicable on Windows")

    # Skip test if running as root (root can write to read-only dirs)
    if hasattr(os, 'geteuid') and os.geteuid() == 0:
        pytest.skip("Test not applicable when running as root")

    # Make directory read-only
    os.chmod(temp_session_dir, 0o444)

    try:
        # Attempt to acquire lock should fail gracefully
        success, error_msg, _ = lock_manager.acquire_lock("M", temp_session_dir)

        assert success is False
        assert error_msg is not None
        assert "failed" in error_msg.lower() or "error" in error_msg.lower()
    finally:
        # Restore permissions for cleanup
        os.chmod(temp_session_dir, 0o755)


def test_concurrent_lock_attempts(lock_manager, another_lock_manager, temp_session_dir):
    """Test multiple PCs trying to lock simultaneously."""
    # PC1 acquires lock
    success1, _, _ = lock_manager.acquire_lock("M", temp_session_dir)
    assert success1 is True

    # PC2 tries to acquire lock (should fail)
    success2, error_msg2, _ = another_lock_manager.acquire_lock("M", temp_session_dir)
    assert success2 is False
    assert error_msg2 is not None

    # PC1 releases lock
    lock_manager.release_lock(temp_session_dir)

    # PC2 can now acquire lock
    success3, _, _ = another_lock_manager.acquire_lock("M", temp_session_dir)
    assert success3 is True


def test_invalid_lock_file_handling(lock_manager, temp_session_dir):
    """Test handling of corrupted lock file."""
    # Create invalid lock file (malformed JSON)
    lock_path = temp_session_dir / SessionLockManager.LOCK_FILENAME
    with open(lock_path, 'w', encoding='utf-8') as f:
        f.write("{ invalid json content }")

    # Should detect as not locked (invalid)
    is_locked, lock_info = lock_manager.is_locked(temp_session_dir)
    assert is_locked is False
    assert lock_info is None

    # Should be able to acquire lock (overwrites invalid file)
    success, _, _ = lock_manager.acquire_lock("M", temp_session_dir)
    assert success is True


def test_release_lock_owned_by_another_process(lock_manager, another_lock_manager, temp_session_dir):
    """Test that we cannot release another process's lock."""
    # PC1 acquires lock
    lock_manager.acquire_lock("M", temp_session_dir)

    # PC2 tries to release PC1's lock
    result = another_lock_manager.release_lock(temp_session_dir)

    # Should fail (cannot release another's lock)
    assert result is False

    # Lock should still exist
    lock_path = temp_session_dir / SessionLockManager.LOCK_FILENAME
    assert lock_path.exists()


# ============================================================================
# F. ADDITIONAL EDGE CASES FOR BETTER COVERAGE
# ============================================================================

def test_acquire_lock_with_stale_lock_returns_error(lock_manager, temp_session_dir):
    """Test that acquiring lock with stale lock present returns proper error."""
    # Create stale lock
    old_time = datetime.now().astimezone() - timedelta(minutes=5)
    lock_data = {
        'locked_by': 'STALE-PC',
        'user_name': 'StaleUser',
        'lock_time': old_time.isoformat(),
        'heartbeat': old_time.isoformat(),
        'process_id': 88888,
        'app_version': '1.0.0'
    }

    lock_path = temp_session_dir / SessionLockManager.LOCK_FILENAME
    with open(lock_path, 'w', encoding='utf-8') as f:
        json.dump(lock_data, f)

    # Try to acquire lock (should fail with stale lock error)
    success, error_msg, _ = lock_manager.acquire_lock("M", temp_session_dir)

    assert success is False
    assert error_msg is not None
    assert "stale" in error_msg.lower()
    assert "StaleUser" in error_msg
    assert "STALE-PC" in error_msg


def test_release_lock_nonexistent(lock_manager, temp_session_dir):
    """Test releasing lock when no lock file exists."""
    # Ensure no lock file exists
    lock_path = temp_session_dir / SessionLockManager.LOCK_FILENAME
    if lock_path.exists():
        lock_path.unlink()

    # Should succeed silently
    result = lock_manager.release_lock(temp_session_dir)
    assert result is True


def test_is_locked_with_missing_fields(lock_manager, temp_session_dir):
    """Test handling lock file with missing required fields."""
    # Create incomplete lock file
    incomplete_lock_data = {
        'locked_by': 'TEST-PC',
        # Missing user_name, lock_time, heartbeat
    }

    lock_path = temp_session_dir / SessionLockManager.LOCK_FILENAME
    with open(lock_path, 'w', encoding='utf-8') as f:
        json.dump(incomplete_lock_data, f)

    # Should detect as invalid (not locked)
    is_locked, lock_info = lock_manager.is_locked(temp_session_dir)
    assert is_locked is False
    assert lock_info is None


def test_is_lock_stale_with_missing_heartbeat(lock_manager):
    """Test stale detection when heartbeat field is missing."""
    lock_info = {
        'locked_by': 'TEST-PC',
        # Missing heartbeat field
    }

    # Should be considered stale
    is_stale = lock_manager.is_lock_stale(lock_info)
    assert is_stale is True


def test_is_lock_stale_with_invalid_heartbeat_format(lock_manager):
    """Test stale detection with invalid heartbeat format."""
    lock_info = {
        'heartbeat': 'invalid-date-format'
    }

    # Should be considered stale (treat parsing error as stale)
    is_stale = lock_manager.is_lock_stale(lock_info)
    assert is_stale is True


def test_get_lock_display_info_with_invalid_timestamp(lock_manager):
    """Test display info formatting with invalid timestamp."""
    lock_data = {
        'locked_by': 'TEST-PC',
        'user_name': 'TestUser',
        'lock_time': 'invalid-timestamp'
    }

    display_info = lock_manager.get_lock_display_info(lock_data)

    # Should handle gracefully and show raw string
    assert 'TestUser' in display_info
    assert 'TEST-PC' in display_info
    assert 'invalid-timestamp' in display_info


def test_get_stale_minutes_with_invalid_heartbeat(lock_manager):
    """Test _get_stale_minutes with invalid heartbeat."""
    lock_info = {
        'heartbeat': 'not-a-date'
    }

    minutes = lock_manager._get_stale_minutes(lock_info)
    # Should return 0 on error
    assert minutes == 0


def test_get_stale_minutes_with_missing_heartbeat(lock_manager):
    """Test _get_stale_minutes with missing heartbeat field."""
    lock_info = {}

    minutes = lock_manager._get_stale_minutes(lock_info)
    assert minutes == 0


# ============================================================================
# G. ADDITIONAL UTILITY TESTS
# ============================================================================

def test_reacquire_own_lock(lock_manager, temp_session_dir):
    """Test reacquiring lock that we already own."""
    # Acquire lock
    success1, _, _ = lock_manager.acquire_lock("M", temp_session_dir)
    assert success1 is True

    # Try to acquire again (should succeed - reacquire own lock)
    success2, error_msg2, _ = lock_manager.acquire_lock("M", temp_session_dir)
    assert success2 is True
    assert error_msg2 is None


def test_get_lock_display_info(lock_manager, temp_session_dir):
    """Test formatting lock information for display."""
    # Create lock
    lock_time = datetime(2025, 1, 15, 14, 30, 0)
    lock_data = {
        'locked_by': 'DISPLAY-PC',
        'user_name': 'DisplayUser',
        'lock_time': lock_time.isoformat(),
        'heartbeat': datetime.now().astimezone().isoformat(),
        'process_id': 11111,
        'app_version': '1.2.0'
    }

    # Get display info
    display_info = lock_manager.get_lock_display_info(lock_data)

    # Verify format
    assert 'DisplayUser' in display_info
    assert 'DISPLAY-PC' in display_info
    assert '15.01.2025' in display_info or '2025' in display_info
    assert '14:30' in display_info


def test_update_heartbeat_for_another_process_lock(lock_manager, another_lock_manager, temp_session_dir):
    """Test that we cannot update heartbeat for another process's lock."""
    # PC1 acquires lock
    lock_manager.acquire_lock("M", temp_session_dir)

    # PC2 tries to update heartbeat
    result = another_lock_manager.update_heartbeat(temp_session_dir)

    # Should fail
    assert result is False


def test_is_lock_stale_with_custom_timeout(lock_manager):
    """Test stale detection with custom timeout."""
    # Create lock info with 1 minute old heartbeat
    one_min_ago = datetime.now().astimezone() - timedelta(minutes=1)
    lock_info = {
        'heartbeat': one_min_ago.isoformat()
    }

    # Should not be stale with 2 minute timeout (default)
    assert lock_manager.is_lock_stale(lock_info, stale_timeout=120) is False

    # Should be stale with 30 second timeout
    assert lock_manager.is_lock_stale(lock_info, stale_timeout=30) is True


def test_get_all_active_sessions(lock_manager, mock_profile_manager, tmp_path):
    """Test retrieving all active sessions across clients."""
    # Setup: Create multiple sessions with locks
    session1 = tmp_path / "Session1"
    session2 = tmp_path / "Session2"
    session3_stale = tmp_path / "Session3"

    session1.mkdir()
    session2.mkdir()
    session3_stale.mkdir()

    # Mock profile manager to return these sessions
    mock_profile_manager.list_clients.return_value = ['M', 'R']
    mock_profile_manager.get_incomplete_sessions.side_effect = lambda client_id: {
        'M': [session1, session3_stale],
        'R': [session2]
    }.get(client_id, [])

    # Create active lock in session1
    lock_data1 = {
        'locked_by': 'PC1',
        'user_name': 'User1',
        'lock_time': datetime.now().astimezone().isoformat(),
        'heartbeat': datetime.now().astimezone().isoformat(),
        'process_id': 1111,
        'app_version': '1.0.0'
    }
    lock_path1 = session1 / SessionLockManager.LOCK_FILENAME
    with open(lock_path1, 'w', encoding='utf-8') as f:
        json.dump(lock_data1, f)

    # Create active lock in session2
    lock_data2 = {
        'locked_by': 'PC2',
        'user_name': 'User2',
        'lock_time': datetime.now().astimezone().isoformat(),
        'heartbeat': datetime.now().astimezone().isoformat(),
        'process_id': 2222,
        'app_version': '1.0.0'
    }
    lock_path2 = session2 / SessionLockManager.LOCK_FILENAME
    with open(lock_path2, 'w', encoding='utf-8') as f:
        json.dump(lock_data2, f)

    # Create stale lock in session3
    old_time = datetime.now().astimezone() - timedelta(minutes=10)
    lock_data3 = {
        'locked_by': 'PC3',
        'user_name': 'User3',
        'lock_time': old_time.isoformat(),
        'heartbeat': old_time.isoformat(),
        'process_id': 3333,
        'app_version': '1.0.0'
    }
    lock_path3 = session3_stale / SessionLockManager.LOCK_FILENAME
    with open(lock_path3, 'w', encoding='utf-8') as f:
        json.dump(lock_data3, f)

    # Get all active sessions
    active_sessions = lock_manager.get_all_active_sessions()

    # Should return only non-stale sessions
    assert 'M' in active_sessions
    assert 'R' in active_sessions
    assert len(active_sessions['M']) == 1  # session3 is stale, should not be included
    assert len(active_sessions['R']) == 1
