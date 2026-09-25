"""Measure delayed synthetic refreshes while the original carrier stays live."""

import argparse
import hashlib
from pathlib import Path
import shutil

from bench import baseline, fork_node, offline_snapshot
from core import build_carrier, file_sha256, save_json, submit
from policy import AnchorProfile, integer, make_payload, payload_fields


DELAYS = (0, 1, 2, 3, 4, 8)
WORKLOADS = {'clear_at_retry': 5, 'longer_backlog': 8}
SOURCES = ('rebuild_delay.py', 'delay_report.py', 'bench.py', 'core.py', 'policy.py')


def ready_height(start_height: int, delay_blocks: int) -> int:
    """Ready candidates are processed before mining the named height's block."""
    integer('start height', start_height, 1)
    integer('delay blocks', delay_blocks)
    return start_height + delay_blocks


def cells() -> list[tuple[str, str, int | None]]:
    return [(workload, policy, delay) for workload in WORKLOADS
            for policy, delay in [('hold', None), ('fee_only', None)]
            + [('refresh', delay) for delay in DELAYS]]


def case_name(workload: str, policy: str, delay: int | None) -> str:
    return f'{workload}-{policy}' + (f'-d{delay}' if delay is not None else '')


def run_case(binary: Path, base: Path, info: dict, work: Path, output: Path,
             workload: str, policy: str, delay: int | None) -> dict:
    name = case_name(workload, policy, delay)
    directory = output / name
    directory.mkdir()
    node = fork_node(binary, base, work / name, trace=directory / 'rpc.jsonl')
    profile = AnchorProfile()
    original_anchor = profile.choose(info['height'] + 1, 16, 6)
    if original_anchor is None:
        raise RuntimeError('initial anchor unavailable')
    candidates, blocks, background, events = [], [], [], []
    winner = None
    replacement = None
    with node:
        node.ensure_wallet()
        if node.call('getblockcount') != 287:
            raise RuntimeError('expected the shared height-287 publication snapshot')
        publication_hash = node.call('getbestblockhash')
        payload = make_payload(original_anchor, 0)
        original = {
            **build_carrier(node, info['utxos'][0], info['change'], payload, 1),
            **payload_fields(payload), 'role': 'original',
            'constructed_before_height': 288, 'ready_before_height': 288,
            'broadcast_before_height': 288,
        }
        original['admission'] = submit(node, original)
        candidates.append(original)
        for step in range(24):
            height = node.call('getblockcount') + 1
            if step == 5 and policy != 'hold':
                anchor = original_anchor if policy == 'fee_only' else profile.choose(height, 16, 6)
                if anchor is None:
                    raise RuntimeError('refresh anchor unavailable')
                # Construct bytes now, but withhold them for the modeled rebuild.
                # This is a block-delay budget, not a measured proving duration.
                fresh_payload = payload if policy == 'fee_only' else make_payload(anchor, 1)
                replacement = {
                    **build_carrier(node, info['utxos'][0], info['change'], fresh_payload, 20),
                    **payload_fields(fresh_payload), 'role': 'replacement',
                    'constructed_before_height': height,
                    'ready_before_height': ready_height(height, delay or 0),
                    'broadcast_before_height': None, 'admission': None,
                }
                candidates.append(replacement)
                events.append({'kind': 'candidate_prepared', 'before_height': height,
                               'ready_before_height': replacement['ready_before_height']})
            if (replacement is not None and replacement['admission'] is None
                    and height >= replacement['ready_before_height']):
                admission = node.call('testmempoolaccept', [replacement['hex']])[0]
                replacement['admission'] = admission
                events.append({'kind': 'candidate_ready', 'before_height': height,
                               'allowed': admission['allowed']})
                if admission.get('allowed'):
                    if node.call('sendrawtransaction', replacement['hex']) != replacement['txid']:
                        raise RuntimeError('submitted candidate txid differs')
                    replacement['broadcast_before_height'] = height
                elif winner is None or winner['role'] != 'original':
                    raise RuntimeError(f'unexpected replacement rejection: {admission}')
            # After the old winner, keep the chain moving only until readiness
            # is tested. Never rebroadcast, cancel or spend another funding UTXO.
            if winner is not None and replacement is not None and replacement['admission'] is not None:
                break
            if step < WORKLOADS[workload]:
                for slot in range(2):
                    data = b'LABBG1' + hashlib.shake_256(f'background-{step}-{slot}'.encode()).digest(604)
                    tx = build_carrier(node, info['utxos'][1 + step * 2 + slot], info['change'], data, 10)
                    submit(node, tx)
                    background.append({**tx, 'step': step, 'slot': slot})
            node.call('setmocktime', 1_700_000_000 + height * 600)
            template = node.call('getblocktemplate', {'rules': ['segwit']})
            selected = [transaction['txid'] for transaction in template['transactions']]
            block_hash = node.mine(info['miner'])[0]
            block = node.call('getblock', block_hash)
            if block['tx'][1:] != selected:
                raise RuntimeError('mined transactions differ from Core template')
            blocks.append({'height': block['height'], 'hash': block_hash,
                           'txids': block['tx'], 'template_txids': selected, 'weight': block['weight']})
            for candidate in candidates:
                if candidate['txid'] in block['tx']:
                    if winner is not None:
                        raise RuntimeError('two conflicting carriers confirmed')
                    winner = {'role': candidate['role'], 'txid': candidate['txid'],
                              'height': block['height'], 'anchor': candidate['anchor_height'],
                              'fee_sats': candidate['fee_sats'], 'vsize': candidate['vsize']}
                    events.append({'kind': 'carrier_confirmed', **winner})
            if winner is not None and (replacement is None or replacement['admission'] is not None):
                break
        if winner is None or (replacement is not None and replacement['admission'] is None):
            raise RuntimeError('experiment did not reach confirmation and candidate readiness')
        mempool = node.call('getrawmempool')
        if any(candidate['txid'] in mempool for candidate in candidates):
            raise RuntimeError('a confirmed or conflicting carrier remains in the mempool')
        funding_unspent = node.call('gettxout', info['utxos'][0]['txid'], info['utxos'][0]['vout'])
        if funding_unspent is not None:
            raise RuntimeError('confirmed carrier did not consume its funding input')
    result = {
        'name': name, 'workload': workload, 'policy': policy, 'delay_blocks': delay,
        'publication_height': 288, 'initial_anchor': original_anchor,
        'candidate_ready_height': replacement['ready_before_height'] if replacement else None,
        'candidate_anchor': replacement['anchor_height'] if replacement else None,
        'candidate_allowed': replacement['admission']['allowed'] if replacement else None,
        'candidate_reject_reason': replacement['admission'].get('reject-reason') if replacement else None,
        'winner': winner['role'], 'included_txid': winner['txid'],
        'inclusion_height': winner['height'], 'final_anchor': winner['anchor'],
        'final_anchor_age': winner['height'] - winner['anchor'],
        'included_fee_sats': winner['fee_sats'], 'vsize': winner['vsize'],
        'model_height_eligible': profile.eligible(winner['anchor'], winner['height']),
        'original_confirmed_while_pending': bool(replacement and winner['role'] == 'original'
                                                and winner['height'] < replacement['ready_before_height']),
        'baseline_hash': info['block_hash'], 'publication_chain_hash': publication_hash,
        'node_stopped': node.stopped, 'authentic_shielded_acceptance': None,
    }
    save_json(directory / 'case.json', {'result': result, 'candidates': candidates,
                                      'background': background, 'blocks': blocks, 'events': events,
                                      'final_mempool': mempool, 'funding_unspent': funding_unspent})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bitcoind', required=True, type=Path)
    parser.add_argument('--work-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    binary = args.bitcoind.resolve(strict=True)
    work, output = args.work_dir.resolve(), args.output.resolve()
    if work == output or work in output.parents or output in work.parents:
        raise ValueError('private runtime and portable output must be separate')
    if work.exists() or output.exists():
        raise ValueError('use new work and output directories')
    work.mkdir(parents=True)
    output.mkdir(parents=True)
    source = output / 'source'
    source.mkdir()
    for name in SOURCES:
        shutil.copyfile(Path(__file__).parent / name, source / name)
    manifest = {
        'experiment': 'carrier-rebuild-delay-v1', 'complete': False, 'network': 'regtest',
        'core_version_required': '31.1', 'binary_sha256': file_sha256(binary),
        'source_sha256': {name: file_sha256(source / name) for name in SOURCES},
        'profile': {'window': 100, 'minimum_depth': 1}, 'wallet_depth': 6, 'spacing': 16,
        'offline_blocks': 87, 'retry_step': 5, 'delays_blocks': list(DELAYS),
        'workloads': WORKLOADS, 'fee_rates_sat_vb': {'initial': 1, 'background': 10, 'retry': 20},
        'blockmaxweight': 10000, 'blockreservedweight': 2000,
        'event_order': 'candidate readiness and broadcast before template and mining',
        'authentic_shielded_verifier': False, 'measured_proving_time': False,
        'all_owned_nodes_stopped': False,
    }
    save_json(output / 'manifest.json', manifest)
    print('Creating isolated baseline and publication snapshot...', flush=True)
    base, info = baseline(binary, work)
    save_json(output / 'baseline.json', info)
    snapshot = offline_snapshot(binary, base, info, work, 87)
    results = []
    for workload, policy, delay in cells():
        result = run_case(binary, snapshot, info, work, output, workload, policy, delay)
        results.append(result)
        print(f'{result["name"]}: {result["winner"]} H={result["inclusion_height"]} '
              f'age={result["final_anchor_age"]} eligible={result["model_height_eligible"]} '
              f'candidate_allowed={result["candidate_allowed"]}', flush=True)
    save_json(output / 'summary.json', {'results': results})
    manifest.update(complete=True, case_count=len(results), all_owned_nodes_stopped=True)
    save_json(output / 'manifest.json', manifest)
    print(f'Completed {len(results)} cases; all owned nodes stopped.', flush=True)


if __name__ == '__main__':
    main()
