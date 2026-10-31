"""Exact dealer recovery must preserve listing identity and durable deletion."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-dealer-')
os.environ.pop('ANTHROPIC_API_KEY', None)
import app as stuff
import market_dealer_listing as dealer

CATEGORY = 'https://wittercoin.com/papermoney/us-large-size/silver-certificate'
EXACT = 'https://wittercoin.com/item/fr-245-1891-2-silver-certificate-pmg-64-epq/1859590001'
OTHER = 'https://wittercoin.com/item/fr-335-1891-50-silver-certificate-pmg-au-50/2193533008'
TITLE = '1891 $2 Silver Certificate Windom Fr. 245 PMG 64 EPQ'
ACTUAL = 'Fr. 245 1891 $2 Silver Certificate PMG 64 EPQ'
PHOTO = 'https://x42solutions.blob.core.windows.net/productimages/front_800.jpeg'
HTML = '<a href="'+OTHER+'">Fr. 335 1891 $50 Silver Certificate PMG AU 50</a><a href="'+EXACT+'"><b>'+ACTUAL+'</b></a>'
PRODUCT = '<h1>'+ACTUAL+'</h1><meta property="og:image" content="'+PHOTO+'"><button>Add to cart</button>'
RAW = dict(title=TITLE, listing_url=CATEGORY, country='United States of America',
           price='$6,000', grade='Choice Uncirculated 64', grade_numeric=64, grading_authority='PMG',
           pick_number='Fr. 245', denomination='$2', date_1=1891,
           why="Fills this gap. The URL is the dealer's category page it lists two 1891 notes.", verified=True)


class DealerTests(unittest.TestCase):
    def setUp(self):
        with stuff.app.app_context():
            db=stuff.get_db()
            db.execute('DELETE FROM market_scan_items')
            db.execute('DELETE FROM market_dismissals')
            db.execute("INSERT OR IGNORE INTO market_scans(id,category,status,started_at) VALUES('fixture','banknotes','done','2026-10-30')")
            db.commit()

    def fetch(self, url, limit=400_000):
        stuff._MARKET_LAST_URL.final = url
        return 200, HTML if url == CATEGORY else PRODUCT

    def test_unique_strict_identity_and_observed_url(self):
        self.assertEqual(dealer.resolve(CATEGORY, TITLE, HTML), EXACT)
        self.assertIsNone(dealer.resolve(CATEGORY, TITLE, HTML.replace('Fr. 245', 'Fr. 246')))
        for changed in (TITLE.replace('1891','1892'), TITLE.replace('$2','$5'),
                        TITLE.replace('64','65'), TITLE.replace(' EPQ',''), 'Fr. 245'):
            self.assertIsNone(dealer.resolve(CATEGORY, changed, HTML), changed)
        duplicate = HTML+'<a href="'+EXACT.replace('1859590001','9999999999')+'">'+ACTUAL+'</a>'
        self.assertIsNone(dealer.resolve(CATEGORY, TITLE, duplicate))
        for bad in ('https://wittercoin.com.evil.test/item/x/123', 'https://evil.test/item/x/123',
                    'https://user@wittercoin.com/item/x/123', 'https://wittercoin.com:444/item/x/123',
                    'https://[invalid/item/x/123'):
            self.assertFalse(dealer.exact_url(bad))
            self.assertIsNone(dealer.resolve(CATEGORY, TITLE, '<a href="'+bad+'">'+ACTUAL+'</a>'))
        self.assertTrue(stuff._market_listing_url_problem(CATEGORY))
        self.assertFalse(stuff._market_listing_url_problem(EXACT))
        self.assertEqual(stuff._market_page_image_urls(CATEGORY, PRODUCT), [])

    def test_recovery_reads_exact_product_and_photos(self):
        with patch.object(stuff, '_market_fetch_page', side_effect=self.fetch):
            recovered = stuff._market_recover_dealer_item(RAW)
        self.assertEqual(recovered['listing_url'], EXACT)
        self.assertEqual(recovered['discovery_url'], CATEGORY)
        self.assertEqual(recovered['image_url'], PHOTO)
        self.assertEqual(recovered['why'], 'Fills this gap.')
        self.assertEqual(recovered['price'], '$6,000')
        self.assertEqual(RAW['listing_url'], CATEGORY)
        old_photo = dict(RAW, image_url='https://img.test/wrong.jpg', image_urls=['https://img.test/wrong.jpg'])
        with patch.object(stuff, '_market_fetch_page', side_effect=self.fetch), patch.object(stuff, '_market_listing_probe', return_value={'state':'live','final':EXACT,'title':ACTUAL}):
            no_photos=stuff._market_recover_dealer_item(old_photo)
            self.assertIsNone(no_photos['image_url'])
            self.assertEqual(no_photos['image_urls'],[])
        for probe in ({'state':'unknown'}, {'state':'ended'},
                      {'state':'live','final':EXACT,'title':ACTUAL.replace('$2','$50')},
                      {'state':'live','final':OTHER,'title':ACTUAL}):
            with patch.object(stuff, '_market_fetch_page', side_effect=self.fetch), patch.object(stuff, '_market_listing_probe', return_value=probe):
                self.assertIs(stuff._market_recover_dealer_item(RAW), RAW)

    def test_existing_current_repair_is_persisted_once_and_dismissals_win(self):
        with stuff.app.app_context():
            db=stuff.get_db()
            for ident, status in (('current','new'),('history','superseded')):
                db.execute("INSERT INTO market_scan_items(id,scan_id,category,status,title,listing_url,payload,created_at) VALUES(?,'fixture','banknotes',?,?,?,?,'2026-10-30')", (ident,status,TITLE,CATEGORY,json.dumps(RAW)))
            db.commit()
            with patch.object(stuff, '_market_fetch_page', side_effect=self.fetch) as fetch:
                rows=stuff._market_items(db,'banknotes')
                self.assertEqual(len(rows),1)
                self.assertEqual(rows[0]['listing_url'],EXACT)
                self.assertEqual(rows[0]['image_url'],PHOTO)
                self.assertEqual(fetch.call_count,2)
                stuff._market_items(db,'banknotes')
                self.assertEqual(fetch.call_count,2)
            saved=db.execute("SELECT * FROM market_scan_items WHERE id='current'").fetchone()
            self.assertEqual(saved['listing_url'],EXACT)
            self.assertEqual(saved['canonical_url'],stuff.market_runtime.canonical_url(EXACT))
            self.assertEqual(json.loads(saved['payload'])['listing_url'],EXACT)
            self.assertEqual(db.execute("SELECT listing_url FROM market_scan_items WHERE id='history'").fetchone()[0],CATEGORY)
            self.assertEqual(db.execute('SELECT count(*) FROM banknotes').fetchone()[0],0)
            stuff.market_runtime.dismiss_listing(db,'banknotes',EXACT)
            with patch.object(stuff, '_market_fetch_page', side_effect=AssertionError('No replay/fetch')):
                self.assertEqual(stuff._market_items(db,'banknotes'),[])
            # A new scan cannot reintroduce the exact item via its category.
            with patch.object(stuff, '_market_fetch_page', side_effect=self.fetch):
                self.assertIsNone(stuff._market_normalize_item(db,'banknotes',RAW))

    def test_delete_during_recovery_prevents_publication(self):
        with stuff.app.app_context():
            db=stuff.get_db()
            db.execute("DELETE FROM market_scan_items")
            db.execute("INSERT INTO market_scan_items(id,scan_id,category,status,title,listing_url,payload,created_at) VALUES('race','fixture','banknotes','new',?,?,?,'2026-10-30')", (TITLE,CATEGORY,json.dumps(RAW)))
            db.commit()
            def recover(item):
                db.execute("UPDATE market_scan_items SET status='dismissed' WHERE id='race'")
                db.commit()
                return dict(item,listing_url=EXACT,image_url=PHOTO)
            with patch.object(stuff,'_market_recover_dealer_item',side_effect=recover):
                self.assertEqual(stuff._market_items(db,'banknotes'),[])
            self.assertEqual(db.execute("SELECT status FROM market_scan_items WHERE id='race'").fetchone()[0],'dismissed')

    def test_delete_exact_url_during_recovery_prevents_repair(self):
        with stuff.app.app_context():
            db=stuff.get_db()
            db.execute("INSERT INTO market_scan_items(id,scan_id,category,status,title,listing_url,payload,created_at) VALUES('race-exact','fixture','banknotes','new',?,?,?,'2026-10-30')", (TITLE,CATEGORY,json.dumps(RAW)))
            db.commit()
            def recover(item):
                stuff.market_runtime.dismiss_listing(db,'banknotes',EXACT)
                return dict(item,listing_url=EXACT,image_url=PHOTO)
            with patch.object(stuff,'_market_recover_dealer_item',side_effect=recover):
                self.assertEqual(stuff._market_items(db,'banknotes'),[])
            saved=db.execute("SELECT status,listing_url FROM market_scan_items WHERE id='race-exact'").fetchone()
            self.assertEqual(saved['listing_url'],CATEGORY)
            self.assertEqual(saved['status'],'new')

    def test_transient_source_failure_preserves_candidate_for_later_recovery(self):
        with stuff.app.app_context():
            db=stuff.get_db()
            db.execute("INSERT INTO market_scan_items(id,scan_id,category,status,title,listing_url,payload,created_at) VALUES('retry','fixture','banknotes','new',?,?,?,'2026-10-30')", (TITLE,CATEGORY,json.dumps(RAW)))
            db.commit()
            for response in ((None,''),(200,'<title>Security challenge</title>')):
                with patch.object(stuff,'_market_fetch_page',return_value=response):
                    self.assertEqual(stuff._market_items(db,'banknotes'),[])
                saved=db.execute("SELECT status,payload FROM market_scan_items WHERE id='retry'").fetchone()
                self.assertEqual(saved['status'],'new')
                self.assertEqual(saved['payload'],json.dumps(RAW))
            with patch.object(stuff,'_market_fetch_page',side_effect=self.fetch):
                self.assertEqual(stuff._market_items(db,'banknotes')[0]['listing_url'],EXACT)


if __name__=='__main__': unittest.main()
