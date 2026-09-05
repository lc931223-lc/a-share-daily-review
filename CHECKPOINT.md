# Checkpoint

## 2026-09-05 Inflection Scanner Phase 1

Checkpoint: 2026-09-05, implementation and real-data replay complete

Task: Implement the first trend-inflection scanner using existing fundamental facts, price-volume anomalies, daily/weekly structure, chip proxy variables, auditable scoring, packets, and historical replay without changing Dashboard, PDF, Auction, or trading behavior.

Completed:

- Added full-market historical daily loading through the existing Tushare archive and FactStore, with unit normalization, DuckDB selected-code reads, stock metadata caching, and an explicit requested-date cutoff.
- Added price-volume, daily K, weekly K, breakout/hold/failure, volatility, pullback, and chip-proxy features.
- Added the 30/25/15/15/15 score model. Missing components remain `null`; totals are not rescaled. Risk and broken-trend overrides remain explicit.
- Added basic fundamental scoring from existing target-date announcement facts only. Future announcements are rejected and no new collector was introduced.
- Added full and compact Inflection Packets, Parquet fact storage, SQLite source observations and quality gates, plus a separate future-outcome backtest.
- Cached 280 real A-share trading days and ran 2026-09-04 across 5,507 eligible stocks. The packet contains 561 surfaced candidates.
- Replayed 24 trading days from 2026-08-03 through 2026-09-04 for change history and generated `data/inflection/backtests/2026-08-01_to_2026-09-04.json`.
- Made Parquet partition writes atomic and added a regression test for interrupted writes.

Current state: The 2026-09-04 scan has 99.64% core-feature coverage and 97.84% complete 250-day history coverage. Turnover features are unavailable because `daily_basic` is unavailable. Five-day and twenty-day score-change coverage remains below the quality threshold because only sampled historical scans exist before 2026-09-03. Capacity/breadth confirmation and positive-catalyst fatigue remain deferred and explicit `null` values. The honest packet status is `PARTIAL`.

Validation: The regenerated full and compact packets pass JSON Schema validation and use the `2026-09-04T15:05:00+08:00` cutoff. Targeted tests pass with 16 tests. `compileall` passes, and the complete non-real-data suite passes with `226 passed, 1 deselected`. The historical replay contains 953 signal records; later horizons have materially smaller samples and are descriptive only. The release secret scan found zero token matches, and the implementation was pushed to `origin/main`.

Blockers / risks: Prices are currently raw rather than adjusted because `adj_factor` is unavailable. The historical replay sample is too small and selection-biased for predictive claims. Existing 2026-09-04 announcement facts contain no qualifying positive fundamental catalyst categories, so the fundamental candidate list is empty rather than fabricated.

Next actions: None for Phase 1. Accumulate full-market daily scans before treating 5-day or 20-day score changes as complete.

## 2026-09-05 Call Auction Phase A1

Checkpoint: source feasibility audit and design complete; no production auction implementation started

Task: Audit at most three 09:15-09:25 call-auction process candidates using 2026-09-04 historical data, then define source routing, schemas, anomaly scoring, previous-review validation, storage, backtest, and implementation order.

Completed:

- Audited KlineShare, TickDB, and eltdx using official documentation and live endpoint reachability checks.
- Installed eltdx 3.1.3 in the local virtual environment for the audit only; no dependency was added to the project manifest.
- Tested 20 stocks across large/small cap, previous limit-up/down, main board, ChiNext, STAR, and BSE.
- eltdx passed 60/60 repeated historical process calls and 60/60 formal 09:25 opening-match calls for 2026-09-04.
- Warm eltdx process requests had 17-21ms median and 43-60ms p95 per stock; formal opening-match median was 80-84ms.
- All 20 eltdx formal opening prices matched Tushare `daily.open`; maximum error was 0%.
- Confirmed the current Tushare token lacks `stk_auction_o` permission; status is optional/unavailable and non-blocking.
- Confirmed KlineShare and TickDB are reachable but cannot be data-validated without API keys.
- Documented source scores, field truth rules, checkpoint behavior, anomaly score, theme aggregation, official-review linkage, 100-point score, Parquet/SQLite/DuckDB layout, Auction Packet contracts, backtest, and staged file plan.

Decision:

- Process primary: eltdx.
- Conditional fallback: KlineShare v2 after credentialed trading-day acceptance.
- TickDB: observation only, not a process fallback.
- Immediate open validation: Tencent primary, Eastmoney fallback; Tushare daily performs EOD reconciliation.

Important limits:

- The audit ran on Saturday and used only 2026-09-04 historical data; no current auction data was fabricated.
- eltdx process points are irregular, not a guaranteed one-second grid. Formal 09:25 results must come from the opening-match record.
- Process history worked for 2025-09-04 and 2026-03-10 but not 2024-09-04 in the tested stock; retention must be measured, not assumed.
- A 2026-09-04 auction would require the 2026-09-03 official review, which is absent. The existing 2026-09-04 review was not backdated or used as fake prior input.

Deliverable: `docs/superpowers/specs/2026-09-05-auction-phase-a-design.md`

Next action: Do not start A2 until a real trading-day acceptance run verifies live freshness, reconnects, unmatched-direction semantics, and 100-200 stock checkpoint completion.

## 2026-09-05 Phase 1.3 High-Value Data Gaps

Checkpoint: 2026-09-05, implementation and Git delivery complete

Task: Improve announcement reliability, daily board snapshots, precise official policy coverage, Tushare efficiency, official margin data, and compact Market Packet value without changing the architecture, Dashboard, PDF, research algorithms, or skills.

Completed:

- Added explicit project-root `.env` loading and credential-status-only CLI output; local token remains ignored and untracked.
- Made Tushare `daily` the core full-market source, cached `trade_cal` annually and `stock_basic` daily, and disabled `daily_basic`/`adj_factor` unless requested.
- Expanded the announcement core pool to 120 stocks, implemented paginated CNInfo date batches, source circuit breaking, risk phrase extraction, deduplication, and success/failure TTL behavior.
- Restricted policies to the 11 required official agencies, separated daily events from background references, capped daily output at 20, and retained `EMPTY_VALID` semantics.
- Added full current-day board snapshots with Eastmoney primary plus THS industry and Sina concept fallbacks. Raw snapshots and normalized derived views now use different Parquet dataset names.
- Fixed Parquet reads for Arrow array values and added schema/date guards that reject mislabeled or cross-date board snapshots.
- Replaced the compact packet with the explicit high-value research fields; the 2026-09-04 compact file is about 22% of the full packet.
- Added official SSE/SZSE margin calls. Both returned no records for 2026-09-04, so margin remains explicitly unavailable rather than zero-filled.
- Ran 2026-09-05 health checks only: CNInfo responded with zero matching records; policies scanned 10/11 sources; THS industry returned 90 rows and Sina concept returned 175 rows. No Saturday Market Packet was written.

Current state: Announcements for 2026-09-02 through 2026-09-04 are all `PASS` with 120/120 pool coverage and 42/52/53 records. Tushare daily for 2026-09-04 is `PASS` with 5,548 rows. Policies are `PARTIAL`: zero same-day events, 41 background references, 10/11 sources available. The honest 2026-09-04 packet score is 63 (`PARTIAL`) because no full board snapshot was archived on the trading date and official margin/northbound data remain unavailable.

Validation: `compileall` passes. The complete non-real-data suite passes with `188 passed, 1 deselected`. The staged secret scan found zero token matches, `.env` is ignored, and the implementation was pushed to `origin/main`.

Blockers / risks: 2026-09-04 industry/concept full snapshots cannot be reconstructed after the date without violating the no-current-to-history rule. The new daily mechanism will archive the next trading day's primary or fallback snapshots.

Next actions: None for Phase 1.3. The next trading-day run will validate and archive the new primary/fallback board snapshot path.

## 2026-09-05 Phase 1.2 Truth Layer Design Gate

Checkpoint: 2026-09-05, Phase 1.2 implementation complete

Task: Repair Market Packet truthfulness, auditability, historical replay, storage layout, and source routing in two separately accepted batches.

Completed:

- Audited the current policy, quality, cache, source-audit, and storage behavior.
- Converted the approved Scheme B requirements into `docs/superpowers/specs/2026-09-05-market-packet-truth-layer-phase-1.2-design.md`.
- Fixed the design interpretation that daily policy events default to the requested calendar date up to `as_of_time`; older records are background references only.
- Self-reviewed the specification for placeholders, contradictions, ambiguity, and scope creep.

Current state: Both approved batches are implemented. The truth and quality rules from the first batch remain active. The second batch adds Parquet fact partitions, a DuckDB query layer, SQLite partition catalog, compressed daily JSONL source batches, explicit source routing, CNInfo date-batch announcement collection with official exchange fallback, and single-snapshot board collection without historical N+1 reconstruction.

Validation:

- `.venv\Scripts\python.exe -m pytest -m "not real_data" -q`: `164 passed, 1 deselected`.
- 2026-09-01 replay: `66 FAIL`, missing `limit_pools,northbound`.
- 2026-09-02 replay: `77 PARTIAL`, missing `northbound`.
- 2026-09-03 replay: `77 PARTIAL`, missing `northbound`.
- 2026-09-04 replay: `74 PARTIAL`, missing `margin,northbound`.
- SQLite now records source batches/observations, quality runs/checks, fallbacks, and append-only fact versions.
- Final non-real-data suite after both batches: `171 passed, 1 deselected`.
- Local production database after replay: 319 source batches, 319 observations, 11 quality runs, 11 fallback records, 131 fact versions, and 29 Parquet partition catalog rows.
- Generated fact store: 29 Zstandard Parquet files, 559,849 bytes; generated data remains gitignored.

