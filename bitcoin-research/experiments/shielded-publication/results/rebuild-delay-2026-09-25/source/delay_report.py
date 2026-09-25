"""Reconcile delayed-refresh observations before rendering any conclusion."""

import argparse
import csv
from decimal import Decimal
import json
from pathlib import Path

from core import file_sha256, save_json
from policy import payload_fields
from rebuild_delay import DELAYS, SOURCES, WORKLOADS, case_name, cells


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate_case(case: dict, trace: list[dict], baseline: dict) -> dict:
    row = case['result']
    name, workload, policy, delay = (row[key] for key in ('name', 'workload', 'policy', 'delay_blocks'))
    require((workload, policy, delay) in cells() and name == case_name(workload, policy, delay),
            'unknown experiment cell')
    require(row['node_stopped'] is True and row['authentic_shielded_acceptance'] is None,
            'cleanup or authentic-acceptance label is invalid')
    require(row['publication_height'] == 288 and row['initial_anchor'] == 192,
            'unexpected publication height or initial anchor')
    require(row['baseline_hash'] == baseline['block_hash'], 'baseline mismatch')
    candidates, blocks = case['candidates'], case['blocks']
    require(len(candidates) == (1 if policy == 'hold' else 2), 'missing or extra candidate')
    require(bool(blocks) and [b['height'] for b in blocks] == list(range(288, 288 + len(blocks))),
            'non-contiguous observed blocks')
    admissions, raw_blocks, templates, broadcasts = {}, {}, [], {}
    last_height = 287
    final_mempool = None
    startup_complete = False
    version_observed = False
    for item in trace:
        request, response = item['request'], item['response']
        if (not startup_complete and request['method'] == 'getblockchaininfo'
                and response.get('error', {}).get('code') == -28):
            continue  # The owned-node helper polls through Core's startup phase.
        require(not response.get('error'), 'unexpected RPC error in trace')
        method, result = request['method'], response['result']
        if method == 'testmempoolaccept':
            admissions[request['params'][0][0]] = result[0]
        elif method == 'getblock':
            raw_blocks[result['hash']] = result
            last_height = result['height']
        elif method == 'getblocktemplate':
            templates.append([t['txid'] for t in result['transactions']])
        elif method == 'sendrawtransaction':
            require(result not in broadcasts, 'duplicate broadcast')
            broadcasts[result] = (request['params'][0], last_height + 1)
        elif method == 'getrawmempool':
            final_mempool = result
        elif method == 'getblockchaininfo':
            startup_complete = True
            require(result['chain'] == 'regtest' and result['blocks'] == 287
                    and result['bestblockhash'] == row['publication_chain_hash'],
                    'publication snapshot mismatch')
        elif method == 'getnetworkinfo':
            require(result['version'] == 310100, 'unexpected observed Core version')
            version_observed = True
    require(startup_complete, 'missing ready-node chain observation')
    require(version_observed, 'missing observed Core version')
    require(len(templates) == len(blocks), 'missing template evidence')
    for block, template in zip(blocks, templates):
        raw = raw_blocks.get(block['hash'])
        require(raw is not None and raw['height'] == block['height'] and raw['tx'] == block['txids']
                and raw['weight'] == block['weight'] <= 10000, 'block differs from raw RPC evidence')
        require(template == block['template_txids'] == block['txids'][1:], 'template/mined mismatch')
    require(final_mempool == case['final_mempool'], 'missing final mempool observation')
    require(case['funding_unspent'] is None, 'carrier funding input was not consumed')
    outpoint = baseline['utxos'][0]
    for index, candidate in enumerate(candidates):
        require(candidate['role'] == ('original' if index == 0 else 'replacement'), 'candidate order')
        fields = payload_fields(bytes.fromhex(candidate['payload_hex']))
        require(all(candidate[key] == value for key, value in fields.items()), 'payload metadata mismatch')
        require(candidate['funding_outpoint'] == {'txid': outpoint['txid'], 'vout': outpoint['vout'],
                                                 'sequence': 0xFFFFFFFD}, 'candidates do not conflict')
        require(candidate['op_return_script_bytes'] == 614, 'unexpected carrier script')
        admission = admissions.get(candidate['hex'])
        require(admission == candidate['admission'] and admission is not None
                and admission['txid'] == candidate['txid'], 'missing candidate admission evidence')
        require(type(admission['allowed']) is bool, 'invalid admission label')
        expected_rate = 1 if index == 0 else 20
        require(candidate['rate_sat_vb'] == expected_rate
                and candidate['fee_sats'] == expected_rate * candidate['vsize'], 'incorrect candidate fee')
        if admission['allowed']:
            require(admission['vsize'] == candidate['vsize']
                    and Decimal(str(admission['fees']['base'])) * 100_000_000 == candidate['fee_sats'],
                    'fee/size differs from Core admission')
            require(broadcasts.get(candidate['txid']) == (candidate['hex'], candidate['ready_before_height'])
                    and candidate['broadcast_before_height'] == candidate['ready_before_height'],
                    'candidate broadcast did not occur at readiness')
        else:
            require(candidate['txid'] not in broadcasts and candidate['broadcast_before_height'] is None,
                    'rejected candidate was broadcast')
        require(candidate['txid'] not in final_mempool, 'conflicting carrier remains in mempool')
    original = candidates[0]
    require(original['anchor_height'] == 192 and original['admission']['allowed'] is True
            and original['ready_before_height'] == original['constructed_before_height'] == 288,
            'invalid original carrier')
    replacement = candidates[1] if len(candidates) == 2 else None
    if replacement:
        expected_ready = 293 + (delay or 0)
        require(replacement['constructed_before_height'] == 293
                and replacement['ready_before_height'] == expected_ready, 'candidate delay mismatch')
        require(replacement['anchor_height'] == (192 if policy == 'fee_only' else 272),
                'candidate anchor was not frozen at construction')
        require((replacement['payload_hex'] == original['payload_hex']) is (policy == 'fee_only'),
                'fee-only and refresh payload distinction is missing')
    confirmations = [(candidate, block['height']) for candidate in candidates for block in blocks
                     if candidate['txid'] in block['txids']]
    require(len(confirmations) == 1, 'expected exactly one observed carrier confirmation')
    winner, height = confirmations[0]
    require(winner['admission']['allowed'] is True and winner['broadcast_before_height'] <= height,
            'winner was not broadcast and admitted before inclusion')
    age = height - winner['anchor_height']
    expected = {
        'winner': winner['role'], 'included_txid': winner['txid'], 'inclusion_height': height,
        'final_anchor': winner['anchor_height'], 'final_anchor_age': age,
        'included_fee_sats': winner['fee_sats'], 'vsize': winner['vsize'],
        'model_height_eligible': 1 <= age <= 100,
        'candidate_ready_height': replacement['ready_before_height'] if replacement else None,
        'candidate_anchor': replacement['anchor_height'] if replacement else None,
        'candidate_allowed': replacement['admission']['allowed'] if replacement else None,
        'candidate_reject_reason': replacement['admission'].get('reject-reason') if replacement else None,
        'original_confirmed_while_pending': bool(replacement and winner['role'] == 'original'
                                                and 293 <= height < replacement['ready_before_height']),
    }
    require(all(row[key] == value and type(row[key]) is type(value) for key, value in expected.items()),
            'summary contradicts observed winner, fee, readiness or height eligibility')
    if replacement and not replacement['admission']['allowed']:
        require(expected['original_confirmed_while_pending']
                and replacement['admission'].get('reject-reason') == 'missing-inputs',
                'rejection is not explained by original confirmation while pending')
    expected_background = [(step, slot) for step in range(min(WORKLOADS[workload], len(blocks)))
                           for slot in (0, 1)]
    require([(t['step'], t['slot']) for t in case['background']] == expected_background,
            'missing or extra background workload')
    for tx in case['background']:
        require(broadcasts.get(tx['txid']) == (tx['hex'], 288 + tx['step'])
                and admissions[tx['hex']]['allowed'] is True
                and tx['rate_sat_vb'] == 10 and tx['fee_sats'] == 10 * tx['vsize'],
                'background broadcast differs from schedule')
    return row


