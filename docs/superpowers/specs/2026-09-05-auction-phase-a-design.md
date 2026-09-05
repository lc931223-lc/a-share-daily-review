# A-share Call Auction Phase A: Source Audit and Design

Date: 2026-09-05 (Asia/Shanghai)

Audit trade date: 2026-09-04. The audit was run on a Saturday, so no current-day auction observations were fabricated. All data tests used historical interfaces for 2026-09-04. This document is the Phase A1 deliverable; it does not implement the collector, scoring pipeline, Auction Packet, Dashboard, PDF, or trading logic.

## 1. Decision Summary

Use the following source routing for the first implementation:

- `AUCTION_PROCESS_PRIMARY=eltdx`
- `AUCTION_PROCESS_FALLBACK=klineshare_v2`, enabled only after an API key and `auction_v2` permission pass a trading-day acceptance test
- `TICKDB=OBSERVATION_ONLY`; it is not a process fallback because the documented interfaces expose ticker/depth/trades rather than a dedicated virtual-match auction series
- `OPEN_PRICE_VALIDATION_PRIMARY=tencent_realtime`
- `OPEN_PRICE_VALIDATION_FALLBACK=eastmoney_realtime`
- `OPEN_PRICE_EOD_RECONCILIATION=tushare_daily`
- `TUSHARE_AUCTION=OPTIONAL_UNAVAILABLE` for the current token

This routing favors a source that actually returned 2026-09-04 process data over a source whose capability is currently documentation-only. KlineShare is architecturally attractive for batch and full-market acquisition, but it cannot become active primary/fallback until credentials, permission, field units, and trading-day latency are verified.

## 2. Actual Test Scope

The 20-stock sample covers the required market and behavior groups:

| Group | Codes |
|---|---|
| Large-cap/main board | `600519.SH`, `601318.SH`, `000001.SZ`, `000858.SZ`, `002594.SZ` |
| 2026-09-04 limit-up samples | `003040.SZ`, `603162.SH`, `000592.SZ`, `000876.SZ` |
| 2026-09-04 limit-down samples | `603256.SH`, `000977.SZ` |
| ChiNext | `300308.SZ`, `301489.SZ`, `300750.SZ` |
| STAR Market | `688981.SH`, `688170.SH`, `688435.SH` |
| Beijing Stock Exchange | `920075.BJ`, `920071.BJ`, `920176.BJ` |

Actual results:

- eltdx 3 repeated rounds: process `60/60` successful, formal 09:25 opening match `60/60` successful.
- Process request latency per stock: round totals `996.6ms`, `506.3ms`, `626.5ms`; median `17.4ms`, `17.2ms`, `21.3ms`; warm-round p95 `42.9ms` and `59.9ms`.
- Formal opening-match request latency per stock: round totals `1591.0ms`, `1533.6ms`, `1546.1ms`; median `79.5ms`, `82.2ms`, `84.2ms`.
- The 20 formal 09:25 prices matched Tushare `daily.open` exactly; maximum and mean error were both `0.000000%`.
- KlineShare v2 returned HTTP `401` in `299.6ms` because no API key is configured. This validates reachability and authentication behavior, not data quality.
- TickDB ticker/depth returned HTTP `403` in `166.8ms` and `125.6ms` because no API key is configured. This validates reachability only.
- The configured Tushare token returned a permission error for `stk_auction_o`; the same token returned 5,548 `daily` rows for 2026-09-04.

## 3. Candidate Source Audit

Scores are 0-10 and separate documented capability from runtime evidence. A low runtime score caused by missing credentials is not a claim that the provider's production data is poor.

| Source | Coverage | History | Realtime | Fields | Stability | Cost | Latency | Total / 70 | Runtime status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| eltdx 3.1.3 | 10 | 8 | 6 | 7 | 8 | 10 | 8 | 57 | Historical 20-stock test passed; live auction not tested on Saturday |
| KlineShare | 10 | 9 | 9 | 8 | 4 | 5 | 5 | 50 | Reachable, but no key; data, quota, and latency unverified |
| TickDB | 7 | 3 | 8 | 6 | 4 | 2 | 5 | Reachable, but no key; no dedicated documented auction-process endpoint |

### 3.1 eltdx

Verified markets: Shanghai main board, Shenzhen main board, ChiNext, STAR, and BSE. `client.auctions.series(code, date)` returned virtual-match price, matched volume, unmatched volume, and unmatched direction. `client.trades.opening_match_history(code, date)` returned the formal 09:25 price and volume.

