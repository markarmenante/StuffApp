# Coin buying power, metal value and fineness

The coin detail panel, immediately above Description, derives two independent
comparisons. Viewing it never edits a coin, its purchase price, photos, weight,
metal, notes or ownership status. `GET /coins/<id>/economics` enforces the same
row visibility as the detail page. It can refresh public quote cache files,
but does not update collection records or call a model.

## Historical worker-pay comparison

The current historical rule is deliberately bounded to silver tetradrachms
attributed to Athens, mint Athens, region Attica, dated wholly within
480–400 BC. Numeric and text dates must agree. Other places, denominations,
metals and periods do not inherit this wage assumption.

[ASCSA, *An Ancient Shopping Center: The Athenian Agora*, pp. 7–8](https://agathe.gr/file?field=PDF&id=Agora%3APublication%3AAgora+Picture+Book+12&path=%2FAgora%2FPDFs%2FPicture+Books%2FAgora+Picture+Book+12.pdf)
identifies a tetradrachm as four drachmai and describes about one drachma per
day for skilled artisans in classical Athens. Thus a matching coin displays
approximately four days of skilled pay. The UI calls this a period proxy,
including for a coin whose range begins in 454 BC, rather than claiming an
observed wage for each exact minting year.

The modern analogy uses an assumed eight-hour workday and the
[BLS construction-laborers-and-helpers median of $22.44/hour for May 2025](https://www.bls.gov/ooh/construction-and-extraction/construction-laborers-and-helpers.htm).
It adjusts that modern benchmark from 2025 to the latest common-base US CPI
in the banknote public-data snapshot:

`4 days × 8 hours × $22.44 × CPI(current) / CPI(2025)`.

The packaged 2026 CPI estimate yields approximately $743.17. Both the wage
date and CPI period/estimate label are visible. This is a comparison with
modern worker pay, not an equivalent basket of goods and not a CPI series
stretched across 2,500 years. Collector prices are never inputs.

## Metal value

Gold (`AV`, `AU`, or Gold) and silver (`AR`, `AG`, or Silver) use:

`weight in grams × fineness / 31.1034768 × USD spot price per troy ounce`.

Unknown purity gives an explicitly labelled **Pure-gold/silver ceiling**, with
a ≤ sign and a visible 100%-metal assumption. Conflicting gold/silver labels,
plated metal, electrum, billon, unsupported metals, invalid weights and
unusable quotes produce a specific explanation instead of an invented value.
An explicit `.900`, `90%`, `900/1000`, or gold karat purity in Metal is accepted
if internally consistent; recorded fineness takes precedence only when it
agrees with such explicit composition evidence.

[`precious_metals.py`](../precious_metals.py) calls the anonymous
[Gold API](https://gold-api.com/docs) fixed public endpoints
`https://api.gold-api.com/price/XAU` and `/price/XAG`. No account, API key or
browser session is needed. It validates the symbol, USD currency,
`exchangeRate=1`, positive finite price and timezone-aware provider timestamp.
Requests have an eight-second timeout per metal and a 64 KiB response limit.

The shared `DATA_DIR/precious-metals.json` cache refreshes at most once per ten
minutes per process/path, with atomic file replacement. Each metal retains its
last valid quote when the other fails. A bundled verified snapshot allows an
offline initial view. The provider timestamp remains visible; quotes older
than ten minutes are explicitly stale, even when a network request succeeds
but the market/provider timestamp has not advanced. The page polls briefly
while a background refresh is active and checks again every ten minutes while
visible. Metal values exclude refining costs, dealer spreads and collector
premiums; they are not guaranteed sale proceeds.

## Persisted fineness and its evidence

The coin row stores `fineness` as a fraction above zero and at most one,
`fineness_basis` (`catalogue standard`, `assay`, or `estimate`), and
`fineness_source` (an HTTPS public source URL). A separate internal
`fineness_identity` signature binds the saved evidence to the coin's region,
mint, authority, denomination, metal and date fields. An identity change flags
the saved fineness for review rather than silently applying it to a different
type. Weight and purchase-price changes do not rewrite fineness.

The percentage editor saves the value and provenance atomically. It requires
the current identity and prior fineness state, so a stale form cannot replace
a newer edit. The generic single-field autosave and full-form path cannot
partially replace these fields. Research first shows a preview; **Save
fineness** records it. Existing fineness is never replaced by research.

Automatic research currently covers the bounded classical Athens type only.
[Healy, “Greek Refining Techniques,” *Revue Belge de Numismatique* 120 (1974), p. 29 n. 68](https://en.numista.com/catalogue/catalogues/pdf/1974_2.pdf)
reports very high purity for these tetradrachms. The rule proposes 0.99 with
the visible basis **published type estimate; specimen unassayed**. It does not
claim a statutory standard or an assay of the user's coin. The separate
archaic sixth-century assay averages are not applied to classical owls.

The existing **Check** workflow also offers this verified proposal. When
fineness is present, it shows the review dialog even for otherwise blank-only
fills. **Apply selected** on fineness writes its entire verified provenance
tuple, only if the fields are still empty and the current type still matches.
Unchecking it, cancelling, or merely viewing the proposal writes no fineness.
The generic coin model response has only a free-text sources string; its
uncited fineness guesses are ignored. Other coin types support documented
manual entries; broader automatic coverage needs additional verified rules.

## Verification

`tests/test_coin_economics.py` covers arithmetic, period/identity boundaries,
purity and currency conflicts, missing/stale quotes, cache failure retention,
read-only pages, explicit preview/save/Check application, stale writes and
preservation of unrelated record metadata. It is included in both regression
runners. The Playwright `coin-economics.spec.ts` uses synthetic coins and fixed
public-quote fixtures on desktop and mobile, including Cancel, Apply, reload
and retained provenance. Set `COIN_ECONOMICS_REFRESH=0` to keep tests offline.
