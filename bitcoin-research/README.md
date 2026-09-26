# Bitcoin contributions and research

Andrew Barnes · [GitHub](https://github.com/Bortlesboat)

I contribute to Bitcoin and Lightning libraries and investigate correctness, recovery and resource costs in private-payment systems. This page collects specific changes and reproducible work. Contribution states below were checked on September 24, 2026; the upstream links carry subsequent review history.

## Selected merged contributions

| Project | Change | Practical effect | Evidence |
| --- | --- | --- | --- |
| Lightning Development Kit / rust-lightning | Expose current dust exposure in `ChannelDetails` | Makes channel dust exposure available to callers for comparison with their configured limit. | [PR #4470](https://github.com/lightningdevkit/rust-lightning/pull/4470), merged May 1, 2026 |
| rust-bitcoin | Implement `From<Infallible>` for public error types | Improves composition with generic Rust code whose error conversion cannot fail. | [PR #5781](https://github.com/rust-bitcoin/rust-bitcoin/pull/5781), merged March 26, 2026 |
| ord | Warn when exporting addresses without the address index | Makes the index requirement visible during address export. | [PR #4558](https://github.com/ordinals/ord/pull/4558), merged August 9, 2026 |

These are contributions to the named upstream projects. The protocol designs and libraries remain the work of their respective authors and maintainers.

## Current contributions

### Ragu: reject malformed proofs cleanly

Malformed proof structure could reach verifier assumptions intended for well-formed inputs. The submitted change checks structural conditions before verification and adds 45 malformed-input cases with a valid control. Local checks included 100 passing PCD tests, with 21 expensive tests ignored by that suite, workspace lint and formatting, and an alloc-only build check.

[PR #886](https://github.com/tachyon-zcash/ragu/pull/886) is **submitted and open** at the checked date. It has not been accepted or merged. This is a verifier robustness contribution, not a cryptographic audit or performance result. Ragu is part of the proposed Zcash Tachyon work and is relevant proof-system research; it is not a Bitcoin L1 implementation.

### Bitcoin fee benchmarks: explain what the scores measure

The submitted change distinguishes error against the current mempool median from a future fee-threshold proxy. It adds 13 synthetic characterization tests and clarifies the README, CLI and generated reports while preserving calculations and result fields.

[PR #2](https://github.com/ClaraShk/bitcoin-fee-benchmarks/pull/2) is **submitted and open** at the checked date. The synthetic tests establish metric behavior; they do not establish a predictor's historical performance.

## Research experiments

### Ordinary checkout after A²L preparation

Can a wallet pay new merchants after a preparation service becomes unavailable? The [checkout experiment](experiments/prepared-checkout/README.md) runs COMIT's archived A²L completed-payment path, then makes two ordinary Bitcoin payments from the resulting output and its change. It includes a selected-input refusal and a deliberate automatic-funding control that joins prepared and ordinary coins.

The package records mined transactions, source hashes and costs on isolated regtest. It studies spending behavior and public transaction links; it does not establish anonymity or recovery safety. A²L and the COMIT implementation are credited upstream work.

The [coin-policy regression kit](experiments/prepared-checkout/POLICY_TESTS.md) adds a Python-only audit of the published bytes and a separate Core fixture for wallet labels across restart, fee shortfalls, missing labels and deliberate pool merges. It makes the payment-friction tradeoff reproducible without rebuilding A²L.

[Try wallet policy kit 0.1.1](https://bortlesboat.github.io/Bortlesboat/): download the source bundle, run the offline checks, and report a reproduction, setup failure or wallet integration use case.

### Publication fees and anchor expiry

Can a fee increase buy a Bitcoin confirmation after a payload's modeled anchor has expired? The [publication-policy benchmark](experiments/shielded-publication/README.md) compares 24 controlled cases on Bitcoin Core 31.1 regtest, with signed transactions, raw traces and reproducible reports.

In one delayed-publication workload, a fee-only retry and an anchor-refresh retry both paid 14,720 regtest satoshis and confirmed at height 293. Their modeled anchor ages were 101 and 21 blocks, respectively; only the latter passed the paper's 100-block height window. This result assumes rebuilding takes zero blocks. The payloads are synthetic, and the experiment does not verify Shielded proofs or implement its replay rules.

The [16-case delay follow-up](experiments/shielded-publication/REBUILD_DELAY.md) leaves the original carrier live during synthetic preparation. A three-block delay succeeded under longer congestion; a one-block delay lost when congestion cleared earlier. Once the original confirmed, Core rejected the later replacement because their shared Bitcoin funding input was already spent. This measures a carrier scheduling constraint, not cryptographic proving time or shielded wallet recovery.

This is an independent research artifact. It has not been reviewed or adopted by the Shielded Bitcoin team.

### Recovering an Arkade wallet across process boundaries

Question: can a wallet reopen a saved database, prepare an exit with Ark services unavailable, and complete that exit through independent Bitcoin access? How does a backup missing the virtual transaction data behave?

The [experiment and reproduction instructions](experiments/arkade-cold-restart/README.md) identify the exact SDK revision, retained state, positive control, missing-data case and result. It exercises an existing SDK capability. Arkade's recovery implementation and protocol are upstream work.

## Direction

Shielded Bitcoin is the main paper-study interest, with Ragu as a proof-engineering track and narrowly selected Bitcoin payment implementations supplying practical experiments. The common question is which data, services, trust assumptions and costs are required to recover and spend.

The [Shielded Bitcoin transfer paper](https://www.allocinit.xyz/uploads/shielded-bitcoin.pdf) describes recovery through accepted history and replay; its transfer guarantees must be distinguished from BTC entry and redemption. [Tachyon's roadmap](https://tachyon.z.cash/roadmap/) identifies backup and recovery tradeoffs in payment delivery. These are research inputs, not claims that this portfolio implements either system.

## Using this work

For each experiment, keep the source revision and assumptions with its result. A successful local test supports the scenario actually exercised. It does not establish general protocol safety, production readiness or equivalent privacy across systems. The experiment code carries its own license and can be reproduced independently.
