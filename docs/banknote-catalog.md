# Historical banknote collection filing

## Catalogue-assisted Check

The ordinary Banknote Check uses the note's country and complete catalogue
reference to research missing type details for any supported country. It also
works when the existing photo/purchase step recovers that identity for a new
draft. `fetch_banknote_specs` reuses the existing authenticated Anthropic model
resolver and web-search adapter, with optional native Perplexity Search through
that instance's existing `PERPLEXITY_API_KEY`. It creates no provider credential
or bulk collection job. Vision and catalogue work share one 75-second
budget, with at most four web searches, one paused search-turn continuation and
no whole-call retries. The first phase uses vision and search. A bounded second
phase receives native source excerpts and at most two ranked URLs: observed
source pages and an eligible configured public catalogue directory. It extracts
supported facts from those excerpts or uses
fetch, preserving direct first-phase facts if retrieval fails. It can read
up to four full public catalogue pages across the request with
`web_fetch_20250910` (12,000 content tokens per fetch, explicit catalogue/auction
domain allowlist). This reuses Anthropic authentication; it carries no browser
cookies and performs no local direct-HTTP fallback. Follow only observed source
links, including from a country catalogue index when search misses an exact
type. Failed fetch attempts count toward the same four-call limit. Actual
fetched text resolves the provider's truncated search citations.

Before that extraction/fetch phase, `banknote_catalog_search.py` can make one
native `POST https://api.perplexity.ai/search` request using the existing key.
Two short country/full-reference queries preserve namespace and suffix; no
purchase, grade, certificate, serial or photo details are sent. The request caps
results at five, total content at 12,000 tokens and each page at 4,000 tokens,
using the same public catalogue-domain allowlist. Its timeout is the lesser of
15 seconds and the shared budget remaining minus ten seconds reserved for
extraction. There are no redirects, retries, new credentials or model-answer
fallbacks. Only native result snippets with their actual safe URLs become
evidence; a model's invented private-source property cannot authorize a fill.
Absent configuration or an unavailable source preserves the direct Check result.

`banknote_catalog_lookup.py` keeps catalogue research distinct from direct
photo/dealer facts. Each usable field has an actual provider-cited URL and a
literal supporting excerpt, together with its exact country, catalogue namespace
and full variety suffix. Competing references, historical-territory mismatches,
unknown states for Criswell/Haxby and conflicting known issue facts remain
unresolved. Specialist reference punctuation is preserved. A stable Pick/TBB
type fact can use a publisher's country-only issuer heading; an explicitly
different named institution is rejected. Existing parenthetical authority names
are accepted only as complete stored alternatives, never by dropping bank names.

Printer, material, dimensions and other type facts can use a matching type-wide
source. Signatures, watermark, date and series need the exact dated variety in
their own cited context; a nearby variant or a series-wide list is insufficient.
Full signer names must appear in that evidence. Known or ambiguous values remain
untouched. Catalogue history can fill the existing blank Historical Context
(`condition`) field, but never replace the user's notes. Serial, certificate,
grade, price, seller, purchase date, status, photos and crops are excluded from
catalogue fills. Source failure leaves direct purchase/photo Check available.

The response adds `catalogue {state, message, fields, guard}` alongside the
existing `filled`/`overwritten` results. `fields` contains `{value, scope,
source_url, quote}` per usable target. `guard.identity` contains the original raw
country, denomination, issuer, series, dates and references; `guard.fields`
identifies catalogue-only additions. `expected_values` contains the raw values
for every proposed target. The detail UI saves pending edits and intentional
clears before Check and suppresses stale results if the user edits while it runs.
Apply receives `catalogue_guard` plus `expected_values`, compares them under
`BEGIN IMMEDIATE`, skips changed identities/occupied fields, and returns
`accepted_values` and `skipped_fields`. These values are not autosaved again.
No research pass writes type fields before the normal Check acceptance path.

