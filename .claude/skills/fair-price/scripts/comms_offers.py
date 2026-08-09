#!/usr/bin/env python3
"""Read collectible-offer emails from the boardroom communications feed.

Mark's Macs sync Apple Mail (EVERY configured account — iCloud, Gmail,
armenante.com alike) into the boardroom Neon Postgres via the 7am comms
sync; offer-flavored mail routes to scenario 'collect'. This reads that
feed — the Apple path Mark prefers over the Gmail API, because it sees
all accounts. Data freshness equals the Mac sync cadence (runs at 7am
Mac-side; the cloud scan at 7am ET reads yesterday-evening-or-newer).

Env: BOARD_DATABASE_URL (or DATABASE_URL) — the board Neon URL. Values
live in the Vercel `board` project; copy into the execution environment,
never into chat or code.

Usage:
    comms_offers.py [--hours 36] [--limit 40]

Prints one JSON object per row: occurred_at, from, handle, subject,
snippet, link. Requires pg8000 (pure python): pip install pg8000
"""
import json
import os
import sys
import urllib.parse


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def connect():
    url = os.environ.get('BOARD_DATABASE_URL') \
        or os.environ.get('DATABASE_URL')
    if not url:
        die('BOARD_DATABASE_URL / DATABASE_URL not set — Apple-mail offer '
            'feed unavailable.', 3)
    try:
        import pg8000.dbapi
    except ImportError:
        die('pg8000 not installed — run: pip install pg8000', 4)
    import ssl
    u = urllib.parse.urlparse(url)
    ctx = ssl.create_default_context()
    return pg8000.dbapi.connect(
        user=urllib.parse.unquote(u.username or ''),
        password=urllib.parse.unquote(u.password or ''),
        host=u.hostname, port=u.port or 5432,
        database=(u.path or '/').lstrip('/') or 'neondb',
        ssl_context=ctx)


def main():
    hours = 36
    limit = 40
    args = sys.argv[1:]
    if '--hours' in args:
        hours = int(args[args.index('--hours') + 1])
    if '--limit' in args:
        limit = int(args[args.index('--limit') + 1])
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "select occurred_at, counterpart, handle, thread, snippet, link "
        "from communications "
        "where scenario_id = 'collect' and channel = 'email' "
        "and direction = 'in' "
        "and occurred_at > now() - (%s || ' hours')::interval "
        "order by occurred_at desc limit %s", (str(hours), limit))
    n = 0
    for occurred_at, counterpart, handle, thread, snippet, link in \
            cur.fetchall():
        print(json.dumps({
            'occurred_at': str(occurred_at),
            'from': counterpart, 'handle': handle,
            'subject': thread, 'snippet': snippet, 'link': link,
        }))
        n += 1
    if not n:
        print(json.dumps({'result': 'no offer mail in window'}))
    conn.close()


if __name__ == '__main__':
    main()
