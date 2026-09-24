# Arkade recovery across process boundaries

**Observed September 24, 2026:** a wallet reopened from persistent SQLite state, prepared an exit while its Ark services were stopped, and completed two sweeps through independent Bitcoin access. A subsequent transaction spent a recovered output and confirmed. Removing only the saved virtual transaction data left the same cached outputs visible but prevented exit construction.

This is an independent experiment of existing Arkade functionality. The SDK, protocol and preceding recovery tests are the work of the Arkade contributors. This result does not identify a new SDK defect.

## Result

The [machine-readable result](results.json) records all five phases. Each phase runs in a separate Node process.

| Phase | Observed result |
| --- | --- |
| Online control | Two VTXOs representing 120,000 regtest satoshis; complete exit data retained; the exit quote had no funding shortfall. |
| Missing exit data | The same outpoints remained visible after reopening SQLite. The exit-chain lookup failed with a refused connection to the stopped Ark indexer. |
| Full saved state | Offline wallet creation used the cached server information. Exit preparation succeeded using the retained SQLite data and confirmed fee funds. |
| Package execution | A fresh directory containing only the exported package supported a separate executor process. Both sweeps confirmed; the destination received 119,408 regtest satoshis. |
| Spend after recovery | A transaction spending a recovered output confirmed on the regtest Bitcoin chain. |

The quote used 2 sat/vB and separately prefunded fee coins. Its fee fields are quote outputs, not an independent measurement of aggregate fees. The result is not a throughput benchmark.

## What this adds to the existing tests

The pinned upstream [exit-data capture test](https://github.com/arkade-os/ts-sdk/blob/8b45b9ee991fb4a0e8611e5b0c39fc733d84c5e1/packages/ts-sdk/test/e2e/exitDataCapture.test.ts) verifies local chain resolution using an in-memory repository and a failing indexer stub. The [operator-offline test](https://github.com/arkade-os/ts-sdk/blob/8b45b9ee991fb4a0e8611e5b0c39fc733d84c5e1/packages/ts-sdk/test/e2e/operatorOffline.test.ts) verifies cached reads. The [unilateral-exit tests](https://github.com/arkade-os/ts-sdk/blob/8b45b9ee991fb4a0e8611e5b0c39fc733d84c5e1/packages/ts-sdk/test/e2e/unilateralExit.test.ts) cover completed exits.

This experiment joins persistence, process termination, stopped services, exit preparation, package execution and a subsequent spend in one scenario, with a missing-data comparison. It does not establish that no equivalent test exists elsewhere.

## Reproduce

Use Bash on Linux or WSL, Docker with Compose, Node 24.15 or a compatible version declared by the pinned SDK, and Corepack. The observed run used Linux x86_64 under WSL, Node 24.15.0, pnpm 10.25.0, Docker 29.8.1 and Compose 5.5.1. Other platforms were not tested.

Clone this portfolio and the SDK into separate directories. The commands below start from the directory containing both clones:

```bash
git clone https://github.com/Bortlesboat/Bortlesboat.git portfolio
git clone https://github.com/arkade-os/ts-sdk.git ts-sdk
cd ts-sdk
git checkout 8b45b9ee991fb4a0e8611e5b0c39fc733d84c5e1
git submodule update --init
corepack pnpm install --frozen-lockfile

set -a
source packages/ts-sdk/.env.regtest
source ../portfolio/bitcoin-research/experiments/arkade-cold-restart/experiment.env
set +a

node regtest/regtest.mjs start --env packages/ts-sdk/.env.regtest
bash ../portfolio/bitcoin-research/experiments/arkade-cold-restart/run.sh "$PWD"
node regtest/regtest.mjs stop --env packages/ts-sdk/.env.regtest
```

The [environment file](experiment.env) selects a dedicated Compose project, container prefix and ports. Use those only when they are free. Keep the `RECOVERY_*` URLs aligned with any port changes. The runner checks the SDK and regtest revisions, rebuilds the SDK, and checks container ownership before stopping its Ark services. It leaves those services stopped and retains its temporary directory; the final command stops the rest of the dedicated stack while preserving its data. It does not clean unrelated containers or volumes.

The runner prints a path to `results.json`. Its temporary directory also contains disposable **regtest** keys and wallet databases; publish only the result file. The package-only executor directory contains neither the original keys nor the wallet database. The script checks regtest genesis and compares a block above genesis between Bitcoin RPC and the explorer before creating keys or transacting.

## Retained state and limits

- The full backup contains the wallet key, cached server information, wallet and contract SQLite state, and full virtual transaction/PSBT data. An online exit quote is run before taking the copy, so this does not test a backup made immediately on first receipt.
- The wallet is disposed and SQLite is closed before its process exits and the database is copied. This tests a restart from a consistent saved state, not power loss or a crash during a database transaction.
- The negative case clears the virtual transaction repository in a copy of that same database. It retains the key and other cached state. This is not a seed-only recovery test.
- Arkd and its wallet service are stopped. Bitcoin Core, the explorer and its indexers remain available. Fee funds are already confirmed. Block-based timelocks are advanced by controlled local mining.
- The workload has two outputs owned by one wallet and uses the default funded exit package. Other contract types, time-based timelocks, reorgs, expiry races, corrupted backups, fee spikes and adversarial servers are outside this result.
- A functional recovery result does not measure privacy or prove the security of Arkade, Shielded Bitcoin or another protocol. Their assumptions differ.

## Source and license

- SDK: [`8b45b9ee991fb4a0e8611e5b0c39fc733d84c5e1`](https://github.com/arkade-os/ts-sdk/tree/8b45b9ee991fb4a0e8611e5b0c39fc733d84c5e1)
- Regtest submodule: [`e3b542f3c219b18be861e06761a0e4c5d565bb1a`](https://github.com/ArkLabsHQ/arkade-regtest/tree/e3b542f3c219b18be861e06761a0e4c5d565bb1a)
- Experiment: [cold-restart.mjs](cold-restart.mjs), [run.sh](run.sh), [MIT license](LICENSE).

The SDK source is unchanged by the experiment. Upstream licenses continue to apply to upstream code.