Pending:

1. Commit the second implementation batch.
2. Retry normal pushes to `origin/main` until GitHub connectivity succeeds.
3. Confirm local `HEAD` equals `origin/main`.

Blockers / risks: The first implementation push failed because GitHub reset the HTTPS connection. No force push or history rewrite is permitted; final acceptance still requires a successful normal push and `local HEAD == origin/main`.

Next actions: Commit and push the completed second batch. Do not modify PDF, auction logic, research features, or skills.

## 2026-09-05 GitHub Safe Sync Mechanism

### Task

为 A 股研究系统建立稳定的 GitHub 自动同步机制。GitHub `main` 是唯一正式验收版本；每日兜底任务只允许 push 已经 commit 的 `main` 提交，不允许自动 add、commit、pull、rebase、force push 或修改 Market Packet / Dashboard / PDF 业务逻辑。

### Completed

- Added independent sync checker:
  - `tools/git_sync_check.py`
- Added Windows wrapper:
  - `scripts/run_git_sync_check.ps1`
- Added unit tests:
  - `tests/unit/test_git_sync_check.py`
- Updated `README.md` with stage-completion push rules, return codes, log location, and Windows Task Scheduler setup.
- Updated `.gitignore` to explicitly ignore `logs/` in addition to generated `.log` files.
- Sync status model:
  - `SYNCED`
  - `LOCAL_AHEAD`
  - `REMOTE_AHEAD`
  - `DIVERGED`
  - `DIRTY_WORKTREE`
  - `NON_MAIN_BRANCH`
- Safety behavior:
  - dirty worktree is never committed or pushed
  - non-main branches are never pushed to `origin/main` by the scheduled fallback
  - remote-ahead and diverged states require manual/Codex handling
  - push uses normal `git push origin main`; no force push path exists
  - sensitive/generated path detection is available for commit-safety checks

### Validation

- Ran: `.venv\Scripts\python.exe -m pytest tests\unit\test_git_sync_check.py -q`
- Result: `8 passed`
- Ran PowerShell wrapper before commit while worktree was dirty.
- Result: script returned `DIRTY_WORKTREE` and did not attempt push, as expected.

### Next Actions

1. Run `compileall`.
2. Run all non-real-data tests.
3. Commit and push this sync-mechanism stage to `origin/main`.
4. Run `tools/git_sync_check.py` once after push and confirm `SYNCED` / no-op.

## 2026-09-04 Three-Layer Architecture Completion

### Task

完成 A 股研究系统三层架构重构，并以 GitHub `main` 作为唯一可验收版本。系统角色固定为：ChatGPT 负责最终研究员/分析师判断；Codex 负责数据工程、执行、存储和展示。

### Completed

- Rechecked Git state before development:
  - remote: `https://github.com/lc931223-lc/a-share-daily-review.git`
  - starting branch: `codex/phase1-dashboard`
  - starting worktree: clean
  - remote `origin/main` after fetch: `55df058`
  - local feature HEAD before this task: `c657b08`
- Removed tracked raw Market Packet caches from Git and added `data/raw/market_packets/` to `.gitignore`.
- Added official review contract and import command:
  - `schemas/official_review.schema.json`
  - `tools/import_official_review.py`
  - `data/official_reviews/2026-09-04.json`
- Added execution commands:
  - `tools/build_market_packet.py`
  - `tools/update_validation_results.py`
  - `tools/run_daily_pipeline.py`
- Added explicit three-layer storage tables:
  - `market_daily`
  - `theme_daily_review`
  - `stock_daily_review`
  - `validation_result`
  - `score_history`
  - `market_packet_log`
- Market Packet output now includes both `leader_candidates` and backward-compatible `leader_board`.
- Market Packet writes `market_daily` and `market_packet_log` into SQLite when outputs are generated.
- Official review import writes:
  - immutable archive via `review_import`
  - `theme_daily_review`
  - `stock_daily_review`
  - `score_history`
  - `validation_result` for resolved checks
- Added Dashboard pages:
  - `pages/7_验证中心.py`
  - `pages/8_回测统计.py`
- Expanded `pages/4_生命周期统计.py` with rating samples, delta-score distribution, stock-role samples, and tomorrow-check statistics.

### Current State

- Default database: `data/a_share_review.db`
- Actual local DB initialization/import completed:
  - imported `data/official_reviews/2026-09-04.json`
  - `trading_day`: 13 rows
  - `review_import`: 17 rows
  - `market_daily`: 1 row
  - `market_packet_log`: 2 rows
  - `theme_daily_review`: 1 row
  - `stock_daily_review`: 1 row
  - `score_history`: 2 rows
  - `validation_result`: 1 row
- Dashboard process started on `http://localhost:8501`.

### Validation

- Ran: `.venv\Scripts\python.exe -m compileall -q src tools scripts pages tests`
- Result: passed
- Ran: `.venv\Scripts\python.exe -m pytest tests\unit\test_market_packet_phase1.py tests\integration\test_database_schema.py tests\integration\test_import_daily_review.py tests\integration\test_tomorrow_checks.py tests\ui\test_dashboard_pages.py -q`
- Result: `27 passed`
- Ran: `.venv\Scripts\python.exe -m pytest -m "not real_data" -q`
- Result: `109 passed, 1 deselected`
- Ran Dashboard visual QA against `http://localhost:8501`.
- Result: desktop and mobile passed, no exception text, no horizontal overflow.
- Token search: no user Tushare token persisted in tracked/untracked project files searched by `rg`.

### 9.1 / 9.2 / 9.3 / 9.4 Market Packet Results

- 2026-09-01: `69 INCOMPLETE`, missing `announcements`, `limit_down`, `policies`
- 2026-09-02: `76 PARTIAL`, missing `announcements`, `policies`
- 2026-09-03: `79 PARTIAL`, missing `announcements`, `policies`
- 2026-09-04: `79 PARTIAL`, missing `announcements`, `policies`

### Blockers / Risks

- Announcement and policy collectors remain Phase 2 data-source work.
- `moneyflow`, `stk_limit`, and `limit_list_d` still lack Tushare permission in the latest probe.
- Some Tushare non-daily endpoints can hit low per-minute frequency limits; `daily` is the stable core supplement currently used.

### Next Actions

1. Merge this branch with latest `origin/main`.
2. Run final tests after merge.
3. Push final accepted state to GitHub `main`.

## 2026-09-04 Market Packet Phase 1 Architecture

### Tushare Daily Permission Recheck

- Retested the user-provided Tushare token after the user enabled daily access.
- Newly available Pro endpoints in this environment:
  - `trade_cal`: returned trading-calendar rows during direct probe, but later hit a `1 request/minute` endpoint frequency limit.
  - `stock_basic`: returned 5556 listed A-share rows during direct probe.
  - `daily`: returned full-market target-date rows and the official doc example worked.
  - `daily_basic`: returned full-market rows during direct probe, but later hit a `1 request/minute` endpoint frequency limit.
  - `adj_factor`: returned full-market rows during direct probe, but later hit a `1 request/minute` endpoint frequency limit.
  - `index_daily`: returned rows for single-index calls, but all-index date calls hit a `1 request/minute` endpoint frequency limit.
- Still unavailable due permission errors:
  - `moneyflow`
  - `stk_limit`
  - `limit_list_d`
- Integrated `tushare.daily` into Market Packet as a high-value core supplement:
  - full-market breadth from `pct_chg`
  - total market turnover from daily `amount` sum
  - previous trading-day turnover by probing previous `daily` dates
  - stock-universe target-day OHLCV from the full-market daily table
- `stock_top100_full_ohlcv`, `market_breadth`, `total_market_turnover`, and `previous_turnover` are no longer missing for 2026-09-02 / 2026-09-03 when `TUSHARE_TOKEN` is set.

### Task

按用户最新架构要求，把 Codex 从最终 A 股复盘分析师改为“数据工程师 + 数据校验员 + 研究资料整理员”，新增每日 Market Research Packet 系统。Codex 只生成事实数据包，不再自行判断第一主线、最终题材评级或买卖建议。

### Completed

- Added Market Packet package:
  - `src/market_packet/collector.py`
  - `src/market_packet/normalizer.py`
  - `src/market_packet/quality_gate.py`
  - `src/market_packet/previous_review_loader.py`
  - `src/market_packet/packet_builder.py`
  - `src/market_packet/models.py`
- Added strict schema:
  - `schemas/market_packet.schema.json`
- Added CLI:
  - `scripts/build_market_packet.py`
- CLI outputs:
  - `data/market_packets/YYYY-MM-DD.json`
  - `data/market_packets/YYYY-MM-DD_quality.json`
  - `data/market_packets/YYYY-MM-DD_compact.json`
  - `reports/market_packets/YYYY-MM-DD-summary.md`
- Raw source cache uses:
  - `data/raw/market_packets/YYYY-MM-DD/*.json`
- Added tests:
  - `tests/unit/test_market_packet_phase1.py`
