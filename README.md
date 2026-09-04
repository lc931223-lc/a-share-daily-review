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

当前 Market Packet 会优先用 Tushare `daily(trade_date=...)` 补齐全市场涨跌家数、总成交额、上一交易日成交额和股票池目标日 OHLCV；没有 `TUSHARE_TOKEN` 或 `daily` 不可用时，股票池 OHLCV 继续顺序尝试 `akshare.stock_zh_a_hist`、`akshare.stock_zh_a_hist_tx`、`akshare.stock_zh_a_daily`。政策和公告仍需要独立数据源。

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

默认使用 SQLite：`data/a_share_review.db`。原因是当前系统是本地单机数据包生成、official review 入库和 Streamlit Dashboard 展示，SQLite 的事务、唯一约束和零服务部署更适合 Phase 1；后续如果多人并发或云端长期服务化，再迁移 DuckDB/PostgreSQL。

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

## 2026-09-02 公开数据复盘

当前环境未配置 `TUSHARE_TOKEN`，因此 2026-09-02 不能生成正式 `PASSED` 快照。已生成一份公开网页交叉核验复盘，明确标注为 `DRAFT_ONLY`：

- `reports/market_reviews/2026-09-02-a-share-public-data-review.md`
- `reports/market_reviews/2026-09-02-a-share-public-data-review.pdf`
- `data/market_reviews/2026-09-02/public_review_payload.json`

## 设计文档

- `docs/superpowers/specs/2026-09-02-real-market-data-pipeline-design.md`
- `docs/superpowers/plans/2026-09-02-real-market-data-pipeline-implementation.md`