The process series is event-like, not a guaranteed fixed one-second grid. Across the 20 samples, 2026-09-04 auction-window point counts ranged from 17 to 197. Required key-minute coverage ranged from 5 to 9. Most series ended at 09:24:57-09:24:59, so a process point must not be treated as the formal 09:25 result.

Historical probes for `600519.SH`:

- 2026-03-10: 104 process points plus formal opening match
- 2025-09-04: 116 process points plus formal opening match
- 2024-09-04: zero process points, but formal opening match available

Conclusion: suitable for immediate focused-pool process collection and at least a 120-trading-day baseline near the audit date, but historical retention is server-dependent. Backfill must record per-stock/per-date completeness instead of assuming a fixed retention period.

### 3.2 KlineShare

The official documentation describes two distinct auction permissions:

- `/v1/auction`: one stock, approximately 09:15-09:25, one-second points, latest trading day only; fields are time, virtual-match price, matched volume, and signed unmatched volume.
- `/v2/auction`: up to 500 symbols or full market, Shanghai/Shenzhen/BSE filters, historical `trade_date`, optional minute sequence, formal auction/open fields and amount.

`auction_v2` is a separate permission and the public catalog currently presents it as trial access rather than a normal included plan entitlement. No local key is configured. Therefore its coverage, units, full-market completion time, retention, and quota remain `UNVERIFIED`, despite strong documented capability.

### 3.3 TickDB

The official OpenAPI exposes ticker, depth, trades, intraday, and K-line endpoints and uses `X-API-Key`. Ticker supports up to 50 symbols per request; depth is single-symbol. Official pricing lists a seven-day free trial, then paid plans beginning at USD 99/month for all symbols, order book, trades, and one year of history.

Ticker and depth can supplement `last_price`, cumulative volume/turnover, bid/ask levels, and timestamps during 09:15-09:25. They do not document dedicated virtual matched/unmatched auction quantities or a historical auction-process endpoint. Reconstructing auction state from unrelated ticker/depth updates would introduce semantic and timestamp risk, so TickDB is not selected as a process fallback in Phase A.

### 3.4 Tushare

`stk_auction_o` is a separate-permission, post-close dataset with OHLC, volume, amount, and VWAP; it is not a 09:15-09:25 process feed. The current token lacks this permission, so status is `OPTIONAL_UNAVAILABLE` and must never block packet generation.

Tushare `daily` remains valid for end-of-day reconciliation. On the audit date it returned 5,548 rows, and all 20 sampled `open` prices exactly matched eltdx's formal 09:25 match.

## 4. Field Mapping and Truth Rules

### 4.1 `auction_snapshot`

Required normalized fields:

| Field | eltdx | KlineShare | TickDB | Rule |
|---|---|---|---|---|
| `match_price` | yes | yes | ticker proxy only | Process source only |
| `change_pct` | derived from previous close | v2 yes | ticker yes | Store derivation inputs |
| `matched_volume` | yes, raw unit is lots | yes, unit requires acceptance check | no dedicated field | Normalize to shares; preserve raw value/unit |
| `matched_amount` | estimated as price x lots x 100 | v2 amount | cumulative turnover, not proven matched amount | Add `value_kind=OFFICIAL/DERIVED`; never present estimate as official |
| `unmatched_buy/sell` | direction plus magnitude | v1 signed unmatched | depth is not unmatched auction quantity | Until direction semantics are cross-validated, preserve signed/raw direction and leave buy/sell null |
| `bid1/ask1 price/volume` | separate quote call only | realtime depth permission | depth endpoint | Optional, timestamp-aligned observation; never backfill from a later snapshot |
| `source_data_time` | point time | source time | timestamp | Required |
| audit fields | generated locally | generated locally | generated locally | `source`, batch, retrieval time, hash, schema, quality |

Add the following fields to prevent semantic loss: `raw_matched_volume`, `raw_volume_unit`, `matched_amount_value_kind`, `unmatched_signed_volume`, `unmatched_direction_raw`, `checkpoint_time`, `checkpoint_lag_ms`, and `is_formal_opening_match`.

Raw process observations are retained. For required checkpoints, select the latest source point at or before the checkpoint with a configurable maximum age. Missing checkpoints remain null and produce `PARTIAL`; do not forward-fill across the entire auction. The 09:25 checkpoint always uses the formal opening-match record when available.

