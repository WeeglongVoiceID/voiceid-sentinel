#!/usr/bin/env python3
"""Standalone standard-library regression tests for the local v1.4 workbench. No external API requests."""
import copy
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import workbench_v1_4 as w

CASE = w.BUILTIN_CASE


class TestPayload(unittest.TestCase):
    def test_01_baseline_offline(self):
        x=w.build_payload(CASE,'offline');self.assertEqual(x['dossier']['generation_mode'],'offline')
    def test_02_offline_has_no_advisory(self):
        self.assertIsNone(w.build_payload(CASE,'offline')['advisory_display'])
    def test_03_offline_false_network_marker(self):
        self.assertFalse(w.build_payload(CASE,'offline')['live_meta_call_made'])
    def test_04_source_3_events(self):
        self.assertEqual(len(w.build_payload(CASE,'offline')['dossier']['event_facts']),3)
    def test_05_source_order_unchanged(self):
        self.assertEqual([v['verification_result'] for v in w.build_payload(CASE,'offline')['dossier']['event_facts']],['failed','failed','passed'])
    def test_06_source_replay_flag(self):
        self.assertEqual(sum(x['replay_flag'] is True for x in w.build_payload(CASE,'offline')['dossier']['event_facts']),1)
    def test_07_priority_policy(self):
        self.assertEqual([x['review_priority'] for x in w.build_payload(CASE,'offline')['dossier']['investigation_queue']],[2,3,5])
    def test_08_audit_hash(self):
        x=w.build_payload(CASE,'offline');self.assertEqual(x['audit']['dossier_canonical_sha256'],w.engine.sha256(w.engine.canonical_bytes(x['dossier'])))
    def test_09_same_source_input_hash(self):
        x=w.build_payload(CASE,'offline');self.assertEqual(x['audit']['input_canonical_sha256'],w.BUILTIN_CASE_HASH)
    def test_10_preview_is_illustrative(self):
        x=w.build_payload(CASE,'preview');self.assertEqual(x['advisory_origin'],'illustrative_fixture')
        self.assertIn('NOT META',x['mode_label'])
    def test_11_preview_remains_offline(self):
        x=w.build_payload(CASE,'preview');self.assertEqual(x['dossier']['generation_mode'],'offline');self.assertIsNone(x['dossier']['ai_advisory'])
    def test_12_preview_passes_validator(self):
        w.engine.validate_legacy_advisory(w.make_fixture(CASE),CASE)
    def test_13_preview_source_unchanged(self):
        self.assertEqual(w.build_payload(CASE,'offline')['dossier']['event_facts'],w.build_payload(CASE,'preview')['dossier']['event_facts'])
    def test_14_preview_different_case_rejected(self):
        case=copy.deepcopy(CASE);case['case_id']='ALTERED-CASE'
        with self.assertRaises(w.WorkbenchError):w.build_payload(case,'preview')
    def test_15_preview_different_fact_rejected(self):
        case=copy.deepcopy(CASE);case['events'][0]['replay_flag']=False
        with self.assertRaises(w.WorkbenchError):w.build_payload(case,'preview')
    def test_16_unknown_mode_rejected(self):
        with self.assertRaises(w.WorkbenchError):w.build_payload(CASE,'fake')
    def test_17_real_records_rejected(self):
        case=copy.deepcopy(CASE);case['data_classification']='bank_records'
        with self.assertRaises(w.engine.ValidationError):w.build_payload(case,'offline')
    def test_18_audio_field_rejected(self):
        case=copy.deepcopy(CASE);case['events'][0]['audio']='base64-audio'
        with self.assertRaises(w.engine.ValidationError):w.build_payload(case,'offline')
    def test_19_duplicate_id_rejected(self):
        case=copy.deepcopy(CASE);case['events'][1]['event_id']=case['events'][0]['event_id']
        with self.assertRaises(w.engine.ValidationError):w.build_payload(case,'offline')
    def test_20_empty_input_rejected(self):
        with self.assertRaises(w.engine.ValidationError):w.build_payload({},'offline')
    def test_21_no_meta_key_rejected(self):
        with self.assertRaises(w.WorkbenchError):w.build_payload(CASE,'meta')
    def test_22_invalid_meta_model_rejected_before_call(self):
        with self.assertRaises(w.WorkbenchError):w.build_payload(CASE,'meta',api_key='fake',model='bad/name')
    def test_23_meta_incomplete_response_fails(self):
        with patch.object(w.legacy,'api_request',return_value=({'status':'incomplete'}, {'api_status':'incomplete'})):
            with self.assertRaises(w.WorkbenchError):w.build_payload(CASE,'meta',api_key='fake')
    def test_24_meta_bad_json_fails(self):
        with patch.object(w.legacy,'api_request',return_value=({'output_text':'not-json'},{'api_status':'completed'})):
            with self.assertRaises(w.WorkbenchError):w.build_payload(CASE,'meta',api_key='fake')
    def test_25_meta_valid_mock(self):
        raw={'output_text':json.dumps(w.make_fixture(CASE))}
        with patch.object(w.legacy,'api_request',return_value=(raw,{'api_status':'completed','model':'muse-spark-1.3'})):
            x=w.build_payload(CASE,'meta',api_key='fake');self.assertEqual(x['advisory_origin'],'meta_api')
            self.assertIsNotNone(x['dossier']['ai_advisory'])
    def test_26_meta_preserves_timeline_facts(self):
        raw={'output_text':json.dumps(w.make_fixture(CASE))}
        with patch.object(w.legacy,'api_request',return_value=(raw,{'api_status':'completed','model':'muse-spark-1.3'})):
            x=w.build_payload(CASE,'meta',api_key='fake')
            self.assertEqual(x['dossier']['event_facts'],w.build_payload(CASE,'offline')['dossier']['event_facts'])
    def test_27_meta_preserves_priorities(self):
        raw={'output_text':json.dumps(w.make_fixture(CASE))}
        with patch.object(w.legacy,'api_request',return_value=(raw,{'api_status':'completed','model':'muse-spark-1.3'})):
            x=w.build_payload(CASE,'meta',api_key='fake')
            self.assertEqual(x['dossier']['investigation_queue'],w.build_payload(CASE,'offline')['dossier']['investigation_queue'])
    def test_28_meta_unsafe_response_rejected(self):
        a=w.make_fixture(CASE);a['case_summary']='Confirmed fraud from one replay flag.'
        with patch.object(w.legacy,'api_request',return_value=({'output_text':json.dumps(a)},{'api_status':'completed'})):
            with self.assertRaises(w.engine.ValidationError):w.build_payload(CASE,'meta',api_key='fake')
    def test_29_meta_timestamp_falsification_rejected(self):
        a=w.make_fixture(CASE);a['timeline'][0]['timestamp']='2030-01-01T00:00:00Z'
        with patch.object(w.legacy,'api_request',return_value=({'output_text':json.dumps(a)},{'api_status':'completed'})):
            with self.assertRaises(w.engine.ValidationError):w.build_payload(CASE,'meta',api_key='fake')
    def test_30_provider_errors_sanitized(self):
        with patch.object(w.legacy,'api_request',side_effect=urllib.error.URLError('API_KEY_SECRET_DO_NOT_EXPOSE')):
            with self.assertRaises(w.WorkbenchError) as cm:w.build_payload(CASE,'meta',api_key='fake')
            self.assertNotIn('API_KEY_SECRET_DO_NOT_EXPOSE',str(cm.exception))
    def test_31_no_network_offline(self):
        with patch.object(w.legacy,'api_request',side_effect=AssertionError('should not be called')):
            w.build_payload(CASE,'offline')
    def test_32_no_network_preview(self):
        with patch.object(w.legacy,'api_request',side_effect=AssertionError('should not be called')):
            w.build_payload(CASE,'preview')
    def test_33_json_duplicate_rejected(self):
        with self.assertRaises(w.WorkbenchError):w.decode_json(b'{"case_id":"x","case_id":"y"}')
    def test_34_json_nan_rejected(self):
        with self.assertRaises(w.WorkbenchError):w.decode_json(b'{"x":NaN}')
    def test_35_json_bytes_rejected(self):
        with self.assertRaises(w.WorkbenchError):w.decode_json(b'\xff')
    def test_36_json_length_limit(self):
        with self.assertRaises(w.WorkbenchError):w.decode_json(b' '* (w.MAX_REQUEST+1))


class TestHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.token='fakesessiontokenfortesting'
        cls.server=w.WorkbenchServer(('127.0.0.1',0),w.WorkbenchHandler,token=cls.token)
        cls.port=cls.server.server_port
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(3)

    def request(self,path,method='GET',body=None,token=True,origin=None,content_type='application/json'):
        url=f'http://127.0.0.1:{self.port}{path}'
        headers={}
        if token:headers['X-Sentinel-Token']=self.token
        if origin:headers['Origin']=origin
        if body is not None:headers['Content-Type']=content_type
        data=None if body is None else (body if isinstance(body,bytes) else json.dumps(body).encode())
        req=urllib.request.Request(url,method=method,data=data,headers=headers)
        try:
            with urllib.request.urlopen(req,timeout=8) as r:return r.status,r.headers,r.read()
        except urllib.error.HTTPError as e:return e.code,e.headers,e.read()

    def test_37_index_renders(self):
        status,headers,raw=self.request('/');self.assertEqual(status,200);self.assertIn(b'AI Investigation Workbench',raw)
    def test_38_js_served(self):
        status,h,raw=self.request('/assets/app.js');self.assertEqual(status,200);self.assertIn(b'Live Meta',raw) if False else self.assertIn(b'execute',raw)
    def test_39_css_served(self):
        self.assertEqual(self.request('/assets/app.css')[0],200)
    def test_40_unknown_route_404(self):
        self.assertEqual(self.request('/api/admin')[0],404)
    def test_41_status_token_required(self):
        self.assertEqual(self.request('/api/status',token=False)[0],403)
    def test_42_sample_token_required(self):
        self.assertEqual(self.request('/api/sample',token=False)[0],403)
    def test_43_status_offline(self):
        status,h,raw=self.request('/api/status');self.assertEqual(status,200);self.assertFalse(json.loads(raw)['meta_enabled'])
    def test_44_sample_is_synthetic(self):
        status,h,raw=self.request('/api/sample');self.assertEqual(status,200);self.assertEqual(json.loads(raw)['case']['data_classification'],'synthetic_demo_data')
    def test_45_offline_http(self):
        status,h,raw=self.request('/api/investigate','POST',{'case':CASE,'mode':'offline'})
        self.assertEqual(status,200);self.assertEqual(json.loads(raw)['advisory_origin'],'none')
    def test_46_preview_http(self):
        status,h,raw=self.request('/api/investigate','POST',{'case':CASE,'mode':'preview'})
        self.assertEqual(status,200);self.assertEqual(json.loads(raw)['advisory_origin'],'illustrative_fixture')
    def test_47_meta_disabled(self):
        status,h,raw=self.request('/api/investigate','POST',{'case':CASE,'mode':'meta'})
        self.assertEqual(status,422);self.assertIn(b'disabled',raw)
    def test_48_post_token_required(self):
        self.assertEqual(self.request('/api/investigate','POST',{'case':CASE,'mode':'offline'},token=False)[0],403)
    def test_49_reject_foreign_origin(self):
        self.assertEqual(self.request('/api/investigate','POST',{'case':CASE,'mode':'offline'},origin='http://malicious.invalid')[0],403)
    def test_50_allow_same_origin(self):
        self.assertEqual(self.request('/api/investigate','POST',{'case':CASE,'mode':'offline'},origin=f'http://127.0.0.1:{self.port}')[0],200)
    def test_51_bad_content_type(self):
        self.assertEqual(self.request('/api/investigate','POST',b'test',content_type='text/plain')[0],415)
    def test_52_bad_json(self):
        self.assertEqual(self.request('/api/investigate','POST',b'{broken')[0],422)
    def test_53_duplicate_nested_case_json_rejected(self):
        raw=json.dumps(CASE).replace('"case_id":', '"case_id":"DUPLICATE", "case_id":',1)
        status,h,result=self.request('/api/investigate','POST',{'case_text':raw,'mode':'offline'})
        self.assertEqual(status,422)
    def test_54_case_text_valid(self):
        status,h,result=self.request('/api/investigate','POST',{'case_text':json.dumps(CASE),'mode':'offline'})
        self.assertEqual(status,200)
    def test_55_cross_origin_headers(self):
        status,headers,raw=self.request('/');self.assertEqual(headers.get('X-Frame-Options'),'DENY')
        self.assertIn("script-src 'self'",headers.get('Content-Security-Policy'))
    def test_56_no_cors(self):
        status,headers,raw=self.request('/');self.assertIsNone(headers.get('Access-Control-Allow-Origin'))
    def test_57_no_response_cache(self):
        status,headers,raw=self.request('/api/status');self.assertIn('no-store',headers.get('Cache-Control'))
    def test_58_session_not_in_static_html(self):
        status,h,raw=self.request('/');self.assertNotIn(self.token.encode(),raw)
    def test_59_unknown_request_payload(self):
        self.assertEqual(self.request('/api/investigate','POST',{'mode':'offline','case':CASE,'key':'injection'})[0],422)
    def test_60_bad_case_fails_closed(self):
        c=copy.deepcopy(CASE);c['events'][0]['audio']='secret'
        self.assertEqual(self.request('/api/investigate','POST',{'case':c,'mode':'offline'})[0],422)


