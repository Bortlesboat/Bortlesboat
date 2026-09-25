# Shielded publication policy benchmark

Andrew Barnes · [Bitcoin research portfolio](../../README.md) · [MIT license](LICENSE) · [Citation](CITATION.cff)

Compare shared-anchor spacing and retry policies using actual Bitcoin Core regtest carriers and a height-only model of the Shielded Bitcoin paper.

The benchmark does not implement or verify Shielded Bitcoin. Its 610-byte payload begins with `LABSB1`, contains public synthetic markers, and cannot serve as a valid Shielded envelope. Bitcoin validates the signed carrier transaction; the benchmark separately evaluates the paper's anchor-height inequality. No authentic transfer verifier is integrated here.

The [recorded 24-case run](results/run-2026-09-24/REPORT.md) compares both anchor spacings across four controlled workloads. In its delayed spacing-16 case, fee-only and refresh retries both cost 14,720 regtest satoshis and confirmed at height 293; only the refreshed anchor passed the modeled height window. The report includes the other outcomes, relay controls, raw evidence and limits.

A separate [16-case rebuild-delay experiment](REBUILD_DELAY.md) now tests what happens while the old carrier remains live. A three-block synthetic rebuild succeeded in one workload, while a one-block rebuild lost in another. The original code and 24-case evidence below remain unchanged.

This is independent experimental work, with no Shielded Bitcoin team review or adoption claimed. The Shielded protocol and proof-system designs belong to their authors. The contribution here is the controlled Bitcoin carrier experiment, its explicit height model and inspectable evidence.

## Run

Requires Python 3.12+ (standard library only) and the official Bitcoin Core 31.1 binary. No running node, public peers, real coins or existing wallet is used. The runner creates marked private data directories, binds to loopback, explicitly selects regtest and its own configuration, checks the RPC chain/version, and stops only its own child processes. Windows child windows are hidden.

Obtain Core from the [official release directory](https://bitcoincore.org/bin/bitcoin-core-31.1/) and verify its checksum/signatures following the [official instructions](https://bitcoincore.org/en/download/). The Windows ZIP used for the recorded experiment has SHA-256 `c99ef173471c58e6766d9eebd12e6c35349082eeed3939bc99eed58ef57db587`.

PowerShell example, with Core extracted alongside the cloned portfolio directory:

```powershell
git clone https://github.com/Bortlesboat/Bortlesboat.git
cd Bortlesboat/bitcoin-research/experiments/shielded-publication
py -3.12 -m unittest -v
py -3.12 bench.py --bitcoind ../../../../bitcoin-31.1/bin/bitcoind.exe --work-dir (Join-Path $env:TEMP 'shielded-regtest-001') --output results/run-001
py -3.12 report.py results/run-001
```

Adjust the binary path if Core is elsewhere. Use new work/output directories on each run. Existing directories are refused. The example keeps private runtime data in the system temporary directory, outside this repository. Private runtime data and portable result data must be separate. Runtime data is retained for inspection and never automatically deleted. Do not publish it: it contains the generated test wallet and RPC cookies. Results contain synthetic regtest transactions and no wallet private keys.

Add `--smoke` for three policies on the delayed spacing-16 case plus the height-boundary control. The full report requires the full 24-cell experiment and both relay controls. On another platform use its Python and Core executable names; the Python runner is portable, but the recorded run uses Windows.

The unit tests run without Bitcoin Core. The node experiment is the separate integration check.

## Experiment

The initial construction view is height 200. A candidate inclusion height of 201 selects either the newest eligible anchor (spacing 1) or the newest multiple of 16, both with wallet depth 6. The paper model uses W=100 and Kmin=1. Offline periods of 0, 85 or 87 blocks consume margin before publication.

Three policies share the same initial 1-sat/vB fee:

- `hold`: retain the initial carrier until it confirms.
- `fee_only`: at publication step 5, replace it at 20 sat/vB without changing its payload.
- `refresh_on_bump`: use the same fee schedule; if fewer than two blocks of height margin remain at that action, replace the synthetic payload with a newer anchor first.

For each of four fixed workloads, all six policy/spacing combinations begin from the same closed snapshot. Two independent 10-sat/vB background carriers arrive before each congested block. Core assembles and mines blocks under a 10,000-WU template limit with 2,000 WU reserved; the runner does not choose confirmation labels. Background transaction prefixes must match across paired runs. Each mined transaction list must match the immediately observed Core template.

`fresh_congested`, `near_deadline` and `deadline_crossed` inject background traffic for eight blocks; `early_clear` injects it for three. A case ends when the carrier confirms. Workloads are deliberately selected controls, not estimates of user behavior. The fee action receives current height and elapsed step, never the future congestion duration.

Additional controls publish two carriers at modeled ages 100/101 and test peer receipt under relaxed versus 83-byte data-carrier limits, including a higher-fee replacement and small positive-control transactions.

Relay waits advance both nodes' mock clocks to exercise inventory timers. These controls measure bounded receipt and admission policy, not relay latency. On the relaxed receiver, a direct admission check after receipt reports that the transaction is already in its mempool; on the restrictive receiver, it reports `datacarrier` rejection.

## Evidence

Each run saves:

- `manifest.json`: binary/source hashes, parameters, evidence limits and completion state.
- `source/`: the exact driver source used for the run.
- `baseline.json` and `anchor-grid.json`: public regtest funding context and phase enumeration.
- Per case: signed carrier/background transactions, decisions, mined blocks and raw RPC exchanges.
- `summary.json`, then generated `summary.csv`, `REPORT.md` and report provenance.

`model_height_eligible` means only the height inequality passed. `authentic_shielded_acceptance` is always null. Fee totals count the included transaction only; replaced carriers pay no miner fee. Marker-link counts describe synthetic public equality, not anonymity or identities.

Proof generation and witness acquisition take zero modeled blocks, and no root reconstruction or reorg behavior is implemented. Mainnet relay, mining behavior, optimal anchor spacing and safe production reserves are unmeasured. A new test wallet changes transaction/block IDs across fresh baselines; semantic outcome comparisons are the reproducibility target.

The recorded experiment ran on September 24, 2026; this public artifact was packaged on September 25. The exported driver, tests and result files are unchanged from the locally reviewed version. All 28 unit tests were rerun from the exported directory. The full experiment was previously rerun after review fixes; publication packaging did not repeat that node run.

To inspect the saved evidence without starting a node, run `py -3.12 report.py results/run-2026-09-24`. This validates the complete case grid, source hashes and control results before regenerating the report. The archived driver files retain their original bytes through the local `.gitattributes` rule.

## What remains to test

The [rebuild-delay follow-up](REBUILD_DELAY.md) records actual old-versus-refreshed Bitcoin carrier outcomes under declared block delays. A real verifier and witness builder are still needed to measure achievable readiness and connect these schedules to authentic Shielded replay and wallet recovery.

## Sources

- [Shielded Bitcoin](https://www.allocinit.xyz/uploads/shielded-bitcoin.pdf), sections 8 and Appendix A.4/A.6; archived SHA-256 `97d92987331f1365b88a4ec909701d7b1a74fa3ea7e07101bfc3e7243409ec18`.
- [Bitcoin Core 30 data-carrier policy](https://bitcoincore.org/en/releases/30.0/); settings are explicitly pinned in this experiment.
- [ZIP 318 draft](https://github.com/zcash/zips/blob/60db9f1e6a1e9988da442b7d8436da6b16dd5c26/zips/zip-0318.md), adjacent prior art for shared anchors. Its provisional 144-block spacing is only a hypothetical compatibility comparison in the arithmetic grid, not a policy adopted by Shielded Bitcoin.
