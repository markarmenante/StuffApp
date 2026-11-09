"""Face-value arithmetic, monetary boundaries, source parsing and all-note UI."""
from datetime import date
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-economics-test-')
os.environ['BANKNOTE_ECONOMICS_REFRESH'] = '0'
import banknote_economics as e
import app as stuff

NOW = date(2026,11,8)


class EconomicTests(unittest.TestCase):
    def setUp(self):
        self.data = {'fx':{'date':'2026-11-06','usd_per_unit':{'GBP':1.25,'EUR':1.1}},
                     'cpi':{iso:{'values':{'1900':10.,'1960':20.,'1980':30.,'1981':20.,'1982':40.},
                         'current':{'value':200.,'period':'2026-09'},'source_url':e.BOE_URL}
                         for iso in ('GBR','USA','DEU')}}

    def test_domestic_inflation_then_current_fx_and_separate_nominal_amount(self):
        n = dict(country='United Kingdom', denomination='10 Shillings', date_1=1900)
        r = e.calculate(n,self.data,NOW)
        self.assertEqual(r['at_issue'], .5*200/10*1.25)
        self.assertEqual(r['today'], .5*1.25)
        self.assertEqual(r['probable_issue_date'], 'c. 1900')
        self.assertIn('estimate',r['issue_basis'])

    def test_series_date_compares_buying_power_without_claiming_actual_release(self):
        n = dict(country='USA', denomination='5 Dollars', date_1=1900,series='Series of 1900')
        r = e.calculate(n,self.data,NOW)
        self.assertEqual(r['at_issue'],100); self.assertEqual(r['today'],5)
        self.assertEqual(r['comparison_year'], '1900')
        self.assertIn('not a verified issue date', r['comparison_basis'])
        self.assertEqual(r['probable_issue_date'], 'Not established')
        n['issue_date']='1960'
        updated = e.calculate(n,self.data,NOW)
        self.assertEqual(updated['at_issue'],100)
        self.assertEqual(updated['probable_issue_date'], '1960')

    def test_series_range_uses_all_years_and_extremes_not_only_endpoints(self):
        n = dict(country='England',denomination='1 Pound',date_1_text='1980–1982',issue_date='1990')
        self.assertEqual(e.calculate(n,self.data,NOW)['at_issue'], [6.25,12.5])
        self.assertEqual(e.calculate(n,self.data,NOW)['comparison_year'], '1980–1982')

    def test_primary_year_series_fallback_conflicts_and_calendar_boundaries(self):
        base = dict(country='England', denomination='1 Pound', date_1=1981)
        family = e.calculate(dict(base, series='1980–1982 issue family'), self.data, NOW)
        self.assertEqual(family['comparison_year'], '1981')
        self.assertEqual(family['at_issue'], 12.5)
        fallback = e.calculate(dict(base, date_1=None, series='Series of 1981'), self.data, NOW)
        self.assertEqual(fallback['at_issue'], 12.5)
        for changed in (dict(series='Series of 1980'), dict(series='1970–1980 issue family'),
                        dict(date_1_text='1980 / 1982'), dict(date_1_text='1982–1980'),
                        dict(date_1_text='AH 1400', series=None),
                        dict(date_1=None, series='Series of 1980 and 1982')):
            with self.subTest(changed=changed):
                result = e.calculate(dict(base, **changed), self.data, NOW)
                self.assertIsNone(result['at_issue'])
                self.assertEqual(result['comparison_year'], 'Unavailable')
        law = e.calculate(dict(base, date_1_text='Act of 1981'), self.data, NOW)
        self.assertEqual(law['at_issue'], 12.5)
        self.assertEqual(law['probable_issue_date'], 'Not established')
        self.assertIn('Printed law year', law['comparison_basis'])

    def test_1917_dollars_use_series_year_and_packaged_current_cpi(self):
        note = dict(country='United States', issuer='United States Treasury',
                    denomination='2 Dollars', date_1=1917, series='Series of 1917')
        result = e.calculate(note, e.snapshot(tempfile.mkdtemp()), NOW)
        self.assertAlmostEqual(result['at_issue'], 2 * 1001.3 / 38.5)
        self.assertEqual(result['at_issue_display'], '≈ $52.02')
        self.assertEqual(result['today'], 2)
        self.assertEqual(result['probable_issue_date'], 'Not established')
        self.assertIn('current CPI estimate', result['data_dates'])

    def test_connecticut_1776_face_value_uses_local_ratio_and_common_cpi_base(self):
        note = dict(country='Connecticut Colony', issuer='Colony of Connecticut',
                    denomination='1 Shilling', date_1=1776)
        data = e.snapshot(tempfile.mkdtemp())
        before = json.dumps((note, data), sort_keys=True)
        result = e.calculate(note, data, NOW)
        expected = (1 / 6) * (1001.3 / ((290 + 299.3 + 312.2) / 3) * 100) / 8.735
        self.assertAlmostEqual(result['at_issue'], expected)
        self.assertEqual(result['at_issue_display'], '≈ $6.36')
        self.assertIsNone(result['today'])
        self.assertEqual(result['today_display'], 'Unavailable')
        self.assertIn('Obsolete Connecticut currency', result['note'])
        self.assertIn('paper-money discounts are not measured', result['note'])
        self.assertEqual({source['url'] for source in result['sources']},
                         {e.FED_URL, e.CONNECTICUT_CURRENCY_URL, e.HISTORICAL_US_CPI_URL})
        self.assertIn('historical CPI estimate', result['data_dates'])
        self.assertEqual(json.dumps((note, data), sort_keys=True), before)
        # Changing a same-base modern index by a scale factor must not change
        # the historical result, and the incompatible 1800 splice is irrelevant.
        data['cpi']['USA']['current']['value'] *= 2
        for year in ('1982', '1983', '1984'):
            data['cpi']['USA']['values'][year] *= 2
        data['cpi']['USA']['values']['1800'] = 99999
        self.assertAlmostEqual(e.calculate(note, data, NOW)['at_issue'], expected)

    def test_connecticut_rule_does_not_apply_to_other_shillings_or_missing_cpi(self):
        base = dict(country='Connecticut Colony', issuer='Colony of Connecticut',
                    denomination='1 Shilling', date_1=1776)
        data = e.snapshot(tempfile.mkdtemp())
        for changed in (dict(country='New York Colony'), dict(country='East Africa'),
                        dict(country='Connecticut'), dict(issuer='State of Connecticut'),
                        dict(issuer='Continental Congress'), dict(issuer=''),
                        dict(date_1=1775), dict(date_1=1777), dict(issue_type='Private / Scrip'),
                        dict(denomination='1 Sterling Shilling'), dict(series='Old tenor')):
            with self.subTest(changed=changed):
                result = e.calculate(dict(base, **changed), data, NOW)
                self.assertIsNone(result['at_issue'])
                self.assertIsNone(result['today'])
        for value in (None, 0, float('nan')):
            with self.subTest(anchor=value):
                data['cpi']['USA']['values']['1983'] = value
                self.assertIsNone(e.calculate(base, data, NOW)['at_issue'])
        data = e.snapshot(tempfile.mkdtemp())
        data['cpi']['USA']['current']['period'] = '2020'
        self.assertIsNone(e.calculate(base, data, NOW)['at_issue'])
        data['cpi']['USA']['current']['period'] = '2026'
        for value in (None, 0, True, float('nan'), float('inf')):
            data['cpi']['USA']['current']['value'] = value
            self.assertIsNone(e.calculate(base, data, NOW)['at_issue'])

    def test_fractional_year_cannot_enter_the_connecticut_rule_or_us_estimate(self):
        data = e.snapshot(tempfile.mkdtemp())
        cases = (
            (dict(country='Connecticut Colony', issuer='Colony of Connecticut',
                  denomination='1 Shilling'), 1776),
            (dict(country='United States', denomination='2 Dollars'), 1917),
        )
        for note, year in cases:
            for field, value in (('date_1', year + .5), ('date_1_text', str(year) + '.5'),
                                 ('series', 'Series of ' + str(year) + '.5')):
                with self.subTest(year=year, field=field):
                    result = e.calculate(dict(note, **{field: value}), data, NOW)
                    self.assertIsNone(result['at_issue'])
                    self.assertEqual(result['comparison_year'], 'Unavailable')
                    self.assertIn('whole Gregorian year', result['comparison_basis'])
            for value in (year, float(year), str(year) + '.0', str(year) + '.05.10',
                          'May 10, ' + str(year)):
                with self.subTest(year=year, value=value):
                    self.assertIsNotNone(e.calculate(dict(note, date_1_text=value), data, NOW)['at_issue'])

    def test_historical_units_and_regime_boundaries_are_not_conflated(self):
        for n in [dict(country='Brazil',denomination='10 Mil Reis',date_1=1925),
                  dict(country='Brazil',denomination='100 Cruzeiros Reais',date_1=1994),
                  dict(country='China',denomination='100 Yuan',date_1=1949),
                  dict(country='Mexico',denomination='100 Pesos',date_1=1980),
                  dict(country='Germany',denomination='100 Reichsmark',date_1=1935),
                  dict(country='Philippines',denomination='10 Pesos',date_1=1943,issuer='The Japanese Government'),
                  dict(country='United States',denomination='10 Dollars',date_1=1864,issuer='Confederate States of America'),
                  dict(country='England',denomination='10 Pounds',date_1=1900,issue_type='Private / Scrip')]:
            with self.subTest(n=n):
                r=e.calculate(n,self.data,NOW)
                self.assertIsNone(r['today']);self.assertIsNone(r['at_issue'])

    def test_euro_conversion_and_subunits(self):
        r=e.calculate(dict(country='Germany',denomination='100 Deutsche Mark',date_1=1960),self.data,NOW)
        self.assertAlmostEqual(r['today'],100/1.95583*1.1)
        self.assertAlmostEqual(r['at_issue'],100/1.95583*200/20*1.1)
        self.assertEqual(e.currency(dict(country='England',denomination='6 Pence'),1900)[2],1/240)
        self.assertEqual(e.currency(dict(country='England',denomination='6 Pence'),1980)[2],.01)
        self.assertIsNone(e.currency(dict(country='England',denomination='6 Pence'),1971))
        self.assertEqual(e._amount('½ Dollar'),.5)
        self.assertEqual(e._amount('1/2 Dollar'),.5)

    def test_missing_cpi_keeps_today_and_never_uses_nearest_year(self):
        n=dict(country='England',denomination='1 Pound',date_1=1901)
        r=e.calculate(n,self.data,NOW)
        self.assertEqual(r['today'],1.25);self.assertIsNone(r['at_issue'])
        self.assertEqual(e.money(.00001),'<$0.01')
        self.assertEqual(e.years('AH 1350'),[])

    def test_official_source_parsers_reject_partial_data_and_keep_fx_direction(self):
        fx=e.parse_fx({'base':'USD','date':'2026-11-06','rates':{'GBP':.8,'EUR':.9,'JPY':150,'CHF':.85}})
        self.assertEqual(fx['usd_per_unit']['GBP'],1.25)
        for parser,payload in [(e.parse_fx,{'base':'EUR'}),(e.parse_boe,'no data'),(e.parse_fed,'no table'),(e.parse_worldbank,[])]:
            with self.assertRaises((ValueError,KeyError)):parser(payload)
        fed=''.join(f'<tr><td>{y}</td><td>{v}</td></tr>' for y,v in [('1800','51'),('2020','800'),('2026*','1000')])
        parsed=e.parse_fed(fed)
        self.assertEqual(parsed['current']['value'],1000)
        self.assertTrue(parsed['current']['estimated'])

    def test_packaged_data_has_real_source_coverage_without_network(self):
        data=e.snapshot(tempfile.mkdtemp())
        self.assertGreaterEqual(len(data['cpi']),40)
        self.assertIn('1800',data['cpi']['USA']['values'])
        self.assertIn('1750',data['cpi']['GBR']['values'])
        self.assertGreater(len(data['fx']['usd_per_unit']),20)

    def test_provider_failure_retains_last_good_public_inputs(self):
        folder=tempfile.mkdtemp()
        before=e.snapshot(folder)
        before['cpi_checked']='1900-01'
        Path(folder,'banknote-economics.json').write_text(json.dumps(before))
        with patch.object(e,'_read',side_effect=OSError('Synthetic unavailable provider')):
            e.refresh(folder)
        after=e.snapshot(folder)
        self.assertEqual(after['cpi'],before['cpi'])
        self.assertEqual(after['fx'],before['fx'])
        self.assertEqual(after['cpi_checked'],'1900-01')


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.context=stuff.app.app_context();self.context.push()
        stuff.init_db();self.db=stuff.get_db()
        self.db.execute("INSERT OR REPLACE INTO banknotes(id,country,denomination,date_1) VALUES('economic','United Kingdom','10 Shillings',1935)")
        self.db.commit();self.client=stuff.app.test_client()

    def tearDown(self):self.context.pop()

    def test_each_banknote_has_only_amount_after_denomination_and_endpoint_never_edits(self):
        response=self.client.get('/banknotes/economic')
        self.assertEqual(response.status_code,200)
        page=response.get_data(as_text=True)
        self.assertLess(page.index('name="denomination"'), page.index('id="banknoteEconomics"'))
        self.assertLess(page.index('id="banknoteEconomics"'), page.index('name="material"'))
        self.assertEqual(page.count('data-economic="'), 1)
        self.assertNotIn('class="banknote-economics-line"', page)
        self.assertNotIn('data-economic-sources', page)
        self.assertIn('type="hidden" name="issue_date"', page)
        self.assertEqual(page.count('name="issue_date"'),1)
        before=dict(self.db.execute("SELECT * FROM banknotes WHERE id='economic'").fetchone())
        data=self.client.get('/banknotes/economic/economics').get_json()
        self.assertIsNotNone(data['at_issue']);self.assertIsNotNone(data['today'])
        self.assertEqual(before,dict(self.db.execute("SELECT * FROM banknotes WHERE id='economic'").fetchone()))
        self.assertEqual(self.client.get('/banknotes/missing/economics').status_code,404)
        with patch.object(stuff,'_user_can_see_row',return_value=False):
            self.assertEqual(self.client.get('/banknotes/economic/economics').status_code,404)

    def test_probable_issue_date_saves_independently_of_catalogue_year(self):
        before = self.client.get('/banknotes/economic/economics').get_json()
        saved=self.client.post('/banknotes/economic/save-field',json={'field':'issue_date','value':'1936–1938'})
        self.assertEqual(saved.status_code,200)
        row=self.db.execute("SELECT * FROM banknotes WHERE id='economic'").fetchone()
        self.assertEqual(row['issue_date'],'1936–1938');self.assertEqual(row['date_1'],1935)
        after = self.client.get('/banknotes/economic/economics').get_json()
        self.assertEqual(after['comparison_year'], '1935')
        self.assertEqual(after['at_issue'], before['at_issue'])
        self.assertEqual(after['probable_issue_date'], '1936–1938')

    def test_historical_price_and_range_amounts_render_without_javascript(self):
        base = self.client.get('/banknotes/economic/economics').get_json()
        for kind in ('historical_price', 'historical_range', 'historical_quote'):
            with self.subTest(kind=kind):
                summary = dict(base, estimate_kind=kind, estimate_basis='Sourced historical benchmark',
                               at_issue_display='≈ $3.00–$5.00')
                with patch.dict(stuff.app.jinja_env.globals, banknote_economic_summary=lambda row: summary):
                    page = self.client.get('/banknotes/economic').get_data(as_text=True)
                self.assertIn('>≈ $3.00–$5.00</span>', page)
                self.assertIn('title="Series year: 1935.', page)
                self.assertIn('Sourced historical benchmark', page)


if __name__=='__main__':unittest.main()
