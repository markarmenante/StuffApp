import sqlite3
import uuid
import os
from datetime import datetime
from flask import (Flask, g, render_template, request, redirect, url_for,
                   flash, send_from_directory, abort, jsonify)
from werkzeug.utils import secure_filename

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
    'owner': ['Mark','Young'],
    'property': ['Carp','NYC','SF','Truckee'],
    'status': ['Owned','Sold','Loaned'],
    'coin_status': ['Owned','Sold','Loaned'],
    'metal_coin': ['AE Bronze','AE Copper','AL Aluminium','AR Silver','AV Gold','BL Billon','EL Electrum','NI Nickel'],
    'coin_grade': ['BU','FDC','MS','PF','AU','cEF','EF','aEF','cVF','VF+','VF','aVF','gVF'],
    'clasp_type': ['Tang','Deployant','Buckle','Velcro'],
    'pen_type': ['Ballpoint','Fountain','Rollerball','Mechanical Pencil'],
    'pen_action': ['Cap','Click','Twist'],
    'pen_cartridge': ['Proprietary','Standard International'],
    'pen_reservoir': ['Cartridge','Converter','Piston','Vacuum'],
    'recording_type': ['LP','CD','SACD','Digital','Cassette','Reel'],
    'recording_genre': ['Classical','Jazz','Rock','Pop','Blues','Folk','Electronic','World'],
    'property_type': ['Residential','Commercial','Land'],
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
        {'name': 'description',     'label': 'Description',       'type': 'textarea'},
        {'name': 'notes',           'label': 'Notes',             'type': 'textarea'},
        {'name': 'owner',           'label': 'Owner',             'type': 'text'},
        {'name': 'property',        'label': 'Property',          'type': 'text'},
        {'name': 'status',          'label': 'Status',            'type': 'select',
         'options': ['', 'Owned', 'Sold', 'Loaned']},
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
         'options': ['', 'Owned', 'Sold', 'Loaned']},
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
         'options': ['', 'Owned', 'Sold', 'Loaned']},
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
         'options': ['', 'Owned', 'Sold', 'Loaned']},
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
         'options': ['', 'Owned', 'Sold', 'Loaned']},
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
         'options': ['', 'Owned', 'Sold', 'Loaned']},
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
         'options': ['', 'Owned', 'Sold', 'Loaned']},
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
         'options': ['', 'Owned', 'Sold', 'Loaned']},
        {'name': 'image',           'label': 'Cover Image',       'type': 'file'},
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
         'options': ['', 'Owned', 'Sold', 'Loaned']},
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
         'options': ['', 'Owned', 'Sold', 'Rented']},
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
    'art':          ('artist', 'medium', 'vendor'),
    'cameras':      ('make', 'vendor'),
    'lenses':       ('make', 'mount', 'vendor'),
    'pens':         ('make', 'vendor'),
    'vehicles':     ('make', 'vendor'),
    'recordings':   ('artist', 'genre', 'vendor'),
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


EXCLUDED_STATUSES = ('Owned', 'Sold', 'Gifted', 'Own')  # dot filter excludes these

def build_search_query(category, q, dot=False):
    """Build a SELECT with optional text search and/or dot (unresolved) filter."""
    table = CATEGORIES[category]['table']
    text_fields = [f['name'] for f in FIELDS[category]
                   if f['type'] in ('text', 'textarea', 'select') and f.get('type') != 'file']

    wheres, params = [], []

    if q and text_fields:
        conditions = ' OR '.join([f"{col} LIKE ?" for col in text_fields])
        wheres.append(f"({conditions})")
        params += [f'%{q}%'] * len(text_fields)

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

    where_clause = f"WHERE {' AND '.join(wheres)}" if wheres else ''
    return f"SELECT * FROM {table} {where_clause} ORDER BY created_at DESC", params


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
    q   = request.args.get('q', '').strip()
    dot = request.args.get('dot', '') == '1'
    sql, params = build_search_query(category, q, dot=dot)
    rows = db.execute(sql, params).fetchall()
    counts = get_counts()
    cat_info = CATEGORIES[category]
    extra_fields = LIST_EXTRA_FIELDS.get(category, [])
    return render_template('list.html',
                           category=category,
                           cat_info=cat_info,
                           rows=rows,
                           counts=counts,
                           current_category=category,
                           categories=CATEGORIES,
                           q=q,
                           dot=dot,
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
                if field['type'] == 'number' or fname in ('price', 'beat', 'reserve'):
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
                if field['type'] == 'number' or fname in ('price', 'beat', 'reserve'):
                    val = val.replace('$', '').replace(',', '').strip()
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

    service_overdue = False
    if category == 'watches' and record['service_date']:
        try:
            from datetime import date as _date
            num_comp = len([c for c in (record['complications'] or '').split(',') if c.strip()])
            threshold = 10 if num_comp > 5 else 15
            svc = datetime.strptime(record['service_date'], '%Y-%m-%d').date()
            service_overdue = (_date.today() - svc).days / 365.25 > threshold
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
                           service_overdue=service_overdue,
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
    if field['type'] == 'number' or field_name in ('price', 'beat', 'reserve'):
        value = str(value).replace('$', '').replace(',', '').strip()

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


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


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
# Temporary art import (remove after upload)
# ---------------------------------------------------------------------------

IMPORT_ART_SECRET = 'stuffapp-art-import-2026'

ART_COLS = (
    'id', 'title', 'artist', 'year', 'medium', 'dimensions', 'date',
    'price', 'vendor', 'notes', 'owner', 'location', 'property', 'status',
    'image', 'receipt', 'created_at', 'updated_at',
)

@app.route('/admin/import-art', methods=['POST'])
def import_art_table():
    if request.form.get('secret') != IMPORT_ART_SECRET:
        abort(403)
    f = request.files.get('db')
    if not f:
        return jsonify(error='no db file'), 400
    tmp_path = os.path.join(DATA_DIR, '_import_tmp.db')
    try:
        f.save(tmp_path)
        src = sqlite3.connect(tmp_path)
        src.row_factory = sqlite3.Row
        rows = src.execute(f"SELECT {', '.join(ART_COLS)} FROM art").fetchall()
        src.close()

        db = get_db()
        db.execute('DELETE FROM art')
        placeholders = ', '.join(['?'] * len(ART_COLS))
        db.executemany(
            f"INSERT INTO art ({', '.join(ART_COLS)}) VALUES ({placeholders})",
            [tuple(r[c] for c in ART_COLS) for r in rows],
        )
        db.commit()
        n = db.execute('SELECT COUNT(*) FROM art').fetchone()[0]
    except Exception as e:
        return jsonify(error=str(e)), 500
    finally:
        try: os.remove(tmp_path)
        except OSError: pass
    return jsonify(ok=True, art_rows=n)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

with app.app_context():
    init_db()

if __name__ == '__main__':
    app.run(debug=True, port=5001)
