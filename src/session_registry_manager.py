"""
Session Registry Manager - Per-client index for fast session browser loading.

Maintains a registry_index.json per client at:
    Sessions/CLIENT_{id}/registry_index.json

This eliminates the need to scan thousands of session directories over the
network file server. Instead of a 15-20 minute scan, the browser reads a
single file per client and resolves only active session lock files to check
heartbeat freshness (typically just a few files).

Update triggers:
    - register_session_start()   → session is in_progress
    - register_session_complete() → session is completed / incomplete
    - register_session_paused()  → session is paused
    - register_available_list()  → new packing list uploaded by Shopify tool
    - ensure_registry()          → first-run migration scan (one time per client)

Design notes:
    - Atomic writes (temp file + rename) prevent partial writes on network drives
    - All registry methods are synchronous; the browser calls them on a background
      thread via RegistryRefreshWorker to keep UI responsive
    - Status values stored in registry: in_progress, paused, completed, incomplete
    - Browser adds stale / abandoned labels at display time (derived from timestamps)
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import logging
from shared.atomic_write import atomic_write_json
from shared.metadata_utils import get_current_timestamp, parse_timestamp

logger = logging.getLogger(__name__)

# Seconds before an "in_progress" heartbeat is considered stale
STALE_HEARTBEAT_SECONDS = 300  # 5 minutes

# Seconds before a session with no summary and no recent activity is "abandoned"
ABANDONED_SECONDS = 86400  # 24 hours


class SessionRegistryManager:
    """
    Manages per-client registry_index.json files on the network file server.

    Each file is a flat JSON index of all sessions and available packing lists
    for a client. The Session Browser reads this single file instead of walking
    the directory tree, reducing load time from minutes to under a second.
    """

    REGISTRY_FILENAME = "registry_index.json"
    REGISTRY_VERSION = "1.0"

    def __init__(self, profile_manager):
        """
        Args:
            profile_manager: ProfileManager instance (uses get_sessions_root()).
        """
        self.profile_manager = profile_manager

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _get_registry_path(self, client_id: str) -> Path:
        """Return path to registry_index.json for the given client."""
        return (
            self.profile_manager.get_sessions_root()
            / f"CLIENT_{client_id}"
            / self.REGISTRY_FILENAME
        )

    def _empty_registry(self, client_id: str) -> dict:
        """Return an empty, versioned registry structure."""
        return {
            "version": self.REGISTRY_VERSION,
            "client_id": client_id,
            "last_updated": "",
            "sessions": {},
            "available_lists": {},
        }

    @staticmethod
    def _session_key(session_id: str, packing_list_name: str) -> str:
        """Composite dict key: '{session_id}::{packing_list_name}'."""
        return f"{session_id}::{packing_list_name}"

    # ------------------------------------------------------------------ #
    #  Read / Write                                                        #
    # ------------------------------------------------------------------ #

    def read_registry(self, client_id: str) -> dict:
        """
        Load registry from disk.

        Returns an empty registry structure if the file is missing or corrupt.
        """
        path = self._get_registry_path(client_id)
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and data.get("version") == self.REGISTRY_VERSION:
                    return data
                logger.warning(
                    f"Registry for client {client_id} has unexpected version/format, using empty."
                )
        except Exception as e:
            logger.warning(f"Could not read registry for client {client_id}: {e}")
        return self._empty_registry(client_id)

    def write_registry(self, client_id: str, registry: dict) -> bool:
        """
        Atomically write registry to disk (temp file + rename).

        Updates registry['last_updated'] before writing.
        Retries up to 3 times with 150 ms backoff to tolerate transient SMB errors.
        Returns True on success, False on failure.
        """
        path = self._get_registry_path(client_id)
        registry["last_updated"] = get_current_timestamp()

        try:
            atomic_write_json(path, registry, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(
                f"Failed to write registry for client {client_id} after 3 attempts: {e}"
            , exc_info=True)
            return False

    def registry_exists(self, client_id: str) -> bool:
        """Return True if registry_index.json already exists for this client."""
        return self._get_registry_path(client_id).exists()

    # ------------------------------------------------------------------ #
    #  First-run migration                                                 #
    # ------------------------------------------------------------------ #

    def ensure_registry(self, client_id: str) -> bool:
        """
        If no registry file exists for client, build it from a directory scan.

        This is the one-time migration path. After this runs, the registry file
        exists and subsequent calls are instant (file already present).

        Returns True if registry is ready (existed or successfully built).
        """
        if self.registry_exists(client_id):
            return True

        logger.info(
            f"No registry for client {client_id} — building from directory scan..."
        )
        try:
            registry = self.build_from_scan(client_id)
            return self.write_registry(client_id, registry)
        except Exception as e:
            logger.error(
                f"Failed to build registry for client {client_id}: {e}", exc_info=True
            )
            return False

    def build_from_scan(self, client_id: str) -> dict:
        """
        Walk the Sessions/CLIENT_{id}/ directory tree and build a registry.

        This is intentionally a full scan — it is only called once per client
        as a migration step when no registry_index.json exists.  After this,
        all updates go through the targeted mutation methods.
        """
        registry = self._empty_registry(client_id)
        client_dir = self.profile_manager.get_sessions_root() / f"CLIENT_{client_id}"

        if not client_dir.exists():
            logger.warning(f"Client directory not found: {client_dir}")
            return registry

        session_count = 0
        try:
            for entry in os.scandir(client_dir):
                if not entry.is_dir():
                    continue
                if entry.name.startswith(".") or entry.name == self.REGISTRY_FILENAME:
                    continue

                session_id = entry.name
                session_dir = Path(entry.path)
                session_count += 1
                self._scan_session_dir(registry, client_id, session_id, session_dir)

        except Exception as e:
            logger.error(f"Error scanning {client_dir}: {e}", exc_info=True)

        logger.info(
            f"Registry scan for client {client_id} complete: "
            f"{session_count} session dirs scanned, "
            f"{len(registry['sessions'])} session entries, "
            f"{len(registry['available_lists'])} available lists"
        )
        return registry

    def _scan_session_dir(
        self,
        registry: dict,
        client_id: str,
        session_id: str,
        session_dir: Path,
    ):
        """
        Examine one timestamped session directory and populate the registry.

        Handles both:
        - Shopify unified workflow: session_dir/packing/{list_name}/ work dirs
        - Legacy Excel workflow:    session_dir/barcodes/ work dir
        """
        # --- Shopify: discover packing lists and their work dirs ---
        packing_lists_dir = session_dir / "packing_lists"
        packing_dir_root = session_dir / "packing"

        if packing_lists_dir.exists():
            for pl_entry in os.scandir(packing_lists_dir):
                if not pl_entry.name.endswith(".json"):
                    continue
                pl_name = Path(pl_entry.name).stem
                work_dir = packing_dir_root / pl_name

                if work_dir.exists():
                    # Session was started for this list
                    self._register_from_work_dir(
                        registry, session_id, pl_name, work_dir, session_dir
                    )
                else:
                    # Packing list uploaded but never started → available
                    self._register_available_from_file(
                        registry, session_id, pl_name, Path(pl_entry.path), session_dir
                    )

        # --- Legacy Excel: session_dir/barcodes/ ---
        barcodes_dir = session_dir / "barcodes"
        if barcodes_dir.exists() and not packing_lists_dir.exists():
            state_file = barcodes_dir / "packing_state.json"
            if state_file.exists():
                try:
                    with open(state_file, "r", encoding="utf-8") as f:
                        state = json.load(f)
                    pl_name = state.get("packing_list_name", "unknown")
                    self._register_from_work_dir(
                        registry, session_id, pl_name, barcodes_dir, session_dir
                    )
                except Exception as e:
                    logger.debug(f"Could not read legacy barcodes state {state_file}: {e}")

    def _register_from_work_dir(
        self,
        registry: dict,
        session_id: str,
        packing_list_name: str,
        work_dir: Path,
        session_dir: Path,
    ):
        """Parse a started-session work directory and add an entry to registry."""
        key = self._session_key(session_id, packing_list_name)

        # Prefer summary (completed) over state file (in-progress / paused)
        summary_file = work_dir / "session_summary.json"
        state_file = work_dir / "packing_state.json"
        lock_file = session_dir / ".session.lock"
        info_file = session_dir / "session_info.json"
        pc_name = os.environ.get("COMPUTERNAME", "Unknown")

        # Read session_info for basic metadata
        session_info = {}
        if info_file.exists():
            try:
                with open(info_file, "r", encoding="utf-8") as f:
                    session_info = json.load(f)
                pc_name = session_info.get("pc_name", pc_name)
            except Exception:
                pass

        if summary_file.exists():
            try:
                with open(summary_file, "r", encoding="utf-8") as f:
                    summary = json.load(f)
                total_orders = summary.get("total_orders", 0)
                completed_orders = summary.get("completed_orders", 0)
                all_done = total_orders > 0 and completed_orders == total_orders
                registry["sessions"][key] = {
                    "session_id": session_id,
                    "packing_list_name": packing_list_name,
                    "status": "completed" if all_done else "incomplete",
                    "worker_id": summary.get("worker_id"),
                    "worker_name": summary.get("worker_name"),
                    "pc_name": summary.get("pc_name", pc_name),
                    "started_at": summary.get("started_at", ""),
                    "last_updated": summary.get("completed_at", ""),
                    "completed_at": summary.get("completed_at"),
                    "duration_seconds": summary.get("duration_seconds"),
                    "total_orders": total_orders,
                    "completed_orders": completed_orders,
                    "skipped_orders": summary.get("skipped_orders_count", 0),
                    "total_items": summary.get("total_items", 0),
                    "work_dir": str(work_dir),
                    "session_path": str(session_dir),
                    "metrics": summary.get("metrics"),
                }
                return
            except Exception as e:
                logger.debug(f"Could not read summary {summary_file}: {e}")

        if state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                progress = state.get("progress", {})

                if lock_file.exists():
                    status = "in_progress"
                elif info_file.exists():
                    status = "paused"
                else:
                    status = "incomplete"

                registry["sessions"][key] = {
                    "session_id": session_id,
                    "packing_list_name": packing_list_name,
                    "status": status,
                    "worker_id": state.get("worker_id"),
                    "worker_name": state.get("worker_name"),
                    "pc_name": state.get("pc_name", pc_name),
                    "started_at": state.get("started_at", ""),
                    "last_updated": state.get("last_updated", ""),
                    "completed_at": None,
                    "duration_seconds": None,
                    "total_orders": progress.get("total_orders", 0),
                    "completed_orders": progress.get("completed_orders", 0),
                    "skipped_orders": len(state.get("skipped_orders", [])),
                    "total_items": progress.get("total_items", 0),
                    "work_dir": str(work_dir),
                    "session_path": str(session_dir),
                    "metrics": None,
                }
            except Exception as e:
                logger.debug(f"Could not read state {state_file}: {e}")

    def _register_available_from_file(
        self,
        registry: dict,
        session_id: str,
        packing_list_name: str,
        pl_file: Path,
        session_dir: Path,
    ):
        """Parse an unstarted packing list JSON and add it to available_lists."""
        key = self._session_key(session_id, packing_list_name)
        try:
            with open(pl_file, "r", encoding="utf-8") as f:
                pl_data = json.load(f)
            # Courier may be under different keys depending on Shopify tool version
            courier = (
                pl_data.get("courier")
                or pl_data.get("filters_applied", {}).get("courier", "")
            )
            registry["available_lists"][key] = {
                "session_id": session_id,
                "packing_list_name": packing_list_name,
                "packing_list_path": str(pl_file),
                "session_path": str(session_dir),
                "courier": courier,
                "created_at": pl_data.get("created_at", ""),
                "total_orders": pl_data.get(
                    "total_orders", len(pl_data.get("orders", []))
                ),
                "total_items": pl_data.get("total_items", 0),
            }
        except Exception as e:
            logger.debug(f"Could not read packing list {pl_file}: {e}")

    # ------------------------------------------------------------------ #
    #  Mutation methods (called during normal app operation)              #
    # ------------------------------------------------------------------ #

    def register_session_start(
        self,
        client_id: str,
        session_id: str,
        packing_list_name: str,
        worker_id: Optional[str],
        worker_name: Optional[str],
        pc_name: str,
        total_orders: int,
        total_items: int,
        work_dir: str,
        session_path: str,
    ) -> bool:
        """
        Add or overwrite a session entry as 'in_progress'.

        Also removes the packing list from available_lists (it has now been started).
        """
        registry = self.read_registry(client_id)
        key = self._session_key(session_id, packing_list_name)
        now = get_current_timestamp()

        registry["sessions"][key] = {
            "session_id": session_id,
            "packing_list_name": packing_list_name,
            "status": "in_progress",
            "worker_id": worker_id,
            "worker_name": worker_name,
            "pc_name": pc_name,
            "started_at": now,
            "last_updated": now,
            "completed_at": None,
            "duration_seconds": None,
            "total_orders": total_orders,
            "completed_orders": 0,
            "skipped_orders": 0,
            "total_items": total_items,
            "work_dir": work_dir,
            "session_path": session_path,
            "metrics": None,
        }

        # Remove the matching available_list entry (same session_id + list_name)
        al_key = self._session_key(session_id, packing_list_name)
        registry["available_lists"].pop(al_key, None)

        return self.write_registry(client_id, registry)

    def register_session_complete(
        self,
        client_id: str,
        session_id: str,
        packing_list_name: str,
        summary: dict,
    ) -> bool:
        """
        Mark a session as 'completed' or 'incomplete' using data from
        session_summary.json.
        """
        registry = self.read_registry(client_id)
        key = self._session_key(session_id, packing_list_name)

        # Create a stub entry if it somehow isn't in the registry yet
        if key not in registry["sessions"]:
            registry["sessions"][key] = {
                "session_id": session_id,
                "packing_list_name": packing_list_name,
                "session_path": "",
                "work_dir": "",
                "started_at": summary.get("started_at", ""),
            }

        total_orders = summary.get("total_orders", 0)
        completed_orders = summary.get("completed_orders", 0)
        all_done = total_orders > 0 and completed_orders == total_orders

        registry["sessions"][key].update(
            {
                "status": "completed" if all_done else "incomplete",
                "worker_id": summary.get("worker_id"),
                "worker_name": summary.get("worker_name"),
                "pc_name": summary.get(
                    "pc_name", registry["sessions"][key].get("pc_name", "")
                ),
                "completed_at": summary.get("completed_at", get_current_timestamp()),
                "last_updated": get_current_timestamp(),
                "duration_seconds": summary.get("duration_seconds"),
                "total_orders": total_orders,
                "completed_orders": completed_orders,
                "skipped_orders": summary.get("skipped_orders_count", 0),
                "total_items": summary.get("total_items", 0),
                "metrics": summary.get("metrics"),
            }
        )
        return self.write_registry(client_id, registry)

    def register_session_paused(
        self,
        client_id: str,
        session_id: str,
        packing_list_name: str,
    ) -> bool:
        """
        Mark a session as 'paused' (worker stepped away without completing).
        Only updates status if the entry exists and is not already completed.
        """
        registry = self.read_registry(client_id)
        key = self._session_key(session_id, packing_list_name)

        if key in registry["sessions"]:
            current_status = registry["sessions"][key].get("status", "")
            if current_status not in ("completed", "incomplete"):
                registry["sessions"][key]["status"] = "paused"
                registry["sessions"][key]["last_updated"] = get_current_timestamp()
                return self.write_registry(client_id, registry)
        return False

    def register_available_list(
        self,
        client_id: str,
        session_id: str,
        packing_list_name: str,
        packing_list_path: str,
        session_path: str,
        metadata: dict,
    ) -> bool:
        """
        Add or update an available packing list in the registry.

        Called when the Session Browser detects a new packing list JSON on the
        server that is not yet represented in the registry.
        """
        registry = self.read_registry(client_id)
        key = self._session_key(session_id, packing_list_name)

        # Don't add to available_lists if a session already exists for this key
        if key in registry["sessions"]:
            return False

        registry["available_lists"][key] = {
            "session_id": session_id,
            "packing_list_name": packing_list_name,
            "packing_list_path": packing_list_path,
            "session_path": session_path,
            "courier": metadata.get("courier", ""),
            "created_at": metadata.get("created_at", ""),
            "total_orders": metadata.get("total_orders", 0),
            "total_items": metadata.get("total_items", 0),
        }
        return self.write_registry(client_id, registry)

    # ------------------------------------------------------------------ #
    #  Read accessors                                                      #
    # ------------------------------------------------------------------ #

    def get_sessions(self, client_id: str) -> list:
        """Return list of all session entry dicts for a client."""
        return list(self.read_registry(client_id).get("sessions", {}).values())

    def get_available_lists(self, client_id: str) -> list:
        """Return list of available packing list dicts for a client."""
        return list(self.read_registry(client_id).get("available_lists", {}).values())

    def get_all_entries(self, client_id: str) -> list:
        """
        Return a combined list of all sessions + available lists with resolved statuses.

        For entries with status 'in_progress', also reads the .session.lock file
        to determine whether the session is truly active or has gone stale.
        Entries with no recent activity are marked 'abandoned'.
        """
        registry = self.read_registry(client_id)
        entries = []

        # --- Sessions (started) ---
        for entry in registry.get("sessions", {}).values():
            resolved = dict(entry)
            resolved["status"] = self._resolve_status(resolved)
            entries.append(resolved)

        # --- Available lists (not yet started) ---
        for entry in registry.get("available_lists", {}).values():
            resolved = dict(entry)
            resolved["status"] = "not_started"
            entries.append(resolved)

        return entries

    # ------------------------------------------------------------------ #
    #  Status resolution                                                   #
    # ------------------------------------------------------------------ #

    def _resolve_status(self, entry: dict) -> str:
        """
        Compute display status from stored registry status + lock file state.

        Stored statuses: in_progress, paused, completed, incomplete
        Display statuses: in_progress, stale, paused, completed, incomplete, abandoned
        """
        stored = entry.get("status", "")

        if stored in ("completed", "incomplete"):
            return stored

        # Check for abandoned: no summary, last activity > 24 hours ago
        last_updated_str = entry.get("last_updated", "") or entry.get("started_at", "")
        if last_updated_str:
            last_updated = parse_timestamp(last_updated_str)
            if last_updated:
                age_seconds = (
                    datetime.now(timezone.utc) - last_updated.astimezone(timezone.utc)
                ).total_seconds()
                if age_seconds > ABANDONED_SECONDS:
                    return "abandoned"

        if stored == "paused":
            return "paused"

        if stored == "in_progress":
            # Check the lock file heartbeat to differentiate active vs stale
            session_path = entry.get("session_path", "")
            if session_path:
                lock_file = Path(session_path) / ".session.lock"
                if lock_file.exists():
                    heartbeat_age = self._get_lock_heartbeat_age(lock_file)
                    if heartbeat_age is not None:
                        return "in_progress" if heartbeat_age < STALE_HEARTBEAT_SECONDS else "stale"
                # Lock file missing but registry says in_progress → treat as paused
                return "paused"

        return stored or "incomplete"

    @staticmethod
    def _get_lock_heartbeat_age(lock_file: Path) -> Optional[float]:
        """
        Read .session.lock and return seconds since last heartbeat.
        Returns None if the file cannot be read or parsed.
        """
        try:
            with open(lock_file, "r", encoding="utf-8") as f:
                lock_data = json.load(f)
            heartbeat_str = lock_data.get("heartbeat") or lock_data.get("lock_time")
            if not heartbeat_str:
                return None
            heartbeat = parse_timestamp(heartbeat_str)
            if heartbeat is None:
                return None
            age = (
                datetime.now(timezone.utc) - heartbeat.astimezone(timezone.utc)
            ).total_seconds()
            return age
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    #  Incremental available-list discovery                               #
    # ------------------------------------------------------------------ #

    def refresh_available_lists(self, client_id: str) -> int:
        """
        Scan packing_lists/ directories for this client and register any new
        available lists that are not yet in the registry.

        This is a lightweight scan — it only lists directories one level deep
        and reads packing list JSON files that are genuinely new (not in registry).

        Returns the number of newly registered lists.
        """
        registry = self.read_registry(client_id)
        client_dir = self.profile_manager.get_sessions_root() / f"CLIENT_{client_id}"
        if not client_dir.exists():
            return 0

        known_keys = set(registry["sessions"].keys()) | set(
            registry["available_lists"].keys()
        )
        new_count = 0
        changed = False

        try:
            for s_entry in os.scandir(client_dir):
                if not s_entry.is_dir():
                    continue
                session_id = s_entry.name
                pl_dir = Path(s_entry.path) / "packing_lists"
                packing_root = Path(s_entry.path) / "packing"
                if not pl_dir.exists():
                    continue

                for pl_entry in os.scandir(pl_dir):
                    if not pl_entry.name.endswith(".json"):
                        continue
                    pl_name = Path(pl_entry.name).stem
                    key = self._session_key(session_id, pl_name)

                    if key in known_keys:
                        continue

                    # New list — check if a work dir exists
                    work_dir = packing_root / pl_name
                    if work_dir.exists():
                        # Session was started; do a full register
                        self._register_from_work_dir(
                            registry, session_id, pl_name, work_dir, Path(s_entry.path)
                        )
                    else:
                        self._register_available_from_file(
                            registry,
                            session_id,
                            pl_name,
                            Path(pl_entry.path),
                            Path(s_entry.path),
                        )
                    known_keys.add(key)
                    new_count += 1
                    changed = True

        except Exception as e:
            logger.error(f"Error scanning for new available lists: {e}", exc_info=True)

        if changed:
            self.write_registry(client_id, registry)

        return new_count