### 4.2 `auction_daily_summary`

Store all fields required by the task plus:

- `baseline_observation_count_5d/20d/60d`
- `baseline_quality_status`
- `open_price_validation_source`
- `open_price_error_pct`
- `conflict_status`
- `process_checkpoint_coverage`
- `score_component_coverage`

`avg_auction_amount_*` and percentiles require valid formal auction amounts with the same normalized unit and security identity. Suspensions, missing records, listing-age gaps, and invalid conflicts are excluded from denominators and counted explicitly.

## 5. Process Sampling

Persist the required checkpoints at 09:15, 09:17, 09:19, 09:20, 09:21, 09:22, 09:23, 09:24, and 09:25. Preserve denser raw points when available.

Use the requested phase weights only in process-derived composite features:

- 09:15-09:20: 30%
- 09:20-09:24: 45%
- formal 09:25: 25%

These weights do not repair missing data. A missing phase reduces component coverage and quality. Ratios with a zero or null denominator are null, never zero or infinity.

## 6. Auction Volume Anomaly

`auction_volume_anomaly_score` is an objective 0-20 feature, not an investment recommendation.

| Component | Points | Initial thresholds |
|---|---:|---|
| `auction_amount_ratio_20d` | 0-5 | `<1=0`, `1-1.5=1`, `1.5-2=2`, `2-3=3`, `3-5=4`, `>=5=5` |
| `auction_amount_percentile_60d` | 0-4 | `<50=0`, `50-70=1`, `70-85=2`, `85-95=3`, `>=95=4` |
| `auction_to_prev_day_amount` | 0-3 | `<0.2%=0`, `0.2-0.5%=1`, `0.5-1%=2`, `>=1%=3`; recalibrate by board/liquidity bucket |
| `post_0920_amount_growth` | 0-3 | `<=1=0`, `1-1.25=1`, `1.25-1.75=2`, `>=1.75=3` |
| last two/one minute increment | 0-3 | based on self-history percentile: `<70=0`, `70-85=1`, `85-95=2`, `>=95=3` |
| price-volume confirmation | 0-2 | weakening `0`, flat/ambiguous `1`, price rises with volume `2` |

Labels: 0-4 normal, 5-8 slight, 9-12 clear, 13-16 significant, 17-20 extreme. Scores with unavailable 20-day/60-day/process components retain their unscaled subtotal and carry `PARTIAL` plus component coverage; they are not rescaled to 20.

Required tags are generated independently of the score: `EXTREME_AUCTION_VOLUME_ANOMALY`, `STRONG_VOLUME_CONFIRMATION`, `PRICE_STRONG_VOLUME_WEAK`, `PRICE_WEAK_VOLUME_STRONG`, `LATE_VOLUME_SURGE`, `EARLY_VOLUME_FADE`, `POST_0920_VOLUME_EXPANSION`, and `POST_0920_SELL_PRESSURE`.

Initial pattern rules combine robust slopes and phase changes rather than one endpoint: `STRENGTHENING`, `STABLE_STRONG`, `LATE_BIDDING`, `WEAK_TO_STRONG`, `STRONG_TO_WEAK`, `LATE_COLLAPSE`, `EARLY_FAKE_STRENGTH`, and `NORMAL`. Thresholds are versioned and must be calibrated by the backtest before they are interpreted as predictive.

## 7. Theme Auction Aggregation

Join stocks to the previous review's themes and roles, then calculate breadth and liquidity-aware aggregates:

- counts of high/low opens and opens above 3%
- mean and median gap, with the median as the robust headline measure
- total formal auction amount and amount ratio versus each stock's own baseline
- counts of high and extreme volume anomalies
- leader, capacity, catch-up, sentiment-leader, and trend-leader results
- `theme_auction_strength` as a 0-100 objective metric

Suggested objective composition: breadth 25, robust gap 20, baseline-adjusted auction amount 25, leader/capacity agreement 20, and risk/conflict quality 10. Winsorize stock-level ratios within market-board/liquidity buckets and use `log1p(amount)` for weighted measures so one small illiquid stock cannot define the theme.

Theme resonance requires at least two roles or a configured minimum breadth. A strong edge stock with weak capacity/leader and negative median breadth is explicitly classified as non-resonant.

## 8. Previous Official Review Validation

