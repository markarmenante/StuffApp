import sqlite3
import uuid
import os
import json
import re
import base64
from datetime import datetime, date
from flask import (Flask, g, render_template, request, redirect, url_for,
                   flash, send_from_directory, abort, jsonify, Response,
                   send_file)
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
    'strap_material': ['Case Metal','Croc','Leather','Ostrich','Rubber','Skin'],
    'strap_color': ['Black','Blue','Blue/Gray','Brown','Burgundy','Dk Brown','Eggplant','Gold','Gray','Green','Lt Brown','Navy Blue','Red','Rose Gold','Stainless','Tan','Titanium','White Gold'],
    'owner': ['YM','Mark','Young'],
    'property': [
        '42 Hotaling',
        'Carpinteria','Glass House','Harlemville','Lahontan','Martis',
        'NYC','Paris','Party Barn','Pond House','Rec Center',
    ],
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
    """Return the canonical value for a known alias, or the value unchanged."""
    if value is None:
        return value
    aliases = FIELD_ALIASES.get((table, field_name))
    if not aliases:
        return value
    return aliases.get(value.strip().lower(), value)


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
    'vehicles':     'YM',
    'recordings':   'Mark',
    'audio':        'Mark',
    'rifles':       'Mark',
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
         'options': ['', 'Automatic', 'Manual', 'Quartz', 'Spring Drive', 'Co-Axial']},
        {'name': 'movement_jewels', 'label': 'Jewels',            'type': 'number'},
        {'name': 'movement_origin', 'label': 'Movement Origin',   'type': 'text'},
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
        {'name': 'image_obv',       'label': 'Image (Obverse)',   'type': 'file'},
        {'name': 'image_rev',       'label': 'Image (Reverse)',   'type': 'file'},
        {'name': 'receipt',         'label': 'Receipt',           'type': 'file'},
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
        {'name': 'receipt',         'label': 'Receipt',           'type': 'file'},
        {'name': 'document_1',      'label': 'Document 1',        'type': 'file'},
        {'name': 'document_2',      'label': 'Document 2',        'type': 'file'},
    ],
    'cameras': [
        {'name': 'make',            'label': 'Make',              'type': 'text'},
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
        {'name': 'receipt',         'label': 'Receipt',           'type': 'file'},
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
        {'name': 'receipt',         'label': 'Receipt',           'type': 'file'},
        {'name': 'doc_2',           'label': 'Doc 2',             'type': 'file'},
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
        {'name': 'receipt',         'label': 'Receipt',           'type': 'file'},
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
        {'name': 'receipt',         'label': 'Receipt',           'type': 'file'},
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
         'options': ['', 'Residence', 'Commercial', 'Rental', 'Vacation', 'Land', 'Other']},
        {'name': 'address',         'label': 'Address',           'type': 'textarea'},
        {'name': 'year_built',      'label': 'Year Built',        'type': 'number'},
        {'name': 'ein',             'label': 'EIN',               'type': 'text'},
        {'name': 'llc',             'label': 'LLC',               'type': 'text'},
        {'name': 'wifi',            'label': 'WiFi Password',     'type': 'text'},
        {'name': 'wifi_name',       'label': 'WiFi Name (SSID)',  'type': 'text'},
        {'name': 'date',            'label': 'Purchase Date',     'type': 'date'},
        {'name': 'price',           'label': 'Price',             'type': 'number'},
        {'name': 'notes',           'label': 'Notes',             'type': 'textarea'},
        {'name': 'status',          'label': 'Status',            'type': 'select',
         'options': ['', 'Own', 'Sold']},
        {'name': 'owner',           'label': 'Owner',             'type': 'select',
         'options': ['', 'YM', 'Mark', 'Young']},
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

# List-view extra info fields per category
LIST_EXTRA_FIELDS = {
    'watches':      ['metal', 'reference', 'vendor', 'property'],
    'coins':        ['metal', 'denomination', 'date_1_text', 'grade'],
    'cameras':      ['digital_film', 'film_size', 'lens_mount', 'megapixels', 'serial_number', 'vendor', 'price', 'property'],
    'lenses':       ['mount', 'aperture', 'filter_size', 'length', 'serial_number', 'vendor', 'price', 'property'],
    'pens':         ['type', 'action', 'nib', 'cartridge', 'vendor', 'price', 'property'],
    'art':          ['medium', 'year', 'dimensions', 'vendor', 'price', 'location', 'property'],
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
    for _t in ('art', 'coins', 'watches', 'pens', 'rifles', 'audio'):
        _migrate_receipt_into_documents(db, _t)
    _strip_phantom_cover_image_docs(db)
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
        docs.insert(0, {'title': 'Receipt', 'filename': receipt})
        db.execute(
            f'UPDATE {table} SET documents = ? WHERE id = ?',
            (json.dumps(docs), row['id']),
        )


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


def _strip_phantom_cover_image_docs(db):
    """Remove phantom doc tiles created by legacy FileMaker imports.
    Two patterns get caught:

      1. Filename match — the tile's filename is identical to any
         OTHER file-typed column on the same record (cover image,
         secondary image slot, etc.). The legacy import wrote the
         same file into multiple columns and the doc-row backfill
         turned each into its own tile.

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
            other_files = {
                (row[c] or '').strip()
                for c in present_files
                if c in row.keys() and (row[c] or '').strip()
            }
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
                    # ident prefix (any dash variant).
                    if ident_prefixes and any(
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
    for slug, cat in CATEGORIES.items():
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


def get_typeahead(table, *fields):
    """Return dict of field -> sorted list of distinct non-empty values."""
    db = get_db()
    result = {}
    for field in fields:
        rows = db.execute(
            f"SELECT DISTINCT {field} as v FROM {table} WHERE {field} IS NOT NULL AND {field} != '' ORDER BY {field}"
        ).fetchall()
        result[field] = [r['v'] for r in rows]
    return result


TYPEAHEAD_FIELDS = {
    'watches':      ('brand', 'dial_color', 'strap_color', 'vendor'),
    'coins':        ('region', 'mint', 'denomination', 'vendor'),
    'art':          ('artist', 'medium', 'vendor', 'property', 'location'),
    'cameras':      ('make', 'vendor'),
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
    return get_typeahead(CATEGORIES[category]['table'], *fields)


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
    HEIC/HEIF input is transcoded to JPEG so browsers can render it."""
    if not file_obj or file_obj.filename == '':
        return None
    if not allowed_file(file_obj.filename):
        return None

    data = file_obj.read()
    ext = file_obj.filename.rsplit('.', 1)[1].lower()

    if _looks_like_heic(data) and HEIF_SUPPORTED:
        from io import BytesIO
        from PIL import Image
        img = Image.open(BytesIO(data))
        if img.mode != 'RGB':
            img = img.convert('RGB')
        out = BytesIO()
        img.save(out, format='JPEG', quality=90)
        data = out.getvalue()
        ext = 'jpg'

    stored_name = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(UPLOAD_FOLDER, stored_name), 'wb') as f:
        f.write(data)
    return stored_name


