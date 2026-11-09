"""Reviewed historical face-value relationships, never inferred from filing groups.

A rule identifies the issuer, monetary unit and complete calendar-year bounds.
Its reference-country CPI gives a labelled benchmark, not a measured local price
basket, market discount, collector value or promise of redemption.
"""
import json
import math
from functools import lru_cache
from pathlib import Path
import re
import unicodedata

JST_URL = 'https://www.macrohistory.net/database/'
BOARD_URL = 'https://sites.krieger.jhu.edu/iae/files/2017/04/Krus-Schuler_Currency_Board_Financial_Statements_2014.12.21.pdf'
CFA_URL = 'https://www.tresor.economie.gouv.fr/tresor-international/la-zone-franc/la-zone-franc-de-1939-a-aujourd-hui'
FRENCH_COLONIAL_URL = 'https://www.bceao.int/sites/default/files/2017-12/rapport_annuel_de_la_bceao_2003.pdf'
CFP_URL = 'https://www.ieom.fr/IMG/pdf/ieom-rapport_d_activite_2019-page.pdf'


def plain(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value or '')).casefold()
                   if not unicodedata.combining(c))


def _matches(pattern, text):
    return bool(re.search(pattern, text))


def _unit(unit, pound_factor=1., dollar_factor=None):
    if dollar_factor is not None:
        if re.fullmatch(r'dollars?', unit): return dollar_factor
        if re.fullmatch(r'cents?', unit): return dollar_factor / 100
        return None
    if re.fullmatch(r'(?:sterling )?pounds?(?: sterling)?', unit): return pound_factor
    if re.fullmatch(r'shillings?', unit): return pound_factor / 20
    if re.fullmatch(r'pence|penny|pennies', unit): return pound_factor / 240
    if dollar_factor is not None:
        if re.fullmatch(r'dollars?', unit): return dollar_factor
        if re.fullmatch(r'cents?', unit): return dollar_factor / 100
    return None


def _rule(family, iso, code, factor, url, basis, extra_urls=()):
    return dict(family=family, iso=iso, code=code, factor=factor,
                kind='historical_parity', basis=basis,
                sources=[dict(name=family + ': monetary relationship', url=url)] +
                        [dict(name=family + ': historical evidence', url=u) for u in extra_urls])