`guard.proposal_id` refers to a server-issued 15-minute proposal in
`banknote_catalog_proposals` with field/value/source rows in
`banknote_catalog_proposal_fields`. Apply checks the record, original identity,
any directly recovered draft identity, proposed value and expiry while holding
the same write lock. Source claims sent by the browser cannot create evidence.
Only fields actually accepted are marked as accepted and appended to the latest
`note_references_research` (Reference Notes) with their reference, acceptance
date, field/value, source URL and excerpt. The existing text is preserved; the
full source excerpt remains in the accepted evidence table even if the visible
notes later change. Expiration removes only unused proposals, not accepted
evidence. A repeated apply cannot append the same evidence again. The UI flushes
Reference Notes before Check and protects edits made while acceptance is pending.
These are catalogue type sources, separate from the specimen's provenance.

Search uses a generated country/numeric-denomination/year query for Numista's
whole domain, then semantic catalogue-reference and specialist/archive queries.
Observed legacy Numista note URLs retain their exact numeric record identity
when normalized to the current URL form. Country indexes can be useful discovery
sources; for missing dimensions with explicit unambiguous Pick/TBB identity,
the verified public Banknote Index Country directory is a configured navigation
fallback and takes priority even if search did not rediscover it. It is labeled
separately from observed URLs and never added to the evidence map merely because
it is configured. The fetch phase follows its actual country/historical-territory
link and then the matching complete-reference entry. It never guesses country
or item IDs; the entry itself must supply the field evidence. Finding another
field does not satisfy a still-unverified dimension request. Clearly different
denominations, references and coin results are not
treated as the requested banknote. The validator still checks the complete
reference after retrieval. Unknown,
inaccessible and conflicting results stay blank rather than becoming guesses;
the former uncited secondary dimensions lookup is removed. Regressions are in
`tests/test_banknote_catalog_lookup.py`, `tests/test_banknote_catalog_fetch.py`,
`tests/test_banknote_catalog_search.py`,
existing purchase/photo Check suites
and the detail-page browser fixture.

Privacy-safe diagnostics distinguish retrieval gaps from validation rejection:
the adapter logs native/source/candidate counts, whether fetch was attempted,
its bounded stop/failure state and allowlisted claimed field names. The route
logs validation state and accepted field names. These summaries omit all note
values, source URLs, purchase details, record identifiers and credentials.

The list files notes by historical collection relationship first, then territory,
then the existing monetary era, year and denomination rules. The catalogue is
`banknote_catalog.py`; SQLite ordering, group filters, list headings, analysis
empire labels and country spelling helpers share it. These are filing families,
not assertions that every member was a colony or remains dependent today.

## Order and scope

1. British Empire & Commonwealth
2. French colonial empire & overseas territories
3. Spanish overseas territories
4. Portuguese overseas territories
5. Netherlands overseas territories
6. Belgian colonial territories
7. German colonial territories
8. Italian territories & trusteeship
9. United States & Philippine issues
10. Japanese empire & occupation issues
11. Danish realm & dependencies
12. Joint administrations
13. Independent & other issues

Only represented groups get list headings. Headings remain visible with History
off. The group selector uses the existing filter axis; choosing a group replaces
a type/status filter, and preserves search and History state. Map and detail
navigation accept the same group filter. The separate Analysis page retains its
issue-type buckets (military, colonial, US, other); its empire labels now use the
same catalogue. Its older colonial-issue eligibility rules are not the list's
historical-family membership test.

Each represented group also has a horizontal entity-pill row. Green shows held
notes (including pending purchases), yellow shows documented issuing entities
without holdings, and unfilled pills identify documented non-issuers. A question
mark explicitly distinguishes unresolved issuance history. Coverage uses the
whole authorized collection, independently of view filters. Green links reach
the exact saved note, revealing its existing group when filters hide it, while
preserving the History preference. The roster in `banknote_entities.py` changes
neither filing nor display numbers; see [entity coverage](banknote-entities.md)
for historical scope, matching safeguards and sources.

Canada and Australia remain in British/Commonwealth holdings at every date, as
requested. New Zealand follows the same collecting convention. Their national
issues are labelled Dominion / independent Commonwealth, not colonial. Crown
Dependencies, British protected states and overseas territories have separate
period labels. Rhodesian UDI is identified as an unrecognized administration.

