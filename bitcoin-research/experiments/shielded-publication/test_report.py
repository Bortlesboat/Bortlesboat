"""Report claims require their recorded controls, without running Bitcoin Core."""

import copy
import csv
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from report import POLICIES, SCENARIOS, render


ARCHIVED_SOURCE = b'# self-contained report fixture\n'
OUTPUTS = ('summary.csv', 'REPORT.md', 'report-provenance.json')


def fixture() -> tuple[dict, dict]:
    manifest = {
        'complete': True, 'smoke_only': False, 'all_owned_nodes_stopped': True,
        'authentic_shielded_verifier': False,
        'payload': '610-byte visibly synthetic LABSB1',
        'source_sha256': {'bench.py': hashlib.sha256(ARCHIVED_SOURCE).hexdigest()},
    }
    rows = []
    for scenario in SCENARIOS:
        for spacing in (1, 16):
            for policy in POLICIES:
                age = 101 if scenario['name'] == 'deadline_crossed' and spacing == 16 and policy != 'refresh_on_bump' else 15
                rows.append({
                    'name': f'{scenario["name"]}-m{spacing}-{policy}',
                    'scenario': dict(scenario), 'spacing': spacing, 'policy': policy,
                    'publication_height': 290, 'inclusion_height': 295,
                    'initial_anchor': 295 - age, 'final_anchor': 295 - age,
                    'final_anchor_age': age, 'model_height_eligible': age <= 100,
                    'included_fee_sats': 736 if policy == 'hold' else 14720,
                    'included_height_ineligible_fee_sats': 14720 if age > 100 else 0,
                    'attempt_count': 1, 'distinct_synthetic_payloads': 1,
                    'synthetic_marker_links': 0, 'vsize': 736,
                    'authentic_shielded_acceptance': None, 'node_stopped': True,
                })
    boundary = {
        'kind': 'forced-height control, not a fee-performance measurement',
        'node_stopped': True,
        'cases': [{
            'anchor_age': age, 'anchor_height': 201 - age, 'inclusion_height': 201,
            'model_height_eligible': age == 100, 'authentic_shielded_acceptance': None,
        } for age in (100, 101)],
    }
    relay = []
    for limit in (100000, 83):
        received = limit == 100000
        rejection = 'txn-already-in-mempool' if received else 'datacarrier'
        relay.append({
            'receiver_datacarriersize': limit, 'small_received': True,
            'barrier_received': True, 'large_received': received,
            'high_fee_large_received': received,
            'receiver_direct_check': {'allowed': False, 'reject-reason': rejection},
            'receiver_high_fee_check': {'allowed': False, 'reject-reason': rejection},
            'sender_admission': {'allowed': True},
            'sender_high_fee_admission': {'allowed': True},
            'authentic_shielded_acceptance': None, 'nodes_stopped': True,
        })
    return manifest, {'results': rows, 'controls': {'boundary': boundary, 'relay': relay}}


class ReportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest, self.summary = fixture()

    def write_fixture(self, directory: Path, summary: dict, manifest: dict) -> None:
        (directory / 'source').mkdir()
        (directory / 'source' / 'bench.py').write_bytes(ARCHIVED_SOURCE)
        (directory / 'summary.json').write_text(json.dumps(summary), encoding='utf-8')
        (directory / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')

    def assert_rejected(self, summary: dict, manifest: dict | None = None) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.write_fixture(directory, summary, self.manifest if manifest is None else manifest)
            with self.assertRaises(ValueError):
                render(directory)
            for name in OUTPUTS:
                self.assertFalse((directory / name).exists(), f'wrote {name} before validation')
            self.assertEqual(json.loads((directory / 'summary.json').read_text()), summary)

    def test_valid_evidence_renders_with_input_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            self.write_fixture(directory, self.summary, self.manifest)
            render(directory)
            report = (directory / 'REPORT.md').read_text(encoding='utf-8')
            self.assertIn('**Practical implication:**', report)
            self.assertIn('ages 100 and 101. Only the first passes', report)
            self.assertIn('| 100000 | True | True | True |', report)
            self.assertIn('| 83 | True | False | False |', report)
            self.assertIn('reports datacarrier rejection', report)
            with (directory / 'summary.csv').open(newline='', encoding='utf-8') as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), len(self.summary['results']))
            provenance = json.loads((directory / 'report-provenance.json').read_text())
            for name in ('summary', 'manifest'):
                self.assertEqual(provenance[f'input_{name}_sha256'],
                                 hashlib.sha256((directory / f'{name}.json').read_bytes()).hexdigest())
            self.assertEqual(json.loads((directory / 'summary.json').read_text()), self.summary)

    def test_changed_outcomes_remain_observed_and_condition_the_conclusion(self) -> None:
        changes = (
            (16, 'fee_only', 'model_height_eligible', True),
            (16, 'refresh_on_bump', 'model_height_eligible', False),
            (1, 'fee_only', 'model_height_eligible', False),
            (16, 'refresh_on_bump', 'included_fee_sats', 15000),
            (16, 'refresh_on_bump', 'inclusion_height', 296),
        )
        for spacing, policy, field, value in changes:
            with self.subTest(spacing=spacing, policy=policy, field=field):
                summary = copy.deepcopy(self.summary)
                row = next(row for row in summary['results'] if
                           (row['scenario']['name'], row['spacing'], row['policy']) ==
                           ('deadline_crossed', spacing, policy))
                row[field] = value
                with tempfile.TemporaryDirectory() as temporary:
                    directory = Path(temporary)
                    self.write_fixture(directory, summary, self.manifest)
                    render(directory)
                    report = (directory / 'REPORT.md').read_text(encoding='utf-8')
                    self.assertNotIn('**Practical implication:**', report)
                    self.assertIn('This run does not show the stated matched-fee, matched-height benefit', report)
                    self.assertIn(f'| deadline_crossed | {spacing} | {policy} | '
                                  f'{row["inclusion_height"]} | {row["final_anchor_age"]} | '
                                  f'{row["included_fee_sats"]} | '
                                  f'{"yes" if row["model_height_eligible"] else "no"} |', report)
                    self.assertEqual(json.loads((directory / 'summary.json').read_text()), summary)

    def test_missing_or_duplicate_boundary_controls_are_rejected(self) -> None:
        for cases in ([], self.summary['controls']['boundary']['cases'][:1],
                      [self.summary['controls']['boundary']['cases'][0]] * 2):
            with self.subTest(cases=cases):
                summary = copy.deepcopy(self.summary)
                summary['controls']['boundary']['cases'] = cases
                self.assert_rejected(summary)

    def test_changed_boundary_age_height_or_eligibility_is_rejected(self) -> None:
        for index in (0, 1):
            for field, value in (
                ('anchor_age', 99), ('anchor_height', 0), ('inclusion_height', 202),
                ('model_height_eligible', index == 1),
            ):
                with self.subTest(index=index, field=field):
                    summary = copy.deepcopy(self.summary)
                    summary['controls']['boundary']['cases'][index][field] = value
                    self.assert_rejected(summary)

    def test_missing_control_records_are_rejected(self) -> None:
        for key in ('boundary', 'relay'):
            with self.subTest(key=key):
                summary = copy.deepcopy(self.summary)
                del summary['controls'][key]
                self.assert_rejected(summary)

    def test_missing_duplicate_or_unexpected_receiver_limits_are_rejected(self) -> None:
        for limits in ([], [100000], [83], [100000, 100000], [100000, 84]):
            with self.subTest(limits=limits):
                summary = copy.deepcopy(self.summary)
                summary['controls']['relay'] = [dict(self.summary['controls']['relay'][0],
                                                   receiver_datacarriersize=limit) for limit in limits]
                self.assert_rejected(summary)

    def test_flipped_or_missing_relay_receipt_flags_are_rejected(self) -> None:
        for index in (0, 1):
            for field in ('small_received', 'barrier_received', 'large_received', 'high_fee_large_received'):
                for missing in (False, True):
                    with self.subTest(index=index, field=field, missing=missing):
                        summary = copy.deepcopy(self.summary)
                        relay = summary['controls']['relay'][index]
                        if missing:
                            del relay[field]
                        else:
                            relay[field] = not relay[field]
                        self.assert_rejected(summary)

    def test_direct_checks_require_the_observed_structural_rejection(self) -> None:
        for index in (0, 1):
            for field in ('receiver_direct_check', 'receiver_high_fee_check'):
                for check in ({}, {'allowed': True, 'reject-reason': 'datacarrier'},
                              {'allowed': False, 'reject-reason': 'min relay fee not met'}):
                    with self.subTest(index=index, field=field, check=check):
                        summary = copy.deepcopy(self.summary)
                        summary['controls']['relay'][index][field] = check
                        self.assert_rejected(summary)

    def test_sender_admission_controls_must_pass(self) -> None:
        for index in (0, 1):
            for field in ('sender_admission', 'sender_high_fee_admission'):
                with self.subTest(index=index, field=field):
                    summary = copy.deepcopy(self.summary)
                    summary['controls']['relay'][index][field]['allowed'] = False
                    self.assert_rejected(summary)

    def test_control_authentic_acceptance_must_be_explicitly_null(self) -> None:
        for group in ('boundary', 'relay'):
            for index in (0, 1):
                for value in (True, False, 'missing'):
                    with self.subTest(group=group, index=index, value=value):
                        summary = copy.deepcopy(self.summary)
                        records = (summary['controls']['boundary']['cases'] if group == 'boundary'
                                   else summary['controls']['relay'])
                        if value == 'missing':
                            del records[index]['authentic_shielded_acceptance']
                        else:
                            records[index]['authentic_shielded_acceptance'] = value
                        self.assert_rejected(summary)

    def test_stopped_node_evidence_is_required(self) -> None:
        summary = copy.deepcopy(self.summary)
        summary['controls']['boundary']['node_stopped'] = False
        self.assert_rejected(summary)
        for index in (0, 1):
            summary = copy.deepcopy(self.summary)
            summary['controls']['relay'][index]['nodes_stopped'] = False
            self.assert_rejected(summary)
        summary = copy.deepcopy(self.summary)
        summary['results'][0]['node_stopped'] = False
        self.assert_rejected(summary)
        manifest = dict(self.manifest, all_owned_nodes_stopped=False)
        self.assert_rejected(self.summary, manifest)

    def test_synthetic_manifest_labels_are_required(self) -> None:
        for field, value in (('authentic_shielded_verifier', True), ('payload', 'authentic transfer')):
            with self.subTest(field=field):
                self.assert_rejected(self.summary, dict(self.manifest, **{field: value}))

    def test_existing_completeness_authenticity_and_source_guards_remain(self) -> None:
        self.assert_rejected(self.summary, dict(self.manifest, complete=False))
        self.assert_rejected(self.summary, dict(self.manifest, smoke_only=True))
        summary = copy.deepcopy(self.summary)
        summary['results'].pop()
        self.assert_rejected(summary)
        summary = copy.deepcopy(self.summary)
        summary['results'][0]['authentic_shielded_acceptance'] = True
        self.assert_rejected(summary)
        self.assert_rejected(self.summary, dict(self.manifest, source_sha256={'bench.py': '0' * 64}))


if __name__ == '__main__':
    unittest.main()