Resolve the previous A-share trading date from the cached official calendar and read only `data/official_reviews/<previous_trade_date>.json`. Join:

- theme: score, rating, lifecycle, implied expectation, strengthen/weaken/invalidate conditions
- stock: theme, role, role detail, expected behavior
- `tomorrow_checks`: explicit conditions to evaluate
- announcement/policy evidence published after the prior review cutoff and before the auction cutoff

Output `EXPECTATION_EXTREME_BEAT`, `EXPECTATION_BEAT`, `EXPECTATION_INLINE`, `EXPECTATION_MISS`, or `EXPECTATION_SEVERE_MISS` by comparing observed auction features with the prior review's encoded expectation. Absolute gap alone is never sufficient.

For a 2026-09-04 auction, the correct prior review is 2026-09-03. That file is absent from the repository. The audit therefore does not produce a fabricated previous-review validation. The existing 2026-09-04 review can seed the next trading day's watch pool, but cannot be relabeled as a 2026-09-03 input.

## 9. Auction Score

The packet exposes objective components and evidence to ChatGPT; Codex does not turn the result into a buy/sell instruction.

| Component | Maximum |
|---|---:|
| Market auction environment | 10 |
| Previous mainline match | 15 |
| Catalyst credibility | 15 |
| Price strength | 15 |
| Auction volume anomaly | 20 |
| Theme resonance | 10 |
| Stock role | 10 |
| Historical abnormality | 5 |
| Risk deduction | 0 to -20 |

Return `gross_score`, `risk_deduction`, `net_score`, `component_scores`, `component_evidence`, `component_coverage`, and `quality_status`. Missing official review or missing baseline leaves affected components null and prevents a misleading full score.

Catalyst evidence uses the existing A/B/C/D hierarchy. Only official company, exchange, government, or formal IR evidence receives A. Rumor, community discussion, and name association cannot create a high catalyst score.

## 10. Market Environment

At 09:25, run a separate full-market final snapshot when a verified batch source exists. Compute high/low-open counts, gaps above 3%, near-limit-down count, previous limit-up and multi-board average gaps, representative index gaps, and key-theme strength.

Until KlineShare v2 is credential-validated, eltdx should collect only the 100-200 stock focused pool. Do not issue full-market per-stock process requests. If no verified full-market final snapshot exists, market-environment coverage is `PARTIAL` rather than extrapolated from the focused pool.

## 11. Storage and Audit

Reuse the existing `FactStore` and audit models.

Parquet/ZSTD:

- `dataset=auction_snapshot/trade_date=YYYY-MM-DD/part-<hash>.parquet`
- `dataset=auction_daily_summary/trade_date=YYYY-MM-DD/part-<hash>.parquet`
- `dataset=auction_backtest_result/trade_date=YYYY-MM-DD/part-<hash>.parquet`

SQLite stores metadata and indexes only: existing `source_batch`, `source_observation`, `source_fallback`, `quality_gate_run`, `quality_gate_check`, and `fact_partition`, plus compact summary/validation metadata if needed. Do not duplicate raw process rows in SQLite.

DuckDB reads the Parquet datasets for baseline windows, percentiles, theme aggregation, and backtest cohorts. Every fact row includes source, source batch, retrieval time, source data time, content hash, schema version, and quality status. Replays are append-only by content hash and never overwrite evidence silently.

## 12. Auction Packet Contracts

Full packet: `data/auction_packets/YYYY-MM-DD.json` with metadata, source audit, focused pool, normalized checkpoints, daily summaries, market environment, theme aggregation, previous-review validation, stock ranking inputs, anomalies, risks, conflicts, quality checks, and 09:30-10:00 validation conditions.

Compact packet: `data/auction_packets/YYYY-MM-DD_compact.json` with exactly the research-facing sections requested in the task, including `top_volume_anomalies`. It retains source/evidence references and quality/conflict status but excludes raw dense observations.

Packet status rules:

- source completely unavailable: `FAIL` for that domain, with fallback audit
- missing checkpoints: `PARTIAL`
- valid no-event/no-candidate result: `EMPTY_VALID`
- missing optional Tushare auction permission: `UNAVAILABLE`, non-blocking
- stale source date: `STALE`
- final auction/open error above threshold: `INVALID` plus conflict; never silently corrected

Initial open-price conflict threshold: `max(0.01 CNY, 1 tick)` and `open_price_error_pct > 0.02%`; calibrate by board tick rules and preserve both source values.

