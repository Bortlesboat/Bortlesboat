"""Render a complete benchmark's observed results without inventing success labels."""

import argparse
import csv
import json
from pathlib import Path

from bench import POLICIES, SCENARIOS
from core import file_sha256, save_json


def validate_controls(manifest: dict, summary: dict) -> None:
    """Require evidence for the report's fixed control claims; never relabel it."""
    try:
        if (manifest['authentic_shielded_verifier'] is not False
                or manifest['payload'] != '610-byte visibly synthetic LABSB1'):
            raise ValueError('the report requires explicitly synthetic evidence')
        if (manifest['all_owned_nodes_stopped'] is not True
                or any(row['node_stopped'] is not True for row in summary['results'])):
            raise ValueError('the report requires all experiment nodes to be stopped')

        boundary = summary['controls']['boundary']
        cases = boundary['cases']
        if len(cases) != 2 or {case['anchor_age'] for case in cases} != {100, 101}:
            raise ValueError('the report requires boundary controls at ages 100 and 101')
        if boundary['node_stopped'] is not True:
            raise ValueError('the boundary control node was not stopped')
        for case in cases:
            if (any(type(case[key]) is not int for key in
                    ('anchor_age', 'anchor_height', 'inclusion_height'))
                    or case['anchor_height'] < 0
                    or case['inclusion_height'] - case['anchor_height'] != case['anchor_age']
                    or case['model_height_eligible'] is not (case['anchor_age'] == 100)):
                raise ValueError('boundary heights or eligibility do not support the report')
            if case['authentic_shielded_acceptance'] is not None:
                raise ValueError('boundary controls cannot claim authentic Shielded acceptance')

        relays = summary['controls']['relay']
        if (len(relays) != 2
                or {relay['receiver_datacarriersize'] for relay in relays} != {100000, 83}):
            raise ValueError('the report requires receiver limits 100000 and 83')
        for relay in relays:
            expected_receipt = relay['receiver_datacarriersize'] == 100000
            if (relay['small_received'] is not True or relay['barrier_received'] is not True
                    or relay['large_received'] is not expected_receipt
                    or relay['high_fee_large_received'] is not expected_receipt):
                raise ValueError('relay receipts do not support the report control claims')
            if (relay['sender_admission']['allowed'] is not True
                    or relay['sender_high_fee_admission']['allowed'] is not True):
                raise ValueError('relay sender admission controls did not pass')
            reason = 'txn-already-in-mempool' if expected_receipt else 'datacarrier'
            for name in ('receiver_direct_check', 'receiver_high_fee_check'):
                check = relay[name]
                if check['allowed'] is not False or check['reject-reason'] != reason:
                    raise ValueError('receiver admission evidence does not support the report')
            if relay['nodes_stopped'] is not True:
                raise ValueError('relay control nodes were not stopped')
            if relay['authentic_shielded_acceptance'] is not None:
                raise ValueError('relay controls cannot claim authentic Shielded acceptance')
    except (KeyError, TypeError) as error:
        raise ValueError('missing or malformed report control evidence') from error


