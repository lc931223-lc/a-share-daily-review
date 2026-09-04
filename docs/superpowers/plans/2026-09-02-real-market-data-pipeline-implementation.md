# A股复盘真实数据链路实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立以 Tushare 为主源、多个公开来源补齐、严格门禁控制且只输出真实数据的每日 A 股复盘链路。

**Architecture:** 采集适配器先把每次响应归档为不可变原始批次，标准化服务再生成统一行情、涨跌停、题材和证据记录。质量门禁在分析前运行，只有 `PASSED` 快照能进入正式数据库、Dashboard 和 PDF；东方财富仅在约定补充字段中降级使用并强制披露。

**Tech Stack:** Python 3.12、Tushare、requests、Pydantic 2、SQLAlchemy 2、SQLite、pandas、Streamlit、ReportLab、pytest、Playwright。

**规格依据：** `docs/superpowers/specs/2026-09-02-real-market-data-pipeline-design.md`

---

## 文件结构

新增文件按责任拆分：

- `src/config/runtime.py`：只负责环境变量和版本化数据门禁配置。
- `src/domain/market_data.py`：标准行情、来源、批次和门禁领域类型。
- `src/adapters/http.py`：统一超时、重试和脱敏错误。
- `src/adapters/tushare_market.py`：Tushare 核心行情适配器。
- `src/adapters/tencent_market.py`：腾讯盘中与收盘补充适配器。
- `src/adapters/ths_market.py`：同花顺涨跌停和题材补充适配器。
- `src/adapters/eastmoney_fallback.py`：受字段白名单限制的东方财富降级适配器。
- `src/adapters/cninfo_disclosure.py`：巨潮公告适配器。
- `src/services/raw_archive_service.py`：原始响应内容寻址归档。
- `src/services/normalization_service.py`：代码、日期、单位和跨源记录标准化。
- `src/services/quality_gate.py`：硬门禁、增强数据缺口和置信度计算。
- `src/services/market_pipeline.py`：单交易日采集编排、降级和事务边界。
- `src/core/sentiment.py`：市场情绪阶段与温度。
- `src/core/theme_cycle.py`：动态题材强度和周期。
- `src/core/stock_role.py`：动态个股地位。
- `src/core/circuit_breaker.py`：交易纪律熔断。
- `src/services/review_builder.py`：把分析结果构造成现有 `DailyReview` 契约。
- `src/reports/pdf_report.py`：从正式分析快照生成中文 PDF。
- `collect_daily_review.py`：真实数据全链路 CLI。
- `generate_daily_pdf.py`：正式 PDF CLI。

现有 `src/storage/models.py`、`sql/schema.sql`、查询和 Streamlit 页面继续沿用，不另建第二套应用。

## Task 1：固定生产配置、凭据和真实数据模式

**Files:**

- Create: `.env.example`
- Create: `config/data_pipeline.json`
- Create: `src/config/__init__.py`
- Create: `src/config/runtime.py`
- Modify: `src/domain/constants.py`
- Modify: `src/validation/review_models.py`
- Test: `tests/unit/test_runtime_config.py`
- Test: `tests/unit/test_review_validation.py`

- [ ] **Step 1: 写入失败测试，要求凭据不泄漏且生产契约拒绝 demo**

```python
def test_runtime_requires_tushare_token(monkeypatch):
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="TUSHARE_TOKEN"):
        RuntimeSettings.load()


def test_daily_review_rejects_demo():
    payload = valid_review()
    payload["data_kind"] = "demo"
    with pytest.raises(ValidationError, match="data_kind"):
        DailyReview.model_validate(payload)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/unit/test_runtime_config.py tests/unit/test_review_validation.py -q`

Expected: FAIL，因为 `RuntimeSettings` 不存在且 `DailyReview` 仍接受 `demo`。

- [ ] **Step 3: 添加版本化门禁配置和运行时设置**

`config/data_pipeline.json` 的首版内容固定为：

```json
{
  "rule_version": "2026.09.02.1",
  "request_timeout_seconds": 15,
  "max_retries": 2,
  "major_indices": ["000001.SH", "399001.SZ", "399006.SZ", "000688.SH"],
  "thresholds": {
    "security_status_explained": 0.995,
    "daily_quote_required_fields": 0.995,
    "major_index_coverage": 1.0,
    "limit_candidate_coverage": 0.98,
    "supplemental_abs_diff": 2,
    "supplemental_ratio_diff": 0.02,
    "critical_conflicts": 0
  },
  "eastmoney_fallback_fields": [
    "advancers", "decliners", "limit_up", "limit_down",
    "failed_limit", "board_height", "theme_name", "theme_membership"
  ]
}
```

