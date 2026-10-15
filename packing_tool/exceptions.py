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
    └── PackingStateUnreadableError (packing_state.json exists but cannot be read)
    PackingListInvalidError (a ValueError: the list lacks a field every order needs)
"""


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


class PackingStateUnreadableError(PackingToolError):
    """
    Raised when a packing list's packing_state.json exists but cannot be
    read. The session must not open: starting fresh would let the first
    scan overwrite every order already packed (Phase 12 Bundle 2, A1).
    """


class PackingListInvalidError(ValueError):
    """A packing list lacks something every order needs.

    A ValueError, unlike the rest of this module: load_packing_list_json has
    always raised ValueError here, and callers and tests catch that.

    Attributes:
        missing: the field or column names that are absent.
        found: the names that are there.
        kind: "field" (an order's JSON key) or "column".
    """

    def __init__(self, message: str, missing, found, kind: str):
        super().__init__(message)
        self.missing = list(missing)
        self.found = list(found)
        self.kind = kind
