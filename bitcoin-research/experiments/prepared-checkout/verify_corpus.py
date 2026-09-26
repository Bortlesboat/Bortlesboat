# SPDX-License-Identifier: GPL-3.0-only
"""Compare corpus serialization decoding with a fresh, network-disabled Core node.

This checks decoding only. It does not broadcast or validate these unsigned
synthetic transactions as spendable payments. Pool policy remains wallet input.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from audit import decode_transaction, read_json
from checkout import digest, sats
from regtest import Regtest, require

HERE = Path(__file__).resolve().parent


def verify(binary: Path) -> dict:
    corpus = read_json(HERE / "conformance-v1.json")
    serializations = sorted({tx["raw_hex"] for case in corpus["cases"] if "trace" in case
                             for tx in case["trace"]["transactions"]})
    node = Regtest(binary)
    results = []
    try:
        node.start()
        version = node.rpc("getnetworkinfo")["subversion"]
        for raw in serializations:
            try:
                decoded = decode_transaction(raw)
            except ValueError:
                decoded = None
            try:
                core = node.rpc("decoderawtransaction", raw)
            except RuntimeError as error:
                require("'code': -22" in str(error), f"Unexpected Core error: {error}")
                core = None
            require((decoded is None) == (core is None), "Core and auditor disagree on decoding")
            if decoded is not None:
                expected = {"txid": core["txid"], "vsize": core["vsize"], "weight": core["weight"],
                            "inputs": [{"txid": i["txid"], "vout": i["vout"]} for i in core["vin"]],
                            "outputs": [{"vout": o["n"], "sats": sats(o["value"]),
                                         "script_hex": o["scriptPubKey"]["hex"]} for o in core["vout"]]}
                require(decoded == expected, "Core and auditor decoded fields differ")
            results.append({"raw_sha256": hashlib.sha256(bytes.fromhex(raw)).hexdigest(),
                            "outcome": "matching_rejection" if core is None else "matching_decoding"})
    finally:
        node.stop()
    require(node.stopped, "Owned node did not stop")
    return {"format": "coin-policy-decoder-comparison-v1", "status": "passed",
            "created_utc": datetime.now(timezone.utc).isoformat(), "bitcoin_version": version,
            "bitcoin_binary_sha256": digest(binary),
            "source_sha256": {name: digest(HERE / name) for name in
                              ("audit.py", "verify_corpus.py", "conformance-v1.json", "regtest.py", "checkout.py")},
            "scope": "Serialization decoding only; no signatures, chain validity or pool-label verification.",
            "serializations_checked": len(results), "results": results, "owned_node_stopped": node.stopped}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bitcoind", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.bitcoind.resolve(strict=True)), indent=2))


if __name__ == "__main__":
    main()
