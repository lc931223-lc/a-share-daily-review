# Opportunity Radar V2.1 production acceptance

## Scope and outcome

The existing `opportunity_radar_objective.2` contract, observation FactStore,
immutable snapshots and objective-only boundary remain in use. This delivery is
PARTIAL coverage, not complete V2.1 acceptance. No investment conclusions or
scoring changes are introduced.

The verified local production snapshot is `2026-09-11_morning`, frozen at
`2026-09-11T01:13:26.314630+08:00`. Full size is 4,217,766 bytes; compact size is
194,660 bytes. This is an early-morning observation, not a complete overnight
sample through 08:10. It contains 52 change/risk candidates including two
shareholder-action evidence candidates for one issuer (002912). These are not
two independent investment opportunities.

The previous baseline had observations in six of sixteen categories. Current
coverage is twelve of sixteen, with six LIVE_OBSERVED provider labels, 439
Tier-1 observations and sixteen distinct company disclosure bodies parsed.
Counts are retained evidence records, not unique events or confirmed orders.
See `data/opportunity_radar/coverage/2026-09-11_acceptance.json` for all sixteen
categories, source tiers, historical/live counts and explicit limitations.

## Actual sources and semantics

| Source | Actual retrieval | Limits |
| --- | --- | --- |
| NBS official publications | 50 circulation-price survey items, utilization, six monthly/YTD energy-production rows, CPI/PPI/PMI publications | Survey prices are not exchange transactions; production is not inventory |
| DRAMeXchange public tables | 17 DRAM/Flash/module/wafer spot quotes | Not contract prices, HBM pricing or licensed history; table dates retained |
| TWSE/TPEX official open data | Monthly total issuer revenue for sixteen selected companies | Returned July revenue published August 17; not September revenue or product-level sales |
| CNINFO | Bounded live disclosure discovery and official PDF body retrieval | One page of thirty discovery records, not complete market coverage |
| SZSE official PDF | Three-Circle 2026 interim report | Historical body evidence, not a new September event |
| SEC companyfacts | XBRL adapter and filing-vintage tests | Actual NVDA request returned HTTP 403; no successful US production coverage claimed |

NBS, CNINFO and SZSE provide Tier-1 original publications. The existing exchange
source-tier policy treats overseas exchange data as Tier 2. Public spot tables
are Tier 3. Raw response bodies and JSON provenance receipts are stored under
`data/raw/opportunity_radar`; content hashes are verified when reading snapshots.

Memory, optics, PCB/CCL, MLCC, probe/test and advanced packaging have actual
issuer/body evidence. Issuer membership in a retrieval watchlist is NOT a
verified supplier/customer relationship. Optics and MLCC have two explicit
official-body company-to-product edges. Depth counts are 2/0/0; no inferred
second/third-order beneficiary edges are fabricated.

## Disclosure integrity

The accepted extractor is `DISCLOSURE_BODY_V21_3`. Confirmed orders require an
executed company-specific statement and explicit amount, without conditional,
planned, framework, pledge or financing language. Shareholder actions require
executed quantity evidence; lockup promises are not reductions. Monthly and YTD
energy production have separate metric identities and period bases.

Real-text inspection found false positives in two unpublished intermediate
snapshots. Their original bytes and receipts are retained under
`data/opportunity_radar/quarantine/`, marked WITHDRAWN. Old parser evidence and
the ambiguous earlier energy metric are ineligible; snapshot validation rejects
them. They are not production snapshots and do not enter coverage counts.

Accepted confirmed-order count is zero. Confirmed customer-validation and
observed commercialization-transition counts are zero. Missing evidence is not
replaced by titles, framework agreements or an assumed transition.

## Point in time and production operation

`published_at`, actual `first_seen_at`, retrieval time and raw body versions are
retained separately. Newly fetched historical series are RETROSPECTIVE_SERIES;
old disclosures are context, not newly occurring events. They are excluded from
lead-time cohorts. Existing retained records span six first-seen dates; new
V2.1 collection has only one observed day. Mature lead-time samples and completed
real counterexamples both remain zero.

The workflow `Opportunity Radar production` schedules 08:10 and 16:10 Shanghai
time on weekdays. Production checks the real trading calendar and temporal
boundary, preserves frozen snapshots, retries twice, persists failed diagnostics
without failed packets and always uploads diagnostics. Failure remains nonzero.
GitHub scheduling can be delayed; a configured cron is not an SLA or a verified
scheduled run.

```powershell
python tools/run_opportunity_radar_production.py --date auto --snapshot MORNING
python tools/run_opportunity_radar_production.py --date auto --snapshot EOD
```

The September 10 EOD artifact under `data/opportunity_radar/replay/` is explicitly
REPLAY, built only from admissible historical evidence. No September 11 live EOD
is claimed before close. A manual Morning rerun of the frozen date validates and
reuses the existing snapshot rather than collecting another version.

## Remaining gaps and verification

No stable licensed consensus estimates, memory contracts/HBM prices, operational
inventory history, 800G/1.6T shipment series, CCL/material prices, MLCC utilization
or delivery series, probe/HBM order series, full overseas IR coverage, original
macro release vintages or mature historical lead-time cohorts are available.
These gaps remain explicit in diagnostics and the coverage audit.

Targeted tests cover body parsing/negation, real-text regressions, spot/futures
semantics, technology sources, vintage boundaries, immutable snapshots,
relations/provenance, compact limits, production failure persistence and
objective-only integration. Full non-real-data tests and compileall are run for
delivery. Auction receives only read-only Morning context after its scoring;
Daily Review scores are unchanged.
