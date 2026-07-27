"""
Async write-behind queue for packing state files.

Eliminates UI freezes caused by synchronous writes to a slow network share.
The latest state is always kept in a single pending slot — never accumulates stale writes.
"""

import copy
import logging
import threading
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class AsyncStateWriter:
    """
    Write-behind queue for state persistence.

    Behaviour:
    - schedule(state_dict): non-blocking, replaces any pending write
    - flush(): blocking, waits until the background thread has finished writing
    - shutdown(): flush then stop daemon thread

    Concurrency model:
    - schedule() and flush() must only be called from the main/UI thread
    - Background daemon thread calls the write_fn
    - Incoming state_dict is deep-copied on schedule() so the caller can freely
      mutate its in-memory state immediately after scheduling

    sync_mode=True skips the background thread and writes synchronously;
    useful for unit tests that assert file content after each call.
    """

    def __init__(
        self,
        write_fn: Callable[[dict[str, Any]], None],
        sync_mode: bool = False,
    ) -> None:
        self._write_fn = write_fn
        self._sync_mode = sync_mode

        if sync_mode:
            return  # No thread needed

        self._condition = threading.Condition()
        self._pending: dict[str, Any] | None = None
        self._is_writing: bool = False  # True while write_fn is executing
        self._stop = False
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="state-writer"
        )
        self._thread.start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def schedule(self, state_dict: dict[str, Any]) -> None:
        """
        Non-blocking: schedule state_dict for writing.

        If a previous write is still pending (not yet started), it is replaced
        by this newer state — only the latest state ever reaches disk.

        A deep copy of state_dict is made immediately so the caller is free to
        continue mutating its in-memory state without risking torn writes.
        """
        if self._sync_mode:
            self._write_fn(state_dict)
            return

        snapshot = copy.deepcopy(state_dict)
        with self._condition:
            self._pending = snapshot
            self._condition.notify()

    def flush(self) -> None:
        """
        Blocking: wait until no pending write remains AND the current write (if
        any) has completed.

        Call before checkpoints (order complete, session end) to guarantee
        the latest state is on disk before proceeding.
        Must be called from the main/UI thread only.
        """
        if self._sync_mode:
            return  # Already written synchronously

        with self._condition:
            while self._pending is not None or self._is_writing:
                self._condition.wait()

    def shutdown(self) -> None:
        """
        Flush any pending write then stop the background thread.

        Safe to call multiple times; subsequent calls are no-ops.
        """
        if self._sync_mode:
            return

        self.flush()
        with self._condition:
            self._stop = True
            self._condition.notify()
        self._thread.join(timeout=10)

    # ------------------------------------------------------------------
    # Background thread
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while True:
            with self._condition:
                # Wait until there is work to do or we should stop
                while self._pending is None and not self._stop:
                    self._condition.wait()

                if self._stop and self._pending is None:
                    break

                state = self._pending
                self._pending = None      # Claim the work
                self._is_writing = True   # Signal that a write is in progress

            # Perform the write outside the lock so schedule() is never blocked
            try:
                self._write_fn(state)
            except Exception:
                logger.exception("AsyncStateWriter: write failed")
            finally:
                with self._condition:
                    self._is_writing = False
                    self._condition.notify_all()  # Wake flush() waiters
