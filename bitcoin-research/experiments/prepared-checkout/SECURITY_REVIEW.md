# Adversarial test findings — September 26, 2026

Local testing of v0.2.0 found two defects, corrected in **v0.2.1**: non-finite JSON values could pass validation, and an oversized export could exhaust a constrained worker's memory before its size check. Regression tests reproduce both failures on the earlier code and pass with the fixes. No new policy-verdict bypass was found with the original labels and relevant transaction bytes retained in the tested cases.

This is an author-run review of a small developer tool, not an independent security audit, wallet certification or Bitcoin privacy assessment. The tests used synthetic local data and fresh, network-disabled Core nodes. No public service or real wallet was attacked. The original A²L protocol and its security are outside this review.

## Findings, in priority order

### 1. Medium: oversized export can exhaust a constrained local worker — fixed

**Impact:** a supplied fixture can terminate a memory-limited export process before it produces a controlled size-limit error.

A 7,200,354-byte bundle with 400,000 minimal outputs was below the input limit. The exporter built the entire indented JSON string before checking its length. Under a 384 MiB address-space limit, the old path raised an uncaught `MemoryError` during the final string join and exited 1. The bounded probe recorded approximately 369 MiB peak child RSS. It used synthetic unsigned bytes, not a consensus-valid transaction.

The fix in [`export_trace.py:26`](export_trace.py#L26) counts encoded bytes incrementally and stops at the existing 16 MB output limit. Python 3.10 CI also exposed unnecessary output-list copies in validation; [`audit.py:154`](audit.py#L154) now compares the same fields incrementally after checking equal lengths. The same memory-constrained regression now exits 2 with the size-limit error and creates no destination file. These changes avoid the observed allocations; they do not promise a fixed memory quota for all parsing and decoding work.

### 2. Low: non-finite JSON values pass through extra metadata — fixed

`NaN`, `Infinity` and `-Infinity` in otherwise valid extra metadata were accepted as clean input. Export could emit these nonstandard tokens with exit 0, and a checker response containing them could pass conformance. A valid numeric token such as `1e400` also overflowed to infinity and could produce nonstandard output. No payment-amount or pool-label bypass was observed: those fields already had separate type checks.

The shared reader in [`audit.py:31`](audit.py#L31) now rejects non-finite constants and floating-point overflow throughout the input, including extra metadata. The exporter also disables non-finite number serialization. Twelve regressions across audit, export and checker output failed before the fix and now pass. The behavior follows Python's documented [JSON parsing controls and non-finite defaults](https://docs.python.org/3/library/json.html#infinite-and-nan-number-values).

## What was exercised

| Check | Observed outcome |
| --- | --- |
| 36 CLI scenarios | Fixed code matched all expectations, including two explicit trust-boundary demonstrations below. |
| Malformed evidence | Deep JSON, invalid UTF-8, escaped duplicate fields, oversized files, huge integers and incorrect container types were rejected. |
| Policy tampering | Missing labels, wrong requested pools, missing change labels, reversed steps and an omitted merge step with its bytes retained were detected. |
| Existing destinations | Existing files and hard-linked destinations were preserved. |
| Six hostile checker responses | False success, wrong exit code, duplicate fields, invalid encoding, oversized stdout and a sleeping checker failed the run. |
| 5,000 seeded transaction-byte mutations | 4,314 rejected; 686 decoded; no unexpected decoder exceptions. Decoding does not establish consensus validity. |
| 150 separately seeded, decoded mutations | Transaction ID, size, weight, inputs and outputs matched Bitcoin Core 31.1. |
| Original corpus | All 27 cases remain unchanged and pass. The eight-serialization Core comparison was refreshed against patched source. |
| Full suite | 34 tests pass on Linux. Windows/macOS skip the one Linux-specific memory-budget check. |

The mutation exercises are bounded samples, not exhaustive coverage. The review did not test Bitcoin signatures, anonymity, network attacks, a third-party wallet integration or abrupt wallet crashes. Existing recorded wallet fixtures remain covered by the suite; a new live payment lifecycle was not needed for these JSON/serialization changes.

## Demonstrated limits of a clean result

- **A dishonest exporter can hide a violation.** Removing both the bad step and its transaction, or changing the original labels so both pools appear identical, produced a clean result. The auditor has no independent wallet history or label authority to contradict those inputs. Keeping the bad bytes while omitting just the step was detected in the tested case.
- **A dishonest checker can memorize the corpus.** A lookup program containing the published expected answers passed all 27 cases without decoding transactions. Conformance tests measure agreement on examples; they do not authenticate an implementation.
- **A custom checker is trusted executable code.** The runner uses direct arguments without a shell, but it is not a sandbox. Its timeout stops the direct child, not arbitrary descendants. File-backed checker logs have no hard disk quota. Run trusted code in an appropriately isolated CI environment.

These are limits of the declared-policy model. A clean result means that supplied evidence passed these rules, not that a wallet is private or safe.

## Reproduce the corrected defects

From the kit directory:

```sh
python3 -m unittest -v test_security
python3 -m unittest -v test_policy test_runner test_integration test_security
python3 conformance.py
```

On Windows use `py -3`. The resource regression runs on Linux and constrains only its own exporter child to 384 MiB with a 20-second timeout. Tests use temporary synthetic files. The strict JSON regression runs on every supported OS. The immutable v0.2.0 release retains the earlier implementation for comparison.
