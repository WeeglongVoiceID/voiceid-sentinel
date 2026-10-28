#!/usr/bin/env python3
"""VoiceID Sentinel v1.5 local-only investigation workbench.

Only synthetic event metadata. No production VoiceID integration, no raw voice,
no secret storage. Optional live Meta API requires explicit --enable-meta opt-in.
"""
from __future__ import annotations

import argparse
import copy
import hmac
import json
import os
import secrets
import sys
import threading
import urllib.error
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'engine_v1_2'))
import sentinel_v1_2 as engine  # noqa: E402
import sentinel_v1_1_reference as legacy  # noqa: E402
import report_v1_5 as report  # noqa: E402

MAX_REQUEST = engine.MAX_INPUT_BYTES + 8192
MAX_RESPONSE_BYTES = 2_000_000
CONTENT_TYPES = {'/': 'text/html; charset=utf-8', '/assets/app.css': 'text/css; charset=utf-8',
                 '/assets/app.js': 'text/javascript; charset=utf-8'}
ASSETS = {'/': ROOT / 'index.html', '/assets/app.css': ROOT / 'assets' / 'app.css',
          '/assets/app.js': ROOT / 'assets' / 'app.js'}


class WorkbenchError(ValueError):
    pass


def decode_json(raw: bytes):
    if len(raw) > MAX_REQUEST:
        raise WorkbenchError('Input exceeds the synthetic case size limit.')
    def no_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise WorkbenchError('Duplicate JSON key rejected.')
            result[key] = value
        return result
    try:
        data = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=no_duplicates,
                          parse_constant=lambda x: (_ for _ in ()).throw(WorkbenchError('Non-finite JSON values rejected.')))
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise WorkbenchError('Invalid UTF-8 JSON input.') from exc
    return data


def make_fixture(case):
    """Illustrative *not model-generated* narrative, only for the built-in example case."""
    if engine.sha256(engine.canonical_bytes(case)) != BUILTIN_CASE_HASH:
        raise WorkbenchError('Illustrative preview is available only for the unchanged built-in synthetic case.')
    events = sorted(case['events'], key=lambda ev: (ev['timestamp'], ev['event_id']))
    a,b,c = events
    return {
        'schema_version': '1.1', 'case_id': case['case_id'],
        'case_summary': ('ILLUSTRATIVE SAMPLE, NOT META OUTPUT: Three independent event observations within 12 minutes. '
                         'Two verifications failed; the third passed. No shared identifiers were provided and actor linkage is unknown.'),
        'timeline': [{'event_id': e['event_id'], 'timestamp': e['timestamp'],
                      'summary': 'Illustrative description. Use the source timeline for authoritative values.'} for e in events],
        'observed_patterns': [
            {'pattern':'Two failed verifications precede a later passing verification; sequence alone does not establish a shared actor.',
             'event_ids':[e['event_id'] for e in events],
             'evidence_refs':[f"{a['event_id']}.verification_result",f"{b['event_id']}.verification_result",f"{c['event_id']}.verification_result"]},
            {'pattern':'One source event has a replay detector flag. The flag is not proof of spoofing or intent.',
             'event_ids':[a['event_id']], 'evidence_refs':[f"{a['event_id']}.replay_flag"]}
        ],
        'relationship_assessments':[{'event_ids':[e['event_id'] for e in events], 'relationship_status':'unknown',
            'basis':'No shared non-empty identifiers supplied; timing and channel are insufficient.',
            'evidence_refs':[f"{e['event_id']}.available_identifiers.device_id" for e in events],
            'caveat':'Neither common identity nor distinct actors can be established from the supplied metadata.'}],
        'hypotheses':[{'hypothesis':'The observations may be unrelated; no shared actor is established.',
            'confidence':'low','supporting_evidence':'All supplied device and session references are null.',
            'contrary_or_missing_evidence':'Session/device provenance and detector traces were not supplied.',
            'evidence_refs':[f"{a['event_id']}.available_identifiers.session_id", f"{b['event_id']}.available_identifiers.session_id"]},
            {'hypothesis':'The flagged event merits closer human review, without a fraud conclusion.',
             'confidence':'moderate', 'supporting_evidence':'Replay detector flag is true in the supplied metadata.',
             'contrary_or_missing_evidence':'Detector traces and thresholds were not supplied.',
             'evidence_refs':[f"{a['event_id']}.replay_flag"]}],
        'investigation_queue':[{'review_priority':2,'title':'Human review of detector flag',
            'event_ids':[a['event_id']], 'rationale':'Illustrative queue only, not used for deterministic ordering.',
            'evidence_to_collect':['Detector rule version and trace'],
            'safe_action':'Request human examination of event context.'}],
        'missing_evidence':['Detector trace and confidence thresholds','Opaque device/session provenance and correlation logs'],
        'recommended_next_steps':['Compare documented detector behavior and session provenance under human review.',
                                  'Do not infer a shared actor from time proximity or channel alone.'],
        'safeguards':['No automatic adverse action; source system retains verification authority.'],
        'limitations':['This illustrative preview was authored for display and was NOT generated by Meta AI.'],
    }


