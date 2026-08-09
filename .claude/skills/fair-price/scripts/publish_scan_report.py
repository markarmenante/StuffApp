#!/usr/bin/env python3
"""Publish a daily offer-scan report to the boardroom DB, where the Today
app's Collections panel renders it.

Input: a JSON file (argument) or stdin with this shape:
  {
    "reportDate": "2026-08-10",          // the scan day, YYYY-MM-DD
    "status": "Gmail: ok · Web: ...",     // the report's one-line status
    "reportMd": "# Daily Collection ...", // full report markdown
    "items": [ { "category": "Banknotes", "title": "...", "venue": "...",
                 "price": "...", "verdict": "pursue", "patches": "...",
                 "fair": "...", "link": "https://...", "closes": "",
                 "note": "..." }, ... ]
  }

Env: BOARD_DATABASE_URL (or DATABASE_URL). Requires pg8000
(pip install pg8000). Upserts on reportDate — republishing a day
replaces that day's report.
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
        die('BOARD_DATABASE_URL / DATABASE_URL not set — cannot publish '
            'to the Today panel.', 3)
    try:
        import pg8000.dbapi
    except ImportError:
        die('pg8000 not installed — run: pip install pg8000', 4)
    import ssl
    u = urllib.parse.urlparse(url)
    return pg8000.dbapi.connect(
        user=urllib.parse.unquote(u.username or ''),
        password=urllib.parse.unquote(u.password or ''),
        host=u.hostname, port=u.port or 5432,
        database=(u.path or '/').lstrip('/') or 'neondb',
        ssl_context=ssl.create_default_context())


def main():
    raw = open(sys.argv[1]).read() if len(sys.argv) > 1 else sys.stdin.read()
    try:
        report = json.loads(raw)
    except ValueError as e:
        die(f'input is not valid JSON: {e}', 2)
    for key in ('reportDate', 'reportMd'):
        if not report.get(key):
            die(f'missing required field {key}', 2)
    items = report.get('items') or []
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        create table if not exists collection_scan_reports (
          report_date date primary key,
          status text not null default '',
          report_md text not null default '',
          items jsonb not null default '[]',
          created_at timestamptz not null default now()
        )""")
    cur.execute(
        "insert into collection_scan_reports "
        "(report_date, status, report_md, items, created_at) "
        "values (%s, %s, %s, %s, now()) "
        "on conflict (report_date) do update set "
        "status = excluded.status, report_md = excluded.report_md, "
        "items = excluded.items, created_at = now()",
        (report['reportDate'], report.get('status', ''),
         report['reportMd'], json.dumps(items)))
    conn.commit()
    conn.close()
    print(json.dumps({'published': report['reportDate'],
                      'items': len(items)}))


if __name__ == '__main__':
    main()
