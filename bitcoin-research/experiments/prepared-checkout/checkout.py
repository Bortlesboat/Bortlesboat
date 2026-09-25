# SPDX-License-Identifier: GPL-3.0-only
"""Test ordinary Bitcoin checkout after an A2L preparation process has exited.

Disposable regtest coins only. This measures spendability, costs and visible
transaction edges, not anonymity. The two wallet roles in the preparation are
treated as belonging to one user; the merchant joins only at checkout.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE = Path(__file__).resolve().parent
from regtest import Regtest, require

SATOSHIS = 100_000_000



def sats(value: float | str) -> int:
    exact = Decimal(str(value)) * SATOSHIS
    require(exact == exact.to_integral_value(), "Unexpected fractional satoshi")
    return int(exact)


def btc(value: int) -> float:
    return value / SATOSHIS


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def outpoint(coin: dict) -> dict:
    return {"txid": coin["txid"], "vout": coin["vout"]}


def coin_ids(coins: list[dict]) -> set[tuple[str, int]]:
    return {(coin["txid"], coin["vout"]) for coin in coins}


def space_cost_scenarios(prep_vb: int, payment_vbytes: list[int]) -> list[dict]:
    require(len(payment_vbytes) == 2, "Expected two measured checkouts")
    scenarios = []
    for count in (1, 2, 10):
        measured = count <= len(payment_vbytes)
        total = sum(payment_vbytes[:count]) if measured else count * sum(payment_vbytes) / len(payment_vbytes)
        scenarios.append({
            "ordinary_payments": count,
            "basis": "measured" if measured else "modeled_from_two_payment_mean",
            "measured_payment_vbytes": payment_vbytes[:count] if measured else None,
            "preparation_vbytes": prep_vb, "baseline_total_vbytes": total,
            "prepared_total_vbytes": prep_vb + total,
            "additional_vbytes_per_payment": prep_vb / count,
            "at_2_sat_per_vbyte_extra_network_sats_total": 2 * prep_vb,
            "at_10_sat_per_vbyte_extra_network_sats_total": 10 * prep_vb,
        })
    return scenarios


def transaction_record(node: Regtest, txid: str, blockhash: str) -> dict:
    tx = node.rpc("getrawtransaction", txid, True, blockhash)
    return {
        "txid": txid,
        "blockhash": blockhash,
        "vsize": tx["vsize"],
        "weight": tx["weight"],
        "inputs": [outpoint(item) for item in tx["vin"]],
        "outputs": [{"vout": item["n"], "sats": sats(item["value"]),
                     "script_type": item["scriptPubKey"]["type"],
                     "address": item["scriptPubKey"].get("address")}
                    for item in tx["vout"]],
        "raw_hex": tx["hex"],
    }


def mine_transaction(node: Regtest, signed: dict, miner: str) -> dict:
    require(signed["complete"] is True, "Wallet could not sign by itself")
    admitted = node.rpc("testmempoolaccept", [signed["hex"]])[0]
    require(admitted.get("allowed") is True, f"Checkout rejected: {admitted}")
    txid = node.rpc("sendrawtransaction", signed["hex"])
    blockhash = node.rpc("generatetoaddress", 1, miner)[0]
    require(txid in node.rpc("getblock", blockhash)["tx"], "Checkout was not mined")
    return {**transaction_record(node, txid, blockhash),
            "fee_sats": sats(admitted["fees"]["base"]),
            "confirmed_height": node.rpc("getblockcount")}


def isolated_checkout(node: Regtest, coin: dict, payment_sats: int,
                      merchant: str, miner: str, fee_sats: int = 1000) -> tuple[dict, dict]:
    """Spend exactly the selected prepared coin; change keeps its origin group."""
    change_sats = sats(coin["amount"]) - payment_sats - fee_sats
    require(change_sats > 546, "This test requires a non-dust change output")
    pay_address = node.rpc("getnewaddress", "", "bech32", wallet=merchant)
    change_address = node.rpc("getrawchangeaddress", "bech32", wallet="receiver")
    raw = node.rpc("createrawtransaction", [outpoint(coin)],
                   [{pay_address: btc(payment_sats)}, {change_address: btc(change_sats)}])
    signed = node.rpc("signrawtransactionwithwallet", raw, wallet="receiver")
    tx = mine_transaction(node, signed, miner)
    require(tx["inputs"] == [outpoint(coin)], "Checkout added an unexpected input")
    require(tx["fee_sats"] == fee_sats, "Unexpected checkout fee")
    require(all(item["script_type"] == "witness_v0_keyhash" for item in tx["outputs"]),
            "Expected ordinary P2WPKH payment and change")
    received = node.rpc("listunspent", 1, wallet=merchant)
    require(sum(sats(item["amount"]) for item in received) == payment_sats,
            "Merchant did not receive the requested amount")
    change = [item for item in node.rpc("listunspent", 1, wallet="receiver")
              if item["txid"] == tx["txid"] and item["address"] == change_address]
    require(len(change) == 1, "Could not identify the new change output")
    return {**tx, "payment_sats": payment_sats, "change_sats": change_sats,
            "merchant_wallet": merchant, "origin_group": "preparation_1",
            "uses_only_selected_prepared_coin": True}, change[0]


def run(work: Path, artifacts: Path, binary: Path, env: dict, cargo: Path) -> None:
    report = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Single-process A2L preparation, then normal Core wallet payments on isolated regtest.",
        "upstream_commit": "a261027f4bdb2384f715efa3f634d5796fe95019",
        "bitcoin_version": subprocess.check_output([str(binary), "--version"], text=True).splitlines()[0],
        "bitcoin_binary_sha256": digest(binary),
        "transaction_source_sha256": digest(work / "src/bitcoin.rs"),
        "adapter_sha256": digest(work / "tests/community_checkout.rs"),
        "experiment_sha256": digest(Path(__file__)),
        "harness_sha256": digest(HERE / "regtest.py"),
        "checks": {},
    }
    node = Regtest(binary)
    try:
        node.start()
        node.rpc("createwallet", "lab_funder")
        cookie = (node.directory / "regtest/.cookie").read_text().strip()
        case_env = {**env, "A2L_TEST_RPC_URL": f"http://{cookie}@127.0.0.1:{node.port}"}
        log_path = artifacts / "preparation.log"
        with log_path.open("w") as log:
            outcome = subprocess.run(
                [str(cargo), "test", "--locked", "--release", "--test", "community_checkout",
                 "e2e_happy_path", "--", "--exact", "--test-threads=1", "--nocapture"],
                cwd=work, env=case_env, stdout=log, stderr=subprocess.STDOUT, timeout=180)
        require(outcome.returncode == 0, f"Preparation failed; see {log_path}")
        log_text = log_path.read_text()
        require("1 passed; 0 failed" in log_text, "Expected one passing preparation test")
        traces = [json.loads(item) for item in re.findall(r"A2L_LAB_TX (\{[^\n]+\})", log_text)]
        preflight = [json.loads(item) for item in re.findall(r"A2L_LAB_PREFLIGHT (\{[^\n]+\})", log_text)]
        require(len(traces) == len(preflight) == 4, "Expected four protocol transactions")
        protocol = []
        for item, check in zip(traces, preflight):
            require(item["txid"] == check["txid"], "Trace order mismatch")
            height = check["tip_height"] + 1
            blockhash = node.rpc("getblockhash", height)
            require(item["txid"] in node.rpc("getblock", blockhash)["tx"], "Preparation not mined")
            protocol.append({**transaction_record(node, item["txid"], blockhash),
                             "fee_sats": sats(item["ready"]["fees"]["base"]),
                             "confirmed_height": height})

        ready_coins = node.rpc("listunspent", 1, wallet="receiver")
        require(len(ready_coins) == 1 and sats(ready_coins[0]["amount"]) == 10_000_000,
                "Expected the completed 0.1 BTC preparation output")
        prepared = ready_coins[0]
        require(prepared["txid"] == protocol[-1]["txid"], "Wrong prepared output")
        require(prepared["spendable"] is True, "Prepared output is not wallet-spendable")

        # A deliberately unprepared coin in the SAME wallet exposes unsafe top-up behavior.
        extra_address = node.rpc("getnewaddress", "unprepared-control", "bech32", wallet="receiver")
        topup_txid = node.rpc("sendtoaddress", extra_address, btc(5_000_000), wallet="lab_funder")
        miner = node.rpc("getnewaddress", "", "bech32", wallet="lab_funder")
        topup_block = node.rpc("generatetoaddress", 1, miner)[0]
        extra = [item for item in node.rpc("listunspent", 1, wallet="receiver")
                 if item["txid"] == topup_txid]
        require(len(extra) == 1 and sats(extra[0]["amount"]) == 5_000_000,
                "Expected the separate unprepared control coin")
        report["setup_control_deposit"] = transaction_record(node, topup_txid, topup_block)

        # The Rust process has exited. Also remove access to every helper/source wallet.
        unloaded = ["tumbler_promise", "tumbler_solver", "sender", "lab_funder"]
        for wallet in unloaded:
            node.rpc("unloadwallet", wallet)
        require(node.rpc("listwallets") == ["receiver"], "Unexpected wallet remains loaded")
        inaccessible = []
        for wallet in ("tumbler_promise", "tumbler_solver", "sender"):
            try:
                node.rpc("getwalletinfo", wallet=wallet)
            except RuntimeError as error:
                require("-18" in str(error), "Wrong unloaded-wallet error")
                inaccessible.append(wallet)
            else:
                raise AssertionError("Helper/source wallet was still accessible")
        report["helper_unavailability"] = {
            "rust_process_returncode": outcome.returncode,
            "all_protocol_actors_in_exited_process": True,
            "unloaded_wallets": unloaded,
            "wallet_access_rejected": inaccessible,
            "not_a_secure_key_deletion_claim": True,
        }
        report["preparation"] = {
            "transactions": protocol, "ready_coin": outpoint(prepared), "ready_sats": 10_000_000,
            "total_vbytes": sum(item["vsize"] for item in protocol),
            "total_network_fee_sats": sum(item["fee_sats"] for item in protocol),
            "configured_helper_fee_sats": 10_000,
            "fixture_funding_and_control_deposit_excluded_from_protocol_cost": True,
        }
        report["checks"]["completed_preparation"] = "passed"
        print("PASS preparation: four confirmed protocol transactions; helper process exited and wallets unloaded", flush=True)

        # The merchant did not exist during preparation and never speaks A2L.
        node.rpc("createwallet", "merchant_one")
        first, change_one = isolated_checkout(node, prepared, 123_456, "merchant_one", miner)
        node.rpc("createwallet", "merchant_two")
        second, change_two = isolated_checkout(node, change_one, 1_234_567, "merchant_two", miner)
        report["checkouts"] = [first, second]
        report["checks"]["arbitrary_amount_without_helper"] = "passed"
        report["checks"]["repeat_payment_from_change_without_helper"] = "passed"
        remaining = node.rpc("listunspent", 1, wallet="receiver")
        require(coin_ids(remaining) == coin_ids([extra[0], change_two]), "Unexpected remaining coins")
        require(node.rpc("gettxout", extra[0]["txid"], extra[0]["vout"]) is not None,
                "Ordinary checkouts consumed the unprepared coin")
        print("PASS checkout: two arbitrary amounts paid with receiver signatures alone", flush=True)

        # A larger payment fits the overall wallet, but not its prepared balance.
        prepared_remaining = sats(change_two["amount"])
        requested = prepared_remaining + 1_000_000
        available = sum(sats(item["amount"]) for item in remaining)
        require(prepared_remaining < requested < available, "Invalid insufficient-prepared-balance control")
        node.rpc("createwallet", "merchant_control")
        control_address = node.rpc("getnewaddress", "", "bech32", wallet="merchant_control")
        selected_only = node.rpc("createrawtransaction", [outpoint(change_two)],
                                 [{control_address: btc(requested)}])
        mempool_before = node.rpc("getrawmempool")
        try:
            node.rpc("fundrawtransaction", selected_only,
                     {"add_inputs": False, "fee_rate": 2}, wallet="receiver")
        except RuntimeError as error:
            require("preselected coins total amount does not cover" in str(error)
                    or "Insufficient funds" in str(error), "Wrong selected-only refusal")
            refusal = str(error)
        else:
            raise AssertionError("A prepared-only payment silently used other coins")
        require(node.rpc("getrawmempool") == mempool_before, "Refusal changed the mempool")
        require(coin_ids(node.rpc("listunspent", 1, wallet="receiver")) == coin_ids(remaining),
                "Refusal changed the wallet's coins")
        report["insufficient_prepared_balance"] = {
            "prepared_sats": prepared_remaining, "total_wallet_sats": available,
            "requested_sats": requested, "add_inputs": False,
            "core_error": refusal, "coins_unchanged": True, "nothing_broadcast": True,
            "policy_scope": "Coin control prevents merging; this is not an anonymity judgment.",
        }
        report["checks"]["no_silent_topup_with_coin_control"] = "passed"

        # Deliberate negative control: ordinary automatic funding is allowed to merge both.
        auto_raw = node.rpc("createrawtransaction", [], [{control_address: btc(requested)}])
        auto_funded = node.rpc("fundrawtransaction", auto_raw,
                               {"fee_rate": 2, "change_type": "bech32"}, wallet="receiver")
        auto_decoded = node.rpc("decoderawtransaction", auto_funded["hex"])
        require(coin_ids(auto_decoded["vin"]) == coin_ids(remaining),
                "Expected automatic funding to join the prepared and unprepared inputs")
        merged = mine_transaction(node, node.rpc("signrawtransactionwithwallet", auto_funded["hex"],
                                                 wallet="receiver"), miner)
        require(merged["fee_sats"] == sats(auto_funded["fee"]), "Wrong automatic funding fee")
        report["unsafe_topup_control"] = {
            **merged, "expected_unsafe_behavior_reproduced": True,
            "publicly_joins_prepared_and_unprepared_outpoints": True,
            "prepared_input": outpoint(change_two), "unprepared_input": outpoint(extra[0]),
            "warning": "A common transaction is observable; ownership or real identity remains an inference.",
        }
        report["checks"]["unsafe_automatic_topup_control"] = "reproduced_expected_linkage"

        # Verify graph claims from actual mined transaction inputs, not wallet labels.
        require(first["inputs"] == [outpoint(prepared)], "Missing preparation-to-payment edge")
        require(second["inputs"] == [outpoint(change_one)], "Missing repeated-spend edge")
        require(coin_ids(merged["inputs"]) == coin_ids([change_two, extra[0]]), "Missing merge edge")
        report["observability"] = {
            "preparation_output_to_first_checkout": True,
            "first_checkout_change_to_second_checkout": True,
            "second_checkout_change_to_unprepared_merge": True,
            "all_output_amounts_public": True,
            "wallet_labels_used_only_to_identify_ground_truth": True,
            "change_ownership_not_proven_by_public_graph_alone": True,
            "anonymity_not_measured": True,
        }
        report["checks"]["public_transaction_edges"] = "passed"

        # Normalize only miner space cost. These are scenarios, not current fee quotes.
        prep_vb = report["preparation"]["total_vbytes"]
        payment_vbytes = [first["vsize"], second["vsize"]]
        report["space_cost_scenarios"] = space_cost_scenarios(prep_vb, payment_vbytes)
        report["cost_scope"] = (
            "A2L costs sum both sides' four protocol transactions. Source fixtures, the deliberate "
            "unprepared deposit and unsafe control are excluded. Helper fee is a separate fixture "
            "parameter, not a market quote or an additional network fee. Ten payments are modeled, "
            "not executed; change reuse does not create ten independent privacy histories."
        )
        network = node.rpc("getnetworkinfo")
        require(network["networkactive"] is False and network["connections"] == 0,
                "Unexpected network activation")
        report["networkactive"] = network["networkactive"]
        report["connections"] = network["connections"]
        report["loaded_wallets_at_end"] = node.rpc("listwallets")
        require(not set(unloaded).intersection(report["loaded_wallets_at_end"]),
                "A helper/source wallet was reloaded during checkout")
        report["status"] = "checks_passed"
        print("PASS controls: prepared-only overspend refused; automatic top-up exposed the common transaction", flush=True)
    finally:
        try:
            node.stop()
        finally:
            report["owned_daemon_stopped"] = node.stopped
            report["status"] = "passed" if node.stopped and report.get("status") == "checks_passed" else "incomplete"
            (artifacts / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    require(node.stopped, "Owned daemon did not stop")
    print(f"PASS isolated experiment; preparation {prep_vb} vB, normal checkouts {payment_vbytes} vB; node stopped", flush=True)