- Updated `README.md` and `CODEx_MEMORY.md` with the new role boundary and packet-first workflow.

### Data Sources

- AKShare/Eastmoney public endpoints are the default Phase 1 source:
  - limit-up pool
  - failed-limit pool
  - limit-down pool
  - previous limit-up feedback
  - daily dragon-tiger detail
  - northbound fund-flow history
  - SZSE margin summary/detail
  - current industry/concept fund-flow when freshness matches the use case
- Added target-day stock OHLCV fallback for the packet stock universe:
  - primary attempt: `akshare.stock_zh_a_hist`
  - fallback: `akshare.stock_zh_a_hist_tx`
  - fallback: `akshare.stock_zh_a_daily`
- Tushare remains optional but is now useful when `TUSHARE_TOKEN` is configured because the current token has `daily` access. Use Tushare `daily` for market breadth, total turnover, previous turnover, and stock-universe OHLCV. Do not assume `moneyflow`, `stk_limit`, or `limit_list_d` are available.
- Missing fields remain `null`; no old cache, zero fill, or LLM-generated market numbers are used.

### Validation

- Ran: `.venv\Scripts\python.exe -m compileall -q src\market_packet scripts\build_market_packet.py tests\unit\test_market_packet_phase1.py`
- Result: passed
- Ran: `.venv\Scripts\python.exe -m pytest tests\unit\test_market_packet_phase1.py -q`
- Result: `5 passed`
- Ran: `.venv\Scripts\python.exe -m pytest -m "not real_data" -q`
- Result: `107 passed, 1 deselected`
- Ran actual packet builds:
  - `.venv\Scripts\python.exe scripts\build_market_packet.py --date 2026-09-01 --refresh`
  - `.venv\Scripts\python.exe scripts\build_market_packet.py --date 2026-09-02 --refresh`
  - `.venv\Scripts\python.exe scripts\build_market_packet.py --date 2026-09-03 --refresh`

### 9.1 / 9.2 / 9.3 Results

- 2026-09-01:
  - quality: `69 INCOMPLETE`
  - limit up / failed / limit down: `83 / 6 / null`
  - stocks: `182`
  - themes: `48`
  - Tushare daily rows: `5546`
  - previous daily rows: `5545`
  - stock-universe OHLCV rows: `120`
  - breadth: `3387 / 2040 / 119`
  - total turnover: `2051946105381.41`
  - previous turnover: `2145356257431.91`
- 2026-09-02:
  - quality: `76 PARTIAL`
  - limit up / failed / limit down: `52 / 15 / 8`
  - stocks: `160`
  - themes: `43`
  - Tushare daily rows: `5547`
  - previous daily rows: `5546`
  - stock-universe OHLCV rows: `120`
  - breadth: `1541 / 3901 / 105`
  - total turnover: `1820297595531.59`
  - previous turnover: `2051946105381.41`
- 2026-09-03:
  - quality: `79 PARTIAL`
  - limit up / failed / limit down: `44 / 33 / 16`
  - stocks: `141`
  - themes: `54`
  - Tushare daily rows: `5549`
  - previous daily rows: `5547`
  - stock-universe OHLCV rows: `120`
  - breadth: `1846 / 3570 / 133`
  - total turnover: `1780237627524.24`
  - previous turnover: `1820297595531.59`

### Current Missing Data

- `announcements`
- `policies`
- 2026-09-01 additionally lacks `limit_down` from the tested AKShare endpoint.

### Next Actions

1. Wire CNINFO announcement collection for the packet stock universe.
2. Add official policy crawler with source-level evidence metadata.
3. Add stable historical all-A breadth, total turnover, and previous-turnover sources.
4. Add SSE margin fallback for environments where the SSE endpoint fails.
5. Only after Phase 1 acceptance, start Phase 2.

## 2026-09-03 Complete 2026-09-02 Dashboard And PDF Review

### Tushare Probe

- User provided a Tushare token for validation.
- The token was used only as a local process environment variable and was not written to project files.
- Probe result for 2026-09-02: core endpoints returned permission errors:
  - `trade_cal`
  - `daily`
  - `daily_basic`
  - `moneyflow`
  - `stk_limit`
  - `limit_list_d`
  - `top_list`
  - `margin`
  - `margin_detail`
  - `moneyflow_hsgt`
  - `hsgt_top10`
  - `index_daily`
- Probe summary is archived at:
  - `data/market_reviews/2026-09-02/tushare_probe/probe_summary.json`
- Current source policy remains: default to Eastmoney/AKShare public data first; use Tushare only when the token has the required endpoint permissions.

### AKShare Probe

- Verified local AKShare package version: `1.18.94`.
- Probe date: `2026-09-02`.
- Successfully available public endpoints:
  - `stock_zt_pool_em`: 52 rows, Eastmoney limit-up pool.
  - `stock_zt_pool_zbgc_em`: 15 rows, Eastmoney failed-limit pool.
  - `stock_zt_pool_dtgc_em`: 8 rows, Eastmoney limit-down pool.
  - `stock_zt_pool_previous_em`: 83 rows, previous limit-up feedback.
  - `stock_lhb_detail_em`: 83 rows, Eastmoney daily dragon-tiger detail.
  - `stock_lhb_stock_statistic_em`: 702 rows, Eastmoney recent dragon-tiger statistics.
  - `stock_hsgt_hist_em`: 2745 rows, northbound fund-flow history.
  - `stock_hsgt_fund_flow_summary_em`: 4 rows, northbound/southbound flow summary.
  - `stock_margin_szse`: 1 row, SZSE margin summary.
  - `stock_margin_detail_szse`: 2103 rows, SZSE margin detail.
  - `stock_fund_flow_industry`: 90 rows, industry capital flow.
  - `stock_fund_flow_concept`: 387 rows, concept capital flow.
- Endpoints that need fallback or retry in this environment:
  - `stock_hsgt_stock_statistics_em`
  - `stock_margin_sse`
  - `stock_margin_detail_sse`
  - `stock_zh_index_daily_em`
  - `stock_board_industry_name_em`
  - `stock_board_concept_name_em`
  - `stock_market_fund_flow`
- Probe summary and sample files are archived at:
  - `data/market_reviews/2026-09-02/akshare_probe/`
- Practical policy: AKShare can provide more useful daily-review data than the currently tested Tushare token. Use AKShare/Eastmoney for limit pools, dragon-tiger, northbound flow, SZSE margin, and industry/concept money flow; use alternate public sources for SSE margin and Eastmoney push2 outages.

### Final补齐

- Replaced the remaining limit-pool gaps with reproducible Eastmoney/AKShare pool data:
  - limit up: 52
  - failed limit: 15
  - failed limit rate: 22.39%
  - limit down: 8
  - highest board: 4
  - multi-board count: 13
  - previous-limit average return: -0.76%
  - previous-limit positive rate: 37.35%
- Raised the 2026-09-02 formal snapshot completeness from 76% to 92%.
- Added explicit source-disagreement disclosure: news-review limit-up/down counts differ from Eastmoney pool counts; Dashboard/PDF use the reproducible Eastmoney pool.
- Added visible scoring tables to the Dashboard homepage:
  - `主线评分拆解`
  - `核心个股评分`
- Updated secondary pages:
  - `主线详情` uses non-virtualized tables for score/history visibility.
  - `核心个股` now defaults to imported real stocks instead of an old sample code.
  - `数据质量` is trade-date selectable and shows resolved gaps, source disagreements, and remaining non-scoring appendices.
- Expanded the PDF to 6 pages with scoring tables and updated data-quality disclosure.
- Archived raw Eastmoney engine outputs under:
  - `data/market_reviews/2026-09-02/engine/2026-09-02_to_2026-09-02/`
- PDF delivery convention from now on:
  - Only deliver one formal daily-review PDF per trade date.
  - The formal PDF path is `reports/market_reviews/YYYY-MM-DD-a-share-dashboard-review.pdf`.
  - Sentiment-engine output is an input/appendix source and should be embedded into the formal PDF, not delivered as a separate `sentiment-review` PDF.

### Task

把 2026-09-02 复盘补成按既定体系运行的完整版交付：真实数据 Dashboard 和同源 PDF，而不是简化 Markdown/PDF。

### Completed

- Extended the strict `DailyReview 2.0` contract with review-dashboard sections:
  - index metrics
  - sentiment dashboard
  - sector strength and weakness
  - limit ladder
  - dragon-tiger summary
  - tomorrow scenario plan
  - data quality detail
- Regenerated JSON Schema from the updated Pydantic model.
- Expanded `data/json/reviews/2026-09-02-dashboard-review.json` with the full 9.2 review structure.
- Re-imported 2026-09-02 into the local Dashboard database:
  - latest date: `2026-09-02`
  - themes: 5
  - stocks: 5
  - evidence: 3
  - tomorrow checks: 3
- Expanded `app.py` homepage to render:
  - market metrics
  - index and liquidity table
  - sentiment temperature
  - TOP5 themes
  - strong and weak sectors
  - limit ladder and loss feedback
  - dragon-tiger summary
  - tomorrow scenario plan
- Expanded `pages/6_数据质量.py` to display imported snapshot quality, known gaps, and cross-check sources when no source-batch rows exist.
- Reworked `src/reports/pdf_report.py` into a structured review report using the same snapshot JSON as Dashboard, including the Eastmoney sentiment-engine validation appendix.

### Validation

