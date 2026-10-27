"""A create acknowledges only file selections actually saved on the record."""
import io
import os
from pathlib import Path
import sys
import tempfile
import types

from PIL import Image

REPO = Path(__file__).resolve().parents[1]
os.chdir(REPO)
sys.path.insert(0, str(REPO))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-upload-ack-')
os.environ['EBAY_SYNC_WORKER'] = '0'
os.environ['ORIGINAL_LISTING_WORKER'] = '0'
os.environ.pop('ANTHROPIC_API_KEY', None)
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda **kwargs: None)
import app as stuffapp

stuffapp.ensure_country_history = lambda *args, **kwargs: None
client = stuffapp.app.test_client()
photo = io.BytesIO()
Image.new('RGB', (120, 60), 'white').save(photo, format='PNG')
photo.seek(0)
response = client.post('/banknotes/new', data={
    'country': 'United States of America', 'denomination': '$5',
    'property_name': 'Carpinteria', 'price': '$599.89',
    'image_1': (photo, 'front.png'),
    'image_2': (io.BytesIO(b'unsupported'), 'back.unsupported'),
}, headers={'Accept': 'application/json'})
assert response.status_code == 200, response.status_code
created = response.get_json()
assert created['ok']
assert set(created['uploaded_files']) == {'image_1'}, created['uploaded_files']
with stuffapp.app.app_context():
    row = stuffapp.get_db().execute('SELECT * FROM banknotes WHERE id=?', (created['id'],)).fetchone()
    assert created['uploaded_files']['image_1'] == row['image_1']
    assert not row['image_2']
    assert row['price'] == '$599.89'
    assert (Path(stuffapp.UPLOAD_FOLDER) / row['image_1']).is_file()

response = client.post('/banknotes/new', data={'denomination': '$10'},
                       headers={'Accept': 'application/json'})
assert response.status_code == 200
assert response.get_json()['uploaded_files'] == {}
print('UPLOAD ACK OK: only persisted selections acknowledged; rejected selection omitted; exact cents retained')
