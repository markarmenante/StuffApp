# Banknote entity coverage

Verified 25 October 2026. `banknote_entities.py` supplies the historical entity
pills beneath the existing collection group headings. It is a curated banknote
collecting roster, not an exhaustive list of every territory ever administered
by an empire, and it makes no claim that every political territory issued notes.
The pills themselves use the existing filing groups and do not rewrite records.
The subsequent Afars spelling correction described below uses the shared
catalogue's existing audited country-normalization and display-position paths.

## Scope and evidence states

The roster contains 194 entities: 152 with documented circulating note issues,
one with no separate territorial circulating banknote series, and 41 whose
separate issuance is not established. It covers every identity already named in
`banknote_catalog.py`'s period, historic, dependency, overseas and American
colonial rosters; all 35 subjects of the existing colonial wantlist; additional
territorial and regional issues represented in The Banknote Book; and selected
related territories where regional circulation must not be mistaken for a
separate issue. Unlisted identities in the authorized collection also appear
as held pills, so an omission from the curated roster does not hide a holding.

| Existing group key | Entities | Documented issue | No separate series | Unresolved |
| --- | ---: | ---: | ---: | ---: |
| british | 88 | 73 | 1 | 14 |
| french | 40 | 33 | 0 | 7 |
| spanish | 6 | 2 | 0 | 4 |
| portuguese | 10 | 9 | 0 | 1 |
| dutch | 6 | 6 | 0 | 0 |
| belgian | 4 | 3 | 0 | 1 |
| german | 10 | 4 | 0 | 6 |
| italian | 5 | 2 | 0 | 3 |
| us | 7 | 4 | 0 | 3 |
| japanese | 10 | 10 | 0 | 0 |
| danish | 4 | 4 | 0 | 0 |
| joint | 3 | 1 | 0 | 2 |
| other | 1 | 1 | 0 | 0 |

`issued=True` means a circulating issue is documented within the stated entity's
scope, including catalogued private/local issues where noted. It does not mean
every date, issuer or object sold under that name is eligible. `issued=False` is
reserved for the scoped, corroborated Pitcairn finding below. `issued=None`
means unresolved; it is never inferred to mean “did not issue.” A catalogue's
missing chapter, modern use of another currency, specimen, fantasy note or
commemorative paper is not sufficient evidence of historical nonissuance or of
a circulating issue. Sources on unresolved entries provide regional context
or research starting points, not proof of absence.

The visible states are green for a held entity, yellow for a documented issuer
without a held record, neutral for the documented nonissuer, and a distinct
question-mark/dashed state for unresolved issuance. Held records take priority;
these pills report the collection's recorded coverage, not an authentication or
circulation-grade assessment of an individual object.

## Primary and catalogue references

