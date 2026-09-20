"""Specific offers must identify one item, including redirects and stored actions."""
import os, sys, tempfile, json, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='market-exact-')
os.environ.pop('ANTHROPIC_API_KEY', None)
import app as stuff
from market_scan import PageResult, canonical_url

ITEM='https://www.ebay.com/itm/375423430457'
SEARCH='https://www.ebay.com/shop/martha-washington-silver-certificate?_nkw=martha'
HTML='<h1>1886 $1 Silver Certificate Martha Washington Fr# 217 PMG 65 EPQ</h1><button>Buy It Now</button>'

def probe(html=HTML, final=ITEM, challenged=False):
    return stuff._market_listing_probe(ITEM,PageResult(200,html,final,challenged))

class ExactListingTests(unittest.TestCase):
    def test_url_identity_and_canonical_queries(self):
        for url in (SEARCH,'https://ebay.com/sch/i.html?_nkw=martha','https://ebay.com/b/Notes/123','https://dealer.test/inventory','https://dealer.test/search?q=note','https://dealer.test/collections/notes'):
            self.assertTrue(stuff._market_listing_url_problem(url),url)
        for url in (ITEM,'https://ebay.co.uk/itm/Martha-Washington/375423430457?hash=x','https://cngcoins.com/Coin.aspx?CoinID=4321','https://ma-shops.com/vendor/item.php?id=2046'):
            self.assertFalse(stuff._market_listing_url_problem(url),url)
        self.assertEqual(canonical_url(ITEM+'?utm_source=test'),canonical_url('https://ebay.com/itm/Martha/375423430457'))
        self.assertIn('CoinID=4321',canonical_url('https://cngcoins.com/Coin.aspx?CoinID=4321&utm_source=test'))
        self.assertNotEqual(canonical_url('https://cngcoins.com/Coin.aspx?CoinID=4321'),canonical_url('https://cngcoins.com/Coin.aspx?CoinID=4322'))

    def test_redirect_search_different_item_and_challenge(self):
        self.assertEqual(probe(final=SEARCH)['state'],'invalid')
        self.assertEqual(probe(final='https://ebay.com/itm/123')['state'],'invalid')
        self.assertEqual(probe(final='https://ebay.com/itm/Martha/375423430457')['state'],'live')
        self.assertEqual(probe(final='https://ebay.com/splashui/captcha',challenged=True)['state'],'unknown')
        self.assertEqual(stuff._market_listing_probe(SEARCH,PageResult(200,HTML,SEARCH,False))['state'],'invalid')

    def test_other_listings_cannot_supply_liveness_or_identity(self):
        self.assertEqual(probe('<h1>Martha Washington</h1><h2>Similar Items</h2><button>Buy It Now</button>')['state'],'ended')
        self.assertEqual(probe('This listing was ended by the seller.<h2>Similar Items</h2><button>Buy It Now</button>')['state'],'ended')
        item={'title':'1886 $1 Martha Washington Fr. 217 PMG 65 EPQ','seller':'sarasotararecoingallery','listing_url':ITEM}
        for title in ('1886 $1 Martha Fr. 216 PMG 65 EPQ','1891 $1 Martha Fr. 217 PMG 65 EPQ','1886 $1 Martha Fr. 217 PMG 64 EPQ','1886 $2 Martha Fr. 217 PMG 65 EPQ'):
            self.assertTrue(stuff._market_listing_identity_problem(item,{'title':title}))
        self.assertTrue(stuff._market_listing_identity_problem(item,{'title':item['title'],'seller':'different-seller'}))
        self.assertFalse(stuff._market_listing_identity_problem(item,{'title':item['title']}))

    def test_photos_bound_to_primary_product(self):
        html='<script type="application/ld+json">'+json.dumps({'@type':'ItemList','itemListElement':[{'@type':'Product','image':'https://img.test/wrong.jpg'}]})+'</script>'
        self.assertEqual(stuff._market_page_image_urls(ITEM,html),[])
        self.assertEqual(stuff._market_page_image_urls(SEARCH,HTML),[])
        self.assertEqual(stuff._market_page_image_urls(ITEM,'<h2>Similar Items</h2><img src="https://i.ebayimg.com/images/g/WRONG/s-l1600.jpg">'),[])
        html += '<script type="application/ld+json">'+json.dumps({'@type':'Product','url':ITEM,'image':['https://img.test/right.jpg']})+'</script>'
        self.assertEqual(stuff._market_page_image_urls(ITEM,html),['https://img.test/right.jpg'])

    def test_saved_invalid_candidates_hidden_and_actions_blocked(self):
        with stuff.app.app_context():
            db=stuff.get_db()
            db.execute("INSERT INTO market_scans(id,category,status,started_at) VALUES ('scan','banknotes','done',datetime('now'))")
            for ident,status in (('bad','new'),('earlier','superseded'),('redirect','new')):
                item={'title':'1886 $1 Fr.217 PMG65','country':'United States of America','empire':'US','listing_url':ITEM if ident=='redirect' else SEARCH,'verified':True}
                db.execute("INSERT INTO market_scan_items(id,scan_id,category,status,payload,created_at) VALUES (?,'scan','banknotes',?,?,datetime('now'))",(ident,status,json.dumps(item)))
            db.commit()
            self.assertEqual([r['id'] for r in stuff._market_items(db,'banknotes')],['redirect'])
            self.assertEqual(stuff._market_items(db,'banknotes',earlier=True),[])
            client=stuff.app.test_client()
            self.assertEqual(client.post('/banknotes/market/bad/buy',json={'location':'Home'}).status_code,409)
            self.assertEqual(client.get('/banknotes/market/bad/listing').status_code,410)
            with patch.object(stuff,'_market_listing_probe',return_value={'state':'invalid','why':'Redirect to search'}):
                self.assertEqual(client.get('/banknotes/market/redirect/listing').status_code,410)
            self.assertEqual(db.execute("SELECT status FROM market_scan_items WHERE id='redirect'").fetchone()[0],'unavailable')
            self.assertEqual(db.execute('SELECT count(*) FROM banknotes').fetchone()[0],0)

    def test_domestic_and_philippine_period_labels(self):
        for country in ('United States','United States of America','USA'):
            self.assertEqual(stuff._market_colonial_empire({'country':country,'empire':'US','date_1':1886}), '')
        for year,expected in ((1944,'US'),(1955,''),(1890,'')):
            self.assertEqual(stuff._market_colonial_empire({'country':'Philippines','empire':'US','date_1':year}),expected)
        self.assertEqual(stuff._market_colonial_empire({'country':'Philippines','empire':'US','date_1':1944,'title':'Japanese occupation 500 pesos'}),'')

if __name__=='__main__':unittest.main()