def get_file_fields(category):
    return [f['name'] for f in FIELDS[category] if f['type'] == 'file']


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


EXCLUDED_STATUSES = ('Own', 'Sold', 'Gifted', 'Own')  # dot filter excludes these

CATEGORY_FILTERS = {
    'watches': {
        'ordered': ("LOWER(TRIM(COALESCE(status,''))) = 'ordered'", []),
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
        'own':  ("LOWER(TRIM(COALESCE(status,''))) = 'own'", []),
        'sold': ("LOWER(TRIM(COALESCE(status,''))) = 'sold'", []),
    },
    # Cameras and lenses intentionally have no filter map — both lists
    # always show every record. Toolbar pills removed; default filter
    # removed.
    'properties': {
        # Single-axis filters
        'own':         ("LOWER(TRIM(COALESCE(status,''))) = 'own'", []),
        'sold':        ("LOWER(TRIM(COALESCE(status,''))) = 'sold'", []),
        'commercial':  ("LOWER(TRIM(COALESCE(type,'')))   = 'commercial'", []),
        'residential': ("LOWER(TRIM(COALESCE(type,'')))   = 'residential'", []),
        # Combined (status + type)
        'own_commercial':   ("LOWER(TRIM(COALESCE(status,''))) = 'own'  AND LOWER(TRIM(COALESCE(type,''))) = 'commercial'",  []),
        'own_residential':  ("LOWER(TRIM(COALESCE(status,''))) = 'own'  AND LOWER(TRIM(COALESCE(type,''))) = 'residential'", []),
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
    text_fields = [f['name'] for f in FIELDS[category]
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
        terms = [t for t in q.split() if t.strip()]
        for term in terms:
            num_term = _normalize_numeric_term(term)
            conds = []
            for col in text_fields:
                conds.append(f"{col} LIKE ?")
                params.append(f'%{term}%')
            for col in numeric_fields:
                conds.append(f"{col} LIKE ?")
                params.append(f'%{num_term}%')
            wheres.append('(' + ' OR '.join(conds) + ')')

    if dot:
        # Find which field holds status for this category
        status_col = 'status'
        field_names = [f['name'] for f in FIELDS[category]]
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


def _cat_id_prefix(property_name, date_1):
    """Two-letter prefix for a coin's cat_id: <location><era>.

    Location: C = Carpinteria, N = New York. Anything else is unmapped.
    Era:      A = minted before 500 AD, M = minted 500 AD or later.
    Returns None if either axis can't be determined.
    """
    p = (property_name or '').strip().lower()
    if p in ('carp', 'carpinteria'):
        loc = 'C'
    elif p in ('nyc', 'new york', 'ny'):
        loc = 'N'
    else:
        return None
    if date_1 is None or date_1 == '':
        return None
    try:
        d = int(date_1)
    except (TypeError, ValueError):
        return None
    return loc + ('A' if d < 500 else 'M')


def next_cat_id(db, property_name, date_1):
    """Next sequential cat_id for a coin at this property / era,
    zero-padded to 3 digits (e.g. 'CA001'). None if unassignable."""
    prefix = _cat_id_prefix(property_name, date_1)
    if not prefix:
        return None
    row = db.execute(
        "SELECT cat_id FROM coins WHERE cat_id LIKE ? "
        "ORDER BY CAST(SUBSTR(cat_id, 3) AS INTEGER) DESC LIMIT 1",
        [f'{prefix}%']).fetchone()
    n = 1
    if row and row['cat_id']:
        try:
            n = int(row['cat_id'][2:]) + 1
        except ValueError:
            n = 1
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
    "emmywatch.com",
    "thewatchpages.com",
    "hodinkee.com",
    "monochrome-watches.com",
    "watch-wiki.org / wikipedia watch entries",
]


def fetch_watch_specs(watch):
    """Use Claude's web_search tool to look up a watch's specs from
    reputable sources and return {field: value} suggestions.

    Only fields the model is confident about should be populated; all
    others should come back null. Raises RuntimeError on missing key or
    API failure.
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
    calibre_hint = (watch['calibre'] or '').strip()
    year_hint = watch['year']

    if not (brand or model or reference):
        raise RuntimeError('Need at least brand, model, or reference to look up specs.')

    ident = ' '.join(x for x in [
        brand, model,
        f'Ref. {reference}' if reference else '',
        f'Cal. {calibre_hint}' if calibre_hint else '',
        str(year_hint) if year_hint else '',
    ] if x)

    sources_bullets = '\n'.join(f'- {s}' for s in WATCH_SPEC_SOURCES)
    metals = ', '.join(VALUE_LISTS['metal_watch'])
    origins = ', '.join(VALUE_LISTS['movement_origin'])
    complications = ', '.join(COMPLICATIONS_OPTIONS)

    prompt = f"""You are filling in specification fields for a specific wristwatch using reputable public sources.

Watch: {ident}

Use at most 6 web searches, preferring these sources (roughly in order):
{sources_bullets}

For each field below, return the value you find in any of those sources. If one reputable source states a value clearly, use it; do not require unanimous agreement. Return null only when NO source you searched mentions the field at all. Prefer sourced values over leaving fields null.

Target fields:
- metal: one of [{metals}]
- case_diameter: number in mm (float)
- dial_color: short string (e.g. "Black", "Blue", "Silver")
- year: integer year of original release/manufacture
- edition: total count of pieces in a limited edition / limited run (integer). Return null for non-limited / open-production references.
- calibre: movement calibre name (e.g. "L951.5", "3135")
- movement_type: "Manual" or "Automatic"
- movement_origin: EXACTLY one of [{origins}] and nothing else. "In-House" = designed and made by the manufacturer; "Ébauche" = bought-in rough movement (e.g. ETA, Sellita, Valjoux) used as-is; "Modified" = an ébauche that has been noticeably reworked. Do not invent values like "Swiss" or "Ebauche-based".
- movement_jewels: integer
- beat: vibrations per hour (VPH) for mechanical movements, or raw Hz for quartz/tuning-fork movements. For mechanical (Manual/Automatic) pick from [18000, 19800, 21600, 25200, 28800, 36000]; if the source gives Hz, multiply by 7200 (2.5 Hz = 18000, 3 Hz = 21600, 4 Hz = 28800, 5 Hz = 36000). For battery-powered/quartz/tuning-fork movements, return the actual rate as stated (e.g. 360 for Accutron, 32768 for a quartz crystal, 7200 for a 1 Hz stepping quartz). Do NOT assume 28800 as a default — only return a value if the source clearly states it.
- reserve: power reserve in hours (integer)
- complications: array of strings drawn from [{complications}]
- clasp_type: clasp mechanism (short string)
- lug_mm: lug width in mm (float)
- strap_material: e.g. "Leather", "Steel", "Rubber"
- notes: a 2-4 sentence quality blurb about what makes this specific reference notable — its place in the brand's history, design innovation, technical distinction, or cultural significance. Write in a knowledgeable but concise collector's voice. Keep under 500 characters. Return null only if sources offer nothing substantive.

Reply with ONLY a JSON object, no prose, no code fences:
{{
  "metal": null,
  "case_diameter": null,
  "dial_color": null,
  "year": null,
  "edition": null,
  "calibre": null,
  "movement_type": null,
  "movement_origin": null,
  "movement_jewels": null,
  "beat": null,
  "reserve": null,
  "complications": null,
  "clasp_type": null,
  "lug_mm": null,
  "strap_material": null,
  "notes": null,
  "sources": "one-line note of which sources hit"
}}
"""

    # Cap the SDK request below gunicorn's 300s killer so we surface a
    # clean Python exception (and a JSON 503) instead of letting the
    # worker get SIGKILLed mid-flight and returning HTML/empty 500s.
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
                max_tokens=2048,
                tools=[{
                    'type': 'web_search_20250305',
                    'name': 'web_search',
                    'max_uses': 6,
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
    return json.loads(m.group(0))


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
together — don't just restate them. The catalog references and
grade notes often carry a lot of signal (BCD pedigree, Calciati
number, hoard provenance, strike quality, rarity call-outs); mine
them for anything useful.

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

3. Numismatic importance — rarity, die-study or hoard context,
   significance within the series (first portrait of a ruler, earliest
   use of a legend, reference-book pedigree, a benchmark type in a
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

    prompt = f"""You are an ancient-numismatics historian summarizing the {kind} of a specific coin.

{kind.capitalize()}: {topic}
Date range: {date_hint or '(not specified)'}
Other coin context: {ctx or '(none)'}

Use up to 4 concise web searches to ground facts. Focus on:
- What this {kind} was (city-state, kingdom, satrapy, Roman province, etc.)
- Key political/cultural events during the coin's date range that shaped its coinage
- Notable rulers or mint activity tied to this {kind}
- One-line significance in the broader Greek/Roman world

Reply with ONLY a JSON object, no prose, no code fences:
{{"markdown": "3–6 short lines. Prefix factual claims with '- '. May include 1–2 plain lines of context. Include 2–4 source URLs as trailing bare URLs after relevant bullets. Under ~700 chars total."}}"""

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
fences, no JSON.{players_block}{tracks_block}"""

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

    return {'markdown': md, 'players': new_players,
            'tracks': new_tracks, 'urls': urls}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return redirect(url_for('list_view', category='watches'))


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
                           extra_fields=extra_fields,
                           fields=FIELDS[category])


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
        for field in FIELDS[category]:
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
                if field['type'] == 'number' or fname in ('price', 'beat', 'reserve', 'value'):
                    val = val.replace('$', '').replace(',', '').strip()
                    # Strip trailing unit suffix ("8.50 g", "26.5 mm", "28800 hrs")
                    # in case the JS submit handler didn't run.
                    m = re.match(r'^\s*(-?\d+(?:\.\d+)?)\s*[A-Za-z%°/]*\s*$', val)
                    if m:
                        val = m.group(1)
                data[fname] = val if val else None

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

        # Required fields on create. Owner is required for every
        # category. Property is required for everything except
        # credit_cards and persons (neither has a property field).
        # Coins additionally need a date — Property + Date drive
        # Display Position numbering downstream.
        missing = []
        if not (data.get('owner') or '').strip():
            missing.append('Owner')
        if category not in ('credit_cards', 'persons'):
            prop_field = 'property_name' if category == 'coins' else 'property'
            if not (data.get(prop_field) or '').strip():
                missing.append('Property')
        if category == 'coins':
            if data.get('date_1') in (None, '') and not (data.get('date_1_text') or '').strip():
                missing.append('Date')
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
            return jsonify({'ok': True, 'id': record_id,
                            'detail_url': detail_url, 'save_url': save_url})
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
                           fields=FIELDS[category],
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
                           vlists=VALUE_LISTS,
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
            all_ids = [r['id'] for r in db.execute(
                f"SELECT id FROM {table} ORDER BY created_at DESC").fetchall()]
    else:
        all_ids = [r['id'] for r in db.execute(
            f"SELECT id FROM {table} ORDER BY created_at DESC").fetchall()]
    idx = all_ids.index(record_id) if record_id in all_ids else -1
    prev_id = all_ids[idx - 1] if idx > 0 else None
    next_id = all_ids[idx + 1] if idx < len(all_ids) - 1 else None

    if request.method == 'POST':
        now = datetime.utcnow().isoformat()
        updates = {'updated_at': now}

        for field in FIELDS[category]:
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
                if field['type'] == 'number' or fname in ('price', 'beat', 'reserve', 'value'):
                    val = val.replace('$', '').replace(',', '').strip()
                val = normalize_field_value(table, fname, val)
                updates[fname] = val if val else None

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
                           fields=FIELDS[category],
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
                           vlists=VALUE_LISTS,
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
    valid_fields = {f['name']: f for f in FIELDS[category]}
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

    # Strip currency/comma formatting for numeric fields
    if field['type'] == 'number' or field_name in ('price', 'beat', 'reserve', 'value'):
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
        'SELECT id, name FROM properties WHERE id = ?', [property_id]
    ).fetchone() if property_id else None
    if prop is None:
        abort(404)
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
        'SELECT id, name FROM properties WHERE id = ?', [topic['property_id']]
    ).fetchone()
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
    topic = db.execute('SELECT 1 FROM topics WHERE id = ?', [topic_id]).fetchone()
    if topic is None:
        return jsonify({'error': 'Unknown topic'}), 404
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
    'movement_type', 'movement_origin', 'movement_jewels',
    'beat', 'reserve', 'complications', 'clasp_type', 'lug_mm',
    'strap_material', 'notes',
)

