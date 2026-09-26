# Put a coin-pool rule in your wallet tests

This kit checks one rule: a payment requested from a particular pool spends only classified, unspent inputs from that pool; its declared change carries that classification forward. It runs locally, requires Python 3.10+, and makes no network requests during export or audit. It adds no service or transaction step for wallet users.

The formats below are a **draft project contract**, not an adopted Bitcoin standard. Passing the corpus establishes agreement on its examples, not wallet certification or anonymity. Labels, payment intent, change positions and history completeness come from your wallet. Do not derive these annotations from the outcome the test is supposed to check.

## A working example

From the extracted kit directory:

```sh
python3 conformance.py
python3 export_trace.py example-export.json --output example.trace.json
python3 audit.py example.trace.json
```

On Windows PowerShell, replace `python3` with `py -3`. Expected: **27/27 cases passed**, then a clean trace containing two payments with fees of 100 and 200 sat. These small example transactions are unsigned synthetic serializations; they are not broadcastable wallet payments or a fee benchmark. `--output` refuses an existing file; use a new filename on another run.

## Connect your exporter

Have a **synthetic wallet integration test** write a UTF-8 JSON object shaped like [example-export.json](example-export.json):

| Field | Your wallet supplies |
| --- | --- |
| `format` | `"coin-policy-export-v1"` |
| `raw_transactions` | An array of raw transaction hex strings, including the transactions that created the roots. Include all later spends in the history under test and parents needed to verify fees. |
| `roots` | Initial outpoints `{ "txid": "…", "vout": 0, "pool": "prepared" }`. Use the wallet's original classifications. Pool names are arbitrary, nonempty strings. |
| `steps` | Ordered payment requests `{ "txid": "…", "required_pool": "prepared", "payment_vout": 0, "payment_sats": 1000, "change_vout": 1 }`. Use `null` for no declared change. Record intent independently of selected inputs. |

Amounts and indices must be JSON integers, never decimals, booleans or strings. Transaction IDs use 64 lowercase hex characters. Duplicate JSON object fields, `NaN`, `Infinity` and numbers that overflow finite floating-point range are invalid, including in extra metadata. Transaction records can be in any order; payment steps must follow spending order. Additional metadata is ignored after JSON validation. Preserve your native classifications in test evidence and document their mapping to pool names.

Readers must preserve numeric token types to enforce that rule; ordinary JavaScript `JSON.parse` loses the distinction between `6000` and `6000.0`. Writers should emit integer tokens. The bundle and resulting trace each have a 16 MB limit; the exporter enforces its output limit while encoding, before creating an output file. File-size limits are not a fixed process-memory quota.

`export_trace.py` derives transaction IDs, size, weight, inputs and outputs from raw bytes. It preserves supplied roots and requests, rejects inconsistent evidence and writes `coin-policy-trace-v1` for `audit.py`. Export exit **0** means conversion succeeded, even when the trace contains a policy violation. Always run the audit afterward. Export exit **2** means invalid input or an output-file error.

Add these commands after your wallet fixture in CI; each must succeed for a clean-policy fixture:

```sh
set -e
python3 export_trace.py wallet-fixture.json --output wallet.trace.json
python3 audit.py wallet.trace.json
```

For PowerShell CI, check each native exit code explicitly:

```powershell
py -3 export_trace.py wallet-fixture.json --output wallet.trace.json
if ($LASTEXITCODE -ne 0) { throw "Wallet export failed" }
py -3 audit.py wallet.trace.json
if ($LASTEXITCODE -ne 0) { throw "Wallet audit failed" }
```

Use a fresh output path or workspace per run. Stop when export fails: auditing an existing trace afterward could pass against stale evidence.