def validate(directory: Path) -> list[dict]:
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    summary = json.loads((directory / 'summary.json').read_text(encoding='utf-8'))
    require(manifest['experiment'] == 'carrier-rebuild-delay-v1' and manifest['complete'] is True
            and manifest['case_count'] == 16 and manifest['all_owned_nodes_stopped'] is True,
            'a complete stopped 16-case experiment is required')
    require(manifest['network'] == 'regtest' and manifest['authentic_shielded_verifier'] is False
            and manifest['measured_proving_time'] is False, 'invalid evidence scope')
    method_parameters = {
        'core_version_required': '31.1', 'blockmaxweight': 10000, 'blockreservedweight': 2000,
        'fee_rates_sat_vb': {'initial': 1, 'background': 10, 'retry': 20},
        'event_order': 'candidate readiness and broadcast before template and mining',
    }
    require(all(manifest.get(key) == value for key, value in method_parameters.items()),
            'unexpected method parameters')
    require(manifest['delays_blocks'] == list(DELAYS) and manifest['workloads'] == WORKLOADS
            and manifest['profile'] == {'window': 100, 'minimum_depth': 1}
            and manifest['spacing'] == 16 and manifest['wallet_depth'] == 6
            and manifest['retry_step'] == 5 and manifest['offline_blocks'] == 87,
            'unexpected experiment parameters')
    require(set(manifest['source_sha256']) == set(SOURCES), 'missing archived sources')
    for name, digest in manifest['source_sha256'].items():
        require(file_sha256(directory / 'source' / name) == digest, f'archived source mismatch: {name}')
    rows = summary['results']
    require(len(rows) == 16 and {r['name'] for r in rows} == {case_name(*cell) for cell in cells()},
            'missing or duplicate experiment cells')
    baseline = json.loads((directory / 'baseline.json').read_text(encoding='utf-8'))
    groups = {workload: [] for workload in WORKLOADS}
    for row in rows:
        case = json.loads((directory / row['name'] / 'case.json').read_text(encoding='utf-8'))
        require(case['result'] == row, 'summary differs from per-case result')
        trace = [json.loads(line) for line in (directory / row['name'] / 'rpc.jsonl').read_text(
            encoding='utf-8').splitlines()]
        validate_case(case, trace, baseline)
        groups[row['workload']].append(case)
    for group in groups.values():
        require(len({c['result']['publication_chain_hash'] for c in group}) == 1,
                'paired cases used different publication snapshots')
        for index, left in enumerate(group):
            for right in group[index + 1:]:
                common = min(len(left['background']), len(right['background']))
                require(left['background'][:common] == right['background'][:common],
                        'paired cases saw different background prefixes')
    return rows


