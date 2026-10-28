#!/usr/bin/env python3
"""VoiceID Sentinel v1.3: generate an offline standalone HTML dashboard from audited v1.2 data.
Only synthetic metadata. No servers, remote scripts, cookies, API calls or biometric data.
"""
import argparse
import hashlib
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path

MAX_FILE_SIZE = 2_000_000
IDENTIFIER_KEYS = {'device_id', 'session_id', 'subject_ref'}
ALLOWED_RESULT = {'passed', 'failed', 'inconclusive', 'unavailable', 'unknown'}

class DashboardError(ValueError):
    pass


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode('utf-8')


def sha(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def load(path):
    if path.stat().st_size > MAX_FILE_SIZE:
        raise DashboardError(f'Input too large: {path.name}')
    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise DashboardError(f'Duplicate JSON key: {k}')
            out[k] = v
        return out
    try:
        return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique,
                          parse_constant=lambda value: (_ for _ in ()).throw(DashboardError(f'Invalid number: {value}')))
    except (OSError, UnicodeError, json.JSONDecodeError) as ex:
        raise DashboardError(f'Unable to read {path.name}: {ex}') from ex


def verify(dossier, audit):
    if not isinstance(dossier, dict) or not isinstance(audit, dict):
        raise DashboardError('Expected JSON objects')
    if dossier.get('schema_version') != '1.2':
        raise DashboardError('Only audited v1.2 dossiers are supported')
    if dossier.get('data_classification') != 'synthetic_demo_data':
        raise DashboardError('Dashboard restricted to declared synthetic demo data')
    if not isinstance(dossier.get('case_id'), str) or not dossier['case_id'] or len(dossier['case_id']) > 120:
        raise DashboardError('Invalid case identifier')
    if dossier.get('human_review_required') is not True or dossier.get('automatic_adverse_action_allowed') is not False:
        raise DashboardError('Required human-review safeguards missing')
    if not re.fullmatch('[0-9a-f]{64}', str(audit.get('dossier_canonical_sha256', ''))):
        raise DashboardError('Missing audit dossier fingerprint')
    if audit['dossier_canonical_sha256'] != sha(dossier):
        raise DashboardError('Dossier content does not match its audit SHA-256 fingerprint')
    if audit.get('case_id') != dossier['case_id'] or audit.get('mode') != dossier.get('generation_mode'):
        raise DashboardError('Dossier/audit identification mismatch')
    if audit.get('human_review_required') is not True:
        raise DashboardError('Audit review safeguard missing')
    if audit.get('ai_advisory_present') is not (dossier.get('ai_advisory') is not None):
        raise DashboardError('Audit/model presence mismatch')
    if audit.get('policy_version') != dossier.get('policy_version'):
        raise DashboardError('Policy version mismatch')
    events = dossier.get('event_facts')
    queue = dossier.get('investigation_queue')
    if not isinstance(events, list) or not events or len(events) > 500 or not isinstance(queue, list):
        raise DashboardError('Missing/invalid event facts or queue')
    if audit.get('event_count') != len(events) or audit.get('queue_count') != len(queue):
        raise DashboardError('Audit event or queue count mismatch')
    ids = set()
    expected = {'event_id', 'timestamp', 'channel', 'verification_result', 'replay_flag', 'liveness_result', 'available_identifiers', 'source_evidence_refs'}
    for event in events:
        if not isinstance(event, dict) or set(event) != expected:
            raise DashboardError('Unexpected or missing event fact fields')
        ident = event['event_id']
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', ident) or ident in ids:
            raise DashboardError('Invalid/duplicate event identifier')
        ids.add(ident)
        try:
            datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
        except (TypeError, ValueError, AttributeError):
            raise DashboardError(f'Invalid timestamp for {ident}')
        if not all(isinstance(event.get(k), str) for k in ['channel', 'verification_result', 'liveness_result']):
            raise DashboardError('Invalid event field type')
        if event['verification_result'] not in ALLOWED_RESULT or event['liveness_result'] not in ALLOWED_RESULT:
            raise DashboardError('Unsupported event result')
        if event['replay_flag'] is not None and not isinstance(event['replay_flag'], bool):
            raise DashboardError('Invalid replay flag')
        identifiers = event['available_identifiers']
        if not isinstance(identifiers, dict) or not set(identifiers).issubset(IDENTIFIER_KEYS):
            raise DashboardError('Unexpected identifier fields')
        if any(v is not None and not isinstance(v, str) for v in identifiers.values()):
            raise DashboardError('Invalid identifier field')
        refs = event['source_evidence_refs']
        if not isinstance(refs, list) or not refs or any(not isinstance(r, str) or not r.startswith(ident + '.') for r in refs):
            raise DashboardError('Invalid source event evidence references')
    for item in queue:
        if not isinstance(item, dict) or type(item.get('review_priority')) is not int or item['review_priority'] not in range(1, 6):
            raise DashboardError('Invalid queue priority')
        ev_ids = item.get('event_ids')
        if not isinstance(ev_ids, list) or not ev_ids or any(i not in ids for i in ev_ids):
            raise DashboardError('Queue contains unknown event')
        for key in ('title', 'rationale', 'safe_action'):
            if not isinstance(item.get(key), str):
                raise DashboardError('Invalid queue text')
        for key in ('evidence_refs', 'evidence_to_collect'):
            if not isinstance(item.get(key), list) or any(not isinstance(r, str) for r in item[key]):
                raise DashboardError('Invalid queue list')
        for ref in item['evidence_refs']:
            parts = ref.split('.')
            if len(parts) < 2 or parts[0] not in ids:
                raise DashboardError('Queue evidence references unavailable event')
            target = next(ev for ev in events if ev['event_id'] == parts[0])
            for segment in parts[1:]:
                if not isinstance(target, dict) or segment not in target:
                    raise DashboardError('Queue evidence references unavailable field')
                target = target[segment]
    shared = dossier.get('shared_identifiers', [])
    if not isinstance(shared, list):
        raise DashboardError('Invalid shared identifiers')
    # Do not render free-form AI/advisory text or supplied identifier values in demo HTML.
    return events, queue, shared


