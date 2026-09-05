# A股每日复盘与真实数据门禁系统

本项目用于生成可审计的 A 股每日研究数据包、Dashboard 和 PDF。Phase 1 架构调整后，Codex 不再负责生成最终 A 股投资研究结论，不再自行判断“第一主线”或给题材做最终 S/A/B/C 评级。Codex 的职责是数据工程师、数据校验员和研究资料整理员；最终复盘判断由 ChatGPT 基于 `market_packet` 完成。

当前数据包链路优先使用东方财富/AKShare 公开结构化数据，腾讯、同花顺、交易所和巨潮用于补充或核验，Tushare 在配置且具备接口权限时作为可选增强/交叉核验源。当前测试 token 已具备 Tushare Pro `daily` 权限，可用于补齐全市场涨跌家数、成交额、上一交易日成交额和股票池 OHLCV。

模拟数据只能出现在自动化测试夹具中，不得写入生产数据库、Dashboard 或正式报告。

## 功能

- Pydantic 与 JSON Schema 双层契约校验，正式 `DailyReview` 使用 schema `2.0` 且 `data_kind` 固定为 `real`。
- 版本化数据门禁配置：`config/data_pipeline.json`。
- 原始来源批次、标准化观察、降级来源、质量门禁和分析快照审计表。
- 东方财富默认行情适配器、Tushare 可选行情适配器，以及腾讯、同花顺和巨潮补充适配器。
- 严格质量门禁：核心行情不完整时拒绝正式复盘和正式 PDF。
- Streamlit 密集工作台 Dashboard，只展示 real/PASSED 快照。
- ReportLab PDF 生成，嵌入 Source Han Sans CN 字体并包含数据质量说明。

## 安装

推荐使用 Python 3.12：

```powershell
python -m pip install -r requirements.txt
```

如果系统 PATH 中没有 Python，可使用 `uv` 创建本地环境：

