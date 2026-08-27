# Packer's Assistant

**Version:** 1.3.2.0 (Pre-release) | **Last Updated:** 2026-02-24

---

## What It Does

Packer's Assistant is a Windows desktop application for warehouse order fulfillment. It works
as the execution stage of a two-tool workflow: Shopify Tool prepares sessions and packing lists
from Shopify orders, and Packer's Assistant is used on the warehouse floor to scan and verify
packed items against those lists.

The application loads a session created by Shopify Tool, then guides a warehouse worker through
scanning order barcodes and product SKU barcodes to confirm that each item has been packed
correctly. Progress is saved after every scan so sessions can be resumed across restarts or
transferred between PCs.

---

## Features

### Packing Workflow

- Load sessions and packing lists from Shopify Tool
- Barcode-scanner-driven packing: scan order barcode to load an order, scan product barcodes to
  pack items
- Automatic order number normalization — scanned barcodes are matched to orders without manual
  mapping
- Per-item confirmation and force-complete controls for edge cases
- Skip an order mid-pack and resume it later in the same session
- Extra-item detection when more units are scanned than required

### Session Management

- Session Browser with three tabs: Active (in-progress), Completed (historical), Available
  (ready to start)
- File-based session locking with heartbeat — prevents two PCs from opening the same session
  simultaneously; stale locks are automatically released
- Crash recovery: incomplete sessions are detected on next startup and offered for restore
- State saved asynchronously after every scan for low latency on hot paths
- Per-session completion reports and statistics

### Interface

- Packer Mode: dedicated scanning view with order metadata panel, per-item status table,
  session-wide progress bar, and scan history
- Dark and light themes (QSS-based)
- Worker selection at startup for multi-worker environments
- SKU mapping management for barcode-to-internal-SKU translation

### Multi-PC Support

- Centralized file server storage (SMB/CIFS share) shared between all warehouse PCs and Shopify
  Tool
- File-based session locking prevents concurrent edits
- Shared statistics across all PCs via a common stats file with safe concurrent access

---

## System Requirements

- Windows 10 or 11
- Python 3.14 or later (or the pre-built `.exe`)
- Network access to the shared file server
- Shopify Tool v1.8.6.0 or later (required to create sessions)
- Barcode scanner (USB HID keyboard-emulation type)

---

## Shopify Tool Integration

All sessions are created by Shopify Tool. Packer's Assistant reads from the same shared directory
structure and writes its packing progress back into it.

### Directory Structure

```text
Sessions/
└── CLIENT_NAME/
    └── YYYY-MM-DD_N/
        ├── session_info.json           # Session metadata
        ├── analysis/
        │   └── analysis_data.json      # Order data from Shopify Tool
        ├── packing_lists/
        │   └── Courier_Orders.json     # Courier-filtered packing list
        └── packing/
            └── DHL_Orders/             # Work directory per packing list
                ├── packing_state.json  # Packing progress (written by Packer's Assistant)
                └── reports/            # Completion reports
```

### Workflow

1. Use Shopify Tool to analyze orders and create a session directory.
2. In Packer's Assistant, open the session via Session Browser > Available Sessions.
3. Select a packing list (or load from the full analysis).
4. Click Start Packing and scan items in the warehouse.
5. End session when complete — a summary report is written and statistics are recorded.

---

## Technical Overview

### Architecture

The application uses a four-layer design: Presentation (PySide6 widgets), Business Logic
(PackerLogic, SessionManager), Data Access (ProfileManager, SessionLockManager,
SessionHistoryManager), and Storage (file server JSON files).

Communication between layers uses Qt Signals/Slots. All file I/O that would block the UI runs
in QThread workers.

### Key Source Files

| File | Responsibility |
| ---- | -------------- |
| `main.py` | Entry point (argument parsing, QApplication startup) |
| `gui/main_window.py` | Main window, session orchestration |
| `gui/workers.py` | Background QThread workers for session start/end |
| `packing_tool/packer_logic.py` | Order loading, barcode scan processing, state machine |
| `gui/packer_mode_widget.py` | Scanning UI widget (3-column layout) |
| `packing_tool/session_manager.py` | Session lifecycle, directory creation |
| `packing_tool/session_lock_manager.py` | File-based locking with heartbeat |
| `packing_tool/session_history_manager.py` | Historical session queries |
| `packing_tool/async_state_writer.py` | Write-behind queue for packing_state.json |
| `packing_tool/profile_manager.py` | Client profiles, SKU mappings, file server I/O |
| `gui/session_browser/` | Session Browser widget and tab implementations |
| `gui/session_selector.py` | Dialog for selecting an available Shopify session |
| `gui/sku_mapping_dialog.py` | Barcode-to-SKU mapping editor |
| `gui/worker_selection_dialog.py` | Worker selection at startup |
| `packing_tool/json_cache.py` | JSON file caching layer |
| `gui/theme.py` | Dark/light theme switching |
| `packing_tool/worker_manager.py` | Worker profile management |
| `shared/stats_manager.py` | Unified statistics (shared with Shopify Tool) |

### State Persistence

`packing_state.json` is the source of truth for session progress:

```json
{
  "in_progress": {
    "ORDER-001": [
      {"original_sku": "SKU-A", "required": 5, "packed": 3},
      {"original_sku": "SKU-B", "required": 2, "packed": 1}
    ]
  },
  "completed_orders": ["ORDER-002"],
  "skipped_orders": ["ORDER-003"]
}
```

Writes go through `AsyncStateWriter` (a write-behind queue) on hot paths (every scan), and are
flushed synchronously on session end and teardown.

---

## Development Setup

### Prerequisites

- Python 3.9+
- A file server path configured in `config.dev.ini`

### Installation

```bash
git clone https://github.com/cognitiveclodfr/packing-tool.git
cd packing-tool
pip install -r requirements.txt
```

### Running

```bash
python main.py --config config.dev.ini
```

### Testing

Tests were removed for a rewrite and are not present in this checkout.

### Running against a local dev server

`run_dev.py` points the app at the shared `dev-server/` mock file server used by Shopify Tool
(sibling repo), instead of the production network share:

```bash
python run_dev.py
```

---

## Links

- Issues: [github.com/cognitiveclodfr/packing-tool/issues](https://github.com/cognitiveclodfr/packing-tool/issues)
- Releases: [github.com/cognitiveclodfr/packing-tool/releases](https://github.com/cognitiveclodfr/packing-tool/releases)
