# Ordinary checkout after A²L preparation

A reproducible research experiment by Andrew Barnes, using the COMIT team's archived A²L proof of concept. It asks whether an ordinary wallet can pay new merchants after preparation finishes and the helper is unavailable, and what later coin selection exposes.

This is test software. It measures Bitcoin spending, transaction sizes and observable links. It does not establish anonymity, validate refund/abort security, or implement Shielded Bitcoin. The original cryptography and protocol are upstream work.

## Run

Use Linux or WSL with Python 3.10+, Git, Cargo/Rust, a C toolchain, Clang/libclang, GMP development headers, make, m4 and Bison. On Ubuntu the native prerequisites are provided by `build-essential clang libclang-dev libgmp-dev m4 bison`. Install Rust and a Bitcoin Core release separately. The runner does not install system packages or download a Bitcoin executable.

From this directory, with prerequisites installed:

```sh
python3 run.py --bitcoind /path/to/bitcoind
```

Optionally pass `--work-dir /path/to/new-directory`. The directory must not exist. Each run clones the pinned upstream, builds into a fresh target, starts its own Bitcoin regtest process with a fresh data directory and disabled peer networking, and stops that process afterward. No existing Bitcoin configuration or wallets are read. Source download/build requires network access; Bitcoin peer networking remains off.

Expect a native compilation lasting several minutes. `results/build.log` and `results/preparation.log` contain diagnostic output. `results/results.json` records the checks, mined transactions, sizes, fees and shutdown result; `results/provenance.json` records tool versions and hashes. A failed run retains its workspace for diagnosis. Logs and temporary regtest wallet data stay local; inspect them before sharing.

The script fails if a prerequisite is absent, the pinned source shape differs, the given workspace already exists, or a required outcome is not observed. It never modifies a pre-existing build tree to resume a failed run.

## What it tests

1. Execute COMIT's cryptographic happy path: two funding and two redemption transactions. Preserve the upstream wallet-balance assertions.
2. Let the protocol process exit and unload the helper/source wallets. Verify those wallet RPC endpoints are inaccessible.
3. Pay two newly created ordinary merchants from the resulting wallet output and its change. Both payments must be mined with only the receiver wallet signing.
4. Put an ordinary deposit in the same wallet. When a payment fits the overall balance but exceeds the selected prepared balance, disallow extra inputs and require funding to fail without broadcasting or consuming coins.
5. Deliberately permit automatic funding. Require a mined transaction joining the prepared and ordinary outpoints. This is an expected unwanted outcome, not a privacy success.

The second payment consumes the first payment's change. Amounts and spending edges are public. Which party owns an output remains a separate inference for an outside observer. A wallet-local label cannot erase a published link.

## Scope and source

- [COMIT A²L PoC](https://github.com/comit-network/a2l-poc), revision `a261027f4bdb2384f715efa3f634d5796fe95019`, supplies the cryptographic flow and original Bitcoin transaction construction. That constructor is unmodified in this package. Only the completed-payment path is run; do not infer recovery safety from this suite.
- The runner changes one dependency transport from HTTP to HTTPS while keeping its locked revision. It generates a test adapter for a local node, a named funding wallet and transaction-admission traces; every patch is saved with the results.
- [A²L paper](https://eprint.iacr.org/2019/589) by Erkan Tairi, Pedro Moreno-Sanchez and Matteo Maffei is the protocol source. COMIT's implementation uses an on-chain multisignature variant; this suite does not measure the paper's reusable channel system.
- [Maxwell's 2013 CoinSwap proposal](https://bitcointalk.org/index.php?topic=321228.0) already discusses background wallet use and the sender taking the receiving role. This experiment is a reproduction/application study, not a claim to have invented that idea.

The prototype's single-process cryptographic setup remains unchanged. Unloading wallets establishes absence of helper participation during checkout, not secure key erasure. No real funds, adversarial network, population anonymity measurement, congestion benchmark or user study is involved.

## Results and outside reproduction

For a faster follow-up that needs no Rust build, see the [coin-policy regression kit](POLICY_TESTS.md). It audits these recorded transaction bytes and separately tests synthetic wallet labels across a Core restart, fee shortfalls and an intentional merge. It does not rerun A²L or establish anonymity.

The September 25, 2026 clean-extraction run passed all six transaction checks on **Bitcoin Core 31.1**, Ubuntu 24.04 under WSL, Python 3.12.3 and Cargo 1.97.0. It fetched upstream anew and used fresh build outputs. The author's Cargo download cache and existing native tools were reused; this was not an independent reproduction or a fresh operating-system install. Conflicting Cargo output settings were overridden, leaving the pre-existing control directories untouched. The owned Bitcoin node stopped successfully.

| Observed operation | Result |
| --- | --- |
| Four preparation transactions | 580 vB total; 10,080 sat in network fees with the fixture's configured fees |
| First ordinary checkout | 123,456 sat paid; 141 vB; 1,000 sat network fee |
| Second checkout, spending change | 1,234,567 sat paid; 141 vB; 1,000 sat network fee |
| Payment exceeding selected prepared balance | Refused; coins and mempool unchanged |
| Automatic-funding negative control | Confirmed transaction joining prepared and ordinary inputs |

These fees are fixture settings, not current market quotes. The cost scenarios in the results isolate transaction space: the observed 580 vB preparation adds 290 vB per payment across the two executed checkouts. The ten-payment scenario is extrapolated, and repeated spending does not provide independent privacy histories.

Evidence: [transaction results](reference-results.json), [versions and source hashes](reference-provenance.json), [Core adapter patch](reference-core-adapter.patch), [manifest transport patch](reference-Cargo.toml.patch) and [lockfile transport patch](reference-Cargo.lock.patch). The source hashes match the Python files and Rust template published here. Raw diagnostic logs and temporary wallets are excluded.

Four targeted harness tests also passed, covering workspace preservation and cost reporting with unequal signature sizes:

```sh
python3 -m unittest -v test_runner
```

Fresh keys and signatures mean transaction IDs need not match between runs. Compare check outcomes, input/output relationships and conservation of value; virtual size can vary slightly with signatures. No outside reproduction has been recorded as of September 25, 2026.

For a reproduction report, include the portfolio commit, upstream revision, platform/Core/Cargo versions, command, outcomes and deviations. An author's second run is not an independent reproduction. A successful run establishes only the scenarios above.

## License

This experiment directory is distributed under GPL-3.0-only; see [LICENSE](LICENSE). The generated Rust test derives from COMIT's GPL-3.0 source. Its authorship is retained through the upstream link and pinned source. Other experiments in the containing portfolio have their own licenses.
