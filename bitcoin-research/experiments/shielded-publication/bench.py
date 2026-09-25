"""Run a bounded publication-policy experiment on private Core 31.1 regtest nodes."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import time

from core import Node, build_carrier, file_sha256, save_json, submit
from policy import POLICIES, AnchorProfile, action_at_height, boundary_summary, make_payload, payload_fields


SCENARIOS = (
    {'name': 'fresh_congested', 'offline_blocks': 0, 'background_blocks': 8},
    {'name': 'near_deadline', 'offline_blocks': 85, 'background_blocks': 8},
    {'name': 'deadline_crossed', 'offline_blocks': 87, 'background_blocks': 8},
    {'name': 'early_clear', 'offline_blocks': 87, 'background_blocks': 3},
)


def baseline(binary: Path, work: Path) -> tuple[Path, dict]:
    directory = work / 'baseline'
    node = Node(binary, directory)
    with node:
        node.call('createwallet', 'lab', False, False, '', False, True, True)
        miner = node.call('getnewaddress', '', 'bech32m', wallet=True)
        change = node.call('getnewaddress', '', 'bech32m', wallet=True)
        node.mine(miner, 200)
        utxos = sorted(node.call('listunspent', wallet=True), key=lambda u: (u['txid'], u['vout']))
        if len(utxos) < 40:
            raise RuntimeError('baseline needs at least 40 mature independent funding outputs')
        info = {
            'height': node.call('getblockcount'), 'block_hash': node.call('getbestblockhash'),
            'miner': miner, 'change': change,
            'utxos': [{'txid': u['txid'], 'vout': u['vout'], 'amount': str(u['amount'])} for u in utxos],
        }
    if not node.stopped:
        raise RuntimeError('baseline must be stopped before snapshot copies')
    return directory, info


def fork_node(binary: Path, base: Path, destination: Path, **kwargs) -> Node:
    # Baseline is closed before this function is called. Never copy a live DB.
    shutil.copytree(base, destination)
    return Node(binary, destination, **kwargs)


def offline_snapshot(binary: Path, base: Path, info: dict, work: Path, blocks: int) -> Path:
    if blocks == 0:
        return base
    destination = work / f'offline-snapshot-{blocks}'
    node = fork_node(binary, base, destination)
    with node:
        node.mine(info['miner'], blocks)
    if not node.stopped:
        raise RuntimeError('offline snapshot must be closed before copying')
    return destination


def wait_until(predicate, seconds: float, description: str, advance=None) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        if advance:
            advance()
        time.sleep(0.2)
    raise TimeoutError(description)


def run_case(
    binary: Path, base: Path, info: dict, work: Path, output: Path,
    scenario: dict, spacing: int, policy: str,
) -> dict:
    name = f'{scenario["name"]}-m{spacing}-{policy}'
    result_dir = output / name
    result_dir.mkdir()
    node = fork_node(binary, base, work / name, trace=result_dir / 'rpc.jsonl')
    profile = AnchorProfile()
    initial_anchor = profile.choose(info['height'] + 1, spacing, 6)
    if initial_anchor is None:
        raise RuntimeError('comparison starts without a height-eligible anchor')
    anchor = initial_anchor
    attempts, blocks, decisions, background = [], [], [], []
    with node:
        node.ensure_wallet()
        if node.call('getblockcount') != info['height'] + scenario['offline_blocks']:
            raise RuntimeError('wrong offline snapshot for the declared scenario')
        publication_chain_hash = node.call('getbestblockhash')
        publication_height = node.call('getblockcount') + 1
        payload = make_payload(anchor, 0)
        carrier = build_carrier(node, info['utxos'][0], info['change'], payload, 1)
        admission = submit(node, carrier)
        attempts.append({**carrier, **payload_fields(payload), 'action': 'initial',
                         'broadcast_before_height': publication_height, 'admission': admission})
        included = None
        for step in range(24):
            candidate_height = node.call('getblockcount') + 1
            # Only information available at this decision height reaches the policy.
            action, next_anchor = action_at_height(
                policy, step, candidate_height, anchor, spacing, 6, profile,
            )
            decisions.append({'step': step, 'candidate_height': candidate_height,
                              'remaining_margin': anchor + profile.window - candidate_height,
                              'action': action, 'anchor_before': anchor, 'anchor_after': next_anchor})
            if action != 'hold':
                anchor = next_anchor
                if action == 'rebuild':
                    payload = make_payload(anchor, len(attempts))
                carrier = build_carrier(node, info['utxos'][0], info['change'], payload, 20)
                admission = submit(node, carrier)
                attempts.append({**carrier, **payload_fields(payload), 'action': action,
                                 'broadcast_before_height': candidate_height, 'admission': admission})
            if step < scenario['background_blocks']:
                for slot in range(2):
                    index = 1 + step * 2 + slot
                    data = b'LABBG1' + hashlib.shake_256(f'background-{step}-{slot}'.encode()).digest(604)
                    tx = build_carrier(node, info['utxos'][index], info['change'], data, 10)
                    submit(node, tx)
                    background.append({**tx, 'step': step, 'slot': slot})
            node.call('setmocktime', 1_700_000_000 + candidate_height * 600)
            template = node.call('getblocktemplate', {'rules': ['segwit']})
            selected = [t['txid'] for t in template['transactions']]
            block_hash = node.mine(info['miner'])[0]
            block = node.call('getblock', block_hash)
            if block['tx'][1:] != selected:
                raise RuntimeError('mined block differs from observed Core template selection')
            blocks.append({'height': block['height'], 'hash': block_hash,
                           'txids': block['tx'], 'weight': block['weight'],
                           'template_weight': sum(t['weight'] for t in template['transactions'])})
            if carrier['txid'] in block['tx']:
                included = block['height']
                break
        if included is None:
            raise RuntimeError('case ended without observed carrier inclusion')
        mempool = node.call('getrawmempool')
        if any(a['txid'] in mempool for a in attempts):
            raise RuntimeError('included/replaced carrier remains in the observed mempool')
    final = attempts[-1]
    eligible = profile.eligible(final['anchor_height'], included)
    result = {
        'name': name, 'scenario': scenario, 'spacing': spacing, 'wallet_depth': 6,
        'policy': policy, 'profile': asdict(profile), 'initial_anchor': initial_anchor,
        'publication_height': publication_height, 'inclusion_height': included,
        'final_anchor': final['anchor_height'], 'final_anchor_age': included - final['anchor_height'],
        'model_height_eligible': eligible, 'authentic_shielded_acceptance': None,
        'included_fee_sats': final['fee_sats'],
        'included_height_ineligible_fee_sats': 0 if eligible else final['fee_sats'],
        'attempt_count': len(attempts),
        'distinct_synthetic_payloads': len({a['payload_hex'] for a in attempts}),
        'synthetic_marker_links': len(attempts) - 1,
        'vsize': final['vsize'], 'carrier_weight': final['weight'],
        'op_return_script_bytes': final['op_return_script_bytes'],
        'baseline_hash': info['block_hash'], 'publication_chain_hash': publication_chain_hash,
        'node_stopped': node.stopped,
    }
    save_json(result_dir / 'transactions.json', {'attempts': attempts, 'background': background})
    save_json(result_dir / 'decisions.json', decisions)
    save_json(result_dir / 'blocks.json', blocks)
    save_json(result_dir / 'result.json', result)
    return result


def boundary_control(binary: Path, base: Path, info: dict, work: Path, output: Path) -> dict:
    directory = output / 'boundary-control'
    directory.mkdir()
    node = fork_node(binary, base, work / 'boundary-control', trace=directory / 'rpc.jsonl')
    cases = []
    with node:
        node.ensure_wallet()
        height = node.call('getblockcount') + 1
        for index, age in enumerate((100, 101)):
            data = make_payload(height - age, index)
            tx = build_carrier(node, info['utxos'][index], info['change'], data, 1)
            submit(node, tx)
            cases.append({**tx, 'anchor_age': age, 'anchor_height': height - age})
        block = node.call('getblock', node.mine(info['miner'])[0])
        for case in cases:
            if case['txid'] not in block['tx']:
                raise RuntimeError('boundary control was not mined by Core')
            case['inclusion_height'] = block['height']
            case['model_height_eligible'] = AnchorProfile().eligible(case['anchor_height'], block['height'])
            case['authentic_shielded_acceptance'] = None
    result = {'kind': 'forced-height control, not a fee-performance measurement',
              'cases': cases, 'node_stopped': node.stopped}
    save_json(directory / 'result.json', result)
    return result


def relay_control(
    binary: Path, base: Path, info: dict, work: Path, output: Path, limit: int,
) -> dict:
    name = f'relay-limit-{limit}'
    directory = output / name
    directory.mkdir()
    sender = fork_node(binary, base, work / f'{name}-sender', trace=directory / 'sender-rpc.jsonl')
    receiver = fork_node(binary, base, work / f'{name}-receiver', carrier_limit=limit,
                         listen=True, trace=directory / 'receiver-rpc.jsonl')
    with sender, receiver:
        def advance_relay_clock():
            # Core's inventory timers use mock time. This is not a latency test.
            moment = max(sender.mock_time, receiver.mock_time) + 5
            sender.call('setmocktime', moment)
            receiver.call('setmocktime', moment)

        def settle_relay():
            for _ in range(10):
                advance_relay_clock()
                time.sleep(0.1)

        sender.ensure_wallet()
        sender.call('addnode', f'127.0.0.1:{receiver.p2p_port}', 'onetry')
        wait_until(lambda: any(p.get('version', 0) > 0 for p in sender.call('getpeerinfo')),
                   15, 'local peer handshake did not finish', advance_relay_clock)
        large = build_carrier(sender, info['utxos'][0], info['change'], make_payload(192, 0), 1)
        small = build_carrier(sender, info['utxos'][1], info['change'], b'LAB-SMALL', 1)
        large_admission = submit(sender, large)
        submit(sender, small)
        wait_until(lambda: small['txid'] in receiver.call('getrawmempool'),
                   30, 'small positive-control transaction did not reach the peer', advance_relay_clock)
        if limit == 100_000:
            wait_until(lambda: large['txid'] in receiver.call('getrawmempool'),
                       30, 'large transaction did not reach relaxed-policy peer', advance_relay_clock)
        else:
            settle_relay()
        receiver_before_bump = receiver.call('getrawmempool')
        large_received = large['txid'] in receiver_before_bump
        direct_large_check = receiver.call('testmempoolaccept', [large['hex']])[0]
        high_fee = build_carrier(sender, info['utxos'][0], info['change'], make_payload(192, 0), 20)
        high_admission = submit(sender, high_fee)
        barrier = build_carrier(sender, info['utxos'][2], info['change'], b'LAB-BARRIER', 1)
        submit(sender, barrier)
        wait_until(lambda: barrier['txid'] in receiver.call('getrawmempool'),
                   30, 'post-bump positive-control transaction did not reach peer', advance_relay_clock)
        if limit == 100_000:
            wait_until(lambda: high_fee['txid'] in receiver.call('getrawmempool'),
                       30, 'fee replacement did not reach relaxed peer', advance_relay_clock)
        else:
            settle_relay()
        high_received = high_fee['txid'] in receiver.call('getrawmempool')
        direct_high_check = receiver.call('testmempoolaccept', [high_fee['hex']])[0]
        expected = limit == 100_000
        if large_received != expected or high_received != expected:
            raise RuntimeError('relay outcome did not match its positive/negative policy control')
        if not expected and (direct_large_check.get('allowed') or direct_high_check.get('allowed')):
            raise RuntimeError('restrictive peer unexpectedly allowed a large payload locally')
    result = {
        'receiver_datacarriersize': limit, 'large_received': large_received,
        'high_fee_large_received': high_received, 'small_received': True, 'barrier_received': True,
        'large': large, 'high_fee': high_fee, 'sender_admission': large_admission,
        'sender_high_fee_admission': high_admission,
        'receiver_direct_check': direct_large_check, 'receiver_high_fee_check': direct_high_check,
        'authentic_shielded_acceptance': None, 'nodes_stopped': sender.stopped and receiver.stopped,
        'relay_clock': 'mock time advances five seconds per wait iteration; not a latency measurement',
    }
    save_json(directory / 'result.json', result)
    return result


def audit_results(results: list[dict], output: Path) -> None:
    # Workloads must match within each scenario before any policy finishes.
    groups = {}
    for result in results:
        group = result['scenario']['name']
        groups.setdefault(group, []).append(result)
        if result['op_return_script_bytes'] != 614:
            raise RuntimeError('610-byte payload did not produce the expected minimal script')
        if not result['node_stopped'] or result['authentic_shielded_acceptance'] is not None:
            raise RuntimeError('invalid cleanup or evidence label')
    for group in groups.values():
        for spacing in {r['spacing'] for r in group}:
            if {r['policy'] for r in group if r['spacing'] == spacing} != set(POLICIES):
                raise RuntimeError('incomplete policy comparison group')
        traces = [json.loads((output / r['name'] / 'transactions.json').read_text()) for r in group]
        common_steps = min(len(t['background']) for t in traces)
        prefix = traces[0]['background'][:common_steps]
        for trace in traces[1:]:
            if trace['background'][:common_steps] != prefix:
                raise RuntimeError('paired policies saw different background transaction prefixes')
        if len({(r['baseline_hash'], r['publication_chain_hash']) for r in group}) != 1:
            raise RuntimeError('paired policies did not start from the same closed snapshot')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bitcoind', required=True, type=Path)
    parser.add_argument('--work-dir', required=True, type=Path, help='new private runtime directory')
    parser.add_argument('--output', required=True, type=Path, help='new portable result directory')
    parser.add_argument('--smoke', action='store_true', help='one scenario/spacing, no relay controls')
    args = parser.parse_args()
    binary = args.bitcoind.resolve(strict=True)
    work, output = args.work_dir.resolve(), args.output.resolve()
    if work == output or work in output.parents or output in work.parents:
        raise ValueError('private runtime and portable output must be separate directories')
    if work.exists() or output.exists():
        raise ValueError('use new work and output directories; existing data is never overwritten')
    work.mkdir(parents=True)
    output.mkdir(parents=True)
    source_dir = output / 'source'
    source_dir.mkdir()
    for name in ('bench.py', 'core.py', 'policy.py'):
        shutil.copyfile(Path(__file__).parent / name, source_dir / name)
    save_json(output / 'manifest.json', {
        'complete': False, 'core_version_required': '31.1', 'binary_name': binary.name,
        'binary_sha256': file_sha256(binary), 'network': 'regtest',
        'authentic_shielded_verifier': False, 'payload': '610-byte visibly synthetic LABSB1',
        'profile': asdict(AnchorProfile()), 'wallet_depth': 6,
        'fee_rates_sat_vb': {'initial': 1, 'background': 10, 'retry': 20},
        'retry_step': 5, 'refresh_reserve_blocks': 2,
        'blockmaxweight': 10_000, 'blockreservedweight': 2_000,
        'background_transactions_per_block': 2,
        'source_sha256': {p.name: file_sha256(p) for p in source_dir.glob('*.py')},
        'paper_url': 'https://www.allocinit.xyz/uploads/shielded-bitcoin.pdf',
        'paper_sha256': '97d92987331f1365b88a4ec909701d7b1a74fa3ea7e07101bfc3e7243409ec18',
    })
    print('Creating a closed 200-block regtest baseline...', flush=True)
    base, info = baseline(binary, work)
    save_json(output / 'baseline.json', info)
    grid = [boundary_summary(AnchorProfile(), m, k) for k in (1, 6) for m in (1, 16, 100, 144)]
    save_json(output / 'anchor-grid.json', grid)
    results = []
    scenarios = SCENARIOS[2:3] if args.smoke else SCENARIOS
    spacings = (16,) if args.smoke else (1, 16)
    snapshots = {delay: offline_snapshot(binary, base, info, work, delay)
                 for delay in sorted({s['offline_blocks'] for s in scenarios})}
    for scenario in scenarios:
        for spacing in spacings:
            for policy in POLICIES:
                result = run_case(binary, snapshots[scenario['offline_blocks']], info,
                                  work, output, scenario, spacing, policy)
                results.append(result)
                print(f'{result["name"]}: H={result["inclusion_height"]}, '
                      f'age={result["final_anchor_age"]}, height_eligible={result["model_height_eligible"]}, '
                      f'fee={result["included_fee_sats"]} sat', flush=True)
    audit_results(results, output)
    controls = {'boundary': boundary_control(binary, base, info, work, output)}
    if not args.smoke:
        controls['relay'] = [relay_control(binary, base, info, work, output, limit)
                             for limit in (100_000, 83)]
    save_json(output / 'summary.json', {'results': results, 'controls': controls})
    manifest = json.loads((output / 'manifest.json').read_text())
    manifest.update({'complete': True, 'smoke_only': args.smoke, 'case_count': len(results),
                     'all_owned_nodes_stopped': True})
    save_json(output / 'manifest.json', manifest)
    print(f'Complete: {len(results)} cases; all owned nodes stopped.', flush=True)


if __name__ == '__main__':
    main()
