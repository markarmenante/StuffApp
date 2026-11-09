# Banknote face-value comparisons

Every banknote detail, including existing collection notes, displays one row
immediately above Description: Year (Series), Probable issue date, buying power
in the series year expressed in today's USD, and buying power of the same nominal amount today.
The amounts are derived from the note and shared public datasets; they are never
written into the purchase price, collector valuation or original description.

Mark's preference (2026-11-08) is to use the recorded series year for this
approximate comparison, even when the actual release date is unverified. The
Year (Series) field supplies the comparison year; an explicit Gregorian year in
Series is a fallback when that field is blank. A broad series range containing
the recorded year is compatible, but contradictory years require review. The
selected comparison year and its basis remain visible below the amounts.

Domestic CPI calculations keep the label **Buying power in series year · today’s
USD**. Historical monetary-parity and exchange-rate routes use **Series-year
benchmark · today’s USD**, with the reference country's CPI basis visible.
For example, a Hong Kong 1940 dollar uses its documented sterling parity and
a UK price benchmark; it does not claim a measured Hong Kong consumer basket.

`issue_date` is an independently editable Gregorian year or range. Check can fill
it only from an explicit release/issue/circulation statement for the complete
catalogue reference, with the normal server-stored evidence proposal. Printed
series and law dates are not actual issue dates. Editing this metadata does not
change the series-year comparison or overwrite any catalogue date. Comparison
ranges evaluate every intervening year and show the minimum/maximum result.
Unknown or conflicting comparison dates stay unavailable.

The preferred series-year calculation is face value, in comparable present monetary units,
multiplied by the domestic CPI ratio (latest / series year), then by the current
USD exchange rate. The today calculation uses the same nominal amount and FX,
without the inflation multiplier. This expresses the cost of the domestic
basket in USD; it is not an international PPP estimate. The latest CPI and FX
periods are visible below the row. Long-run historical indices and forecast
indices are marked as estimates. CPI more than two years old cannot supply a
current comparison. This does not imply a cancelled note remains spendable or
redeemable; see the expandable Basis & sources explanation.

Connecticut's 1776 lawful-money issues have a bounded historical exception:
six shillings per Spanish milled dollar supplies the face-value dollar equivalent,
then the 1776 US historical CPI estimates its purchasing power. The latest
Minneapolis Fed index is rebased using its 1982–84 mean to match the historical
index's 1982–84=100 base. This estimates the lawful-money/specie equivalent, not
an observed market discount on circulating colonial paper. It does not extend
to ambiguous Connecticut issues or competing currencies. Separate reviewed rules
apply the same source’s individual lawful-money relationships to other named
colonies; those rules never treat every shilling as sterling. Connecticut
currency has no current nominal exchange rate, so its buying power today stays
Unavailable even when the historical comparison can be calculated.

When local CPI or monetary continuity is unavailable, `banknote_historical_rates.py`
tries an explicit issuer/unit/year rule. Documented sterling, French franc,
Portuguese escudo and other parities support a **reference-country purchasing-power
benchmark**. This measures the reference basket at a stated monetary relationship,
not the issuing territory’s basket. For example, the Malayan board dollar’s
2s4d sterling relationship uses UK CPI; a Japanese occupation dollar does not
inherit that relationship. Legal parity does not prove an unrestricted retail
exchange rate, and circulating paper could trade at a discount.

A further bounded route uses the World Bank’s published **official annual FX**:
face amount ÷ selected-year local-currency units per USD × US CPI change. This is
a US-dollar basket benchmark, distinct from domestic inflation and from a current
exchange conversion. Only known denomination regimes are eligible: predecessor
pounds, reformed currencies and occupation money cannot inherit the later unit’s
historical rates. Annual rates can cover a year with a peg change without pretending
one peg lasted the whole year. Every year in a comparison range is evaluated.

The historical route does not invent a present nominal spending amount. US private
bank dollar notes can show their face-claim benchmark before issuer credit discounts;
that is labelled and is not their actual traded purchasing power or redemption value.
The 1964 Bahrain Currency Board authorization-year comparison explicitly applies
its first-issue October 1965 parity as a counterfactual series-year benchmark, never
as an observed 1964 exchange rate. Statutory unit changes, such as New Zealand’s
one old pound to two dollars, are separate from sterling exchange relationships.

`banknote_face_value.py` reads English number words, fractions, mixed numbers,
redundant written equivalents and compound shilling/pence values without changing
the saved denomination. The leading unit controls conversion: one pound with a
parenthesized 20-shilling equivalent is one pound. Ambiguous decimal/thousands
spellings, contradictory currency prefixes and conflicting equivalents remain
unavailable.

