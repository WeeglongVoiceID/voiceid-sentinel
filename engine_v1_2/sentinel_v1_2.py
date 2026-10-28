#!/usr/bin/env python3
"""VoiceID Sentinel v1.2 | Local, synthetic-metadata-only review prototype.

By default this does not make network calls. Meta API mode is explicit.
A model is never the authority for event facts, linkage or review priorities.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
import urllib.error
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sentinel_v1_1_reference as legacy

VERSION = '1.2'
POLICY_VERSION = 'sentinel-queue-1.2.0'
MAX_INPUT_BYTES = 256 * 1024
MAX_EVENTS = 100
CASE_KEYS = {'case_id', 'case_type', 'data_classification', 'purpose', 'events', 'explicit_constraints'}
EVENT_KEYS = {'event_id', 'timestamp', 'channel', 'verification_result', 'replay_flag',
              'liveness_result', 'available_identifiers', 'notes'}
IDENTIFIER_KEYS = {'device_id', 'session_id', 'subject_ref', 'account_id',
                   'transaction_id', 'correlation_id'}
RESULTS = {'passed', 'failed', 'inconclusive', 'not_assessed'}
LIVENESS = {'passed', 'failed', 'inconclusive', 'not_assessed'}
ID_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$')
TOKEN_PATTERN = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.:@/\-]{0,127}$')
REQUIRED_CONSTRAINT_CONCEPTS = ('shared actor', 'fraud', 'later successful', 'human review')
UNSUPPORTED_CERTAINTY = [
    re.compile(r'\b(?:confirmed|proven|definitive)\s+(?:fraud|spoofing|same actor|same identity)\b', re.I),
    re.compile(r'\b(?:fraud|spoofing|same actor|same identity)\s+(?:is\s+|was\s+)?(?:confirmed|proven)\b', re.I),
    re.compile(r'\b(?:automatically|immediately)\s+(?:block|deny|freeze|blacklist)\b', re.I),
]


class ValidationError(Exception):
    """A fail-closed, locally reportable input or advisory validation issue."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def require_text(v: Any, label: str, maximum: int = 500) -> str:
    if not isinstance(v, str) or not v.strip() or len(v) > maximum or any(ord(ch) < 32 for ch in v):
        raise ValidationError(f'{label} must be non-empty text (at most {maximum} characters, no control characters).')
    return v


