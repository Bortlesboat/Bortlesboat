# SPDX-License-Identifier: GPL-3.0-only
"""Regression cases from bounded local adversarial testing."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
NONFINITE = ("NaN", "Infinity", "-Infinity", "1e400")


def cli(script, *args):
    return subprocess.run([sys.executable, str(HERE / script), *map(str, args)],
                          capture_output=True, text=True, timeout=10)


class HostileJson(unittest.TestCase):
    def test_audit_rejects_nonfinite_numbers_even_in_extra_metadata(self):
        corpus = json.loads((HERE / "conformance-v1.json").read_text())
        trace = json.dumps(corpus["cases"][0]["trace"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.json"
            for token in NONFINITE:
                with self.subTest(token=token):
                    path.write_text(trace[:-1] + ',"extra":' + token + '}', encoding="utf-8")
                    result = cli("audit.py", path)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertEqual(json.loads(result.stdout)["status"], "invalid")

    def test_export_rejects_nonfinite_numbers_before_creating_a_file(self):
        bundle = json.loads((HERE / "example-export.json").read_text())
        bundle["roots"][0]["extra"] = "NONFINITE_MARKER"
        template = json.dumps(bundle)
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "bundle.json"
            for number, token in enumerate(NONFINITE):
                with self.subTest(token=token):
                    output = Path(directory) / f"trace-{number}.json"
                    source.write_text(template.replace('"NONFINITE_MARKER"', token), encoding="utf-8")
                    result = cli("export_trace.py", source, "--output", output)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertFalse(output.exists())

    def test_nonfinite_checker_metadata_cannot_pass_conformance(self):
        corpus = json.loads((HERE / "conformance-v1.json").read_text())
        corpus["cases"] = corpus["cases"][:1]
        # Otherwise exact expected clean response: malformed JSON must be the
        # reason for failure, not an unrelated missing field or wrong outcome.
        report = {"status": "clean", "steps": [
            {"violations": [], "fee_sats": 100, "vsize": 71},
            {"violations": [], "fee_sats": 200, "vsize": 71}],
            "undeclared_spends": [], "fees_unverified_missing_parents": ["funding"]}
        with tempfile.TemporaryDirectory() as directory:
            suite, checker = Path(directory) / "suite.json", Path(directory) / "checker.py"
            suite.write_text(json.dumps(corpus), encoding="utf-8")
            for token in NONFINITE:
                with self.subTest(token=token):
                    payload = json.dumps(report)[:-1] + ',"extra":' + token + '}'
                    checker.write_text(f"print({payload!r})\n", encoding="utf-8")
                    result = cli("conformance.py", "--corpus", suite, "--", sys.executable, checker)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    self.assertEqual(json.loads(result.stdout)["cases_passed"], 0)


@unittest.skipUnless(sys.platform.startswith("linux"), "Address-space budget check runs on Linux")
class ExportResourceBudget(unittest.TestCase):
    def test_large_export_fails_cleanly_within_a_memory_budget(self):
        # This 7.2 MB input previously exhausted 384 MiB while materializing a
        # JSON output that would only afterward be rejected as over 16 MB.
        count = 400_000
        raw = b"\x02\x00\x00\x00\x01" + b"\x11" * 32 + b"\x00" * 5 + b"\xff" * 4
        raw += b"\xfe" + count.to_bytes(4, "little") + b"\x00" * (9 * count) + b"\x00" * 4
        txid = hashlib.sha256(hashlib.sha256(raw).digest()).digest()[::-1].hex()
        bundle = {"format": "coin-policy-export-v1", "raw_transactions": [raw.hex()], "roots": [],
                  "steps": [{"txid": txid, "required_pool": "a", "payment_vout": 0,
                             "payment_sats": 0, "change_vout": None}]}
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "bundle.json", Path(directory) / "trace.json"
            source.write_text(json.dumps(bundle), encoding="utf-8")
            worker = Path(directory) / "limited.py"
            worker.write_text(
                "import os, resource, sys\n"
                "resource.setrlimit(resource.RLIMIT_AS, (384 * 1024**2, 384 * 1024**2))\n"
                "os.execv(sys.executable, [sys.executable, *sys.argv[1:]])\n", encoding="utf-8")
            result = subprocess.run([sys.executable, str(worker), str(HERE / "export_trace.py"),
                                     str(source), "--output", str(output)],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertIn("16 MB limit", json.loads(result.stdout)["error"])
            self.assertFalse(output.exists())
            self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