## 13. Backtest Design

Backfill 120 trading days where process data exists, recording coverage by stock/date/source. Persist outcomes at 09:30, 09:35, 10:00, 11:30, 15:00, and next close, plus maximum gain/drawdown, limit-up/down, broken-board, and spike-fade flags.

Evaluate cohorts by anomaly band, pattern, theme resonance, role, market regime, board, liquidity bucket, and data-quality tier. Report sample count, median return, hit rate, confidence interval, and adverse excursion. Use walk-forward calibration; do not optimize and evaluate on the same dates. This is descriptive validation, not an automated trading model.

## 14. Implementation Plan

1. A2 schema and source adapters: add versioned contracts, eltdx adapter, conditional KlineShare adapter, source audit, unit tests, and no-current-to-history guards.
2. A3 focused-pool scheduler: derive 100-200 names from the previous official review and objective limit/amount/risk pools; persist raw points and required checkpoints.
3. A4 anomaly engine: baseline queries, null-safe ratios, 0-20 components, tags, patterns, and quality coverage.
4. A5 theme aggregation: role-aware breadth/liquidity metrics and objective theme strength.
5. A6 previous-review validation: trading-date resolution, explicit expectation checks, announcement/policy cutoff rules, and missing-review behavior.
6. A7 full and compact Auction Packet builders with schema validation and audit chain.
7. A8 120-day backfill and outcome backtest, followed by threshold calibration.

Planned files, subject to existing package conventions at implementation time:

- `src/auction/contracts.py`
- `src/auction/source_router.py`
- `src/auction/collectors/eltdx.py`
- `src/auction/collectors/klineshare.py`
- `src/auction/checkpoints.py`
- `src/auction/baselines.py`
- `src/auction/anomaly.py`
- `src/auction/themes.py`
- `src/auction/previous_review.py`
- `src/auction/packet_builder.py`
- `scripts/run_auction_pipeline.py`
- `schemas/auction_packet.schema.json`
- focused unit/integration tests under `tests/`

## 15. Acceptance Gates Before A2

- Run eltdx on a real trading day from 09:14:50 through 09:30:10 for at least the same 20-stock set.
- Verify server/source timestamps, point freshness, reconnect behavior, and 100-200 stock completion within every checkpoint window.
- Determine unmatched direction mapping using an independent source; until then keep `unmatched_buy/sell` null.
- Obtain a KlineShare key/trial with `auction_v2`, then test 20-stock batch and full-market modes, units, quota, history, and latency.
- Confirm Tencent/Eastmoney 09:30 open fields and EOD Tushare reconciliation on the same trading day.
- Establish the actual oldest complete eltdx process date across a representative stock sample.

## 16. Risks

- eltdx uses undocumented server protocols and server-dependent retention; upstream behavior can change without notice.
- eltdx process points are irregular and may include both opening and closing auction records; collectors must filter 09:15-09:25 explicitly.
- A formal 09:25 trade is distinct from a 09:25 virtual-match process point.
- KlineShare permissions are independent and currently unconfigured; documented features are not runtime acceptance.
- TickDB requires credentials and paid depth/trade access, and lacks a documented dedicated process feed.
- Tushare `stk_auction_o` is unavailable to the current token and is post-close only.
- Amount and volume units differ by source. Raw units must be preserved and normalized explicitly.
- Quote depth is not equivalent to unmatched auction quantity; these fields cannot be substituted.
- Missing prior official review or historical baseline must reduce quality/coverage rather than produce an invented score.
- Full-market per-stock polling can miss checkpoints and overload providers; it is forbidden until a batch endpoint is accepted.

## 17. Primary Sources

Accessed 2026-09-05:

- KlineShare market and auction documentation: https://data.klineshare.cn/docs/market/
- KlineShare authentication and permissions: https://data.klineshare.cn/docs/auth/
- KlineShare account/catalog documentation: https://data.klineshare.cn/docs/account/
- TickDB official API repository/OpenAPI: https://github.com/TickDB/tickdb-api-docs
- TickDB official pricing: https://docs.tickdb.ai/en/pricing
- eltdx repository and method reference: https://github.com/electkismet/eltdx
- eltdx field reference: https://github.com/electkismet/eltdx/blob/main/docs/FIELD_REFERENCE.md
- Tushare opening-auction documentation: https://tushare.pro/document/2?doc_id=353