- Ran: `.venv\Scripts\python.exe -m py_compile app.py pages\6_数据质量.py src\reports\pdf_report.py src\validation\review_models.py tools\build_20260902_dashboard_review.py tools\visual_qa_dashboard.py`
- Result: passed
- Ran: `.venv\Scripts\python.exe -m pytest -m "not real_data" -q`
- Result: `102 passed, 1 deselected`
- Ran: `.venv\Scripts\python.exe tools\visual_qa_pdf.py reports\market_reviews\2026-09-02-a-share-dashboard-review.pdf`
- Result: passed, 6 pages, Source Han Sans CN embedded
- Ran: `$env:DASHBOARD_URL='http://localhost:8502'; .venv\Scripts\python.exe tools\visual_qa_dashboard.py`
- Result: passed desktop and mobile, no horizontal overflow, no exception text
- Browser text check confirmed homepage contains `主线评分拆解`, `核心个股评分`, `52 / 8`, `22.39%`, `竞业达`, `国芳集团`, and `东方财富涨停池`.
- Data-quality page check through sidebar navigation confirmed `东方财富涨停池`, `已补齐缺口`, `口径差异`, `仍未纳入项`, and `涨停52家` appear.
- Rendered PDF pages and visually inspected page 1 and page 3 for Chinese glyphs, spacing, and table layout.

### Current State

- Dashboard service is running at `http://localhost:8502`.
- Final Dashboard PDF:
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\reports\market_reviews\2026-09-02-a-share-dashboard-review.pdf`
- Final Dashboard source JSON:
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\data\json\reviews\2026-09-02-dashboard-review.json`
- The local SQLite database is intentionally ignored by Git but has been updated on this machine:
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\data\a_share_review.db`

## 2026-09-02 Dashboard Review Import

### Task

补齐 2026-09-02 复盘在 Dashboard 框架中的交付，而不是只生成独立 Markdown/PDF。

### Completed

- Added 2026-09-02 Dashboard review builder:
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\tools\build_20260902_dashboard_review.py`
- Generated validated `DailyReview 2.0` source data:
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\data\json\reviews\2026-09-02-dashboard-review.json`
- Imported the review into the local Dashboard database:
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\data\a_share_review.db`
  - latest Dashboard date is now `2026-09-02`
  - imported 5 themes, 5 stocks, 3 evidence items, and 3 tomorrow checks
- Fixed Dashboard home rendering:
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\app.py`
  - removed hard-coded `PASSED` from the visible status chip
  - changed TOP5 theme table from virtualized `st.dataframe` to stable `st.table` so screenshots and browser rendering show rows reliably
- Generated Dashboard-framework PDF:
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\reports\market_reviews\2026-09-02-a-share-dashboard-review.pdf`

### Validation

- Ran: `.venv\Scripts\python.exe tools\build_20260902_dashboard_review.py`
- Result: generated JSON and passed `DailyReview` validation
- Ran import through `src.services.import_service.import_review`
- Result: `themes=5`, `stocks=5`, `evidence=3`, `checks=3`
- Ran Streamlit at `http://localhost:8502`
- Visual check: Dashboard homepage shows `2026-09-02`, completeness `76%`, turnover `1.79万亿`, breadth `1,537 / 3,898`, limit-up/down `71 / 19`, and TOP5 themes including `军工装备`.
- Ran: `$env:DASHBOARD_URL='http://localhost:8502'; .venv\Scripts\python.exe tools\visual_qa_dashboard.py`
- Result: passed on desktop and mobile, no horizontal overflow, no exception text
- Ran: `.venv\Scripts\python.exe tools\visual_qa_pdf.py reports\market_reviews\2026-09-02-a-share-dashboard-review.pdf`
- Result: passed, 2 pages, Source Han Sans CN embedded
- Ran: `.venv\Scripts\python.exe -m pytest -m "not real_data" -q`
- Result: `102 passed, 1 deselected`

### Current State

- Dashboard is currently running at `http://localhost:8502` in this task session.
- The local database file is intentionally ignored by Git but has been updated on this machine.
- The committed JSON file can regenerate/import the same 2026-09-02 Dashboard state.

## 2026-09-02 Default Source Policy Changed To Eastmoney

### Task

按用户新要求调整 A 股复盘数据源策略：以后默认优先使用东方财富公开数据；Tushare 仅在 token 可用时作为增强或交叉核验。

### Completed

- Updated default source configuration:
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\config\data_pipeline.json`
  - `primary_market_source` now defaults to `eastmoney`
  - `tushare_role` now defaults to `optional_cross_check`
- Relaxed runtime loading:
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\src\config\runtime.py`
  - missing `TUSHARE_TOKEN` is allowed for Eastmoney-primary workflows
  - `TUSHARE_TOKEN` is still required if config explicitly sets Tushare as primary
- Added Eastmoney primary collection methods while preserving `fetch()` fallback whitelist semantics:
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\src\adapters\eastmoney_fallback.py`
- Updated pipeline routing:
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\src\services\market_pipeline.py`
  - core market collection now follows `primary_market_source`
  - Tushare is instantiated only when a token exists
- Updated tests and README for the new policy.

### Validation

- Ran: `.venv\Scripts\python.exe -m pytest tests/unit/test_runtime_config.py tests/integration/test_market_pipeline.py tests/unit/test_supplemental_adapters.py -q`
- Result: `16 passed`
- Ran: `.venv\Scripts\python.exe -m pytest -m "not real_data" -q`
- Result: `102 passed, 1 deselected`
- Ran: `.venv\Scripts\python.exe -m pytest tests/e2e/test_historical_real_day.py -m real_data -q`
- Result: skipped when the live public source path did not reach formal gate coverage in this network environment.

### Blockers / Risks

- 东方财富公开接口仍可能受网络、风控或字段变化影响；批量请求必须限流。
- Tushare 网站内容公开不等于匿名 API 可用；Pro API 仍需要 token，部分接口还可能受积分和权限影响。
- 当前 Eastmoney-primary 正式门禁仍需继续加强字段覆盖率和日期一致性校验，避免把公开接口异常误判为正式 `PASSED`。

## 2026-09-02 Remaining Issues Closed And 9.2 Public Review

### Task

解决真实数据链路剩余验证问题，并生成 2026-09-02 A股复盘报告。

### Completed

- Installed Python Playwright into the existing ignored virtual environment and added a no-npm Dashboard QA path:
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\tools\visual_qa_dashboard.py`
- Updated JS Dashboard QA to support non-default ports through `DASHBOARD_URL`:
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\tools\visual_qa_dashboard.js`
- Updated PDF QA to render pages into `tmp/pdf-qa` instead of the report directory:
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\tools\visual_qa_pdf.py`
- Added a 2026-09-02 public-data review generator:
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\tools\generate_20260902_public_review.py`
- Generated 2026-09-02 DRAFT_ONLY review artifacts:
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\data\market_reviews\2026-09-02\public_review_payload.json`
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\reports\market_reviews\2026-09-02-a-share-public-data-review.md`
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\reports\market_reviews\2026-09-02-a-share-public-data-review.pdf`
- Updated README with Python visual QA commands and the 2026-09-02 public review artifact paths.

### Current State

- Streamlit Dashboard visual QA now passes in this environment by importing `tests/fixtures/reviews/market_alpha_complete.json` into `tmp/dashboard-qa/dashboard-qa.db` and running against `DASHBOARD_URL=http://localhost:8502`.
- The 2026-09-02 report is intentionally `DRAFT_ONLY`, not a formal `PASSED` market snapshot, because the environment lacks `TUSHARE_TOKEN`.
- Public data used for the 9.2 report was cross-checked from Sina Finance, The Paper/Wind, Investing.com/智通财经, and Eastmoney data center pages. The report discloses the成交额口径差异：17912亿元 versus 18202亿元.

### Validation

- Ran: `.venv\Scripts\python.exe -m pytest -m "not real_data" -q`
- Result: `100 passed, 1 deselected`
- Ran: `.venv\Scripts\python.exe -m pytest tests/e2e/test_historical_real_day.py -m real_data -q`
- Result: `1 skipped` because `TUSHARE_TOKEN` is not configured
- Ran: `.venv\Scripts\python.exe tools\generate_20260902_public_review.py`
- Result: generated Markdown, PDF, and JSON payload
- Ran: `.venv\Scripts\python.exe tools\visual_qa_pdf.py reports\market_reviews\2026-09-02-a-share-public-data-review.pdf`
- Result: passed, 1 page, Source Han Sans CN Regular/Medium/Bold embedded
- Ran: `.venv\Scripts\python.exe -m py_compile tools\generate_20260902_public_review.py tools\visual_qa_dashboard.py tools\visual_qa_pdf.py`
- Result: passed
- Ran: `$env:DASHBOARD_URL='http://localhost:8502'; .venv\Scripts\python.exe tools\visual_qa_dashboard.py`
- Result: passed on desktop `1440x900` and mobile `390x844`, with `overflow=0` and no Traceback/Exception text.

### Blockers / Risks

- Formal live real-data end-to-end验收 remains blocked until `TUSHARE_TOKEN` is configured locally.
- The 2026-09-02 public-data report should not be treated as a production PASSED PDF; it is a user-facing interim review with disclosed source limitations.

### Next Actions