# Fields we'll only populate when blank — never overwrite the existing
# value. Year is frequently engraved on caseback or papers, so the user's
# entry is authoritative over a web guess. Strap material is set from
# the physical strap on the watch — a web guess ("Leather") is almost
# always less precise than what's already there ("Croc").
WATCH_LOOKUP_BLANK_ONLY = {'year', 'strap_material', 'clasp_type', 'dial_color', 'metal'}


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
            if pd:
                try:
                    purchase_year = int(str(pd)[:4])
                    sugg_year = int(float(val))
                    if purchase_year < sugg_year:
                        val = purchase_year
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
            mech_allowed = {18000, 19800, 21600, 25200, 28800, 36000}
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


@app.route('/watches/<record_id>/apply-lookup', methods=['POST'])
def watch_apply_lookup(record_id):
    """Apply a user-selected subset of lookup suggestions to a watch.

    Body: ``{"updates": {"<field>": <value>, ...}}``
    Only fields listed in ``WATCH_LOOKUP_FILLABLE`` are accepted.
    """
    db = get_db()
    watch = db.execute("SELECT id FROM watches WHERE id = ?", (record_id,)).fetchone()
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
        return jsonify({'updated': 0, 'fields': []})
    set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
    now = datetime.utcnow().isoformat()
    params = list(updates.values()) + [now, record_id]
    db.execute(
        f"UPDATE watches SET {set_clause}, updated_at = ? WHERE id = ?",
        params,
    )
    db.commit()
    return jsonify({'updated': len(updates), 'fields': list(updates.keys())})


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
    new_players = data.get('players') or ''
    new_tracks = data.get('tracks') or ''
    try:
        existing_players = (rec['players'] or '').strip()
    except (IndexError, KeyError):
        existing_players = ''
    try:
        existing_tracks = (rec['tracks'] or '').strip()
    except (IndexError, KeyError):
        existing_tracks = ''
    sets, params = [], []
    if new_players and not existing_players:
        sets.append('players = ?'); params.append(new_players)
    if new_tracks and not existing_tracks:
        sets.append('tracks = ?'); params.append(new_tracks)
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
    # excluding this record). Each field is written only if the
    # sibling's column is currently empty — never clobbering user
    # edits on another copy. Saves the user from re-running Lookup
    # on every pressing in their collection.
    siblings_updated = 0
    title_norm = (rec['title']  or '').strip()
    artist_norm = (rec['artist'] or '').strip()
    new_notes = data.get('markdown') or ''
    new_urls_csv = ','.join(merged) if merged else ''
    if title_norm and artist_norm and (
        new_notes or new_players or new_tracks or new_urls_csv
    ):
        sib_rows = db.execute(
            "SELECT id, notes, players, tracks, notes_urls FROM recordings "
            "WHERE LOWER(TRIM(title)) = LOWER(TRIM(?)) "
            "  AND LOWER(TRIM(artist)) = LOWER(TRIM(?)) "
            "  AND id != ?",
            (title_norm, artist_norm, record_id),
        ).fetchall()
        for sib in sib_rows:
            sib_sets, sib_params = [], []
            if new_notes and not (sib['notes'] or '').strip():
                sib_sets.append('notes = ?'); sib_params.append(new_notes)
            if new_players and not (sib['players'] or '').strip():
                sib_sets.append('players = ?'); sib_params.append(new_players)
            if new_tracks and not (sib['tracks'] or '').strip():
                sib_sets.append('tracks = ?'); sib_params.append(new_tracks)
            if new_urls_csv and not (sib['notes_urls'] or '').strip():
                sib_sets.append('notes_urls = ?'); sib_params.append(new_urls_csv)
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

    stored = save_upload(f)
    if not stored:
        return jsonify({'error': 'Upload failed'}), 500

    # Allow specifying which image field to update (for coins with image_1/image_2 etc.)
    image_field = request.form.get('field') or CATEGORIES[category]['image_field']
    table       = CATEGORIES[category]['table']
    # Validate field name exists in the table schema
    db = get_db()
    cols = [row['name'] for row in db.execute(f"PRAGMA table_info({table})").fetchall()]
    if image_field not in cols:
        return jsonify({'error': 'Invalid field'}), 400
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
    valid = {f['name']: f for f in FIELDS[category]}
    if field_name not in valid or valid[field_name].get('type') != 'file':
        return jsonify({'error': 'Invalid file field'}), 400
    db = get_db()
    table = CATEGORIES[category]['table']
    cols = [row['name'] for row in db.execute(f"PRAGMA table_info({table})").fetchall()]
    if field_name not in cols:
        return jsonify({'error': 'Column not in table'}), 400
    existing = db.execute(
        f"SELECT {field_name} FROM {table} WHERE id = ?", [record_id]
    ).fetchone()
    old_filename = existing[field_name] if existing else None
    # Clear the paired title/label column too so the tile doesn't keep
    # showing a leftover auto-fill from a since-removed file.
    title_field = _title_field_for(category, field_name)
    cleared_title = title_field if title_field and title_field in cols else None
    sets = [f"{field_name} = NULL"]
    if cleared_title:
        sets.append(f"{cleared_title} = NULL")
    sets.append("updated_at = ?")
    db.execute(
        f"UPDATE {table} SET {', '.join(sets)} WHERE id = ?",
        [datetime.utcnow().isoformat(), record_id],
    )
    db.commit()
    if old_filename and field_name not in _PRESERVE_FILE_FIELDS:
        _unlink_upload(old_filename)
    return jsonify({'ok': True, 'cleared_title': cleared_title})