With the packaged November 2026 data, a 1776 Connecticut shilling compares to
about $6.36 today; a US two-dollar Series 1917 note compares to about $52.02.
Both use the displayed 2026 CPI estimate. These figures change when the shared
public data changes. The legacy API fields `at_issue` and `at_issue_display`
carry the series-year result for compatibility; `comparison_year` and
`comparison_basis` explain its meaning. `estimate_kind` distinguishes `domestic_cpi`,
`historical_parity`, `historical_fx`, `historical_quote`, `historical_price` and
`historical_range`; `estimate_basis` remains visible outside the expandable
sources. All historical methods display **Series-year benchmark · today’s USD**.
The domestic CPI method keeps its buying-power label.

Historical quotations retain the source's actual observation period and transaction
scope. Federal Reserve Table 173 supplies the national Chinese legal-tender yuan
for 1937 and a partial 1941 mean through July 25, including nominal quotations;
it does not identify the value of 1914 silver-yuan notes or Japanese military yen.
The Hong Kong 1941 quotation mean ends December 24 and excludes occupation; the
1935 silver-dollar annual average comes from HKMA/HKIMR, rather than applying the
late-year sterling peg to the entire year. These rates do not establish when an
individual note was first issued or spent.

For Bank of Greece occupation notes, the reviewed Athens price index is measured
in **old drachmas**. The formula is face amount × Athens index in 1939 (100.2) ÷
the selected year's mean price index ÷ 1939 drachmas per USD (125.090), followed by
US CPI change **from 1939**. This is an Athens-price benchmark through a historical
dollar anchor, not a modern Greek-currency conversion. The 1944 index covers only
January–10 November; that rule requires an identified old occupation issue and
excludes the new drachma. Hyperinflation makes a mean-price result very different
from values at individual dates. The source's monthly averages, reconstructed
where official reporting stopped, and this limitation remain explicit.

Intervals are preserved instead of replaced with a midpoint. The North Carolina
legal scale supplies the 1864 Confederate **new-issue** benchmark for April–December:
18–49 Confederate dollars per gold US dollar. *Haughton v. Merony* expressly applies
the scale to new-issue currency. Gold dollars are converted at the gold-unit ratio
4.8665 per pound sterling, then UK CPI is applied. This avoids treating Civil War
gold dollars as paper US dollars. It is a retrospective regional legal benchmark;
Virginia state-treasury claims and explicitly old-issue notes do not inherit it.
Iran's 1954 commercial-import comparison shows the two documented selling rates,
90.50 and 84.50 rials per dollar, before and after August. It describes two scoped
benchmarks, not guaranteed full-year extrema or all-transaction purchasing power.
Colombia's 1954 effective import rate and Laos's 1957 restricted official rate are
also labelled by transaction scope; free-market and export values could differ.

Data sources (anonymous public reads, no credentials or note data):

