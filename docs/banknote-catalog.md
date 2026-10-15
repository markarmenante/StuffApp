# Historical banknote collection filing

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

Canada and Australia remain in British/Commonwealth holdings at every date, as
requested. New Zealand follows the same collecting convention. Their national
issues are labelled Dominion / independent Commonwealth, not colonial. Crown
Dependencies, British protected states and overseas territories have separate
period labels. Rhodesian UDI is identified as an unrecognized administration.

All Philippine issues remain together under United States as explicitly
requested, including Spanish, American, Commonwealth, Japanese occupation and
Republic issues. This is a collection choice, not a claim of continuous US rule.
Occupation issuers elsewhere take precedence over territorial filing: Japanese
issues in Burma, Malaya, Netherlands Indies, China and French Indo-China move to
the Japanese group. Metropolitan Japanese, French, German, Italian, etc. national
issues go to Independent & other. Spanish Puerto Rico and Cuba do not get grouped
with their later administrations. Independent Algerian, Cuban, Belizean,
Indonesian, Cypriot and other successor-state issues stay in the final group.

Currency areas remain distinct: British Caribbean Territories is not East
Caribbean States; British East Africa's post-independence currency-board issues
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
