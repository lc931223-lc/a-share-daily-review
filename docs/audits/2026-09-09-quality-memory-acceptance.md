# Quality And Formal Memory Acceptance

Baseline: `63022fb6408fbfad7a13b41ba6fc4460fc01006c`.
Real acceptance date: 2026-09-08; replayed adjacent support date: 2026-09-07.

## Root Causes And Corrections

- Empty API responses lacked independent zero verification. Same-date daily prices
  now conservatively exclude possible lower bands; ambiguous cases remain unavailable.
- Objective support defaulted to PASS despite failed market quality. It now inherits
  PARTIAL_WITH_UPSTREAM_FAILURE; daily manifests expose upstream_warnings and degraded_inputs.
- Free-text objective checks were judged using price direction and mixed with formal
  validation. This statistic is withdrawn. Formal predicates are evaluated separately;
  free text without a supported predicate remains NOT_EVALUABLE.
- Prior formal review discovery mixed legacy/support concepts. Canonical v3 records
  live only in data/formal_reviews; exact previous trading date is mandatory.
- Industry-only and concept-available days switched the candidate universe. The same
  existing scoring path now retains previously monitored industry candidates.
- Historical file offsets were mistaken for trading-day offsets. Prior feature windows
  now resolve against the real exchange calendar, not file count.

## Real Results

Market Packet remains **FAIL, score 69**. This is not a claim of full data repair.
5,549 daily rows passed; the empty limit-down pool remains **UNAVAILABLE** because
21 securities need exact band/exemption evidence. Tushare stk_limit permission is
unavailable. It would be incorrect to label this real sample EMPTY_VALID.
The verified-zero path passes synthetic unit tests, without fabricating real zeros.

Formal support is **PARTIAL_WITH_UPSTREAM_FAILURE**. Across 15 themes / 615 factors:
3 CONFIRMED, 20 PARTIAL, 592 UNCONFIRMED. Confirmed market structure does not confirm
orders, earnings, policy or valuation. No final ChatGPT judgement was generated.

| Dimension | Available points / maximum across 15 themes | Coverage |
| --- | --- | --- |
| base_logic | 0 / 600 | 0%; no qualifying fundamental evidence |
| realization | 0 / 375 | 0%; no qualifying realization evidence |
| expectation_gap | 0 / 225 | 0%; NO_EXPECTATION_BASELINE |
| continuity | 118 / 150 | 78.67%; eleven 5D, four 1D windows |
| market_confirmation | 150 / 150 | 100%; fixed objective rubric |
| risk_deduction | 105 / 300 | 35%; absent risk inputs stay unavailable |

Coverage is evidence availability, not a final investment score or proof that all
risk dimensions are observed. Risk deduction is excluded from gross positive points.

Real lifecycle example: publishing (出版), VALIDATION -> MAIN_UP; strength 78.63,
one-day change +13.9443; positive evidence is objective theme strength, negative
evidence is empty, confidence MEDIUM. This is a quantitative candidate, not the
ChatGPT final lifecycle. Aliases share identity; parent-child relations do not merge states.

The 2026-09-08 previous formal date is exactly 2026-09-07. No canonical formal record
exists for that date: PREVIOUS_FORMAL_REVIEW_UNAVAILABLE, zero formal predictions,
hit_rate=null and weighted_hit_rate=null. Support hypotheses remain separately labelled
OBJECTIVE_SUPPORT_HYPOTHESIS and cannot enter formal hit rates.

## Delivery And Persistence

The daily entry imports data/formal_review_inbox/*.json automatically. The same
validated entry supports stdin and --inbox. It enforces schema, exchange dates,
previous_trade_date, 41 factors, evidence tiers, Tier-4 restrictions, no future
evidence, owner=chatgpt, idempotency and SHA provenance. Conflicting same-date formal
content is rejected. The scheduled workflow persists canonical formal reviews and
separate research_feedback/formal outputs. A changed prior formal file invalidates
cached context, and changed upstream content invalidates support.

Auction remains optional and unavailable, with optional_missing=true. Its production
integration is not claimed complete. External scheduled execution requires configured
GitHub Actions/Secrets; this local acceptance does not establish a successful cloud run.

## Verification

- Full non-real-data suite: 293 passed, 1 deselected.
- Targeted tests: 23 passed. compileall passed for src, scripts, tools and tests.
- Market Packet, adjacent-day intelligence/context/support and daily manifest rebuilt.
- No new research model, trading signal, Dashboard or PDF work.

Remaining blockers: exact lower-band/exemption coverage, qualifying theme-linked
fundamentals/realization, expectation baselines, missing risk observations, and actual
ChatGPT structured formal review delivery. No fabricated data or quality-score uplift.