def esc(obj):
    return html.escape(str(obj), quote=True)


def status(value):
    s = str(value).lower()
    klass = 'pass' if s == 'passed' else 'fail' if s == 'failed' else 'warn'
    return f'<span class="pill {klass}">{esc(s)}</span>'


def build(dossier, audit):
    events, queue, shared = verify(dossier, audit)
    ordered = sorted(events, key=lambda e: (e['timestamp'], e['event_id']))
    failed = sum(e['verification_result'] == 'failed' for e in events)
    passed = sum(e['verification_result'] == 'passed' for e in events)
    replay = sum(e['replay_flag'] is True for e in events)
    case_id = esc(dossier['case_id'])
    rows = []
    for event in ordered:
        ev = esc(event['event_id'])
        ts = esc(event['timestamp'].replace('T', ' ').replace('Z', ' UTC'))
        replay_label = 'Flagged' if event['replay_flag'] is True else 'Not flagged' if event['replay_flag'] is False else 'Unavailable'
        refs = ''.join(f'<code>{esc(x)}</code>' for x in event['source_evidence_refs'])
        rows.append(f'''<div class="event" id="{ev}"><div class="event-rail"><span class="event-dot"></span></div>
          <div class="event-body"><div class="event-top"><strong>{ev}</strong><time>{ts}</time></div>
          <div class="event-status"><span>Verification {status(event['verification_result'])}</span><span>Liveness {status(event['liveness_result'])}</span><span>Replay <b>{replay_label}</b></span></div>
          <details><summary>Inspect source evidence references</summary><div class="ref-grid">{refs}</div></details></div></div>''')
    qitems = []
    for ix, item in enumerate(sorted(queue, key=lambda x: (x['review_priority'], x['title'])), 1):
        qrefs = ''.join(f'<code>{esc(v)}</code>' for v in item['evidence_refs'])
        collect = ''.join(f'<li>{esc(v)}</li>' for v in item['evidence_to_collect'])
        qitems.append(f'''<article class="queue-card"><div class="queue-card-top"><span class="queue-index">{ix:02}</span><span class="priority p{item['review_priority']}">Priority {item['review_priority']}</span></div>
          <h3>{esc(item['title'])}</h3><p>{esc(item['rationale'])}</p>
          <div class="micro">Relevant events: {', '.join('<a href="#'+esc(e)+'">'+esc(e)+'</a>' for e in item['event_ids'])}</div>
          <details><summary>Evidence and recommended collection</summary><div class="ref-grid">{qrefs}</div><ul>{collect}</ul></details>
          <div class="safe"><span aria-hidden="true">✓</span> {esc(item['safe_action'])}</div></article>''')
    advisory = dossier.get('ai_advisory') is not None
    mode = 'Model advisory attached — not a decision' if advisory else 'Offline source-derived mode'
    digest = esc(audit['dossier_canonical_sha256'])
    input_hash = esc(audit.get('input_canonical_sha256', 'unavailable'))
    policy = esc(dossier.get('policy_version', 'unspecified'))
    generated = esc(audit.get('generated_at_utc', 'unspecified'))
    limitations = ''.join(f'<li>{esc(v)}</li>' for v in dossier.get('limitations', []) if isinstance(v,str))
    markup = '''<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; object-src 'none'"><title>VoiceID Sentinel — Investigation Dashboard</title><style>
:root{color-scheme:dark;--bg:#060e1d;--panel:#0d1b30;--panel2:#101f36;--line:#213852;--gold:#e7b962;--cyan:#59d3dd;--muted:#9cb1c4;--white:#eff7ff}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:radial-gradient(ellipse at 78% -12%,#163351 0%,transparent 52%),var(--bg);color:var(--white);font:15px/1.56 'Segoe UI',Inter,system-ui,sans-serif}a{color:var(--cyan);text-decoration:none}a:hover{text-decoration:underline}.wrap{max-width:1250px;margin:auto;padding:0 28px}.header{border-bottom:1px solid var(--line);background:#071324a8}.header .wrap{min-height:82px;display:flex;align-items:center;gap:16px}.logo{border:2px solid var(--gold);color:var(--gold);font-weight:800;letter-spacing:-1px;font-size:23px;width:44px;height:44px;display:grid;place-items:center;clip-path:polygon(25% 4%,75% 4%,100% 50%,75% 96%,25% 96%,0 50%)}.brand{font-weight:800;font-size:18px;letter-spacing:.01em}.brand small{display:block;color:var(--muted);font-size:10px;letter-spacing:.16em;font-weight:600}.header-state{margin-left:auto;white-space:nowrap;border:1px solid #2e786e;background:#10352f;color:#a4eed9;border-radius:100px;padding:6px 13px;font-size:12px}.hero{padding-top:47px;padding-bottom:18px}.eyebrow{text-transform:uppercase;color:var(--gold);letter-spacing:.19em;font-weight:800;font-size:11px}.hero h1{font-size:clamp(29px,4vw,46px);line-height:1.12;margin:12px 0 12px;letter-spacing:-.03em}.subtitle{color:var(--muted);max-width:760px;margin:0 0 24px}.meta{display:flex;gap:12px;flex-wrap:wrap}.meta span{border:1px solid var(--line);border-radius:8px;padding:8px 12px;color:#c0d0de;font-size:12px}.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;padding-top:15px;padding-bottom:25px}.stat{border:1px solid var(--line);background:linear-gradient(155deg,#13263e,#0a192c);padding:21px 19px;border-radius:14px}.stat .val{font-size:35px;line-height:1.08;font-weight:800;letter-spacing:-.025em}.stat .lab{font-size:12px;color:var(--muted);margin-top:9px}.stat.highlight .val{color:var(--gold)}.stat.cyan .val{color:var(--cyan)}.notice{border-left:3px solid var(--gold);background:#2a251c;padding:14px 18px;border-radius:0 9px 9px 0;margin-bottom:28px;font-size:13px;color:#f5dcb5}.columns{display:grid;grid-template-columns:1.05fr .95fr;gap:24px;padding-bottom:30px}.panel{background:#0b192a;border:1px solid var(--line);border-radius:14px;padding:25px;min-width:0}.panel h2{margin:0 0 5px;font-size:19px}.desc{font-size:12px;color:var(--muted);margin:0 0 25px}.event{display:flex;gap:15px}.event-rail{width:17px;flex:0 0 17px;border-right:1px solid #315270;position:relative;margin-right:4px}.event:last-child .event-rail{border-right-color:transparent}.event-dot{position:absolute;right:-7px;top:6px;background:var(--cyan);border:4px solid #0c2436;width:13px;height:13px;border-radius:50%;box-shadow:0 0 0 1px var(--cyan)}.event-body{flex:1;padding:0 0 28px;min-width:0}.event-top{display:flex;gap:8px;justify-content:space-between;flex-wrap:wrap;margin-bottom:13px}.event-top strong{font-size:13px}.event-top time{font-size:11px;color:var(--muted)}.event-status{display:flex;gap:8px;flex-wrap:wrap}.event-status>span{font-size:11px;background:#142941;border-radius:7px;padding:7px 9px;color:#c7d5e3}.event-status b{color:var(--gold);font-weight:600}.pill{display:inline-block;padding:0 6px;border-radius:5px;font-weight:700}.pill.pass{color:#8ee5c6}.pill.fail{color:#ffa5a9}.pill.warn{color:#f1cc80}details{margin-top:15px;border-top:1px solid #213850;padding-top:10px}summary{cursor:pointer;color:var(--cyan);font-size:12px;user-select:none}.ref-grid{margin-top:10px;display:flex;flex-wrap:wrap;gap:6px}code{font-size:10px;color:#b7dce4;padding:5px 7px;border:1px solid #24455c;border-radius:5px;background:#112638;overflow-wrap:anywhere}.queue-card{background:#102239;border:1px solid #264059;padding:16px;border-radius:11px;margin-bottom:12px}.queue-card:last-child{margin-bottom:0}.queue-card-top{display:flex;justify-content:space-between;align-items:center}.queue-index{color:#728ca7;font-size:11px}.priority{font-size:10px;letter-spacing:.04em;text-transform:uppercase;border:1px solid #795f36;color:#e9bf7c;border-radius:20px;padding:3px 10px}.priority.p5{border-color:#486078;color:#bbc9d8}.queue-card h3{font-size:14px;margin:12px 0 4px}.queue-card p{color:#c6d3e1;font-size:12px;margin:0 0 12px}.micro{color:#8ca9c4;font-size:11px}.micro a{margin-right:4px}.queue-card ul{font-size:12px;color:#c1d0dd;padding-left:18px}.safe{margin-top:12px;font-size:11px;color:#8ed7b3}.section{padding-bottom:45px}.digest-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.digest{background:#102239;border:1px solid #274159;padding:14px;border-radius:9px}.digest .small{color:var(--muted);font-size:11px;letter-spacing:.05em;text-transform:uppercase}.digest code{display:block;margin-top:10px;overflow-wrap:anywhere;font-size:11px;line-height:1.6}.disclaimer{font-size:12px;color:#9ab0c2;line-height:1.8}.disclaimer li{margin:5px 0}.footer{border-top:1px solid var(--line);padding:24px 0 37px;color:#8ca6bd;font-size:11px}.footer .wrap{display:flex;justify-content:space-between;gap:15px;flex-wrap:wrap}@media(max-width:1000px){.stats{grid-template-columns:repeat(3,1fr)}.columns{grid-template-columns:1fr}}@media(max-width:620px){.wrap{padding:0 15px}.stats{grid-template-columns:repeat(2,1fr)}.stat{padding:15px}.stat .val{font-size:28px}.header-state{display:none}.panel{padding:16px}.digest-grid{grid-template-columns:1fr}.hero{padding-top:28px}}@media print{body{background:white;color:#0c2238;font-size:11px}.header,.panel,.stat,.digest{background:white;color:#0c2238}.panel,.stat,.digest{border-color:#ccc}.subtitle,.desc,.stat .lab,.disclaimer{color:#333}.notice{color:#333;background:#fff8e7}.columns{display:block}.panel{break-inside:avoid;margin-bottom:16px}.footer{display:none}.queue-card{background:white;color:#0c2238;break-inside:avoid}.queue-card p{color:#333}details{display:none}}
</style></head><body><header class="header"><div class="wrap"><span class="logo" aria-hidden="true">W</span><div class="brand">Weeglong AI™ <small>VOICEID SENTINEL / INVESTIGATION INTELLIGENCE</small></div><span class="header-state">● Human review required</span></div></header>
<main><section class="wrap hero"><div class="eyebrow">Enterprise voice biometric and forensic intelligence platform</div><h1>Investigation Command Center</h1><p class="subtitle">Evidence-grounded authentication event review. Source metadata remains authoritative; AI commentary cannot override biometric decisions.</p><div class="meta"><span>CASE · {{CASE}}</span><span>{{MODE}}</span><span>POLICY · {{POLICY}}</span><span>Generated {{GENERATED}}</span></div></section>
<section class="wrap stats" aria-label="Case metrics"><div class="stat cyan"><div class="val">{{EVENT_COUNT}}</div><div class="lab">Source events</div></div><div class="stat"><div class="val">{{PASS_COUNT}}</div><div class="lab">Passed verification</div></div><div class="stat"><div class="val">{{FAIL_COUNT}}</div><div class="lab">Failed verification</div></div><div class="stat highlight"><div class="val">{{REPLAY_COUNT}}</div><div class="lab">Replay flags for review</div></div><div class="stat"><div class="val">{{LINK_COUNT}}</div><div class="lab">Shared identifier signals</div></div></section>
<div class="wrap"><div class="notice"><strong>Investigative safeguard.</strong> Detector flags and failed verifications are not proof of fraud or identity. No automatic adverse action is permitted. All recommendations require human assessment.</div></div>
<section class="wrap columns"><div class="panel"><h2>Event timeline</h2><p class="desc">Chronological facts copied from the validated source dossier</p>{{EVENTS}}</div><div class="panel"><h2>Investigation queue</h2><p class="desc">Deterministic review policy · lower priority number means earlier review, not higher fraud probability</p>{{QUEUE}}</div></section>
<section class="wrap section"><div class="panel"><h2>Evidence integrity & audit</h2><p class="desc">SHA-256 fingerprints were checked against the supplied dossier before dashboard generation. This is not a digital signature.</p><div class="digest-grid"><div class="digest"><div class="small">Dossier SHA-256 · verified match</div><code>{{DIGEST}}</code></div><div class="digest"><div class="small">Original input SHA-256 · recorded</div><code>{{INPUT_HASH}}</code></div></div><p class="disclaimer">Model commentary status: {{AI_STATUS}}. Identifier values and free-form AI narrative are deliberately withheld from this demonstration dashboard.</p><ul class="disclaimer">{{LIMITATIONS}}</ul></div></section></main><footer class="footer"><div class="wrap"><span>WEEGLONG AI™ · VOICEID SENTINEL · SYNTHETIC DEMONSTRATION ONLY</span><span>Offline generated / no live customer data / no production connectivity</span></div></footer></body></html>'''
    replacements = {
        'CASE':case_id,'MODE':esc(mode),'POLICY':policy,'GENERATED':generated,
        'EVENT_COUNT':str(len(events)),'PASS_COUNT':str(passed),'FAIL_COUNT':str(failed),
        'REPLAY_COUNT':str(replay),'LINK_COUNT':str(len(shared)),
        'EVENTS': '\n'.join(rows),'QUEUE':'\n'.join(qitems),'DIGEST':digest,
        'INPUT_HASH':input_hash,'AI_STATUS': 'present as separately validated advisory' if advisory else 'not requested (offline)',
        'LIMITATIONS':limitations,
    }
    for key,value in replacements.items():
        markup = markup.replace('{{'+key+'}}', value)
    return markup


def main(argv=None):
    p = argparse.ArgumentParser(description='Generate offline VoiceID Sentinel investigation dashboard (synthetic metadata only)')
    p.add_argument('--dossier', required=True, type=Path)
    p.add_argument('--audit', required=True, type=Path)
    p.add_argument('--output', default='voiceid_sentinel_dashboard.html', type=Path)
    args=p.parse_args(argv)
    try:
        dossier = load(args.dossier)
        audit = load(args.audit)
        page = build(dossier, audit)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(page, encoding='utf-8')
    except (DashboardError, OSError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1
    print(f'PASS: dashboard generated from verified synthetic v1.2 dossier: {args.output}')
    print(f'Events: {len(dossier["event_facts"])} | Review items: {len(dossier["investigation_queue"])} | Live API calls: 0')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
