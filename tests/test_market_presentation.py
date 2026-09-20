"""Existing scan payloads wrap and omit internal retrieval notes at render time."""
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-market-presentation-')
os.environ.pop('ANTHROPIC_API_KEY', None)
import app as stuff

HEURISTIC = ('Listing carries active Buy It Now / Klarna financing language typical of a current fixed-price offer; '
             'exact live-price text was not captured in the search snippet.')
PAYLOAD = {'title': 'PHILIPPINES 1944 (ND) 500 PESO VICTORY P-101c. PMG CHOICE UNC 64EPQ, SCARCE & FANCY',
    'country': 'Philippines', 'issue_year_start':1944, 'issue_year_end':1945, 'issue_date_source':'https://catalogue.example/fixture', 'denomination': '500 Pesos', 'date_1': 1944, 'pick_number': 'P-101c',
    'region': 'Attica', 'denomination_type': 'Tetradrachm', 'grade': 'Choice Uncirculated', 'grade_numeric': 64,
    'grading_authority': 'PMG', 'designation': 'EPQ', 'price': 'See listing', 'venue': 'eBay',
    'seller': 'philippinesmyphilippines', 'listing_url': 'https://example.test/candidate', 'verified': True,
    'live_evidence': HEURISTIC, 'why': HEURISTIC + ' 500 Pesos fills the Victory Series denomination gap.',
    'fills': 'Philippines Victory Series 66 — closes the 500 Pesos gap (1, 2, 5, 10, 50, 500 missing).',
    'owned': 'P 235 500 Pesos 1944 (P-114a, SB-2232a) PCGS Banknote Choice UNC — same denomination and year',
    'fair': 'No comparable-sale price was captured in this pass; seller reports top-7 graded, only 6 finer. '
            'Buyer premium 20%; shipping excluded. Heritage sold a comparable for $900 in 2025.',
    'empire': 'US', 'image_url': '', 'sale_type': 'fixed'}

class PresentationTests(unittest.TestCase):
    def test_narrow_cleanup_keeps_concrete_facts(self):
        self.assertEqual(stuff._market_display_copy(HEURISTIC), '')
        self.assertEqual(stuff._market_display_copy(HEURISTIC + ' Scarce type.'), 'Scarce type.')
        for text in ('Sold; no longer available.', 'Reserve not met.', 'Price excludes shipping and buyer premium.',
                     'Estimate $700–900.', 'Search result says this lot sold for $900.', 'PMG population 7, six finer.'):
            for phrase in text.split('; '):
                self.assertIn(phrase, stuff._market_display_copy(text))
        self.assertIn('Comparable sales not available.', stuff._market_display_copy(PAYLOAD['fair']))
        self.assertIn('seller reports top-7 graded', stuff._market_display_copy(PAYLOAD['fair']))

    def test_saved_current_and_earlier_candidates_use_clean_display(self):
        with stuff.app.app_context():
            db=stuff.get_db(); now=datetime.utcnow().isoformat()
            for category in ('coins','banknotes'):
                db.execute('INSERT INTO market_scans(id,category,started_at,finished_at,status) VALUES(?,?,?,?,?)',
                           (category,category,now,now,'done'))
                for status in ('new','superseded'):
                    db.execute('INSERT INTO market_scan_items(id,scan_id,category,rank,status,payload,created_at) VALUES(?,?,?,?,?,?,?)',
                               (category+status,category,category,1,status,json.dumps(PAYLOAD),now))
            db.commit()
            for category in ('coins','banknotes'):
                for suffix in ('','?earlier=1'):
                    response=stuff.app.test_client().get('/'+category+'/market'+suffix)
                    self.assertEqual(response.status_code,200)
                    html=response.get_data(as_text=True)
                    self.assertNotIn('Klarna',html); self.assertNotIn('search snippet',html)
                    self.assertIn('500 Pesos fills',html); self.assertIn('Buyer premium 20%',html)
                    self.assertIn('seller reports top-7',html); self.assertIn('$900 in 2025',html)
                    self.assertIn('✓ live',html); self.assertIn('See listing',html)
                    self.assertIn('list-toolbar-market',html)
                    self.assertNotIn('banknote-history-position.js',html)
                raw=json.loads(db.execute('SELECT payload FROM market_scan_items WHERE id=?',(category+'new',)).fetchone()[0])
                self.assertEqual(raw['live_evidence'],HEURISTIC)
                self.assertEqual(raw['why'],PAYLOAD['why'])

if __name__=='__main__': unittest.main()