Audit exit **0** means clean declared policy, **1** a policy violation, and **2** malformed or inconsistent evidence. For a deliberate bad control, assert exit 1 and the expected violation rather than ignoring every failure. The [full trace contract](POLICY_TESTS.md#reuse-in-another-wallet) and recorded signed regtest traces supply further examples. A partial spend should be followed by a payment from its change in your fixture; checking the first payment alone misses label-propagation failures.

## Implement an independent checker

[conformance-v1.json](conformance-v1.json) contains 27 cases with explicit, manually specified expectations: clean change chains, pool mixing, label loss, step ordering, witness size and transaction IDs, empty witness rejection, hidden supplied spends, relabeling, repeated records, dishonest metadata and malformed evidence. The corpus includes valid policies, violated policies and invalid inputs. The unsigned bytes are purpose-built fixtures; the original signed regtest vectors remain covered by `test_policy.py`.

Run any trusted local executable that implements the audit output contract:

```sh
python3 conformance.py -- ./my-checker
python3 conformance.py -- python3 audit.py
```

The runner appends a temporary trace-file path as the last argument. It invokes the command directly without a shell; put flags before the appended path. Only execute a checker you trust. Each invocation has a ten-second timeout (change with `--timeout SECONDS`). The runner stops its direct child on timeout; it is not a sandbox for an arbitrary program or its descendants. Trace files are local and temporary.

The checker must print one JSON object to stdout and return the audit exit code. For `invalid`, only `status` and the exit code are compared; error wording is not fixed. For `clean`/`violated`, the runner additionally requires these output fields:

| Checker field | Comparison against case `expected` |
| --- | --- |
| `steps[].violations` | Ordered arrays, compared with `step_violations` |
| `steps[].fee_sats` | Integer fee or `null`, compared with `step_fee_sats` |
| `steps[].vsize` | Integer virtual size, compared with `step_vsize` |
| `undeclared_spends` | Array length compared with `undeclared_spends` |
| `fees_unverified_missing_parents` | Array length compared with `fees_unverified` |

Both JSON types and values must agree. A checker that prints only `clean`, exits with the wrong code, emits malformed output or times out fails the run. Result JSON includes every case's expected and observed values. Runner exit **0** means all cases agree, **1** a checker mismatch/failure, **2** a corpus or execution setup error. `--corpus FILE` supports a separate experimental corpus; identify the exact file and revision when sharing results.

Cases contain either `trace` (a JSON object) or `json_text` (literal text for ambiguous/malformed JSON). Corpus v1's published cases are fixed; add a new version for additions or changed expectations so comparisons remain reproducible. A disputed expectation needs a minimal reproducer and reasoning about the rule before a change.

## Check the evidence independently

```sh
python3 -m unittest -v test_policy test_runner test_integration test_security
python3 verify_corpus.py --bitcoind /path/to/bitcoind
```

The second command creates a fresh, network-disabled regtest node and stops only that node. It compares the eight distinct serializations in the structured corpus cases with Core's `decoderawtransaction`: six matching decodings and two matching rejections in the [recorded Core 31.1 comparison](conformance-core-31.1.json). It does not verify signatures, consensus validity or wallet labels. No external wallet has been integrated or independently reproduced by this release.

The [live lifecycle fixture](POLICY_TESTS.md#run-the-live-fixture) covers confirmed transactions, saved-wallet restarts and expected balance/fee/label refusals. Its measured fees and refusal counts are controlled examples, not a wallet leaderboard, real-world failure rate or proof of recovery from a seed. Keep these costs beside any policy result when evaluating usability.

## Contribute something verifiable

The most useful next contribution is an exporter from an existing wallet's synthetic tests, with its pinned revision, commands and expected good/bad results. An independently written checker or a case that demonstrates an incorrect verdict is also useful. Start with the [trial report](https://github.com/Bortlesboat/Bortlesboat/issues/new?template=wallet-policy-trial.yml); share synthetic artifacts only. Never publish real wallet histories, seeds or wallet files.

The [September 26 adversarial review](SECURITY_REVIEW.md) records two corrected input/resource defects, the checks performed and demonstrated limits of trusting supplied labels and history. A passing corpus cannot certify a deliberately dishonest checker.

This tooling lives under the kit's [GPL-3.0-only license](LICENSE). It builds on the original attributed A²L experiment while testing a separate declared-policy rule.