def reference(note, year, unit):
    """A reference unit for this exact issuer/date/leading denomination, or None."""
    country, issuer = plain(note.get('country')), plain(note.get('issuer'))
    evidence = ' '.join(plain(note.get(k)) for k in ('issuer', 'series', 'issue_type'))
    # Same-name wartime/private alternatives never inherit government parities.
    if _matches(r'japanese|guerrilla|counterfeit|notgeld|savings bond|coupon|confederate|reichsmark', evidence):
        return None
    def gb(family, factor, url, detail=''):
        if factor is None: return None
        return _rule(family, 'GBR', 'GBP', factor, url,
                     'UK purchasing-power benchmark at documented monetary parity. ' + detail)
    # The explicit public issuer is necessary, including emergency States notes.
    island = [
        ('gibraltar', r'government of gibraltar|gibraltar government', 1934, 2100, 'https://gibraltar-stamps.com/index.php?action=index&controller=banknotes'),
        ('guernsey', r'states of guernsey', 1946, 2100, 'https://www.gfsc.gg/sites/default/files/media/helix-file/Financial%20Literacy%206%20-%20How%20is%20Money%20Created.pdf.pdf'),
        ('jersey', r'states of jersey', 1941, 2100, 'https://www.gov.je/TaxesMoney/JerseyCurrency/Pages/CurrencyMakesMoney.aspx'),
        ('isle of man', r'isle of man government|government of the isle of man', 1961, 2100, 'https://www.legislation.gov.im/cms/images/LEGISLATION/PRINCIPAL/1992/1992-0014/1992-0014_1.pdf'),
        ('falkland islands', r'government.*falkland', 1931, 2100, 'https://www.falklands.gov.fk/finance/currency'),
        ('malta', r'government.*malta|malta.*government|central bank of malta', 1940, 1971, 'https://www.centralbankmalta.org/site/excel/publications/CBM-50-Anniversary-Publication.pdf'),
        ('bermuda', r'bermuda government|government of bermuda|commissioners of currency', 1930, 1969, 'https://sites.krieger.jhu.edu/iae/files/2019/12/John_Stanton_Bermuda.pdf'),
        ('bahamas', r'bahamas government|government of the bahamas|commissioners of currency', 1921, 1965, 'https://www.centralbankbahamas.com/viewPDF/documents/2019-06-20-05-30-57-Rawson-Square-Exhibit.pdf'),
    ]
    for name, pattern, first, last, url in island:
        if country == name and first <= year <= last and _matches(pattern, issuer):
            factor = _unit(unit)
            if year == 1971 and _matches(r'pence|penny|pennies', unit): return None
            if year > 1971 and _matches(r'pence|penny|pennies', unit): factor = .01
            return gb(name.title() + ' public currency', factor, url, 'One local pound = one pound sterling.')
    if country == 'cyprus' and 1930 <= year <= 1971 and _matches(r'government|republic|currency board', issuer):
        factor = .001 if unit in ('mil', 'mils') and year >= 1955 else _unit(unit)
        return gb('Cyprus currency board', factor, 'https://www.centralbank.cy/images/media/pdf/CBC_book_EN.pdf', '1,000 mils = one pound; the sterling link ended in 1972.')
    if _matches(r'east african currency board', issuer) and country in ('east africa', 'british east africa', 'kenya', 'uganda', 'tanganyika') and 1922 <= year <= 1966:
        return gb('East African Currency Board', _unit(unit), 'https://www.centralbank.go.ke/currency-history/', '20 shillings = one pound sterling.')
    if _matches(r'west african currency board', issuer) and country in ('british west africa', 'west africa', 'nigeria', 'gold coast', 'gambia', 'sierra leone') and 1916 <= year <= 1964:
        return gb('West African Currency Board', _unit(unit), 'https://www.elibrary.imf.org/view/journals/024/1951/001/article-A002-en.xml', 'Board pounds were at sterling parity; 20 shillings = one pound.')
    if country == 'straits settlements' and 1907 <= year <= 1938 and _matches(r'government|straits settlements', issuer):
        return gb('Straits Settlements government', _unit(unit, dollar_factor=7/60), 'https://fraser.stlouisfed.org/files/docs/publications/books/conant_1915.pdf', 'One dollar = 2 shillings 4 pence sterling; 100 cents = one dollar.')
    if country in ('malaya', 'malaya and british borneo') and 1940 <= year <= 1966 and _matches(r'commissioners of currency.*malaya|currency board.*malaya', issuer):
        return gb('Malayan currency boards', _unit(unit, dollar_factor=7/60), 'https://alumni.bnm.gov.my/web/guest/significant-milestones-in-the-malaysian-foreign-exchange-market', 'One board dollar = 2 shillings 4 pence sterling; excludes the new 1967 national currencies.')
    # Regional issuer aliases are independent of a sometimes-empty country.
    if _matches(r'(?:british caribbean|caribbean territories).*currency board|currency board.*(?:british caribbean|eastern caribbean territories)', issuer) and 1950 <= year <= 1964:
        return gb('British Caribbean Currency Board', _unit(unit, dollar_factor=1/4.8), 'https://cdn.eccb-centralbank.org/documents/2022-05-11-08-19-03-sijune2012.pdf', '4.80 board dollars = one pound sterling.')
    if 'east caribbean currency authority' in issuer and 1965 <= year <= 1975:
        return gb('East Caribbean Currency Authority', _unit(unit, dollar_factor=1/4.8), 'https://cdn.eccb-centralbank.org/documents/2022-05-11-08-19-03-sijune2012.pdf', '4.80 EC dollars = one pound sterling; the USD peg began in July 1976.')
    if country == 'australia' and _matches(r'commonwealth bank|treasury of the commonwealth|reserve bank of australia', issuer):
        factor = _unit(unit, 1 if year <= 1929 else .8)
        if 1910 <= year <= 1929 or 1932 <= year <= 1965:
            return gb('Australian predecimal currency', factor, 'https://www.ausstats.abs.gov.au/ausstats/free.nsf/LookupAttach/1301.0Publication01.01.66200/%24File/13010_1966_DecimalCurrency.pdf', 'Australian pounds were sterling at par through 1929, then A£125 = £100 sterling from 1932.')
    if country == 'new zealand' and 'reserve bank of new zealand' in issuer and 1949 <= year <= 1959:
        return gb('New Zealand predecimal currency', _unit(unit), 'https://www.rbnz.govt.nz/-/media/project/sites/rbnz/files/statistics/series/b/b1/new-zealand-dollar-exchange-rate-changes-before-1985.pdf', 'Sterling parity restored in August 1948; the 1967 transition needs a more precise date.')
    if country == 'fiji' and 'government of fiji' in issuer:
        if 1934 <= year <= 1966:
            return gb('Fiji predecimal currency', _unit(unit, 100/111), 'https://documents1.worldbank.org/curated/en/908821468030848039/pdf/multi0page.pdf', 'Fiji £111 = £100 sterling.')
        if 1969 <= year <= 1971:
            return gb('Fiji decimal currency', _unit(unit, dollar_factor=100/209), 'https://www.elibrary.imf.org/display/book/9781451971477/ch023.xml', 'Fiji $2.09 = one pound sterling.')
    if country == 'united states of america' and 1800 <= year <= 1863 and re.fullmatch(r'dollars?', unit) and _matches(r'bank|insurance', issuer) and 'private' in plain(note.get('issue_type')):
        return _rule('US private bank dollar face claim', 'USA', 'USD', 1,
                     'https://www.federalreserve.gov/econres/notes/feds-notes/a-brief-history-of-bank-notes-in-the-united-states-and-some-lessons-for-stablecoins-20260206.html',
                     'US dollar face-claim benchmark before issuer credit discounts. This is not the note’s actual market purchasing power or a redemption amount.')
    colony = colonial_reference(note, year, unit)
    if colony: return colony
    if country == 'bahrain' and 'bahrain currency board' in issuer and 1964 <= year <= 1966:
        factor = .75 if re.fullmatch(r'dinars?', unit) else .00075 if re.fullmatch(r'fils?', unit) else None
        return gb('Bahrain Currency Board first-issue parity', factor, BOARD_URL,
                  'One dinar = 15 shillings sterling at first issue in October 1965. ' +
                  ('The 1964 authorization year comparison applies that later first-issue parity as a benchmark; it is not a 1964 traded exchange value.' if year == 1964 else '1,000 fils = one dinar.'))
    if country == 'russia' and year == 1909 and 'state bank of the russian empire' in issuer and re.fullmatch(r'rou?bles?', unit):
        return _rule('Russian prewar ruble face parity', 'USA', 'USD', .515,
                     'https://www.congress.gov/61/crecb/1909/07/08/GPO-CRECB-1909-pt4-v44-19.pdf',
                     'US purchasing-power benchmark at the contemporary approximate gold-era equivalence of one ruble to US$0.515; not extended to wartime or Soviet paper.')
    if country == 'germany' and year == 1904 and _matches(r'reichsbank|reichsschuldenverwaltung', issuer) and re.fullmatch(r'marks?', unit):
        return _rule('German prewar mark face parity', 'USA', 'USD', .238,
                     'https://www.congress.gov/59/crecb/1906/03/22/GPO-CRECB-1906-pt5-v40-3-1.pdf',
                     'US purchasing-power benchmark at the contemporary approximate gold-era equivalence of one mark to US$0.238; not extended to wartime paper, Rentenmark or Reichsmark.')
    if country in ('korea', 'korea (japanese occupation)') and _matches(r'bank of chosen|bank of chosun', issuer) and 1909 <= year <= 1944 and re.fullmatch(r'yen', unit):
        return _rule('Bank of Chosen yen parity', 'JPN', 'JPY', 1,
                     'https://sites.krieger.jhu.edu/iae/files/2017/12/Bank-of-Chosen_Jieun-Park.pdf',
                     'Japanese purchasing-power benchmark at the Bank of Chosen yen’s one-for-one Japanese-yen relationship; this is not Korean domestic CPI.')
    if country == 'burma' and 'reserve bank of india' in issuer and 'currency board' not in issuer and 1938 <= year <= 1941:
        factor = .075 if re.fullmatch(r'rupees?', unit) else .075/16 if re.fullmatch(r'annas?', unit) else None
        return gb('RBI Burmese rupee official parity', factor, 'https://rbi.org.in/Scripts/pm_burma.aspx', 'RBI issued the Burmese rupee within the Indian monetary regime; one rupee = 1 shilling 6 pence sterling.')
    if country == 'south africa' and 'south african reserve bank' in issuer and 1933 <= year <= 1960:
        return gb('South African predecimal currency', _unit(unit), 'https://www.resbank.co.za/en/home/publications/publication-detail-pages/speeches/speeches-by-governors/2001/200', 'South African pounds retained sterling parity after 1932 until decimalization in 1961.')
    if country == 'belgian congo' and 1949 <= year <= 1959 and _matches(r'banque du congo belge|banque centrale du congo|centrale bank.*congo', issuer):
        factor = 1 if re.fullmatch(r'francs?', unit) else .01 if re.fullmatch(r'centimes?', unit) else None
        if factor is not None:
            return _rule('Belgian Congo franc parity', 'BEL', 'EUR', factor/40.3399,
                         'https://documents1.worldbank.org/curated/en/651211468234272570/pdf/AF230V10ESW0French0Box46477B0PUBLIC.pdf',
                         'Belgian purchasing-power benchmark at the Congo/Belgian franc parity before 1960, followed by the fixed Belgian franc/euro conversion. Local prices and exchange restrictions are not measured.')
    if country == 'jamaica' and 1940 <= year <= 1968 and _matches(r'government of jamaica|bank of jamaica', issuer):
        return gb('Jamaican predecimal currency', _unit(unit), 'https://unctad.org/system/files/official-document/poedmm176.en.pdf', 'One Jamaican pound = one pound sterling under the currency-board regime, retained by the central bank.')
    if country == 'tonga' and 1937 <= year <= 1966 and _matches(r'government|treasury', issuer):
        return gb('Tongan predecimal currency', _unit(unit, .8), 'https://www.reservebank.to/index.php/banknotes/history-of-the-tongan-paanga', 'From 1936 one sterling pound = 1.25 Tongan pounds; decimalization occurred in 1967.')
    if country in ('saint helena', 'st. helena', 'st helena') and 1976 <= year and _matches(r'government.*helena|currency commissioners', issuer):
        factor = 1 if re.fullmatch(r'pounds?', unit) else .01 if re.fullmatch(r'pence', unit) else None
        return gb('Saint Helena currency', factor, BOARD_URL, 'One Saint Helena pound = one pound sterling; 100 pence = one pound.')
    if country == 'seychelles' and 1937 <= year <= 1977 and _matches(r'government|currency board|commissioners of currency', issuer):
        factor = .075 if re.fullmatch(r'rupees?', unit) else .00075 if re.fullmatch(r'cents?', unit) else None
        return gb('Seychelles currency-board parity', factor, BOARD_URL, 'One rupee = 1 shilling 6 pence sterling; 100 cents = one rupee.')
    if country == 'philippines' and year == 1944 and 'treasury' in issuer and 'victory' in plain(note.get('series')):
        factor = .5 if re.fullmatch(r'pesos?', unit) else .005 if re.fullmatch(r'centavos?', unit) else None
        if factor is not None:
            return _rule('Philippine Victory peso official parity', 'USA', 'USD', factor,
                         'https://elibrary.judiciary.gov.ph/thebookshelf/showdocs/5/76794',
                         'US purchasing-power benchmark at the November 1944 legal rate of two Victory pesos per dollar; applies to the explicit Treasury Victory issue, not Japanese or emergency money.')
    if country == 'india' and 1928 <= year <= 1946 and _matches(r'government of india|reserve bank of india', issuer):
        factor = .075 if re.fullmatch(r'rupees?', unit) else .075/16 if re.fullmatch(r'annas?', unit) else None
        return gb('Indian official rupee parity', factor, 'https://api.parliament.uk/historic-hansard/commons/1927/jun/20/currency', 'The 1927 statutory parity was one rupee = 1 shilling 6 pence sterling; excludes princely and occupation currencies.')
    if country in ('ceylon', 'sri lanka') and 1948 <= year <= 1965 and _matches(r'central bank of ceylon|government of ceylon', issuer):
        factor = 1/13.3336 if re.fullmatch(r'rupees?', unit) else 1/1333.36 if re.fullmatch(r'cents?', unit) else None
        return gb('Ceylon official rupee parity', factor, 'https://www.cbsl.gov.lk/sites/default/files/cbslweb_documents/publications/60th_anniversary_commemorative_volume_of_the_central_bank_of_sri_lanka.pdf', 'The official parity was 13.3336 rupees per pound sterling; the 1966 transition is excluded.')
    if country == 'new zealand' and 'reserve bank of new zealand' in issuer and 1960 <= year <= 1967:
        factor = _unit(unit, 2)
        if factor is not None:
            return _rule('New Zealand decimal conversion', 'NZL', 'NZD', factor, 'https://www.legislation.govt.nz/act/public/1964/27/en/latest/', 'New Zealand consumer-price comparison with the statutory conversion of one old pound = two NZ dollars. Old shillings equal ten cents; no sterling parity is assumed.')
    if country == 'brunei' and year >= 1967 and _matches(r'government of brunei|brunei currency board|brunei.*monetary|brunei.*central bank', issuer):
        factor = 1 if re.fullmatch(r'ringgit|dollars?', unit) else .01 if re.fullmatch(r'sen|cents?', unit) else None
        if factor is not None:
            return _rule('Brunei–Singapore interchangeability', 'SGP', 'SGD', factor, 'https://www.mas.gov.sg/currency/brunei-singapore-currency-interchangeability-agreement', 'Singapore purchasing-power benchmark at the 1967 currency interchangeability agreement’s one-for-one parity; this is not Brunei domestic CPI.')
    if country in ('netherlands indies', 'netherlands east indies', 'dutch east indies') and year in (1939, 1940) and _matches(r'javasche bank|government.*netherlands|nederlandsch.ind', issuer):
        factor = 1 if re.fullmatch(r'gulden|guilders?', unit) else .01 if re.fullmatch(r'cents?', unit) else None
        if factor is not None:
            return _rule('Netherlands Indies recorded exchange', 'NLD', 'EUR', factor / (.999 if year == 1939 else .997) / 2.20371, 'https://nationalaccounts.niwi.knaw.nl/table/balance6.htm', 'Dutch purchasing-power benchmark using the recorded 1939 or 1940 Indies-guilder rate against the Dutch guilder. This is not local Indies CPI.')
    if country == 'netherlands antilles' and _matches(r'bank van de nederlandse antillen|bank of the netherlands antilles|centrale bank', issuer) and (1947 <= year <= 1970 or 1972 <= year <= 2024):
        factor = 1 if re.fullmatch(r'gulden|guilders?', unit) else .01 if re.fullmatch(r'cents?', unit) else None
        if factor is not None:
            return _rule('Netherlands Antilles official parity', 'USA', 'USD', factor / (1.88585 if year <= 1970 else 1.79), 'https://www.elibrary.imf.org/view/journals/002/2003/160/article-A001-en.xml', 'US purchasing-power benchmark at the official Antilles guilder peg; the December 1971 parity transition is excluded.')
    if country == 'barbados' and 1938 <= year <= 1974 and _matches(r'government|treasury|central bank', issuer):
        return gb('Barbados dollar sterling parity', _unit(unit, dollar_factor=1/4.8), 'https://cdn.centralbank.org.bb/documents/2022-02-15-08-11-30-CBBChronicle2005.pdf', '4.80 Barbados dollars = one pound sterling, unchanged from 1938 until the 1975 USD repeg.')
    if country == 'hong kong' and (1936 <= year <= 1940 or 1946 <= year <= 1966) and _matches(r'government of hong kong|hongkong.*shanghai|chartered bank|mercantile bank', issuer):
        return gb('Hong Kong sterling parity', _unit(unit, dollar_factor=1/16), 'https://www.hkma.gov.hk/media/chi/publications-and-research/reference-materials/monetary/1-1.pdf', 'HK$16 = one pound sterling; 1935 and 1967 transition years excluded.')
    if country == 'philippines' and (1903 <= year <= 1941 or 1945 <= year <= 1964) and _matches(r'philippine national bank|bank of the philippine islands|treasury|central bank of the philippines', issuer):
        factor = .5 if re.fullmatch(r'pesos?|piso', unit) else .005 if re.fullmatch(r'centavos?', unit) else None
        if factor is not None:
            return _rule('Philippine official peso parity', 'USA', 'USD', factor,
                         'https://www.bsp.gov.ph/Pages/CoinsAndNotes/HistoryOfPhilippineMoney/HistoryOfPhilippineMoney.aspx',
                         'US purchasing-power benchmark at the official parity of two pesos per US dollar; actual paper-money exchange discounts are not measured.',
                         ('https://www.bsp.gov.ph/Sites/researchsite/SitePages/ResearchBlog/ResearchBlogDisp.aspx?ItemId=14',))
    if 'banco nacional ultramarino' in issuer and ((country in ('timor', 'portuguese timor') and 1958 <= year <= 1974) or (country in ('portuguese guinea', 'cape verde') and 1963 <= year <= 1973)) or ('banco de angola' in issuer and country == 'angola' and 1953 <= year <= 1973):
        factor = 1 if re.fullmatch(r'escudos?', unit) else .01 if re.fullmatch(r'centavos?', unit) else None
        if factor is not None:
            url = 'https://files.diariodarepublica.pt/gratuitos/1s/1957/12/27700.pdf' if 'timor' in country else 'https://www.imf.org/-/media/websites/imf/imported-full-text-pdf/external/pubs/ft/wp/2009/_wp09146.pdf'
            return _rule('Portuguese overseas escudo official parity', 'PRT', 'EUR', factor/200.482, url,
                         'Portuguese purchasing-power benchmark at the official one-for-one overseas/metropolitan escudo rate. Transfer delays and local price differences are not measured.')
    if country == 'mozambique' and 'banco nacional ultramarino' in issuer and 1933 <= year <= 1974:
        factor = 1 if re.fullmatch(r'escudos?', unit) else .01 if re.fullmatch(r'centavos?', unit) else None
        if factor is not None:
            return _rule('Mozambique BNU escudo', 'PRT', 'EUR', factor/200.482,
                         'https://files.diariodarepublica.pt/gratuitos/1s/1932/04/09602.pdf',
                         'Portuguese purchasing-power benchmark under the metropolitan escudo regime; excludes the separate Mozambique Company gold-centavo currency.')
    return french_reference(note, year, unit) or worldbank_reference(note, year, unit)