class TestHTTPMetaMock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.token='anotherfakewebsession'
        cls.server=w.WorkbenchServer(('127.0.0.1',0),w.WorkbenchHandler,token=cls.token,
                                     enable_meta=True,key='DUMMY_KEY_NOT_REAL',model='muse-spark-1.3')
        cls.port=cls.server.server_port
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(3)
    def request(self,path='/api/investigate',mode='meta',token=True):
        data=json.dumps({'case':CASE,'mode':mode}).encode()
        headers={'Content-Type':'application/json'}
        if token:headers['X-Sentinel-Token']=self.token
        req=urllib.request.Request(f'http://127.0.0.1:{self.port}{path}', data=data if path!='/api/status' else None,
                                   method='POST' if path!='/api/status' else 'GET',headers=headers)
        try:
            with urllib.request.urlopen(req,timeout=10) as resp:return resp.status,json.loads(resp.read())
        except urllib.error.HTTPError as e:return e.code,json.loads(e.read())

    def test_61_meta_status_explicit_enabled(self):
        status,data=self.request('/api/status');self.assertEqual(status,200);self.assertTrue(data['meta_enabled'])
    def test_62_meta_api_mocked_http_success(self):
        mocked={'output_text':json.dumps(w.make_fixture(CASE))}
        with patch.object(w.legacy,'api_request',return_value=(mocked,{'api_status':'completed','model':'muse-spark-1.3'})) as fn:
            status,data=self.request()
        self.assertEqual(status,200);self.assertTrue(data['live_meta_call_made']);self.assertEqual(fn.call_count,1)
        self.assertEqual(data['dossier']['generation_mode'],'api')
        self.assertNotIn('DUMMY_KEY_NOT_REAL',json.dumps(data))
    def test_63_meta_api_mocked_http_unsafe_fails(self):
        a=w.make_fixture(CASE);a['case_summary']='Confirmed fraud from sequence alone.'
        with patch.object(w.legacy,'api_request',return_value=({'output_text':json.dumps(a)},{'api_status':'completed'})):
            status,data=self.request()
        self.assertEqual(status,422);self.assertNotIn('dossier',data)
    def test_64_meta_request_unauthorized(self):
        status,data=self.request(token=False);self.assertEqual(status,403)
    def test_65_meta_concurrent_request_lock(self):
        self.server.meta_lock.acquire()
        try:status,data=self.request()
        finally:self.server.meta_lock.release()
        self.assertEqual(status,429)


if __name__ == '__main__':
    unittest.main(verbosity=2)
