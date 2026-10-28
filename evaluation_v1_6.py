#!/usr/bin/env python3
"""Reproducible synthetic fixtures evaluation; not a real-world benchmark."""
from __future__ import annotations
import json
from pathlib import Path
import workbench_v1_4 as wb
from showcase_v1_6 import CASES, DESCRIPTIONS
from assurance_v1_6 import run_assurance, validate_export_pair


def evaluate() -> dict:
    scenarios=[]
    for slug,case in CASES.items():
        r=wb.build_payload(case,'offline')
        facts=r['dossier']['event_facts'];q=r['dossier']['investigation_queue'];shared=r['dossier']['shared_identifiers']
        verification=validate_export_pair(r['dossier'],r['audit'])
        scenarios.append({
            'scenario_id':slug,'case_id':case['case_id'],'title':DESCRIPTIONS[slug]['headline'],
            'source_events':len(facts),'passed':sum(e['verification_result']=='passed' for e in facts),
            'failed':sum(e['verification_result']=='failed' for e in facts),
            'replay_flags':sum(e['replay_flag'] is True for e in facts),
            'shared_opaque_identifiers':len(shared),
            'review_queue_items':len(q),
            'minimum_review_priority':min((e['review_priority'] for e in q),default=None),
            'human_review_required':r['dossier']['human_review_required'],
            'automatic_adverse_action_allowed':r['dossier']['automatic_adverse_action_allowed'],
            'export_consistency_checks_passed':verification['passed'],
            'export_consistency_checks_total':verification['total'],
            'source_fact_result_preserved':[
                (e['event_id'],e['verification_result']) for e in facts
            ]==[(e['event_id'],e['verification_result']) for e in wb.engine.normalized_event_facts(case)],
        })
    return {
        'evaluation_kind':'fixed_synthetic_scenario_review',
        'model_api_calls':0,'production_requests':0,
        'case_count':len(scenarios),'scenario_results':scenarios,
        'assurance':run_assurance(),
        'interpretation':'These are known fixed synthetic fixtures, not accuracy, recall, precision, customer testing, red teaming or independent security certification. Human review is required.'
    }


def markdown(r):
    lines=['# VoiceID Sentinel v1.6 — Reproducible Synthetic Evaluation','','**Scope:** fixed synthetic demo scenarios only; no live Meta model calls, production data or external evaluation.','',
           '| Synthetic scenario | Events | Passed | Failed | Replay flags | Shared token signals | Review items | Export consistency |',
           '|---|---:|---:|---:|---:|---:|---:|---|']
    for x in r['scenario_results']:
        lines.append(f"| {x['title']} | {x['source_events']} | {x['passed']} | {x['failed']} | {x['replay_flags']} | {x['shared_opaque_identifiers']} | {x['review_queue_items']} | {x['export_consistency_checks_passed']}/{x['export_consistency_checks_total']} |")
    a=r['assurance']
    lines+=['',f"**Fixed safeguard challenges:** {a['passed']}/{a['total']} passed.",'',
            '**Model API credits consumed:** 0.','',
            '**Not demonstrated:** statistical fraud-detection performance, adjudicated real incidents, correct model interpretations across varied populations, privacy compliance, multi-user authentication, enterprise uptime, production security posture, independent validation.','',
            '**Caveat:** Hash-pair verification checks self-consistency only. Model advisory references are structurally validated but not fully semantically fact-checked.','',
            '**Rule:** No automatic fraud/identity outcome or adverse action based on these synthetic observations.','']
    return '\n'.join(lines)

if __name__=='__main__':
    path=Path(__file__).resolve().parent
    result=evaluate()
    (path/'EVALUATION_RESULTS.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (path/'EVALUATION_REPORT.md').write_text(markdown(result),encoding='utf-8')
    print(f"Evaluated {result['case_count']} fictional scenarios; {result['assurance']['passed']}/{result['assurance']['total']} fixed safeguards; 0 Meta calls")
