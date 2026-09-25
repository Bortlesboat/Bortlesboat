# When the old carrier wins during a rebuild

Andrew Barnes · [Original benchmark](README.md) · [Recorded results](results/rebuild-delay-2026-09-25/REPORT.md) · [MIT license](LICENSE) · [Citation](CITATION.cff)

The original benchmark made a refresh instantaneous. This follow-up tests the missing interval: the old Bitcoin transaction remains live while its replacement is unavailable. Sixteen Core 31.1 regtest cases compare hold, immediate fee-only replacement, and synthetic refresh delays of 0, 1, 2, 3, 4 and 8 blocks.

In the longer-congestion workload, refresh delays of 0–3 blocks produced a refreshed winner with an eligible modeled anchor. At delays of 4 or 8 blocks, the original confirmed at H296 while preparation was pending. When congestion ended at the rebuild step, only the zero-delay refresh won; even one block of preparation let the original confirm at H293. In every losing refresh case, Core rejected the later candidate with `missing-inputs`: the original had already consumed their shared Bitcoin funding input.

| Workload | Tested delays with an eligible refreshed winner | Tested delays where the original confirmed during preparation |
| --- | --- | --- |
| Congestion through five blocks | 0 | 1, 2, 3, 4, 8 |
| Congestion through eight blocks | 0, 1, 2, 3 | 4, 8 |

This gives a concrete requirement for a future wallet experiment: account for the original's possible confirmation throughout proof/witness rebuilding. A newer anchor and a higher eventual fee cannot retroactively replace a confirmed Bitcoin transaction. The result does not imply that rejected shielded notes are spent or lost, or rule out a separately funded retry. Those are separate replay and wallet questions.

## What was measured

Each case starts from the same closed H287 snapshot, with the original anchor selected from the H200 construction view. W=100, minimum depth 1, wallet depth 6 and spacing 16 select initial anchor 192. The original is broadcast before H288 at 1 sat/vB. Two background carriers per congested block pay 10 sat/vB. At H293, refresh selects anchor 272 and its eventual replacement pays 20 sat/vB. The fee-only control pays the same higher rate while preserving the old payload.

Candidate bytes are constructed and signed at rebuild start, then withheld for the declared number of blocks. This is a readiness model; no proving latency is measured. A candidate ready before height H is processed before Core assembles and mines H. Consequently, readiness before H296 can beat the old H296 confirmation in the longer workload, while readiness before H297 cannot. The one-block offset is part of the experiment, not a claim about simultaneous network events.

Core chooses the block contents. The runner checks every mined transaction list against the immediately observed template. The report reconciles confirmations, fees, candidate admissions, broadcast order and matched workload prefixes against the saved RPC records. Expired original winners paid 736 satoshis; eligible refreshed winners paid 14,720. Rejected, never-broadcast replacements paid no miner fee. These are controlled regtest outcomes, not mainnet fee or timing estimates.

## Reproduce

Use the original README's Python 3.12 and verified Core 31.1 setup. From this experiment directory in PowerShell:

```powershell
py -3.12 -m unittest -v
py -3.12 rebuild_delay.py --bitcoind ../../../../bitcoin-31.1/bin/bitcoind.exe --work-dir (Join-Path $env:TEMP 'shielded-rebuild-delay-001') --output results/delay-001
py -3.12 delay_report.py results/delay-001
```

Use fresh work/output paths. Private node data contains test-wallet keys and RPC cookies and must stay outside the public repository. Each run uses isolated, loopback-only nodes and stops its own child processes. It does not connect to public peers or use existing wallets.

The saved [16-case evidence](results/rebuild-delay-2026-09-25) can be checked without a node:

```powershell
py -3.12 delay_report.py results/rebuild-delay-2026-09-25
```

`case.json` retains signed candidates, actual admission responses, background traffic, blocks, events and summary observations. `rpc.jsonl` retains the corresponding exchanges. The manifest pins the binary and archives the exact source. Wallet generation changes transaction/block IDs between runs; compare semantic outcomes across fresh baselines, not those random identifiers. The original September 24 results remain unchanged.

## Scope

The `LABSB1` payload is explicitly synthetic. Real Bitcoin signatures, mempool replacement and block inclusion are exercised; Shielded eligibility remains only a height inequality, and authentic acceptance is always null. No cryptographic proof, shielded replay state, note consumption, recovery behavior, anonymity result or production safety claim is established. This is independent experimental work, with no paper-author review or adoption claimed.

Both candidates use the same Bitcoin funding input. An experiment with independently funded carriers racing to spend the same shielded notes tests a different boundary. Real proving and witness-acquisition measurements can inform these block budgets, but accelerated regtest blocks alone cannot map seconds to a mainnet success probability.

The next technical integration is to feed measured proof/witness readiness and chain advances into a publication policy, checking the actual original transaction status before choosing a retry. A fixed successful delay in either of these two workloads is not a generally safe reserve.