`RuntimeSettings.load()` 使用 `dotenv.load_dotenv()`，要求非空 `TUSHARE_TOKEN`，并只在对象中保存密钥；`safe_dict()` 返回配置时必须排除 token。

- [ ] **Step 4: 收紧生产数据契约**

把 `DataKind` 改为仅包含 `REAL = "real"`，把 `DailyReview.schema_version` 提升为 `2.0`，并把 `data_kind` 固定为 `Literal["real"]`。测试夹具仍可构造内存对象，但不能通过正式导入契约写入 demo。

- [ ] **Step 5: 验证并提交**

Run: `python -m pytest tests/unit/test_runtime_config.py tests/unit/test_review_validation.py -q`

Expected: PASS。

Commit: `feat: enforce real-data runtime configuration`

## Task 2：建立来源、原始批次和质量审计模型

**Files:**

- Create: `src/domain/market_data.py`
- Modify: `src/storage/models.py`
- Modify: `sql/schema.sql`
- Create: `scripts/migrate_real_pipeline.py`
- Modify: `tests/integration/test_database_schema.py`
- Create: `tests/integration/test_real_pipeline_migration.py`

- [ ] **Step 1: 写入模型和迁移失败测试**

```python
REQUIRED_PIPELINE_TABLES = {
    "source_batch", "source_observation", "quality_gate_run",
    "quality_gate_check", "source_fallback", "analysis_snapshot",
}


def test_pipeline_tables_exist(tmp_path):
    engine = create_db_engine(tmp_path / "pipeline.db")
    create_schema(engine)
    assert REQUIRED_PIPELINE_TABLES <= set(inspect(engine).get_table_names())


def test_migration_removes_demo_rows_after_backup(tmp_path):
    db = build_legacy_database_with_demo_and_real(tmp_path)
    backup = migrate_database(db)
    assert backup.exists()
    assert count_rows(db, "trading_day", "data_kind = 'demo'") == 0
    assert count_rows(db, "trading_day", "data_kind = 'real'") == 1
```

- [ ] **Step 2: 运行测试并确认缺表失败**

Run: `python -m pytest tests/integration/test_database_schema.py tests/integration/test_real_pipeline_migration.py -q`

Expected: FAIL，列出六张新表不存在。

- [ ] **Step 3: 添加统一领域类型**

`src/domain/market_data.py` 定义 `SourceName`、`BatchStatus`、`GateStatus`、`ReportStatus` 枚举，以及以下不可变模型：

```python
class SourceRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    source: SourceName
    dataset: str
    trade_date: date
    fetched_at: datetime
    payload: list[dict[str, Any]]
    is_fallback: bool = False
    fallback_reason: str | None = None


class GateDecision(BaseModel):
    status: GateStatus
    rule_version: str
    checks: tuple[GateCheck, ...]
    confidence: int = Field(ge=0, le=100)
```

- [ ] **Step 4: 添加六张审计表并同步 SQL**

`SourceBatch` 保存来源、数据集、目标日期、抓取时间、SHA256、归档路径、记录数、状态和错误类别；`SourceObservation` 保存标准化实体键、字段、值、单位和冲突状态；`QualityGateRun` 与 `QualityGateCheck` 保存规则版本和每项门禁；`SourceFallback` 保存主源、降级源、原因、字段和交叉验证状态；`AnalysisSnapshot` 保存正式状态、规则版本、数据版本、置信度和 JSON 结果。

- [ ] **Step 5: 编写备份优先迁移脚本**

`migrate_database(path)` 先复制为 `<name>.pre-real-pipeline-<UTC时间>.bak`，再创建新表并在事务中删除 `data_kind='demo'` 的业务树。脚本只删除 demo 关联记录，不删除原始真实记录。

- [ ] **Step 6: 验证并提交**

Run: `python -m pytest tests/integration/test_database_schema.py tests/integration/test_real_pipeline_migration.py -q`

Expected: PASS。

Commit: `feat: add auditable source and quality schema`

