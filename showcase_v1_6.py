#!/usr/bin/env python3
"""Fixed, fictional scenario gallery for repeatable demonstrations.

Only synthetic data. Scenario descriptions are authored claims about a fixture,
not findings about a real person or production banking event.
"""
from __future__ import annotations
import copy
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'engine_v1_2'))
import sentinel_v1_2 as engine

BASE=engine.load_case(HERE/'engine_v1_2'/'sample_multi_event_case.json')
CONSTRAINTS=copy.deepcopy(BASE['explicit_constraints'])


def event(eid,ts,channel,verification,liveness,replay,*,device=None,session=None,subject=None):
    return {
        'event_id':eid,'timestamp':ts,'channel':channel,
        'verification_result':verification,'liveness_result':liveness,
        'replay_flag':replay,
        'available_identifiers':{'device_id':device,'session_id':session,'subject_ref':subject},
        'notes':'Entirely fictional demonstration observation; no audio, biometrics or customer records.'
    }


def case(case_id,case_type,purpose,events):
    return {'case_id':case_id,'case_type':case_type,'purpose':purpose,
            'data_classification':'synthetic_demo_data','events':events,
            'explicit_constraints':copy.deepcopy(CONSTRAINTS)}

CASES={
    'unlinked-sequence': copy.deepcopy(BASE),
    'shared-token':case('SENTINEL-SHARED-TOKEN-002','synthetic_cross_event_identifier_review',
        'Show explicit shared opaque device token as a correlation signal, never proof of who acted.',[
            event('TOKEN-DEMO-A','2026-10-21T10:01:00Z','web_demo','failed','inconclusive',True,device='FAKE-DEVICE-ALPHA',session='FAKE-SESSION-01'),
            event('TOKEN-DEMO-B','2026-10-21T10:04:00Z','web_demo','passed','passed',False,device='FAKE-DEVICE-ALPHA',session='FAKE-SESSION-02'),
            event('TOKEN-DEMO-C','2026-10-21T10:08:00Z','app_demo','failed','failed',False,device='FAKE-DEVICE-BETA',session='FAKE-SESSION-03'),
            event('TOKEN-DEMO-D','2026-10-21T10:11:00Z','app_demo','passed','passed',False,device=None,session='FAKE-SESSION-04'),
        ]),
    'low-signal':case('SENTINEL-LOW-SIGNAL-003','synthetic_routine_metadata_review',
        'Demonstrate restraint and no invented fraud/identity conclusion for uneventful authentication metadata.',[
            event('ROUTINE-DEMO-A','2026-10-22T15:05:00Z','web_demo','passed','passed',False,device='FAKE-DEVICE-X'),
            event('ROUTINE-DEMO-B','2026-10-22T15:19:00Z','app_demo','passed','passed',False,device='FAKE-DEVICE-Y'),
            event('ROUTINE-DEMO-C','2026-10-22T16:01:00Z','web_demo','passed','passed',False,device='FAKE-DEVICE-Z'),
        ]),
}
DESCRIPTIONS={
    'unlinked-sequence':{'name':'01 · Unlinked sequence','headline':'Two failures, then a pass','lesson':'Close timing does not establish a shared actor, session or device.'},
    'shared-token':{'name':'02 · Shared token','headline':'Explicit correlation, uncertain identity','lesson':'One matching opaque device token is a signal, never proof of the person controlling it.'},
    'low-signal':{'name':'03 · Low-signal case','headline':'Avoid false accusations','lesson':'A routine-looking sequence should not be embellished into a fraud narrative.'},
}


def scenario_list():
    out=[]
    for slug, case_data in CASES.items():
        engine.validate_case(case_data)
        facts=engine.normalized_event_facts(case_data)
        out.append({'id':slug,**DESCRIPTIONS[slug],
                    'events':len(facts),
                    'replay_flags':sum(e['replay_flag'] is True for e in facts),
                    'shared_signals':len(engine.identifier_relationships(case_data)),
                    'case_id':case_data['case_id']})
    return out


def load_scenario(slug):
    if slug not in CASES:
        raise KeyError(slug)
    value=copy.deepcopy(CASES[slug]);engine.validate_case(value)
    return value

for _entry in CASES.values():
    engine.validate_case(_entry)