BUILTIN_CASE = engine.load_case(ROOT / 'engine_v1_2' / 'sample_multi_event_case.json')
BUILTIN_CASE_HASH = engine.sha256(engine.canonical_bytes(BUILTIN_CASE))


def build_payload(case, mode, *, api_key=None, model=None, max_tokens=3500):
    """Server-side validation and safe assembly; returns JSON-serializable response.

    mode: offline | preview | meta. The browser never receives the API key.
    """
    engine.validate_case(case)
    if len(engine.canonical_bytes(case)) > engine.MAX_INPUT_BYTES:
        raise WorkbenchError('Synthetic case is too large.')
    if mode == 'offline':
        dossier = engine.assemble_dossier(case, 'offline')
        label = 'OFFLINE · SOURCE FACTS ONLY'
        origin = 'none'
        extra = None
    elif mode == 'preview':
        extra = make_fixture(case)
        engine.validate_legacy_advisory(extra, case)
        dossier = engine.assemble_dossier(case, 'offline')
        label = 'ILLUSTRATIVE PREVIEW · NOT META AI'
        origin = 'illustrative_fixture'
    elif mode == 'meta':
        if not api_key:
            raise WorkbenchError('Live Meta mode is disabled or MODEL_API_KEY is not configured.')
        if not 800 <= max_tokens <= 8000:
            raise WorkbenchError('Token limit must be between 800 and 8000.')
        model = model or legacy.DEFAULT_MODEL
        if not isinstance(model, str) or not model or len(model) > 100 or not all(x.isalnum() or x in '._-' for x in model):
            raise WorkbenchError('Invalid model identifier.')
        try:
            raw, meta = legacy.api_request(api_key, model, case, max_tokens)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
            # Intentionally do not return exception details; some providers include request headers in them.
            raise WorkbenchError('Meta request failed. Check internet, API access, model name or credits in the terminal/provider portal.') from None
        if meta.get('api_status') != 'completed':
            raise WorkbenchError('Meta response did not complete; no validated AI advisory was published.')
        try:
            advisory = decode_json(legacy.extract_text(raw).encode('utf-8'))
        except (ValueError, WorkbenchError):
            raise WorkbenchError('Meta returned invalid JSON; no AI advisory was published.') from None
        dossier = engine.assemble_dossier(case, 'api', advisory, meta)
        label = 'LIVE META RESPONSE · STRUCTURALLY VALIDATED'
        origin = 'meta_api'
        extra = None
    else:
        raise WorkbenchError('Unsupported workbench mode.')
    audit = engine.make_audit(case, dossier, Path(engine.__file__).read_bytes(), Path(legacy.__file__).read_bytes())
    displayed_advisory = extra if mode == 'preview' else dossier.get('ai_advisory')
    presentation = report.make_presentation(case, dossier, audit, displayed_advisory, origin)
    return {'dossier': dossier, 'audit': audit, 'advisory_display': displayed_advisory,
            **presentation,
            'advisory_origin': origin, 'mode_label': label,
            'warning': ('Illustrative preview is not Meta output; human review remains necessary.' if mode == 'preview'
                        else 'Validated references do not prove the semantic truth of AI prose; human review is mandatory.'),
            'version':'1.5', 'live_meta_call_made': mode == 'meta'}


class WorkbenchServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    def __init__(self, server_address, handler, *, token, enable_meta=False, key='', model=''):
        super().__init__(server_address, handler)
        self.session_token = token
        self.enable_meta = bool(enable_meta)
        self.model_api_key = key if enable_meta else ''
        self.model_name = model or legacy.DEFAULT_MODEL
        self.meta_lock = threading.Lock()


