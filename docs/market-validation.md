# Market offers and colonial eligibility

Market rows must link to one specific lot. eBay accepts only `/itm/<id>` or
`/itm/<title>/<id>`; shop, category and search URLs are rejected. Direct dealer
links retain identity queries such as CNG `CoinID` and MA-Shops `id`. Redirects
are checked before reading liveness or images; search destinations, different
item identifiers and conflicting primary-title catalogue/date/grade/denomination
or seller evidence reject the offer. Recommendation sections cannot supply
buy/bid wording. A bot challenge on an exact item remains unknown, not ended.

Saved generic candidates are marked `unavailable` when the market is read. Both
row links and View listing pass through a fresh exact-item, identity and eligibility
check. If only eBay availability is unknown, they open the original saved item URL
for inspection. They never redirect to a fetched challenge or search destination.
Known ended, invalid, mismatched and ineligible offers remain blocked. Buying an
eBay offer still requires live availability before creating an Ordered record.
Unavailable/generic candidates cannot be filed.
Bought explicitly records a purchase already made and may therefore file an
otherwise valid exact listing after it ends. Photo extraction uses the primary
Product JSON-LD, page image metadata or an identified gallery, never arbitrary
recommendation thumbnails. These checks reduce false matches; unreadable pages
remain unverified and cannot supply independent identity evidence.