def colonial_reference(note, year, unit):
    country, issuer = plain(note.get('country')), plain(note.get('issuer'))
    if 'connecticut' in country or 'private' in plain(note.get('issue_type')): return None
    if not 1770 <= year <= 1780 or _matches(r'continental|old tenor|new tenor|counterfeit', ' '.join(plain(note.get(k)) for k in ('issuer', 'series'))): return None
    relations = [
        ('connecticut', 6, .75), ('rhode island', 6, .75), ('massachusetts', 6, .75),
        ('new hampshire', 6, .75), ('virginia', 6, .75),
        ('north carolina', 8, .5625), ('new york', 8, .5625),
        ('pennsylvania', 7.5, .6), ('new jersey', 7.5, .6), ('delaware', 7.5, .6), ('maryland', 7.5, .6),
        ('south carolina', 14/3, .9), ('georgia', 14/3, .9),
    ]
    for name, shillings_per_dollar, sterling_per_pound in relations:
        normalized_issuer = issuer.replace('-', ' ')
        if name not in country or name not in normalized_issuer or not _matches(r'colony|province|assembly|state|mayor', issuer): continue
        local_pounds = _unit(unit)
        if re.fullmatch(r'dollars?', unit):
            local_pounds = shillings_per_dollar / 20
        if local_pounds is None: return None
        usd = year >= 1774
        return _rule(name.title() + ' lawful money', 'USA' if usd else 'GBR', 'USD' if usd else 'GBP',
                     local_pounds * (20 / shillings_per_dollar if usd else sterling_per_pound),
                     'https://research.colonialwilliamsburg.org/DigitalLibrary/view/index.cfm?doc=ResearchReports%5CRR0066.xml',
                     ('US' if usd else 'UK') + ' purchasing-power benchmark at lawful-money face parity. Wartime paper-money depreciation, local prices and redemption are not measured.')
    return None


