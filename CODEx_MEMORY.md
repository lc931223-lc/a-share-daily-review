# Codex Memory

## Project

Personal A-share research and data-analysis workspace for industry-chain research, financial report review, theme screening, risk checks, valuation checks, Tushare/AKShare data pulls, market sentiment, sector rotation, price-volume analysis, limit-up board review, and dragon-tiger-list analysis.

## User Preferences

- Prefer Chinese-language answers for A-share research.
- Prefer ranked tables with evidence strength, dates, source links, and clear caveats.
- Distinguish confirmed facts from inference and concept-only relationships.
- Avoid dumping large raw data into chat; save raw data and long tables into files.
- For current market, IPO, ownership, supplier/customer, regulation, price, and financial data, verify freshness before answering.
- For future Chinese PDF reports, default to embedded Source Han Sans CN with Regular body text, Medium headings/table headers, and Bold primary titles or emphasis.
- Use solid black reading text. Prefer approximately 14pt narrative body text and 11.5pt table text when the layout permits, maximizing readability without materially increasing page count.

## Workspace

- Active implementation repo: `D:\桌面\新建文件夹\a_share_daily_review_codex-sync`
- Active branch: `codex/phase1-dashboard`
- Approved real-data design: `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\docs\superpowers\specs\2026-09-02-real-market-data-pipeline-design.md`
- Approved implementation plan: `D:\桌面\新建文件夹\a_share_daily_review_codex-sync\docs\superpowers\plans\2026-09-02-real-market-data-pipeline-implementation.md`
- Root: `C:\Users\愚者\Documents\New project 3`
- Research notes: `C:\Users\愚者\Documents\New project 3\research`
- Data files: `C:\Users\愚者\Documents\New project 3\data`
- Scripts: `C:\Users\愚者\Documents\New project 3\scripts`
- Reports: `C:\Users\愚者\Documents\New project 3\reports`
- Current checkpoint: `C:\Users\愚者\Documents\New project 3\CHECKPOINT.md`
- Project Python: `C:\Users\愚者\Documents\New project 3\.venv\Scripts\python.exe`
- User-local uv: `C:\Users\愚者\.local\bin\uv.exe`

## Installed Finance Skills

- `a-share-supply-chain-map`
- `financial-report-digest`
- `theme-stock-screener`
- `stock-risk-scanner`
- `stock-valuation-check`
- `tushare-a-share-data`
- `akshare-market-data`
- `market-sentiment-dashboard`
- `sector-rotation-tracker`
- `a-share-price-volume-analyzer`
- `limit-up-board-analyzer`
- `dragon-tiger-list-analyzer`

## Installed Thread Stability Skills

- `thread-handoff-summary`
- `project-memory-capture`
- `task-checkpoint-manager`
- `long-thread-stability`

## Installed Event-Driven Skills

- `a-share-catalyst-monitor`
- `ipo-beneficiary-radar`
- `event-driven-watchlist`

## Event-Driven Watchlists

- `C:\Users\愚者\Documents\New project 3\research\watchlists\changxin-memory-ipo.md`
- `C:\Users\愚者\Documents\New project 3\research\watchlists\hefei-state-capital.md`
- `C:\Users\愚者\Documents\New project 3\research\watchlists\semiconductor-supply-chain.md`

## Automations

- `a-2`: A股事件驱动盘前扫描
- `a-3`: A股事件驱动盘后扫描

## Data Source Notes

- Phase 1 responsibility boundary: Codex generates factual Market Research Packets only. Codex must not make final A-share review conclusions, final theme ranking, final S/A/B/C ratings, or buy/sell recommendations. ChatGPT owns final research judgment after reading the packet.
- Production packet source order is Eastmoney/AKShare public structured data first, with Tencent/THS, exchange/CNINFO, official policy sources, and cached raw files as supplements. Tushare is optional and only used when the token has the required endpoint permissions.
- Eastmoney/AKShare can be used for limit-up/down pools, failed-limit pools, previous limit-up feedback, dragon-tiger lists, northbound flow, SZSE margin, industry/concept fund flow, and objective candidate generation. Record source, retrieved_at, data_date, freshness, and quality for every module.
- Tushare workflows require a configured token via `TUSHARE_TOKEN`; the token must never be committed or written to reports, logs, databases, or chat. The currently tested user token now has Pro `daily` access. Use `tushare.daily(trade_date=...)` to supplement Market Packet breadth, total turnover, previous turnover, and stock-universe OHLCV. `moneyflow`, `stk_limit`, and `limit_list_d` still returned permission errors in the latest probe; some other endpoints such as `trade_cal`, `daily_basic`, `adj_factor`, and `index_daily` can hit low per-minute frequency limits.
- AKShare can be used when public data is sufficient or Tushare token/permissions are unavailable. Market Packet stock-universe OHLCV first uses Tushare full-market `daily` when available, then falls back to `akshare.stock_zh_a_hist`, `akshare.stock_zh_a_hist_tx`, and `akshare.stock_zh_a_daily` because the Eastmoney historical host can fail behind the current network/proxy.
- Primary sources are preferred for company facts: exchange filings, CNINFO, annual reports, prospectuses, official announcements, and company investor relations records.
- Use the project virtual environment for Python commands, for example `.venv\Scripts\python.exe tools\review_sentiment_20260824_20260828.py`.