## Task 3：实现不可变原始归档和统一 HTTP 失败语义

**Files:**

- Create: `src/adapters/http.py`
- Create: `src/services/raw_archive_service.py`
- Modify: `src/adapters/base.py`
- Test: `tests/unit/test_http_client.py`
- Test: `tests/unit/test_raw_archive_service.py`

- [ ] **Step 1: 写入归档、重试和脱敏测试**

```python
def test_archive_is_content_addressed(tmp_path):
    result = archive_raw(b'{"ok":true}', "tushare", "daily", date(2026, 9, 1), tmp_path)
    assert result.path.read_bytes() == b'{"ok":true}'
    assert result.sha256 in result.path.name


def test_http_error_redacts_credentials(fake_session):
    client = SafeHttpClient(fake_session, timeout=1, max_retries=0)
    with pytest.raises(AdapterError) as error:
        client.get("https://example.invalid", params={"token": "secret-value"})
    assert "secret-value" not in str(error.value)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/unit/test_http_client.py tests/unit/test_raw_archive_service.py -q`

Expected: FAIL，因为归档器和安全客户端尚不存在。

- [ ] **Step 3: 实现内容寻址归档**

归档路径固定为 `data/raw/<source>/<trade_date>/<dataset>/<sha256>.json`。若内容已存在则返回同一路径，不重复写入。先写临时文件，再用原子替换完成落盘。

- [ ] **Step 4: 实现有限重试和错误分类**

`SafeHttpClient` 只重试超时、连接失败、HTTP 429 和 5xx；最多使用配置的两次重试。400、401、403 和字段解析错误立即失败。错误对象只包含来源、数据集、状态码和错误分类，不包含请求头、token 或完整 URL 查询参数。

- [ ] **Step 5: 验证并提交**

Run: `python -m pytest tests/unit/test_http_client.py tests/unit/test_raw_archive_service.py -q`

Expected: PASS。

Commit: `feat: archive immutable raw source batches`

## Task 4：实现 Tushare 核心行情适配器

**Files:**

- Create: `src/adapters/tushare_market.py`
- Create: `tests/fixtures/tushare/trade_cal.json`
- Create: `tests/fixtures/tushare/stock_basic.json`
- Create: `tests/fixtures/tushare/daily.json`
- Create: `tests/fixtures/tushare/index_daily.json`
- Create: `tests/fixtures/tushare/adj_factor.json`
- Test: `tests/unit/test_tushare_market.py`

- [ ] **Step 1: 写入使用固定真实结构快照的失败测试**

```python
def test_tushare_daily_uses_ts_code_and_trade_date(adapter):
    rows = adapter.stock_daily(date(2026, 9, 1))
    assert rows
    assert set(rows[0]) >= {"ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"}
    assert rows[0]["ts_code"].endswith((".SH", ".SZ", ".BJ"))


def test_tushare_rejects_wrong_date(adapter):
    adapter.pro.daily.return_value = frame_with_trade_date("20260831")
    with pytest.raises(AdapterDataError, match="交易日期"):
        adapter.stock_daily(date(2026, 9, 1))
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/unit/test_tushare_market.py -q`

Expected: FAIL，因为 `TushareMarketAdapter` 不存在。

- [ ] **Step 3: 实现五个核心数据集**

适配器通过注入的 `pro` 客户端调用 `trade_cal`、`stock_basic`、`daily`、`index_daily` 和 `adj_factor`。每个方法返回 `SourceRecord`，严格校验请求日期、必需列、重复 `ts_code` 和空响应。生产构造函数使用 `ts.pro_api(settings.tushare_token)`；测试只注入假客户端，不访问网络。

- [ ] **Step 4: 增加 Tushare 权限诊断**

权限不足转换为 `AdapterPermissionError(dataset=...)`，流水线据此生成失败门禁；不得改用东方财富替代核心数据。

- [ ] **Step 5: 验证并提交**

Run: `python -m pytest tests/unit/test_tushare_market.py -q`

Expected: PASS。

Commit: `feat: collect core market data from tushare`

## Task 5：实现补充来源和东方财富白名单降级

**Files:**