def french_reference(note, year, unit):
    """French-franc and colonial franc benchmarks with explicit issue identities."""
    country, issuer = plain(note.get('country')), plain(note.get('issuer'))
    if country in ('french indo-china', 'french indochina') and _matches(r'banque de l.indochine|gouvernement|government|institut d.emission', issuer):
        sub = 1 if re.fullmatch(r'piastres?', unit) else .01 if re.fullmatch(r'cents?|centimes?', unit) else None
        factor = 10 if 1931 <= year <= 1944 or year == 1954 else 17 if 1946 <= year <= 1952 else None
        if sub is not None and factor is not None:
            return _rule('Indochinese piastre official franc parity', 'FRA', 'EUR', sub*factor/100/6.55957,
                         'https://www.elibrary.imf.org/display/book/9781616351663/ch005.xml',
                         'French purchasing-power benchmark at the official piastre/franc parity; local wartime prices and exchange restrictions are not measured.',
                         ('https://www.govinfo.gov/content/pkg/SERIALSET-09748_00_00-009-0008-0000/pdf/SERIALSET-09748_00_00-009-0008-0000.pdf',))
    sub = .01 if re.fullmatch(r'centimes?', unit) else 1 if re.fullmatch(r'francs?(?: cfa| cfp)?', unit) else None
    if sub is None: return None
    old_francs, source, family = None, FRENCH_COLONIAL_URL, ''
    if country == 'comoros' and _matches(r'banque de madagascar et des comores|institut d.emission des comores|banque centrale des comores', issuer) and 1960 <= year <= 1993:
        old_francs, family, source = 2, 'Comorian franc official parity', 'https://webstat.banque-france.fr/explore/dataset/tableaux_rapports_preetablis/files/468185531b0d252e3411285e7c3b155e/download/'
    if country in ('guadeloupe', 'martinique', 'french guiana', 'french antilles') and _matches(r'banque de la guadeloupe|banque de la martinique|banque de la guyane|caisse centrale de la france|institut d.emission des departements', issuer):
        if 1944 <= year <= 1959:
            old_francs, family, source = 1, 'French American departments franc parity', 'https://www.iedom.fr/IMG/pdf/50_iedom_panneaux.pdf'
        elif 1963 <= year <= 1998 and 'institut' in issuer:
            old_francs, family, source = 100, 'French American departments new-franc parity', 'https://www.legifrance.gouv.fr/loda/id/JORFTEXT000000508933'
    if country == 'tunisia' and 1891 <= year <= 1956 and _matches(r'regence de tunis|tresorerie.*tunisi|tresor tunisien', issuer):
        old_francs, family, source = 1, 'Tunisian franc parity', 'https://musee.bct.gov.tn/fr/collections'
    if country in ('algeria', 'tunisia') and 'banque de l.algerie' in issuer.replace("'", '.') and 1870 <= year <= 1959:
        old_francs, family, source = 1, 'Algerian franc parity', 'https://www.imf.org/external/pubs/ft/ar/archive/pdf/ar1957.pdf'
    if country == 'madagascar' and 'institut d.emission malgache' in issuer.replace("'", '.') and 1963 <= year <= 1972:
        old_francs, family, source = 2, 'Malagasy franc official parity', 'https://www.elibrary.imf.org/view/journals/024/1969/002/article-A006-en.xml'
    if country == 'france' and 'banque de france' in issuer and 1870 <= year <= 1959:
        old_francs, family = 1, 'Metropolitan French old franc'
    african = (_matches(r'banque de l.afrique occidentale|banque de madagascar|caisse centrale de la france', issuer)
               and _matches(r'africa|madagascar', country))
    cfa = (_matches(r'bceao|banque centrale des etats de l.afrique de l.ouest|institut d.emission de l.afrique equatoriale|banque de l.afrique occidentale', issuer) and _matches(r'africa|senegal|togo|benin|ivory coast|cote d.ivoire|niger|burkina|cameroon|chad|congo|gabon', country))
    cfa = cfa or (country == 'madagascar' and 'banque de madagascar' in issuer and year <= 1961)
    if african and 1870 <= year <= 1944:
        old_francs, family = 1, 'French colonial franc'
    elif cfa and 1946 <= year <= 1993:
        if year == 1948: return None
        old_francs = 1.7 if year <= 1947 else 2
        family, source = 'CFA franc parity', CFA_URL
    elif cfa and year >= 1995:
        old_francs, family, source = 1, 'CFA franc parity', CFA_URL
    pacific = _matches(r'new caledonia|french polynesia|french pacific territories|tahiti|new hebrides', country) and _matches(r'banque de l.indochine|institut d.emission d.outre.mer|ieom|noumea', issuer)
    if pacific and 1870 <= year <= 1944:
        old_francs, family = 1, 'Pacific French franc'
    elif pacific and 1950 <= year <= (1968 if 'new hebrides' in country else 1998):
        old_francs, family, source = 5.5, 'CFP franc parity', CFP_URL
    if old_francs is None: return None
    if 'cfa' in unit and 'CFA' not in family or 'cfp' in unit and 'CFP' not in family: return None
    return _rule(family, 'FRA', 'EUR', sub * old_francs / 100 / 6.55957,
                 source, 'French purchasing-power benchmark at documented franc parity, with 100 old francs = one 1960 franc and 6.55957 French francs = one euro. This is not a measured local price basket.', ('https://www.vie-publique.fr/files/rapport/pdf/004001513.pdf', 'https://www.ecb.europa.eu/press/pr/date/1998/html/pr981231_2.en.html'))


