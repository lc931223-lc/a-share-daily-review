# Opportunity Radar V2: First-Phase Operations and Limits

This is an objective evidence layer, not a stock recommendation engine. It is a
first-phase implementation, NOT complete live coverage of all 16 signal families.
The first frozen snapshot must not be advertised as a completed historical
leading-signal validation.

## Commands

Run Morning collection and freeze once, before 08:20 Asia/Shanghai:

```powershell
python tools/build_opportunity_radar.py --date auto --snapshot MORNING --collect
```

Run EOD after the close. Unlike Morning, EOD collection includes that day's closed
session; it does not silently collect yesterday's data:

```powershell
python tools/build_opportunity_radar.py --date auto --snapshot EOD --collect
```

Import independently sourced, structured facts with their local raw receipt:

```powershell
python tools/build_opportunity_radar.py --date auto --snapshot MORNING --import-json data/radar_inbox/observations.json
```

The import is a JSON array of observations. Each record identifies signal_type,
entity, metric, value (nullable), facts, source, source_tier, source_date,
published_at (nullable if unknown), first_seen_at, event_date, effective_date,
source_path, url and provenance.sha256. The local source receipt must exist within
the project and match the digest. This is not permission to submit an unsupported
company relationship or to infer a stage from a title. Dates and evidence must
come from the actual receipt, not from the desired replay date.

Replay a closed historical interval without claiming it was a live run:

```powershell
python tools/build_opportunity_radar.py --date 2026-09-09 --snapshot EOD --replay --replay-start 2026-06-01 --replay-end 2026-09-09
```

The interval summary enumerates every real trading session, including sessions
with no admissible observations. It does not manufacture missing daily history.
There is no automatic scheduler installed by this change. Run these commands from
the production scheduler after the required source archives are available.

## Contract and Storage

- Schema: `opportunity_radar_objective.2`, generated from
  `src/opportunity_radar/schema.py` into the checked-in schema file.
- All 16 signal families have a typed section with required metadata and
  category-specific field presence. Unsupported values are null, not zero.
- The common metadata says OBJECTIVE_OPPORTUNITY_EVIDENCE and assigns final
  judgement to chatgpt. A recursive guard rejects final-research fields and final
  lifecycle labels.
- Facts use the existing FactStore's `opportunity_observation` dataset. No new
  quote database or duplicated A-share OHLCV table is created.
- Content-addressed partitions retain observation revisions. Repeated ingestion
  of the same semantic fact preserves its original first_seen_at.
- Raw API responses and source-version receipts are immutable audit evidence.
  Source SHA checks tolerate only Git LF/CRLF text transport, not content changes.
- Full and compact snapshots have canonical-hash receipts. Re-running a frozen
  Morning returns the existing snapshot; EOD writes another path. A missing
  compact file can be recovered from the frozen full file.
- Retrospective outputs live under `data/opportunity_radar/replay/` and are marked
  AS_OF_REPLAY. They cannot masquerade as a production Morning context.

## Time and Calculation Semantics

A fact must have been observed by the as-of cutoff. Known publication timestamps
must also be no later than the cutoff. A fetched historical series with an unknown
publication vintage is usable after its actual retrieval time, NOT before it.
Effective dates can remain future dates for announced plans; this does not make
an announced project an operating asset.

Price changes, slopes and percentiles use ordered source observations, explicitly
identified by `window_basis`. They are not calendar-day interpolation. Continuous
futures can contain roll effects and are never labeled spot prices. Missing
windows stay null. Partial A-share trading-day histories do not generate daily
change candidates across a missing session.

Positive/negative candidate means an observed numerical or explicitly evidenced
event change. It does not mean that a related equity should rise/fall. Inventory
and credit-spread increases use an explicitly reversed directional convention.
No news counts or headline sentiment determine candidate significance.

The mechanical compact order is source tier, absolute measured change, freshness,
completeness and stable ID. The prescribed category caps are enforced. Category
associations with DRIVER_TYPES 1..41 are LOW-confidence indexing links, NOT causal
confirmation or future importance weights.

Commercialization/order stage claims require structured body evidence. A title,
a rumor, a negated statement or a prospective statement cannot confirm an order,
mass production or revenue. The classifier is deliberately conservative; full
automatic PDF-body extraction is not implemented in this phase.

## Relations and Handoffs

The taxonomy contains 19 chain/family groups, including the requested storage,
optical, probe/test, MLCC, PCB/CCL, packaging, equipment and robot subdivisions,
as well as non-technology sectors. It is a classification vocabulary supplied by
the task specification, NOT a verified company-beneficiary graph.

Optional evidenced edges are read from `data/reference/opportunity_relations.json`.
Each edge includes from/to, relationship_type, exposure fields (nullable), source
timestamps, url/source_path, provenance and confidence. Traversal is cycle-safe
and limited to three edges; every edge must be admissible as of the cutoff.
There are currently no verified production company/transmission edges.

`read_only_summary(root, date)` is available to Auction consumers without touching
their scoring. Daily Review reads this optional Morning summary into full/compact
Review Context. A missing/corrupt radar remains optional, and score_effect is
always zero. No Auction pipeline or frozen Auction file was modified.

## Feedback Definition

The fixed market rule is relative five-session return >=3 percentage points,
breadth >=0.60, and amount / prior-20-session average >=1.20. It is descriptive,
not an investment judgement. Parameters are fixed in `feedback.RULE` and do not
adapt to results. Complete subsequent 20-session windows are required for rate
denominators. Missing and right-censored cases are excluded, not treated as wins.

Lead time also searches the prior 20-session context. If the market met the rule
before the signal, the reported lead is negative, not falsely positive. This is
the first observed match within the declared window, not a claim about all
history. Signal dates persist across consecutive same-direction snapshots.

Survival/source-confirmation rates remain null when independently verified
follow-up values are unavailable. They must not be filled from news popularity
or interpreted as recommendation win rates.

## First Real Acceptance

First live Morning: `2026-09-10_morning.json` and its compact file. It contains
5 positive changes, 3 negative changes and 0 company-specific change candidates.
All eight directional candidates are numerical commodity/freight observations.
The full snapshot has 270 observations with category-to-factor indexing links;
this 100% indexing coverage is not a claim of 270 confirmed investment drivers.

Eight real numerical series responded: coking coal, coke, corn, soybean meal,
methanol, copper and aluminium continuous futures (Sina), and BDI (Eastmoney).
Their source tier is 3. Archived CNINFO/government/exchange disclosure metadata
is reused with official-domain source classification; title-only items stay
PARTIAL and do not become hard confirmations. The frozen snapshot has observations
in 6 of the 16 families; only the price family has directional candidates.

The replay covers 72 trading sessions from 2026-06-01 through 2026-09-09.
Only 4 sessions contain admissible archived observations. The historical EOD
September 9 replay has zero directional candidates. No pre-September-9 first
commodity, freight, agriculture, CPO/PCB, storage, probe/test or MLCC discovery
date has been established. The new numerical sources were first collected on
September 10. Median lead time and false-positive rate are therefore unavailable,
not zero. Ten counterexample scenarios are synthetic tests, not claimed real
historical case studies.

Still missing: reliable point-in-time inventory/utilization histories, official
spot/contract price histories, fiscal implementation amounts, technology and
commercialization body evidence, quantified orders and profit contribution,
earnings/consensus revisions, competition shares, overseas Capex/orders, macro
vintages, valuation comparisons, verified company exposures/relations, and mature
forward confirmation samples. No conclusion about 9/9 price-action causes is
made from these gaps.
