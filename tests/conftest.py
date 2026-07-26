"""Shared fixtures for the backend test suite.

Design notes:
- Tests exercise real collaborators (real ProfileManager, real file I/O,
  real AsyncStateWriter background thread) rather than mocks, since the
  goal of this suite is to validate actual persistence/scanning behavior,
  not to re-describe the code in different words.
- AppLogger is neutralized before any app module is imported: its default
  config falls back to a hardcoded Windows UNC path
  (\\\\192.168.88.101\\_Fulfilment_\\0UFulfilment) which, on POSIX, is
  treated as a single literal directory name and gets created in the repo
  root the first time any module calls get_logger().
"""
import os
import sys
import json
import configparser
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import pytest

from logger import AppLogger
AppLogger._initialized = True  # skip real _setup_logging(); avoid UNC-path side effects

from PySide6.QtWidgets import QApplication
from profile_manager import ProfileManager
from packer_logic import PackerLogic


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """A QApplication is required for QObject subclasses with Signals (PackerLogic)."""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _clear_fulfillment_server_path_env(monkeypatch):
    """Hermetic tests: FULFILLMENT_SERVER_PATH must not leak in from the
    developer's shell (e.g. left set from working on the sibling
    shopify-fulfillment-tool repo), or every fixture that builds a
    ProfileManager from config_ini would silently redirect to whatever
    that variable points at instead of the tmp_path server_root.
    """
    monkeypatch.delenv("FULFILLMENT_SERVER_PATH", raising=False)


@pytest.fixture(scope="session", autouse=True)
def _isolate_qsettings(tmp_path_factory):
    """Hermetic tests: resolve_server_path's QSettings layer must not read
    (or write) the developer's real "PackingTool"/"Connection" settings —
    a path saved via the Server Connection dialog on this machine would
    otherwise silently override the tmp_path server_root used everywhere
    below, the same class of leak _clear_fulfillment_server_path_env guards
    against for the env var.
    """
    from PySide6.QtCore import QSettings
    settings_dir = tmp_path_factory.mktemp("qsettings")
    # QSettings(org, app) uses NativeFormat; redirect both formats since
    # setPath only affects settings objects of the format it's given.
    QSettings.setPath(QSettings.NativeFormat, QSettings.UserScope, str(settings_dir))
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(settings_dir))


@pytest.fixture
def server_root(tmp_path):
    root = tmp_path / "server"
    root.mkdir()
    return root


@pytest.fixture
def config_ini(tmp_path, server_root):
    path = tmp_path / "config.ini"
    config = configparser.ConfigParser()
    config["Network"] = {
        "FileServerPath": str(server_root),
        "ConnectionTimeout": "5",
        "LocalCachePath": str(tmp_path / "cache"),
    }
    config["Logging"] = {"LogLevel": "INFO", "LogRetentionDays": "30", "MaxLogSizeMB": "10"}
    with open(path, "w", encoding="utf-8") as f:
        config.write(f)
    return path


@pytest.fixture
def profile_manager(config_ini):
    return ProfileManager(config_path=str(config_ini))


def make_packing_list(orders):
    """Build a minimal Shopify-Tool-style packing list dict.

    orders: list of (order_number, courier, items) where items is a list of
    dicts with keys sku/quantity/product_name (extra keys allowed).
    """
    return {
        "list_name": "Test_Orders",
        "created_at": "2026-01-01T10:00:00+00:00",
        "orders": [
            {
                "order_number": order_number,
                "courier": courier,
                "items": items,
            }
            for order_number, courier, items in orders
        ],
    }


@pytest.fixture
def session_factory(server_root):
    """Create a Sessions/CLIENT_<id>/<session_id>/ tree with a packing_lists JSON
    and return (work_dir, packing_list_path) for load_packing_list_json().
    """

    def _make(client_id="M", session_id="2026-01-01_1", list_name="DHL_Orders", orders=()):
        session_dir = server_root / "Sessions" / f"CLIENT_{client_id}" / session_id
        (session_dir / "packing_lists").mkdir(parents=True, exist_ok=True)
        work_dir = session_dir / "packing" / list_name
        work_dir.mkdir(parents=True, exist_ok=True)

        packing_list = make_packing_list(orders)
        packing_list["list_name"] = list_name
        list_path = session_dir / "packing_lists" / f"{list_name}.json"
        list_path.write_text(json.dumps(packing_list, ensure_ascii=False), encoding="utf-8")

        return session_dir, work_dir, list_path

    return _make


@pytest.fixture
def packer_logic_factory(profile_manager):
    """Construct real PackerLogic instances, tracking them for clean shutdown
    (each instance owns a live background writer thread).
    """
    created = []

    def _make(client_id, work_dir):
        logic = PackerLogic(client_id=client_id, profile_manager=profile_manager, work_dir=str(work_dir))
        created.append(logic)
        return logic

    yield _make

    for logic in created:
        logic.close()


@pytest.fixture
def loaded_logic(packer_logic_factory, session_factory):
    """A PackerLogic instance with a 2-order packing list already loaded."""
    orders = [
        (
            "ORDER-001",
            "DHL",
            [
                {"sku": "SKU-AAA", "quantity": 2, "product_name": "Widget A"},
                {"sku": "SKU-BBB", "quantity": 1, "product_name": "Widget B"},
            ],
        ),
        (
            "ORDER-002",
            "DHL",
            [{"sku": "SKU-CCC", "quantity": 1, "product_name": "Widget C"}],
        ),
    ]
    session_dir, work_dir, list_path = session_factory(client_id="M", orders=orders)
    logic = packer_logic_factory("M", work_dir)
    logic.load_packing_list_json(list_path)
    return logic