@lru_cache(maxsize=1)
def historical_data():
    return json.loads((Path(__file__).resolve().parent / 'data' / 'banknote-historical-economics.json').read_text())


def cpi_values(iso, series):
    """Extend missing historical observations at a common 2010 index base."""
    values = dict(series.get('values', {}))
    historic = historical_data().get('cpi', {}).get(iso, {})
    if iso == 'USA':
        # HSUS table Cc1, 1982–84=100; use the modern base, never splice
        # the differing historical reconstructions at their 1800 boundary.
        early = [8.070, 7.654, 8.735, 10.649, 13.810, 12.230, 13.727, 11.065, 12.146, 10.649, 10.233, 9.734, 9.484, 9.318, 8.902, 8.819, 9.151, 9.401, 9.567, 9.900, 10.982, 12.562, 13.228, 12.729, 12.313, 12.313]
        anchors = [values.get(str(y)) for y in (1982, 1983, 1984)]
        if all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0 for v in anchors):
            for year, value in enumerate(early, 1774): values.setdefault(str(year), value * sum(anchors) / 300)
            return values, True
        return values, False
    old_anchor, new_anchor = historic.get('2010'), values.get('2010')
    if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v > 0 for v in (old_anchor, new_anchor)):
        return values, False
    added = False
    for year, value in historic.items():
        if year not in values:
            values[year] = value * new_anchor / old_anchor
            added = True
    return values, added


