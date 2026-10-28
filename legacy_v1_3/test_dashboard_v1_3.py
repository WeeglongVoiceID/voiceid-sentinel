"""Offline tests for standalone VoiceID Sentinel dashboard v1.3."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import dashboard_v1_3 as app

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'example_v1_2_dossier.json'
AUDIT = ROOT / 'example_v1_2_audit.json'

class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = app.load(DATA)
        cls.audit = app.load(AUDIT)

    def case(self):
        return copy.deepcopy(self.base), copy.deepcopy(self.audit)

    def resign(self, d, a):
        a['dossier_canonical_sha256'] = app.sha(d)

    def rejects(self, d, a):
        with self.assertRaises(app.DashboardError):
            app.verify(d, a)

    def test_01_verified_sample(self):
        d, a = self.case()
        ev, queue, shared = app.verify(d, a)
        self.assertEqual((len(ev), len(queue), len(shared)), (3, 3, 0))

    def test_02_render_title(self):
        d, a = self.case()
        self.assertIn('Investigation Command Center', app.build(d, a))

    def test_03_source_event_preserved(self):
        d, a = self.case()
        page=app.build(d, a)
        for name in ('EVENT-DEMO-A', 'EVENT-DEMO-B', 'EVENT-DEMO-C'):
            self.assertIn(name, page)

    def test_04_count_replay(self):
        d, a = self.case()
        page=app.build(d, a)
        self.assertIn('Replay flags for review', page)
        self.assertIn('<div class="val">1</div><div class="lab">Replay flags', page)

    def test_05_detect_tampering(self):
        d, a = self.case()
        d['event_facts'][0]['verification_result']='passed'
        self.rejects(d, a)

    def test_06_reject_case_mismatch(self):
        d, a = self.case()
        a['case_id']='other'
        self.rejects(d, a)

    def test_07_reject_real_data_classification(self):
        d, a = self.case()
        d['data_classification']='restricted_real'
        self.resign(d, a)
        self.rejects(d, a)

    def test_08_rejects_automated_adverse_action(self):
        d, a = self.case()
        d['automatic_adverse_action_allowed']=True
        self.resign(d, a)
        self.rejects(d, a)

    def test_09_duplicate_event_ids(self):
        d, a = self.case()
        d['event_facts'][1]['event_id']=d['event_facts'][0]['event_id']
        self.resign(d, a)
        self.rejects(d, a)

    def test_10_queue_unknown_event(self):
        d, a = self.case()
        d['investigation_queue'][0]['event_ids']=['PHANTOM']
        self.resign(d, a)
        self.rejects(d, a)

    def test_11_queue_unsupported_evidence_reference(self):
        d, a = self.case()
        d['investigation_queue'][0]['evidence_refs']=['EVENT-DEMO-A.nonexistent']
        self.resign(d, a)
        self.rejects(d, a)

    def test_12_audit_count_mismatch(self):
        d, a = self.case()
        a['queue_count']=101
        self.rejects(d, a)

    def test_13_ai_presence_mismatch(self):
        d, a = self.case()
        a['ai_advisory_present']=True
        self.rejects(d, a)

    def test_14_escaping_markup(self):
        d, a = self.case()
        d['investigation_queue'][0]['title']='<script>alert(1)</script>'
        self.resign(d, a)
        page=app.build(d, a)
        self.assertNotIn('<script>', page)
        self.assertIn('&lt;script&gt;', page)

    def test_15_identifier_value_not_rendered(self):
        d, a = self.case()
        d['event_facts'][0]['available_identifiers']['device_id']='SECRET_DEVICE_IDENTIFIER'
        self.resign(d, a)
        self.assertNotIn('SECRET_DEVICE_IDENTIFIER', app.build(d, a))

    def test_16_model_prose_not_rendered(self):
        d, a = self.case()
        d['ai_advisory']={'untrusted': '<script>ALERT</script>'}
        a['ai_advisory_present']=True
        self.resign(d, a)
        self.assertNotIn('ALERT', app.build(d, a))

    def test_17_no_scripts_or_network(self):
        d, a = self.case()
        page=app.build(d, a)
        self.assertNotIn('<script', page)
        self.assertNotIn('http://', page)
        self.assertNotIn('https://', page)
        self.assertIn("default-src 'none'", page)

    def test_18_invalid_priority(self):
        d, a = self.case()
        d['investigation_queue'][0]['review_priority']=0
        self.resign(d, a)
        self.rejects(d, a)

    def test_19_rejects_extra_event_fields(self):
        d, a = self.case()
        d['event_facts'][0]['audio']='forbidden'
        self.resign(d, a)
        self.rejects(d, a)

    def test_20_rejects_unapproved_identifier_type(self):
        d, a = self.case()
        d['event_facts'][0]['available_identifiers']['raw_voice_embedding']='no'
        self.resign(d, a)
        self.rejects(d, a)

    def test_21_rejects_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x.json'
            p.write_text('{"case_id": "X", "case_id": "Y"}', encoding='utf-8')
            with self.assertRaises(app.DashboardError):
                app.load(p)

    def test_22_generation_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'dashboard.html'
            code=app.main(['--dossier',str(DATA),'--audit',str(AUDIT),'--output',str(target)])
            self.assertEqual(code,0)
            self.assertIn('VOICEID SENTINEL', target.read_text(encoding='utf-8').upper())

    def test_23_wrong_policy(self):
        d,a=self.case()
        a['policy_version']='unauthorized'
        self.rejects(d,a)

    def test_24_unsafe_replay_type(self):
        d,a=self.case()
        d['event_facts'][0]['replay_flag']='true'
        self.resign(d,a)
        self.rejects(d,a)

    def test_25_queue_display_order(self):
        d,a=self.case()
        page=app.build(d,a)
        self.assertLess(page.find('Priority 2'),page.find('Priority 3'))
        self.assertLess(page.find('Priority 3'),page.find('Priority 5'))

if __name__ == '__main__':
    unittest.main(verbosity=2)
