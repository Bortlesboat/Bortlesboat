# Wallet policy kit 0.2.1

Test whether a wallet keeps two coin pools separate through payments, change and a saved-wallet restart. Start with the recorded transactions; no Bitcoin node, package installation or funds are needed for the offline checks.

Download **wallet-policy-kit-v0.2.1.zip** and **SHA256SUMS.txt** from the [versioned release](https://github.com/Bortlesboat/Bortlesboat/releases/tag/wallet-policy-v0.2.1). Extract the ZIP and open a terminal in the folder containing `START_HERE.md` and `test_policy.py`. Windows “Extract All” may create two nested folders named `wallet-policy-kit-v0.2.1`; use the inner one containing those files.

## Run

Python 3.10 or newer is required. On Linux/macOS:

```sh
python3 -m unittest -v test_policy test_runner test_integration test_security
```

On Windows PowerShell:

```powershell
py -3 -m unittest -v test_policy test_runner test_integration test_security
```

Expected: **34 tests, OK**, exit code 0 (one Linux-only memory-budget check is skipped on Windows/macOS). The suite checks the recorded transaction bytes and includes intentional mistakes that the auditor must reject. A passing suite means those examples behaved as expected; it does not establish privacy or wallet safety.

To check the download before extraction, compare its SHA-256 with `SHA256SUMS.txt`: `sha256sum wallet-policy-kit-v0.2.1.zip` on Linux, `shasum -a 256 wallet-policy-kit-v0.2.1.zip` on macOS, or `Get-FileHash wallet-policy-kit-v0.2.1.zip -Algorithm SHA256` in PowerShell.

## Try the next step

- **Run the shared corpus:** `python3 conformance.py` checks 27 policy cases. See the [integration guide](INTEGRATION.md) for the raw-transaction export bridge, CI commands and independent-checker contract. These are synthetic conformance cases, not an anonymity benchmark.

- **Inspect a deliberate pool merge:** `python3 audit.py --reference reference-results.json` (Windows: replace `python3` with `py -3`). Expected exit **1** and a `wrong_pool` violation in the last step. This is a successful detection, not a failed installation.
- **Run fresh transactions:** follow the [live regtest instructions](POLICY_TESTS.md#run-the-live-fixture). The recorded run used Core 31.1 on Linux/WSL. This creates isolated test wallets and synthetic coins; it does not use a real wallet.
- **Test your wallet's exporter:** use the [trace format](POLICY_TESTS.md#reuse-in-another-wallet) and `audit.py your-trace.json`. Exit **0** means the supplied history follows the declared rule, **1** means a policy violation, and **2** means invalid evidence. Labels and the completeness of the history are exporter assumptions.

The [original A²L experiment](README.md) has separate build requirements. The synthetic live fixture does not run A²L or OpenSwap. This release is developer research tooling, not a payment wallet or a production privacy protocol.

## Tell us whether it helps

Read the [adversarial test findings](SECURITY_REVIEW.md) for the v0.2.1 fixes and the limits of a clean result.

[Report your trial or use case](https://github.com/Bortlesboat/Bortlesboat/issues/new?template=wallet-policy-trial.yml). Useful feedback: the version and environment, what command ran, what happened, and which wallet behavior you need to check. Setup failures and reasons not to use it are welcome. Share only synthetic evidence in public; do not attach wallet files or private histories.

An outside reproduction and a concrete wallet integration are the next milestones. Neither is claimed by this release. The [project page](https://bortlesboat.github.io/Bortlesboat/) links to the source and feedback route.

## License and provenance

[GPL-3.0-only](LICENSE). The original experiment builds on [COMIT's A²L proof of concept](https://github.com/comit-network/a2l-poc); its pinned revision, patches and attribution remain in [README.md](README.md). The separate policy fixture's [provenance](policy-reference/provenance.json) records the September 25 measurements and exact measured source hashes. The release tag identifies the packaging and documentation revision. Those are different records; old measurements are not relabeled as new runs.