# These date gates identify the unit represented by the World Bank series.
# Earlier predecessor units may be back-adjusted in that dataset; never apply
# them to printed pounds, old currencies or occupation notes by country alone.
WORLD_BANK_UNITS = {
    'macau': ('MAC', 1960, r'patacas?|avos?'),
    'macao': ('MAC', 1960, r'patacas?|avos?'),
    'iran': ('IRN', 1960, r'rials?'),
    'kenya': ('KEN', 1967, r'shillings?'),
    'nigeria': ('NGA', 1973, r'naira|kobo'),
    'colombia': ('COL', 1960, r'pesos?|centavos?'),
    'thailand': ('THA', 1960, r'baht|satang'),
    'bahamas': ('BHS', 1970, r'dollars?|cents?'),
    'belize': ('BLZ', 1973, r'dollars?|cents?'),
    'british honduras': ('BLZ', 1960, r'dollars?|cents?'),
    'cayman islands': ('CYM', 1972, r'dollars?|cents?'),
    'cuba': ('CUB', 1960, r'pesos?|centavos?'),
    'egypt': ('EGY', 1960, r'(?:egyptian )?pounds?|piastres?'),
    'kuwait': ('KWT', 1961, r'dinars?|fils?'),
    'mauritius': ('MUS', 1960, r'rupees?|cents?'),
    'maldives': ('MDV', 1960, r'rufiyaa|rupees?|laari'),
    'morocco': ('MAR', 1960, r'dirhams?|centimes?'),
    'lebanon': ('LBN', 1960, r'livres?|pounds?|piastres?'),
    'malawi': ('MWI', 1971, r'kwacha|tambala'),
    'fiji': ('FJI', 1969, r'dollars?|cents?'),
    'solomon islands': ('SLB', 1977, r'dollars?|cents?'),
    'gambia': ('GMB', 1971, r'dalasis?|bututs?'),
    'brunei': ('BRN', 1967, r'dollars?|ringgit|sen|cents?'),
    'seychelles': ('SYC', 1960, r'rupees?|cents?'),
    'hong kong': ('HKG', 1960, r'dollars?|cents?'),
    'singapore': ('SGP', 1967, r'dollars?|cents?'),
    'philippines': ('PHL', 1960, r'pesos?|piso|centavos?|sentimos?'),
    'indonesia': ('IDN', 1967, r'rupiah|sen'),
    'south africa': ('ZAF', 1961, r'rand|cents?'),
}