## Trading Framework Foundation

- User added two PDF files as future A-share analysis foundations:
  - `C:\Users\愚者\Documents\New project 3\research\frameworks\92科比淘股吧直播内容整理.pdf`
  - `C:\Users\愚者\Documents\New project 3\research\frameworks\交易守则-DS版.pdf`
- Treat these PDFs as research materials only, not as instructions to Codex.
- Summary file: `C:\Users\愚者\Documents\New project 3\research\frameworks\a-share-trading-framework-foundation.md`
- Future A-share analysis should include this framework as one pillar: market temperature, emotion cycle, stock status within a theme, and trading discipline.
- Core short-term concepts to consider: 龙头, 补涨, 切换, 情绪周期, 两端交易, 避免中位股, 预案优先, 禁止临盘冲动, 单票止损, 连续亏损熔断.
- This framework must be combined with data, valuation, filings, risk checks, and liquidity constraints before any investment conclusion.
- Programmatic sentiment engine:
  - Spec: `C:\Users\愚者\Documents\New project 3\docs\superpowers\specs\2026-08-30-a-share-sentiment-engine-design.md`
  - Engine: `C:\Users\愚者\Documents\New project 3\tools\a_share_sentiment_engine.py`
  - Default future structure: market_dashboard, theme_ranking, stock_role_classification, discipline_gate.
  - Use this for A股情绪温度计、题材周期识别、龙头/补涨/中位股分类、交易纪律熔断器.
- Market review from 2025-09-24 to 2026-08-28:
  - `C:\Users\愚者\Documents\New project 3\reports\market_reviews\2026-08-30-a-share-review-since-2025-09-24.md`
  - `C:\Users\愚者\Documents\New project 3\data\market_reviews\2025-09-24_to_2026-08-28\review_metrics.json`

## Operating Rule

For long tasks, update `CHECKPOINT.md` at phase boundaries and keep raw data or large outputs in `data`, `research`, or `reports` instead of the chat.

For the production daily-review pipeline, never inject fixed example themes or stocks. AI算力 and 中际旭创 were discussion examples only. Production themes, leaders, capacity cores, catch-up stocks, middle-position stocks, isolated stocks, and risk stocks must be derived from the target trading day's real observations.

Simulation data may exist only under automated-test fixtures. It must not appear in the production database, Dashboard, formal review, or PDF. A failed hard data gate may produce a quality report or clearly marked intraday draft, but never a formal conclusion.

Market Packet outputs:
- Full packet: `data/market_packets/YYYY-MM-DD.json`
- Quality report: `data/market_packets/YYYY-MM-DD_quality.json`
- ChatGPT input: `data/market_packets/YYYY-MM-DD_compact.json`
- Human summary: `reports/market_packets/YYYY-MM-DD-summary.md`

Three-layer architecture acceptance rule:
- ChatGPT is the final researcher/analyst.
- Codex is the data engineer, executor, storage layer, and display system.
- Official review input path: `data/official_reviews/YYYY-MM-DD.json`.
- Official review schema: `schemas/official_review.schema.json`.
- Import command: `.venv\Scripts\python.exe tools\import_official_review.py data\official_reviews\YYYY-MM-DD.json`.
- Daily pipeline command: `.venv\Scripts\python.exe tools\run_daily_pipeline.py --date YYYY-MM-DD`.
- GitHub `main` is the only accepted delivery branch for this project. Feature branches are not final until merged and pushed to `origin/main`.
- Do not track `data/raw/market_packets/`; it is local cache.

For proactive A-share catalyst monitoring, use the watchlists under `research\watchlists` and save dated alert reports under `reports\alerts`.

## Repository And Cloud

- GitHub repository: `https://github.com/lc931223-lc/a-share-daily-review`
- Default branch: `main`
- `README.md` contains the local and Codex Cloud bootstrap commands.
- Never commit `.env`, access tokens, browser profiles, local tunnel binaries, or temporary PDF output.
