# SPDX-License-Identifier: GPL-3.0-only
"""Audit the published bytes, then change the evidence to exercise failures."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from audit import audit_trace, decode_transaction, reference_trace

HERE = Path(__file__).resolve().parent


class PolicyAudit(unittest.TestCase):
    def setUp(self):
        self.reference = json.loads((HERE / "reference-results.json").read_text())
        self.trace = reference_trace(self.reference)

    def test_real_transactions_match_core_decoding(self):
        for record in self.trace["transactions"]:
            with self.subTest(txid=record["txid"]):
                decoded = decode_transaction(record["raw_hex"])
                for field in ("txid", "vsize", "weight", "inputs"):
                    self.assertEqual(decoded[field], record[field])
                self.assertEqual([o["sats"] for o in decoded["outputs"]],
                                 [o["sats"] for o in record["outputs"]])

    def test_original_payments_and_real_merge_control(self):
        isolated = copy.deepcopy(self.trace)
        isolated["steps"] = isolated["steps"][:2]
        isolated["transactions"] = isolated["transactions"][:-1]
        clean = audit_trace(isolated)
        self.assertEqual(clean["status"], "clean")
        self.assertEqual([s["fee_sats"] for s in clean["steps"]], [1000, 1000])
        merged = audit_trace(self.trace)
        self.assertEqual(merged["status"], "violated")
        self.assertEqual(merged["steps"][-1]["violations"], ["wrong_pool"])
        self.assertEqual(merged["steps"][-1]["fee_sats"], 416)

    def test_recorded_success_flags_cannot_hide_merge(self):
        self.reference["checks"] = {"everything": "passed"}
        self.reference["unsafe_topup_control"]["publicly_joins_prepared_and_unprepared_outpoints"] = False
        self.assertEqual(audit_trace(reference_trace(self.reference))["status"], "violated")

    def test_omitting_step_cannot_hide_supplied_merge_bytes(self):
        self.trace["steps"] = self.trace["steps"][:2]
        result = audit_trace(self.trace)
        self.assertEqual(result["status"], "violated")
        self.assertEqual([t["txid"] for t in result["undeclared_spends"]],
                         [self.reference["unsafe_topup_control"]["txid"]])

    def test_new_root_cannot_hide_supplied_merge(self):
        self.trace["steps"] = self.trace["steps"][:2]
        self.trace["roots"].append({"txid": self.reference["unsafe_topup_control"]["txid"],
                                    "vout": 0, "pool": "prepared"})
        self.assertEqual(audit_trace(self.trace)["status"], "violated")

    def test_committed_core_traces_match_saved_audits(self):
        for rate in (1, 10, 50):
            with self.subTest(rate=rate):
                root = HERE / "policy-reference"
                trace = json.loads((root / f"fee-{rate}.trace.json").read_text())
                report = json.loads((root / f"fee-{rate}.result.json").read_text())
                self.assertEqual(audit_trace(trace), report["merge_control_audit"])

    def test_metadata_loss_fails_closed(self):
        self.trace["roots"] = self.trace["roots"][1:]
        result = audit_trace(self.trace)
        self.assertIn("unclassified_or_spent_input", result["steps"][0]["violations"])
        self.assertIn("unclassified_or_spent_input", result["steps"][1]["violations"])

    def test_replaying_payment_is_invalid(self):
        self.trace["steps"].insert(1, copy.deepcopy(self.trace["steps"][0]))
        with self.assertRaises(ValueError):
            audit_trace(self.trace)

    def test_tampered_record_is_rejected(self):
        for field, value in (("txid", "00" * 32), ("vsize", 1), ("weight", 1),
                             ("inputs", []), ("fee_sats", 1)):
            with self.subTest(field=field):
                trace = copy.deepcopy(self.trace)
                trace["transactions"][-1][field] = value
                with self.assertRaises(ValueError):
                    audit_trace(trace)
        self.trace["transactions"][-1]["outputs"][0]["sats"] += 1
        with self.assertRaises(ValueError):
            audit_trace(self.trace)

    def test_bad_payment_amount_or_change_index_is_rejected(self):
        for field, value in (("payment_sats", 1), ("change_vout", 99),
                             ("change_vout", 0)):
            with self.subTest(field=field):
                trace = copy.deepcopy(self.trace)
                trace["steps"][0][field] = value
                with self.assertRaises(ValueError):
                    audit_trace(trace)

    def test_duplicate_root_and_relabelled_change_are_rejected(self):
        duplicate = copy.deepcopy(self.trace)
        duplicate["roots"].append(copy.deepcopy(duplicate["roots"][0]))
        with self.assertRaises(ValueError):
            audit_trace(duplicate)
        step = self.trace["steps"][0]
        self.trace["roots"].append({"txid": step["txid"],
                                    "vout": step["change_vout"], "pool": "prepared"})
        with self.assertRaises(ValueError):
            audit_trace(self.trace)

    def test_truncated_trailing_and_noncanonical_transactions_rejected(self):
        raw = self.trace["transactions"][0]["raw_hex"]
        for invalid in (raw[:-2], raw + "00", raw[:12] + "fd0100" + raw[14:], "xx"):
            with self.subTest(raw=invalid[:30]):
                with self.assertRaises(ValueError):
                    decode_transaction(invalid)

    def test_missing_parent_does_not_invent_a_fee(self):
        result = audit_trace(self.trace)
        self.assertEqual(result["fees_unverified_missing_parents"],
                         [t["txid"] for t in self.trace["transactions"][:2]] +
                         [self.reference["setup_control_deposit"]["txid"]])

    def test_legacy_serialization_against_core_31_1_vector(self):
        # Core createrawtransaction + decoderawtransaction; unsigned serialization only.
        raw = ("0200000001" + "11" * 32 +
               "0000000000fdffffff010000000000000000046a02000100000000")
        decoded = decode_transaction(raw)
        self.assertEqual(decoded["txid"], "393072a5eab18ce9d56e50ac0acea34b3d8065caf063c015f09c16a19a4dba89")
        self.assertEqual((decoded["vsize"], decoded["weight"]), (64, 256))
        self.assertEqual(decoded["outputs"], [{"vout": 0, "sats": 0, "script_hex": "6a020001"}])

    def test_cli_separates_clean_violation_and_invalid_evidence(self):
        clean = copy.deepcopy(self.trace)
        clean["steps"] = clean["steps"][:2]
        clean["transactions"] = clean["transactions"][:-1]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.json"
            for trace, code, status in ((clean, 0, "clean"), (self.trace, 1, "violated"),
                                        ({}, 2, "invalid")):
                with self.subTest(status=status):
                    path.write_text(json.dumps(trace), encoding="utf-8")
                    result = subprocess.run([sys.executable, str(HERE / "audit.py"), str(path)],
                                            capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, code, result.stderr)
                    self.assertEqual(json.loads(result.stdout)["status"], status)
            path.write_text("[" * 100_000, encoding="utf-8")
            result = subprocess.run([sys.executable, str(HERE / "audit.py"), str(path)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "invalid")


if __name__ == "__main__":
    unittest.main()
