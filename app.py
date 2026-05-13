import sqlite3
import uuid
import os
import json
import re
import base64
import unicodedata
from datetime import datetime, date
from flask import (Flask, g, render_template, request, redirect, url_for,
                   flash, send_from_directory, abort, jsonify, Response,
                   send_file, after_this_request)
from werkzeug.utils import secure_filename

try:
    from dotenv import load_dotenv
    # override=True: a pre-existing empty ANTHROPIC_API_KEY in the parent env
    # (e.g. from shell profile) otherwise wins over the .env value.
    load_dotenv(override=True)
except Exception:
    pass

app = Flask(__name__)
app.secret_key = 'stuffapp-secret-key-change-me'

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get('DATA_DIR', BASE_DIR)
DATABASE = os.path.join(DATA_DIR, 'stuffapp.db')
UPLOAD_FOLDER = os.path.join(DATA_DIR, 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'tif', 'tiff', 'heic', 'heif'}

# iPhones export photos as HEIC; browsers can't render it. Register the HEIF
# opener so PIL can decode HEIC bytes, then convert to JPEG on upload.
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    HEIF_SUPPORTED = True
except ImportError:
    HEIF_SUPPORTED = False

# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------

CATEGORIES = {
    'watches': {
        'name': 'Watches', 'singular': 'Watch', 'icon': '⌚', 'table': 'watches',
        'label_field': 'brand', 'sublabel_field': 'model', 'image_field': 'image_obv',
    },
    'coins': {
        'name': 'Coins', 'singular': 'Coin', 'icon': '🪙', 'table': 'coins',
        'label_field': 'authority', 'sublabel_field': 'denomination', 'image_field': 'image_1',
    },
    'cameras': {
        'name': 'Cameras', 'singular': 'Camera', 'icon': '📷', 'table': 'cameras',
        'label_field': 'make', 'sublabel_field': 'model', 'image_field': 'image',
    },
    'lenses': {
        'name': 'Lenses', 'singular': 'Lens', 'icon': '🔘', 'table': 'lenses',
        'label_field': 'make', 'sublabel_field': 'model', 'image_field': 'image',
    },
    'pens': {
        'name': 'Pens', 'singular': 'Pen', 'icon': '✒️', 'table': 'pens',
        'label_field': 'make', 'sublabel_field': 'model', 'image_field': 'image',
    },
    'art': {
        'name': 'Art', 'singular': 'Artwork', 'icon': '🎨', 'table': 'art',
        'label_field': 'artist', 'sublabel_field': 'title', 'image_field': 'image',
    },
    'items': {
        'name': 'Items', 'singular': 'Item', 'icon': '📦', 'table': 'items',
        'label_field': 'name', 'sublabel_field': 'type', 'image_field': 'image',
    },
    'vehicles': {
        'name': 'Vehicles', 'singular': 'Vehicle', 'icon': '🚗', 'table': 'vehicles',
        'label_field': 'make', 'sublabel_field': 'model', 'image_field': 'image',
    },
    'recordings': {
        'name': 'Music', 'singular': 'Recording', 'icon': '🎵', 'table': 'recordings',
        'label_field': 'artist', 'sublabel_field': 'title', 'image_field': 'image',
    },
    'audio': {
        'name': 'Audio', 'singular': 'Audio Component', 'icon': '🔊', 'table': 'audio',
        'label_field': 'make', 'sublabel_field': 'model', 'image_field': 'image',
    },
    'rifles': {
        'name': 'Rifles', 'singular': 'Rifle', 'icon': '🔫', 'table': 'rifles',
        'label_field': 'make', 'sublabel_field': 'model', 'image_field': 'image',
    },
    'credit_cards': {
        'name': 'Credit Cards', 'singular': 'Credit Card', 'icon': '💳', 'table': 'credit_cards',
        'label_field': 'name', 'sublabel_field': 'number', 'image_field': 'image_front',
    },
    'properties': {
        'name': 'Properties', 'singular': 'Property', 'icon': '🏠', 'table': 'properties',
        'label_field': 'name', 'sublabel_field': 'address', 'image_field': 'image',
    },
    'persons': {
        'name': 'People', 'singular': 'Person', 'icon': '👤', 'table': 'persons',
        'label_field': 'name', 'sublabel_field': 'phone', 'image_field': 'head_shot',
    },
}

# Fields per category: name, label, type, options (for select/checkbox-group)
COMPLICATIONS_OPTIONS = [
    'Hours', 'Minutes', 'Seconds', 'Hacking', 'Day', 'Date', 'Month',
    'Moon', 'Annual', 'Perpetual', 'Pw Res', 'GMT', 'Eq Time',
    'Chronograph', 'Split Chrono', 'Tourbillon', 'Resonance', 'Remontoire',
    'Fusee Chain', 'Minute Rep', 'Sonnerie', 'Open Back', 'Open Dial',
]

VALUE_LISTS = {
    'metal_watch': ['Bronze','Ceramic','Gold Filled','Gold, Yellow','Gold: Red/Rose','Gold: Rose','Gold: White','Gold: Yellow','Platinum','Silver','Stainless','Tantalum','Titanium','Zirconium'],
    'dial_color': ['Abalone','Black','Black/Gray','Blue','Blue/Open','Brown','Champagne','Copper','Cream','Crystal','Damascus Steel','Ebony','Enamel','Gold','Gray','Gray/Black','Green','Green/Inlaid','Grey','Inlaid','Ivory','Jade','Nacre','Open','Platinum','Purple','Red','Rose Gold','Ruthenium','Salmon','Silver','Silver / Open','Silver/Black','White','White Ceramic','White Enamel','Yellow','Yellow Gold','Zirconium'],
    'movement_origin': ['In-House','Ébauche','Modified'],
    'escapement': ['Swiss Lever','Co-Axial','Natural','Constant Force',
                   'Detent','Chronometer','Cylinder','Verge','Pin Lever',
                   'Duplex','Tuning Fork','Quartz','Other'],
    'strap_material': ['Case Metal','Croc','Leather','Ostrich','Rubber','Skin'],
    'strap_color': ['Black','Blue','Blue/Gray','Brown','Burgundy','Dk Brown','Eggplant','Gold','Gray','Green','Lt Brown','Navy Blue','Red','Rose Gold','Stainless','Tan','Titanium','White Gold'],
    'owner': [o.strip() for o in (os.environ.get('STUFFAPP_OWNER_OPTIONS') or 'YM,Mark,Young').split(',') if o.strip()],
    # 'property' is loaded per-request from the properties table; see
    # current_vlists(). Keeping it out of the static dict ensures a
    # fork of this app pointed at a different DB doesn't leak the
    # original deployment's property names.
    'status': ['Own','Ordered','Sold','Loaned','Gifted','Consigned','Lost'],
    'location_status': ['Storage','Consigned','Missing','Gifted'],
    'camera_status': ['Own','Sold','Gifted'],
    'coin_status': ['Own','Ordered','Sold','Loaned'],
    'recording_status': ['Own','Ordered'],
    'metal_coin': ['AE Bronze','AE Copper','AL Aluminium','AR Silver','AV Gold','BL Billon','EL Electrum','NI Nickel'],
    'coin_grade': ['BU','FDC','MS','PF','cAU','AU','aAU','cEF','EF','aEF','cVF','VF+','VF','aVF','gVF'],
    'clasp_type': ['Tang','Fold Over','Butterfly','Velcro'],
    'pen_type':      ['Fountain Pen', 'Ball Point', 'Roller Ball', 'Mechanical Pencil'],
    'pen_action':    ['Cap', 'Click', 'Twist'],
    'pen_nib':       ['Extra Fine', 'Fine', 'Medium', 'Broad'],
    'pen_cartridge': ['International', 'Pilot/Namiki', 'Platinum/Nakaya', 'Sailor', 'Proprietary'],
    # Stored in the legacy `reservoir` column; surfaced to the user as "Filling".
    'pen_filling':   ['Cartridge', 'Converter', 'Piston', 'Eyedropper', 'Vacuum'],
    'recording_type': ['Vinyl','CD','SACD','Tape'],
    'recording_genre': ['Afro-Pop', 'Blues', 'Classical', 'Country', 'Folk', 'Funk/Soul',
                        'Jazz', 'Pop/Rock', 'R&B', 'Rap', 'Reggae', 'World'],
    'property_type': ['Residential','Commercial','Land'],
    'audio_type': ['Amplifier','CD Player','DAC','Pre-Amp','Scaler','Speakers','Streamer','Tape Deck','Turntable','Phono Stage','Headphones','Cables','Other'],
}

# (table, field) -> {alias (lowercase): canonical}. Values entered through
# the web UI or imported from CSV get folded to the canonical form so
# dropdowns and filters don't fragment across synonyms.
FIELD_ALIASES = {
    ('watches', 'clasp_type'): {
        # Fold Over synonyms
        'deployant':        'Fold Over',
        'deployment':       'Fold Over',
        'deployant clasp':  'Fold Over',
        'deployment clasp': 'Fold Over',
        'folding clasp':    'Fold Over',
        'flip clasp':       'Fold Over',
        'fold clasp':       'Fold Over',
        # Tang synonyms
        'tang buckle':      'Tang',
        'pin buckle':       'Tang',
        'strap buckle':     'Tang',
        'belt buckle':      'Tang',
        'pin clasp':        'Tang',
        'ardillon buckle':  'Tang',
        'ardillon':         'Tang',
        'buckle':           'Tang',
    },
    ('watches', 'strap_material'): {
        'alligator': 'Croc',
        'aligator':  'Croc',   # common misspelling
    },
    ('watches', 'dial_color'): {
        'skeleton': 'Open',
    },
    # Coin grade abbreviations the value list uses (cEF / aEF / cVF /
    # aVF / gVF) — map natural-language equivalents back to the
    # canonical short form so a description that says "Choice EF"
    # snaps to the value-list entry "cEF" on save.
    ('coins', 'grade'): {
        'choice au':  'cAU',
        'choice ef':  'cEF',
        'choice xf':  'cEF',
        'choice vf':  'cVF',
        'about au':   'aAU',
        'almost au':  'aAU',
        'about ef':   'aEF',
        'almost ef':  'aEF',
        'about xf':   'aEF',
        'almost xf':  'aEF',
        'about vf':   'aVF',
        'almost vf':  'aVF',
        'good vf':    'gVF',
        'xf':         'EF',
    },
}


def normalize_field_value(table, field_name, value):
    """Return the canonical value for a known alias, or the input
    unchanged. Strings are first NFC-normalized so pre-composed and
    decomposed Unicode forms of the same character (e.g. 'ü' as U+00FC
    vs U+0075+U+0308) collapse to one canonical form before any alias
    lookup or DB write — keeps a pasted brand name from creating two
    visually-identical-but-different entries down the line."""
    if value is None:
        return value
    if isinstance(value, str):
        import unicodedata
        value = unicodedata.normalize('NFC', value)
    if field_name == 'status' and value.strip().lower() == 'owned':
        return 'Own'
    aliases = FIELD_ALIASES.get((table, field_name))
    if not aliases:
        return value
    return aliases.get(value.strip().lower(), value)


def _normalize_owned_status_values(db):
    """Fold legacy status='Owned' rows to the canonical status='Own'."""
    tables = [
        r['name'] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]
    for table in tables:
        cols = [r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()]
        if 'status' in cols:
            db.execute(
                f"UPDATE {table} SET status = 'Own' "
                "WHERE LOWER(TRIM(COALESCE(status, ''))) = 'owned'"
            )


def _backfill_blank_status_own(db):
    """Default blank lifecycle statuses to Own for item tables."""
    for category, info in CATEGORIES.items():
        table = info['table']
        cols = [r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()]
        if 'status' in cols:
            db.execute(
                f"UPDATE {table} SET status = 'Own' "
                "WHERE status IS NULL OR TRIM(status) = ''"
            )


# Default owner assigned to brand-new records when the form's owner
# field is blank (which it always is for member users — the field is
# hidden in the template for them). Owner-role users see the owner
# dropdown and can override these defaults at create time.
DEFAULT_OWNER_BY_CATEGORY = {
    'watches':      'Mark',
    'coins':        'Mark',
    'properties':   'YM',
    'credit_cards': 'YM',
    'persons':      'YM',
    'cameras':      'Mark',
    'lenses':       'Mark',
    'pens':         'Mark',
    'art':          'YM',
    'items':        'YM',
    'vehicles':     'Mark',
    'recordings':   'Mark',
    'audio':        'Mark',
    'rifles':       'Mark',
}

# Tenant override — when STUFFAPP_OWNER_OPTIONS is set (e.g. for a
# third-party deployment whose owners aren't Mark/Young/YM), default
# every category to the first option in that list. The historical
# Mark/YM split only makes sense for the original deployment.
if os.environ.get('STUFFAPP_OWNER_OPTIONS'):
    _first_owner = VALUE_LISTS['owner'][0] if VALUE_LISTS['owner'] else ''
    DEFAULT_OWNER_BY_CATEGORY = {
        cat: _first_owner for cat in DEFAULT_OWNER_BY_CATEGORY
    }


FIELDS = {
    'watches': [
        {'name': 'brand',           'label': 'Brand',             'type': 'text'},
        {'name': 'model',           'label': 'Model',             'type': 'text'},
        {'name': 'reference',       'label': 'Reference',         'type': 'text'},
        {'name': 'metal',           'label': 'Metal',             'type': 'text'},
        {'name': 'case_diameter',   'label': 'Case Diameter (mm)','type': 'number'},
        {'name': 'dial_color',      'label': 'Dial Color',        'type': 'text'},
        {'name': 'case_num',        'label': 'Case Number',       'type': 'text'},
        {'name': 'movement_num',    'label': 'Movement Number',   'type': 'text'},
        {'name': 'edition',         'label': 'Edition',           'type': 'text'},
        {'name': 'year',            'label': 'Year',              'type': 'number'},
        {'name': 'calibre',         'label': 'Calibre',           'type': 'text'},
        {'name': 'movement_type',   'label': 'Movement Type',     'type': 'select',
         'options': ['', 'Automatic', 'Manual', 'Quartz', 'Spring Drive', 'Co-Axial', 'Tuning Fork']},
        {'name': 'movement_jewels', 'label': 'Jewels',            'type': 'number'},
        {'name': 'movement_origin', 'label': 'Movement Origin',   'type': 'text'},
        {'name': 'escapement',      'label': 'Escapement',        'type': 'text'},
        {'name': 'balance_wheel',   'label': 'Balance Wheel',     'type': 'text'},
        {'name': 'calibre_notes',   'label': 'Calibre Notes',     'type': 'textarea'},
        {'name': 'beat',            'label': 'Beat (vph)',        'type': 'number'},
        {'name': 'reserve',         'label': 'Power Reserve (hrs)','type': 'number'},
        {'name': 'complications',   'label': 'Complications',     'type': 'checkbox-group',
         'options': COMPLICATIONS_OPTIONS},
        {'name': 'clasp_type',      'label': 'Clasp Type',        'type': 'text'},
        {'name': 'lug_mm',          'label': 'Lug Width (mm)',     'type': 'number'},
        {'name': 'strap_material',  'label': 'Strap Material',    'type': 'text'},
        {'name': 'strap_color',     'label': 'Strap Color',       'type': 'text'},
        {'name': 'date',            'label': 'Purchase Date',     'type': 'date'},
        {'name': 'price',           'label': 'Price',             'type': 'number'},
        {'name': 'vendor',          'label': 'Vendor',            'type': 'text'},
        {'name': 'order_purchase_price', 'label': 'Order Purchase Price', 'type': 'text'},
        {'name': 'order_deposit',    'label': 'Order Deposit',     'type': 'text'},
        {'name': 'expected_delivery_date', 'label': 'Promised Delivery Date', 'type': 'date'},
        {'name': 'actual_delivery_date', 'label': 'Actual Delivery Date', 'type': 'date'},
        {'name': 'service_date',    'label': 'Service Date',      'type': 'date'},
        {'name': 'value',           'label': 'Value',             'type': 'number'},
        {'name': 'results',         'label': 'Results',           'type': 'textarea'},
        {'name': 'description',     'label': 'Description',       'type': 'textarea'},
        {'name': 'notes',           'label': 'Notes',             'type': 'textarea'},
        {'name': 'owner',           'label': 'Owner',             'type': 'text'},
        {'name': 'property',        'label': 'Property',          'type': 'text'},
        {'name': 'status',          'label': 'Status',            'type': 'select',
         'options': ['', 'Own', 'Sold', 'Loaned']},
        {'name': 'location_status', 'label': 'Disposition',       'type': 'select',
         'options': ['', 'Storage', 'Consigned', 'Missing', 'Gifted']},
        {'name': 'image_obv',       'label': 'Image',             'type': 'file'},
        {'name': 'container_1',     'label': 'Container 1',       'type': 'file'},
        {'name': 'container_2',     'label': 'Container 2',       'type': 'file'},
        {'name': 'document',        'label': 'Document',          'type': 'file'},
    ],
    'coins': [
        {'name': 'coin_id',         'label': 'Coin ID',           'type': 'text', 'readonly': True},
        {'name': 'cat_id',          'label': 'Cat ID',            'type': 'text', 'readonly': True},
        {'name': 'authority',       'label': 'Authority',         'type': 'text'},
        {'name': 'region',          'label': 'Region',            'type': 'text'},
        {'name': 'official',        'label': 'Official',          'type': 'text'},
        {'name': 'denomination',    'label': 'Denomination',      'type': 'text'},
        {'name': 'metal',           'label': 'Metal',             'type': 'text'},
        {'name': 'mint',            'label': 'Mint',              'type': 'text'},
        {'name': 'date_1',          'label': 'Date From (year, negative=BC)', 'type': 'number'},
        {'name': 'date_1_text',     'label': 'Date From (text)',  'type': 'text'},
        {'name': 'date_2',          'label': 'Date To (year)',    'type': 'number'},
        {'name': 'date_2_text',     'label': 'Date To (text)',    'type': 'text'},
        {'name': 'description',     'label': 'Description',       'type': 'textarea'},
        {'name': 'coin_references',  'label': 'References / Pedigree', 'type': 'textarea'},
        {'name': 'notes',           'label': 'Notes / Grade',     'type': 'textarea'},
        {'name': 'history_context', 'label': 'Historical Context','type': 'textarea'},
        {'name': 'grade',           'label': 'Grade',             'type': 'text'},
        {'name': 'die_axis',        'label': 'Die Axis',          'type': 'text'},
        {'name': 'strike',          'label': 'Strike',            'type': 'number'},
        {'name': 'surface',         'label': 'Surface',           'type': 'number'},
        {'name': 'weight',          'label': 'Weight (g)',        'type': 'number'},
        {'name': 'size',            'label': 'Diameter (mm)',     'type': 'number'},
        {'name': 'bullion',         'label': 'Bullion',           'type': 'text'},
        {'name': 'bin',             'label': 'Bin',               'type': 'text'},
        {'name': 'storage_location','label': 'Storage Location',  'type': 'text'},
        {'name': 'sheldon',         'label': 'Sheldon',           'type': 'text'},
        {'name': 'obv_rev',         'label': 'Obv/Rev',           'type': 'text'},
        {'name': 'condition',       'label': 'Condition',         'type': 'text'},
        {'name': 'received',        'label': 'Received',          'type': 'text'},
        {'name': 'print_field',     'label': 'Print Field',       'type': 'text'},
        {'name': 'price',           'label': 'Price',             'type': 'number'},
        {'name': 'vendor',          'label': 'Vendor',            'type': 'text'},
        {'name': 'purchase_date',   'label': 'Purchase Date',     'type': 'date'},
        {'name': 'owner',           'label': 'Owner',             'type': 'text'},
        {'name': 'property_name',   'label': 'Property',          'type': 'text'},
        {'name': 'status',          'label': 'Status',            'type': 'select',
         'options': ['', 'Own', 'Sold', 'Loaned']},
        {'name': 'image_1',         'label': 'Image (Obverse)',   'type': 'file'},
        {'name': 'image_2',         'label': 'Image (Reverse)',   'type': 'file'},
        {'name': 'document_1',      'label': 'Document 1',        'type': 'file'},
        {'name': 'document_2',      'label': 'Document 2',        'type': 'file'},
    ],
    'cameras': [
        {'name': 'make',            'label': 'Brand',             'type': 'text'},
        {'name': 'model',           'label': 'Model',             'type': 'text'},
        {'name': 'digital_film',    'label': 'Digital / Film',    'type': 'select',
         'options': ['', 'Digital', 'Film', 'Both']},
        {'name': 'film_size',       'label': 'Film Size',         'type': 'text'},
        {'name': 'lens_mount',      'label': 'Mount',             'type': 'text'},
        {'name': 'megapixels',      'label': 'Megapixels',        'type': 'number'},
        {'name': 'sensor',          'label': 'Sensor',            'type': 'text'},
        {'name': 'serial_number',   'label': 'Serial Number',     'type': 'text'},
        {'name': 'date',            'label': 'Purchase Date',     'type': 'date'},
        {'name': 'price',           'label': 'Price',             'type': 'number'},
        {'name': 'vendor',          'label': 'Vendor',            'type': 'text'},
        {'name': 'notes',           'label': 'Notes',             'type': 'textarea'},
        {'name': 'owner',           'label': 'Owner',             'type': 'text'},
        {'name': 'property',        'label': 'Property',          'type': 'text'},
        {'name': 'status',          'label': 'Status',            'type': 'select',
         'options': ['', 'Own', 'Sold', 'Loaned']},
        {'name': 'location_status', 'label': 'Disposition',       'type': 'select',
         'options': ['', 'Storage', 'Consigned', 'Missing', 'Gifted']},
        {'name': 'image',           'label': 'Image',             'type': 'file'},
    ],
    'lenses': [
        {'name': 'make',            'label': 'Make',              'type': 'text'},
        {'name': 'model',           'label': 'Model',             'type': 'text'},
        {'name': 'mount',           'label': 'Mount',             'type': 'text'},
        {'name': 'aperture',        'label': 'Aperture (ƒ/)',     'type': 'number'},
        {'name': 'filter_size',     'label': 'Filter Size (mm)',  'type': 'number'},
        {'name': 'length',          'label': 'Length (mm)',       'type': 'number'},
        {'name': 'serial_number',   'label': 'Serial Number',     'type': 'text'},
        {'name': 'date',            'label': 'Purchase Date',     'type': 'date'},
        {'name': 'price',           'label': 'Price',             'type': 'number'},
        {'name': 'vendor',          'label': 'Vendor',            'type': 'text'},
        {'name': 'notes',           'label': 'Notes',             'type': 'textarea'},
        {'name': 'owner',           'label': 'Owner',             'type': 'text'},
        {'name': 'property',        'label': 'Property',          'type': 'text'},
        {'name': 'status',          'label': 'Status',            'type': 'select',
         'options': ['', 'Own', 'Sold', 'Loaned']},
        {'name': 'location_status', 'label': 'Disposition',       'type': 'select',
         'options': ['', 'Storage', 'Consigned', 'Missing', 'Gifted']},
        {'name': 'image',           'label': 'Image',             'type': 'file'},
    ],
    'pens': [
        {'name': 'make',            'label': 'Make',              'type': 'text'},
        {'name': 'model',           'label': 'Model',             'type': 'text'},
        {'name': 'type',            'label': 'Type',              'type': 'select',
         'options': [''] + VALUE_LISTS['pen_type']},
        {'name': 'action',          'label': 'Action',            'type': 'select',
         'options': [''] + VALUE_LISTS['pen_action']},
        {'name': 'nib',             'label': 'Nib',               'type': 'select',
         'options': [''] + VALUE_LISTS['pen_nib']},
        {'name': 'cartridge',       'label': 'Cartridge',         'type': 'select',
         'options': [''] + VALUE_LISTS['pen_cartridge']},
        # Column is `reservoir` for backwards compat; user sees "Filling".
        {'name': 'reservoir',       'label': 'Filling',           'type': 'select',
         'options': [''] + VALUE_LISTS['pen_filling']},
        {'name': 'date',            'label': 'Purchase Date',     'type': 'date'},
        {'name': 'price',           'label': 'Price',             'type': 'number'},
        {'name': 'vendor',          'label': 'Vendor',            'type': 'text'},
        {'name': 'notes',           'label': 'Notes',             'type': 'textarea'},
        {'name': 'owner',           'label': 'Owner',             'type': 'text'},
        {'name': 'property',        'label': 'Property',          'type': 'text'},
        {'name': 'status',          'label': 'Status',            'type': 'select',
         'options': ['', 'Own', 'Sold', 'Loaned']},
        {'name': 'location_status', 'label': 'Disposition',       'type': 'select',
         'options': ['', 'Storage', 'Consigned', 'Missing', 'Gifted']},
        {'name': 'image',           'label': 'Image',             'type': 'file'},
    ],
    'art': [
        {'name': 'title',           'label': 'Title',             'type': 'text'},
        {'name': 'artist',          'label': 'Artist',            'type': 'text'},
        {'name': 'year',            'label': 'Year',              'type': 'number'},
        {'name': 'medium',          'label': 'Medium',            'type': 'text'},
        {'name': 'dimensions',      'label': 'Dimensions',        'type': 'text'},
        {'name': 'date',            'label': 'Purchase Date',     'type': 'date'},
        {'name': 'price',           'label': 'Price',             'type': 'number'},
        {'name': 'vendor',          'label': 'Vendor',            'type': 'text'},
        {'name': 'notes',           'label': 'Artist Notes',      'type': 'textarea'},
        {'name': 'object_notes',    'label': 'Object Notes',      'type': 'textarea'},
        {'name': 'owner',           'label': 'Owner',             'type': 'text'},
        {'name': 'location',        'label': 'Location',          'type': 'text'},
        {'name': 'property',        'label': 'Property',          'type': 'text'},
        {'name': 'status',          'label': 'Status',            'type': 'select',
         'options': ['', 'Own', 'Sold', 'Loaned']},
        {'name': 'location_status', 'label': 'Disposition',       'type': 'select',
         'options': ['', 'Storage', 'Consigned', 'Missing', 'Gifted']},
        {'name': 'image',           'label': 'Image',             'type': 'file'},
        {'name': 'doc_2',           'label': 'Doc 2',             'type': 'file'},
    ],
    'items': [
        {'name': 'name',            'label': 'Name',              'type': 'text'},
        # Alphabetical, with 'Other' pinned at the end so the catch-
        # all stays out of the working set. Free-text values typed
        # before this dropdown was added still display fine on detail
        # pages — the select just can't reproduce them on edit until
        # the user picks one of the canonical entries. Same list on
        # both Mark's and Gerri's deployments since FIELDS is global.
        {'name': 'type',            'label': 'Type',              'type': 'select',
         'options': ['', 'Antiques', 'Books', 'Computer',
                     'Electronics', 'Furniture', 'Gym Equipment',
                     'Household Items', 'Jewelry', 'Kitchen',
                     'Knives', 'Other']},
        {'name': 'serial',          'label': 'Serial',            'type': 'text'},
        {'name': 'description',     'label': 'Description',       'type': 'textarea'},
        {'name': 'date',            'label': 'Purchase Date',     'type': 'date'},
        {'name': 'price',           'label': 'Price',             'type': 'number'},
        {'name': 'vendor',          'label': 'Vendor',            'type': 'text'},
        {'name': 'warranty_until',  'label': 'Warranty Until',    'type': 'date'},
        {'name': 'notes',           'label': 'Notes',             'type': 'textarea'},
        {'name': 'owner',           'label': 'Owner',             'type': 'text'},
        {'name': 'property',        'label': 'Property',          'type': 'text'},
        {'name': 'location',        'label': 'Location at Property', 'type': 'text'},
        {'name': 'status',          'label': 'Status',            'type': 'select',
         'options': ['', 'Own', 'Sold', 'Gifted', 'Lost']},
        {'name': 'image',           'label': 'Image',             'type': 'file'},
    ],
    'vehicles': [
        {'name': 'make',            'label': 'Make',              'type': 'text'},
        {'name': 'model',           'label': 'Model',             'type': 'text'},
        {'name': 'year',            'label': 'Year',              'type': 'number'},
        {'name': 'vin',             'label': 'VIN',               'type': 'text'},
        {'name': 'state',           'label': 'State',             'type': 'text'},
        {'name': 'tags',            'label': 'Tags / License',    'type': 'text'},
        {'name': 'date',            'label': 'Purchase Date',     'type': 'date'},
        {'name': 'price',           'label': 'Price',             'type': 'number'},
        {'name': 'vendor',          'label': 'Vendor',            'type': 'text'},
        {'name': 'notes',           'label': 'Notes',             'type': 'textarea'},
        {'name': 'owner',           'label': 'Owner',             'type': 'text'},
        {'name': 'property',        'label': 'Property',          'type': 'text'},
        {'name': 'status',          'label': 'Status',            'type': 'select',
         'options': ['', 'Own', 'Sold', 'Loaned']},
        {'name': 'location_status', 'label': 'Disposition',       'type': 'select',
         'options': ['', 'Storage', 'Consigned', 'Missing', 'Gifted']},
        {'name': 'image',           'label': 'Image',             'type': 'file'},
        {'name': 'insurance',       'label': 'Insurance',         'type': 'file'},
        {'name': 'invoice',         'label': 'Invoice',           'type': 'file'},
        {'name': 'registration',    'label': 'Registration',      'type': 'file'},
        {'name': 'auto_title',      'label': 'Auto Title',        'type': 'file'},
        {'name': 'insurance_label',     'label': 'Insurance Title',     'type': 'text'},
        {'name': 'invoice_label',       'label': 'Invoice Title',       'type': 'text'},
        {'name': 'registration_label',  'label': 'Registration Title',  'type': 'text'},
        {'name': 'auto_title_label',    'label': 'Auto Title Label',    'type': 'text'},
        # Slots 5..8 — fully user-supplied (file + editable title) to
        # match the property docs pattern.
        *[v for i in range(5, 9) for v in (
            {'name': f'vehicle_doc_{i}',       'label': f'Vehicle Doc {i}',       'type': 'file'},
            {'name': f'vehicle_doc_{i}_title', 'label': f'Vehicle Doc {i} Title', 'type': 'text'},
        )],
    ],
    'recordings': [
        {'name': 'title',           'label': 'Title',             'type': 'text'},
        {'name': 'artist',          'label': 'Artist',            'type': 'text'},
        {'name': 'type',            'label': 'Type',              'type': 'select',
         'options': ['', 'LP', '45', '78', 'EP', 'CD', 'Cassette', '8-Track', 'Reel', 'Digital', 'Other']},
        {'name': 'genre',           'label': 'Genre',             'type': 'text'},
        {'name': 'genre_2',         'label': 'Genre 2',           'type': 'text'},
        {'name': 'players',         'label': 'Players',           'type': 'text'},
        {'name': 'tracks',          'label': 'Tracks',            'type': 'textarea'},
        {'name': 'year_recorded',   'label': 'Year Recorded',     'type': 'text'},
        {'name': 'speed',           'label': 'Speed',             'type': 'text'},
        {'name': 'sound',           'label': 'Sound',             'type': 'select',
         'options': ['', 'Mono', 'Stereo', 'Quad', 'Surround']},
        {'name': 'like_field',      'label': 'Rating',            'type': 'text'},
        {'name': 'number_position', 'label': 'Number / Position', 'type': 'number'},
        {'name': 'other',           'label': 'Other',             'type': 'text'},
        {'name': 'date',            'label': 'Purchase Date',     'type': 'date'},
        {'name': 'price',           'label': 'Price',             'type': 'number'},
        {'name': 'vendor',          'label': 'Vendor',            'type': 'text'},
        {'name': 'notes',           'label': 'Notes',             'type': 'textarea'},
        {'name': 'owner',           'label': 'Owner',             'type': 'text'},
        {'name': 'property',        'label': 'Property',          'type': 'text'},
        {'name': 'status',          'label': 'Status',            'type': 'select',
         'options': ['', 'Own', 'Sold', 'Loaned']},
        {'name': 'location_status', 'label': 'Disposition',       'type': 'select',
         'options': ['', 'Storage', 'Consigned', 'Missing', 'Gifted']},
        {'name': 'image',           'label': 'Cover Image',       'type': 'file'},
        {'name': 'receipt',         'label': 'Receipt',           'type': 'file'},
    ],
    'audio': [
        {'name': 'make',            'label': 'Make',              'type': 'text'},
        {'name': 'model',           'label': 'Model',             'type': 'text'},
        {'name': 'type',            'label': 'Type',              'type': 'select',
         'options': ['', 'Amplifier', 'CD Player', 'DAC', 'Pre-Amp', 'Scaler', 'Speakers', 'Streamer', 'Tape Deck', 'Turntable', 'Phono Stage', 'Headphones', 'Cables', 'Other']},
        {'name': 'serial_number',   'label': 'Serial Number',     'type': 'text'},
        {'name': 'date',            'label': 'Purchase Date',     'type': 'date'},
        {'name': 'price',           'label': 'Price',             'type': 'number'},
        {'name': 'vendor',          'label': 'Vendor',            'type': 'text'},
        {'name': 'notes',           'label': 'Notes',             'type': 'textarea'},
        {'name': 'owner',           'label': 'Owner',             'type': 'text'},
        {'name': 'property',        'label': 'Property',          'type': 'text'},
        {'name': 'status',          'label': 'Status',            'type': 'select',
         'options': ['', 'Own', 'Sold', 'Loaned']},
        {'name': 'location_status', 'label': 'Disposition',       'type': 'select',
         'options': ['', 'Storage', 'Consigned', 'Missing', 'Gifted']},
        {'name': 'image',           'label': 'Image',             'type': 'file'},
    ],
    'rifles': [
        {'name': 'make',            'label': 'Make',              'type': 'text'},
        {'name': 'model',           'label': 'Model',             'type': 'text'},
        {'name': 'caliber',         'label': 'Caliber',           'type': 'text'},
        {'name': 'serial_number',   'label': 'Serial Number',     'type': 'text'},
        {'name': 'date',            'label': 'Purchase Date',     'type': 'date'},
        {'name': 'price',           'label': 'Price',             'type': 'number'},
        {'name': 'vendor',          'label': 'Vendor',            'type': 'text'},
        {'name': 'notes',           'label': 'Notes',             'type': 'textarea'},
        {'name': 'owner',           'label': 'Owner',             'type': 'text'},
        {'name': 'property',        'label': 'Property',          'type': 'text'},
        {'name': 'status',          'label': 'Status',            'type': 'select',
         'options': ['', 'Own', 'Sold', 'Loaned']},
        {'name': 'location_status', 'label': 'Disposition',       'type': 'select',
         'options': ['', 'Storage', 'Consigned', 'Missing', 'Gifted']},
        {'name': 'image',           'label': 'Image',             'type': 'file'},
    ],
    'credit_cards': [
        {'name': 'name',            'label': 'Card Name',         'type': 'text'},
        {'name': 'number',          'label': 'Card Number',       'type': 'text'},
        {'name': 'cvc',             'label': 'CVC',               'type': 'text'},
        {'name': 'cvc_2',           'label': 'CVC 2',             'type': 'text'},
        {'name': 'expiration',      'label': 'Expiration',        'type': 'date'},
        {'name': 'description',     'label': 'Description',       'type': 'textarea'},
        {'name': 'billing_address', 'label': 'Billing Address',   'type': 'textarea'},
        {'name': 'billing_short',   'label': 'Billing Short',     'type': 'text'},
        {'name': 'owner',           'label': 'Owner',             'type': 'text'},
        {'name': 'image_front',     'label': 'Image (Front)',     'type': 'file'},
        {'name': 'image_back',      'label': 'Image (Back)',      'type': 'file'},
    ],
    'properties': [
        {'name': 'name',            'label': 'Property Name',     'type': 'text'},
        {'name': 'short_name',      'label': 'Short Name',        'type': 'text'},
        {'name': 'type',            'label': 'Type',              'type': 'select',
         'options': [''] + VALUE_LISTS['property_type']},
        {'name': 'address',         'label': 'Address',           'type': 'textarea'},
        {'name': 'year_built',      'label': 'Year Built',        'type': 'number'},
        {'name': 'ein',             'label': 'EIN',               'type': 'text'},
        {'name': 'llc',             'label': 'LLC',               'type': 'text'},
        {'name': 'wifi',            'label': 'WiFi Password',     'type': 'text'},
        {'name': 'wifi_name',       'label': 'WiFi Name (SSID)',  'type': 'text'},
        {'name': 'wifi_2',          'label': 'WiFi Password 2',   'type': 'text'},
        {'name': 'wifi_name_2',     'label': 'WiFi Name 2 (SSID)','type': 'text'},
        {'name': 'date',            'label': 'Purchase Date',     'type': 'date'},
        {'name': 'price',           'label': 'Price',             'type': 'number'},
        {'name': 'notes',           'label': 'Notes',             'type': 'textarea'},
        {'name': 'status',          'label': 'Status',            'type': 'select',
         'options': ['', 'Own', 'Sold']},
        {'name': 'owner',           'label': 'Owner',             'type': 'select',
         'options': [''] + VALUE_LISTS['owner']},
        {'name': 'archive',         'label': 'Archive',           'type': 'text'},
        {'name': 'image',           'label': 'Image',             'type': 'file'},
        # Ten freeform document slots with editable titles. Two rows of
        # five on the detail page so the user can drop deeds/insurance/
        # warranties/etc. with their own labels.
        *[v for i in range(1, 11) for v in (
            {'name': f'doc_{i}_title', 'label': f'Doc {i} Title', 'type': 'text'},
            {'name': f'doc_{i}',       'label': f'Doc {i}',       'type': 'file'},
        )],
        # Alarm code list — 8 rows of (Entry, Code, Notes) under the
        # existing alarm fields, with delete-row + shift-up like meds.
        *[v for i in range(1, 9) for v in (
            {'name': f'alarm_codes_entry_{i}', 'label': f'Alarm Entry {i}', 'type': 'text'},
            {'name': f'alarm_codes_code_{i}',  'label': f'Alarm Code {i}',  'type': 'text'},
            {'name': f'alarm_codes_note_{i}',  'label': f'Alarm Note {i}',  'type': 'text'},
        )],
        # People list — 10 rows of (Name, Role, Phone, Email, Notes).
        # Sits above Documents on the property detail. Same per-row ×
        # delete + shift-up behaviour as the alarm-codes / medications
        # tables.
        *[v for i in range(1, 11) for v in (
            {'name': f'people_name_{i}',  'label': f'Person {i} Name',  'type': 'text'},
            {'name': f'people_role_{i}',  'label': f'Person {i} Role',  'type': 'text'},
            {'name': f'people_phone_{i}', 'label': f'Person {i} Phone', 'type': 'text'},
            {'name': f'people_email_{i}', 'label': f'Person {i} Email', 'type': 'text'},
            {'name': f'people_note_{i}',  'label': f'Person {i} Notes', 'type': 'text'},
        )],
    ],
    'persons': [
        {'name': 'name',                  'label': 'Name',                   'type': 'text'},
        {'name': 'owner',                 'label': 'Owner',                  'type': 'text'},
        {'name': 'phone',                 'label': 'Phone',                  'type': 'text'},
        {'name': 'home_address',          'label': 'Home Address',           'type': 'textarea'},
        {'name': 'birth_date',            'label': 'Birth Date',             'type': 'date'},
        {'name': 'blood_type',            'label': 'Blood Type',             'type': 'text'},
        {'name': 'ssn',                   'label': 'SSN',                    'type': 'text'},
        {'name': 'spouse',                'label': 'Spouse',                 'type': 'text'},
        {'name': 'spouse_name_and_phone', 'label': 'Spouse Name & Phone',    'type': 'text'},
        {'name': 'primary_care_physician','label': 'Primary Care Physician', 'type': 'text'},
        {'name': 'prescriptions',         'label': 'Prescriptions',          'type': 'textarea'},
        {'name': 'health_notes',          'label': 'Health Notes',           'type': 'textarea'},
        {'name': 'notes',                 'label': 'Notes',                  'type': 'textarea'},
        {'name': 'text_1',                'label': 'Text 1',                 'type': 'text'},
        {'name': 'text_2',                'label': 'Text 2',                 'type': 'text'},
        {'name': 'text_3',                'label': 'Text 3',                 'type': 'text'},
        {'name': 'text_4',                'label': 'Text 4',                 'type': 'text'},
        {'name': 'head_shot',             'label': 'Head Shot',              'type': 'file'},
        {'name': 'image_1',               'label': 'Image 1',                'type': 'file'},
        {'name': 'image_7',               'label': 'Image 7',                'type': 'file'},
        {'name': 'image_9',               'label': 'Image 9',                'type': 'file'},
        {'name': 'image_text_1',          'label': 'Image Caption 1',        'type': 'text'},
        {'name': 'image_text_2',          'label': 'Image Caption 2',        'type': 'text'},
        {'name': 'image_text_3',          'label': 'Image Caption 3',        'type': 'text'},
        {'name': 'image_text_4',          'label': 'Image Caption 4',        'type': 'text'},
        {'name': 'image_text_5',          'label': 'Image Caption 5',        'type': 'text'},
        {'name': 'image_text_6',          'label': 'Image Caption 6',        'type': 'text'},
        {'name': 'image_text_7',          'label': 'Image Caption 7',        'type': 'text'},
        {'name': 'image_text_8',          'label': 'Image Caption 8',        'type': 'text'},
        {'name': 'image_text_9',          'label': 'Image Caption 9',        'type': 'text'},
        {'name': 'license_obverse',       'label': "License (Front)",        'type': 'file'},
        {'name': 'license_reverse',       'label': "License (Back)",         'type': 'file'},
        {'name': 'license_number',        'label': 'License Number',         'type': 'text'},
        {'name': 'passport',              'label': 'Passport',               'type': 'file'},
        {'name': 'passport_number',       'label': 'Passport Number',        'type': 'text'},
        {'name': 'medicare',              'label': 'Medicare Card',          'type': 'file'},
        {'name': 'medicare_number',       'label': 'Medicare Number',        'type': 'text'},
        {'name': 'health_card_obv',       'label': 'Health Card (Front)',    'type': 'file'},
        {'name': 'health_card_rev',       'label': 'Health Card (Back)',     'type': 'file'},
        {'name': 'health_insurance_number','label': 'Health Insurance Number','type': 'text'},
        {'name': 'other_health_1',        'label': 'Other Health 1',         'type': 'file'},
        {'name': 'other_health_2',        'label': 'Other Health 2',         'type': 'file'},
        {'name': 'global_entry',          'label': 'Global Entry',           'type': 'file'},
        {'name': 'global_entry_number',   'label': 'Global Entry Number',    'type': 'text'},
        {'name': 'eye_prescription',      'label': 'Eye Prescription',       'type': 'file'},
        *[{'name': f'med_name_{i}', 'label': f'Medication {i}', 'type': 'text'} for i in range(1, 8)],
        *[{'name': f'med_dose_{i}', 'label': f'Dosage {i}',     'type': 'text'} for i in range(1, 8)],
        *[{'name': f'med_note_{i}', 'label': f'Med Note {i}',   'type': 'text'} for i in range(1, 8)],
        # Persons IDs tab — slots 1+2 reuse the existing license_obverse /
        # license_reverse columns with a hardwired "License Front/Back"
        # title; slots 3..8 are user-supplied (file + editable title).
        *[v for i in range(3, 9) for v in (
            {'name': f'id_doc_{i}',       'label': f'ID Doc {i}',       'type': 'file'},
            {'name': f'id_doc_{i}_title', 'label': f'ID Doc {i} Title', 'type': 'text'},
        )],
        # Persons Health tab — slots 1+2 reuse health_card_obv/rev with
        # a hardwired "Health Card Front/Back" title; slots 3..8 are
        # user-supplied (file + editable title).
        *[v for i in range(3, 9) for v in (
            {'name': f'health_doc_{i}',       'label': f'Health Doc {i}',       'type': 'file'},
            {'name': f'health_doc_{i}_title', 'label': f'Health Doc {i} Title', 'type': 'text'},
        )],
    ],
}


def _parse_hide_fields(raw):
    """STUFFAPP_HIDE_FIELDS format: 'cat:field1,field2;cat2:field3'.
    Per-tenant field hiding — drops listed fields from forms, detail
    views, and save_field validation so the surface is consistent.
    Existing data in those columns stays in the DB (just not shown)."""
    out = {}
    for part in (raw or '').split(';'):
        part = part.strip()
        if ':' not in part:
            continue
        cat, names = part.split(':', 1)
        cat = cat.strip()
        if cat not in CATEGORIES:
            continue
        out[cat] = {n.strip() for n in names.split(',') if n.strip()}
    return out


HIDE_FIELDS = _parse_hide_fields(os.environ.get('STUFFAPP_HIDE_FIELDS'))


def visible_fields(category):
    """FIELDS[category] minus tenant-hidden fields. Use this everywhere
    forms render or validation runs so a hidden field is invisible end
    to end (no render, no save, no clear)."""
    fields = FIELDS.get(category) or []
    hidden = HIDE_FIELDS.get(category)
    if not hidden:
        return fields
    return [f for f in fields if f['name'] not in hidden]


# List-view extra info fields per category
LIST_EXTRA_FIELDS = {
    'watches':      ['metal', 'reference', 'vendor', 'property'],
    'coins':        ['metal', 'denomination', 'date_1_text', 'grade'],
    'cameras':      ['digital_film', 'film_size', 'lens_mount', 'megapixels', 'serial_number', 'vendor', 'price', 'property'],
    'lenses':       ['mount', 'aperture', 'filter_size', 'length', 'serial_number', 'vendor', 'price', 'property'],
    'pens':         ['type', 'action', 'nib', 'cartridge', 'vendor', 'price', 'property'],
    'art':          ['medium', 'year', 'dimensions', 'vendor', 'price', 'location', 'property'],
    'items':        ['type', 'vendor', 'price', 'location', 'property'],
    'vehicles':     ['year', 'vin', 'state', 'tags', 'vendor', 'price', 'property'],
    'recordings':   ['type', 'genre', 'year_recorded', 'speed', 'vendor', 'price', 'property'],
    'audio':        ['type', 'serial_number', 'vendor', 'price', 'property'],
    'rifles':       ['caliber', 'serial_number', 'vendor', 'price', 'property'],
    'credit_cards': ['number', 'expiration', 'billing_short', 'description', 'owner'],
    'properties':   ['type', 'address', 'short_name', 'year_built', 'llc', 'price', 'status'],
    'persons':      ['phone', 'birth_date', 'blood_type', 'spouse'],
}

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def _strip_diacritics(s):
    """Fold a string to ASCII lowercase, dropping diacritical marks so
    'Roumégoux' compares as 'roumegoux' and 'Blåder' as 'blader'.
    SQLite's built-in LOWER() / NOCASE only handles ASCII A-Z, which
    leaves multi-byte UTF-8 characters in odd positions in a sort.
    """
    import unicodedata as _ud
    if s is None:
        return ''
    return _ud.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode('ascii').lower()


def _nodiacritic_collation(a, b):
    """Custom SQLite collation: lexicographic order on the diacritic-
    folded, lowercased forms. Used in CATEGORY_ORDER_BY for art (and
    anywhere else humans expect 'café' to sort next to 'cafe')."""
    a = _strip_diacritics(a)
    b = _strip_diacritics(b)
    if a < b: return -1
    if a > b: return 1
    return 0


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        # Register the diacritic-folding collation on every fresh
        # connection — collations are per-connection in sqlite3.
        g.db.create_collation('NODIACRITIC', _nodiacritic_collation)
        # NODIA(text) — function form of the same fold, usable in WHERE
        # clauses like NODIA(brand) LIKE ?. Lets free-text search match
        # 'Urban Jürgensen' from the term 'urban jurg', and folds both
        # pre-composed and decomposed Unicode variants to the same form.
        g.db.create_function('NODIA', 1, _strip_diacritics,
                             deterministic=True)
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    schema_path = os.path.join(BASE_DIR, 'schema.sql')
    with open(schema_path, 'r') as f:
        db.executescript(f.read())
    # Idempotent column additions for existing DBs
    for stmt in (
        'ALTER TABLE watches ADD COLUMN value REAL',
        'ALTER TABLE watches ADD COLUMN results TEXT',
        'ALTER TABLE watches ADD COLUMN value_searched_at TEXT',
        'ALTER TABLE watches ADD COLUMN specs_searched_at TEXT',
        'ALTER TABLE art ADD COLUMN object_notes TEXT',
        'ALTER TABLE art ADD COLUMN art_searched_at TEXT',
        'ALTER TABLE coins ADD COLUMN official TEXT',
        'ALTER TABLE coins ADD COLUMN specs_searched_at TEXT',
        'ALTER TABLE vehicles ADD COLUMN auto_title TEXT',
        'ALTER TABLE vehicles ADD COLUMN insurance_label TEXT',
        'ALTER TABLE users ADD COLUMN row_filters TEXT',
        'ALTER TABLE users ADD COLUMN last_export_at TEXT',
        'ALTER TABLE persons ADD COLUMN owner TEXT',
        'ALTER TABLE vehicles ADD COLUMN invoice_label TEXT',
        'ALTER TABLE vehicles ADD COLUMN registration_label TEXT',
        'ALTER TABLE vehicles ADD COLUMN auto_title_label TEXT',
        # Vehicle docs slots 5..8 (full user-supplied title + file)
        *[f'ALTER TABLE vehicles ADD COLUMN vehicle_doc_{i} TEXT'        for i in range(5, 9)],
        *[f'ALTER TABLE vehicles ADD COLUMN vehicle_doc_{i}_title TEXT'  for i in range(5, 9)],
        'ALTER TABLE watches ADD COLUMN container_1 TEXT',
        'ALTER TABLE watches ADD COLUMN container_2 TEXT',
        'ALTER TABLE art ADD COLUMN doc_2 TEXT',
        'ALTER TABLE properties ADD COLUMN doc_1 TEXT',
        'ALTER TABLE properties ADD COLUMN doc_1_title TEXT',
        'ALTER TABLE properties ADD COLUMN doc_2 TEXT',
        'ALTER TABLE properties ADD COLUMN doc_2_title TEXT',
        'ALTER TABLE properties ADD COLUMN doc_3 TEXT',
        'ALTER TABLE properties ADD COLUMN doc_3_title TEXT',
        'ALTER TABLE properties ADD COLUMN doc_4 TEXT',
        'ALTER TABLE properties ADD COLUMN doc_4_title TEXT',
        'ALTER TABLE properties ADD COLUMN doc_5 TEXT',
        'ALTER TABLE properties ADD COLUMN doc_5_title TEXT',
        'ALTER TABLE properties ADD COLUMN doc_6 TEXT',
        'ALTER TABLE properties ADD COLUMN doc_6_title TEXT',
        'ALTER TABLE properties ADD COLUMN doc_7 TEXT',
        'ALTER TABLE properties ADD COLUMN doc_7_title TEXT',
        'ALTER TABLE properties ADD COLUMN doc_8 TEXT',
        'ALTER TABLE properties ADD COLUMN doc_8_title TEXT',
        'ALTER TABLE properties ADD COLUMN doc_9 TEXT',
        'ALTER TABLE properties ADD COLUMN doc_9_title TEXT',
        'ALTER TABLE properties ADD COLUMN doc_10 TEXT',
        'ALTER TABLE properties ADD COLUMN doc_10_title TEXT',
        # Flexible documents column — JSON array of {title, filename}
        # objects, replacing the fixed doc_1..10 + doc_N_title slots.
        # The legacy columns above are kept dual-populated during the
        # transition so older code paths and the export/sweep flows
        # don't break mid-deploy. They'll be dropped once every read
        # path moves to the JSON column.
        'ALTER TABLE properties ADD COLUMN documents TEXT',
        # Same JSON-backed documents column for the simpler categories
        # that previously had 1-2 fixed user-doc slots. Receipts stay
        # as their own fixed column on each — only the "free" doc slots
        # move into JSON. Backfilled at boot from the legacy columns.
        'ALTER TABLE watches    ADD COLUMN documents TEXT',
        'ALTER TABLE coins      ADD COLUMN documents TEXT',
        'ALTER TABLE art        ADD COLUMN documents TEXT',
        'ALTER TABLE vehicles   ADD COLUMN documents TEXT',
        'ALTER TABLE pens       ADD COLUMN documents TEXT',
        'ALTER TABLE recordings ADD COLUMN documents TEXT',
        'ALTER TABLE rifles     ADD COLUMN documents TEXT',
        'ALTER TABLE audio      ADD COLUMN documents TEXT',
        'ALTER TABLE cameras    ADD COLUMN documents TEXT',
        'ALTER TABLE lenses     ADD COLUMN documents TEXT',
        # location_status (Storage / Consigned / Missing / Gifted) is a
        # second status axis distinct from the lifecycle `status` field.
        # Declared in FIELDS with type='select', so the search builder
        # references it in WHERE — must exist on every item table or
        # any text search 500s.
        'ALTER TABLE watches    ADD COLUMN location_status TEXT',
        'ALTER TABLE cameras    ADD COLUMN location_status TEXT',
        'ALTER TABLE lenses     ADD COLUMN location_status TEXT',
        'ALTER TABLE pens       ADD COLUMN location_status TEXT',
        'ALTER TABLE art        ADD COLUMN location_status TEXT',
        'ALTER TABLE vehicles   ADD COLUMN location_status TEXT',
        'ALTER TABLE recordings ADD COLUMN location_status TEXT',
        'ALTER TABLE rifles     ADD COLUMN location_status TEXT',
        'ALTER TABLE audio      ADD COLUMN location_status TEXT',
        # Persons has TWO independent doc-rows (IDs and Health) because
        # the tabs are semantically distinct. License front/back +
        # health card front/back stay as fixed columns (their semantic
        # number fields — license_number, health_insurance_number —
        # are tied to those slots). Only the user-titled id_doc_3..8
        # and health_doc_3..8 slots compact into these JSON columns.
        'ALTER TABLE persons  ADD COLUMN id_documents TEXT',
        'ALTER TABLE persons  ADD COLUMN health_documents TEXT',
        # Alarm-codes list (8 rows × {entry, code, note})
        *[f'ALTER TABLE properties ADD COLUMN alarm_codes_entry_{i} TEXT' for i in range(1, 9)],
        *[f'ALTER TABLE properties ADD COLUMN alarm_codes_code_{i} TEXT' for i in range(1, 9)],
        *[f'ALTER TABLE properties ADD COLUMN alarm_codes_note_{i} TEXT' for i in range(1, 9)],
        # People list (10 rows × {name, role, phone, note})
        *[f'ALTER TABLE properties ADD COLUMN people_name_{i} TEXT'  for i in range(1, 11)],
        *[f'ALTER TABLE properties ADD COLUMN people_role_{i} TEXT'  for i in range(1, 11)],
        *[f'ALTER TABLE properties ADD COLUMN people_phone_{i} TEXT' for i in range(1, 11)],
        *[f'ALTER TABLE properties ADD COLUMN people_note_{i} TEXT'  for i in range(1, 11)],
        *[f'ALTER TABLE properties ADD COLUMN people_email_{i} TEXT' for i in range(1, 11)],
        # Drop legacy single-value alarm fields — replaced by the
        # alarm-codes table. Idempotent: try/except below treats
        # already-dropped columns as a no-op.
        'ALTER TABLE properties DROP COLUMN alarm_company',
        'ALTER TABLE properties DROP COLUMN alarm_account',
        'ALTER TABLE properties DROP COLUMN alarm_code_1',
        'ALTER TABLE properties DROP COLUMN alarm_password',
        'ALTER TABLE properties DROP COLUMN alarm_phone',
        'ALTER TABLE properties DROP COLUMN alarm_notes',
        'ALTER TABLE properties ADD COLUMN owner TEXT',
        'ALTER TABLE properties ADD COLUMN wifi_name TEXT',
        # Second WiFi network (e.g. main + guest) — paired pair so
        # the property detail can show two rows of network/password.
        'ALTER TABLE properties ADD COLUMN wifi_name_2 TEXT',
        'ALTER TABLE properties ADD COLUMN wifi_2 TEXT',
        # Persistent FX rate cache — historical rates never change, so
        # once we've fetched (CHF, 2024-03-15) once we never need to
        # call out again. Survives redeploys and any future migration
        # of the upstream FX API.
        ('CREATE TABLE IF NOT EXISTS fx_rates ('
         'currency TEXT NOT NULL, '
         'date TEXT NOT NULL, '
         'usd_rate REAL NOT NULL, '
         'fetched_at TEXT NOT NULL, '
         'PRIMARY KEY (currency, date))'),
        'ALTER TABLE topics ADD COLUMN image TEXT',
        'ALTER TABLE recordings ADD COLUMN players TEXT',
        'ALTER TABLE recordings ADD COLUMN notes_urls TEXT',
        'ALTER TABLE recordings ADD COLUMN tracks TEXT',
        'ALTER TABLE coins ADD COLUMN history_region TEXT',
        'ALTER TABLE coins ADD COLUMN history_authority TEXT',
        'ALTER TABLE coins ADD COLUMN history_searched_at TEXT',
        'ALTER TABLE coins ADD COLUMN history_context TEXT',
        'ALTER TABLE coins ADD COLUMN image_audit_match TEXT',
        'ALTER TABLE coins ADD COLUMN image_audit_confidence REAL',
        'ALTER TABLE coins ADD COLUMN image_audit_reason TEXT',
        'ALTER TABLE coins ADD COLUMN image_audit_at TEXT',
        'ALTER TABLE coins ADD COLUMN cat_id TEXT',
        'ALTER TABLE watches ADD COLUMN cat_id TEXT',
        'ALTER TABLE watches ADD COLUMN escapement TEXT',
        'ALTER TABLE watches ADD COLUMN escape_wheel TEXT',
        'ALTER TABLE watches RENAME COLUMN escape_wheel TO balance_wheel',
        'ALTER TABLE watches ADD COLUMN balance_wheel TEXT',
        'ALTER TABLE watches ADD COLUMN calibre_notes TEXT',
        'ALTER TABLE watches ADD COLUMN order_purchase_price REAL',
        'ALTER TABLE watches ADD COLUMN order_deposit REAL',
        'ALTER TABLE watches ADD COLUMN order_deposit_percent REAL',
        'ALTER TABLE watches ADD COLUMN expected_delivery_date TEXT',
        'ALTER TABLE watches ADD COLUMN actual_delivery_date TEXT',
        'ALTER TABLE watches ADD COLUMN order_balance REAL',
        'ALTER TABLE art ADD COLUMN cat_id TEXT',
        'ALTER TABLE persons ADD COLUMN license_number TEXT',
        'ALTER TABLE persons ADD COLUMN passport_number TEXT',
        'ALTER TABLE persons ADD COLUMN global_entry_number TEXT',
        'ALTER TABLE persons ADD COLUMN medicare_number TEXT',
        'ALTER TABLE persons ADD COLUMN health_insurance_number TEXT',
        'ALTER TABLE persons ADD COLUMN other_health_1 TEXT',
        'ALTER TABLE persons ADD COLUMN other_health_2 TEXT',
        *[f'ALTER TABLE persons ADD COLUMN med_name_{i} TEXT' for i in range(1, 8)],
        *[f'ALTER TABLE persons ADD COLUMN med_dose_{i} TEXT' for i in range(1, 8)],
        *[f'ALTER TABLE persons ADD COLUMN med_note_{i} TEXT' for i in range(1, 8)],
        # IDs / Health 8-tile docs (slots 3..8 are user-titled)
        *[f'ALTER TABLE persons ADD COLUMN id_doc_{i} TEXT'           for i in range(3, 9)],
        *[f'ALTER TABLE persons ADD COLUMN id_doc_{i}_title TEXT'     for i in range(3, 9)],
        *[f'ALTER TABLE persons ADD COLUMN health_doc_{i} TEXT'       for i in range(3, 9)],
        *[f'ALTER TABLE persons ADD COLUMN health_doc_{i}_title TEXT' for i in range(3, 9)],
    ):
        try:
            db.execute(stmt)
        except sqlite3.OperationalError:
            pass
    db.commit()
    _ensure_owner_user(db)
    _normalize_owned_status_values(db)
    _backfill_blank_status_own(db)
    db.commit()

    # Migration-state ledger: one row per applied one-shot data
    # migration so subsequent boots skip them. Used for the kind of
    # change where boot-time helpers can't infer "needs to run" from
    # row state alone — e.g. the post-1ebf6ed updated_at bump that
    # has to walk every row regardless of current contents.
    db.execute("CREATE TABLE IF NOT EXISTS migration_state ("
               "key TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
    db.commit()

    # One-shot: when commit 1ebf6ed added the per-row _data.json
    # snapshot writer to the export, every row that already existed
    # needed to flow through the export at least once to gain a
    # snapshot file. The export's incremental `since` filter excludes
    # rows whose updated_at hasn't moved, so any record not edited
    # since 1ebf6ed stayed frozen in pre-snapshot state on local
    # mirrors (e.g. the user's whole Atelier de Chronométrie folder
    # had files but no _data.json files, breaking sweep round-trip).
    # Bumping updated_at on every row in every export-eligible table
    # forces the next incremental export to re-include them all.
    # Gated by a sentinel so subsequent boots don't re-bump.
    if not db.execute(
        "SELECT 1 FROM migration_state WHERE key = ?",
        ('data_json_initial_bump_v1',),
    ).fetchone():
        _bump_now = datetime.utcnow().isoformat()
        for _cat, _info in CATEGORIES.items():
            _table = _info.get('table')
            if not _table:
                continue
            try:
                db.execute(
                    f"UPDATE {_table} SET updated_at = ? "
                    f"WHERE updated_at IS NOT NULL",
                    (_bump_now,),
                )
            except sqlite3.OperationalError:
                pass
        db.execute(
            "INSERT INTO migration_state (key, applied_at) VALUES (?, ?)",
            ('data_json_initial_bump_v1', _bump_now),
        )
        db.commit()

    # One-shot: nuke the watches.image_rev column. Legacy FileMaker
    # import populated it with copies of the cover image on every
    # watch, so the export emitted bogus '<ident> — Back.<ext>' files
    # everywhere. The Back slot has been removed from FIELDS,
    # EXPORT_LAYOUT, FM_FIELD_MAP, and import_fm_images.py — this
    # one-shot cleans up the existing data:
    #   1) Tombstone every '<ident> — Back.<ext>' so the next
    #      syncDown removes the orphan from the user's local mirror.
    #   2) NULL image_rev so subsequent exports don't emit anything.
    # Tombstones use the actual extension from each row's image_rev
    # value (different rows may have .png / .jpg / .heic etc).
    # Coins (image_1 / image_2 = Obverse/Reverse) are NOT touched —
    # that pair is genuine identity for numismatics.
    if not db.execute(
        "SELECT 1 FROM migration_state WHERE key = ?",
        ('watches_drop_image_rev_v1',),
    ).fetchone():
        _now = datetime.utcnow().isoformat()
        try:
            _watch_rows = db.execute(
                "SELECT * FROM watches WHERE image_rev IS NOT NULL "
                "AND TRIM(image_rev) != ''"
            ).fetchall()
        except sqlite3.OperationalError:
            _watch_rows = []
        for _row in _watch_rows:
            try:
                _back_filename = (_row['image_rev'] or '').strip()
                if _back_filename:
                    _record_tombstone(db, 'watches', _row, 'Back',
                                      _back_filename)
            except Exception:
                app.logger.exception(
                    'image_rev tombstone failed for watch %s', _row['id']
                )
        try:
            db.execute(
                "UPDATE watches SET image_rev = NULL, updated_at = ? "
                "WHERE image_rev IS NOT NULL",
                (_now,),
            )
        except sqlite3.OperationalError:
            pass
        db.execute(
            "INSERT INTO migration_state (key, applied_at) VALUES (?, ?)",
            ('watches_drop_image_rev_v1', _now),
        )
        db.commit()

    _backfill_meds_from_prescriptions(db)
    _backfill_persons_doc_slots(db)
    _backfill_properties_documents_json(db)
    _backfill_docs_json(db, 'watches', 'documents', [
        ('container_1', None, 'Document 1'),
        ('container_2', None, 'Document 2'),
    ])
    _backfill_docs_json(db, 'coins', 'documents', [
        ('document_1', None, 'Doc 1'),
        ('document_2', None, 'Doc 2'),
    ])
    _backfill_docs_json(db, 'art', 'documents', [
        ('doc_2', None, 'Doc 2'),
    ])
    # All item categories now fold receipt into the dynamic docs row
    # instead of rendering it as a fixed cell. Recordings excluded:
    # FileMaker historically reused the receipt slot to hold the album
    # cover. Same issue happens elsewhere too (vehicles' Auto Title
    # column got the cover image, etc.), so the strip-phantom helper
    # below sweeps every item table for cover-image duplicates.
    for _t in ('art', 'coins', 'watches', 'pens', 'rifles', 'audio',
               'cameras', 'lenses'):
        _migrate_receipt_into_documents(db, _t)
        # Collapse historical "Receipt"-titled duplicates left behind
        # by an earlier boot that ran the migration with only a
        # filename-based dedupe — see _dedupe_receipt_docs for the
        # full story.
        _dedupe_receipt_docs(db, _t)
    _strip_phantom_cover_image_docs(db)
    _strip_redundant_receipts(db)
    _backfill_docs_json(db, 'vehicles', 'documents', [
        ('insurance',     'insurance_label',     'Insurance'),
        ('invoice',       'invoice_label',       'Invoice'),
        ('registration',  'registration_label',  'Registration'),
        ('auto_title',    'auto_title_label',    'Auto Title'),
        ('vehicle_doc_5', 'vehicle_doc_5_title', 'Doc 5'),
        ('vehicle_doc_6', 'vehicle_doc_6_title', 'Doc 6'),
        ('vehicle_doc_7', 'vehicle_doc_7_title', 'Doc 7'),
        ('vehicle_doc_8', 'vehicle_doc_8_title', 'Doc 8'),
    ])
    try:
        db.execute(
            "UPDATE vehicles SET owner = 'Mark', updated_at = ? "
            "WHERE owner IS NULL OR TRIM(owner) = ''",
            (datetime.utcnow().isoformat(),),
        )
    except sqlite3.OperationalError:
        pass
    _backfill_docs_json(db, 'persons', 'id_documents', [
        (f'id_doc_{i}', f'id_doc_{i}_title', f'ID Doc {i}')
        for i in range(3, 9)
    ])
    _backfill_docs_json(db, 'persons', 'health_documents', [
        (f'health_doc_{i}', f'health_doc_{i}_title', f'Health Doc {i}')
        for i in range(3, 9)
    ])
    db.commit()
    # Apply field-alias normalizations to legacy rows so the UI never has to
    # handle synonym values. Runs every boot — cheap (small table, indexed
    # by the rewritten column being equal to a constant) and idempotent.
    for (table, field), aliases in FIELD_ALIASES.items():
        for synonym, canonical in aliases.items():
            try:
                db.execute(
                    f"UPDATE {table} SET {field} = ? "
                    f"WHERE LOWER(TRIM({field})) = ?",
                    (canonical, synonym),
                )
            except sqlite3.OperationalError:
                pass

    # One-time consolidation: every item record stored under either
    # "Truckee" or "Martis Camp" snaps to the short form "Martis"
    # going forward. Idempotent — re-running this migration on an
    # already-Martis row updates 0 rows.
    for cat, field in CATEGORY_PROPERTY_FIELD.items():
        table = CATEGORIES[cat]['table']
        try:
            db.execute(
                f"UPDATE {table} SET {field} = 'Martis' "
                f"WHERE LOWER(TRIM(COALESCE({field}, ''))) "
                f"      IN ('truckee', 'martis camp')"
            )
        except sqlite3.OperationalError:
            pass

    # Apr 2026 property cleanup, applied once at boot. Strips legacy
    # FileMaker-era prefixes (Ghent:, NYC:, SF:), folds short-form
    # abbreviations (Carp, SF, Montecito) to canonical names, and
    # migrates status-like values out of the property column into
    # the new location_status axis. Each UPDATE is idempotent — a row
    # already in canonical form is left alone.
    _apply_property_renames(db)

    # Compact any fully-empty entries left behind by the brief window
    # when documents_delete blanked entries in place instead of popping.
    # The trailing "+ Add document" slot is rendered by the macro, so
    # an in-array empty has no purpose and just wastes screen space.
    _compact_empty_doc_slots(db)

    # Pen cartridges: fold the "Pilot-Namiki" variant into the canonical
    # "Pilot/Namiki" so the strict select doesn't reject existing rows.
    # Idempotent — re-running on already-folded data updates 0 rows.
    try:
        db.execute(
            "UPDATE pens SET cartridge = 'Pilot/Namiki' "
            "WHERE LOWER(TRIM(COALESCE(cartridge, ''))) = 'pilot-namiki'"
        )
    except sqlite3.OperationalError:
        pass

    # Recording genres: fold the strays that don't appear in the canonical
    # VALUE_LISTS['recording_genre'] dropdown. Each is a small-N tail of
    # the histogram. Idempotent.
    for old, new in [
        ('pop/jazzrock', 'Pop/Rock'),
        ('folk rock',    'Folk'),
        ('international','World'),
    ]:
        try:
            db.execute(
                "UPDATE recordings SET genre = ? "
                "WHERE LOWER(TRIM(COALESCE(genre, ''))) = ?",
                [new, old],
            )
        except sqlite3.OperationalError:
            pass

    # Recording notes: extract any embedded http(s) URLs into the new
    # notes_urls column and strip them out of the prose so the pills
    # row above the textarea is the only place sources appear.
    # Gated on notes_urls IS NULL so each row migrates once.
    try:
        url_re = re.compile(r'https?://[^\s<>"\']+')
        # Trailing chunks like "Sources:" / "References:" left dangling
        # after URL extraction get cleaned out.
        sources_line_re = re.compile(
            r'(?im)^[\s\-•*]*(sources?|references?|citations?)\s*:?\s*$\n?'
        )
        rows = db.execute(
            "SELECT id, notes FROM recordings WHERE notes_urls IS NULL"
        ).fetchall()
        for row in rows:
            notes = (row['notes'] or '')
            urls_found = url_re.findall(notes)
            if not urls_found:
                # Mark as processed so re-runs skip it.
                db.execute(
                    "UPDATE recordings SET notes_urls = '' WHERE id = ?",
                    (row['id'],),
                )
                continue
            # Strip URLs + dangling Sources/References headers + collapse
            # triple+ newlines from the resulting prose.
            cleaned = url_re.sub('', notes)
            cleaned = sources_line_re.sub('', cleaned)
            cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
            # Dedupe + strip trailing punctuation that often hugs URLs in
            # prose (commas, parens, periods, brackets, quotes).
            seen = set()
            uniq = []
            for u in urls_found:
                u = u.rstrip('),.;:!?\\]>"\'')
                if u and u not in seen:
                    seen.add(u)
                    uniq.append(u)
            db.execute(
                "UPDATE recordings SET notes = ?, notes_urls = ? WHERE id = ?",
                (cleaned or None, ','.join(uniq), row['id']),
            )
    except sqlite3.OperationalError:
        pass
    db.commit()


def _parse_prescription_lines(text):
    """Split free-text prescriptions into [(name, dose), ...].
    Heuristic: dose starts at the first whitespace-separated token containing
    a digit; everything before is the name. Header lines like 'Medications:'
    are skipped."""
    out = []
    for raw in (text or '').splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.endswith(':') and not any(c.isdigit() for c in line):
            continue
        tokens = line.split()
        split_at = next((i for i, t in enumerate(tokens) if any(c.isdigit() for c in t)), None)
        if not split_at:
            out.append((line, ''))
        else:
            out.append((' '.join(tokens[:split_at]), ' '.join(tokens[split_at:])))
    return out


def _backfill_persons_doc_slots(db):
    """One-time copy of the legacy single-purpose persons file fields
    (passport / global_entry / medicare / eye_prescription /
    other_health_1 / other_health_2) into the new id_doc_3..8 and
    health_doc_3..8 slots so the data shows in the new tile layout.

    Idempotent: only writes a slot when it's currently empty, so
    re-running on a row whose target slot has been edited by hand
    leaves the user's edit alone."""
    # IDs tab — slots 3 (passport), 4 (global_entry).
    plan_ids = [
        (3, 'passport',     'passport_number',     'Passport'),
        (4, 'global_entry', 'global_entry_number', 'Global Entry'),
    ]
    # Health tab — slots 3..6
    plan_health = [
        (3, 'medicare',         'medicare_number', 'Medicare Card'),
        (4, 'eye_prescription', None,              'Eye Prescription'),
        (5, 'other_health_1',   None,              'Other Health 1'),
        (6, 'other_health_2',   None,              'Other Health 2'),
    ]

    def existing_cols():
        return {r['name'] for r in db.execute("PRAGMA table_info(persons)").fetchall()}
    cols = existing_cols()

    def copy_one(slot_prefix, slot_idx, src_col, num_col, base_label):
        if src_col not in cols: return
        dst_file = f'{slot_prefix}_doc_{slot_idx}'
        dst_title = f'{slot_prefix}_doc_{slot_idx}_title'
        if dst_file not in cols or dst_title not in cols: return
        sel = f"SELECT id, {src_col}"
        if num_col and num_col in cols:
            sel += f", {num_col}"
        rows = db.execute(
            f"{sel} FROM persons WHERE {src_col} IS NOT NULL "
            f"AND TRIM({src_col}) != ''"
        ).fetchall()
        for row in rows:
            cur = db.execute(
                f"SELECT {dst_file}, {dst_title} FROM persons WHERE id = ?",
                [row['id']]
            ).fetchone()
            if cur[dst_file]:    # slot already has a file → skip
                continue
            num_val = row[num_col] if (num_col and num_col in row.keys()) else ''
            label = (base_label + (' ' + num_val if num_val else '')).strip()
            db.execute(
                f"UPDATE persons SET {dst_file} = ?, {dst_title} = COALESCE(NULLIF({dst_title},''), ?) "
                f"WHERE id = ?",
                [row[src_col], label, row['id']]
            )

    for slot, src, numc, lbl in plan_ids:
        copy_one('id', slot, src, numc, lbl)
    for slot, src, numc, lbl in plan_health:
        copy_one('health', slot, src, numc, lbl)


def _backfill_properties_documents_json(db):
    """Compact the legacy doc_1..10 + doc_N_title columns on properties
    into a single JSON array stored in `documents`. See
    `_backfill_docs_json` for the general pattern."""
    sources = []
    for i in range(1, 11):
        sources.append((f'doc_{i}', f'doc_{i}_title', ''))
    _backfill_docs_json(db, 'properties', 'documents', sources)


def _strip_redundant_receipts(db):
    """Null out the receipt column on rows where it's pointing at the
    same filename as the cover image. The legacy FileMaker import left
    the cover filename in BOTH columns on many rows, which made
    /export-files write the same JPEG twice (once as "<ident> —
    Cover.jpg", once as "<ident> — Receipt.jpg"). The phantom-doc
    cleanup catches the JSON-doc form of this; this helper takes the
    legacy fixed-column form.

    Idempotent — once the receipt is nulled it stays nulled. If the
    user later uploads a real receipt to that record it'll go in via
    the documents JSON path, not the legacy column."""
    targets = [
        ('recordings', 'image',     'receipt'),
        ('audio',      'image',     'receipt'),
        ('rifles',     'image',     'receipt'),
        ('art',        'image',     'receipt'),
        ('cameras',    'image',     'receipt'),
        ('lenses',     'image',     'receipt'),
        ('pens',       'image',     'receipt'),
        ('vehicles',   'image',     'receipt'),
        ('watches',    'image_obv', 'receipt'),
        ('coins',      'image_1',   'receipt'),
    ]
    for table, primary, secondary in targets:
        try:
            cols = {r['name'] for r in db.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()}
            if primary not in cols or secondary not in cols:
                continue
            db.execute(
                f"UPDATE {table} SET {secondary} = NULL "
                f"WHERE {primary} IS NOT NULL "
                f"AND TRIM({primary}) != '' "
                f"AND {primary} = {secondary}"
            )
        except sqlite3.OperationalError:
            pass
    db.commit()


def _migrate_receipt_into_documents(db, table):
    """One-shot: for each row of `table` with a populated `receipt`
    column, ensure a corresponding entry exists in the `documents`
    JSON array titled 'Receipt'. Idempotent (matched by filename) so
    re-running on rows whose receipt is already in JSON is a no-op.
    Inserts at index 0 so receipts retain their historical "first"
    position in the row.

    The legacy `receipt` column is left populated so old code paths
    and existing exports that still reference it keep working. The
    detail templates no longer render it as a fixed cell."""
    cols = {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if 'documents' not in cols or 'receipt' not in cols:
        return
    rows = db.execute(f"SELECT id, receipt, documents FROM {table}").fetchall()
    now = datetime.utcnow().isoformat()
    for row in rows:
        receipt = (row['receipt'] or '').strip()
        if not receipt:
            continue
        try:
            docs = json.loads(row['documents'] or '[]')
        except (TypeError, ValueError):
            docs = []
        if not isinstance(docs, list):
            docs = []
        if any(isinstance(d, dict) and (d.get('filename') or '') == receipt for d in docs):
            continue
        # Skip when ANY Receipt-titled entry already exists — even with
        # a different filename. The user's manual docs-UI upload takes
        # precedence over the legacy column. Without this guard, every
        # boot after a re-upload stacks another Receipt-titled entry,
        # which collides at export time and gets the " (2).ext" suffix.
        if any(isinstance(d, dict)
               and (d.get('title') or '').strip().lower() == 'receipt'
               for d in docs):
            continue
        docs.insert(0, {'title': 'Receipt', 'filename': receipt})
        # Bump updated_at so the next incremental export picks up the
        # changed docs JSON. Without this, the row's documents column
        # is silently rewritten but the export's `updated_at >= since`
        # filter excludes the row, so the new entry never ships.
        db.execute(
            f'UPDATE {table} SET documents = ?, updated_at = ? WHERE id = ?',
            (json.dumps(docs), now, row['id']),
        )


def _dedupe_receipt_docs(db, table):
    """Collapse multiple 'Receipt'-titled entries in the documents
    JSON down to one. Earlier boots of _migrate_receipt_into_documents
    deduped only by filename, so a row that already had a user-uploaded
    {title:'Receipt', filename:B} ended up with {title:'Receipt',
    filename:A} inserted at index 0 by the migration — and both then
    collided at export time as '<ident> — Receipt.<ext>' /
    '<ident> — Receipt (2).<ext>'.
    Keeps the LAST Receipt-titled entry (the user's manual upload
    that lived in the JSON before the migration ran) and drops the
    earlier ones (the auto-derived migration inserts at index 0).
    Other shared titles are left alone — only literal 'Receipt'
    duplicates are collapsed, since the user might intentionally have
    multiple docs with other matching titles. Idempotent."""
    cols = {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if 'documents' not in cols:
        return
    cat = next((c for c, info in CATEGORIES.items()
                if info.get('table') == table), None)
    rows = db.execute(f"SELECT * FROM {table}").fetchall()
    now = datetime.utcnow().isoformat()
    for row in rows:
        try:
            docs = json.loads(row['documents'] or '[]')
        except (TypeError, ValueError):
            continue
        if not isinstance(docs, list):
            continue
        receipt_kept = False
        kept = []
        dropped = []
        for d in reversed(docs):
            if isinstance(d, dict) and (d.get('title') or '').strip().lower() == 'receipt':
                if receipt_kept:
                    dropped.append(d)
                    continue
                receipt_kept = True
            kept.append(d)
        kept.reverse()
        if len(kept) != len(docs):
            # Bump updated_at so the next incremental export re-includes
            # this row and ships the deduped docs JSON. Without it, the
            # row is silently mutated and the export's `updated_at >=
            # since` filter leaves the duplicate-laden previous export
            # in place on the client's local mirror.
            db.execute(
                f'UPDATE {table} SET documents = ?, updated_at = ? WHERE id = ?',
                (json.dumps(kept), now, row['id']),
            )
            # Tombstone the dropped entries so the next syncDown removes
            # the orphan files from the user's local mirror. Without
            # tombstones, the dedupe rewrites the docs JSON cleanly but
            # the previous export's '<ident> — Receipt (2).<ext>'
            # collision-suffixed file persists locally with no path
            # back to the server saying "delete me".
            if cat:
                for d in dropped:
                    fname = (d.get('filename') or '').strip()
                    if fname:
                        try:
                            _record_tombstone(db, cat, row, 'Receipt', fname)
                        except Exception:
                            app.logger.exception(
                                'dedupe tombstone write failed for %s/%s',
                                cat, row['id'],
                            )


def _undo_receipt_phantoms(db, table, dry_run, write_tombstones=True):
    """Remove Receipt-titled docs entries that are exact phantoms of the
    legacy receipt column — same title 'Receipt', filename equal to the
    row's receipt column value. These are entries the migration created
    from FileMaker-era receipt slots that actually held cover-image
    duplicates (different filename than the cover image column, so
    _strip_redundant_receipts couldn't NULL them, and
    _strip_phantom_cover_image_docs couldn't strip them by filename).

    Conservative — does NOT touch:
      * User-added Receipt docs whose filename differs from the receipt
        column value (those came in via the dynamic docs UI and are
        legitimate user uploads).
      * Receipt docs in non-migrated categories (recordings).
      * Any doc whose title isn't exactly 'Receipt' (case-insensitive).

    For each match it: splices the docs entry, NULLs the receipt column
    so the boot-time migration won't re-insert on the next restart,
    bumps updated_at, and (optionally) writes a tombstone so the next
    syncDown removes the orphan from the user's local mirror.

    Returns a per-table report:
      {'matched': N, 'sample': [...up to 25 entries...]}
    Sample entries: {record_id, ident, label, filename, ext, group}.
    """
    out = {'matched': 0, 'sample': []}
    cols = {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if 'documents' not in cols or 'receipt' not in cols:
        return out
    cat = next((c for c, info in CATEGORIES.items()
                if info.get('table') == table), None)
    plan = EXPORT_LAYOUT.get(cat) if cat else None
    rows = db.execute(f"SELECT * FROM {table}").fetchall()
    now = datetime.utcnow().isoformat()
    for row in rows:
        receipt = (row['receipt'] or '').strip() if 'receipt' in row.keys() else ''
        if not receipt:
            continue
        try:
            docs = json.loads(row['documents'] or '[]')
        except (TypeError, ValueError):
            continue
        if not isinstance(docs, list):
            continue
        # Find the phantom: title == 'Receipt', filename == receipt column.
        new_docs = []
        removed_entry = None
        for d in docs:
            if (removed_entry is None
                    and isinstance(d, dict)
                    and (d.get('title') or '').strip().lower() == 'receipt'
                    and (d.get('filename') or '').strip() == receipt):
                removed_entry = d
                continue
            new_docs.append(d)
        if not removed_entry:
            continue
        out['matched'] += 1
        if len(out['sample']) < 25 and plan:
            try:
                ident = plan['ident'](row)
                group = plan['group'](row)
            except Exception:
                ident, group = '?', '?'
            out['sample'].append({
                'record_id': row['id'],
                'ident':     ident,
                'group':     group,
                'label':     'Receipt',
                'filename':  receipt,
                'ext':       os.path.splitext(receipt)[1] or '',
            })
        if dry_run:
            continue
        db.execute(
            f"UPDATE {table} SET documents = ?, receipt = NULL, "
            f"updated_at = ? WHERE id = ?",
            [json.dumps(new_docs), now, row['id']],
        )
        if write_tombstones and cat:
            try:
                _record_tombstone(db, cat, row, 'Receipt', receipt)
            except Exception:
                app.logger.exception('tombstone write failed for %s/%s',
                                     cat, row['id'])
    return out


def _undo_numbered_doc_phantoms(db, table, dry_run):
    """Remove docs entries whose title is a fixed-slot label followed
    by a numeric suffix — 'Front 2', 'Receipt 3', 'Image 2', etc.
    These come from FileMaker imports that auto-numbered duplicate
    container fields; the legacy importer carried the numeric suffix
    into the title verbatim, and the receipt→documents migration
    faithfully preserved it. They typically point at an extra copy
    of the cover image (different filename than the cover slot, so
    _strip_phantom_cover_image_docs can't catch them by filename
    match) and clutter the docs UI as redundant tiles.

    Conservative — only matches titles where the prefix is a known
    label drawn from the category's EXPORT_LAYOUT.files defaults,
    plus a small set of common legacy FileMaker labels (Image, Cover,
    Front, Back, Receipt, Doc, Document, Obverse, Reverse). User-
    authored titles like 'Service receipt 2024' or 'Front of dial'
    aren't matched because the suffix has to be a bare integer.
    """
    out = {'matched': 0, 'sample': []}
    cols = {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
    cat = next((c for c, info in CATEGORIES.items()
                if info.get('table') == table), None)
    if not cat:
        return out
    plan = EXPORT_LAYOUT.get(cat) or {}
    json_cols = [c for c in DOC_SETS_BY_CATEGORY.get(cat, {}).values() if c in cols]
    if not json_cols:
        return out

    known_labels = set()
    for spec in plan.get('files', []):
        _field, default_label, _title_field = spec
        if default_label:
            known_labels.add(default_label.lower())
    for extra in ('image', 'cover', 'front', 'back', 'receipt',
                  'image (obverse)', 'image (reverse)',
                  'obverse', 'reverse', 'doc', 'document'):
        known_labels.add(extra)
    if not known_labels:
        return out
    label_re = re.compile(
        r'^(' + '|'.join(re.escape(lbl) for lbl in sorted(known_labels)) + r')\s+\d+$',
        re.IGNORECASE,
    )

    rows = db.execute(f"SELECT * FROM {table}").fetchall()
    now = datetime.utcnow().isoformat()
    for row in rows:
        for json_col in json_cols:
            try:
                docs = json.loads((row[json_col] if json_col in row.keys() else None) or '[]')
            except (TypeError, ValueError):
                continue
            if not isinstance(docs, list):
                continue
            new_docs = []
            removed = []
            for d in docs:
                if isinstance(d, dict):
                    title = (d.get('title') or '').strip()
                    if title and label_re.match(title):
                        removed.append(d)
                        continue
                new_docs.append(d)
            if not removed:
                continue
            out['matched'] += len(removed)
            if len(out['sample']) < 25:
                try:
                    ident = plan['ident'](row) if 'ident' in plan else '?'
                    group = plan['group'](row) if 'group' in plan else '?'
                except Exception:
                    ident, group = '?', '?'
                for entry in removed:
                    out['sample'].append({
                        'record_id': row['id'],
                        'ident':     ident,
                        'group':     group,
                        'json_col':  json_col,
                        'label':     entry.get('title'),
                        'filename':  entry.get('filename'),
                        'ext':       os.path.splitext(entry.get('filename') or '')[1],
                    })
                    if len(out['sample']) >= 25:
                        break
            if dry_run:
                continue
            db.execute(
                f"UPDATE {table} SET {json_col} = ?, updated_at = ? "
                f"WHERE id = ?",
                [json.dumps(new_docs), now, row['id']],
            )
            for entry in removed:
                title = (entry.get('title') or '').strip()
                fname = (entry.get('filename') or '').strip()
                if fname:
                    try:
                        _record_tombstone(db, cat, row, title, fname)
                    except Exception:
                        app.logger.exception(
                            'tombstone write failed for %s/%s/%s',
                            cat, row['id'], title,
                        )
    return out


def _backfill_docs_json(db, table, target_col, sources):
    """Compact legacy fixed doc columns into a JSON array stored in
    `target_col`. `sources` is a list of (filename_col, title_col,
    default_title) tuples in desired order — title_col may be None to
    fall back to the default. Idempotent: a row whose `target_col` is
    already populated is left alone, so re-running doesn't clobber
    edits made through the dynamic UI."""
    cols = {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if target_col not in cols:
        return
    selectable = {'id', target_col}
    for fn_col, title_col, _ in sources:
        if fn_col in cols:
            selectable.add(fn_col)
        if title_col and title_col in cols:
            selectable.add(title_col)
    rows = db.execute(
        f"SELECT {', '.join(selectable)} FROM {table}"
    ).fetchall()
    for row in rows:
        existing = row[target_col] if target_col in row.keys() else None
        if existing:
            try:
                parsed = json.loads(existing)
                # Skip if the column is ANY valid JSON list — including
                # an empty list. An empty list means the user (or the
                # phantom-doc cleanup) has explicitly emptied it; the
                # backfill must not repopulate from legacy *_label
                # columns or it'll resurrect the phantoms every boot.
                if isinstance(parsed, list):
                    continue
            except (TypeError, ValueError):
                pass
        docs = []
        for fn_col, title_col, default_title in sources:
            if fn_col not in row.keys():
                continue
            fn = row[fn_col]
            if not fn:
                continue
            title = ''
            if title_col and title_col in row.keys():
                title = (row[title_col] or '').strip()
            if not title:
                title = default_title or ''
            docs.append({'title': title, 'filename': fn})
        db.execute(
            f'UPDATE {table} SET {target_col} = ? WHERE id = ?',
            (json.dumps(docs), row['id']),
        )


# File columns whose values are the LEGITIMATE source of a JSON
# documents array (populated by the various backfill helpers below).
# Phantom-strip pattern 1 must NOT count these as "other files" when
# evaluating the matching JSON column — the tile and its slot column
# point at the same file BY DESIGN, not because the legacy importer
# accidentally duplicated a cover image. Without this exclusion the
# strip nukes every legitimate persons health/id document on every
# boot (slot file present + JSON tile referencing it = both true).
DOC_JSON_BACKFILL_SOURCES = {
    ('persons',    'id_documents'):     {f'id_doc_{i}'     for i in range(3, 9)},
    ('persons',    'health_documents'): {f'health_doc_{i}' for i in range(3, 9)},
    ('vehicles',   'documents'):        {'insurance', 'invoice', 'registration', 'auto_title',
                                         'vehicle_doc_5', 'vehicle_doc_6',
                                         'vehicle_doc_7', 'vehicle_doc_8'},
    ('properties', 'documents'):        {f'doc_{i}' for i in range(1, 11)},
}


def _strip_phantom_cover_image_docs(db):
    """Remove phantom doc tiles created by legacy FileMaker imports.
    Two patterns get caught:

      1. Filename match — the tile's filename is identical to any
         OTHER file-typed column on the same record (cover image,
         secondary image slot, etc.). The legacy import wrote the
         same file into multiple columns and the doc-row backfill
         turned each into its own tile.

         Exception: columns declared in DOC_JSON_BACKFILL_SOURCES
         for the JSON column under evaluation are excluded — those
         file columns ARE the legitimate source of the tile, not a
         redundant copy.

      2. Title match — the tile's title starts with the record's
         EXPORT_LAYOUT ident (e.g. "2013 Global 6000 — Image" on a
         vehicle, "Adele — Receipt" on a recording). These titles
         come from `*_label` columns that the backfill copied
         verbatim. Even when the filename is a separate UUID (so
         the filename-match path misses them), the title gives them
         away as redundant auto-generated tiles re-rendering the
         cover.

    Fixed file columns are never touched; only JSON documents
    arrays are filtered. Idempotent."""
    layout = globals().get('EXPORT_LAYOUT') or {}
    total_dropped = 0
    per_cat_dropped = {}
    per_cat_kept = {}
    suspicious_kept = []  # tiles we LEFT IN that look like potential phantoms
    sample_dropped = []
    for cat, fields in FIELDS.items():
        table = CATEGORIES.get(cat, {}).get('table')
        if not table:
            continue
        json_cols = list(DOC_SETS_BY_CATEGORY.get(cat, {}).values())
        if not json_cols:
            continue
        file_cols = [f['name'] for f in fields if f.get('type') == 'file']
        try:
            present = {r['name'] for r in db.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()}
        except sqlite3.OperationalError:
            continue
        present_files = [c for c in file_cols if c in present]
        present_jsons = [c for c in json_cols if c in present]
        if not present_jsons:
            continue
        ident_fn = (layout.get(cat) or {}).get('ident')
        select_cols = ', '.join(['*'])
        try:
            rows = db.execute(f"SELECT {select_cols} FROM {table}").fetchall()
        except sqlite3.OperationalError:
            continue
        for row in rows:
            ident_prefixes = []
            if ident_fn:
                try:
                    ident = (ident_fn(row) or '').strip()
                    if ident:
                        # Match all three dash variants: em (—), en (–),
                        # and hyphen (-). Different FileMaker exporters
                        # used different glyphs; the current upload
                        # path strips all three.
                        for dash in ('—', '–', '-'):
                            ident_prefixes.append(f'{ident} {dash} ')
                except Exception:
                    pass
            for jc in present_jsons:
                try:
                    docs = json.loads(row[jc] or '[]')
                except (TypeError, ValueError):
                    continue
                if not isinstance(docs, list):
                    continue
                # Per-JSON-column "other_files" set. Excludes the file
                # columns declared as the legitimate backfill source for
                # `jc` — otherwise the strip nukes every tile that points
                # at its own slot column (e.g. persons health_documents
                # tile referencing health_doc_3).
                exclude = DOC_JSON_BACKFILL_SOURCES.get((cat, jc), set())
                other_files = {
                    (row[c] or '').strip()
                    for c in present_files
                    if c not in exclude and c in row.keys()
                    and (row[c] or '').strip()
                }
                # If this JSON column has declared backfill sources, the
                # title-prefix heuristic must be skipped too — the
                # backfill writes titles like "<property-name> — Deed"
                # (legitimate user data) which the heuristic would
                # otherwise treat as auto-generated cover-image phantoms
                # and nuke. The phantom-strip is meant to catch the
                # FileMaker pattern where a SEPARATE file column got
                # populated with the cover; declared sources are not
                # that pattern.
                use_ident_prefix = (cat, jc) not in DOC_JSON_BACKFILL_SOURCES
                kept = []
                for d in docs:
                    if not isinstance(d, dict):
                        continue
                    fn = (d.get('filename') or '').strip()
                    title = (d.get('title') or '').strip()
                    # Drop pattern 1: filename matches another file column
                    if fn and fn in other_files:
                        continue
                    # Drop pattern 2: title starts with the auto-generated
                    # ident prefix (any dash variant) — only for columns
                    # without declared backfill sources.
                    if use_ident_prefix and ident_prefixes and any(
                        title.startswith(p) for p in ident_prefixes
                    ):
                        continue
                    kept.append(d)
                    # Diagnostic: tiles LEFT IN whose title looks like
                    # it could be a phantom (contains a dash), so we
                    # can spot what the matcher is missing.
                    if (' — ' in title or ' – ' in title or ' - ' in title) \
                            and len(suspicious_kept) < 16:
                        suspicious_kept.append({
                            'cat': cat,
                            'title': title[:80],
                            'ident_first': (ident_prefixes[0] if ident_prefixes else None),
                        })
                if len(kept) != len(docs):
                    dropped_now = [
                        d for d in docs
                        if d not in kept
                    ]
                    total_dropped += len(dropped_now)
                    per_cat_dropped[cat] = per_cat_dropped.get(cat, 0) + len(dropped_now)
                    if len(sample_dropped) < 16:
                        for d in dropped_now:
                            if isinstance(d, dict) and len(sample_dropped) < 16:
                                sample_dropped.append({
                                    'cat': cat,
                                    'title': (d.get('title') or '')[:60],
                                    'filename': (d.get('filename') or '')[:40],
                                })
                    try:
                        db.execute(
                            f"UPDATE {table} SET {jc} = ? WHERE id = ?",
                            (json.dumps(kept), row['id']),
                        )
                    except sqlite3.OperationalError:
                        pass
    db.commit()
    print(
        f'[phantom-doc-cleanup] dropped {total_dropped} tile(s); '
        f'per_cat={per_cat_dropped}',
        flush=True,
    )
    print(
        f'[phantom-doc-cleanup] dropped sample={sample_dropped}',
        flush=True,
    )
    print(
        f'[phantom-doc-cleanup] kept-with-dash={suspicious_kept}',
        flush=True,
    )


def _compact_empty_doc_slots(db):
    """Strip empty entries from every JSON documents-style column. An
    entry is "empty" if it has no filename AND the title is either
    blank or a placeholder-like 'Doc <N>' / 'Document <N>' / 'Receipt'-
    when-it-came-from-an-auto-migration string. Real user-typed titles
    on a still-empty filename slot are preserved (the user might be
    about to upload to it). Idempotent."""
    placeholder_re = re.compile(r'^(doc|document)\s*\d*$', re.IGNORECASE)
    targets = [
        ('properties', 'documents'),
        ('watches',    'documents'),
        ('coins',      'documents'),
        ('art',        'documents'),
        ('vehicles',   'documents'),
        ('pens',       'documents'),
        ('recordings', 'documents'),
        ('rifles',     'documents'),
        ('audio',      'documents'),
        ('persons',    'id_documents'),
        ('persons',    'health_documents'),
    ]
    for table, col in targets:
        try:
            cols = {r['name'] for r in db.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()}
        except sqlite3.OperationalError:
            continue
        if col not in cols:
            continue
        rows = db.execute(
            f"SELECT id, {col} FROM {table} WHERE {col} IS NOT NULL"
        ).fetchall()
        for row in rows:
            try:
                docs = json.loads(row[col] or '[]')
            except (TypeError, ValueError):
                continue
            if not isinstance(docs, list):
                continue
            kept = []
            for d in docs:
                if not isinstance(d, dict):
                    continue
                fn = (d.get('filename') or '').strip()
                title = (d.get('title') or '').strip()
                if fn:
                    kept.append(d)
                    continue
                # No filename. Drop if title is also missing/placeholder.
                if not title or placeholder_re.match(title):
                    continue
                kept.append(d)
            if len(kept) != len(docs):
                db.execute(
                    f"UPDATE {table} SET {col} = ? WHERE id = ?",
                    (json.dumps(kept), row['id']),
                )
    db.commit()


def _apply_property_renames(db):
    """Apply the Apr 2026 property/item-property cleanup. Strips legacy
    FileMaker-era prefixes (Ghent:, NYC:, SF:), folds short-form
    abbreviations to canonical names (Carp→Carpinteria, SF→42 Hotaling,
    Montecito→Carpinteria), splits the Paris properties (the old Sold
    one becomes its address; the active Saint-Guillaume one becomes
    just Paris), and migrates status-like values out of the property
    column into location_status. Each step is idempotent."""

    # --- Paris split (must run before any other 'Paris' rename) ---
    # OLD state: properties has both 'Paris' (Sold, 77 rue de Lille) and
    # 'Paris Saint-Guillaume' (Own). 5 items reference 'Paris', 23
    # reference 'Paris Saint-Guillaume'. NEW state: 'Paris' becomes
    # '77 rue de Lille', 'Paris Saint-Guillaume' becomes 'Paris',
    # items follow. We detect "not yet applied" by the existence of
    # the Saint-Guillaume property record — once it's gone, the rename
    # has happened (or this DB never had FileMaker's split).
    needs_paris = False
    try:
        needs_paris = db.execute(
            "SELECT 1 FROM properties WHERE name='Paris Saint-Guillaume' LIMIT 1"
        ).fetchone() is not None
    except sqlite3.OperationalError:
        pass
    if needs_paris:
        for cat, field in CATEGORY_PROPERTY_FIELD.items():
            table = CATEGORIES[cat]['table']
            try:
                db.execute(
                    f"UPDATE {table} SET {field} = '77 rue de Lille' "
                    f"WHERE {field} = 'Paris'"
                )
                db.execute(
                    f"UPDATE {table} SET {field} = 'Paris' "
                    f"WHERE {field} = 'Paris Saint-Guillaume'"
                )
            except sqlite3.OperationalError:
                pass
        try:
            db.execute(
                "UPDATE properties SET name='77 rue de Lille' WHERE name='Paris'"
            )
            db.execute(
                "UPDATE properties SET name='Paris' WHERE name='Paris Saint-Guillaume'"
            )
        except sqlite3.OperationalError:
            pass

    # --- Property record renames (idempotent unilateral renames) ---
    record_renames = (
        ('Ghent: Pond House',    'Pond House'),
        ('Ghent: Glass House',   'Glass House'),
        ('Ghent: Harlemville',   'Harlemville'),
        ('Ghent: Party Barn',    'Party Barn'),
        ('Ghent: Rec Center',    'Rec Center'),
        ('Ghent: Rigor Hill',    'Rigor Hill'),
        ('Ghent: 223 Rigor',     '223 Rigor'),
        ('NYC: 1 White St',      '1 White St'),
        ('NYC: 357 W Broadway',  '357 W Broadway'),
        ('NYC: 67 Engert',       '67 Engert'),
        ('SF: 432 Jackson',      '432 Jackson'),
        ('4956 Fifth',           '3956 Fifth'),
        ('56 Leonard',           'NYC'),
        ('Truckee',              'Lahontan'),
        ('San Francisco',        '3450 Washington'),
        ('Martis Camp',          'Martis'),
    )
    for old, new in record_renames:
        try:
            db.execute(
                "UPDATE properties SET name=? WHERE name=?", (new, old)
            )
        except sqlite3.OperationalError:
            pass

    # --- 6790 Rincon address typo fix (street number transposed) ---
    try:
        db.execute(
            "UPDATE properties "
            "SET address = REPLACE(address, '6970 Rincon Road', '6790 Rincon Road') "
            "WHERE name='6790 Rincon' AND address LIKE '%6970 Rincon Road%'"
        )
    except sqlite3.OperationalError:
        pass

    # --- Item-side property value rewrites ---
    item_renames = (
        # Strip legacy prefixes
        ('Ghent: Pond House',     'Pond House'),
        ('Ghent: Glass House',    'Glass House'),
        ('Ghent: Harlemville',    'Harlemville'),
        ('Ghent: Party Barn',     'Party Barn'),
        ('Ghent: Rec Center',     'Rec Center'),
        ('Ghent: Rec Center/Arena', 'Rec Center'),
        ('Ghent: Rigor Hill',     'Rigor Hill'),
        ('Ghent: 223 Rigor',      '223 Rigor'),
        ('NYC: 1 White St',       '1 White St'),
        ('NYC: 357 W Broadway',   '357 W Broadway'),
        ('NYC: 67 Engert',        '67 Engert'),
        ('SF: 432 Jackson',       '432 Jackson'),
        # Short-form expansions
        ('Carp',                  'Carpinteria'),
        ('Montecito',             'Carpinteria'),
        ('Rec Center/Arena',      'Rec Center'),
        # Old San Francisco / SF → 42 Hotaling
        ('San Francisco',         '42 Hotaling'),
        ('SF',                    '42 Hotaling'),
    )
    for cat, field in CATEGORY_PROPERTY_FIELD.items():
        table = CATEGORIES[cat]['table']
        for old, new in item_renames:
            try:
                db.execute(
                    f"UPDATE {table} SET {field} = ? WHERE {field} = ?",
                    (new, old),
                )
            except sqlite3.OperationalError:
                pass

    # --- Move status-like property values into location_status ---
    # (Storage / Archived / Missing / Gifted / Dolby Chadwick used to
    # be valid property values; now they live in the location_status
    # axis. Archived was later folded into Gifted, so skip it as a
    # destination value.)
    status_bucket_map = {
        'Storage':         'Storage',
        'Archived':        'Gifted',
        'Missing':         'Missing',
        'Gifted':          'Gifted',
        'Dolby Chadwick':  'Consigned',
    }
    for cat, field in CATEGORY_PROPERTY_FIELD.items():
        table = CATEGORIES[cat]['table']
        # location_status only exists on item tables (added by the boot
        # ALTER block). Skip if missing for some reason.
        try:
            cols = {r['name'] for r in db.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()}
        except sqlite3.OperationalError:
            continue
        if 'location_status' not in cols:
            continue
        for prop_value, loc_status in status_bucket_map.items():
            try:
                db.execute(
                    f"UPDATE {table} SET location_status = ?, "
                    f"{field} = NULL WHERE {field} = ?",
                    (loc_status, prop_value),
                )
            except sqlite3.OperationalError:
                pass

    # --- Drop Archived from location_status (folded into Gifted) ---
    for cat in CATEGORY_PROPERTY_FIELD:
        table = CATEGORIES[cat]['table']
        try:
            db.execute(
                f"UPDATE {table} SET location_status = 'Gifted' "
                f"WHERE location_status = 'Archived'"
            )
        except sqlite3.OperationalError:
            pass

    db.commit()


def _backfill_meds_from_prescriptions(db):
    """One-time: copy free-text prescriptions into the structured med_* slots.
    Skips a person if any med_name_N is already populated, so re-running is
    safe and won't clobber edits."""
    rows = db.execute(
        "SELECT id, prescriptions, "
        + ", ".join(f"med_name_{i}" for i in range(1, 8))
        + " FROM persons WHERE prescriptions IS NOT NULL AND prescriptions != ''"
    ).fetchall()
    for row in rows:
        if any((row[f'med_name_{i}'] or '').strip() for i in range(1, 8)):
            continue  # already migrated or hand-edited
        meds = _parse_prescription_lines(row['prescriptions'])[:7]
        if not meds:
            continue
        cols, vals = [], []
        for i, (name, dose) in enumerate(meds, start=1):
            cols.append(f'med_name_{i} = ?'); vals.append(name)
            cols.append(f'med_dose_{i} = ?'); vals.append(dose)
        db.execute(f"UPDATE persons SET {', '.join(cols)} WHERE id = ?",
                   vals + [row['id']])
    db.commit()


def get_counts():
    db = get_db()
    counts = {}
    # Skip categories the current user can't see — otherwise the nav
    # leaks the existence and row count of hidden tables (e.g. a
    # third-party deployment would still see "Watches: 73" in the
    # nav even though the watches tab is hidden by visibility rules).
    # Falls back to all categories outside a request context (CLI,
    # tests) where g.allowed_cats isn't populated.
    allowed = g.get('allowed_cats') or set(CATEGORIES.keys())
    for slug, cat in CATEGORIES.items():
        if slug not in allowed:
            continue
        # Apply the current user's row filter so the nav count
        # matches what they can actually see in the list.
        wheres, params = [], []
        _apply_row_filter_clauses(slug, wheres, params)
        where = f"WHERE {' AND '.join(wheres)}" if wheres else ''
        row = db.execute(
            f"SELECT COUNT(*) as c FROM {cat['table']} {where}", params
        ).fetchone()
        counts[slug] = row['c']
    return counts


def current_owner_name():
    """First word of the current user's display_name (e.g. 'Mark
    Armenante' -> 'Mark'). Used as the per-user owner-string for
    scoping items property dropdowns, typeaheads, and ownership.
    Returns None outside a request context or for users without a
    display_name."""
    user = g.get('current_user')
    if not user:
        return None
    dn = (user.get('display_name') or '').strip()
    return dn.split()[0] if dn else None


def get_property_choices():
    """Property names (or short_name if name is blank) sorted
    case-insensitively. Limited to currently-owned residential
    properties (status='Own', type='Residential') — the dropdown is
    for placing new items, so sold and commercial properties just add
    noise. The full `name` is preferred because that's what the
    item-table property columns (watches.property, coins.property,
    etc.) actually store. Returns [] when nothing matches so a fresh
    install renders an empty dropdown instead of a stale seed list.

    NB: the `archive` column is not used as an archive flag here —
    historical data stores wifi passwords in it, so it can't be
    filtered on safely without a data cleanup pass first."""
    db = get_db()
    # Strictly Residential — Mark's deployment uses one canonical
    # type value. Tenants whose `type` is hidden have type=NULL on
    # every row, so the filter is skipped there.
    type_filter = (
        "" if 'type' in HIDE_FIELDS.get('properties', set())
        else "  AND type = 'Residential' "
    )
    sql = (
        "SELECT name, short_name FROM properties "
        f"WHERE {_own_status_predicate()} "
        f"{type_filter}"
        "  AND COALESCE(NULLIF(name,''), short_name) IS NOT NULL "
        "  AND COALESCE(NULLIF(name,''), short_name) != '' "
        "ORDER BY LOWER(COALESCE(NULLIF(name,''), short_name))"
    )
    rows = db.execute(sql).fetchall()
    seen, out = set(), []
    for r in rows:
        label = (r['name'] or '').strip() or (r['short_name'] or '').strip()
        if label and label not in seen:
            seen.add(label)
            out.append(label)
    return out


def current_vlists(category=None):
    """Per-request VALUE_LISTS with 'property' resolved from the DB.
    For the items category we also resolve a few values from the
    deployment's current state instead of from the static dict:

      * 'property' is scoped to properties owned by the current user
        (or marked 'Jointly').
      * 'items_owner' lists every household member (first word of
        each user's display_name), with the current user first so
        they're the default, plus 'Jointly' as a tail option.
      * 'items_status' is the simplified status set used by items
        ('Own', 'Sold', 'Gifted', 'Lost') — no 'Loaned'/'Ordered'/
        'Consigned' since those concepts don't apply to general
        household inventory.
    """
    if category == 'items':
        me = current_owner_name()
        # Tenant override: when STUFFAPP_OWNER_OPTIONS is set, use
        # that explicit list verbatim (first option = default) so
        # items' owner dropdown matches what the rest of the app
        # shows. On Mark's deployment the household members come
        # from the users table, with 'YM' (the joint Mark+Young
        # marker) appended as a tail option. 'Jointly' is Gerri's
        # convention, never Mark's.
        if os.environ.get('STUFFAPP_OWNER_OPTIONS'):
            items_owner = VALUE_LISTS['owner']
        else:
            db = get_db()
            rows = db.execute(
                "SELECT display_name FROM users "
                "WHERE display_name IS NOT NULL AND display_name != ''"
            ).fetchall()
            seen, members = set(), []
            for r in rows:
                first = (r['display_name'] or '').strip().split()
                if not first:
                    continue
                n = first[0]
                if n not in seen:
                    seen.add(n)
                    members.append(n)
            if me:
                members = [me] + [m for m in members if m != me]
            items_owner = members + ['YM']
        return {
            **VALUE_LISTS,
            'property': get_property_choices(),
            'items_owner': items_owner,
            'items_status': ['Own', 'Sold', 'Gifted', 'Lost'],
        }
    return {**VALUE_LISTS, 'property': get_property_choices()}


def get_typeahead(table, *fields, owner_filter=None):
    """Return dict of field -> sorted list of distinct non-empty values.
    When `owner_filter` is set, the DISTINCT scan is restricted to
    rows the current user owns — items autocompletes only suggest
    values the user themselves entered, not values from other
    members' records."""
    db = get_db()
    result = {}
    extra_where = ""
    extra_params = []
    if owner_filter:
        extra_where = " AND owner = ?"
        extra_params = [owner_filter]
    for field in fields:
        rows = db.execute(
            f"SELECT DISTINCT {field} as v FROM {table} "
            f"WHERE {field} IS NOT NULL AND {field} != ''" + extra_where + f" "
            f"ORDER BY {field}",
            extra_params,
        ).fetchall()
        result[field] = [r['v'] for r in rows]
    return result


TYPEAHEAD_FIELDS = {
    'watches':      ('brand', 'dial_color', 'strap_color', 'vendor'),
    'coins':        ('region', 'mint', 'denomination', 'vendor'),
    'art':          ('artist', 'medium', 'vendor', 'property', 'location'),
    # Items typeahead: only the fields still present in the form
    # (type/subtype/make/model were removed). `type` is the key one —
    # it's free-text but should converge as the user enters values.
    'items':        ('type', 'vendor', 'location'),
    'cameras':      ('make', 'lens_mount', 'vendor'),
    'lenses':       ('make', 'mount', 'vendor'),
    'pens':         ('make', 'vendor'),
    'vehicles':     ('make', 'vendor'),
    'recordings':   ('artist', 'genre', 'vendor'),
    'audio':        ('make', 'vendor'),
    'rifles':       ('make', 'caliber', 'vendor'),
}


def build_typeahead(category):
    fields = TYPEAHEAD_FIELDS.get(category)
    if not fields:
        return {}
    owner_filter = current_owner_name() if category == 'items' else None
    return get_typeahead(
        CATEGORIES[category]['table'], *fields, owner_filter=owner_filter
    )


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


_HEIF_BRANDS = {b'heic', b'heix', b'hevc', b'heim', b'heis', b'hevx',
                b'mif1', b'msf1', b'heif'}


def _looks_like_heic(data):
    """Detect HEIC/HEIF by ISO BMFF magic bytes regardless of file extension.
    iPhone photos often arrive as .jpg but are actually HEIC."""
    return len(data) >= 12 and data[4:8] == b'ftyp' and data[8:12] in _HEIF_BRANDS


def save_upload(file_obj):
    """Save an uploaded file and return the stored filename.

    Decode-and-re-encode runs whenever the image is HEIC/HEIF OR has
    an alpha channel that would otherwise paint black behind
    transparent pixels (PIL's default RGBA→RGB fill). Both cases
    converge on a JPEG re-encode with the alpha (if any) composited
    over white. Non-alpha JPEG/PNG/RGB images pass through untouched
    so we don't lose source quality on a needless re-encode."""
    if not file_obj or file_obj.filename == '':
        return None
    if not allowed_file(file_obj.filename):
        return None

    data = file_obj.read()
    ext = file_obj.filename.rsplit('.', 1)[1].lower()

    is_heic = _looks_like_heic(data) and HEIF_SUPPORTED

    try:
        from io import BytesIO
        from PIL import Image
        img = Image.open(BytesIO(data))
        # Promote palette-with-transparency to RGBA so alpha gets
        # flattened by the next branch (PNGs saved with type-3 palette
        # + tRNS chunk land here).
        if img.mode == 'P' and 'transparency' in img.info:
            img = img.convert('RGBA')
        has_alpha = img.mode in ('RGBA', 'LA')

        if is_heic or has_alpha:
            if has_alpha:
                bg = Image.new('RGB', img.size, (255, 255, 255))
                alpha = img.split()[-1]
                bg.paste(img.convert('RGB'), mask=alpha)
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            out = BytesIO()
            img.save(out, format='JPEG', quality=90)
            data = out.getvalue()
            ext = 'jpg'
            app.logger.info(
                'save_upload: re-encoded as JPEG (heic=%s, had_alpha=%s, '
                'orig_ext=%s)', is_heic, has_alpha,
                file_obj.filename.rsplit('.', 1)[-1].lower()
            )
    except Exception as e:
        # Decode failed (SVG, unsupported format, malformed data). We
        # still write the original bytes — the file just bypasses the
        # alpha-flatten / HEIC branch.
        app.logger.warning(
            'save_upload: PIL decode failed for %r: %s — saving as-is',
            file_obj.filename, e
        )

    stored_name = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(UPLOAD_FOLDER, stored_name), 'wb') as f:
        f.write(data)
    return stored_name


def get_file_fields(category):
    return [f['name'] for f in visible_fields(category) if f['type'] == 'file']


def _title_field_for(category, file_field):
    """Return the paired *_title / *_label column for a file field, or
    None if the field has no companion title column. Source of truth is
    EXPORT_LAYOUT (defined later); falls back to a name convention
    when EXPORT_LAYOUT isn't available yet (e.g. early-boot lookups)."""
    plan = globals().get('EXPORT_LAYOUT', {}).get(category)
    if plan:
        for spec in plan['files']:
            f, _, title_field = spec
            if f == file_field:
                return title_field
    # Fallback convention: try <field>_title then <field>_label.
    for f in [f['name'] for f in FIELDS.get(category, [])]:
        if f == file_field + '_title':
            return f
    return None


def _autofill_title_from_filename(db, table, record_id, category,
                                  file_field, original_filename):
    """When a file lands on a slot that has a paired _title/_label
    column, default that title to the upload's original basename —
    but only if the column is currently empty. Never overwrites a
    user-set title. No-op if there's no paired title column.

    Returns (title_field, new_value) when a write happened so callers
    keeping an in-memory copy of the row can stay in sync; returns
    None otherwise."""
    if not original_filename:
        return None
    title_field = _title_field_for(category, file_field)
    if not title_field:
        return None
    cols = {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if title_field not in cols:
        return None
    cur = db.execute(
        f"SELECT {title_field} FROM {table} WHERE id = ?", [record_id]
    ).fetchone()
    if cur and (cur[title_field] or '').strip():
        return None
    base = os.path.splitext(os.path.basename(original_filename))[0].strip()
    if not base:
        return None
    db.execute(
        f"UPDATE {table} SET {title_field} = ? WHERE id = ?",
        [base, record_id],
    )
    return (title_field, base)


EXCLUDED_STATUSES = ('Own', 'Owned', 'Sold', 'Gifted')  # dot filter excludes these


def _own_status_predicate(column='status'):
    return f"LOWER(TRIM(COALESCE({column}, ''))) IN ('own', 'owned')"


CATEGORY_FILTERS = {
    'watches': {
        'ordered': ("LOWER(TRIM(COALESCE(status,''))) = 'ordered'", []),
        # Inverts the default list view: shows ONLY watches that have
        # actually left the collection (sold / gifted / lost). The
        # default list (no filter) hides these — see build_search_query.
        'no_longer_owned': ("LOWER(TRIM(COALESCE(status,''))) IN ('sold','gifted','lost')", []),
    },
    'coins': {
        'ca_ancient': ("date_1 <  500 AND property_name IN ('Carp','Carpinteria')", []),
        'ny_ancient': ("date_1 <  500 AND property_name = 'NYC'", []),
        'ca_modern':  ("date_1 >= 500 AND property_name IN ('Carp','Carpinteria')", []),
        'ny_modern':  ("date_1 >= 500 AND property_name = 'NYC'", []),
        'ordered':    ("LOWER(TRIM(COALESCE(status,''))) = 'ordered'", []),
    },
    'audio': {
        'carp':   ("property IN ('Carpinteria', 'Carp')", []),
        'martis': ("property IN ('Martis', 'Truckee')", []),
    },
    'recordings': {
        'carp':   ("property IN ('Carpinteria', 'Carp')", []),
        'martis': ("property IN ('Martis', 'Truckee')", []),
    },
    # status/type comparisons are case- and whitespace-insensitive so data
    # imported with inconsistent casing (e.g. 'commercial' vs 'Commercial')
    # still matches.
    'vehicles': {
        'own':  (_own_status_predicate(), []),
        'sold': ("LOWER(TRIM(COALESCE(status,''))) = 'sold'", []),
    },
    # Cameras and lenses intentionally have no filter map — both lists
    # always show every record. Toolbar pills removed; default filter
    # removed.
    'properties': {
        # Single-axis filters
        'own':         (_own_status_predicate(), []),
        'sold':        ("LOWER(TRIM(COALESCE(status,''))) = 'sold'", []),
        'commercial':  ("LOWER(TRIM(COALESCE(type,'')))   = 'commercial'", []),
        'residential': ("LOWER(TRIM(COALESCE(type,'')))   = 'residential'", []),
        # Combined (status + type)
        'own_commercial':   (_own_status_predicate() + " AND LOWER(TRIM(COALESCE(type,''))) = 'commercial'",  []),
        'own_residential':  (_own_status_predicate() + " AND LOWER(TRIM(COALESCE(type,''))) = 'residential'", []),
        'sold_commercial':  ("LOWER(TRIM(COALESCE(status,''))) = 'sold' AND LOWER(TRIM(COALESCE(type,''))) = 'commercial'",  []),
        'sold_residential': ("LOWER(TRIM(COALESCE(status,''))) = 'sold' AND LOWER(TRIM(COALESCE(type,''))) = 'residential'", []),
    },
}

# For properties, a filter key is split into two axes: status (own/sold)
# and type (commercial/residential). These helpers let the template
# independently cycle each axis while encoding the pair in one URL param.
def _split_property_filter(f):
    if not f:
        return None, None
    parts = f.split('_')
    status = next((p for p in parts if p in ('own', 'sold')), None)
    ptype  = next((p for p in parts if p in ('commercial', 'residential')), None)
    return status, ptype


def _join_property_filter(status, ptype):
    if status and ptype:
        return f'{status}_{ptype}'
    return status or ptype or None


SEARCHABLE_NUMERIC = {
    'coins': ['weight'],
}


def _normalize_numeric_term(term):
    """Strip trailing zeros after the decimal point so a user search for
    '10.20' still matches a column stored as REAL 10.2 (which SQLite's
    LIKE coerces to the string '10.2', not '10.20')."""
    try:
        f = float(term)
    except (TypeError, ValueError):
        return term
    s = ('%f' % f).rstrip('0').rstrip('.')
    return s or term


def build_search_query(category, q, dot=False, coin_filter=None, at_property=None):
    """Build a SELECT with optional text search and/or dot (unresolved) filter."""
    table = CATEGORIES[category]['table']
    text_fields = [f['name'] for f in visible_fields(category)
                   if f['type'] in ('text', 'textarea', 'select') and f.get('type') != 'file']
    # Per-category extra columns to expose in free-text search. SQLite's
    # LIKE coerces numerics to strings, but strips trailing zeros — so
    # the search term gets normalized before matching against these.
    numeric_fields = SEARCHABLE_NUMERIC.get(category, [])

    wheres, params = [], []

    if q and (text_fields or numeric_fields):
        # Split the query on whitespace and AND the terms together: each
        # term must match at least one searchable field. "Breguet Carp"
        # finds watches where 'Breguet' is in some field AND 'Carp' is
        # in some field — so brand+property combos work.
        #
        # Text fields go through NODIA(col) LIKE NODIA('%term%') so
        # 'urban jurg' matches 'Urban Jürgensen', and both pre-composed
        # and decomposed Unicode forms of the same string match each
        # other. Numeric fields are ASCII-only, so plain LIKE suffices.
        terms = [t for t in q.split() if t.strip()]
        for term in terms:
            num_term = _normalize_numeric_term(term)
            folded_term = _strip_diacritics(term)
            conds = []
            for col in text_fields:
                conds.append(f"NODIA({col}) LIKE ?")
                params.append(f'%{folded_term}%')
            for col in numeric_fields:
                conds.append(f"{col} LIKE ?")
                params.append(f'%{num_term}%')
            wheres.append('(' + ' OR '.join(conds) + ')')

    if dot:
        # Find which field holds status for this category
        status_col = 'status'
        field_names = [f['name'] for f in visible_fields(category)]
        if 'property_name' in field_names and 'status' not in field_names:
            status_col = None  # no status column — skip
        if status_col:
            placeholders = ','.join(['?' for _ in EXCLUDED_STATUSES])
            wheres.append(f"(COALESCE({status_col},'') NOT IN ({placeholders}))")
            params += list(EXCLUDED_STATUSES)

    cat_filters = CATEGORY_FILTERS.get(category, {})
    if coin_filter and coin_filter in cat_filters:
        clause, extra_params = cat_filters[coin_filter]
        wheres.append(f"({clause})")
        params += list(extra_params)

    # Watches: default list hides Sold / Gifted / Lost — those have
    # truly left the collection and clutter the working view. The
    # 'no_longer_owned' pill flips the view to show only those, so
    # only suppress the default exclusion when that filter is active.
    if category == 'watches' and coin_filter != 'no_longer_owned':
        wheres.append(
            "(LOWER(TRIM(COALESCE(status,''))) NOT IN ('sold','gifted','lost'))"
        )

    # "?at=<property name>" — narrow to items physically located at
    # that property. Only meaningful for categories that store a
    # property name on each row (see CATEGORY_PROPERTY_FIELD). The
    # alias group expands "Carpinteria" to also match "Carp", etc.
    if at_property:
        prop_col = CATEGORY_PROPERTY_FIELD.get(category)
        if prop_col:
            aliases = _property_alias_group(at_property)
            if aliases:
                ph = ','.join(['?' for _ in aliases])
                wheres.append(
                    f"(LOWER(TRIM(COALESCE({prop_col},''))) IN ({ph}))"
                )
                params.extend(aliases)

    # Row-level access enforcement. Owners and unrestricted members
    # add nothing; restricted members get an extra
    # "<field> IN (...)" clause per filtered field.
    _apply_row_filter_clauses(category, wheres, params)

    where_clause = f"WHERE {' AND '.join(wheres)}" if wheres else ''
    order_by = CATEGORY_ORDER_BY.get(category, 'created_at DESC')
    return f"SELECT * FROM {table} {where_clause} ORDER BY {order_by}", params


# Make-then-model alpha order, used by several gear categories whose
# list view renders <make> as the brand line and <model> below it.
# COLLATE NODIACRITIC folds 'Voigtländer' to 'voigtlander' so it
# sorts in the V block, not as multi-byte UTF-8 garbage.
_MAKE_MODEL_ORDER = ("COALESCE(NULLIF(make, ''), 'zzz') COLLATE NODIACRITIC, "
                     "COALESCE(NULLIF(model, ''), 'zzz') COLLATE NODIACRITIC")

CATEGORY_ORDER_BY = {
    'coins': ("COALESCE(NULLIF(region, ''), 'zzz') COLLATE NODIACRITIC, "
              "COALESCE(NULLIF(authority, ''), 'zzz') COLLATE NODIACRITIC, "
              "COALESCE(date_1, 99999) ASC"),
    'watches': ("COALESCE(NULLIF(brand, ''), 'zzz') COLLATE NODIACRITIC, "
                "COALESCE(NULLIF(description, ''), 'zzz') COLLATE NODIACRITIC"),
    'vehicles':   _MAKE_MODEL_ORDER,
    'cameras':    _MAKE_MODEL_ORDER,
    'lenses':     _MAKE_MODEL_ORDER,
    'pens':       _MAKE_MODEL_ORDER,
    'audio':      _MAKE_MODEL_ORDER,
    'rifles':     _MAKE_MODEL_ORDER,
    # Art: alpha by artist (records use "Last, First" so this gives
    # surname order), then by title for the same artist's pieces.
    'art': ("COALESCE(NULLIF(artist, ''), 'zzz') COLLATE NODIACRITIC, "
            "COALESCE(title, '') COLLATE NODIACRITIC"),
    # Recordings: artist then album/track title, same shape as art.
    'recordings': ("COALESCE(NULLIF(artist, ''), 'zzz') COLLATE NODIACRITIC, "
                   "COALESCE(title, '') COLLATE NODIACRITIC"),
    # Persons: alpha by name (stored "Last, First" by convention).
    'persons': "COALESCE(NULLIF(name, ''), 'zzz') COLLATE NODIACRITIC",
    # Type first (Residential block, then Commercial block, with a
    # bold divider rendered between them in the template), then the
    # six primary homes featured-first within each type, then alpha.
    'properties': ("CASE COALESCE(type,'') "
                   "WHEN 'Residential' THEN 0 "
                   "WHEN 'Commercial'  THEN 1 "
                   "ELSE 2 END, "
                   "CASE "
                   "  WHEN LOWER(COALESCE(name,'')) = 'carpinteria'    THEN 0 "
                   "  WHEN LOWER(COALESCE(name,'')) = 'nyc'            THEN 1 "
                   "  WHEN LOWER(COALESCE(name,'')) = 'martis'         THEN 2 "
                   "  WHEN LOWER(COALESCE(name,'')) LIKE '%42 hotaling%' THEN 3 "
                   "  WHEN LOWER(COALESCE(name,'')) LIKE '%glass house%' THEN 4 "
                   "  WHEN LOWER(COALESCE(name,'')) = 'paris'          THEN 5 "
                   "  ELSE 99 "
                   "END, "
                   "COALESCE(name,'') COLLATE NODIACRITIC"),
    # Cards: sort by description (the bank/issuer name shown next to
    # each card) descending so heavier-use families group together.
    'credit_cards': ("COALESCE(description, '') COLLATE NODIACRITIC DESC, "
                     "COALESCE(name, '') COLLATE NODIACRITIC"),
}


def next_coin_id(db):
    row = db.execute("SELECT coin_id FROM coins ORDER BY rowid DESC LIMIT 1").fetchone()
    if row and row['coin_id']:
        try:
            last_n = int(row['coin_id'].replace('C ', '').strip())
            return f"C {last_n + 1}"
        except ValueError:
            pass
    # fallback: count rows
    count = db.execute("SELECT COUNT(*) as c FROM coins").fetchone()['c']
    return f"C {count + 1}"


CAT_ID_PREFIX = 'C'
CAT_ID_RE = re.compile(r'^C(\d+)$', re.IGNORECASE)


def _cat_id_prefix(property_name=None, date_1=None):
    """Cat ID is a flat global serial — every coin gets a 'C' prefix
    regardless of location or era. Arguments preserved for caller
    backwards-compat (next_cat_id is invoked from a few places that
    still pass them); they're ignored."""
    return CAT_ID_PREFIX


def next_cat_id(db, property_name=None, date_1=None):
    """Next sequential cat_id, zero-padded to 3 digits (e.g. 'C001').
    Single global series — no location/era partition. Always returns
    a value; the legacy `None` path no longer triggers."""
    row = db.execute(
        "SELECT cat_id FROM coins "
        "WHERE cat_id GLOB 'C[0-9]*' "
        "ORDER BY CAST(SUBSTR(cat_id, 2) AS INTEGER) DESC LIMIT 1"
    ).fetchone()
    n = 1
    if row and row['cat_id']:
        m = CAT_ID_RE.match(row['cat_id'])
        if m:
            n = int(m.group(1)) + 1
    return f'C{n:03d}'


# Watches and Art use the same flat-serial scheme as coins, just with
# their own letter prefix and their own series. No per-brand/per-artist
# partitioning — keeps the next-id query trivial and the IDs stable
# across brand/artist renames.
def next_serial_cat_id(db, table, prefix):
    """Next zero-padded serial cat_id for a category table, e.g.
    'W001' / 'A001'. Mirrors next_cat_id but accepts the table and
    prefix as args so watches and art can share the helper without
    further duplication."""
    glob = f'{prefix}[0-9]*'
    row = db.execute(
        f"SELECT cat_id FROM {table} "
        f"WHERE cat_id GLOB ? "
        f"ORDER BY CAST(SUBSTR(cat_id, {len(prefix) + 1}) AS INTEGER) DESC LIMIT 1",
        (glob,),
    ).fetchone()
    n = 1
    if row and row['cat_id']:
        m = re.match(rf'^{re.escape(prefix)}(\d+)$', row['cat_id'], re.IGNORECASE)
        if m:
            n = int(m.group(1)) + 1
    return f'{prefix}{n:03d}'


def coin_age(date_1):
    if date_1 is None:
        return None
    current_year = datetime.now().year
    if date_1 < 0:
        return current_year + abs(date_1)
    return current_year - date_1


def watch_hertz(beat):
    if beat:
        try:
            return round(int(beat) / 7200, 2)
        except (ValueError, TypeError):
            pass
    return None


def fetch_watch_valuation(watch):
    """Use Claude's web_search tool to estimate current market value.

    Returns dict {value: float|None, results: str}. Raises RuntimeError
    on missing key or API failure.
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY not configured')
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Run 'pip install anthropic'.")

    brand = (watch['brand'] or '').strip()
    model = (watch['model'] or '').strip()
    reference = (watch['reference'] or '').strip()
    year = watch['year']
    metal = (watch['metal'] or '').strip()
    description = (watch['description'] or '').strip()

    ident = ' '.join(x for x in [brand, model, f'Ref. {reference}' if reference else '',
                                 f'({metal})' if metal else '',
                                 str(year) if year else ''] if x)

    prompt = f"""You are valuing a specific wristwatch from public web data.

Watch: {ident}
Description: {(description[:280] + '…') if len(description) > 280 else description or '(none)'}

Use at most 5 concise web searches. Focus on:
- Chrono24 active listings for this reference (one search; note median/range)
- WatchCharts market data / price history for this reference (one search)
- One recent auction result (Phillips, Christie's, Sotheby's, Antiquorum, or Bonhams)
- Watchbox or A Collected Man if this reference is listed (one search combined)

Compute a consensus USD value (central estimate of the comps found).
Also capture the WatchCharts market median specifically, if that page publishes one for this reference.

Reply with ONLY a JSON object, no prose, no code fences:
{{"consensus_usd": 12345, "watchcharts_median_usd": 12000, "results_markdown": "- Chrono24 (N listings, median): $X,XXX — URL\\n- WatchCharts median: $X,XXX — URL\\n- Phillips, Month YYYY: $X,XXX — URL\\n- ..."}}

results_markdown rules:
- 3–6 bullet lines for comps that have a URL source (prefix each with '- ').
- You MAY add 1–2 short plain (non-bullet) lines of context above or below the comps when it's useful — e.g. rarity / production numbers, condition-sensitive caveats, or noting why a comp doesn't apply. These don't need a URL.
- Keep the whole field under ~600 chars.
- Use null for consensus_usd / watchcharts_median_usd if not available."""

    client = anthropic.Anthropic(api_key=api_key)

    import time as _time
    last_err = None
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model='claude-sonnet-4-5',
                max_tokens=1536,
                tools=[{
                    'type': 'web_search_20250305',
                    'name': 'web_search',
                    'max_uses': 5,
                }],
                messages=[{'role': 'user', 'content': prompt}],
            )
            break
        except anthropic.RateLimitError as e:
            last_err = e
            # honour Retry-After if present, else exponential backoff
            wait = 10 * (attempt + 1)
            try:
                ra = e.response.headers.get('retry-after') if getattr(e, 'response', None) else None
                if ra: wait = max(wait, int(float(ra)))
            except Exception:
                pass
            _time.sleep(wait)
    else:
        raise RuntimeError(f'Rate limited after retries: {last_err}')

    # Concatenate all text blocks in the final assistant message
    text = ''
    for block in resp.content:
        if getattr(block, 'type', None) == 'text':
            text += block.text
    text = text.strip()

    # Strip possible markdown code fences
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if not m:
        raise RuntimeError(f'Could not parse JSON from model output: {text[:200]}')
    data = json.loads(m.group(0))

    def _num(x):
        if x is None:
            return None
        try:
            return float(x)
        except (ValueError, TypeError):
            return None

    consensus = _num(data.get('consensus_usd'))
    wc_median = _num(data.get('watchcharts_median_usd'))
    orig_price = _num(watch['price'])

    # Fallback chain: AI consensus → WatchCharts median → original purchase price
    value = consensus
    fallback_note = None
    if value is None:
        if wc_median is not None:
            value = wc_median
            fallback_note = (f"_No consensus computed — defaulted to WatchCharts median "
                             f"(${wc_median:,.0f})._")
        elif orig_price is not None:
            value = orig_price
            fallback_note = (f"_No consensus or WatchCharts median found — defaulted to "
                             f"original purchase price (${orig_price:,.0f})._")

    # Models sometimes emit HTML entities (&#39;, &amp;, etc.) in JSON string
    # values. Decode them once so the downstream format_results filter only
    # performs a single round of HTML-escaping when rendering.
    import html as _html
    results_md = _html.unescape(data.get('results_markdown') or '')
    if fallback_note:
        results_md = (results_md + '\n\n' + fallback_note).strip()
    return {'value': value, 'results': results_md}


WATCH_SPEC_SOURCES = [
    "manufacturer's official website",
    "chrono24.com",
    "watchbox / thewatchbox.com",
    "calibercorner.com",
    "17jewels.info",
    "sjx.com.sg",
    "emmywatch.com",
    "thewatchpages.com",
    "hodinkee.com",
    "monochrome-watches.com",
    "watch-wiki.org / wikipedia watch entries",
]

# When the watch already has a calibre value, the lookup can go
# straight to calibre-specific reference sites for movement detail
# (jewels, escapement, beat, reserve). These two cover the long tail
# of obscure references better than the generalist watch sites.
WATCH_CALIBRE_SOURCES = [
    "calibercorner.com",
    "17jewels.info",
]


def fetch_watch_specs(watch):
    """Use Perplexity's web-search-grounded completions to look up a
    watch's specs from reputable sources and return {field: value}
    suggestions.

    Perplexity is search-first by design — every response is grounded
    in web results — and in side-by-side testing against Anthropic's
    web_search tool it tends to surface more reference / movement
    detail per query. Prompt and return shape are unchanged from the
    Claude version so the calling code (apply-lookup propagation,
    field-by-field validation, blank-only rules) doesn't need to know.

    Only fields the model is confident about should be populated; all
    others come back null. Raises RuntimeError on missing key or
    API failure.
    """
    api_key = os.environ.get('PERPLEXITY_API_KEY')
    if not api_key:
        raise RuntimeError('PERPLEXITY_API_KEY not configured')

    brand = (watch['brand'] or '').strip()
    model = (watch['model'] or '').strip()
    reference = (watch['reference'] or '').strip()
    calibre_hint = (watch['calibre'] or '').strip()
    case_num = (watch['case_num'] or '').strip()
    movement_num = (watch['movement_num'] or '').strip()
    purchase_date = (watch['date'] or '').strip()
    description = (watch['description'] or '').strip()
    notes = (watch['notes'] or '').strip()
    year_hint = watch['year']

    if not (brand or model or reference):
        raise RuntimeError('Need at least brand, model, or reference to look up specs.')

    ident = ' '.join(x for x in [
        brand, model,
        f'Ref. {reference}' if reference else '',
        f'Cal. {calibre_hint}' if calibre_hint else '',
        f'Case {case_num}' if case_num else '',
        f'Movement {movement_num}' if movement_num else '',
        str(year_hint) if year_hint else '',
    ] if x)

    sources_bullets = '\n'.join(f'- {s}' for s in WATCH_SPEC_SOURCES)
    metals = ', '.join(VALUE_LISTS['metal_watch'])
    origins = ', '.join(VALUE_LISTS['movement_origin'])
    escapements = ', '.join(VALUE_LISTS['escapement'])
    complications = ', '.join(COMPLICATIONS_OPTIONS)

    # When the record already has a calibre, point the searcher at
    # the two calibre-specific reference sites for movement detail
    # (jewels / escapement / beat / reserve). They cover obscure
    # references better than the generalist watch sites.
    if calibre_hint:
        calibre_sources_bullets = '\n'.join(
            f'- {s}' for s in WATCH_CALIBRE_SOURCES
        )
        calibre_hint_block = (
            f"\nThe calibre is already known: {calibre_hint}. For "
            f"movement-detail fields (movement_jewels, escapement, "
            f"balance_wheel, beat, reserve, movement_type, "
            f"movement_origin, calibre_notes) prefer these "
            f"calibre-specific sources first:\n"
            f"{calibre_sources_bullets}\n"
        )
    else:
        calibre_hint_block = ''

    prompt = f"""You are filling in specification fields for a specific wristwatch using reputable public sources.

Watch: {ident}
Record context that may contain piece-specific dating evidence:
- Description: {(description[:300] + '…') if len(description) > 300 else description or '(none)'}
- Notes: {(notes[:220] + '…') if len(notes) > 220 else notes or '(none)'}

Use at most 6 web searches, preferring these sources (roughly in order):
{sources_bullets}
{calibre_hint_block}
For each field below, return the value you find in any of those sources. If one reputable source states a value clearly, use it; do not require unanimous agreement. Return null only when NO source you searched mentions the field at all. Prefer sourced values over leaving fields null.

Target fields:
- metal: one of [{metals}]
- case_diameter: number in mm (float)
- dial_color: short string (e.g. "Black", "Blue", "Silver")
- year: integer production year of THIS individual watch, not the model/reference introduction year. Only return a year when you can derive it from piece-specific evidence: case/serial number, movement number when present (common for Lange and a few others, not most brands), papers, archive extract, warranty card, certificate, or a brand serial-to-year table. If sources only say when the reference/model was introduced or produced generally, return null. Never return a year later than the purchase date ({purchase_date or 'unknown'}).
- year_basis: one short phrase explaining the evidence for year, e.g. "movement number dates to 2003 via Omega serial table" or null. If year is null, year_basis must be null.
- edition: total count of pieces in a limited edition / limited run (integer). Return null for non-limited / open-production references.
- calibre: movement calibre name in its complete canonical form, with the manufacturer prefix when one is conventionally used (e.g. "F.P. Journe Calibre 1300.3", "A. Lange & Söhne L951.5", "ETA 7750", "Frédéric Piguet 1185", "Patek Philippe CH 29-535 PS"). Avoid returning just a bare number ("1304", "7750") — those are ambiguous because multiple manufacturers reuse number-style designations. CRITICAL: the case/reference number is NOT the calibre. The "Ref." value above is the case reference (e.g. Lange 1815 Chronograph references like 414.031 / 414.028 / 401.026; Patek Nautilus 5711/1A) — never copy that value into this field. The calibre is the MOVEMENT designation (Lange L951.5, Patek 26-330, Rolex 3135, etc.) and is published on calibercorner.com / 17jewels.info / brand technical sheets, not on retailer reference pages. If sources only mention the reference and don't disclose the movement calibre, return null.
- movement_type: one of ["Manual", "Automatic", "Quartz", "Spring Drive", "Co-Axial", "Tuning Fork"]. "Manual"/"Automatic" for traditional mechanical, "Quartz" for battery-powered crystal-regulated, "Spring Drive" only for Seiko/Grand Seiko Spring Drive, "Co-Axial" only for Omega watches the brand explicitly markets as Co-Axial, "Tuning Fork" for Bulova Accutron and similar hum movements.
- movement_origin: EXACTLY one of [{origins}] and nothing else. "In-House" = designed and made by the manufacturer; "Ébauche" = bought-in rough movement (e.g. ETA, Sellita, Valjoux) used as-is; "Modified" = an ébauche that has been noticeably reworked. Do not invent values like "Swiss" or "Ebauche-based".
- movement_jewels: integer
- escapement: EXACTLY one of [{escapements}]. Do NOT assume — return null when no source mentions the escapement. But when a source explicitly names one (e.g. "Swiss Lever escapement", "lever escapement", "anchor escapement", "Co-Axial", "natural escapement", "constant-force escapement", "detent", "tuning fork", "quartz"), you MUST return the matching enum — silence in that case is a bug. "Swiss Lever" is the canonical lever-escapement bucket; map "lever", "Swiss lever", "anchor", "straight-line lever" all to "Swiss Lever". "Co-Axial" only for Omega's George Daniels-derived escapement. "Natural" for Breguet's natural escapement (also revived by Daniels and others). "Constant Force" for Lange Zeitwerk, Romain Gauthier, F.P. Journe Chronomètre Optimum-style. "Detent" / "Chronometer" for marine/pivoted-detent escapements. "Cylinder", "Verge", "Pin Lever", "Duplex" for vintage/historical pieces. "Tuning Fork" for Accutron / Bulova hum movements. "Quartz" for quartz watches. "Other" only if a clearly novel escapement is named (e.g. Genequand silicon, Ulysse Nardin Anchor) and none above fit.
- balance_wheel: short text describing the regulating organ — balance wheel AND its hairspring/balance-spring together, including material, construction, and any notable detail. Examples: "Glucydur with regulating screws", "Beryllium copper, free-sprung", "Variable-inertia gold mass with silicon hairspring", "Modern bimetallic screw balance paired with contemporary balance spring, both selected and tuned by Sekiguchi". Keep it under 160 characters. Return null only if no source mentions any balance-wheel or hairspring detail.
- beat: vibrations per hour (VPH) for mechanical movements, or raw Hz for quartz/tuning-fork movements. For mechanical (Manual/Automatic) pick from [18000, 19800, 21600, 25200, 28800, 36000, 72000]; if the source gives Hz, multiply by 7200 (2.5 Hz = 18000, 3 Hz = 21600, 4 Hz = 28800, 5 Hz = 36000, 10 Hz = 72000). For battery-powered/quartz/tuning-fork movements, return the actual rate as stated (e.g. 360 for Accutron, 32768 for a quartz crystal, 7200 for a 1 Hz stepping quartz). Do NOT assume 28800 as a default — only return a value if the source clearly states it.
- reserve: power reserve in hours (integer)
- complications: array of strings drawn from [{complications}]
- clasp_type: clasp mechanism (short string)
- lug_mm: lug width in mm (float)
- strap_material: e.g. "Leather", "Steel", "Rubber"
- notes: a 2-4 sentence quality blurb about what makes this specific reference notable — its place in the brand's history, design innovation, technical distinction, or cultural significance. Write in a knowledgeable but concise collector's voice. Keep under 500 characters. Return null only if sources offer nothing substantive.
- calibre_notes: a 1-3 sentence summary of the calibre's distinguishing features — architecture (e.g. twin barrels in parallel, going train under the dial), key complications integrated into the movement, escapement / regulator design, hand-finishing, family lineage (which calibre it evolved from), or any patented mechanisms. This is about the MOVEMENT, not the watch as a whole — write what a movement-savvy collector would want to know. Keep under 400 characters. Return null if sources don't describe the calibre's internals.

Reply with ONLY a JSON object, no prose, no code fences:
{{
  "metal": null,
  "case_diameter": null,
  "dial_color": null,
  "year": null,
  "year_basis": null,
  "edition": null,
  "calibre": null,
  "movement_type": null,
  "movement_origin": null,
  "movement_jewels": null,
  "escapement": null,
  "balance_wheel": null,
  "beat": null,
  "reserve": null,
  "complications": null,
  "clasp_type": null,
  "lug_mm": null,
  "strap_material": null,
  "notes": null,
  "calibre_notes": null,
  "sources": "one-line note of which sources hit"
}}
"""

    # POST to Perplexity's chat-completions endpoint. urllib avoids
    # adding a `requests` dependency. Timeout is held below the 300s
    # gunicorn killer so the worker raises a clean Python exception
    # (mapped to a JSON 503 by the route) instead of getting SIGKILLed
    # and returning empty 500s.
    import urllib.request
    import urllib.error
    import time as _time

    body = json.dumps({
        'model': 'sonar-pro',
        'messages': [{'role': 'user', 'content': prompt}],
        'max_tokens': 2048,
    }).encode('utf-8')
    req = urllib.request.Request(
        'https://api.perplexity.ai/chat/completions',
        data=body,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        },
        method='POST',
    )

    last_err = None
    api_data = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                api_data = json.loads(resp.read().decode('utf-8'))
            break
        except urllib.error.HTTPError as e:
            last_err = e
            # 5xx + 429 are transient; 4xx (except 429) are permanent.
            if e.code == 429 or 500 <= e.code < 600:
                wait = 10 * (attempt + 1)
                try:
                    ra = e.headers.get('retry-after') if getattr(e, 'headers', None) else None
                    if ra:
                        wait = max(wait, int(float(ra)))
                except Exception:
                    pass
                _time.sleep(wait)
                continue
            try:
                detail = e.read().decode('utf-8', 'ignore')[:200]
            except Exception:
                detail = ''
            raise RuntimeError(f'Perplexity HTTP {e.code}: {detail}')
        except urllib.error.URLError as e:
            last_err = e
            _time.sleep(10 * (attempt + 1))
    else:
        raise RuntimeError(f'Lookup failed after retries: {last_err}')

    try:
        text = api_data['choices'][0]['message']['content'] or ''
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f'Unexpected Perplexity response: {str(api_data)[:200]}')
    text = text.strip()

    m = re.search(r'\{.*\}', text, re.DOTALL)
    if not m:
        raise RuntimeError(f'Could not parse JSON from model output: {text[:200]}')
    parsed = json.loads(m.group(0))

    # Surface Perplexity's citation URLs alongside the model's own
    # one-line "sources" note. Helpful when reviewing a lookup result
    # to see which pages it actually drew from.
    citations = api_data.get('citations') or []
    if citations and isinstance(parsed, dict):
        existing = (parsed.get('sources') or '').strip()
        cite_list = '; '.join(citations[:6])
        parsed['sources'] = (f'{existing} | citations: {cite_list}'
                             if existing else f'citations: {cite_list}')
    return parsed


def audit_coin_image_vs_description(coin):
    """Send a coin's obverse + reverse images and its catalog description
    to Claude vision and ask whether they describe the same coin.

    Returns {match: True|False|None, confidence: float|None, reason: str}.
    Returns match=None when there isn't enough material to judge.
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY not configured')
    desc = (coin['description'] or '').strip()
    if not desc:
        return {'match': None, 'confidence': None,
                'reason': 'no description on record'}
    images = []
    for fld, label in (('image_1', 'obverse'), ('image_2', 'reverse')):
        name = coin[fld]
        if not name:
            continue
        path = os.path.join(UPLOAD_FOLDER, name)
        if not os.path.exists(path):
            continue
        ext = os.path.splitext(name)[1].lower().lstrip('.')
        media_type = {
            'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
            'png': 'image/png', 'webp': 'image/webp', 'gif': 'image/gif',
        }.get(ext)
        if not media_type:
            continue
        try:
            import base64
            with open(path, 'rb') as fh:
                data = base64.b64encode(fh.read()).decode('ascii')
            images.append({'label': label, 'data': data,
                           'media_type': media_type})
        except Exception:
            continue
    if not images:
        return {'match': None, 'confidence': None,
                'reason': 'no usable images on record'}

    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed.")
    content = []
    for img in images:
        content.append({'type': 'text', 'text': f'{img["label"].capitalize()}:'})
        content.append({'type': 'image', 'source': {
            'type': 'base64',
            'media_type': img['media_type'],
            'data': img['data'],
        }})
    content.append({'type': 'text', 'text':
        f"""Catalog description for the same coin:
\"\"\"{desc}\"\"\"

Compare the image(s) above to the description. Focus on iconography
(figures, animals, legends, layout, key symbols). Wear, lighting,
angle, and minor flan differences do NOT count as mismatches. A
mismatch means the depicted subject is fundamentally different from
what the description says.

Reply with ONLY a JSON object, no prose:
{{"match": true|false, "confidence": 0.0, "reason": "one short sentence"}}"""})
    client = anthropic.Anthropic(api_key=api_key)
    resp = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=300,
        messages=[{'role': 'user', 'content': content}],
    )
    text = ''
    for block in resp.content:
        if getattr(block, 'type', None) == 'text':
            text += block.text
    text = text.strip()
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if not m:
        return {'match': None, 'confidence': None,
                'reason': f'parse error: {text[:80]}'}
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return {'match': None, 'confidence': None,
                'reason': f'JSON error: {text[:80]}'}
    return {
        'match': bool(data.get('match')) if data.get('match') is not None else None,
        'confidence': data.get('confidence'),
        'reason': (data.get('reason') or '').strip(),
    }


def fetch_coin_context(coin):
    """Claude-driven historical-environment summary for a coin, drawing
    on region, authority, mint, date, and description together.
    Returns dict {markdown: str}. Raises RuntimeError on missing key
    / API failure.
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY not configured')
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Run 'pip install anthropic'.")

    region    = (coin['region']    or '').strip()
    authority = (coin['authority'] or '').strip()
    mint      = (coin['mint']      or '').strip()
    desc      = (coin['description'] or '').strip()
    refs      = (coin['coin_references'] or '').strip()
    grade_notes = (coin['notes'] or '').strip()
    date_hint = ''
    if coin['date_1_text'] or coin['date_2_text']:
        date_hint = (coin['date_1_text'] or '')
        if coin['date_2_text']:
            date_hint = f"{date_hint} – {coin['date_2_text']}"

    if not (region or authority or mint or date_hint):
        raise RuntimeError('Fill in at least region, authority, mint, or date first.')

    prompt = f"""You are an ancient-numismatics historian writing a short,
rich profile of a specific coin. You have seven inputs; weave them
together — don't just restate them. Put special weight on pedigree,
provenance, sale history, hoard context, and catalog references. The
catalog references and grade notes often carry a lot of signal (BCD
pedigree, Calciati number, SNG / HGC / RIC / RPC / Crawford / Ravel
references, hoard provenance, strike quality, rarity call-outs); mine
them for anything useful and cite the reference trail when it matters.

Region:      {region or '(not specified)'}
Authority:   {authority or '(not specified)'}
Mint:        {mint or '(not specified)'}
Date range:  {date_hint or '(not specified)'}
Description: {desc or '(not specified)'}
Pedigree / References: {refs or '(not specified)'}
Grade / Conditions:    {grade_notes or '(not specified)'}

Use up to 4 concise web searches to ground the facts. Cover, in this order:

1. Historical environment — the political / military situation at this
   mint during the date range; who was in power (dynasty, magistrate,
   satrap, emperor…) and what they were reacting to (war, trade boom,
   succession, reform).

2. Coin style — the iconography, engraving school, fabric / flan, and
   any artistic signatures (e.g. late-Classical Syracusan masters,
   Hellenistic realism, archaic incuse reverse, Roman provincial
   portrait conventions). Name the style when it's identifiable.

3. Numismatic importance — lead with the pedigree / reference evidence
   when present: collection pedigree, prior sale, hoard, die-study,
   rarity, catalog placement, or significance within the series (first
   portrait of a ruler, earliest use of a legend, benchmark type in a
   standard catalog). Skip padding; only include what actually applies.

4. How this coin reflected the times — propaganda choices, civic pride,
   response to economic or military pressure, religious festival,
   trade denomination. Tie the imagery or metal directly to the moment.

Write four short sections using these bold labels on their own lines:
**Historical environment**, **Style**, **Numismatic importance**,
**Reflection of the times**. Each label is followed by 1–3 bullets
starting with '- '. Include 2–4 source URLs as trailing bare URLs
after relevant bullets. Under ~1600 chars total.

Reply with ONLY the markdown, wrapped in a <markdown>…</markdown> tag.
No prose, no code fences, no JSON."""

    client = anthropic.Anthropic(api_key=api_key)
    import time as _time
    last_err = None
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model='claude-sonnet-4-5',
                max_tokens=2000,
                tools=[{
                    'type': 'web_search_20250305',
                    'name': 'web_search',
                    'max_uses': 4,
                }],
                messages=[{'role': 'user', 'content': prompt}],
            )
            break
        except anthropic.RateLimitError as e:
            last_err = e
            wait = 10 * (attempt + 1)
            try:
                ra = e.response.headers.get('retry-after') if getattr(e, 'response', None) else None
                if ra: wait = max(wait, int(float(ra)))
            except Exception:
                pass
            _time.sleep(wait)
    else:
        raise RuntimeError(f'Rate limited after retries: {last_err}')

    text = ''
    for block in resp.content:
        if getattr(block, 'type', None) == 'text':
            text += block.text
    text = text.strip()

    # Prefer the <markdown>…</markdown> envelope. Fall back to legacy
    # JSON shape, then finally to the raw text, so a sloppy output
    # from Claude still lands as usable content.
    md = ''
    m = re.search(r'<markdown>(.*?)</markdown>', text, re.DOTALL | re.IGNORECASE)
    if m:
        md = m.group(1).strip()
    else:
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(0))
                md = (data.get('markdown') or '').strip()
            except ValueError:
                md = ''
        if not md:
            md = text  # last-ditch: show the whole thing
    if not md:
        raise RuntimeError(f'Empty response from model: {text[:200]}')
    import html as _html
    md = _html.unescape(md).strip()
    md = re.sub(r'</?cite\b[^>]*>', '', md, flags=re.IGNORECASE)
    return {'markdown': md}


def fetch_coin_history(field_name, topic, coin):
    """Use Claude's web_search tool to describe the history of a coin's
    region or authority. Returns dict {markdown: str}.
    Raises RuntimeError on missing key or API failure.
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY not configured')
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed. Run 'pip install anthropic'.")

    topic = (topic or '').strip()
    if not topic:
        raise RuntimeError(f'No {field_name} set for this coin')

    date_hint = ''
    if coin['date_1_text'] or coin['date_2_text']:
        date_hint = (coin['date_1_text'] or '')
        if coin['date_2_text']:
            date_hint = f"{date_hint} – {coin['date_2_text']}"
    context_bits = [x for x in [coin['denomination'], coin['metal'], coin['mint']] if x]
    ctx = (' / '.join(context_bits)) if context_bits else ''
    kind = 'region' if field_name == 'region' else 'issuing authority'
    desc = (coin['description'] or '').strip()
    refs = (coin['coin_references'] or '').strip()
    grade_notes = (coin['notes'] or '').strip()

    prompt = f"""You are an ancient-numismatics historian summarizing the {kind} of a specific coin.

{kind.capitalize()}: {topic}
Date range: {date_hint or '(not specified)'}
Other coin context: {ctx or '(none)'}
Description: {desc[:500] if desc else '(not specified)'}
Pedigree / References: {refs[:500] if refs else '(not specified)'}
Grade / Conditions: {grade_notes[:300] if grade_notes else '(not specified)'}

Use up to 4 concise web searches to ground facts. Stress pedigree and
references wherever the record gives you a lead: collection pedigree,
prior sale, hoard provenance, die-study, catalog numbers, rarity notes,
or standard references (SNG, HGC, RIC, RPC, Crawford, Ravel, Calciati,
BCD, etc.). Do not bury this evidence behind generic political history.

Focus on:
- What this {kind} was (city-state, kingdom, satrapy, Roman province, etc.)
- Key political/cultural events during the coin's date range that shaped its coinage
- Notable rulers or mint activity tied to this {kind}
- Pedigree / reference evidence that helps identify why this coin matters
- One-line significance in the broader Greek/Roman world

Reply with ONLY a JSON object, no prose, no code fences:
{{"markdown": "4–7 short lines. Prefix factual claims with '- '. Lead with pedigree / reference evidence when present, then add necessary historical context. Include 2–4 source URLs as trailing bare URLs after relevant bullets. Under ~900 chars total."}}"""

    client = anthropic.Anthropic(api_key=api_key)

    import time as _time
    last_err = None
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model='claude-sonnet-4-5',
                max_tokens=1200,
                tools=[{
                    'type': 'web_search_20250305',
                    'name': 'web_search',
                    'max_uses': 4,
                }],
                messages=[{'role': 'user', 'content': prompt}],
            )
            break
        except anthropic.RateLimitError as e:
            last_err = e
            wait = 10 * (attempt + 1)
            try:
                ra = e.response.headers.get('retry-after') if getattr(e, 'response', None) else None
                if ra: wait = max(wait, int(float(ra)))
            except Exception:
                pass
            _time.sleep(wait)
    else:
        raise RuntimeError(f'Rate limited after retries: {last_err}')

    text = ''
    for block in resp.content:
        if getattr(block, 'type', None) == 'text':
            text += block.text
    text = text.strip()

    m = re.search(r'\{.*\}', text, re.DOTALL)
    if not m:
        raise RuntimeError(f'Could not parse JSON from model output: {text[:200]}')
    data = json.loads(m.group(0))
    import html as _html
    md = _html.unescape(data.get('markdown') or '').strip()
    # Strip Claude web_search <cite index="...">...</cite> wrappers.
    md = re.sub(r'</?cite\b[^>]*>', '', md, flags=re.IGNORECASE)
    return {'markdown': md}


def fetch_recording_notes(rec):
    """Claude-driven review + historical-context summary for a recording.
    Returns dict {markdown: str}. Raises RuntimeError on missing key
    or empty model output. Mirrors the coin-context pattern: Sonnet
    with web_search, output wrapped in <markdown>...</markdown>.
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY not configured')
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed.")

    title  = (rec['title']  or '').strip()
    artist = (rec['artist'] or '').strip()
    if not (title or artist):
        raise RuntimeError('Need a title or artist before fetching notes.')

    year   = (rec['year_recorded'] or '').strip()
    genre  = ' / '.join(x for x in [
        (rec['genre'] or '').strip(),
        (rec['genre_2'] or '').strip(),
    ] if x)
    # players column may not exist on older DBs that haven't run the
    # ALTER yet — sqlite3.Row raises IndexError on missing columns.
    try:
        players = (rec['players'] or '').strip()
    except (IndexError, KeyError):
        players = ''
    fmt_bits = [x for x in [
        (rec['type']  or '').strip(),
        (rec['speed'] or '').strip(),
        (rec['sound'] or '').strip(),
        (rec['other'] or '').strip(),
    ] if x]
    fmt = ' · '.join(fmt_bits)

    # Only ask Claude to populate Players when the field is empty —
    # we never want to clobber a user-entered roster.
    want_players = not players
    players_block = ("\nAlso return a comma-separated list of the "
                     "key musicians on this recording (lead artist + "
                     "sidemen / band members), each followed by their "
                     "primary instrument or role in parentheses — "
                     "e.g. \"John Coltrane (tenor sax), McCoy Tyner "
                     "(piano), Jimmy Garrison (bass), Elvin Jones "
                     "(drums)\". Use short instrument names (sax, not "
                     "tenor saxophone Selmer Mark VI). Wrap the list "
                     "in a <players>...</players> tag immediately "
                     "after the <markdown> block. Omit the <players> "
                     "tag entirely if you can't determine personnel "
                     "with reasonable confidence.") if want_players else ""

    # Always ask for the tracklist when the DB doesn't have one yet —
    # Claude's track names feed the per-track Spotify pill row in the
    # UI. Each track on its own line (no numbering, no quotes), wrapped
    # in <tracks>...</tracks>. Skip the tag if track-level data isn't
    # findable for this recording.
    try:
        existing_tracks = (rec['tracks'] or '').strip()
    except (IndexError, KeyError):
        existing_tracks = ''
    want_tracks = not existing_tracks
    tracks_block = ("\nAlso return the tracklist for the recording, "
                    "one track title per line, in album order, no "
                    "numbering and no surrounding quotes. Wrap the "
                    "list in a <tracks>...</tracks> tag (after any "
                    "<players> tag if present). Omit the <tracks> "
                    "tag entirely if you can't recover the tracklist "
                    "with reasonable confidence.") if want_tracks else ""

    # Always verify genre + sub-genre on Lookup. The model returns its
    # best assessment regardless of whether the DB already has values,
    # so a wrong existing genre gets corrected. Genre is constrained to
    # the recording_genre dropdown values; sub-genre is free text.
    allowed_genres = list(VALUE_LISTS.get('recording_genre', []))
    genres_csv = ', '.join(allowed_genres)
    genre_block = (
        f"\nAlso classify the recording. Return the primary genre in a "
        f"<genre>...</genre> tag — it MUST be exactly one of: "
        f"{genres_csv}. Pick the closest fit; if you can't decide with "
        f"reasonable confidence, omit the <genre> tag entirely. Then "
        f"return a more specific sub-genre in a <genre_2>...</genre_2> "
        f"tag (free text — e.g. \"Bebop\", \"Hard Rock\", \"Bossa Nova\", "
        f"\"Soul-Jazz\"). Omit the <genre_2> tag if no useful "
        f"sub-classification fits."
    )

    prompt = f"""You are a music critic + recording historian writing a
brief reference note for a single album / recording in a personal
collection. Use up to 4 web searches to ground facts.

Title:   {title or '(unknown)'}
Artist:  {artist or '(unknown)'}
Year:    {year or '(unknown)'}
Genre:   {genre or '(unspecified)'}
Players: {players or '(unspecified)'}
Format:  {fmt or '(unspecified)'}

Cover whichever of these are notable for this specific recording:
- critical reception / canonical status
- recording history (studio, dates, key personnel beyond the headliner)
- standout tracks
- awards or chart performance
- the artist's career context at the time

Style: 4–8 short bullets starting with "- ". Plain factual prose,
no headers, no fluff, no marketing copy. Under ~1400 chars total.
DO NOT include URLs anywhere in the bullet text — sources go in a
separate tag below.

Wrap the bullets in <markdown>…</markdown>. Then, immediately
after, list 2–4 source URLs (bare https://…, comma-separated) in
a <urls>…</urls> tag. No prose outside these tags, no code
fences, no JSON.{players_block}{tracks_block}{genre_block}"""

    client = anthropic.Anthropic(api_key=api_key)
    import time as _time
    last_err = None
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model='claude-sonnet-4-5',
                max_tokens=2000,
                tools=[{
                    'type': 'web_search_20250305',
                    'name': 'web_search',
                    'max_uses': 4,
                }],
                messages=[{'role': 'user', 'content': prompt}],
            )
            break
        except anthropic.RateLimitError as e:
            last_err = e
            wait = 10 * (attempt + 1)
            try:
                ra = e.response.headers.get('retry-after') if getattr(e, 'response', None) else None
                if ra: wait = max(wait, int(float(ra)))
            except Exception:
                pass
            _time.sleep(wait)
    else:
        raise RuntimeError(f'Rate limited after retries: {last_err}')

    text = ''
    for block in resp.content:
        if getattr(block, 'type', None) == 'text':
            text += block.text
    text = text.strip()

    md = ''
    m = re.search(r'<markdown>(.*?)</markdown>', text, re.DOTALL | re.IGNORECASE)
    if m:
        md = m.group(1).strip()
    else:
        md = text  # last-ditch: use whatever the model returned
    if not md:
        raise RuntimeError(f'Empty response from model: {text[:200]}')

    import html as _html
    md = _html.unescape(md).strip()
    # Strip Claude web_search <cite index="...">...</cite> wrappers.
    md = re.sub(r'</?cite\b[^>]*>', '', md, flags=re.IGNORECASE)
    # Defensive: if Claude ignored the "no URLs in bullets" rule,
    # extract them out and feed into the urls list below. Strips
    # trailing punctuation that hugs URLs in prose.
    leaked_urls = re.findall(r'https?://[^\s<>"\']+', md)
    if leaked_urls:
        md = re.sub(r'https?://[^\s<>"\']+', '', md)
        md = re.sub(r'(?im)^[\s\-•*]*(sources?|references?|citations?)\s*:?\s*$\n?', '', md)
        md = re.sub(r'\n{3,}', '\n\n', md).strip()

    # <urls>...</urls> block — comma- or whitespace-separated sources.
    urls = []
    um = re.search(r'<urls>(.*?)</urls>', text, re.DOTALL | re.IGNORECASE)
    raw_urls = (um.group(1) if um else '') + '\n' + ' '.join(leaked_urls)
    raw_urls = _html.unescape(raw_urls)
    raw_urls = re.sub(r'</?cite\b[^>]*>', '', raw_urls, flags=re.IGNORECASE)
    seen = set()
    for u in re.findall(r'https?://[^\s<>"\',;]+', raw_urls):
        u = u.rstrip('),.;:!?\\]>"\'')
        if u and u not in seen:
            seen.add(u)
            urls.append(u)

    # Optional <players>...</players> block — only meaningful when the
    # caller asked for it (i.e. the field was empty going in).
    new_players = ''
    if want_players:
        pm = re.search(r'<players>(.*?)</players>', text, re.DOTALL | re.IGNORECASE)
        if pm:
            new_players = _html.unescape(pm.group(1)).strip()
            new_players = re.sub(r'</?cite\b[^>]*>', '', new_players, flags=re.IGNORECASE)
            # Collapse any internal newlines / extra whitespace in the
            # comma-separated list so it lands clean in the input.
            new_players = re.sub(r'\s+', ' ', new_players).strip(' ,')

    # Optional <tracks>...</tracks> block. One title per line; we
    # normalize to a newline-separated string so the UI can split on
    # \n to render Spotify-search pills.
    new_tracks = ''
    if want_tracks:
        tm = re.search(r'<tracks>(.*?)</tracks>', text, re.DOTALL | re.IGNORECASE)
        if tm:
            raw = _html.unescape(tm.group(1)).strip()
            raw = re.sub(r'</?cite\b[^>]*>', '', raw, flags=re.IGNORECASE)
            lines = []
            for line in raw.splitlines():
                t = line.strip()
                # Strip leading numbering ("1.", "1)", "1 -") and
                # surrounding quotes the model sometimes adds despite
                # the prompt asking it not to.
                t = re.sub(r'^[\s\-•*]*\d+[\.\)]\s*', '', t)
                t = t.strip(' "\'')
                if t:
                    lines.append(t)
            new_tracks = '\n'.join(lines)

    # Optional <genre>...</genre> + <genre_2>...</genre_2> blocks. Genre
    # is validated against the recording_genre dropdown (case-
    # insensitive); a model-returned value not in the list is dropped.
    new_genre = ''
    gm = re.search(r'<genre>(.*?)</genre>', text, re.DOTALL | re.IGNORECASE)
    if gm:
        cand = _html.unescape(gm.group(1)).strip()
        cand = re.sub(r'</?cite\b[^>]*>', '', cand, flags=re.IGNORECASE).strip()
        cand_l = cand.lower()
        for allowed in allowed_genres:
            if allowed.lower() == cand_l:
                new_genre = allowed
                break
    new_genre_2 = ''
    g2m = re.search(r'<genre_2>(.*?)</genre_2>', text, re.DOTALL | re.IGNORECASE)
    if g2m:
        cand = _html.unescape(g2m.group(1)).strip()
        cand = re.sub(r'</?cite\b[^>]*>', '', cand, flags=re.IGNORECASE).strip()
        new_genre_2 = re.sub(r'\s+', ' ', cand).strip(' ,"\'')

    return {'markdown': md, 'players': new_players,
            'tracks': new_tracks, 'urls': urls,
            'genre': new_genre, 'genre_2': new_genre_2}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

LANDING_CATEGORY = (os.environ.get('STUFFAPP_LANDING_CATEGORY') or '').strip()


@app.route('/')
def index():
    allowed = g.get('allowed_cats') or set()
    if LANDING_CATEGORY in CATEGORIES and LANDING_CATEGORY in allowed:
        target = LANDING_CATEGORY
    else:
        target = next((c for c in CATEGORIES if c in allowed), 'watches')
    return redirect(url_for('list_view', category=target))


@app.route('/persons-default')
def persons_default():
    """Entry point used by the People nav tab — opens the most relevant
    person detail directly so the tab lands on a useful record instead
    of the full list. Back / search / direct list URLs still route
    through list_view normally.

    Resolution order:
      1. The current user's display_name (set in admin/users) — match
         it as a name fragment against persons.name. Lets young.sohn@…
         with display_name "Young Sohn" land on the Sohn record.
      2. Fall back to "Mark Armenante" — the historical default and
         what most users want when there's no display_name set.
    """
    db = get_db()
    row = None
    user = g.get('current_user') or {}
    display = (user.get('display_name') or '').strip()
    if display:
        # Build a fragment pattern: "Young Sohn" → "%Young%Sohn%".
        # Matches even if the persons.name has a middle name in
        # between (e.g. "Young A. Sohn").
        parts = [p for p in display.split() if p]
        if parts:
            pattern = '%' + '%'.join(parts) + '%'
            row = db.execute(
                "SELECT id FROM persons WHERE name LIKE ? "
                "ORDER BY length(name) DESC LIMIT 1",
                (pattern,)
            ).fetchone()
    if not row:
        row = db.execute(
            "SELECT id FROM persons "
            "WHERE name LIKE 'Mark%Armenante%' "
            "ORDER BY length(name) DESC LIMIT 1"
        ).fetchone()
    if row:
        return redirect(url_for('detail_view', category='persons', record_id=row['id']))
    return redirect(url_for('list_view', category='persons'))


@app.route('/<category>')
def list_view(category):
    if category not in CATEGORIES:
        abort(404)
    db = get_db()
    # Form field is named q_<category> so browser autocomplete history is
    # scoped per category; legacy ?q= links (toolbar pills, bookmarks)
    # still work.
    q   = (request.args.get(f'q_{category}')
           or request.args.get('q') or '').strip()
    dot = request.args.get('dot', '') == '1'
    raw_filter = request.args.get('filter')
    coin_filter = (raw_filter or '').strip() or None
    # ?at=<property name> — drill in from a Property's pill row.
    at_property = (request.args.get('at') or '').strip() or None
    # Default filters apply on a fresh visit (no explicit ?filter= and no
    # search query). An active search bypasses the default so users don't
    # have to click Other / clear filter just to find a sold/loaned item.
    # An explicit empty ?filter= still clears all filters.
    if not q:
        if category == 'properties' and raw_filter is None:
            coin_filter = 'own'
        if category == 'vehicles' and raw_filter is None:
            coin_filter = 'own'
    sql, params = build_search_query(category, q, dot=dot,
                                     coin_filter=coin_filter,
                                     at_property=at_property)
    rows = db.execute(sql, params).fetchall()
    # When ?at=<name> is set, resolve the matching Property's id so
    # the list page can render a "← back to <Property>" pill that
    # jumps to its detail directly (browser back also works, this
    # is just a one-tap shortcut). Alias-aware: "Carp" or
    # "Carpinteria" both find the same property record.
    at_property_url = None
    if at_property:
        aliases = _property_alias_group(at_property)
        if aliases:
            ph = ','.join(['?' for _ in aliases])
            prop_row = db.execute(
                f"SELECT id FROM properties "
                f"WHERE LOWER(TRIM(name)) IN ({ph}) LIMIT 1",
                aliases
            ).fetchone()
            if prop_row:
                at_property_url = url_for('detail_view', category='properties',
                                          record_id=prop_row['id'])
    counts = get_counts()
    cat_info = CATEGORIES[category]
    extra_fields = LIST_EXTRA_FIELDS.get(category, [])
    # Split the compound properties filter into its two axes for the template.
    prop_status, prop_type = _split_property_filter(coin_filter) \
        if category == 'properties' else (None, None)
    # The Ordered pill only makes sense if there's at least one such
    # row (or the user is already viewing filter=ordered and wants a
    # way to toggle back off).
    has_ordered = False
    if category in ('coins', 'watches'):
        table = CATEGORIES[category]['table']
        has_ordered = db.execute(
            f"SELECT EXISTS(SELECT 1 FROM {table} "
            f"WHERE LOWER(TRIM(COALESCE(status,''))) = 'ordered')"
        ).fetchone()[0] == 1
    # Same toggle-when-relevant rule for the No-longer-Owned pill so
    # an empty collection doesn't show a filter that produces nothing.
    has_no_longer_owned = False
    if category == 'watches':
        table = CATEGORIES[category]['table']
        has_no_longer_owned = db.execute(
            f"SELECT EXISTS(SELECT 1 FROM {table} "
            f"WHERE LOWER(TRIM(COALESCE(status,''))) IN ('sold','gifted','lost'))"
        ).fetchone()[0] == 1
    return render_template('list.html',
                           category=category,
                           cat_info=cat_info,
                           rows=rows,
                           counts=counts,
                           current_category=category,
                           categories=CATEGORIES,
                           q=q,
                           dot=dot,
                           coin_filter=coin_filter,
                           at_property=at_property,
                           at_property_url=at_property_url,
                           prop_status=prop_status,
                           prop_type=prop_type,
                           result_count=len(rows),
                           has_ordered=has_ordered,
                           has_no_longer_owned=has_no_longer_owned,
                           extra_fields=extra_fields,
                           fields=visible_fields(category))


@app.route('/<category>/new', methods=['GET', 'POST'])
def new_record(category):
    if category not in CATEGORIES:
        abort(404)
    db = get_db()
    counts = get_counts()
    cat_info = CATEGORIES[category]

    if request.method == 'POST':
        record_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat()
        data = {'id': record_id, 'created_at': now, 'updated_at': now}

        # Track originals so we can default empty *_title columns to the
        # uploaded file's basename after the row is parsed.
        file_originals = {}
        for field in visible_fields(category):
            fname = field['name']
            if field.get('readonly'):
                continue
            if field['type'] == 'file':
                f = request.files.get(fname)
                stored = save_upload(f)
                if stored:
                    data[fname] = stored
                    if f and f.filename:
                        file_originals[fname] = f.filename
                else:
                    data[fname] = None
            elif field['type'] == 'checkbox-group':
                checked = request.form.getlist(fname)
                data[fname] = ','.join(checked)
            else:
                val = request.form.get(fname, '').strip()
                if fname == 'price':
                    # Multi-currency: preserve "US$100,000.00" /
                    # "A$50,000.00" verbatim; fall back to legacy
                    # strip-and-parse for plain numbers.
                    val = _normalize_price_input(val)
                elif field['type'] == 'number' or fname in ('beat', 'reserve', 'value'):
                    val = val.replace('$', '').replace(',', '').strip()
                    # Strip trailing unit suffix ("8.50 g", "26.5 mm", "28800 hrs")
                    # in case the JS submit handler didn't run.
                    m = re.match(r'^\s*(-?\d+(?:\.\d+)?)\s*[A-Za-z%°/]*\s*$', val)
                    if m:
                        val = m.group(1)
                data[fname] = val if val else None

        if category == 'watches':
            _apply_watch_order_form_fields(data, request.form)
            _graduate_watch_order_if_owned(data, data.get('status'))

        # Auto-fill empty *_title / *_label columns with the uploaded
        # file's basename for each file field that has a paired title
        # column. Only fills when the user didn't supply a title via
        # the form — never overwrites.
        for file_field, original in file_originals.items():
            title_field = _title_field_for(category, file_field)
            if title_field and not (data.get(title_field) or '').strip():
                base = os.path.splitext(os.path.basename(original))[0].strip()
                if base:
                    data[title_field] = base

        # Owner default — applied whenever the form arrived without
        # an owner. The owner field is hidden for member users (the
        # form is gated by current_user.role == 'owner' in the
        # template), so this branch always fires for them.
        #
        # Coins always seed Mark regardless of who creates them — the
        # coin collection is his. Watches default to Mark only for
        # owner-role creators; members creating a watch get the
        # standard 'YM' default. All other categories: members get
        # 'YM', owners get DEFAULT_OWNER_BY_CATEGORY.
        if not (data.get('owner') or '').strip():
            if category == 'coins':
                data['owner'] = 'Mark'
            else:
                user = g.get('current_user') or {}
                if user.get('role') != 'owner':
                    data['owner'] = 'YM'
                else:
                    d = DEFAULT_OWNER_BY_CATEGORY.get(category)
                    if d:
                        data['owner'] = d

        # Required fields on create. Owner only — needed for the
        # row-filter / per-user access check from the moment the
        # record exists. Property is intentionally NOT required here:
        # the autosave-on-new flow would silently 400 every keystroke
        # for users who hadn't filled Property yet, and nothing got
        # persisted. Property can be filled in afterwards via the
        # normal save_field path. Same for coin date: a coin should come
        # into existence when the user starts typing Authority / Region /
        # Denomination, then Date can be filled later.
        missing = []
        if not (data.get('owner') or '').strip():
            missing.append('Owner')
        if missing:
            err = 'Missing required field(s): ' + ', '.join(missing)
            # AJAX autosave-on-/new flow: client expects JSON.
            if request.headers.get('Accept', '').startswith('application/json') \
                    or request.headers.get('X-Requested-With') == 'fetch':
                return jsonify({'ok': False, 'error': err}), 400
            flash(err, 'error')
            # Re-render the same new-record form with the data the user
            # already entered (preserves their work) and focus the first
            # missing field. A redirect here would wipe everything.
            focus_map = {
                'Property': 'property_name' if category == 'coins' else 'property',
                'Owner': 'owner',
                'Date': 'date_1' if category == 'coins' else 'date',
            }
            focus_field = focus_map.get(missing[0])
            return _render_new_form(category, data=data, focus_field=focus_field)
        if category == 'coins':
            data['coin_id'] = next_coin_id(db)
            data['cat_id'] = next_cat_id(db, data.get('property_name'), data.get('date_1'))
        elif category == 'watches':
            data['cat_id'] = next_serial_cat_id(db, 'watches', 'W')
        elif category == 'art':
            data['cat_id'] = next_serial_cat_id(db, 'art', 'A')

        # Row-filter guard on creation. If the user is restricted on
        # any field for this category, the new record's value must
        # land within their allowed set — otherwise they'd create a
        # record they immediately can't see.
        cat_filt = _row_filter_for_category(g.get('current_user'), category)
        for fld, allowed in cat_filt.items():
            if not allowed:
                continue
            v = (data.get(fld) or '')
            if str(v).strip() not in allowed:
                err = (f'New record\'s {fld} must be one of: '
                       + ', '.join(allowed))
                if request.headers.get('Accept', '').startswith('application/json') \
                        or request.headers.get('X-Requested-With') == 'fetch':
                    return jsonify({'ok': False, 'error': err}), 403
                flash(err, 'error')
                return _render_new_form(category, data=data, focus_field=fld)

        cols = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        db.execute(f"INSERT INTO {CATEGORIES[category]['table']} ({cols}) VALUES ({placeholders})",
                   list(data.values()))

        # Resequence Display Position for only the new coin's group
        # (Carp Ancient, Carp Modern, NY Ancient, or NY Modern).
        if category == 'coins':
            new_group = _coin_group_for(
                data.get('property_name'), data.get('date_1'))
            if new_group:
                _renumber_coin_groups(db, [new_group])

        db.commit()
        detail_url = url_for('detail_view', category=category, record_id=record_id)
        save_url = url_for('save_field', category=category, record_id=record_id)
        # AJAX path (used by autosave-on-/new flow): return JSON so the
        # client can flip into save_field mode without a page reload.
        if request.headers.get('Accept', '').startswith('application/json') \
                or request.headers.get('X-Requested-With') == 'fetch':
            generated = {
                k: data.get(k) for k in ('coin_id', 'cat_id')
                if data.get(k) not in (None, '')
            }
            return jsonify({'ok': True, 'id': record_id,
                            'detail_url': detail_url, 'save_url': save_url,
                            'generated': generated})
        flash(f"Record created successfully.", 'success')
        return redirect(detail_url)

    # GET - blank form
    return _render_new_form(category)


def _render_new_form(category, data=None, focus_field=None):
    """Render the /<category>/new form. Used both for the bare GET and
    for re-rendering after a server-side validation failure on POST so
    the user's already-entered data isn't lost. Pass `data` (a dict
    keyed by field name) to repopulate inputs; pass `focus_field` to
    auto-focus a specific field on load (e.g. the missing required
    field that triggered the re-render)."""
    cat_info = CATEGORIES[category]
    return render_template('detail.html',
                           category=category,
                           cat_info=cat_info,
                           record=data,
                           counts=get_counts(),
                           current_category=category,
                           categories=CATEGORIES,
                           fields=visible_fields(category),
                           is_new=True,
                           prev_id=None,
                           next_id=None,
                           hertz=None,
                           coin_age_val=None,
                           property_topics=None,
                           camera_compatible_lenses=None,
                           lens_compatible_cameras=None,
                           property_pill_categories=None,
                           back_href=None,
                           service_overdue=None,
                           service_years=None,
                           today_iso=date.today().isoformat(),
                           complications_options=COMPLICATIONS_OPTIONS,
                           vlists=current_vlists(category),
                           focus_field=focus_field,
                           ta=build_typeahead(category))


@app.route('/<category>/<record_id>', methods=['GET', 'POST'])
def detail_view(category, record_id):
    if category not in CATEGORIES:
        abort(404)
    db = get_db()
    table = CATEGORIES[category]['table']
    cat_info = CATEGORIES[category]
    counts = get_counts()

    record = db.execute(f"SELECT * FROM {table} WHERE id = ?", [record_id]).fetchone()
    if record is None:
        abort(404)
    # Row-level access: a member with a filter on this category can
    # only see records whose filtered fields match. Pretend the row
    # doesn't exist (404) rather than 403 — fewer leaks about what's
    # there.
    if not _user_can_see_row(category, record):
        abort(404)

    # Prev/Next navigation. If the URL carries the same q / filter the
    # list view used (we forward both into the detail link), navigate
    # within that scoped, sorted set instead of the full table — so
    # < / > on a NY-Ancient-filtered coin walks the NY-Ancient list,
    # not the entire collection.
    nav_q = (request.args.get('q') or '').strip()
    nav_filter = (request.args.get('filter') or '').strip() or None
    nav_at = (request.args.get('at') or '').strip() or None
    if nav_q or nav_filter or nav_at:
        try:
            nav_sql, nav_params = build_search_query(
                category, nav_q, dot=False, coin_filter=nav_filter,
                at_property=nav_at)
        except Exception:
            nav_sql, nav_params = None, None
        if nav_sql:
            id_sql = re.sub(r'^SELECT \*', 'SELECT id', nav_sql, count=1)
            all_ids = [r['id'] for r in db.execute(id_sql, nav_params).fetchall()]
        else:
            nav_wheres, nav_params2 = [], []
            _apply_row_filter_clauses(category, nav_wheres, nav_params2)
            nav_where = f"WHERE {' AND '.join(nav_wheres)}" if nav_wheres else ''
            all_ids = [r['id'] for r in db.execute(
                f"SELECT id FROM {table} {nav_where} ORDER BY created_at DESC",
                nav_params2).fetchall()]
    else:
        nav_wheres, nav_params2 = [], []
        _apply_row_filter_clauses(category, nav_wheres, nav_params2)
        nav_where = f"WHERE {' AND '.join(nav_wheres)}" if nav_wheres else ''
        all_ids = [r['id'] for r in db.execute(
            f"SELECT id FROM {table} {nav_where} ORDER BY created_at DESC",
            nav_params2).fetchall()]
    idx = all_ids.index(record_id) if record_id in all_ids else -1
    prev_id = all_ids[idx - 1] if idx > 0 else None
    next_id = all_ids[idx + 1] if idx < len(all_ids) - 1 else None

    if request.method == 'POST':
        now = datetime.utcnow().isoformat()
        updates = {'updated_at': now}

        for field in visible_fields(category):
            fname = field['name']
            if field.get('readonly'):
                continue
            if field['type'] == 'file':
                f = request.files.get(fname)
                if f and f.filename:
                    stored = save_upload(f)
                    if stored:
                        updates[fname] = stored
                # else keep existing value (don't overwrite)
            elif field['type'] == 'checkbox-group':
                checked = request.form.getlist(fname)
                updates[fname] = ','.join(checked)
            else:
                val = request.form.get(fname, '').strip()
                # Strip currency formatting before saving numeric fields
                if fname == 'price':
                    val = _normalize_price_input(val)
                elif field['type'] == 'number' or fname in ('beat', 'reserve', 'value'):
                    val = val.replace('$', '').replace(',', '').strip()
                val = normalize_field_value(table, fname, val)
                updates[fname] = val if val else None

        if category == 'watches':
            _apply_watch_order_form_fields(updates, request.form)
            _graduate_watch_order_if_owned(updates, updates.get('status'))

        # If a coin moved groups, resequence both the old group (to
        # close the gap) and the new group (to place the coin).
        groups_to_resequence = []
        if category == 'coins':
            new_prop = updates.get('property_name', record['property_name'])
            new_date = updates.get('date_1', record['date_1'])
            old_group = _coin_group_for(record['property_name'], record['date_1'])
            new_group = _coin_group_for(new_prop, new_date)
            if old_group != new_group:
                if old_group: groups_to_resequence.append(old_group)
                if new_group: groups_to_resequence.append(new_group)

        set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
        db.execute(f"UPDATE {table} SET {set_clause} WHERE id = ?",
                   list(updates.values()) + [record_id])
        if groups_to_resequence:
            _renumber_coin_groups(db, groups_to_resequence)
        db.commit()
        flash("Record saved.", 'success')
        return redirect(url_for('detail_view', category=category, record_id=record_id))

    # GET
    hertz = None
    if category == 'watches' and record['beat']:
        hertz = watch_hertz(record['beat'])

    coin_age_val = None
    if category == 'coins' and record['date_1'] is not None:
        coin_age_val = coin_age(record['date_1'])

    property_topics = None
    if category == 'properties':
        property_topics = db.execute(
            'SELECT id, subject, body, image FROM topics '
            'WHERE property_id = ? ORDER BY created_at',
            [record_id]
        ).fetchall()

    # Lens detail opened from a camera detail: Back should return to
    # the camera rather than the lenses list.
    back_href = None
    if category == 'lenses':
        from_camera = request.args.get('from_camera')
        if from_camera:
            cam = db.execute(
                "SELECT id FROM cameras WHERE id = ?", [from_camera]
            ).fetchone()
            if cam:
                back_href = url_for('detail_view',
                                    category='cameras',
                                    record_id=cam['id'])

    # Preserve the list's search/filter when returning via Back, so
    # "search Gela → click coin → Back" lands on the same filtered list
    # scrolled to the same record.
    if back_href is None:
        back_q = (request.args.get('q') or '').strip() or None
        back_filter = (request.args.get('filter') or '').strip() or None
        back_at = (request.args.get('at') or '').strip() or None
        if back_q or back_filter or back_at:
            back_href = url_for('list_view', category=category,
                                q=back_q, filter=back_filter, at=back_at) \
                        + f'#item-{record_id}'

    # Camera detail: list every lens with the same mount and property,
    # so the user can see the full kit available at that location.
    # Lenses whose make matches the mount brand (e.g. Leica make on a
    # Leica M mount) sort to the top; other brands fall underneath.
    camera_compatible_lenses = None
    if category == 'cameras' and record['lens_mount'] and record['property']:
        mount_brand = record['lens_mount'].split()[0] if record['lens_mount'] else ''
        camera_compatible_lenses = db.execute(
            "SELECT id, make, model, aperture, length, image FROM lenses "
            "WHERE LOWER(TRIM(COALESCE(mount,''))) = LOWER(TRIM(?)) "
            "  AND LOWER(TRIM(COALESCE(property,''))) = LOWER(TRIM(?)) "
            "ORDER BY CASE WHEN LOWER(COALESCE(make,'')) LIKE LOWER(?) || '%' "
            "              THEN 0 ELSE 1 END, "
            "         LOWER(COALESCE(make,'')), "
            "         CAST(COALESCE(length,0) AS REAL)",
            [record['lens_mount'], record['property'], mount_brand],
        ).fetchall()

    # Lens detail: list every camera with the same mount and property,
    # so the user can see which bodies the lens pairs with at that
    # location. Same sort logic as compatible_lenses — same-make
    # bodies (e.g. a Canon body for a Canon lens) sort to the top.
    lens_compatible_cameras = None
    if category == 'lenses' and record['mount'] and record['property']:
        mount_brand = record['mount'].split()[0] if record['mount'] else ''
        lens_compatible_cameras = db.execute(
            "SELECT id, make, model, digital_film, film_size, megapixels, image "
            "FROM cameras "
            "WHERE LOWER(TRIM(COALESCE(lens_mount,''))) = LOWER(TRIM(?)) "
            "  AND LOWER(TRIM(COALESCE(property,''))) = LOWER(TRIM(?)) "
            "ORDER BY CASE WHEN LOWER(COALESCE(make,'')) LIKE LOWER(?) || '%' "
            "              THEN 0 ELSE 1 END, "
            "         LOWER(COALESCE(make,'')), "
            "         LOWER(COALESCE(model,''))",
            [record['mount'], record['property'], mount_brand],
        ).fetchall()

    # Property detail: row of pills linking to "<Items> at this
    # property" lists. Each pill is a category the user is allowed
    # to see AND that has a property field per CATEGORY_PROPERTY_FIELD.
    # Coins is excluded — they're navigated by era and the Coins map
    # already covers location. Watches is included so users with
    # watch access can drill into watches at this property.
    PROPERTY_PILL_EXCLUDE = {'coins'}
    property_pill_categories = []
    if category == 'properties' and record and record['name']:
        allowed = g.get('allowed_cats') or set(CATEGORIES.keys())
        prop_name = record['name']
        # Owners see every accessible category as a pill (green when
        # populated, red when zero — useful at-a-glance "what's
        # missing from this property"). Members only see pills with
        # at least one item they can actually access; the row-filter
        # is applied to the count so categories with all-restricted
        # rows drop off entirely instead of showing a misleading red.
        viewer = g.get('current_user') or {}
        is_member_view = viewer.get('role') != 'owner'
        # Match the alias group so a pill for "Carpinteria" counts items
        # still tagged with the legacy short form "Carp" — same lookup
        # the /<cat>?at=<name> filter uses, so the pill count never
        # disagrees with the list it links to.
        aliases = _property_alias_group(prop_name) or [prop_name.strip().lower()]
        for slug in CATEGORY_PROPERTY_FIELD:
            if slug not in allowed or slug in PROPERTY_PILL_EXCLUDE:
                continue
            # Tenant scope — when a deployment restricts what the owner
            # sees, broader-access viewers (e.g. cross-tenant admins)
            # still get only the tenant's slice of pills.
            if TENANT_CATEGORIES is not None and slug not in TENANT_CATEGORIES:
                continue
            prop_field = CATEGORY_PROPERTY_FIELD[slug]
            table = CATEGORIES[slug]['table']
            ph = ','.join(['?'] * len(aliases))
            wheres = [f"LOWER(TRIM(COALESCE({prop_field}, ''))) IN ({ph})"]
            params = list(aliases)
            _apply_row_filter_clauses(slug, wheres, params)
            try:
                cnt = db.execute(
                    f"SELECT COUNT(*) AS c FROM {table} "
                    f"WHERE {' AND '.join(wheres)}",
                    params
                ).fetchone()['c']
            except sqlite3.OperationalError:
                cnt = 0
            if is_member_view and cnt == 0:
                continue
            property_pill_categories.append(
                (slug, CATEGORIES[slug]['name'], cnt))

    service_overdue = False
    service_years = None
    if category == 'watches' and record['service_date']:
        try:
            from datetime import date as _date
            num_comp = len([c for c in (record['complications'] or '').split(',') if c.strip()])
            threshold = 10 if num_comp > 5 else 15
            svc = datetime.strptime(record['service_date'], '%Y-%m-%d').date()
            years = (_date.today() - svc).days / 365.25
            service_years = int(years)  # floor
            service_overdue = years > threshold
        except Exception:
            pass

    return render_template('detail.html',
                           category=category,
                           cat_info=cat_info,
                           record=record,
                           counts=counts,
                           current_category=category,
                           categories=CATEGORIES,
                           fields=visible_fields(category),
                           is_new=False,
                           prev_id=prev_id,
                           next_id=next_id,
                           hertz=hertz,
                           coin_age_val=coin_age_val,
                           property_topics=property_topics,
                           camera_compatible_lenses=camera_compatible_lenses,
                           property_pill_categories=property_pill_categories,
                           lens_compatible_cameras=lens_compatible_cameras,
                           back_href=back_href,
                           service_overdue=service_overdue,
                           service_years=service_years,
                           today_iso=None,
                           complications_options=COMPLICATIONS_OPTIONS,
                           vlists=current_vlists(category),
                           ta=build_typeahead(category))


@app.route('/<category>/<record_id>/save-field', methods=['POST'])
def save_field(category, record_id):
    """Auto-save a single field via JSON fetch."""
    if category not in CATEGORIES:
        return jsonify({'error': 'Unknown category'}), 400
    db = get_db()
    table = CATEGORIES[category]['table']

    data = request.get_json(force=True)
    field_name = data.get('field', '').strip()
    value = data.get('value', '')

    # Validate field exists in this category
    valid_fields = {f['name']: f for f in visible_fields(category)}
    if field_name not in valid_fields:
        return jsonify({'error': f'Unknown field: {field_name}'}), 400
    # Owner field is owner-only — members can't edit it via the API
    # even if they hit save_field directly (the UI hides the input).
    if field_name == 'owner' and (g.get('current_user') or {}).get('role') != 'owner':
        return jsonify({'error': 'Forbidden'}), 403

    field = valid_fields[field_name]
    if field.get('readonly') or field['type'] == 'file':
        return jsonify({'error': 'Field not auto-saveable'}), 400

    # Row-filter guard. Two checks:
    #   (1) The user must already be allowed to see the existing row.
    #   (2) If they're editing a filtered field itself, the new value
    #       must stay within their allowed set — otherwise they could
    #       lock themselves out of the record.
    existing = db.execute(
        f"SELECT * FROM {table} WHERE id = ?", [record_id]
    ).fetchone()
    if existing is None:
        return jsonify({'error': 'Record not found'}), 404
    if not _user_can_see_row(category, existing):
        return jsonify({'error': 'Forbidden'}), 403
    cat_filt = _row_filter_for_category(g.get('current_user'), category)
    if field_name in cat_filt and cat_filt[field_name]:
        if str(value).strip() not in cat_filt[field_name]:
            return jsonify({
                'error': f'Cannot set {field_name} outside your allowed values'
            }), 403

    if category == 'watches' and field_name in ('order_purchase_price', 'order_deposit'):
        if _update_watch_order_field(db, record_id, field_name, value):
            db.commit()
            return jsonify({'ok': True})

    # Strip currency/comma formatting for numeric fields. price keeps
    # its currency prefix (US$ / A$) verbatim — see _normalize_price_input.
    if field_name == 'price':
        value = _normalize_price_input(str(value))
    elif field['type'] == 'number' or field_name in ('beat', 'reserve', 'value'):
        value = str(value).replace('$', '').replace(',', '').strip()
        # Coin date fields render as "625 BC" / "1952" / "1952 AD" but
        # store as a signed integer year. Accept any of those forms.
        if category == 'coins' and field_name in ('date_1', 'date_2'):
            s = str(value).strip()
            m = re.match(r'^\s*(-?\d+)\s*(BC|BCE|AD|CE)?\s*$', s, re.IGNORECASE)
            if m:
                n = int(m.group(1))
                era = (m.group(2) or '').upper()
                if era in ('BC', 'BCE') and n > 0:
                    n = -n
                value = str(n)
        else:
            # Generic unit-suffix strip: "8.50 g", "26.5 mm", etc.
            m = re.match(r'^\s*(-?\d+(?:\.\d+)?)\s*[A-Za-z%°/]*\s*$', str(value))
            if m:
                value = m.group(1)

    value = normalize_field_value(table, field_name, str(value).strip() if value else '')

    # Grab the old value before writing so we can decide whether a
    # coin-group resequence is needed on property_name / date_1 changes.
    old_row = None
    if category == 'coins' and field_name in ('property_name', 'date_1'):
        old_row = db.execute(
            "SELECT property_name, date_1 FROM coins WHERE id = ?",
            [record_id]).fetchone()

    now = datetime.utcnow().isoformat()
    db.execute(f"UPDATE {table} SET {field_name} = ?, updated_at = ? WHERE id = ?",
               [value if value != '' else None, now, record_id])

    if category == 'watches' and field_name == 'status' \
            and str(value or '').strip().lower() == 'own':
        _graduate_watch_order_status(db, record_id)

    # date_1 / date_2 each have a parallel _text column the detail
    # template prefers for display. Without keeping them in sync, the
    # old text shadows the new integer on reload (the field appears
    # to "revert" even though the integer was saved correctly).
    if category == 'coins' and field_name in ('date_1', 'date_2'):
        try:
            n = int(value) if value not in ('', None) else None
        except (TypeError, ValueError):
            n = None
        text_col = f'{field_name}_text'
        text_val = (f'{abs(n)} BC' if n is not None and n < 0
                    else (str(n) if n is not None else None))
        db.execute(
            f"UPDATE {table} SET {text_col} = ? WHERE id = ?",
            [text_val, record_id])

    if old_row is not None:
        new_prop = value if field_name == 'property_name' else old_row['property_name']
        new_date = value if field_name == 'date_1' else old_row['date_1']
        old_group = _coin_group_for(old_row['property_name'], old_row['date_1'])
        new_group = _coin_group_for(new_prop, new_date)
        if old_group != new_group:
            touched = [g for g in (old_group, new_group) if g]
            if touched:
                _renumber_coin_groups(db, touched)

    db.commit()
    return jsonify({'ok': True})


@app.route('/<category>/<record_id>/delete', methods=['POST'])
def delete_record(category, record_id):
    if category not in CATEGORIES:
        abort(404)
    db = get_db()
    table = CATEGORIES[category]['table']
    # Row-filter guard: don't let a member delete a record whose
    # filtered field is outside their allowed set.
    existing = db.execute(
        f"SELECT * FROM {table} WHERE id = ?", [record_id]
    ).fetchone()
    if existing is None:
        abort(404)
    if not _user_can_see_row(category, existing):
        abort(404)
    # Capture the coin's group before deleting so we can close the gap.
    gap_group = None
    if category == 'coins':
        gap_group = _coin_group_for(existing['property_name'], existing['date_1'])
    # Tombstone every file this record owned — both fixed-slot files
    # and JSON-array document filenames — so the next incremental
    # syncDown can mirror the deletion locally. We read these from
    # `existing` (already fetched), not the DB, so they survive the
    # DELETE below.
    plan = EXPORT_LAYOUT.get(category, {})
    cols = {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
    for spec in plan.get('files', []):
        field, default_label, t_field = spec
        if field not in cols:
            continue
        try:
            fn = (existing[field] or '').strip()
        except (KeyError, IndexError):
            fn = ''
        if not fn:
            continue
        label = ''
        if t_field and t_field in cols:
            try:
                label = (existing[t_field] or '').strip()
            except (KeyError, IndexError):
                label = ''
        if not label:
            label = default_label or ''
        _record_tombstone(db, category, existing, label, fn)
    for json_col in DOC_SETS_BY_CATEGORY.get(category, {}).values():
        if json_col not in cols:
            continue
        try:
            raw = existing[json_col]
        except (KeyError, IndexError):
            raw = None
        if not raw:
            continue
        try:
            docs = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if not isinstance(docs, list):
            continue
        for d in docs:
            if not isinstance(d, dict):
                continue
            fn = (d.get('filename') or '').strip()
            if fn:
                _record_tombstone(db, category, existing,
                                  (d.get('title') or '').strip(), fn)
    db.execute(f"DELETE FROM {table} WHERE id = ?", [record_id])
    if gap_group:
        _renumber_coin_groups(db, [gap_group])
    db.commit()
    flash("Record deleted.", 'info')
    return redirect(url_for('list_view', category=category))


@app.route('/topics/new', methods=['GET', 'POST'])
def topic_new():
    db = get_db()
    property_id = request.values.get('property_id') or ''
    prop = db.execute(
        'SELECT * FROM properties WHERE id = ?', [property_id]
    ).fetchone() if property_id else None
    if prop is None:
        abort(404)
    if not _user_can_see_row('properties', prop):
        abort(403)
    if request.method == 'POST':
        tid = str(uuid.uuid4())
        subject = (request.form.get('subject') or '').strip() or None
        body = (request.form.get('body') or '').strip() or None
        image = None
        f = request.files.get('image')
        if f and f.filename:
            image = save_upload(f)
        db.execute(
            'INSERT INTO topics (id, property_id, subject, body, image) '
            'VALUES (?, ?, ?, ?, ?)',
            [tid, prop['id'], subject, body, image],
        )
        db.commit()
        # Autosave-from-typing flow: client expects JSON so it can flip
        # the form into save_field-style updates without a redirect.
        if request.headers.get('Accept', '').startswith('application/json') \
                or request.headers.get('X-Requested-With') == 'fetch':
            return jsonify({'ok': True, 'id': tid,
                            'detail_url': url_for('topic_detail', topic_id=tid)})
        return redirect(url_for('topic_detail', topic_id=tid))
    return render_template(
        'topic_detail.html', topic=None, property=prop, is_new=True,
        categories=CATEGORIES, counts=get_counts(), current_category='properties',
    )


@app.route('/topics/<topic_id>', methods=['GET', 'POST'])
def topic_detail(topic_id):
    db = get_db()
    topic = db.execute('SELECT * FROM topics WHERE id = ?', [topic_id]).fetchone()
    if topic is None:
        abort(404)
    prop = db.execute(
        'SELECT * FROM properties WHERE id = ?', [topic['property_id']]
    ).fetchone()
    if prop is None or not _user_can_see_row('properties', prop):
        abort(403)
    if request.method == 'POST':
        subject = (request.form.get('subject') or '').strip() or None
        body = (request.form.get('body') or '').strip() or None
        updates = {'subject': subject, 'body': body,
                   'updated_at': datetime.utcnow().isoformat()}
        f = request.files.get('image')
        if f and f.filename:
            stored = save_upload(f)
            if stored:
                updates['image'] = stored
        set_clause = ', '.join(f'{k} = ?' for k in updates)
        db.execute(f'UPDATE topics SET {set_clause} WHERE id = ?',
                   list(updates.values()) + [topic_id])
        db.commit()
        # Autosave-from-typing flow: skip the flash + redirect so the
        # client can keep typing without a full page navigation.
        if request.headers.get('Accept', '').startswith('application/json') \
                or request.headers.get('X-Requested-With') == 'fetch':
            return jsonify({'ok': True, 'id': topic_id})
        flash('Topic saved.', 'success')
        return redirect(url_for('topic_detail', topic_id=topic_id))
    return render_template(
        'topic_detail.html', topic=topic, property=prop, is_new=False,
        categories=CATEGORIES, counts=get_counts(), current_category='properties',
    )


@app.route('/topics/<topic_id>/delete', methods=['POST'])
def topic_delete(topic_id):
    db = get_db()
    row = db.execute(
        'SELECT property_id FROM topics WHERE id = ?', [topic_id]
    ).fetchone()
    prop = None
    if row and row['property_id']:
        prop = db.execute(
            'SELECT * FROM properties WHERE id = ?', [row['property_id']]
        ).fetchone()
    if prop is None or not _user_can_see_row('properties', prop):
        abort(403)
    db.execute('DELETE FROM topics WHERE id = ?', [topic_id])
    db.commit()
    # AJAX path (per-row × button on the property detail) — return
    # JSON so the row can be removed in place without a navigation.
    if request.headers.get('Accept', '').startswith('application/json') \
            or request.headers.get('X-Requested-With') == 'fetch':
        return jsonify({'ok': True, 'id': topic_id})
    flash('Topic deleted.', 'info')
    if row and row['property_id']:
        return redirect(url_for('detail_view', category='properties',
                                record_id=row['property_id']))
    return redirect(url_for('list_view', category='properties'))


@app.route('/topics/<topic_id>/upload-image', methods=['POST'])
def topic_upload_image(topic_id):
    db = get_db()
    topic = db.execute('SELECT * FROM topics WHERE id = ?', [topic_id]).fetchone()
    if topic is None:
        return jsonify({'error': 'Unknown topic'}), 404
    prop = db.execute(
        'SELECT * FROM properties WHERE id = ?', [topic['property_id']]
    ).fetchone()
    if prop is None or not _user_can_see_row('properties', prop):
        return jsonify({'error': 'Forbidden'}), 403
    f = request.files.get('image')
    if not f or not f.filename or not allowed_file(f.filename):
        return jsonify({'error': 'No file'}), 400
    stored = save_upload(f)
    if not stored:
        return jsonify({'error': 'Upload failed'}), 500
    db.execute(
        'UPDATE topics SET image = ?, updated_at = datetime(\'now\') WHERE id = ?',
        [stored, topic_id],
    )
    db.commit()
    return jsonify({'url': url_for('uploaded_file', filename=stored)})


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    if not _upload_visible_to_current_user(filename):
        abort(404)
    return send_from_directory(UPLOAD_FOLDER, filename)


_FILE_THUMB_DIR = os.path.join(UPLOAD_FOLDER, '.thumbs')


@app.route('/file-thumb/<filename>')
def file_thumb(filename):
    """Render a small preview for an uploaded document.

    PDFs: first page rendered via pypdfium2.
    HEIC/HEIF: rendered via pillow-heif (browsers don't display them).
    Cached as JPEG under .thumbs/. Failures log a reason and 404 so the
    template can fall back to its existing 📄 icon.

    `?debug=1` returns the failure reason as plain text instead of 404
    so production issues can be diagnosed without shell access.
    """
    debug = request.args.get('debug') == '1'
    if not _upload_visible_to_current_user(filename):
        abort(404)
    def _bail(msg, code=404):
        app.logger.warning(f'file-thumb {filename}: {msg}')
        if debug:
            return Response(msg, status=200, mimetype='text/plain')
        abort(code)

    src = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(src):
        return _bail(f'source file missing at {src}')
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ('.pdf', '.heic', '.heif'):
        return _bail(f'unsupported extension: {ext!r}')

    try:
        os.makedirs(_FILE_THUMB_DIR, exist_ok=True)
    except OSError as e:
        return _bail(f'cannot create thumb dir: {e}', code=500)

    thumb_path = os.path.join(_FILE_THUMB_DIR, filename + '.jpg')
    if not os.path.exists(thumb_path) or \
            os.path.getmtime(thumb_path) < os.path.getmtime(src):
        try:
            from PIL import Image
            if ext == '.pdf':
                try:
                    import pypdfium2 as pdfium
                except ImportError as e:
                    return _bail(f'pypdfium2 not installed: {e}', code=500)
                doc = pdfium.PdfDocument(src)
                try:
                    page = doc[0]
                    bitmap = page.render(scale=2.0)
                    pil = bitmap.to_pil()
                finally:
                    doc.close()
            else:  # .heic / .heif
                try:
                    import pillow_heif
                    pillow_heif.register_heif_opener()
                except ImportError as e:
                    return _bail(f'pillow-heif not installed: {e}', code=500)
                pil = Image.open(src)
            pil.thumbnail((320, 320))
            if pil.mode not in ('RGB', 'L'):
                pil = pil.convert('RGB')
            pil.save(thumb_path, format='JPEG', quality=82)
        except Exception as e:
            import traceback
            app.logger.warning('file-thumb render failed:\n' + traceback.format_exc())
            return _bail(f'render failed: {e.__class__.__name__}: {e}', code=500)
    return send_from_directory(_FILE_THUMB_DIR, filename + '.jpg')


@app.route('/watches/<record_id>/value', methods=['POST'])
def watch_fetch_value(record_id):
    """Search the web for current market value of this watch and store it."""
    db = get_db()
    watch = db.execute("SELECT * FROM watches WHERE id = ?", (record_id,)).fetchone()
    if not watch:
        return jsonify({'error': 'Watch not found'}), 404
    try:
        data = fetch_watch_valuation(watch)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 503
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(tb, flush=True)  # surface in Railway logs
        detail = str(e) or e.__class__.__name__
        return jsonify({'error': f'Valuation failed: {detail}'}), 500
    now = datetime.utcnow().isoformat()
    # If the user has already entered a value, preserve it — only refresh
    # the supporting research (results + timestamp). The response still
    # carries the freshly-fetched number so the UI can display it inside
    # the Results panel, but the stored Value field is left alone.
    user_value = watch['value']
    user_set = user_value is not None and (not isinstance(user_value, (int, float)) or user_value > 0)
    if user_set:
        db.execute(
            "UPDATE watches SET results = ?, value_searched_at = ?, "
            "updated_at = ? WHERE id = ?",
            (data['results'], now, now, record_id),
        )
        db.commit()
        return jsonify({**data, 'value': user_value, 'value_overridden': True, 'searched_at': now})
    db.execute(
        "UPDATE watches SET value = ?, results = ?, value_searched_at = ?, "
        "updated_at = ? WHERE id = ?",
        (data['value'], data['results'], now, now, record_id),
    )
    db.commit()
    return jsonify({**data, 'value_overridden': False, 'searched_at': now})


# Fields the lookup is allowed to auto-fill. Serial numbers, purchase
# details, ownership, and photos stay off this list on purpose.
WATCH_LOOKUP_FILLABLE = (
    'metal', 'case_diameter', 'dial_color', 'year', 'edition', 'calibre',
    'movement_type', 'movement_origin', 'movement_jewels', 'escapement',
    'balance_wheel', 'beat', 'reserve', 'complications', 'clasp_type',
    'lug_mm', 'strap_material', 'notes', 'calibre_notes',
)

# Fields we'll only populate when blank — never overwrite the existing
# value. Strap material is set from the physical strap on the watch —
# a web guess ("Leather") is almost always less precise than what's
# already there ("Croc"). Year used to be in this set, but the lookup
# now derives year from case/movement serial numbers when possible
# (which is more accurate than the reference's release year), so
# overwrites are allowed.
WATCH_LOOKUP_BLANK_ONLY = {'strap_material', 'clasp_type', 'dial_color', 'metal'}


def _numeric_field(field):
    """True for watch fields whose values are numbers and should be
    compared numerically rather than as strings (e.g. 41.0 vs '41')."""
    return field in ('case_diameter', 'lug_mm', 'reserve', 'beat',
                     'movement_jewels', 'year', 'edition')


def _values_equivalent(field, current, new):
    """Are these two values effectively equal for change-tracking?

    For numeric fields, compare as floats so the stored REAL (e.g. 41.0)
    matches a stringified int ('41') from the lookup. For everything else
    fall back to stripped string equality.
    """
    if _numeric_field(field):
        try:
            return float(current) == float(new)
        except (TypeError, ValueError):
            pass
    return str(current or '').strip() == str(new or '').strip()

# Fields that should append to existing content rather than replace it.
# For notes the lookup writes a quality blurb about the reference;
# merging it onto the user's own notes (separated by a blank line)
# preserves their wording while still surfacing the web research.
WATCH_LOOKUP_APPEND = {'notes'}


def _text_already_present(needle, haystack):
    """True if `needle` is effectively contained in `haystack`, ignoring
    cosmetic differences the model often introduces between runs:
    smart vs straight quotes, em/en dashes, non-breaking spaces, case,
    and whitespace runs. Without this, re-running the lookup on a
    record that already has the model's blurb appends a near-duplicate.
    """
    def _norm(s):
        s = (s or '').lower()
        # Unify quote / dash families.
        s = (s.replace('’', "'").replace('‘', "'")
              .replace('“', '"').replace('”', '"')
              .replace('–', '-').replace('—', '-')
              .replace(' ', ' '))
        # Collapse all whitespace.
        return re.sub(r'\s+', ' ', s).strip()
    n = _norm(needle)
    return bool(n) and n in _norm(haystack)


@app.route('/watches/<record_id>/lookup', methods=['POST'])
def watch_lookup_specs(record_id):
    """Use web search to fill in blank spec fields on a watch."""
    db = get_db()
    watch = db.execute("SELECT * FROM watches WHERE id = ?", (record_id,)).fetchone()
    if not watch:
        return jsonify({'error': 'Watch not found'}), 404
    try:
        suggestions = fetch_watch_specs(watch)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 503
    except Exception as e:
        import traceback
        print(traceback.format_exc(), flush=True)
        return jsonify({'error': f'Lookup failed: {e or e.__class__.__name__}'}), 500

    def _clasp_equivalent(a, b):
        """Two clasp values are equivalent if they normalize (via the
        shared FIELD_ALIASES map) to the same canonical form.
        Handles 'Tang'/'Tang Buckle'/'Pin Buckle'/'Ardillon' as one
        group and 'Fold Over'/'Deployant'/'Folding Clasp' as another.
        """
        ca = normalize_field_value('watches', 'clasp_type', (a or '').strip())
        cb = normalize_field_value('watches', 'clasp_type', (b or '').strip())
        if not ca or not cb:
            return False
        # Trailing " buckle"/" clasp" suffixes are stripped so e.g.
        # "Butterfly" and "Butterfly Clasp" are still equal even though
        # neither is in the alias map.
        def trim(s):
            s = s.strip().lower()
            for suf in (' buckle', ' clasp'):
                if s.endswith(suf):
                    s = s[: -len(suf)]
            return s.strip()
        return trim(ca) == trim(cb)

    # Fill blanks AND overwrite existing values whenever the web-sourced
    # suggestion differs. Complications is handled specially: we merge
    # (union) rather than replace, so user-checked items aren't lost.
    filled = {}            # blank → value
    overwritten = {}       # existing → new value (was wrong/different)
    for f in WATCH_LOOKUP_FILLABLE:
        if f not in suggestions or suggestions[f] is None:
            continue
        val = suggestions[f]
        # A watch can't have been bought before it was made — if the
        # lookup's year is later than the purchase date, clamp it down
        # to the purchase year (the receipt is hard evidence, the web
        # isn't). The watches column is named `date` (UI label
        # "Purchase Date").
        if f == 'year':
            pd = watch['date']
            basis = str(suggestions.get('year_basis') or '').strip()
            record_evidence = ' '.join(str(watch[x] or '') for x in (
                'case_num', 'movement_num', 'description', 'notes'
            ))
            has_piece_identifier = bool(re.search(
                r'\b(case|movement|serial|papers?|archive|extract|warranty|certificate)\b|\d{4,}',
                record_evidence,
                flags=re.IGNORECASE,
            ))
            basis_is_piece_specific = bool(re.search(
                r'\b(case|movement|serial|papers?|archive|extract|warranty|certificate)\b',
                basis,
                flags=re.IGNORECASE,
            ))
            # The model often finds the year a reference was introduced.
            # That is not the production year of this individual watch.
            # Only accept year when it is anchored to case/movement/papers
            # style evidence for the specific piece.
            if not (has_piece_identifier and basis_is_piece_specific):
                continue
            if pd:
                try:
                    purchase_year = int(str(pd)[:4])
                    sugg_year = int(float(val))
                    if purchase_year < sugg_year:
                        continue
                except (TypeError, ValueError):
                    pass
        # Beat sanity check. Mechanical movements (Manual/Automatic) run at
        # well-known VPH rates and sources often quote Hz instead — so for
        # those we auto-convert small numbers and snap to the canonical set.
        # Quartz and tuning-fork movements (e.g. Accutron at 360 Hz) have
        # non-standard rates that should be stored verbatim.
        if f == 'beat':
            try:
                n = float(val)
            except (TypeError, ValueError):
                continue
            if n <= 0:
                continue
            mech_allowed = {18000, 19800, 21600, 25200, 28800, 36000, 72000}
            # Determine whether this is a mechanical movement (from the new
            # suggestion if provided, otherwise from the existing record).
            mt_sugg = suggestions.get('movement_type')
            mt = (mt_sugg if isinstance(mt_sugg, str) and mt_sugg else (watch['movement_type'] or '')).strip()
            is_mechanical = mt in ('Manual', 'Automatic')
            if is_mechanical:
                if 0 < n < 100:  # source gave Hz
                    n = n * 7200
                val = int(round(n))
                if val not in mech_allowed:
                    continue
            else:
                # Quartz / tuning fork / other — accept any positive integer
                # up to a reasonable ceiling. 32768 is a common quartz crystal.
                val = int(round(n))
                if val < 1 or val > 200_000:
                    continue
        # Enforce strict enum for movement_origin: only In-House / Ébauche / Modified.
        if f == 'movement_origin':
            if not isinstance(val, str):
                continue
            val_norm = val.strip()
            allowed = VALUE_LISTS['movement_origin']
            match = next((a for a in allowed if a.lower() == val_norm.lower()), None)
            if not match:
                continue  # silently drop off-menu values like "Ebauche base", "Swiss"
            val = match
        if f == 'complications':
            if isinstance(val, list):
                new_set = {str(v).strip() for v in val if str(v).strip()}
            else:
                new_set = {c.strip() for c in str(val).split(',') if c.strip()}
            current_set = {c.strip() for c in (watch['complications'] or '').split(',') if c.strip()}
            merged = current_set | new_set
            if merged != current_set:
                val = ','.join(sorted(merged, key=lambda x: COMPLICATIONS_OPTIONS.index(x)
                                      if x in COMPLICATIONS_OPTIONS else 999))
                if current_set:
                    overwritten[f] = {'current': watch['complications'], 'new': val}
                else:
                    filled[f] = val
                continue
            else:
                continue
        if isinstance(val, str):
            val = val.strip()
            if not val:
                continue
        current = watch[f]
        current_is_blank = current is None or (isinstance(current, str) and not current.strip())
        if current_is_blank:
            filled[f] = val
            continue
        # Fields in WATCH_LOOKUP_BLANK_ONLY are never overwritten.
        if f in WATCH_LOOKUP_BLANK_ONLY:
            continue
        # For append fields, don't replace — concatenate new text after
        # existing text (separated by a blank line). Skip if the existing
        # content already contains the suggestion verbatim.
        if f in WATCH_LOOKUP_APPEND:
            cur_text = str(current).rstrip()
            new_text = str(val).strip()
            if not new_text or _text_already_present(new_text, cur_text):
                continue
            merged = cur_text + '\n\n' + new_text
            overwritten[f] = {'current': current, 'new': merged}
            continue
        # For clasp_type, don't mark changes that are just verbose variants.
        if f == 'clasp_type' and _clasp_equivalent(current, val):
            continue
        if _values_equivalent(f, current, val):
            continue
        overwritten[f] = {'current': current, 'new': val}

    # Combined update map — apply both blank-fills and overwrites.
    updates = {}
    for k, v in filled.items():
        updates[k] = v
    for k, info in overwritten.items():
        updates[k] = info['new']

    # Stamp that the lookup ran successfully — used to mark the button
    # green on subsequent visits to this watch. We stamp here (after the
    # API succeeded) rather than in apply-lookup so it still counts when
    # the user cancels the review modal.
    now = datetime.utcnow().isoformat()
    db.execute(
        "UPDATE watches SET specs_searched_at = ? WHERE id = ?",
        (now, record_id),
    )
    db.commit()

    # Return the proposed changes WITHOUT applying. The client presents
    # a checkbox review; accepted items are POSTed to /apply-lookup.
    return jsonify({
        'filled': filled,
        'overwritten': overwritten,
        'sources': suggestions.get('sources', ''),
        'specs_searched_at': now,
    })


# Fields that describe the calibre itself — a property of the
# movement, not of the specific watch reference. When a Lookup
# updates these on one watch, propagate the same values to every
# other watch sharing the same calibre so the movement spec stays
# consistent across the collection. `calibre` itself is included so
# that when the lookup normalises a short form (e.g. "1304") to its
# complete canonical form (e.g. "F.P. Journe Calibre 1304"), the
# expanded value also lands on every sibling — keeping the whole
# collection in lockstep on naming.
MOVEMENT_PROPERTY_FIELDS = frozenset([
    'calibre', 'movement_jewels', 'movement_origin', 'movement_type',
    'escapement', 'balance_wheel', 'beat', 'reserve',
    'calibre_notes',
])


@app.route('/watches/<record_id>/apply-lookup', methods=['POST'])
def watch_apply_lookup(record_id):
    """Apply a user-selected subset of lookup suggestions to a watch.

    Body: ``{"updates": {"<field>": <value>, ...}}``
    Only fields listed in ``WATCH_LOOKUP_FILLABLE`` are accepted.

    Movement-property fields (jewels, escapement, balance wheel, beat,
    reserve, calibre notes, etc. — see MOVEMENT_PROPERTY_FIELDS) get
    propagated to every other watch with the same calibre, so the
    movement spec stays consistent across siblings on the same calibre.
    """
    db = get_db()
    watch = db.execute(
        "SELECT id, calibre FROM watches WHERE id = ?", (record_id,)
    ).fetchone()
    if not watch:
        return jsonify({'error': 'Watch not found'}), 404
    data = request.get_json(force=True) or {}
    raw_updates = data.get('updates') or {}
    if not isinstance(raw_updates, dict):
        return jsonify({'error': 'updates must be an object'}), 400
    updates = {}
    for k, v in raw_updates.items():
        if k not in WATCH_LOOKUP_FILLABLE:
            continue
        if isinstance(v, str):
            v = normalize_field_value('watches', k, v)
        updates[k] = v
    if not updates:
        return jsonify({'updated': 0, 'fields': [],
                        'propagated_to': 0, 'propagated_fields': []})
    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    now = datetime.utcnow().isoformat()
    params = list(updates.values()) + [now, record_id]
    db.execute(
        f"UPDATE watches SET {set_clause}, updated_at = ? WHERE id = ?",
        params,
    )

    # Propagate movement-property fields to siblings with the same
    # calibre. Match siblings by the OLD calibre — the value they
    # still share with this watch before the update lands. If the
    # lookup is normalising the calibre (short "1304" → complete
    # "F.P. Journe Calibre 1304"), the new value gets pushed onto
    # siblings as part of the same propagation, so all watches that
    # were on the old short form end up on the canonical form
    # together.
    propagated_to = 0
    propagated_fields = []
    old_calibre = (watch['calibre'] or '').strip()
    movement_updates = {
        k: v for k, v in updates.items() if k in MOVEMENT_PROPERTY_FIELDS
    }
    if old_calibre and movement_updates:
        sib_set = ', '.join(f'{k} = ?' for k in movement_updates.keys())
        sib_params = (list(movement_updates.values())
                      + [now, old_calibre, record_id])
        cur = db.execute(
            f"UPDATE watches SET {sib_set}, updated_at = ? "
            f"WHERE TRIM(COALESCE(calibre,'')) = ? AND id != ?",
            sib_params,
        )
        propagated_to = cur.rowcount or 0
        propagated_fields = list(movement_updates.keys())

    db.commit()
    return jsonify({
        'updated': len(updates),
        'fields': list(updates.keys()),
        'propagated_to': propagated_to,
        'propagated_fields': propagated_fields,
    })


# ---------------------------------------------------------------------------
# Art lookup: simple biography + per-piece notes via Claude web search.
# ---------------------------------------------------------------------------

def fetch_art_lookup(art):
    """Return {artist_notes, object_notes, sources} for an art record.

    Single small web-search prompt — short artist biography plus a
    couple of sentences about the specific piece if any source has
    something to say. Either may come back as None.
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY not configured')
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed.")

    artist = (art['artist'] or '').strip()
    title  = (art['title'] or '').strip()
    year   = art['year']
    medium = (art['medium'] or '').strip()
    vendor = (art['vendor'] or '').strip()
    if not artist:
        raise RuntimeError('Need an artist name to look up.')

    ident_bits = [artist]
    if title:  ident_bits.append(f'"{title}"')
    if year:   ident_bits.append(str(year))
    if medium: ident_bits.append(f'({medium})')
    ident = ' '.join(ident_bits)

    # Galleries often publish their own bios + edition/exhibition info
    # for pieces they sold — give the model a nudge to check the
    # vendor's site too.
    vendor_hint = (
        f'\n- The acquiring gallery / vendor is "{vendor}"; their site '
        f'often has artist bios and per-piece notes worth checking.'
        if vendor else ''
    )

    # We always ask for BOTH fields with the same prompt, regardless of
    # whether the bio is on file. The previous "have_bio → narrow prompt"
    # branch made the model return object_notes=null much more often:
    # presumably the broader bio search gives the model the context it
    # needs to recognize and describe the specific piece. When bio is
    # already on file, the route ignores the returned artist_notes (the
    # per-field loop in art_lookup_bio handles the "don't overwrite"
    # rule), so the only cost is one extra short search per call.
    prompt = f"""You are filling in two short notes fields about a piece of art.

Piece: {ident}{vendor_hint}

Use up to 3 web searches. Return:
- artist_notes: 2-4 sentence biography of {artist} — birth/death years, nationality, primary medium, what they're known for. Plain prose, no headings, under 500 chars.
- object_notes: 2-3 sentences about THIS specific work or its series — period, technique, exhibition history, edition info, or any notable context. Fall back to the series / edition / period if the piece itself is poorly documented; only return null if absolutely nothing surfaces.

Reply with ONLY a JSON object, no prose, no code fences:
{{
  "artist_notes": "...",
  "object_notes": "..." or null,
  "sources": "one-line note of which sources hit"
}}"""

    client = anthropic.Anthropic(api_key=api_key, timeout=240.0)
    import time as _time
    last_err = None
    transient_errs = (
        anthropic.RateLimitError,
        anthropic.APIConnectionError,
        anthropic.APITimeoutError,
        anthropic.InternalServerError,
    )
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model='claude-sonnet-4-5',
                max_tokens=1024,
                tools=[{
                    'type': 'web_search_20250305',
                    'name': 'web_search',
                    # Same budget either way — when bio is on file the
                    # piece search needs every search to land something
                    # useful before falling back to null.
                    'max_uses': 3,
                }],
                messages=[{'role': 'user', 'content': prompt}],
            )
            break
        except transient_errs as e:
            last_err = e
            wait = 10 * (attempt + 1)
            try:
                ra = e.response.headers.get('retry-after') if getattr(e, 'response', None) else None
                if ra:
                    wait = max(wait, int(float(ra)))
            except Exception:
                pass
            _time.sleep(wait)
    else:
        raise RuntimeError(f'Lookup failed after retries: {last_err}')

    text = ''
    for block in resp.content:
        if getattr(block, 'type', None) == 'text':
            text += block.text
    text = text.strip()
    m = re.search(r'\{.*\}', text, re.DOTALL)
    if not m:
        raise RuntimeError(f'Could not parse JSON from model output: {text[:200]}')
    data = json.loads(m.group(0))

    # Claude's web_search tool wraps quoted spans in <cite index="...">…</cite>
    # markers — strip them so the raw tags don't end up in the saved
    # notes fields.
    def _scrub(s):
        if not isinstance(s, str):
            return s
        return re.sub(r'</?cite\b[^>]*>', '', s, flags=re.IGNORECASE).strip()
    for k in ('artist_notes', 'object_notes', 'sources'):
        if k in data:
            data[k] = _scrub(data[k]) if data[k] else data[k]
    return data


@app.route('/art/<record_id>/lookup', methods=['POST'])
def art_lookup_bio(record_id):
    db = get_db()
    art = db.execute("SELECT * FROM art WHERE id = ?", (record_id,)).fetchone()
    if not art:
        return jsonify({'error': 'Art not found'}), 404
    try:
        suggestions = fetch_art_lookup(art)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 503
    except Exception as e:
        import traceback
        print(traceback.format_exc(), flush=True)
        return jsonify({'error': f'Lookup failed: {e or e.__class__.__name__}'}), 500

    # Map response keys to the art table's columns. The artist
    # biography goes into the existing `notes` column (relabeled
    # "Artist Notes" in the UI); per-piece info into `object_notes`.
    pairs = (('notes', suggestions.get('artist_notes')),
             ('object_notes', suggestions.get('object_notes')))
    filled = {}
    overwritten = {}
    for field, val in pairs:
        if not val or not isinstance(val, str):
            continue
        val = val.strip()
        if not val:
            continue
        current = art[field]
        current_blank = current is None or (isinstance(current, str) and not current.strip())
        if current_blank:
            filled[field] = val
            continue
        # Artist Notes ('notes') is the propagated artist bio — never
        # prompt the user to overwrite an existing one; just discard
        # the new draft so a fill of object_notes can apply silently.
        if field == 'notes':
            continue
        if _text_already_present(val, str(current)):
            continue
        overwritten[field] = {'current': current, 'new': val}

    now = datetime.utcnow().isoformat()
    db.execute("UPDATE art SET art_searched_at = ? WHERE id = ?",
               (now, record_id))
    db.commit()

    return jsonify({
        'filled': filled,
        'overwritten': overwritten,
        'sources': suggestions.get('sources', ''),
        'art_searched_at': now,
    })


@app.route('/art/<record_id>/apply-lookup', methods=['POST'])
def art_apply_lookup(record_id):
    db = get_db()
    art = db.execute("SELECT id, artist FROM art WHERE id = ?",
                     (record_id,)).fetchone()
    if not art:
        return jsonify({'error': 'Art not found'}), 404
    data = request.get_json(force=True) or {}
    raw = data.get('updates') or {}
    if not isinstance(raw, dict):
        return jsonify({'error': 'updates must be an object'}), 400
    updates = {k: v for k, v in raw.items()
               if k in ('notes', 'object_notes') and isinstance(v, str)}
    if not updates:
        return jsonify({'updated': 0, 'fields': []})
    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    now = datetime.utcnow().isoformat()
    params = list(updates.values()) + [now, record_id]
    db.execute(f"UPDATE art SET {set_clause}, updated_at = ? WHERE id = ?",
               params)

    # Artist biography is not piece-specific — fan it out to every
    # other work by the same artist whose Artist Notes are still
    # blank, so the user only has to look an artist up once. Pieces
    # that already have manually-written notes are left alone.
    propagated = 0
    if 'notes' in updates and art['artist']:
        new_bio = updates['notes']
        artist_name = (art['artist'] or '').strip()
        if artist_name:
            cur = db.execute(
                "UPDATE art SET notes = ?, updated_at = ? "
                "WHERE LOWER(TRIM(COALESCE(artist,''))) = LOWER(TRIM(?)) "
                "  AND id != ? "
                "  AND (notes IS NULL OR TRIM(notes) = '')",
                (new_bio, now, artist_name, record_id),
            )
            propagated = cur.rowcount or 0
    db.commit()
    return jsonify({
        'updated': len(updates),
        'fields': list(updates.keys()),
        'propagated': propagated,
    })


@app.route('/coins/map')
def coins_map_view():
    """Distribution map of ancient coins across the Mediterranean.

    Honours the same filter pills the list view uses: ?filter=ca_ancient or
    ?filter=ny_ancient apply the matching WHERE clause. No filter falls
    back to the default ancient threshold (date_1 < 500).
    """
    db = get_db()
    coin_filter = (request.args.get('filter') or '').strip() or None
    base_cols = ("id, coin_id, region, mint, authority, denomination, "
                 "date_1, date_1_text, date_2_text, image_1, property_name")
    filters = CATEGORY_FILTERS.get('coins', {})
    if coin_filter and coin_filter in filters:
        where, params = filters[coin_filter]
        label = 'CA Ancient' if coin_filter == 'ca_ancient' else \
                'NY Ancient' if coin_filter == 'ny_ancient' else coin_filter
    else:
        where = "date_1 IS NOT NULL AND CAST(date_1 AS INTEGER) < 500"
        params = []
        label = 'ancient (date < 500)'
    sql = (f"SELECT {base_cols} FROM coins WHERE {where} ORDER BY date_1")
    rows = db.execute(sql, params).fetchall()
    coins = [dict(r) for r in rows]
    return render_template('coins_map.html', coins=coins,
                           filter_label=label,
                           coin_filter=coin_filter,
                           current_category='coins',
                           cat_info=CATEGORIES['coins'])


def _merge_recording_genres(existing_genre, existing_genre_2,
                            new_genre, new_genre_2):
    """Merge lookup-derived genre + sub-genre into the DB values without
    overwriting. Returns (final_genre, final_genre_2).

    Rules:
      - Existing genre wins if non-empty. If it's blank, fall back to
        new_genre so the dropdown gets populated.
      - genre_2 accumulates: anything from the lookup that isn't
        already represented in (final_genre, existing_genre_2)
        (case-insensitive, comma-tokenised) gets appended to genre_2.
      - Token comparison is case-insensitive and trims whitespace, so
        "Pop/Rock" and "pop/rock" are treated as the same token.
    """
    final_genre = existing_genre or (new_genre or '')

    def _tokens(s):
        return [t.strip() for t in (s or '').split(',') if t.strip()]

    seen = set()
    if final_genre:
        seen.add(final_genre.lower())
    existing_tokens = _tokens(existing_genre_2)
    for t in existing_tokens:
        seen.add(t.lower())

    additions = []
    for cand in (new_genre, new_genre_2):
        cand = (cand or '').strip()
        if not cand:
            continue
        if cand.lower() in seen:
            continue
        seen.add(cand.lower())
        additions.append(cand)

    if not additions:
        return final_genre, existing_genre_2

    final_genre_2 = ', '.join(existing_tokens + additions)
    return final_genre, final_genre_2


@app.route('/recordings/<record_id>/fetch-notes', methods=['POST'])
def recording_fetch_notes(record_id):
    """Generate a brief review/historical note for a recording via
    Claude + web_search. Returns {notes: str} on success. Does NOT
    write to the DB — the client appends to the existing notes
    textarea and the per-field autosave persists on blur."""
    db = get_db()
    rec = db.execute(
        "SELECT * FROM recordings WHERE id = ?", (record_id,)
    ).fetchone()
    if not rec:
        return jsonify({'error': 'Recording not found'}), 404
    try:
        data = fetch_recording_notes(rec)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 503
    except Exception as e:
        import traceback
        print(traceback.format_exc(), flush=True)
        detail = str(e) or e.__class__.__name__
        return jsonify({'error': f'Notes lookup failed: {detail}'}), 500

    # Append new URLs to the persistent notes_urls column (deduped),
    # so the pill row survives a reload without re-extracting from
    # textarea content.
    new_urls = data.get('urls') or []
    try:
        existing_csv = (rec['notes_urls'] or '').strip()
    except (IndexError, KeyError):
        existing_csv = ''
    merged = [u for u in (s.strip() for s in existing_csv.split(',')) if u]
    seen = set(merged)
    for u in new_urls:
        if u not in seen:
            merged.append(u)
            seen.add(u)
    if new_urls:
        try:
            db.execute(
                "UPDATE recordings SET notes_urls = ?, updated_at = ? WHERE id = ?",
                [','.join(merged), datetime.utcnow().isoformat(), record_id],
            )
            db.commit()
        except sqlite3.OperationalError:
            pass

    # Persist players + tracks if the model returned them and the
    # column is currently empty. fetch_recording_notes already gates
    # the model request on emptiness, so this is just the write side
    # of the same condition.
    #
    # Genre + genre_2 are merged (never overwritten):
    #   - genre stays whatever's in the DB if non-empty. A blank genre
    #     is filled with the lookup's primary value, which then counts
    #     as "already covered" for the genre_2 merge below.
    #   - any lookup value (primary or sub-genre) that isn't already
    #     present in genre OR genre_2 (case-insensitive token match)
    #     gets appended to genre_2 as a comma-separated tail. Re-runs
    #     are idempotent because everything that landed last time is
    #     in the existing tokens.
    new_players = data.get('players') or ''
    new_tracks = data.get('tracks') or ''
    new_genre = data.get('genre') or ''
    new_genre_2 = data.get('genre_2') or ''
    try:
        existing_players = (rec['players'] or '').strip()
    except (IndexError, KeyError):
        existing_players = ''
    try:
        existing_tracks = (rec['tracks'] or '').strip()
    except (IndexError, KeyError):
        existing_tracks = ''
    try:
        existing_genre = (rec['genre'] or '').strip()
    except (IndexError, KeyError):
        existing_genre = ''
    try:
        existing_genre_2 = (rec['genre_2'] or '').strip()
    except (IndexError, KeyError):
        existing_genre_2 = ''

    final_genre, final_genre_2 = _merge_recording_genres(
        existing_genre, existing_genre_2, new_genre, new_genre_2
    )

    sets, params = [], []
    if new_players and not existing_players:
        sets.append('players = ?'); params.append(new_players)
    if new_tracks and not existing_tracks:
        sets.append('tracks = ?'); params.append(new_tracks)
    if final_genre != existing_genre:
        sets.append('genre = ?'); params.append(final_genre)
    if final_genre_2 != existing_genre_2:
        sets.append('genre_2 = ?'); params.append(final_genre_2)
    if sets:
        sets.append('updated_at = ?'); params.append(datetime.utcnow().isoformat())
        params.append(record_id)
        try:
            db.execute(
                f"UPDATE recordings SET {', '.join(sets)} WHERE id = ?",
                params,
            )
            db.commit()
        except sqlite3.OperationalError:
            pass

    # Propagate the lookup-derived content to any sibling copies of
    # the same album (matched on artist + title, case-insensitive,
    # excluding this record). Saves the user from re-running Lookup on
    # every pressing in their collection.
    #
    #   notes       — APPEND the lookup output to each sibling's notes
    #                 (separated by a blank line) so per-copy notes
    #                 like "bought 2018 from Shady Records" survive.
    #                 Skipped if the new notes already appear in the
    #                 sibling's notes (re-runs are idempotent).
    #   players     — OVERWRITE. Personnel is a fact about the
    #                 recording, not the copy.
    #   tracks      — OVERWRITE. Same reasoning.
    #   notes_urls  — UNION. Source URLs accumulate across runs.
    #   genre       — fill if blank, never overwrite.
    #   genre_2     — append any lookup-derived genre / sub-genre that
    #                 isn't already represented in the sibling's
    #                 (genre, genre_2) pair.
    siblings_updated = 0
    title_norm = (rec['title']  or '').strip()
    artist_norm = (rec['artist'] or '').strip()
    new_notes = data.get('markdown') or ''
    if title_norm and artist_norm and (
        new_notes or new_players or new_tracks or new_urls
        or new_genre or new_genre_2
    ):
        sib_rows = db.execute(
            "SELECT id, notes, players, tracks, notes_urls, genre, genre_2 "
            "FROM recordings "
            "WHERE LOWER(TRIM(title)) = LOWER(TRIM(?)) "
            "  AND LOWER(TRIM(artist)) = LOWER(TRIM(?)) "
            "  AND id != ?",
            (title_norm, artist_norm, record_id),
        ).fetchall()
        for sib in sib_rows:
            sib_sets, sib_params = [], []

            sib_notes = (sib['notes'] or '').rstrip()
            if new_notes and new_notes not in sib_notes:
                appended = (sib_notes + '\n\n' + new_notes) if sib_notes else new_notes
                sib_sets.append('notes = ?'); sib_params.append(appended)

            if new_players and (sib['players'] or '').strip() != new_players:
                sib_sets.append('players = ?'); sib_params.append(new_players)
            if new_tracks and (sib['tracks'] or '').strip() != new_tracks:
                sib_sets.append('tracks = ?'); sib_params.append(new_tracks)

            # Merge URLs: existing sibling URLs first, then any new ones
            # not already present. Preserves order, dedupes.
            sib_urls_csv = (sib['notes_urls'] or '').strip()
            sib_urls = [u for u in (s.strip() for s in sib_urls_csv.split(',')) if u]
            sib_url_set = set(sib_urls)
            added_any = False
            for u in merged:
                if u not in sib_url_set:
                    sib_urls.append(u); sib_url_set.add(u); added_any = True
            if added_any:
                sib_sets.append('notes_urls = ?'); sib_params.append(','.join(sib_urls))

            sib_existing_genre = (sib['genre'] or '').strip()
            sib_existing_genre_2 = (sib['genre_2'] or '').strip()
            sib_final_genre, sib_final_genre_2 = _merge_recording_genres(
                sib_existing_genre, sib_existing_genre_2,
                new_genre, new_genre_2,
            )
            if sib_final_genre != sib_existing_genre:
                sib_sets.append('genre = ?'); sib_params.append(sib_final_genre)
            if sib_final_genre_2 != sib_existing_genre_2:
                sib_sets.append('genre_2 = ?'); sib_params.append(sib_final_genre_2)

            if sib_sets:
                sib_sets.append('updated_at = ?')
                sib_params.append(datetime.utcnow().isoformat())
                sib_params.append(sib['id'])
                try:
                    db.execute(
                        f"UPDATE recordings SET {', '.join(sib_sets)} "
                        f"WHERE id = ?",
                        sib_params,
                    )
                    siblings_updated += 1
                except sqlite3.OperationalError:
                    pass
        if siblings_updated:
            db.commit()

    return jsonify({
        'notes': data.get('markdown') or '',
        'players': new_players,
        'tracks': new_tracks,
        'urls': merged,
        # Merged values (after appending any new lookup-derived
        # genres / sub-genres to what was already in the DB), so the
        # client can sync the form fields without re-deriving the
        # merge itself.
        'genre': final_genre,
        'genre_2': final_genre_2,
        'siblings_updated': siblings_updated,
    })


@app.route('/coins/<record_id>/context', methods=['POST'])
def coin_fetch_context(record_id):
    """Combined historical-environment lookup using region + authority +
    mint + date + description together."""
    db = get_db()
    coin = db.execute("SELECT * FROM coins WHERE id = ?", (record_id,)).fetchone()
    if not coin:
        return jsonify({'error': 'Coin not found'}), 404
    try:
        data = fetch_coin_context(coin)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 503
    except Exception as e:
        import traceback
        print(traceback.format_exc(), flush=True)
        detail = str(e) or e.__class__.__name__
        return jsonify({'error': f'Context lookup failed: {detail}'}), 500
    now = datetime.utcnow().isoformat()
    db.execute(
        "UPDATE coins SET history_context = ?, history_searched_at = ?, "
        "updated_at = ? WHERE id = ?",
        (data['markdown'], now, now, record_id),
    )
    db.commit()
    return jsonify({'markdown': data['markdown'], 'searched_at': now})


@app.route('/coins/<record_id>/history', methods=['POST'])
def coin_fetch_history(record_id):
    """AI history search for a coin's region or authority."""
    db = get_db()
    coin = db.execute("SELECT * FROM coins WHERE id = ?", (record_id,)).fetchone()
    if not coin:
        return jsonify({'error': 'Coin not found'}), 404
    payload = request.get_json(silent=True) or {}
    field = payload.get('field', 'region')
    if field not in ('region', 'authority'):
        return jsonify({'error': 'field must be region or authority'}), 400
    topic = coin[field]
    if not topic:
        return jsonify({'error': f'{field.capitalize()} is empty'}), 400
    try:
        data = fetch_coin_history(field, topic, coin)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 503
    except Exception as e:
        import traceback
        print(traceback.format_exc(), flush=True)
        detail = str(e) or e.__class__.__name__
        return jsonify({'error': f'History fetch failed: {detail}'}), 500
    now = datetime.utcnow().isoformat()
    col = 'history_region' if field == 'region' else 'history_authority'
    db.execute(
        f"UPDATE coins SET {col} = ?, history_searched_at = ?, updated_at = ? WHERE id = ?",
        (data['markdown'], now, now, record_id),
    )
    db.commit()
    return jsonify({'field': field, 'topic': topic, 'markdown': data['markdown'], 'searched_at': now})


# ---------------------------------------------------------------------------
# Coin spec lookup: fill missing region/authority/denomination/metal/dates
# from whatever the user has already entered.
# ---------------------------------------------------------------------------

COIN_SPEC_FILLABLE = ('region', 'authority', 'denomination', 'metal',
                      'date_1', 'date_2', 'official',
                      'weight', 'size', 'die_axis', 'grade')


def fetch_coin_specs(coin):
    """Use Claude web_search to fill missing identifying fields on a coin.

    Returns a dict like ``{field: value, ...}`` containing ONLY fields the
    model is confident about. Existing non-empty fields are sent as
    context but never overwritten by the caller.
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY not configured')
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("anthropic package not installed.")

    known = {}
    for f in COIN_SPEC_FILLABLE:
        v = coin[f]
        if v not in (None, ''):
            known[f] = v
    if not known:
        raise RuntimeError(
            'Need at least one of region / authority / denomination / metal '
            '/ date to look up the rest.')

    metals = ', '.join(VALUE_LISTS['metal_coin'])
    obv_rev = (coin['obv_rev'] or '').strip()
    description = (coin['description'] or '').strip()
    mint = (coin['mint'] or '').strip()
    pedigree = (coin['coin_references'] or '').strip()
    condition = (coin['condition'] or '').strip()

    known_lines = '\n'.join(f'- {k}: {v}' for k, v in known.items())
    extras = []
    if mint:        extras.append(f'mint: {mint}')
    if obv_rev:     extras.append(f'obv/rev: {obv_rev}')
    if description: extras.append(f'description (first 400 chars): {description[:400]}')
    if pedigree:    extras.append(f'references / pedigree: {pedigree[:300]}')
    if condition:   extras.append(f'condition note: {condition[:200]}')
    extras_text = '\n'.join(f'- {e}' for e in extras) if extras else '(none)'

    prompt = f"""You are identifying a specific ancient or historical coin.

What the user has entered so far (treat as evidence, but you may correct it if a reputable source clearly shows otherwise):
{known_lines}

Other context for matching:
{extras_text}

Use up to 4 web searches across reputable numismatic sources (e.g. CoinArchives, ACSearch, Wildwinds, NGC Ancients, British Museum, ANS Mantis, vCoins, CNG, Roma Numismatics, NumisBids).

For every field below, return your best identified value if you can. The user wants both fills (where they left a field blank) and corrections (where what they entered conflicts with what reputable sources clearly indicate). Return null only when you genuinely cannot identify the value.

Target fields:
- region: short geographic / cultural region name (e.g. "Ionia", "Roman Republic", "Byzantine Empire", "United States")
- authority: ruler, polity, or issuing authority (e.g. "Augustus", "Phokaia", "Constantine I", "United States Mint")
- denomination: coin denomination (e.g. "Drachm", "Tetradrachm", "Aureus", "Antoninianus", "Dollar")
- metal: EXACTLY one of [{metals}]. Use the two-letter prefix codes shown.
- date_1: integer year of issue. NEGATIVE for BC (e.g. -450 for 450 BC), positive for AD/CE.
- date_2: integer year ending a date range. Same sign convention. Return null if not a range.
- official: the named individual associated with the coin's striking and their role, formatted as "Name, role" — e.g. "Straton, magistrate", "Marcus Junius Brutus, moneyer", "John Reich, engraver", "Lucius Memmius, mint official". Look in the user-entered description FIRST — it often spells this out as "<Name>, <role>" anywhere in the text, including parenthetical asides and even abbreviated or initialed magistrate signatures (e.g. "Ct..., magistrate", "ΔΗ, magistrate", "CT, magistrate"). Capture those verbatim — partial / two-letter names ARE the actual signature on the die. Then fall back to your web sources for fuller context. If the dies are explicitly "unsigned", "attributed to", or "in the style of" a known artist/official, preserve that nuance in the value — e.g. "Euainetos, engraver (unsigned, attributed)" or "Kimon, engraver (style of)". Do NOT silently promote a stylistic attribution to a confirmed signature. Return null only if the description contains no "<Name>, <role>" construct AND your sources don't surface one.
- weight: weight in grams (float). Pull from the user's description / pedigree / condition note if it includes an explicit "X.XX g" measurement; otherwise look up the canonical published weight for this exact reference from your sources. Return null if you cannot find a specific figure.
- size: diameter in mm (float). Take the explicit "XX mm" / "XX.X mm" from the user's notes first, then fall back to the canonical published size for the reference.
- die_axis: integer 0-12 representing the orientation of the reverse die relative to the obverse, expressed as a clock position. The standard numismatic shorthand is the trailing token of "(diameter mm, weight g, NNh)" — e.g. "(32.5mm, 16.83 g, 12h)" → die_axis 12, "9h" → 9, "6 h" → 6. The user's description usually carries this. Return null only if no clock-position notation is present and no reputable source gives one.
- grade: short condition grade as written by collectors (e.g. "VF", "gVF", "EF", "MS-65", "Choice EF"). Pull from the description or condition note when present; only return one if the source actually grades the coin (don't invent).

Reply with ONLY a JSON object, no prose, no code fences. Use null only when you cannot identify a value:
{{
  "region": null,
  "authority": null,
  "denomination": null,
  "metal": null,
  "date_1": null,
  "date_2": null,
  "official": null,
  "weight": null,
  "size": null,
  "die_axis": null,
  "grade": null,
  "sources": "one-line note of which sources hit"
}}
"""

    client = anthropic.Anthropic(api_key=api_key, timeout=240.0)
    import time as _time
    last_err = None
    transient_errs = (
        anthropic.RateLimitError,
        anthropic.APIConnectionError,
        anthropic.APITimeoutError,
        anthropic.InternalServerError,
    )
    resp = None
    for attempt in range(3):
        try:
            resp = client.messages.create(
                model='claude-sonnet-4-5',
                max_tokens=1024,
                tools=[{
                    'type': 'web_search_20250305',
                    'name': 'web_search',
                    'max_uses': 4,
                }],
                messages=[{'role': 'user', 'content': prompt}],
            )
            break
        except transient_errs as e:
            last_err = e
            wait = 10 * (attempt + 1)
            try:
                ra = e.response.headers.get('retry-after') if getattr(e, 'response', None) else None
                if ra:
                    wait = max(wait, int(float(ra)))
            except Exception:
                pass
            if attempt == 2:
                raise RuntimeError(f'Coin spec lookup failed: {last_err}')
            _time.sleep(wait)
    if resp is None:
        raise RuntimeError('Coin spec lookup returned no response')

    text = ''
    for block in resp.content:
        if getattr(block, 'type', None) == 'text':
            text += block.text
    text = text.strip()
    # Strip code fences if the model added them anyway
    text = re.sub(r'^```(?:json)?\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r'\{[\s\S]*\}', text)
        if m:
            return json.loads(m.group(0))
        raise RuntimeError('Could not parse Claude response as JSON')


@app.route('/coins/<record_id>/lookup-specs', methods=['POST'])
def coin_lookup_specs(record_id):
    """Fill blank region/authority/denomination/metal/date fields from web."""
    db = get_db()
    coin = db.execute("SELECT * FROM coins WHERE id = ?", (record_id,)).fetchone()
    if not coin:
        return jsonify({'error': 'Coin not found'}), 404
    try:
        suggestions = fetch_coin_specs(coin)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 503
    except Exception as e:
        import traceback
        print(traceback.format_exc(), flush=True)
        return jsonify({'error': f'Lookup failed: {e or e.__class__.__name__}'}), 500

    metal_allowed = {m.lower(): m for m in VALUE_LISTS['metal_coin']}

    def _coerce(field, raw):
        if raw is None:
            return None
        if field == 'metal':
            if not isinstance(raw, str):
                return None
            return metal_allowed.get(raw.strip().lower())
        if field in ('date_1', 'date_2'):
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None
        if field in ('weight', 'size'):
            # Accept "16.85", "16.85 g", "30 mm" — strip the unit.
            if isinstance(raw, str):
                m = re.match(r'^\s*(-?\d+(?:\.\d+)?)', raw)
                if not m:
                    return None
                try:
                    return float(m.group(1))
                except ValueError:
                    return None
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None
        if field == 'die_axis':
            # Accept "12", "12h", "12 h", "12hr". Clamp to 0-12; the
            # column stores it as text to match the existing select.
            if isinstance(raw, str):
                m = re.match(r'^\s*(\d+)', raw)
                if not m:
                    return None
                n = int(m.group(1))
            else:
                try:
                    n = int(raw)
                except (TypeError, ValueError):
                    return None
            if n < 0 or n > 12:
                return None
            return str(n)
        if isinstance(raw, str):
            v = normalize_field_value('coins', field, raw.strip())
            return v or None
        return raw

    def _equivalent(field, current, suggested):
        if field in ('date_1', 'date_2'):
            try:
                return int(current) == int(suggested)
            except (TypeError, ValueError):
                return False
        if field in ('weight', 'size'):
            # Tolerance: don't propose a "change" for a sub-0.05
            # difference (rounding noise / source-to-source jitter).
            try:
                return abs(float(current) - float(suggested)) < 0.05
            except (TypeError, ValueError):
                return False
        if field == 'die_axis':
            try:
                return int(current) == int(suggested)
            except (TypeError, ValueError):
                return str(current or '').strip() == str(suggested or '').strip()
        return str(current or '').strip().lower() == str(suggested or '').strip().lower()

    # Build proposals (no longer auto-apply fills — every change now
    # flows through the review modal client-side, matching the watch
    # lookup behaviour).
    filled = {}
    overwritten = {}
    for f in COIN_SPEC_FILLABLE:
        v = _coerce(f, suggestions.get(f))
        if v in (None, ''):
            continue
        cur = coin[f]
        if cur in (None, ''):
            filled[f] = v
        elif not _equivalent(f, cur, v):
            overwritten[f] = {'current': cur, 'new': v}

    # Stamp that the lookup ran successfully — used to mark the Check
    # pill green on subsequent visits to this coin.
    now = datetime.utcnow().isoformat()
    db.execute("UPDATE coins SET specs_searched_at = ? WHERE id = ?",
               (now, record_id))
    db.commit()

    return jsonify({
        'filled': filled,
        'overwritten': overwritten,
        'sources': suggestions.get('sources', ''),
        'specs_searched_at': now,
    })


@app.route('/coins/<record_id>/apply-lookup-specs', methods=['POST'])
def coin_apply_lookup_specs(record_id):
    """Apply a user-selected subset of coin spec lookup suggestions.

    Body: ``{"updates": {"<field>": <value>, ...}}``
    Only fields in COIN_SPEC_FILLABLE are accepted. Handles the
    cat_id assignment + group resequencing if date_1 changes — the
    same housekeeping the old lookup endpoint did inline.
    """
    db = get_db()
    coin = db.execute("SELECT * FROM coins WHERE id = ?",
                      (record_id,)).fetchone()
    if not coin:
        return jsonify({'error': 'Coin not found'}), 404
    data = request.get_json(force=True) or {}
    raw = data.get('updates') or {}
    if not isinstance(raw, dict):
        return jsonify({'error': 'updates must be an object'}), 400

    metal_allowed = {m.lower(): m for m in VALUE_LISTS['metal_coin']}

    def _coerce(field, raw_v):
        if raw_v is None:
            return None
        if field == 'metal':
            if not isinstance(raw_v, str):
                return None
            return metal_allowed.get(raw_v.strip().lower())
        if field in ('date_1', 'date_2'):
            try:
                return int(raw_v)
            except (TypeError, ValueError):
                return None
        if field in ('weight', 'size'):
            if isinstance(raw_v, str):
                m = re.match(r'^\s*(-?\d+(?:\.\d+)?)', raw_v)
                if not m:
                    return None
                try:
                    return float(m.group(1))
                except ValueError:
                    return None
            try:
                return float(raw_v)
            except (TypeError, ValueError):
                return None
        if isinstance(raw_v, str):
            return normalize_field_value('coins', field, raw_v.strip()) or None
        return raw_v

    updates = {}
    for k, v in raw.items():
        if k not in COIN_SPEC_FILLABLE:
            continue
        coerced = _coerce(k, v)
        if coerced in (None, ''):
            continue
        updates[k] = coerced
    if not updates:
        return jsonify({'updated': 0, 'fields': []})

    # The detail template prefers date_1_text / date_2_text for
    # display when present. If we update the integer date columns
    # without also rewriting the text columns, the old text value
    # shadows the new integer and the field appears unchanged on
    # reload. Sync both whenever a date integer is updated.
    def _date_text(n):
        try:
            n = int(n)
        except (TypeError, ValueError):
            return ''
        return f'{abs(n)} BC' if n < 0 else str(n)

    if 'date_1' in updates:
        updates['date_1_text'] = _date_text(updates['date_1'])
    if 'date_2' in updates:
        updates['date_2_text'] = _date_text(updates['date_2'])

    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    now = datetime.utcnow().isoformat()
    params = list(updates.values()) + [now, record_id]
    db.execute(
        f"UPDATE coins SET {set_clause}, updated_at = ? WHERE id = ?",
        params,
    )

    # date_1 housekeeping — same as the old lookup endpoint did
    # inline. If the coin now falls into a numbered group (Carp/NY ×
    # Ancient/Modern), resequence Display Position; if cat_id was
    # blank, mint a fresh one for the new group.
    if 'date_1' in updates:
        group = _coin_group_for(coin['property_name'], updates['date_1'])
        if group:
            _renumber_coin_groups(db, [group])
        if not coin['cat_id']:
            new_cat = next_cat_id(db, coin['property_name'], updates['date_1'])
            if new_cat:
                db.execute("UPDATE coins SET cat_id = ? WHERE id = ?",
                           (new_cat, record_id))
                updates['cat_id'] = new_cat
    db.commit()
    return jsonify({'updated': len(updates), 'fields': list(updates.keys())})


@app.route('/<category>/<record_id>/upload-image', methods=['POST'])
def upload_image(category, record_id):
    """AJAX endpoint: drop an image on a list row to set its primary image."""
    if category not in CATEGORIES:
        return jsonify({'error': 'Unknown category'}), 400
    f = request.files.get('image')
    if not f or not f.filename:
        return jsonify({'error': 'No file'}), 400
    if not allowed_file(f.filename):
        return jsonify({'error': 'File type not allowed'}), 400

    # Allow specifying which image field to update (for coins with image_1/image_2 etc.)
    image_field = request.form.get('field') or CATEGORIES[category]['image_field']
    table       = CATEGORIES[category]['table']
    db = get_db()
    valid = {f['name']: f for f in visible_fields(category)}
    if image_field not in valid or valid[image_field].get('type') != 'file':
        return jsonify({'error': 'Invalid file field'}), 400
    cols = [row['name'] for row in db.execute(f"PRAGMA table_info({table})").fetchall()]
    if image_field not in cols:
        return jsonify({'error': 'Invalid field'}), 400
    existing = db.execute(
        f"SELECT * FROM {table} WHERE id = ?", [record_id]
    ).fetchone()
    if not existing:
        return jsonify({'error': 'Record not found'}), 404
    if not _user_can_see_row(category, existing):
        return jsonify({'error': 'Forbidden'}), 403

    stored = save_upload(f)
    if not stored:
        return jsonify({'error': 'Upload failed'}), 500

    db.execute(f"UPDATE {table} SET {image_field} = ?, updated_at = ? WHERE id = ?",
               [stored, datetime.utcnow().isoformat(), record_id])
    _autofill_title_from_filename(db, table, record_id, category,
                                  image_field, f.filename)
    db.commit()

    return jsonify({'url': url_for('uploaded_file', filename=stored)})


# File-typed columns whose underlying file we INTENTIONALLY keep on disk
# after a UI delete. These four power record-specific lookups (license OCR,
# health-card auto-fill) and may be re-attached after a mistaken delete; the
# orphan-uploads admin can still sweep them later if truly abandoned.
_PRESERVE_FILE_FIELDS = frozenset({
    'license_obverse', 'license_reverse',
    'health_card_obv', 'health_card_rev',
})


def _unlink_upload(filename):
    """Best-effort delete of an uploaded file (and its cached thumbnail)
    from UPLOAD_FOLDER. Filename must be the bare basename written by
    save_upload (uuid.ext); anything with a path separator or leading
    dot is rejected to prevent traversal or hitting the .thumbs cache."""
    name = (filename or '').strip()
    if not name or '/' in name or '\\' in name or name.startswith('.'):
        return
    try:
        os.unlink(os.path.join(UPLOAD_FOLDER, name))
    except OSError:
        pass
    try:
        os.unlink(os.path.join(_FILE_THUMB_DIR, name + '.jpg'))
    except OSError:
        pass


@app.route('/<category>/<record_id>/delete-file', methods=['POST'])
def delete_file_field(category, record_id):
    """Clear a single file column on a record (NULL it out) and delete the
    underlying file from disk, EXCEPT for the four ID/health card fields
    in _PRESERVE_FILE_FIELDS — those keep the file so the special OCR /
    auto-fill flows can still reach it. Validated against FIELDS so only
    declared file fields can be cleared."""
    if category not in CATEGORIES:
        return jsonify({'error': 'Unknown category'}), 400
    payload = request.get_json(silent=True) or {}
    field_name = (payload.get('field') or '').strip()
    valid = {f['name']: f for f in visible_fields(category)}
    if field_name not in valid or valid[field_name].get('type') != 'file':
        return jsonify({'error': 'Invalid file field'}), 400
    db = get_db()
    table = CATEGORIES[category]['table']
    cols = [row['name'] for row in db.execute(f"PRAGMA table_info({table})").fetchall()]
    if field_name not in cols:
        return jsonify({'error': 'Column not in table'}), 400
    existing = db.execute(
        f"SELECT * FROM {table} WHERE id = ?", [record_id]
    ).fetchone()
    if not existing:
        return jsonify({'error': 'Record not found'}), 404
    if not _user_can_see_row(category, existing):
        return jsonify({'error': 'Forbidden'}), 403
    old_filename = existing[field_name] if existing else None
    # Clear the paired title/label column too so the tile doesn't keep
    # showing a leftover auto-fill from a since-removed file.
    title_field = _title_field_for(category, field_name)
    cleared_title = title_field if title_field and title_field in cols else None
    # Compute the export-shaped label for the tombstone before we NULL
    # the title column. Prefer the user-supplied title; fall back to
    # the default label from EXPORT_LAYOUT.
    tombstone_label = ''
    if existing and old_filename:
        plan = EXPORT_LAYOUT.get(category, {})
        for spec in plan.get('files', []):
            f, default_label, t_field = spec
            if f == field_name:
                if t_field and t_field in cols and existing[t_field]:
                    tombstone_label = (existing[t_field] or '').strip()
                if not tombstone_label:
                    tombstone_label = default_label or ''
                break
    sets = [f"{field_name} = NULL"]
    if cleared_title:
        sets.append(f"{cleared_title} = NULL")
    sets.append("updated_at = ?")
    db.execute(
        f"UPDATE {table} SET {', '.join(sets)} WHERE id = ?",
        [datetime.utcnow().isoformat(), record_id],
    )
    if old_filename and field_name not in _PRESERVE_FILE_FIELDS:
        _record_tombstone(db, category, existing, tombstone_label, old_filename)
    db.commit()
    if old_filename and field_name not in _PRESERVE_FILE_FIELDS:
        _unlink_upload(old_filename)
    return jsonify({'ok': True, 'cleared_title': cleared_title})


# ---------------------------------------------------------------------------
# Template filters
# ---------------------------------------------------------------------------

# Currency prefixes the JS formatter writes on blur. Anything starting
# with one of these is treated as already-formatted and round-trips
# verbatim through save / display.
_CURRENCY_PREFIX_RE = re.compile(
    r'^\s*(A\$|US\$|\$|€|£|¥|CHF\s|EUR\s|USD\s|AUD\s|AUS\s|GBP\s|JPY\s|YEN\s|CHF$|EUR$|USD$|AUD$|AUS$|GBP$|JPY$|YEN$)',
    re.IGNORECASE)


@app.route('/fx-rate')
def fx_rate():
    """Lookup-only: return a cached USD-conversion rate from the
    fx_rates table, or 404 if not cached. The browser blur handler
    tries this first; on a 404 it falls back to a direct fetch from
    api.frankfurter.dev and POSTs the result to /fx-rate/save so
    future hits are served from this cache. Outbound HTTP doesn't
    happen on this path — Railway's flaky egress is bypassed
    entirely."""
    currency = (request.args.get('currency') or '').strip().upper()
    date_str = (request.args.get('date') or '').strip()
    if not currency or not date_str:
        return jsonify({'ok': False, 'error': 'currency + date required'}), 400
    if currency == 'USD':
        return jsonify({'ok': True, 'rate': 1.0, 'cached': True})
    db = get_db()
    row = db.execute(
        'SELECT usd_rate FROM fx_rates WHERE currency = ? AND date = ?',
        [currency, date_str]
    ).fetchone()
    if row is None:
        return jsonify({'ok': False, 'error': 'not cached'}), 404
    return jsonify({'ok': True, 'rate': float(row['usd_rate']), 'cached': True})


@app.route('/fx-rate/save', methods=['POST'])
def fx_rate_save():
    """Client posts a (currency, date, rate) triple here after a
    successful direct fetch from the FX provider. Idempotent —
    PRIMARY KEY (currency, date) means re-saves are no-ops."""
    payload = request.get_json(silent=True) or {}
    currency = (payload.get('currency') or '').strip().upper()
    date_str = (payload.get('date') or '').strip()
    try:
        rate = float(payload.get('rate'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'rate must be a number'}), 400
    if not currency or not date_str or rate <= 0:
        return jsonify({'ok': False, 'error': 'currency + date + rate required'}), 400
    db = get_db()
    db.execute(
        'INSERT OR REPLACE INTO fx_rates '
        '(currency, date, usd_rate, fetched_at) VALUES (?, ?, ?, ?)',
        [currency, date_str, rate, datetime.utcnow().isoformat()]
    )
    db.commit()
    return jsonify({'ok': True})


def _normalize_price_input(val):
    """Price-input normaliser. Pre-formatted strings with a currency
    prefix ($/A$/€/£/¥/CHF/USD/AUD/EUR/CHF/GBP/JPY/YEN) round-trip
    verbatim — the JS blur formatter is the source of truth for those.
    Anything else falls back to the legacy strip-symbols-and-parse
    behaviour so existing plain-number entries keep working."""
    s = (val or '').strip()
    if not s:
        return s
    if _CURRENCY_PREFIX_RE.match(s):
        return s
    s = s.replace('$', '').replace(',', '').strip()
    m = re.match(r'^\s*(-?\d+(?:\.\d+)?)\s*[A-Za-z%°/]*\s*$', s)
    return m.group(1) if m else s


def _parse_order_money(value):
    if isinstance(value, (int, float)):
        return float(value)
    s = (value or '').strip()
    if not s:
        return None
    s = re.split(r'\s*/\s*\$', s, maxsplit=1)[0]
    s = re.sub(r'\([^)]*\)', '', s)
    cleaned = re.sub(r'[^0-9.\-]', '', s)
    if cleaned in ('', '-', '.', '-.'):
        return None
    try:
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _parse_watch_order_deposit(value, purchase_price):
    s = (value or '').strip()
    pct = None
    m = re.search(r'(-?\d+(?:\.\d+)?)\s*%', s)
    if m:
        try:
            pct = float(m.group(1))
        except (TypeError, ValueError):
            pct = None
    if pct is not None and purchase_price is not None:
        return purchase_price * pct / 100.0, pct
    return _parse_order_money(s), pct


def _row_get(record, name):
    if not record:
        return None
    if hasattr(record, 'keys'):
        return record[name] if name in record.keys() else None
    return record.get(name)


def _watch_order_purchase_amount(record):
    order_purchase = _row_get(record, 'order_purchase_price')
    if order_purchase not in (None, ''):
        return order_purchase
    if str(_row_get(record, 'status') or '').strip() == 'Ordered':
        return _parse_order_money(_row_get(record, 'price'))
    return None


def _infer_watch_order_deposit_percent(record):
    notes = _row_get(record, 'notes') or ''
    m = re.search(r'(\d+(?:\.\d+)?)\s*%\s*(?:down|deposit|paid)', notes, re.IGNORECASE)
    if not m:
        m = re.search(r'(?:down|deposit|paid)[^\d]{0,20}(\d+(?:\.\d+)?)\s*%', notes, re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1))
    except (TypeError, ValueError):
        return None


def _watch_order_deposit_values(record):
    deposit = _row_get(record, 'order_deposit')
    pct = _row_get(record, 'order_deposit_percent')
    if deposit not in (None, ''):
        return deposit, pct
    purchase = _watch_order_purchase_amount(record)
    pct = pct if pct not in (None, '') else _infer_watch_order_deposit_percent(record)
    if pct is not None and purchase is not None:
        return float(purchase) * float(pct) / 100.0, pct
    return None, pct


def _watch_order_balance(purchase_price, deposit):
    if purchase_price is None:
        return None
    if deposit is None:
        return purchase_price
    return purchase_price - deposit


def _watch_order_lateness(expected, actual=None):
    if not expected:
        return ''
    try:
        expected_date = datetime.strptime(str(expected)[:10], '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return ''
    actual_date = None
    if actual:
        try:
            actual_date = datetime.strptime(str(actual)[:10], '%Y-%m-%d').date()
        except (TypeError, ValueError):
            actual_date = None
    compare_date = actual_date or date.today()
    if compare_date <= expected_date:
        return 'On time'
    months = (
        (compare_date.year - expected_date.year) * 12
        + compare_date.month - expected_date.month
    )
    if compare_date.day < expected_date.day:
        months -= 1
    months = max(months, 0)
    if months == 0:
        days = (compare_date - expected_date).days
        return f"{days} day{'s' if days != 1 else ''} late"
    years, rem_months = divmod(months, 12)
    parts = []
    if years:
        parts.append(f"{years} yr{'s' if years != 1 else ''}")
    if rem_months:
        parts.append(f"{rem_months} mo")
    return ' '.join(parts) + ' late'


def _apply_watch_order_form_fields(target, form):
    purchase = _parse_order_money(form.get('order_purchase_price'))
    deposit, pct = _parse_watch_order_deposit(form.get('order_deposit'), purchase)
    target['order_purchase_price'] = purchase
    target['order_deposit'] = deposit
    target['order_deposit_percent'] = pct
    target['order_balance'] = _watch_order_balance(purchase, deposit)


def _has_watch_order_data(record):
    def _field_value(name):
        return _row_get(record, name)

    return any(
        _field_value(k) not in (None, '')
        for k in ('order_purchase_price', 'order_deposit', 'expected_delivery_date')
    )


def _graduate_watch_order_if_owned(target, status_value):
    if str(status_value or '').strip().lower() != 'own':
        return
    purchase = target.get('order_purchase_price')
    if purchase is not None:
        target['price'] = purchase
    if _has_watch_order_data(target) and not target.get('actual_delivery_date'):
        target['actual_delivery_date'] = date.today().isoformat()


def _update_watch_order_field(db, record_id, field_name, raw_value):
    row = db.execute(
        "SELECT order_purchase_price, order_deposit, order_deposit_percent "
        "FROM watches WHERE id = ?",
        [record_id],
    ).fetchone()
    if not row:
        return False
    purchase = row['order_purchase_price']
    deposit = row['order_deposit']
    pct = row['order_deposit_percent']
    if field_name == 'order_purchase_price':
        purchase = _parse_order_money(raw_value)
        if pct is not None and purchase is not None:
            deposit = purchase * float(pct) / 100.0
    elif field_name == 'order_deposit':
        deposit, pct = _parse_watch_order_deposit(raw_value, purchase)
    else:
        return False
    balance = _watch_order_balance(purchase, deposit)
    now = datetime.utcnow().isoformat()
    db.execute(
        "UPDATE watches SET order_purchase_price = ?, order_deposit = ?, "
        "order_deposit_percent = ?, order_balance = ?, updated_at = ? "
        "WHERE id = ?",
        [purchase, deposit, pct, balance, now, record_id],
    )
    return True


def _graduate_watch_order_status(db, record_id):
    row = db.execute(
        "SELECT order_purchase_price, order_deposit, expected_delivery_date, "
        "actual_delivery_date "
        "FROM watches WHERE id = ?",
        [record_id],
    ).fetchone()
    if not row:
        return
    updates = []
    params = []
    if row['order_purchase_price'] is not None:
        updates.append('price = ?')
        params.append(row['order_purchase_price'])
    if _has_watch_order_data(row) and not row['actual_delivery_date']:
        updates.append('actual_delivery_date = ?')
        params.append(date.today().isoformat())
    if updates:
        updates.append('updated_at = ?')
        params.append(datetime.utcnow().isoformat())
        params.append(record_id)
        db.execute(f"UPDATE watches SET {', '.join(updates)} WHERE id = ?", params)


@app.template_filter('currency')
def currency_filter(value):
    """Format as $1,234 by default. Already-formatted strings carrying
    a currency prefix round-trip unchanged so the user's chosen
    currency stays put. Empty -> empty, garbage -> str."""
    if value is None or value == '':
        return ''
    s = str(value).strip()
    # Round-trip already-formatted strings (the JS formatter writes
    # these on blur). Recognised by a currency prefix.
    if _CURRENCY_PREFIX_RE.match(s):
        return s
    try:
        return f"${float(s.replace(',', '').replace('$', '')):,.0f}"
    except (ValueError, TypeError):
        return s


@app.template_filter('order_deposit')
def order_deposit_filter(value, percent=None):
    base = currency_filter(value)
    if percent in (None, ''):
        return base
    try:
        pct = float(percent)
    except (TypeError, ValueError):
        return base
    pct_text = f"{pct:g}%"
    return f"{base} ({pct_text})" if base else pct_text


@app.template_filter('watch_order_purchase')
def watch_order_purchase_filter(record):
    return currency_filter(_watch_order_purchase_amount(record))


@app.template_filter('watch_order_deposit')
def watch_order_deposit_filter(record):
    deposit, pct = _watch_order_deposit_values(record)
    return order_deposit_filter(deposit, pct)


@app.template_filter('watch_order_balance')
def watch_order_balance_filter(record):
    purchase = _watch_order_purchase_amount(record)
    deposit, _pct = _watch_order_deposit_values(record)
    return currency_filter(_watch_order_balance(purchase, deposit))


@app.template_filter('delivery_lateness')
def delivery_lateness_filter(expected, actual=None):
    return _watch_order_lateness(expected, actual)


@app.template_filter('lug_fmt')
def lug_fmt_filter(value):
    """Convert stored lug value to display string.
    >= 1000  →  '20/16'  (front/back in mm)
    < 1000   →  '20'     (single measurement)
    Already text like '20/16' → pass through.
    """
    if value is None or value == '' or value == '0' or value == 0:
        return ''
    # Already formatted (contains '/')
    if isinstance(value, str) and '/' in value:
        return value
    try:
        f = float(value)
        if f == 0:
            return ''
        if f >= 1000:
            int_part = int(f)
            dec_part = round(f - int_part, 6)
            s = str(int_part)
            front = s[:2]
            back_int = int(s[2:])
            back = f"{back_int + dec_part:g}" if dec_part else str(back_int)
            return f"{front}/{back}"
        else:
            return f"{f:g}"          # strips trailing zeros (17.5, 20, 14)
    except (ValueError, TypeError):
        return str(value)


@app.template_filter('fmt_int')
def fmt_int_filter(value):
    """Display a number as a plain integer with no decimals."""
    if value is None or value == '':
        return ''
    try:
        return f"{int(float(value)):,}"
    except (ValueError, TypeError):
        return str(value)


@app.template_filter('short_date')
def short_date_filter(value):
    """Render an ISO datetime or YYYY-MM-DD string as 'MMM D, YYYY'."""
    if not value:
        return ''
    s = str(value)
    try:
        # datetime.fromisoformat handles both 'YYYY-MM-DD' and full ISO.
        dt = datetime.fromisoformat(s.replace('Z', ''))
    except ValueError:
        return s
    return dt.strftime('%b %-d, %Y')


@app.template_filter('format_results')
def format_results_filter(value):
    """Turn the AI-generated Results markdown into clean HTML.

    - Lines starting with -, * or • become <li> items.
    - URLs become clickable <a target=_blank> links.
    - Dollar amounts like $1,234 or $12,345.67 are wrapped in <strong>.
    """
    if not value:
        return ''
    import html as _html
    from markupsafe import Markup

    # Decode any stray HTML entities the AI may have embedded (&#39; etc.)
    # before we re-escape during rendering.
    raw = _html.unescape(str(value)).strip()
    # Claude's web_search tool injects <cite index="...">...</cite> markers
    # around quoted text. Strip the tags but keep the inner content.
    raw = re.sub(r'</?cite\b[^>]*>', '', raw, flags=re.IGNORECASE)
    lines = raw.split('\n')
    out = []
    in_list = False
    url_re = re.compile(r'https?://[^\s<>()]+')
    money_re = re.compile(r'(\$[0-9][0-9,]*(?:\.\d+)?)')
    # Trim stray punctuation the model tends to attach to URLs
    _url_trail = '.,;:)]}"\''

    def _short(url):
        u = url.rstrip(_url_trail)
        try:
            from urllib.parse import urlparse
            host = urlparse(u).hostname or u
            if host.startswith('www.'):
                host = host[4:]
            return host
        except Exception:
            return 'link'

    def _inline(text):
        # Replace URLs first (on raw text) with a placeholder that survives
        # HTML-escape, then substitute the final anchor markup.
        anchors = []
        def _cap(m):
            url = m.group(0).rstrip(_url_trail)
            anchors.append(url)
            return f'\x00A{len(anchors) - 1}\x00'
        text = url_re.sub(_cap, text)
        text = _html.escape(text)
        # Drop any em/en-dash + whitespace immediately before the placeholder —
        # the model tends to write "... : $X,XXX — <url>" which now reads
        # "... : $X,XXX" with a trailing pill.
        text = re.sub(r'\s*[\u2014\u2013-]\s*(\x00A\d+\x00)', r' \1', text)
        for i, url in enumerate(anchors):
            pill = (f'<a class="result-src" href="{_html.escape(url, quote=True)}" '
                    f'target="_blank" rel="noopener">{_html.escape(_short(url))}</a>')
            text = text.replace(f'\x00A{i}\x00', pill)
        # Markdown **bold** → <strong>, and *italic* → <em>. Run bold first
        # so its ** markers aren't eaten by the single-asterisk italic rule.
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        # Tolerate the AI's lopsided bold attempts: `*Heading**` and
        # `**Heading*` show up periodically (especially as bullet headings)
        # and would otherwise render with a stray asterisk on each side.
        text = re.sub(r'(?<!\*)\*([^*\n]+?)\*\*(?!\*)', r'<strong>\1</strong>', text)
        text = re.sub(r'(?<!\*)\*\*([^*\n]+?)\*(?!\*)', r'<strong>\1</strong>', text)
        text = re.sub(r'(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])', r'<em>\1</em>', text)
        text = money_re.sub(r'<strong>\1</strong>', text)
        return text

    for raw in lines:
        line = raw.strip()
        if not line:
            if in_list:
                out.append('</ul>')
                in_list = False
            continue
        # A bullet is '-', '•', or '*' followed by whitespace. Bare
        # '*' at line start belongs to **bold** and must NOT be treated
        # as a bullet marker (otherwise the first asterisk gets eaten
        # and `**Style**` renders as `*Style**`).
        bullet = False
        content = line
        if len(line) >= 2 and line[0] in ('-', '•', '*') and line[1] in ' \t':
            bullet = True
            content = line[2:].strip()
        if bullet:
            if not in_list:
                out.append('<ul class="results-list">')
                in_list = True
            out.append(f'<li>{_inline(content)}</li>')
        else:
            if in_list:
                out.append('</ul>')
                in_list = False
            out.append(f'<p>{_inline(line)}</p>')
    if in_list:
        out.append('</ul>')
    return Markup(''.join(out))


@app.template_filter('from_json')
def from_json_filter(value):
    """Parse a JSON string in templates. Returns [] on null / invalid
    input so callers can iterate without guarding."""
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


# ---------------------------------------------------------------------------
# Documents JSON helpers + endpoints
# ---------------------------------------------------------------------------
# Per-category map of doc-set name → JSON column name. The set name
# appears in the route URL so categories with multiple independent
# doc-rows (persons: ids + health) can route through the same handlers.
# Categories with a single row use 'main' → 'documents' by convention.
DOC_SETS_BY_CATEGORY = {
    'properties': {'main': 'documents'},
    'watches':    {'main': 'documents'},
    'coins':      {'main': 'documents'},
    'art':        {'main': 'documents'},
    'items':      {'main': 'documents'},
    'vehicles':   {'main': 'documents'},
    'pens':       {'main': 'documents'},
    'recordings': {'main': 'documents'},
    'rifles':     {'main': 'documents'},
    'audio':      {'main': 'documents'},
    'cameras':    {'main': 'documents'},
    'lenses':     {'main': 'documents'},
    'persons':    {'ids': 'id_documents', 'health': 'health_documents'},
}
DOCUMENTS_CATEGORIES = set(DOC_SETS_BY_CATEGORY.keys())


def _docs_col(category, doc_set):
    """Return the JSON column name for (category, doc_set), or None if
    the pair isn't enabled."""
    return DOC_SETS_BY_CATEGORY.get(category, {}).get(doc_set)


def _docs_cols_for(category):
    """All JSON columns this category uses for documents (zero or more)."""
    return list(DOC_SETS_BY_CATEGORY.get(category, {}).values())


# Title keywords used to route a Sweep upload to the right doc-set on
# multi-set categories (persons). Match is whole-token (case-insensitive)
# — the label is split on whitespace + punctuation and a keyword has to
# equal one of the resulting tokens. Substring matching was too loose:
# 'id' was a substring of 'covid', so a vaccination card got routed to
# the IDs tab. Multi-word phrases need to be expressed as their
# component tokens (e.g. 'global entry' → 'global', 'entry').
SWEEP_DOC_SET_HINTS = {
    'persons': [
        ('health_documents', ('health', 'medic', 'medical', 'rx',
                              'prescription', 'doctor', 'eye', 'dental',
                              'insurance', 'covid', 'vaccine',
                              'vaccinated', 'vaccination', 'vax',
                              'fever')),
        ('id_documents',     ('id', 'license', 'passport', 'visa',
                              'global', 'entry', 'birth', 'social')),
    ],
}


_LABEL_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _route_sweep_doc_set(category, label):
    """Pick the JSON column for a sweep-uploaded file. Single-set
    categories always return their lone column; multi-set ones run
    SWEEP_DOC_SET_HINTS against the file's parsed label (tokenized) and
    fall back to the first declared set if nothing matches."""
    cols = _docs_cols_for(category)
    if not cols:
        return 'documents'
    if len(cols) == 1:
        return cols[0]
    tokens = set(_LABEL_TOKEN_RE.findall((label or '').lower()))
    for col, keywords in SWEEP_DOC_SET_HINTS.get(category, []):
        if col not in cols:
            continue
        if any(k in tokens for k in keywords):
            return col
    return cols[0]


def _docs_load(db, table, record_id, col='documents'):
    """Read the documents JSON for a record from `col`, normalizing to
    a list of {title, filename} dicts. Returns None if record missing,
    [] when the column is null/malformed."""
    row = db.execute(
        f"SELECT {col} FROM {table} WHERE id = ?", [record_id]
    ).fetchone()
    if not row:
        return None
    try:
        docs = json.loads(row[col] or '[]')
    except (TypeError, ValueError):
        docs = []
    if not isinstance(docs, list):
        docs = []
    # Defensive: drop any stray entries that aren't dicts so the
    # endpoints can assume shape.
    return [d for d in docs if isinstance(d, dict)]


def _docs_save(db, table, record_id, docs, col='documents'):
    db.execute(
        f"UPDATE {table} SET {col} = ?, updated_at = ? WHERE id = ?",
        [json.dumps(docs), datetime.utcnow().isoformat(), record_id],
    )
    db.commit()


def _docs_update(db, table, record_id, docs, col='documents', now=None):
    """Update a document JSON column without committing.

    Used when multiple document columns must change atomically; callers
    commit once after every column update succeeds.
    """
    db.execute(
        f"UPDATE {table} SET {col} = ?, updated_at = ? WHERE id = ?",
        [json.dumps(docs), now or datetime.utcnow().isoformat(), record_id],
    )


def _auto_title_from_basename(category, record_id, basename):
    """Compute a sensible default title for a doc tile from its
    uploaded filename. Drops the extension, then strips a leading
    '<record-ident> — ' prefix when it matches the record's
    EXPORT_LAYOUT ident — that prefix duplicates information already
    attached to the record (e.g. a 'Rec Center — Image.jpg' dropped
    on the Rec Center property becomes 'Image', not the full
    redundant string). Falls back to the bare basename if the
    EXPORT_LAYOUT lookup fails for any reason."""
    base = os.path.splitext(os.path.basename(basename or ''))[0].strip()
    if not base:
        return ''
    plan = (globals().get('EXPORT_LAYOUT') or {}).get(category) or {}
    ident_fn = plan.get('ident')
    if not ident_fn:
        return base
    try:
        db = get_db()
        row = db.execute(
            f"SELECT * FROM {CATEGORIES[category]['table']} WHERE id = ?",
            [record_id]
        ).fetchone()
        if not row:
            return base
        ident = (ident_fn(row) or '').strip()
        if ident:
            prefix = f'{ident} — '
            if base.startswith(prefix):
                base = base[len(prefix):].strip() or base
    except Exception:
        pass
    return base


def _docs_guard(category, record_id, doc_set):
    """Common pre-flight. Returns (err_response, col): on error
    err_response is a Flask error tuple and col is None; on success
    err_response is None and col is the JSON column to operate on."""
    col = _docs_col(category, doc_set)
    if not col:
        return (jsonify({'error': 'Unknown documents set'}), 400), None
    table = CATEGORIES[category]['table']
    db = get_db()
    row = db.execute(
        f"SELECT * FROM {table} WHERE id = ?", [record_id]
    ).fetchone()
    if not row:
        return (jsonify({'error': 'Record not found'}), 404), None
    if not _user_can_see_row(category, row):
        return (jsonify({'error': 'Forbidden'}), 403), None
    return None, col


@app.route('/<category>/<record_id>/documents/<doc_set>/append', methods=['POST'])
def documents_append(category, record_id, doc_set):
    """Append a new document. Accepts multipart with optional `file`
    and optional `title`. At least one must be present."""
    err, col = _docs_guard(category, record_id, doc_set)
    if err: return err
    db = get_db()
    table = CATEGORIES[category]['table']
    docs = _docs_load(db, table, record_id, col) or []
    title = (request.form.get('title') or '').strip()
    upload = request.files.get('file') or request.files.get('image')
    filename = ''
    original_basename = ''
    if upload and upload.filename:
        if not allowed_file(upload.filename):
            return jsonify({'error': 'File type not allowed'}), 400
        original_basename = upload.filename
        filename = save_upload(upload) or ''
        if not filename:
            return jsonify({'error': 'Upload failed'}), 500
    if not title and not filename:
        return jsonify({'error': 'title or file required'}), 400
    # Default title to the dropped file's basename (sans extension) so
    # newly-added tiles render with something readable instead of just
    # the file preview. _auto_title_from_basename also strips a
    # redundant '<record-ident> — ' prefix when the dropped file came
    # from a Files export of this same record. The user can rename
    # via the title input.
    if not title and original_basename:
        title = _auto_title_from_basename(category, record_id, original_basename)
    docs.append({'title': title, 'filename': filename})
    _docs_save(db, table, record_id, docs, col)
    return jsonify({
        'ok': True, 'idx': len(docs) - 1,
        'title': title, 'filename': filename,
        'url': url_for('uploaded_file', filename=filename) if filename else '',
    })


@app.route('/<category>/<record_id>/documents/<doc_set>/<int:idx>/title', methods=['POST'])
def documents_set_title(category, record_id, doc_set, idx):
    err, col = _docs_guard(category, record_id, doc_set)
    if err: return err
    db = get_db()
    table = CATEGORIES[category]['table']
    docs = _docs_load(db, table, record_id, col) or []
    if idx < 0 or idx >= len(docs):
        return jsonify({'error': 'Index out of range'}), 400
    payload = request.get_json(silent=True) or {}
    docs[idx]['title'] = (payload.get('title') or '').strip()
    _docs_save(db, table, record_id, docs, col)
    return jsonify({'ok': True})


@app.route('/<category>/<record_id>/documents/<doc_set>/<int:idx>/file', methods=['POST'])
def documents_set_file(category, record_id, doc_set, idx):
    """Replace the file on an existing document tile."""
    err, col = _docs_guard(category, record_id, doc_set)
    if err: return err
    db = get_db()
    table = CATEGORIES[category]['table']
    docs = _docs_load(db, table, record_id, col) or []
    if idx < 0 or idx >= len(docs):
        return jsonify({'error': 'Index out of range'}), 400
    upload = request.files.get('file') or request.files.get('image')
    if not upload or not upload.filename:
        return jsonify({'error': 'No file'}), 400
    if not allowed_file(upload.filename):
        return jsonify({'error': 'File type not allowed'}), 400
    original_basename = upload.filename
    filename = save_upload(upload)
    if not filename:
        return jsonify({'error': 'Upload failed'}), 500
    docs[idx]['filename'] = filename
    # Backfill title from the new file's basename only if this tile is
    # currently untitled — leave deliberate user titles alone. Strips
    # the redundant '<record-ident> — ' prefix the same way as append.
    if not (docs[idx].get('title') or '').strip() and original_basename:
        docs[idx]['title'] = _auto_title_from_basename(category, record_id, original_basename)
    _docs_save(db, table, record_id, docs, col)
    return jsonify({
        'ok': True, 'filename': filename, 'title': docs[idx].get('title', ''),
        'url': url_for('uploaded_file', filename=filename),
    })


@app.route('/<category>/<record_id>/documents/<doc_set>/<int:idx>/delete', methods=['POST'])
def documents_delete(category, record_id, doc_set, idx):
    """Remove a document tile and the underlying file. The row's
    always-present trailing '+ Add document' slot is the empty drop
    zone; we don't preserve a bin in the deleted slot's place. (Special
    license/health-card cells live in dedicated columns handled by
    delete_file_field.)"""
    err, col = _docs_guard(category, record_id, doc_set)
    if err: return err
    db = get_db()
    table = CATEGORIES[category]['table']
    docs = _docs_load(db, table, record_id, col) or []
    if idx < 0 or idx >= len(docs):
        return jsonify({'error': 'Index out of range'}), 400
    removed = docs.pop(idx)
    # Tombstone the deleted file so the next incremental syncDown can
    # mirror the deletion locally. Read the row before the save so we
    # can compute the export-shaped path.
    if isinstance(removed, dict):
        rm_filename = (removed.get('filename') or '').strip()
        rm_title = (removed.get('title') or '').strip()
        if rm_filename:
            row = db.execute(
                f"SELECT * FROM {table} WHERE id = ?", [record_id]
            ).fetchone()
            if row:
                _record_tombstone(db, category, row, rm_title, rm_filename)
    _docs_save(db, table, record_id, docs, col)
    if isinstance(removed, dict):
        _unlink_upload(removed.get('filename') or '')
    return jsonify({'ok': True, 'count': len(docs)})


@app.route('/<category>/<record_id>/documents/<doc_set>/<int:idx>/move-to/<dst_set>', methods=['POST'])
def documents_move(category, record_id, doc_set, idx, dst_set):
    """Move a document entry from one doc-set to another within the
    same record. Used by the UI when the user drags a tile from one
    persons row (e.g. ids) onto the other (e.g. health). The entry is
    appended to the end of the destination set so it lands in a
    visible position; the source set is reindexed by the natural pop.
    Returns counts for both sets so the caller can refresh.

    Single-set categories never invoke this — DOC_SETS_BY_CATEGORY
    only declares one column for them, and _docs_guard rejects
    unknown set names. Same-set moves are also rejected (use the
    /reorder endpoint instead)."""
    err, src_col = _docs_guard(category, record_id, doc_set)
    if err: return err
    dst_col = _docs_col(category, dst_set)
    if not dst_col:
        return jsonify({'error': 'Unknown destination set'}), 400
    if dst_col == src_col:
        return jsonify({'error': 'Use reorder for same-set moves'}), 400
    db = get_db()
    table = CATEGORIES[category]['table']
    src_docs = _docs_load(db, table, record_id, src_col) or []
    if idx < 0 or idx >= len(src_docs):
        return jsonify({'error': 'Index out of range'}), 400
    dst_docs = _docs_load(db, table, record_id, dst_col) or []
    entry = src_docs.pop(idx)
    dst_docs.append(entry)
    now = datetime.utcnow().isoformat()
    _docs_update(db, table, record_id, src_docs, src_col, now)
    _docs_update(db, table, record_id, dst_docs, dst_col, now)
    db.commit()
    return jsonify({
        'ok': True,
        'src_count': len(src_docs),
        'dst_count': len(dst_docs),
    })


@app.route('/<category>/<record_id>/documents/<doc_set>/reorder', methods=['POST'])
def documents_reorder(category, record_id, doc_set):
    """Reorder the documents JSON array. Body: {"order": [old_idx, ...]}
    must be a permutation of 0..N-1; the new array is built by reading
    the old one in the order given."""
    err, col = _docs_guard(category, record_id, doc_set)
    if err: return err
    db = get_db()
    table = CATEGORIES[category]['table']
    docs = _docs_load(db, table, record_id, col) or []
    payload = request.get_json(silent=True) or {}
    order = payload.get('order')
    if (not isinstance(order, list)
            or len(order) != len(docs)
            or sorted(order) != list(range(len(docs)))):
        return jsonify({'error': 'order must be a permutation of 0..N-1'}), 400
    docs = [docs[i] for i in order]
    _docs_save(db, table, record_id, docs, col)
    return jsonify({'ok': True, 'count': len(docs)})


@app.template_filter('is_image')
def is_image_filter(filename):
    if not filename:
        return False
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext in ('png', 'jpg', 'jpeg', 'gif', 'webp', 'tif', 'tiff')


def _asset_v(rel_path):
    """Cache-bust token for a static asset — its mtime as an int. Lets
    base.html hand `?v=…` to <script>/<link> URLs so a fresh deploy
    invalidates the browser's 12-hour static-asset cache the moment
    the underlying file changes (and stays stable across requests
    when nothing has)."""
    try:
        return int(os.path.getmtime(
            os.path.join(app.static_folder or 'static', rel_path)
        ))
    except OSError:
        return 0


@app.context_processor
def inject_globals():
    return {
        'CATEGORIES': CATEGORIES,
        'now': datetime.utcnow(),
        'current_user': g.get('current_user'),
        'allowed_cats': g.get('allowed_cats', set()),
        'asset_v': _asset_v,
        'is_hidden_field': lambda cat, field: field in HIDE_FIELDS.get(cat, set()),
        'count_visible': lambda cat, names: sum(
            1 for n in names if n not in HIDE_FIELDS.get(cat, set())),
        'is_tenant': TENANT_CATEGORIES is not None,
    }


# ---------------------------------------------------------------------------
# Multi-user authorization
#
# Cloudflare Access authenticates the visitor at the edge and forwards
# their verified email in `Cf-Access-Authenticated-User-Email`. The app
# trusts that header (production-only — locally we fall back to an env
# var so dev still works).
#
# The `users` table maps each email to a set of allowed category slugs.
# Owner role gets categories='*' which expands to every category. Anyone
# whose email isn't in the table gets 403.
# ---------------------------------------------------------------------------

OWNER_EMAIL = (os.environ.get('STUFFAPP_OWNER_EMAIL') or
               'MarkArmenante@gmail.com').lower()
OWNER_DISPLAY_NAME = (os.environ.get('STUFFAPP_OWNER_DISPLAY_NAME') or
                      'Mark Armenante')
OWNER_CATEGORIES = os.environ.get('STUFFAPP_OWNER_CATEGORIES') or '*'

# Tenant scope — when a deployment restricts the owner's categories,
# this is the canonical "what does this tenant deal with" set. Used to
# constrain UI surfaces (e.g. property pills) so visiting users with
# broader access still see only the tenant's slice.
TENANT_CATEGORIES = (
    None if OWNER_CATEGORIES.strip() in ('*', '')
    else {c.strip() for c in OWNER_CATEGORIES.split(',') if c.strip()}
)


def _ensure_owner_user(db):
    """Idempotent: make sure the owner email exists. On a fresh DB,
    seed the configured display_name and categories. On an existing
    DB, only re-assert role='owner' so an admin's manual edits to
    display_name or categories aren't clobbered on every boot."""
    db.execute(
        "INSERT INTO users (id, email, display_name, role, categories) "
        "VALUES (?, ?, ?, 'owner', ?) "
        "ON CONFLICT(email) DO UPDATE SET role='owner'",
        [str(uuid.uuid4()), OWNER_EMAIL, OWNER_DISPLAY_NAME, OWNER_CATEGORIES]
    )


def _resolve_user_email():
    """Email of the currently authenticated visitor. CF Access on prod;
    STUFFAPP_DEV_USER env var locally so per-user testing still works."""
    e = (request.headers.get('Cf-Access-Authenticated-User-Email') or
         os.environ.get('STUFFAPP_DEV_USER') or OWNER_EMAIL)
    return (e or '').strip().lower()


def _expand_categories(raw, role):
    """Resolve a user's category list. '*' (or empty for owner role)
    means all categories; otherwise the explicit comma-separated
    list. Owner role no longer auto-bypasses an explicit list — that
    way a third-party deployment can be owner-role-but-restricted
    without forking the visibility model."""
    s = (raw or '').strip()
    if s == '*' or (role == 'owner' and not s):
        return set(CATEGORIES.keys())
    return {c.strip() for c in s.split(',') if c.strip() in CATEGORIES}


# Property name aliases — different ways the same physical property
# is recorded across categories (Carp / Carpinteria, Truckee / Martis
# Camp / Martis). Filtering by any one form matches all of them.
# Keys + values are lowercase. Adding a new alias here is the only
# change needed to make the at-property filter and the back-pill
# lookup recognise it.
PROPERTY_ALIASES = {
    'carpinteria': ['carpinteria', 'carp', 'montecito'],
    'carp':        ['carpinteria', 'carp', 'montecito'],
    'truckee':     ['truckee', 'martis camp', 'martis'],
    'martis camp': ['truckee', 'martis camp', 'martis'],
    'martis':      ['truckee', 'martis camp', 'martis'],
    # 42 Hotaling absorbed the old "SF" / "San Francisco" tag set after
    # the 3450 Washington property was retired (kept as Sold record).
    '42 hotaling':   ['42 hotaling', 'sf', 'san francisco'],
    # Ghent campus — strip the legacy "Ghent: " prefix from each
    # building. Bidirectional so a stray "Ghent: Pond House" item still
    # surfaces under the Pond House pill until the boot migration
    # rewrites it.
    'pond house':    ['pond house', 'ghent: pond house'],
    'glass house':   ['glass house', 'ghent: glass house'],
    'harlemville':   ['harlemville', 'ghent: harlemville'],
    'party barn':    ['party barn', 'ghent: party barn'],
    'rec center':    ['rec center', 'ghent: rec center',
                      'ghent: rec center/arena', 'rec center/arena'],
    'rigor hill':    ['rigor hill', 'ghent: rigor hill'],
    '223 rigor':     ['223 rigor', 'ghent: 223 rigor'],
    # NYC: prefix strip
    '1 white st':       ['1 white st', 'nyc: 1 white st'],
    '357 w broadway':   ['357 w broadway', 'nyc: 357 w broadway'],
    '67 engert':        ['67 engert', 'nyc: 67 engert'],
    # The "NYC" property record was previously named "56 Leonard"
    'nyc':           ['nyc', '56 leonard', 'nyc: 56 leonard'],
    # SF: prefix strip
    '432 jackson':   ['432 jackson', 'sf: 432 jackson'],
    # Address typo correction
    '3956 fifth':    ['3956 fifth', '4956 fifth'],
}


def _property_alias_group(name):
    """Return every equivalent form for a property name (lowercased,
    trimmed). Falls back to a single-element list with the input
    when the name has no known aliases."""
    n = (name or '').strip().lower()
    if not n:
        return []
    return PROPERTY_ALIASES.get(n, [n])


# Per-category mapping of which column stores the owning Property's
# name. Categories not listed here can't be filtered "at <property>"
# (e.g. credit cards, persons). Used by the Property detail's pill
# row and by /<cat>?at=<name> list filtering.
CATEGORY_PROPERTY_FIELD = {
    'watches':    'property',
    'coins':      'property_name',
    'cameras':    'property',
    'lenses':     'property',
    'pens':       'property',
    'art':        'property',
    'items':      'property',
    'vehicles':   'property',
    'recordings': 'property',
    'audio':      'property',
    'rifles':     'property',
}


# Row-level filtering. Per category, which fields can a member be
# restricted on, and where does the value list for each field come
# from in VALUE_LISTS. Add an entry here to enable filtering on a
# new field — UI + enforcement pick it up automatically.
ROW_FILTER_FIELDS = {
    'watches':      ['owner'],
    'coins':        ['owner'],
    'cameras':      ['owner'],
    'lenses':       ['owner'],
    'pens':         ['owner'],
    'art':          ['owner'],
    'items':        ['owner'],
    'vehicles':     ['owner'],
    'recordings':   ['owner'],
    'audio':        ['owner'],
    'rifles':       ['owner'],
    'credit_cards': ['owner'],
    'properties':   ['owner'],
    'persons':      ['owner'],
}
# field name → VALUE_LISTS key for picking allowed values in the UI.
ROW_FILTER_VALUE_LISTS = {
    'owner': 'owner',
}


def _parse_row_filters_json(raw):
    """Decode a users.row_filters JSON blob; tolerant of NULL / bad
    input (returns {})."""
    if not raw:
        return {}
    try:
        d = json.loads(raw) if isinstance(raw, str) else raw
        return d if isinstance(d, dict) else {}
    except (ValueError, TypeError):
        return {}


def _user_row_filters(user):
    """Effective per-category row filters for a user dict. Owners have
    no row restrictions; everyone else gets whatever JSON they have."""
    if not user or user.get('role') == 'owner':
        return {}
    return _parse_row_filters_json(user.get('row_filters'))


def _row_filter_for_category(user, category):
    """Return {field: [allowed_values, …]} for one category, or {}."""
    f = _user_row_filters(user).get(category)
    return f if isinstance(f, dict) else {}


def _user_can_see_row(category, row):
    """Does the current user pass the row filter for this record? True
    when there's no filter or the row's filtered fields are all in the
    allowed lists."""
    user = g.get('current_user')
    filt = _row_filter_for_category(user, category)
    if not filt:
        return True
    for field, allowed in filt.items():
        if not allowed:
            continue
        try:
            v = row[field] if hasattr(row, 'keys') and field in row.keys() else None
        except (KeyError, IndexError):
            v = None
        if v not in allowed:
            return False
    return True


def _apply_row_filter_clauses(category, wheres, params):
    """Mutate a build_search_query-style (wheres, params) pair to
    add `(<field> IN (?, ?...))` clauses for each filtered field on
    the current user."""
    user = g.get('current_user')
    filt = _row_filter_for_category(user, category)
    for field, allowed in filt.items():
        if not allowed:
            continue
        ph = ','.join(['?' for _ in allowed])
        wheres.append(f'({field} IN ({ph}))')
        params.extend(allowed)


def _upload_visible_to_current_user(filename):
    """Return True when an upload filename belongs to a visible row.

    Upload URLs are intentionally opaque UUID-ish names, but they still
    need the same category + row-filter privacy model as the list/detail
    pages. This checks fixed file columns, JSON document lists, and
    property topic images before serving `/uploads/...` or thumbnails.
    """
    name = (filename or '').strip()
    if not name or '/' in name or '\\' in name or name.startswith('.'):
        return False
    if not g.get('current_user'):
        return False
    allowed = g.get('allowed_cats') or set()
    if not allowed:
        return False
    db = get_db()

    for cat, info in CATEGORIES.items():
        if cat not in allowed:
            continue
        table = info['table']
        try:
            cols = {
                r['name']
                for r in db.execute(f"PRAGMA table_info({table})").fetchall()
            }
        except sqlite3.OperationalError:
            continue

        file_cols = [
            f['name'] for f in FIELDS.get(cat, [])
            if f.get('type') == 'file' and f['name'] in cols
        ]
        if file_cols:
            wheres = ['(' + ' OR '.join(f"{c} = ?" for c in file_cols) + ')']
            params = [name] * len(file_cols)
            _apply_row_filter_clauses(cat, wheres, params)
            where_clause = ' AND '.join(wheres)
            try:
                row = db.execute(
                    f"SELECT id FROM {table} WHERE {where_clause} LIMIT 1",
                    params,
                ).fetchone()
            except sqlite3.OperationalError:
                row = None
            if row:
                return True

        doc_cols = [c for c in _docs_cols_for(cat) if c in cols]
        if doc_cols:
            wheres = [
                '(' + ' OR '.join(f"{c} LIKE ?" for c in doc_cols) + ')'
            ]
            params = [f'%{name}%'] * len(doc_cols)
            _apply_row_filter_clauses(cat, wheres, params)
            where_clause = ' AND '.join(wheres)
            try:
                rows = db.execute(
                    f"SELECT {', '.join(doc_cols)} FROM {table} "
                    f"WHERE {where_clause}",
                    params,
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
            for row in rows:
                for col in doc_cols:
                    try:
                        docs = json.loads(row[col] or '[]')
                    except (TypeError, ValueError):
                        continue
                    if not isinstance(docs, list):
                        continue
                    for d in docs:
                        if isinstance(d, dict) and \
                                (d.get('filename') or '').strip() == name:
                            return True

    # Property topic images live in topics.image rather than the regular
    # category file fields. They inherit visibility from the parent
    # property row.
    if 'properties' in allowed:
        try:
            rows = db.execute(
                "SELECT p.* FROM topics t "
                "JOIN properties p ON p.id = t.property_id "
                "WHERE t.image = ?",
                [name],
            ).fetchall()
        except sqlite3.OperationalError:
            rows = []
        for row in rows:
            if _user_can_see_row('properties', row):
                return True

    return False


# Endpoints that everyone gets to hit regardless of category access.
# Uploaded files and generated thumbnails are NOT exempt: the route
# handlers enforce category + row-filter access before serving bytes.
_AUTH_EXEMPT_ENDPOINTS = {'static'}


@app.before_request
def _load_user_and_authorize():
    """Identify the user, attach to flask.g, and 403 if they don't have
    access to whichever category the URL targets. Owner-only routes
    check g.current_user.role themselves."""
    if request.endpoint in _AUTH_EXEMPT_ENDPOINTS:
        return
    db = get_db()
    email = _resolve_user_email()
    g.user_email = email
    row = db.execute(
        "SELECT * FROM users WHERE LOWER(email) = ?", [email]
    ).fetchone()
    if not row:
        # Fail closed: unknown email → 403, no app access.
        g.current_user = None
        g.allowed_cats = set()
        return Response(
            f"<h1>403 Forbidden</h1>"
            f"<p>Your email ({email}) isn't registered with this app. "
            f"Ask the owner to grant access.</p>",
            status=403, mimetype='text/html'
        )
    g.current_user = dict(row)
    g.allowed_cats = _expand_categories(row['categories'], row['role'])
    # Tenant clamp — even a user with '*' access (e.g. a cross-tenant
    # admin) sees only the tenant's slice on this deployment, so the
    # nav, list views, and pills match what the tenant owner sees.
    if TENANT_CATEGORIES is not None:
        g.allowed_cats = g.allowed_cats & TENANT_CATEGORIES
    # Anything under /admin is owner-only.
    if (request.path or '').startswith('/admin') and \
            g.current_user['role'] != 'owner':
        abort(403)
    # Path-based category gate. Catches both /<category>/... routes and
    # category-prefixed routes like /coins/<id>/lookup-specs.
    if g.current_user['role'] != 'owner':
        first = (request.path or '/').strip('/').split('/', 1)[0]
        if first in CATEGORIES and first not in g.allowed_cats:
            abort(403)


def require_owner():
    """Call inside an owner-only route to 403 non-owners."""
    if not g.get('current_user') or g.current_user.get('role') != 'owner':
        abort(403)


# ---------------------------------------------------------------------------
# Missing-rows import endpoints (coins + watches). Safe to re-run.
# ---------------------------------------------------------------------------

IMPORT_MISSING_SECRET = 'stuffapp-bulk-import-2026'


def _csv_rows(filename):
    import csv, io
    path = os.path.join(BASE_DIR, filename)
    with open(path, 'r', encoding='utf-8-sig') as f:
        content = f.read().replace('\r', '\n')
    return [r for r in csv.reader(io.StringIO(content)) if any(c.strip() for c in r)]


def _mclean(s):
    return (s or '').replace('\x0b', '\n').strip() or None


def _mnum(s, cast=float):
    s = (s or '').strip().replace(',', '').replace('$', '')
    try:
        return cast(s)
    except (ValueError, TypeError):
        return None


def _mdate(s):
    s = (s or '').strip().split(' ')[0]
    if not s:
        return None
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def _mdatetime(s):
    s = (s or '').strip()
    if not s:
        return None
    for fmt in (
        '%m/%d/%Y %I:%M:%S %p', '%m/%d/%Y %I:%M %p',
        '%m/%d/%Y %H:%M:%S', '%m/%d/%Y %H:%M',
        '%Y-%m-%d %H:%M:%S', '%Y-%m-%d',
        '%m/%d/%Y',
    ):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            continue
    return None


@app.route('/admin/import-coins-missing', methods=['POST'])
def import_coins_missing():
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    existing_coin_ids = {r['coin_id'] for r in db.execute(
        "SELECT coin_id FROM coins WHERE coin_id IS NOT NULL AND coin_id != ''")}
    existing_ids = {(r['id'] or '').lower() for r in db.execute("SELECT id FROM coins")}

    inserted = 0
    skipped_existing = 0
    skipped_bad = 0
    now = datetime.utcnow().isoformat()

    for row in _csv_rows('Coin.csv'):
        if len(row) < 45:
            skipped_bad += 1
            continue
        coin_id = _mclean(row[1])
        csv_uuid = _mclean(row[29])
        if coin_id:
            if coin_id in existing_coin_ids:
                skipped_existing += 1
                continue
            record_id = str(uuid.uuid4())
        else:
            if not csv_uuid:
                skipped_bad += 1
                continue
            if csv_uuid.lower() in existing_ids:
                skipped_existing += 1
                continue
            record_id = csv_uuid

        d1_text = row[11].strip().split(' - ', 1)[0].strip() if row[11] else ''

        db.execute('''
            INSERT INTO coins (
                id, coin_id, authority, print_field, notes,
                date_1, date_1_text, date_2, date_2_text,
                denomination, obv_rev, die_axis, grade, metal,
                mint, description, owner, price,
                property_name, purchase_date, coin_references,
                region, sheldon, size, status, strike, surface,
                vendor, weight, created_at, updated_at
            ) VALUES (?,?,?,?,?, ?,?,?,?, ?,?,?,?,?, ?,?,?,?, ?,?,?, ?,?,?,?,?,?, ?,?, ?,?)
        ''', (
            record_id, coin_id, _mclean(row[0]), _mclean(row[2]), _mclean(row[4]),
            _mnum(row[10], int), _mclean(d1_text), _mnum(row[12], int), _mclean(row[13]),
            _mclean(row[14]), _mclean(row[15]), _mclean(row[17]), _mclean(row[18]), _mclean(row[20]),
            _mclean(row[21]), _mclean(row[24]), _mclean(row[27]), _mnum(row[28]),
            _mclean(row[31]), _mdate(row[32]), _mclean(row[34]),
            _mclean(row[35]), _mclean(row[36]), _mnum(row[38]), _mclean(row[39]),
            _mnum(row[40]), _mnum(row[41]), _mclean(row[43]), _mnum(row[44]),
            now, now,
        ))
        inserted += 1
        if coin_id:
            existing_coin_ids.add(coin_id)
        existing_ids.add(record_id.lower())

    db.commit()
    total = db.execute('SELECT COUNT(*) FROM coins').fetchone()[0]
    return jsonify(inserted=inserted, skipped_existing=skipped_existing,
                   skipped_bad=skipped_bad, total=total)


@app.route('/admin/import-watches-missing', methods=['POST'])
def import_watches_missing():
    """Insert any rows from Watch.csv that aren't already in the
    watches table. Dedupe key: (reference, case_num, movement_num).

    `dry=1` reports what WOULD be inserted (brand / model / ref /
    case / mvt / year for each missing row) without writing — useful
    when the live count has dropped to spot-check whether the diff
    is recoverable accidental loss versus intentional deletions you
    DON'T want resurrected. Default behaviour is unchanged: actual
    insert."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    dry = request.form.get('dry') == '1'
    db = get_db()
    existing = set()
    for r in db.execute("SELECT reference, case_num, movement_num FROM watches"):
        existing.add(((r['reference'] or '').strip(),
                      (r['case_num'] or '').strip(),
                      (r['movement_num'] or '').strip()))
    # Secondary index for the no-paperwork CSV rows. Every entry in
    # Watch.csv where all three of (reference, case_num, movement_num)
    # are blank — the vintage / orphan pieces — falls through the
    # primary dedupe (which can't tell ('','','') keys apart) and
    # would otherwise be silently dropped. We also dedupe those by
    # case-insensitive (brand, model) so we restore them once and
    # only once.
    existing_by_brand_model = set()
    for r in db.execute("SELECT brand, model FROM watches"):
        existing_by_brand_model.add(
            ((r['brand'] or '').strip().lower(),
             (r['model'] or '').strip().lower()))

    inserted = 0
    skipped_existing = 0
    skipped_bad = 0
    now = datetime.utcnow().isoformat()
    would_insert = []  # dry-run only

    for row in _csv_rows('Watch.csv'):
        if len(row) < 38:
            skipped_bad += 1
            continue
        reference = _mclean(row[28])
        case_num = _mclean(row[3])
        movement_num = _mclean(row[19])
        key = ((reference or '').strip(), (case_num or '').strip(), (movement_num or '').strip())
        brand_v = _mclean(row[1])
        model_v = _mclean(row[11])
        bm_key = ((brand_v or '').strip().lower(),
                  (model_v or '').strip().lower())

        if not any(key):
            # No-paperwork row — fall back to (brand, model) dedupe.
            # Skip if we can't even identify the piece by name.
            if not (bm_key[0] or bm_key[1]):
                skipped_bad += 1
                continue
            if bm_key in existing_by_brand_model:
                skipped_existing += 1
                continue
        elif key in existing:
            skipped_existing += 1
            continue

        if dry:
            would_insert.append({
                'brand':        brand_v,
                'model':        model_v,
                'reference':    reference,
                'case_num':     case_num,
                'movement_num': movement_num,
                'year':         _mnum(row[37], int),
                'matched_by':   '(brand, model)' if not any(key) else '(ref, case, mvt)',
            })
            if any(key):
                existing.add(key)
            else:
                existing_by_brand_model.add(bm_key)
            continue

        db.execute('''
            INSERT INTO watches (
                id, brand, model, reference, metal, case_diameter,
                dial_color, case_num, movement_num, edition, year,
                calibre, movement_type, movement_origin,
                beat, reserve, complications, clasp_type,
                strap_material, strap_color,
                date, price, vendor, description,
                owner, property, status,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?, ?,?,?,?,?, ?,?,?, ?,?,?,?, ?,?, ?,?,?,?, ?,?,?, ?,?)
        ''', (
            str(uuid.uuid4()),
            _mclean(row[1]), _mclean(row[11]), reference,
            _mclean(row[16]), _mnum(row[4]),
            _mclean(row[12]), case_num, movement_num,
            _mclean(row[15]), _mnum(row[37], int),
            _mclean(row[2]), _mclean(row[22]), _mclean(row[21]),
            _mnum(row[0], int), _mnum(row[13]),
            _mclean(row[6]), _mclean(row[5]),
            _mclean(row[35]), _mclean(row[34]),
            _mdate(row[10]), _mnum(row[25]), _mclean(row[36]), _mclean(row[23]),
            _mclean(row[24]), _mclean(row[27]), _mclean(row[33]),
            now, now,
        ))
        inserted += 1
        if any(key):
            existing.add(key)
        else:
            existing_by_brand_model.add(bm_key)

    if not dry:
        db.commit()
    total = db.execute('SELECT COUNT(*) FROM watches').fetchone()[0]
    return jsonify(inserted=inserted, skipped_existing=skipped_existing,
                   skipped_bad=skipped_bad, total=total,
                   dry_run=dry,
                   would_insert=would_insert if dry else None)


@app.route('/coins/print-pdf')
def coins_print_pdf():
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import mm
    import io

    db = get_db()
    q = (request.args.get('q') or '').strip()
    coin_filter = (request.args.get('filter') or '').strip() or None

    wheres, params = [], []
    if q:
        # Same multi-term AND logic as build_search_query: each
        # whitespace-separated term must match at least one column.
        search_cols = ['coin_id', 'authority', 'region', 'denomination',
                       'mint', 'obv_rev', 'description']
        terms = [t for t in q.split() if t.strip()]
        for term in terms:
            conditions = ' OR '.join([f'{c} LIKE ?' for c in search_cols])
            wheres.append(f"({conditions})")
            params += [f'%{term}%'] * len(search_cols)
    cat_filters = CATEGORY_FILTERS.get('coins', {})
    if coin_filter and coin_filter in cat_filters:
        clause, extra = cat_filters[coin_filter]
        wheres.append(f"({clause})")
        params += list(extra)

    where_sql = f"WHERE {' AND '.join(wheres)}" if wheres else ''
    rows = db.execute(
        f"SELECT * FROM coins {where_sql}", params).fetchall()
    # Recompute display-position bins for the print set: existing C\d+(\w*)
    # bins are preserved; new (no-bin / non-conforming) coins get a letter
    # suffix slotted between their neighbours per region/authority/mint.
    rows, _ = _recompute_coin_bins(db, rows, total=False)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    W, H = letter
    card = 35 * mm  # 35mm square (coin-tray label size)
    gap = 0  # cards abut each other for easier cutting
    cols = int(W // card)
    rows_per_page = int(H // card)
    total_w = cols * card
    total_h = rows_per_page * card
    left = (W - total_w) / 2
    top = (H + total_h) / 2  # top of grid

    per_page = cols * rows_per_page
    for idx, coin in enumerate(rows):
        slot = idx % per_page
        if idx > 0 and slot == 0:
            c.showPage()
        col_i = slot % cols
        row_i = slot // cols
        x = left + col_i * (card + gap)
        y = top - (row_i + 1) * card - row_i * gap
        _draw_coin_card(c, coin, x, y, card, card)
    c.save()
    buf.seek(0)
    return Response(buf.read(), mimetype='application/pdf',
                    headers={'Content-Disposition': 'inline; filename="coins.pdf"'})


COIN_BIN_PREFIXES = ('C', 'CM', 'N', 'NM')
# Alternation order: longer prefixes first so "CM5" hits the CM branch
# instead of C with leftover M5.
COIN_BIN_RE = re.compile(
    r'^(CM|NM|C|N)\s*(\d+)\s*([a-z]*)$',
    re.IGNORECASE,
)


def _parse_coin_bin(s):
    """Return (prefix, numeric, letter_suffix_lower) for a bin matching
    the C / CM / N / NM scheme; None otherwise."""
    if not s:
        return None
    m = COIN_BIN_RE.match(s.strip())
    if not m:
        return None
    return (m.group(1).upper(), int(m.group(2)), (m.group(3) or '').lower())


def _coin_bin_prefix(coin):
    """Bin prefix from property + date_1 — Carp/NY × Ancient/Modern.
    Ancient drops the 'A': Carp Ancient → C, Carp Modern → CM,
    NYC Ancient → N, NYC Modern → NM. None when either axis is
    unmappable (no recognisable property, or no date_1).

    Reads property+date_1 directly rather than parsing cat_id — the
    flat C001..Cn cat_id no longer carries location/era info."""
    p = (coin['property_name'] or '').strip().lower()
    if p in ('carp', 'carpinteria'):
        loc = 'C'
    elif p in ('nyc', 'new york', 'ny'):
        loc = 'N'
    else:
        return None
    d = coin['date_1']
    if d in (None, ''):
        # No date → assume modern (mirrors the cat-id-fixer fallback).
        return loc + 'M'
    try:
        n = int(d)
    except (TypeError, ValueError):
        return None
    return loc if n < 500 else loc + 'M'


def _coin_renumber_sort_key(row):
    """Sort key for display-position renumbering. Empty fields sort last
    so positioned-up coins lead. Case-insensitive on the text fields."""
    return (
        ((row['region'] or '').strip().lower() or 'zzz'),
        ((row['authority'] or '').strip().lower() or 'zzz'),
        ((row['mint'] or '').strip().lower() or 'zzz'),
        ((row['cat_id'] or '').strip().lower() or 'zzz'),
    )


def _recompute_coin_bins(db, rows, total=False):
    """Assign display-position bins partitioned by location/era prefix
    (C / CM / N / NM, derived from property + date_1). Each prefix has
    its own 1..n sequence — Carpinteria Ancient coins are C1, C2, C2a;
    Carpinteria Modern are CM1, CM2, CM2a; NYC follows the same shape
    with N / NM.

    `total=True`: clean reassignment within each prefix group, ordered
    by region / authority / mint / cat_id. Letter suffixes are wiped.

    `total=False` (default — what the print route calls): preserve any
    coin already labelled with a conforming `<prefix><n>(<letters>)?`
    bin. Coins without a conforming bin slot between their neighbours
    with a letter suffix tied to the previous numeric anchor in the
    same prefix group — a Carp-Ancient coin between C15 and C16
    becomes C15a, a second one C15b.

    Special case: when a prefix group has zero conforming bins (first
    run on that group, or after a scheme change) the group is treated
    as a fresh total renumber so coins start at <prefix>1 instead of
    <prefix>0a.

    Returns (sorted_rows_as_dicts, updates_count). Coins with no
    mappable prefix appear in the returned list (in sort order) with
    their existing bin untouched."""
    by_prefix = {p: [] for p in COIN_BIN_PREFIXES}
    no_prefix = []
    for r in rows:
        p = _coin_bin_prefix(r)
        if p:
            by_prefix[p].append(r)
        else:
            no_prefix.append(r)

    out = []
    updates = []
    now = datetime.utcnow().isoformat()

    for prefix in COIN_BIN_PREFIXES:
        group = sorted(by_prefix[prefix], key=_coin_renumber_sort_key)
        if not group:
            continue
        has_conforming = any(
            _parse_coin_bin(r['bin']) and _parse_coin_bin(r['bin'])[0] == prefix
            for r in group
        )
        if total or not has_conforming:
            for i, r in enumerate(group, start=1):
                d = dict(r)
                new_bin = f'{prefix}{i}'
                if (d.get('bin') or '').strip() != new_bin:
                    updates.append((d['id'], new_bin))
                    d['bin'] = new_bin
                out.append(d)
        else:
            prev_anchor = None    # int — last numeric anchor in this prefix
            used_letters = set()  # letters already used at prev_anchor
            for r in group:
                d = dict(r)
                parsed = _parse_coin_bin(d.get('bin'))
                if parsed and parsed[0] == prefix:
                    _, num, letters = parsed
                    canonical = f'{prefix}{num}{letters}'
                    if (d.get('bin') or '').strip() != canonical:
                        updates.append((d['id'], canonical))
                        d['bin'] = canonical
                    if letters:
                        if num == prev_anchor and len(letters) == 1:
                            used_letters.add(letters)
                    else:
                        prev_anchor = num
                        used_letters = set()
                else:
                    letter = None
                    for i in range(26):
                        cand = chr(ord('a') + i)
                        if cand not in used_letters:
                            letter = cand
                            break
                    if letter is None:
                        letter = 'z'
                    base = prev_anchor if prev_anchor is not None else 0
                    new_bin = f'{prefix}{base}{letter}'
                    updates.append((d['id'], new_bin))
                    used_letters.add(letter)
                    d['bin'] = new_bin
                out.append(d)

    for r in sorted(no_prefix, key=_coin_renumber_sort_key):
        out.append(dict(r))

    if updates:
        db.executemany(
            "UPDATE coins SET bin = ?, updated_at = ? WHERE id = ?",
            [(b, now, i) for (i, b) in updates]
        )
        db.commit()
    return out, len(updates)


def _metal_short(metal):
    if not metal:
        return ''
    return metal.split(' ')[0] if ' ' in metal else metal


def _fit_text(c, text, max_width, font_name, font_size):
    from reportlab.pdfbase.pdfmetrics import stringWidth
    if not text:
        return ''
    while text and stringWidth(text, font_name, font_size) > max_width:
        text = text[:-1]
    return text


def _card_image_reader(path):
    """Downscale a source image to ~card size before handing to ReportLab.

    Why: the card prints at 35mm (~414px at 300dpi). Decoding a full-resolution
    source JPEG per coin is the PDF's bottleneck.

    Transparent source images (RGBA / palette-with-alpha) are flattened onto
    a WHITE background — without this, PIL's RGBA→RGB conversion fills
    transparent pixels with black, painting a black square behind every coin.
    """
    from io import BytesIO
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    try:
        im = Image.open(path)
        im.thumbnail((512, 512))
        # Promote palette-with-transparency to RGBA so the alpha-aware
        # branch below catches it.
        if im.mode == 'P' and 'transparency' in im.info:
            im = im.convert('RGBA')
        if im.mode in ('RGBA', 'LA'):
            bg = Image.new('RGB', im.size, (255, 255, 255))
            alpha = im.split()[-1]
            bg.paste(im.convert('RGB'), mask=alpha)
            im = bg
        elif im.mode not in ('RGB', 'L'):
            im = im.convert('RGB')
        buf = BytesIO()
        im.save(buf, format='JPEG', quality=85)
        buf.seek(0)
        return ImageReader(buf)
    except Exception:
        return None


def _coin_date_range_text(d1, d2):
    """Format a coin date range tightly. When both dates share an era
    suffix (BC / BCE / AD / CE), the suffix appears only on the second
    date with no space — e.g. '480 - 440BC' instead of '480 BC - 440 BC'."""
    d1 = (d1 or '').strip()
    d2 = (d2 or '').strip()
    if d1 and d2:
        for era in ('BCE', 'BC', 'CE', 'AD'):
            if d1.upper().endswith(era) and d2.upper().endswith(era):
                d1 = d1[:-len(era)].rstrip()
                d2 = d2[:-len(era)].rstrip() + era
                break
        return f'{d1} - {d2}'
    return d1 or d2


def _format_die_axis(v):
    """Render die axis as '<n>h'. Accepts numeric strings, ints, floats,
    or already-formatted '12h'. Returns '' for blank/unparseable input."""
    if v is None:
        return ''
    s = str(v).strip()
    if not s:
        return ''
    if s.lower().endswith('h'):
        return s
    try:
        f = float(s)
        if f.is_integer():
            return f'{int(f)}h'
        return f'{f:g}h'
    except (TypeError, ValueError):
        return s


def _draw_coin_card(c, coin, x, y, w, h):
    c.setStrokeColorRGB(0.25, 0.25, 0.25)
    c.setLineWidth(0.9)
    c.rect(x, y, w, h, stroke=1, fill=0)

    pad = 3
    inner_w = w - 2 * pad

    # Top-left: region (bold). Falls back to authority when region is blank.
    title = (coin['region'] or coin['authority'] or '').strip()

    # Top-right: tight date range — shared era folds onto the trailing date
    date_range = _coin_date_range_text(coin['date_1_text'], coin['date_2_text'])

    top_y = y + h - pad - 7
    c.setFont('Helvetica-Bold', 7)
    c.drawString(x + pad, top_y, _fit_text(c, title, inner_w * 0.5, 'Helvetica-Bold', 7))
    c.setFont('Helvetica', 7)
    # Wider date allowance so the BC tail isn't truncated.
    c.drawRightString(x + w - pad, top_y, _fit_text(c, date_range, inner_w * 0.55, 'Helvetica', 7))

    # Description (obv_rev), full-width under title — 7pt to match the
    # date and the right-side spec stack.
    obv = (coin['obv_rev'] or '').strip()
    desc_y = top_y - 9
    if obv:
        c.setFont('Helvetica', 7)
        c.drawString(x + pad, desc_y, _fit_text(c, obv, inner_w, 'Helvetica', 7))

    # Bottom-right ident: "<cat_id> / <bin>" — cat_id regular, bin bold.
    # The display-position bin is the visually distinguishing handle when
    # locating a card in a tray, so it gets the weight.
    from reportlab.pdfbase.pdfmetrics import stringWidth
    bin_label = (coin['bin'] or '').strip()
    if bin_label:
        bin_label = re.sub(r'\s+', '', bin_label)
    cat_id = (coin['cat_id'] or '').strip()

    bottom_y = y + pad
    ident_font_size = 7
    right_x = x + w - pad
    if bin_label and cat_id:
        c.setFont('Helvetica-Bold', ident_font_size)
        c.drawRightString(right_x, bottom_y, bin_label)
        bold_w = stringWidth(bin_label, 'Helvetica-Bold', ident_font_size)
        prefix = f'{cat_id} / '
        c.setFont('Helvetica', ident_font_size)
        c.drawRightString(right_x - bold_w, bottom_y,
                          _fit_text(c, prefix, inner_w - bold_w,
                                    'Helvetica', ident_font_size))
    else:
        fallback = bin_label or cat_id or (coin['coin_id'] or '').strip()
        if fallback:
            c.setFont('Helvetica-Bold', ident_font_size)
            c.drawRightString(right_x, bottom_y,
                              _fit_text(c, fallback, inner_w,
                                        'Helvetica-Bold', ident_font_size))

    # Middle area: image (left) + specs stack (right). Bottom row holds the
    # ident, so the image bottom must clear it.
    mid_top = desc_y - 3
    mid_bottom = bottom_y + 9
    mid_h = mid_top - mid_bottom
    if mid_h < 10:
        return
    # Image takes ~62% of card width — coin renders ~58pt across, up
    # from ~52pt before. Spec column still has ~38% (≈34pt).
    img_w = w * 0.62

    # Image
    img_path = None
    for fld in ('image_1', 'image_2'):
        if coin[fld]:
            p = os.path.join(UPLOAD_FOLDER, coin[fld])
            if os.path.exists(p):
                img_path = p
                break
    if img_path:
        reader = _card_image_reader(img_path)
        if reader:
            try:
                c.drawImage(reader, x + pad, mid_bottom,
                            width=img_w - pad, height=mid_h,
                            preserveAspectRatio=True, mask='auto')
            except Exception:
                pass

    # Right-side specs (top-down): denomination, metal, mint, weight, mm, die axis.
    # Font bumps to 7pt; "Tetradrachm" is the widest typical denomination
    # and still fits the 34pt spec column at this size.
    specs = []
    if coin['denomination']: specs.append(coin['denomination'].strip())
    m = _metal_short(coin['metal'])
    if m: specs.append(m)
    if coin['mint']: specs.append(coin['mint'].strip())
    if coin['weight'] is not None: specs.append(f"{coin['weight']:.2f}g")
    if coin['size'] is not None: specs.append(f"{coin['size']:.1f}mm")
    da = _format_die_axis(coin['die_axis'])
    if da: specs.append(da)

    spec_font_size = 7
    c.setFont('Helvetica', spec_font_size)
    spec_count = len(specs)
    if spec_count:
        spec_w = w - img_w - pad
        # Squeeze line-height when there are many specs.
        step = min(9, max(7, mid_h / max(spec_count, 1)))
        # Vertically center the stack on the image. Total visible height ≈
        # last-baseline → first-cap = (count-1)*step + font_size; the empty
        # band above gets half the leftover so the column visually balances.
        stack_height = (spec_count - 1) * step + spec_font_size
        top_offset = max(0, (mid_h - stack_height) / 2)
        sy = mid_top - top_offset - spec_font_size
        for s in specs:
            c.drawRightString(x + w - pad,
                              sy,
                              _fit_text(c, s, spec_w, 'Helvetica', spec_font_size))
            sy -= step


@app.route('/admin/status-owned-to-own', methods=['POST'])
def status_owned_to_own():
    """Rename status='Owned' -> 'Own' across every table that has a status column."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    tables = [r['name'] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    per_table = {}
    total = 0
    for t in tables:
        cols = [r['name'] for r in db.execute(f"PRAGMA table_info({t})").fetchall()]
        if 'status' in cols:
            r = db.execute(
                f"UPDATE {t} SET status='Own' "
                "WHERE LOWER(TRIM(COALESCE(status, ''))) = 'owned'"
            )
            if r.rowcount:
                per_table[t] = r.rowcount
            total += r.rowcount
    db.commit()
    return jsonify(updated=total, per_table=per_table)


@app.route('/admin/dedupe-watches', methods=['POST'])
def dedupe_watches():
    """Collapse watch duplicates created by sweep auto-create when the
    matcher couldn't see "A. Lange & Söhne" and "A. Lange Sohne" as the
    same brand. Groups rows by (_norm(brand), _norm(model), _norm(ref))
    so spelling drift (diacritics, ampersands, dots) collapses into one
    bucket.

    Winner per group = the row with the most non-NULL fields (the
    "original" rich record). Tiebreaker: the spelling with more
    diacritics + ampersands. Sibling fields fill in where the winner
    is NULL — never overwrites real data — and siblings are deleted.

    Default: dry-run. Pass ?dry=0 to actually merge + delete.
    Always returns a JSON report of what was (or would be) done."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    dry = request.args.get('dry', '1') != '0'
    db = get_db()
    cols = [c['name'] for c in db.execute("PRAGMA table_info(watches)").fetchall()]
    rows = [dict(r) for r in db.execute("SELECT * FROM watches").fetchall()]

    groups = {}
    for r in rows:
        key = (_norm(r.get('brand') or ''),
               _norm(r.get('model') or ''),
               _norm(r.get('reference') or ''))
        # Skip empty-brand rows — too risky to merge blind, the user
        # should look at those manually.
        if not key[0]:
            continue
        groups.setdefault(key, []).append(r)

    def fancy_count(s):
        """Diacritics + ampersands — markers of the canonical spelling."""
        s = s or ''
        return sum(1 for c in s if (not c.isascii()) or c == '&')

    def score(m):
        """Higher = better winner."""
        non_null = sum(1 for c in cols
                       if m.get(c) not in (None, '', 0))
        brand = m.get('brand') or ''
        return (non_null, fancy_count(brand), len(brand))

    actions = []
    rows_deleted = 0
    fields_filled = 0
    brands_canonicalized = 0
    for key, members in groups.items():
        if len(members) < 2:
            continue
        members.sort(key=score, reverse=True)
        winner = members[0]
        siblings = members[1:]

        # Canonical brand for the group = the spelling with the most
        # diacritics + ampersands across ALL members. Picks
        # "A. Lange & Söhne" over "A. Lange Sohne" even when the
        # richest-data row carries the impoverished spelling.
        canonical_brand = max(
            (m.get('brand') or '' for m in members),
            key=lambda b: (fancy_count(b), len(b)),
        )
        brand_change = None
        if canonical_brand and (winner.get('brand') or '') != canonical_brand:
            brand_change = {'from': winner.get('brand'), 'to': canonical_brand}
            winner['brand'] = canonical_brand
            brands_canonicalized += 1

        merge_updates = {}
        if brand_change:
            merge_updates['brand'] = canonical_brand
        for sib in siblings:
            for c in cols:
                if c in ('id', 'created_at'):
                    continue
                w = winner.get(c)
                if w in (None, '') and sib.get(c) not in (None, ''):
                    merge_updates[c] = sib[c]
                    winner[c] = sib[c]  # prevent later siblings overwriting

        actions.append({
            'norm_key':       ' | '.join(key),
            'winner_id':      winner['id'],
            'winner_brand':   winner.get('brand'),
            'winner_model':   winner.get('model'),
            'winner_ref':     winner.get('reference'),
            'sibling_ids':    [s['id'] for s in siblings],
            'sibling_brands': [s.get('brand') for s in siblings],
            'brand_change':   brand_change,
            'fields_filled':  sorted(merge_updates.keys()),
        })
        rows_deleted += len(siblings)
        fields_filled += len(merge_updates)

        if not dry:
            if merge_updates:
                set_sql = ', '.join(f"{c} = ?" for c in merge_updates)
                db.execute(
                    f"UPDATE watches SET {set_sql}, updated_at = ? WHERE id = ?",
                    list(merge_updates.values())
                    + [datetime.utcnow().isoformat(), winner['id']]
                )
            for sib in siblings:
                db.execute("DELETE FROM watches WHERE id = ?", [sib['id']])

    if not dry:
        db.commit()

    return jsonify({
        'dry_run':              dry,
        'groups_with_dupes':    len(actions),
        'rows_would_delete':    rows_deleted,
        'fields_would_fill':    fields_filled,
        'brands_canonicalized': brands_canonicalized,
        'actions':              actions,
    })


@app.route('/admin/canonicalize-watch-brands', methods=['POST'])
def canonicalize_watch_brands():
    """Standalone brand-spelling cleanup for watches that already
    DON'T have duplicates — i.e., a single row whose brand is spelled
    "A. Lange Sohne" when the canonical name is "A. Lange & Söhne".

    Groups every watch by _norm(brand). For each normalized group,
    picks the spelling with the most diacritics + ampersands as
    canonical and rewrites every row in the group to use it.

    Defaults to dry-run; pass ?dry=0 to apply.

    Note: dedupe-watches already canonicalizes brand for groups it
    collapses; this endpoint covers the rest."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    dry = request.args.get('dry', '1') != '0'
    db = get_db()
    rows = [dict(r) for r in db.execute(
        "SELECT id, brand FROM watches WHERE COALESCE(brand, '') != ''"
    ).fetchall()]

    def fancy_count(s):
        s = s or ''
        return sum(1 for c in s if (not c.isascii()) or c == '&')

    groups = {}
    for r in rows:
        groups.setdefault(_norm(r['brand']), []).append(r)

    actions = []
    rows_changed = 0
    for nb, members in groups.items():
        if not nb:
            continue
        canonical = max(
            (m['brand'] for m in members),
            key=lambda b: (fancy_count(b), len(b)),
        )
        affected = [m for m in members if m['brand'] != canonical]
        if not affected:
            continue
        actions.append({
            'norm_brand':     nb,
            'canonical':      canonical,
            'rows_changed':   len(affected),
            'sample_changes': sorted({(m['brand'], canonical) for m in affected}),
        })
        rows_changed += len(affected)
        if not dry:
            for m in affected:
                db.execute(
                    "UPDATE watches SET brand = ?, updated_at = ? WHERE id = ?",
                    [canonical, datetime.utcnow().isoformat(), m['id']],
                )
    if not dry:
        db.commit()
    return jsonify({
        'dry_run':       dry,
        'groups_fixed':  len(actions),
        'rows_changed':  rows_changed,
        'actions':       actions,
    })


@app.route('/admin/watches-needing-relocation', methods=['GET'])
def watches_needing_relocation():
    """Diagnostic: list every watch whose status is Ordered, Loaned, or
    Consigned. Before the bucket-fix commit these routed under
    StuffFiles/Watches/No longer Owned/<brand>/ on disk; from now on
    they land in the main Watches/<brand>/ folder. Auto-purge is off,
    so the old copies stay behind for manual cleanup — this endpoint
    tells the user exactly which folders to drag to the Trash."""
    user = g.get('current_user') or {}
    if user.get('role') != 'owner':
        abort(403)
    db = get_db()
    rows = db.execute(
        "SELECT * FROM watches "
        "WHERE LOWER(TRIM(COALESCE(status,''))) IN ('ordered','loaned','consigned') "
        "ORDER BY brand COLLATE NODIACRITIC"
    ).fetchall()
    plan = EXPORT_LAYOUT['watches']
    file_specs = plan['files']           # [(field, default_label, title_field), …]
    docs_cols  = _docs_cols_for('watches') or []
    affected = []
    file_count = 0
    for r in rows:
        brand_raw = plan['group'](r)
        ident_raw = plan['ident'](r)
        # _safe_path matches what the actual export does — accents and
        # punctuation get sanitized identically so the paths reported
        # here are byte-equal to what's actually on disk.
        brand_safe, ident_safe = _safe_path(brand_raw, ident_raw)

        files = []

        def _emit(label, fname):
            """Build the same '<ident> — <label><ext>' leaf the export
            writes, then pair the No-longer-Owned path (where it lives
            now) with the main path (where the next sync will land it)."""
            if not fname:
                return
            label_safe = _safe_path(label)[0]
            ext = os.path.splitext(fname)[1] or ''
            leaf = (f'{ident_safe} — {label_safe}{ext}'
                    if label_safe else f'{ident_safe}{ext}')
            files.append({
                'label':    label_safe or label,
                'old_path': f'StuffFiles/Watches/No longer Owned/{brand_safe}/{leaf}',
                'new_path': f'StuffFiles/Watches/{brand_safe}/{leaf}',
            })

        # Fixed file slots (image_obv / image_rev / receipt). Mirrors
        # the per-row dedupe in the export so the same upload referenced
        # from two columns is reported once.
        seen = set()
        for field, default_label, title_field in file_specs:
            try:
                fname = (r[field] or '').strip()
            except (KeyError, IndexError):
                continue
            if not fname or fname in seen:
                continue
            seen.add(fname)
            label = default_label
            if title_field:
                try:
                    t = (r[title_field] or '').strip()
                    if t:
                        label = t
                except (KeyError, IndexError):
                    pass
            _emit(label, fname)

        # JSON-column documents (e.g. the `documents` array on watches).
        for json_col in docs_cols:
            try:
                raw = r[json_col]
            except (KeyError, IndexError):
                continue
            try:
                docs = json.loads(raw or '[]')
            except (TypeError, ValueError):
                docs = []
            if not isinstance(docs, list):
                continue
            for i, d in enumerate(docs, 1):
                if not isinstance(d, dict):
                    continue
                fname = (d.get('filename') or '').strip()
                if not fname:
                    continue
                label = (d.get('title') or '').strip() or f'Doc {i}'
                _emit(label, fname)

        file_count += len(files)
        affected.append({
            'brand':  brand_safe,
            'ident':  ident_safe,
            'status': r['status'],
            'files':  files,
        })
    return jsonify(watch_count=len(affected),
                   file_count=file_count,
                   affected=affected)


def _backfill_serial_cat_ids(table, prefix):
    """Assign cat_ids to every row in `table` that doesn't have one,
    using the same flat W###/A### scheme as live inserts. Walks rows
    deterministically (id ASC) so re-runs are stable. Returns
    (assigned_count, sample_assignments).

    Side effect to flag to the user before running: every record that
    gets a fresh cat_id will have its file path in StuffFiles change
    on the next sync (because EXPORT_LAYOUT prefers cat_id when set).
    Old paths stay on disk for manual cleanup since auto-purge is
    off — typically dozens-to-hundreds of orphaned files."""
    db = get_db()
    rows = db.execute(
        f"SELECT id FROM {table} WHERE COALESCE(cat_id, '') = '' "
        f"ORDER BY id"
    ).fetchall()
    sample = []
    assigned = 0
    for r in rows:
        new_id = next_serial_cat_id(db, table, prefix)
        db.execute(
            f"UPDATE {table} SET cat_id = ?, updated_at = ? WHERE id = ?",
            (new_id, datetime.utcnow().isoformat(timespec='seconds'), r['id']),
        )
        if len(sample) < 10:
            sample.append({'id': r['id'], 'cat_id': new_id})
        assigned += 1
    db.commit()
    return assigned, sample


# F.P. Journe calibre details from the Perplexity research dump.
# Keys are exact calibre strings except where match_prefix=True (1499.x
# family covers all Résonance variants). Targeting is brand-scoped to
# anything matching F.P. Journe so we don't accidentally overwrite a
# non-Journe watch that happens to share a calibre number.
JOURNE_CALIBRE_DETAILS = {
    '1498': {
        'escapement': 'Straight-line lever escapement',
        'balance_wheel': '15-tooth wheel, 90° anchor fork',
        'calibre_notes': "Classic Swiss-lever-type in a horizontal straight line; tourbillon + remontoir d'égalité, dead seconds.",
    },
    '1403': {
        'escapement': 'Straight-line lever escapement',
        'balance_wheel': '15-tooth wheel, 90° anchor fork',
        'calibre_notes': 'Evolves 1498: tourbillon + 1-sec remontoir + dead seconds; straight-line Swiss-lever-type.',
    },
    '1412': {
        'escapement': 'Pallet escapement',
        'balance_wheel': '15-tooth escape wheel',
        'calibre_notes': 'Lateral pallet (lever) escapement in Breguet-style architecture; two barrels in parallel.',
    },
    '1408': {
        'escapement': 'Linear escapement',
        'balance_wheel': '15-tooth escape wheel',
        'calibre_notes': 'Linear escapement with 15-tooth escape wheel; going train tucked under the dial, escapement visually isolated.',
    },
    '1505': {
        'escapement': 'Linear escapement',
        'balance_wheel': '15-tooth escape wheel',
        'calibre_notes': 'Linear escapement with 15-tooth escape wheel; hand-wound grande/petite sonnerie with specific safety architecture.',
    },
    '1300.3': {
        'escapement': 'In-line (linear) lever escapement',
        'balance_wheel': '15-tooth wheel',
        'calibre_notes': 'Automatic Octa base, long-reserve architecture; in-line lever escapement in gold movement.',
    },
    '1510': {
        'escapement': 'EBHP "High-Performance Bi-axial" escapement',
        'balance_wheel': 'Twin wheels; bi-axial direct impulse',
        'calibre_notes': 'Dual-escape-wheel direct-impulse escapement, oil-free, with constant-force remontoir and natural dead-beat seconds.',
    },
    '1519': {
        'escapement': 'Straight-line lever escapement',
        'balance_wheel': '15-tooth wheel, 90° anchor fork',
        'calibre_notes': 'Vertical tourbillon with remontoir and dead seconds; straight-line Swiss-lever-type escapement.',
    },
    '1304': {
        'escapement': 'Swiss lever escapement',
        'balance_wheel': 'Standard Swiss lever',
        'calibre_notes': 'Time-only, twin barrels in parallel feeding a classic detached lever escapement in a very flat architecture.',
    },
    '1499': {  # match_prefix — covers all 1499.x Résonance variants
        'escapement': 'Straight-line lever escapements (x2)',
        'balance_wheel': 'Swiss lever for each train',
        'calibre_notes': 'Two balances in resonance, each with its own straight-line lever escapement.',
        'match_prefix': True,
    },
    '1518': {
        'escapement': 'Swiss lever escapement',
        'balance_wheel': 'Swiss lever',
        'calibre_notes': 'High-beat integrated rattrapante chronograph in LineSport; classic lever escapement.',
    },
    '1619': {
        'escapement': 'Swiss lever escapement + tourbillon',
        'balance_wheel': 'Tourbillon + Swiss-lever-type escapement',
        'calibre_notes': 'Grand complication with tourbillon; Journe does not detail a special escapement, so it is a tourbillon with lever.',
    },
    '1520': {
        'escapement': 'Lever escapement with remontoir',
        'balance_wheel': 'Lever escapement, constant-force system',
        'calibre_notes': 'Evolution of the tourbillon architecture with remontoir; classic lever escapement in the cage.',
    },
}


@app.route('/admin/normalize-watch-brand-unicode', methods=['POST'])
def normalize_watch_brand_unicode():
    """One-shot: NFC-normalize every watch's brand string so pre-composed
    and decomposed Unicode variants of the same name (e.g. 'Urban
    Jürgensen' as U+00FC vs U+0075+U+0308) collapse to one canonical
    form. Without this, two visually-identical brand entries can
    diverge in the data and fragment lookups.

    Defaults to dry-run; pass ?dry=0 to actually apply. Always returns
    the list of rows where NFC would change the brand, so you can
    review before committing."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    import unicodedata as _ud
    dry = request.args.get('dry', '1') != '0'
    db = get_db()
    rows = db.execute(
        "SELECT id, brand FROM watches WHERE brand IS NOT NULL AND brand != ''"
    ).fetchall()
    diffs = []
    for r in rows:
        original = r['brand']
        canonical = _ud.normalize('NFC', original)
        if canonical != original:
            diffs.append({
                'id': r['id'],
                'before': original,
                'before_codepoints': [hex(ord(c)) for c in original],
                'after': canonical,
                'after_codepoints': [hex(ord(c)) for c in canonical],
            })
            if not dry:
                db.execute(
                    "UPDATE watches SET brand = ?, updated_at = ? WHERE id = ?",
                    (canonical,
                     datetime.utcnow().isoformat(timespec='seconds'),
                     r['id'])
                )
    if not dry:
        db.commit()
    return jsonify(dry=dry, count=len(diffs), changes=diffs)


@app.route('/admin/seed-journe-calibres', methods=['POST'])
def seed_journe_calibres():
    """One-shot: overwrite escapement / balance_wheel / calibre_notes
    on every F.P. Journe watch whose calibre matches one of the
    families documented in JOURNE_CALIBRE_DETAILS. Targeting is
    brand-scoped (TRIM/LOWER contains 'journe') and either exact-match
    or prefix-match per entry, so a 1499.x Résonance variant isn't
    skipped just because of a sub-version suffix.

    Returns matched / updated lists with before/after for spot checks,
    plus 'unmatched_calibres' so the caller can see which families
    didn't land on any owned record."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    now = datetime.utcnow().isoformat(timespec='seconds')

    journe_rows = db.execute(
        "SELECT id, brand, model, calibre, escapement, balance_wheel, "
        "       calibre_notes "
        "FROM watches "
        "WHERE LOWER(TRIM(COALESCE(brand,''))) LIKE '%journe%'"
    ).fetchall()

    updated = []
    matched_keys = set()
    skipped = []
    for r in journe_rows:
        cal = (r['calibre'] or '').strip()
        if not cal:
            skipped.append({'id': r['id'], 'brand': r['brand'],
                            'model': r['model'],
                            'reason': 'no calibre on record'})
            continue
        # First pass: exact match. Second pass: prefix match for entries
        # flagged match_prefix=True (e.g. 1499.x family).
        match_key = None
        if cal in JOURNE_CALIBRE_DETAILS:
            match_key = cal
        else:
            for k, v in JOURNE_CALIBRE_DETAILS.items():
                if v.get('match_prefix') and cal.startswith(k):
                    match_key = k
                    break
        if not match_key:
            skipped.append({'id': r['id'], 'brand': r['brand'],
                            'model': r['model'], 'calibre': cal,
                            'reason': 'calibre not in seed table'})
            continue
        d = JOURNE_CALIBRE_DETAILS[match_key]
        before = {'escapement': r['escapement'],
                  'balance_wheel': r['balance_wheel'],
                  'calibre_notes': r['calibre_notes']}
        after = {'escapement': d['escapement'],
                 'balance_wheel': d['balance_wheel'],
                 'calibre_notes': d['calibre_notes']}
        db.execute(
            "UPDATE watches SET escapement=?, balance_wheel=?, "
            "       calibre_notes=?, updated_at=? WHERE id=?",
            (after['escapement'], after['balance_wheel'],
             after['calibre_notes'], now, r['id'])
        )
        matched_keys.add(match_key)
        updated.append({'id': r['id'], 'brand': r['brand'],
                        'model': r['model'], 'calibre': cal,
                        'matched_via': match_key,
                        'before': before, 'after': after})
    db.commit()
    unmatched_calibres = sorted(set(JOURNE_CALIBRE_DETAILS.keys()) - matched_keys)
    return jsonify(updated=updated, skipped=skipped,
                   unmatched_calibres=unmatched_calibres,
                   total_journe_watches=len(journe_rows),
                   total_updated=len(updated))


@app.route('/admin/watches-backfill-cat-ids', methods=['POST'])
def watches_backfill_cat_ids():
    """One-shot: assign W### cat_ids to every watch missing one. After
    running, every backfilled watch's file path in StuffFiles changes
    on the next sync — the new path uses cat_id, the old path stays
    behind for manual cleanup."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    assigned, sample = _backfill_serial_cat_ids('watches', 'W')
    return jsonify(assigned=assigned, sample=sample)


WATCH_BULK_LOOKUP_FIELDS = (
    'calibre', 'movement_jewels', 'movement_origin', 'escapement', 'beat',
)


@app.route('/admin/watches-bulk-lookup', methods=['POST'])
def watches_bulk_lookup():
    """Walk every watch (with enough identity to be looked up) and use
    the AI watch lookup to OVERWRITE calibre / jewels / origin /
    escapement / beat with whatever the lookup returns. Re-runs
    progress oldest-first — we order by updated_at ASC, and each
    successful update bumps the row's updated_at to now, so processed
    rows naturally fall to the back of the queue. Just keep calling
    until the report says everything in scope was attempted.

    Form params:
      secret  – IMPORT_MISSING_SECRET
      limit   – max watches per call (default 5). gunicorn has a 300s
                timeout and each lookup is 30-90s, so 5-10 is the
                realistic ceiling per request. Loop the call from a
                shell to chew through the rest.
      dry     – '1' to fetch from AI but skip the UPDATE (preview the
                changes without committing them).

    Overwrite semantics: a non-null AI suggestion replaces any
    existing value. AI null means "I don't know" — never wipes. Beat
    still gets the canonical-snap sanity check (Manual/Automatic snap
    to {18000…72000}; everything else accepts any positive integer)."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    try:
        limit = int(request.form.get('limit', '5'))
    except ValueError:
        limit = 5
    limit = max(1, limit)
    dry = request.form.get('dry') == '1'

    db = get_db()
    # Need brand/model/reference to even attempt a lookup — rows with
    # none of those can't be identified online, so skip them. Order by
    # updated_at ASC so re-runs progress through the queue oldest-first
    # (each successful update bumps updated_at → row drops to the back).
    rows = db.execute(
        "SELECT * FROM watches "
        "WHERE COALESCE(brand,'') != '' OR COALESCE(model,'') != '' "
        "   OR COALESCE(reference,'') != '' "
        "ORDER BY COALESCE(updated_at, '') ASC "
        "LIMIT ?",
        (limit,),
    ).fetchall()

    mech_allowed = {18000, 19800, 21600, 25200, 28800, 36000, 72000}

    report = {
        'attempted': len(rows),
        'updated':   [],
        'unchanged': [],
        'failed':    [],
    }

    for r in rows:
        watch_id = r['id']
        label = ' / '.join(x for x in [
            (r['brand'] or '').strip(),
            (r['model'] or '').strip(),
        ] if x) or watch_id[:8]

        try:
            suggestions = fetch_watch_specs(r)
        except Exception as e:
            report['failed'].append({
                'id':    watch_id, 'label': label,
                'error': (str(e) or e.__class__.__name__)[:200],
            })
            continue

        applied = {}
        for f in WATCH_BULK_LOOKUP_FIELDS:
            sug = suggestions.get(f)
            if sug in (None, ''):
                continue
            # Beat sanity: snap to canonical for mechanical, accept any
            # positive integer for non-mechanical (Quartz, Tuning Fork,
            # Spring Drive, Co-Axial). Mirrors the single-watch path.
            if f == 'beat':
                try:
                    n = float(sug)
                except (TypeError, ValueError):
                    continue
                if n <= 0:
                    continue
                mt = (suggestions.get('movement_type')
                      or (r['movement_type'] or '')).strip()
                if mt in ('Manual', 'Automatic'):
                    if 0 < n < 100:  # source quoted Hz
                        n = n * 7200
                    sug = int(round(n))
                    if sug not in mech_allowed:
                        continue
                else:
                    sug = int(round(n))
            # Overwrite mode: apply any non-null AI suggestion regardless
            # of the existing value. AI null is filtered out above.
            applied[f] = sug

        if not applied:
            report['unchanged'].append({'id': watch_id, 'label': label})
            continue

        if not dry:
            sets = ', '.join(f"{k} = ?" for k in applied)
            params = (list(applied.values())
                      + [datetime.utcnow().isoformat(timespec='seconds'),
                         watch_id])
            try:
                db.execute(
                    f"UPDATE watches SET {sets}, updated_at = ? WHERE id = ?",
                    params,
                )
                db.commit()
            except Exception as e:
                report['failed'].append({
                    'id':    watch_id, 'label': label,
                    'error': f'update failed: {e}',
                })
                continue

        report['updated'].append({
            'id':      watch_id,
            'label':   label,
            'applied': applied,
        })

    # Total identifiable watches in scope. With overwrite semantics
    # there's no "done" condition — the same row could in principle be
    # re-processed forever — so we just report how many haven't been
    # touched in the longest. Use the oldest updated_at still in the
    # candidate pool as a freshness anchor: when that timestamp is
    # newer than your batch's start, you've cycled the whole library.
    in_scope = db.execute(
        "SELECT COUNT(*) AS n FROM watches "
        "WHERE COALESCE(brand,'') != '' OR COALESCE(model,'') != '' "
        "OR COALESCE(reference,'') != ''"
    ).fetchone()['n']
    oldest = db.execute(
        "SELECT MIN(COALESCE(updated_at, '')) AS t FROM watches "
        "WHERE COALESCE(brand,'') != '' OR COALESCE(model,'') != '' "
        "OR COALESCE(reference,'') != ''"
    ).fetchone()['t']
    report['in_scope'] = in_scope
    report['oldest_updated_at'] = oldest or None
    return jsonify(report)


@app.route('/admin/art-backfill-cat-ids', methods=['POST'])
def art_backfill_cat_ids():
    """One-shot: assign A### cat_ids to every art piece missing one.
    Same disk-side caveat as watches-backfill-cat-ids."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    assigned, sample = _backfill_serial_cat_ids('art', 'A')
    return jsonify(assigned=assigned, sample=sample)


@app.route('/admin/recordings-collisions', methods=['GET'])
def recordings_collisions():
    """Diagnostic: count (artist, title) pairs that appear more than
    once in recordings — the situations a cat_id rollout would
    disambiguate. Comparison is case-insensitive and trims whitespace
    so 'Live' vs 'live ' don't read as distinct.

    Output:
      total_rows          — every row in recordings
      colliding_rows      — rows whose (artist,title) is non-unique
      colliding_groups    — number of distinct duplicated pairs
      pct_colliding       — colliding_rows / total_rows
      worst               — top 20 pairs by row count, with sample IDs
    """
    user = g.get('current_user') or {}
    if user.get('role') != 'owner':
        abort(403)
    db = get_db()
    total = db.execute("SELECT COUNT(*) AS n FROM recordings").fetchone()['n']
    rows = db.execute(
        "SELECT id, "
        "       LOWER(TRIM(COALESCE(artist,''))) AS a, "
        "       LOWER(TRIM(COALESCE(title,'')))  AS t, "
        "       artist, title "
        "FROM recordings"
    ).fetchall()
    buckets = {}
    for r in rows:
        key = (r['a'], r['t'])
        buckets.setdefault(key, {'artist': r['artist'], 'title': r['title'],
                                 'ids': []})['ids'].append(r['id'])
    dup_groups = [b for b in buckets.values() if len(b['ids']) > 1]
    colliding_rows = sum(len(b['ids']) for b in dup_groups)
    dup_groups.sort(key=lambda b: (-len(b['ids']),
                                   (b['artist'] or '').lower(),
                                   (b['title'] or '').lower()))
    worst = [
        {'artist': b['artist'], 'title': b['title'],
         'count': len(b['ids']), 'ids': b['ids'][:5]}
        for b in dup_groups[:20]
    ]
    return jsonify(
        total_rows=total,
        colliding_rows=colliding_rows,
        colliding_groups=len(dup_groups),
        pct_colliding=round(100 * colliding_rows / total, 1) if total else 0,
        worst=worst,
    )


@app.route('/admin/coins-fix-missing-cat-id', methods=['POST'])
def coins_fix_missing_cat_id():
    """Assign cat_id to any coin missing one. _cat_id_prefix wants both
    a mappable property and a date; if date_1 is empty we fall back to
    era='M' (modern) — safe for US Mint coins, the typical case where
    this gap shows up. Rows whose property isn't mappable are reported
    but skipped so the caller can fix them by hand.

    Defaults to dry-run; pass ?dry=0 to actually apply."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    dry = request.args.get('dry', '1') != '0'
    db = get_db()
    rows = db.execute(
        "SELECT id, property_name, date_1, region, authority, "
        "       denomination FROM coins WHERE COALESCE(cat_id, '') = ''"
    ).fetchall()

    # Per-prefix counter so multiple rows in this batch don't all get
    # the same next-number; works correctly in dry-run too.
    prefix_counters = {}

    def _seed_counter(prefix):
        cur = db.execute(
            "SELECT cat_id FROM coins WHERE cat_id LIKE ? "
            "ORDER BY CAST(SUBSTR(cat_id, 3) AS INTEGER) DESC LIMIT 1",
            [f'{prefix}%']
        ).fetchone()
        n = 1
        if cur and cur['cat_id']:
            try:
                n = int(cur['cat_id'][2:]) + 1
            except ValueError:
                n = 1
        prefix_counters[prefix] = n

    actions = []
    skipped = []
    for r in rows:
        prop = r['property_name']
        date = r['date_1']
        prefix = _cat_id_prefix(prop, date) if (date not in (None, '')) else None
        used_fallback = False
        if prefix is None:
            p = (prop or '').strip().lower()
            if p in ('carp', 'carpinteria'):
                prefix = 'CM'
                used_fallback = True
            elif p in ('nyc', 'new york', 'ny'):
                prefix = 'NM'
                used_fallback = True
            else:
                skipped.append({
                    'id': r['id'],
                    'reason': f"property '{prop}' not mappable",
                    'region': r['region'],
                    'denomination': r['denomination'],
                })
                continue
        if prefix not in prefix_counters:
            _seed_counter(prefix)
        n = prefix_counters[prefix]
        prefix_counters[prefix] = n + 1
        new_cat_id = f'{prefix}{n:03d}'
        actions.append({
            'id':                r['id'],
            'region':            r['region'],
            'authority':         r['authority'],
            'denomination':      r['denomination'],
            'property':          prop,
            'date_1':            date,
            'cat_id':            new_cat_id,
            'used_fallback_era': used_fallback,
        })
        if not dry:
            db.execute(
                "UPDATE coins SET cat_id = ?, updated_at = ? WHERE id = ?",
                [new_cat_id, datetime.utcnow().isoformat(), r['id']]
            )

    if not dry:
        db.commit()

    return jsonify({
        'dry_run':                  dry,
        'rows_with_missing_cat_id': len(rows),
        'assigned':                 len(actions),
        'skipped':                  len(skipped),
        'actions':                  actions,
        'skipped_rows':             skipped,
    })


@app.route('/admin/coins-renumber-cat-ids', methods=['POST'])
def coins_renumber_cat_ids():
    """Total renumber of every coin's cat_id to a flat C001..Cn series.

    cat_id is the unchanging serial — once assigned to a coin it stays
    with that coin. This endpoint exists for the one-time switch from
    the old per-(location,era) partition (CA/CM/NA/NM) to the unified
    'C' prefix. After this runs, NEW coins pick up via next_cat_id().

    Order: region / authority / mint / existing-cat_id, so the new
    serial roughly tracks the printed-card reading order at renumber
    time. Coins where every sort field is blank go to the end."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    rows = db.execute("SELECT * FROM coins").fetchall()
    sorted_rows = sorted(rows, key=_coin_renumber_sort_key)
    updated = 0
    now = datetime.utcnow().isoformat()
    for i, r in enumerate(sorted_rows, start=1):
        new_cat = f'C{i:03d}'
        if (r['cat_id'] or '').strip() != new_cat:
            db.execute(
                "UPDATE coins SET cat_id = ?, updated_at = ? WHERE id = ?",
                [new_cat, now, r['id']]
            )
            updated += 1
    db.commit()
    return jsonify(total=len(sorted_rows), updated=updated)


@app.route('/admin/coins-renumber-bins', methods=['POST'])
def coins_renumber_bins():
    """Total renumber of coin display-position bins. Sorts every coin by
    region, authority, mint, cat_id and reassigns C1..Cn from scratch.
    Wipes any letter-suffix inserts the print-time incremental routine
    has added since the last total renumber.

    Optional `?filter=<key>` to scope the renumber to a coin filter
    (matches CATEGORY_FILTERS['coins'] keys: ca_ancient, ny_ancient,
    ca_modern, ny_modern, ordered). Without `filter`, every coin row
    is renumbered into a single C1..Cn sequence."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    coin_filter = (request.args.get('filter') or '').strip() or None
    cat_filters = CATEGORY_FILTERS.get('coins', {})
    if coin_filter and coin_filter in cat_filters:
        clause, extra = cat_filters[coin_filter]
        rows = db.execute(
            f"SELECT * FROM coins WHERE ({clause})", list(extra)
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM coins").fetchall()
    out, updated = _recompute_coin_bins(db, rows, total=True)
    return jsonify(filter=coin_filter, total=len(out), updated=updated)


@app.route('/admin/coins-cat-id-audit', methods=['POST'])
def coins_cat_id_audit():
    """Report cat_id health: total rows, missing count, duplicate IDs.
    Read-only — no writes. Use the cat-id fixer to populate gaps."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    total = db.execute('SELECT COUNT(*) FROM coins').fetchone()[0]
    missing = db.execute(
        "SELECT id, property_name, region, denomination FROM coins "
        "WHERE COALESCE(cat_id, '') = '' OR TRIM(cat_id) = ''"
    ).fetchall()
    dup_rows = db.execute(
        "SELECT cat_id, COUNT(*) AS n FROM coins "
        "WHERE COALESCE(cat_id, '') != '' "
        "GROUP BY cat_id HAVING n > 1 ORDER BY n DESC, cat_id"
    ).fetchall()
    duplicates = []
    for d in dup_rows:
        members = db.execute(
            "SELECT id, property_name, region, denomination, date_1 "
            "FROM coins WHERE cat_id = ?",
            [d['cat_id']]
        ).fetchall()
        duplicates.append({
            'cat_id': d['cat_id'],
            'count':  d['n'],
            'rows':   [dict(m) for m in members],
        })
    return jsonify({
        'total':           total,
        'missing_count':   len(missing),
        'missing_rows':    [dict(r) for r in missing],
        'duplicate_count': len(duplicates),
        'duplicates':      duplicates,
    })


@app.route('/admin/pens-owner-mark', methods=['POST'])
def pens_owner_mark():
    """Set owner='Mark' for all pens records."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    r = db.execute("UPDATE pens SET owner='Mark'")
    db.commit()
    return jsonify(updated=r.rowcount, total=db.execute('SELECT COUNT(*) FROM pens').fetchone()[0])


@app.route('/admin/users', methods=['GET'])
def admin_users():
    """List + manage application users (owner-only). Cloudflare Access
    still controls who can hit the URL at all; this page controls
    per-category authorization once they're past the edge."""
    db = get_db()
    rows = db.execute(
        "SELECT id, email, display_name, role, categories, row_filters, "
        "       created_at FROM users ORDER BY role DESC, LOWER(email)"
    ).fetchall()
    users = []
    for r in rows:
        d = dict(r)
        d['cat_set'] = _expand_categories(d['categories'], d['role'])
        d['row_filters_dict'] = _parse_row_filters_json(d.get('row_filters'))
        users.append(d)
    cat_choices = [(slug, info['name']) for slug, info in CATEGORIES.items()]
    return render_template('admin_users.html',
                           users=users,
                           cat_choices=cat_choices,
                           owner_email=OWNER_EMAIL,
                           current_category='__admin__',
                           categories=CATEGORIES,
                           counts=get_counts(),
                           row_filter_fields=ROW_FILTER_FIELDS,
                           row_filter_value_lists=ROW_FILTER_VALUE_LISTS,
                           vlists=current_vlists())


def _collect_row_filters_from_form(cats_list):
    """Read rfilter_<cat>_<field> checkboxes from the current request
    and return a JSON string suitable for users.row_filters (or None
    when nothing is restricted)."""
    filters = {}
    for cat, fields in ROW_FILTER_FIELDS.items():
        if cat not in cats_list:
            continue  # category not granted at all → no row filter to record
        cat_filters = {}
        for field in fields:
            vals = request.form.getlist(f'rfilter_{cat}_{field}')
            allowed = VALUE_LISTS.get(ROW_FILTER_VALUE_LISTS.get(field, ''), [])
            kept = [v for v in vals if v in allowed]
            if kept:
                cat_filters[field] = kept
        if cat_filters:
            filters[cat] = cat_filters
    return json.dumps(filters) if filters else None


@app.route('/admin/users/add', methods=['POST'])
def admin_users_add():
    db = get_db()
    email = (request.form.get('email') or '').strip().lower()
    if not email or '@' not in email:
        flash('Email is required.', 'error')
        return redirect(url_for('admin_users'))
    display = (request.form.get('display_name') or '').strip()
    role = request.form.get('role') or 'member'
    if role not in ('owner', 'member'):
        role = 'member'
    cats_list = request.form.getlist('categories')
    cats_csv = '*' if role == 'owner' else \
        ','.join(c for c in cats_list if c in CATEGORIES)
    row_filters_json = None if role == 'owner' else \
        _collect_row_filters_from_form(set(cats_list))
    try:
        db.execute(
            "INSERT INTO users (id, email, display_name, role, "
            "                   categories, row_filters) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [str(uuid.uuid4()), email, display or None, role, cats_csv,
             row_filters_json]
        )
        db.commit()
        flash(f'Added {email}.', 'success')
    except sqlite3.IntegrityError:
        flash(f'{email} already exists — edit it instead.', 'error')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<user_id>/update', methods=['POST'])
def admin_users_update(user_id):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", [user_id]).fetchone()
    if not row:
        abort(404)
    display = (request.form.get('display_name') or '').strip()
    role = request.form.get('role') or row['role']
    if role not in ('owner', 'member'):
        role = 'member'
    cats_list = request.form.getlist('categories')
    cats_csv = '*' if role == 'owner' else \
        ','.join(c for c in cats_list if c in CATEGORIES)
    row_filters_json = None if role == 'owner' else \
        _collect_row_filters_from_form(set(cats_list))
    # Don't allow demoting the very last owner — would lock everyone out.
    if row['role'] == 'owner' and role != 'owner':
        owner_count = db.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role = 'owner'"
        ).fetchone()['c']
        if owner_count <= 1:
            flash('Cannot demote the only owner.', 'error')
            return redirect(url_for('admin_users'))
    db.execute(
        "UPDATE users SET display_name = ?, role = ?, categories = ?, "
        "       row_filters = ?, updated_at = datetime('now') WHERE id = ?",
        [display or None, role, cats_csv, row_filters_json, user_id]
    )
    db.commit()
    flash(f"Updated {row['email']}.", 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<user_id>/delete', methods=['POST'])
def admin_users_delete(user_id):
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", [user_id]).fetchone()
    if not row:
        abort(404)
    # Block deleting yourself or the last owner.
    if row['email'].lower() == g.current_user['email'].lower():
        flash('Cannot delete yourself.', 'error')
        return redirect(url_for('admin_users'))
    if row['role'] == 'owner':
        owner_count = db.execute(
            "SELECT COUNT(*) AS c FROM users WHERE role = 'owner'"
        ).fetchone()['c']
        if owner_count <= 1:
            flash('Cannot delete the only owner.', 'error')
            return redirect(url_for('admin_users'))
    db.execute("DELETE FROM users WHERE id = ?", [user_id])
    db.commit()
    flash(f"Removed {row['email']}.", 'success')
    return redirect(url_for('admin_users'))


# Categories the receipt-into-documents migration ran for. Recordings
# is intentionally excluded — its FileMaker receipt slot historically
# held cover-image data, and the migration was never enabled there.
RECEIPT_MIGRATED_CATEGORIES = (
    'art', 'coins', 'watches', 'pens', 'rifles', 'audio', 'cameras', 'lenses',
)


@app.route('/admin/undo-receipt-phantoms', methods=['POST'])
def admin_undo_receipt_phantoms():
    """Remove Receipt-titled docs entries the receipt→documents
    migration created from FileMaker-era receipt slots that actually
    held cover-image duplicates. Conservative: only entries whose
    filename matches the row's receipt column value AND whose title is
    exactly 'Receipt' get removed. User-uploaded Receipt docs (added
    via the dynamic docs UI with a different filename) are preserved.

    `dry=1` reports what WOULD be removed without writing — run this
    first to spot-check the list. Default behaviour is `dry=0`: applies
    the cleanup. Both modes return per-category counts and a sample.
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    dry = request.form.get('dry') == '1'
    db = get_db()
    by_category = {}
    total = 0
    samples = []
    for cat in RECEIPT_MIGRATED_CATEGORIES:
        info = CATEGORIES.get(cat)
        if not info:
            continue
        rep = _undo_receipt_phantoms(db, info['table'], dry_run=dry)
        by_category[cat] = rep['matched']
        total += rep['matched']
        for s in rep['sample']:
            samples.append({**s, 'category': cat})
            if len(samples) >= 50:
                break
    if not dry:
        db.commit()
    return jsonify({
        'dry_run': dry,
        'total':   total,
        'by_category': by_category,
        'sample':  samples[:50],
    })


@app.route('/admin/undo-numbered-doc-phantoms', methods=['POST'])
def admin_undo_numbered_doc_phantoms():
    """Sibling cleanup to /admin/undo-receipt-phantoms — removes docs
    entries whose title is a fixed-slot label plus a numeric suffix
    ('Front 2', 'Receipt 3', 'Image 2', etc.). These are typically
    legacy FileMaker auto-numbered duplicates the receipt-phantom
    cleanup couldn't catch (different title, sometimes different
    filename from the cover slot). Runs across every DOCUMENTS_-
    CATEGORIES table.

    `dry=1` reports what WOULD be removed without writing — run this
    first. `dry=0` applies + tombstones each removed file's export
    path so the next syncDown removes the orphan from local mirrors.
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    dry = request.form.get('dry') == '1'
    db = get_db()
    by_category = {}
    total = 0
    samples = []
    for cat in sorted(DOCUMENTS_CATEGORIES):
        info = CATEGORIES.get(cat)
        if not info:
            continue
        rep = _undo_numbered_doc_phantoms(db, info['table'], dry_run=dry)
        by_category[cat] = rep['matched']
        total += rep['matched']
        for s in rep['sample']:
            samples.append({**s, 'category': cat})
            if len(samples) >= 50:
                break
    if not dry:
        db.commit()
    return jsonify({
        'dry_run':     dry,
        'total':       total,
        'by_category': by_category,
        'sample':      samples[:50],
    })


@app.route('/admin', methods=['GET'])
def admin_index():
    """Tiny browser-friendly index of one-shot maintenance actions.
    The action POSTs are still gated by IMPORT_MISSING_SECRET; the secret
    is just baked into the page's submit JS so the button works without
    extra typing. Cloudflare Access still gates the page itself in prod.
    """
    actions = [
        {
            'label': "Receipt phantoms: scan (dry run)",
            'desc':  "Reports per-category counts of legacy receipt-column "
                     "phantoms that the receipt→documents migration left "
                     "as 'Receipt'-titled docs entries pointing at "
                     "cover-image duplicates. Only entries whose filename "
                     "exactly matches the row's receipt column value are "
                     "counted — user-uploaded Receipt docs (different "
                     "filename) are safe and never reported. "
                     "Pair with the numbered-suffix scan below — together "
                     "they cover both phantom shapes (bare 'Receipt' here, "
                     "numbered 'Receipt 2' / 'Front 2' there).",
            'url':   url_for('admin_undo_receipt_phantoms'),
            'extra': {'dry': '1'},
        },
        {
            'label': "Receipt phantoms: REMOVE",
            'desc':  "Splices the matched Receipt-titled docs entries, "
                     "NULLs the legacy receipt column on the affected "
                     "rows so the boot-time migration doesn't re-insert, "
                     "and tombstones each '<ident> — Receipt.<ext>' path "
                     "so the next ⬇ Files syncDown removes the orphan "
                     "from your local mirror. Run the dry scan first. "
                     "Run the numbered-suffix REMOVE below afterwards "
                     "(or before — order doesn't matter) for a complete "
                     "cleanup; this one alone misses 'Receipt 2', "
                     "'Front 2', 'Image 2' style phantoms.",
            'url':   url_for('admin_undo_receipt_phantoms'),
            'extra': {'dry': '0'},
            'confirm': True,
        },
        {
            'label': "Numbered-suffix doc phantoms: scan (dry run)",
            'desc':  "Reports docs entries titled '<known-label> N' "
                     "across every category — 'Front 2', 'Front 3', "
                     "'Receipt 2', 'Image 2', 'Back 3', 'Doc 4', etc. "
                     "These are legacy FileMaker auto-numbered duplicates "
                     "that the title-exact 'Receipt' cleanup couldn't "
                     "match. User-authored titles like 'Service Receipt "
                     "2024' aren't matched (the suffix has to be a bare "
                     "integer following a known label). "
                     "Pair with the bare-Receipt scan above — together "
                     "they cover both phantom shapes.",
            'url':   url_for('admin_undo_numbered_doc_phantoms'),
            'extra': {'dry': '1'},
        },
        {
            'label': "Numbered-suffix doc phantoms: REMOVE",
            'desc':  "Splices each matched entry, bumps updated_at on "
                     "the affected row, and tombstones the '<ident> — "
                     "<title>.<ext>' export path so the next ⬇ Files "
                     "syncDown removes the orphan locally. Run the dry "
                     "scan first. Run the bare-Receipt REMOVE above too "
                     "(order doesn't matter) for a complete cleanup; "
                     "this one alone leaves the legacy receipt column "
                     "populated, so the next boot's migration would "
                     "re-create a {title:'Receipt'} entry.",
            'url':   url_for('admin_undo_numbered_doc_phantoms'),
            'extra': {'dry': '0'},
            'confirm': True,
        },
    ]
    archived_actions = [
        # Older one-shot maintenance actions — preserved for history /
        # re-run if needed, but archived under a collapsed section so
        # the active set stays focused.
        {
            'label': "Watches: bulk AI lookup (calibre/jewels/origin/escapement/beat)",
            'desc':  "Walks every watch with enough identity (brand/model/"
                     "ref) and uses the AI lookup to OVERWRITE those five "
                     "movement fields. Loops batches of 5 in the browser "
                     "until every row has been touched since you started. "
                     "Click Stop while running to halt.",
            'url':   url_for('watches_bulk_lookup'),
            'kind':  'loop',
            'extra': {'limit': '5'},
        },
        {
            'label': "Download backup (DB + uploads)",
            'desc':  "Streams a zip of the SQLite database (consistent "
                     "snapshot via SQLite's online backup API) plus every "
                     "file in uploads/. Save somewhere offsite.",
            'url':   url_for('admin_backup'),
            'kind':  'download',
        },
        {
            'label': "Export StuffFiles (per-user, organized)",
            'desc':  "Streams a zip with every file you can see, organized "
                     "as StuffFiles/<Category>/<Group>/<Item> — <Label>.<ext>. "
                     "Unzip into your iCloud Drive's StuffFiles folder. "
                     "Also available to members via the ⬇ link in the top nav.",
            'url':   url_for('admin_export_files'),
            'kind':  'download_no_secret',
        },
        {
            'label': "Scan orphan upload files (dry run)",
            'desc':  "Reports how many files in uploads/ aren't referenced "
                     "by any DB row, total bytes, and a sample. Doesn't "
                     "delete anything. Run this first.",
            'url':   url_for('admin_orphan_uploads'),
            'extra': {'dry': '1'},
        },
        {
            'label': "DELETE orphan upload files",
            'desc':  "Actually removes every file in uploads/ that isn't "
                     "referenced by any DB row. Also deletes the matching "
                     "PDF/HEIC thumbnail cache. Run the dry scan first.",
            'url':   url_for('admin_orphan_uploads'),
            'extra': {'dry': '0'},
        },
        {
            'label': "Scan watches missing from Watch.csv (dry run)",
            'desc':  "Reads the bundled Watch.csv legacy import and lists "
                     "rows missing from the watches table. Primary "
                     "dedupe is (reference, case_num, movement_num); "
                     "no-paperwork CSV rows (vintage / orphan pieces "
                     "with all three blank) fall back to (brand, model) "
                     "dedupe so they're not silently dropped. Use when "
                     "the live count has dropped below the legacy 410 "
                     "to confirm whether the diff is recoverable "
                     "accidental loss vs. intentional deletions you "
                     "DON'T want resurrected.",
            'url':   url_for('import_watches_missing'),
            'extra': {'dry': '1'},
        },
        {
            'label': "Re-import watches missing from Watch.csv",
            'desc':  "Inserts every Watch.csv row that isn't already "
                     "present, by (reference, case_num, movement_num) "
                     "or — for no-paperwork rows — (brand, model). "
                     "Safe to re-run; dedupes both ways. Will resurrect "
                     "any intentionally-deleted watches that still "
                     "match a CSV row, so run the dry scan first.",
            'url':   url_for('import_watches_missing'),
        },
        {
            'label': "Coins: set every owner to 'Mark'",
            'desc':  "Sets owner='Mark' on every coin whose owner is NULL, "
                     "blank, or anything other than 'Mark'.",
            'url':   url_for('coins_owner_mark'),
        },
        {
            'label': "Coins: total renumber display position (bins)",
            'desc':  "Wipes every letter-suffix insert and reassigns "
                     "C/CM/N/NM bins from 1..n within each "
                     "location/era group, ordered by region / authority "
                     "/ mint / cat_id. Card-print routine adds suffixes "
                     "back as new coins land between existing positions.",
            'url':   url_for('coins_renumber_bins'),
            'confirm': True,
        },
        {
            'label': "Coins: total renumber cat_ids (C001..Cn)",
            'desc':  "Reassigns every coin's cat_id to the flat C-prefix "
                     "global serial. Destroys the prior CA/CM/NA/NM "
                     "partition. Cat_ids are meant to be unchanging — "
                     "only run this for a one-time scheme switch.",
            'url':   url_for('coins_renumber_cat_ids'),
            'confirm': True,
        },
        {
            'label': "Properties: restore lost docs from doc_1..10",
            'desc':  "Repopulates properties.documents JSON from the "
                     "legacy doc_1..10 columns when the JSON is empty. "
                     "Recovers any property docs the phantom-strip nuked "
                     "via the title-prefix heuristic (titles like "
                     "\"Carpinteria — Deed\" looked like auto-generated "
                     "phantoms). Idempotent — skips rows whose JSON "
                     "already has tiles.",
            'url':   url_for('properties_restore_docs'),
        },
        {
            'label': "Music: canonicalize artist spellings (dry run)",
            'desc':  "Reports which recordings.artist values differ "
                     "only by case / whitespace and would be collapsed "
                     "to a single canonical spelling. Does NOT write — "
                     "review the JSON action list before running the "
                     "apply variant below. Prevents Files from creating "
                     "duplicate artist folders ("
                     "\"Bob Marley and The Wailers\" vs \"and the\").",
            'url':   url_for('recordings_canonicalize_artists'),
            'extra': {'dry': '1'},
        },
        {
            'label': "Music: canonicalize artist spellings (apply)",
            'desc':  "Actually rewrites differing artist spellings to "
                     "the most-common variant within each case-insensitive "
                     "group. Run the dry-run above first to verify the "
                     "merges look right.",
            'url':   url_for('recordings_canonicalize_artists'),
            'extra': {'dry': '0'},
            'confirm': True,
        },
        {
            'label': "Recordings: clear bare-numeric notes (FM import fix)",
            'desc':  "The earlier FileMaker import wrote price values into "
                     "the notes column. Nulls out any recordings.notes that "
                     "is just an integer or decimal (< 12 chars, no spaces). "
                     "Run before re-upserting from Recording.csv.",
            'url':   url_for('clear_recording_numeric_notes'),
        },
        {
            'label': "Recordings: re-upsert from Recording.csv",
            'desc':  "Refills price + notes (and every other column) from "
                     "Recording.csv, matching on UUID. Existing in-app edits "
                     "to non-blank columns are preserved. Pair with the "
                     "clear-numeric-notes action above to undo the bad "
                     "import.",
            'url':   url_for('upsert_recordings'),
        },
    ]
    return render_template('admin.html', actions=actions,
                           archived_actions=archived_actions,
                           secret=IMPORT_MISSING_SECRET,
                           current_category='__admin__',
                           categories=CATEGORIES,
                           counts=get_counts())


@app.route('/admin/backup', methods=['GET'])
def admin_backup():
    """Stream a zip containing a consistent snapshot of the SQLite DB
    plus the entire uploads/ directory. Browser triggers a download.

    Authentication: in production Cloudflare Access gates the URL; the
    IMPORT_MISSING_SECRET is also required as a query string so the link
    isn't trivially fetchable by anything that gets past Access.
    """
    if request.args.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)

    import io
    import zipfile
    import tempfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Use SQLite's online backup API for a consistent snapshot —
        # safer than copying stuffapp.db while writes may be in flight.
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
            tmp_path = tmp.name
        try:
            src = sqlite3.connect(DATABASE)
            dst = sqlite3.connect(tmp_path)
            src.backup(dst)
            dst.close()
            src.close()
            zf.write(tmp_path, arcname='stuffapp.db')
        finally:
            try: os.unlink(tmp_path)
            except OSError: pass

        # Walk uploads/ but skip the .thumbs cache (regenerable).
        if os.path.isdir(UPLOAD_FOLDER):
            for dirpath, dirnames, filenames in os.walk(UPLOAD_FOLDER):
                dirnames[:] = [d for d in dirnames if d != '.thumbs']
                for name in filenames:
                    if name == '.DS_Store':
                        continue
                    full = os.path.join(dirpath, name)
                    rel = os.path.relpath(full, UPLOAD_FOLDER)
                    zf.write(full, arcname=os.path.join('uploads', rel))

    buf.seek(0)
    fname = f"stuffapp-backup-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.zip"
    return send_file(buf, as_attachment=True, download_name=fname,
                     mimetype='application/zip')


def _collect_referenced_uploads(db):
    """Walk every table's file-typed columns and collect the set of
    filenames currently referenced by at least one row. Also scoops up
    the topics.image column which lives outside the FIELDS map."""
    referenced = set()
    for cat, fields in FIELDS.items():
        table = CATEGORIES[cat]['table']
        file_cols = [f['name'] for f in fields if f.get('type') == 'file']
        if not file_cols:
            continue
        cols = {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
        present = [c for c in file_cols if c in cols]
        if not present:
            continue
        sel = ', '.join(present)
        for row in db.execute(f"SELECT {sel} FROM {table}").fetchall():
            for c in present:
                v = (row[c] or '').strip()
                if v:
                    referenced.add(v)
    # topics.image isn't in FIELDS but lives in UPLOAD_FOLDER too.
    try:
        for row in db.execute("SELECT image FROM topics").fetchall():
            v = (row['image'] or '').strip()
            if v:
                referenced.add(v)
    except sqlite3.OperationalError:
        pass
    # Documents JSON columns: every DOCUMENTS_CATEGORIES table has one or
    # more JSON columns holding [{title, filename}, …] arrays. Files
    # referenced only via these arrays were getting marked as orphans
    # because the FIELDS-driven walk above misses them.
    for cat, sets in DOC_SETS_BY_CATEGORY.items():
        table = CATEGORIES[cat]['table']
        cols = {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
        json_cols = [c for c in sets.values() if c in cols]
        if not json_cols:
            continue
        sel = ', '.join(json_cols)
        try:
            rows = db.execute(f"SELECT {sel} FROM {table}").fetchall()
        except sqlite3.OperationalError:
            continue
        for row in rows:
            for c in json_cols:
                raw = row[c]
                if not raw:
                    continue
                try:
                    docs = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if not isinstance(docs, list):
                    continue
                for d in docs:
                    if not isinstance(d, dict):
                        continue
                    fn = (d.get('filename') or '').strip()
                    if fn:
                        referenced.add(fn)
    return referenced


def _norm(s):
    """Aggressive normalization for matching folder/identifier strings
    across the export ↔ sweep round trip. Lowercased, whitespace
    collapsed, filesystem-hostile chars stripped, diacritics folded,
    and punctuation softened so spelling drift like "A. Lange & Söhne"
    vs "A. Lange Sohne" doesn't fragment a record into duplicates."""
    if not s:
        return ''
    bad = set('/\\:*?"<>|\n\r\t')
    s = ''.join(c for c in s if c not in bad)
    # Fold diacritics — "Söhne" → "Sohne", "Eulèr" → "Euler".
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    # Treat any non-alphanumeric as soft whitespace so "&", ".", "-" etc.
    # collapse: "A. Lange & Söhne" and "A Lange Sohne" hash the same.
    s = re.sub(r'[^0-9A-Za-z\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip().lower()
    return s


def _safe_path(*parts):
    """Strip filesystem-hostile characters from each path segment so the
    zip writes cleanly across macOS / iCloud Drive."""
    bad = set('/\\:*?"<>|\n\r\t')
    out = []
    for p in parts:
        s = ''.join(c for c in (p or '') if c not in bad).strip()
        # Collapse runs of whitespace, trim trailing dots/spaces.
        s = re.sub(r'\s+', ' ', s).strip(' .')
        out.append(s or 'Unknown')
    return out


def _record_tombstone(db, category, row, label, filename):
    """Record a server-side delete so the next incremental syncDown can
    remove the matching local file from the user's StuffFiles folder.
    Computes the same export-shaped path the zip writer uses so the
    client doesn't need to guess. No-ops if anything's missing — a
    missed tombstone just leaves a stale local file (the safe miss),
    which is preferable to a wrong tombstone deleting good local data.
    """
    if not (category and row and filename):
        return
    plan = EXPORT_LAYOUT.get(category)
    if not plan:
        return
    try:
        group_raw = plan['group'](row)
        ident_raw = plan['ident'](row)
    except Exception:
        return
    group, ident = _safe_path(group_raw, ident_raw)
    cat_label = EXPORT_CATEGORY_LABELS.get(category, category.title())
    db.execute(
        "INSERT INTO tombstones (id, category, cat_label, group_path, "
        "                        ident_path, label, filename, deleted_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [str(uuid.uuid4()), category, cat_label, group, ident,
         (label or '').strip(), filename, datetime.utcnow().isoformat()]
    )


# Per-category export plan. For each category:
#   group:  fn(row) → folder name (e.g. brand)
#   ident:  fn(row) → item identifier (used as filename prefix)
#   files:  list of (file_field, default_label, optional_title_field)
#           default_label is used when title_field is missing or empty
def _g(r, key):
    """sqlite3.Row.get-equivalent — returns '' for missing columns or
    NULL values, so the export lambdas don't blow up on tables that
    are missing optional fields."""
    try:
        v = r[key]
    except (IndexError, KeyError):
        return ''
    return v if v is not None else ''


def _watch_ident(r):
    """Filename ident for watches: '<model> (<cat_id>)' when a cat_id
    is set, e.g. 'Galet Minute Repeater (W127)'. Year and reference
    are intentionally dropped from the human descriptor — cat_id
    already disambiguates and shorter filenames read better in Finder.
    Legacy rows without a cat_id keep the older 'year model Ref ref'
    form so their on-disk paths don't move until backfill."""
    cat_id = (_g(r, 'cat_id') or '').strip()
    model = (_g(r, 'model') or '').strip()
    if cat_id:
        return f'{model} ({cat_id})'.strip() if model else cat_id
    year = _g(r, 'year')
    legacy = ' '.join(filter(None, [
        str(year) if year else '',
        model,
        f'Ref {_g(r, "reference")}' if _g(r, 'reference') else '',
    ])).strip()
    return legacy or (_g(r, 'brand') or '')[:40] or _g(r, 'id')[:8]


def _art_ident(r):
    """Filename ident for art: '<cat_id> — <title>' when a cat_id is
    set, e.g. 'A042 — Sunset Over Carpinteria'. Year is dropped from
    the human descriptor (cat_id is the stable id; year is one click
    away in the detail view). Legacy rows without a cat_id keep the
    older 'title — year' form."""
    cat_id = (_g(r, 'cat_id') or '').strip()
    title = _g(r, 'title') or ''
    if cat_id:
        return f'{cat_id} — {title}' if title else cat_id
    legacy = ' — '.join(filter(None, [
        title,
        str(_g(r, 'year')) if _g(r, 'year') else '',
    ]))
    return legacy or _g(r, 'id')[:8]


# Per-category constructors used by the sweep tool's auto-create path.
# Each takes (group, ident) parsed from the StuffFiles path and returns
# a dict of column → value to seed a new row, or None if the category
# can't safely auto-create (don't guess where guessing would mangle
# data — e.g. coins, cards). The id column is filled by the caller.
def _create_watch(g, i):
    out = {'brand': g}
    m = re.match(r'^\s*(\d{4})\b\s*', i or '')
    if m:
        try:
            out['year'] = int(m.group(1))
        except ValueError:
            pass
        rest = (i or '')[m.end():].strip()
    else:
        rest = (i or '').strip()
    # "Model name Ref XYZ" → split on " Ref " (case-insensitive)
    parts = re.split(r'\s+Ref\s+', rest, flags=re.IGNORECASE, maxsplit=1)
    if parts and parts[0].strip():
        out['model'] = parts[0].strip()
    if len(parts) > 1 and parts[1].strip():
        out['reference'] = parts[1].strip()
    return out

def _create_property(g, i): return {'name': g}
def _create_person(g, i):   return {'name': g}
def _create_art(g, i):
    out = {'artist': g}
    if i:
        # Title — Year (export shape uses ' — ')
        if ' — ' in i:
            t, _, y = i.rpartition(' — ')
            out['title'] = t.strip()
            try: out['year'] = int(y.strip())
            except ValueError: pass
        else:
            out['title'] = i.strip()
    return out
def _create_recording(g, i): return {'artist': g, 'title': (i or '').strip() or None}
def _create_make_only(g, i): return {'make': g}
def _create_vehicle(g, i):
    out = {'make': g}
    m = re.match(r'^\s*(\d{4})\b\s*(.*)$', i or '')
    if m:
        try: out['year'] = int(m.group(1))
        except ValueError: pass
        if m.group(2).strip(): out['model'] = m.group(2).strip()
    elif i:
        out['model'] = i.strip()
    return out

EXPORT_LAYOUT = {
    'watches': {
        'group': lambda r: _g(r, 'brand') or 'Unknown',
        'ident': _watch_ident,
        'create': _create_watch,
        # Single cover image (image_obv, exported as 'Front') is the
        # only fixed slot for watches now. The image_rev column (Back)
        # was dropped — legacy FileMaker import populated it with copies
        # of the cover on every watch, so the export emitted bogus
        # '<ident> — Back.<ext>' files everywhere. Receipts and other
        # user-titled docs (container_1, container_2) flow through the
        # JSON `documents` column. Coins still keep their Obverse/Reverse
        # pair (image_1, image_2) — that pair is genuinely identity for
        # numismatics.
        'files': [
            ('image_obv', 'Front', None),
        ],
    },
    'coins': {
        'group': lambda r: _g(r, 'region') or 'Unknown',
        'ident': lambda r: ' '.join(filter(None, [
            _g(r, 'cat_id') or '',
            _g(r, 'authority') or '',
            _g(r, 'denomination') or '',
        ])).strip() or _g(r, 'id')[:8],
        # User-titled docs (document_1, document_2) moved into JSON.
        'files': [
            ('image_1', 'Obverse', None),
            ('image_2', 'Reverse', None),
        ],
    },
    'properties': {
        'group': lambda r: _g(r, 'name') or 'Unknown',
        'ident': lambda r: _g(r, 'name') or _g(r, 'id')[:8],
        'create': _create_property,
        # `image` is the only fixed file slot — generic documents move
        # into the JSON `documents` column, walked separately below
        # because they're unbounded. Legacy doc_1..10 + doc_N_title
        # columns still exist (dual-write migration), but we no longer
        # export from them: documents is now the source of truth.
        'files': [
            ('image', 'Image', None),
        ],
    },
    'credit_cards': {
        'group': lambda r: _g(r, 'name') or 'Cards',
        'ident': lambda r: ' — '.join(filter(None, [
            _g(r, 'name') or '',
            (_g(r, 'description') or '').splitlines()[0] if _g(r, 'description') else '',
        ])) or _g(r, 'id')[:8],
        'files': [
            ('image_front', 'Front', None),
            ('image_back',  'Back',  None),
        ],
    },
    'persons': {
        'group': lambda r: _g(r, 'name') or 'Unknown',
        'ident': lambda r: _g(r, 'name') or _g(r, 'id')[:8],
        'create': _create_person,
        # User-titled id_doc_3..8 + health_doc_3..8 moved to the
        # `id_documents` and `health_documents` JSON columns. The four
        # license/health-card front+back tiles keep their fixed columns
        # because they're bound to the semantic number fields
        # (license_number, health_insurance_number) used by the
        # share/lookup buttons.
        'files': [
            ('head_shot',       'Head Shot',         None),
            ('license_obverse', 'License Front',     None),
            ('license_reverse', 'License Back',      None),
            ('health_card_obv', 'Health Card Front', None),
            ('health_card_rev', 'Health Card Back',  None),
        ],
    },
    'cameras': {
        'group': lambda r: _g(r, 'make') or 'Unknown',
        'ident': lambda r: ' '.join(filter(None, [_g(r, 'model') or '', _g(r, 'serial_number') or ''])).strip() or _g(r, 'id')[:8],
        'create': _create_make_only,
        # Receipt moved into the JSON `documents` column.
        'files': [('image', 'Image', None)],
    },
    'lenses': {
        'group': lambda r: _g(r, 'make') or 'Unknown',
        'ident': lambda r: ' '.join(filter(None, [_g(r, 'model') or '', _g(r, 'serial_number') or ''])).strip() or _g(r, 'id')[:8],
        'create': _create_make_only,
        # Receipt moved into the JSON `documents` column.
        'files': [('image', 'Image', None)],
    },
    'pens': {
        'group': lambda r: _g(r, 'make') or 'Unknown',
        'ident': lambda r: ' '.join(filter(None, [_g(r, 'model') or '', _g(r, 'serial_number') or ''])).strip() or _g(r, 'id')[:8],
        'create': _create_make_only,
        # Receipt moved into the JSON `documents` column.
        'files': [('image', 'Image', None)],
    },
    'art': {
        'group': lambda r: _g(r, 'artist') or 'Unknown',
        'ident': _art_ident,
        'create': _create_art,
        # doc_2 + receipt moved to JSON `documents` column. Image is
        # the only fixed file slot for art now — receipts are exported
        # as a normal doc entry via the JSON-column walk below.
        'files': [
            ('image', 'Image', None),
        ],
    },
    'vehicles': {
        'group': lambda r: _g(r, 'make') or 'Unknown',
        'ident': lambda r: ' '.join(filter(None, [
            str(_g(r, 'year')) if _g(r, 'year') else '',
            _g(r, 'model') or '',
        ])).strip() or _g(r, 'id')[:8],
        'create': _create_vehicle,
        # All eight user-titled doc slots (insurance / invoice /
        # registration / auto_title + vehicle_doc_5..8) moved to the
        # JSON `documents` column; only the image stays fixed.
        'files': [
            ('image', 'Image', None),
        ],
    },
    'recordings': {
        'group': lambda r: _g(r, 'artist') or 'Unknown',
        'ident': lambda r: _g(r, 'title') or _g(r, 'id')[:8],
        'create': _create_recording,
        'files': [('image', 'Cover', None), ('receipt', 'Receipt', None)],
    },
    'audio': {
        'group': lambda r: _g(r, 'make') or 'Unknown',
        'ident': lambda r: ' '.join(filter(None, [_g(r, 'model') or '', _g(r, 'type') or ''])).strip() or _g(r, 'id')[:8],
        'create': _create_make_only,
        # Receipt moved into the JSON `documents` column.
        'files': [('image', 'Image', None)],
    },
    'rifles': {
        'group': lambda r: _g(r, 'make') or 'Unknown',
        'ident': lambda r: ' '.join(filter(None, [_g(r, 'model') or '', _g(r, 'serial_number') or ''])).strip() or _g(r, 'id')[:8],
        'create': _create_make_only,
        # Receipt moved into the JSON `documents` column.
        'files': [('image', 'Image', None)],
    },
}

# Slot columns that the delete-sync flow refuses to clear, even when
# the local file is missing from the upload. These are identity-bearing
# (cover image, obverse/reverse pair, license front/back, etc.) and a
# user dragging a record's folder back into Sweep without the cover
# should not silently nuke the cover from the DB. Categories not listed
# default to {'image'} via _identity_slots(). Receipts and free docs
# (which live in the JSON documents column) are deliberately not in
# this set — their whole purpose is to be add/remove-able via Files.
IDENTITY_SLOTS_BY_CATEGORY = {
    'watches':      {'image_obv'},
    'coins':        {'image_1', 'image_2'},
    'persons':      {'head_shot', 'license_obverse', 'license_reverse',
                     'health_card_obv', 'health_card_rev'},
    'credit_cards': {'image_front', 'image_back'},
}


def _identity_slots(category):
    return IDENTITY_SLOTS_BY_CATEGORY.get(category, {'image'})


# Pretty labels for the top-level category folders inside the zip.
EXPORT_CATEGORY_LABELS = {
    'watches': 'Watches', 'coins': 'Coins', 'properties': 'Properties',
    'credit_cards': 'Cards', 'persons': 'People', 'cameras': 'Cameras',
    'lenses': 'Lenses', 'pens': 'Pens', 'art': 'Art', 'vehicles': 'Vehicles',
    'recordings': 'Music', 'audio': 'Audio', 'rifles': 'Rifles',
}
# Reverse map for the sweep tool — pretty label → category slug.
EXPORT_LABEL_TO_CATEGORY = {v: k for k, v in EXPORT_CATEGORY_LABELS.items()}


@app.route('/export-files', methods=['GET'])
def admin_export_files():
    """Stream a zip containing every file the current user has access to,
    laid out as StuffFiles/<Category>/<Group>/<Item> — <Label>.<ext>.

    Auth: the before_request hook already requires a signed-in user;
    per-user category filtering via g.allowed_cats limits the export
    to whatever the user can see. (Members can hit this endpoint;
    they only get files for their permitted categories.)
    """
    user = g.get('current_user')
    if not user:
        abort(403)
    allowed = g.get('allowed_cats') or set()
    if not allowed:
        abort(403)

    # Incremental export: when the client passes ?since=<iso>, only
    # rows updated at or after that timestamp go into the zip, and a
    # _tombstones.json at the zip root lists files deleted server-side
    # since the same timestamp. Empty/missing `since` falls back to
    # the original "everything" behavior so first sync still works.
    since_param = (request.args.get('since') or '').strip()

    import io
    import zipfile
    import csv as _csv
    import tempfile

    db = get_db()
    # Build the zip on disk instead of in memory: a full StuffFiles
    # export can reach hundreds of megabytes of cover images, receipts
    # and docs, and an in-memory BytesIO either OOMs the Railway
    # container or holds a connection long enough for Cloudflare's
    # ~100s edge timeout to drop it ("Failed to fetch" client-side).
    # NamedTemporaryFile keeps the file path stable so send_file can
    # stream it after we close the ZipFile.
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    written = 0
    skipped_missing = 0
    seen_paths = set()

    def _next_unique(base_dir, ident, label, ext):
        """Avoid name collisions when two items in the same folder render
        to the same '<ident> — <label>.<ext>'. Suffix with -2, -3, ..."""
        cand = f'{ident} — {label}{ext}' if label else f'{ident}{ext}'
        full = f'{base_dir}/{cand}'
        if full not in seen_paths:
            seen_paths.add(full)
            return cand
        n = 2
        while True:
            cand = f'{ident} — {label} ({n}){ext}' if label else f'{ident} ({n}){ext}'
            full = f'{base_dir}/{cand}'
            if full not in seen_paths:
                seen_paths.add(full)
                return cand
            n += 1

    # ZIP_STORED (no compression) — the vast majority of payload is
    # already-compressed JPEG / HEIC / PNG / PDF, so DEFLATE just burns
    # CPU for sub-1% size savings. Storing instead drops build time
    # roughly 5-10× and keeps each .write() at near-disk speed, well
    # under Cloudflare's ~100s edge timeout.
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_STORED) as zf:
        for cat, plan in EXPORT_LAYOUT.items():
            if cat not in allowed:
                continue
            table = CATEGORIES[cat]['table']
            # Apply per-user row filters so members only export the
            # records they can actually see (e.g., owner ∈ {YM, Young}).
            wheres, params = [], []
            _apply_row_filter_clauses(cat, wheres, params)
            # Incremental: only emit records modified at or after `since`.
            if since_param:
                wheres.append("(updated_at IS NOT NULL AND updated_at >= ?)")
                params.append(since_param)
            where_clause = f"WHERE {' AND '.join(wheres)}" if wheres else ''
            try:
                rows = db.execute(
                    f"SELECT * FROM {table} {where_clause}", params).fetchall()
            except sqlite3.OperationalError:
                continue
            cat_label = EXPORT_CATEGORY_LABELS.get(cat, cat.title())
            # One PRAGMA per category, then derive both the membership
            # set (for `field in cols` checks below) and the ordered
            # column list (for the per-category CSV header) from the
            # same fetch.
            col_names = [r['name'] for r in
                         db.execute(f"PRAGMA table_info({table})").fetchall()]
            cols = set(col_names)

            for row in rows:
                ident_raw = plan['ident'](row)
                group_raw = plan['group'](row)
                group, ident = _safe_path(group_raw, ident_raw)

                # Owned vs. No longer Owned. Only Sold / Gifted / Lost
                # route under the "No longer Owned" interstitial — those
                # are the statuses where the item has actually left the
                # collection. Ordered (paid for, awaiting delivery),
                # Loaned (lent out, will return), and Consigned (with a
                # seller, may return unsold) are all still legally
                # owned and stay in the main category folder. Blank /
                # missing status defaults to owned too.
                status_val = ''
                if 'status' in cols:
                    try:
                        status_val = (row['status'] or '').strip()
                    except (KeyError, IndexError):
                        status_val = ''
                no_longer_owned = status_val.lower() in ('sold', 'gifted', 'lost')
                cat_root = f'StuffFiles/{cat_label}/No longer Owned' if no_longer_owned \
                            else f'StuffFiles/{cat_label}'

                # Per-row dedupe: legacy FileMaker imports often left the
                # cover-image filename in BOTH the primary file column
                # (image / image_obv / image_1) AND the receipt column,
                # so without this guard every record would export the
                # same JPEG twice — once as "Cover", once as "Receipt".
                seen_files = set()
                for spec in plan['files']:
                    field, default_label, title_field = spec
                    if field not in cols:
                        continue
                    fname = (row[field] or '').strip()
                    if not fname:
                        continue
                    if fname in seen_files:
                        continue
                    seen_files.add(fname)
                    src = os.path.join(UPLOAD_FOLDER, fname)
                    if not os.path.isfile(src):
                        skipped_missing += 1
                        continue
                    label = default_label
                    if title_field and title_field in cols:
                        t = (row[title_field] or '').strip()
                        if t:
                            label = t
                    label = _safe_path(label)[0]
                    ext = os.path.splitext(fname)[1] or ''
                    base_dir = f'{cat_root}/{group}'
                    arcname = f'{base_dir}/{_next_unique(base_dir, ident, label, ext)}'
                    zf.write(src, arcname=arcname)
                    written += 1

                # Per-row data snapshot. Writes the full row as JSON
                # inside the record's folder so the StuffFiles mirror is
                # round-trip-able — sweep can read it back to reconstruct
                # all column data (calibre, escapement, balance_wheel,
                # calibre_notes, notes, description, vendor, price,
                # service dates, every category's spec fields) even if
                # the SQLite DB has been blown away. Without this, only
                # the files survive an export/sweep cycle and every
                # column value is permanently lost on rebuild — the
                # StuffFiles mirror is misleadingly partial. Applies to
                # all categories that have a record-folder layout.
                base_dir = f'{cat_root}/{group}'
                arcname = (
                    f'{base_dir}/'
                    f'{_next_unique(base_dir, ident, "_data", ".json")}'
                )
                payload = json.dumps(
                    dict(row), default=str, indent=2,
                    ensure_ascii=False, sort_keys=True,
                )
                zf.writestr(arcname, payload)
                written += 1

                # JSON documents columns — unbounded user-titled docs.
                # Walk every doc-set declared for this category (e.g.
                # persons has 'ids' + 'health'). Each entry exports as
                # "<ident> — <title>.<ext>" same as a fixed slot, so
                # the round-trip with sweep stays symmetric.
                # `seen_files` carries over from the fixed-slot loop
                # above so a docs entry whose filename happens to match
                # a fixed slot (legacy phantom that escaped the boot-
                # time strip + a row mutation since boot) doesn't get
                # re-emitted — would have shown up as the same file at
                # two different arcnames in the same record folder.
                for json_col in _docs_cols_for(cat):
                    if json_col not in cols:
                        continue
                    try:
                        json_docs = json.loads(row[json_col] or '[]')
                    except (TypeError, ValueError):
                        json_docs = []
                    if not isinstance(json_docs, list):
                        continue
                    for i, d in enumerate(json_docs, 1):
                        if not isinstance(d, dict):
                            continue
                        fname = (d.get('filename') or '').strip()
                        if not fname:
                            continue
                        if fname in seen_files:
                            continue
                        seen_files.add(fname)
                        src = os.path.join(UPLOAD_FOLDER, fname)
                        if not os.path.isfile(src):
                            skipped_missing += 1
                            continue
                        label = (d.get('title') or '').strip() or f'Doc {i}'
                        label = _safe_path(label)[0]
                        ext = os.path.splitext(fname)[1] or ''
                        base_dir = f'{cat_root}/{group}'
                        arcname = f'{base_dir}/{_next_unique(base_dir, ident, label, ext)}'
                        zf.write(src, arcname=arcname)
                        written += 1

            # Per-category CSV at the top of each category's folder.
            # Always written with the FULL table (subject to the user's
            # row filter) — independent of the `since` filter applied
            # to the per-row file/JSON loop above. Without this, an
            # incremental sync would emit a CSV containing only the N
            # changed rows, replacing the user's previously-complete
            # local CSV with a sliver — silently turning a "schema
            # snapshot" into "diff of recent edits". Re-fetching with
            # the row filter only is cheap (single SELECT) and the
            # user gets a real complete dump on every export.
            csv_wheres, csv_params = [], []
            _apply_row_filter_clauses(cat, csv_wheres, csv_params)
            csv_where_clause = (
                f"WHERE {' AND '.join(csv_wheres)}" if csv_wheres else ''
            )
            try:
                csv_rows_full = db.execute(
                    f"SELECT * FROM {table} {csv_where_clause}",
                    csv_params,
                ).fetchall()
            except sqlite3.OperationalError:
                csv_rows_full = []
            if csv_rows_full:
                sio = io.StringIO()
                w = _csv.writer(sio, quoting=_csv.QUOTE_MINIMAL)
                w.writerow(col_names)
                for r in csv_rows_full:
                    w.writerow(['' if r[c] is None else r[c] for c in col_names])
                zf.writestr(f'StuffFiles/{cat_label}/{cat_label}.csv',
                            sio.getvalue().encode('utf-8'))

        # _tombstones.json: deletions newer than `since` that are in a
        # category the caller has access to. Each entry carries the
        # full export-shaped path so the client can `removeEntry()`
        # the matching local file without recomputing anything.
        tomb_wheres = []
        tomb_params = []
        if since_param:
            tomb_wheres.append("(deleted_at IS NOT NULL AND deleted_at >= ?)")
            tomb_params.append(since_param)
        if allowed:
            ph = ','.join(['?' for _ in allowed])
            tomb_wheres.append(f"(category IN ({ph}))")
            tomb_params.extend(sorted(allowed))
        tomb_where = (' WHERE ' + ' AND '.join(tomb_wheres)) if tomb_wheres else ''
        tomb_entries = []
        try:
            tomb_rows = db.execute(
                f"SELECT category, cat_label, group_path, ident_path, "
                f"       label, filename, deleted_at "
                f"FROM tombstones {tomb_where} "
                f"ORDER BY deleted_at",
                tomb_params,
            ).fetchall()
        except sqlite3.OperationalError:
            tomb_rows = []
        for t in tomb_rows:
            cat_label = t['cat_label'] or EXPORT_CATEGORY_LABELS.get(
                t['category'] or '', '')
            group = t['group_path'] or ''
            ident = t['ident_path'] or ''
            label = t['label'] or ''
            filename = t['filename'] or ''
            ext = ''
            if '.' in filename:
                ext = '.' + filename.rsplit('.', 1)[-1]
            base = f'{ident} — {label}{ext}' if label else f'{ident}{ext}'
            path = f'StuffFiles/{cat_label}/{group}/{base}'
            tomb_entries.append({
                'path':       path,
                'category':   t['category'],
                'filename':   filename,
                'deleted_at': t['deleted_at'],
            })
        zf.writestr('StuffFiles/_tombstones.json',
                    json.dumps({'tombstones': tomb_entries,
                                'since':      since_param or None,
                                'as_of':      datetime.utcnow().isoformat()
                                              + 'Z'}, indent=2).encode('utf-8'))

    tmp.close()
    ts = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    fname = f'StuffFiles-{user["email"].split("@")[0]}-{ts}.zip'
    # Delete the tempfile after Flask finishes streaming. send_file
    # opens its own descriptor for streaming, so unlink-after-response
    # is safe on POSIX (the open fd keeps the inode alive until the
    # response finishes).
    tmp_path = tmp.name
    user_id = user['id']

    @after_this_request
    def _cleanup(response):
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        # Bump last_export_at only when the response actually built
        # cleanly (status_code 200). Previously the bump ran BEFORE
        # send_file returned, so a Cloudflare timeout, browser close,
        # or any send_file exception left the user marked as having
        # exported when no zip ever reached them — the next sync's
        # `since` filter would then skip everything in the cancelled
        # export window. Moving the update here means a 5xx from
        # send_file (or an exception bubbling out of the view) leaves
        # last_export_at unchanged so the next click retries cleanly.
        if response.status_code == 200:
            try:
                db2 = get_db()
                db2.execute(
                    'UPDATE users SET last_export_at = ? WHERE id = ?',
                    (datetime.utcnow().isoformat(timespec='seconds'),
                     user_id),
                )
                db2.commit()
            except Exception:
                app.logger.exception(
                    'last_export_at bump failed for user %s', user_id
                )
        return response

    return send_file(tmp_path, as_attachment=True, download_name=fname,
                     mimetype='application/zip')


def _files_export_stale(db, user, allowed):
    """True when at least one record in the user's allowed categories
    has been touched (updated_at) since the user's last successful
    /export-files run, OR a server-side delete was tombstoned in the
    same window, OR the export has never run for this user. Honors
    per-user row filters so members don't see "stale" because of
    records they can't access. Returns (stale, last_export_at,
    latest_update)."""
    last = (user['last_export_at'] if 'last_export_at' in user.keys() else None) or None
    latest = None
    for cat in allowed:
        info = CATEGORIES.get(cat)
        if not info:
            continue
        wheres, params = [], []
        _apply_row_filter_clauses(cat, wheres, params)
        where_clause = f"WHERE {' AND '.join(wheres)}" if wheres else ''
        try:
            row = db.execute(
                f"SELECT MAX(updated_at) AS m FROM {info['table']} {where_clause}",
                params,
            ).fetchone()
        except sqlite3.OperationalError:
            continue
        m = row and row['m']
        if m and (latest is None or m > latest):
            latest = m
    # Tombstones: a delete in an allowed category since `last` should
    # also flip the indicator to stale so the user knows there's a
    # mirror-deletion waiting in the next syncDown.
    if allowed:
        ph = ','.join(['?' for _ in allowed])
        try:
            row = db.execute(
                f"SELECT MAX(deleted_at) AS m FROM tombstones "
                f"WHERE category IN ({ph})",
                sorted(allowed),
            ).fetchone()
            tomb_latest = row and row['m']
            if tomb_latest and (latest is None or tomb_latest > latest):
                latest = tomb_latest
        except sqlite3.OperationalError:
            pass
    if latest is None:
        # No data yet → not stale. Avoid a permanent red indicator on
        # an empty account.
        return (False, last, None)
    if not last:
        return (True, None, latest)
    return (latest > last, last, latest)


@app.route('/files-status', methods=['GET'])
def files_status():
    """JSON status for the nav Files indicator. Cheap query — runs on
    every page load via base.html."""
    user = g.get('current_user')
    if not user:
        return jsonify(stale=False), 200
    allowed = g.get('allowed_cats') or set()
    db = get_db()
    stale, last, latest = _files_export_stale(db, user, allowed)
    return jsonify(stale=stale, last_export_at=last, latest_update=latest)


def _build_record_index(db, category):
    """Return a list of (norm_group, norm_ident, row) tuples for fast
    matching during sweep. Pre-normalizes group + ident strings so we
    can match incoming filenames cheaply. Honors the current user's
    row filters so members can't sweep into records they can't see."""
    plan = EXPORT_LAYOUT.get(category)
    if not plan:
        return []
    table = CATEGORIES[category]['table']
    wheres, params = [], []
    _apply_row_filter_clauses(category, wheres, params)
    where_clause = f"WHERE {' AND '.join(wheres)}" if wheres else ''
    try:
        rows = db.execute(f"SELECT * FROM {table} {where_clause}", params).fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for row in rows:
        try:
            g_raw = plan['group'](row)
            i_raw = plan['ident'](row)
        except Exception:
            continue
        # Store as dict (not sqlite3.Row) so the sweep loop can mutate
        # it after each save. Without this, `row[chosen_field]` keeps
        # reporting the start-of-request value and multiple files in the
        # same record collapse onto the same first-empty slot.
        out.append((_norm(g_raw), _norm(i_raw), dict(row)))
    return out


def _parse_sweep_path(rel_path):
    """Pull (category, group, ident, label, ext, original_basename) out
    of a StuffFiles-style relative path. Returns None on parse failure
    so the caller can mark the file as unmatched.

    Recognises the optional "No longer Owned" interstitial that the
    export inserts between Category and Group for non-owned items —
    skipped here so the matching logic doesn't see it as a group name.
    """
    parts = [p for p in rel_path.split('/') if p]
    # Allow either StuffFiles/<Cat>/<Group>/<file> or just <Cat>/<Group>/<file>
    if parts and parts[0].lower() == 'stufffiles':
        parts = parts[1:]
    if len(parts) < 3:
        return None
    cat_label = parts[0]
    cat = EXPORT_LABEL_TO_CATEGORY.get(cat_label) \
        or EXPORT_LABEL_TO_CATEGORY.get(cat_label.title())
    if not cat:
        return None
    # Strip the "No longer Owned" routing folder if present.
    if len(parts) > 3 and parts[1].strip().lower() == 'no longer owned':
        parts = [parts[0]] + parts[2:]
    group, fname = parts[1], parts[-1]
    base, ext = os.path.splitext(fname)
    # "<Item> — <Label>" — split on the EM-DASH-with-spaces; if absent,
    # the whole base is the ident and we'll match the first empty slot.
    if ' — ' in base:
        ident, _, label = base.rpartition(' — ')
    else:
        ident, label = base, ''
    return {
        'category': cat,
        'group':    group,
        'ident':    ident.strip(),
        'label':    label.strip(),
        'ext':      ext,
        'original_basename': base + ext,
    }


# Cat-id-prefix sweep: if a dropped file's basename leads with a known
# cat_id (C### / W### / A###), or contains a parenthesised cat_id token
# anywhere (the export naming convention, e.g. 'Foo (W307) — Front.pdf'),
# bypass the StuffFiles/<Cat>/<Group>/... path parsing entirely and look
# up the record by cat_id. Lets the user drop an export-shaped file
# anywhere, or invent their own filename around a known (W###) tag.
#
# Accepts a 2+-digit serial (the live scheme is 3 digits, but old data
# or hand-typed names with fewer digits still match) and tolerates any
# of em-dash / en-dash / ASCII hyphen as the label separator.
_CAT_ID_SWEEP_PREFIXES = {'C': 'coins', 'W': 'watches', 'A': 'art'}
_CAT_ID_SWEEP_RE = re.compile(
    r'^\s*([CWA]\d{2,})\b\s*(?:[—–-]\s*(.+?))?\s*$',
    re.IGNORECASE,
)
# Parens form: '(W307)' anywhere in the basename. Strict on both sides
# (literal '(' and ')') so a stray substring like 'W307abc' inside a
# longer token can't trigger a misroute.
_CAT_ID_PARENS_RE = re.compile(r'\(([CWA]\d{2,})\)', re.IGNORECASE)


def _try_cat_id_sweep_match(db, filename):
    """If the basename matches '<CatId>[ — <Label>].<ext>' OR contains
    a '(<CatId>)' token (the export format, e.g.
    'Foo (W307) — Front.pdf'), look the record up directly. Returns
    (category, row_dict, target_label) or None. Label is empty when
    no ' — Label' suffix is present, and the slot resolver picks the
    first empty slot (or appends to the documents JSON for categories
    in DOCUMENTS_CATEGORIES)."""
    base, _ext = os.path.splitext(filename)
    m = _CAT_ID_SWEEP_RE.match(base)
    if m:
        cat_id_raw = m.group(1).upper()
        label = (m.group(2) or '').strip()
    else:
        m2 = _CAT_ID_PARENS_RE.search(base)
        if not m2:
            return None
        cat_id_raw = m2.group(1).upper()
        # Strip the (CatId) token; the part after ' — ' in what's left,
        # if any, is the slot label. Otherwise leave label empty so the
        # slot resolver picks the first empty slot (or appends to the
        # documents JSON for DOCUMENTS_CATEGORIES).
        remainder = (base[:m2.start()] + base[m2.end():]).strip()
        if ' — ' in remainder:
            label = remainder.rpartition(' — ')[2].strip()
        else:
            label = ''
    cat = _CAT_ID_SWEEP_PREFIXES.get(cat_id_raw[0])
    if not cat:
        return None
    table = CATEGORIES[cat]['table']
    row = db.execute(
        f"SELECT * FROM {table} "
        f"WHERE UPPER(TRIM(COALESCE(cat_id, ''))) = ?",
        (cat_id_raw,),
    ).fetchone()
    if not row:
        return None
    if not _user_can_see_row(cat, row):
        return None
    return cat, dict(row), label


@app.route('/<category>/<record_id>/print-pdf', methods=['GET'])
def record_print_pdf(category, record_id):
    """Generic per-record PDF: title + a 2-column key/value table of
    every populated field + the primary image (if any) inline. Works
    for all categories — uses FIELDS for ordering/labels."""
    if category not in CATEGORIES:
        abort(404)
    db = get_db()
    table = CATEGORIES[category]['table']
    row = db.execute(f"SELECT * FROM {table} WHERE id = ?", [record_id]).fetchone()
    if not row:
        abort(404)

    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                     Paragraph, Spacer, Image, KeepTogether,
                                     PageBreak)
    import io as _io

    plan = EXPORT_LAYOUT.get(category, {})
    cat_label = EXPORT_CATEGORY_LABELS.get(category, category.title())

    # Pretty title for the record — reuse the export ident if available.
    if plan.get('ident'):
        try:
            ident = plan['ident'](row) or row['id'][:8]
        except Exception:
            ident = row['id'][:8]
    else:
        ident = row['id'][:8]
    group = ''
    if plan.get('group'):
        try:
            group = plan['group'](row) or ''
        except Exception:
            group = ''

    buf = _io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter,
                            leftMargin=0.6 * inch, rightMargin=0.6 * inch,
                            topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle('h1', parent=styles['Heading1'], fontSize=18, spaceAfter=2)
    h2 = ParagraphStyle('h2', parent=styles['Heading2'], fontSize=13,
                        spaceAfter=10)
    sub = ParagraphStyle('sub', parent=styles['Normal'], fontSize=10,
                         textColor=colors.grey, spaceAfter=10)
    cell_style = ParagraphStyle('cell', parent=styles['Normal'],
                                fontSize=9, leading=11)

    story = []
    if category == 'watches':
        # Mirror the desktop UI: brand as the prominent H1, model
        # (with cat_id, e.g. "Reference 8 (W402)") as the sub-header.
        story.append(Paragraph(group or '(unknown brand)', h1))
        if ident:
            story.append(Paragraph(ident, h2))
    else:
        story.append(Paragraph(ident or '(untitled)', h1))
        sub_text = ' · '.join(filter(None, [cat_label, group]))
        if sub_text:
            story.append(Paragraph(sub_text, sub))

    # Find a primary image to embed near the top.
    fields = FIELDS.get(category, [])
    file_fields = [f['name'] for f in fields if f.get('type') == 'file']
    primary_img = None
    for cand in (CATEGORIES[category].get('image_field'),
                 'image', 'image_obv', 'image_1', 'image_front', 'head_shot'):
        if not cand: continue
        v = ''
        try: v = (row[cand] or '').strip()
        except (KeyError, IndexError): v = ''
        if v and is_image_filter(v):
            p = os.path.join(UPLOAD_FOLDER, v)
            if os.path.isfile(p):
                primary_img = p
                break

    # Long-text fields render as full-width sections below the spec
     # grid instead of getting cramped into a label/value table cell.
    # Includes any 'textarea' field plus a few text fields the user
    # treats as prose (calibre_notes, history_context).
    LONG_TEXT_FIELDS = {f['name'] for f in fields if f.get('type') == 'textarea'}
    LONG_TEXT_FIELDS |= {'calibre_notes', 'history_context'}

    def _val(name):
        try:
            v = row[name]
        except (KeyError, IndexError):
            return ''
        if v is None:
            return ''
        s = str(v).strip()
        return s

    def _spec_cell(label, value):
        """One label/value cell pair — Paragraph wrapping handles long
        values. Returns ['<value>', '<label>'] so the Table renders
        with the label-as-clabel underneath the value, matching the
        desktop UI's bottom-right label position."""
        return [Paragraph(value or '', cell_style),
                Paragraph(f'<font size=7 color="#888">{label}</font>',
                          cell_style)]

    if category == 'watches':
        # Top row: image left, structured spec grid right.
        spec_data = []
        # Brand specs — four dg2 pairs.
        for left_l, left_n, right_l, right_n in [
            ('Metal', 'metal', 'Width', 'case_diameter'),
            ('Ref', 'reference', 'Dial', 'dial_color'),
            ('Case#', 'case_num', 'Mvt#', 'movement_num'),
            ('Edition', 'edition', 'Yr Mfg', 'year'),
        ]:
            spec_data.append([Paragraph(_val(left_n), cell_style),
                              Paragraph(f'<font size=7 color="#888">{left_l}</font>', cell_style),
                              Paragraph(_val(right_n), cell_style),
                              Paragraph(f'<font size=7 color="#888">{right_l}</font>', cell_style)])
        # Movement specs — four dg2 pairs.
        beat_v = _val('beat')
        try:
            hz_v = '%.2g Hz' % (float(beat_v) / 7200) if beat_v else ''
        except (TypeError, ValueError):
            hz_v = ''
        reserve_v = _val('reserve')
        if reserve_v and not reserve_v.endswith('hrs'):
            reserve_v = f'{reserve_v} hrs'
        for left_l, left_v, right_l, right_v in [
            ('Calibre', _val('calibre'), 'Jewels', _val('movement_jewels')),
            ('Escapement', _val('escapement'), 'Origin', _val('movement_origin')),
            ('Beat', f'{int(float(beat_v)):,}' if beat_v else '', 'Hz (calc)', hz_v),
            ('Winding', _val('movement_type'), 'Reserve', reserve_v),
        ]:
            spec_data.append([Paragraph(left_v, cell_style),
                              Paragraph(f'<font size=7 color="#888">{left_l}</font>', cell_style),
                              Paragraph(right_v, cell_style),
                              Paragraph(f'<font size=7 color="#888">{right_l}</font>', cell_style)])

        # Image cell (left) + spec grid (right) side-by-side.
        img_cell = ''
        if primary_img:
            try:
                ir = ImageReader(primary_img)
                iw, ih = ir.getSize()
                max_w, max_h = 2.4 * inch, 3.0 * inch
                scale = min(max_w / iw, max_h / ih)
                img_cell = Image(primary_img, width=iw * scale, height=ih * scale)
            except Exception:
                pass

        # Right-side nested spec grid: value | label | value | label.
        # Column ratios mirror the desktop dgrid dg2 (each value cell
        # takes ~3x the width of its clabel).
        right_w = doc.width - 2.6 * inch
        spec_table = Table(
            spec_data,
            colWidths=[right_w * 0.35, right_w * 0.15,
                       right_w * 0.35, right_w * 0.15]
        )
        spec_table.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.lightgrey),
            # Tint the four movement rows (rows 4..7) grey to set them
            # apart from the brand specs above, matching the desktop.
            ('BACKGROUND', (0, 4), (-1, 7), colors.HexColor('#f4f4f6')),
        ]))
        outer = Table(
            [[img_cell, spec_table]],
            colWidths=[2.5 * inch, doc.width - 2.5 * inch]
        )
        outer.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(outer)
        story.append(Spacer(1, 6))

        # Full-width Balance Wheel + Calibre Notes rows.
        for label, name in [('Balance Wheel', 'balance_wheel'),
                            ('Calibre Notes', 'calibre_notes')]:
            v = _val(name)
            if v:
                tbl = Table([[Paragraph(v, cell_style),
                              Paragraph(f'<font size=7 color="#888">{label}</font>', cell_style)]],
                            colWidths=[doc.width * 0.85, doc.width * 0.15])
                tbl.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 4),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.lightgrey),
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f4f4f6')),
                ]))
                story.append(tbl)

        # Service / Strap / Purchase rows — short-field 4-up tables.
        def _kv4(triples):
            """Build a 4-column row of (label, value) pairs from a list
            of (label, name) tuples. Each cell is value-on-top, label
            below in small grey text."""
            cells = []
            for lbl, name in triples:
                v = _val(name)
                cells.extend([Paragraph(v, cell_style),
                              Paragraph(f'<font size=7 color="#888">{lbl}</font>', cell_style)])
            # Pad to 8 columns (4 value/label pairs).
            while len(cells) < 8:
                cells.extend(['', ''])
            return cells

        # Svc | Since
        svc_v = _val('service_date')
        try:
            from datetime import date as _date
            svc_d = _date.fromisoformat(svc_v) if svc_v else None
        except (TypeError, ValueError):
            svc_d = None
        since_v = ''
        if svc_d:
            today = datetime.utcnow().date()
            since_v = f'{(today - svc_d).days // 365} yrs'
        if svc_v or since_v:
            tbl = Table([_kv4([('Svc', 'service_date'), ('Since (calc)', None)])[:4]],
                        colWidths=[doc.width * 0.35, doc.width * 0.15,
                                   doc.width * 0.35, doc.width * 0.15])
            # Override the second value-cell to use the computed since_v.
            data = [[Paragraph(svc_v, cell_style),
                     Paragraph('<font size=7 color="#888">Svc</font>', cell_style),
                     Paragraph(since_v, cell_style),
                     Paragraph('<font size=7 color="#888">Since (calc)</font>', cell_style)]]
            tbl = Table(data, colWidths=[doc.width * 0.35, doc.width * 0.15,
                                          doc.width * 0.35, doc.width * 0.15])
            tbl.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ]))
            story.append(tbl)

        # Cell builder: value on top, small grey label underneath.
        # Mirrors the desktop UI where the clabel sits at the bottom
        # of each cell — and avoids the cramped 8-column-row problem
        # where short label tracks (~0.28") forced labels like
        # "Material" and "Vendor" to wrap to 2 or 3 lines.
        def _kv_cell(value, label):
            return Paragraph(
                f'{value}<br/><font size=7 color="#888">{label}</font>',
                cell_style
            )

        # Tang | Lug | Material | Color
        if any(_val(n) for n in ('clasp_type', 'lug_mm', 'strap_material', 'strap_color')):
            data = [[_kv_cell(_val('clasp_type'), 'Clasp'),
                     _kv_cell(_val('lug_mm'), 'Lug mm'),
                     _kv_cell(_val('strap_material'), 'Material'),
                     _kv_cell(_val('strap_color'), 'Color')]]
            tbl = Table(data, colWidths=[doc.width / 4] * 4)
            tbl.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ]))
            story.append(tbl)

        # Date | Price | Vendor | Value
        price_v = _val('price')
        try:
            price_v = '${:,.0f}'.format(float(price_v)) if price_v else ''
        except (TypeError, ValueError):
            pass
        value_v = _val('value')
        try:
            value_v = '${:,.0f}'.format(float(value_v)) if value_v else ''
        except (TypeError, ValueError):
            pass
        if any([_val('date'), price_v, _val('vendor'), value_v]):
            data = [[_kv_cell(_val('date'), 'Date'),
                     _kv_cell(price_v, 'Price'),
                     _kv_cell(_val('vendor'), 'Vendor'),
                     _kv_cell(value_v, 'Value')]]
            tbl = Table(data, colWidths=[doc.width / 4] * 4)
            tbl.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 4),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ]))
            story.append(tbl)

        # Complications (single full-width line).
        comp_v = _val('complications')
        if comp_v:
            story.append(Spacer(1, 4))
            story.append(Paragraph(f'<b>Complications:</b> {comp_v}', cell_style))

        # Owner | Property | Status (small footer line).
        op_bits = []
        for lbl, name in [('Owner', 'owner'), ('Property', 'property'), ('Status', 'status')]:
            v = _val(name)
            if v:
                op_bits.append(f'<b>{lbl}:</b> {v}')
        if op_bits:
            story.append(Spacer(1, 4))
            story.append(Paragraph(' &nbsp;·&nbsp; '.join(op_bits), cell_style))

        # Long-text sections — full-width prose blocks for description,
        # notes, results, history_context. Each gets its own bold
        # heading followed by the text content, with the text using
        # the page's full inner width (no narrow column).
        long_section_style = ParagraphStyle(
            'long', parent=cell_style, fontSize=9, leading=12, spaceAfter=4
        )
        for name, label in [('description', 'Description'),
                            ('notes', 'Notes'),
                            ('results', 'Value Estimate from Retailers and Recent Auctions')]:
            v = _val(name)
            if v:
                story.append(Spacer(1, 8))
                story.append(Paragraph(f'<b>{label}</b>', cell_style))
                # Preserve paragraph breaks: split on double newline,
                # render each as its own Paragraph so blank lines
                # become real spacing.
                for para in v.split('\n\n'):
                    para = para.replace('\n', '<br/>')
                    story.append(Paragraph(para, long_section_style))

    else:
        # Generic (non-watches) layout — image at top, then a 2-col
        # key/value table for short fields, plus full-width sections
        # for long-text fields underneath.
        if primary_img:
            try:
                ir = ImageReader(primary_img)
                iw, ih = ir.getSize()
                max_w, max_h = 4.0 * inch, 3.5 * inch
                scale = min(max_w / iw, max_h / ih)
                story.append(Image(primary_img, width=iw * scale, height=ih * scale))
                story.append(Spacer(1, 8))
            except Exception:
                pass

        short_rows = []
        long_sections = []
        for f in fields:
            name = f['name']
            if f.get('type') == 'file': continue
            if name in ('id', 'created_at', 'updated_at'): continue
            try:
                v = row[name]
            except (KeyError, IndexError):
                continue
            if v is None or (isinstance(v, str) and not v.strip()):
                continue
            label = f.get('label') or name
            if name in LONG_TEXT_FIELDS:
                long_sections.append((label, str(v)))
            else:
                short_rows.append((label, str(v)))

        if short_rows:
            col_w = (doc.width / 2) - 4
            data = []
            for i in range(0, len(short_rows), 2):
                left = short_rows[i]
                right = short_rows[i + 1] if i + 1 < len(short_rows) else ('', '')
                data.append([
                    Paragraph(f'<b>{left[0]}</b>', cell_style),
                    Paragraph(left[1], cell_style),
                    Paragraph(f'<b>{right[0]}</b>', cell_style) if right[0] else '',
                    Paragraph(right[1], cell_style) if right[1] else '',
                ])
            tbl = Table(data, colWidths=[col_w * 0.35, col_w * 0.65,
                                          col_w * 0.35, col_w * 0.65])
            tbl.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
                ('LINEBELOW', (0, 0), (-1, -1), 0.25, colors.lightgrey),
            ]))
            story.append(tbl)

        # Full-width long-text sections for non-watches categories.
        long_section_style = ParagraphStyle(
            'long', parent=cell_style, fontSize=9, leading=12, spaceAfter=4
        )
        for label, text in long_sections:
            story.append(Spacer(1, 8))
            story.append(Paragraph(f'<b>{label}</b>', cell_style))
            for para in text.split('\n\n'):
                para = para.replace('\n', '<br/>')
                story.append(Paragraph(para, long_section_style))

    # Append remaining file fields as a small "Documents" list
    other_files = [f for f in file_fields if not (primary_img and
                  os.path.basename(primary_img) == (
                      (lambda v: v if v else '')(row[f] if f in row.keys() else '')))]
    docs = []
    for f in other_files:
        try:
            v = (row[f] or '').strip()
        except (KeyError, IndexError):
            continue
        if not v:
            continue
        docs.append(f'{f}: {v}')
    if docs:
        story.append(Spacer(1, 12))
        story.append(Paragraph('<b>Files on this record</b>', cell_style))
        for d in docs:
            story.append(Paragraph(d, cell_style))

    doc.build(story)
    buf.seek(0)
    safe_ident = re.sub(r'[^A-Za-z0-9._ -]', '', ident)[:80].strip() or row['id'][:8]
    return send_file(buf, as_attachment=True,
                     download_name=f'{cat_label} — {safe_ident}.pdf',
                     mimetype='application/pdf')


# ---------------------------------------------------------------------------
# Inventory report — compact one-document summary across categories.
# Two layouts (detailed=thumbnail card, compact=spreadsheet row), filtered
# by a chosen subset of categories and properties. Used for owner-side
# "give me a printable list of everything" workflows on both the primary
# (Mark) deployment and tenant deployments (e.g. Gerri).
# ---------------------------------------------------------------------------

# Compact-mode columns per category — short label + db column name. Picked
# to land 6–8 columns wide so a row fits on Letter portrait without wrap.
REPORT_COMPACT_COLS = {
    'watches':      [('Brand', 'brand'), ('Model', 'model'), ('Ref', 'reference'),
                     ('Year', 'year'),
                     ('Owner', 'owner'), ('Property', 'property'),
                     ('Status', 'status'),
                     ('Bought', 'date'), ('Price', 'price')],
    'coins':        [('Cat', 'cat_id'), ('Authority', 'authority'),
                     ('Denom', 'denomination'), ('Minted', 'date_1'),
                     ('Grade', 'grade'),
                     ('Owner', 'owner'), ('Property', 'property_name'),
                     ('Bought', 'purchase_date'), ('Price', 'price')],
    'cameras':      [('Make', 'make'), ('Model', 'model'),
                     ('Serial', 'serial_number'),
                     ('Owner', 'owner'), ('Property', 'property'),
                     ('Status', 'status'),
                     ('Bought', 'date'), ('Price', 'price')],
    'lenses':       [('Make', 'make'), ('Model', 'model'),
                     ('Serial', 'serial_number'),
                     ('Owner', 'owner'), ('Property', 'property'),
                     ('Bought', 'date'), ('Price', 'price')],
    'pens':         [('Make', 'make'), ('Model', 'model'),
                     ('Type', 'type'),
                     ('Owner', 'owner'), ('Property', 'property'),
                     ('Bought', 'date'), ('Price', 'price')],
    'art':          [('Artist', 'artist'), ('Title', 'title'),
                     ('Year', 'year'),
                     ('Owner', 'owner'), ('Property', 'property'),
                     ('Bought', 'date'), ('Price', 'price')],
    'items':        [('Name', 'name'), ('Type', 'type'),
                     ('Owner', 'owner'), ('Property', 'property'),
                     ('Status', 'status'),
                     ('Bought', 'date'), ('Price', 'price')],
    'vehicles':     [('Year', 'year'), ('Make', 'make'), ('Model', 'model'),
                     ('VIN', 'vin'),
                     ('Owner', 'owner'), ('Property', 'property'),
                     ('Bought', 'date'), ('Price', 'price')],
    'recordings':   [('Artist', 'artist'), ('Title', 'title'),
                     ('Type', 'recording_type'),
                     ('Owner', 'owner'), ('Property', 'property'),
                     ('Bought', 'date'), ('Price', 'price')],
    'audio':        [('Make', 'make'), ('Model', 'model'),
                     ('Type', 'type'),
                     ('Owner', 'owner'), ('Property', 'property'),
                     ('Bought', 'date'), ('Price', 'price')],
    'rifles':       [('Make', 'make'), ('Model', 'model'),
                     ('Caliber', 'caliber'), ('Serial', 'serial_number'),
                     ('Owner', 'owner'), ('Property', 'property'),
                     ('Bought', 'date'), ('Price', 'price')],
    'credit_cards': [('Name', 'name'), ('Number', 'number'),
                     ('Owner', 'owner')],
    'properties':   [('Name', 'name'), ('Address', 'address'),
                     ('Type', 'type'), ('Status', 'status'),
                     ('Owner', 'owner'),
                     ('Bought', 'date'), ('Price', 'price')],
    'persons':      [('Name', 'name'), ('Phone', 'phone'),
                     ('Email', 'email')],
}


# Detailed-mode caption fields per category — short label/value pairs
# printed next to each thumbnail. Same Bought/Price additions as
# compact mode so both layouts surface acquisition cost.
REPORT_DETAILED_FIELDS = {
    'watches':      [('Ref', 'reference'), ('Year', 'year'),
                     ('Metal', 'metal'), ('Owner', 'owner'),
                     ('Property', 'property'), ('Status', 'status'),
                     ('Bought', 'date'), ('Price', 'price')],
    'coins':        [('Minted', 'date_1'), ('Mint', 'mint'),
                     ('Grade', 'grade'), ('Metal', 'metal'),
                     ('Owner', 'owner'), ('Property', 'property_name'),
                     ('Bought', 'purchase_date'), ('Price', 'price')],
    'cameras':      [('Serial', 'serial_number'), ('Owner', 'owner'),
                     ('Property', 'property'), ('Status', 'status'),
                     ('Bought', 'date'), ('Price', 'price')],
    'lenses':       [('Serial', 'serial_number'), ('Owner', 'owner'),
                     ('Property', 'property'),
                     ('Bought', 'date'), ('Price', 'price')],
    'pens':         [('Type', 'type'), ('Owner', 'owner'),
                     ('Property', 'property'),
                     ('Bought', 'date'), ('Price', 'price')],
    'art':          [('Year', 'year'), ('Medium', 'medium'),
                     ('Owner', 'owner'), ('Property', 'property'),
                     ('Bought', 'date'), ('Price', 'price')],
    'items':        [('Type', 'type'), ('Owner', 'owner'),
                     ('Property', 'property'), ('Status', 'status'),
                     ('Bought', 'date'), ('Price', 'price')],
    'vehicles':     [('VIN', 'vin'), ('Owner', 'owner'),
                     ('Property', 'property'),
                     ('Bought', 'date'), ('Price', 'price')],
    'recordings':   [('Type', 'recording_type'), ('Owner', 'owner'),
                     ('Property', 'property'),
                     ('Bought', 'date'), ('Price', 'price')],
    'audio':        [('Type', 'type'), ('Owner', 'owner'),
                     ('Property', 'property'),
                     ('Bought', 'date'), ('Price', 'price')],
    'rifles':       [('Caliber', 'caliber'), ('Serial', 'serial_number'),
                     ('Owner', 'owner'), ('Property', 'property'),
                     ('Bought', 'date'), ('Price', 'price')],
    'credit_cards': [('Number', 'number'), ('Owner', 'owner')],
    'properties':   [('Address', 'address'), ('Type', 'type'),
                     ('Status', 'status'), ('Owner', 'owner'),
                     ('Bought', 'date'), ('Price', 'price')],
    'persons':      [('Phone', 'phone'), ('Email', 'email')],
}


def _format_report_value(field_name, value):
    """Stringify a row value for the report. Money fields get
    "$1,234" formatting (drops the .0 SQLite returns for REAL
    columns and the bare int otherwise prints with no thousands
    separator). Everything else passes through unchanged."""
    if value is None:
        return ''
    if field_name in ('price', 'value'):
        try:
            return '${:,.0f}'.format(float(value))
        except (TypeError, ValueError):
            pass
    return str(value).strip()


def _format_money(value):
    """Compact money formatter for HTML report views."""
    if value is None or value == '':
        return ''
    try:
        return '${:,.0f}'.format(float(str(value).replace(',', '').replace('$', '')))
    except (TypeError, ValueError):
        return str(value).strip()


def _report_record_title(category, row):
    """Row identifier used as the bold header line in detailed mode and
    the leading column in compact mode. Reuses EXPORT_LAYOUT's ident
    when defined so report titles match the export-folder naming."""
    plan = EXPORT_LAYOUT.get(category, {})
    try:
        if plan.get('ident'):
            return (plan['ident'](row) or '').strip()
    except Exception:
        pass
    info = CATEGORIES.get(category, {})
    lf = info.get('label_field')
    sf = info.get('sublabel_field')
    parts = []
    for f in (lf, sf):
        if not f:
            continue
        try:
            v = row[f]
        except (KeyError, IndexError):
            v = None
        if v:
            parts.append(str(v).strip())
    return ' '.join(parts).strip() or (row['id'][:8] if 'id' in row.keys() else '')


def _report_property_predicate(category, properties):
    """SQL fragment + params restricting `category` rows to the given
    property names. Returns ('', []) when no filter applies (all
    properties chosen, or category has no property field)."""
    if not properties:
        return '', []
    # Properties category itself: match by name.
    if category == 'properties':
        ph = ','.join(['?' for _ in properties])
        return f"(LOWER(TRIM(COALESCE(name,''))) IN ({ph}))", \
               [p.lower().strip() for p in properties]
    prop_col = CATEGORY_PROPERTY_FIELD.get(category)
    if not prop_col:
        # Category has no property field — return a never-true predicate
        # so a property-restricted run yields zero rows for it instead
        # of returning the entire table.
        return '(1=0)', []
    expanded = []
    for p in properties:
        expanded.extend(_property_alias_group(p))
    if not expanded:
        return '', []
    seen, dedup = set(), []
    for v in expanded:
        if v not in seen:
            seen.add(v)
            dedup.append(v)
    ph = ','.join(['?' for _ in dedup])
    return f"(LOWER(TRIM(COALESCE({prop_col},''))) IN ({ph}))", dedup


def _report_primary_image(category, row):
    """Absolute path to a thumbnail-able cover image for this row, or
    None when no image is on disk."""
    candidates = []
    info_field = CATEGORIES.get(category, {}).get('image_field')
    if info_field:
        candidates.append(info_field)
    candidates.extend(['image', 'image_obv', 'image_1', 'image_front',
                       'head_shot'])
    seen = set()
    for c in candidates:
        if not c or c in seen:
            continue
        seen.add(c)
        try:
            v = (row[c] or '').strip()
        except (KeyError, IndexError):
            continue
        if v and is_image_filter(v):
            p = os.path.join(UPLOAD_FOLDER, v)
            if os.path.isfile(p):
                return p
    return None


@app.route('/report/options', methods=['GET'])
def report_options():
    """JSON: categories the current user can include in a report, plus
    the deployment's property names. Drives the Report dialog's
    checkbox groups."""
    if not g.get('current_user'):
        abort(403)
    allowed = g.get('allowed_cats') or set()
    cats = [
        {'slug': slug, 'label': CATEGORIES[slug]['name'],
         'icon':  CATEGORIES[slug].get('icon', '')}
        for slug in CATEGORIES if slug in allowed
    ]
    # Owned + Residential first (same predicate the rest of the app's
    # property dropdowns use), then filter down to properties that
    # actually have at least one item in one of the user's allowed
    # categories — listing a property with zero items in the report
    # dialog is just noise.
    candidates = get_property_choices()
    used_aliases = _report_used_property_aliases(allowed)
    props = [
        p for p in candidates
        if any(a in used_aliases for a in _property_alias_group(p))
    ]
    return jsonify({'categories': cats, 'properties': props})


@app.route('/admin/watch-acquisitions', methods=['GET'])
def admin_watch_acquisitions():
    """Annual acquisitions report for watches and coins.

    Strawman admin view: pick a purchase year and review the watches and
    coins acquired in that year, with quick summary cuts by month, owner,
    property, status, and vendor.
    """
    db = get_db()
    years = [
        row['year'] for row in db.execute(
            "SELECT DISTINCT year FROM ("
            "  SELECT SUBSTR(date, 1, 4) AS year "
            "  FROM watches "
            "  WHERE date IS NOT NULL "
            "    AND TRIM(date) != '' "
            "    AND date GLOB '[0-9][0-9][0-9][0-9]-*' "
            "  UNION "
            "  SELECT SUBSTR(purchase_date, 1, 4) AS year "
            "  FROM coins "
            "  WHERE purchase_date IS NOT NULL "
            "    AND TRIM(purchase_date) != '' "
            "    AND purchase_date GLOB '[0-9][0-9][0-9][0-9]-*'"
            ") WHERE year IS NOT NULL ORDER BY year DESC"
        ).fetchall()
        if row['year']
    ]
    default_year = years[0] if years else str(datetime.utcnow().year)
    year = (request.args.get('year') or default_year).strip()
    if not re.fullmatch(r'\d{4}', year):
        year = default_year

    rows = db.execute(
        "SELECT * FROM watches "
        "WHERE date IS NOT NULL "
        "  AND TRIM(date) != '' "
        "  AND SUBSTR(date, 1, 4) = ? "
        "ORDER BY date ASC, "
        "         COALESCE(NULLIF(brand, ''), 'zzz') COLLATE NODIACRITIC, "
        "         COALESCE(NULLIF(model, ''), 'zzz') COLLATE NODIACRITIC",
        [year],
    ).fetchall()

    watches = []
    total_spend = 0.0
    known_price_count = 0
    for row in rows:
        price = None
        if row['price'] not in (None, ''):
            try:
                price = float(str(row['price']).replace(',', '').replace('$', ''))
                total_spend += price
                known_price_count += 1
            except (TypeError, ValueError):
                price = None
        value = None
        if 'value' in row.keys() and row['value'] not in (None, ''):
            try:
                value = float(str(row['value']).replace(',', '').replace('$', ''))
            except (TypeError, ValueError):
                value = None
        image = (row['image_obv'] or '').strip()
        watches.append({
            'row': row,
            'title': _report_record_title('watches', row),
            'month': row['date'][5:7] if row['date'] and len(row['date']) >= 7 else '',
            'price_number': price,
            'value_number': value,
            'price_display': _format_money(row['price']),
            'value_display': _format_money(row['value']) if 'value' in row.keys() else '',
            'delta_display': _format_money(value - price) if value is not None and price is not None else '',
            'image': image if image and is_image_filter(image) else '',
        })

    def bucket_counts(field):
        counts = {}
        spend = {}
        for item in watches:
            row = item['row']
            label = (row[field] or '').strip() if field in row.keys() else ''
            if not label:
                label = 'Unspecified'
            counts[label] = counts.get(label, 0) + 1
            spend[label] = spend.get(label, 0.0) + (item['price_number'] or 0.0)
        return [
            {'label': label, 'count': counts[label], 'spend': spend[label]}
            for label in sorted(counts, key=lambda k: (-counts[k], k.lower()))
        ]

    month_names = [
        'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
        'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
    ]
    monthly = []
    for index, name in enumerate(month_names, start=1):
        key = f'{index:02d}'
        items = [item for item in watches if item['month'] == key]
        monthly.append({
            'month': name,
            'count': len(items),
            'spend': sum(item['price_number'] or 0.0 for item in items),
        })

    most_expensive = sorted(
        [item for item in watches if item['price_number'] is not None],
        key=lambda item: item['price_number'],
        reverse=True,
    )[:5]
    avg_spend = total_spend / known_price_count if known_price_count else 0

    coin_rows = db.execute(
        "SELECT * FROM coins "
        "WHERE purchase_date IS NOT NULL "
        "  AND TRIM(purchase_date) != '' "
        "  AND SUBSTR(purchase_date, 1, 4) = ? "
        "ORDER BY purchase_date ASC, "
        "         COALESCE(NULLIF(region, ''), 'zzz') COLLATE NODIACRITIC, "
        "         COALESCE(NULLIF(authority, ''), 'zzz') COLLATE NODIACRITIC, "
        "         COALESCE(NULLIF(denomination, ''), 'zzz') COLLATE NODIACRITIC",
        [year],
    ).fetchall()

    coins = []
    coin_total_spend = 0.0
    coin_known_price_count = 0
    for row in coin_rows:
        price = None
        if row['price'] not in (None, ''):
            try:
                price = float(str(row['price']).replace(',', '').replace('$', ''))
                coin_total_spend += price
                coin_known_price_count += 1
            except (TypeError, ValueError):
                price = None
        image = (row['image_1'] or '').strip()
        date_text = (row['date_1_text'] or '').strip()
        if not date_text and row['date_1'] not in (None, ''):
            try:
                date_num = int(row['date_1'])
                date_text = f"{abs(date_num)} BC" if date_num < 0 else str(date_num)
            except (TypeError, ValueError):
                date_text = str(row['date_1']).strip()
        coins.append({
            'row': row,
            'title': _report_record_title('coins', row),
            'month': row['purchase_date'][5:7] if row['purchase_date'] and len(row['purchase_date']) >= 7 else '',
            'price_number': price,
            'price_display': _format_money(row['price']),
            'date_text': date_text,
            'image': image if image and is_image_filter(image) else '',
        })

    def coin_bucket_counts(field):
        counts = {}
        spend = {}
        for item in coins:
            row = item['row']
            label = (row[field] or '').strip() if field in row.keys() else ''
            if not label:
                label = 'Unspecified'
            counts[label] = counts.get(label, 0) + 1
            spend[label] = spend.get(label, 0.0) + (item['price_number'] or 0.0)
        return [
            {'label': label, 'count': counts[label], 'spend': spend[label]}
            for label in sorted(counts, key=lambda k: (-counts[k], k.lower()))
        ]

    coin_monthly = []
    for index, name in enumerate(month_names, start=1):
        key = f'{index:02d}'
        items = [item for item in coins if item['month'] == key]
        coin_monthly.append({
            'month': name,
            'count': len(items),
            'spend': sum(item['price_number'] or 0.0 for item in items),
        })
    coin_most_expensive = sorted(
        [item for item in coins if item['price_number'] is not None],
        key=lambda item: item['price_number'],
        reverse=True,
    )[:5]
    coin_avg_spend = (
        coin_total_spend / coin_known_price_count
        if coin_known_price_count else 0
    )

    return render_template(
        'watch_acquisitions.html',
        current_category='__admin__',
        categories=CATEGORIES,
        counts=get_counts(),
        year=year,
        years=years,
        watches=watches,
        total_spend=total_spend,
        avg_spend=avg_spend,
        known_price_count=known_price_count,
        monthly=monthly,
        by_owner=bucket_counts('owner'),
        by_property=bucket_counts('property'),
        by_status=bucket_counts('status'),
        by_vendor=bucket_counts('vendor')[:10],
        most_expensive=most_expensive,
        coins=coins,
        coin_total_spend=coin_total_spend,
        coin_avg_spend=coin_avg_spend,
        coin_known_price_count=coin_known_price_count,
        coin_monthly=coin_monthly,
        coins_by_owner=coin_bucket_counts('owner'),
        coins_by_property=coin_bucket_counts('property_name'),
        coins_by_status=coin_bucket_counts('status'),
        coins_by_vendor=coin_bucket_counts('vendor')[:10],
        coin_most_expensive=coin_most_expensive,
    )


def _money_number(value):
    if value in (None, ''):
        return None
    try:
        return float(str(value).replace(',', '').replace('$', ''))
    except (TypeError, ValueError):
        return None


def _coin_date_label(row):
    text = (row['date_1_text'] or '').strip()
    if text:
        if row['date_2_text']:
            return f"{text} – {row['date_2_text']}"
        return text
    if row['date_1'] not in (None, ''):
        try:
            start = int(row['date_1'])
            start_text = f"{abs(start)} BC" if start < 0 else str(start)
            if row['date_2'] not in (None, ''):
                end = int(row['date_2'])
                return f"{start_text} – {abs(end)} BC" if end < 0 else f"{start_text} – {end}"
            return start_text
        except (TypeError, ValueError):
            return str(row['date_1']).strip()
    return ''


def _coin_scope_predicate(scope):
    if scope == 'ancient':
        return 'date_1 < 500', []
    if scope == 'modern':
        return '(date_1 >= 500 OR date_1 IS NULL)', []
    return '1=1', []


def _coin_collection_buckets(items, field, limit=None):
    counts = {}
    spend = {}
    for item in items:
        row = item['row']
        label = (row[field] or '').strip() if field in row.keys() else ''
        if not label:
            label = 'Unspecified'
        counts[label] = counts.get(label, 0) + 1
        spend[label] = spend.get(label, 0.0) + (item['price_number'] or 0.0)
    rows = [
        {'label': label, 'count': counts[label], 'spend': spend[label]}
        for label in sorted(counts, key=lambda k: (-counts[k], k.lower()))
    ]
    return rows[:limit] if limit else rows


def _coin_collection_narrative(scope_label, q, summary, top_regions,
                               top_authorities, top_references,
                               era_rows):
    total = summary['total']
    if not total:
        return [
            f"No coins match this {scope_label.lower()} report"
            + (f" for “{q}”." if q else ".")
        ]

    scope_phrase = scope_label.lower()
    search_phrase = f" matching “{q}”" if q else ''
    ancient = summary['ancient_count']
    modern = summary['modern_count']
    oldest = summary.get('oldest_label') or 'undated'
    newest = summary.get('newest_label') or 'undated'
    refs = summary['with_refs']
    priced = summary['known_price_count']

    region_text = ', '.join(
        f"{r['label']} ({r['count']})" for r in top_regions[:3]
        if r['label'] != 'Unspecified'
    )
    authority_text = ', '.join(
        f"{r['label']} ({r['count']})" for r in top_authorities[:3]
        if r['label'] != 'Unspecified'
    )
    era_text = ', '.join(
        f"{r['label']} ({r['count']})" for r in era_rows
        if r['count']
    )
    reference_text = ', '.join(
        f"{r['label']} ({r['count']})" for r in top_references[:3]
        if r['label'] != 'Unspecified'
    )

    lines = [
        f"This {scope_phrase} coin report{search_phrase} covers {total} coins, "
        f"spanning {oldest} to {newest}. It currently breaks out as "
        f"{ancient} ancient and {modern} modern or undated records.",
        f"Reference coverage is {refs} of {total} records, with {priced} priced "
        f"records totaling {_format_money(summary['total_spend'])}. The report "
        "is meant to surface pedigree, catalog trail, and acquisition context "
        "alongside the basic inventory facts.",
    ]
    if region_text:
        lines.append(f"The strongest regional concentrations are {region_text}.")
    if authority_text:
        lines.append(f"Leading authorities or issuers are {authority_text}.")
    if era_text:
        lines.append(f"Chronologically, the collection clusters around {era_text}.")
    if reference_text:
        lines.append(f"The most common reference signals are {reference_text}.")
    return lines


def _table_column_names(db, table):
    return {
        row['name'] for row in db.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _item_report_row_value(row, columns, *names):
    for name in names:
        if name in columns:
            value = row[name]
            if value not in (None, ''):
                return str(value).strip()
    return ''


def _item_report_date(row, columns):
    return _item_report_row_value(
        row, columns, 'purchase_date', 'date', 'service_date', 'created_at'
    )


def _item_report_search_columns(columns):
    excluded = {
        'image', 'image_obv', 'image_1', 'image_2', 'image_front',
        'head_shot', 'receipt', 'document', 'document_1', 'document_2',
        'documents', 'container_1', 'container_2',
    }
    return [c for c in columns if c not in excluded]


def _item_report_bucket(items, key, limit=None):
    counts = {}
    spend = {}
    for item in items:
        label = (item.get(key) or '').strip() or 'Unspecified'
        counts[label] = counts.get(label, 0) + 1
        spend[label] = spend.get(label, 0.0) + (item.get('price_number') or 0.0)
    rows = [
        {'label': label, 'count': counts[label], 'spend': spend[label]}
        for label in sorted(counts, key=lambda k: (-counts[k], k.lower()))
    ]
    return rows[:limit] if limit else rows


def _item_type_narrative(type_label, q, summary, by_type, by_property,
                         by_owner, by_status):
    total = summary['total']
    if not total:
        return [
            f"No records match this {type_label.lower()} report"
            + (f" for “{q}”." if q else ".")
        ]
    search_phrase = f" matching “{q}”" if q else ''
    lines = [
        f"This {type_label.lower()} report{search_phrase} covers {total} records "
        f"across {summary['type_count']} item type"
        f"{'' if summary['type_count'] == 1 else 's'}.",
        f"{summary['priced_count']} records carry a price, totaling "
        f"{_format_money(summary['total_spend'])}. {summary['with_images']} "
        f"records have a primary image available for review.",
    ]
    type_text = ', '.join(
        f"{r['label']} ({r['count']})" for r in by_type[:5]
        if r['label'] != 'Unspecified'
    )
    property_text = ', '.join(
        f"{r['label']} ({r['count']})" for r in by_property[:5]
        if r['label'] != 'Unspecified'
    )
    owner_text = ', '.join(
        f"{r['label']} ({r['count']})" for r in by_owner[:4]
        if r['label'] != 'Unspecified'
    )
    status_text = ', '.join(
        f"{r['label']} ({r['count']})" for r in by_status[:4]
        if r['label'] != 'Unspecified'
    )
    if type_text:
        lines.append(f"The largest item-type blocks are {type_text}.")
    if property_text:
        lines.append(f"The most represented properties are {property_text}.")
    if owner_text:
        lines.append(f"Ownership is concentrated in {owner_text}.")
    if status_text:
        lines.append(f"Status mix: {status_text}.")
    return lines


@app.route('/admin/coin-collections', methods=['GET'])
def admin_coin_collections():
    """Coin collection report, filterable by all / ancient / modern."""
    db = get_db()
    scope = (request.args.get('scope') or 'all').strip().lower()
    if scope not in ('all', 'ancient', 'modern'):
        scope = 'all'
    q = (request.args.get('q') or '').strip()

    scope_clause, scope_params = _coin_scope_predicate(scope)
    where, params = [scope_clause], list(scope_params)
    if q:
        like = f"%{q.lower()}%"
        fields = [
            'coin_id', 'cat_id', 'region', 'authority', 'official',
            'denomination', 'metal', 'mint', 'date_1_text',
            'description', 'coin_references', 'notes', 'condition',
            'grade', 'vendor', 'owner', 'property_name', 'status',
        ]
        where.append('(' + ' OR '.join(
            f"LOWER(COALESCE({field}, '')) LIKE ?" for field in fields
        ) + ')')
        params.extend([like] * len(fields))

    sql = (
        "SELECT * FROM coins "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY CASE WHEN date_1 IS NULL THEN 1 ELSE 0 END, "
        "         date_1 ASC, "
        "         COALESCE(NULLIF(region, ''), 'zzz') COLLATE NODIACRITIC, "
        "         COALESCE(NULLIF(authority, ''), 'zzz') COLLATE NODIACRITIC, "
        "         COALESCE(NULLIF(denomination, ''), 'zzz') COLLATE NODIACRITIC"
    )
    rows = db.execute(sql, params).fetchall()

    coins = []
    total_spend = 0.0
    known_price_count = 0
    with_refs = 0
    with_images = 0
    ancient_count = 0
    modern_count = 0
    oldest_label = ''
    newest_label = ''
    era_counts = {
        'Archaic / Early': 0,
        'Classical': 0,
        'Hellenistic': 0,
        'Roman / Late Antique': 0,
        'Modern / Undated': 0,
    }
    reference_counts = {}

    for row in rows:
        price = _money_number(row['price'])
        if price is not None:
            total_spend += price
            known_price_count += 1
        image = (row['image_1'] or '').strip()
        if image and is_image_filter(image):
            with_images += 1
        date_label = _coin_date_label(row)
        if row['date_1'] not in (None, ''):
            try:
                d = int(row['date_1'])
                if d < 500:
                    ancient_count += 1
                    if d <= -480:
                        era_counts['Archaic / Early'] += 1
                    elif d <= -323:
                        era_counts['Classical'] += 1
                    elif d <= -31:
                        era_counts['Hellenistic'] += 1
                    else:
                        era_counts['Roman / Late Antique'] += 1
                else:
                    modern_count += 1
                    era_counts['Modern / Undated'] += 1
            except (TypeError, ValueError):
                modern_count += 1
                era_counts['Modern / Undated'] += 1
        else:
            modern_count += 1
            era_counts['Modern / Undated'] += 1

        if date_label:
            if not oldest_label:
                oldest_label = date_label
            newest_label = date_label

        refs = (row['coin_references'] or '').strip()
        if refs:
            with_refs += 1
            for pattern in [
                'BCD', 'SNG', 'HGC', 'RIC', 'RPC', 'Crawford',
                'Ravel', 'Calciati', 'CNG', 'Roma', 'ANS', 'BMC',
                'Jameson', 'Weber', 'Boston MFA',
            ]:
                if re.search(rf'\b{re.escape(pattern)}\b', refs, re.IGNORECASE):
                    reference_counts[pattern] = reference_counts.get(pattern, 0) + 1

        coins.append({
            'row': row,
            'title': _report_record_title('coins', row),
            'date_label': date_label,
            'price_number': price,
            'price_display': _format_money(row['price']),
            'image': image if image and is_image_filter(image) else '',
            'has_refs': bool(refs),
        })

    scope_labels = {
        'all': 'All Coins',
        'ancient': 'Ancient Coins',
        'modern': 'Modern Coins',
    }
    summary = {
        'total': len(coins),
        'ancient_count': ancient_count,
        'modern_count': modern_count,
        'with_refs': with_refs,
        'with_images': with_images,
        'known_price_count': known_price_count,
        'total_spend': total_spend,
        'avg_spend': total_spend / known_price_count if known_price_count else 0,
        'oldest_label': oldest_label,
        'newest_label': newest_label,
    }
    by_region = _coin_collection_buckets(coins, 'region', 12)
    by_authority = _coin_collection_buckets(coins, 'authority', 12)
    by_metal = _coin_collection_buckets(coins, 'metal', 10)
    by_denomination = _coin_collection_buckets(coins, 'denomination', 10)
    by_property = _coin_collection_buckets(coins, 'property_name', 10)
    by_vendor = _coin_collection_buckets(coins, 'vendor', 10)
    era_rows = [
        {'label': label, 'count': count}
        for label, count in era_counts.items()
    ]
    top_references = [
        {'label': label, 'count': reference_counts[label]}
        for label in sorted(reference_counts, key=lambda k: (-reference_counts[k], k.lower()))
    ][:10]
    most_expensive = sorted(
        [item for item in coins if item['price_number'] is not None],
        key=lambda item: item['price_number'],
        reverse=True,
    )[:8]
    narrative = _coin_collection_narrative(
        scope_labels[scope], q, summary, by_region, by_authority,
        top_references, era_rows,
    )

    return render_template(
        'coin_collection_report.html',
        current_category='__admin__',
        categories=CATEGORIES,
        counts=get_counts(),
        scope=scope,
        scope_label=scope_labels[scope],
        q=q,
        coins=coins,
        summary=summary,
        narrative=narrative,
        by_region=by_region,
        by_authority=by_authority,
        by_metal=by_metal,
        by_denomination=by_denomination,
        by_property=by_property,
        by_vendor=by_vendor,
        era_rows=era_rows,
        top_references=top_references,
        most_expensive=most_expensive,
    )


@app.route('/admin/item-type-report', methods=['GET'])
def admin_item_type_report():
    """Admin HTML report across all categories, selectable by item type."""
    db = get_db()
    requested_type = (request.args.get('type') or 'all').strip()
    if requested_type != 'all' and requested_type not in CATEGORIES:
        requested_type = 'all'
    q = (request.args.get('q') or '').strip()

    selected_categories = (
        list(CATEGORIES.keys()) if requested_type == 'all' else [requested_type]
    )
    items = []
    total_spend = 0.0
    priced_count = 0
    with_images = 0

    for category in selected_categories:
        info = CATEGORIES[category]
        table = info['table']
        columns = _table_column_names(db, table)
        wheres, params = [], []
        _apply_row_filter_clauses(category, wheres, params)
        if 'status' in columns:
            wheres.append(_own_status_predicate())

        if q:
            search_columns = _item_report_search_columns(columns)
            if search_columns:
                like = f"%{q.lower()}%"
                wheres.append('(' + ' OR '.join(
                    f"LOWER(CAST({col} AS TEXT)) LIKE ?"
                    for col in search_columns
                ) + ')')
                params.extend([like] * len(search_columns))

        where_sql = f"WHERE {' AND '.join(wheres)}" if wheres else ''
        order_by = CATEGORY_ORDER_BY.get(category, 'created_at DESC')
        sql = f"SELECT * FROM {table} {where_sql} ORDER BY {order_by}"
        try:
            rows = db.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            rows = db.execute(
                f"SELECT * FROM {table} {where_sql} ORDER BY created_at DESC",
                params,
            ).fetchall()
        rows = [row for row in rows if _user_can_see_row(category, row)]

        compact_cols = REPORT_COMPACT_COLS.get(category, [])[:4]
        for row in rows:
            price_number = _money_number(row['price']) if 'price' in columns else None
            if price_number is not None:
                priced_count += 1
                total_spend += price_number
            value_number = _money_number(row['value']) if 'value' in columns else None
            image = ''
            image_field = info.get('image_field')
            if image_field in columns:
                image = (row[image_field] or '').strip()
                if image and is_image_filter(image):
                    with_images += 1
                else:
                    image = ''
            details = []
            for label, field in compact_cols:
                if field in columns and row[field] not in (None, ''):
                    details.append({'label': label, 'value': _format_report_value(field, row[field])})
            property_field = CATEGORY_PROPERTY_FIELD.get(category)
            status_display = (
                _item_report_row_value(row, columns, 'status')
                if 'status' in columns else 'Own'
            )
            item = {
                'category': category,
                'category_name': info['name'],
                'category_icon': info.get('icon', ''),
                'row': row,
                'title': _report_record_title(category, row),
                'owner': _item_report_row_value(row, columns, 'owner'),
                'property': row[property_field] if property_field in columns else '',
                'status': status_display,
                'date': _item_report_date(row, columns),
                'price_number': price_number,
                'price_display': _format_money(row['price']) if 'price' in columns else '',
                'value_display': _format_money(row['value']) if 'value' in columns else '',
                'value_number': value_number,
                'image': image,
                'details': details,
            }
            items.append(item)

    items.sort(key=lambda item: (
        item['category_name'].lower(),
        (item['title'] or '').lower(),
    ))
    by_type = _item_report_bucket(items, 'category_name')
    by_property = _item_report_bucket(items, 'property', 12)
    by_owner = _item_report_bucket(items, 'owner', 10)
    by_status = _item_report_bucket(items, 'status', 10)
    most_expensive = sorted(
        [item for item in items if item['price_number'] is not None],
        key=lambda item: item['price_number'],
        reverse=True,
    )[:10]
    type_options = [
        {'slug': slug, 'label': CATEGORIES[slug]['name'], 'icon': CATEGORIES[slug].get('icon', '')}
        for slug in CATEGORIES
    ]
    type_label = (
        'All Items' if requested_type == 'all'
        else CATEGORIES[requested_type]['name']
    )
    summary = {
        'total': len(items),
        'type_count': len([row for row in by_type if row['count']]),
        'priced_count': priced_count,
        'total_spend': total_spend,
        'avg_spend': total_spend / priced_count if priced_count else 0,
        'with_images': with_images,
    }
    narrative = _item_type_narrative(
        type_label, q, summary, by_type, by_property, by_owner, by_status,
    )

    return render_template(
        'item_type_report.html',
        current_category='__admin__',
        categories=CATEGORIES,
        counts=get_counts(),
        selected_type=requested_type,
        type_label=type_label,
        type_options=type_options,
        q=q,
        items=items,
        summary=summary,
        narrative=narrative,
        by_type=by_type,
        by_property=by_property,
        by_owner=by_owner,
        by_status=by_status,
        most_expensive=most_expensive,
    )


def _report_used_property_aliases(allowed):
    """Set of lowercased property-name aliases that have at least one
    record in any allowed category whose schema carries a property
    column. Honors row-level access so a restricted member only
    'sees' properties through items they themselves are allowed to
    see."""
    db = get_db()
    used = set()
    for cat, prop_col in CATEGORY_PROPERTY_FIELD.items():
        if cat not in allowed:
            continue
        table = CATEGORIES[cat]['table']
        wheres, params = [
            f"COALESCE({prop_col},'') != ''",
        ], []
        _apply_row_filter_clauses(cat, wheres, params)
        sql = (
            f"SELECT DISTINCT LOWER(TRIM({prop_col})) AS p "
            f"FROM {table} WHERE {' AND '.join(wheres)}"
        )
        try:
            for row in db.execute(sql, params).fetchall():
                if row['p']:
                    used.add(row['p'])
        except sqlite3.OperationalError:
            # Schema drift (column doesn't exist yet on a freshly
            # provisioned tenant) — skip the category, don't 500.
            continue
    return used


@app.route('/report/generate', methods=['GET'])
def report_generate():
    """Build a one-document inventory report PDF.

    Query string:
      mode=detailed | compact     (default: compact)
      categories=watches,coins…   ('*' or omitted = all allowed)
      properties=Carpinteria,…    ('*' or omitted = all)

    The detailed layout prints a thumbnail + caption per record.
    The compact layout prints a single spreadsheet row per record.
    Categories print in the order listed in CATEGORIES and respect
    g.allowed_cats / row-level access — the same scoping the rest of
    the app uses, so a tenant deployment automatically restricts to
    its own slice without any extra config."""
    if not g.get('current_user'):
        abort(403)

    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                     Paragraph, Spacer, Image, KeepTogether,
                                     PageBreak)
    import io as _io

    mode = (request.args.get('mode') or 'compact').strip().lower()
    if mode not in ('detailed', 'compact'):
        mode = 'compact'

    cats_raw = (request.args.get('categories') or '*').strip()
    props_raw = (request.args.get('properties') or '*').strip()

    allowed = g.get('allowed_cats') or set()
    if cats_raw == '*' or not cats_raw:
        selected_cats = [c for c in CATEGORIES if c in allowed]
    else:
        wanted = {c.strip() for c in cats_raw.split(',') if c.strip()}
        selected_cats = [c for c in CATEGORIES if c in wanted and c in allowed]

    if props_raw == '*' or not props_raw:
        properties = None
    else:
        properties = [p.strip() for p in props_raw.split(',') if p.strip()]

    db = get_db()
    buf = _io.BytesIO()
    pagesize = landscape(letter) if mode == 'compact' else letter
    doc = SimpleDocTemplate(buf, pagesize=pagesize,
                            leftMargin=0.4 * inch, rightMargin=0.4 * inch,
                            topMargin=0.4 * inch, bottomMargin=0.4 * inch)
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle('rh1', parent=styles['Heading1'],
                        fontSize=18, spaceAfter=4)
    h2 = ParagraphStyle('rh2', parent=styles['Heading2'],
                        fontSize=13, spaceBefore=10, spaceAfter=4)
    sub = ParagraphStyle('rsub', parent=styles['Normal'],
                         fontSize=9, textColor=colors.grey, spaceAfter=8)
    cell = ParagraphStyle('rcell', parent=styles['Normal'],
                          fontSize=8, leading=10)
    cell_bold = ParagraphStyle('rcellb', parent=cell, fontName='Helvetica-Bold')
    # NB: reportlab's HexColor() does NOT support CSS 3-digit shorthand
    # — it parses '#888' as the integer 0x888 (= dark blue), not as
    # '#888888'. Always use the full 6-digit form for greys here.
    cell_h = ParagraphStyle('rcellh', parent=cell,
                            fontName='Helvetica-Bold', fontSize=7,
                            textColor=colors.HexColor('#555555'))
    title_p = ParagraphStyle('rtitle', parent=styles['Normal'],
                             fontSize=10, fontName='Helvetica-Bold',
                             leading=12)
    cap = ParagraphStyle('rcap', parent=cell, fontSize=8, leading=10)
    cap_lbl = ParagraphStyle('rcaplbl', parent=cell,
                             fontSize=7, textColor=colors.HexColor('#777777'),
                             leading=9)

    story = []
    user = g.current_user
    user_name = (user.get('display_name') or user.get('email') or 'StuffApp')
    title = 'Inventory Report'
    if properties:
        title += f' — {", ".join(properties)}'
    story.append(Paragraph(title, h1))
    bits = [user_name, datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')]
    if cats_raw not in ('', '*'):
        bits.append('Categories: ' + ', '.join(
            CATEGORIES[c]['name'] for c in selected_cats))
    else:
        bits.append('All categories')
    story.append(Paragraph(' · '.join(bits), sub))

    grand_total = 0
    for cat in selected_cats:
        info = CATEGORIES[cat]
        table_name = info['table']
        cat_label = EXPORT_CATEGORY_LABELS.get(cat, info['name'])

        # Property predicate first so a property-restricted report
        # zeroes out rows for property-less categories.
        prop_clause, prop_params = _report_property_predicate(cat, properties)

        wheres, params = [], []
        if prop_clause:
            wheres.append(prop_clause)
            params.extend(prop_params)

        # Same row-level access enforcement the list view uses, so a
        # restricted member sees only their share in the report.
        _apply_row_filter_clauses(cat, wheres, params)

        # Owned-only: drop records that have left the collection.
        # Mirrors the watches list-view default so the report can't
        # surprise the user with sold/gifted/lost items mixed in.
        # Categories without a status field (credit_cards, persons)
        # are unaffected.
        cat_field_names = {f['name'] for f in FIELDS.get(cat, [])}
        if 'status' in cat_field_names:
            wheres.append(
                "(LOWER(TRIM(COALESCE(status,''))) "
                "NOT IN ('sold','gifted','lost'))"
            )

        order_by = CATEGORY_ORDER_BY.get(cat, 'created_at DESC')
        where_sql = f'WHERE {" AND ".join(wheres)}' if wheres else ''
        sql = f'SELECT * FROM {table_name} {where_sql} ORDER BY {order_by}'
        try:
            rows = db.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            # Bad ORDER BY column on a category that hasn't defined one
            # — fall back to created_at.
            sql = f'SELECT * FROM {table_name} {where_sql} ORDER BY created_at DESC'
            rows = db.execute(sql, params).fetchall()
        # Belt-and-suspenders: filter through _user_can_see_row in case
        # a category has filters not expressible as a SQL IN clause.
        rows = [r for r in rows if _user_can_see_row(cat, r)]

        if not rows:
            continue

        story.append(Paragraph(
            f'{info.get("icon","")}  {cat_label}  '
            f'<font size=9 color="#888888">({len(rows)})</font>',
            h2))
        grand_total += len(rows)

        if mode == 'compact':
            cols = REPORT_COMPACT_COLS.get(cat) or []
            # Header row: ID + chosen short cols.
            header = [Paragraph('<b>Item</b>', cell_h)]
            for label, _ in cols:
                header.append(Paragraph(f'<b>{label}</b>', cell_h))
            data = [header]
            for r in rows:
                line = [Paragraph(_report_record_title(cat, r) or '—',
                                  cell_bold)]
                for _, fname in cols:
                    try:
                        v = r[fname]
                    except (KeyError, IndexError):
                        v = None
                    s = _format_report_value(fname, v)
                    line.append(Paragraph(s, cell))
                data.append(line)

            # Wider Item column, even split across the rest.
            n_cols = 1 + len(cols)
            item_w = doc.width * 0.22
            rest = (doc.width - item_w) / max(1, n_cols - 1)
            col_widths = [item_w] + [rest] * (n_cols - 1)
            tbl = Table(data, colWidths=col_widths, repeatRows=1)
            tbl.setStyle(TableStyle([
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('LEFTPADDING', (0, 0), (-1, -1), 3),
                ('RIGHTPADDING', (0, 0), (-1, -1), 3),
                ('TOPPADDING', (0, 0), (-1, -1), 2),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
                ('LINEBELOW', (0, 0), (-1, 0), 0.5, colors.black),
                ('LINEBELOW', (0, 1), (-1, -1), 0.25, colors.HexColor('#dddddd')),
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eeeeff')),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 6))

        else:
            # Detailed: thumbnail + 3-col caption grid, two records per
            # row across the page. Each record renders as a 2x1 table
            # (image | caption) and pairs of records sit side by side.
            field_plan = REPORT_DETAILED_FIELDS.get(cat) or []
            cards = []
            for r in rows:
                img_path = _report_primary_image(cat, r)
                img_cell = ''
                if img_path:
                    try:
                        ir = ImageReader(img_path)
                        iw, ih = ir.getSize()
                        max_w, max_h = 1.1 * inch, 1.1 * inch
                        scale = min(max_w / iw, max_h / ih)
                        img_cell = Image(img_path, width=iw * scale,
                                          height=ih * scale)
                    except Exception:
                        img_cell = ''
                # Caption block: title at top, then 2-col label/value
                # pairs in a small grid.
                cap_rows = [[Paragraph(_report_record_title(cat, r) or '—',
                                        title_p), '']]
                pairs = []
                for label, fname in field_plan:
                    try:
                        v = r[fname]
                    except (KeyError, IndexError):
                        v = None
                    s = _format_report_value(fname, v)
                    if not s:
                        continue
                    pairs.append((label, s))
                # Pack pairs into 2-column rows.
                for i in range(0, len(pairs), 2):
                    left = pairs[i]
                    right = pairs[i + 1] if i + 1 < len(pairs) else None
                    lcell = Paragraph(
                        f'{left[1]}<br/><font size=6 color="#888888">{left[0]}</font>',
                        cap)
                    rcell = ''
                    if right:
                        rcell = Paragraph(
                            f'{right[1]}<br/><font size=6 color="#888888">{right[0]}</font>',
                            cap)
                    cap_rows.append([lcell, rcell])

                caption_tbl = Table(cap_rows, colWidths=['50%', '50%'])
                caption_tbl.setStyle(TableStyle([
                    ('SPAN', (0, 0), (1, 0)),  # title spans both columns
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 2),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                    ('TOPPADDING', (0, 0), (-1, -1), 1),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
                ]))
                card = Table([[img_cell, caption_tbl]],
                             colWidths=[1.2 * inch, doc.width / 2 - 1.2 * inch - 0.1 * inch])
                card.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 2),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 2),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ('BOX', (0, 0), (-1, -1), 0.25, colors.HexColor('#dddddd')),
                ]))
                cards.append(card)

            # Pair cards into rows of 2.
            for i in range(0, len(cards), 2):
                left = cards[i]
                right = cards[i + 1] if i + 1 < len(cards) else ''
                pair = Table([[left, right]],
                             colWidths=[doc.width / 2, doc.width / 2])
                pair.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                story.append(pair)
            story.append(Spacer(1, 4))

    if grand_total == 0:
        story.append(Paragraph('No matching records.', sub))
    else:
        story.append(Spacer(1, 8))
        story.append(Paragraph(
            f'<font size=9 color="#888888">Total: {grand_total} record'
            f'{"" if grand_total == 1 else "s"}</font>', sub))

    doc.build(story)
    buf.seek(0)
    fname = f'Inventory Report — {datetime.utcnow().strftime("%Y-%m-%d")}.pdf'
    return send_file(buf, as_attachment=False,
                     download_name=fname,
                     mimetype='application/pdf')


# ---------------------------------------------------------------------------
# Offline / read-only PWA support. The service worker (static/js/sw.js)
# does cache-first for /static, /uploads, /file-thumb and network-first
# for app pages, so a low-connectivity iPhone keeps working as long as
# the user pre-warmed the cache via the "Offline" nav button.
#
# /sw.js — proxy that serves static/js/sw.js at the site root so its
#          default scope covers every URL, not just /static/js/.
# /offline/manifest — JSON list of every URL the pre-warm walker hits.
# ---------------------------------------------------------------------------

@app.route('/sw.js')
def service_worker():
    """Serve the worker file at the root path so Service Worker scope
    defaults to the entire app — without needing the
    Service-Worker-Allowed header trick."""
    p = os.path.join(app.static_folder or 'static', 'js', 'sw.js')
    if not os.path.isfile(p):
        abort(404)
    resp = send_file(p, mimetype='application/javascript', max_age=0)
    # Don't let an intermediate cache pin a stale worker — the browser's
    # own update check handles freshness. Service-Worker-Allowed left
    # off because /sw.js's default scope is already '/'.
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp


@app.route('/offline/manifest', methods=['GET'])
def offline_manifest():
    """JSON: every URL the offline pre-warm walker should hit. Includes
    list pages, detail pages, and every uploaded file referenced by
    visible records. Scoped to g.allowed_cats + row filters so a
    member only pre-warms what they can already see."""
    if not g.get('current_user'):
        abort(403)
    db = get_db()
    allowed = g.get('allowed_cats') or set()

    pages = []
    images = []
    docs = []  # non-image files (PDFs etc.) — kept separate so the UI
               # can show them as "documents" in progress reporting.

    # Top-level entry URLs: '/' redirects to the landing category, and
    # the People nav button targets /persons-default rather than
    # /persons (it lands on the most relevant person directly). Both
    # are skipped by the SW cache because they 302, but adding them
    # here means the cache-fallback case can still serve them — and
    # surfaces any redirect-target URL on first warm.
    pages.append(url_for('index'))
    if 'persons' in allowed:
        pages.append(url_for('persons_default'))

    # Warm priority: when iOS storage is constrained, these categories
    # cache before everything else so the most-used surfaces survive
    # a partial warm. Order matches the pages → docs → images groups
    # the client concatenates in (so all priority pages cache before
    # any non-priority page, etc.).
    OFFLINE_PRIORITY = ['properties', 'watches', 'persons', 'coins']
    ordered_slugs = (
        [s for s in OFFLINE_PRIORITY if s in CATEGORIES] +
        [s for s in CATEGORIES if s not in OFFLINE_PRIORITY]
    )

    for slug in ordered_slugs:
        info = CATEGORIES[slug]
        if slug not in allowed:
            continue
        table = info['table']
        # Reuse the list-view's pagination by hitting the bare list URL —
        # cached HTML lets the offline user navigate categories.
        pages.append(url_for('list_view', category=slug))

        wheres, params = [], []
        _apply_row_filter_clauses(slug, wheres, params)
        where_sql = f'WHERE {" AND ".join(wheres)}' if wheres else ''
        try:
            rows = db.execute(
                f'SELECT * FROM {table} {where_sql}', params
            ).fetchall()
        except sqlite3.OperationalError:
            continue
        rows = [r for r in rows if _user_can_see_row(slug, r)]

        # Collect every file slot defined for this category, plus
        # whatever the JSON `documents` (or persons' id_documents /
        # health_documents) column carries. UUID-stamped filenames
        # mean a single SET dedupes naturally.
        file_fields = [f['name'] for f in FIELDS.get(slug, [])
                       if f.get('type') == 'file']
        doc_cols = list(DOC_SETS_BY_CATEGORY.get(slug, {}).values())

        for r in rows:
            try:
                rid = r['id']
            except (KeyError, IndexError):
                continue
            pages.append(url_for('detail_view', category=slug, record_id=rid))

            # Fixed-slot files.
            for f in file_fields:
                try:
                    v = (r[f] or '').strip()
                except (KeyError, IndexError):
                    v = ''
                if not v:
                    continue
                target = images if is_image_filter(v) else docs
                target.append(url_for('uploaded_file', filename=v))

            # JSON documents column(s).
            for col in doc_cols:
                try:
                    raw = r[col]
                except (KeyError, IndexError):
                    raw = None
                if not raw:
                    continue
                try:
                    arr = json.loads(raw) if isinstance(raw, str) else raw
                except (ValueError, TypeError):
                    arr = None
                if not isinstance(arr, list):
                    continue
                for item in arr:
                    if not isinstance(item, dict):
                        continue
                    fn = (item.get('filename') or '').strip()
                    if not fn:
                        continue
                    target = images if is_image_filter(fn) else docs
                    target.append(url_for('uploaded_file', filename=fn))

    # Dedupe while preserving order so progress feels predictable.
    def _dedup(seq):
        seen, out = set(), []
        for u in seq:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out

    return jsonify({
        'pages': _dedup(pages),
        'images': _dedup(images),
        'docs': _dedup(docs),
        'generated_at': datetime.utcnow().isoformat() + 'Z',
    })


# ---------------------------------------------------------------------------
# Per-row data snapshots (_data.json). Pair with admin_export_files's per-row
# JSON write so the StuffFiles mirror round-trips: sweep can read the
# snapshot back to recreate or fill rows when the SQLite DB is missing or
# blank for those columns.
# ---------------------------------------------------------------------------

# Categories that allocate W### / A### style cat_ids on creation. Sweep's
# auto-create path mirrors the /new route here so paths-only and snapshot-
# only auto-creates both end up with a usable cat_id (which the export's
# folder naming relies on, _watch_ident etc.).
_SERIAL_CAT_PREFIX = {'watches': 'W', 'art': 'A'}


def _is_data_snapshot_path(path):
    """True if `path` (or a bare basename) names a per-row JSON snapshot
    written by admin_export_files. Convention: '<ident> — _data.json'."""
    base = os.path.basename(path or '')
    name, ext = os.path.splitext(base)
    if ext.lower() != '.json':
        return False
    # Trailing ' — _data' on the canonical em-dash separator. Tolerate
    # the user hand-renaming with an en-dash or hyphen too.
    # Also recognize the collision-suffix variant '_data (2)' that
    # _next_unique produces when two records in the same group share
    # an ident — without this the second snapshot would be parsed as
    # an opaque doc upload titled "_data (2)" and never restore its
    # row's blank columns.
    return bool(re.search(r'\s+[—–-]\s+_data(\s+\(\d+\))?$', name))


def _process_sweep_deletes(record_state, allowed, db, now, dry_run, max_deletes=50):
    """For each record in this sweep batch that included a `_data.json`
    snapshot, compare what files the snapshot says the row owns against
    what files actually arrived in the upload. Anything in the snapshot
    but missing from the upload is a local deletion the user wants
    mirrored: clear the slot column (NULL) or splice the entry out of
    the docs JSON, bump updated_at, and record a tombstone so other
    clients pick up the deletion on their next syncDown.

    record_state: {row_id: {
        'cat':      category slug,
        'row':      row dict,
        'snapshot': parsed _data.json (or None if no snapshot uploaded),
        'uploads':  set of (label_norm, ext) for files actually uploaded,
    }}
    dry_run:   True returns a report without modifying the DB.
    max_deletes: refuse `apply` mode if total candidates exceed this.
                 The cap protects against a misconfigured upload (e.g.
                 user dragged a single file thinking they'd dragged the
                 whole folder, then ticked apply) wiping out dozens of
                 records' files in one go. Preview is unaffected.

    Returns {'deleted': [...], 'skipped': [...]} for the JSON report.
    """
    deleted = []
    skipped = []
    candidates = []  # (cat, row_id, row, kind, field, label, ext, fname)

    for row_id, state in record_state.items():
        snapshot = state.get('snapshot')
        if not snapshot:
            continue
        cat = state['cat']
        row = state['row']
        if cat not in allowed:
            skipped.append({
                'record': f'{cat}/{row_id[:8] if row_id else "?"}',
                'reason': f"no access to category '{cat}'",
            })
            continue
        plan = EXPORT_LAYOUT.get(cat) or {}
        identity = _identity_slots(cat)
        actual = state.get('uploads') or set()

        # Build the expected file set from the snapshot. Mirrors the
        # arcname-shaping logic in admin_export_files so what's compared
        # is what was actually written into the export the user is now
        # editing locally.
        expected = []  # (kind, field, label, ext, fname)
        for spec in plan.get('files', []):
            field, default_label, title_field = spec
            fname = (snapshot.get(field) or '').strip() if isinstance(snapshot.get(field), str) else ''
            if not fname:
                continue
            label = default_label
            if title_field and snapshot.get(title_field):
                t = (snapshot.get(title_field) or '').strip()
                if t:
                    label = t
            ext = os.path.splitext(fname)[1] or ''
            expected.append(('slot', field, label, ext, fname))
        for json_col in DOC_SETS_BY_CATEGORY.get(cat, {}).values():
            try:
                docs = json.loads(snapshot.get(json_col) or '[]')
            except (TypeError, ValueError):
                docs = []
            if not isinstance(docs, list):
                continue
            for d in docs:
                if not isinstance(d, dict):
                    continue
                fname = (d.get('filename') or '').strip()
                if not fname:
                    continue
                label = (d.get('title') or '').strip() or 'Doc'
                ext = os.path.splitext(fname)[1] or ''
                expected.append(('doc', json_col, label, ext, fname))

        for kind, field, label, ext, fname in expected:
            if (_norm(label), ext) in actual:
                continue
            if kind == 'slot' and field in identity:
                # Cover images, obverse/reverse pairs, license front/back
                # — never auto-delete via sync. Removing them in the app
                # is a deliberate UI action.
                skipped.append({
                    'record': f'{cat}/{row_id[:8]}',
                    'label':  label,
                    'reason': f"{field} is an identity slot — won't delete via sync",
                })
                continue
            candidates.append((cat, row_id, row, kind, field, label, ext, fname))

    # Per-batch cap: if apply mode would exceed it, downgrade everything
    # to a dry-run report and tell the caller.
    capped = (not dry_run) and len(candidates) > max_deletes
    effective_dry = dry_run or capped

    for cat, row_id, row, kind, field, label, ext, fname in candidates:
        entry = {
            'record':   f'{cat}/{row_id[:8]}',
            'label':    label,
            'kind':     kind,
            'field':    field,
            'filename': fname,
        }
        if effective_dry:
            entry['dry_run'] = True
            if capped:
                entry['note'] = (
                    f'apply refused — {len(candidates)} candidate deletions '
                    f'exceeds cap ({max_deletes}); review and re-submit')
            deleted.append(entry)
            continue
        table = CATEGORIES[cat]['table']
        try:
            if kind == 'slot':
                db.execute(
                    f"UPDATE {table} SET {field} = NULL, updated_at = ? "
                    f"WHERE id = ?",
                    [now, row_id],
                )
            else:  # 'doc'
                cur = db.execute(
                    f"SELECT {field} FROM {table} WHERE id = ?", [row_id]
                ).fetchone()
                try:
                    cur_docs = json.loads((cur[field] if cur else None) or '[]')
                except (TypeError, ValueError):
                    cur_docs = []
                if not isinstance(cur_docs, list):
                    cur_docs = []
                label_norm = _norm(label)
                # Splice the matching entry. Try (title + filename) first
                # for precision; if filename drifted (e.g. user re-uploaded
                # via UI), fall back to title alone.
                new_docs = []
                removed = False
                for d in cur_docs:
                    if not removed and isinstance(d, dict) \
                            and _norm((d.get('title') or '').strip()) == label_norm \
                            and (d.get('filename') or '').strip() == fname:
                        removed = True
                        continue
                    new_docs.append(d)
                if not removed:
                    title_matches = [
                        i for i, d in enumerate(cur_docs)
                        if isinstance(d, dict)
                        and _norm((d.get('title') or '').strip()) == label_norm
                    ]
                    if len(title_matches) == 1:
                        new_docs = [
                            d for i, d in enumerate(cur_docs)
                            if i != title_matches[0]
                        ]
                        removed = True
                    elif len(title_matches) > 1:
                        skipped.append({
                            **entry,
                            'reason': 'ambiguous docs title at apply-time; '
                                      'multiple entries match this label',
                        })
                        continue
                if not removed:
                    skipped.append({
                        **entry,
                        'reason': 'no matching docs entry at apply-time '
                                  '(probably already removed via UI)',
                    })
                    continue
                db.execute(
                    f"UPDATE {table} SET {field} = ?, updated_at = ? "
                    f"WHERE id = ?",
                    [json.dumps(new_docs), now, row_id],
                )
            _record_tombstone(db, cat, row, label, fname)
            deleted.append(entry)
        except Exception as exc:
            app.logger.exception('sweep delete failed for %s', entry)
            skipped.append({
                **entry,
                'reason': f'server error: {exc.__class__.__name__}: {exc}',
            })

    return {'deleted': deleted, 'skipped': skipped, 'capped': capped}


def _finalize_sweep_seed(seed, cat, user, db, now):
    """Apply the defaults a freshly-created sweep row needs: id (UUID
    fallback), created_at / updated_at, owner (per-category default),
    and cat_id (for the W### / A### serial categories).

    Doesn't overwrite values already in `seed` — so a snapshot-driven
    create that already carries a stable id, owner, and cat_id keeps
    them, while a path-driven create gets fresh ones."""
    seed.setdefault('id', str(uuid.uuid4()))
    seed.setdefault('created_at', now)
    # updated_at intentionally overwrites: this is a fresh INSERT, not
    # a re-creation of the historical row, so the snapshot's stale
    # updated_at would lie about when the row entered THIS database.
    seed['updated_at'] = now
    if 'owner' not in seed or not seed.get('owner'):
        if cat == 'coins':
            seed['owner'] = 'Mark'
        elif user.get('role') != 'owner':
            seed['owner'] = 'YM'
        else:
            d = DEFAULT_OWNER_BY_CATEGORY.get(cat)
            if d:
                seed['owner'] = d
    if not seed.get('cat_id'):
        prefix = _SERIAL_CAT_PREFIX.get(cat)
        if prefix:
            try:
                seed['cat_id'] = next_serial_cat_id(
                    db, CATEGORIES[cat]['table'], prefix
                )
            except Exception:
                pass
    return seed


@app.route('/sweep', methods=['GET', 'POST'])
def sweep_files():
    """Bulk-import files from a StuffFiles-shaped folder.

    GET → renders the upload form. Two pickers: a webkitdirectory
    folder picker (desktop) and a multi-file picker (iOS Files app).

    POST → processes each uploaded file:
      1. Parse its relative path against StuffFiles/<Cat>/<Group>/<f>.
         iOS multi-file uploads have no relative path; user can
         override via the `category_hint` form field which gets
         pre-pended to each file's name to form a synthetic path.
      2. Match (category, group, ident) → existing record (skip if
         multiple records match — never auto-pick).
      3. Match label → file slot. If the label matches one of the
         category's slot labels (default OR existing user-title),
         use that. Otherwise pick the first empty slot.
      4. Skip if the slot is already populated (never overwrite).
      5. Save file, set the slot column, default the title column to
         the file's basename if it doesn't have a user title yet.

    Per-user: respects g.allowed_cats (members can sweep into their
    own categories only).

    Returns a JSON report when `Accept: application/json`, else
    re-renders the page with the report inline.
    """
    user = g.get('current_user')
    if not user:
        abort(403)
    allowed = g.get('allowed_cats') or set()

    if request.method == 'GET':
        cat_options = [(slug, label) for slug, label in EXPORT_CATEGORY_LABELS.items()
                       if slug in allowed]
        return render_template('sweep.html',
                               cat_options=cat_options,
                               current_category='__sweep__',
                               categories=CATEGORIES,
                               counts=get_counts())

    files = request.files.getlist('files')
    if not files:
        return jsonify({'error': 'No files uploaded'}), 400

    # Process per-row data snapshots (`<ident> — _data.json`) before any
    # regular files. Snapshot processing creates or fills rows from the
    # JSON column dump, so any rows it materialises are in the index by
    # the time the regular files arrive looking for slots — otherwise a
    # regular file would race-create an empty stub row first and the
    # snapshot's column data would be ignored on the fill-blanks pass.
    def _is_snapshot(f):
        if not (f and f.filename):
            return False
        rel = (getattr(f, 'webkit_relative_path', None) or
               getattr(f, 'webkitRelativePath', None) or
               request.form.get(f'path_{f.filename}', '') or
               f.filename)
        return _is_data_snapshot_path(rel)
    files = sorted(files, key=lambda f: 0 if _is_snapshot(f) else 1)

    cat_hint = (request.form.get('category_hint') or '').strip()
    cat_hint_label = EXPORT_CATEGORY_LABELS.get(cat_hint) if cat_hint else None
    group_hint = (request.form.get('group_hint') or '').strip()
    auto_create = request.form.get('auto_create') == '1'
    # Watches require a separate opt-in. Watch model names drift between
    # folder and DB ("Chronomètre Souverain" vs "Chronomètre Souveraine
    # Ref CSXX" vs years prefixed/missing), so a single auto-create tick
    # could spawn dozens of stub records before the user notices. Default
    # OFF; the sweep UI exposes a second checkbox specifically for it.
    auto_create_watches = request.form.get('auto_create_watches') == '1'
    # Delete-sync mode: 'off' (default), 'preview' (report only), or
    # 'apply' (mirror local deletions to the DB). When on, we use each
    # record's _data.json snapshot as the baseline and treat any file
    # the snapshot expected but the upload didn't deliver as a local
    # delete to mirror server-side. See _process_sweep_deletes.
    sync_deletes_mode = (request.form.get('sync_deletes') or 'off').strip().lower()
    if sync_deletes_mode not in ('off', 'preview', 'apply'):
        sync_deletes_mode = 'off'

    db = get_db()
    # Cache record indexes per category so we don't re-scan the table
    # for every file.
    indexes = {}
    def _index_for(cat):
        if cat not in indexes:
            indexes[cat] = _build_record_index(db, cat)
        return indexes[cat]

    report = {'uploaded': [], 'skipped': []}
    now = datetime.utcnow().isoformat()
    # Per-row state for the optional delete-sync pass at the end. Each
    # entry tracks the snapshot (if a _data.json was uploaded for this
    # row) and the set of (label_norm, ext) pairs the upload actually
    # delivered. Populated only when a file successfully matches a row.
    record_state = {}  # row_id -> {'cat', 'row', 'snapshot', 'uploads'}
    def _track_upload(cat, row, label, ext):
        rid = row.get('id') if isinstance(row, dict) else row['id']
        st = record_state.setdefault(rid, {
            'cat': cat, 'row': row, 'snapshot': None, 'uploads': set()
        })
        st['uploads'].add((_norm(label), ext))
    def _track_snapshot(cat, row, data_obj):
        rid = row.get('id') if isinstance(row, dict) else row['id']
        st = record_state.setdefault(rid, {
            'cat': cat, 'row': row, 'snapshot': None, 'uploads': set()
        })
        st['snapshot'] = data_obj

    for f in files:
        if not f or not f.filename:
            continue
        # Per-file try/except so a single bad file becomes a skipped
        # entry instead of taking the whole 20-file batch down with a
        # 500. The "server error:" prefix is matched client-side to
        # decide which entries should retry on the next sweep.
        try:
            # Browser may send the relative path on a webkitdirectory upload
            # via Werkzeug's `webkitRelativePath` attribute (preserved as
            # part of the multipart filename in newer browsers).
            rel = (getattr(f, 'webkit_relative_path', None) or
                   getattr(f, 'webkitRelativePath', None) or
                   request.form.get(f'path_{f.filename}', '') or
                   f.filename)
            # iOS multi-file picker: no path. Synthesize one from category +
            # group hints + the bare filename so the parser still works.
            if '/' not in rel and cat_hint_label:
                rel = '/'.join(['StuffFiles', cat_hint_label,
                                group_hint or 'Unknown', f.filename])

            # Cat-id fast path: if the filename leads with a known
            # cat_id (C### / W### / A###), match the record directly
            # and skip the path-based parse. Lets the user drop a file
            # anywhere — no need to know the StuffFiles folder shape,
            # no category hint required.
            cat_id_match = _try_cat_id_sweep_match(db, os.path.basename(rel))
            if cat_id_match:
                cat, matched_row, cat_id_label = cat_id_match
                if cat not in allowed:
                    report['skipped'].append({'file': rel, 'reason': f"no access to category '{cat}'"})
                    continue
                plan = EXPORT_LAYOUT[cat]
                # Skip past path-parsing — synthesize the (group, ident,
                # row) tuple the rest of the loop expects so slot
                # resolution proceeds normally.
                target_group = _norm(plan['group'](matched_row))
                target_ident = _norm(plan['ident'](matched_row))
                target_label = _norm(cat_id_label)
                matches = [(target_group, target_ident, matched_row)]
                # Skip parsed = ... and exact/prefix matching below; jump
                # straight to the slot-resolution / save block.
                parsed = {
                    'category': cat,
                    'group':    plan['group'](matched_row),
                    'ident':    plan['ident'](matched_row),
                    'label':    cat_id_label,
                    'ext':      os.path.splitext(rel)[1],
                    'original_basename': os.path.basename(rel),
                }
            else:
                parsed = _parse_sweep_path(rel)
                if not parsed:
                    report['skipped'].append({'file': rel, 'reason': 'unparsable path (need StuffFiles/<Category>/<Group>/<file> shape, or pick a category, or prefix the filename with a cat_id like W042 or C001)'})
                    continue
                cat = parsed['category']
                if cat not in allowed:
                    report['skipped'].append({'file': rel, 'reason': f"no access to category '{cat}'"})
                    continue

                plan = EXPORT_LAYOUT[cat]
                idx = _index_for(cat)
                target_group = _norm(parsed['group'])
                target_ident = _norm(parsed['ident'])
                # Initialized here (not at the slot-resolve step below) so the
                # single-record-per-group fallback can read it without
                # tripping UnboundLocalError.
                target_label = _norm(parsed['label'])

            # ─── Per-row data snapshot branch ─────────────────────────
            # Files named "<ident> — _data.json" carry the row's column
            # data (written by admin_export_files). Process them here
            # instead of as file-slot uploads so the JSON content
            # restores spec data rather than getting saved as an opaque
            # blob in a slot. Files are sorted snapshot-first up top, so
            # by the time regular files arrive any rows the snapshot
            # created are already in the index.
            if _is_data_snapshot_path(rel):
                try:
                    raw = f.read()
                    if isinstance(raw, bytes):
                        raw = raw.decode('utf-8')
                    data_obj = json.loads(raw)
                    if not isinstance(data_obj, dict):
                        raise ValueError('snapshot is not a JSON object')
                except Exception as e:
                    report['skipped'].append({
                        'file': rel,
                        'reason': f'_data.json parse failed: {e}',
                    })
                    continue

                table = CATEGORIES[cat]['table']
                table_cols = {r['name'] for r in db.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()}
                file_slot_cols = {spec[0] for spec in plan.get('files', [])}
                doc_json_cols = set(DOC_SETS_BY_CATEGORY.get(cat, {}).values())
                # Columns we never restore from snapshot:
                # - id is generated fresh per record (collision avoidance);
                # - created_at/updated_at are managed locally;
                # - file slot columns reference the original UPLOAD_FOLDER
                #   filenames which may not exist after a rebuild — leave
                #   them blank so sweep's regular file-slot logic populates
                #   them with the actual on-disk filenames;
                # - doc JSON columns reference uploads similarly;
                # - owner is derived from the uploading user's role so a
                #   member can't claim a row for someone else by editing
                #   the JSON;
                # - cat_id is allocated by _finalize_sweep_seed so a
                #   snapshot can't claim an arbitrary serial (W001 etc.)
                #   on auto-create, and a fill-blanks pass can't paint
                #   a chosen cat_id onto an existing row with a blank
                #   one.
                skip_cols = (file_slot_cols | doc_json_cols
                             | {'id', 'created_at', 'updated_at',
                                'owner', 'cat_id'})

                # Try to find an existing row by (group, ident). On the
                # cat_id fast path we already matched the row directly —
                # use it instead of searching the per-category index
                # (which wasn't built on that path).
                if cat_id_match:
                    snap_matches = matches
                else:
                    snap_matches = [(g, i, r) for (g, i, r) in idx
                                    if g == target_group and i == target_ident]
                    if not snap_matches and target_ident:
                        snap_matches = [(g, i, r) for (g, i, r) in idx
                                        if g == target_group
                                        and i.startswith(target_ident)]

                if snap_matches:
                    if len(snap_matches) > 1:
                        report['skipped'].append({
                            'file': rel,
                            'reason': f"_data.json: ambiguous — {len(snap_matches)} matches in {cat}",
                        })
                        continue
                    row = snap_matches[0][2]
                    # Stash the parsed snapshot keyed by the matched row's
                    # id so the optional delete-sync pass at the end of
                    # the request can use it as the "expected files"
                    # baseline for this record.
                    _track_snapshot(cat, row, data_obj)
                    # Fill BLANK columns only — never overwrite live
                    # column data with stale snapshot values. The
                    # snapshot is for recovering missing data, not for
                    # one-way replacement.
                    cur_row = db.execute(
                        f"SELECT * FROM {table} WHERE id = ?", [row['id']]
                    ).fetchone()
                    updates = {}
                    for col, val in data_obj.items():
                        if col in skip_cols or col not in table_cols:
                            continue
                        cur = cur_row[col] if col in cur_row.keys() else None
                        cur_blank = cur is None or (
                            isinstance(cur, str) and not cur.strip())
                        if not cur_blank:
                            continue
                        updates[col] = val
                    if updates:
                        set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
                        db.execute(
                            f"UPDATE {table} SET {set_clause}, "
                            f"updated_at = ? WHERE id = ?",
                            list(updates.values()) + [now, row['id']],
                        )
                        # Refresh in-memory index so subsequent regular
                        # files in this batch see the filled values. On
                        # the cat_id fast path we never built indexes[cat];
                        # subsequent cat_id_match calls re-query the DB
                        # so they pick up the UPDATE without a cache hit.
                        # NB: tuple element renamed off `g` because Python
                        # treats `g` as local for the WHOLE function once
                        # any assignment exists, which would shadow
                        # `flask.g` at sweep_files entry and crash with
                        # UnboundLocalError before user auth even ran.
                        for (_g_cached, _i_cached, r_cached) in indexes.get(cat, []):
                            if r_cached.get('id') == row['id']:
                                for k, v in updates.items():
                                    r_cached[k] = v
                                break
                    report['uploaded'].append({
                        'file':   rel,
                        'record': f"{cat}/{row['id'][:8]} (snapshot filled {len(updates)} blank cols)",
                        'slot':   '(metadata)',
                    })
                    continue

                # No match — auto-create from snapshot. Same gates as
                # path-based auto-create: needs auto_create, plus the
                # watches-specific opt-in for cat=='watches'.
                if not auto_create or (cat == 'watches' and not auto_create_watches):
                    report['skipped'].append({
                        'file':   rel,
                        'reason': (
                            f"_data.json: no record matches in {cat} "
                            f"(group='{parsed['group']}', ident='{parsed['ident']}'); "
                            f"auto-create off"
                        ),
                    })
                    continue

                seed = {k: v for k, v in data_obj.items()
                        if k in table_cols and k not in skip_cols}
                seed = _finalize_sweep_seed(seed, cat, user, db, now)
                cols_sql = ', '.join(seed.keys())
                placeholders = ', '.join(['?'] * len(seed))
                try:
                    db.execute(
                        f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders})",
                        list(seed.values()),
                    )
                except sqlite3.IntegrityError as e:
                    report['skipped'].append({
                        'file': rel,
                        'reason': f'_data.json insert failed: {e}',
                    })
                    continue
                new_row = dict(db.execute(
                    f"SELECT * FROM {table} WHERE id = ?", [seed['id']]
                ).fetchone())
                g_norm = _norm(plan['group'](new_row))
                i_norm = _norm(plan['ident'](new_row))
                indexes[cat].append((g_norm, i_norm, new_row))
                report['uploaded'].append({
                    'file':   rel,
                    'record': f"{cat}/{seed['id'][:8]} (CREATED FROM _data.json)",
                    'slot':   '(metadata)',
                })
                continue
            # ─── End data snapshot branch ─────────────────────────────

            # Find rows whose (group, ident) match. ident match is exact
            # after normalization; if no exact match, fall back to a prefix
            # match so partial idents still land. Skipped on the cat_id
            # fast path — `matches` is already set there and `idx` was
            # never built.
            if not cat_id_match:
                exact = [(g, i, r) for (g, i, r) in idx if g == target_group and i == target_ident]
                if not exact:
                    prefix = [(g, i, r) for (g, i, r) in idx
                              if g == target_group and target_ident and i.startswith(target_ident)]
                    matches = prefix
                else:
                    matches = exact
            # "Single-record-per-group" fallback. For categories where the
            # group field IS the record's identity (Properties → name,
            # Persons → name, Recordings → an artist's record per item),
            # the path naturally looks like
            #   StuffFiles/<Cat>/<RecordName>/<DocTitle>.<ext>
            # with no " — " separator, so target_ident is actually the doc
            # title. If exactly one record shares the group, treat that as
            # the match and re-purpose `target_ident` as the slot label
            # search key.
            if not matches:
                same_group = [(g, i, r) for (g, i, r) in idx if g == target_group]
                if len(same_group) == 1:
                    matches = same_group
                    if not target_label and parsed['ident']:
                        target_label = _norm(parsed['ident'])
            if not matches:
                # Optional auto-create. Only happens when the user opts in
                # AND the category has a 'create' constructor in the layout.
                # Watches require a second, watches-specific opt-in
                # (auto_create_watches) — model names drift too easily and
                # one bad sweep can spawn dozens of stub records. If the
                # main auto-create is on but watches-specific isn't, log
                # what would have been created so the user can see the
                # impact before flipping the second flag.
                create_fn = plan.get('create')
                if auto_create and create_fn and cat == 'watches' and not auto_create_watches:
                    report['skipped'].append({
                        'file': rel,
                        'reason': (
                            f"watches auto-create requires the separate "
                            f"'auto_create_watches' opt-in (group="
                            f"'{parsed['group']}', ident='{parsed['ident']}')"
                        ),
                    })
                    continue
                if auto_create and create_fn:
                    seed = create_fn(parsed['group'], parsed['ident']) or {}
                    if seed:
                        # Centralised seed defaults (id, timestamps,
                        # owner, cat_id). Without this, sweep-created
                        # watches landed with cat_id=NULL even though
                        # /new-created watches always get a W### —
                        # which is what _watch_ident later relies on
                        # to build the export folder name.
                        seed = _finalize_sweep_seed(seed, cat, user, db, now)
                        table = CATEGORIES[cat]['table']
                        table_cols = {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
                        seed = {k: v for k, v in seed.items() if k in table_cols}
                        cols_sql = ', '.join(seed.keys())
                        placeholders = ', '.join(['?'] * len(seed))
                        db.execute(
                            f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders})",
                            list(seed.values()),
                        )
                        # Refresh the index so subsequent files in the same
                        # sweep can match this brand-new row. dict() so
                        # the loop can mutate slot fields after saves.
                        new_row = dict(db.execute(
                            f"SELECT * FROM {table} WHERE id = ?", [seed['id']]
                        ).fetchone())
                        g_norm = _norm(plan['group'](new_row))
                        i_norm = _norm(plan['ident'](new_row))
                        indexes[cat].append((g_norm, i_norm, new_row))
                        matches = [(g_norm, i_norm, new_row)]
                        report['uploaded'].append({
                            'file':   rel,
                            'record': f"{cat}/{seed['id'][:8]} (CREATED)",
                            'slot':   '(record)',
                        })
                    else:
                        report['skipped'].append({'file': rel, 'reason': f"auto-create returned no seed for {cat}"})
                        continue
                else:
                    report['skipped'].append({'file': rel, 'reason': f"no record matches group='{parsed['group']}' ident='{parsed['ident']}' in {cat}" + ('' if create_fn else ' (auto-create unavailable for this category)')})
                    continue
            if len(matches) > 1:
                report['skipped'].append({'file': rel, 'reason': f"ambiguous — {len(matches)} records match in {cat} (won't auto-pick)"})
                continue
            row = matches[0][2]
            # Record this upload against the matched row so the
            # optional delete-sync pass knows the file was delivered
            # (and therefore is NOT a deletion candidate). Tracked
            # before any "skipped: slot full / duplicate" continue
            # below — those still represent files the user has
            # locally and doesn't want deleted.
            _track_upload(cat, row, target_label, parsed['ext'])
            table = CATEGORIES[cat]['table']
            cols = {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}

            # Resolve the slot. Try label match first. Also track whether
            # we matched a label whose slot is already filled — that's a
            # duplicate, and we want to skip the file outright instead of
            # falling through to "first empty slot" or "JSON append".
            chosen_field = None
            matched_filled_slot = None
            for spec in plan['files']:
                field, default_label, title_field = spec
                if field not in cols:
                    continue
                label_candidates = [default_label]
                if title_field and title_field in cols:
                    t = (row[title_field] or '').strip()
                    if t:
                        label_candidates.append(t)
                matched_label = next(
                    (c for c in label_candidates if _norm(c) == target_label),
                    None)
                if matched_label is not None:
                    if not (row[field] or '').strip():
                        chosen_field = field
                        break
                    elif matched_filled_slot is None:
                        matched_filled_slot = (field, matched_label)

            # Label matched a named slot but the slot is occupied → the
            # incoming file is a duplicate of the existing one. Skip
            # before save_upload so we don't write an orphan or add a
            # parallel JSON entry on the docs path.
            if not chosen_field and matched_filled_slot is not None:
                field_name, matched_label = matched_filled_slot
                report['skipped'].append({
                    'file':   rel,
                    'reason': f"already in named slot {field_name} ('{matched_label}')",
                })
                continue

            # For DOCUMENTS_CATEGORIES, never fall through to "first
            # empty slot" — the documents JSON column is unbounded so
            # every file that didn't match a named slot becomes a new
            # entry in there. Categories with only fixed slots keep
            # the original behavior.
            if not chosen_field and cat not in DOCUMENTS_CATEGORIES:
                # Label match failed entirely — find the first empty
                # slot in declaration order.
                for spec in plan['files']:
                    field, _, _ = spec
                    if field not in cols:
                        continue
                    if not (row[field] or '').strip():
                        chosen_field = field
                        break

            if not chosen_field and cat not in DOCUMENTS_CATEGORIES:
                report['skipped'].append({
                    'file': rel,
                    'reason': f"all file slots full on this record ({_g(row, 'id')[:8]})",
                })
                continue

            # DOCUMENTS_CATEGORIES: check the destination JSON column for
            # an existing entry with the same normalized title BEFORE
            # writing the file to disk. Without this, a re-run of sweep
            # would append a fresh duplicate every time. Title fallback
            # mirrors the append branch below: parsed label first, then
            # the bare filename basename.
            if not chosen_field and cat in DOCUMENTS_CATEGORIES:
                docs_col_pre = _route_sweep_doc_set(cat, parsed.get('label') or '')
                try:
                    existing_docs = json.loads(row[docs_col_pre] or '[]') if docs_col_pre in row.keys() else []
                except (TypeError, ValueError):
                    existing_docs = []
                if not isinstance(existing_docs, list):
                    existing_docs = []
                candidate_title = ((parsed.get('label') or '').strip()
                                   or (parsed.get('original_basename') or '').strip())
                candidate_norm = _norm(candidate_title)
                duplicate_of = None
                if candidate_norm:
                    for d in existing_docs:
                        if _norm((d.get('title') or '').strip()) == candidate_norm:
                            duplicate_of = d.get('title') or candidate_title
                            break
                if duplicate_of is not None:
                    report['skipped'].append({
                        'file':   rel,
                        'reason': f"already in {docs_col_pre} as '{duplicate_of}'",
                    })
                    continue

            stored = save_upload(f)
            if not stored:
                report['skipped'].append({'file': rel, 'reason': 'save_upload failed (unsupported type?)'})
                continue
            if chosen_field:
                db.execute(
                    f"UPDATE {table} SET {chosen_field} = ?, updated_at = ? WHERE id = ?",
                    [stored, now, _g(row, 'id')],
                )
                # Keep the cached row in sync so the next file targeting
                # this record sees the slot as filled (and any auto-titled
                # column shows up in subsequent label-match candidates).
                row[chosen_field] = stored
                row['updated_at'] = now
                wrote = _autofill_title_from_filename(db, table, _g(row, 'id'), cat,
                                                      chosen_field, parsed['original_basename'])
                if wrote:
                    row[wrote[0]] = wrote[1]
                report['uploaded'].append({
                    'file':   rel,
                    'record': f"{cat}/{_g(row, 'id')[:8]}",
                    'slot':   chosen_field,
                })
            else:
                # DOCUMENTS_CATEGORIES path — append to the JSON column.
                # For multi-set categories (persons: ids + health), use
                # a title-based heuristic to route between sets so a
                # round-trip Files-export → Sweep keeps user-titled docs
                # roughly in their original tab. Misroutes can be fixed
                # by deleting + re-uploading on the right tab.
                docs_col = _route_sweep_doc_set(cat, parsed.get('label') or '')
                try:
                    docs = json.loads(row[docs_col] or '[]') if docs_col in row.keys() else []
                except (TypeError, ValueError):
                    docs = []
                if not isinstance(docs, list):
                    docs = []
                # Title fallback: when the parsed label is empty (filename
                # didn't decompose into "<title>.<ext>" cleanly), use the
                # original basename so the doc renders with a real name
                # instead of the UI's generic "Doc N" placeholder.
                doc_title = ((parsed.get('label') or '').strip()
                             or (parsed.get('original_basename') or '').strip())
                docs.append({
                    'title':    doc_title,
                    'filename': stored,
                })
                db.execute(
                    f"UPDATE {table} SET {docs_col} = ?, updated_at = ? WHERE id = ?",
                    [json.dumps(docs), now, _g(row, 'id')],
                )
                row[docs_col] = json.dumps(docs)
                row['updated_at'] = now
                report['uploaded'].append({
                    'file':   rel,
                    'record': f"{cat}/{_g(row, 'id')[:8]}",
                    'slot':   f'{docs_col}[{len(docs) - 1}]',
                })
        except Exception as exc:
            app.logger.exception('sweep: failed on %s', getattr(f, 'filename', '?'))
            report['skipped'].append({
                'file':   getattr(f, 'filename', '?'),
                'reason': f'server error: {exc.__class__.__name__}: {exc}',
            })

    # Optional delete-sync pass. Runs after all files are processed so
    # `record_state` has both the snapshot baseline and the full set of
    # uploaded files for each record. Only records whose upload included
    # a _data.json contribute — partial uploads can't trigger deletes.
    if sync_deletes_mode in ('preview', 'apply'):
        delete_report = _process_sweep_deletes(
            record_state, allowed, db, now,
            dry_run=(sync_deletes_mode == 'preview'),
        )
        report['deleted'] = delete_report['deleted']
        report['delete_skipped'] = delete_report['skipped']
        report['delete_capped'] = delete_report.get('capped', False)
        report['sync_deletes_mode'] = sync_deletes_mode

    db.commit()

    if request.headers.get('Accept', '').startswith('application/json') \
            or request.headers.get('X-Requested-With') == 'fetch':
        return jsonify(report)
    return render_template('sweep.html',
                           report=report,
                           cat_options=[(slug, label) for slug, label in EXPORT_CATEGORY_LABELS.items()
                                        if slug in allowed],
                           current_category='__sweep__',
                           categories=CATEGORIES,
                           counts=get_counts())


@app.route('/admin/dedupe-doc-lists', methods=['POST'])
def admin_dedupe_doc_lists():
    """Walk every record in every DOCUMENTS_CATEGORIES table, parse each
    docs JSON column, and dedupe entries by normalized title — keep the
    first occurrence, drop the rest. Doesn't touch upload files; run
    /admin/orphan-uploads dry=0 afterwards to reclaim the orphaned files
    on disk.

    Pass `dry=0` to actually write changes; default is a dry-run report.
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    dry = request.form.get('dry', '1') != '0'
    db = get_db()
    summary = []
    total_records_touched = 0
    total_dupes_removed = 0
    for cat in sorted(DOCUMENTS_CATEGORIES):
        table = CATEGORIES[cat]['table']
        cols = _docs_cols_for(cat)
        if not cols:
            continue
        select_cols = ', '.join(['id'] + cols)
        rows = db.execute(f"SELECT {select_cols} FROM {table}").fetchall()
        cat_records = 0
        cat_dupes = 0
        for row in rows:
            updates = {}
            for col in cols:
                try:
                    docs = json.loads(row[col] or '[]')
                except (TypeError, ValueError):
                    continue
                if not isinstance(docs, list) or not docs:
                    continue
                seen = set()
                kept = []
                for d in docs:
                    if not isinstance(d, dict):
                        continue
                    key = _norm((d.get('title') or '').strip())
                    if not key:
                        # Untitled entries are kept as-is (we can't
                        # safely group them).
                        kept.append(d)
                        continue
                    if key in seen:
                        cat_dupes += 1
                        continue
                    seen.add(key)
                    kept.append(d)
                if len(kept) != len(docs):
                    updates[col] = kept
            if updates:
                cat_records += 1
                if not dry:
                    set_sql = ', '.join(f"{c} = ?" for c in updates) + ", updated_at = ?"
                    params = [json.dumps(v) for v in updates.values()]
                    params.append(datetime.utcnow().isoformat())
                    params.append(row['id'])
                    db.execute(f"UPDATE {table} SET {set_sql} WHERE id = ?", params)
        if cat_records:
            summary.append({'category': cat, 'records_touched': cat_records, 'dupes_removed': cat_dupes})
            total_records_touched += cat_records
            total_dupes_removed += cat_dupes
    if not dry:
        db.commit()
    return jsonify(dry_run=dry,
                   total_records_touched=total_records_touched,
                   total_dupes_removed=total_dupes_removed,
                   per_category=summary)


@app.route('/admin/heal-doc-lists', methods=['POST'])
def admin_heal_doc_lists():
    """One-shot cleanup for the damage caused by today's sweep + orphan
    bugs. For every record in every DOCUMENTS_CATEGORIES table, walk
    each docs JSON column and classify each entry:

      - dead_pointer: filename references a file that's no longer in
        UPLOAD_FOLDER → removed.
      - named_slot_dup_orphan: title matches a filled named-slot label
        AND the entry's filename is also missing → removed (the named
        slot is canonical and the duplicate's file is gone anyway).
      - named_slot_dup_with_file: title matches a filled named-slot
        label but the file still exists on disk → KEPT and reported,
        because it might be a distinct user-uploaded photo and we
        don't want to silently lose it.
      - kept: everything else.

    Dry-run by default; pass dry=0 to actually write changes.
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    dry = request.form.get('dry', '1') != '0'
    db = get_db()

    summary = []
    total_dead_pointer = 0
    total_dup_orphan = 0
    total_dup_with_file = 0
    review = []  # records where a named-slot duplicate has its own real file

    for cat in sorted(DOCUMENTS_CATEGORIES):
        table = CATEGORIES[cat]['table']
        plan = EXPORT_LAYOUT.get(cat, {})
        named_slots = []  # list of (field, default_label, title_field)
        for spec in plan.get('files', []):
            named_slots.append(spec)
        cols = {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}
        json_cols = [c for c in DOC_SETS_BY_CATEGORY[cat].values() if c in cols]
        if not json_cols:
            continue
        # Pull the named-slot fields too so we can read each row's
        # current named-slot labels and occupancy.
        named_select = [f for (f, _, _) in named_slots if f in cols]
        named_title_cols = [t for (_, _, t) in named_slots if t and t in cols]
        all_select = list({'id', *json_cols, *named_select, *named_title_cols})
        sel = ', '.join(all_select)
        try:
            rows = db.execute(f"SELECT {sel} FROM {table}").fetchall()
        except sqlite3.OperationalError:
            continue
        cat_dead = 0
        cat_dup_orphan = 0
        cat_dup_with_file = 0
        for row in rows:
            # Build the set of filled named-slot labels for THIS row,
            # using both the default label and the user's title column
            # if present.
            filled_labels = set()
            for (field, default_label, title_field) in named_slots:
                if field not in cols:
                    continue
                slot_val = (row[field] or '').strip() if field in row.keys() else ''
                if not slot_val:
                    continue
                filled_labels.add(_norm(default_label))
                if title_field and title_field in cols and title_field in row.keys():
                    t = (row[title_field] or '').strip()
                    if t:
                        filled_labels.add(_norm(t))

            updates = {}
            for col in json_cols:
                raw = row[col] if col in row.keys() else None
                if not raw:
                    continue
                try:
                    docs = json.loads(raw)
                except (TypeError, ValueError):
                    continue
                if not isinstance(docs, list) or not docs:
                    continue
                kept = []
                for d in docs:
                    if not isinstance(d, dict):
                        kept.append(d)
                        continue
                    fn = (d.get('filename') or '').strip()
                    title = (d.get('title') or '').strip()
                    file_exists = bool(fn) and os.path.exists(
                        os.path.join(UPLOAD_FOLDER, fn))
                    is_named_slot_dup = (
                        bool(title) and _norm(title) in filled_labels)
                    if not file_exists:
                        if is_named_slot_dup:
                            cat_dup_orphan += 1
                            total_dup_orphan += 1
                        else:
                            cat_dead += 1
                            total_dead_pointer += 1
                        continue  # drop
                    if is_named_slot_dup:
                        cat_dup_with_file += 1
                        total_dup_with_file += 1
                        review.append({
                            'category': cat,
                            'record_id': row['id'],
                            'col': col,
                            'title': title,
                            'filename': fn,
                        })
                        # Keep the entry — needs human review.
                    kept.append(d)
                if len(kept) != len(docs):
                    updates[col] = kept
            if updates and not dry:
                set_sql = ', '.join(f"{c} = ?" for c in updates) + ", updated_at = ?"
                params = [json.dumps(v) for v in updates.values()]
                params.append(datetime.utcnow().isoformat())
                params.append(row['id'])
                db.execute(f"UPDATE {table} SET {set_sql} WHERE id = ?", params)
        if cat_dead or cat_dup_orphan or cat_dup_with_file:
            summary.append({
                'category': cat,
                'dead_pointer_removed': cat_dead,
                'named_slot_dup_orphan_removed': cat_dup_orphan,
                'named_slot_dup_with_file_kept': cat_dup_with_file,
            })
    if not dry:
        db.commit()
    return jsonify(dry_run=dry,
                   total_dead_pointer_removed=total_dead_pointer,
                   total_named_slot_dup_orphan_removed=total_dup_orphan,
                   total_named_slot_dup_with_file_kept=total_dup_with_file,
                   per_category=summary,
                   review_sample=review[:30],
                   review_count=len(review))


@app.route('/admin/orphan-uploads', methods=['POST'])
def admin_orphan_uploads():
    """Find (and optionally delete) files in UPLOAD_FOLDER that aren't
    referenced by any DB row. Pass `dry=0` to actually delete; any
    other value (including absent) is a dry-run that only reports.

    Skips the .thumbs cache directory (regenerable) and any
    .DS_Store crud."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    dry = request.form.get('dry', '1') != '0'
    db = get_db()
    referenced = _collect_referenced_uploads(db)

    if not os.path.isdir(UPLOAD_FOLDER):
        return jsonify(total=0, referenced=len(referenced),
                       orphan_count=0, orphan_size_bytes=0,
                       deleted=0, dry_run=dry, sample=[])

    orphans = []           # list of (filename, size_bytes)
    total_files = 0
    for name in os.listdir(UPLOAD_FOLDER):
        full = os.path.join(UPLOAD_FOLDER, name)
        if not os.path.isfile(full):
            continue
        if name == '.DS_Store':
            continue
        total_files += 1
        if name not in referenced:
            try:
                sz = os.path.getsize(full)
            except OSError:
                sz = 0
            orphans.append((name, sz))

    deleted = 0
    if not dry:
        for name, _ in orphans:
            try:
                os.unlink(os.path.join(UPLOAD_FOLDER, name))
                deleted += 1
                # Also nuke the cached PDF/HEIC thumbnail if present.
                thumb = os.path.join(_FILE_THUMB_DIR, name + '.jpg')
                if os.path.exists(thumb):
                    try: os.unlink(thumb)
                    except OSError: pass
            except OSError:
                pass

    return jsonify(
        total=total_files,
        referenced=len(referenced),
        orphan_count=len(orphans),
        orphan_size_bytes=sum(sz for _, sz in orphans),
        deleted=deleted,
        dry_run=dry,
        sample=[n for n, _ in orphans[:10]],
    )


@app.route('/admin/coins-owner-mark', methods=['POST'])
def coins_owner_mark():
    """Set owner='Mark' on every coin whose owner isn't already 'Mark'."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    now = datetime.utcnow().isoformat()
    r = db.execute(
        "UPDATE coins SET owner='Mark', updated_at=? "
        "WHERE owner IS NULL OR TRIM(owner) = '' OR owner != 'Mark'",
        [now],
    )
    db.commit()
    return jsonify(updated=r.rowcount,
                   total=db.execute('SELECT COUNT(*) FROM coins').fetchone()[0])


@app.route('/admin/audio-owner-ym', methods=['POST'])
def audio_owner_ym():
    """Set owner='YM' on every audio row whose owner isn't already 'YM'."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    now = datetime.utcnow().isoformat()
    r = db.execute(
        "UPDATE audio SET owner='YM', updated_at=? "
        "WHERE owner IS NULL OR TRIM(owner) = '' OR owner != 'YM'",
        [now],
    )
    db.commit()
    return jsonify(updated=r.rowcount,
                   total=db.execute('SELECT COUNT(*) FROM audio').fetchone()[0])


@app.route('/admin/cameras-owner-mark', methods=['POST'])
def cameras_owner_mark():
    """Set owner='Mark' on every camera whose owner isn't already 'Mark'."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    now = datetime.utcnow().isoformat()
    r = db.execute(
        "UPDATE cameras SET owner='Mark', updated_at=? "
        "WHERE owner IS NULL OR TRIM(owner) = '' OR owner != 'Mark'",
        [now],
    )
    db.commit()
    return jsonify(updated=r.rowcount,
                   total=db.execute('SELECT COUNT(*) FROM cameras').fetchone()[0])


@app.route('/admin/persons-restore-docs', methods=['POST'])
def persons_restore_docs():
    """Repopulate id_documents / health_documents JSON columns from the
    per-slot id_doc_3..8 / health_doc_3..8 file columns when the JSON
    column is currently empty. Recovers data nuked by an earlier overly
    aggressive phantom-doc strip — the slot columns themselves were
    never modified, so we still have the source of truth.

    Idempotent: rows whose JSON already has tiles are skipped (no
    deduping, no merging). Returns a per-set count of rows restored."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    cols = {r['name'] for r in db.execute("PRAGMA table_info(persons)").fetchall()}
    plans = [
        ('id_documents', [
            (f'id_doc_{i}', f'id_doc_{i}_title', f'ID Doc {i}')
            for i in range(3, 9)
        ]),
        ('health_documents', [
            (f'health_doc_{i}', f'health_doc_{i}_title', f'Health Doc {i}')
            for i in range(3, 9)
        ]),
    ]
    out = {}
    rows = db.execute("SELECT * FROM persons").fetchall()
    for json_col, sources in plans:
        if json_col not in cols:
            out[json_col] = 0
            continue
        restored = 0
        for row in rows:
            try:
                existing = json.loads(row[json_col] or '[]')
            except (TypeError, ValueError):
                existing = []
            if isinstance(existing, list) and existing:
                continue  # JSON already has tiles — leave alone
            docs = []
            for fn_col, title_col, default_title in sources:
                if fn_col not in cols:
                    continue
                fn = row[fn_col] if fn_col in row.keys() else None
                if not fn:
                    continue
                title = ''
                if title_col in cols and title_col in row.keys():
                    title = (row[title_col] or '').strip()
                if not title:
                    title = default_title
                docs.append({'title': title, 'filename': fn})
            if not docs:
                continue
            db.execute(
                f"UPDATE persons SET {json_col} = ?, updated_at = ? "
                f"WHERE id = ?",
                [json.dumps(docs), datetime.utcnow().isoformat(), row['id']],
            )
            restored += 1
        out[json_col] = restored
    db.commit()
    return jsonify(restored=out,
                   total=db.execute('SELECT COUNT(*) FROM persons').fetchone()[0])


@app.route('/admin/properties-restore-docs', methods=['POST'])
def properties_restore_docs():
    """Repopulate properties.documents JSON from the legacy doc_1..10
    file columns when the JSON is currently empty. Mirrors the persons
    restore endpoint — recovers data nuked by the phantom-strip's
    title-prefix path on rows whose doc titles started with the
    property name (e.g. "Carpinteria — Deed").

    Idempotent: rows whose JSON already has tiles are skipped."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    cols = {r['name'] for r in db.execute(
        "PRAGMA table_info(properties)"
    ).fetchall()}
    sources = [
        (f'doc_{i}', f'doc_{i}_title', f'Doc {i}')
        for i in range(1, 11)
    ]
    if 'documents' not in cols:
        return jsonify(restored=0, total=0)
    rows = db.execute("SELECT * FROM properties").fetchall()
    restored = 0
    for row in rows:
        try:
            existing = json.loads(row['documents'] or '[]')
        except (TypeError, ValueError):
            existing = []
        if isinstance(existing, list) and existing:
            continue
        docs = []
        for fn_col, title_col, default_title in sources:
            if fn_col not in cols:
                continue
            fn = row[fn_col] if fn_col in row.keys() else None
            if not fn:
                continue
            title = ''
            if title_col in cols and title_col in row.keys():
                title = (row[title_col] or '').strip()
            if not title:
                title = default_title
            docs.append({'title': title, 'filename': fn})
        if not docs:
            continue
        db.execute(
            "UPDATE properties SET documents = ?, updated_at = ? "
            "WHERE id = ?",
            [json.dumps(docs), datetime.utcnow().isoformat(), row['id']],
        )
        restored += 1
    db.commit()
    return jsonify(restored=restored,
                   total=db.execute(
                       'SELECT COUNT(*) FROM properties'
                   ).fetchone()[0])


@app.route('/admin/recordings-canonicalize-artists', methods=['POST'])
def recordings_canonicalize_artists():
    """Collapse case / whitespace variants of the same artist into a
    single canonical spelling. For each group of recordings whose
    artist matches case-insensitively (after trim + collapse-spaces),
    pick the most-used spelling as the canonical and rewrite the
    others. Avoids orphan-folder churn after Files runs ("Bob Marley
    and The Wailers" vs "Bob Marley and the Wailers" each get their
    own folder otherwise).

    Defaults to dry-run; pass dry=0 (form OR query) to apply. Returns
    a per-group report of the chosen canonical and what got rewritten."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    # Admin-page buttons send `dry` as form data; curl callers tend to
    # use ?dry=0 in the query string. Accept either so both paths work.
    dry_raw = (request.form.get('dry')
               or request.args.get('dry')
               or '1')
    dry = dry_raw != '0'
    db = get_db()
    rows = db.execute(
        "SELECT id, artist FROM recordings "
        "WHERE artist IS NOT NULL AND TRIM(artist) != ''"
    ).fetchall()

    # Bucket by normalized key (lowercase, single-spaced, trimmed).
    buckets = {}  # key → {variant_text: [row_ids]}
    for r in rows:
        a = (r['artist'] or '').strip()
        if not a:
            continue
        key = re.sub(r'\s+', ' ', a).lower()
        buckets.setdefault(key, {}).setdefault(a, []).append(r['id'])

    actions = []
    rewritten = 0
    now = datetime.utcnow().isoformat()
    for key, variants in buckets.items():
        if len(variants) < 2:
            continue
        # Canonical = highest-count variant; tiebreaker = lexicographic
        # sort so the run is deterministic across calls.
        ranked = sorted(
            variants.items(),
            key=lambda kv: (-len(kv[1]), kv[0]),
        )
        canonical, _ = ranked[0]
        merged_ids = []
        for variant, ids in ranked[1:]:
            merged_ids.extend(ids)
        if not merged_ids:
            continue
        actions.append({
            'canonical': canonical,
            'merged_from': [v for v, _ in ranked[1:]],
            'rows_rewritten': len(merged_ids),
        })
        if not dry:
            db.executemany(
                "UPDATE recordings SET artist = ?, updated_at = ? "
                "WHERE id = ?",
                [(canonical, now, rid) for rid in merged_ids],
            )
            rewritten += len(merged_ids)
    if not dry:
        db.commit()
    return jsonify(
        dry_run=dry,
        groups_collapsed=len(actions),
        rows_rewritten=rewritten,
        actions=actions,
    )


@app.route('/admin/lenses-owner-mark', methods=['POST'])
def lenses_owner_mark():
    """Set owner='Mark' on every lens whose owner isn't already 'Mark'."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    now = datetime.utcnow().isoformat()
    r = db.execute(
        "UPDATE lenses SET owner='Mark', updated_at=? "
        "WHERE owner IS NULL OR TRIM(owner) = '' OR owner != 'Mark'",
        [now],
    )
    db.commit()
    return jsonify(updated=r.rowcount,
                   total=db.execute('SELECT COUNT(*) FROM lenses').fetchone()[0])


@app.route('/admin/vehicles-default-sold', methods=['POST'])
def vehicles_default_sold():
    """Set any vehicle with null/empty status to 'Sold'. Safe to re-run."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    r = db.execute("UPDATE vehicles SET status='Sold' WHERE status IS NULL OR status=''")
    db.commit()
    total = db.execute('SELECT COUNT(*) FROM vehicles').fetchone()[0]
    return jsonify(updated=r.rowcount, total=total)


@app.route('/admin/prune-empty-coin-id-dupes', methods=['POST'])
def prune_empty_coin_id_dupes():
    """Delete coins rows whose coin_id is empty and whose id isn't a CSV UUID.

    These are leftovers from an earlier import where bullion rows without a
    coin_id got auto-generated UUIDs; newer imports use the CSV's own UUID,
    creating duplicates.
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    csv_uuids = set()
    for row in _csv_rows('Coin.csv'):
        if len(row) >= 30 and row[29]:
            csv_uuids.add(row[29].strip().lower())
    db = get_db()
    stray = db.execute(
        "SELECT id, authority, denomination FROM coins WHERE coin_id IS NULL OR coin_id = ''"
    ).fetchall()
    deleted = 0
    kept = 0
    for r in stray:
        if (r['id'] or '').lower() in csv_uuids:
            kept += 1
        else:
            db.execute("DELETE FROM coins WHERE id = ?", (r['id'],))
            deleted += 1
    db.commit()
    total = db.execute('SELECT COUNT(*) FROM coins').fetchone()[0]
    return jsonify(deleted=deleted, kept=kept, total=total)


@app.route('/admin/coin-image-audit', methods=['POST'])
def coin_image_audit():
    """Run a Claude-vision pass over coins and flag rows where the
    obverse/reverse images don't match the catalog description.

    Form params:
      secret    — IMPORT_MISSING_SECRET (required)
      limit     — max coins to process this call (default 25)
      offset    — skip N before starting (default 0)
      recheck   — '1' to re-run on rows that already have a stored verdict
                  (default skips them; set to recheck after image edits)
      mismatch_only — '1' to return only the mismatches in the JSON

    Persists per-coin verdicts so successive calls walk the table
    incrementally. Use small limits (~25) to stay under Railway's
    request timeout.
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    try:
        limit = int(request.form.get('limit') or 25)
    except ValueError:
        limit = 25
    try:
        offset = int(request.form.get('offset') or 0)
    except ValueError:
        offset = 0
    recheck = request.form.get('recheck') == '1'
    mismatch_only = request.form.get('mismatch_only') == '1'

    where = ("description IS NOT NULL AND TRIM(description) <> '' "
             "AND (image_1 IS NOT NULL OR image_2 IS NOT NULL)")
    if not recheck:
        where += " AND (image_audit_at IS NULL OR TRIM(image_audit_at) = '')"
    rows = db.execute(
        f"SELECT * FROM coins WHERE {where} ORDER BY rowid "
        "LIMIT ? OFFSET ?",
        [max(1, min(limit, 200)), max(0, offset)],
    ).fetchall()

    now = datetime.utcnow().isoformat()
    results = []
    for coin in rows:
        try:
            r = audit_coin_image_vs_description(coin)
        except Exception as e:
            import traceback
            print(traceback.format_exc(), flush=True)
            r = {'match': None, 'confidence': None,
                 'reason': f'exception: {str(e)[:120]}'}
        match_str = ('true' if r['match'] is True
                     else 'false' if r['match'] is False else None)
        db.execute(
            "UPDATE coins SET image_audit_match = ?, "
            "image_audit_confidence = ?, image_audit_reason = ?, "
            "image_audit_at = ? WHERE id = ?",
            [match_str, r.get('confidence'), r.get('reason'), now, coin['id']],
        )
        results.append({
            'id': coin['id'],
            'cat_id': coin['cat_id'],
            'coin_id': coin['coin_id'],
            'region': coin['region'],
            'authority': coin['authority'],
            'match': r['match'],
            'confidence': r.get('confidence'),
            'reason': r.get('reason'),
        })
    db.commit()

    mismatches = [r for r in results if r['match'] is False]
    payload = {
        'checked': len(results),
        'mismatches': mismatches,
        'mismatch_count': len(mismatches),
        'next_offset': offset + len(rows),
    }
    if not mismatch_only:
        payload['all'] = results
    return jsonify(payload)


@app.route('/admin/lens-mount-audit', methods=['GET'])
def lens_mount_audit():
    """Distinct mount values in lenses and lens_mount values in cameras.
    Helps identify drift between camera mount and lens mount strings."""
    if request.args.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    lenses = [dict(r) for r in db.execute(
        "SELECT COALESCE(mount,'(null)') AS mount, COUNT(*) AS n "
        "FROM lenses GROUP BY mount ORDER BY mount").fetchall()]
    cameras = [dict(r) for r in db.execute(
        "SELECT COALESCE(lens_mount,'(null)') AS lens_mount, COUNT(*) AS n "
        "FROM cameras GROUP BY lens_mount ORDER BY lens_mount").fetchall()]
    return jsonify(lenses=lenses, cameras=cameras)


@app.route('/admin/property-type-audit', methods=['GET'])
def property_type_audit():
    """Return the distinct status/type values in the properties table.

    Diagnostic endpoint — gated by the shared import secret. Helps
    identify data-casing or naming drift that makes filter pills miss rows.
    """
    if request.args.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    rows = db.execute(
        "SELECT COALESCE(type,'(null)') AS type, "
        "COALESCE(status,'(null)') AS status, COUNT(*) AS n "
        "FROM properties GROUP BY type, status ORDER BY type, status"
    ).fetchall()
    return jsonify(rows=[dict(r) for r in rows])


@app.route('/admin/backfill-property-status-own', methods=['POST'])
def backfill_property_status_own():
    """Set status='Own' for any property with a NULL/blank status.

    Matches the local DB after the 2026 data cleanup that restricted
    the Property Status dropdown to {Own, Sold}. Preserves existing
    'Sold' rows. Safe to re-run.
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    r = db.execute(
        "UPDATE properties SET status = 'Own' "
        "WHERE status IS NULL OR TRIM(status) = ''"
    )
    db.commit()
    return jsonify(updated=r.rowcount)


_RENUMBER_GROUPS = {
    # filter_name: (display prefix, human label)
    'ca_ancient': ('C',  'CA Ancient'),
    'ny_ancient': ('N',  'NY Ancient'),
    'ca_modern':  ('CM', 'CA Modern'),
    'ny_modern':  ('NM', 'NY Modern'),
}


def _renumber_coin_groups(db, groups=None):
    """Resequence coin_id (Display Position) for the given groups.
    Defaults to every Ancient/Modern group. Caller is responsible for
    commit — we stay inside the surrounding transaction."""
    if groups is None:
        groups = list(_RENUMBER_GROUPS.keys())
    order_by = CATEGORY_ORDER_BY['coins']
    for g in groups:
        if g not in _RENUMBER_GROUPS:
            continue
        prefix, _ = _RENUMBER_GROUPS[g]
        where, extra = CATEGORY_FILTERS['coins'][g]
        rows = db.execute(
            f"SELECT id FROM coins WHERE {where} ORDER BY {order_by}",
            list(extra),
        ).fetchall()
        for i, row in enumerate(rows, start=1):
            db.execute("UPDATE coins SET coin_id = ? WHERE id = ?",
                       (f'{prefix}{i}', row['id']))


def _coin_group_for(property_name, date_1):
    """Return the era/property group name ('ca_ancient', 'ny_modern',
    etc.) a coin belongs to, or None if either axis is unmappable.
    Boundary: date_1 < 500 → Ancient, otherwise Modern."""
    p = (property_name or '').strip().lower()
    if p in ('carp', 'carpinteria'):
        loc = 'ca'
    elif p in ('nyc', 'new york', 'ny'):
        loc = 'ny'
    else:
        return None
    if date_1 in (None, ''):
        return None
    try:
        d = int(date_1)
    except (TypeError, ValueError):
        return None
    return f"{loc}_{'ancient' if d < 500 else 'modern'}"


@app.route('/coins/renumber/<group>', methods=['POST'])
def coins_renumber_group(group):
    """Resequence coin_id for every coin in the given filter group.

    Ordering matches the coin list: region, authority, date_1. The first
    coin becomes <prefix>1, the second <prefix>2, and so on — so the
    Display Position on the printed cards matches the order shown in
    the list. Prefix per group: C for CA Ancient, N for NY Ancient.
    """
    if group not in _RENUMBER_GROUPS:
        abort(404)
    prefix, label = _RENUMBER_GROUPS[group]
    db = get_db()
    where, extra = CATEGORY_FILTERS['coins'][group]
    order_by = CATEGORY_ORDER_BY['coins']
    rows = db.execute(
        f"SELECT id FROM coins WHERE {where} ORDER BY {order_by}",
        list(extra),
    ).fetchall()
    for i, row in enumerate(rows, start=1):
        db.execute("UPDATE coins SET coin_id = ? WHERE id = ?",
                   (f'{prefix}{i}', row['id']))
    db.commit()
    flash(
        f'Renumbered {len(rows)} {label} coins '
        f'({prefix}1–{prefix}{len(rows)}).',
        'success',
    )
    return redirect(url_for('list_view', category='coins', filter=group))


@app.route('/admin/backfill-coin-cat-ids', methods=['POST'])
def backfill_coin_cat_ids():
    """Assign cat_id to every coin that still lacks one.

    Coins are grouped by (location letter, era letter) and numbered
    sequentially in purchase order (rowid). Existing cat_id values are
    preserved. Coins without a mappable property (Carp/NYC) or a date_1
    are skipped. Safe to re-run.
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    # Per-prefix counter starts at the current max.
    counters = {}
    for r in db.execute(
            "SELECT cat_id FROM coins "
            "WHERE cat_id IS NOT NULL AND LENGTH(cat_id) >= 3"):
        c = r['cat_id']
        try:
            counters[c[:2]] = max(counters.get(c[:2], 0), int(c[2:]))
        except ValueError:
            pass
    assigned = 0
    per_prefix = {}
    rows = db.execute(
        "SELECT id, property_name, date_1 FROM coins "
        "WHERE cat_id IS NULL OR TRIM(cat_id) = '' "
        "ORDER BY rowid").fetchall()
    for row in rows:
        prefix = _cat_id_prefix(row['property_name'], row['date_1'])
        if not prefix:
            continue
        counters[prefix] = counters.get(prefix, 0) + 1
        cat_id = f'{prefix}{counters[prefix]:03d}'
        db.execute("UPDATE coins SET cat_id = ? WHERE id = ?",
                   (cat_id, row['id']))
        assigned += 1
        per_prefix[prefix] = per_prefix.get(prefix, 0) + 1
    db.commit()
    return jsonify(assigned=assigned, per_prefix=per_prefix,
                   skipped=len(rows) - assigned)


@app.route('/admin/backfill-status-own-all', methods=['POST'])
def backfill_status_own_all():
    """Set status='Own' in every table that has a status column,
    for any row where status is NULL or blank. Safe to re-run."""
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    per_table = {}
    total = 0
    tables = [r['name'] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")]
    for t in tables:
        cols = [r['name'] for r in db.execute(f"PRAGMA table_info({t})")]
        if 'status' not in cols:
            continue
        r = db.execute(
            f"UPDATE {t} SET status = 'Own' "
            "WHERE status IS NULL OR TRIM(status) = ''"
        )
        if r.rowcount:
            per_table[t] = r.rowcount
            total += r.rowcount
    db.commit()
    return jsonify(updated=total, per_table=per_table)


@app.route('/admin/set-all-recording-status-own', methods=['POST'])
def set_all_recording_status_own():
    """Set every recording's status to 'Own'.

    Matches the local backfill alongside the dropdown restriction
    to {Own, Ordered}. Safe to re-run.
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    r = db.execute("UPDATE recordings SET status = 'Own'")
    db.commit()
    return jsonify(updated=r.rowcount)


@app.route('/admin/rename-recording-type-lp-to-vinyl', methods=['POST'])
def rename_recording_type_lp_to_vinyl():
    """Rename recordings.type 'LP' -> 'Vinyl'.

    Dropdown is now {Vinyl, CD, SACD, Tape}. Any stale 'LP' rows
    (from an earlier short-lived migration) are flipped back to
    'Vinyl'. Safe to re-run.
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    r = db.execute("UPDATE recordings SET type = 'Vinyl' WHERE type = 'LP'")
    db.commit()
    return jsonify(updated=r.rowcount)


@app.route('/admin/clear-recording-numeric-notes', methods=['POST'])
def clear_recording_numeric_notes():
    """Null out recordings.notes where it's a bare number.

    The earlier FM import mistakenly wrote CSV column 6 (price) into
    the notes column. Any row whose notes is just an integer or
    decimal (< 12 chars, no spaces) is that stale price data. Run
    this on Railway once, then hit /admin/upsert-recordings to fill
    the real price + notes columns from Recording.csv. Safe to
    re-run.
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    r = db.execute(
        "UPDATE recordings SET notes = NULL "
        "WHERE notes IS NOT NULL "
        "  AND TRIM(notes) NOT LIKE '% %' "
        "  AND LENGTH(TRIM(notes)) < 12 "
        "  AND CAST(TRIM(notes) AS REAL) >= 0 "
        "  AND TRIM(notes) GLOB '[0-9]*'"
    )
    db.commit()
    return jsonify(updated=r.rowcount)


@app.route('/admin/upsert-recordings', methods=['POST'])
def upsert_recordings():
    """Upsert Recording.csv into the recordings table.

    Matches on CSV UUID (col 23) against recordings.id.
    - existing row: overwrite a column only when the CSV value is
      non-blank, preserving in-app edits.
    - new UUID: INSERT as a fresh record.
    Safe to re-run; never deletes.
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)

    def _clean(s): return (s or '').replace('\x0b', '\n').strip() or None
    def _pdate(s):
        s = (s or '').strip().split(' ')[0]
        if not s: return None
        for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y', '%d/%m/%Y'):
            try: return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
            except ValueError: continue
        return None
    def _pnum(s, cast=float):
        s = (s or '').strip().replace(',', '').replace('$', '')
        try: return cast(s)
        except (ValueError, TypeError): return None

    field_map = [
        ('title',           lambda r: _clean(r[10])),
        ('artist',          lambda r: _clean(r[0])),
        ('type',            lambda r: _clean(r[11])),
        ('genre',           lambda r: _clean(r[2])),
        ('genre_2',         lambda r: _clean(r[3])),
        ('year_recorded',   lambda r: _clean(r[13])),
        ('speed',           lambda r: _clean(r[9])),
        ('sound',           lambda r: _clean(r[8])),
        ('like_field',      lambda r: _clean(r[18])),
        ('number_position', lambda r: _pnum(r[21], int)),
        ('other',           lambda r: _clean(r[5])),
        ('date',            lambda r: _pdate(r[1])),
        ('price',           lambda r: _pnum(r[6])),
        ('vendor',          lambda r: _clean(r[12])),
        ('notes',           lambda r: _clean(r[4])),
        ('owner',           lambda r: _clean(r[22])),
        ('property',        lambda r: _clean(r[7])),
    ]

    db = get_db()
    updated = filled_cols = inserted = skipped = 0
    now = datetime.utcnow().isoformat()

    for row in _csv_rows('Recording.csv'):
        if len(row) < 24:
            skipped += 1
            continue
        uid = (row[23] or '').strip()
        if not uid:
            skipped += 1
            continue
        vals = {col: fn(row) for col, fn in field_map}
        existing = db.execute(
            "SELECT * FROM recordings WHERE lower(id) = lower(?)", (uid,)
        ).fetchone()
        if existing:
            to_set = {}
            for col, new_val in vals.items():
                if new_val in (None, ''):
                    continue
                old_val = existing[col]
                old_n = '' if old_val is None else str(old_val).strip()
                new_n = str(new_val).strip()
                if old_n != new_n:
                    to_set[col] = new_val
            if to_set:
                assigns = ', '.join(f'{c} = ?' for c in to_set) + ', updated_at = ?'
                db.execute(
                    f'UPDATE recordings SET {assigns} WHERE lower(id) = lower(?)',
                    list(to_set.values()) + [now, uid],
                )
                updated += 1
                filled_cols += len(to_set)
        else:
            cols = ['id'] + list(vals.keys()) + ['created_at', 'updated_at']
            placeholders = ','.join(['?'] * len(cols))
            db.execute(
                f'INSERT INTO recordings ({",".join(cols)}) VALUES ({placeholders})',
                [uid] + list(vals.values()) + [now, now],
            )
            inserted += 1

    db.commit()
    total = db.execute('SELECT COUNT(*) FROM recordings').fetchone()[0]
    return jsonify(updated=updated, filled_columns=filled_cols,
                   inserted=inserted, skipped=skipped, total=total)


@app.route('/admin/backfill-camera-status-own', methods=['POST'])
def backfill_camera_status_own():
    """Set status='Own' for any camera with a NULL/blank status.

    Mirrors the local backfill after the Camera Status dropdown was
    restricted to {Own, Sold, Gifted}. Preserves existing non-blank
    values. Safe to re-run.
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    r = db.execute(
        "UPDATE cameras SET status = 'Own' "
        "WHERE status IS NULL OR TRIM(status) = ''"
    )
    db.commit()
    return jsonify(updated=r.rowcount)


@app.route('/admin/backfill-property-owner-ym', methods=['POST'])
def backfill_property_owner_ym():
    """Set owner='YM' for every Own Residential/Commercial property.

    Mirrors the local backfill done after the Owner field was added.
    Leaves Sold rows alone. Safe to re-run.
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    r = db.execute(
        "UPDATE properties SET owner = 'YM' "
        "WHERE status = 'Own' AND type IN ('Residential', 'Commercial')"
    )
    db.commit()
    return jsonify(updated=r.rowcount)


# FileMaker container-field export filename -> (table, column)
#   Coin_<UUID>_Image1.jpg  -> coins.image_1 (obverse)
#   Coin_<UUID>_Image2.jpg  -> coins.image_2 (reverse)
# See import_fm_images.py for the matching CLI importer.
FM_FIELD_MAP = {
    # Receipt mappings deliberately removed for the categories whose
    # receipt → documents migration completed (watches, coins, pens,
    # art, rifles). Routing a FileMaker `<table>_<uuid>_Receipt.<ext>`
    # back into the legacy receipt column would re-populate the very
    # field the migration just NULLed, and the next boot's
    # _migrate_receipt_into_documents would re-create the phantom
    # Receipt-titled docs entry. Files matching those keys now hit
    # the "no mapping" skip branch and are reported as skipped — the
    # user can re-upload via the dynamic docs UI if they're real
    # receipts, or just leave them out of the FM batch.
    # Recordings keeps its Receipt mapping because the migration was
    # never run for it (the FM-era receipt slot historically held
    # cover-image data and migrating it would corrupt the docs JSON).
    ('Watch', 'ImageObv'):        ('watches',      'image_obv'),
    ('Watch', 'Document'):        ('watches',      'document'),
    ('Coin', 'Image1'):           ('coins',        'image_1'),
    ('Coin', 'Image2'):           ('coins',        'image_2'),
    ('Coin', 'Document1'):        ('coins',        'document_1'),
    ('Coin', 'Document2'):        ('coins',        'document_2'),
    ('Camera', 'Image'):          ('cameras',      'image'),
    ('Lens', 'Image'):            ('lenses',       'image'),
    ('Pen', 'Image'):             ('pens',         'image'),
    ('Art', 'Image'):             ('art',          'image'),
    ('Vehicle', 'Image'):         ('vehicles',     'image'),
    ('Vehicle', 'Registration'):  ('vehicles',     'registration'),
    ('Vehicle', 'Insurance'):     ('vehicles',     'insurance'),
    ('Vehicle', 'Invoice'):       ('vehicles',     'invoice'),
    ('Recording', 'Image'):       ('recordings',   'image'),
    ('Recording', 'Receipt'):     ('recordings',   'receipt'),
    ('Rifle', 'Image'):           ('rifles',       'image'),
    ('CreditCard', 'ImageFront'): ('credit_cards', 'image_front'),
    ('CreditCard', 'ImageBack'):  ('credit_cards', 'image_back'),
    ('Property', 'Image'):        ('properties',   'image'),
    ('Person', 'HeadShot'):       ('persons',      'head_shot'),
    ('Person', 'Image1'):         ('persons',      'image_1'),
    ('Person', 'Image7'):         ('persons',      'image_7'),
    ('Person', 'Image9'):         ('persons',      'image_9'),
    ('Person', 'LicenseObverse'): ('persons',      'license_obverse'),
    ('Person', 'LicenseReverse'): ('persons',      'license_reverse'),
    ('Person', 'HealthCardObv'):  ('persons',      'health_card_obv'),
    ('Person', 'HealthCardRev'):  ('persons',      'health_card_rev'),
    ('Person', 'Passport'):       ('persons',      'passport'),
    ('Person', 'GlobalEntry'):    ('persons',      'global_entry'),
    ('Person', 'EyePrescription'):('persons',      'eye_prescription'),
    ('Person', 'Medicare'):       ('persons',      'medicare'),
}


def _parse_fm_filename(filename):
    """Parse 'Coin_<UUID>_Image1.jpg' -> ('Coin', uuid, 'Image1', '.jpg')."""
    name, ext = os.path.splitext(filename)
    parts = name.split('_', 2)
    if len(parts) < 3:
        return None
    table = parts[0]
    remainder = parts[1] + '_' + parts[2]
    for i in range(len(remainder) - 1, -1, -1):
        if remainder[i] == '_':
            pk = remainder[:i]
            field = remainder[i + 1:]
            clean = pk.replace('-', '')
            if len(clean) >= 16 and all(c in '0123456789abcdefABCDEF' for c in clean):
                return (table, pk, field, ext)
    return None


def _coin_bin_candidates(filename):
    """Yield plausible (bin, slot, ext) interpretations of a coin filename.

    FileMaker's container-field export convention:
      - first image keeps the bin as its base name      → slot 1 (Obverse)
      - second image gets a ' 2' suffix appended        → slot 2 (Reverse)

    So the caller sees all of these:

        C 94.jpg      → ('C 94', 1)              # Obverse only
        C 94 2.jpg    → ('C 94', 2)              # Reverse
        C 1_1.jpg     → ('C 1', 1)               # explicit suffix form
        NM 100 2.jpg  → ('NM 100', 2)

    There's genuine ambiguity with names like ``C 2.jpg`` — it could mean
    bin ``C`` slot 2 OR bin ``C 2`` slot 1. We yield the suffix-stripped
    interpretation first and the whole-name interpretation second; the
    upload handler picks the first one whose bin exists in the coins
    table.
    """
    name, ext = os.path.splitext(filename)
    name = name.strip()
    if not name:
        return
    seen = set()
    for suffix, slot in ((' 2', '2'), ('_2', '2'), (' 1', '1'), ('_1', '1')):
        if name.endswith(suffix):
            bin_part = name[:-len(suffix)].strip()
            if bin_part and (bin_part, slot) not in seen:
                seen.add((bin_part, slot))
                yield (bin_part, slot, ext)
            break
    if (name, '1') not in seen:
        yield (name, '1', ext)


@app.route('/admin/upload-fm-images', methods=['POST'])
def upload_fm_images():
    """Bulk-upload coin / FileMaker-exported image files.

    Two filename conventions are accepted:

    1. ``<Table>_<UUID>_<Field>.<ext>`` — the CLI exporter's format.
       Example: ``Coin_1DCBA0A5-...-98F2CB200C67_Image1.jpg``.

    2. ``<bin>_<slot>.<ext>`` — coin-only shortcut where ``<bin>`` is the
       coin's ``bin`` column (e.g. ``C 1``) and ``<slot>`` is ``1`` for the
       obverse (``image_1``) or ``2`` for the reverse (``image_2``).
       Example: ``C 1_1.jpg`` (obverse of bin ``C 1``).

    curl example:
        for f in ~/Desktop/fm_images/*; do
          curl -F "files=@$f" \\
               -F "secret=stuffapp-bulk-import-2026" \\
               https://<host>/admin/upload-fm-images
        done
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    files = request.files.getlist('files')
    if not files:
        return jsonify(error='No files uploaded'), 400
    db = get_db()
    imported = 0
    skipped = []
    for f in files:
        if not f or not f.filename:
            continue
        if not allowed_file(f.filename):
            skipped.append({'file': f.filename, 'reason': 'extension not allowed'})
            continue

        sql_table = sql_column = pk = ext = None

        parsed = _parse_fm_filename(f.filename)
        if parsed:
            table_prefix, pk, field_name, ext = parsed
            key = (table_prefix, field_name)
            if key not in FM_FIELD_MAP:
                skipped.append({'file': f.filename,
                                'reason': f'no mapping for {table_prefix}.{field_name}'})
                continue
            sql_table, sql_column = FM_FIELD_MAP[key]
            row = db.execute(f"SELECT id FROM {sql_table} WHERE id = ?",
                             (pk,)).fetchone()
            if not row:
                skipped.append({'file': f.filename,
                                'reason': f'no record {pk} in {sql_table}'})
                continue
        else:
            candidates = list(_coin_bin_candidates(f.filename))
            if not candidates:
                skipped.append({'file': f.filename, 'reason': 'unparseable'})
                continue
            matched = None
            tried_bins = []
            for bin_value, slot, file_ext in candidates:
                tried_bins.append(bin_value)
                row = db.execute(
                    "SELECT id FROM coins WHERE bin = ?", (bin_value,)
                ).fetchone()
                if row:
                    matched = (row['id'], slot, file_ext)
                    break
            if not matched:
                skipped.append({
                    'file': f.filename,
                    'reason': f'no coin with bin (tried: {tried_bins})',
                })
                continue
            pk, slot, ext = matched
            sql_table = 'coins'
            sql_column = 'image_1' if slot == '1' else 'image_2'

        stored_name = f"{uuid.uuid4().hex}{ext.lower()}"
        f.save(os.path.join(UPLOAD_FOLDER, stored_name))
        db.execute(
            f"UPDATE {sql_table} SET {sql_column} = ?, updated_at = ? WHERE id = ?",
            (stored_name, datetime.utcnow().isoformat(), pk),
        )
        imported += 1
    db.commit()
    return jsonify(imported=imported, skipped_count=len(skipped), skipped=skipped[:20])


_IMG_MAGIC = (
    (b'\xff\xd8\xff',       '.jpg'),
    (b'\x89PNG\r\n\x1a\n',  '.png'),
    (b'GIF8',               '.gif'),
    (b'RIFF',               '.webp'),   # actual WEBP check is done separately
    (b'II*\x00',            '.tif'),
    (b'MM\x00*',            '.tif'),
    (b'%PDF',               '.pdf'),
)


def _image_ext_from_bytes(data):
    if len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return '.webp'
    for prefix, ext in _IMG_MAGIC:
        if data.startswith(prefix):
            return ext
    return '.bin'


@app.route('/admin/upload-lens-b64', methods=['POST'])
def upload_lens_b64():
    """Decode and apply a FileMaker base64 text export of lens images.

    Accepts a single multipart field ``file`` pointing at the .txt file
    produced by the Lens "Export Images" FM script. Each line is:

        <serial_number>|<base64-image>

    separated by ``¶`` (CR) or ``\\n``. We decode, detect the image
    format from magic bytes, write to uploads/ with a fresh UUID, and
    set ``lenses.image`` on the matching row.

    Lines whose serial is unknown (or empty) come back in ``skipped``.
    Safe to re-run.

    curl example:
        curl -F "file=@~/Desktop/lens_images_b64.txt" \\
             -F "secret=stuffapp-bulk-import-2026" \\
             https://<host>/admin/upload-lens-b64
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    upload = request.files.get('file')
    if not upload:
        return jsonify(error='No file uploaded (field name: "file")'), 400
    raw = upload.read()
    # FileMaker's Export Field Contents writes UTF-16 with a BOM; handle it
    # along with UTF-8 (with or without BOM).
    if raw.startswith(b'\xff\xfe'):
        content = raw[2:].decode('utf-16-le', errors='replace')
    elif raw.startswith(b'\xfe\xff'):
        content = raw[2:].decode('utf-16-be', errors='replace')
    elif raw.startswith(b'\xef\xbb\xbf'):
        content = raw[3:].decode('utf-8', errors='replace')
    else:
        content = raw.decode('utf-8', errors='replace')
    # FM separates records with bare CR ("¶") but Base64Encode's wraps
    # may be CRLF (depending on OS/version). If we converted CRLF → CR
    # first, those wrap breaks would split records. Convert CRLF → LF
    # so only the true record terminator (bare CR) remains, then split
    # on that. b64decode ignores internal LFs as whitespace.
    content = content.replace('\r\n', '\n')
    sep = '\r' if '\r' in content else '\n'
    lines = [ln for ln in content.split(sep) if ln.strip()]
    db = get_db()
    imported = 0
    skipped = []
    for i, line in enumerate(lines, 1):
        if '|' not in line:
            skipped.append({'line': i, 'reason': 'no separator'})
            continue
        serial, b64 = line.split('|', 1)
        serial = serial.strip()
        if not serial:
            skipped.append({'line': i, 'reason': 'empty serial'})
            continue
        try:
            data = base64.b64decode(b64, validate=False)
        except Exception as e:
            skipped.append({'line': i, 'serial': serial, 'reason': f'base64 decode: {e}'})
            continue
        if not data:
            skipped.append({'line': i, 'serial': serial, 'reason': 'empty image'})
            continue
        row = db.execute(
            'SELECT id FROM lenses WHERE serial_number = ?', (serial,)
        ).fetchone()
        if not row:
            skipped.append({'line': i, 'serial': serial, 'reason': 'no lens with this serial'})
            continue
        ext = _image_ext_from_bytes(data)
        stored_name = f'{uuid.uuid4().hex}{ext}'
        with open(os.path.join(UPLOAD_FOLDER, stored_name), 'wb') as out:
            out.write(data)
        db.execute(
            'UPDATE lenses SET image = ?, updated_at = ? WHERE serial_number = ?',
            (stored_name, datetime.utcnow().isoformat(), serial),
        )
        imported += 1
    db.commit()
    return jsonify(imported=imported, skipped_count=len(skipped), skipped=skipped[:20])


@app.route('/admin/upload-art-b64', methods=['POST'])
def upload_art_b64():
    """Decode a FileMaker base64 text export of art images.

    Line format: ``<title>||<artist>||<base64-image>`` separated by
    ``\\r`` (CR, from FM's ``¶``). Same encoding rules as
    ``/admin/upload-lens-b64`` (UTF-16 BOM detection, CR/LF handling).

    Matches art rows by the ``(title, artist)`` pair since the prod
    UUIDs don't align with Art.csv UUIDs (legacy import generated
    fresh UUIDs).
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    upload = request.files.get('file')
    if not upload:
        return jsonify(error='No file uploaded (field name: "file")'), 400
    raw = upload.read()
    if raw.startswith(b'\xff\xfe'):
        content = raw[2:].decode('utf-16-le', errors='replace')
    elif raw.startswith(b'\xfe\xff'):
        content = raw[2:].decode('utf-16-be', errors='replace')
    elif raw.startswith(b'\xef\xbb\xbf'):
        content = raw[3:].decode('utf-8', errors='replace')
    else:
        content = raw.decode('utf-8', errors='replace')
    content = content.replace('\r\n', '\n')
    sep = '\r' if '\r' in content else '\n'
    lines = [ln for ln in content.split(sep) if ln.strip()]
    db = get_db()
    imported = 0
    skipped = []
    for i, line in enumerate(lines, 1):
        # Accept either '||' (intended) or single '|' (common typo) as the
        # field separator. Base64 alphabet never contains '|', so splitting
        # on single '|' is safe even when that's what FM wrote.
        if '||' in line:
            parts = line.split('||')
        else:
            parts = line.split('|')
        if len(parts) < 3:
            skipped.append({'line': i, 'reason': 'bad format (need title,artist,base64)'})
            continue
        title = parts[0].strip()
        artist = parts[1].strip()
        b64 = ('||' if '||' in line else '|').join(parts[2:])
        if not title or not artist:
            skipped.append({'line': i, 'reason': 'missing title or artist'})
            continue
        try:
            data = base64.b64decode(b64, validate=False)
        except Exception as e:
            skipped.append({'line': i, 'title': title, 'reason': f'base64 decode: {e}'})
            continue
        if not data:
            skipped.append({'line': i, 'title': title, 'reason': 'empty image'})
            continue
        row = db.execute(
            'SELECT id FROM art WHERE title = ? AND artist = ?', (title, artist)
        ).fetchone()
        if not row:
            skipped.append({'line': i, 'title': title, 'artist': artist,
                            'reason': 'no art with this title/artist'})
            continue
        ext = _image_ext_from_bytes(data)
        stored_name = f'{uuid.uuid4().hex}{ext}'
        with open(os.path.join(UPLOAD_FOLDER, stored_name), 'wb') as out:
            out.write(data)
        db.execute(
            'UPDATE art SET image = ?, updated_at = ? WHERE title = ? AND artist = ?',
            (stored_name, datetime.utcnow().isoformat(), title, artist),
        )
        imported += 1
    db.commit()
    return jsonify(imported=imported, skipped_count=len(skipped), skipped=skipped[:20])


@app.route('/admin/sync-coin-bins', methods=['POST'])
def sync_coin_bins():
    """Populate ``coins.bin`` so the bin-slot image upload can find coins.

    Two-pass strategy:

    1. **UUID match from Coin.csv.** Col 1 = bin (e.g. ``C 1``), col 29 = UUID.
       Updates any coin whose id matches.
    2. **coin_id fallback.** The legacy ``import_coins.py`` wrote bin-like
       strings into ``coin_id`` instead of ``bin``. For any coin still with a
       NULL/blank bin, copy ``coin_id`` across if it looks like a bin label
       (starts with a letter and a space — ``C 1``, ``N 12``, …).

    Safe to re-run.
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()

    # Pass 1 — UUID match
    uuid_updated = 0
    missing = []
    for row in _csv_rows('Coin.csv'):
        if len(row) < 30:
            continue
        bin_value = _mclean(row[1])
        pk = (row[29] or '').strip()
        if not bin_value or not pk:
            continue
        existing = db.execute('SELECT 1 FROM coins WHERE id = ?', (pk,)).fetchone()
        if not existing:
            missing.append({'id': pk, 'bin': bin_value})
            continue
        db.execute(
            "UPDATE coins SET bin = ?, updated_at = ? WHERE id = ?",
            (bin_value, datetime.utcnow().isoformat(), pk),
        )
        uuid_updated += 1

    # Pass 2 — coin_id fallback (common for data imported before bin existed)
    coin_id_updated = db.execute(
        "UPDATE coins "
        "SET bin = TRIM(coin_id), updated_at = ? "
        "WHERE (bin IS NULL OR TRIM(bin) = '') "
        "  AND coin_id IS NOT NULL "
        "  AND TRIM(coin_id) != '' "
        "  AND LENGTH(TRIM(coin_id)) BETWEEN 3 AND 8 "
        "  AND (TRIM(coin_id) LIKE '_ %' OR TRIM(coin_id) LIKE '__ %')",
        (datetime.utcnow().isoformat(),),
    ).rowcount

    db.commit()
    total = db.execute(
        "SELECT COUNT(*) FROM coins WHERE bin IS NOT NULL AND TRIM(bin) != ''"
    ).fetchone()[0]
    return jsonify(
        uuid_updated=uuid_updated,
        coin_id_updated=coin_id_updated,
        coins_with_bin=total,
        missing_from_csv_count=len(missing),
        missing_from_csv=missing[:20],
    )


@app.route('/admin/reimport-properties-topics', methods=['POST'])
def reimport_properties_topics():
    """Re-import properties and topics from Property.csv / Topic.csv.

    Fixes the mis-aligned columns from the prior property import
    (wifi, wifi_name, alarm_account, archive) and populates the new
    topics table. UPSERTs properties by id so existing ``owner`` and
    ``image`` values are preserved. Topics are fully replaced. Safe
    to re-run.
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()

    # --- Properties: UPSERT by id, preserving owner + image ---
    prop_updated = 0
    prop_inserted = 0
    for row in _csv_rows('Property.csv'):
        if len(row) < 26:
            continue
        uid = (row[19] or '').strip()
        if len(uid) < 8:
            uid = str(uuid.uuid4())
        created = _mdatetime(row[10]) or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        updated = _mdatetime(row[14]) or created
        existed = db.execute('SELECT 1 FROM properties WHERE id=?', (uid,)).fetchone()
        db.execute('''
            INSERT INTO properties (
                id, name, short_name, type, address, year_built,
                ein, llc, wifi, wifi_name, alarm_company, alarm_account,
                alarm_code_1, alarm_password, alarm_phone, alarm_notes,
                date, price, notes, status, archive, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                name          = excluded.name,
                short_name    = excluded.short_name,
                type          = excluded.type,
                address       = excluded.address,
                year_built    = excluded.year_built,
                ein           = excluded.ein,
                llc           = excluded.llc,
                wifi          = excluded.wifi,
                wifi_name     = excluded.wifi_name,
                alarm_company = excluded.alarm_company,
                alarm_account = excluded.alarm_account,
                alarm_code_1  = excluded.alarm_code_1,
                alarm_password= excluded.alarm_password,
                alarm_phone   = excluded.alarm_phone,
                alarm_notes   = excluded.alarm_notes,
                date          = excluded.date,
                price         = excluded.price,
                notes         = excluded.notes,
                status        = excluded.status,
                archive       = excluded.archive,
                created_at    = excluded.created_at,
                updated_at    = excluded.updated_at
        ''', (
            uid, _mclean(row[16]), _mclean(row[20]), _mclean(row[22]),
            _mclean(row[0]), _mnum(row[25], int),
            _mclean(row[12]), _mclean(row[13]),
            _mclean(row[23]), _mclean(row[24]),
            _mclean(row[3]), _mclean(row[1]), _mclean(row[2]),
            _mclean(row[5]), _mclean(row[6]), _mclean(row[4]),
            _mdate(row[11]), _mnum(row[18]), _mclean(row[17]), _mclean(row[21]),
            _mclean(row[7]),
            created, updated,
        ))
        if existed:
            prop_updated += 1
        else:
            prop_inserted += 1

    # --- Topics: full replace ---
    db.execute('DELETE FROM topics')
    name_to_id = {
        r['name']: r['id'] for r in db.execute(
            'SELECT name, id FROM properties WHERE name IS NOT NULL'
        )
    }
    topics_inserted = 0
    topics_unlinked = 0
    for row in _csv_rows('Topic.csv'):
        if len(row) < 8:
            continue
        subject = _mclean(row[4])
        body = _mclean(row[5])
        if not subject and not body:
            continue
        uid = (row[6] or '').strip()
        if len(uid) < 8:
            uid = str(uuid.uuid4())
        prop_id = name_to_id.get(_mclean(row[7]) or '')
        created = _mdatetime(row[1]) or datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        updated = _mdatetime(row[2]) or created
        db.execute(
            'INSERT INTO topics (id, property_id, subject, body, created_at, updated_at) '
            'VALUES (?,?,?,?,?,?)',
            (uid, prop_id, subject, body, created, updated),
        )
        topics_inserted += 1
        if prop_id is None:
            topics_unlinked += 1

    db.commit()
    return jsonify(
        properties_updated=prop_updated,
        properties_inserted=prop_inserted,
        topics_inserted=topics_inserted,
        topics_unlinked=topics_unlinked,
    )


@app.route('/admin/assign-missing-coin-ids', methods=['POST'])
def assign_missing_coin_ids():
    """Assign the next NM N coin_id to coins with an empty coin_id.

    Iterates empty-coin_id rows ordered by denomination, obv_rev and
    assigns NM <max+1>, NM <max+2>, ... in that order. Safe to re-run.
    """
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    rows = db.execute(
        "SELECT id, denomination, obv_rev FROM coins "
        "WHERE coin_id IS NULL OR TRIM(coin_id) = '' "
        "ORDER BY denomination, obv_rev"
    ).fetchall()
    max_nm = 0
    for r in db.execute("SELECT coin_id FROM coins WHERE coin_id LIKE 'NM %'"):
        try:
            n = int((r['coin_id'] or '').split()[1])
            if n > max_nm: max_nm = n
        except (ValueError, IndexError):
            pass
    assigned = []
    for i, r in enumerate(rows):
        new_id = f'NM {max_nm + 1 + i}'
        db.execute("UPDATE coins SET coin_id = ? WHERE id = ?", (new_id, r['id']))
        assigned.append({'id': r['id'], 'denomination': r['denomination'],
                         'obv_rev': r['obv_rev'], 'coin_id': new_id})
    db.commit()
    return jsonify(assigned=assigned, count=len(assigned))


@app.route('/admin/fix-coin-region-mint', methods=['POST'])
def fix_coin_region_mint():
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    updated = 0
    not_found = 0
    for row in _csv_rows('Coin.csv'):
        if len(row) < 45:
            continue
        coin_id = _mclean(row[1])
        csv_uuid = _mclean(row[29])
        mint = _mclean(row[21])
        region = _mclean(row[35])
        if coin_id:
            r = db.execute("UPDATE coins SET mint = ?, region = ? WHERE coin_id = ?",
                           (mint, region, coin_id))
            if r.rowcount:
                updated += r.rowcount
                continue
        if csv_uuid:
            r = db.execute("UPDATE coins SET mint = ?, region = ? WHERE lower(id) = lower(?)",
                           (mint, region, csv_uuid))
            if r.rowcount:
                updated += r.rowcount
                continue
        not_found += 1
    db.commit()
    return jsonify(updated=updated, not_found=not_found)


@app.route('/admin/import-audio-missing', methods=['POST'])
def import_audio_missing():
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    existing_ids = {(r['id'] or '').lower() for r in db.execute("SELECT id FROM audio")}

    inserted = 0
    skipped_existing = 0
    skipped_bad = 0
    now = datetime.utcnow().isoformat()

    for row in _csv_rows('Audio.csv'):
        if len(row) < 14:
            skipped_bad += 1
            continue
        csv_uuid = _mclean(row[9])
        if not csv_uuid:
            skipped_bad += 1
            continue
        if csv_uuid.lower() in existing_ids:
            skipped_existing += 1
            continue

        db.execute('''
            INSERT INTO audio (
                id, make, model, type, date, price, vendor, notes, property,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            csv_uuid,
            _mclean(row[0]),          # make
            _mclean(row[4]),          # model
            _mclean(row[12]),         # type
            _mdate(row[3]),           # date
            _mnum(row[8]),            # price
            _mclean(row[13]),         # vendor
            _mclean(row[7]),          # notes
            _mclean(row[10]),         # property
            now, now,
        ))
        inserted += 1
        existing_ids.add(csv_uuid.lower())

    db.commit()
    total = db.execute('SELECT COUNT(*) FROM audio').fetchone()[0]
    return jsonify(inserted=inserted, skipped_existing=skipped_existing,
                   skipped_bad=skipped_bad, total=total)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5001)
