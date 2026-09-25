"""Negative controls for the paired-workload audit, without Bitcoin Core."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bench import audit_results


class ComparisonAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix='publication-audit-test-')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.rows = []
        for policy in ('hold', 'fee_only', 'refresh_on_bump'):
            row = {
                'name': policy, 'policy': policy, 'scenario': {'name': 'fixture'},
                'spacing': 16, 'op_return_script_bytes': 614, 'node_stopped': True,
                'authentic_shielded_acceptance': None,
                'baseline_hash': 'shared-fixture-baseline',
                'publication_chain_hash': 'shared-fixture-publication',
            }
            self.rows.append(row)
            (self.directory / policy).mkdir()
            self.write_background(policy, [{'txid': 'shared-synthetic-fixture'}])

    def write_background(self, policy, transactions):
        (self.directory / policy / 'transactions.json').write_text(
            json.dumps({'background': transactions}), encoding='utf-8',
        )

    def test_matching_prefixes_allow_later_work_after_another_policy_finishes(self):
        self.write_background('hold', [
            {'txid': 'shared-synthetic-fixture'}, {'txid': 'later-synthetic-fixture'},
        ])
        audit_results(self.rows, self.directory)

    def test_changed_background_prefix_is_rejected(self):
        self.write_background('fee_only', [{'txid': 'different-synthetic-fixture'}])
        with self.assertRaisesRegex(RuntimeError, 'different background transaction prefixes'):
            audit_results(self.rows, self.directory)

    def test_missing_policy_in_a_comparison_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'incomplete policy comparison group'):
            audit_results(self.rows[:2], self.directory)

    def test_different_publication_snapshot_is_rejected(self):
        self.rows[1]['publication_chain_hash'] = 'different-fixture-publication'
        with self.assertRaisesRegex(RuntimeError, 'same closed snapshot'):
            audit_results(self.rows, self.directory)


if __name__ == '__main__':
    unittest.main()
