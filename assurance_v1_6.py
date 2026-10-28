#!/usr/bin/env python3
"""Local, reproducible safeguard exercise and artifact consistency verifier.

These are limited fixed-case checks, not a security audit, certification or guarantee.
No model calls, production calls, files, external dependencies or customer data.
"""
from __future__ import annotations
import copy
import json
from typing import Any

from showcase_v1_6 import CASES
import workbench_v1_4 as wb


def validate_export_pair(dossier: Any, audit: Any) -> dict[str, Any]:
    """Check a self-consistent exported pair, not authenticity or custody."""
    if not isinstance(dossier, dict) or not isinstance(audit, dict):
        raise ValueError('Both exported files must contain JSON objects.')
    if len(wb.engine.canonical_bytes(dossier)) > wb.MAX_RESPONSE_BYTES:
        raise ValueError('Dossier exceeds verification size limit.')
    if len(wb.engine.canonical_bytes(audit)) > 100_000:
        raise ValueError('Audit exceeds verification size limit.')
    check = [
        ('audit schema', audit.get('audit_schema_version') == '1.0'),
        ('dossier schema', dossier.get('schema_version') == '1.2'),
        ('case identifier', bool(dossier.get('case_id')) and audit.get('case_id') == dossier.get('case_id')),
        ('dossier canonical SHA-256', audit.get('dossier_canonical_sha256') == wb.engine.sha256(wb.engine.canonical_bytes(dossier))),
        ('policy version', audit.get('policy_version') == dossier.get('policy_version')),
        ('classification', dossier.get('data_classification') == 'synthetic_demo_data'),
        ('source authority', dossier.get('source_facts_authority') == 'supplied_case_metadata_only'),
        ('review-only constraints', dossier.get('human_review_required') is True and dossier.get('automatic_adverse_action_allowed') is False),
        ('source event count', isinstance(dossier.get('event_facts'), list) and audit.get('event_count') == len(dossier['event_facts'])),
        ('review queue count', isinstance(dossier.get('investigation_queue'),list) and audit.get('queue_count') == len(dossier['investigation_queue'])),
        ('advisory presence', audit.get('ai_advisory_present') == (dossier.get('ai_advisory') is not None)),
        ('generation mode', audit.get('mode') == dossier.get('generation_mode') and audit.get('mode') in ('offline','api')),
    ]
    return {
        'status': 'consistent' if all(v for _,v in check) else 'mismatch',
        'passed':sum(bool(v) for _,v in check),'total':len(check),
        'checks':[{'name':name,'passed':bool(v)} for name,v in check],
        'dossier_sha256':wb.engine.sha256(wb.engine.canonical_bytes(dossier)),
        'warning':'This verifies self-consistency only. If someone alters BOTH files and recomputes hashes, the pair may still pass. It does not authenticate the source, prove custody or replace a digital signature.'
    }


def run_assurance() -> dict[str, Any]:
    """Run fixed in-memory positive/negative tests without invoking the network."""
    base=copy.deepcopy(wb.BUILTIN_CASE)
    checks=[]
    def check(name, fn):
        try:
            fn(); checks.append({'name':name,'passed':True})
        except Exception:
            checks.append({'name':name,'passed':False})
    def should_reject(name, transform, exception):
        def runner():
            value=copy.deepcopy(base)
            transform(value)
            try:
                wb.engine.validate_case(value)
            except exception:
                return
            raise AssertionError('unsafe case accepted')
        check(name, runner)
    def changed_event(case):case['events'][1]['event_id']=case['events'][0]['event_id']
    def added_audio(case):case['events'][0]['raw_audio']='faked-voice-data'
    def bad_time(case):case['events'][0]['timestamp']='not-a-time'
    def bad_type(case):case['events'][0]['replay_flag']='false'
    def unknown_id_field(case):case['events'][0]['available_identifiers']['phone_number']='1234'
    def bad_class(case):case['data_classification']='customer_records'
    def bad_constraint(case):case['explicit_constraints']=[]
    for label,fn in (
        ('Reject duplicate event IDs',changed_event),
        ('Reject raw audio fields',added_audio),
        ('Reject malformed timestamps',bad_time),
        ('Reject false replay string',bad_type),
        ('Reject unapproved identifiers',unknown_id_field),
        ('Reject non-synthetic classification',bad_class),
        ('Require human-review constraints',bad_constraint),
    ):
        should_reject(label,fn,wb.engine.ValidationError)

    def reject_forged_advisory(changer):
        advisory=wb.make_fixture(base)
        changer(advisory)
        try:wb.engine.validate_legacy_advisory(advisory,base)
        except wb.engine.ValidationError:return
        raise AssertionError('forged AI narrative accepted')
    check('Reject model-altered event timestamp',lambda:reject_forged_advisory(lambda a:a['timeline'][0].__setitem__('timestamp','2026-12-01T00:00:00Z')))
    check('Reject fabricated evidence field',lambda:reject_forged_advisory(lambda a:a['hypotheses'][0]['evidence_refs'].__setitem__(0,'EVENT-DEMO-A.fake_result')))
    check('Reject confirmed fraud claim',lambda:reject_forged_advisory(lambda a:a.__setitem__('case_summary','Confirmed fraud detected.')))
    check('Reject automatic account block advice',lambda:reject_forged_advisory(lambda a:a['recommended_next_steps'].__setitem__(0,'Immediately block account.')))

    def tamper_audit():
        result=wb.build_payload(base,'offline')
        changed=copy.deepcopy(result['dossier'])
        changed['event_facts'][0]['verification_result']='passed'
        value=validate_export_pair(changed,result['audit'])
        assert value['status']=='mismatch'
    check('Detect changed exported source result',tamper_audit)

    def preserve_authority():
        result=wb.build_payload(base,'offline')
        assert result['dossier']['human_review_required'] is True
        assert result['dossier']['automatic_adverse_action_allowed'] is False
        assert [f['verification_result'] for f in result['dossier']['event_facts']]==['failed','failed','passed']
    check('Keep biometric result and human authority intact',preserve_authority)
    def comparison():
        for case_data in CASES.values():
            dossier=wb.build_payload(case_data,'offline')['dossier']
            assert not dossier['automatic_adverse_action_allowed']
            assert dossier['human_review_required']
        shared=wb.build_payload(CASES['shared-token'],'offline')['dossier']['shared_identifiers']
        assert len(shared)==1
        assert 'identity' not in shared[0]['status']
    check('Multi-scenario linkage remains qualified',comparison)
    return {
        'status':'pass' if all(c['passed'] for c in checks) else 'fail',
        'passed':sum(c['passed'] for c in checks),'total':len(checks),
        'checks':checks,'policy_version':wb.engine.POLICY_VERSION,
        'scope':'Local fixed-fixture assertions; no live Meta evaluation, penetration testing, or production certification.',
        'network_requests':0,'meta_api_requests':0,'production_requests':0,
        'limitations':'Passing does not ensure every possible prompt injection, ungrounded narrative, privacy failure or operational risk is prevented.'
    }