- [Minneapolis Fed CPI, 1800 onward](https://www.minneapolisfed.org/about-us/monetary-policy/inflation-calculator/consumer-price-index-1800-): historical estimates before 1913; the latest forecast, if present, remains labelled.
- [Historical Statistics of the United States, table Cc1–2](https://hsus.cambridge.org/HSUSWeb/toc/treeTablePathIdCc1-2.html): 1774–1799 reconstructed CPI; the 1776 estimate is 8.735 on the 1982–84=100 base.
- [Colonial Williamsburg, The Economic Role of Williamsburg, table XIII](https://research.colonialwilliamsburg.org/DigitalLibrary/view/index.cfm?doc=ResearchReports%5CRR0066.xml): Connecticut lawful-money valuation of six shillings per Spanish milled dollar.
- [Bank of England inflation calculator](https://www.bankofengland.co.uk/monetary-policy/inflation/inflation-calculator): long-run British CPI and latest monthly CPI. Historical estimates are labelled; complete years use annual averages.
- [World Bank / IMF CPI FP.CPI.TOTL](https://data.worldbank.org/indicator/FP.CPI.TOTL): 40 supported country series, mostly from 1960 onward, subject to country availability. World Bank data attribution: CC BY 4.0.
- [ECB reference rates through the existing Frankfurter provider](https://api.frankfurter.dev/v1/latest?base=USD): quotes are units per USD, inverted once for USD per unit.
- [ECB fixed euro conversions](https://www.ecb.europa.eu/euro/intro/html/index.en.html): explicit old-unit-to-euro factors, not a general rule for every obsolete currency.

- [Jordà–Schularick–Taylor Macrohistory Database, release 6](https://www.macrohistory.net/database/): historical CPI for reviewed reference economies. Missing observations are rebased at a shared 2010 observation; current World Bank observations retain precedence. Historical FX columns are deliberately excluded because several have been adjusted for currency reforms.
- [World Bank / IMF official annual exchange rates PA.NUS.FCRF](https://data.worldbank.org/indicator/PA.NUS.FCRF): selected, explicitly gated currency units, with source year shown. Official rates may differ from accessible or unofficial rates. World Bank attribution: CC BY 4.0.
- Each monetary rule includes its own institutional source URL. These include central-bank histories, contemporary IMF and World Bank reports, monetary legislation and historical currency-board research. Rules distinguish CFA from CFP and Comorian francs, and national from occupation issues.
- [Federal Reserve, Banking and Monetary Statistics 1914–1941, Table 173](https://fraser.stlouisfed.org/title/banking-monetary-statistics-1914-1941-38/part-i-6408/fulltext): historical currency quotations, their units, nominal flags and partial-year dates. The selected facts are from the original US government publication, not a licensed third-party bulk dataset.
- [Bank of Greece, Greece from 1833 to 1949](https://www.bankofgreece.gr/BogDocumentEn/III.%20GREECE.pdf): Tables GR3_A and GR7_A, with the wartime price methodology and source breaks on pages 139–142. Prewar paper-drachma annual rates are separate from the wartime price-index method.
- [The Confederate Note Case, US Reports 86, page 552](https://www.govinfo.gov/content/pkg/USREPORTS-86/pdf/USREPORTS-86-548.pdf) and [Haughton v. Merony, 65 NC 124](https://calculators.law/caselaw/decisions/oeW8n7npk3dM/haughton-v-merony): the regional gold-value scale and its application to the 1864 new issue. The [US Gold Commission report](https://fraser.stlouisfed.org/title/report-congress-commission-role-gold-domestic-international-monetary-systems-339/volume-i-6346/fulltext) documents the gold units behind the sterling conversion.
- [BIS 1955 annual report](https://www.bis.org/publ/arpdf/archive/ar1955_en.pdf) and [IMF 1955 annual report](https://www.imf.org/external/pubs/ft/ar/archive/pdf/ar1955.pdf): the dated Iranian commercial-import selling-rate benchmarks.

Additional bounded rules retain their sources next to the factors: Egyptian
piastres before July 1947; Faroese/Danish parity; Greenland trading-post Danish
face claims with restricted redemption; old Israeli pounds; initial Ugandan
shillings and Somali somali; South Arabian dinars; early Burundi francs; Rhodesian
official dollar values subject to blocked exchange; Suriname guilders; selected
Peruvian soles de oro; Lebanese observed rates; and the documented UN national-income
conversion rates for Afghanistan and Peru. BEAC's CFA issuer alias is distinct from
the New Hebrides 1980 annual exchange rule: the latter unit was renamed vatu at
unchanged value in 1981 and does not use CFP parity.

The separate derived JST file `data/banknote-historical-economics.json` retains
**CC BY-NC-SA 4.0** licensing and attribution. Citation: Òscar Jordà, Moritz
Schularick, and Alan M. Taylor (2017), “Macrofinancial History and the New Business
Cycle Facts,” *NBER Macroeconomics Annual 2016*, volume 31. Its license applies to
that dataset; it is not relicensed as application code. `scripts/extract-historical-economics.py`
recreates the CPI subset from the official R6 Stata download; pandas is a research
utility only and is not a runtime dependency. `scripts/update-historical-fx.py`
refreshes the separate public World Bank annual FX snapshot. No collection records
are inputs to either script.

`data/banknote-economics.json` provides a verified initial public-data snapshot
for supported calculations without per-note backfills or provider calls.
`banknote_economics.py` refreshes shared CPI monthly and FX daily in a bounded
background thread, retaining each last good source on failure. Historical source
subsets remain versioned, reviewable snapshots. The data cache is local to each
deployment’s DATA_DIR; no collection or owner data is shared. No AI call runs when
viewing this row. The endpoint applies the detail page’s row visibility checks.
Tests disable refresh and use synthetic collection rows.

Unsupported monetary reforms, competing/occupation currencies, undocumented
historical relationships, ambiguous subunits and unresolved comparison dates
return Unavailable with an explanation. In particular Brazilian mil-réis,
unsupported pre-reform Chinese yuan and Reichsmark are never treated as modern
reais, yuan or Deutsche Mark. Reviewed 1937/1941 fabi quotations are explicit
exceptions, not a general Chinese-yuan conversion. Multiple-rate regimes, missing
denominations and unresolved dates retain specific explanations. Tiny nonzero
amounts display as less than one cent, not zero.

Regression coverage: `tests/test_banknote_economics.py`,
`tests/test_banknote_historical_economics.py`, and the desktop/mobile
`browser-tests/tests/banknote-economics.spec.ts`. Both Python runners include
the economic suites. No personal record identifiers or private inventory are
stored in the tests or historical data files.
