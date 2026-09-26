"""Tell Shopify Tool and the Session Browser what a session has packed so far.

Shopify's repeat detection reads the packed-order signal from the session's
session_info.json; the Session Browser reads counts from the session
registry. Both used to hear only at End session, so a paused, overnight or
crashed list stayed invisible (Phase 12 Bundle 2, E1 / D4).

Each publish is a locked read-modify-write on the share, so it runs on
AsyncStateWriter's background thread; a later publish replaces one not yet
written, and both files take cumulative values, so the latest is enough.
Best-effort by contract, as on Shopify's side: a failure is logged, never
raised into packing.
"""

import logging
from pathlib import Path

from packing_tool.async_state_writer import AsyncStateWriter

logger = logging.getLogger(__name__)


class ProgressPublisher:
    def __init__(
        self,
        session_manager,
        registry_manager,
        client_id: str,
        session_path: str,
        packing_list_name: str,
        *,
        sync_mode: bool = False,
    ):
        self._session_manager = session_manager
        self._registry_manager = registry_manager
        self._client_id = client_id
        self._session_path = str(session_path)
        self._list_name = packing_list_name
        self._stopped = False
        self._writer = AsyncStateWriter(self._write, sync_mode=sync_mode)

    def publish(
        self, completed_orders: list[str], skipped_count: int, completed_count: int | None = None
    ) -> None:
        """completed_orders is every packed order, for Shopify; completed_count,
        when given, is the registry's count (orders the list still holds)."""
        self._writer.schedule(
            {
                "completed_orders": list(completed_orders),
                "skipped_count": int(skipped_count),
                "completed_count": (
                    len(completed_orders) if completed_count is None else int(completed_count)
                ),
            }
        )

    def close(self) -> None:
        """Write whatever is pending, then stop. Call before the final End-session write."""
        self._writer.shutdown()

    def stop(self) -> None:
        """Drop every write from now on, pending ones included, and shut down.

        For a PC that lost its session lock: the new owner's files are the
        live ones (spec B3).
        """
        self._stopped = True
        self.close()

    def _write(self, snapshot: dict) -> None:
        if self._stopped:
            return
        completed = snapshot["completed_orders"]
        try:
            self._session_manager.update_session_metadata(
                self._session_path,
                self._list_name,
                "in_progress",
                completed_orders=completed,
            )
        except Exception:
            logger.exception("Could not publish packed orders to session_info.json")
        try:
            if self._registry_manager is not None:
                self._registry_manager.update_session_progress(
                    self._client_id,
                    Path(self._session_path).name,
                    self._list_name,
                    snapshot["completed_count"],
                    snapshot["skipped_count"],
                )
        except Exception:
            logger.exception("Could not publish progress to the session registry")
