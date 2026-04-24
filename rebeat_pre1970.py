#!/usr/bin/env python3
"""One-off: re-run the /lookup endpoint against every pre-1970 watch
currently stored at beat=28800. The lookup endpoint now validates beat
against the canonical VPH set and overwrites when the web-sourced
value differs, so pre-1970 pieces that should be 18000 or 21600 will
self-correct where sources have data.

Usage:  python3 rebeat_pre1970.py
Requires the local Flask server running on :5001.
"""
import sqlite3
import time
import os
import urllib.request
import json

DB = os.path.join(os.path.dirname(__file__), 'stuffapp.db')
HOST = 'http://localhost:5001'
SLEEP = 1.5  # polite pause between API calls

conn = sqlite3.connect(DB)
rows = conn.execute(
    "SELECT id, brand, model, year, beat FROM watches "
    "WHERE year < 1970 AND beat = 28800 ORDER BY year"
).fetchall()
conn.close()

print(f"Re-lookup targets: {len(rows)} watches")

changed = []
unchanged = []
errors = []

for i, (rid, brand, model, year, old_beat) in enumerate(rows, 1):
    label = f"{year} {brand} {model}"[:60]
    print(f"[{i:>2}/{len(rows)}] {label:<60} ", end='', flush=True)
    try:
        req = urllib.request.Request(
            f'{HOST}/watches/{rid}/lookup', method='POST'
        )
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"ERROR: {e}")
        errors.append((rid, label, str(e)))
        time.sleep(SLEEP)
        continue

    new_beat = None
    for section in ('filled', 'overwritten'):
        if 'beat' in (data.get(section) or {}):
            entry = data[section]['beat']
            new_beat = entry['new'] if isinstance(entry, dict) else entry
            break

    # Re-read from DB so we're always reporting actual stored value.
    conn2 = sqlite3.connect(DB)
    stored = conn2.execute("SELECT beat FROM watches WHERE id=?", (rid,)).fetchone()[0]
    conn2.close()

    if stored != old_beat:
        print(f"{old_beat} -> {stored}")
        changed.append((rid, label, old_beat, stored))
    else:
        print("(no change)")
        unchanged.append((rid, label))

    time.sleep(SLEEP)

print()
print(f"Changed:   {len(changed)}")
for rid, label, o, n in changed:
    print(f"  {label:<60} {o} -> {n}")
print(f"Unchanged: {len(unchanged)}")
print(f"Errors:    {len(errors)}")
for rid, label, err in errors:
    print(f"  {label:<60} {err}")