All Philippine issues remain together under United States as explicitly
requested, including Spanish, American, Commonwealth, Japanese occupation and
Republic issues. This is a collection choice, not a claim of continuous US rule.
Confederate States and Confederate States of America also file in this US
collection family, after domestic US notes and before Philippine notes. Their
stored country and issuer identities remain unchanged; the period label keeps
Confederate obligations distinct from US federal issues. Migration v28 refreshes
display positions only, preserving permanent catalogue IDs and purchase data.
Occupation issuers elsewhere take precedence over territorial filing: Japanese
issues in Burma, Malaya, Netherlands Indies, China and French Indo-China move to
the Japanese group. Metropolitan Japanese, French, German, Italian, etc. national
issues go to Independent & other. Spanish Puerto Rico and Cuba do not get grouped
with their later administrations. Independent Algerian, Cuban, Belizean,
Indonesian, Cypriot and other successor-state issues stay in the final group.

Currency authorities remain distinct within regional collection families: the
Eastern Caribbean family retains separate British Caribbean Currency Board,
East Caribbean Currency Authority and Eastern Caribbean Central Bank sections
(see below). British East Africa's post-independence currency-board issues
are labelled transitional. West African States/BCEAO remains a related successor
currency area in the French collection family; qualifiers such as “(Senegal)”
are preserved. New Hebrides belongs to the joint-administration group. Italian
Somaliland's 1950–1960 issues explicitly identify the UN trusteeship.

Within an existing country/issuer era and series-year group, denominations
sort by numeric value, including equivalent symbols and written units. For
example, 50 cents, $1, 150 cents, 10 Dollars and $100 appear in that order.
Dollar and pound symbols and their USD/GBP labels use the same currency family
as the written denomination; an explicit currency name still wins when a
symbol is ambiguous (such as $10 Pesos). Separate currency families remain
separate, and the existing historical groups and chronology take priority.
Migration v27 refreshes display positions (P numbers) without rewriting saved
denominations or permanent B numbers.

## Eastern Caribbean regional family

The collection list and PDF report gather this regional currency lineage under
one **Eastern Caribbean** heading, with three distinct issuer subsections:

- **British Caribbean Territories — Eastern Group (BCCB), 1950–1965.** The
  British Caribbean Currency Board was established in 1950; its first unified
  notes entered circulation on 1 August 1951.
- **East Caribbean States — Currency Authority (ECCA), 1965–1983.** The ECCA
  succeeded the Board and first issued notes on 6 October 1965. Grenada joined
  the arrangement in 1968. An `ND (1965)` catalogue family does not establish
  the actual issue date of a later territorial or signature variety.
- **East Caribbean States — Central Bank (ECCB), established 1983, notes from
  1984.** The ECCB began on 1 October 1983; its first notes entered circulation
  on 15 November 1984.

Each regional run is a named section with a visible closing rule in both
History modes. A following Jamaican or other nonregional note stays outside
that section; interrupted date-filtered runs close and reopen separately.

The issuer headers retain an **Issued** denomination list with History both
on and off. These are the authority's issued denominations, including values
not held in the collection, rather than a summary of the visible records:

- BCCB: $1, $2, $5, $10, $20, $100.
- ECCA: $1, $5, $20, $100.
- ECCB: $1, $2, $5, $10, $20, $50, $100 across its history. The header's
  explanation includes the withdrawn $1 and the $2 circulation commemorative;
  the list does not claim every denomination belonged to every series.

