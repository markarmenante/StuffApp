# Monetary-history date coverage

Every dated note must fit an actual history period. A note outside all bands
never inherits the nearest period. Missing dates before, between or after the
existing periods trigger background research on collection views (including
History off), country/date/series/issuer edits, accepted Check changes and startup.
Single-note and multiple-note imports trigger the same check after publication
commits. A history scheduling failure cannot reject a completed purchase.

The check reads the collection's saved issue/series dates and canonical country
aliases. It extends both built-in and previously generated histories. Existing
periods, their wording and issuer gates remain intact; the result adds only
non-overlapping periods covering all requested missing years. Undated and future
dates cannot fabricate a period. Federal US series and Colonial America retain
their dedicated panel rules.

Research uses the existing Anthropic history model and web-search integration.
The response must supply published sources whose URLs appeared in provider search
results/citations. Unsupported dates, overlapping periods, incomplete coverage,
missing sources and failed research are rejected. Successful periods and sources
are retained in `country_history_updates`; `country_eras` holds the added bands.
This checks date coverage and source provenance, not independent historical peer
review of every generated sentence.

`country_history_jobs` gives each country one durable lease and publication token.
Expired leases can be reclaimed after a restart; a superseded worker cannot
publish. Transient failures wait at least a minute before another view/status poll
can retry, with three automatic attempts per unchanged request. Manual retry
resets the attempts. Changed dates/coverage create a fresh request.

The list shows the uncovered date while research is pending and polls for updates.
It refreshes once all that country's saved dates are covered. After successful
research, list panels, sort keys and newly generated reports use the extended
history. Only the derived P display positions are resequenced; note facts,
catalogue IDs, purchases and photos are untouched. Migration
`banknote_display_number_v42` handles the initial ordering change once.

France's built-in history now separates 1789–1799 (Revolution and assignats),
1800–1802 (founding of the Banque de France) and 1803–1913 (Germinal franc).
Sources for these curated periods:

- [University of Chicago French Currency Collection](https://www.lib.uchicago.edu/e/scrc/findingaids/view.php?eadid=ICU.SPCL.FRENCHCURRENCY)
- [Citéco: issuance of assignats](https://www.citeco.fr/10000-years-history-economics/industrial-revolutions/issuance-of-assignats-in-france)
- [Banque de France: founding history](https://www.banque-france.fr/en/banque-de-france/institution-rooted-history/founding-history-banque-de-france)

`tests/test_country_history_coverage.py` covers the photographed 1792 assignat,
period boundaries, automatic additions to built-in/generated histories, gaps,
source validation, durable deduplication/retries/expired leases, date-only edits,
list/report consistency and preservation of note data.