1. Configure `TUSHARE_TOKEN` in `.env` or the local environment.
2. Run `.venv\Scripts\python.exe -m pytest tests/e2e/test_historical_real_day.py -m real_data -q`.
3. If the real-data gate returns `PASSED`, generate the formal 2026-09-02 PDF through `generate_daily_pdf.py`.

## 2026-09-02 Task 13 Offline Verification And Real-Data E2E Gate

### Completed

- Added credential-protected real-data e2e test:
  - `tests/e2e/test_historical_real_day.py`
  - marked with `real_data`
  - skips explicitly when `TUSHARE_TOKEN` is missing
- Registered the `real_data` pytest marker in `pyproject.toml`.
- Updated Dashboard visual QA script:
  - `tools/visual_qa_dashboard.js`
  - checks formal real-data status instead of old demo-derived values
  - checks desktop `1440x900` and mobile `390x844`
- Added PDF QA script:
  - `tools/visual_qa_pdf.py`
  - checks page count, Source Han Sans embedding, data quality text, and Poppler rendering
- Rewrote `README.md` for the real-data pipeline:
  - removed demo seed instructions
  - documented credentials, collection, gate exit codes, Dashboard, PDF, and QA commands
- Declared `playwright` in `package.json` dev dependencies for Dashboard visual QA environments.

### Validation

- Ran: `.venv\Scripts\python.exe -m pytest -m "not real_data" -q`
- Result: `100 passed, 1 deselected`
- Ran: `.venv\Scripts\python.exe -m pytest tests/e2e/test_historical_real_day.py -m real_data -q`
- Result: `1 skipped` because `TUSHARE_TOKEN` is not configured
- Ran: `.venv\Scripts\python.exe tools\visual_qa_pdf.py tmp\pdfs\task12-sample.pdf`
- Result: passed, 1 page, Source Han Sans CN Regular/Medium/Bold embedded
- Attempted: `node tools\visual_qa_dashboard.js`
- Result: blocked because `node` is not on PATH
- Attempted with bundled Node:
  - `C:\Users\愚者\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe tools\visual_qa_dashboard.js`
- Result: blocked because local JS `playwright` module is not installed and no bundled npm was available
- Attempted to install Python Playwright into `.venv`; download did not complete in a reasonable time and was interrupted. `.venv` is ignored and not committed.

### Current State

- Tasks 1 through 13 are implemented and committed locally except this final verification commit.
- Offline implementation and tests pass.
- Formal live real-data end-to-end验收 is not complete because `TUSHARE_TOKEN` is missing in this environment.
- Dashboard Playwright visual QA is not complete because the local JS Playwright dependency could not be installed/run in this environment.
- PDF generation and PDF rendering QA passed on a generated fixture PDF.

## 2026-09-02 Task 12 Formal Source Han Sans PDF Generation

### Completed

- Added formal PDF generator:
  - `src/reports/__init__.py`
  - `src/reports/pdf_report.py`
  - `generate_daily_pdf.py`
- PDF generator behavior:
  - accepts only `PASSED` snapshots
  - blocks `DRAFT_ONLY` and `FAILED` snapshots
  - embeds Source Han Sans CN Regular, Medium, and Bold fonts
  - uses black text
  - includes market conclusion, metrics, theme cycle, stock roles, tomorrow checks, and data quality
- PDF CLI reads only `PASSED` `analysis_snapshot` rows for the requested date.

### Validation

- Ran: `.venv\Scripts\python.exe -m pytest tests/integration/test_pdf_report.py -q`
- Result: `2 passed`
- Generated sample: `tmp/pdfs/task12-sample.pdf`
- Rendered page 1 with Poppler: `tmp/pdfs/task12-sample-page1.png`
- Visual check: Chinese glyphs rendered, black body text, no table overflow, no obvious clipping.

### Current State

- Task 12 implementation is complete.
- Next implementation step: Task 13, full offline test sweep, credential-protected real e2e test, dashboard/PDF visual QA scripts, README cleanup, and final checkpoint.

## 2026-09-02 Task 11 Dashboard Real-Data Quality UI

### Completed

- Removed the Dashboard data-kind selector from UI layout and pages.
- Updated all Streamlit pages to call real/PASSED query APIs without `data_kind`.
- Home page now displays `正式真实数据 · PASSED` instead of real/demo toggle labels.
- Added data quality page:
  - `pages/6_数据质量.py`
  - shows analysis snapshot status, rule version, confidence, source batches, quality gate checks, and fallback records
  - discloses Eastmoney fallback records when present
- Updated UI tests to seed from neutral real fixture instead of deleted demo seed script.

### Validation

- Ran: `.venv\Scripts\python.exe -m pytest tests/ui/test_dashboard_home.py tests/ui/test_dashboard_pages.py -q`
- Result: `9 passed`

### Current State

- Task 11 implementation is complete.
- Dashboard runs against formal real-data snapshots only.
- Next implementation step: Task 12, formal Source Han Sans PDF generation from passed snapshots.

## 2026-09-02 Task 10 Remove Production Demo Paths And Tighten Queries

### Completed

- Removed production demo files:
  - `data/json/demo/*.json`
  - `scripts/seed_demo_data.py`
  - `tests/integration/test_seed_data.py`
- Added neutral real-data fixture:
  - `tests/fixtures/reviews/market_alpha_complete.json`
- Replaced query integration tests so they no longer import the demo seed script or example names.
- Removed fixed theme aliases from `src/services/theme_normalizer.py`.
- `import_review()` now creates a `PASSED` `analysis_snapshot` for validated real review imports.
- Production query APIs now omit `data_kind` parameters and return only `TradingDay.data_kind == "real"` joined to `analysis_snapshot.status == "PASSED"`.
- Existing validation test fixtures now use neutral `主题甲` instead of AI算力.

### Validation

- Ran: `.venv\Scripts\python.exe -m pytest tests/integration/test_import_daily_review.py tests/integration/test_queries.py -q`
- Result: `9 passed`
- Ran: `.venv\Scripts\python.exe -m pytest tests/unit/test_review_validation.py -q`
- Result: `12 passed`

### Current State

- Task 10 implementation is complete for import and query paths.
- UI pages still call older query signatures and still contain demo-toggle UI; this is the expected next scope for Task 11.
- README still mentions the former demo seed path; this is scheduled for Task 13 documentation cleanup.

## 2026-09-02 Task 9 Dynamic Sentiment, Theme, Stock Role, And Review Builder

### Completed

- Added dynamic analysis modules:
  - `src/core/sentiment.py`
  - `src/core/theme_cycle.py`
  - `src/core/stock_role.py`
  - `src/core/circuit_breaker.py`
  - `src/services/review_builder.py`
- Sentiment analysis returns stage, temperature, suggested position range, reasons, and conflicts.
- Theme ranking derives names only from `snapshot.theme_memberships`; equal-strength themes preserve source order.
- Stock role classification requires observed theme membership and returns role reasons.
- Circuit breaker blocks formal opening when the gate fails and reduces/pause exposure on discipline triggers.
- Review builder:
  - accepts only `GateStatus.PASSED`
  - emits `DailyReview 2.0`
  - validates every theme and stock against observed snapshot data
  - does not inject fixed examples such as AI算力 or 中际旭创

### Validation

- Ran: `.venv\Scripts\python.exe -m pytest tests/unit/test_sentiment_analysis.py tests/unit/test_theme_cycle.py tests/unit/test_stock_role.py tests/unit/test_circuit_breaker.py tests/integration/test_review_builder.py -q`
- Result: `8 passed`

### Current State

- Task 9 implementation is complete.
- Next implementation step: Task 10, remove production demo data paths and restrict production queries to passed real snapshots.

## 2026-09-02 Task 8 Audited Collection Orchestration And CLI

### Completed

- Added `src/services/market_pipeline.py`.
- Added `collect_daily_review.py`.
- Pipeline behavior:
  - Collects Tushare trade calendar, stock basic, daily quotes, index daily, and adjustment factors first.
  - Does not call Eastmoney when a Tushare core dataset fails.
  - Uses Eastmoney fallback only after supplemental THS limit-pool failure.
  - Writes source batch audit rows and quality gate rows.
  - Creates an analysis snapshot only when the quality gate returns `PASSED`.
- CLI behavior:
  - `--date YYYY-MM-DD`
  - `--mode close|intraday`
  - exit `0` for `PASSED`
  - exit `2` for `DRAFT_ONLY`
  - exit `3` for `FAILED`
  - exit `1` for program errors
  - output includes batch IDs, gate status, missing checks, and fallback summary only.

### Validation

- Ran: `.venv\Scripts\python.exe -m pytest tests/integration/test_market_pipeline.py tests/integration/test_collect_daily_review_cli.py -q`
- Result: `5 passed`
- Ran: `.venv\Scripts\python.exe -m pytest tests/unit/test_http_client.py tests/unit/test_tushare_market.py tests/unit/test_supplemental_adapters.py -q`
- Result: `17 passed`

### Current State

- Task 8 implementation is complete for offline/injected-adapter orchestration.
- Live collection is still not validated because `TUSHARE_TOKEN` is not configured in this task environment.
- Next implementation step: Task 9, dynamic sentiment, theme cycle, stock role, circuit breaker, and review builder.

## 2026-09-02 Task 7 Strict Quality Gate And Confidence

### Completed

