# Controlled publication-policy results

These are real Bitcoin Core 31.1 regtest carrier observations combined with a height-only model of the Shielded paper. Payloads are visibly synthetic. **No Shielded proof, note, root or complete transfer was verified.**

## Decision supported by this workload

With a 16-block shared boundary, six-block wallet depth and 87 blocks offline, the fee-only policy paid 14,720 satoshis and was mined at height 293. Its original anchor was then 101 blocks old; height eligibility was False. The refresh policy used the **same fee schedule**, paid 14,720 satoshis and was mined at height 293; its anchor age was 21 and height eligibility was True.

Waiting cost 736 satoshis and reached height 296, at anchor age 104. Under the same workload, choosing the newest six-block-deep anchor (spacing 1) left the fee-only policy at age 98, with height eligibility True.

**Practical implication:** check the remaining anchor budget when raising the fee. In this workload, fee escalation alone buys a Bitcoin confirmation whose payload is already height-ineligible. Refreshing the modeled anchor avoids that condition at the same fee and inclusion height, assuming rebuilding completes in time. The experiment does not establish an optimal spacing, a safe mainnet reserve or a production default.

## All observed cells

The four workloads are deliberately chosen controls, not samples of user behavior. Do not interpret their fraction of ineligible cells as a failure rate.

| Workload | Spacing | Retry policy | Included H | Anchor age | Fee (sat) | Height eligible | Attempts / payloads |
|---|---:|---|---:|---:|---:|---|---|
| fresh_congested | 1 | hold | 209 | 14 | 736 | yes | 1 / 1 |
| fresh_congested | 1 | fee_only | 206 | 11 | 14720 | yes | 2 / 1 |
| fresh_congested | 1 | refresh_on_bump | 206 | 11 | 14720 | yes | 2 / 1 |
| fresh_congested | 16 | hold | 209 | 17 | 736 | yes | 1 / 1 |
| fresh_congested | 16 | fee_only | 206 | 14 | 14720 | yes | 2 / 1 |
| fresh_congested | 16 | refresh_on_bump | 206 | 14 | 14720 | yes | 2 / 1 |
| near_deadline | 1 | hold | 294 | 99 | 736 | yes | 1 / 1 |
| near_deadline | 1 | fee_only | 291 | 96 | 14720 | yes | 2 / 1 |
| near_deadline | 1 | refresh_on_bump | 291 | 96 | 14720 | yes | 2 / 1 |
| near_deadline | 16 | hold | 294 | 102 | 736 | no | 1 / 1 |
| near_deadline | 16 | fee_only | 291 | 99 | 14720 | yes | 2 / 1 |
| near_deadline | 16 | refresh_on_bump | 291 | 19 | 14720 | yes | 2 / 2 |
| deadline_crossed | 1 | hold | 296 | 101 | 736 | no | 1 / 1 |
| deadline_crossed | 1 | fee_only | 293 | 98 | 14720 | yes | 2 / 1 |
| deadline_crossed | 1 | refresh_on_bump | 293 | 98 | 14720 | yes | 2 / 1 |
| deadline_crossed | 16 | hold | 296 | 104 | 736 | no | 1 / 1 |
| deadline_crossed | 16 | fee_only | 293 | 101 | 14720 | no | 2 / 1 |
| deadline_crossed | 16 | refresh_on_bump | 293 | 21 | 14720 | yes | 2 / 2 |
| early_clear | 1 | hold | 291 | 96 | 736 | yes | 1 / 1 |
| early_clear | 1 | fee_only | 291 | 96 | 736 | yes | 1 / 1 |
| early_clear | 1 | refresh_on_bump | 291 | 96 | 736 | yes | 1 / 1 |
| early_clear | 16 | hold | 291 | 99 | 736 | yes | 1 / 1 |
| early_clear | 16 | fee_only | 291 | 99 | 736 | yes | 1 / 1 |
| early_clear | 16 | refresh_on_bump | 291 | 99 | 736 | yes | 1 / 1 |

## Controls and provenance

Each policy starts from the same closed regtest snapshot. Background transaction prefixes are checked byte-for-byte across policies and anchor spacings in each workload. Each mined block is checked against the immediately observed Core template. Outcomes come from Core block contents, not assigned confirmation labels.

The carrier is a 610-byte LABSB1 payload in a 614-byte OP_RETURN script. With one P2TR funding input and one P2TR change output, the measured whole transaction is 736 vB. Fees use this whole-transaction size.

Two no-background carriers were both mined at explicitly controlled anchor ages 100 and 101. Only the first passes the paper height predicate; these are boundary controls, not performance measurements.

| Receiver data-carrier limit | Small carrier received | 610-byte payload received | Higher-fee replacement received |
|---|---|---|---|
| 100000 | True | True | True |
| 83 | True | False | False |

Direct receiver admission tests accompany the bounded peer observations. A restrictive carrier policy is a structural rejection that the fee increase does not remove. The two-node local topology does not measure public-network reachability.

Relay waits advance the nodes' mock clocks to exercise inventory timers; elapsed relay latency is not measured. After receipt, the relaxed receiver's direct admission check reports already-in-mempool; the restrictive receiver reports datacarrier rejection.

## Limits

- Rebuilding only replaces labeled synthetic bytes. Real proving time, witness acquisition, reorganizations and full Shielded validity are absent.
- Six blocks is the wallet selection depth; replay still uses Kmin=1. Spacing 1 and 16, the two-block reserve, fee levels and workload durations are experimental choices.
- Blocks use a deliberately small 10,000-WU template limit with 2,000 WU reserved, two 10-sat/vB background carriers per congested block, and no public peers. Their timestamps and offline blocks are controlled inputs, not elapsed mainnet time.
- Policies observe only current height, anchor and elapsed step. Both fee policies raise 1 to 20 sat/vB at step 5; the refresh variant checks the same current-height margin. A workload stops being recorded when its carrier confirms; all earlier background prefixes match.
- Replaced attempts do not pay a miner fee. Only the included attempt contributes to fee totals. Fees on height-ineligible carriers are not measured fees on real failed Shielded transfers.
- Public test markers stay equal across rebuilt payloads. The exported link count describes these synthetic bytes; it is not an anonymity score or evidence about human identities.
- A fresh baseline uses a new test wallet, so block/transaction IDs can change on rerun. The declared workloads, fee amounts, heights, margins and control outcomes are reproducible.

## Reproduce and inspect

See the repository README. `summary.csv` supports analysis; each case retains transactions, decision inputs, selected blocks and raw RPC exchanges. The manifest hashes the binary and an archived copy of the exact runner source. Private wallets, cookies and node databases are outside this result directory. All owned nodes were stopped.

Sources: [Shielded Bitcoin, sections 8 and Appendix A.4/A.6](https://www.allocinit.xyz/uploads/shielded-bitcoin.pdf), [Core 30 data-carrier policy](https://bitcoincore.org/en/releases/30.0/), [ZIP 318 prior art for shared anchors](https://github.com/zcash/zips/blob/60db9f1e6a1e9988da442b7d8436da6b16dd5c26/zips/zip-0318.md).
