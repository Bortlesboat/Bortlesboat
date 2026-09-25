# SPDX-License-Identifier: GPL-3.0-only
"""Run a disposable Core coin-policy fixture, including restart and bad controls.

Labels are synthetic fixture metadata. This does not execute A²L or OpenSwap.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess

from audit import audit_trace
from checkout import btc, coin_ids, digest, mine_transaction, outpoint, sats, transaction_record
from regtest import Regtest, require
from run import fresh_directory

HERE = Path(__file__).resolve().parent


def snapshot(node: Regtest) -> list[dict]:
    coins = node.rpc("listunspent", 1, wallet="receiver")
    return sorted([{**outpoint(c), "sats": sats(c["amount"]),
                    "labels": node.rpc("getaddressinfo", c["address"], wallet="receiver")["labels"]}
                   for c in coins], key=lambda c: (c["txid"], c["vout"]))


def fund(node: Regtest, amount: int, rate: int, add_inputs: bool = False) -> tuple[dict, str]:
    eligible = [c for c in snapshot(node) if c["labels"] == ["prepared"]]
    if not eligible:
        raise ValueError("no_eligible_coins")
    pay_address = node.rpc("getnewaddress", "", "bech32", wallet="merchant")
    change_address = node.rpc("getrawchangeaddress", "bech32", wallet="receiver")
    raw = node.rpc("createrawtransaction", [outpoint(c) for c in eligible],
                   [{pay_address: btc(amount)}])
    funded = node.rpc("fundrawtransaction", raw,
                      {"add_inputs": add_inputs, "fee_rate": rate,
                       "changeAddress": change_address, "changePosition": 1}, wallet="receiver")
    return funded, change_address


def payment(node: Regtest, amount: int, rate: int, miner: str,
            allow_merge: bool = False) -> tuple[dict, dict]:
    before = snapshot(node)
    funded, change_address = fund(node, amount, rate, add_inputs=allow_merge)
    require(funded["changepos"] == 1, "Fixture requires a change output")
    if not allow_merge:
        # The test adapter explicitly preserves source classification on change.
        node.rpc("setlabel", change_address, "prepared", wallet="receiver")
    signed = node.rpc("signrawtransactionwithwallet", funded["hex"], wallet="receiver")
    tx = mine_transaction(node, signed, miner)
    selected = before if allow_merge else [c for c in before if c["labels"] == ["prepared"]]
    require(coin_ids(tx["inputs"]) == coin_ids(selected), "Unexpected payment input set")
    require(tx["outputs"][0]["sats"] == amount, "Payment amount changed")
    require(tx["fee_sats"] == sats(funded["fee"]), "Core fee results disagree")
    # Allow a conservative size estimate of one extra vbyte per P2WPKH input.
    require(rate * tx["vsize"] <= tx["fee_sats"] <= rate * (tx["vsize"] + len(tx["inputs"])),
            "Mined fee does not match the requested rate within the fixture's size tolerance")
    received = [c for c in node.rpc("listunspent", 1, wallet="merchant") if c["txid"] == tx["txid"]]
    require(sum(sats(c["amount"]) for c in received) == amount, "Merchant payment missing")
    step = {"txid": tx["txid"], "required_pool": "prepared", "payment_vout": 0,
            "payment_sats": amount, "change_vout": None if allow_merge else 1}
    return tx, step


def refusal(node: Regtest, amount: int, rate: int, missing_label: bool = False) -> dict:
    before, mempool = snapshot(node), node.rpc("getrawmempool")
    try:
        fund(node, amount, rate)
    except ValueError as error:
        require(missing_label and str(error) == "no_eligible_coins", "Unexpected adapter failure")
        reason = str(error)
    except RuntimeError as error:
        reason = str(error)
        require(not missing_label and reason.startswith("fundrawtransaction:")
                and "'code': -4" in reason and "preselected coins" in reason,
                f"Expected selected-input funding refusal, got {reason}")
    else:
        raise AssertionError("Payment unexpectedly funded")
    require(snapshot(node) == before, "Refusal changed wallet coins or labels")
    require(node.rpc("getrawmempool") == mempool, "Refusal changed mempool")
    return {"requested_sats": amount, "eligible_sats": sum(c["sats"] for c in before
            if c["labels"] == ["prepared"]), "total_wallet_sats": sum(c["sats"] for c in before),
            "reason": reason, "coins_and_labels_unchanged": True, "mempool_unchanged": True}


def run_case(binary: Path, rate: int, destination: Path) -> dict:
    node = Regtest(binary)
    report = {"requested_fee_rate_sat_vb": rate, "status": "incomplete"}
    trace = {"format": "coin-policy-trace-v1", "transactions": [], "roots": [], "steps": []}
    try:
        node.start()
        for wallet in ("funder", "receiver", "merchant"):
            node.rpc("createwallet", wallet)
        miner = node.rpc("getnewaddress", "", "bech32", wallet="funder")
        # Keep each call within the shared harness's ten-second RPC timeout.
        for count in [10] * 10 + [1]:
            node.rpc("generatetoaddress", count, miner)
        for pool, amount in (("prepared", 10_000_000), ("ordinary", 5_000_000)):
            address = node.rpc("getnewaddress", pool, "bech32", wallet="receiver")
            txid = node.rpc("sendtoaddress", address, btc(amount), wallet="funder")
            block = node.rpc("generatetoaddress", 1, miner)[0]
            trace["transactions"].append(transaction_record(node, txid, block))
            coins = [c for c in node.rpc("listunspent", 1, wallet="receiver") if c["txid"] == txid]
            require(len(coins) == 1 and sats(coins[0]["amount"]) == amount, "Incorrect fixture funding")
            trace["roots"].append({**outpoint(coins[0]), "pool": pool})

        tx, step = payment(node, 123_456, rate, miner)
        trace["transactions"].append(tx)
        trace["steps"].append(step)
        before, height = snapshot(node), node.rpc("getblockcount")
        require(any(c["txid"] == tx["txid"] and c["labels"] == ["prepared"] for c in before),
                "Change classification missing before restart")
        node.stop()
        require(node.stopped, "First node process did not stop")
        (node.directory / "process.log").rename(node.directory / "before-restart.log")
        node.stopped = False
        node.start()  # Same on-disk wallet/chain, new owned process.
        for wallet in ("receiver", "merchant"):
            if wallet not in node.rpc("listwallets"):
                node.rpc("loadwallet", wallet)
        after = snapshot(node)
        require(after == before and node.rpc("getblockcount") == height,
                "Wallet labels, coins or chain height changed across restart")
        report["restart"] = {"before": before, "after": after, "height": height, "matched": True}
        tx, step = payment(node, 1_234_567, rate, miner)
        trace["transactions"].append(tx)
        trace["steps"].append(step)
        clean = audit_trace(trace)
        require(clean["status"] == "clean", "Isolated payments failed offline audit")
        report["isolated_payment_audit"] = clean
        report["ordinary_payment_fee_sats"] = [s["fee_sats"] for s in clean["steps"]]
        report["ordinary_payment_vbytes"] = [s["vsize"] for s in clean["steps"]]
        eligible = [c for c in snapshot(node) if c["labels"] == ["prepared"]]
        require(len(eligible) == 1, "Expected one prepared change coin")
        balance = eligible[0]["sats"]
        report["insufficient_pool"] = refusal(node, balance + 1_000_000, rate)
        report["fee_shortfall"] = refusal(node, balance - 1, rate)

        labeled_before = snapshot(node)
        change = next(c for c in node.rpc("listunspent", 1, wallet="receiver")
                      if outpoint(c) == outpoint(eligible[0]))
        node.rpc("setlabel", change["address"], "", wallet="receiver")
        report["missing_label"] = refusal(node, 123_456, rate, missing_label=True)
        # Restore only from known fixture ground truth; not a backup-recovery algorithm.
        node.rpc("setlabel", change["address"], "prepared", wallet="receiver")
        require(snapshot(node) == labeled_before, "Fixture label restoration failed")

        tx, step = payment(node, balance + 1_000_000, rate, miner, allow_merge=True)
        trace["transactions"].append(tx)
        trace["steps"].append(step)
        report["merge_control_audit"] = audit_trace(trace)
        require(report["merge_control_audit"]["steps"][-1]["violations"] == ["wrong_pool"],
                "Offline audit failed to catch the deliberate merge")
        report["status"] = "passed_with_expected_merge_violation"
        return report
    finally:
        try:
            node.stop()
        finally:
            report["owned_node_stopped"] = node.stopped
            (destination / f"fee-{rate}.trace.json").write_text(json.dumps(trace, indent=2) + "\n")
            (destination / f"fee-{rate}.result.json").write_text(json.dumps(report, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bitcoind", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True, help="new directory; never overwritten")
    args = parser.parse_args()
    binary = args.bitcoind.resolve(strict=True)
    destination = fresh_directory(args.work_dir)
    provenance = {"created_utc": datetime.now(timezone.utc).isoformat(),
                  "python": platform.python_version(), "system": platform.system(),
                  "bitcoin_version": subprocess.check_output([str(binary), "--version"], text=True).splitlines()[0],
                  "bitcoin_binary_sha256": digest(binary),
                  "source_sha256": {name: digest(HERE / name) for name in
                                    ("audit.py", "lifecycle.py", "checkout.py", "regtest.py", "run.py")},
                  "scope": "Synthetic labeled regtest coins; no A²L/OpenSwap execution or anonymity measurement."}
    (destination / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    for rate in (1, 10, 50):
        report = run_case(binary, rate, destination)
        require(report["owned_node_stopped"], "Owned regtest node still running")
        print(f"{rate} sat/vB: {report['status']}; fees {report['ordinary_payment_fee_sats']}", flush=True)
    print(f"Results: {destination}")


if __name__ == "__main__":
    main()