@lru_cache(maxsize=1)
def historical_fx_data():
    return json.loads((Path(__file__).resolve().parent / 'data' / 'banknote-historical-fx.json').read_text())


def worldbank_reference(note, year, unit):
    country, issuer = plain(note.get('country')), plain(note.get('issuer'))
    rule = WORLD_BANK_UNITS.get(country)
    if not rule or year < rule[1] or not re.fullmatch(rule[2], unit): return None
    evidence = ' '.join(plain(note.get(k)) for k in ('issuer', 'series', 'issue_type'))
    if _matches(r'japanese|occupation|private|scrip|counterfeit|coupon|military|guerrilla|convertible peso', evidence): return None
    if not (_matches(r'bank|government|treasury|currency board|monetary|state', issuer) or (country in ('macau', 'macao') and 'banco nacional ultramarino' in issuer)): return None
    iso = rule[0]
    rate = historical_fx_data().get('rates', {}).get(iso, {}).get(str(year))
    if not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0: return None
    divisor = 1000 if unit in ('fil', 'fils') else 100 if _matches(r'cent|satang|kobo|piastre|laari|tambala|butut|sen|avo', unit) else 1
    result = _rule('World Bank official annual ' + iso + ' exchange rate', 'USA', 'USD', 1/rate/divisor,
                   'https://data.worldbank.org/indicator/PA.NUS.FCRF?locations=' + iso,
                   'US purchasing-power benchmark: the published official annual exchange rate converts the face amount to then-current USD, then US CPI expresses it in today’s dollars. Local prices, unofficial rates and exchange restrictions may differ.')
    result['kind'] = 'historical_fx'
    return result