```powershell
C:\Users\愚者\.local\bin\uv.exe venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 凭据

默认东方财富公开数据路径不需要 `TUSHARE_TOKEN`。如果要启用 Tushare `daily` 增强补齐，复制 `.env.example` 为 `.env` 并填入本地凭据；不要提交 `.env`。

```powershell
TUSHARE_TOKEN=你的本地Token
DATA_PIPELINE_CONFIG=config/data_pipeline.json
```

没有 `TUSHARE_TOKEN` 时，系统仍会优先尝试东方财富公开数据。真实历史交易日端到端验收如果遇到实时公开源不可达或覆盖不足会跳过，不能视为正式通过。

## 采集

### Market Packet

每天收盘后先生成给 ChatGPT 使用的事实数据包：

```powershell
python scripts/build_market_packet.py --date auto
python scripts/build_market_packet.py --date 2026-09-03
python tools/build_market_packet.py --date 2026-09-03
```

输出：

- `data/market_packets/YYYY-MM-DD.json`
- `data/market_packets/YYYY-MM-DD_quality.json`
- `data/market_packets/YYYY-MM-DD_compact.json`
- `reports/market_packets/YYYY-MM-DD-summary.md`

`*_compact.json` 是推荐交给 ChatGPT 做正式复盘的输入。Market Packet 只保存事实、候选和数据质量，不生成最终主线、最终评级或买卖建议。缺失字段使用 `null`，并同步写入 `missing_data` 和质量报告；禁止用 0、旧缓存或推测值冒充缺失事实。

可使用 `--refresh-dataset policy|announcements|industry_board|concept_board|northbound` 定向刷新单个数据集；成功历史缓存保持原始 `retrieved_at`，失败缓存按错误类型设置 `retry_after`，不会永久粘住失败结果。

当前 Market Packet 会优先用 Tushare `daily(trade_date=...)` 补齐全市场涨跌家数、总成交额、上一交易日成交额和股票池目标日 OHLCV；没有 `TUSHARE_TOKEN` 或 `daily` 不可用时，股票池 OHLCV 继续顺序尝试 `akshare.stock_zh_a_hist`、`akshare.stock_zh_a_hist_tx`、`akshare.stock_zh_a_daily`。政策和公告仍需要独立数据源。

`trade_cal` 按年度长期缓存，`stock_basic` 每日最多刷新一次。`daily_basic` 和 `adj_factor` 默认不请求，仅在 `.env` 中分别设置 `MARKET_PACKET_INCLUDE_DAILY_BASIC=1`、`MARKET_PACKET_INCLUDE_ADJ_FACTOR=1` 时启用；可选增强失败不会拖垮核心 `daily` 行情。

公告按日期批量查询巨潮并在本地过滤核心股票池，交易所接口只作失败回退。成功与 `EMPTY_VALID` 结果永久复用，失败结果按 `retry_after` 重试。核心池覆盖涨停、跌停、昨日涨停、龙虎榜、全市场成交额前列、前一日正式复盘股票和可选跟踪池。

行业板块优先使用东方财富全量快照，失败时使用同花顺行业概览；概念板块优先使用东方财富全量快照，失败时使用新浪概念板块。两者都只在请求日为上海当前日期时联网，并以单批次方式归档。原始快照分别写入 `industry_board_daily`、`concept_board_daily`；涨停池推导后的研究视图另写入 `industries`、`themes`，不得冒充全量快照。历史日期只读取匹配 `source_data_date` 的已归档原始快照。

### Review Import

ChatGPT 输出正式 `review_YYYY-MM-DD.json` 后，再由 Codex 导入数据库，供 Dashboard、历史统计、回测和 PDF 使用。

```powershell
python tools/import_official_review.py data/official_reviews/2026-09-04.json
python tools/update_validation_results.py --date 2026-09-04
```

`official_review` 使用 `schemas/official_review.schema.json` 校验。Codex 只校验、归档、入库和统计，不修改 ChatGPT 给出的最终评分、评级、生命周期或判断。

### Daily Pipeline

统一执行入口：

```powershell
python tools/run_daily_pipeline.py --date auto
python tools/run_daily_pipeline.py --date 2026-09-04
```

`run_daily_pipeline` 只负责生成 Market Packet、记录质量、检查是否存在 `data/official_reviews/YYYY-MM-DD.json`、存在则导入并更新验证结果；不存在时退出 `2`，不会自动编造正式复盘结论。

旧的真实数据采集门禁命令仍保留：

```powershell
python collect_daily_review.py --date 2026-09-01 --mode close
python collect_daily_review.py --date 2026-09-01 --mode intraday
```

退出码：

- `0`：`PASSED`
- `2`：`DRAFT_ONLY`
- `3`：`FAILED`
- `1`：程序错误

## 数据库

数据存储采用两层结构：SQLite `data/a_share_review.db` 保存目录、来源批次、质量门、事实版本和服务状态；中大规模规范化事实写入 `data/facts/dataset=<name>/trade_date=<date>/part-<hash>.parquet`。Parquet 使用 Zstandard 压缩和内容哈希幂等命名，DuckDB 负责跨日分析查询。公告和政策的原始输入按日保存为 `source_records.jsonl.gz`，不再逐条产生小 JSON 文件。Parquet 读取会将 Arrow 数组和 NumPy 标量恢复成 JSON 安全类型，板块历史读取还会校验原始快照标识，防止派生数据或跨日数据污染。

板块数据源路由保存在 `config/market_packet_sources.json`。行业和概念板块在当日使用东方财富单次全量快照并归档；历史日期只读取已归档快照，缺失时返回 `UNAVAILABLE`，禁止用当前数据回填或逐板块 N+1 重建。公告优先使用巨潮按日期批量查询，批量接口失败后才按核心股票池走交易所正式来源回退。

正式三层架构表包括：

- `trading_day`
- `market_daily`
- `theme`
- `theme_daily_review`
- `stock`
- `stock_daily_review`
- `evidence`
- `tomorrow_check`
- `validation_result`
- `score_history`
- `market_packet_log`

## 集合竞价 Phase A2

历史回放、真实交易日采集和盘后 Tushare 开盘价复核分别运行：

```powershell
python scripts/run_auction_pipeline.py --date 2026-09-04 --mode historical --baseline-days 60
python scripts/run_auction_pipeline.py --date 2026-09-07 --mode live --baseline-days 60
python scripts/run_auction_pipeline.py --date 2026-09-07 --mode eod
```

`live` 必须在 Asia/Shanghai 09:15 前启动，并持续运行到 09:30:05。重点池、完整 Auction Packet 和 ChatGPT 用 compact Packet 写入 `data/auction_watchlists/`、`data/auction_packets/`；compact 文件名为 `YYYY-MM-DD_compact.json`，包含客观市场环境、昨日主线验证、板块/个股竞价排名、四类异常放量、弱转强/强转弱候选和 09:30-10:00 待验证条件。原始过程、checkpoint 和日汇总写入 `data/facts/` Parquet，采集批次、逐股观测、fallback 与质量门记录复用 `data/a_share_review.db` 现有审计表。KlineShare fallback 保持禁用，TickDB 仅作观察源。

## Dashboard

```powershell
python -m streamlit run app.py
```

默认地址为 [http://localhost:8501](http://localhost:8501)。Dashboard 只读取正式真实快照，不提供真实/模拟切换。

## PDF

```powershell
python generate_daily_pdf.py --date 2026-09-01 --output reports/2026-09-01-a-share-review.pdf
```

PDF 只从 `PASSED` 快照生成。没有正式快照时命令退出 `3`，不会生成空 PDF。

## Inflection Scanner

趋势拐点扫描器基于全市场日线事实数据计算基本面变化、量价异常、日 K / 周 K 结构和筹码代理变量。评分只累加实际可用项，不对缺失项补零，也不按可用分数重新缩放到 100 分。

```powershell
python scripts/run_inflection_scanner.py --date 2026-09-04
python scripts/run_inflection_scanner.py --date 2026-09-04 --limit 50 --no-fetch
python scripts/run_inflection_backtest.py --start 2026-08-01 --end 2026-09-04
```

`--no-fetch` 只读取本地 FactStore，适合离线重放和测试。完整结果写入 `data/inflection/YYYY-MM-DD.json`，给 ChatGPT 使用的精简结果写入 `data/inflection/YYYY-MM-DD_compact.json`，历史回放结果写入 `data/inflection/backtests/`。

## 测试

离线测试：

```powershell
python -m pytest -m "not real_data" -q
```

真实数据测试：

```powershell
python -m pytest tests/e2e/test_historical_real_day.py -m real_data -q
```

视觉 QA：

```powershell
python tools/visual_qa_dashboard.py
python tools/visual_qa_pdf.py reports/2026-09-01-a-share-review.pdf
```

有本地 Node Playwright 依赖时也可以运行 `node tools/visual_qa_dashboard.js`；两版脚本都支持通过 `DASHBOARD_URL` 指定非默认端口。

## GitHub 同步

GitHub `main` 是本项目唯一正式验收版本。每个明确开发阶段完成后，收尾流程固定为：运行相关测试，更新 `CHECKPOINT.md`，检查敏感文件和临时文件，选择性 `git add`，使用清晰 commit message 提交，`git fetch origin` 后推送到 `origin/main` 并确认本地 HEAD 与远端一致。

禁止为同步使用 `git add .`、自动提交半成品、提交 `.env` / token / 本地数据库 / raw cache / 临时输出，除非文件明确属于版本化资源。禁止 `force push`，远端有新提交时先 rebase 并重新测试。

每日 18:30 兜底同步只负责推送已经 commit 但尚未 push 的 `main` 提交，不会自动 add、commit、pull、rebase 或修改业务数据：

```powershell
python tools/git_sync_check.py
scripts\run_git_sync_check.ps1
```

状态返回码：

- `0`：已同步、无需操作或 push 成功
- `1`：工作区存在未提交修改，未自动同步
- `2`：远端领先，未自动 pull
- `3`：本地与远端分叉，未自动处理
- `4`：push 失败
- `5`：Git 命令或仓库校验错误

Windows Task Scheduler 建议配置：

- 任务名称：`A股项目 GitHub 兜底同步`
- 触发器：每日 `18:30`
- 时区：Windows 本地北京时间 / Asia Shanghai
- 操作：启动 PowerShell
- 参数：`-NoProfile -ExecutionPolicy Bypass -File "D:\桌面\新建文件夹\a_share_daily_review_codex-sync\scripts\run_git_sync_check.ps1"`
- 运行方式：仅在当前用户登录时运行，或按本机凭据策略选择合适方式

同步日志写入 `logs/git_sync/YYYY-MM-DD.log`，只记录时间、分支、本地 HEAD、远端 main、工作区是否干净、同步状态和 push 结果。

## 2026-09-02 公开数据复盘

当前环境未配置 `TUSHARE_TOKEN`，因此 2026-09-02 不能生成正式 `PASSED` 快照。已生成一份公开网页交叉核验复盘，明确标注为 `DRAFT_ONLY`：

- `reports/market_reviews/2026-09-02-a-share-public-data-review.md`
- `reports/market_reviews/2026-09-02-a-share-public-data-review.pdf`
- `data/market_reviews/2026-09-02/public_review_payload.json`

## 设计文档

- `docs/superpowers/specs/2026-09-02-real-market-data-pipeline-design.md`
- `docs/superpowers/plans/2026-09-02-real-market-data-pipeline-implementation.md`
