"""Short-lived Check proposals and durable accepted field/source evidence.

The caller owns transactions. No collection fields are changed here until an
explicit Check apply accepts an originally blank target under its identity lock.
"""
import html
import json
import time
import uuid

TTL = 15 * 60


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS banknote_catalog_proposals (
        id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES banknotes(id) ON DELETE CASCADE,
        identity_json TEXT NOT NULL, recovered_json TEXT NOT NULL DEFAULT '{}',
        created_at REAL NOT NULL, expires_at REAL NOT NULL)''')
    if 'recovered_json' not in {row[1] for row in db.execute('PRAGMA table_info(banknote_catalog_proposals)')}:
        db.execute("ALTER TABLE banknote_catalog_proposals ADD COLUMN recovered_json TEXT NOT NULL DEFAULT '{}'")
    db.execute('''CREATE INDEX IF NOT EXISTS banknote_catalog_proposals_record
        ON banknote_catalog_proposals(record_id, created_at)''')
    db.execute('''CREATE TABLE IF NOT EXISTS banknote_catalog_proposal_fields (
        proposal_id TEXT NOT NULL REFERENCES banknote_catalog_proposals(id) ON DELETE CASCADE,
        field TEXT NOT NULL, value_json TEXT NOT NULL, scope TEXT NOT NULL,
        source_url TEXT NOT NULL, quote TEXT NOT NULL, accepted_at REAL,
        accepted_value_json TEXT, PRIMARY KEY(proposal_id, field))''')


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def create(db, record_id, identity, fields, now=None, recovered=None):
    now = time.time() if now is None else now
    # Accepted rows are evidence, not an expiring cache. Only unaccepted
    # abandoned proposals can be removed when the short approval window ends.
    stale = [r[0] for r in db.execute('''SELECT p.id FROM banknote_catalog_proposals p
        WHERE p.expires_at < ? AND NOT EXISTS (SELECT 1 FROM banknote_catalog_proposal_fields f
        WHERE f.proposal_id=p.id AND f.accepted_at IS NOT NULL)''', (now,))]
    for ident in stale:
        db.execute('DELETE FROM banknote_catalog_proposal_fields WHERE proposal_id=?', (ident,))
        db.execute('DELETE FROM banknote_catalog_proposals WHERE id=?', (ident,))
    if not fields:
        return None
    ident = uuid.uuid4().hex
    db.execute('''INSERT INTO banknote_catalog_proposals
        (id,record_id,identity_json,recovered_json,created_at,expires_at) VALUES(?,?,?,?,?,?)''',
        (ident, record_id, _json(identity), _json(recovered or {}), now, now + TTL))
    for field, proof in fields.items():
        db.execute('''INSERT INTO banknote_catalog_proposal_fields
            (proposal_id,field,value_json,scope,source_url,quote) VALUES(?,?,?,?,?,?)''',
            (ident, field, _json(proof['value']), proof['scope'], proof['source_url'], proof['quote']))
    return ident


def approve(db, record_id, proposal_id, identity, values, now=None, final_identity=None):
    """Use server-stored proofs only; no source evidence is accepted from JSON."""
    now = time.time() if now is None else now
    proposal = db.execute('''SELECT identity_json,expires_at,recovered_json FROM banknote_catalog_proposals
        WHERE id=? AND record_id=?''', (proposal_id, record_id)).fetchone()
    if not proposal or proposal[1] <= now or json.loads(proposal[0]) != identity:
        return {}
    # A draft's catalogue match may depend on direct label/purchase identity
    # recovered in the same Check. It must accompany that catalogue acceptance.
    final_identity = identity if final_identity is None else final_identity
    if any(final_identity.get(field) != value for field,value in json.loads(proposal[2]).items()):
        return {}
    accepted = {}
    for row in db.execute('''SELECT field,value_json,scope,source_url,quote FROM banknote_catalog_proposal_fields
        WHERE proposal_id=? AND accepted_at IS NULL''', (proposal_id,)):
        field, value, scope, url, quote = row
        if field in values and json.loads(value) == values[field]:
            accepted[field] = dict(value=values[field], scope=scope, source_url=url, quote=quote)
    return accepted


def mark_accepted(db, proposal_id, values, now=None):
    now = time.time() if now is None else now
    for field, value in values.items():
        db.execute('''UPDATE banknote_catalog_proposal_fields SET accepted_at=?,accepted_value_json=?
            WHERE proposal_id=? AND field=? AND accepted_at IS NULL''',
            (now, _json(value), proposal_id, field))


def append_reference_notes(current, proofs, identity, day):
    if not proofs:
        return current
    def safe(value):
        return html.escape(' '.join(str(value or '').split()))
    reference = ', '.join(str(identity.get(field) or '') for field in ('pick_number','other_catalog') if identity.get(field))
    lines = ['Catalogue Check type evidence — ' + safe(day) + ' — ' +
             safe(identity.get('country')) + (' · ' + safe(reference) if reference else '')]
    for field, proof in sorted(proofs.items()):
        lines.append('- ' + safe(field.replace('_',' ').capitalize()) + ': ' + safe(proof['value']) +
                     '. Source: ' + safe(proof['source_url']))
        lines.append('  Evidence: ' + safe(proof['quote'][:400]))
    prefix = '' if current is None else str(current)
    return prefix + ('\n\n' if prefix else '') + '\n'.join(lines)
