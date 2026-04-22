import sqlite3
import uuid
import os
import json
import re
import base64
from datetime import datetime
from flask import (Flask, g, render_template, request, redirect, url_for,
                   flash, send_from_directory, abort, jsonify, Response)
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
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'tif', 'tiff'}

# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------

CATEGORIES = {
    'watches': {
        'name': 'Watches', 'icon': '⌚', 'table': 'watches',
        'label_field': 'brand', 'sublabel_field': 'model', 'image_field': 'image_obv',
    },
    'coins': {
        'name': 'Coins', 'icon': '🪙', 'table': 'coins',
        'label_field': 'authority', 'sublabel_field': 'denomination', 'image_field': 'image_1',
    },
    'cameras': {
        'name': 'Cameras', 'icon': '📷', 'table': 'cameras',
        'label_field': 'make', 'sublabel_field': 'model', 'image_field': 'image',
    },
    'lenses': {
        'name': 'Lenses', 'icon': '🔘', 'table': 'lenses',
        'label_field': 'make', 'sublabel_field': 'model', 'image_field': 'image',
    },
    'pens': {
        'name': 'Pens', 'icon': '✒️', 'table': 'pens',
        'label_field': 'make', 'sublabel_field': 'model', 'image_field': 'image',
    },
    'art': {
        'name': 'Art', 'icon': '🎨', 'table': 'art',
        'label_field': 'artist', 'sublabel_field': 'title', 'image_field': 'image',
    },
    'vehicles': {
        'name': 'Vehicles', 'icon': '🚗', 'table': 'vehicles',
        'label_field': 'make', 'sublabel_field': 'model', 'image_field': 'image',
    },
    'recordings': {
        'name': 'Music', 'icon': '🎵', 'table': 'recordings',
        'label_field': 'artist', 'sublabel_field': 'title', 'image_field': 'image',
    },
    'audio': {
        'name': 'Audio', 'icon': '🔊', 'table': 'audio',
        'label_field': 'make', 'sublabel_field': 'model', 'image_field': 'image',
    },
    'rifles': {
        'name': 'Rifles', 'icon': '🔫', 'table': 'rifles',
        'label_field': 'make', 'sublabel_field': 'model', 'image_field': 'image',
    },
    'credit_cards': {
        'name': 'Credit Cards', 'icon': '💳', 'table': 'credit_cards',
        'label_field': 'name', 'sublabel_field': 'number', 'image_field': 'image_front',
    },
    'properties': {
        'name': 'Properties', 'icon': '🏠', 'table': 'properties',
        'label_field': 'name', 'sublabel_field': 'address', 'image_field': 'image',
    },
    'persons': {
        'name': 'People', 'icon': '👤', 'table': 'persons',
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
        'Carp','Carpinteria','NYC','SF','Truckee',
        '770 Ladera','Paris','Paris Saint-Guillaume',
        'Ghent: Pond House','Ghent: Glass House',
        'Ghent: Rec Center','Ghent: Rec Center/Arena','Ghent: Harlemville',
        'Dolby Chadwick','Storage','Archived','Missing','Gifted',
    ],
    'status': ['Own','Ordered','Sold','Loaned','Gifted','Consigned','Lost'],
    'camera_status': ['Own','Sold','Gifted'],
    'coin_status': ['Own','Ordered','Sold','Loaned'],
    'recording_status': ['Own','Ordered'],
    'metal_coin': ['AE Bronze','AE Copper','AL Aluminium','AR Silver','AV Gold','BL Billon','EL Electrum','NI Nickel'],
    'coin_grade': ['BU','FDC','MS','PF','AU','cEF','EF','aEF','cVF','VF+','VF','aVF','gVF'],
    'clasp_type': ['Tang','Fold Over','Butterfly','Buckle','Velcro'],
    'pen_type': ['Ballpoint','Fountain','Rollerball','Mechanical Pencil'],
    'pen_action': ['Cap','Click','Twist'],
    'pen_cartridge': ['Proprietary','Standard International'],
    'pen_reservoir': ['Cartridge','Converter','Piston','Vacuum'],
    'recording_type': ['Vinyl','CD','SACD','Tape'],
    'recording_genre': ['Classical','Jazz','Rock','Pop','Blues','Folk','Electronic','World'],
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
    },
    ('watches', 'strap_material'): {
        'alligator': 'Croc',
        'aligator':  'Croc',   # common misspelling
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
        {'name': 'image_obv',       'label': 'Image (Obverse)',   'type': 'file'},
        {'name': 'image_rev',       'label': 'Image (Reverse)',   'type': 'file'},
        {'name': 'receipt',         'label': 'Receipt',           'type': 'file'},
        {'name': 'document',        'label': 'Document',          'type': 'file'},
    ],
    'coins': [
        {'name': 'coin_id',         'label': 'Coin ID',           'type': 'text', 'readonly': True},
        {'name': 'authority',       'label': 'Authority',         'type': 'text'},
        {'name': 'region',          'label': 'Region',            'type': 'text'},
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
        {'name': 'grade',           'label': 'Grade',             'type': 'text'},
        {'name': 'die_axis',        'label': 'Die Axis',          'type': 'text'},
        {'name': 'strike',          'label': 'Strike',            'type': 'number'},
        {'name': 'surface',         'label': 'Surface',           'type': 'number'},
        {'name': 'weight',          'label': 'Weight (g)',        'type': 'number'},
        {'name': 'size',            'label': 'Size (mm)',         'type': 'number'},
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
        {'name': 'lens_mount',      'label': 'Lens Mount',        'type': 'text'},
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
        {'name': 'image',           'label': 'Image',             'type': 'file'},
    ],
    'lenses': [
        {'name': 'make',            'label': 'Make',              'type': 'text'},
        {'name': 'model',           'label': 'Model',             'type': 'text'},
        {'name': 'mount',           'label': 'Mount',             'type': 'text'},
        {'name': 'aperture',        'label': 'Aperture (f/)',     'type': 'number'},
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
        {'name': 'image',           'label': 'Image',             'type': 'file'},
    ],
    'pens': [
        {'name': 'make',            'label': 'Make',              'type': 'text'},
        {'name': 'model',           'label': 'Model',             'type': 'text'},
        {'name': 'type',            'label': 'Type',              'type': 'text'},
        {'name': 'action',          'label': 'Action',            'type': 'text'},
        {'name': 'nib',             'label': 'Nib',               'type': 'text'},
        {'name': 'cartridge',       'label': 'Cartridge',         'type': 'text'},
        {'name': 'reservoir',       'label': 'Reservoir',         'type': 'text'},
        {'name': 'date',            'label': 'Purchase Date',     'type': 'date'},
        {'name': 'price',           'label': 'Price',             'type': 'number'},
        {'name': 'vendor',          'label': 'Vendor',            'type': 'text'},
        {'name': 'notes',           'label': 'Notes',             'type': 'textarea'},
        {'name': 'owner',           'label': 'Owner',             'type': 'text'},
        {'name': 'property',        'label': 'Property',          'type': 'text'},
        {'name': 'status',          'label': 'Status',            'type': 'select',
         'options': ['', 'Own', 'Sold', 'Loaned']},
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
        {'name': 'notes',           'label': 'Notes',             'type': 'textarea'},
        {'name': 'owner',           'label': 'Owner',             'type': 'text'},
        {'name': 'location',        'label': 'Location',          'type': 'text'},
        {'name': 'property',        'label': 'Property',          'type': 'text'},
        {'name': 'status',          'label': 'Status',            'type': 'select',
         'options': ['', 'Own', 'Sold', 'Loaned']},
        {'name': 'image',           'label': 'Image',             'type': 'file'},
        {'name': 'receipt',         'label': 'Receipt',           'type': 'file'},
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
        {'name': 'image',           'label': 'Image',             'type': 'file'},
        {'name': 'insurance',       'label': 'Insurance',         'type': 'file'},
        {'name': 'invoice',         'label': 'Invoice',           'type': 'file'},
        {'name': 'registration',    'label': 'Registration',      'type': 'file'},
    ],
    'recordings': [
        {'name': 'title',           'label': 'Title',             'type': 'text'},
        {'name': 'artist',          'label': 'Artist',            'type': 'text'},
        {'name': 'type',            'label': 'Type',              'type': 'select',
         'options': ['', 'LP', '45', '78', 'EP', 'CD', 'Cassette', '8-Track', 'Reel', 'Digital', 'Other']},
        {'name': 'genre',           'label': 'Genre',             'type': 'text'},
        {'name': 'genre_2',         'label': 'Genre 2',           'type': 'text'},
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
        {'name': 'alarm_company',   'label': 'Alarm Company',     'type': 'text'},
        {'name': 'alarm_account',   'label': 'Alarm Account',     'type': 'text'},
        {'name': 'alarm_code_1',    'label': 'Alarm Code',        'type': 'text'},
        {'name': 'alarm_password',  'label': 'Alarm Password',    'type': 'text'},
        {'name': 'alarm_phone',     'label': 'Alarm Phone',       'type': 'text'},
        {'name': 'alarm_notes',     'label': 'Alarm Notes',       'type': 'textarea'},
        {'name': 'date',            'label': 'Purchase Date',     'type': 'date'},
        {'name': 'price',           'label': 'Price',             'type': 'number'},
        {'name': 'notes',           'label': 'Notes',             'type': 'textarea'},
        {'name': 'status',          'label': 'Status',            'type': 'select',
         'options': ['', 'Own', 'Sold']},
        {'name': 'owner',           'label': 'Owner',             'type': 'select',
         'options': ['', 'YM', 'Mark', 'Young']},
        {'name': 'archive',         'label': 'Archive',           'type': 'text'},
        {'name': 'image',           'label': 'Image',             'type': 'file'},
    ],
    'persons': [
        {'name': 'name',                  'label': 'Name',                   'type': 'text'},
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
        {'name': 'owner',                 'label': 'Owner',                  'type': 'text'},
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
        {'name': 'passport',              'label': 'Passport',               'type': 'file'},
        {'name': 'medicare',              'label': 'Medicare Card',          'type': 'file'},
        {'name': 'health_card_obv',       'label': 'Health Card (Front)',    'type': 'file'},
        {'name': 'health_card_rev',       'label': 'Health Card (Back)',     'type': 'file'},
        {'name': 'global_entry',          'label': 'Global Entry',           'type': 'file'},
        {'name': 'eye_prescription',      'label': 'Eye Prescription',       'type': 'file'},
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
    'persons':      ['phone', 'birth_date', 'blood_type', 'spouse', 'owner'],
}

# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
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
        'ALTER TABLE properties ADD COLUMN owner TEXT',
        'ALTER TABLE properties ADD COLUMN wifi_name TEXT',
        'ALTER TABLE topics ADD COLUMN image TEXT',
        'ALTER TABLE coins ADD COLUMN history_region TEXT',
        'ALTER TABLE coins ADD COLUMN history_authority TEXT',
        'ALTER TABLE coins ADD COLUMN history_searched_at TEXT',
    ):
        try:
            db.execute(stmt)
        except sqlite3.OperationalError:
            pass
    db.commit()


def get_counts():
    db = get_db()
    counts = {}
    for slug, cat in CATEGORIES.items():
        row = db.execute(f"SELECT COUNT(*) as c FROM {cat['table']}").fetchone()
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


def save_upload(file_obj):
    """Save an uploaded file and return the stored filename."""
    if not file_obj or file_obj.filename == '':
        return None
    if allowed_file(file_obj.filename):
        ext = file_obj.filename.rsplit('.', 1)[1].lower()
        stored_name = f"{uuid.uuid4().hex}.{ext}"
        file_obj.save(os.path.join(UPLOAD_FOLDER, stored_name))
        return stored_name
    return None


def get_file_fields(category):
    return [f['name'] for f in FIELDS[category] if f['type'] == 'file']


