#!/usr/bin/env python3
"""Gmail search/read via the Google API with env-var OAuth credentials.

The same connector pattern the boardroom app uses: a long-lived refresh
token (gmail.readonly scope) exchanged per run for an access token. No
claude.ai connector needed, so scheduled sessions can scan mail.

Requires env vars (set them on the execution environment, copied from
the Vercel `board` project — never paste values into chat or code):
    GOOGLE_CLIENT_ID  GOOGLE_CLIENT_SECRET  GOOGLE_REFRESH_TOKEN

Usage:
    gmail_search.py search 'newer_than:1d (offer OR "for sale" OR auction)' [--max 20]
    gmail_search.py read MESSAGE_ID

`search` prints one JSON object per message: id, from, subject, date,
snippet. `read` prints the decoded plain-text body of one message.
Tokens are never printed. Read-only scope: this tool cannot send,
label, or modify mail.
"""
import base64
import json
import os
import sys
import urllib.parse
import urllib.request

TOKEN_URL = 'https://oauth2.googleapis.com/token'
API = 'https://gmail.googleapis.com/gmail/v1/users/me'


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def access_token():
    cid = os.environ.get('GOOGLE_CLIENT_ID')
    secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    refresh = os.environ.get('GOOGLE_REFRESH_TOKEN')
    if not (cid and secret and refresh):
        die('GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / GOOGLE_REFRESH_TOKEN '
            'not set in this environment — Gmail sweep unavailable.', 3)
    body = urllib.parse.urlencode({
        'client_id': cid, 'client_secret': secret,
        'refresh_token': refresh, 'grant_type': 'refresh_token',
    }).encode()
    try:
        with urllib.request.urlopen(
                urllib.request.Request(TOKEN_URL, data=body), timeout=30) as r:
            return json.load(r)['access_token']
    except Exception as e:
        die(f'token exchange failed: {e}', 4)


def api_get(tok, path, params=None):
    url = f'{API}/{path}'
    if params:
        url += '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header('Authorization', f'Bearer {tok}')
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def header(msg, name):
    for h in msg.get('payload', {}).get('headers', []):
        if h.get('name', '').lower() == name.lower():
            return h.get('value', '')
    return ''


def cmd_search(query, max_results):
    tok = access_token()
    listing = api_get(tok, 'messages',
                      {'q': query, 'maxResults': max_results})
    for stub in listing.get('messages', []):
        m = api_get(tok, f"messages/{stub['id']}", {
            'format': 'metadata',
            'metadataHeaders': ['From', 'Subject', 'Date'],
        })
        print(json.dumps({
            'id': stub['id'],
            'from': header(m, 'From'),
            'subject': header(m, 'Subject'),
            'date': header(m, 'Date'),
            'snippet': m.get('snippet', ''),
        }))
    if not listing.get('messages'):
        print(json.dumps({'result': 'no matches'}))


def _text_parts(payload):
    if payload.get('mimeType', '').startswith('text/plain') \
            and payload.get('body', {}).get('data'):
        yield payload['body']['data']
    for part in payload.get('parts', []) or []:
        yield from _text_parts(part)


def cmd_read(msg_id):
    tok = access_token()
    m = api_get(tok, f'messages/{msg_id}', {'format': 'full'})
    print(f"From: {header(m, 'From')}\nSubject: {header(m, 'Subject')}\n"
          f"Date: {header(m, 'Date')}\n")
    chunks = list(_text_parts(m.get('payload', {})))
    if not chunks:
        print('[no text/plain body; snippet follows]')
        print(m.get('snippet', ''))
        return
    for data in chunks:
        print(base64.urlsafe_b64decode(data + '==').decode(
            'utf-8', errors='replace'))


if __name__ == '__main__':
    args = sys.argv[1:]
    if not args or args[0] not in ('search', 'read'):
        die(__doc__)
    if args[0] == 'search':
        if len(args) < 2:
            die('search needs a Gmail query string')
        mx = 20
        if '--max' in args:
            mx = int(args[args.index('--max') + 1])
        cmd_search(args[1], mx)
    else:
        if len(args) < 2:
            die('read needs a message id')
        cmd_read(args[1])