def render(directory: Path) -> None:
    rows = validate(directory)
    fields = ['name', 'delay_blocks', 'candidate_ready_height', 'winner', 'inclusion_height',
              'final_anchor_age', 'included_fee_sats', 'model_height_eligible', 'candidate_reject_reason']
    with (directory / 'summary.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    lines = [
        '# Delayed rebuilds and the old-carrier race', '',
        'Sixteen isolated Core 31.1 regtest cases. Bitcoin confirmation and fees are observed; '
        'Shielded eligibility is only the W=100 height model. No authentic proof is generated or verified.', '',
        '| Workload / policy | Delay (blocks) | Ready before H | Winner | Included H | Anchor age | Fee (sat) | Height eligible |',
        '| --- | ---: | ---: | --- | ---: | ---: | ---: | --- |',
    ]
    for row in rows:
        lines.append(f'| {row["name"]} | {row["delay_blocks"] if row["delay_blocks"] is not None else "—"} '
                     f'| {row["candidate_ready_height"] or "—"} | {row["winner"]} '
                     f'| {row["inclusion_height"]} | {row["final_anchor_age"]} '
                     f'| {row["included_fee_sats"]} | {str(row["model_height_eligible"]).lower()} |')
    lines.extend(['', '## Observed delay budgets', ''])
    for workload in WORKLOADS:
        selected = [r for r in rows if r['workload'] == workload and r['policy'] == 'refresh']
        successful = [r['delay_blocks'] for r in selected if r['winner'] == 'replacement'
                      and r['model_height_eligible']]
        lost = [r['delay_blocks'] for r in selected if r['original_confirmed_while_pending']]
        lines.append(f'- `{workload}`: tested delays with an eligible refreshed winner: {successful}; '
                     f'tested delays where the original confirmed during preparation: {lost}.')
    lines.extend([
        '', 'A rejected late replacement spends no additional miner fee. The old winner still pays '
        'its recorded Bitcoin fee even when its synthetic anchor fails the height model. '
        'This does not establish that any shielded note was lost or spent.', '',
        '## Method and limits', '',
        'The initial construction view is H200 (anchor 192); publication begins before H288. '
        'At H293 the fee-only control raises fees without changing the payload, while refresh '
        'freezes a new anchor at 272 and withholds its candidate for the declared delay. '
        'Initial, background and replacement rates are 1, 10 and 20 sat/vB. '
        'The two workloads inject two background transactions before each of five or eight blocks. '
        'All cases start from the same closed snapshot and shared background prefixes.', '',
        'Readiness is processed before that height\'s template and mining. A candidate ready before '
        'H296 can replace the old carrier before the H296 block; readiness before H297 is too late '
        'if the original confirmed at H296. These are explicit sequential event-order cases, '
        'not a measurement of a simultaneous network race or propagation latency.', '',
        'Candidates share a Bitcoin funding input. This tests Bitcoin replacement; it is different '
        'from two independently funded carriers competing over the same shielded notes. '
        'No cancellation, alternative fee funding, reorg, authentic verifier, witness builder or '
        'wallet recovery is implemented. No privacy, production safety or mainnet probability claim follows.', '',
        'The candidate bytes are signed at rebuild start and withheld. Delay counts are controlled '
        'block budgets, not measured cryptographic computation. A useful next integration is to '
        'map observed proof/witness completion and chain advances into this schedule, retaining the '
        'old carrier and accounting for a ready candidate arriving after a block.', '',
        '## Evidence', '',
        '`case.json` stores both candidates (including rejected, never-broadcast replacements), '
        'Core admissions, backgrounds, mined blocks and event records; `rpc.jsonl` records the '
        'corresponding Core replies. The report validates all cells, actual winner/fee/admission '
        'observations, template agreement, scheduled broadcasts, shared workload prefixes, '
        'stopped-node labels and source hashes before writing outputs.', '',
    ])
    (directory / 'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
    inputs = [p for p in directory.rglob('*') if p.is_file()
              and p.name not in {'REPORT.md', 'summary.csv', 'report-provenance.json'}]
    save_json(directory / 'report-provenance.json', {
        'report_source_sha256': file_sha256(Path(__file__)),
        'input_sha256': {p.relative_to(directory).as_posix(): file_sha256(p) for p in sorted(inputs)},
    })


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    render(parser.parse_args().directory)
