# SPDX-License-Identifier: GPL-3.0-only
"""Exercise the public exporter and cross-implementation checker boundary."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def cli(script, *args):
    return subprocess.run([sys.executable, str(HERE / script), *map(str, args)],
                          capture_output=True, text=True, timeout=30)


class IntegrationCommands(unittest.TestCase):
    def test_export_preserves_policy_intent_and_detects_the_known_merge(self):
        trace = json.loads((HERE / "policy-reference/fee-1.trace.json").read_text())
        bundle = {"format": "coin-policy-export-v1",
                  "raw_transactions": [t["raw_hex"] for t in trace["transactions"]],
                  "roots": trace["roots"], "steps": trace["steps"]}
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "wallet.json", Path(directory) / "trace.json"
            source.write_text(json.dumps(bundle), encoding="utf-8")
            result = cli("export_trace.py", source, "--output", output)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            exported = json.loads(output.read_text())
            self.assertEqual(exported["roots"], trace["roots"])
            self.assertEqual(exported["steps"], trace["steps"])
            result = cli("audit.py", output)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            audit = json.loads(result.stdout)
            self.assertEqual(audit["steps"][-1]["violations"], ["wrong_pool"])
            self.assertEqual([s["fee_sats"] for s in audit["steps"][:2]], [141, 141])
            before = output.read_bytes()
            result = cli("export_trace.py", source, "--output", output)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(output.read_bytes(), before)
            # A contradictory intent must fail before a destination is created.
            bundle["steps"][0]["payment_sats"] += 1
            source.write_text(json.dumps(bundle), encoding="utf-8")
            bad = Path(directory) / "bad.json"
            result = cli("export_trace.py", source, "--output", bad)
            self.assertEqual(result.returncode, 2)
            self.assertFalse(bad.exists())

    def test_bundled_and_explicit_checker_pass_the_published_corpus(self):
        for command in ([], ["--", sys.executable, str(HERE / "audit.py")]):
            with self.subTest(command=command):
                result = cli("conformance.py", *command)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                report = json.loads(result.stdout)
                self.assertEqual(report["status"], "passed")
                self.assertEqual(report["cases_checked"], 27)
                self.assertEqual(report["cases_checked"], report["cases_passed"])

    def test_false_success_timeout_and_invalid_output_fail_the_runner(self):
        with tempfile.TemporaryDirectory() as directory:
            checker = Path(directory) / "checker.py"
            corpus = json.loads((HERE / "conformance-v1.json").read_text())
            corpus["cases"] = corpus["cases"][:1]
            suite = Path(directory) / "suite.json"
            suite.write_text(json.dumps(corpus), encoding="utf-8")
            for body, extra in (("print('{\"status\": \"clean\"}')", []),
                                ("print('not json')", []),
                                ("import time; time.sleep(3)", ["--timeout", "0.1"])):
                with self.subTest(body=body):
                    checker.write_text(body, encoding="utf-8")
                    result = cli("conformance.py", "--corpus", suite, *extra,
                                 "--", sys.executable, checker)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                    report = json.loads(result.stdout)
                    self.assertEqual(report["status"], "failed")
                    self.assertEqual(report["cases_passed"], 0)

    def test_empty_corpus_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.json"
            path.write_text('{"format":"coin-policy-conformance-v1","cases":[]}', encoding="utf-8")
            result = cli("conformance.py", "--corpus", path)
            self.assertEqual(result.returncode, 2)

    def test_wrong_exit_code_or_numeric_type_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            corpus = json.loads((HERE / "conformance-v1.json").read_text())
            corpus["cases"] = corpus["cases"][:1]
            suite, checker = Path(directory) / "suite.json", Path(directory) / "checker.py"
            suite.write_text(json.dumps(corpus), encoding="utf-8")
            for exit_code, first_fee in ((9, 100), (0, 100.0)):
                with self.subTest(exit_code=exit_code, first_fee=first_fee):
                    report = {"status": "clean", "steps": [
                        {"violations": [], "fee_sats": first_fee, "vsize": 71},
                        {"violations": [], "fee_sats": 200, "vsize": 71}],
                        "undeclared_spends": [], "fees_unverified_missing_parents": ["funding"]}
                    checker.write_text(f"print({json.dumps(report)!r})\nraise SystemExit({exit_code})\n",
                                       encoding="utf-8")
                    result = cli("conformance.py", "--corpus", suite, "--", sys.executable, checker)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_non_array_result_containers_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            corpus = json.loads((HERE / "conformance-v1.json").read_text())
            corpus["cases"] = corpus["cases"][:1]
            suite, checker = Path(directory) / "suite.json", Path(directory) / "checker.py"
            suite.write_text(json.dumps(corpus), encoding="utf-8")
            report = {"status": "clean", "steps": [
                {"violations": [], "fee_sats": 100, "vsize": 71},
                {"violations": [], "fee_sats": 200, "vsize": 71}],
                "undeclared_spends": "", "fees_unverified_missing_parents": "x"}
            checker.write_text(f"print({json.dumps(report)!r})\n", encoding="utf-8")
            result = cli("conformance.py", "--corpus", suite, "--", sys.executable, checker)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)

    def test_export_that_exceeds_audit_limit_creates_no_output(self):
        bundle = json.loads((HERE / "example-export.json").read_text())
        # UTF-8 input is under 16 MB; ASCII-escaped output would exceed it.
        label = "\u03b1" * 1_600_000
        bundle["roots"][0]["pool"] = label
        for step in bundle["steps"]:
            step["required_pool"] = label
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / "wallet.json", Path(directory) / "trace.json"
            source.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
            self.assertLess(source.stat().st_size, 16_000_000)
            result = cli("export_trace.py", source, "--output", output)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertFalse(output.exists())

    def test_corpus_rejects_first_wins_and_legacy_only_checkers(self):
        # Isolated subprocess mutations represent two plausible independent-checker
        # mistakes. Production files stay untouched; outcomes come from the corpus.
        mutations = [
            "def first_wins(pairs):\n"
            "    result = {}\n"
            "    for key, value in pairs: result.setdefault(key, value)\n"
            "    return result\n"
            "audit.read_json = lambda path: json.loads(path.read_text(), object_pairs_hook=first_wins)\n",
            "native_decode = audit.decode_transaction\n"
            "def legacy(raw):\n"
            "    result = native_decode(raw)\n"
            "    data = bytes.fromhex(raw)\n"
            "    result.update(txid=hashlib.sha256(hashlib.sha256(data).digest()).digest()[::-1].hex(),\n"
            "                  vsize=len(data), weight=len(data)*4)\n"
            "    return result\n"
            "audit.decode_transaction = legacy\n"]
        with tempfile.TemporaryDirectory() as directory:
            checker = Path(directory) / "checker.py"
            for mutation in mutations:
                with self.subTest(mutation=mutation.splitlines()[0]):
                    checker.write_text("import json, hashlib, sys\n"
                                       f"sys.path.insert(0, {str(HERE)!r})\nimport audit\n" + mutation +
                                       "raise SystemExit(audit.main())\n", encoding="utf-8")
                    result = cli("conformance.py", "--", sys.executable, checker)
                    self.assertEqual(result.returncode, 1, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
