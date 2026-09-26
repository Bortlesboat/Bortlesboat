# SPDX-License-Identifier: GPL-3.0-only
"""Convert raw transactions plus wallet-owned annotations to an auditable trace."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from audit import MAX_JSON_BYTES, audit_trace, check, decode_transaction, read_json


def export_trace(bundle: dict) -> dict:
    check(bundle["format"] == "coin-policy-export-v1", "Unknown export format")
    check(isinstance(bundle["raw_transactions"], list), "raw_transactions must be an array")
    trace = {"format": "coin-policy-trace-v1",
             "transactions": [{"raw_hex": raw, **decode_transaction(raw)}
                              for raw in bundle["raw_transactions"]],
             "roots": bundle["roots"], "steps": bundle["steps"]}
    # Validate evidence before writing. Preserve valid traces that violate policy:
    # an exporter must not silently drop failure controls or change wallet intent.
    audit_trace(trace)
    return trace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="coin-policy-export-v1 JSON")
    parser.add_argument("--output", type=Path, help="new UTF-8 file; default is stdout")
    args = parser.parse_args()
    try:
        encoded = json.dumps(export_trace(read_json(args.bundle)), indent=2) + "\n"
        check(len(encoded.encode("utf-8")) <= MAX_JSON_BYTES, "Export exceeds the audit's 16 MB limit")
        if args.output:
            with args.output.open("x", encoding="utf-8", newline="\n") as output:
                output.write(encoded)
        else:
            print(encoded, end="")
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
