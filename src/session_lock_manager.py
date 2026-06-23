"""
Session Lock Manager for preventing concurrent access to sessions.

This module provides file-based locking mechanism to ensure that only one
user can work on a session at a time, with crash recovery support.
"""

import json
import os
import socket
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple
import shutil
import tempfile

# Windows-specific file locking
try:
    import msvcrt
    WINDOWS_LOCKING_AVAILABLE = True
except ImportError:
    WINDOWS_LOCKING_AVAILABLE = False

from logger import AppLogger


class SessionLockManager:
    """
    Manages session locks to prevent concurrent access.

    Features:
    - File-based locking with .session.lock files
    - Heartbeat mechanism to detect crashed sessions
    - Stale lock detection and recovery
    - Detailed lock information for UI display
    """

    LOCK_FILENAME = ".session.lock"
    HEARTBEAT_INTERVAL = 60  # seconds - how often to update heartbeat
    STALE_TIMEOUT = 120  # seconds - lock is stale after 2 minutes without heartbeat

    def __init__(self, profile_manager):
        """
        Initialize SessionLockManager.

        Args:
            profile_manager: ProfileManager instance for accessing session directories
        """
        self.profile_manager = profile_manager
        self.logger = AppLogger.get_logger(self.__class__.__name__)
        self.hostname = socket.gethostname()
        self.username = self._get_username()
        self.process_id = os.getpid()
        self.app_version = "1.3.0"

    def _get_username(self) -> str:
        """
        Get current Windows username.

        Returns:
            Username or 'Unknown' if cannot be determined
        """
        try:
            return os.getlogin()
        except Exception:
            # Fallback to environment variable
            return os.environ.get('USERNAME', 'Unknown')

    def acquire_lock(
        self,
        client_id: str,
        session_dir: Path,
        worker_id: Optional[str] = None,
        worker_name: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[Dict]]:
        """
        Attempt to acquire a lock on the session.

        Args:
            client_id: Client identifier
            session_dir: Path to session directory
            worker_id: Worker ID (e.g., "worker_001")
            worker_name: Worker display name

        Returns:
            Tuple of (success: bool, error_message: Optional[str], lock_info: Optional[Dict])
            - (True, None, None) if lock acquired successfully
            - (False, error_message, lock_info) if session is locked by another process
              (lock_info is None when the failure is a file I/O error)

        Raises:
            IOError: If file operations fail
        """
        lock_path = session_dir / self.LOCK_FILENAME

        # Check if lock already exists
        if lock_path.exists():
            is_locked, lock_info = self.is_locked(session_dir)

            if is_locked:
                # Check if it's our own lock (same PC and process)
                if (lock_info.get('locked_by') == self.hostname and
                    lock_info.get('process_id') == self.process_id):
                    # It's our own lock, just update heartbeat
                    self.logger.info(
                        f"Reacquiring own lock for session {session_dir.name}",
                        extra={"client_id": client_id, "session_dir": str(session_dir)}
                    )
                    self.update_heartbeat(session_dir)
                    return True, None, None
                else:
                    # Check if lock is stale
                    if self.is_lock_stale(lock_info):
                        error_msg = self._format_stale_lock_message(lock_info)
                        self.logger.warning(
                            f"Session has stale lock",
                            extra={
                                "client_id": client_id,
                                "session_dir": str(session_dir),
                                "original_lock_by": lock_info.get('locked_by'),
                                "stale_for_minutes": self._get_stale_minutes(lock_info)
                            }
                        )
                        return False, error_msg, lock_info
                    else:
                        # Active lock by another process
                        error_msg = self._format_active_lock_message(lock_info)
                        self.logger.warning(
                            f"Attempt to open locked session",
                            extra={
                                "client_id": client_id,
                                "session_dir": str(session_dir),
                                "locked_by": lock_info.get('locked_by'),
                                "attempted_by": self.hostname
                            }
                        )
                        return False, error_msg, lock_info

        # Create new lock
        try:
            lock_data = {
                "locked_by": self.hostname,
                "user_name": self.username,
                "lock_time": datetime.now().astimezone().isoformat(),
                "process_id": self.process_id,
                "app_version": self.app_version,
                "heartbeat": datetime.now().astimezone().isoformat(),
                "worker_id": worker_id,
                "worker_name": worker_name
            }

            # Write atomically using temp file
            with tempfile.NamedTemporaryFile(
                mode='w',
                dir=session_dir,
                delete=False,
                encoding='utf-8',
                suffix='.tmp'
            ) as tmp_file:
                json.dump(lock_data, tmp_file, indent=2)
                tmp_path = tmp_file.name

            # Atomic move
            shutil.move(tmp_path, lock_path)

            self.logger.info(
                f"Session lock acquired successfully",
                extra={
                    "client_id": client_id,
                    "session_dir": str(session_dir),
                    "locked_by": self.hostname,
                    "user_name": self.username
                }
            )
            return True, None, None

        except Exception as e:
            self.logger.error(
                f"Failed to acquire lock: {e}",
                extra={"client_id": client_id, "session_dir": str(session_dir)},
                exc_info=True
            )
            return False, f"Failed to create lock file: {e}", None

    def release_lock(self, session_dir: Path) -> bool:
        """
        Release the lock on a session.

        Args:
            session_dir: Path to session directory

        Returns:
            True if lock was released, False otherwise
        """
        lock_path = session_dir / self.LOCK_FILENAME

        if not lock_path.exists():
            self.logger.debug(f"No lock file to release: {lock_path}")
            return True

        try:
            # Verify it's our lock before deleting
            is_locked, lock_info = self.is_locked(session_dir)
            if is_locked:
                if (lock_info.get('locked_by') == self.hostname and
                    lock_info.get('process_id') == self.process_id):
                    # It's our lock, safe to delete
                    lock_path.unlink()
                    self.logger.info(
                        f"Session lock released",
                        extra={"session_dir": str(session_dir)}
                    )
                    return True
                else:
                    # Not our lock, don't delete
                    self.logger.warning(
                        f"Attempted to release lock owned by another process",
                        extra={
                            "session_dir": str(session_dir),
                            "lock_owner": lock_info.get('locked_by'),
                            "attempted_by": self.hostname
                        }
                    )
                    return False
            else:
                # Lock file exists but invalid, safe to delete
                lock_path.unlink()
                return True

        except Exception as e:
            self.logger.error(
                f"Failed to release lock: {e}",
                extra={"session_dir": str(session_dir)},
                exc_info=True
            )
            return False

    def is_locked(self, session_dir: Path) -> Tuple[bool, Optional[Dict]]:
        """
        Check if a session is locked.

        Args:
            session_dir: Path to session directory

        Returns:
            Tuple of (is_locked: bool, lock_info: Optional[Dict])
            - (False, None) if not locked or lock file invalid
            - (True, lock_info_dict) if locked with lock details
        """
        lock_path = session_dir / self.LOCK_FILENAME

        if not lock_path.exists():
            return False, None

        try:
            with open(lock_path, 'r', encoding='utf-8') as f:
                lock_info = json.load(f)

            # Validate lock info has required fields
            required_fields = ['locked_by', 'user_name', 'lock_time', 'heartbeat']
            if not all(field in lock_info for field in required_fields):
                self.logger.warning(
                    f"Invalid lock file (missing fields): {lock_path}",
                    extra={"session_dir": str(session_dir)}
                )
                return False, None

            # Ensure worker fields exist (backward compatibility)
            if 'worker_id' not in lock_info:
                lock_info['worker_id'] = None
            if 'worker_name' not in lock_info:
                lock_info['worker_name'] = None

            return True, lock_info

        except (json.JSONDecodeError, IOError) as e:
            self.logger.warning(
                f"Failed to read lock file: {e}",
                extra={"session_dir": str(session_dir)}
            )
            return False, None

    def update_heartbeat(self, session_dir: Path) -> bool:
        """
        Update the heartbeat timestamp in the lock file.

        This should be called periodically (every 60 seconds) to prove
        the session is still active.

        Args:
            session_dir: Path to session directory

        Returns:
            True if heartbeat updated successfully, False otherwise
        """
        lock_path = session_dir / self.LOCK_FILENAME

        if not lock_path.exists():
            self.logger.warning(
                f"Cannot update heartbeat: lock file doesn't exist",
                extra={"session_dir": str(session_dir)}
            )
            return False

        max_retries = 3
        for attempt in range(max_retries):
            try:
                with open(lock_path, 'r+', encoding='utf-8') as f:
                    # Acquire exclusive lock (Windows only)
                    _lock_nbytes = max(1, os.fstat(f.fileno()).st_size)
                    if WINDOWS_LOCKING_AVAILABLE:
                        try:
                            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, _lock_nbytes)
                        except IOError:
                            # File is locked by another process, retry
                            if attempt < max_retries - 1:
                                time.sleep(0.1)
                                continue
                            else:
                                raise

                    try:
                        # Read current data
                        f.seek(0)
                        data = json.load(f)

                        # Verify it's our lock
                        if (data.get('locked_by') != self.hostname or
                            data.get('process_id') != self.process_id):
                            self.logger.warning(
                                f"Attempted to update heartbeat for lock owned by another process",
                                extra={"session_dir": str(session_dir)}
                            )
                            return False

                        # Update heartbeat
                        data['heartbeat'] = datetime.now().astimezone().isoformat()

                        # Write back
                        f.seek(0)
                        f.truncate()
                        json.dump(data, f, indent=2)

                        self.logger.debug(
                            f"Heartbeat updated",
                            extra={"session_dir": str(session_dir)}
                        )
                        return True

                    finally:
                        # Release lock (Windows only)
                        if WINDOWS_LOCKING_AVAILABLE:
                            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, _lock_nbytes)

            except (IOError, OSError, json.JSONDecodeError) as e:
                # Network issue or file error - don't crash
                self.logger.warning(
                    f"Failed to update heartbeat (attempt {attempt + 1}/{max_retries}): {e}",
                    extra={"session_dir": str(session_dir)}
                )
                if attempt < max_retries - 1:
                    time.sleep(0.5)
                else:
                    return False

        return False

    def is_lock_stale(self, lock_info: Dict, stale_timeout: Optional[int] = None) -> bool:
        """
        Check if a lock is stale (no recent heartbeat).

        Args:
            lock_info: Lock information dictionary
            stale_timeout: Optional timeout in seconds (default: STALE_TIMEOUT)

        Returns:
            True if lock is stale, False otherwise
        """
        if stale_timeout is None:
            stale_timeout = self.STALE_TIMEOUT

        try:
            heartbeat_str = lock_info.get('heartbeat')
            if not heartbeat_str:
                return True

            from shared.metadata_utils import parse_timestamp
            heartbeat_time = parse_timestamp(heartbeat_str)
            if not heartbeat_time:
                return True  # Can't parse, consider stale
            now = datetime.now().astimezone()
            elapsed = (now - heartbeat_time).total_seconds()

            return elapsed > stale_timeout

        except (ValueError, TypeError) as e:
            self.logger.warning(f"Failed to parse heartbeat time: {e}")
            return True  # Treat invalid heartbeat as stale

    def force_release_lock(self, session_dir: Path) -> bool:
        """
        Forcefully release a lock, regardless of who owns it.

        This should only be used for stale locks (crash recovery).

        Args:
            session_dir: Path to session directory

        Returns:
            True if lock was released, False otherwise
        """
        lock_path = session_dir / self.LOCK_FILENAME

        if not lock_path.exists():
            return True

        try:
            # Get lock info for logging
            is_locked, lock_info = self.is_locked(session_dir)

            # Delete the lock file
            lock_path.unlink()

            if lock_info:
                stale_minutes = self._get_stale_minutes(lock_info)
                self.logger.warning(
                    f"Stale lock force-released",
                    extra={
                        "session_dir": str(session_dir),
                        "original_lock_by": lock_info.get('locked_by'),
                        "released_by": self.hostname,
                        "stale_for_minutes": stale_minutes
                    }
                )
            else:
                self.logger.info(
                    f"Invalid lock file removed",
                    extra={"session_dir": str(session_dir)}
                )

            return True

        except Exception as e:
            self.logger.error(
                f"Failed to force-release lock: {e}",
                extra={"session_dir": str(session_dir)},
                exc_info=True
            )
            return False

    def get_lock_display_info(self, lock_info: Dict) -> str:
        """
        Format lock information for display to user.

        Args:
            lock_info: Lock information dictionary

        Returns:
            Formatted string for UI display
        """
        locked_by = lock_info.get('locked_by', 'Unknown')
        user_name = lock_info.get('user_name', 'Unknown')
        lock_time = lock_info.get('lock_time', 'Unknown')

        # Format time nicely
        try:
            from shared.metadata_utils import parse_timestamp
            lock_dt = parse_timestamp(lock_time)
            if lock_dt:
                lock_time_formatted = lock_dt.strftime('%d.%m.%Y %H:%M')
            else:
                lock_time_formatted = lock_time
        except (ValueError, TypeError):
            lock_time_formatted = lock_time

        return (
            f"Locked by: {user_name}\n"
            f"Computer: {locked_by}\n"
            f"Since: {lock_time_formatted}"
        )

    def _get_stale_minutes(self, lock_info: Dict) -> int:
        """Get how many minutes the lock has been stale."""
        try:
            heartbeat_str = lock_info.get('heartbeat')
            if not heartbeat_str:
                return 0

            from shared.metadata_utils import parse_timestamp
            heartbeat_time = parse_timestamp(heartbeat_str)
            if not heartbeat_time:
                return 0
            now = datetime.now().astimezone()
            elapsed_minutes = int((now - heartbeat_time).total_seconds() / 60)
            return elapsed_minutes

        except (ValueError, TypeError):
            return 0

    def _format_active_lock_message(self, lock_info: Dict) -> str:
        """Format error message for active lock."""
        locked_by = lock_info.get('locked_by', 'Unknown PC')
        user_name = lock_info.get('user_name', 'Unknown user')

        return (
            f"Session is currently active on another PC:\n"
            f"👤 {user_name} on 💻 {locked_by}\n"
            f"Please wait or choose another session."
        )

    def _format_stale_lock_message(self, lock_info: Dict) -> str:
        """Format error message for stale lock."""
        locked_by = lock_info.get('locked_by', 'Unknown PC')
        user_name = lock_info.get('user_name', 'Unknown user')
        stale_minutes = self._get_stale_minutes(lock_info)

        return (
            f"Session has a stale lock (no heartbeat for {stale_minutes} minutes):\n"
            f"👤 {user_name} on 💻 {locked_by}\n"
            f"The application may have crashed.\n"
            f"You can force-release the lock."
        )

    def get_all_active_sessions(self) -> Dict[str, list]:
        """
        Get all active sessions across all clients.

        Returns:
            Dictionary mapping client_id to list of active session info dicts:
            {
                'M': [
                    {
                        'session_name': 'Session_2025-10-28_143045',
                        'session_dir': Path(...),
                        'lock_info': {...}
                    },
                    ...
                ],
                'R': [...],
                ...
            }
        """
        all_sessions = {}

        try:
            clients = self.profile_manager.list_clients()

            for client_id in clients:
                sessions = self.profile_manager.get_incomplete_sessions(client_id)
                active_sessions = []

                for session_dir in sessions:
                    is_locked, lock_info = self.is_locked(session_dir)

                    if is_locked and not self.is_lock_stale(lock_info):
                        # Active (non-stale) lock
                        active_sessions.append({
                            'session_name': session_dir.name,
                            'session_dir': session_dir,
                            'lock_info': lock_info
                        })

                if active_sessions:
                    all_sessions[client_id] = active_sessions

        except Exception as e:
            self.logger.error(f"Failed to get all active sessions: {e}", exc_info=True)

        return all_sessions
