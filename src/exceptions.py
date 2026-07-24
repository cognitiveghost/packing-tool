"""
Custom exceptions for the Packing Tool application.

This module defines application-specific exceptions for better error handling,
user feedback, and debugging. Using custom exceptions allows the application to:
- Provide specific error messages tailored to warehouse operations
- Include contextual information (lock details, validation errors)
- Enable targeted exception handling in UI layer
- Improve logging and error reporting

For small warehouse operations, clear error messages are critical because:
- Workers may not be technical users
- Network/file server issues are common in warehouse environments
- Lock conflicts need user-friendly resolution options
- Validation errors should guide correct data entry

Exception hierarchy:
    PackingToolError (base)
    └── SessionLockedError (session in use by another PC)
        └── StaleLockError (crashed session, can be force-released)
"""

from typing import Dict, Optional


class PackingToolError(Exception):
    """
    Base exception for all Packing Tool errors.

    All application-specific exceptions inherit from this class.
    This allows catching all application errors with a single except clause:
        try:
            # ... application code ...
        except PackingToolError as e:
            # Handle any application error
            logger.error(f"Application error: {e}")

    Note: This does NOT inherit from built-in errors like ValueError, IOError
    to maintain clear separation between application and system errors.
    """


class SessionLockedError(PackingToolError):
    """
    Raised when attempting to access a session actively locked by another process.

    This exception indicates that another PC (or another application instance on
    the same PC) is currently working on this session. The lock is ACTIVE, meaning
    the heartbeat is recent (< 2 minutes), proving the session is in active use.

    For multi-PC warehouse operations, this prevents data corruption from:
    - Two workers packing the same order on different PCs
    - Overwriting each other's progress
    - Conflicting state updates causing data loss

    The exception includes detailed lock information (PC name, username, lock time)
    so the UI can display helpful messages like:
    "Session is locked by John on PC-WAREHOUSE-2. Please wait or choose another session."

    This helps workers coordinate without technical knowledge of file locking.

    Attributes:
        lock_info (Dict): Dictionary containing lock details from .session.lock file
    """

    def __init__(self, message: str, lock_info: Optional[Dict] = None):
        """
        Initialize SessionLockedError with lock details.

        Args:
            message: Brief error message describing the lock situation
                    Example: "Session is locked by another process"

            lock_info: Dictionary containing lock details from .session.lock file:
                - locked_by (str): Hostname of the PC holding the lock
                - user_name (str): Windows username who locked the session
                - lock_time (str): ISO timestamp when lock was acquired
                - heartbeat (str): ISO timestamp of last heartbeat update
                - process_id (int): PID of the locking process
                - app_version (str): Version of the app that created the lock

        Example:
            lock_info = {
                'locked_by': 'PC-WAREHOUSE-2',
                'user_name': 'john.smith',
                'lock_time': '2025-11-03T14:30:00',
                'heartbeat': '2025-11-03T14:32:00',
                'process_id': 12345,
                'app_version': '1.2.0'
            }
            raise SessionLockedError("Session locked", lock_info=lock_info)
        """
        super().__init__(message)
        self.lock_info = lock_info or {}

    def get_display_message(self) -> str:
        """
        Get a user-friendly message for display in UI dialogs.

        Formats the technical lock information into a human-readable message
        that warehouse workers can understand. Uses emoji icons for visual
        clarity and friendly tone.

        Returns:
            Formatted message with lock details, suitable for QMessageBox display

        Example output:
            "This session is currently locked by:

            👤 User: john.smith
            💻 Computer: PC-WAREHOUSE-2
            🕐 Lock time: 2025-11-03T14:30:00

            Please wait for the user to finish, or choose another session."
        """
        if not self.lock_info:
            # Fallback if lock_info wasn't provided (shouldn't happen in practice)
            return str(self)

        # Extract lock details with fallbacks for missing fields
        locked_by = self.lock_info.get('locked_by', 'Unknown PC')
        user_name = self.lock_info.get('user_name', 'Unknown user')
        lock_time = self.lock_info.get('lock_time', 'Unknown time')

        # Format user-friendly message
        return (
            f"This session is currently locked by:\n\n"
            f"👤 User: {user_name}\n"
            f"💻 Computer: {locked_by}\n"
            f"🕐 Lock time: {lock_time}\n\n"
            f"Please wait for the user to finish, or choose another session."
        )


