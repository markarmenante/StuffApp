# Banknote face-value comparisons

Every banknote detail, including existing collection notes, displays one row
immediately above Description: Year (Series), Probable issue date, buying power
at issue in today's USD, and buying power of the same nominal amount today.
The amounts are derived from the note and shared public datasets; they are never
written into the purchase price, collector valuation or original description.

`issue_date` is an independently editable Gregorian year or range. Check can fill
it only from an explicit release/issue/circulation statement for the complete
catalogue reference, with the normal server-stored evidence proposal. Printed
series and law dates are not actual issue dates. A plain non-US catalogue year
can supply a clearly labelled approximate year; US series and identified law
dates require separate issue-date evidence. Ranges evaluate every intervening
year and show the minimum/maximum result. Unknown dates stay unknown.

The at-issue calculation is face value, in comparable present monetary units,
multiplied by the domestic CPI ratio (latest / issue year), then by the current
USD exchange rate. The today calculation uses the same nominal amount and FX,
without the inflation multiplier. This expresses the cost of the domestic
basket in USD; it is not an international PPP estimate. The latest CPI and FX
periods are visible below the row. Long-run historical indices and forecast
indices are marked as estimates. CPI more than two years old cannot supply a
current comparison. This does not imply a cancelled note remains spendable or
redeemable; see the expandable Basis & sources explanation.

Data sources (anonymous public reads, no credentials or note data):

- [Minneapolis Fed CPI, 1800 onward](https://www.minneapolisfed.org/about-us/monetary-policy/inflation-calculator/consumer-price-index-1800-): historical estimates before 1913; the latest forecast, if present, remains labelled.
- [Bank of England inflation calculator](https://www.bankofengland.co.uk/monetary-policy/inflation/inflation-calculator): long-run British CPI and latest monthly CPI. Historical estimates are labelled; complete years use annual averages.
- [World Bank / IMF CPI FP.CPI.TOTL](https://data.worldbank.org/indicator/FP.CPI.TOTL): 40 supported country series, mostly from 1960 onward, subject to country availability. World Bank data attribution: CC BY 4.0.
- [ECB reference rates through the existing Frankfurter provider](https://api.frankfurter.dev/v1/latest?base=USD): quotes are units per USD, inverted once for USD per unit.
- [ECB fixed euro conversions](https://www.ecb.europa.eu/euro/intro/html/index.en.html): explicit old-unit-to-euro factors, not a general rule for every obsolete currency.

`data/banknote-economics.json` provides a verified initial public-data snapshot
so all notes work immediately without a per-note backfill or provider call.
`banknote_economics.py` refreshes shared CPI monthly and FX daily in a bounded
background thread, retaining each last good source on failure. The data cache
is local to each deployment's DATA_DIR; no collection or owner data is shared.
No AI call runs when viewing this row. The endpoint applies the detail page's
row visibility checks. Tests disable refresh and use synthetic collection rows.

Unsupported monetary reforms, competing/occupation currencies, local scrip,
missing domestic CPI, ambiguous subunits and unverified release dates return
Unavailable with a specific explanation. In particular Brazilian mil-réis,
pre-reform Chinese yuan and Reichsmark are never treated as modern reais, yuan
or Deutsche Mark. Tiny nonzero amounts display as less than one cent, not zero.
