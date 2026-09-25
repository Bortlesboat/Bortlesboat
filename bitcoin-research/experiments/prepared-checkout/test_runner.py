# SPDX-License-Identifier: GPL-3.0-only
"""Workspace guards; transaction behavior is tested by the real-node runner."""
from pathlib import Path
import tempfile
import unittest

from run import fresh_directory
from checkout import space_cost_scenarios


class WorkspaceGuards(unittest.TestCase):
    def test_refuses_existing_directory_without_altering_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "existing-work"
            marker.write_bytes(b"preserve me")
            with self.assertRaises(FileExistsError):
                fresh_directory(root)
            self.assertEqual(marker.read_bytes(), b"preserve me")
            self.assertEqual(list(root.iterdir()), [marker])

    def test_refuses_existing_file_without_altering_contents(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "file"
            marker.write_bytes(b"preserve me")
            with self.assertRaises(FileExistsError):
                fresh_directory(marker)
            self.assertEqual(marker.read_bytes(), b"preserve me")

    def test_creates_new_workspace_at_requested_path(self):
        with tempfile.TemporaryDirectory() as directory:
            requested = Path(directory) / "new"
            result = fresh_directory(requested)
            self.assertEqual(result, requested.resolve())
            self.assertTrue(result.is_dir())
            self.assertEqual(list(result.iterdir()), [])


class CostReporting(unittest.TestCase):
    def test_unequal_signature_sizes_preserve_measured_totals(self):
        one, two, ten = space_cost_scenarios(580, [140, 141])
        self.assertEqual(one["baseline_total_vbytes"], 140)
        self.assertEqual(two["baseline_total_vbytes"], 281)
        self.assertEqual(two["prepared_total_vbytes"], 861)
        self.assertEqual(two["measured_payment_vbytes"], [140, 141])
        self.assertEqual(two["basis"], "measured")
        self.assertEqual(ten["baseline_total_vbytes"], 1405)
        self.assertEqual(ten["basis"], "modeled_from_two_payment_mean")
        self.assertIsNone(ten["measured_payment_vbytes"])


if __name__ == "__main__":
    unittest.main()