- Create: `src/adapters/tencent_market.py`
- Create: `src/adapters/ths_market.py`
- Create: `src/adapters/eastmoney_fallback.py`
- Create: `src/adapters/cninfo_disclosure.py`
- Create: `tests/fixtures/supplemental/tencent_quotes.txt`
- Create: `tests/fixtures/supplemental/ths_limit_pool.json`
- Create: `tests/fixtures/supplemental/eastmoney_breadth.json`
- Create: `tests/fixtures/supplemental/cninfo_announcements.json`
- Test: `tests/unit/test_supplemental_adapters.py`

- [ ] **Step 1: 写入来源边界失败测试**

```python
def test_eastmoney_rejects_core_dataset(adapter):
    with pytest.raises(FallbackScopeError):
        adapter.fetch("stock_daily", date(2026, 9, 1))


@pytest.mark.parametrize("dataset", ["market_breadth", "limit_pool", "failed_limit", "theme_membership"])
def test_eastmoney_allows_only_whitelisted_supplements(adapter, dataset):
    assert adapter.fetch(dataset, date(2026, 9, 1)).is_fallback is True


def test_cninfo_keeps_official_url(adapter):
    announcement = adapter.announcements(date(2026, 9, 1)).payload[0]
    assert announcement["source_url"].startswith("https://")
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/unit/test_supplemental_adapters.py -q`

Expected: FAIL，因为补充适配器不存在。

- [ ] **Step 3: 实现腾讯、同花顺和巨潮适配器**

腾讯适配器输出代码、名称、现价、昨收、成交额和时间戳；同花顺适配器输出涨停、跌停、炸板、连板高度、题材名称和题材成员；巨潮适配器输出公告代码、标题、发布时间、官方 URL 和摘要。字段缺失时抛出 `AdapterSchemaError`，不得返回部分伪完整记录。

- [ ] **Step 4: 实现东方财富字段白名单**

`EastmoneyFallbackAdapter.fetch()` 首先用配置中的 `eastmoney_fallback_fields` 校验请求数据集映射；`stock_daily`、`trade_calendar`、`index_daily`、`adj_factor`、`financials` 和 `announcements` 必须无条件拒绝。允许结果强制设置 `is_fallback=True` 和非空 `fallback_reason`。

- [ ] **Step 5: 验证并提交**

Run: `python -m pytest tests/unit/test_supplemental_adapters.py -q`

Expected: PASS。

Commit: `feat: add supplemental and scoped fallback sources`

## Task 6：实现标准化、重算和跨源冲突记录

**Files:**

- Create: `src/services/normalization_service.py`
- Create: `src/services/market_calculations.py`
- Test: `tests/unit/test_normalization_service.py`
- Test: `tests/unit/test_market_calculations.py`

- [ ] **Step 1: 写入代码、单位、日期和涨跌停重算测试**

```python
def test_normalize_stock_code():
    assert normalize_ts_code("sh600000") == "600000.SH"
    assert normalize_ts_code("300750") == "300750.SZ"


def test_market_breadth_is_recomputed_from_quotes():
    result = calculate_breadth(quotes([1.2, 0.0, -0.5]))
    assert result.advancers == 1
    assert result.flat == 1
    assert result.decliners == 1


def test_conflicting_supplement_is_preserved():
    resolved = resolve_observations(primary=94, supplement=97, field="limit_up_count")
    assert resolved.selected_value == 94
    assert resolved.conflict is not None
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/unit/test_normalization_service.py tests/unit/test_market_calculations.py -q`

Expected: FAIL，因为标准化和重算函数不存在。

- [ ] **Step 3: 实现标准化和市场重算**

金额统一为亿元，成交量保留股数和原始单位，日期统一为 `date`，时间统一为带时区 `datetime`。涨跌家数和成交额从 Tushare 个股行情重算；涨跌停候选按证券板块、ST 状态、昨收和价格精度计算，再用补充源核验。

- [ ] **Step 4: 实现冲突选择规则**

核心行情永远选 Tushare 值；补充字段按“同花顺/腾讯、东方财富降级”的顺序选择。所有候选值写入 `source_observation`；超过允许差异时标记关键冲突，不静默覆盖。

- [ ] **Step 5: 验证并提交**

Run: `python -m pytest tests/unit/test_normalization_service.py tests/unit/test_market_calculations.py -q`

Expected: PASS。

Commit: `feat: normalize and reconcile market observations`

## Task 7：实现严格质量门禁和置信度

**Files:**