On 20 September 2026, the Canada 1937 $20 PMG 64 EPQ recommendation
([eBay 185386368846](https://www.ebay.ca/itm/185386368846)) was also ended.
The scan log recorded HTTP 403; the stored model claim said "Active eBay.ca
Buy It Now listing" and the old fallback admitted it with `verified: false`.
The row was marked unavailable without deleting its history. eBay now requires
an independently readable live listing: no model wording or future close can
override an unknown verdict. Legacy unverified offers move to Earlier
candidates instead of appearing as current recommendations. Buy rejects unknown
availability. View listing can open a known exact item during that transient
block, while clearing `verified` and moving a current candidate to Earlier.
The saved record remains available for retries and Bought; viewing creates no
collection record. Regression tests cover this exact 403, captcha, timeout,
inspection after a failed Buy, ended banners with recommendation controls,
existing saved rows, and recording purchases already made.

On 20 September 2026, the Martha Washington offer linked an eBay search page.
The matching exact item, [375423430457](https://www.ebay.com/itm/375423430457),
showed an ended-by-seller banner dated 3 July and the same $6,324.99 price.
It was hidden immediately; deployment quarantines its stored search URL too.
Its missing thumbnail is consistent with the wrong source, but does not prove
which image-fetch step failed. No replacement live offer was invented.

## Colonial recommendations versus collection groups

`market_colonial.py` separates recommendation eligibility from collection grouping
and holdings. Search scope is worldwide: colonies, protectorates, mandates, trust
territories, dependencies, condominiums, leased territories, client states and
military occupations. No fixed empire, territory or want-list limits discovery.
The legacy route shares territory periods in `banknote_catalog.py`, with stricter
market boundaries. A British/Commonwealth or US/Philippines collection group is
not proof of administration. Domestic US notes keep their separate themes;
documented British-American colonial issues can use the sourced route below.
Ordinary independent successor issues remain excluded, including saved candidates.

For undated issues and reissues the scan must provide the actual issue-year
range and a corroborating catalogue/issuing-bank source URL. The whole range
must fall within the administration years. Explicit later years or successor
institutions in the title/series override a misleading old printed date.

Additional territories, occupations and transition-year issues use an
`administration` object: relationship `kind`, administration `name`, matching
`territory`, ordered `year_start`/`year_end`, reference `source` URL and
issue-specific `evidence` excerpt. The candidate also needs an issuer, catalogue
identity, both actual issue years and an `issue_date_source` URL. The issue range
must fit the administration range (inclusive only with this detailed evidence).
Military occupation need not precede a country's original independence. Missing
evidence remains excluded; a year alone never invents a day/month cutoff.

Source attribution is retained in candidate JSON; these checks validate supplied
evidence structure and consistency, not an independent audit of the cited source.
Discovery must read real references and never invent URLs or history. Existing
known-territory dates retain conservative boundaries when detailed evidence is
absent. All sources, saved results, refreshed exact-listing titles and actions use
the same gate. No eligibility rule alters existing collection records.

Labels name the documented relationship (for example, “Japanese administration ·
military occupation”); dependencies and occupations are not automatically called
colonies. Supported administrations receive the same ranking priority. Specimens,
proofs, remainders, replicas, counterfeits and propaganda overprints remain outside
issued-currency recommendations; grade, live-listing and duplicate checks apply.

**Mark's explicit exception:** genuine Philippine VICTORY notes remain wanted,
including later signature varieties and Victory–Central Bank overprints after
independence. Philippine country, Victory type and a corresponding Pick number
identify the exception. When Pick is absent, explicit Victory Series 66/Victory-CBP
and a matching Philippine Commonwealth/Treasury/Central Bank issuer suffice; an
incompatible supplied Pick remains a conflict. A marketing keyword alone does not. Original-series Pick 94–101 and CBP Pick 117–124 are recognized with Victory
context. [Heritage’s Pick 120 catalogue record](https://currency.ha.com/itm/world-currency/philippines-victory-series-10-pesos-nd-1949-pick-120-pmg-choice-uncirculated-63-epq/p/64183-25004.s)
identifies the 1949 Victory issue. Original-series
notes receive “Philippine Victory issue” without inferring a colonial issue
date; identified CBP overprints receive “post-independence.” Existing quality,
exact listing, liveness and duplicate rules still apply.

Evidence for represented issues and important boundaries:

- [National Park Service: WWII currency](https://www.nps.gov/articles/000/currency-on-the-world-war-ii-home-front.htm)
  distinguishes Japanese occupation currency in the Philippines from emergency,
  propaganda, counterfeit and Victory issues.
- [Bank of Korea museum](https://www.bok.or.kr/eng/bbs/B0000338/view.do?menuNo=400390&nttId=10085252&pageIndex=1)
  identifies Bank of Joseon notes under Japanese occupation.
- [US Currency history](https://www.uscurrency.gov/history) covers British-American
  colonial notes and Allied military currency for occupied countries.
- Smithsonian examples: [Italy, 1943](https://americanhistory.si.edu/collections/object/nmah_1519256)
  and [Germany, 1944](https://americanhistory.si.edu/collections/nmah_1591210).
- [US State Department: Philippines](https://history.state.gov/countries/philippines):
  independence 4 July 1946.
- [BSP: English series](https://www.bsp.gov.ph/SitePages/CoinsAndNotes/EnglishSeries.aspx):
  Victory notes brought in 1944 and Central Bank overprints issued in 1949.
- [Commonwealth Executive Order 25 of 1944](https://lawphil.net/executive/execord/eo1944/eo_25_1944.html):
  original Victory currency; the printed date does not date every later variety.
- [Portuguese official gazette: 1964 BNU Guiné series](https://diariodarepublica.pt/dr/detalhe/aviso/237148):
  the 1964 Portuguese Guinea 1000 escudos is within colonial administration.
- [Guinea-Bissau declaration](https://history.state.gov/historicaldocuments/frus1969-76ve06/d69)
  and [recognition](https://history.state.gov/countries/guinea-bissau):
  1973 declaration / 1974 Portuguese recognition; both transition years excluded.
- [Algeria](https://history.state.gov/countries/algeria): 1962 transition;
  [Mozambique](https://history.state.gov/historicaldocuments/frus1969-76v28/d104),
  [Angola](https://history.state.gov/historicaldocuments/frus1969-76v28/d136),
  [Cabo Verde](https://1997-2001.state.gov/background_notes/cape_verde_0598_bgn.html): 1975 transitions.
- [RBI history](https://www.rbi.org.in/CommonPerson/english/history/Scripts/BriefHistory.aspx):
  issuing-bank continuity across political changes means issuer alone is insufficient.
- [RBA banknote history](https://banknotes.rba.gov.au/australias-banknotes/history/)
  and [Bank of Canada history](https://www.bankofcanada.ca/wp-content/uploads/2010/07/illustrated-history.pdf):
  colonial notes differ from Commonwealth/federal and Dominion issues.

Tests cover URL/redirect identity, preserved dealer query IDs, recommendation
isolation, stored/action quarantine, pre/post/boundary years, date ranges,
successor issuers, domestic US themes, unchanged collection families and the
Victory exception. History-position tests cover reload/layout changes and
query/anchor preservation; market presentation tests cover existing payloads.