- Added `src/services/quality_gate.py`.
- Quality gate now evaluates hard checks for:
  - confirmed trading day
  - trade-date consistency
  - security status explained ratio
  - required daily quote field coverage
  - major index coverage
  - limit candidate coverage
  - supplemental source difference
  - critical unresolved conflicts
- Gate status rules:
  - any failed hard check returns `FAILED`
  - complete close snapshots return `PASSED`
  - intraday snapshots return `DRAFT_ONLY` even if complete
- Enhancement gaps reduce confidence without changing `PASSED` when hard checks pass.

### Validation

- Ran: `.venv\Scripts\python.exe -m pytest tests/unit/test_quality_gate.py -q`
- Result: `5 passed`

### Current State

- Task 7 implementation is complete.
- Next implementation step: Task 8, collection orchestration, fallback audit writing, and CLI exit semantics.

## 2026-09-02 Task 6 Normalization, Recalculation, And Conflict Preservation

### Completed

- Added `src/services/normalization_service.py`.
  - Normalizes A-share codes to `ts_code` format.
  - Normalizes trade dates from `YYYYMMDD`, ISO date strings, `date`, and `datetime`.
  - Converts turnover units to 亿元, including Tushare daily `amount` from 千元.
  - Preserves primary and supplemental candidates when values conflict.
- Added `src/services/market_calculations.py`.
  - Recomputes advancers, flat names, decliners, and turnover from quote rows.
  - Calculates limit-up reference prices using board rules:
    - 10% for main board
    - 20% for ChiNext and STAR
    - 30% for Beijing Stock Exchange
    - 5% for ST names
- Added unit tests for code/date/unit normalization, market breadth, limit price rules, and conflict preservation.

### Validation

- Ran: `.venv\Scripts\python.exe -m pytest tests/unit/test_normalization_service.py tests/unit/test_market_calculations.py -q`
- Result: `9 passed`

### Current State

- Task 6 implementation is complete.
- Next implementation step: Task 7, strict market data quality gate and confidence calculation.

## 2026-09-02 Task 5 Supplemental Sources And Scoped Eastmoney Fallback

### Completed

- Added supplemental adapters:
  - `src/adapters/tencent_market.py`
  - `src/adapters/ths_market.py`
  - `src/adapters/cninfo_disclosure.py`
  - `src/adapters/eastmoney_fallback.py`
- Added offline fixtures under `tests/fixtures/supplemental`.
- Tencent adapter parses quote text into code, name, price, previous close, amount, and timestamp.
- THS adapter normalizes limit-up, limit-down, failed-limit, and theme-membership payload sections.
- CNINFO adapter preserves official announcement URLs and validates required announcement fields.
- Eastmoney fallback adapter:
  - rejects core datasets including `stock_daily`, `trade_calendar`, `index_daily`, `adj_factor`, `financials`, and `announcements`
  - allows only configured supplemental field groups
  - forces `is_fallback=True` and non-empty fallback reason

### Validation

- Ran: `.venv\Scripts\python.exe -m pytest tests/unit/test_supplemental_adapters.py -q`
- Result: `8 passed`

### Current State

- Task 5 implementation is complete.
- Supplemental adapters are offline-testable through injected loaders; production remote wiring remains for the orchestration task.
- Next implementation step: Task 6, normalization, recomputation, and cross-source conflict preservation.

## 2026-09-02 Task 4 Tushare Core Market Adapter

### Completed

- Added `src/adapters/tushare_market.py`.
- Implemented core Tushare datasets:
  - `trade_cal`
  - `stock_basic`
  - `daily`
  - `index_daily`
  - `adj_factor`
- Production construction uses `tushare.pro_api(settings.tushare_token)` through `RuntimeSettings`.
- Unit tests inject a fake `pro` client and do not access the network.
- Added fixed Tushare-structure fixtures under `tests/fixtures/tushare`.
- Adapter validation now rejects:
  - non-DataFrame responses
  - missing required columns
  - empty responses
  - trade-date mismatches
  - duplicate `ts_code` records where uniqueness is required
  - Tushare permission failures, converted to `AdapterPermissionError`

### Validation

- Ran: `.venv\Scripts\python.exe -m pytest tests/unit/test_tushare_market.py -q`
- Result: `5 passed`

### Current State

- Task 4 implementation is complete.
- No live Tushare request was run because `TUSHARE_TOKEN` is not configured in this task environment.
- Next implementation step: Task 5, supplemental adapters and strictly scoped Eastmoney fallback.

## 2026-09-02 Task 3 Immutable Raw Archive And Safe HTTP

### Completed

- Added adapter error taxonomy in `src/adapters/base.py`:
  - `AdapterError`
  - `AdapterTimeout`
  - `AdapterPermissionError`
  - `AdapterSchemaError`
  - `AdapterDataError`
- Added safe HTTP client in `src/adapters/http.py`.
  - Retries timeouts, connection failures, HTTP 429, and 5xx responses.
  - Does not retry HTTP 400, 401, or 403.
  - Converts 401/403 into `AdapterPermissionError`.
  - Error messages do not include token values or full query parameters.
- Added immutable content-addressed raw archive service:
  - `src/services/raw_archive_service.py`
  - Path format: `data/raw/<source>/<trade_date>/<dataset>/<sha256>.json`
  - Same content returns the existing path.
  - Writes through a temporary file and atomic replace.

### Validation

- Ran: `.venv\Scripts\python.exe -m pytest tests/unit/test_http_client.py tests/unit/test_raw_archive_service.py -q`
- Result: `6 passed`

### Current State

- Task 3 implementation is complete.
- Next implementation step: Task 4, Tushare core market adapter using injected test clients and real production token loading.

## 2026-09-02 Task 2 Auditable Source And Quality Schema

### Completed

- Added market data domain types in `src/domain/market_data.py`:
  - `SourceName`, `BatchStatus`, `GateStatus`, `ReportStatus`
  - immutable `SourceRecord`, `GateCheck`, and `GateDecision`
- Added six real-pipeline audit tables to SQLAlchemy models and `sql/schema.sql`:
  - `source_batch`
  - `source_observation`
  - `quality_gate_run`
  - `quality_gate_check`
  - `source_fallback`
  - `analysis_snapshot`
- Added backup-first migration script:
  - `scripts/migrate_real_pipeline.py`
- Migration behavior:
  - Copies the database to `<name>.pre-real-pipeline-<UTC时间>.bak` first.
  - Creates the new schema tables.
  - Deletes `data_kind='demo'` review-import and trading-day business records.
  - Preserves existing `real` records.

### Validation

- Ran: `.venv\Scripts\python.exe -m pytest tests/integration/test_database_schema.py tests/integration/test_real_pipeline_migration.py -q`
- Result: `5 passed`

### Current State

- Task 2 implementation is complete.
- The formal database schema now has audit space for immutable source batches, normalized observations, fallback disclosure, quality gate checks, and analysis snapshots.
- Next implementation step: Task 3, immutable raw archive service and safe HTTP error semantics.

## 2026-09-02 Task 1 Real-Data Runtime Configuration

### Completed

- Added versioned real-data pipeline configuration:
  - `config/data_pipeline.json`
  - `src/config/runtime.py`
  - `src/config/__init__.py`
- Updated `.env.example` with `DATA_PIPELINE_CONFIG` and kept `TUSHARE_TOKEN` as an uncommitted local secret.
- Tightened the formal review contract:
  - `DataKind` now contains only `real`.
  - `DailyReview.schema_version` is now `2.0`.
  - `DailyReview.data_kind` accepts only `real`.
  - JSON Schema was regenerated from the Pydantic model.
- Added tests for missing `TUSHARE_TOKEN`, token-safe config summaries, environment config path loading, demo rejection, and schema-version rejection.

### Validation

- Ran: `.venv\Scripts\python.exe -m pytest tests/unit/test_runtime_config.py tests/unit/test_review_validation.py -q`
- Result: `15 passed`

### Current State

- Task 1 implementation is complete.
- No real-data end-to-end validation has been performed because `TUSHARE_TOKEN` is still not configured in this task environment.
- Next implementation step: Task 2, auditable source, raw batch, fallback, quality gate, and analysis snapshot schema.

## 2026-09-02 真实数据链路设计与计划

### Task

把第一阶段 A 股复盘 Dashboard 升级为只使用真实数据、可审计且受严格数据门禁控制的生产链路。

### Completed

- 用户批准真实数据源方案：Tushare 为核心主源；腾讯、同花顺、交易所和巨潮资讯补充。
- 东方财富仅可在市场宽度、涨跌停、炸板、连板和题材归属等补充字段中应急降级，且必须披露来源、原因、抓取时间和交叉验证状态。
- 用户批准严格数据门禁：核心行情不完整时禁止生成正式复盘和正式 PDF；增强数据缺失时降低对应结论置信度。
- 明确 AI 算力、中际旭创等仅为历史示例，不能写入固定生产配置；题材和个股必须从目标交易日真实数据动态识别。
- 明确模拟数据只能保留在自动化测试夹具中，不得进入生产数据库、Dashboard 或正式报告。
- 已完成并提交设计规格：
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\docs\superpowers\specs\2026-09-02-real-market-data-pipeline-design.md`
  - Commit: `44b4c09 docs: design real market data pipeline`
- 已完成并提交 13 个任务的实施计划：
  - `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\docs\superpowers\plans\2026-09-02-real-market-data-pipeline-implementation.md`
  - Commit: `829e7ca docs: plan real market data pipeline`

### Current State

- 正式工作区：`D:\桌面\新建文件夹\a_share_daily_review_codex-sync`
- Git 分支：`codex/phase1-dashboard`
- GitHub 目标仓库：`https://github.com/lc931223-lc/a-share-daily-review`
- 当前阶段停在实施开始前，业务代码尚未按新规格修改。
- 下一次无需重新讨论设计；直接从实施计划 Task 1 开始。
- 推荐执行方式：子任务驱动，每个 Task 完成后运行定向测试和提交。

