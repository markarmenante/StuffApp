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

    def test_auction_indexes_are_not_individual_lots(self):
        invalid = ('https://leunumismatik.com/en/auction',
                   'https://leunumismatik.com/en/auction/77/',
                   'https://leunumismatik.com/en/catalogue/77',
                   'https://leunumismatik.com/en/livebidding',
                   'https://auction.test/auction.aspx?id=77',
                   'https://auction.test/auctions/upcoming',
                   'https://auction.test/en/auction?AuctionID=24')
        for url in invalid:
            with self.subTest(url=url):
                self.assertTrue(stuff._market_listing_url_problem(url))
                with patch.object(stuff, '_market_price_from_page') as price:
                    self.assertIsNone(stuff._market_normalize_item(None, 'coins', {'listing_url':url}))
                    price.assert_not_called()
                self.assertEqual(stuff._market_page_image_urls(url, HTML), [])
        valid = ('https://leunumismatik.com/en/lot/77/1014',
                 'https://leunumismatik.com/en/lot/77/1014/%5B77%5D',
                 'https://auction.test/auctions/24/lot/1014',
                 'https://auction.test/auction.aspx?AuctionID=24&LotID=1014',
                 'https://auction.test/catalogue/24?lot=1014')
        for url in valid:
            self.assertFalse(stuff._market_listing_url_problem(url),url)

    def test_auction_index_controls_cannot_verify_a_lot(self):
        lot='https://leunumismatik.com/en/lot/77/1014'
        index='https://leunumismatik.com/en/auction'
        html='<h1>Auctions 23, 24 &amp; 25</h1><button>Place bid</button>'
        for original,final in ((index,index),(lot,index),(lot,lot)):
            with self.subTest(original=original,final=final):
                result=stuff._market_listing_probe(original,PageResult(200,html,final,False))
                self.assertEqual(result['state'],'invalid')
                self.assertNotIn('images',result)
        html='<h1>Auction 24, Lot 1014: Lucania, Velia</h1><button>Place bid</button>'
        self.assertEqual(stuff._market_listing_probe(lot,PageResult(200,html,lot,False))['state'],'live')

    def test_saved_auction_index_cannot_be_viewed_or_bought(self):
        with stuff.app.app_context():
            db=stuff.get_db()
            db.execute("INSERT INTO market_scans(id,category,status,started_at) VALUES ('auction-scan','coins','done',datetime('now'))")
            item={'title':'Auction 24 Lot 1014 Velia','listing_url':'https://leunumismatik.com/en/auction','verified':True}
            for ident,status in (('auction-index','new'),('old-auction-index','dismissed')):
                db.execute("INSERT INTO market_scan_items(id,scan_id,category,status,payload,created_at) VALUES (?,'auction-scan','coins',?,?,datetime('now'))",(ident,status,json.dumps(item)))
            db.commit()
            client=stuff.app.test_client()
            self.assertEqual(client.get('/coins/market/auction-index/listing').status_code,410)
            for paid in (False,True):
                self.assertEqual(client.post('/coins/market/old-auction-index/buy',json={'bought':paid,'location':'Home'}).status_code,409)
            self.assertEqual(stuff._market_items(db,'coins'),[])
            self.assertEqual(stuff._market_items(db,'coins',earlier=True),[])
            self.assertEqual(db.execute('SELECT count(*) FROM coins').fetchone()[0],0)

    def test_winning_bids_fee_notice_does_not_end_live_auction(self):
        lot='https://leunumismatik.com/en/lot/77/1014'
        html='<h1>Lot 1014: Lucania, Velia</h1><button>Bid now</button>'
        html+="<p>All winning bids are subject to a 22.5% buyer's fee.</p>"
        self.assertEqual(stuff._market_listing_probe(lot,PageResult(200,html,lot,False))['state'],'live')
        for result in ('Winning bid: CHF 5,000', 'Hammer price: CHF 5,000'):
            ended=html+'<p>'+result+'</p>'
            self.assertEqual(stuff._market_listing_probe(lot,PageResult(200,ended,lot,False))['state'],'ended')

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