- Create: `src/services/quality_gate.py`
- Test: `tests/unit/test_quality_gate.py`

- [ ] **Step 1: 写入三种门禁结果测试**

```python
def test_complete_close_snapshot_passes(complete_snapshot, config):
    decision = QualityGate(config).evaluate(complete_snapshot, report_mode="close")
    assert decision.status == GateStatus.PASSED


def test_missing_core_daily_data_fails(incomplete_snapshot, config):
    incomplete_snapshot.daily_required_coverage = 0.98
    decision = QualityGate(config).evaluate(incomplete_snapshot, report_mode="close")
    assert decision.status == GateStatus.FAILED
    assert "daily_quote_required_fields" in failed_check_names(decision)


def test_intraday_snapshot_is_draft_only(complete_snapshot, config):
    decision = QualityGate(config).evaluate(complete_snapshot, report_mode="intraday")
    assert decision.status == GateStatus.DRAFT_ONLY
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/unit/test_quality_gate.py -q`

Expected: FAIL，因为 `QualityGate` 不存在。

- [ ] **Step 3: 实现七项硬门禁**

逐项计算交易日一致性、证券状态可解释率、个股关键字段完整率、指数覆盖率、涨跌停候选覆盖率、补充源差异和关键冲突数。每项 `GateCheck` 保存实际值、阈值、通过状态和中文原因。

- [ ] **Step 4: 实现增强数据降置信度**

公告、龙虎榜、资金流或催化缺失不改变 `PASSED`，但按配置扣减对应模块置信度。硬门禁任一失败则 `FAILED`；盘中模式固定为 `DRAFT_ONLY`，不能升级为正式状态。

- [ ] **Step 5: 验证并提交**

Run: `python -m pytest tests/unit/test_quality_gate.py -q`

Expected: PASS。

Commit: `feat: enforce strict market data quality gate`

## Task 8：编排真实数据采集、降级和事务写入

**Files:**

- Create: `src/services/market_pipeline.py`
- Create: `collect_daily_review.py`
- Test: `tests/integration/test_market_pipeline.py`
- Test: `tests/integration/test_collect_daily_review_cli.py`

- [ ] **Step 1: 写入编排和禁止静默降级测试**

```python
def test_pipeline_uses_eastmoney_only_after_supplement_failure(pipeline):
    pipeline.ths.limit_pool.side_effect = AdapterTimeout("ths", "limit_pool")
    result = pipeline.collect(date(2026, 9, 1), mode="close")
    assert result.fallbacks[0].fallback_source == "eastmoney"
    assert result.fallbacks[0].fields == ["limit_up", "limit_down", "failed_limit"]


def test_pipeline_never_falls_back_for_tushare_daily(pipeline):
    pipeline.tushare.stock_daily.side_effect = AdapterPermissionError("daily")
    result = pipeline.collect(date(2026, 9, 1), mode="close")
    assert result.gate.status == GateStatus.FAILED
    pipeline.eastmoney.fetch.assert_not_called()
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/integration/test_market_pipeline.py tests/integration/test_collect_daily_review_cli.py -q`

Expected: FAIL，因为编排服务和 CLI 不存在。

- [ ] **Step 3: 实现按序采集和审计写入**

`MarketPipeline.collect()` 按交易日历、基础证券、个股日线、指数、复权因子、补充情绪和公告顺序执行。每次调用都先归档原始响应，再写 `source_batch`。补充源失败时仅对允许字段调用东方财富，并写 `source_fallback`。

- [ ] **Step 4: 实现门禁前后事务边界**

原始批次和失败审计允许独立提交；标准化正式业务数据、门禁记录和分析快照必须在同一事务中写入。门禁失败时不创建正式 `TradingDay`，只保存质量记录。

- [ ] **Step 5: 实现 CLI**

命令接口固定为：

```powershell
python collect_daily_review.py --date 2026-09-01 --mode close
python collect_daily_review.py --date 2026-09-01 --mode intraday
```

退出码：`0` 表示 `PASSED`，`2` 表示 `DRAFT_ONLY`，`3` 表示 `FAILED`，`1` 表示程序错误。输出只含批次 ID、门禁状态、缺失项和安全配置摘要。

- [ ] **Step 6: 验证并提交**

Run: `python -m pytest tests/integration/test_market_pipeline.py tests/integration/test_collect_daily_review_cli.py -q`