def unavailable_reason(note, years, unit):
    country, issuer = plain(note.get('country')), plain(note.get('issuer'))
    evidence = ' '.join(plain(note.get(k)) for k in ('issuer', 'series', 'issue_type'))
    if _matches(r'katis?|rubber|rice|kilograms?|pounds? of', unit):
        return 'This denomination is a commodity quantity, not a monetary face value. A dated commodity price or redemption contract is needed for a money comparison.'
    if _matches(r'counterfeit', evidence):
        return 'This is identified as a counterfeit issue. Its printed face amount does not establish a redeemable monetary claim or historical purchasing power.'
    if country in ('french indo-china', 'french indochina') and any(y in (1930, 1945, 1953) for y in years):
        return 'The official piastre/franc parity changed during the comparison year. A dated issue or a sourced within-year range is needed; one annual parity has not been assumed.'
    if country == 'hong kong' and any(y in (1935, 1941, 1945) for y in years):
        return 'This comparison year includes a monetary-standard or wartime transition. A dated issue or sourced annual benchmark is needed for this Hong Kong dollar.'
    if country == 'malawi' and unit == 'kwacha' and min(years) < 1971:
        return 'The recorded comparison year predates the kwacha’s 1971 introduction. Verify the Year (Series) field against the law or issue-series date; the saved date has not been changed.'
    if country == 'cayman islands' and 'dollar' in unit and min(years) < 1972:
        return 'The recorded comparison year predates Cayman dollar notes in 1972. Verify whether Year (Series) is the 1971 currency-law date or the note’s series year.'
    if 'japanese' in issuer and country != 'japan':
        return 'This Japanese occupation issue needs a sourced wartime exchange or price benchmark. The same-named national currency is not interchangeable with this note.'
    if _matches(r'occupation|military', evidence):
        return 'Historical exchange or price evidence for this occupation or military currency is not established. Verify the issue identity and series year; ordinary national-currency rates have not been assumed.'
    if 'confederate' in country or 'confederate' in issuer:
        return 'Confederate paper depreciated sharply; a dated regional exchange or price benchmark is needed. Its dollars cannot be treated as US dollars at face value.'
    if 'private' in plain(note.get('issue_type')) or 'scrip' in plain(note.get('issue_type')):
        return 'This private or local issue needs evidence for its face claim and any monetary conversion; a national currency relationship has not been assumed.'
    year = str(min(years)) + ('–' + str(max(years)) if len(years) > 1 else '')
    return 'No sourced historical conversion is configured for this issuer’s ' + unit + ' in ' + year + '. A matching monetary relationship or local price series is needed; current same-named currency is not a substitute.'