class WorkbenchHandler(BaseHTTPRequestHandler):
    server_version = 'SentinelLocal/1.5'
    sys_version = ''
    def log_message(self, format, *args):
        # Avoid logging query strings or request bodies; no user secrets in logs.
        print('127.0.0.1 - ' + (format % args).split(' HTTP/')[0][:100], file=sys.stderr)

    def _local_host(self):
        host = self.headers.get('Host', '')
        port = self.server.server_port
        return host in (f'127.0.0.1:{port}', f'localhost:{port}')

    def _send(self, status, data, mime='application/json; charset=utf-8'):
        if isinstance(data, dict):
            raw = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
        elif isinstance(data, bytes):
            raw = data
        else:
            raw = str(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store, max-age=0')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Content-Security-Policy',
                         "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def _authorized(self):
        if not self._local_host():
            return False
        # Reject requests that originate from another site or from non-browser clients
        # which claim a different Origin. Token is required regardless.
        origin = self.headers.get('Origin')
        valid_origins = (f'http://127.0.0.1:{self.server.server_port}',
                         f'http://localhost:{self.server.server_port}')
        if origin and origin not in valid_origins:
            return False
        return hmac.compare_digest(self.headers.get('X-Sentinel-Token', ''), self.server.session_token)

    def do_GET(self):
        path = urlsplit(self.path).path
        if not self._local_host():
            self._send(403, {'error':'Local host restriction.'}); return
        if path == '/api/status':
            if not self._authorized():
                self._send(403, {'error':'Session token required.'}); return
            self._send(200, {'version':'1.5', 'meta_enabled':bool(self.server.enable_meta and self.server.model_api_key),
                             'model':self.server.model_name if self.server.enable_meta else None,
                             'classification':'synthetic_demo_data', 'production_connected':False}); return
        if path == '/api/sample':
            if not self._authorized():
                self._send(403, {'error':'Session token required.'}); return
            self._send(200, {'case':BUILTIN_CASE}); return
        if path in ASSETS:
            try:
                raw = ASSETS[path].read_bytes()
                self._send(200, raw, CONTENT_TYPES[path])
            except OSError:
                self._send(500, {'error':'App asset missing.'})
            return
        self._send(404, {'error':'Not found.'})

    def do_POST(self):
        if urlsplit(self.path).path != '/api/investigate':
            self._send(404, {'error':'Not found.'}); return
        if not self._authorized():
            self._send(403, {'error':'Session token or origin rejected.'}); return
        if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
            self._send(415, {'error':'Only JSON is accepted.'}); return
        raw_length = self.headers.get('Content-Length', '')
        try:
            size = int(raw_length)
        except ValueError:
            self._send(411, {'error':'Content-Length required.'}); return
        if size <= 0 or size > MAX_REQUEST:
            self._send(413, {'error':'JSON input exceeds size limit.'}); return
        try:
            body = decode_json(self.rfile.read(size))
            if not isinstance(body, dict) or set(body) not in ({'case', 'mode'}, {'case_text', 'mode'}):
                raise WorkbenchError('Expected case or case_text together with mode.')
            case = body['case'] if 'case' in body else decode_json(body['case_text'].encode('utf-8')) if isinstance(body['case_text'], str) else None
            mode = body['mode']
            if mode == 'meta' and not self.server.enable_meta:
                raise WorkbenchError('Live Meta calls are disabled. Restart with --enable-meta to opt in.')
            if mode == 'meta':
                if not self.server.meta_lock.acquire(blocking=False):
                    self._send(429, {'error':'A live Meta request is already running.'}); return
                try:
                    result = build_payload(case, mode, api_key=self.server.model_api_key,
                                           model=self.server.model_name)
                finally:
                    self.server.meta_lock.release()
            else:
                result = build_payload(case, mode)
            if len(engine.canonical_bytes(result)) > MAX_RESPONSE_BYTES:
                raise WorkbenchError('Generated dossier exceeds response size limit.')
            self._send(200, result)
        except (WorkbenchError, engine.ValidationError, ValueError, TypeError, OverflowError) as exc:
            self._send(422, {'error':str(exc)[:450]})
        except Exception:
            # Fail-closed; do not disclose raw provider errors, credentials or stack traces.
            self._send(500, {'error':'Internal validation error. No validated dossier published.'})


def main(argv=None):
    p = argparse.ArgumentParser(description='VoiceID Sentinel v1.5 local-only investigation workbench.')
    p.add_argument('--port', type=int, default=8765, help='Local 127.0.0.1 port, default 8765')
    p.add_argument('--enable-meta', action='store_true', help='Allow user-triggered live Meta API calls (synthetic data only)')
    p.add_argument('--model', default=legacy.DEFAULT_MODEL, help='Meta model name (default muse-spark-1.3)')
    p.add_argument('--no-browser', action='store_true', help='Do not automatically launch the default browser')
    args = p.parse_args(argv)
    if args.port < 1024 or args.port > 65535:
        p.error('port must be 1024–65535')
    key = os.environ.get('MODEL_API_KEY', '').strip() if args.enable_meta else ''
    if args.enable_meta and not key:
        print('NOTICE: --enable-meta requested but MODEL_API_KEY is not configured. Offline modes remain available.')
    token = secrets.token_urlsafe(32)
    try:
        server = WorkbenchServer(('127.0.0.1', args.port), WorkbenchHandler, token=token,
                                 enable_meta=args.enable_meta, key=key, model=args.model)
    except OSError as ex:
        print(f'ERROR: Cannot start localhost port {args.port}. Is it already in use? ({ex})', file=sys.stderr)
        return 2
    url = f'http://127.0.0.1:{args.port}/?session={token}'
    print('VoiceID Sentinel v1.5 — local-only synthetic investigation workbench')
    print('No production endpoints. No user data or credentials written to disk by this server.')
    print('Meta mode: ' + ('enabled (explicit button required)' if args.enable_meta and key else 'disabled'))
    print('Open your browser at: ' + url)
    print('Press Ctrl+C in PowerShell to stop the local server.')
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print('\nWorkbench stopped.')
    finally:
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