Expected: PASS。

Commit: `feat: orchestrate audited real-data collection`

## Task 9：实现动态情绪、题材、个股地位和熔断分析

**Files:**

- Create: `src/core/sentiment.py`
- Create: `src/core/theme_cycle.py`
- Create: `src/core/stock_role.py`
- Create: `src/core/circuit_breaker.py`
- Create: `src/services/review_builder.py`
- Test: `tests/unit/test_sentiment_analysis.py`
- Test: `tests/unit/test_theme_cycle.py`
- Test: `tests/unit/test_stock_role.py`
- Test: `tests/unit/test_circuit_breaker.py`
- Test: `tests/integration/test_review_builder.py`

- [ ] **Step 1: 写入动态名称和可解释结论测试**

```python
def test_analysis_contains_only_observed_themes(snapshot):
    result = build_review(snapshot)
    observed = set(snapshot.theme_memberships)
    assert {theme.name for theme in result.main_themes} <= observed


def test_stock_role_requires_evidence(snapshot):
    result = classify_stock(snapshot.stock("600001.SH"), snapshot)
    assert result.role in {"龙头", "容量中军", "低位补涨", "中位股", "孤立票", "风险票"}
    assert result.reasons


def test_unobserved_examples_never_appear(snapshot):
    rendered = build_review(snapshot).model_dump_json()
    assert "AI算力" not in rendered
    assert "中际旭创" not in rendered
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/unit/test_sentiment_analysis.py tests/unit/test_theme_cycle.py tests/unit/test_stock_role.py tests/unit/test_circuit_breaker.py tests/integration/test_review_builder.py -q`

Expected: FAIL，因为四个分析器和构建器不存在。

- [ ] **Step 3: 实现市场情绪和纪律熔断**

市场情绪以市场宽度、成交额变化、涨跌停比、炸板率、晋级率、最高板、昨日涨停反馈和指数强弱生成 0—100 温度，并映射冰点、修复、主升、分歧、退潮。每个指标保存贡献和冲突。门禁失败直接触发禁止开仓；退潮、连续亏损和回撤阈值按规则输出降低仓位或暂停交易。

- [ ] **Step 4: 实现题材周期和个股地位**

题材强度只从标准化题材成员、涨停分布、成交额、扩散度、持续天数和公告证据计算。无可靠归因的题材进入观察集合，不进入前三主线。个股地位根据题材贡献、连板辨识度、成交容量、主动性、带动性和封板质量分类，并输出指标依据。

- [ ] **Step 5: 构建 `DailyReview 2.0`**

`ReviewBuilder` 只接受 `GateStatus.PASSED`；其他状态抛出 `FormalReviewBlocked`。构建结果中的所有题材名和股票代码必须能在快照的来源观察表中找到。

- [ ] **Step 6: 验证并提交**

Run: `python -m pytest tests/unit/test_sentiment_analysis.py tests/unit/test_theme_cycle.py tests/unit/test_stock_role.py tests/unit/test_circuit_breaker.py tests/integration/test_review_builder.py -q`

Expected: PASS。

Commit: `feat: derive explainable review conclusions from observed data`

## Task 10：移除生产演示数据并更新导入和查询

**Files:**

- Delete: `data/json/demo/*.json`
- Delete: `scripts/seed_demo_data.py`
- Create: `tests/fixtures/reviews/market_alpha_complete.json`
- Modify: `src/services/import_service.py`
- Modify: `src/queries/dashboard_queries.py`
- Modify: `src/queries/theme_queries.py`
- Modify: `src/queries/stock_queries.py`
- Modify: `src/queries/evidence_queries.py`
- Modify: `tests/integration/test_import_daily_review.py`
- Modify: `tests/integration/test_queries.py`
- Delete: `tests/integration/test_seed_data.py`

- [ ] **Step 1: 把演示依赖改成中性测试夹具**

测试夹具使用“主题甲”和 `600001` 等中性实体，只放在 `tests/fixtures`。测试不得从 `data/json/demo` 或生产种子脚本读取。

- [ ] **Step 2: 写入生产查询只返回正式快照的失败测试**

```python
def test_dashboard_lists_only_passed_real_days(session):
    seed_day(session, "2026-09-01", data_kind="real", report_status="PASSED")
    seed_day(session, "2026-09-02", data_kind="real", report_status="DRAFT_ONLY")
    assert [row.trade_date.isoformat() for row in list_days(session)] == ["2026-09-01"]
```

