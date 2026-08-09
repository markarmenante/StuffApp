#!/usr/bin/env python3
"""Read collectible-offer emails from the boardroom communications feed.

Mark's Macs sync Apple Mail (EVERY configured account — iCloud, Gmail,
armenante.com alike) into the boardroom Neon Postgres via the 7am comms
sync; offer-flavored mail routes to scenario 'collect'. This reads that
feed over Neon's HTTPS SQL endpoint (stdlib only — raw Postgres TCP is
firewalled in the cloud sandboxes). Freshness equals the Mac sync
cadence.

Env: BOARD_DATABASE_URL (or DATABASE_URL) — the board Neon URL.

Usage: comms_offers.py [--hours 36] [--limit 40]
Prints one JSON object per row.
"""
import json
import os
import sys


def neon_query(url, query, params=None):
    """Run one SQL statement over Neon's serverless HTTPS endpoint —
    plain HTTPS, so it works where raw Postgres TCP is firewalled
    (Claude cloud sandboxes included). $1-style placeholders."""
    import json
    import urllib.parse
    import urllib.request
    host = urllib.parse.urlparse(url).hostname
    req = urllib.request.Request(
        f'https://{host}/sql',
        data=json.dumps({'query': query,
                         'params': params or []}).encode(),
        headers={'Neon-Connection-String': url,
                 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    url = os.environ.get('BOARD_DATABASE_URL') \
        or os.environ.get('DATABASE_URL')
    if not url:
        print('BOARD_DATABASE_URL / DATABASE_URL not set — Apple-mail '
              'offer feed unavailable.', file=sys.stderr)
        sys.exit(3)
    hours, limit = 36, 40
    args = sys.argv[1:]
    if '--hours' in args:
        hours = int(args[args.index('--hours') + 1])
    if '--limit' in args:
        limit = int(args[args.index('--limit') + 1])
    out = neon_query(
        url,
        "select occurred_at, counterpart, handle, thread, snippet, link "
        "from communications "
        "where scenario_id = 'collect' and channel = 'email' "
        "and direction = 'in' "
        f"and occurred_at > now() - interval '{hours} hours' "
        f"order by occurred_at desc limit {limit}")
    rows = out.get('rows', [])
    for r in rows:
        print(json.dumps({
            'occurred_at': r.get('occurred_at'),
            'from': r.get('counterpart'), 'handle': r.get('handle'),
            'subject': r.get('thread'), 'snippet': r.get('snippet'),
            'link': r.get('link'),
        }))
    if not rows:
        print(json.dumps({'result': 'no offer mail in window'}))


if __name__ == '__main__':
    main()
