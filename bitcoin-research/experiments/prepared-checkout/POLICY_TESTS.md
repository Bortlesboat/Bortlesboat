# Coin selection after payment and restart

A small regression kit for a specific wallet rule: a payment designated for one coin pool must use only that pool, and its change must retain the classification. This follows the [A²L checkout experiment](README.md). It adds an offline audit and a separate Bitcoin Core test using synthetic wallet labels.

The audit needs only Python 3.10+. The live test needs Python and an installed Bitcoin Core binary; it does not compile the archived cryptography. The original A²L runner and reference results are unchanged.

## Run the offline checks

From this directory:

```sh
python3 -m unittest -v test_policy test_runner
python3 audit.py --reference reference-results.json
```

The second command intentionally exits **1**: the original results include a mined transaction combining prepared and ordinary inputs. Its first two payment steps have no violations; the last reports `wrong_pool`. The unit suite treats detection of this control as the expected result.

The auditor recomputes transaction IDs, weight, virtual size, input outpoints and output amounts from the raw serialization and compares them with the recorded fields. It recomputes fees where every parent transaction is supplied, and lists missing-parent cases instead of trusting their recorded fees. Success flags in the input report are ignored.

This is a byte-consistency and declared-policy check. It does not validate signatures, script execution, block inclusion, address strings or script-type descriptions. A modified witness of the same length can retain the same txid and weight; this auditor does not authenticate witnesses. Bitcoin Core validates the transactions in the live fixture.

## Run the live fixture

Use Linux or WSL, with a new output directory:

```sh
python3 lifecycle.py --bitcoind /path/to/bitcoind --work-dir /path/to/new-results
```

The command runs three independent cases at configured rates of 1, 10 and 50 sat/vB. Each starts a fresh regtest node with peer networking disabled. It never uses an existing Bitcoin configuration or wallet. Existing output directories are refused. Only its own node is stopped, including after failures. Disposable wallet datadirs remain local for diagnosis; do not share them.

Each case:

1. Funds a receiver with 10,000,000 sat labeled `prepared` and 5,000,000 sat labeled `ordinary`. Both are ordinary regtest coins; no swap or preparation protocol runs.
2. Pays 123,456 sat using explicitly selected `prepared` inputs and labels the change.
3. Stops the node, restarts it using the same datadir, reopens the wallet, and compares its outpoints, amounts, labels and chain height. It then pays another 1,234,567 sat from the change.
4. Requires two Core funding refusals: a payment exceeding the eligible pool, and a payment leaving only one sat for fees. The wallet has enough total value in its two pools. Coins, labels and mempool must stay unchanged.
5. Removes the change label deliberately. The adapter must refuse a payment because it has no classified eligible inputs. It restores the label from the fixture's known history.
6. Enables automatic input addition deliberately, mines a transaction joining both pools, and requires the offline auditor to detect `wrong_pool`.

The adapter selects inputs and carries labels forward explicitly. This is not a claim that Bitcoin Core supplies this policy automatically. Restart uses the full saved wallet; seed-only recovery, backup loss, crash consistency and reorgs are outside this fixture. Restoring a deliberately removed label from known test data is not a recovery algorithm. The fee check allows Core's estimate to exceed signed virtual size by one vbyte per input; a run outside this fixture tolerance fails for investigation.

## Recorded run

The author's September 25, 2026 run on Core 31.1, Python 3.12.3, Ubuntu under WSL passed all three cases. Six payments confirmed, three saved-wallet restarts preserved labels, nine refusal checks left coins and mempool unchanged, and all three deliberate merges were detected. All owned nodes stopped.

| Configured fee rate | First payment fee / size | Second payment fee / size | Restart and refusal checks | Merge control |
| --- | --- | --- | --- | --- |
| 1 sat/vB | 141 sat / 141 vB | 141 sat / 141 vB | Passed | Detected |
| 10 sat/vB | 1,410 sat / 141 vB | 1,410 sat / 141 vB | Passed | Detected |
| 50 sat/vB | 7,050 sat / 141 vB | 7,050 sat / 141 vB | Passed | Detected |

Evidence: [source and binary hashes](policy-reference/provenance.json), [1 sat/vB result](policy-reference/fee-1.result.json), [10 sat/vB result](policy-reference/fee-10.result.json), [50 sat/vB result](policy-reference/fee-50.result.json). Each result has a matching `.trace.json` containing the raw transactions and supplied policy annotations. Fresh keys and signatures can change txids and sizes.

These are controlled examples, not observed market fees, a payment-failure rate or an anonymity measurement. They show a concrete usability tradeoff: a wallet can refuse a payment despite sufficient total funds when combining pools is forbidden. The missing-label case shows another dependency: the wallet needs its classification data to apply the rule. This kit does not determine whether merging a particular pair of pools would harm a user's privacy.

## Reuse in another wallet

Export a JSON object with `format: "coin-policy-trace-v1"` and these fields; the recorded traces provide complete examples:

| Field | Contents |
| --- | --- |
| `transactions` | Unique records with `raw_hex`, `txid`, `vsize`, `weight`, `inputs` (`txid`, `vout`) and `outputs` (`vout`, integer `sats`). Optional integer `fee_sats` is checked when all parents are present. |
| `roots` | Initial classified outpoints: `txid`, `vout`, `pool`. Their transactions must be included. Roots cannot relabel a payment's output. |
| `steps` | Ordered payments: `txid`, `required_pool`, `payment_vout`, integer `payment_sats`, and `change_vout` (an index or `null`). |

Run `python3 audit.py your-trace.json`. Exit codes: **0** clean declared policy, **1** policy violation, **2** malformed or inconsistent evidence. Every step consumes its inputs. Only a passing step passes its pool label to its declared change; undeclared outputs stay unclassified. Duplicate steps and conflicting roots are rejected. Missing or already consumed input labels fail closed.

Every supplied transaction that spends an initially classified coin or classified change must also appear in `steps`. Otherwise the audit reports `undeclared_spend_of_classified_coin`, including when an exporter tries to reset the classification by supplying a new root. To audit a prefix of a history, omit its later transactions as well as their steps. The auditor still cannot detect transactions or initial classifications the exporter never supplies.

The exporter supplies the truth about pool labels and which output is change. The public graph establishes spending edges, not who owns the outputs or what an outside observer can infer. Correct labels are an input assumption; forged labels can produce a misleading result. The audit does not prove a supplied history is complete.

A useful next integration is to export these facts from an existing wallet's integration tests, preserving its own source classifications. No OpenSwap code is changed or tested by this kit, and no outside reproduction or adoption is claimed. The directory's [GPL-3.0-only license](LICENSE) applies.