- [ ] **Step 3: 运行测试并确认失败**

Run: `python -m pytest tests/integration/test_import_daily_review.py tests/integration/test_queries.py -q`

Expected: FAIL，因为查询仍接受 `data_kind` 并可读取 demo。

- [ ] **Step 4: 删除生产 demo 路径并收紧查询**

移除查询函数的 `data_kind` 参数，统一连接 `AnalysisSnapshot` 并只返回 `status='PASSED'` 的真实交易日。导入服务拒绝 schema 1.0 和非 real 数据。迁移脚本负责清理现有数据库中的 demo 记录。

- [ ] **Step 5: 验证并提交**

Run: `python -m pytest tests/integration/test_import_daily_review.py tests/integration/test_queries.py -q`

Expected: PASS。

Commit: `refactor: remove demo data from production paths`

## Task 11：改造密集工作台的数据质量和动态分析页面

**Files:**

- Modify: `src/ui/layout.py`
- Modify: `src/ui/styles.py`
- Modify: `app.py`
- Modify: `pages/1_主线详情.py`
- Modify: `pages/2_核心个股.py`
- Modify: `pages/3_上涨驱动力.py`
- Modify: `pages/4_生命周期统计.py`
- Modify: `pages/5_证据中心.py`
- Create: `pages/6_数据质量.py`
- Modify: `tests/ui/test_dashboard_home.py`
- Modify: `tests/ui/test_dashboard_pages.py`

- [ ] **Step 1: 写入不再出现模拟切换和示例名称的 UI 测试**

```python
def test_dashboard_has_only_real_formal_data(app):
    assert not any(control.label == "数据类型" for control in app.selectbox)
    assert "模拟演示数据" not in rendered_text(app)
    assert "数据质量" in rendered_text(app)


def test_quality_page_discloses_fallback(quality_app):
    assert "东方财富降级" in rendered_text(quality_app)
    assert "使用原因" in rendered_text(quality_app)
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/ui/test_dashboard_home.py tests/ui/test_dashboard_pages.py -q`

Expected: FAIL，因为界面仍显示真实/模拟切换且没有数据质量页。

- [ ] **Step 3: 更新首页和分析页面**

移除 `choose_data_kind()`。首页顶部展示交易日期、`PASSED` 状态、抓取时间、门禁规则版本、置信度和仓位纪律；指标区增加情绪温度、阶段、炸板率和晋级率。题材和个股页面使用动态结果及理由，不提供固定默认股票代码。

- [ ] **Step 4: 添加数据质量页面**

页面表格展示来源、数据集、覆盖率、抓取时间、状态、降级原因和交叉验证状态。门禁检查逐项展示实际值、阈值和结果；东方财富降级使用醒目标记，但保持密集工作台信息层级。

- [ ] **Step 5: 验证并提交**

Run: `python -m pytest tests/ui/test_dashboard_home.py tests/ui/test_dashboard_pages.py -q`

Expected: PASS。

Commit: `feat: show formal real-data quality in dashboard`

## Task 12：从正式快照生成思源黑体 PDF

**Files:**

- Create: `src/reports/__init__.py`
- Create: `src/reports/pdf_report.py`
- Create: `generate_daily_pdf.py`
- Test: `tests/integration/test_pdf_report.py`

- [ ] **Step 1: 写入门禁、字体和正文颜色测试**

```python
def test_pdf_requires_passed_snapshot(tmp_path, draft_snapshot):
    with pytest.raises(FormalReportBlocked):
        generate_pdf(draft_snapshot, tmp_path / "draft.pdf")


def test_pdf_embeds_source_han_and_black_body(tmp_path, passed_snapshot):
    output = generate_pdf(passed_snapshot, tmp_path / "report.pdf")
    reader = PdfReader(output)
    assert len(reader.pages) >= 1
    assert "SourceHanSans" in embedded_font_names(reader)
    assert extract_text(output).find("数据质量") >= 0
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/integration/test_pdf_report.py -q`

Expected: FAIL，因为正式快照 PDF 生成器不存在。

- [ ] **Step 3: 实现统一 PDF 生成器**