Unresolved issuing authorities receive no borrowed denomination list. This
display change does not modify records, grouping, sorting or display numbers.
The BCCB set is documented in its
[1961 Executive Commissioner report](https://www.parliament.gov.gy/documents/documents-laid/20110-report_of_the_executive_commisioner_1961_.pdf).
The Bank of Guyana's
[History of Bank Notes](https://bankofguyana.org.gy/bog/images/communications/history_notescoins/History_of_Guyana_Notes.pdf)
illustrates the ECCA $1, $5, $20 and $100 on PDF pages 47–50. ECCB's
[2006–2007 report](https://cdn.eccb-centralbank.org/documents/2022-05-11-04-53-07-Annual-Report-2006-2007-PDF1.pdf)
documents its earlier issues and the end of $1 issuance in 1989; its
[2020–2021 report](https://cdn.eccb-centralbank.org/documents/2023-07-03-15-59-20-2020-2021-Annual-Report-2.pdf)
shows the $5, $10, $20, $50 and $100 polymer family; and its
[2023–2024 report](https://cdn.eccb-centralbank.org/documents/2024-07-03-12-52-21-2023-2024-Annual-Report.pdf)
documents the circulation $2 commemorative introduced in December 2023.

These dates and the succession come from the ECCB's
[currency anniversary history in its 2014–2015 annual report](https://cdn.eccb-centralbank.org/documents/2023-10-18-02-17-12-Report-and-statement-of-accounts---ending-31-march-2015.PDF)
and [2007–2008 annual report chronology](https://cdn.eccb-centralbank.org/documents/2022-05-11-04-52-02-Annual-Report-2007-2008-PDF.pdf).
The [Board's own 1961 report](https://www.parliament.gov.gy/documents/documents-laid/20110-report_of_the_executive_commisioner_1961_.pdf)
documents its formal name and regional constitution. The grouping is a
numismatic currency lineage, not a claim of identical membership or continuous
colonial rule.

`eastern_caribbean_issue` is a display/filing resolver, separate from the saved
country normalizer. It recognizes explicit regional country labels, qualified
labels such as `East Caribbean States - Grenada`, and the exact regional issuer
when the country is blank or a named member territory. A standalone Grenada
record is not a regional alias. A missing or conflicting issuer remains
unresolved; the year 1965 alone never chooses an authority. Country, territorial
attribution, issuer, series, full Pick suffix, photos, purchase details and
permanent B numbers are retained. The report repeats each note's raw country
within its shared issuer section so a territorial qualifier is still visible.

Within an issuer, equivalent dated/undated series labels file together before
numeric denominations and the full natural-order catalogue reference. Written
dollar denominations such as `Five Dollars` compare with `$5` in this regional
family. Range descriptions retain their distinct design/series wording, except
for the reviewed BCCB 1953–1964 Currency Board/Elizabeth II wording variants.
The original labels stay unchanged. Migration **v30** updates only the
P display positions to match the list/report order; edits to either catalogue
reference also resequence positions. The two existing regional entity pills
remain separate (BCCB and the ECCA/ECCB successor area); a regional Grenada
attribution does not assert a standalone Grenadian issue or pre-independence
territorial coverage. Tests: `test_banknote_caribbean.py` and the isolated
`test_banknote_caribbean_browser.cjs` fixture.

## Spelling and preservation

The canonical numismatic spelling is **French Indo-China**. “Indochina,”
“Indo China,” “Indo-China” and “French Indochina” search the same country. French
Cochin-China, North/South Vietnam, British Honduras/Belize, Rhodesia/Rhodesia and
Nyasaland, and historical versus successor currency areas are not merged.

Other explicit spelling aliases include Rhodesia & Nyasaland → Rhodesia and
Nyasaland; Saint Pierre & Miquelon → Saint Pierre and Miquelon; Sao Tome and
Principe → São Tomé and Príncipe; Sarawak (Malaysia) → Sarawak; and
Viet Nam - South (South Vietnam) → South Vietnam. Timor stays Timor: a dated BNU
issue can be classified as Portuguese Timor without rewriting an ambiguous name.

French Afars & Issas and French Afars and Issas resolve to French Territory of
the Afars and Issas, as do the equivalent longer English and French names. The
same identity drives French filing, search and the entity pill, so a holding is
not split into an independent issue and a missing French territory. French
Somaliland and independent Djibouti remain separate. Migration v29 refreshes
display positions after this correction, preserving permanent catalogue IDs
and other note facts; the original country spelling remains in the alias audit.

Create, edit, autosave, AI intake, Market Buy/Bought and Sweep import normalize
country spellings. Startup normalizes existing aliases before older intake
migrations, preserving the original spelling in `banknote_country_alias_history`.
The audit table has a composite primary key beginning with its banknote foreign
key and cascades on deletion. No issuer, historical date, Pick number or note
identity is changed by this spelling migration. Display-number migration v22
resequenced the list, and issuer edits now resequence too.

The explicit legacy label “United States (Colonial - Pennsylvania)” normalizes
to **Pennsylvania Colony**, matching the other Pennsylvania colonial notes.
Their history panels can therefore share a heading, retaining “now United
States” only as the modern-country reference. Generic US names, other colonies,
and the later Commonwealth of Pennsylvania are not covered by this alias.
The original value remains in the alias audit table; migration v23 resequences
display numbers after this correction. Check, edit and import use the same alias
rule so the old heading cannot be reintroduced through those paths.

Generic US records now resolve to a named American colony when a dated issuer
explicitly says Colony or Province (through 1776), or identifies New York City
Water Works in its known 1774-1776 issue period. The last Water Works issue is
March 5, 1776, before independence; a bare 1776 year or a New York mention on its
own is insufficient. Continental Congress and later state/federal notes are not
reclassified by this rule. A conflicting named country is not overwritten.
The same rule drives filing, save/Check/import normalization and startup repair.
Original country values are retained in the country-history audit table;
migration v24 resequences display positions without changing permanent B-numbers
or ownership status. History panels, maps and reports use the corrected country.

American colonies sort alphabetically within their historical group, then by
era and date within each colony. They no longer share a country sort key that
interleaves Pennsylvania's 1772-1773 and 1776 issues with Connecticut, New Jersey
and New York. Migration v25 refreshes display positions only; later state and
federal ordering is unchanged. The report likewise has one contiguous section
per colony, retaining all of that colony's historical periods.

Confirmed New Jersey colonial issues use **New Jersey Colony**, including the
1776 one-shilling (Fr. NJ-175) and six-shilling (Fr. NJ-178) notes with a Colony
of New Jersey issuer. Startup repairs the old shortened label, retains its
audit history, and migration v26 refreshes display positions. A generic New
Jersey name in 1776 is not sufficient: later state issues keep their own label.

## Evidence and limits

- [PMG - Colonial Currency: Water Works](https://www.pmgnotes.com/news/article/4442/)
  documents the four New York City issues of August 25, 1774; August 2, 1775;
  January 6, 1776; and March 5, 1776, including the 8-shilling denomination.
- [Library of Congress — Early American Paper Money Collection](https://findingaids.loc.gov/exist_collections/ead3pdf/rbc/2019/rb019001.pdf)
  catalogs the Pennsylvania two-shilling issue dated April 3, 1772.
- [PMG French Indo-China population report](https://www.pmgnotes.com/population-report/french-cochin-china-and-indo-china/french-indo-china/5-piastres/)
  supplies the canonical numismatic spelling and separates Cochin-China.
- [Bangko Sentral ng Pilipinas — history of Philippine money](https://www.bsp.gov.ph/Pages/CoinsAndNotes/HistoryOfPhilippineMoney/HistoryOfPhilippineMoney.aspx)
  distinguishes Spanish, revolutionary, American, Japanese and Republic periods.
- [Bank of Canada — Dominion notes](https://www.bankofcanada.ca/2017/02/staff-working-paper-2017-5/)
  and [Reserve Bank of Australia — banknote history](https://banknotes.rba.gov.au/australias-banknotes/history/)
  support Dominion/Commonwealth terminology rather than calling modern issues colonial.
- [UK government — Crown Dependencies](https://www.gov.uk/government/publications/crown-dependencies-jersey-guernsey-and-the-isle-of-man)
  distinguishes Jersey, Guernsey and the Isle of Man.
- [Central Bank of Somalia — history](https://centralbank.gov.so/history/)
  identifies the monetary institution under the Italian-administered trusteeship.
- [Reserve Bank of Vanuatu — history](https://www.rbv.gov.vu/index.php/en/about/our-history)
  describes independence and the New Hebrides currency transition.
- [Central Bank of Kenya — currency history](https://www.centralbank.go.ke/currency-history/)
  distinguishes the East African Currency Board from successor national banks.
- [Danmarks Nationalbank — Faroese banknotes](https://www.nationalbanken.dk/en/what-we-do/notes-and-coins/faroese-banknote-series)
  describes the distinct Faroese series.
- [BNU — banknote exhibition](https://bnu.com.mo/notes_for_collection/en/Pagina%20Principal.htm)
  and [BNU's current issue agreement](https://www.bnu.com.mo/storage/documents/PRs/Press%20Ad%20Banknote%20Issuance%20Agency%20Contract%20Exchange%20Ceremony%20EN%20_FINAL.pdf)
  show why BNU's name alone cannot make a modern Macau note Portuguese-colonial.

The exact day of a sovereignty change cannot be inferred from a year alone.
Boundary-year entries receive a transition label unless the issuer resolves the
period. Unknown countries remain in Independent & other, not “never colonized.”
Historically explicit territory names are evidence of the issue family, not
rewritten to modern states. The catalogue is deliberately finite: new ambiguous
territories need an explicit rule rather than guessing an empire from a name.

Read-only production audit on 2026-09-20: 355 records, five spelling pairs changed,
13 represented groups. French Guiana's recorded 2026 date with historical CCFOM /
Banque de la Guyane issuer is flagged for review, not corrected. New Hebrides 1980
is labelled condominium / Vanuatu transition. None of this work writes to
production or changes its running release.

Validation: regression tests cover all requested examples, mixed administrations,
alias search, distinct territories, idempotent audited migration, filters,
History-off headings, save/import canonicalization and display-number resequencing.
The existing US monetary-era and Philippine-era tests remain in place. Browser
verification uses a disposable local database populated with country/year/issuer/
series metadata from the read-only audit; its denomination and images are fixtures.

## Catalogue-specific distribution callouts

Fr. 1500 (including replacement notes) receives a Puerto Rico distribution
callout on the collection row even with History hidden, and a sourced explanation
on its detail page. It remains a United States legal tender note; distribution
does not change its issuing country, series date, map origin or sort order.
Match the explicit Friedberg catalogue number, not signatures or a narrative
mention: Woods–Woodin also occurs on other types.

Source: Jamie Yakes, [“Series of 1928 $1 United States Notes,” Paper Money,
January/February 2013, pp. 40–51](https://s3.amazonaws.com/pmarchives.spmc/pm283-2013-series-1928-1-united-states-notes.pdf),
based on Treasury correspondence and inventories at the National Archives.
The live B362 record retained its Puerto Rico narrative on 2026-09-20; the list
only exposed a generic United States label. Its saved history was corrected to
acknowledge the early mainland release and shipments through April 1949, with
the source linked. No individual circulation provenance is inferred.

## State treasury notes and federal coin-note history

The generic words “Treasury Note” do not identify the United States federal
Treasury (Coin) Note class. That history is selected only for an 1890 or 1891
series/date and a compatible federal issuer; a supplied state, territorial,
Confederate or obsolete-bank authority is not treated as the federal Treasury.
An unknown date does not borrow the 1890 redemption clause.

A positively identified Commonwealth of Virginia / Virginia Treasury issue in
1861–1865 receives state treasury history under its saved issuer and year,
including notes filed under either United States or Confederate States. State
is a separate issue type: the subnational Virginia obligation is not a national
Confederate or federal US issue. Check proposes State for a known Virginia note
and classification saves normalize generic National/blank values to State;
custom types and unrelated field saves are preserved. Sovereign governments,
central banks and names merely containing “State” or “État” are not inferred to
be subnational issuers. The existing startup migration explicitly skips this
new type normalization, so existing records require a reviewed save. This
corrects the 1862 $100 Virginia note’s displayed history without rewriting its
country, issuer, date, CR-6 reference, images, purchase facts or saved notes.
No display-number migration or record renumbering accompanies this history fix.

Sources:

- [Virginia General Assembly — Acts passed in 1861, chapter 6, March 14, pp. 29–30](https://archive.org/details/actsofgeneralas00virg)
  is the original state treasury-note authorization: state defence financing,
  the Commonwealth’s faith pledged for redemption, and receipt for state taxes
  and dues. It establishes the separate Virginia obligation, not a Confederate
  national obligation; it is not presented as the specific authorization of
  every later denomination or variety.
- [Library of Virginia — Government Work](https://old.lva.virginia.gov/exhibits/destiny/work/government.htm)
  documents the continuing state Treasury’s production of Virginia currency in
  1861–1864. Joining the Confederacy did not end the state’s own Treasury,
  expenses or obligations. The panel explains that distinction rather than
  treating the Commonwealth as the Confederate national issuer.
- [Emory / Digital Library of Georgia — Virginia $10, October 15, 1862](https://dlg.usg.edu/record/geusc_139x0k6f6s-cor_235gb5mmq3-cor)
  identifies Virginia as creator while grouping the note under Confederate
  currency. The 1862 $10 and $100 note faces preserved on B412/B411 provide
  the direct evidence for the Commonwealth pledge and taxes/public-dues wording.
- [Smithsonian — Virginia $100, 1862, object nmah_1762087](https://americanhistory.si.edu/collections/object/nmah_1762087)
  identifies the October 15, 1862 issue and Keatinge & Ball as maker. This is
  distinct from the Smithsonian’s national Confederate $100 object nmah_1211831.
- [Newman Numismatic Portal — Virginia Treasury $100 Cr. 6](https://nnp.wustl.edu/library/ImageDetail/599348)
  corroborates the exact catalogue identity and printer. Its institutional
  record reproduces an auction description; the Smithsonian object and
  Virginia archive provide the primary institutional evidence.
- [Bureau of Engraving and Printing — History](https://www.bep.gov/currency/history)
  dates the first federal Treasury Coin Notes to 1890; its
  [Currency Notes publication, p. 5](https://www.govinfo.gov/content/pkg/GOVPUB-T18-PURL-LPS66873/pdf/GOVPUB-T18-PURL-LPS66873.pdf)
  identifies Series 1890 and 1891 and the July 14, 1890 authorization.

Regression coverage includes the Virginia history panel, legitimate federal
1890/1891 issues, incompatible dates, other treasury authorities, and unchanged
saved record fields after history rendering.


## Portraits and design: exact Virginia Cr. 6 reference

Check now distinguishes multiple named portraits from allegorical figures and
keeps their left/center/right positions in the short description. The former
90-character instruction could omit secondary figures; the prompt now allows
up to 240 characters and does not invent a reverse when only the face is known.

The 1862 Virginia $100 Cr. 6 has a deterministic type-reference safeguard, gated
by all four of issuer, year, denomination and explicit Cr. 6 catalogue number
(including VA CR-6 / VACR6). Virginia location, printer, denomination alone or
an ambiguous P-6 cannot trigger it; the $10 Cr. 11 is excluded. A proposed
conflicting catalogue identity holds this fallback for review. It adds reviewed
suggestions for Portrait and Short Description, not an automatic record edit.
The original reverse description is retained; no reverse is guessed. The source
attribution is shown in Check and cannot supply purchase price, grade or other
personal facts.

[Heritage lot 95435](https://currency.ha.com/itm/obsoletes-by-state/virginia/richmond-va-commonwealth-of-virginia-100-oct-15-1862-cr-6-pmg-about-uncirculated-50/a/62324-95435.s)
identifies Governor John Letcher in the center, Washington at left, a Native
American figure at right, and two orange C protectors. The
[Newman collection catalogue record](https://nnp.wustl.edu/library/ImageDetail/599348)
corroborates the same Cr. 6 layout (describing the protectors as red). The app
labels the unnamed female figure as an allegorical Native American maiden,
not an identified historical woman. These are catalogue observations of the
type, not the user's own grade, price or provenance.


The same Heritage catalogue identifies this as the largest denomination of the
Commonwealth’s second and final emission, intended to redeem earlier
interest-bearing Treasury notes. Check offers that source-backed fact only in
an empty Historical Context field; existing historical notes and the saved
series label remain unchanged. It is a type-level fact, not evidence of this
individual note’s circulation or redemption.


## Signatures: dated British Honduras Pick 28b variety

Check can fill a missed signature combination for the Government of British
Honduras $1 dated 1964, explicitly identified as Pick 28b. The exact 1 April
1964 variety names Henry Edney Conrad Cain, Rafael Aloysius Fonseca and Henry
Ignatius Melhado. [Numista's dated variety table](https://en.numista.com/202483)
provides the full names; [Noonans, 31 May 2022, lots 2349–2351](https://www.noonans.co.uk/auctions/calendar/647/download-pdf/)
corroborates the date, denomination, Pick number and Cain/Fonseca/Melhado set.
The 1961 Pick 28b rows have Parcher/Cottrell/Melhado instead, so Pick 28b alone
cannot establish the signatures.

This finite reference requires a consistent saved country, issuer, denomination,
year and unambiguous Pick variety. A conflicting proposed identity withholds it,
and direct image/dealer signature suggestions take precedence. It supplies only
Signatures through the existing fill/review flow, with source attribution; the
lookup does not write the saved signature field or infer specimen facts. The
model prompt also requires the dated variety instead of the entire series' list.

The combined catalogue field also accepts the verified cross-reference spelling
`P-28b, TBB# 127 (type-level, per Numista)`. Only this recognized TBB127 source
annotation is ignored for matching; uncertain or competing Pick attributions
still reject the fallback, and the saved catalogue text is never rewritten.

## French Pacific and African currency families

The collection display now files the French Pacific under one family, retaining
separate Tahiti / French Oceania / French Polynesia, New Caledonian, and explicit
common French Pacific issue areas. Each territorial branch keeps its Banque de
l’Indochine and IEOM sections. IEOM or a date alone does not supply a territory;
unknown or contradictory issuers remain separate and do not borrow a denomination
roster. New Hebrides remains in the Joint administrations family, and French
Indo-China remains separate.

The [IEOM history, chapter 2, pp. 19–25](https://www.ieom.fr/IMG/pdf/livre_ieom_f_cfp_10.2014_-_web03_chapitre-2-p1825.pdf)
distinguishes the Nouméa and Papeete branches. [Chapter 3, pp. 27–28](https://www.ieom.fr/IMG/pdf/livre_ieom_f_cfp_10.2014_-_web04_chapitre-3-p2637.pdf)
records the territorial IEOM 100, 500, 1,000 and 5,000-franc families and the
common 10,000-franc issue introduced in 1986. The common regional header lists
500, 1,000, 5,000 and 10,000 francs, corroborated by
[IEOM’s denomination page](https://www.ieom.fr/Les-pieces-et-billets-en-circulation?lang=fr).
Territorial withdrawal dates differ between official summaries, so the resolver
uses explicit geography, never an assumed year boundary.

The Nouméa Banque de l’Indochine headers use narrower, reference-backed rosters:
[Pick 48, 5 francs](https://www.pmgnotes.com/priceguide/world-note-prices.aspx?deid=1744274)
and [Pick 49, 20 francs](https://www.pmgnotes.com/priceguide/world-note-prices.aspx?deid=1744277)
belong to the **1944 Australian-printed issue**; its issued set is 5 and 20 francs.
[Pick 50](https://www.pmgnotes.com/priceguide/world-note-prices.aspx?deid=1787856&subcat=1951-nd-issue)
is a separate **1951–1963 20-franc type**, including the 1963 P50c variety.
Only a single unambiguous Pick attribution and a compatible recorded date enables
these type labels. Other catalogue namespaces may accompany that Pick reference,
but competing Pick references withhold the scoped roster. Stored text is retained.
The [IEOM New Hebrides appendix, pp. 81–82](https://www.ieom.fr/IMG/pdf/livre_ieom_f_cfp_10.2014_-_web08_annexe-1-p80a87.pdf)
confirms its distinct Anglo-French currency history and separate denominations.

[The African family catalogue](banknote-africa.md) documents the West African
BAO/BCEAO and Central African CCFOM/Institut d’Émission/BEAC sections. They are
monetary lineages, with independent successor periods stated explicitly. Each
review warning remains attached to its affected saved row in either History mode.
BCEAO and BEAC notes cover their regional successor entities, not colonial member
territories.

`collection_family_issue` supplies display metadata; `collection_family_for_row`
adds exact type scopes where supported. `collection_family_section_key` keeps
unknown issuer identities separate in reports. List and PDF share family/issuer
ordering, full series text, numeric denomination order, and complete catalogue
references. Family sections close visibly and semantically before unrelated
notes, including when a date-sorted view interrupts and reopens a family.

Migration **v31** changes only the derived `banknote_id` display positions, once.
Saved countries, dates, issuers, catalogue namespaces and suffixes, photos,
prices, purchase state and notes are unchanged. Collection search treats Tahiti,
French Oceania and French Polynesia as lineage search terms; this is isolated
from `canonical_country`, intake normalization and Market Scan duplicate matching.
The original Caribbean grouping, denomination rosters and family boundaries are
unchanged. Coverage aliases are documented in [the entity catalogue](banknote-entities.md).
