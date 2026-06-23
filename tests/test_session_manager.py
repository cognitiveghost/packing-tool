import unittest
from unittest.mock import patch, MagicMock
import os
import json
from pathlib import Path

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../src')))

from session_manager import SessionManager, SESSION_INFO_FILE


class TestSessionManager(unittest.TestCase):

    def setUp(self):
        self.base_dir = Path("/tmp/test_sessions")

        # Create mock ProfileManager
        self.mock_profile_manager = MagicMock()
        self.mock_profile_manager.get_session_dir.return_value = self.base_dir / "test_session"

        # Create mock SessionLockManager
        self.mock_lock_manager = MagicMock()
        self.mock_lock_manager.acquire_lock.return_value = (True, None, None)
        self.mock_lock_manager.is_locked.return_value = (False, {})

        # Create SessionManager with mocks
        self.manager = SessionManager(
            client_id="TEST",
            profile_manager=self.mock_profile_manager,
            lock_manager=self.mock_lock_manager
        )

    def test_start_session_creates_directory_and_info_file(self):
        """
        Verify that starting a new session creates a unique directory
        and a session_info.json file inside it.
        """
        test_path = "dummy_path.xlsx"
        expected_session_id = "2025-11-06_14-30-45"
        expected_dir = self.base_dir / expected_session_id

        # Configure mock to return specific session directory
        self.mock_profile_manager.get_session_dir.return_value = expected_dir

        mock_tmp = MagicMock()
        mock_tmp.return_value.__enter__.return_value.name = '/tmp/fake_session.tmp'

        with patch('pathlib.Path.mkdir') as mock_mkdir, \
             patch('session_manager.tempfile.NamedTemporaryFile', mock_tmp), \
             patch('session_manager.shutil.move') as mock_move, \
             patch('json.dump') as mock_json_dump:

            self.manager.start_session(test_path)

            # Check that ProfileManager.get_session_dir was called
            self.mock_profile_manager.get_session_dir.assert_called_once_with("TEST")

            # Check that directory mkdir was called (for main dir and barcodes dir)
            self.assertEqual(mock_mkdir.call_count, 2)

            # Check that lock was acquired
            self.mock_lock_manager.acquire_lock.assert_called_once()

            # Check that the session info file was written atomically
            expected_file_path = expected_dir / SESSION_INFO_FILE
            mock_move.assert_called_once_with('/tmp/fake_session.tmp', str(expected_file_path))

            # Verify json.dump was called with correct structure
            call_args = mock_json_dump.call_args
            self.assertIsNotNone(call_args)
            session_info = call_args[0][0]
            self.assertEqual(session_info['client_id'], 'TEST')
            self.assertEqual(session_info['packing_list_path'], test_path)
            self.assertIn('started_at', session_info)
            self.assertIn('pc_name', session_info)

            self.assertEqual(self.manager.session_id, expected_session_id)
            self.assertTrue(self.manager.is_active())

    def test_end_session_removes_info_file(self):
        """
        Verify that ending a session removes the session_info.json file.
        """
        # First, simulate an active session
        self.manager.session_id = "test_session_123"
        output_dir = self.base_dir / self.manager.session_id
        self.manager.output_dir = output_dir
        self.manager.session_active = True

        info_path = self.manager.output_dir / SESSION_INFO_FILE

        with patch('pathlib.Path.exists') as mock_exists, \
             patch('pathlib.Path.unlink') as mock_unlink:

            mock_exists.return_value = True  # Simulate that the info file exists

            self.manager.end_session()

            # Check that the file removal was attempted
            mock_unlink.assert_called_once()

            # Check that lock was released (with the output_dir value before it was cleared)
            self.mock_lock_manager.release_lock.assert_called_once_with(output_dir)

            self.assertFalse(self.manager.is_active())
            self.assertIsNone(self.manager.session_id)

    def test_load_packing_list_success(self):
        """
        Verify that load_packing_list correctly loads a valid packing list JSON.
        """
        # Create test session directory structure
        session_path = self.base_dir / "2025-11-10_1"
        packing_lists_dir = session_path / "packing_lists"
        packing_lists_dir.mkdir(parents=True, exist_ok=True)

        # Create test packing list JSON
        test_data = {
            "session_id": "2025-11-10_1",
            "report_name": "DHL Orders",
            "created_at": "2025-11-10T10:00:00",
            "total_orders": 2,
            "total_items": 5,
            "filters_applied": [
                {"field": "Shipping_Provider", "operator": "==", "value": "DHL"}
            ],
            "orders": [
                {
                    "order_number": "#1001",
                    "order_type": "single",
                    "destination": "Bulgaria",
                    "courier": "DHL",
                    "tags": [],
                    "items": [
                        {
                            "sku": "01-DM-0379-110-L",
                            "product_name": "Python Camo Denim - Size Large",
                            "quantity": 1
                        }
                    ]
                },
                {
                    "order_number": "#1002",
                    "order_type": "single",
                    "destination": "Germany",
                    "courier": "DHL",
                    "tags": [],
                    "items": [
                        {
                            "sku": "02-DM-0380-120-M",
                            "product_name": "Urban Camo Jacket - Size Medium",
                            "quantity": 2
                        }
                    ]
                }
            ]
        }

        packing_list_file = packing_lists_dir / "DHL_Orders.json"
        with open(packing_list_file, 'w', encoding='utf-8') as f:
            json.dump(test_data, f, indent=2)

        # Test loading with .json extension
        result = self.manager.load_packing_list(str(session_path), "DHL_Orders.json")

        self.assertIsNotNone(result)
        self.assertEqual(result['session_id'], "2025-11-10_1")
        self.assertEqual(result['report_name'], "DHL Orders")
        self.assertEqual(result['total_orders'], 2)
        self.assertEqual(len(result['orders']), 2)
        self.assertEqual(result['orders'][0]['order_number'], "#1001")

        # Test loading without .json extension
        result2 = self.manager.load_packing_list(str(session_path), "DHL_Orders")

        self.assertIsNotNone(result2)
        self.assertEqual(result2['total_orders'], 2)

        # Cleanup
        packing_list_file.unlink()
        packing_lists_dir.rmdir()
        session_path.rmdir()

    def test_load_packing_list_file_not_found(self):
        """
        Verify that load_packing_list raises FileNotFoundError for missing file.
        """
        session_path = self.base_dir / "2025-11-10_1"
        session_path.mkdir(parents=True, exist_ok=True)
        packing_lists_dir = session_path / "packing_lists"
        packing_lists_dir.mkdir(exist_ok=True)

        with self.assertRaises(FileNotFoundError) as context:
            self.manager.load_packing_list(str(session_path), "NonExistent_Orders")

        self.assertIn("Packing list not found", str(context.exception))

        # Cleanup
        packing_lists_dir.rmdir()
        session_path.rmdir()

    def test_load_packing_list_invalid_json(self):
        """
        Verify that load_packing_list raises JSONDecodeError for malformed JSON.
        """
        session_path = self.base_dir / "2025-11-10_1"
        packing_lists_dir = session_path / "packing_lists"
        packing_lists_dir.mkdir(parents=True, exist_ok=True)

        # Create invalid JSON file
        invalid_json_file = packing_lists_dir / "Invalid_Orders.json"
        with open(invalid_json_file, 'w', encoding='utf-8') as f:
            f.write("{ invalid json content }")

        with self.assertRaises(json.JSONDecodeError):
            self.manager.load_packing_list(str(session_path), "Invalid_Orders")

        # Cleanup
        invalid_json_file.unlink()
        packing_lists_dir.rmdir()
        session_path.rmdir()

    def test_load_packing_list_missing_orders_key(self):
        """
        Verify that load_packing_list raises KeyError if 'orders' key is missing.
        """
        session_path = self.base_dir / "2025-11-10_1"
        packing_lists_dir = session_path / "packing_lists"
        packing_lists_dir.mkdir(parents=True, exist_ok=True)

        # Create JSON without 'orders' key
        invalid_data = {
            "session_id": "2025-11-10_1",
            "report_name": "Missing Orders"
        }

        invalid_file = packing_lists_dir / "Missing_Orders.json"
        with open(invalid_file, 'w', encoding='utf-8') as f:
            json.dump(invalid_data, f)

        with self.assertRaises(KeyError) as context:
            self.manager.load_packing_list(str(session_path), "Missing_Orders")

        self.assertIn("orders", str(context.exception))

        # Cleanup
        invalid_file.unlink()
        packing_lists_dir.rmdir()
        session_path.rmdir()

    def test_get_packing_work_dir_creates_structure(self):
        """
        Verify that get_packing_work_dir creates proper directory structure.
        """
        session_path = self.base_dir / "2025-11-10_1"
        session_path.mkdir(parents=True, exist_ok=True)

        # Test with .json extension
        work_dir = self.manager.get_packing_work_dir(str(session_path), "DHL_Orders.json")

        self.assertTrue(work_dir.exists())
        self.assertEqual(work_dir.name, "DHL_Orders")
        self.assertTrue((work_dir / "barcodes").exists())
        self.assertTrue((work_dir / "reports").exists())

        # Cleanup
        (work_dir / "barcodes").rmdir()
        (work_dir / "reports").rmdir()
        work_dir.rmdir()
        (session_path / "packing").rmdir()
        session_path.rmdir()

    def test_get_packing_work_dir_removes_extensions(self):
        """
        Verify that get_packing_work_dir removes various file extensions.
        """
        session_path = self.base_dir / "2025-11-10_1"
        session_path.mkdir(parents=True, exist_ok=True)

        # Test with different extensions
        for extension in ['.json', '.xlsx', '.xls', '']:
            packing_list_name = f"Test_Orders{extension}"
            work_dir = self.manager.get_packing_work_dir(str(session_path), packing_list_name)

            self.assertEqual(work_dir.name, "Test_Orders")
            self.assertTrue(work_dir.exists())

            # Cleanup
            (work_dir / "barcodes").rmdir()
            (work_dir / "reports").rmdir()
            work_dir.rmdir()

        (session_path / "packing").rmdir()
        session_path.rmdir()

    def test_get_packing_work_dir_idempotent(self):
        """
        Verify that get_packing_work_dir is idempotent (can be called multiple times).
        """
        session_path = self.base_dir / "2025-11-10_1"
        session_path.mkdir(parents=True, exist_ok=True)

        # Call multiple times
        work_dir1 = self.manager.get_packing_work_dir(str(session_path), "DHL_Orders")
        work_dir2 = self.manager.get_packing_work_dir(str(session_path), "DHL_Orders")

        self.assertEqual(work_dir1, work_dir2)
        self.assertTrue(work_dir1.exists())
        self.assertTrue((work_dir1 / "barcodes").exists())
        self.assertTrue((work_dir1 / "reports").exists())

        # Cleanup
        (work_dir1 / "barcodes").rmdir()
        (work_dir1 / "reports").rmdir()
        work_dir1.rmdir()
        (session_path / "packing").rmdir()
        session_path.rmdir()