使用 `assets/fonts/SourceHanSansCN-Regular.ttf`、`Medium.ttf` 和 `Bold.ttf` 注册 ReportLab 字体。A4 正文默认 12pt、行距 17pt，表格正文不低于 9.5pt，正文颜色固定 `#000000`。内容依次为市场结论、核心指标、题材周期、个股地位、次日条件和数据质量。

- [ ] **Step 4: 实现 PDF CLI**

```powershell
python generate_daily_pdf.py --date 2026-09-01 --output reports/2026-09-01-a-share-review.pdf
```

CLI 只读取 `PASSED` 快照。不存在正式快照时退出码为 `3`，并提示先运行真实数据采集，不生成空 PDF。

- [ ] **Step 5: 验证并提交**

Run: `python -m pytest tests/integration/test_pdf_report.py -q`

Expected: PASS。

Commit: `feat: generate formal source-han review pdf`

## Task 13：完成真实历史日端到端验证和视觉验收

**Files:**

- Create: `tests/e2e/test_historical_real_day.py`
- Modify: `tools/visual_qa_dashboard.js`
- Create: `tools/visual_qa_pdf.py`
- Modify: `README.md`
- Modify: `CHECKPOINT.md`

- [ ] **Step 1: 添加凭据保护的真实端到端测试**

```python
@pytest.mark.real_data
def test_historical_day_end_to_end(tmp_path):
    settings = RuntimeSettings.load()
    result = build_pipeline(settings, database_path=tmp_path / "real.db").collect(
        date(2026, 9, 1), mode="close"
    )
    assert result.gate.status == GateStatus.PASSED
    assert result.snapshot.status == ReportStatus.PASSED
    assert result.snapshot.source_batches
```

没有 `TUSHARE_TOKEN` 时该测试明确跳过并说明原因；正式验收时不允许以跳过状态结项。

- [ ] **Step 2: 运行全部离线测试**

Run: `python -m pytest -m "not real_data" -q`

Expected: 所有测试 PASS，且没有网络请求。

- [ ] **Step 3: 配置本地凭据并运行真实数据测试**

在未纳入 Git 的 `.env` 中设置 `TUSHARE_TOKEN`，然后运行：

```powershell
python -m pytest tests/e2e/test_historical_real_day.py -m real_data -q
python collect_daily_review.py --date 2026-09-01 --mode close
python generate_daily_pdf.py --date 2026-09-01 --output reports/2026-09-01-a-share-review.pdf
```

Expected: 门禁 `PASSED`；生成正式快照和 PDF。若 Tushare 权限不足，必须输出受影响数据集并停止正式验收，不得换用模拟数据。

- [ ] **Step 4: 完成 Dashboard 视觉验收**

启动 `python -m streamlit run app.py`，再运行 `node tools/visual_qa_dashboard.js`。检查 1440×900 和 390×844：无横向溢出、无异常堆栈、动态题材可见、数据质量状态可见。

- [ ] **Step 5: 完成 PDF 渲染验收**

`tools/visual_qa_pdf.py` 使用 Poppler 将全部页面渲染为 PNG，检查嵌入字体、页面数量、黑色正文、表格越界和空白页。人工抽查首页、题材页和数据质量页。

- [ ] **Step 6: 更新文档并提交**

README 只保留真实数据安装、凭据、采集、门禁、Dashboard 和 PDF 命令；删除模拟数据初始化说明。CHECKPOINT 记录真实交易日、批次 ID、门禁状态、测试数量、PDF 路径和已知权限限制。

Run: `git diff --check && git status --short`

Expected: 无空白错误，只包含预期文档和验收产物。

Commit: `docs: verify real-data daily review workflow`

## 最终验收命令

```powershell
python -m pytest -m "not real_data" -q
python -m pytest tests/e2e/test_historical_real_day.py -m real_data -q
python collect_daily_review.py --date 2026-09-01 --mode close
python generate_daily_pdf.py --date 2026-09-01 --output reports/2026-09-01-a-share-review.pdf
node tools/visual_qa_dashboard.js
python tools/visual_qa_pdf.py reports/2026-09-01-a-share-review.pdf
git diff --check
git status --short
```

验收必须同时满足：生产数据库不存在 demo 记录；门禁通过；题材和个股来自目标日来源观察；东方财富只用于白名单字段且被披露；Dashboard 与 PDF 使用相同正式快照；思源黑体嵌入且正文为黑色。
