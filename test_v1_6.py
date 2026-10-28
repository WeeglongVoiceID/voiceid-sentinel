#!/usr/bin/env python3
"""v1.6 assurance, scenario and export verification regression tests. Offline only."""
from __future__ import annotations
import copy
import json
import http.client
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import workbench_v1_4 as base
import workbench_v1_6 as v16
import showcase_v1_6 as gallery
import assurance_v1_6 as a

ROOT=Path(__file__).resolve().parent

class TestScenarioGallery(unittest.TestCase):
    def test_01_three_cases(self):self.assertEqual(len(gallery.CASES),3)
    def test_02_gallery_is_valid(self):
        for c in gallery.CASES.values():base.engine.validate_case(c)
    def test_03_base_unchanged(self):self.assertEqual(gallery.CASES['unlinked-sequence'],base.BUILTIN_CASE)
    def test_04_distinct_case_ids(self):self.assertEqual(len({v['case_id'] for v in gallery.CASES.values()}),3)
    def test_05_shared_one_signal(self):
        p=base.build_payload(gallery.CASES['shared-token'],'offline')
        self.assertEqual(len(p['dossier']['shared_identifiers']),1)
        self.assertEqual(p['dossier']['shared_identifiers'][0]['identifier_type'],'device_id')
        self.assertEqual(p['dossier']['shared_identifiers'][0]['event_ids'],['TOKEN-DEMO-A','TOKEN-DEMO-B'])
    def test_06_no_identity_claim(self):
        p=base.build_payload(gallery.CASES['shared-token'],'offline')
        self.assertIn('do not establish',p['executive_summary'])
    def test_07_no_shared_in_clean(self):self.assertEqual(base.engine.identifier_relationships(gallery.CASES['low-signal']),[])
    def test_08_clean_verification(self):
        c=gallery.CASES['low-signal'];self.assertTrue(all(e['verification_result']=='passed' for e in c['events']))
    def test_09_no_raw_audio_or_templates(self):
        for c in gallery.CASES.values():
            for e in c['events']:
                self.assertNotIn('audio',e);self.assertNotIn('template',e)
    def test_10_returns_copy(self):
        c=gallery.load_scenario('shared-token');c['events'][0]['replay_flag']=False
        self.assertTrue(gallery.load_scenario('shared-token')['events'][0]['replay_flag'])
    def test_11_invalid_slug_rejected(self):
        with self.assertRaises(KeyError):gallery.load_scenario('../../passwords')
    def test_12_no_network_in_gallery(self):
        with patch.object(base.legacy,'api_request',side_effect=AssertionError('network')):
            for c in gallery.CASES.values():self.assertTrue(base.build_payload(c,'offline')['dossier'])

class TestAssuranceLab(unittest.TestCase):
    def test_13_all_assurance_pass(self):
        x=a.run_assurance();self.assertEqual(x['passed'],x['total']);self.assertEqual(x['status'],'pass')
    def test_14_detailed_test_count(self):self.assertGreaterEqual(a.run_assurance()['total'],12)
    def test_15_no_api_calls(self):
        with patch.object(base.legacy,'api_request',side_effect=AssertionError('network')):
            self.assertEqual(a.run_assurance()['meta_api_requests'],0)
    def test_16_scope_limitations(self):self.assertIn('not ensure',a.run_assurance()['limitations'])
    def test_17_tests_have_unique_names(self):
        labels=[x['name'] for x in a.run_assurance()['checks']];self.assertEqual(len(labels),len(set(labels)))

class TestExportVerifier(unittest.TestCase):
    def setUp(self):
        r=base.build_payload(base.BUILTIN_CASE,'offline')
        self.d=copy.deepcopy(r['dossier']);self.a=copy.deepcopy(r['audit'])
    def test_18_baseline_consistent(self):self.assertEqual(a.validate_export_pair(self.d,self.a)['status'],'consistent')
    def test_19_no_fraud_certification(self):self.assertIn('not authenticate',a.validate_export_pair(self.d,self.a)['warning'])
    def test_20_tamper_source_fails(self):
        self.d['event_facts'][0]['verification_result']='passed'
        self.assertEqual(a.validate_export_pair(self.d,self.a)['status'],'mismatch')
    def test_21_altered_hash_fails(self):
        self.a['dossier_canonical_sha256']='0'*64
        self.assertEqual(a.validate_export_pair(self.d,self.a)['status'],'mismatch')
    def test_22_caseid_mismatch(self):
        self.a['case_id']='WRONG';self.assertEqual(a.validate_export_pair(self.d,self.a)['status'],'mismatch')
    def test_23_policy_mismatch(self):
        self.a['policy_version']='forged';self.assertEqual(a.validate_export_pair(self.d,self.a)['status'],'mismatch')
    def test_24_wrong_event_count(self):
        self.a['event_count']=40;self.assertEqual(a.validate_export_pair(self.d,self.a)['status'],'mismatch')
    def test_25_false_flag(self):
        self.d['automatic_adverse_action_allowed']=True
        self.a['dossier_canonical_sha256']=base.engine.sha256(base.engine.canonical_bytes(self.d))
        self.assertEqual(a.validate_export_pair(self.d,self.a)['status'],'mismatch')
    def test_26_both_changed_can_pass_but_not_authentic(self):
        # Demonstrates why pair consistency is not a signature.
        self.d['event_facts'][0]['verification_result']='passed'
        self.a['dossier_canonical_sha256']=base.engine.sha256(base.engine.canonical_bytes(self.d))
        result=a.validate_export_pair(self.d,self.a)
        self.assertEqual(result['status'],'consistent')
        self.assertIn('BOTH files',result['warning'])
    def test_27_nonobjects_rejected(self):
        with self.assertRaises(ValueError):a.validate_export_pair([],{})
    def test_28_oversized_fails(self):
        self.d['padding']='a'*2_100_000
        with self.assertRaises(ValueError):a.validate_export_pair(self.d,self.a)
    def test_29_no_identifier_values_in_verifier(self):
        self.assertNotIn('FAKE-DEVICE',json.dumps(a.validate_export_pair(self.d,self.a)))

