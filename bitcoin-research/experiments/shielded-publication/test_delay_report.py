"""Challenge the report with altered recorded observations, without Core."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from delay_report import render, validate, validate_case


RECORDED = Path(__file__).parent / 'results' / 'rebuild-delay-2026-09-25'


class DelayEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = json.loads((RECORDED / 'baseline.json').read_text(encoding='utf-8'))
        cls.cases = {}
        for name in ('longer_backlog-refresh-d3', 'longer_backlog-refresh-d4'):
            case = json.loads((RECORDED / name / 'case.json').read_text(encoding='utf-8'))
            trace = [json.loads(line) for line in (RECORDED / name / 'rpc.jsonl').read_text(
                encoding='utf-8').splitlines()]
            cls.cases[name] = (case, trace)

    def evidence(self, delay=3):
        return deepcopy(self.cases[f'longer_backlog-refresh-d{delay}'])

    def test_recorded_boundary_and_first_lost_case(self):
        success, success_trace = self.evidence(3)
        lost, lost_trace = self.evidence(4)
        self.assertEqual(validate_case(success, success_trace, self.baseline)['winner'], 'replacement')
        self.assertEqual(validate_case(lost, lost_trace, self.baseline)['winner'], 'original')
        self.assertEqual(success['result']['inclusion_height'], 296)
        self.assertEqual(lost['result']['inclusion_height'], 296)

    def test_wrong_winner_fee_age_or_eligibility_is_rejected(self):
        for key, value in (('winner', 'original'), ('included_fee_sats', 1),
                           ('final_anchor_age', 100), ('model_height_eligible', False),
                           ('authentic_shielded_acceptance', True), ('node_stopped', False)):
            with self.subTest(key=key):
                case, trace = self.evidence()
                case['result'][key] = value
                with self.assertRaises(ValueError):
                    validate_case(case, trace, self.baseline)

    def test_changed_block_without_raw_evidence_is_rejected(self):
        case, trace = self.evidence()
        case['blocks'][-1]['txids'].remove(case['result']['included_txid'])
        with self.assertRaisesRegex(ValueError, 'block differs'):
            validate_case(case, trace, self.baseline)

    def test_ready_candidate_cannot_claim_broadcast_before_it_is_ready(self):
        case, trace = self.evidence()
        case['candidates'][1]['broadcast_before_height'] -= 1
        with self.assertRaisesRegex(ValueError, 'broadcast did not occur at readiness'):
            validate_case(case, trace, self.baseline)

    def test_missing_candidate_admission_is_rejected(self):
        case, trace = self.evidence()
        raw = case['candidates'][1]['hex']
        trace = [item for item in trace if not (item['request']['method'] == 'testmempoolaccept'
                 and item['request']['params'][0][0] == raw)]
        with self.assertRaisesRegex(ValueError, 'admission evidence'):
            validate_case(case, trace, self.baseline)

    def test_other_rejections_cannot_be_reported_as_a_spent_input(self):
        case, trace = self.evidence(4)
        replacement = case['candidates'][1]
        replacement['admission']['reject-reason'] = 'datacarrier'
        case['result']['candidate_reject_reason'] = 'datacarrier'
        for item in trace:
            if (item['request']['method'] == 'testmempoolaccept'
                    and item['request']['params'][0][0] == replacement['hex']):
                item['response']['result'][0]['reject-reason'] = 'datacarrier'
        with self.assertRaisesRegex(ValueError, 'not explained by original confirmation'):
            validate_case(case, trace, self.baseline)

    def test_warmup_is_accepted_only_before_the_ready_chain_observation(self):
        case, trace = self.evidence()
        warmup = {'request': {'method': 'getblockchaininfo'},
                  'response': {'error': {'code': -28, 'message': 'Loading block index'}}}
        validate_case(case, [warmup] + trace, self.baseline)
        with self.assertRaisesRegex(ValueError, 'unexpected RPC error'):
            validate_case(case, trace + [warmup], self.baseline)

    def test_wrong_or_missing_observed_core_version_is_rejected(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                case, trace = self.evidence()
                if missing:
                    trace = [item for item in trace if item['request']['method'] != 'getnetworkinfo']
                else:
                    for item in trace:
                        if item['request']['method'] == 'getnetworkinfo':
                            item['response']['result']['version'] = 290000
                with self.assertRaisesRegex(ValueError, 'Core version'):
                    validate_case(case, trace, self.baseline)


class DelayReportTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(prefix='delay-report-test-')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name) / 'results'
        shutil.copytree(RECORDED, self.directory)

    def rewrite(self, name, change):
        path = self.directory / name
        value = json.loads(path.read_text(encoding='utf-8'))
        change(value)
        path.write_text(json.dumps(value), encoding='utf-8')

    def test_complete_evidence_reproduces_report_and_csv(self):
        self.assertEqual(len(validate(self.directory)), 16)
        render(self.directory)
        for name in ('REPORT.md', 'summary.csv', 'report-provenance.json'):
            self.assertEqual((self.directory / name).read_bytes(), (RECORDED / name).read_bytes())

    def test_missing_cell_and_incomplete_run_are_rejected(self):
        self.rewrite('summary.json', lambda summary: summary['results'].pop())
        with self.assertRaisesRegex(ValueError, 'missing or duplicate'):
            render(self.directory)
        self.rewrite('manifest.json', lambda manifest: manifest.update(complete=False))
        with self.assertRaisesRegex(ValueError, 'complete stopped'):
            render(self.directory)

    def test_changed_archived_source_is_rejected(self):
        with (self.directory / 'source' / 'rebuild_delay.py').open('a', encoding='utf-8') as stream:
            stream.write('\n# altered source\n')
        with self.assertRaisesRegex(ValueError, 'archived source mismatch'):
            render(self.directory)

    def test_contradictory_method_metadata_is_rejected(self):
        path = self.directory / 'manifest.json'
        original = json.loads(path.read_text(encoding='utf-8'))
        changes = {'core_version_required': '29.0', 'blockmaxweight': 4000000,
                   'blockreservedweight': 4000, 'event_order': 'mining before readiness',
                   'fee_rates_sat_vb': {'initial': 2, 'background': 3, 'retry': 4}}
        for key, value in changes.items():
            with self.subTest(key=key):
                path.write_text(json.dumps({**original, key: value}), encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'method parameters'):
                    render(self.directory)


if __name__ == '__main__':
    unittest.main()
