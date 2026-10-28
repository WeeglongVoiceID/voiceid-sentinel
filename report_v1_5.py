#!/usr/bin/env python3
"""VoiceID Sentinel v1.5 presentation and export policy (offline, deterministic).

Never changes the SHA-256-bound v1.2 dossier or audit. Does not make network calls.
The model's original validated advisory remains separately in the dossier JSON.
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

REPORT_VERSION = 'sentinel-report-1.5.0'


def executive_summary(dossier: dict[str, Any]) -> str:
    """Generate only facts from the authoritative, source-derived dossier."""
    facts = dossier['event_facts']
    n = len(facts)
    passed = sum(event['verification_result'] == 'passed' for event in facts)
    failed = sum(event['verification_result'] == 'failed' for event in facts)
    flagged = sum(event['replay_flag'] is True for event in facts)
    channels = sorted({event['channel'] for event in facts})
    if n > 1:
        start = datetime.fromisoformat(facts[0]['timestamp'].replace('Z', '+00:00'))
        end = datetime.fromisoformat(facts[-1]['timestamp'].replace('Z', '+00:00'))
        minutes = (end - start).total_seconds() / 60
        time_phrase = f' within {minutes:g} minutes' if minutes >= 0 else ''
    else:
        time_phrase = ''
    channel_phrase = ' on one reported channel' if len(channels) == 1 else f' across {len(channels)} reported channels'
    s = (f'{n} synthetic authentication ' + ('event' if n == 1 else 'events') + time_phrase + channel_phrase + ': '
         + f'{failed} failed verification' + ('' if failed == 1 else 's')
         + f', {passed} passed verification' + ('' if passed == 1 else 's')
         + f', and {flagged} replay detector flag' + ('' if flagged == 1 else 's') + '. ')
    if dossier['shared_identifiers']:
        s += ('Matching non-empty opaque identifier values occur across some events. '
              'Such matches do not establish who controlled the events or prove fraud. ')
    else:
        s += ('No matching non-empty identifier values link the events in the supplied metadata. '
              'A common actor, device or session has not been established. ')
    s += ('Retain all source events, including failures before any success. '
          'Review detector signals and permitted existing system logs with a human investigator. '
          'There is no basis in these metadata alone for an automated adverse action or a definitive fraud finding.')
    return s


def privacy_steps() -> list[str]:
    """Approved synthetic-demo guidance, independent of model recommendations."""
    return [
        'Preserve the existing source event decisions and the dossier/audit hashes; a later successful result does not erase earlier failures.',
        'Review existing authorized detector configuration, liveness/replay decision logs, and documented thresholds under access-controlled human review.',
        'Where approved and necessary, check existing opaque session/device correlation metadata; never infer a shared person merely from timing or channel.',
        'Use minimum-necessary access, established retention policies and an authorized human investigator. Do not collect raw voice recordings, biometric templates, or real customer records for this synthetic demonstration.',
        'Escalate any proposed collection of sensitive evidence through separately approved legal, privacy, security and retention procedures; do not automatically block or accuse anyone.',
    ]


def md_text(value: Any) -> str:
    """Escape arbitrary LLM prose when placed in a Markdown report."""
    text = str(value)
    text = text.replace('\\', '\\\\')
    for char in ('`', '*', '_', '[', ']', '#', '<', '>', '|'):
        text = text.replace(char, '\\' + char)
    return text.replace('\r', ' ').replace('\n', ' ')


def report_markdown(dossier: dict[str, Any], audit: dict[str, Any],
                    advisory: dict[str, Any] | None, origin: str) -> str:
    n = len(dossier['event_facts'])
    provenance = {'meta_api': 'LIVE META API — validated structure/references, not truth of prose',
                  'illustrative_fixture': 'ILLUSTRATIVE PREVIEW — hand-authored, NOT Meta AI',
                  'none': 'OFFLINE — no AI advisory requested'}[origin]
    lines = [
        '# VoiceID Sentinel v1.5 — Investigation Review Report', '',
        f"**Case:** `{dossier['case_id']}`  ",
        '**Data classification:** synthetic demonstration metadata only  ',
        f'**Source event count:** {n}  ',
        f'**AI provenance:** {provenance}  ',
        f"**Review policy:** `{dossier['policy_version']}`  ",
        f"**Generated (UTC):** {audit['generated_at_utc']}  ",
        '**Decision authority:** source observations + local deterministic triage; AI is advisory only  ',
        '**Required:** human review; no automatic adverse action', '',
        '## Executive conclusion — deterministic source-derived', '',
        executive_summary(dossier), '',
        '## Source event timeline — not model-generated', '',
        '| Event | Timestamp | Verification | Liveness | Replay detector |',
        '|---|---|---|---|---|',
    ]
    for event in dossier['event_facts']:
        replay = 'flagged' if event['replay_flag'] is True else 'not flagged' if event['replay_flag'] is False else 'unknown'
        lines.append(f"| `{event['event_id']}` | `{event['timestamp']}` | "
                     f"{event['verification_result']} | {event['liveness_result']} | {replay} |")
    lines += ['', '## Deterministic investigation queue', '']
    for row in dossier['investigation_queue']:
        lines += [f"### Priority {row['review_priority']}: {md_text(row['title'])}", '',
                  f"**Events:** {', '.join('`'+eid+'`' for eid in row['event_ids'])}  ",
                  f"**Rationale:** {md_text(row['rationale'])}  ",
                  f"**Human-only action:** {md_text(row['safe_action'])}", '',
                  '**Source references:** ' + ', '.join('`'+ref+'`' for ref in row['evidence_refs']), '']
    lines += ['## Privacy-first review plan — deterministic local policy', '']
    lines.extend(f'{i}. {step}' for i, step in enumerate(privacy_steps(), 1))
    lines += ['', '## AI advisory (separate from authoritative facts)', '',
              f'**Provenance:** {provenance}', '',
              '**Caution:** The system checks structural and source-field references, not the factual truth of every model claim. '
              'Model-suggested evidence collection is not automatically authorized.', '']
    if advisory:
        lines += ['### Model case summary — unverified interpretation', '', md_text(advisory['case_summary']), '',
                  '### Observed patterns — unverified interpretation', '']
        for pattern in advisory.get('observed_patterns', []):
            lines += [f"- {md_text(pattern['pattern'])}",
                      '  - References: ' + ', '.join('`'+ref+'`' for ref in pattern.get('evidence_refs', []))]
        lines += ['', '### Relationship assessments — unverified interpretation', '']
        for relationship in advisory.get('relationship_assessments', []):
            lines += [f"- **{md_text(relationship['relationship_status'])}:** {md_text(relationship['basis'])}",
                      '  - References: ' + ', '.join('`'+ref+'`' for ref in relationship.get('evidence_refs', [])),
                      '  - Caveat: ' + md_text(relationship['caveat'])]
        lines += ['', '### Hypotheses — advisory only', '']
        for hypothesis in advisory.get('hypotheses', []):
            lines += [f"- **{md_text(hypothesis['confidence'])} confidence:** {md_text(hypothesis['hypothesis'])}",
                      '  - References: ' + ', '.join('`'+ref+'`' for ref in hypothesis.get('evidence_refs', [])),
                      '  - Missing/contrary evidence: ' + md_text(hypothesis.get('contrary_or_missing_evidence', ''))]
        lines += ['', '**Model-recommended evidence requests are deliberately not reproduced here as approved actions.** '
                  'The original advisory, including its suggestions, is preserved in the JSON dossier for controlled review '
                  '(in illustrative mode, it is a hand-authored preview and not part of the dossier).', '']
    else:
        lines += ['No model advisory was requested.', '']
    lines += [
        '## Integrity record — not a digital signature', '',
        f"- **Dossier SHA-256:** `{audit['dossier_canonical_sha256']}`",
        f"- **Input SHA-256:** `{audit['input_canonical_sha256']}`",
        '- These fingerprints cover their respective canonical JSON objects, **not this Markdown report**.',
        '- No cryptographic signature, source attestation or chain-of-custody certification is claimed.', '',
        '## Release limitations', '',
        '- Local prototype only; synthetic/anonymized test metadata; no VoiceID production connectivity.',
        '- Data classification is supplied by the user and cannot by itself prove that input is synthetic.',
        '- Neither verified human identity nor fraud is established by an identifier match, timing, or detector flags.',
        '- A human must independently assess any Meta narrative and authorize any additional evidence access.', '',
        '---', '',
        '**Human investigator review required. No automated fraud finding, identity assignment, or adverse action.**', '',
    ]
    return '\n'.join(lines)


def make_presentation(case: dict[str, Any], dossier: dict[str, Any], audit: dict[str, Any],
                      displayed_advisory: dict[str, Any] | None, origin: str) -> dict[str, Any]:
    # The case is already strictly validated by the engine before this is called.
    text = report_markdown(dossier, audit, displayed_advisory, origin)
    return {
        'executive_summary': executive_summary(dossier),
        'privacy_review_steps': privacy_steps(),
        'report_markdown': text,
        'report_markdown_sha256': hashlib.sha256(text.encode('utf-8')).hexdigest(),
        'report_version': REPORT_VERSION,
        'report_note': 'Report hash is an informational digest. Dossier audit SHA-256 covers the dossier JSON only.',
    }