EXCLUDED_STATUSES = ('Own', 'Sold', 'Gifted', 'Own')  # dot filter excludes these

CATEGORY_FILTERS = {
    'coins': {
        'ca_ancient': ("date_1 < 1000 AND property_name IN ('Carp','Carpinteria')", []),
        'ny_ancient': ("date_1 < 1000 AND property_name = 'NYC'", []),
    },
    'audio': {
        'carp':   ("property = 'Carpinteria'", []),
        'martis': ("property = 'Truckee'", []),
    },
    'recordings': {
        'carp':   ("property = 'Carpinteria'", []),
        'martis': ("property = 'Truckee'", []),
    },
    # status/type comparisons are case- and whitespace-insensitive so data
    # imported with inconsistent casing (e.g. 'commercial' vs 'Commercial')
    # still matches.
    'vehicles': {
        'own':  ("LOWER(TRIM(COALESCE(status,''))) = 'own'", []),
        'sold': ("LOWER(TRIM(COALESCE(status,''))) = 'sold'", []),
    },
    'cameras': {
        'own':   ("LOWER(TRIM(COALESCE(status,''))) = 'own'",  []),
        'other': ("LOWER(TRIM(COALESCE(status,''))) <> 'own'", []),
    },
    'lenses': {
        'own':   ("LOWER(TRIM(COALESCE(status,''))) = 'own'",  []),
        'other': ("LOWER(TRIM(COALESCE(status,''))) <> 'own'", []),
    },
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


def build_search_query(category, q, dot=False, coin_filter=None):
    """Build a SELECT with optional text search and/or dot (unresolved) filter."""
    table = CATEGORIES[category]['table']
    text_fields = [f['name'] for f in FIELDS[category]
                   if f['type'] in ('text', 'textarea', 'select') and f.get('type') != 'file']

    wheres, params = [], []

    if q and text_fields:
        # Split the query on whitespace and AND the terms together: each
        # term must match at least one text field. "Breguet Carp" finds
        # watches where 'Breguet' appears in any text field AND 'Carp'
        # appears in any text field — so brand+property combos work.
        terms = [t for t in q.split() if t.strip()]
        for term in terms:
            conditions = ' OR '.join([f"{col} LIKE ?" for col in text_fields])
            wheres.append(f"({conditions})")
            params += [f'%{term}%'] * len(text_fields)

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

    where_clause = f"WHERE {' AND '.join(wheres)}" if wheres else ''
    order_by = CATEGORY_ORDER_BY.get(category, 'created_at DESC')
    return f"SELECT * FROM {table} {where_clause} ORDER BY {order_by}", params


CATEGORY_ORDER_BY = {
    'coins': ("COALESCE(NULLIF(region, ''), 'zzz') ASC, "
              "COALESCE(NULLIF(authority, ''), 'zzz') ASC, "
              "COALESCE(date_1, 99999) ASC"),
    'watches': ("COALESCE(NULLIF(brand, ''), 'zzz'), "
                "COALESCE(NULLIF(description, ''), 'zzz')"),
    'vehicles': ("COALESCE(NULLIF(make, ''), 'zzz'), "
                 "COALESCE(NULLIF(model, ''), 'zzz')"),
    # Residential first, then Commercial, everything else last.
    # Alphabetical within each group (case-insensitive).
    'properties': ("CASE COALESCE(type,'') "
                   "WHEN 'Residential' THEN 0 "
                   "WHEN 'Commercial'  THEN 1 "
                   "ELSE 2 END, "
                   "LOWER(COALESCE(name,''))"),
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

    client = anthropic.Anthropic(api_key=api_key)

    import time as _time
    last_err = None
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
        except anthropic.RateLimitError as e:
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
        raise RuntimeError(f'Rate limited after retries: {last_err}')

    text = ''
    for block in resp.content:
        if getattr(block, 'type', None) == 'text':
            text += block.text
    text = text.strip()

    m = re.search(r'\{.*\}', text, re.DOTALL)
    if not m:
        raise RuntimeError(f'Could not parse JSON from model output: {text[:200]}')
    return json.loads(m.group(0))


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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return redirect(url_for('list_view', category='watches'))


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
    # Default filters apply on a fresh visit (no explicit ?filter= and no
    # search query). An active search bypasses the default so users don't
    # have to click Other / clear filter just to find a sold/loaned item.
    # An explicit empty ?filter= still clears all filters.
    if not q:
        if category == 'properties' and raw_filter is None:
            coin_filter = 'own_residential'
        if category == 'vehicles' and raw_filter is None:
            coin_filter = 'own'
        if category in ('cameras', 'lenses') and raw_filter is None:
            coin_filter = 'own'
    sql, params = build_search_query(category, q, dot=dot, coin_filter=coin_filter)
    rows = db.execute(sql, params).fetchall()
    counts = get_counts()
    cat_info = CATEGORIES[category]
    extra_fields = LIST_EXTRA_FIELDS.get(category, [])
    # Split the compound properties filter into its two axes for the template.
    prop_status, prop_type = _split_property_filter(coin_filter) \
        if category == 'properties' else (None, None)
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
                           prop_status=prop_status,
                           prop_type=prop_type,
                           result_count=len(rows),
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

        for field in FIELDS[category]:
            fname = field['name']
            if field.get('readonly'):
                continue
            if field['type'] == 'file':
                f = request.files.get(fname)
                stored = save_upload(f)
                if stored:
                    data[fname] = stored
                else:
                    data[fname] = None
            elif field['type'] == 'checkbox-group':
                checked = request.form.getlist(fname)
                data[fname] = ','.join(checked)
            else:
                val = request.form.get(fname, '').strip()
                if field['type'] == 'number' or fname in ('price', 'beat', 'reserve', 'value'):
                    val = val.replace('$', '').replace(',', '').strip()
                data[fname] = val if val else None

        # Auto coin_id
        if category == 'coins':
            data['coin_id'] = next_coin_id(db)

        cols = ', '.join(data.keys())
        placeholders = ', '.join(['?' for _ in data])
        db.execute(f"INSERT INTO {CATEGORIES[category]['table']} ({cols}) VALUES ({placeholders})",
                   list(data.values()))
        db.commit()
        flash(f"Record created successfully.", 'success')
        return redirect(url_for('detail_view', category=category, record_id=record_id))

    # GET - blank form
    return render_template('detail.html',
                           category=category,
                           cat_info=cat_info,
                           record=None,
                           counts=counts,
                           current_category=category,
                           categories=CATEGORIES,
                           fields=FIELDS[category],
                           is_new=True,
                           prev_id=None,
                           next_id=None,
                           hertz=None,
                           coin_age_val=None,
                           complications_options=COMPLICATIONS_OPTIONS,
                           vlists=VALUE_LISTS,
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

    # Prev/Next navigation
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

        set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
        db.execute(f"UPDATE {table} SET {set_clause} WHERE id = ?",
                   list(updates.values()) + [record_id])
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

    # Camera detail: list every lens with the same mount and property,
    # so the user can see the full kit available at that location.
    camera_compatible_lenses = None
    if category == 'cameras' and record['lens_mount'] and record['property']:
        camera_compatible_lenses = db.execute(
            "SELECT id, make, model, aperture, length, image FROM lenses "
            "WHERE LOWER(TRIM(COALESCE(mount,''))) = LOWER(TRIM(?)) "
            "  AND LOWER(TRIM(COALESCE(property,''))) = LOWER(TRIM(?)) "
            "ORDER BY LOWER(COALESCE(make,'')), "
            "         CAST(COALESCE(length,0) AS REAL)",
            [record['lens_mount'], record['property']],
        ).fetchall()

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
                           service_overdue=service_overdue,
                           service_years=service_years,
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

    field = valid_fields[field_name]
    if field.get('readonly') or field['type'] == 'file':
        return jsonify({'error': 'Field not auto-saveable'}), 400

    # Strip currency/comma formatting for numeric fields
    if field['type'] == 'number' or field_name in ('price', 'beat', 'reserve', 'value'):
        value = str(value).replace('$', '').replace(',', '').strip()

    value = normalize_field_value(table, field_name, str(value).strip() if value else '')

    now = datetime.utcnow().isoformat()
    db.execute(f"UPDATE {table} SET {field_name} = ?, updated_at = ? WHERE id = ?",
               [value if value != '' else None, now, record_id])
    db.commit()
    return jsonify({'ok': True})


@app.route('/<category>/<record_id>/delete', methods=['POST'])
def delete_record(category, record_id):
    if category not in CATEGORIES:
        abort(404)
    db = get_db()
    table = CATEGORIES[category]['table']
    db.execute(f"DELETE FROM {table} WHERE id = ?", [record_id])
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
    db.execute(
        "UPDATE watches SET value = ?, results = ?, value_searched_at = ?, "
        "updated_at = ? WHERE id = ?",
        (data['value'], data['results'], now, now, record_id),
    )
    db.commit()
    return jsonify({**data, 'searched_at': now})


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
# entry is authoritative over a web guess.
WATCH_LOOKUP_BLANK_ONLY = {'year'}

# Fields that should append to existing content rather than replace it.
# For notes the lookup writes a quality blurb about the reference;
# merging it onto the user's own notes (separated by a blank line)
# preserves their wording while still surfacing the web research.
WATCH_LOOKUP_APPEND = {'notes'}


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
            if not new_text or new_text in cur_text:
                continue
            merged = cur_text + '\n\n' + new_text
            overwritten[f] = {'current': current, 'new': merged}
            continue
        # For clasp_type, don't mark changes that are just verbose variants.
        if f == 'clasp_type' and _clasp_equivalent(current, val):
            continue
        if str(current).strip() != str(val).strip():
            overwritten[f] = {'current': current, 'new': val}

    # Combined update map — apply both blank-fills and overwrites.
    updates = {}
    for k, v in filled.items():
        updates[k] = v
    for k, info in overwritten.items():
        updates[k] = info['new']

    # Return the proposed changes WITHOUT applying. The client presents
    # a checkbox review; accepted items are POSTed to /apply-lookup.
    return jsonify({
        'filled': filled,
        'overwritten': overwritten,
        'sources': suggestions.get('sources', ''),
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
    db.commit()

    return jsonify({'url': url_for('uploaded_file', filename=stored)})


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
        bullet = line[:1] in ('-', '*', '•')
        if bullet:
            if not in_list:
                out.append('<ul class="results-list">')
                in_list = True
            out.append(f'<li>{_inline(line[1:].strip())}</li>')
        else:
            if in_list:
                out.append('</ul>')
                in_list = False
            out.append(f'<p>{_inline(line)}</p>')
    if in_list:
        out.append('</ul>')
    return Markup(''.join(out))


@app.template_filter('is_image')
def is_image_filter(filename):
    if not filename:
        return False
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    return ext in ('png', 'jpg', 'jpeg', 'gif', 'webp', 'tif', 'tiff')


@app.context_processor
def inject_globals():
    return {'CATEGORIES': CATEGORIES, 'now': datetime.utcnow()}


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
        c.drawRightString(x + w - pad, bottom_y, f'{coin["weight"]:g} g')

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
    if coin['size'] is not None: specs.append(f"{coin['size']:g} mm")

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