class TestInterface(unittest.TestCase):
    def test_30_scenario_section(self):self.assertIn('id="scenario-gallery"',(ROOT/'index.html').read_text())
    def test_31_assurance_button(self):self.assertIn('id="run-assurance"',(ROOT/'index.html').read_text())
    def test_32_pair_ui(self):self.assertIn('id="verify-pair"',(ROOT/'index.html').read_text())
    def test_33_no_insecure_inner_html(self):self.assertNotIn('innerHTML',(ROOT/'assets/app.js').read_text())
    def test_34_browser_scenario_loader(self):self.assertIn("request('/api/showcase/'+",(ROOT/'assets/app.js').read_text())
    def test_35_fetch_guardrails(self):self.assertIn("request('/api/assurance')",(ROOT/'assets/app.js').read_text())
    def test_36_pair_verify_api(self):self.assertIn("request('/api/verify','POST'",(ROOT/'assets/app.js').read_text())
    def test_37_print_hide_assurance(self):self.assertIn('.scenario-section,.assurance-section{display:none!important}',(ROOT/'assets/app.css').read_text())

class TestHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv=base.WorkbenchServer(('127.0.0.1',0),v16.WorkbenchHandlerV16,token='offline-test-token',enable_meta=False)
        cls.thread=threading.Thread(target=cls.srv.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.srv.shutdown();cls.thread.join(2);cls.srv.server_close()
    def send(self,path,method='GET',obj=None,headers=None):
        port=self.srv.server_port
        conn=http.client.HTTPConnection('127.0.0.1',port,timeout=5)
        h={'Host':f'127.0.0.1:{port}','X-Sentinel-Token':'offline-test-token'}
        if headers:h.update(headers)
        body=None
        if obj is not None:
            body=json.dumps(obj);h['Content-Type']='application/json'
        conn.request(method,path,body=body,headers=h);resp=conn.getresponse();data=resp.read();status=resp.status;conn.close()
        return status,json.loads(data.decode('utf-8')) if path.startswith('/api/') else data
    def test_38_status(self):self.assertEqual(self.send('/api/status')[1]['version'],'1.6')
    def test_39_gallery(self):self.assertEqual(len(self.send('/api/showcase')[1]['scenarios']),3)
    def test_40_case_http(self):
        s,x=self.send('/api/showcase/shared-token');self.assertEqual(s,200);self.assertEqual(len(x['case']['events']),4)
    def test_41_invalid_case(self):self.assertEqual(self.send('/api/showcase/bad')[0],404)
    def test_42_unauthorized(self):self.assertEqual(self.send('/api/assurance',headers={'X-Sentinel-Token':'wrong'})[0],403)
    def test_43_wrong_host(self):self.assertEqual(self.send('/api/showcase',headers={'Host':'evil.invalid'})[0],403)
    def test_44_assurance(self):self.assertEqual(self.send('/api/assurance')[1]['status'],'pass')
    def test_45_verify_valid(self):
        r=base.build_payload(base.BUILTIN_CASE,'offline')
        self.assertEqual(self.send('/api/verify','POST',{'dossier_text':json.dumps(r['dossier']),'audit_text':json.dumps(r['audit'])})[1]['status'],'consistent')
    def test_46_verify_tamper(self):
        r=base.build_payload(base.BUILTIN_CASE,'offline');r['dossier']['event_facts'][0]['replay_flag']=False
        self.assertEqual(self.send('/api/verify','POST',{'dossier_text':json.dumps(r['dossier']),'audit_text':json.dumps(r['audit'])})[1]['status'],'mismatch')
    def test_duplicate_export_keys_rejected(self):
        r=base.build_payload(base.BUILTIN_CASE,'offline')
        dossier_text=json.dumps(r['dossier'])
        dossier_text=dossier_text.replace('"case_id":', '"case_id":"FORGED", "case_id":',1)
        s,x=self.send('/api/verify','POST',{'dossier_text':dossier_text,'audit_text':json.dumps(r['audit'])})
        self.assertEqual(s,422)
    def test_47_meta_disabled(self):
        s,x=self.send('/api/investigate','POST',{'case':base.BUILTIN_CASE,'mode':'meta'})
        self.assertEqual(s,422);self.assertIn('disabled',x['error'])
    def test_48_default_offline(self):
        s,x=self.send('/api/investigate','POST',{'case':base.BUILTIN_CASE,'mode':'offline'})
        self.assertEqual(s,200);self.assertEqual(x['dossier']['generation_mode'],'offline')
    def test_49_no_provider_key_in_status(self):self.assertNotIn('api_key',str(self.send('/api/status')[1]))
    def test_50_bad_origin(self):self.assertEqual(self.send('/api/showcase',headers={'Origin':'https://evil.invalid'})[0],403)

if __name__=='__main__':unittest.main(verbosity=2)
