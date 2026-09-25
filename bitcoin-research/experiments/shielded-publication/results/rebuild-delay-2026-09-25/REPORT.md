# Delayed rebuilds and the old-carrier race

Sixteen isolated Core 31.1 regtest cases. Bitcoin confirmation and fees are observed; Shielded eligibility is only the W=100 height model. No authentic proof is generated or verified.

| Workload / policy | Delay (blocks) | Ready before H | Winner | Included H | Anchor age | Fee (sat) | Height eligible |
| --- | ---: | ---: | --- | ---: | ---: | ---: | --- |
| clear_at_retry-hold | — | — | original | 293 | 101 | 736 | false |
| clear_at_retry-fee_only | — | 293 | replacement | 293 | 101 | 14720 | false |
| clear_at_retry-refresh-d0 | 0 | 293 | replacement | 293 | 21 | 14720 | true |
| clear_at_retry-refresh-d1 | 1 | 294 | original | 293 | 101 | 736 | false |
| clear_at_retry-refresh-d2 | 2 | 295 | original | 293 | 101 | 736 | false |
| clear_at_retry-refresh-d3 | 3 | 296 | original | 293 | 101 | 736 | false |
| clear_at_retry-refresh-d4 | 4 | 297 | original | 293 | 101 | 736 | false |
| clear_at_retry-refresh-d8 | 8 | 301 | original | 293 | 101 | 736 | false |
| longer_backlog-hold | — | — | original | 296 | 104 | 736 | false |
| longer_backlog-fee_only | — | 293 | replacement | 293 | 101 | 14720 | false |
| longer_backlog-refresh-d0 | 0 | 293 | replacement | 293 | 21 | 14720 | true |
| longer_backlog-refresh-d1 | 1 | 294 | replacement | 294 | 22 | 14720 | true |
| longer_backlog-refresh-d2 | 2 | 295 | replacement | 295 | 23 | 14720 | true |
| longer_backlog-refresh-d3 | 3 | 296 | replacement | 296 | 24 | 14720 | true |
| longer_backlog-refresh-d4 | 4 | 297 | original | 296 | 104 | 736 | false |
| longer_backlog-refresh-d8 | 8 | 301 | original | 296 | 104 | 736 | false |

## Observed delay budgets

- `clear_at_retry`: tested delays with an eligible refreshed winner: [0]; tested delays where the original confirmed during preparation: [1, 2, 3, 4, 8].
- `longer_backlog`: tested delays with an eligible refreshed winner: [0, 1, 2, 3]; tested delays where the original confirmed during preparation: [4, 8].

A rejected late replacement spends no additional miner fee. The old winner still pays its recorded Bitcoin fee even when its synthetic anchor fails the height model. This does not establish that any shielded note was lost or spent.

## Method and limits

The initial construction view is H200 (anchor 192); publication begins before H288. At H293 the fee-only control raises fees without changing the payload, while refresh freezes a new anchor at 272 and withholds its candidate for the declared delay. Initial, background and replacement rates are 1, 10 and 20 sat/vB. The two workloads inject two background transactions before each of five or eight blocks. All cases start from the same closed snapshot and shared background prefixes.

Readiness is processed before that height's template and mining. A candidate ready before H296 can replace the old carrier before the H296 block; readiness before H297 is too late if the original confirmed at H296. These are explicit sequential event-order cases, not a measurement of a simultaneous network race or propagation latency.

Candidates share a Bitcoin funding input. This tests Bitcoin replacement; it is different from two independently funded carriers competing over the same shielded notes. No cancellation, alternative fee funding, reorg, authentic verifier, witness builder or wallet recovery is implemented. No privacy, production safety or mainnet probability claim follows.

The candidate bytes are signed at rebuild start and withheld. Delay counts are controlled block budgets, not measured cryptographic computation. A useful next integration is to map observed proof/witness completion and chain advances into this schedule, retaining the old carrier and accounting for a ready candidate arriving after a block.

## Evidence

`case.json` stores both candidates (including rejected, never-broadcast replacements), Core admissions, backgrounds, mined blocks and event records; `rpc.jsonl` records the corresponding Core replies. The report validates all cells, actual winner/fee/admission observations, template agreement, scheduled broadcasts, shared workload prefixes, stopped-node labels and source hashes before writing outputs.