def render(directory: Path) -> None:
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    summary = json.loads((directory / 'summary.json').read_text(encoding='utf-8'))
    if not manifest['complete'] or manifest['smoke_only']:
        raise ValueError('the report requires a complete full experiment')
    rows = summary['results']
    expected = {(s['name'], m, p) for s in SCENARIOS for m in (1, 16) for p in POLICIES}
    actual = {(r['scenario']['name'], r['spacing'], r['policy']) for r in rows}
    if actual != expected or len(rows) != len(expected):
        raise ValueError('missing or duplicate experiment cells')
    if any(r['authentic_shielded_acceptance'] is not None for r in rows):
        raise ValueError('synthetic experiment cannot claim authentic Shielded acceptance')
    for name, digest in manifest['source_sha256'].items():
        if file_sha256(directory / 'source' / name) != digest:
            raise ValueError(f'archived source hash mismatch: {name}')
    validate_controls(manifest, summary)
    fields = [
        'name', 'spacing', 'policy', 'publication_height', 'inclusion_height',
        'initial_anchor', 'final_anchor', 'final_anchor_age', 'model_height_eligible',
        'included_fee_sats', 'included_height_ineligible_fee_sats', 'attempt_count',
        'distinct_synthetic_payloads', 'synthetic_marker_links', 'vsize',
    ]
    with (directory / 'summary.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    by_key = {(r['scenario']['name'], r['spacing'], r['policy']): r for r in rows}
    fee = by_key['deadline_crossed', 16, 'fee_only']
    fresh = by_key['deadline_crossed', 16, 'refresh_on_bump']
    hold = by_key['deadline_crossed', 16, 'hold']
    near_tip = by_key['deadline_crossed', 1, 'fee_only']
    matched_fee_and_height = (
        fee['included_fee_sats'] == fresh['included_fee_sats']
        and fee['inclusion_height'] == fresh['inclusion_height']
    )
    supported = (
        matched_fee_and_height and not fee['model_height_eligible']
        and fresh['model_height_eligible'] and near_tip['model_height_eligible']
    )
    implication = (
        '**Practical implication:** check the remaining anchor budget when raising the fee. '
        'In this workload, fee escalation alone buys a Bitcoin confirmation whose payload '
        'is already height-ineligible. Refreshing the modeled anchor avoids that condition '
        'at the same fee and inclusion height, assuming rebuilding completes in time.'
        if supported else
        'This run does not show the stated matched-fee, matched-height benefit from '
        'refreshing a shared anchor. Inspect the individual outcomes and controls below.'
    )
    text = [
        '# Controlled publication-policy results', '',
        'These are real Bitcoin Core 31.1 regtest carrier observations combined with a '
        'height-only model of the Shielded paper. Payloads are visibly synthetic. '
        '**No Shielded proof, note, root or complete transfer was verified.**', '',
        '## Decision supported by this workload', '',
        f'With a 16-block shared boundary, six-block wallet depth and 87 blocks offline, '
        f'the fee-only policy paid {fee["included_fee_sats"]:,} satoshis and was mined at '
        f'height {fee["inclusion_height"]}. Its original anchor was then '
        f'{fee["final_anchor_age"]} blocks old; height eligibility was '
        f'{fee["model_height_eligible"]}. '
        f'The refresh policy used the **same fee schedule**, paid '
        f'{fresh["included_fee_sats"]:,} satoshis and was mined at height '
        f'{fresh["inclusion_height"]}; its anchor age was {fresh["final_anchor_age"]} '
        f'and height eligibility was {fresh["model_height_eligible"]}.', '',
        f'Waiting cost {hold["included_fee_sats"]:,} satoshis and reached height '
        f'{hold["inclusion_height"]}, at anchor age {hold["final_anchor_age"]}. '
        f'Under the same workload, choosing the newest six-block-deep anchor (spacing 1) '
        f'left the fee-only policy at age {near_tip["final_anchor_age"]}, with height '
        f'eligibility {near_tip["model_height_eligible"]}.', '',
        implication + ' The experiment does not establish an optimal spacing, '
        'a safe mainnet reserve or a production default.', '',
        '## All observed cells', '',
        'The four workloads are deliberately chosen controls, not samples of user behavior. '
        'Do not interpret their fraction of ineligible cells as a failure rate.', '',
        '| Workload | Spacing | Retry policy | Included H | Anchor age | Fee (sat) | Height eligible | Attempts / payloads |',
        '|---|---:|---|---:|---:|---:|---|---|',
    ]
    for row in rows:
        text.append(
            f'| {row["scenario"]["name"]} | {row["spacing"]} | {row["policy"]} | '
            f'{row["inclusion_height"]} | {row["final_anchor_age"]} | {row["included_fee_sats"]} | '
            f'{"yes" if row["model_height_eligible"] else "no"} | '
            f'{row["attempt_count"]} / {row["distinct_synthetic_payloads"]} |'
        )
    text += [
        '', '## Controls and provenance', '',
        'Each policy starts from the same closed regtest snapshot. Background transaction '
        'prefixes are checked byte-for-byte across policies and anchor spacings in each '
        'workload. Each mined block is checked against the immediately observed Core '
        'template. Outcomes come from Core block contents, not assigned confirmation labels.', '',
        'The carrier is a 610-byte LABSB1 payload in a 614-byte OP_RETURN script. '
        'With one P2TR funding input and one P2TR change output, the measured whole '
        f'transaction is {rows[0]["vsize"]} vB. Fees use this whole-transaction size.', '',
        'Two no-background carriers were both mined at explicitly controlled anchor '
        'ages 100 and 101. Only the first passes the paper height predicate; these '
        'are boundary controls, not performance measurements.', '',
        '| Receiver data-carrier limit | Small carrier received | 610-byte payload received | Higher-fee replacement received |',
        '|---|---|---|---|',
    ]
    for relay in summary['controls']['relay']:
        text.append(f'| {relay["receiver_datacarriersize"]} | {relay["small_received"]} | '
                    f'{relay["large_received"]} | {relay["high_fee_large_received"]} |')
    text += [
        '', 'Direct receiver admission tests accompany the bounded peer observations. '
        'A restrictive carrier policy is a structural rejection that the fee increase '
        'does not remove. The two-node local topology does not measure public-network reachability.', '',
        'Relay waits advance the nodes\' mock clocks to exercise inventory timers; '
        'elapsed relay latency is not measured. After receipt, the relaxed receiver\'s '
        'direct admission check reports already-in-mempool; the restrictive receiver '
        'reports datacarrier rejection.', '',
        '## Limits', '',
        '- Rebuilding only replaces labeled synthetic bytes. Real proving time, witness acquisition, '
        'reorganizations and full Shielded validity are absent.',
        '- Six blocks is the wallet selection depth; replay still uses Kmin=1. '
        'Spacing 1 and 16, the two-block reserve, fee levels and workload durations are experimental choices.',
        '- Blocks use a deliberately small 10,000-WU template limit with 2,000 WU reserved, '
        'two 10-sat/vB background carriers per congested block, and no public peers. '
        'Their timestamps and offline blocks are controlled inputs, not elapsed mainnet time.',
        '- Policies observe only current height, anchor and elapsed step. Both fee policies '
        'raise 1 to 20 sat/vB at step 5; the refresh variant checks the same current-height margin. '
        'A workload stops being recorded when its carrier confirms; all earlier background prefixes match.',
        '- Replaced attempts do not pay a miner fee. Only the included attempt contributes to fee totals. '
        'Fees on height-ineligible carriers are not measured fees on real failed Shielded transfers.',
        '- Public test markers stay equal across rebuilt payloads. The exported link count describes '
        'these synthetic bytes; it is not an anonymity score or evidence about human identities.',
        '- A fresh baseline uses a new test wallet, so block/transaction IDs can change on rerun. '
        'The declared workloads, fee amounts, heights, margins and control outcomes are reproducible.', '',
        '## Reproduce and inspect', '',
        'See the repository README. `summary.csv` supports analysis; each case retains transactions, '
        'decision inputs, selected blocks and raw RPC exchanges. The manifest hashes the binary and '
        'an archived copy of the exact runner source. Private wallets, cookies and node databases '
        'are outside this result directory. All owned nodes were stopped.', '',
        'Sources: [Shielded Bitcoin, sections 8 and Appendix A.4/A.6]'
        '(https://www.allocinit.xyz/uploads/shielded-bitcoin.pdf), '
        '[Core 30 data-carrier policy](https://bitcoincore.org/en/releases/30.0/), '
        '[ZIP 318 prior art for shared anchors]'
        '(https://github.com/zcash/zips/blob/60db9f1e6a1e9988da442b7d8436da6b16dd5c26/zips/zip-0318.md).', '',
    ]
    (directory / 'REPORT.md').write_text('\n'.join(text), encoding='utf-8')
    save_json(directory / 'report-provenance.json', {
        'report_script_sha256': file_sha256(Path(__file__)),
        'input_summary_sha256': file_sha256(directory / 'summary.json'),
        'input_manifest_sha256': file_sha256(directory / 'manifest.json'),
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    render(parser.parse_args().directory)
