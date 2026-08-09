---
name: fair-price
description: Appraise collectibles and judge offers against the market — watches, coins, banknotes, art, cameras, lenses, pens, rifles, vehicles, and anything else collectible. Use this whenever Mark asks what something is worth, whether a price is fair, whether to buy or sell at a quoted number, to value an item in the collection app (stuff.armenante.com), or to evaluate an incoming dealer/auction offer from email or messages — even if he doesn't say the word "appraise". Also use it before recommending a purchase price, counteroffer, or insurance value.
---

# Fair-Price Appraisal

Produce a defensible fair-value range for one collectible item, grounded in
real sales — never a single guessed number, never uncited.

## Method

### 1. Identify the item precisely

An appraisal is only as good as the identification. Pin down the
category-specific identity before touching prices:

- **Banknotes**: country, denomination, series/date, Pick # (US: Friedberg #),
  grade + grader (PMG/PCGS Banknote), EPQ/star, serial if relevant (fancy
  serials carry premiums).
- **Coins**: country, denomination, date + mintmark, variety, grade + grader
  (PCGS/NGC), designation (FB, FBL, CAM, RD…).
- **Watches**: brand, model, reference number, movement, dial variant,
  production era, box/papers status, service history if known.
- **Art**: artist, title, medium, dimensions, date, edition (if print),
  signature, provenance/exhibition history.
- **Cameras/lenses**: maker, model, version (mark/serial era), mount,
  functional + cosmetic condition.
- **Pens**: maker, model, filling system, nib size/material, era, condition.
- **Firearms**: maker, model, caliber, era, condition class — value research
  only; leave transfer/legal questions alone unless asked.

If the item lives in the collection app, its record (cert number, grade,
purchase price, images) IS the identification — use those fields verbatim.
When a certification number is given, verify it on the grader's cert-lookup
page; a cert that doesn't match the described note/coin is a finding in
itself, not a footnote.

### 2. Find comparable SALES, not asking prices

Realized prices are evidence; listings are hopes. Search the venues in
`references/sources.md` for the category. Aim for 3–6 comparables, same item
and grade where possible, adjacent grades otherwise. Record for each: venue,
date, grade, realized price. Prefer sales within ~3 years; older comps need a
market-drift caveat.

### 3. Adjust to THIS item

- **Grade steps matter non-linearly.** One grade point near the top of the
  scale can double a price. Interpolate between grade comps, don't average.
- **Population/rarity**: check pop reports (PMG/PCGS/NGC) when the grade is
  high — a top-pop or low-pop item breaks the price curve upward.
- **Auction math**: a realized auction price already includes ~20% buyer's
  premium — it is what a buyer actually paid. A fair private-sale price sits
  between auction hammer and full dealer retail.
- **Category multipliers**: watches with original box + papers +15–30%;
  EPQ/star on notes; original-surfaces vs cleaned on coins; artist market
  momentum for art.

### 4. Output — always this shape

```
## <Item, one line>
**Identification**: <the pinned-down identity, cert verified: yes/no/n-a>
**Fair value**: $X–$Y private sale · $A–$B at auction (net) · $R retail replacement
**Comparables**:
- <venue, date, grade — $price>
- ...
**Verdict** (when a price is on the table): <good deal / fair / rich / walk>
  — asking $N is Z% above/below the fair private range.
**Confidence**: high/medium/low — <what would tighten it>
```

State confidence honestly. Thin comps, unverifiable grade, or a hot/volatile
market all cap confidence at medium. If comps genuinely can't be found, say
so and give the nearest anchor (same type different grade, price-guide value
with the guide named) — never fabricate a comp.

## Evaluating an incoming offer (email / message)

When the input is a dealer email, auction alert, or message offering an item:

1. Extract the claims: item, grade, cert #, price, seller.
2. Run the appraisal above on the claims.
3. Screen for red flags before the verdict: stock/borrowed photos, cert
   number that fails lookup or matches a different item, a price far below
   fair value from an unknown seller (bait), pressure language, payment by
   irreversible rails only.
4. Collection fit: when `references/collection-profile.md` (or the live
   collection) is available, say whether the item fills a stated gap or
   duplicates a holding — a fair price on a gap-filler outranks a bargain
   duplicate. Skip silently when no profile is on hand.
5. Verdict: **pursue / counter at $X / pass**, one sentence of reasoning.
   When countering, anchor at the low end of the fair private range.

## Ground rules

- Every number cited gets a source. No source, no number.
- Currency is USD unless the item's market trades elsewhere (state the
  conversion date if converting).
- Mark's cost basis (purchase price in the app) is context for the verdict
  ("you're up/down ~N%"), never evidence of value.
- This is research, not a formal USPAP appraisal — say so if the value is
  needed for insurance, estate, or legal purposes, and size the retail
  replacement figure for that use.