class StaleLockError(SessionLockedError):
    """
    Raised when a session lock exists but appears to be stale (no recent heartbeat).

    A stale lock indicates that the process that locked the session has likely
    crashed or become unresponsive. The lock is considered stale when:
    - Heartbeat hasn't been updated in over 2 minutes (STALE_TIMEOUT = 120 seconds)
    - This suggests the application crashed, PC was forcefully shut down, or
      network connection was lost

    Unlike SessionLockedError (active lock), StaleLockError allows the user
    to force-release the lock and take over the session. This is safe because
    the original process is no longer running.

    For small warehouse operations, this is critical because:
    - Workers need to continue packing even if another PC crashed
    - Manual IT intervention is not always available quickly
    - Orders must be fulfilled on time regardless of technical issues

    The exception provides stale_minutes to help users make informed decisions:
    - "2 minutes stale" -> maybe wait a bit longer (could be network lag)
    - "10 minutes stale" -> definitely crashed, safe to force-release

    Attributes:
        lock_info (Dict): Lock details from .session.lock file
        stale_minutes (int): Minutes since last heartbeat update
    """

    def __init__(self, message: str, lock_info: Optional[Dict] = None, stale_minutes: int = 0):
        """
        Initialize StaleLockError with staleness information.

        Args:
            message: Brief error message
                    Example: "Session has stale lock"

            lock_info: Lock information dictionary (inherited from SessionLockedError)
                      Contains: locked_by, user_name, lock_time, heartbeat, etc.

            stale_minutes: How many minutes since last heartbeat update
                          Calculated as: (now - last_heartbeat) / 60
                          Example: 5 means heartbeat stopped 5 minutes ago

        Example:
            stale_minutes = 10  # Heartbeat stopped 10 minutes ago
            raise StaleLockError(
                "Session has stale lock",
                lock_info=lock_info,
                stale_minutes=stale_minutes
            )
        """
        super().__init__(message, lock_info)
        self.stale_minutes = stale_minutes

    def get_display_message(self) -> str:
        """
        Get user-friendly message for stale lock with force-release option.

        Formats a message that:
        1. Explains the lock is stale (no heartbeat)
        2. Shows original lock holder details
        3. Indicates the original process likely crashed
        4. Offers user the option to force-release the lock

        This empowers warehouse workers to resolve issues themselves without
        requiring IT support.

        Returns:
            Formatted message suitable for confirmation dialog (Yes/No)

        Example output:
            "This session has a stale lock (no heartbeat for 10 minutes).

            👤 Original user: john.smith
            💻 Computer: PC-WAREHOUSE-2
            🕐 Last heartbeat: 2025-11-03T14:30:00
            ❌ Status: No response (possible crash)

            The application may have crashed on that PC.

            You can force-release the lock to open this session."
        """
        if not self.lock_info:
            # Fallback if lock_info wasn't provided
            return str(self)

        # Extract lock details
        locked_by = self.lock_info.get('locked_by', 'Unknown PC')
        user_name = self.lock_info.get('user_name', 'Unknown user')
        heartbeat = self.lock_info.get('heartbeat', 'Unknown')

        # Format user-friendly message with stale duration
        return (
            f"This session has a stale lock (no heartbeat for {self.stale_minutes} minutes).\n\n"
            f"👤 Original user: {user_name}\n"
            f"💻 Computer: {locked_by}\n"
            f"🕐 Last heartbeat: {heartbeat}\n"
            f"❌ Status: No response (possible crash)\n\n"
            f"The application may have crashed on that PC.\n\n"
            f"You can force-release the lock to open this session."
        )
