#!/usr/bin/env python3
"""Local-only Google OAuth bootstrap and dedicated CAL calendar setup."""
import argparse
import base64
import hashlib
import json
import secrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs, quote
from urllib.request import Request, urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from Sources.calendar_domain.google_calendar import SCOPE, GoogleClient, GoogleError, private_json, event_body
from uuid import uuid4

ROOT=Path('/Users/us/Tools/LocalData/Calendar_Local')


def authorize(root):
    credentials=json.loads((root/'settings/google-client.json').read_text())['installed']
    state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)
    received={}
    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            values=parse_qs(urlparse(self.path).query)
            valid=values.get('state')==[state] and bool(values.get('code'))
            if valid:received['code']=values['code'][0]
            self.send_response(200 if valid else 400);self.end_headers()
            self.wfile.write(b'CAL authorization received. You may close this window.' if valid else b'Authorization failed. Return to the terminal.')
        def log_message(self,*args):pass
    with HTTPServer(('127.0.0.1',0),Callback) as server:
        server.timeout=300
        redirect='http://127.0.0.1:'+str(server.server_port)+'/'
        challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
        query=urlencode(dict(client_id=credentials['client_id'],redirect_uri=redirect,response_type='code',scope=SCOPE,
                             access_type='offline',prompt='consent',state=state,code_challenge=challenge,code_challenge_method='S256'))
        if not webbrowser.open('https://accounts.google.com/o/oauth2/v2/auth?'+query):raise ValueError('browser_open_failed')
        print('Google画面で対象アカウントとCALの権限を確認してください。',flush=True)
        server.handle_request()
    if 'code' not in received:raise ValueError('authorization_not_received')
    data=urlencode(dict(code=received['code'],client_id=credentials['client_id'],client_secret=credentials.get('client_secret',''),
                        redirect_uri=redirect,grant_type='authorization_code',code_verifier=verifier)).encode()
    with urlopen(Request('https://oauth2.googleapis.com/token',data=data),timeout=20) as response:token=json.load(response)
    if not token.get('refresh_token'):raise ValueError('refresh_token_missing')
    private_json(root/'settings/google-token.json',dict(refresh_token=token['refresh_token']))
    # Token-only placeholder; create-calendar replaces it with the confirmed ID.
    if not (root/'settings/google-calendar.json').exists():private_json(root/'settings/google-calendar.json',{})
    print('認証をprivate localに保存しました。')


def create_calendar(root):
    client=GoogleClient(root)
    if client.config.get('calendar_id'):raise ValueError('calendar_already_configured')
    # Do not adopt a same-name existing calendar. An unknown outcome must be checked manually, never blindly retried.
    result=client.request('POST','calendars',dict(summary='CAL',timeZone='Asia/Tokyo',description='CALを正本とする専用一方向連携'))
    if not result.get('id'):raise ValueError('calendar_creation_unknown')
    private_json(root/'settings/google-calendar.json',dict(calendar_id=result['id']))
    print('専用CAL calendar IDをprivate localに確定保存しました。')


def probe(root):
    client=GoogleClient(root);cid=client.config.get('calendar_id')
    if not cid or cid=='primary':raise ValueError('calendar_required')
    base='calendars/'+quote(cid,safe='')+'/events';path=root/'settings/google-probe.json'
    if path.exists():identity=json.loads(path.read_text())['event_id']
    else:
        identity='cal'+uuid4().hex;private_json(path,dict(event_id=identity))
    body=event_body(dict(title='CAL API接続確認（一時）',start_date='2099-01-01'),'probe:'+identity)
    try:remote=client.request('GET',base+'/'+identity)
    except GoogleError as e:
        if str(e) not in ('http_404','http_410'):raise
        remote=None
    if remote is None:client.request('POST',base,dict(body,id=identity))
    elif remote.get('extendedProperties',{}).get('private')!=body['extendedProperties']['private']:raise ValueError('probe_ownership_conflict')
    client.request('PUT',base+'/'+identity,dict(body,summary='CAL API接続確認（変更）'))
    remote=client.request('GET',base+'/'+identity)
    if remote.get('summary')!='CAL API接続確認（変更）':raise ValueError('probe_readback_failed')
    client.request('DELETE',base+'/'+identity);path.unlink()
    print('一時イベントの追加・変更・取得・削除を確認しました。')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--local-root',type=Path,default=ROOT)
    p.add_argument('action',choices=['authorize','create-calendar','probe']);args=p.parse_args()
    try:
        {'authorize':authorize,'create-calendar':create_calendar,'probe':probe}[args.action](args.local_root)
    except Exception:
        print('設定未完了。秘密値を共有せず、設定手順とprivateファイルを確認してください。',file=sys.stderr)
        sys.exit(2)
