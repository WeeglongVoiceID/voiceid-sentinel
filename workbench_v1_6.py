#!/usr/bin/env python3
"""VoiceID Sentinel v1.6 Assurance & Showcase workbench.

Keeps the v1.5 investigation engine unchanged. Adds a scenario gallery,
local fixed-fixture safety exercises, and exported JSON-pair verification.
This is NOT production banking software and has no production connectivity.
"""
from __future__ import annotations
import argparse
import os
import secrets
import sys
import webbrowser
from urllib.parse import urlsplit
import workbench_v1_4 as wb
from showcase_v1_6 import scenario_list, load_scenario
from assurance_v1_6 import run_assurance, validate_export_pair

VERIFY_BODY_LIMIT=1_600_000

class WorkbenchHandlerV16(wb.WorkbenchHandler):
    server_version='SentinelLocal/1.6'

    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/api/status':
            if not self._authorized():
                self._send(403,{'error':'Session token or host/origin rejected.'});return
            self._send(200,{'version':'1.6',
                'meta_enabled':bool(self.server.enable_meta and self.server.model_api_key),
                'model':self.server.model_name if self.server.enable_meta else None,
                'classification':'synthetic_demo_data','production_connected':False,
                'scenario_count':len(scenario_list()),'assurance_mode':'offline-fixed-fixtures'});return
        if path=='/api/showcase':
            if not self._authorized():
                self._send(403,{'error':'Session token or host/origin rejected.'});return
            self._send(200,{'scenarios':scenario_list()});return
        if path.startswith('/api/showcase/'):
            if not self._authorized():
                self._send(403,{'error':'Session token or host/origin rejected.'});return
            slug=path[len('/api/showcase/'):]
            try:self._send(200,{'case':load_scenario(slug),'scenario_id':slug})
            except KeyError:self._send(404,{'error':'Unknown synthetic scenario.'})
            return
        if path=='/api/assurance':
            if not self._authorized():
                self._send(403,{'error':'Session token or host/origin rejected.'});return
            self._send(200,run_assurance());return
        return super().do_GET()

    def do_POST(self):
        path=urlsplit(self.path).path
        if path!='/api/verify':
            return super().do_POST()
        if not self._authorized():
            self._send(403,{'error':'Session token or host/origin rejected.'});return
        if self.headers.get('Content-Type','').split(';')[0].strip().lower()!='application/json':
            self._send(415,{'error':'Only JSON input is accepted.'});return
        try:size=int(self.headers.get('Content-Length',''))
        except ValueError:
            self._send(411,{'error':'Content-Length required.'});return
        if size<=0 or size>VERIFY_BODY_LIMIT:
            self._send(413,{'error':'Verification request exceeds size limit.'});return
        try:
            payload=wb.decode_json(self.rfile.read(size))
            if not isinstance(payload,dict) or set(payload)!={'dossier_text','audit_text'}:
                raise wb.WorkbenchError('Expected dossier_text and audit_text (raw JSON file contents).')
            if not isinstance(payload['dossier_text'],str) or not isinstance(payload['audit_text'],str):
                raise wb.WorkbenchError('Exported files must be UTF-8 JSON text.')
            dossier=wb.decode_json(payload['dossier_text'].encode('utf-8'))
            audit=wb.decode_json(payload['audit_text'].encode('utf-8'))
            result=validate_export_pair(dossier,audit)
            self._send(200,result)
        except (ValueError,TypeError,OverflowError,wb.WorkbenchError) as exc:
            self._send(422,{'error':str(exc)[:240]})
        except Exception:
            self._send(500,{'error':'Verification failed closed. No verified result published.'})


def main(argv=None):
    p=argparse.ArgumentParser(description='VoiceID Sentinel v1.6 — local synthetic-only demo and assurance lab')
    p.add_argument('--port',type=int,default=8765)
    p.add_argument('--enable-meta',action='store_true',help='Explicitly allow live synthetic-only Meta calls')
    p.add_argument('--model',default=wb.legacy.DEFAULT_MODEL)
    p.add_argument('--no-browser',action='store_true')
    args=p.parse_args(argv)
    if not 1024<=args.port<=65535:p.error('port must be between 1024 and 65535')
    key=os.getenv('MODEL_API_KEY','').strip() if args.enable_meta else ''
    if args.enable_meta and not key:
        print('NOTICE: Meta API key is absent. Offline-only modes remain available.')
    token=secrets.token_urlsafe(32)
    try:
        srv=wb.WorkbenchServer(('127.0.0.1',args.port),WorkbenchHandlerV16,
                               token=token,enable_meta=args.enable_meta,key=key,model=args.model)
    except OSError as exc:
        print(f'ERROR: localhost port {args.port} unavailable. Stop the older server first. ({exc})',file=sys.stderr)
        return 2
    url=f'http://127.0.0.1:{args.port}/?session={token}'
    print('VoiceID Sentinel v1.6 | Local-only synthetic investigation / assurance workbench')
    print('Scenario gallery: 3 invented cases. Safeguard lab: fixed offline checks.')
    print('No production VoiceID endpoints; no real customer or biometric data permitted.')
    print('Live Meta calls: '+('enabled with separate consent' if args.enable_meta and key else 'disabled'))
    print('OPEN THIS LOCAL BROWSER ADDRESS (do not share its session token): '+url)
    print('Ctrl+C to stop server.')
    if not args.no_browser:webbrowser.open(url)
    try:srv.serve_forever(poll_interval=.3)
    except KeyboardInterrupt:print('\nWorkbench stopped.')
    finally:srv.server_close()
    return 0

if __name__=='__main__':raise SystemExit(main())
