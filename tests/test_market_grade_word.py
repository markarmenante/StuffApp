"""Market Scan: the dealer's own grade word is read off a VCoins listing
(Mark, 2026-09-20: the Schmidt Knidos drachm showed 'grade not stated'
while its page said 'Toned EF')."""
import os, sys, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-grade-')
os.environ['ANTHROPIC_API_KEY'] = 'test-key'

import app as stuffapp

SCHMIDT = ("Knidos, Caria. c. 480-449 BC, AR Drachm, 6.19g (16mm, 9h). Forepart of roaring lion "
           "right / Square incuse within which the head of Aphrodite r. of fine archaic style, hair "
           "curling upwards beneath sphendone. Pedigree: Reportedly a private purchase from Tom "
           "Cederlind at Denver coin show on March 16, 2016 References: BM 17-19. SNG 4833 Grade: "
           "Lovely toned surfaces and high relief. The obverse lion is abutted against the right side "
           "of flan; so a bit tight. Toned EF Price: $7,500 gk1902 Around 350 BCE, the sculptor "
           "Praxiteles carved an Aphrodite.")
g = stuffapp._market_grade_from_text
assert g(SCHMIDT) == 'Toned EF', g(SCHMIDT)
assert g('Grade: EF, the obverse a little soft. Price: $900') == 'EF'
assert g('Grade: Good VF. Reference: SNG Cop 12') == 'Good VF'
assert g('Grade: Fine. Price: $120') == 'Fine'
assert g('Grade: Very Good, worn. Price: $60') == 'Very Good'
assert g('Head of Apollo of fine archaic style. 3.4g. Price: $400') == ''      # style, not condition
assert g('Miletos AR obol, gVF, attractive. 1.1g') == 'gVF'
assert g('Corinth stater, About EF with a fine reverse. 8.5g') == 'About EF'
assert g('NGC Ch XF 5/5 4/5, ex NAC 100. Strike 5/5') == 'Ch XF'
assert g('Kyzikos EL hekte, AU stater style, EF/VF, 2.6g') == 'EF/VF'
assert g('Lampsakos AU stater, 8.4 g, lovely') == ''                            # AU is the metal
assert g('') == ''

strip = stuffapp._market_strip_no_grade
assert strip('Fills the named Knidos gap with a Cederlind-sourced early classical drachm; card states no numeric or word grade.') \
    == 'Fills the named Knidos gap with a Cederlind-sourced early classical drachm.'
assert strip('$7,500 is a strong price for an ungraded drachm — value rests on the named-dealer pedigree rather than a stated condition.') == ''
assert strip('Rare type; priced above the archive median.') == 'Rare type; priced above the archive median.'

# The stage: the model left grade empty though the card's description was read.
card = {'store': 'Shanna Schmidt Numismatics Inc.', 'title': 'Knidos, Caria. c. 480-449 BC, AR Drachm',
        'price': 'US$ 7,500.00', 'listing_url': 'https://www.vcoins.com/en/stores/shanna_schmidt_numismatics_inc/x/gk1902',
        'description': SCHMIDT, 'grade_hint': stuffapp._market_grade_from_text(SCHMIDT)}
it = {'grade': '', 'grade_numeric': None,
      'why': 'Fills the named Knidos gap with a Cederlind-sourced early classical drachm; card states no numeric or word grade.',
      'fair': '$7,500 is a strong price for an ungraded drachm — value rests on the named-dealer pedigree rather than a stated condition.'}
stuffapp._market_catalogue_fill_grade(it, card)
assert it['grade'] == 'Toned EF', it
assert it['grade_read'] is True
assert it['why'].startswith('Dealer grades it Toned EF'), it['why']
assert 'no numeric' not in it['why'] and 'ungraded' not in it['fair'], it
assert 'dealer-graded Toned EF' in it['fair'], it['fair']

# A model grade already there is left alone.
it2 = {'grade': 'Good VF', 'why': 'x', 'fair': 'y'}
stuffapp._market_catalogue_fill_grade(it2, dict(card))
assert it2['grade'] == 'Good VF' and it2['why'] == 'x'

# A card past the read cap (no description): the page is opened now.
PAGE = ('<html><body><a>Inquire about this item</a> <a>Print this page</a> ' + SCHMIDT +
        ' <button>Add To Cart</button></body></html>')
stuffapp._market_fetch_page = lambda url, limit=0: (200, PAGE) if 'gk1902' in url else (None, '')
card3 = {'store': 'S', 'title': 'Knidos drachm', 'price': 'US$ 7,500.00', 'listing_url': card['listing_url']}
it3 = {'grade': '', 'why': 'card states no numeric or word grade.', 'fair': ''}
stuffapp._market_catalogue_fill_grade(it3, card3)
assert it3['grade'] == 'Toned EF', it3
assert card3['description'].startswith('Knidos, Caria.'), card3['description'][:60]   # the new anchor

# The normaliser: an item that skipped the stage's pass reads the page
# itself, and 'grade not stated' is stamped only when the page has no word.
stuffapp._fetch_usd_rate = lambda currency, date_str: None
stuffapp.app.config['TESTING'] = True
with stuffapp.app.app_context():
    stuffapp.init_db()
    db = stuffapp.get_db()
    raw = {'title': 'Knidos, Caria. c. 480-449 BC, AR Drachm', 'listing_url': card['listing_url'],
           'price': 'US$ 7,500.00', 'theme': 'vcoins-catalogue', 'fills': 'Knidos (Aphrodite / lion)',
           'sale_type': 'fixed', 'grade': '', 'why': 'card states no numeric or word grade.',
           'fair': '$7,500 is a strong price for an ungraded drachm.'}
    item = stuffapp._market_normalize_item(db, 'coins', dict(raw))
    assert item and item['grade'] == 'Toned EF', item
    assert item['why'].startswith('Dealer grades it Toned EF'), item['why']
    assert 'ungraded' not in item['fair'], item['fair']
    # No grade word on the page at all: the honest stamp stays.
    stuffapp._market_fetch_page = lambda url, limit=0: (200, '<html><body>Print this page Knidos drachm 6.1g. Price: $500 <button>Add To Cart</button></body></html>')
    item = stuffapp._market_normalize_item(db, 'coins', dict(raw, why='no grade stated'))
    assert item and item['grade'] == 'grade not stated', item
print('ok: dealer grade word')
