#!/usr/bin/env python3
"""VoiceID Sentinel v1.5 offline regression: no live model or production calls."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch

import workbench_v1_4 as w
import report_v1_5 as report

ROOT = Path(__file__).resolve().parent
JS = (ROOT / 'assets' / 'app.js').read_text(encoding='utf-8')
CSS = (ROOT / 'assets' / 'app.css').read_text(encoding='utf-8')
HTML = (ROOT / 'index.html').read_text(encoding='utf-8')
CASE = w.BUILTIN_CASE


class TestExecutive(unittest.TestCase):
    def test_01_case_count(self): self.assertIn('3 synthetic authentication events', w.build_payload(CASE, 'offline')['executive_summary'])
    def test_02_durations(self): self.assertIn('within 12 minutes', w.build_payload(CASE, 'offline')['executive_summary'])
    def test_03_source_outcomes(self): self.assertIn('2 failed verifications, 1 passed verification',w.build_payload(CASE,'offline')['executive_summary'])
    def test_04_replay(self): self.assertIn('1 replay detector flag', w.build_payload(CASE,'offline')['executive_summary'])
    def test_05_no_unproved_identity(self): self.assertIn('has not been established',w.build_payload(CASE,'offline')['executive_summary'])
    def test_06_no_automatic_action(self): self.assertIn('no basis',w.build_payload(CASE,'offline')['executive_summary'].lower())
    def test_07_matching_identifiers_still_not_actor(self):
        case=copy.deepcopy(CASE)
        for e in case['events'][:2]: e['available_identifiers']['device_id']='SYNTHETIC-MATCH-ALPHA'
        r=w.build_payload(case,'offline')
        self.assertIn('Matching non-empty opaque identifier',r['executive_summary'])
        self.assertIn('do not establish who controlled',r['executive_summary'])
    def test_08_one_event_grammatically_correct(self):
        case=copy.deepcopy(CASE);case['events']=case['events'][:1]
        x=w.build_payload(case,'offline')['executive_summary']
        self.assertIn('1 synthetic authentication event on one reported channel',x)
        self.assertNotIn(' within ',x)
    def test_09_hashes_identical_to_original_engine(self):
        r=w.build_payload(CASE,'offline')
        original=w.engine.assemble_dossier(CASE,'offline')
        self.assertEqual(r['dossier'], original)
        self.assertEqual(r['audit']['dossier_canonical_sha256'],w.engine.sha256(w.engine.canonical_bytes(original)))
    def test_10_report_not_in_dossier(self):
        r=w.build_payload(CASE,'offline')
        self.assertNotIn('report_markdown',r['dossier'])
        self.assertNotIn('executive_summary',r['dossier'])
    def test_11_source_identifiers_not_exposed_in_executive(self):
        case=copy.deepcopy(CASE)
        for e in case['events'][:2]:e['available_identifiers']['session_id']='PRIVATE-DEMO-TOKEN-ABC'
        self.assertNotIn('PRIVATE-DEMO-TOKEN-ABC',w.build_payload(case,'offline')['executive_summary'])


class TestPrivacy(unittest.TestCase):
    def test_12_has_approved_guidance(self):self.assertGreaterEqual(len(report.privacy_steps()),4)
    def test_13_no_raw_voice_collection_instruction(self):
        self.assertIn('Do not collect raw voice recordings', ' '.join(report.privacy_steps()))
    def test_14_human_review_required(self):self.assertIn('human investigator',' '.join(report.privacy_steps()))
    def test_15_steps_same_for_model_and_offline(self):
        with patch.object(w.legacy,'api_request',return_value=({'output_text':json.dumps(w.make_fixture(CASE))}, {'api_status':'completed','model':'muse-spark-1.3'})):
            self.assertEqual(w.build_payload(CASE,'offline')['privacy_review_steps'],w.build_payload(CASE,'meta',api_key='test-only')['privacy_review_steps'])
    def test_16_mocked_meta_does_not_change_review_queue(self):
        with patch.object(w.legacy,'api_request',return_value=({'output_text':json.dumps(w.make_fixture(CASE))}, {'api_status':'completed','model':'muse-spark-1.3'})):
            self.assertEqual(w.build_payload(CASE,'offline')['dossier']['investigation_queue'],w.build_payload(CASE,'meta',api_key='test-only')['dossier']['investigation_queue'])
    def test_17_model_sensitive_request_not_approved_in_report(self):
        advisory=w.make_fixture(CASE)
        advisory['missing_evidence']=['Raw voice recordings and biometric templates']
        advisory['recommended_next_steps']=['Collect raw biometric templates now']
        x=report.report_markdown(w.engine.assemble_dossier(CASE,'offline'),w.build_payload(CASE,'offline')['audit'],advisory,'illustrative_fixture')
        self.assertNotIn('Collect raw biometric templates now',x)
        self.assertIn('deliberately not reproduced',x)
        self.assertIn('Do not collect raw voice recordings',x)
    def test_18_invalidation_of_raw_meta_remains_engine_job(self):
        case=copy.deepcopy(CASE);case['data_classification']='production_data'
        with self.assertRaises(w.engine.ValidationError):w.build_payload(case,'offline')


class TestExport(unittest.TestCase):
    def test_19_report_version(self):self.assertEqual(w.build_payload(CASE,'offline')['report_version'],'sentinel-report-1.5.0')
    def test_20_hash_of_report(self):
        x=w.build_payload(CASE,'offline')
        self.assertEqual(x['report_markdown_sha256'],hashlib.sha256(x['report_markdown'].encode('utf-8')).hexdigest())
    def test_21_no_false_attestation(self):self.assertIn('not a digital signature',w.build_payload(CASE,'offline')['report_markdown'])
    def test_22_no_model_in_offline(self):self.assertIn('no AI advisory requested',w.build_payload(CASE,'offline')['report_markdown'])
    def test_23_preview_marked_illustrative(self):
        self.assertIn('NOT Meta AI',w.build_payload(CASE,'preview')['report_markdown'])
    def test_24_export_contains_evidence_refs(self):
        self.assertIn('EVENT-DEMO-A.replay_flag', w.build_payload(CASE,'offline')['report_markdown'])
    def test_25_report_markdown_escape_html(self):self.assertIn('\\<script\\>',report.md_text('<script>'))
    def test_26_case_specific_export_generated(self):
        case=copy.deepcopy(CASE);case['case_id']='TEST-CASE-042'
        self.assertIn('TEST-CASE-042',w.build_payload(case,'offline')['report_markdown'])
    def test_27_meta_structural_validation_still_applies(self):
        a=w.make_fixture(CASE);a['case_summary']='Confirmed fraud proven.'
        with patch.object(w.legacy,'api_request',return_value=({'output_text':json.dumps(a)}, {'api_status':'completed'})):
            with self.assertRaises(w.engine.ValidationError):w.build_payload(CASE,'meta',api_key='test-only')
    def test_28_meta_export_labeled_not_certified(self):
        with patch.object(w.legacy,'api_request',return_value=({'output_text':json.dumps(w.make_fixture(CASE))}, {'api_status':'completed','model':'muse-spark-1.3'})):
            md=w.build_payload(CASE,'meta',api_key='test-only')['report_markdown']
            self.assertIn('LIVE META API',md)
            self.assertIn('not the factual truth of every model claim',md)
    def test_29_source_data_not_written_to_disk_by_build(self):
        # Build is pure; report is returned for browser download, not persisted on server.
        self.assertEqual(w.build_payload(CASE,'offline')['dossier']['case_id'],CASE['case_id'])
        self.assertIn('saveDownload',JS)
    def test_30_bad_origin_rejected(self):
        x=w.build_payload(CASE,'offline')
        with self.assertRaises(KeyError):report.report_markdown(x['dossier'],x['audit'],None,'fake')


class TestInterface(unittest.TestCase):
    def test_31_executive_panel_present(self):self.assertIn('id="executive-panel"',HTML)
    def test_32_executive_summary_binding(self):self.assertIn("text('executive-summary',response.executive_summary)",JS)
    def test_33_clickable_evidence_links(self):self.assertIn("link.dataset.evidenceRef = ref",JS)
    def test_34_separator_not_concatenated(self):self.assertIn("document.createTextNode(' · ')",JS)
    def test_35_source_detail_auto_opens(self):self.assertIn('details.open=true',JS)
    def test_36_highlight(self):self.assertIn('source-highlight',CSS)
    def test_37_no_identifier_value_display(self):self.assertIn('Opaque identifier values are deliberately not displayed',JS)
    def test_38_privacy_plan_binding(self):self.assertIn('response.privacy_review_steps',JS)
    def test_39_original_model_recommendations_collapsed(self):self.assertIn('id="model-gaps"',HTML)
    def test_40_model_recommendations_not_in_print(self):self.assertIn('.model-gaps{display:none!important}',CSS)
    def test_41_report_button(self):self.assertIn('id="export-report"',HTML)
    def test_42_print_button(self):self.assertIn('id="print-report"',HTML)
    def test_43_js_report_download(self):self.assertIn("download('report')",JS)
    def test_44_js_print(self):self.assertIn('window.print()',JS)
    def test_45_model_integrity_banner_maintained(self):self.assertIn('LIVE META API RESPONSE. Structural and reference validation passed',JS)
    def test_46_retain_old_navigation(self):self.assertIn("if (mode==='preview' || mode==='meta') navigateToAdvisory()",JS)
    def test_47_retain_large_text_control(self):self.assertIn('type-extra-large',JS)
    def test_48_no_insecure_inline_html(self):self.assertNotIn('.innerHTML',JS)
    def test_49_no_external_scripts(self):
        self.assertNotIn('src="https:',HTML)
        self.assertNotIn('href="https:',HTML)
    def test_50_release_tag(self):self.assertIn('v1.6</strong>',HTML)

if __name__=='__main__':unittest.main(verbosity=2)