def valid_timestamp(s: Any, label: str) -> None:
    require_text(s, label, 40)
    try:
        dt = datetime.fromisoformat(s.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValidationError(f'{label} is not a valid ISO-8601 timestamp.') from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValidationError(f'{label} must include a timezone (e.g. Z).')


def validate_case(case: Any) -> dict[str, Any]:
    """Reject non-synthetic, excess, unexpected and biometric-bearing input, fail closed."""
    if not isinstance(case, dict):
        raise ValidationError('Case must be a JSON object.')
    unknown = set(case) - CASE_KEYS
    if unknown:
        raise ValidationError(f'Unexpected case-level fields: {sorted(unknown)}')
    case_id = require_text(case.get('case_id'), 'case_id', 80)
    if not ID_PATTERN.fullmatch(case_id):
        raise ValidationError('case_id must use letters, numbers, underscores or hyphens.')
    if case.get('data_classification') != 'synthetic_demo_data':
        raise ValidationError('Only data_classification="synthetic_demo_data" is accepted; no real records.')
    require_text(case.get('case_type'), 'case_type', 120)
    require_text(case.get('purpose'), 'purpose', 1000)
    events = case.get('events')
    if not isinstance(events, list) or not 1 <= len(events) <= MAX_EVENTS:
        raise ValidationError(f'events must be a non-empty list of at most {MAX_EVENTS} items.')
    constraints = case.get('explicit_constraints')
    if not isinstance(constraints, list) or not all(isinstance(v, str) and 1 <= len(v) <= 500 for v in constraints):
        raise ValidationError('explicit_constraints must be an array of non-empty strings.')
    constraints_text = ' '.join(constraints).lower()
    if not all(term in constraints_text for term in REQUIRED_CONSTRAINT_CONCEPTS):
        raise ValidationError('Required human-review, linkage and no-fraud-inference constraints are missing.')
    seen = set()
    for index, event in enumerate(events):
        label = f'events[{index}]'
        if not isinstance(event, dict):
            raise ValidationError(f'{label} must be an object.')
        unexpected = set(event) - EVENT_KEYS
        if unexpected:
            raise ValidationError(f'{label} contains unsupported or potentially sensitive fields: {sorted(unexpected)}')
        eid = require_text(event.get('event_id'), f'{label}.event_id', 80)
        if not ID_PATTERN.fullmatch(eid):
            raise ValidationError(f'{label}.event_id contains unsupported characters.')
        if eid in seen:
            raise ValidationError(f'Duplicate event_id: {eid}')
        seen.add(eid)
        valid_timestamp(event.get('timestamp'), f'{label}.timestamp')
        require_text(event.get('channel'), f'{label}.channel', 100)
        if event.get('verification_result') not in RESULTS:
            raise ValidationError(f'{label}.verification_result must be one of {sorted(RESULTS)}.')
        if event.get('liveness_result') not in LIVENESS:
            raise ValidationError(f'{label}.liveness_result must be one of {sorted(LIVENESS)}.')
        if event.get('replay_flag') is not None and type(event.get('replay_flag')) is not bool:
            raise ValidationError(f'{label}.replay_flag must be true, false or null.')
        require_text(event.get('notes'), f'{label}.notes', 500)
        ids = event.get('available_identifiers')
        if not isinstance(ids, dict):
            raise ValidationError(f'{label}.available_identifiers must be an object.')
        if set(ids) - IDENTIFIER_KEYS:
            raise ValidationError(f'{label}.available_identifiers includes unsupported fields.')
        for field, value in ids.items():
            if value is not None and (not isinstance(value, str) or not TOKEN_PATTERN.fullmatch(value)):
                raise ValidationError(f'{label}.available_identifiers.{field} must be a non-empty opaque token or null.')
    return case


def load_case(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_INPUT_BYTES:
        raise ValidationError(f'Input exceeds {MAX_INPUT_BYTES} bytes.')
    text = path.read_text(encoding='utf-8-sig')
    def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f'Duplicate JSON key: {key}')
            obj[key] = value
        return obj
    try:
        case = json.loads(text, object_pairs_hook=unique_keys,
                          parse_constant=lambda v: (_ for _ in ()).throw(ValueError(f'Invalid number: {v}')))
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValidationError(f'Invalid JSON input: {exc}') from exc
    if len(canonical_bytes(case)) > MAX_INPUT_BYTES:
        raise ValidationError('Canonical input exceeds size limit.')
    return validate_case(case)


def normalized_event_facts(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Event facts are read directly from case JSON, never generated by a model."""
    facts = []
    for e in sorted(case['events'], key=lambda x: (datetime.fromisoformat(x['timestamp'].replace('Z', '+00:00')), x['event_id'])):
        facts.append({
            'event_id': e['event_id'], 'timestamp': e['timestamp'], 'channel': e['channel'],
            'verification_result': e['verification_result'], 'replay_flag': e['replay_flag'],
            'liveness_result': e['liveness_result'],
            'available_identifiers': dict(sorted(e['available_identifiers'].items())),
            'source_evidence_refs': [f"{e['event_id']}.{field}" for field in
                                     ('timestamp', 'channel', 'verification_result', 'replay_flag', 'liveness_result')],
        })
    return facts


def identifier_relationships(case: dict[str, Any]) -> list[dict[str, Any]]:
    """Equality of an explicit opaque identifier is evidence of equality of that identifier, NOT identity."""
    entries: dict[tuple[str, str], list[str]] = defaultdict(list)
    for e in case['events']:
        for key, val in e['available_identifiers'].items():
            if isinstance(val, str) and val.strip():
                entries[(key, val)].append(e['event_id'])
    found = []
    for (kind, value), ids in sorted(entries.items()):
        unique_ids = sorted(set(ids))
        if len(unique_ids) >= 2:
            found.append({
                'status': 'shared_identifier_observed', 'identifier_type': kind,
                # Never export identifier value; hash the opaque token instead.
                'identifier_value_sha256': sha256(value.encode('utf-8')),
                'event_ids': unique_ids,
                'evidence_refs': [f'{eid}.available_identifiers.{kind}' for eid in unique_ids],
                'caveat': 'An equal supplied identifier does not prove the same human actor, device ownership, fraud, or intent.',
            })
    return found


def determine_queue(case: dict[str, Any], shared: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deterministic review-only policy; no LLM-assigned scores and no account action."""
    rows: list[dict[str, Any]] = []
    for e in case['events']:
        eid = e['event_id']
        # Priority 1 is reserved; metadata alone is never sufficient for an urgent finding.
        if e['replay_flag'] is True:
            priority, why, collect = 2, 'Replay detector flag; unverified signal.', ['Detector trace and rule version', 'Liveness context']
            refs = [f'{eid}.replay_flag']
        elif e['verification_result'] == 'failed' and e['liveness_result'] in ('failed', 'inconclusive'):
            priority, why, collect = 3, 'Failed verification with failed or inconclusive liveness; requires contextual review.', ['Verification logs', 'Liveness quality metrics']
            refs = [f'{eid}.verification_result', f'{eid}.liveness_result']
        elif e['verification_result'] == 'failed':
            priority, why, collect = 4, 'Failed verification event; no cause inferred.', ['Verification logs', 'Relevant threshold policy']
            refs = [f'{eid}.verification_result']
        else:
            priority, why, collect = 5, 'Routine source event; retain for historical context.', ['Relevant audit event if needed']
            refs = [f'{eid}.verification_result']
        rows.append({'review_priority': priority, 'title': 'Human review of ' + eid,
                     'event_ids': [eid], 'rationale': why, 'evidence_refs': refs,
                     'evidence_to_collect': collect,
                     'safe_action': 'Review source evidence manually; no automated adverse action.'})
    for rel in shared:
        rows.append({'review_priority': 3, 'title': 'Review repeated supplied identifier',
                     'event_ids': rel['event_ids'],
                     'rationale': f"The same non-empty {rel['identifier_type']} token appears in multiple events; identity and intent remain unproven.",
                     'evidence_refs': rel['evidence_refs'], 'evidence_to_collect': ['Confirm identifier provenance and logging semantics'],
                     'safe_action': 'Human review only; no automatic identity or fraud finding.'})
    return sorted(rows, key=lambda x: (x['review_priority'], x['event_ids'], x['title']))


def validate_legacy_advisory(advisory: Any, case: dict[str, Any]) -> None:
    """Require 1.1 schema AND stronger temporal, referential and claim checks."""
    errors = legacy.validate_result(advisory, case)
    if errors:
        raise ValidationError('v1.1 structural validation failed: ' + '; '.join(errors[:12]))
    by_id = {e['event_id']: e for e in case['events']}
    timeline = advisory['timeline']
    event_ids = [row['event_id'] for row in timeline]
    if len(event_ids) != len(set(event_ids)) or set(event_ids) != set(by_id):
        raise ValidationError('Advisory timeline must include every source event exactly once.')
    for row in timeline:
        if row['timestamp'] != by_id[row['event_id']]['timestamp']:
            raise ValidationError(f"Advisory changed timestamp for {row['event_id']}.")
    for section in ('observed_patterns', 'relationship_assessments', 'hypotheses'):
        for i, row in enumerate(advisory[section]):
            refs = row.get('evidence_refs')
            if not isinstance(refs, list) or not refs:
                raise ValidationError(f'{section}[{i}] needs at least one evidence reference.')
            declared_ids = row.get('event_ids')
            if declared_ids is not None:
                if not isinstance(declared_ids, list) or not declared_ids:
                    raise ValidationError(f'{section}[{i}] needs non-empty event_ids.')
                if any(r.split('.', 1)[0] not in declared_ids for r in refs):
                    raise ValidationError(f'{section}[{i}] evidence reference lies outside declared event_ids.')
    for section in ('observed_patterns', 'relationship_assessments', 'hypotheses'):
        for row in advisory[section]:
            if section == 'observed_patterns':
                strings = [row.get('pattern', '')]
            elif section == 'relationship_assessments':
                strings = [row.get('basis', '')]
            else:
                strings = [row.get('hypothesis', ''), row.get('supporting_evidence', '')]
            for string in strings:
                if not isinstance(string, str):
                    raise ValidationError(f'{section} has invalid narrative text.')
                if any(p.search(string) for p in UNSUPPORTED_CERTAINTY):
                    raise ValidationError(f'{section} contains a high-risk unsupported certainty or adverse-action phrase.')
    def scan_strings(value: Any, trail: str = 'advisory') -> None:
        if isinstance(value, str) and any(pattern.search(value) for pattern in UNSUPPORTED_CERTAINTY):
            raise ValidationError(f'{trail} contains high-risk unsupported certainty/adverse-action phrasing.')
        if isinstance(value, dict):
            for key, item in value.items():
                scan_strings(item, f'{trail}.{key}')
        elif isinstance(value, list):
            for i, item in enumerate(value):
                scan_strings(item, f'{trail}[{i}]')
    scan_strings(advisory)
    # Queue is deterministically calculated; model queue is not used. It still must be safe in raw output.
    for row in advisory['investigation_queue']:
        action = row.get('safe_action')
        if not isinstance(action, str) or any(p.search(action) for p in UNSUPPORTED_CERTAINTY):
            raise ValidationError('Model-proposed queue contains an unsafe or invalid action.')


def assemble_dossier(case: dict[str, Any], mode: str, advisory: dict[str, Any] | None = None,
                     meta: dict[str, Any] | None = None) -> dict[str, Any]:
    validate_case(case)
    if mode not in ('offline', 'api'):
        raise ValidationError('mode must be offline or api.')
    if mode == 'api':
        if advisory is None:
            raise ValidationError('An API-mode dossier needs a validated advisory.')
        validate_legacy_advisory(advisory, case)
    elif advisory is not None:
        raise ValidationError('Offline mode must not include an AI advisory.')
    shared = identifier_relationships(case)
    return {
        'schema_version': VERSION, 'case_id': case['case_id'], 'data_classification': 'synthetic_demo_data',
        'generation_mode': mode, 'source_facts_authority': 'supplied_case_metadata_only',
        'policy_version': POLICY_VERSION,
        'event_facts': normalized_event_facts(case),
        'shared_identifiers': shared,
        'linkage_caveat': 'Only matching supplied identifier values are detectable; no shared actor, human identity or fraud is established.',
        'investigation_queue': determine_queue(case, shared),
        'ai_advisory': ({
            'schema_version': advisory['schema_version'],
            'case_summary': advisory['case_summary'],
            'observed_patterns': advisory['observed_patterns'],
            'relationship_assessments': advisory['relationship_assessments'],
            'hypotheses': advisory['hypotheses'],
            'missing_evidence': advisory['missing_evidence'],
            'recommended_next_steps': advisory['recommended_next_steps'],
            'safeguards': advisory['safeguards'],
            'limitations': advisory['limitations'],
            'warning': 'LLM narrative is NOT independently verified against all underlying evidence; human review required.',
        } if advisory is not None else None),
        'model_metadata': {'model': (meta or {}).get('model'), 'api_status': (meta or {}).get('api_status')} if mode == 'api' else None,
        'human_review_required': True, 'automatic_adverse_action_allowed': False,
        'limitations': [
            'Local proof-of-concept; synthetic metadata only. Not integrated with production VoiceID.',
            'Reference validation ensures field existence, not the semantic truth of all AI prose.',
            'Equal supplied opaque identifiers do not establish who controlled an account or device.',
            'Queue priorities are triage policy, not fraud probabilities or automatic decisions.',
        ],
    }


def make_audit(case: dict[str, Any], dossier: dict[str, Any], script_source: bytes,
               legacy_source: bytes) -> dict[str, Any]:
    return {
        'audit_schema_version': '1.0', 'generated_at_utc': utc_now(),
        'case_id': case['case_id'], 'mode': dossier['generation_mode'],
        'input_canonical_sha256': sha256(canonical_bytes(case)),
        'dossier_canonical_sha256': sha256(canonical_bytes(dossier)),
        'sentinel_v1_2_source_sha256': sha256(script_source),
        'legacy_validator_source_sha256': sha256(legacy_source),
        'policy_version': POLICY_VERSION,
        'event_count': len(case['events']), 'queue_count': len(dossier['investigation_queue']),
        'ai_advisory_present': dossier['ai_advisory'] is not None,
        'human_review_required': True,
        'note': 'SHA-256 records integrity of files at creation; not a cryptographic signature or attestation.',
    }


def markdown(dossier: dict[str, Any], audit: dict[str, Any]) -> str:
    out = [f"# VoiceID Sentinel v1.2 — {dossier['case_id']}", '',
           f"- **Mode:** {dossier['generation_mode']}",
           '- **Classification:** synthetic demo data only',
           '- **Decision authority:** source event metadata (never the AI model)',
           '- **Status:** human review required; no automatic adverse action',
           f"- **Policy version:** {POLICY_VERSION}",
           f"- **Generated (UTC):** {audit['generated_at_utc']}", '',
           '## Source-derived event facts', '']
    for e in dossier['event_facts']:
        replay = 'unknown' if e['replay_flag'] is None else str(e['replay_flag']).lower()
        out.append(f"- **{e['timestamp']} | {e['event_id']}** — verification: `{e['verification_result']}`; "
                   f"replay flag: `{replay}`; liveness: `{e['liveness_result']}`; channel: `{e['channel']}`.")
    out += ['', '## Identifier observations', '']
    if dossier['shared_identifiers']:
        for rel in dossier['shared_identifiers']:
            out.append(f"- **{rel['identifier_type']}** shared across {', '.join(rel['event_ids'])}; "
                       'this does not establish a common actor or fraud.')
    else:
        out.append('- No shared non-empty identifier found in supplied metadata; linkage unknown.')
    out += ['', '## Deterministic human-review queue', '']
    for q in dossier['investigation_queue']:
        out += [f"### Priority {q['review_priority']}: {q['title']}",
                f"- **Rationale:** {q['rationale']}",
                f"- **Events:** {', '.join(q['event_ids'])}",
                f"- **Evidence references:** {', '.join(q['evidence_refs'])}",
                '- **Evidence to collect:**']
        out.extend(f'  - {item}' for item in q['evidence_to_collect'])
        out += [f"- **Permitted action:** {q['safe_action']}", '']
    if dossier['ai_advisory'] is not None:
        a = dossier['ai_advisory']
        out += ['## Meta model advisory — NOT independently verified', '',
                '> AI narrative is advisory only. Reference checks cannot certify every natural-language assertion.', '',
                '### Case summary', '', a['case_summary'], '', '### Patterns', '']
        for p in a['observed_patterns']:
            out.append(f"- {p['pattern']} (refs: {', '.join(p['evidence_refs'])})")
        out += ['', '### Hypotheses', '']
        for h in a['hypotheses']:
            out.append(f"- **{h['confidence']} confidence:** {h['hypothesis']} (refs: {', '.join(h['evidence_refs'])})")
        for heading, key in [('Missing evidence', 'missing_evidence'), ('Recommended next steps', 'recommended_next_steps')]:
            out += ['', '### ' + heading, '']
            out.extend('- ' + x for x in a[key])
    else:
        out += ['## AI advisory', '', '- Not requested. This is an offline source-derived dossier.', '']
    out += ['', '## Audit digest', '', f"- Input SHA-256: `{audit['input_canonical_sha256']}`",
            f"- Dossier SHA-256: `{audit['dossier_canonical_sha256']}`", '',
            '## Limitations', '']
    out.extend('- ' + x for x in dossier['limitations'])
    out += ['', '---', '', '**Do not use this report to establish fraud, assign identity, block transactions, or take adverse action automatically.**', '']
    return '\n'.join(out)


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description='VoiceID Sentinel v1.2 — synthetic-metadata-only local investigation.')
    ap.add_argument('input_json', help='Path to synthetic case JSON')
    ap.add_argument('--mode', choices=['offline', 'api'], default='offline', help='offline (default) makes zero API calls')
    ap.add_argument('--model', default=legacy.DEFAULT_MODEL)
    ap.add_argument('--max-output-tokens', type=int, default=3500)
    ap.add_argument('--save-json', default='sentinel_v1_2_dossier.json')
    ap.add_argument('--save-report', default='sentinel_v1_2_report.md')
    ap.add_argument('--save-audit', default='sentinel_v1_2_audit.json')
    ap.add_argument('--save-raw', default='sentinel_v1_2_raw_response.json')
    args = ap.parse_args(argv)
    paths = [Path(args.save_json), Path(args.save_report), Path(args.save_audit)]
    if args.mode == 'api':
        paths.append(Path(args.save_raw))
    resolved = [p.resolve() for p in paths]
    if len(resolved) != len(set(resolved)):
        print('ERROR: Output paths must be distinct.', file=sys.stderr)
        return 2
    if Path(args.input_json).resolve() in set(resolved):
        print('ERROR: Refusing to overwrite the input file.', file=sys.stderr)
        return 2
    try:
        case = load_case(Path(args.input_json))
        advisory, meta = None, None
        if args.mode == 'api':
            if not 500 <= args.max_output_tokens <= 12000:
                raise ValidationError('--max-output-tokens must be 500 to 12000.')
            key = os.environ.get('MODEL_API_KEY', '').strip()
            if not key:
                raise ValidationError('MODEL_API_KEY is not set (never paste the key here).')
            print('Meta API mode requested; sending synthetic case metadata only.')
            try:
                raw, meta = legacy.api_request(key, args.model, case, args.max_output_tokens)
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                raise ValidationError(f'Meta API request failed: {exc}') from exc
            # Untrusted raw response for diagnostics only; never called a validated report.
            atomic_write(Path(args.save_raw), json.dumps(raw, ensure_ascii=False, indent=2).encode('utf-8'))
            if meta.get('api_status') != 'completed':
                raise ValidationError(f"Meta API status was {meta.get('api_status')!r}, not completed.")
            try:
                advisory = json.loads(legacy.extract_text(raw))
            except json.JSONDecodeError as exc:
                raise ValidationError(f'API advisory was not valid JSON: {exc}') from exc
        dossier = assemble_dossier(case, args.mode, advisory, meta)
        audit = make_audit(case, dossier, Path(__file__).read_bytes(), Path(legacy.__file__).read_bytes())
        report = markdown(dossier, audit)
        # All computation and validation completes BEFORE validated artifacts are written.
        atomic_write(Path(args.save_json), json.dumps(dossier, ensure_ascii=False, indent=2).encode('utf-8') + b'\n')
        atomic_write(Path(args.save_report), report.encode('utf-8'))
        atomic_write(Path(args.save_audit), json.dumps(audit, ensure_ascii=False, indent=2).encode('utf-8') + b'\n')
    except (ValidationError, OSError, UnicodeError, TypeError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        print('No new validated dossier was produced by this execution.', file=sys.stderr)
        return 2
    print(f"VoiceID Sentinel v{VERSION} | {case['case_id']} | {len(case['events'])} synthetic events | {args.mode}")
    print(f'Validated dossier: {args.save_json}')
    print(f'Markdown report: {args.save_report}')
    print(f'Audit digest: {args.save_audit}')
    print(f"Review queue: {len(dossier['investigation_queue'])} items | shared identifiers: {len(dossier['shared_identifiers'])}")
    print('PASS: source facts, deterministic queue and SHA-256 audit recorded; human review required.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