# ---------------------------------------------------------------------------
# Template filters
# ---------------------------------------------------------------------------

@app.template_filter('currency')
def currency_filter(value):
    """Format as $1,234 (no decimals)."""
    if value is None or value == '':
        return ''
    try:
        return f"${float(value):,.0f}"
    except (ValueError, TypeError):
        return str(value)


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
    'vehicles':   {'main': 'documents'},
    'pens':       {'main': 'documents'},
    'recordings': {'main': 'documents'},
    'rifles':     {'main': 'documents'},
    'audio':      {'main': 'documents'},
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
# multi-set categories (persons). Match is case-insensitive substring.
# The first matching column wins; otherwise the first declared set is
# used. Empty for single-set categories — they always land in 'main'.
SWEEP_DOC_SET_HINTS = {
    'persons': [
        ('health_documents', ('health', 'medic', 'medical', 'rx',
                              'prescription', 'doctor', 'eye', 'dental',
                              'insurance')),
        ('id_documents',     ('id', 'license', 'passport', 'visa',
                              'global entry', 'birth', 'social')),
    ],
}


def _route_sweep_doc_set(category, label):
    """Pick the JSON column for a sweep-uploaded file. Single-set
    categories always return their lone column; multi-set ones run
    SWEEP_DOC_SET_HINTS against the file's parsed label and fall back
    to the first declared set if nothing matches."""
    cols = _docs_cols_for(category)
    if not cols:
        return 'documents'
    if len(cols) == 1:
        return cols[0]
    label_l = (label or '').lower()
    for col, keywords in SWEEP_DOC_SET_HINTS.get(category, []):
        if col not in cols:
            continue
        if any(k in label_l for k in keywords):
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
    _docs_save(db, table, record_id, src_docs, src_col)
    _docs_save(db, table, record_id, dst_docs, dst_col)
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


