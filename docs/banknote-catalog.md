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
resequences the list, and issuer edits now resequence too.

## Evidence and limits

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