### Validation

- 设计规格已完成占位符、矛盾、范围和歧义自审。
- 实施计划已完成规格覆盖、占位符和类型一致性自审。
- 两份文档均已提交，记录在当前本地分支。
- 尚未运行真实 Tushare 采集、真实历史日门禁、Dashboard 新版视觉验收或正式 PDF 验收。

### Blockers / Risks

- 当前环境未检测到 `TUSHARE_TOKEN`。离线实现和模拟适配器单元测试可以先进行，但真实历史交易日验收必须配置 Token。
- Token 只能放在未纳入 Git 的 `.env` 或环境变量中，不得写入聊天、代码、日志、数据库或报告。
- Tushare 账户权限和积分可能限制接口；权限不足时必须停止相关正式验收，不能用模拟数据代替。
- GitHub 推送状态未在本次检查点中重新验证；本地提交是当前可靠恢复点。

### Next Actions

1. 读取上述设计规格和实施计划。
2. 选择子任务驱动或当前线程分批执行；默认采用子任务驱动。
3. 执行 Task 1：生产配置、`.env.example`、严格 real 契约和配置测试。
4. 依次完成原始批次审计、Tushare 主适配器和严格质量门禁。
5. 在真实端到端验收前，本地配置 `TUSHARE_TOKEN`，不要提交密钥。

## Task

Set up a long-thread-friendly A-share research workspace and user-level Codex skills.

## Completed

- Created workspace directories:
  - `C:\Users\愚者\Documents\New project 3\data`
  - `C:\Users\愚者\Documents\New project 3\research`
  - `C:\Users\愚者\Documents\New project 3\reports`
  - `C:\Users\愚者\Documents\New project 3\scripts`
- Created project memory file:
  - `C:\Users\愚者\Documents\New project 3\CODEx_MEMORY.md`
- Installed finance research skills under:
  - `C:\Users\愚者\.codex\skills`
- Installed thread stability skills:
  - `thread-handoff-summary`
  - `project-memory-capture`
  - `task-checkpoint-manager`
  - `long-thread-stability`
- Installed event-driven alert skills:
  - `a-share-catalyst-monitor`
  - `ipo-beneficiary-radar`
  - `event-driven-watchlist`
- Created watchlists:
  - `C:\Users\愚者\Documents\New project 3\research\watchlists\changxin-memory-ipo.md`
  - `C:\Users\愚者\Documents\New project 3\research\watchlists\hefei-state-capital.md`
  - `C:\Users\愚者\Documents\New project 3\research\watchlists\semiconductor-supply-chain.md`
- Created alert report template:
  - `C:\Users\愚者\Documents\New project 3\reports\alerts\ALERT_TEMPLATE.md`
- Created active automations:
  - `a-2`: A股事件驱动盘前扫描
  - `a-3`: A股事件驱动盘后扫描

## Current State

This workspace should be used as the persistent state layer for future A-share research, data pulls, scripts, and reports. Chat history should not be the only source of memory.

Event-driven monitoring is now organized around watchlists and dated alert reports. The main initial topics are 长鑫科技/长鑫存储 IPO, 合肥国资/产业资本映射, and 半导体国产化供应链.

Generated a 2026-05-27 A-share market analysis report that combines the user's local PDF framework, the TimesFM GitHub project, and same-day public market data:
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-27-a-share-market-analysis.html`
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-27-a-share-market-analysis.pdf`
- Extracted source PDF text: `C:\Users\愚者\Documents\New project 3\research\skill-pdf-extract-2026-05-27.txt`

Generated a revised version incorporating `5月27日大盘异动解密.pdf`:
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-27-a-share-market-analysis-revised.html`
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-27-a-share-market-analysis-revised.pdf`
- Extracted second source PDF text: `C:\Users\愚者\Documents\New project 3\research\market-move-decode-2026-05-27-extract.txt`

Generated a cleaner 5-day A-share analysis report that uses the user's provided materials but omits source-title/method-positioning language:
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-28-a-share-5day-market-analysis.html`
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-28-a-share-5day-market-analysis.pdf`

Generated final 5.27 A-share market analysis and 5.28 forecast report:
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-27-a-share-final-analysis-forecast.md`
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-27-a-share-final-analysis-forecast.html`
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-27-a-share-final-analysis-forecast.pdf`
- Extracted final source PDF text: `C:\Users\愚者\Documents\New project 3\research\market-move-decode-2026-05-27-final-extract.txt`

## Validation

- Directory creation was verified by listing the workspace folders.
- Skill files should be picked up after restarting Codex.
- Watchlist files and alert template were created.
- Automation cards were created in the Codex app.
- The generated market-analysis PDF was checked with PDF.js: 4 pages and readable text on page 1.
- The revised PDF was checked with PDF.js: 5 pages and readable text on page 1.
- The 5-day analysis PDF was checked with PDF.js: 4 pages and readable text on page 1.
- The final 5.27 analysis and 5.28 forecast PDF was generated directly with embedded Chinese font and checked with PDF.js: 3 pages and readable text on page 1.

Regenerated a UI-styled final PDF with explicit 5.27 intraday evolution sections:
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-27-a-share-final-analysis-forecast-ui.pdf`
- Render script: `C:\Users\愚者\Documents\New project 3\scripts\render_final_ui_market_pdf.js`
- Checked with PDF.js: 3 pages and readable text on page 1.

Regenerated a larger black Songti-style version:
- `C:\Users\愚者\Documents\New project 3\reports\2026-05-27-a-share-final-analysis-forecast-songti-black.pdf`
- Uses `C:\Windows\Fonts\STSONG.TTF`, black text, larger font/line spacing.
- Checked with PDF.js: 4 pages and readable text on page 1.

## Pending

- Configure `TUSHARE_TOKEN` if Tushare data access is needed.
- Add actual data scripts when the first data-driven workflow is requested.
- Tune automation schedules in the Codex app if exact wall-clock timing needs adjustment.

## 2026-06-28 Automation a-2 Status

- Ran A股事件驱动盘前扫描 for the watchlists under `C:\Users\愚者\Documents\New project 3\research\watchlists`.
- Wrote alert report: `C:\Users\愚者\Documents\New project 3\reports\alerts\2026-06-28-a-share-preopen-event-scan.md`.
- Conclusion: no material new CXMT IPO / Hefei state-capital direct catalyst found after 2026-06-19; CXMT official status remains CSRC approval / SSE 注册生效 from 2026-06-12 to 2026-06-15 public updates.
- Noted one indirect semiconductor-localization signal: 华虹公司(688347) 2026-06-23 report for acquiring 华力微 97.4988% equity and raising matching funds; not treated as a direct CXMT beneficiary chain.

## Next Actions

1. Restart Codex so newly installed skills are discoverable in new threads.
2. For future long tasks, read `CODEx_MEMORY.md` and `CHECKPOINT.md` first.
3. Save large outputs into `research`, `data`, or `reports`.

## 2026-08-31 PDF Typography Update

- Replaced the report fallback font with the embedded Source Han Sans CN variable font:
  - `C:\Users\愚者\Documents\New project 3\assets\fonts\SourceHanSansCN-VF.ttf`
- Increased title, body, annotation, and table text sizes and expanded line spacing/padding.
- Added explicit pagination so theme and stock-role tables are not split from their dates.
- Regenerated and visually checked all 11 pages with Poppler; no clipping, overlap, or missing Chinese glyphs were found.
- Final report:
  - `C:\Users\愚者\Documents\New project 3\output\pdf\2026-08-30-sentiment-review-2026-08-24-to-2026-08-28.pdf`

## 2026-09-01 Reference-Matched Font Weights

- Inspected `D:\桌面\92科比淘股吧直播内容整理.pdf` strictly as a visual/font reference.
- Identified its font hierarchy as Source Han Sans CN Regular, Medium, and Bold.
- Generated static Regular/Medium/Bold TTF instances and mapped them to body text, headings/table headers, and primary emphasis respectively.
- Regenerated the 11-page report and visually checked every page; text is solid black with no clipping or table overflow.
- Final readability tuning kept the report at 11 pages while increasing narrative body text from 12pt to 14pt and table text from 10pt to 11.5pt.
- This Source Han Sans CN font hierarchy and readable-size policy is now stored in `CODEx_MEMORY.md` as the default for future Chinese PDFs.

## 2026-08-30 A股情绪引擎集成

- Wrote and committed the Chinese design spec:
  - `C:\Users\愚者\Documents\New project 3\docs\superpowers\specs\2026-08-30-a-share-sentiment-engine-design.md`
- Implemented reusable engine:
  - `C:\Users\愚者\Documents\New project 3\tools\a_share_sentiment_engine.py`
- Refactored the 2026-08-24 to 2026-08-28 sentiment review script into a thin wrapper:
  - `C:\Users\愚者\Documents\New project 3\tools\review_sentiment_20260824_20260828.py`
