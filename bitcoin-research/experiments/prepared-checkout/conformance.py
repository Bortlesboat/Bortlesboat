# SPDX-License-Identifier: GPL-3.0-only
"""Run the versioned policy corpus against the bundled or a caller-selected auditor.

The auditor receives a trace file path as its last argument, returns JSON on
stdout, and exits 0/1/2 for clean/violated/invalid. No shell is invoked.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

from audit import check, read_json

HERE = Path(__file__).resolve().parent


def observation(report: dict, exit_code: int) -> dict:
    status = report["status"]
    check(status in ("clean", "violated", "invalid"), "Unknown auditor status")
    result = {"exit_code": exit_code, "status": status}
    if status != "invalid":
        for field in ("steps", "undeclared_spends", "fees_unverified_missing_parents"):
            check(isinstance(report[field], list), f"Auditor {field} must be an array")
        result.update(
            step_violations=[s["violations"] for s in report["steps"]],
            step_fee_sats=[s["fee_sats"] for s in report["steps"]],
            step_vsize=[s["vsize"] for s in report["steps"]],
            undeclared_spends=len(report["undeclared_spends"]),
            fees_unverified=len(report["fees_unverified_missing_parents"]))
    return result


def run_corpus(corpus: dict, command: list[str], timeout: float) -> dict:
    check(corpus["format"] == "coin-policy-conformance-v1", "Unknown corpus format")
    cases = corpus["cases"]
    check(isinstance(cases, list) and bool(cases), "Corpus must contain cases")
    names = [case["id"] for case in cases]
    check(all(isinstance(name, str) and name for name in names) and len(set(names)) == len(names),
          "Case names must be unique nonempty strings")
    results = []
    with tempfile.TemporaryDirectory(prefix="coin-policy-conformance-") as directory:
        root = Path(directory)
        trace_path, stdout_path, stderr_path = (root / name for name in
                                               ("trace.json", "stdout.json", "stderr.txt"))
        for case in cases:
            expected = case["expected"]
            check(isinstance(expected, dict) and "status" in expected and "exit_code" in expected,
                  "Each case needs an expected status and exit code")
            check(("trace" in case) != ("json_text" in case), "Case needs trace or json_text")
            content = case["json_text"] if "json_text" in case else json.dumps(case["trace"])
            trace_path.write_text(content, encoding="utf-8")
            result = {"id": case["id"], "expected": expected, "passed": False}
            try:
                # File-backed capture avoids holding a noisy checker's output in memory.
                with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                    process = subprocess.run([*command, str(trace_path)], stdout=stdout,
                                             stderr=stderr, timeout=timeout, check=False)
                actual = observation(read_json(stdout_path), process.returncode)
                result["observed"] = actual
                # JSON types are part of the contract (false != 0, 100.0 != 100).
                result["passed"] = json.dumps(actual, sort_keys=True) == json.dumps(expected, sort_keys=True)
            except subprocess.TimeoutExpired:
                result["error"] = "Auditor exceeded the per-case timeout"
            except (ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError) as error:
                result["error"] = f"Invalid auditor response: {error}"
            results.append(result)
    passed = sum(result["passed"] for result in results)
    return {"format": "coin-policy-conformance-result-v1",
            "status": "passed" if passed == len(cases) else "failed",
            "scope": "Agreement on these declared-policy cases only; no wallet certification.",
            "cases_checked": len(cases), "cases_passed": passed, "cases": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=HERE / "conformance-v1.json")
    parser.add_argument("--timeout", type=float, default=10, help="seconds per case (default: 10)")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="optional: -- executable [args]; trace path is appended")
    args = parser.parse_args()
    try:
        check(math.isfinite(args.timeout) and args.timeout > 0, "Timeout must be finite and positive")
        command = args.command[1:] if args.command[:1] == ["--"] else args.command
        report = run_corpus(read_json(args.corpus), command or [sys.executable, str(HERE / "audit.py")],
                            args.timeout)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}))
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
