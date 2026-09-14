# Opportunity Radar Company Evidence Acceptance

## Scope and Status

The existing Radar pipeline, FactStore, full/compact contract, freeze receipts,
taxonomy and final-judgement boundary are retained. This is an additive evidence
extension, not a second Radar. Auction, Daily Close and formal-review scoring are
unchanged. Overall evidence completeness remains **PARTIAL**.

Machine-readable acceptance, including complete top-10 themes and top-20 companies:
`reports/opportunity_radar_acceptance/2026-09-15_morning.json`.

Canonical production delivery:

- `data/opportunity_radar/2026-09-15_morning.json`
- `data/opportunity_radar/2026-09-15_morning_compact.json`
- `data/opportunity_radar/2026-09-15_morning_receipt.json`
- `data/opportunity_radar/coverage/2026-09-15_morning.json`
- `data/opportunity_radar/diagnostics/2026-09-15_morning_production.json`

Schema remains `opportunity_radar_objective.2`; added facts and candidate fields are
backward compatible. Score methodology is versioned separately as
`objective_evidence.1`. The packet role remains `OBJECTIVE_OPPORTUNITY_EVIDENCE`
and `final_judgement_owner=chatgpt`.

## A. Coverage Interpretation

The 16 category arrays now have admissible real evidence, compared with 12 before
this extension. **16/16 is category presence, not complete coverage or a quality
score of 100.** All categories remain PARTIAL because continuity, product-level
metrics or original historical vintages are incomplete.

The focused snapshot contains 10 technology observations, 2 distinct expectation
comparisons, 8 competition disclosures, and 35 company price/fundamental feature
records. Economic evidence covers 14 companies and 92 source-backed relation
records. Multiple independent statements about the same company/product remain
auditable evidence, not 92 independent beneficiary companies.

There are 44 company evidence-screen records, but only three satisfy the minimum
score coverage. This is not a claim that 44 stocks have demonstrated investment
alpha. The audit separates scorable companies from total company records.

## B. Source Status

New production inputs include official CNINFO annual-interim disclosures and issuer
forecasts, AMD IR releases, NVIDIA's newsroom, and existing FactStore daily bars.
CNINFO discovery scans a bounded 100-result page per issuer, validates the security
code and report title, and retains the discovery response. The 22-issuer watchlist
is retrieval scope only, not evidence of a supply relationship.

Technology classification uses local body predicates, not titles. Generic business
descriptions, overly broad report-table extraction, planned production and negated
production cannot establish mass production. A 1.6T switch-PCB disclosure remains
PCB evidence; it does not prove optical-module production.

Public Taiwan monthly issuer revenue, NBS releases, DRAM spot quotes and existing
commodity feeds remain connected. Licensed consensus, HBM/contract prices,
product inventory/utilization, forward PE and valuation vintages are still absent
or incomplete. Overseas semiconductor/IR coverage is not comprehensive.

## C. Expectations and Relationships

Two real comparisons demonstrate the production path:

- AMD 2026 Q2 revenue: prior issuer guidance USD 11,200 million versus reported
  USD 11,536 million, +3.0% relative to that guidance point.
- Dinglong 2026 H1 attributable profit: CNY 525 million forecast midpoint versus
  CNY 529.43671039 million reported. The result is **within the disclosed range**,
  not a demonstrated market-consensus beat.

Both sides retain source dates, actual observation timestamps, body evidence,
accounting basis, units, period and provenance. YoY fundamentals remain a separate
comparison and cannot establish expectation revision. The generic comparator
supports all ten requested metrics, but only revenue/earnings currently have live
production parser examples. Other metric types are not claimed as connected feeds.

Relationships retain null unknown exposures. CLASSIFICATION_ONLY and PARTIAL
relationships cannot become verified transmission edges. A producer disclosure is
terminal exposure evidence: two companies sharing a product do not establish a
customer/supplier relationship. Actual production paths are one-hop; second/third
order traversal remains tested but no unsupported real chain is manufactured.

## D. Objective Score

Weights: fundamentals 20, expectation 20, industry 15, technology 10, supply/demand
10, valuation 10, price 5, catalyst 5, evidence 5. Crowding and downside each deduct
up to 10 points. Every available component and weighted contribution is retained.

The total is not renormalized upward when inputs are absent. At least 40% weighted
coverage and one economic component are required; otherwise the total is null.
Missing risk evidence is unknown, not a zero-risk assessment. Confidence is LOW
below 60% coverage, MEDIUM below 85%, and cannot be HIGH with unknown risk inputs.

Descriptive transforms are explicit: reported fundamental change maps to
`clip(50 + change_pct/2)`, expectation revision to `clip(50 + revision_pct)`, and
20-session price response to `clip(50 + return20)`. Technology stages map to
10/25/40/60/80/100 evidence points. These are fixed research-input transforms,
not calibrated return probabilities. Industry, supply and valuation components
stay null without sufficient supporting inputs.

Company order is a mechanical score/coverage/code sort. Theme order is evidence
count/name order. Neither is ChatGPT's final opportunity ranking. Main drivers,
relations, expectation comparisons, divergence, risks and confidence for the first
20 companies are in the JSON acceptance report; missing totals are not filled to
complete a top-20 list.

## E. Time and Acceptance Limits

September 14 daily bars were genuinely retrieved through the existing Tushare
adapter into the existing FactStore: 5,550 rows. Price windows compound exchange
daily percentage changes and require complete trading-day windows; suspension or
conflicting duplicate days produce null, not shortened lookbacks.

September 15 Morning uses September 14 prices, never September 15 close data.
Historical documents first retrieved now are labeled HISTORICAL_BACKFILL and do
not enter overnight change candidates or historical lead-time success statistics.

The existing September 10, 11 and 14 LIVE snapshots and receipts remain unchanged.
September 14 Morning was unavailable in main and is not reconstructed as LIVE.
September 14 enhanced EOD is explicitly under `data/opportunity_radar/replay/`.
September 15 EOD awaits an actual close; its new behavior is integration-tested.
Preacceptance revisions are retained with raw data and receipts in the existing
quarantine tree, rather than deleted or presented as accepted production.

Validation commands:

```text
python -m compileall -q src tools scripts tests
python -m pytest tests/unit/test_radar_company_evidence.py tests/unit/test_opportunity_radar.py tests/unit/test_opportunity_radar_enrichment.py -q
python -m pytest -q
python tools/run_opportunity_radar_production.py --date 2026-09-15 --snapshot MORNING
python tools/build_opportunity_radar.py --date 2026-09-14 --snapshot EOD --replay
python tools/audit_opportunity_radar.py --date 2026-09-15 --snapshot MORNING
```

The full suite includes the pre-existing real-data gate test. Its skip is reported
as a skip, not a successful production test. The separate real Radar production
run and source/receipt verification provide the production acceptance evidence.

Final results: compileall PASS; focused Radar tests **208 passed**; full suite
**623 passed, 1 skipped**. The skipped September 1 legacy end-to-end data test did
not meet its existing source quality gate; no threshold was lowered. The accepted
Morning compact is **181,747 bytes**, below the 200,000-byte regression limit.

The 60 original FactStore partitions referenced by the price evidence receipt are
included in delivery (June 23 through September 14, approximately 19.6 MB). This
prevents Cloud execution from relying on an untracked local-only history cache.