- Engine output contract:
  - `market_dashboard`
  - `theme_ranking`
  - `stock_role_classification`
  - `discipline_gate`
- Intended validation command once Python is available in PATH:
  - `python tools/review_sentiment_20260824_20260828.py`
- Runtime status update: Python is now available through the project virtual environment:
  - `C:\Users\愚者\Documents\New project 3\.venv\Scripts\python.exe`
- Created the virtual environment with user-local uv:
  - `C:\Users\愚者\.local\bin\uv.exe`
- Installed A-share and PDF dependencies into `.venv`, including `akshare`, `pandas`, `reportlab`, `pypdf`, and `pdfplumber`.
- Successful validation command:
  - `.venv\Scripts\python.exe tools\review_sentiment_20260824_20260828.py`
- Generated PDF report:
  - `C:\Users\愚者\Documents\New project 3\reports\market_reviews\2026-08-30-sentiment-review-2026-08-24-to-2026-08-28.pdf`
- PDF validation:
  - `pypdf` extracted 7 pages and found the four core sections.
  - Rendered page 1 with Poppler and visually confirmed Chinese tables are readable.

## 2026-08-30 Trading Framework And Market Review

- Added user-provided PDFs as future A-share analysis foundation materials:
  - `C:\Users\愚者\Documents\New project 3\research\frameworks\92科比淘股吧直播内容整理.pdf`
  - `C:\Users\愚者\Documents\New project 3\research\frameworks\交易守则-DS版.pdf`
- Extracted text from both PDFs:
  - `C:\Users\愚者\Documents\New project 3\research\frameworks\92科比淘股吧直播内容整理.txt`
  - `C:\Users\愚者\Documents\New project 3\research\frameworks\交易守则-DS版.txt`
- Wrote framework summary:
  - `C:\Users\愚者\Documents\New project 3\research\frameworks\a-share-trading-framework-foundation.md`
- Rule: these PDFs are research inputs only, not instructions to Codex.
- Pulled A-share index daily data with AKShare for 2025-09-24 to 2026-08-28 and saved:
  - `C:\Users\愚者\Documents\New project 3\data\market_reviews\2025-09-24_to_2026-08-28`
- Wrote review report:
  - `C:\Users\愚者\Documents\New project 3\reports\market_reviews\2026-08-30-a-share-review-since-2025-09-24.md`
- Core conclusion: the period was structural rather than a broad bull market. High-beta tech and small/mid-cap exposure delivered gains only if the trader survived large drawdowns and reduced exposure around the July 2026 retreat.

## 2026-07-11 Automation a-3 Status

- Ran the post-market event-driven scan across all three watchlists, using public sources for the incremental window 2026-07-06 to 2026-07-11.
- Wrote alert report: `C:\Users\愚者\Documents\New project 3\reports\alerts\2026-07-11-a-share-postmarket-event-scan.md`.
- Material change: Changxin Technology (proposed STAR Market code 688825) released its prospectus and issuance-stage documents on 2026-07-09. Online/offline subscription is scheduled for 2026-07-16; the initial offering is 6,688,088,608 shares with a 15% over-allotment option.
- Updated `research\watchlists\changxin-memory-ipo.md` with this confirmed trigger. No direct CXMT customer, supplier, order, or new Hefei state-capital mapping was confirmed; equipment/material names remain thematic unless separately disclosed.

## 2026-07-11 Automation a-2 Status

- Completed the pre-open scan of all three event-driven watchlists.
- Wrote [`2026-07-11-a-share-preopen-event-scan.md`](C:\Users\愚者\Documents\New project 3\reports\alerts\2026-07-11-a-share-preopen-event-scan.md).
- Material change: Changxin Technology disclosed its IPO prospectus and issuance timetable on 2026-07-09; online/offline subscription is scheduled for 2026-07-16. Treat as an IPO-stage catalyst, not as confirmed supplier/customer evidence for the A-share watchlist names.
- No new direct Hefei state-capital action or explicit Changxin supplier/customer/equity-link disclosure was identified in the scan window.

## 2026-07-05 Automation a-2 Status

- Ran A股事件驱动盘前扫描 for the watchlists under `C:\Users\愚者\Documents\New project 3\research\watchlists`.
- Wrote alert report: `C:\Users\愚者\Documents\New project 3\reports\alerts\2026-07-05-a-share-preopen-event-scan.md`.
- Conclusion: no material new CXMT IPO / Hefei state-capital direct catalyst found after 2026-06-28. SSE project JSON still shows Changxin update time `2026-06-15 09:03:25`; latest attachment remains the 2026-06-12 registration approval.
- Noted one indirect semiconductor equipment-chain financing signal: 拓荆科技(688072) 2026-07-03 private-placement issuance result / listing announcement; not treated as direct CXMT customer/order evidence.

## 2026-09-01 Codex Cloud Migration

- Prepared the project for `https://github.com/lc931223-lc/a-share-daily-review` on branch `main`.
- Added a cross-platform `README.md`, cloud environment guidance, secret handling rules, and the Source Han Sans license.
- Excluded `.env`, virtual environments, browser caches, temporary output, local Cloudflare binaries, and the unused variable font.
- Verified Python compilation and regenerated the cached 2026-08-24 to 2026-08-28 PDF successfully before migration.

## 2026-09-01 Codex Cloud Reproducibility Fix

- Made cached sentiment outputs deterministic across operating systems and repeated runs.
- Sorted theme names before aggregation and used theme name as the stable tiebreaker for equal scores.
- Normalized the recorded data directory to POSIX separators on every platform.
- Enabled invariant ReportLab output so identical inputs produce an identical PDF hash.
- Added a regression test for equal-score theme ordering.
- Verified Python compilation, dependency integrity, the regression test, and two consecutive cached report runs.
- Both generated PDFs had SHA-256 `4486a02b1341578df861754011c4c7fd33b7b543cdd802cbb2f686ff2c382f33`.
- Rendered and visually checked all 11 pages; Source Han Sans CN remained embedded and no layout defects were found.

## 2026-09-05 Auction Phase A2

- Implemented the minimum auction pipeline under `src/auction` with a 100-200 stock watchlist, eltdx process events, nine checkpoints, formal 09:25 match, Parquet facts, existing SQLite audit tables, anomaly fields, realtime open routing, and Tushare EOD reconciliation.
- Added `scripts/run_auction_pipeline.py` with `historical`, `live`, and `eod` modes. Live mode rejects starts after 09:15 Asia/Shanghai so replay data cannot pass as a realtime session.
- Latest 2026-09-04 historical replay result: 100 stocks, 100% stock completion, 94.67% overall checkpoint coverage, 100% post-09:20 coverage, 100% formal match coverage, and 100/100 archived Tushare open validation with zero price error or conflicts.
- The 2026-09-04 packet remains `PARTIAL`: the prior 2026-09-03 official review is absent and a historical replay cannot satisfy the required live-session acceptance.
- Added initial objective anomaly classifications: `EXTREME_VOLUME_ANOMALY`, `STRONG_VOLUME_CONFIRMATION`, `PRICE_STRONG_VOLUME_WEAK`, and `PRICE_WEAK_VOLUME_STRONG`.
- Added objective market/sector/stock rankings and a compact ChatGPT packet. Mainline validation and strength-transition candidates require the previous official review; they remain explicitly `UNAVAILABLE` when it is missing.
- Output files: `data/auction_watchlists/auction_watchlist_2026-09-04.json`, `data/auction_packets/2026-09-04.json`, and `data/auction_packets/2026-09-04_compact.json`.
- The compact replay contains 20 sector rows, 30 stock rows, 30 compact anomaly rows, and four pending 09:30-10:00 objective validation conditions. Full replay found 85 stocks with at least one anomaly label.
- Final validation: `compileall` passed; non-real-data suite `213 passed, 1 deselected`; auction-focused suite `25 passed`.
- Pending external-time acceptance: start `python scripts/run_auction_pipeline.py --date 2026-09-07 --mode live --baseline-days 60` before 09:15 Asia/Shanghai on the next trading day, then run `--mode eod` after Tushare daily data is available.

## 2026-09-01 CODEX_HOME Migration Verification

- Migrated the effective Codex home to `D:\CodexData\codex-home` and preserved `C:\Users\愚者\.codex` as an untouched recovery source.
- Verified both the active Codex process and the Windows user environment resolve `CODEX_HOME` to `D:\CodexData\codex-home`.
- Verified `config.toml`, `sessions`, `skills`, `plugins`, and `CODEX_HOME_MIGRATION_COMPLETE.txt` in the new home.
- Preserved Codex-managed junctions into `D:\CodexData\.codex-live` and `D:\CodexData\.codex-moved`.
- Second-pass testing found that the browser service resolves the `plugins` junction to `D:\CodexData\.codex-live\plugins`; added junction targets to `NODE_REPL_TRUSTED_CODE_PATHS` and updated `tools\migrate_codex_home.ps1` to apply this rule on future runs.
- Browser control must be retested after restarting Codex because restarting only the Node REPL closes the current MCP transport.
- The Codex app project API currently lists the local project and the ChatGPT project `股海愚者`, but no repository-backed Cloud project. A Cloud ChatGPT Work task was queued as a connectivity probe; repository mounting remains unverified until browser control or the Cloud environment UI succeeds.