@app.context_processor
def inject_globals():
    return {
        'CATEGORIES': CATEGORIES,
        'now': datetime.utcnow(),
        'current_user': g.get('current_user'),
        'allowed_cats': g.get('allowed_cats', set()),
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


def _ensure_owner_user(db):
    """Idempotent: make sure the owner email exists with full access."""
    db.execute(
        "INSERT INTO users (id, email, display_name, role, categories) "
        "VALUES (?, ?, ?, 'owner', '*') "
        "ON CONFLICT(email) DO UPDATE SET role='owner', categories='*'",
        [str(uuid.uuid4()), OWNER_EMAIL, 'Mark Armenante']
    )


def _resolve_user_email():
    """Email of the currently authenticated visitor. CF Access on prod;
    STUFFAPP_DEV_USER env var locally so per-user testing still works."""
    e = (request.headers.get('Cf-Access-Authenticated-User-Email') or
         os.environ.get('STUFFAPP_DEV_USER') or OWNER_EMAIL)
    return (e or '').strip().lower()


def _expand_categories(raw, role):
    """Resolve a user's category list. '*' or owner role → everything."""
    if role == 'owner' or (raw or '').strip() == '*':
        return set(CATEGORIES.keys())
    return {c.strip() for c in (raw or '').split(',') if c.strip() in CATEGORIES}


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


# Endpoints that everyone gets to hit regardless of category access.
# (The static handler also bypasses; checked separately below.)
_AUTH_EXEMPT_ENDPOINTS = {'static', 'uploaded_file', 'file_thumb'}


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
    if request.form.get('secret') != IMPORT_MISSING_SECRET:
        abort(403)
    db = get_db()
    existing = set()
    for r in db.execute("SELECT reference, case_num, movement_num FROM watches"):
        existing.add(((r['reference'] or '').strip(),
                      (r['case_num'] or '').strip(),
                      (r['movement_num'] or '').strip()))

    inserted = 0
    skipped_existing = 0
    skipped_bad = 0
    now = datetime.utcnow().isoformat()

    for row in _csv_rows('Watch.csv'):
        if len(row) < 38:
            skipped_bad += 1
            continue
        reference = _mclean(row[28])
        case_num = _mclean(row[3])
        movement_num = _mclean(row[19])
        key = ((reference or '').strip(), (case_num or '').strip(), (movement_num or '').strip())
        if not any(key):
            skipped_bad += 1
            continue
        if key in existing:
            skipped_existing += 1
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
        existing.add(key)

    db.commit()
    total = db.execute('SELECT COUNT(*) FROM watches').fetchone()[0]
    return jsonify(inserted=inserted, skipped_existing=skipped_existing,
                   skipped_bad=skipped_bad, total=total)


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
        f"SELECT * FROM coins {where_sql} "
        "ORDER BY (coin_id IS NULL OR TRIM(coin_id) = ''), CAST(SUBSTR(coin_id, 3) AS INTEGER), coin_id",
        params).fetchall()

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
    """
    from io import BytesIO
    from PIL import Image
    from reportlab.lib.utils import ImageReader
    try:
        im = Image.open(path)
        im.thumbnail((512, 512))
        if im.mode not in ('RGB', 'L'):
            im = im.convert('RGB')
        buf = BytesIO()
        im.save(buf, format='JPEG', quality=85)
        buf.seek(0)
        return ImageReader(buf)
    except Exception:
        return None


def _draw_coin_card(c, coin, x, y, w, h):
    c.setStrokeColorRGB(0.25, 0.25, 0.25)
    c.setLineWidth(0.9)
    c.rect(x, y, w, h, stroke=1, fill=0)

    pad = 3
    inner_w = w - 2 * pad

    # Top row: region (bold, left) + date range (right)
    title = (coin['region'] or coin['authority'] or '').strip()
    date_from = (coin['date_1_text'] or '').strip()
    date_to = (coin['date_2_text'] or '').strip()
    date_range = f'{date_from} - {date_to}' if date_from and date_to else (date_from or date_to)

    top_y = y + h - pad - 7
    c.setFont('Helvetica-Bold', 7)
    c.drawString(x + pad, top_y, _fit_text(c, title, inner_w * 0.55, 'Helvetica-Bold', 7))
    c.setFont('Helvetica', 6)
    c.drawRightString(x + w - pad, top_y, _fit_text(c, date_range, inner_w * 0.45, 'Helvetica', 6))

    # Description (obv_rev), full-width under title
    obv = (coin['obv_rev'] or '').strip()
    desc_y = top_y - 8
    if obv:
        c.setFont('Helvetica', 6)
        c.drawString(x + pad, desc_y, _fit_text(c, obv, inner_w, 'Helvetica', 6))

    # Bottom row: coin_id (left), weight (right)
    bottom_y = y + pad
    if coin['coin_id']:
        c.setFont('Helvetica-Bold', 6)
        c.drawString(x + pad, bottom_y, coin['coin_id'])
    if coin['weight'] is not None:
        c.setFont('Helvetica', 6)
        c.drawRightString(x + w - pad, bottom_y, f'{coin["weight"]:.2f} g')

    # Middle area: image (left) + specs stack (right)
    mid_top = desc_y - 3
    mid_bottom = bottom_y + 8
    mid_h = mid_top - mid_bottom
    if mid_h < 10:
        return
    img_w = w * 0.5

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

    # Right-side specs: denomination, mint, metal (short), size
    specs = []
    if coin['denomination']: specs.append(coin['denomination'].strip())
    if coin['mint']: specs.append(coin['mint'].strip())
    m = _metal_short(coin['metal'])
    if m: specs.append(m)
    if coin['size'] is not None: specs.append(f"{coin['size']:.1f} mm")

    c.setFont('Helvetica', 6)
    spec_count = len(specs)
    if spec_count:
        step = min(8, mid_h / max(spec_count, 1))
        sy = mid_top - 6
        for s in specs:
            c.drawRightString(x + w - pad,
                              sy,
                              _fit_text(c, s, w * 0.5 - pad, 'Helvetica', 6))
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
            r = db.execute(f"UPDATE {t} SET status='Own' WHERE status='Owned'")
            if r.rowcount:
                per_table[t] = r.rowcount
            total += r.rowcount
    db.commit()
    return jsonify(updated=total, per_table=per_table)


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
                           vlists=VALUE_LISTS)


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


@app.route('/admin', methods=['GET'])
def admin_index():
    """Tiny browser-friendly index of one-shot maintenance actions.
    The action POSTs are still gated by IMPORT_MISSING_SECRET; the secret
    is just baked into the page's submit JS so the button works without
    extra typing. Cloudflare Access still gates the page itself in prod.
    """
    actions = [
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
            'label': "Coins: set every owner to 'Mark'",
            'desc':  "Sets owner='Mark' on every coin whose owner is NULL, "
                     "blank, or anything other than 'Mark'.",
            'url':   url_for('coins_owner_mark'),
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
    return referenced


def _norm(s):
    """Aggressive normalization for matching folder/identifier strings
    across the export ↔ sweep round trip. Lowercased, whitespace
    collapsed, filesystem-hostile chars stripped (mirrors _safe_path
    rules so an item written one way matches itself read back)."""
    bad = set('/\\:*?"<>|\n\r\t')
    s = ''.join(c for c in (s or '') if c not in bad)
    s = re.sub(r'\s+', ' ', s).strip(' .').lower()
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
        'ident': lambda r: ' '.join(filter(None, [
            str(_g(r, 'year')) if _g(r, 'year') else '',
            _g(r, 'model'),
            (f'Ref {_g(r, "reference")}') if _g(r, 'reference') else '',
        ])).strip() or (_g(r, 'brand'))[:40] or _g(r, 'id')[:8],
        'create': _create_watch,
        # User-titled docs (container_1, container_2) moved into the
        # JSON `documents` column; export walks them separately. Image
        # + receipt remain fixed columns.
        'files': [
            ('image_obv', 'Front', None),
            ('image_rev', 'Back', None),
            ('receipt',   'Receipt', None),
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
        'files': [('image', 'Image', None), ('receipt', 'Receipt', None)],
    },
    'lenses': {
        'group': lambda r: _g(r, 'make') or 'Unknown',
        'ident': lambda r: ' '.join(filter(None, [_g(r, 'model') or '', _g(r, 'serial_number') or ''])).strip() or _g(r, 'id')[:8],
        'create': _create_make_only,
        'files': [('image', 'Image', None), ('receipt', 'Receipt', None)],
    },
    'pens': {
        'group': lambda r: _g(r, 'make') or 'Unknown',
        'ident': lambda r: ' '.join(filter(None, [_g(r, 'model') or '', _g(r, 'serial_number') or ''])).strip() or _g(r, 'id')[:8],
        'create': _create_make_only,
        'files': [('image', 'Image', None), ('receipt', 'Receipt', None)],
    },
    'art': {
        'group': lambda r: _g(r, 'artist') or 'Unknown',
        'ident': lambda r: ' — '.join(filter(None, [
            _g(r, 'title') or '',
            str(_g(r, 'year')) if _g(r, 'year') else '',
        ])) or _g(r, 'id')[:8],
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
        'files': [('image', 'Image', None), ('receipt', 'Receipt', None)],
    },
    'rifles': {
        'group': lambda r: _g(r, 'make') or 'Unknown',
        'ident': lambda r: ' '.join(filter(None, [_g(r, 'model') or '', _g(r, 'serial_number') or ''])).strip() or _g(r, 'id')[:8],
        'create': _create_make_only,
        'files': [('image', 'Image', None), ('receipt', 'Receipt', None)],
    },
}

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

    import io
    import zipfile
    import csv as _csv

    db = get_db()
    buf = io.BytesIO()
    written = 0
    skipped_missing = 0
    seen_paths = set()
    # Track per-category rows so we can write one CSV per category at
    # the top of that category's folder once all files are processed.
    csv_rows = {}      # category → list[dict-like row]
    csv_columns = {}   # category → list[column name]

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

    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for cat, plan in EXPORT_LAYOUT.items():
            if cat not in allowed:
                continue
            table = CATEGORIES[cat]['table']
            try:
                rows = db.execute(f"SELECT * FROM {table}").fetchall()
            except sqlite3.OperationalError:
                continue
            cat_label = EXPORT_CATEGORY_LABELS.get(cat, cat.title())
            cols = {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}

            # Stash for the per-category CSV. Capture every column in
            # column-info order so the CSV is stable across exports.
            csv_columns[cat] = [r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()]
            csv_rows[cat] = [dict(r) for r in rows]

            for row in rows:
                ident_raw = plan['ident'](row)
                group_raw = plan['group'](row)
                group, ident = _safe_path(group_raw, ident_raw)

                # Owned vs. No longer Owned. Categories without a
                # status column → always treated as owned. status
                # null/blank → also treated as owned (default state for
                # records the user hasn't classified yet). Any other
                # value (Sold, Loaned, etc.) routes the row's files
                # under "No longer Owned" inside the category folder.
                status_val = ''
                if 'status' in cols:
                    try:
                        status_val = (row['status'] or '').strip()
                    except (KeyError, IndexError):
                        status_val = ''
                is_owned = (not status_val) or status_val.lower() in ('own', 'owned')
                cat_root = f'StuffFiles/{cat_label}' if is_owned \
                            else f'StuffFiles/{cat_label}/No longer Owned'

                for spec in plan['files']:
                    field, default_label, title_field = spec
                    if field not in cols:
                        continue
                    fname = (row[field] or '').strip()
                    if not fname:
                        continue
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

                # JSON documents columns — unbounded user-titled docs.
                # Walk every doc-set declared for this category (e.g.
                # persons has 'ids' + 'health'). Each entry exports as
                # "<ident> — <title>.<ext>" same as a fixed slot, so
                # the round-trip with sweep stays symmetric.
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

        # Per-category CSV at the top of each category's folder. Rows
        # in the same order as the table; columns straight from
        # PRAGMA table_info so the schema is faithfully captured.
        for cat, rows in csv_rows.items():
            if not rows:
                continue
            cat_label = EXPORT_CATEGORY_LABELS.get(cat, cat.title())
            cols = csv_columns[cat]
            sio = io.StringIO()
            w = _csv.writer(sio, quoting=_csv.QUOTE_MINIMAL)
            w.writerow(cols)
            for r in rows:
                w.writerow(['' if r.get(c) is None else r.get(c) for c in cols])
            zf.writestr(f'StuffFiles/{cat_label}/{cat_label}.csv',
                        sio.getvalue().encode('utf-8'))

    buf.seek(0)
    ts = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    fname = f'StuffFiles-{user["email"].split("@")[0]}-{ts}.zip'
    # Mark this user's Files export as fresh — the nav indicator turns
    # green once the zip is delivered. Any record edited after this
    # timestamp will flip the indicator back to red on the next page
    # load (see _files_export_stale + /files-status below).
    db.execute(
        'UPDATE users SET last_export_at = ? WHERE id = ?',
        (datetime.utcnow().isoformat(timespec='seconds'), user['id']),
    )
    db.commit()
    return send_file(buf, as_attachment=True, download_name=fname,
                     mimetype='application/zip')


def _files_export_stale(db, user, allowed):
    """True when at least one record in the user's allowed categories
    has been touched (updated_at) since the user's last successful
    /export-files run, OR when the export has never run for this user.
    Returns (stale, last_export_at, latest_update)."""
    last = (user['last_export_at'] if 'last_export_at' in user.keys() else None) or None
    latest = None
    for cat in allowed:
        info = CATEGORIES.get(cat)
        if not info:
            continue
        try:
            row = db.execute(
                f"SELECT MAX(updated_at) AS m FROM {info['table']}"
            ).fetchone()
        except sqlite3.OperationalError:
            continue
        m = row and row['m']
        if m and (latest is None or m > latest):
            latest = m
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
    can match incoming filenames cheaply."""
    plan = EXPORT_LAYOUT.get(category)
    if not plan:
        return []
    table = CATEGORIES[category]['table']
    try:
        rows = db.execute(f"SELECT * FROM {table}").fetchall()
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
    h1 = ParagraphStyle('h1', parent=styles['Heading1'], fontSize=16, spaceAfter=2)
    sub = ParagraphStyle('sub', parent=styles['Normal'], fontSize=10,
                         textColor=colors.grey, spaceAfter=10)
    cell_style = ParagraphStyle('cell', parent=styles['Normal'],
                                fontSize=9, leading=11)

    story = []
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

    # Field table — every populated, non-file field. Two columns
    # (label / value), repeated for compactness.
    rows_for_table = []
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
        rows_for_table.append((label, str(v)))

    if rows_for_table:
        # Two-column layout: label/value pairs flowing left-to-right.
        col_w = (doc.width / 2) - 4
        data = []
        for i in range(0, len(rows_for_table), 2):
            left = rows_for_table[i]
            right = rows_for_table[i + 1] if i + 1 < len(rows_for_table) else ('', '')
            data.append([
                Paragraph(f'<b>{left[0]}</b>', cell_style),
                Paragraph(left[1], cell_style),
                Paragraph(f'<b>{right[0]}</b>', cell_style) if right[0] else '',
                Paragraph(right[1], cell_style) if right[1] else '',
            ])
        tbl = Table(data, colWidths=[col_w * 0.35, col_w * 0.65, col_w * 0.35, col_w * 0.65])
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
    cat_hint = (request.form.get('category_hint') or '').strip()
    cat_hint_label = EXPORT_CATEGORY_LABELS.get(cat_hint) if cat_hint else None
    group_hint = (request.form.get('group_hint') or '').strip()
    auto_create = request.form.get('auto_create') == '1'

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

            parsed = _parse_sweep_path(rel)
            if not parsed:
                report['skipped'].append({'file': rel, 'reason': 'unparsable path (need StuffFiles/<Category>/<Group>/<file> shape, or pick a category)'})
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

            # Find rows whose (group, ident) match. ident match is exact
            # after normalization; if no exact match, fall back to a prefix
            # match so partial idents still land.
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
                create_fn = plan.get('create')
                if auto_create and create_fn:
                    seed = create_fn(parsed['group'], parsed['ident']) or {}
                    if seed:
                        new_id = str(uuid.uuid4())
                        seed['id'] = new_id
                        seed['created_at'] = now
                        seed['updated_at'] = now
                        # Owner default for the freshly-created record.
                        # Coins always seed Mark; otherwise members get
                        # 'YM', owners get the per-category canonical
                        # default.
                        if 'owner' not in seed:
                            if cat == 'coins':
                                seed['owner'] = 'Mark'
                            elif user.get('role') != 'owner':
                                seed['owner'] = 'YM'
                            else:
                                d = DEFAULT_OWNER_BY_CATEGORY.get(cat)
                                if d:
                                    seed['owner'] = d
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
                            f"SELECT * FROM {table} WHERE id = ?", [new_id]
                        ).fetchone())
                        g_norm = _norm(plan['group'](new_row))
                        i_norm = _norm(plan['ident'](new_row))
                        indexes[cat].append((g_norm, i_norm, new_row))
                        matches = [(g_norm, i_norm, new_row)]
                        report['uploaded'].append({
                            'file':   rel,
                            'record': f"{cat}/{new_id[:8]} (CREATED)",
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
            table = CATEGORIES[cat]['table']
            cols = {r['name'] for r in db.execute(f"PRAGMA table_info({table})").fetchall()}

            # Resolve the slot. Try label match first.
            chosen_field = None
            for spec in plan['files']:
                field, default_label, title_field = spec
                if field not in cols:
                    continue
                label_candidates = [default_label]
                if title_field and title_field in cols:
                    t = (row[title_field] or '').strip()
                    if t:
                        label_candidates.append(t)
                if any(_norm(c) == target_label for c in label_candidates):
                    # Only use this slot if it's currently empty.
                    if not (row[field] or '').strip():
                        chosen_field = field
                        break
            # For DOCUMENTS_CATEGORIES, never fall through to "first
            # empty slot" — the documents JSON column is unbounded so
            # every file that didn't match a named slot becomes a new
            # entry in there. Categories with only fixed slots keep
            # the original behavior.
            if not chosen_field and cat not in DOCUMENTS_CATEGORIES:
                # Label match failed (or matched-but-occupied) — find the
                # first empty slot in declaration order.
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
                docs.append({
                    'title':    (parsed.get('label') or '').strip(),
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
    ('Watch', 'ImageObv'):        ('watches',      'image_obv'),
    ('Watch', 'ImageRev'):        ('watches',      'image_rev'),
    ('Watch', 'Receipt'):         ('watches',      'receipt'),
    ('Watch', 'Document'):        ('watches',      'document'),
    ('Coin', 'Image1'):           ('coins',        'image_1'),
    ('Coin', 'Image2'):           ('coins',        'image_2'),
    ('Coin', 'Receipt'):          ('coins',        'receipt'),
    ('Coin', 'Document1'):        ('coins',        'document_1'),
    ('Coin', 'Document2'):        ('coins',        'document_2'),
    ('Camera', 'Image'):          ('cameras',      'image'),
    ('Lens', 'Image'):            ('lenses',       'image'),
    ('Pen', 'Image'):             ('pens',         'image'),
    ('Pen', 'Receipt'):           ('pens',         'receipt'),
    ('Art', 'Image'):             ('art',          'image'),
    ('Art', 'Receipt'):           ('art',          'receipt'),
    ('Vehicle', 'Image'):         ('vehicles',     'image'),
    ('Vehicle', 'Registration'):  ('vehicles',     'registration'),
    ('Vehicle', 'Insurance'):     ('vehicles',     'insurance'),
    ('Vehicle', 'Invoice'):       ('vehicles',     'invoice'),
    ('Recording', 'Image'):       ('recordings',   'image'),
    ('Recording', 'Receipt'):     ('recordings',   'receipt'),
    ('Rifle', 'Image'):           ('rifles',       'image'),
    ('Rifle', 'Receipt'):         ('rifles',       'receipt'),
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
