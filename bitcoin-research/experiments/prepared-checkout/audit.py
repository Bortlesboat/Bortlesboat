# SPDX-License-Identifier: GPL-3.0-only
"""Offline byte/graph consistency and declared coin-pool policy checks.

No signature, consensus, chain inclusion, ownership or anonymity verification.
Pool labels and change positions are supplied wallet ground truth.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

MAX_JSON_BYTES = 16_000_000


def check(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def unique_object(pairs: list[tuple]) -> dict:
    result = {}
    for name, value in pairs:
        check(name not in result, f"Duplicate JSON field: {name}")
        result[name] = value
    return result


def finite_number(token: str) -> float:
    number = float(token)
    check(math.isfinite(number), "Non-finite JSON number")
    return number


def read_json(path: Path) -> dict:
    with path.open("rb") as source:
        data = source.read(MAX_JSON_BYTES + 1)
    check(len(data) <= MAX_JSON_BYTES, "JSON exceeds 16 MB limit")
    # Apply to ignored metadata too: accepted evidence must remain portable JSON.
    return json.loads(data.decode("utf-8-sig"), object_pairs_hook=unique_object,
                      parse_float=finite_number, parse_constant=finite_number)


def index(value: int, size: int) -> int:
    check(type(value) is int and 0 <= value < size, "Invalid output index")
    return value


class Reader:
    def __init__(self, data: bytes):
        self.data, self.pos = data, 0

    def take(self, size: int) -> bytes:
        check(size <= len(self.data) - self.pos, "Truncated transaction")
        start = self.pos
        self.pos += size
        return self.data[start:self.pos]

    def compact(self) -> int:
        prefix = self.take(1)[0]
        if prefix < 253:
            return prefix
        width, minimum = {253: (2, 253), 254: (4, 65536), 255: (8, 4294967296)}[prefix]
        value = int.from_bytes(self.take(width), "little")
        check(value >= minimum, "Noncanonical CompactSize")
        return value

    def vector(self) -> bytes:
        return self.take(self.compact())


def decode_transaction(raw_hex: str) -> dict:
    """Decode bounded legacy/SegWit serialization; scripts are opaque bytes."""
    check(isinstance(raw_hex, str) and len(raw_hex) <= 8_000_000,
          "Expected at most four million transaction bytes")
    data = bytes.fromhex(raw_hex)
    reader = Reader(data)
    version = reader.take(4)
    witness = data[4:5] == b"\x00"
    if witness:
        check(reader.take(2) == b"\x00\x01", "Unsupported witness flags")
    body_start = reader.pos
    inputs = []
    count = reader.compact()
    check(0 < count <= len(data) // 41, "Invalid input count")
    for _ in range(count):
        inputs.append({"txid": reader.take(32)[::-1].hex(),
                       "vout": int.from_bytes(reader.take(4), "little")})
        reader.vector()  # scriptSig
        reader.take(4)  # sequence
    check(len({(i["txid"], i["vout"]) for i in inputs}) == count, "Duplicate input")
    outputs = []
    count = reader.compact()
    check(0 < count <= len(data) // 9, "Invalid output count")
    for position in range(count):
        amount = int.from_bytes(reader.take(8), "little")
        check(amount <= 2_100_000_000_000_000, "Output exceeds money range")
        outputs.append({"vout": position, "sats": amount,
                        "script_hex": reader.vector().hex()})
    check(sum(o["sats"] for o in outputs) <= 2_100_000_000_000_000,
          "Output total exceeds money range")
    body_end = reader.pos
    if witness:
        has_witness = False
        for _ in inputs:
            count = reader.compact()
            check(count <= len(data) - reader.pos, "Invalid witness item count")
            has_witness |= count > 0
            for _ in range(count):
                reader.vector()
        check(has_witness, "Superfluous witness serialization")
    locktime = reader.take(4)
    check(reader.pos == len(data), "Trailing transaction bytes")
    stripped = version + data[body_start:body_end] + locktime
    weight = len(stripped) * 3 + len(data)
    return {"txid": hashlib.sha256(hashlib.sha256(stripped).digest()).digest()[::-1].hex(),
            "vsize": (weight + 3) // 4, "weight": weight,
            "inputs": inputs, "outputs": outputs}


def key(coin: dict) -> tuple[str, int]:
    check(isinstance(coin["txid"], str) and len(coin["txid"]) == 64
          and all(c in "0123456789abcdef" for c in coin["txid"])
          and type(coin["vout"]) is int and 0 <= coin["vout"] <= 0xffffffff,
          "Invalid outpoint")
    return coin["txid"], coin["vout"]


def audit_trace(trace: dict) -> dict:
    check(trace["format"] == "coin-policy-trace-v1", "Unknown trace format")
    for field in ("transactions", "roots", "steps"):
        check(isinstance(trace[field], list), f"{field} must be an array")
    transactions = {}
    for record in trace["transactions"]:
        decoded = decode_transaction(record["raw_hex"])
        txid = decoded["txid"]
        check(txid not in transactions, "Duplicate transaction record")
        for field in ("vsize", "weight"):
            check(type(record[field]) is int, f"Recorded {field} must be an integer")
        check(isinstance(record["inputs"], list) and isinstance(record["outputs"], list),
              "Inputs and outputs must be arrays")
        for item in record["inputs"]:
            key(item)
        for item in record["outputs"]:
            check(type(item["vout"]) is int and type(item["sats"]) is int,
                  "Output index and amount must be integers")
        if "fee_sats" in record:
            check(type(record["fee_sats"]) is int and record["fee_sats"] >= 0,
                  "Recorded fee must be a nonnegative integer")
        for field in ("txid", "vsize", "weight", "inputs"):
            check(record[field] == decoded[field], f"Recorded {field} differs from bytes")
        expected = [{"vout": o["vout"], "sats": o["sats"]} for o in decoded["outputs"]]
        actual = [{"vout": o["vout"], "sats": o["sats"]} for o in record["outputs"]]
        check(actual == expected, "Recorded outputs differ from bytes")
        transactions[txid] = decoded

    def output(coin: dict) -> dict:
        txid, vout = key(coin)
        check(txid in transactions, "Referenced transaction is missing")
        outputs = transactions[txid]["outputs"]
        return outputs[index(vout, len(outputs))]

    fees, missing = {}, []
    for record in trace["transactions"]:
        decoded = transactions[record["txid"]]
        # A missing parent prevents fee computation, not validation of known edges.
        for item in decoded["inputs"]:
            if item["txid"] in transactions:
                output(item)
        if any(i["txid"] not in transactions for i in decoded["inputs"]):
            missing.append(decoded["txid"])
            continue
        fee = sum(output(i)["sats"] for i in decoded["inputs"]) - sum(
            o["sats"] for o in decoded["outputs"])
        check(fee >= 0, "Transaction creates value from known parents")
        if "fee_sats" in record:
            check(type(record["fee_sats"]) is int and record["fee_sats"] == fee,
                  "Recorded fee differs from known parents")
        fees[decoded["txid"]] = fee

    check(bool(trace["steps"]), "No policy steps supplied")
    step_txids = {s["txid"] for s in trace["steps"]}
    check(len(step_txids) == len(trace["steps"]), "Repeated policy transaction")
    available = {}
    for root in trace["roots"]:
        point = key(root)
        output(root)
        check(point not in available and point[0] not in step_txids,
              "Duplicate root or relabelled payment output")
        check(isinstance(root["pool"], str) and bool(root["pool"]), "Empty pool")
        available[point] = root["pool"]

    classified = set(available)
    steps = []
    for step in trace["steps"]:
        txid, pool = step["txid"], step["required_pool"]
        check(txid in transactions, "Policy transaction is missing")
        check(isinstance(pool, str) and bool(pool), "Empty required pool")
        tx = transactions[txid]
        payment = tx["outputs"][index(step["payment_vout"], len(tx["outputs"]))]
        check(type(step["payment_sats"]) is int and payment["sats"] == step["payment_sats"],
              "Declared payment differs from bytes")
        change = step["change_vout"]
        if change is not None:
            index(change, len(tx["outputs"]))
            check(change != step["payment_vout"], "Payment cannot also be change")
        input_pools = [available.get(key(i)) for i in tx["inputs"]]
        violations = []
        if None in input_pools:
            violations.append("unclassified_or_spent_input")
        if any(p is not None and p != pool for p in input_pools):
            violations.append("wrong_pool")
        for item in tx["inputs"]:
            available.pop(key(item), None)
        if not violations and change is not None:
            available[(txid, change)] = pool
            classified.add((txid, change))
        steps.append({"txid": txid, "required_pool": pool, "input_pools": input_pools,
                      "fee_sats": fees.get(txid), "vsize": tx["vsize"],
                      "violations": violations})
    undeclared = []
    for txid, tx in transactions.items():
        if txid not in step_txids:
            consumed = [i for i in tx["inputs"] if key(i) in classified]
            if consumed:
                undeclared.append({"txid": txid, "classified_inputs": consumed,
                                   "violation": "undeclared_spend_of_classified_coin"})
    return {"status": "violated" if undeclared or any(s["violations"] for s in steps) else "clean",
            "scope": "Declared pool policy and byte consistency only; anonymity not measured.",
            "transactions_checked": len(transactions), "fees_verified": len(fees),
            "fees_unverified_missing_parents": missing, "steps": steps,
            "undeclared_spends": undeclared}


def reference_trace(report: dict) -> dict:
    """Adapt the original, unchanged A²L results (including its bad control)."""
    payments = report["checkouts"]
    check(len(payments) == 2, "Expected the two original checkout records")
    control = report["unsafe_topup_control"]
    steps = []
    for tx, change in zip(payments, [payments[1]["inputs"][0], control["prepared_input"]]):
        check(change["txid"] == tx["txid"], "Broken reference change edge")
        vout = change["vout"]
        check(len(tx["outputs"]) == 2, "Expected payment and change")
        index(vout, 2)
        check(tx["outputs"][vout]["sats"] == tx["change_sats"], "Wrong change amount")
        steps.append({"txid": tx["txid"], "required_pool": "prepared",
                      "payment_vout": 1 - vout, "payment_sats": tx["payment_sats"],
                      "change_vout": vout})
    amount = report["insufficient_prepared_balance"]["requested_sats"]
    candidates = [o["vout"] for o in control["outputs"] if o["sats"] == amount]
    check(len(candidates) == 1, "Ambiguous control payment")
    steps.append({"txid": control["txid"], "required_pool": "prepared",
                  "payment_vout": candidates[0], "payment_sats": amount, "change_vout": None})
    return {"format": "coin-policy-trace-v1",
            "transactions": report["preparation"]["transactions"] +
            [report["setup_control_deposit"]] + payments + [control],
            "roots": [{**report["preparation"]["ready_coin"], "pool": "prepared"},
                      {**control["unprepared_input"], "pool": "ordinary"}],
            "steps": steps}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="coin-policy-trace-v1 JSON, or original results")
    parser.add_argument("--reference", action="store_true", help="adapt original A²L results")
    args = parser.parse_args()
    try:
        trace = read_json(args.trace)
        result = audit_trace(reference_trace(trace) if args.reference else trace)
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError, RecursionError) as error:
        print(json.dumps({"status": "invalid", "error": str(error)}))
        return 2
    print(json.dumps(result, indent=2))
    return 1 if result["status"] == "violated" else 0


if __name__ == "__main__":
    raise SystemExit(main())
