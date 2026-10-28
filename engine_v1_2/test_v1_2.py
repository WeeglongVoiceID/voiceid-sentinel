#!/usr/bin/env python3
"""Offline regression tests for v1.2, including fail-closed API-output validation.
No network, Meta credits, production resources, keys, or third-party dependencies.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sentinel_v1_2 as s

ROOT = Path(__file__).parent
CASE = json.loads((ROOT / 'sample_multi_event_case.json').read_text(encoding='utf-8'))


def model_report(case=None):
    case = case or CASE
    ids = [e['event_id'] for e in case['events']]
    return {
        'schema_version': '1.1', 'case_id': case['case_id'],
        'case_summary': 'Events are independent observations; linkage not established.',
        'timeline': [{'event_id': e['event_id'], 'timestamp': e['timestamp'],
                      'summary': 'Observed ' + e['verification_result']} for e in case['events']],
        'observed_patterns': [{'pattern': 'Two failures and one pass are shown without actor linkage.',
                               'event_ids': ids, 'evidence_refs': [f'{eid}.verification_result' for eid in ids]}],
        'relationship_assessments': [{'event_ids': ids, 'relationship_status': 'unknown',
                                      'basis': 'Identifiers are absent or null.',
                                      'evidence_refs': [f'{eid}.available_identifiers.device_id' for eid in ids],
                                      'caveat': 'No link can be established.'}],
        'hypotheses': [{'hypothesis': 'Replay flag warrants investigation, not fraud inference.',
                        'confidence': 'low', 'supporting_evidence': 'Flag is true in first source event.',
                        'contrary_or_missing_evidence': 'Detector traces are missing.',
                        'evidence_refs': [f'{ids[0]}.replay_flag']}],
        'investigation_queue': [{'review_priority': 3, 'title': 'Model review suggestion',
                                 'event_ids': [ids[0]], 'rationale': 'Review the flag.',
                                 'evidence_to_collect': ['Detector traces'],
                                 'safe_action': 'Ask human investigator to review.'}],
        'missing_evidence': ['Detector traces'],
        'recommended_next_steps': ['Human review'],
        'safeguards': ['No automatic adverse action'],
        'limitations': ['Synthetic inputs only'],
    }


class TestInputContract(unittest.TestCase):
    def setUp(self):
        self.c = copy.deepcopy(CASE)

    def fails(self):
        with self.assertRaises(s.ValidationError):
            s.validate_case(self.c)

    def test_01_baseline_valid(self):
        self.assertEqual(self.c, s.validate_case(self.c))

    def test_02_not_real_records(self):
        self.c['data_classification'] = 'production_customer_data'
        self.fails()

    def test_03_extra_case_field_rejected(self):
        self.c['api_token'] = 'test'
        self.fails()

    def test_04_audio_field_rejected(self):
        self.c['events'][0]['audio_base64'] = 'anything'
        self.fails()

    def test_05_template_field_rejected(self):
        self.c['events'][0]['voice_embedding'] = []
        self.fails()

    def test_06_unknown_identifier_field_rejected(self):
        self.c['events'][0]['available_identifiers']['email'] = 'n@example.test'
        self.fails()

    def test_07_duplicate_event_ids_rejected(self):
        self.c['events'][1]['event_id'] = 'EVENT-DEMO-A'
        self.fails()

    def test_08_empty_events_rejected(self):
        self.c['events'] = []
        self.fails()

    def test_09_excess_events_rejected(self):
        self.c['events'] = [dict(self.c['events'][0], event_id='TEST_' + str(i)) for i in range(101)]
        self.fails()

    def test_10_invalid_timestamp_rejected(self):
        self.c['events'][0]['timestamp'] = '2026-14-77'
        self.fails()

    def test_11_naive_timestamp_rejected(self):
        self.c['events'][0]['timestamp'] = '2026-10-20T09:14:00'
        self.fails()

    def test_12_false_replay_string_rejected(self):
        self.c['events'][0]['replay_flag'] = 'false'
        self.fails()

    def test_13_null_replay_supported(self):
        self.c['events'][0]['replay_flag'] = None
        self.assertIsNotNone(s.validate_case(self.c))

    def test_14_invalid_verification_value_rejected(self):
        self.c['events'][0]['verification_result'] = 'fraud'
        self.fails()

    def test_15_unknown_liveness_value_rejected(self):
        self.c['events'][0]['liveness_result'] = 'suspicious'
        self.fails()

    def test_16_blank_identifier_rejected(self):
        self.c['events'][0]['available_identifiers']['device_id'] = '   '
        self.fails()

    def test_17_missing_constraints_rejected(self):
        self.c['explicit_constraints'] = []
        self.fails()

    def test_18_invalid_event_id_rejected(self):
        self.c['events'][0]['event_id'] = 'EXAMPLE.A'
        self.fails()

    def test_19_reject_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'bad.json'
            p.write_text('{"case_id":"A","case_id":"B"}', encoding='utf-8')
            with self.assertRaises(s.ValidationError):
                s.load_case(p)

    def test_20_reject_oversized_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'huge.json'
            p.write_bytes(b' ' * (s.MAX_INPUT_BYTES + 1))
            with self.assertRaises(s.ValidationError):
                s.load_case(p)


class TestDeterministicFindings(unittest.TestCase):
    def setUp(self):
        self.c = copy.deepcopy(CASE)

    def test_21_order_source_facts(self):
        self.c['events'].reverse()
        result = s.normalized_event_facts(self.c)
        self.assertEqual(['EVENT-DEMO-A', 'EVENT-DEMO-B', 'EVENT-DEMO-C'], [x['event_id'] for x in result])

    def test_22_source_outcomes_preserved(self):
        result = s.normalized_event_facts(self.c)
        self.assertEqual(['failed', 'failed', 'passed'], [x['verification_result'] for x in result])

    def test_23_flags_not_fraud_conclusion(self):
        dossier = s.assemble_dossier(self.c, 'offline')
        self.assertEqual([True, False, False], [x['replay_flag'] for x in dossier['event_facts']])
        self.assertNotIn('fraud_proven', dossier)
        self.assertFalse(dossier['automatic_adverse_action_allowed'])

    def test_24_no_shared_identifier_has_no_linkage(self):
        self.assertEqual([], s.identifier_relationships(self.c))

    def test_25_matching_identifier_detected(self):
        for e in self.c['events'][:2]:
            e['available_identifiers']['device_id'] = 'SYNTHETIC_DEVICE_001'
        x = s.identifier_relationships(self.c)
        self.assertEqual(1, len(x))
        self.assertEqual('shared_identifier_observed', x[0]['status'])
        self.assertNotIn('SYNTHETIC_DEVICE_001', json.dumps(x))
        self.assertEqual(2, len(x[0]['evidence_refs']))

    def test_26_mismatched_tokens_not_linked(self):
        self.c['events'][0]['available_identifiers']['device_id'] = 'AA'
        self.c['events'][1]['available_identifiers']['device_id'] = 'BB'
        self.assertEqual([], s.identifier_relationships(self.c))

    def test_27_different_identifier_types_not_linked(self):
        self.c['events'][0]['available_identifiers']['device_id'] = 'SAME'
        self.c['events'][1]['available_identifiers']['session_id'] = 'SAME'
        self.assertEqual([], s.identifier_relationships(self.c))

    def test_28_priority_is_deterministic(self):
        one = s.determine_queue(self.c, [])
        two = s.determine_queue(self.c, [])
        self.assertEqual(one, two)
        self.assertEqual([2, 3, 5], [x['review_priority'] for x in one])

    def test_29_priority_policy_ignores_model(self):
        a = s.assemble_dossier(self.c, 'offline')
        self.assertIsNone(a['ai_advisory'])
        self.assertEqual(3, len(a['investigation_queue']))
        self.assertTrue(all('human' in x['safe_action'].lower() or 'manual' in x['safe_action'].lower()
                            for x in a['investigation_queue']))

    def test_30_shared_identifier_adds_review_item(self):
        self.c['events'][0]['available_identifiers']['session_id'] = 'DEMO_SHARED'
        self.c['events'][2]['available_identifiers']['session_id'] = 'DEMO_SHARED'
        d = s.assemble_dossier(self.c, 'offline')
        self.assertEqual(4, len(d['investigation_queue']))
        self.assertTrue(d['human_review_required'])

    def test_31_hash_repeatable(self):
        self.assertEqual(s.sha256(s.canonical_bytes(self.c)), s.sha256(s.canonical_bytes(copy.deepcopy(self.c))))

    def test_32_changed_input_changes_hash(self):
        before = s.sha256(s.canonical_bytes(self.c))
        self.c['events'][0]['verification_result'] = 'passed'
        self.assertNotEqual(before, s.sha256(s.canonical_bytes(self.c)))

    def test_33_audit_corresponds_to_dossier(self):
        d = s.assemble_dossier(self.c, 'offline')
        audit = s.make_audit(self.c, d, b'filea', b'fileb')
        self.assertEqual(audit['input_canonical_sha256'], hashlib.sha256(s.canonical_bytes(self.c)).hexdigest())
        self.assertEqual(audit['dossier_canonical_sha256'], s.sha256(s.canonical_bytes(d)))
        self.assertNotIn('SYNTHETIC_DEVICE_001', json.dumps(audit))

    def test_34_markdown_limits_adverse_action(self):
        d = s.assemble_dossier(self.c, 'offline')
        audit = s.make_audit(self.c, d, b'a', b'b')
        md = s.markdown(d, audit)
        self.assertIn('no automatic adverse action', md.lower())
        self.assertIn('not requested', md.lower())


class TestModelBoundary(unittest.TestCase):
    def setUp(self):
        self.c = copy.deepcopy(CASE)
        self.r = model_report(self.c)

    def rejects(self):
        with self.assertRaises(s.ValidationError):
            s.validate_legacy_advisory(self.r, self.c)

    def test_35_valid_advisory_passes(self):
        self.assertIsNone(s.validate_legacy_advisory(self.r, self.c))

    def test_36_changed_timestamp_rejected(self):
        self.r['timeline'][0]['timestamp'] = '2026-10-20T11:11:00Z'
        self.rejects()

    def test_37_missing_timeline_event_rejected(self):
        self.r['timeline'].pop()
        self.rejects()

    def test_38_duplicate_timeline_event_rejected(self):
        self.r['timeline'].append(copy.deepcopy(self.r['timeline'][0]))
        self.rejects()

    def test_39_unknown_event_evidence_rejected(self):
        self.r['hypotheses'][0]['evidence_refs'] = ['NON_EXISTENT.replay_flag']
        self.rejects()

    def test_40_missing_pattern_refs_rejected(self):
        self.r['observed_patterns'][0]['evidence_refs'] = []
        self.rejects()

    def test_41_refs_outside_declared_events_rejected(self):
        self.r['observed_patterns'][0]['event_ids'] = ['EVENT-DEMO-A']
        self.rejects()

    def test_42_confirmed_linkage_without_shared_values_rejected(self):
        self.r['relationship_assessments'][0]['relationship_status'] = 'confirmed_by_supplied_evidence'
        self.rejects()

    def test_43_model_claims_confirmed_fraud_rejected(self):
        self.r['hypotheses'][0]['hypothesis'] = 'Confirmed fraud was perpetrated.'
        self.rejects()

    def test_44_model_claims_same_actor_proven_rejected(self):
        self.r['relationship_assessments'][0]['basis'] = 'Same actor is proven by timing.'
        self.rejects()

    def test_45_automatic_block_advice_rejected(self):
        self.r['investigation_queue'][0]['safe_action'] = 'Automatically block the account.'
        self.rejects()

    def test_46_advisory_queue_not_used_for_priority(self):
        self.r['investigation_queue'][0]['review_priority'] = 1
        d = s.assemble_dossier(self.c, 'api', self.r, {'model': 'fixture', 'api_status': 'completed'})
        self.assertEqual([2, 3, 5], [x['review_priority'] for x in d['investigation_queue']])
        self.assertTrue(d['ai_advisory']['warning'])

    def test_47_offline_rejects_ai_advisory(self):
        with self.assertRaises(s.ValidationError):
            s.assemble_dossier(self.c, 'offline', self.r)

    def test_48_api_requires_advisory(self):
        with self.assertRaises(s.ValidationError):
            s.assemble_dossier(self.c, 'api')

    def test_49_api_mode_mock_no_network(self):
        # Entire CLI API path exercised with stubbed source, no external traffic.
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'MODEL_API_KEY': 'SYNTHETIC_TEST_KEY'}):
            paths = [str(Path(tmp) / f) for f in ['output.json', 'report.md', 'audit.json', 'raw.json']]
            case_path = Path(tmp) / 'case.json'
            case_path.write_text(json.dumps(self.c), encoding='utf-8')
            raw = {'status': 'completed', 'model': 'synthetic-model', 'output_text': json.dumps(self.r)}
            fake_meta = {'api_status': 'completed', 'model': 'synthetic-model', 'http_status': 200}
            with patch.object(s.legacy, 'api_request', return_value=(raw, fake_meta)) as mock_api:
                result = s.main([str(case_path), '--mode', 'api', '--save-json', paths[0],
                                 '--save-report', paths[1], '--save-audit', paths[2], '--save-raw', paths[3]])
            self.assertEqual(0, result)
            mock_api.assert_called_once()
            self.assertTrue(all(Path(p).is_file() for p in paths))
            final = json.loads(Path(paths[0]).read_text(encoding='utf-8'))
            self.assertEqual('api', final['generation_mode'])
            self.assertEqual([2, 3, 5], [x['review_priority'] for x in final['investigation_queue']])

    def test_50_api_fail_closed_no_validated_files(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'MODEL_API_KEY': 'SYNTHETIC_TEST_KEY'}):
            paths = [str(Path(tmp) / f) for f in ['output.json', 'report.md', 'audit.json', 'raw.json']]
            case_path = Path(tmp) / 'case.json'
            case_path.write_text(json.dumps(self.c), encoding='utf-8')
            self.r['timeline'][0]['timestamp'] = '2026-10-20T23:59:59Z'
            raw = {'status': 'completed', 'model': 'synthetic-model', 'output_text': json.dumps(self.r)}
            with patch.object(s.legacy, 'api_request', return_value=(raw, {'api_status': 'completed'})):
                from contextlib import redirect_stderr
                from io import StringIO
                with redirect_stderr(StringIO()):
                    result = s.main([str(case_path), '--mode', 'api', '--save-json', paths[0],
                                     '--save-report', paths[1], '--save-audit', paths[2], '--save-raw', paths[3]])
            self.assertNotEqual(0, result)
            self.assertTrue(Path(paths[3]).exists())
            self.assertFalse(any(Path(p).exists() for p in paths[:3]))

    def test_51_case_summary_confirmed_fraud_rejected(self):
        self.r['case_summary'] = 'The events prove confirmed fraud.'
        self.rejects()

    def test_52_model_next_steps_auto_block_rejected(self):
        self.r['recommended_next_steps'] = ['Immediately freeze the account.']
        self.rejects()

    def test_53_cli_offline_no_key_and_no_api(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {'MODEL_API_KEY': ''}):
            paths = [str(Path(tmp) / f) for f in ['output.json', 'report.md', 'audit.json']]
            case_path = Path(tmp) / 'case.json'
            case_path.write_text(json.dumps(self.c), encoding='utf-8')
            with patch.object(s.legacy, 'api_request', side_effect=AssertionError('API should never run')):
                result = s.main([str(case_path), '--save-json', paths[0], '--save-report', paths[1], '--save-audit', paths[2]])
            self.assertEqual(0, result)
            self.assertTrue(all(Path(p).is_file() for p in paths))
            saved = json.loads(Path(paths[0]).read_text(encoding='utf-8'))
            self.assertEqual('offline', saved['generation_mode'])


if __name__ == '__main__':
    unittest.main(testRunner=unittest.TextTestRunner(stream=sys.stdout, verbosity=2))
