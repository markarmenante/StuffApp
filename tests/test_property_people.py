"""Property contacts grow past the legacy slots without losing saves or backups."""
import os
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-property-people-')

import app as stuffapp

client = stuffapp.app.test_client()
spec = stuffapp.PROPERTY_SLOT_SPECS['people']
with stuffapp.app.app_context():
    db = stuffapp.get_db()
    db.executemany('INSERT INTO properties (id, name) VALUES (?, ?)',
                   [('p1', 'Test property'), ('p2', 'Backup property'),
                    ('legacy', 'Legacy property')])
    db.commit()


def save(field, value, record_id='p1'):
    response = client.post(f'/properties/{record_id}/save-field',
                           json={'field': field, 'value': value})
    assert response.status_code == 200, (field, response.status_code, response.get_json())
    assert response.get_json()['ok']


def people(record_id='p1'):
    with stuffapp.app.app_context():
        return stuffapp._property_slot_rows(stuffapp.get_db(), spec, record_id)


for position in range(1, 31):
    save(f'people_name_{position}', f'Contact {position}')
save('people_role_30', 'Caretaker')
save('people_phone_30', '2125550130')
save('people_email_30', 'contact30@example.test')
save('people_note_30', 'Available weekdays')
assert len(people()) == 30
assert people()[-1]['phone'] == '(212) 555-0130'
response = client.get('/properties/p1')
assert response.status_code == 200
html = response.get_data(as_text=True)
assert 'value="Contact 30"' in html and 'name="people_name_31"' in html
assert 'aria-label="Property people"' in html

# Submitting an older form must not truncate the extra child rows.
response = client.post('/properties/p1', data={'name': 'Updated property', 'people_name_1': 'Updated contact'})
assert response.status_code == 302
assert len(people()) == 30 and people()[0]['name'] == 'Updated contact'
assert people()[-1]['note'] == 'Available weekdays'
save('notes', 'Unrelated edit')
assert len(people()) == 30

# Clear one person without shifting other contacts or their stable positions.
for prefix in spec['field_columns']:
    save(f'{prefix}_11', '')
assert len(people()) == 29
assert 11 not in {person['position'] for person in people()}
assert people()[-1]['position'] == 30
save('people_name_31', 'Next contact')

# Blur/autosave sends fields together; concurrent clears must not restore old values.
def concurrent_save(entry):
    field, value = entry
    with stuffapp.app.test_client() as parallel_client:
        result = parallel_client.post('/properties/p1/save-field', json={'field': field, 'value': value})
        assert result.status_code == 200, result.get_data(as_text=True)


for position in range(40, 45):
    fields = [(f'{prefix}_{position}', f'Test {column}') for prefix, column in spec['field_columns'].items()]
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(concurrent_save, fields))
    saved_person = next(person for person in people() if person['position'] == position)
    assert all(saved_person[column] == f'Test {column}' for column in spec['columns'])
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(concurrent_save, [(field, '') for field, _ in fields]))
    assert position not in {person['position'] for person in people()}

# Create and full-form edit both accept contacts beyond the legacy columns.
form = {'name': 'New property', 'people_name_1': 'First', 'people_name_21': 'Twenty first'}
response = client.post('/properties/new', data=form, headers={'Accept': 'application/json'})
assert response.status_code == 200, response.get_json()
new_id = response.get_json()['id']
assert [person['position'] for person in people(new_id)] == [1, 21]
response = client.post(f'/properties/{new_id}', data={**form, 'people_role_21': 'Agent'})
assert response.status_code == 302
assert people(new_id)[-1]['role'] == 'Agent'

# Snapshots and restore retain all contacts, while the first ten still mirror.
with stuffapp.app.app_context():
    db = stuffapp.get_db()
    row = db.execute('SELECT * FROM properties WHERE id = ?', ['p1']).fetchone()
    assert row['people_name_1'] == 'Updated contact'
    assert row['people_name_10'] == 'Contact 10'
    snapshot = stuffapp._record_data_snapshot(db, 'properties', 'properties', row)
    assert len(snapshot['property_people']) == 30
    stuffapp._restore_snapshot_child_tables(db, 'properties', 'p2', snapshot, '2026-09-26T00:00:00')
    db.execute("UPDATE properties SET people_name_1 = 'Legacy contact' WHERE id = 'legacy'")
    db.commit()
    stuffapp._backfill_property_slot_tables(db)
assert len(people('p2')) == 30
assert people('p2')[-1]['name'] == 'Next contact'
assert people('legacy')[0]['name'] == 'Legacy contact'
assert len(people()) == 30

# Other slot lists retain their bounds; malformed names cannot reach SQL.
for field in ['people_name_0', 'people_name_-1', 'people_name_2147483648',
              'people_unknown_11', 'people_name_11;DROP', 'alarm_codes_entry_9']:
    response = client.post('/properties/p1/save-field', json={'field': field, 'value': 'no'})
    assert response.status_code == 400, (field, response.status_code)
assert client.post('/properties/missing/save-field', json={'field': 'people_name_11', 'value': 'no'}).status_code == 404
assert client.post('/persons/missing/save-field', json={'field': 'people_name_11', 'value': 'no'}).status_code == 400
save('alarm_codes_entry_8', 'Back door')
assert client.get('/properties/new').status_code == 200
print('PROPERTY PEOPLE OK: extra contacts, autosave, forms, delete, legacy sync, backup, validation')