The default positive evidence is the publisher's [The Banknote Book country and
issuer index](https://www.greysheet.com/world-paper-money-prices), which identifies
issuing authorities within territorial chapters. A chapter for a modern country
alone does not prove colonial issuance. In particular, German New Guinea's
Australian military administration, later national issues of African countries,
and metropolitan currency circulating abroad do not establish a separate issue
under the earlier administration. Those cases remain unresolved where the
historical issue was not established.

The following references resolve important boundaries and less familiar entries;
individual definitions also retain source URLs and explanatory notes.

| Entities or question | Evidence and interpretation |
| --- | --- |
| British American colonies and United States | [US Currency Education Program history](https://www.uscurrency.gov/history) documents colonial paper and subsequent federal currency. Named colonies remain distinct from later state/federal issues. |
| Portuguese overseas issues | [Banco Nacional Ultramarino's institutional history](https://www.bnu.tl/Institucional/Historia/Paginas/Historia-do-BNU.aspx), with The Banknote Book's issuer chapters, supports the territorial BNU issues. Nyassa Company is retained from the legacy wantlist as **unresolved**; the old wantlist is not proof of issuance. |
| Central African regional currencies | [BEAC's historical banknotes](https://www.beac.int/billets-pieces/signes-monetaires/billets-de-type-ancien/) identifies the common issuing authorities. A regional note is not automatic proof of a separate Gabon, Chad or Middle Congo issue. |
| East African regional currency | [Central Bank of Kenya currency history](https://www.centralbank.go.ke/currency-history/) distinguishes regional currency from later national currency. Kenya, Uganda and Tanganyika do not gain a separate colonial issue merely from EACB circulation. |
| French India and Cochin-China | Publisher chapters for [French India](https://www.greysheet.com/prices/nc/french-india-world-paper-money/8484) and [French Cochin-China](https://www.greysheet.com/prices/nc/french-cochinchina-world-paper-money/8482) identify their note issues separately. |
| Gilbert and Ellice Islands | [Publisher's territorial chapter](https://www.greysheet.com/prices/nc/gilbert-and-ellice-islands-world-paper-money/8491) identifies government issues. Modern use of another currency must not erase that history. |
| Kamerun and Italian East Africa | Publisher chapters for [Kamerun](https://www.greysheet.com/prices/nc/kamerun-world-paper-money/8900) and [Italian East Africa](https://www.greysheet.com/prices/nc/italian-east-africa-world-paper-money/8375) document the distinct territorial issues. |
| Greenland, Faroe Islands, Danish West Indies and Iceland | [Greenland's historical issuer chapter](https://www.greysheet.com/prices/nc/greenland-world-paper-money/8363), [Nationalbanken's Faroese series](https://www.nationalbanken.dk/en/what-we-do/notes-and-coins/faroese-banknote-series) and [Nationalbanken's historical appendix](https://www.nationalbanken.dk/media/14xdu45n/nationalbanken-1818-2018-webappendix-en.pdf) distinguish historical local notes, current Faroese notes and the Danish West Indian bank. Iceland's later independent Republic notes are excluded; the earlier Danish monetary/union relationship is not a claim that the independent Kingdom lacked sovereignty. |
| Taiwan | [Taiwan Ministry of Finance museum](https://museum.mof.gov.tw/eng/singlehtml/009e91624d7848449733665a5bc46832?cntId=40b0615d3772461288a3145b9c474187) distinguishes the Japanese-period Bank of Taiwan, established in 1899, from the postwar bank and Taiwan-dollar issues. The shared bank name alone is insufficient. |
| Brunei | [Brunei Darussalam Central Bank historical publication](https://cms.bdcb.gov.bn/storage/uploads/publications/17089426511258820.pdf) documents the 1967 Currency Board issue. Matching excludes independence from 1984 onward. |
| Suriname | [Central Bank of Suriname's account of emergency money](https://www.cbvs.sr/nieuwsartikelen?catid=27&id=80%3Ahet-noodgeld-van-suriname&view=article) documents historical issues. Matching excludes the independent period from 1975. |
| Philippines and New Hebrides | [Bangko Sentral ng Pilipinas currency history](https://www.bsp.gov.ph/Pages/CoinsAndNotes/HistoryOfPhilippineMoney/HistoryOfPhilippineMoney.aspx) and [Reserve Bank of Vanuatu history](https://www.rbv.gov.vu/index.php/en/about/our-history) support the distinct periods. Philippine notes retain the user's existing all-period collection family; New Hebrides remains a joint administration. |
| Alderney | The [1810 one-pound catalogue record, Pick S181](https://en.numista.com/234220), documents private circulating paper. Current government coin issuance alone would have produced a false historical nonissuer claim. |
| Pitcairn | The [official Currency Ordinance](https://static1.squarespace.com/static/6526ff6fef608a3828c13d05/t/655839b56f256e21c55fe7e6/1781566287508/Currency+Ordinance.pdf), section 3(1), provides for New Zealand currency notes; sections 4–8 provide local coin issuance. The [Pitcairn catalogue](https://en.numista.com/catalogue/pitcairn-3.html) identifies the banknote-like items as fantasy issues. The neutral status concerns a separate **Pitcairn circulating banknote series**, not an assertion that paper money never circulated there. |

No “never issued” conclusion is drawn for Alderney, Greenland, Turks and Caicos,
or Gilbert and Ellice Islands from their current currency arrangements. No
negative is drawn from an unsuccessful web search. Regional West African and
East Caribbean successor areas are explicitly independent currency areas, not
territories described as currently controlled by France or Britain.

## Matching and navigation

`entity_for_row(row, classification=None)` first respects the existing
`banknote_catalog.row_classification` result. Japanese occupation Burma or
Netherlands Indies therefore cannot credit the British or Dutch territorial
pill. Modern independent India, Cuba, Belize and other successors do not credit
their colonial predecessor. Canada, Australia, New Zealand, Ceylon and regional
successor areas retain the existing nuanced collection-family descriptions;
membership is not an assertion of ongoing foreign control.

Eastern Caribbean collection grouping (26 October 2026) uses the shared
`eastern_caribbean_issue` resolver for coverage as well as filing. Recognized
Currency Authority / Central Bank records count toward the existing East
Caribbean States pill, including a blank country with an explicit regional
issuer, an authority saved as the country, and a recognized member-island suffix.
The British Caribbean Currency Board retains its separate predecessor pill.
These are regional holdings: an ECCA note labelled Grenada does not turn the
separate Grenada territorial pill green. Full Pick varieties and saved country
labels remain intact. The successor region has no colonial scan period;
ND (1965) alone cannot establish the actual issue date of a territorial variety
or eligibility before that territory's independence.

The Solomon Islands Monetary Authority's 1977 first dollar issue counts toward
the British Solomon Islands pill, including Ordered notes. The stored modern
country spelling remains intact. [CBSI's currency history](https://www.cbsi.com.sb/financial-stability/currency-management/currency-overview)
documents the 1977 introduction; the [Independence Order](https://parliament.gov.sb/files/business%26procedures/constitution.htm)
specifies 7 July 1978. That date is retained in the entity's independence
metadata. Year-only 1978 notes and later independent issues do not gain this
colonial coverage. The scan scope now includes the documented 1977 issue as
well as the earlier Government issues, without implying uninterrupted issuance.

For historic names absent from the existing classifier, a narrow exact-name
fallback supplies coverage without moving a record: for example North Borneo,
French India, Italian East Africa and Danish West Indies. Shared modern names
such as Palestine, Newfoundland, Suriname and Taiwan require a compatible date;
Taiwan also requires Bank of Taiwan or Japanese issuer evidence. Transition
years are conservatively excluded from the added rules where the year alone
cannot resolve the change. Saint Kitts excludes later regional issuers; German
territories with unresolved issuance exclude postcolonial paper. Hawaii remains
in the existing independent/other family, including Kingdom and Republic notes;
US federal Hawaii-overprint records remain federal US issues.

French Afars & Issas and French Afars and Issas are spelling aliases of French
Territory of the Afars and Issas, including the longer form with “the Issas” and
the French-language name. The shared country catalogue now resolves these
names for filing, search and pill coverage alike. They credit one French green
pill when held; French Somaliland and independent Djibouti remain distinct.
Startup retains the original spelling in the country-alias audit table and
normalizes the saved country; display-number migration v29 places the note in
the French run. Permanent B numbers and all other note and purchase facts are
preserved.

Coverage reads the viewer's authorized collection, independently of the current
search, status, location or dot filter. It uses the existing held lifecycle:
Own/Owned/blank, Ordered, Shipped and Delivered count; Sold, Gifted, Lost,
Consigned and Loaned do not. A visible held target links directly to its exact
row. A filtered-out target links to its existing historical group and exact row
anchor, retaining the History setting. A cross-group historical identity links
to the record's actual filing; the coverage helper never silently refiles it.

## Years displayed on entity pills

The collection's historical entity pills append a reviewed year to their visible
name, for example **India (1947)** and **Hong Kong (1997)**. The tooltip and
accessible description identify the actual event: Hong Kong's 1997 handover to
China is not described as independence. Tooltips also retain the supporting
source URL. Continuing territories and regions without one defensible common
year keep their names without an invented independence date.

`banknote_entity_date_data.py` holds the display-only, source-backed events and
explicit exclusions. `banknote_entity_dates.pill_date` can also reuse an existing
verified exact `independence_date` with its source for an issuing colonial entity
or the Philippines. It never derives an independence year from `scan_period`,
whose final year may instead concern a rename, an occupation or a documented
issue. Reviewed display events apply even where banknote issuance remains
unverified; the question mark and existing coverage meaning still apply.

All ten German entries show **1919**, the postwar Treaty of Versailles settlement,
including **German South West Africa (1919)**. This replaces Namibia's much later
independence year. [Article 119](https://history.state.gov/historicaldocuments/frus1919Parisv13/ch13subch1)
records Germany's renunciation of its colonial rights; Kiautschou's leased-territory
rights were transferred to Japan under
[Articles 156–158](https://avalon.law.yale.edu/imt/partiv.asp). The tooltips distinguish
the [28 June 1919 signature from entry into force on 10 January 1920](https://researchbriefings.files.parliament.uk/documents/LLN-2019-0079/LLN-2019-0079.pdf).
The caption does not use the earlier wartime occupation dates or later successor
independence dates. Unknown banknote issuance retains its question mark.

All ten Japanese entries show **1945**, marking the end of Japanese rule or
occupation in the year of the [2 September surrender](https://www.archives.gov/milestone-documents/surrender-of-japan).
These dates concern the Japanese administration: Japanese Hong Kong shows 1945,
while British Hong Kong retains its separate 1997 handover date. They do not
describe the affected territories as becoming independent in 1945.

Italian Eritrea, Libya, Somaliland and the Dodecanese show **1947**, the formal
[Treaty of Peace settlement signed 10 February and effective 15 September](https://treaties.un.org/Pages/showDetails.aspx?objid=080000028028c6f9).
Article 23 renounced colonial rights in Eritrea, Libya and Somaliland; Article 14
ceded the Dodecanese to Greece. Somaliland's later Italian administration was a
[UN trusteeship in 1950–1960](https://research.un.org/en/docs/tc/somaliland).
**Italian East Africa (1941)** instead dates the end of that combined colonial
administration through [Allied conquest](https://researchcentre.army.gov.au/library/australian-army-journal-aaj/number-1-july-1948/ex-italian-colonies-africa).
The tooltips identify these different events rather than substituting later
independence dates.

These parenthetical years change only presentation. Canonical entity labels and
keys, sorting, coverage, alias resolution, list filters, exact-note links and
History behavior retain their existing rules. No collection field or Market
Scan cutoff is rewritten. Date explanations are available with History on or off.

## Missing entities and dated Market Scan priorities

The scan uses the same roster and full authorized collection coverage as the
pills, including Owned and Ordered notes and the intervening delivery states.
The three existing priority families receive every missing **eligible** entity;
the old 35-subject list is retained as research history, not a second coverage
system. Independent successor issues cannot retire a colonial gap. The regional
currency helper described below can retire several documented territories from
one shared-board issue without changing that note's country or issuer.

Each definition stores `independence_date` and `independence_source` only when an
exact date has been verified. `scan_period` stores a reviewed start year, an
**exclusive** end year, the kind of transition, evidence, an explanatory note,
and an exact end date when supported. An open end is allowed only for an
explicitly identified continuing dependency; `scan_period=None` means excluded
or unresolved. These fields do not alter collection filing. Candidate dates
must fit the whole scope, even if a model supplies a broader administration or
an old printed date on a later reissue. A year-only transition-year issue is
conservatively excluded; Kuwait's first 1961 notes are an example where the
year alone cannot prove pre-independence issuance.

The current focused pass supplies 123 reviewed scopes and 25 source-backed exact
independence-date entries. Of the 29 documented
issuers without a scan scope, five are independent national/successor identities
(US federal, Confederate, Hawaii, East Caribbean States and West African
States), South Africa needs more precise colonial identity than its broad
collection family, and 23 await sufficiently precise period attribution.
They retain their truthful yellow/green pill status. No boundary is fabricated
to make an unresolved item eligible. All 41 unresolved issuers and the scoped
Pitcairn nonissuer are excluded from priority searches.

The unresolved period set is Falkland Islands, Isle of Man, Gilbert and Ellice
Islands, Saint Kitts, Cocos (Keeling) Islands, French Guiana, Guadeloupe,
Martinique, Réunion, New Caledonia, French Antilles, French Pacific Territories,
Mozambique Company, Netherlands Antilles, US-period Puerto Rico, Japanese
Korea/Burma/Malaya/Netherlands Indies/China/French Indo-China/Oceania, and
Greenland. The existing broad scan retains its separately sourced discovery
rules; this omission applies to the new fixed missing-entity priorities.

Most year bounds retain provenance to the existing reviewed catalogue,
`market_colonial.PERIODS`, and dated entity rules. Additional established scope
comes from the existing country history and legacy wantlist. Exact dates and
newly added boundaries have the following primary evidence:

- [Djibouti's foreign ministry history](https://diplomatie.gouv.dj/djibouti-historique)
  supports Afars and Issas independence on 27 June 1977.
- The US Office of the Historian verifies the dates for
  [India](https://history.state.gov/countries/india),
  [Bahamas](https://history.state.gov/countries/bahamas),
  [Barbados](https://history.state.gov/countries/barbados),
  [Belize/British Honduras](https://history.state.gov/countries/belize),
  [Brunei](https://history.state.gov/countries/brunei), and
  [Philippines](https://history.state.gov/countries/philippines).
- [Malaysia's official history](https://www.malaysia.gov.my/en/government/learn-about-malaysia/malaysian-history)
  distinguishes Malaya's 31 August 1957 independence from the formation of
  Malaysia on 16 September 1963. North Borneo and Sarawak use the latter as a
  transfer/formation cutoff, with no invented independence date.
- [Singapore's foreign ministry](https://www.mfa.gov.sg/about-mfa/histories-and-milestones/)
  gives independence on 9 August 1965.
  [MAS's currency history](https://www.mas.gov.sg/currency/history-of-currency-in-singapore)
  documents Singapore branch-bank notes from 1840 and shared-board issues.
  The new Singapore entry requires an identified historical issuer and excludes
  independent national notes from 1967.
- [The National Archives' Declaration](https://www.archives.gov/milestone-documents/declaration-of-independence)
  supplies 4 July 1776 for the 13 American colonial entities. The
  [US Currency Education Program](https://www.uscurrency.gov/history) supplies
  1690 as the beginning of the American colonial paper-money era, not an
  asserted founding date for every colony.
- [Germany's Federal Archives](https://www.bundesarchiv.de/en/research-our-records/research-by-topic/sources-on-colonial-history/geographical-access-to-colonial-history-holdings/)
  supports Kamerun's 1884–1916 administration. The
  [Curaçao central bank](https://centralbank.cw/about-the-bank/history) documents
  its 1828 beginning; the existing 1954 autonomy cutoff remains conservative.
- [Bermuda's national museum](https://nmb.bm/exhibit/banknotes-of-bermuda/),
  [Cayman's Monetary Authority](https://www.cima.ky/currency), and
  [Jersey's government](https://www.gov.je/TaxesMoney/JerseyCurrency/Pages/CurrencyMakesMoney.aspx)
  establish documented issues for continuing territories. The
  [Commons Library](https://commonslibrary.parliament.uk/research-briefings/cbp-9706/)
  distinguishes overseas territories and Crown Dependencies. Alderney is scoped
  to its verified 1810 issue, with no asserted modern banknote series.
- The [Centrale Bank van Aruba](https://www.cbaruba.org/the-aruban-florin/)
  dates its florin to 1986 Status Aparte within the Kingdom; that is not an
  independence date. The [Dutch National Archives](https://www.nationaalarchief.nl/onderzoeken/archief/2.10.60/download/pdf)
  and [UNTEA history](https://peacekeeping.un.org/sites/default/files/past/unsfbackgr.html)
  bound Netherlands New Guinea to 1950–1962. The
  [Congolese central bank](https://www.bcc.cd/la-banque/histoire/historique-de-la-banque-centrale)
  dates BCCBRU operations to 1952–1960; the
  [Burundian central bank](https://archive.brb.bi/en/content/historic) dates BERB
  to 1960, before the 1962 independence cutoff.
- [Benin's government history](https://www.gouv.bj/pages/histoire/) supports
  Dahomey's 1894–1960 period and 1 August 1960 independence. The
  [AfricaMuseum exhibition](https://independance.africamuseum.be/sites/independance.africamuseum.be/files/files/booklet_independance_en.pdf)
  distinguishes Upper Senegal and Niger, French Sudan, and independent Mali.
  [French Polynesia's statistics institute](https://www.ispf.pf/publication/diagnostic-territorial-2021)
  documents the 1957 name/status and continuing relationship to France.
- [Hong Kong's Government Records Service](https://www.grs.gov.hk/ws/online/80VWR/en/home/index.html)
  supports its 1941–1945 occupation scope. Publisher records bound the known
  [British Solomon issues](https://banknote.news/files/tag-british-solomon-islands.php)
  to 1916–1933 and document the
  [1928 Turks and Caicos issue](https://www.greysheet.com/prices/detail/10th-january-1928-sig-3-southby-frith-prefix-a-1-s-n-a-1-07105-07664/gsid/141809/60/0).
  Those limited issue scopes do not pretend to establish the territories'
  entire monetary history or independence dates.

## Validation

`tests/test_banknote_entities.py` checks unique evidence-bearing entries, all
existing filing rosters and all 35 legacy wantlist subjects, correct modern and
occupation separation, explicit historical aliases and canonical filing, uncertain
and nonissuer states, SQLite row support and unchanged inputs. The integration
suite covers lifecycle, access restrictions, filtering, cross-group navigation
and actual Pitcairn status. Isolated browser fixtures verify desktop/mobile
layout and exact destination rows without changing real collection data.
The same tests check visible independence years, Hong Kong's handover wording,
undated continuing territories, canonical aliases and preserved dated-pill links
with History on and off. The display helper rejects unsourced date fallbacks and
does not infer dates from scan periods or mutate the roster.

## Pacific lineage and African successor coverage

Tahiti / French Oceania / French Polynesia now share one displayed coverage pill,
**Tahiti / French Polynesia**. The original French Oceania and French Polynesia
entity keys and issue periods remain available for existing candidate identities;
`coverage_entity` merges their collection coverage only. A held or pending 1973
Tahiti note retires the missing-lineage prompt without claiming it was issued
before the 1957 name change. Sold and other disposed notes do not retire it.
The shared missing-lineage prompt retains the existing French Oceania
continuing-dependency period (from 1905, with no invented independence cutoff).
The name change is not independence; existing candidate date and issuer gates
still apply after the coverage-key comparison.
New Caledonia and the common French Pacific issue area retain separate pills.

The [IEOM territorial history](https://www.ieom.fr/IMG/pdf/livre_ieom_f_cfp_10.2014_-_web03_chapitre-2-p1825.pdf)
and [IEOM transition to territorial/common notes](https://www.ieom.fr/IMG/pdf/livre_ieom_f_cfp_10.2014_-_web04_chapitre-3-p2637.pdf)
underpin that lineage. It is not a cross-territory Pick-number equivalence; Market
Scan still requires the saved country/catalogue namespace and complete reference.
An IEOM label without an explicit territory supplies no inferred Pacific branch.

African regional coverage follows the reviewed issuer and territory, independently
of the display family’s French monetary lineage. BAO covers French West Africa;
BCEAO covers West African States. CCFOM and the AEF/Cameroon issuing institute
retain compatible historical territorial coverage. BEAC covers the new
**Central African States — successor regional issues** entity, with no colonial
scan period; it cannot credit French colonial Cameroon or another member country.
See [African family sources and scope](banknote-africa.md) and the
[BEAC historical notes](https://www.beac.int/billets-pieces/signes-monetaires/billets-de-type-ancien/).
The roster contains 195 stable entity keys; the French Polynesia coverage alias
is omitted from the displayed pill and active missing-entity lists to avoid a
second misleading yellow pill.
