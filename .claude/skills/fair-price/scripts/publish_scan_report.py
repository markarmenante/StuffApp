#!/usr/bin/env python3
"""Publish a daily offer-scan report to the boardroom DB, where the
Today app's Collections panel renders it. Uses Neon's HTTPS SQL
endpoint (stdlib only). Upserts on reportDate.

Input JSON (file argument or stdin):
  {{"reportDate": "YYYY-MM-DD", "status": "...", "reportMd": "...",
     "items": [{{category,title,venue,price,verdict,patches,fair,link,
                closes,note}}, ...]}}

Env: BOARD_DATABASE_URL (or DATABASE_URL).
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
        print('BOARD_DATABASE_URL / DATABASE_URL not set — cannot '
              'publish to the Today panel.', file=sys.stderr)
        sys.exit(3)
    raw = open(sys.argv[1]).read() if len(sys.argv) > 1 \
        else sys.stdin.read()
    report = json.loads(raw)
    for key in ('reportDate', 'reportMd'):
        if not report.get(key):
            print(f'missing required field {key}', file=sys.stderr)
            sys.exit(2)
    neon_query(url, """
        create table if not exists collection_scan_reports (
          report_date date primary key,
          status text not null default '',
          report_md text not null default '',
          items jsonb not null default '[]',
          created_at timestamptz not null default now()
        )""")
    neon_query(
        url,
        "insert into collection_scan_reports "
        "(report_date, status, report_md, items, created_at) "
        "values ($1, $2, $3, $4, now()) "
        "on conflict (report_date) do update set "
        "status = excluded.status, report_md = excluded.report_md, "
        "items = excluded.items, created_at = now()",
        [report['reportDate'], report.get('status', ''),
         report['reportMd'], json.dumps(report.get('items') or [])])
    print(json.dumps({'published': report['reportDate'],
                      'items': len(report.get('items') or [])}))


if __name__ == '__main__':
    main()
