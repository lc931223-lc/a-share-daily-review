# A股复盘系统第一阶段实施计划

**规格依据：** `docs/superpowers/specs/2026-09-01-phase1-database-dashboard-design.md`

**目标：** 在远端同源 Git 工作区中完成 SQLAlchemy 数据库、Pydantic/JSON Schema 契约、原子导入器、10 日演示数据、2026-09-01 真实严格记录、历史查询服务和 Streamlit 中文密集工作台，并通过自动化测试与视觉验收。

**工作方法：** 每项任务先写失败测试，再做最小实现，运行该任务的定向测试，最后运行累计测试。每个提交只包含一个清晰主题。现有 41 项上涨驱动力和 100 分评分规则不可修改。

## 任务 1：建立远端同源工作区与环境基线

**涉及文件：**

- 远端：`lc931223-lc/a-share-daily-review` 的 `codex/phase1-dashboard` 分支
- 保留并迁移：`docs/superpowers/specs/2026-09-01-phase1-database-dashboard-design.md`
- 新增：`.gitignore`
- 修改：`requirements.txt`

**步骤：**

1. 浅克隆远端开发分支到新的同级目录，不在当前非 Git 目录中创建独立历史。
2. 比较 README、提示词、评分配置、Schema 和源码；确认远端与当前项目同源后，将已批准规格复制到克隆目录。
3. 配置仓库级 Git 用户：`user.name=愚者`、`user.email=junmo1993@sina.com`。
4. 在 `.gitignore` 中排除 `.env`、虚拟环境、缓存、SQLite 运行库、归档临时文件和 `.superpowers/` 原型文件，但保留演示 JSON。
5. 在 `requirements.txt` 增加 `streamlit`、`pytest`、`jsonschema`，不引入 Alembic 或额外前端框架。
6. 创建虚拟环境并执行 `pip install -r requirements.txt`，记录 Python 与核心包版本。
7. 提交规格和环境基线：`docs: add approved phase 1 design and environment baseline`。

**验证：**

```powershell
python --version
python -c "import pydantic, sqlalchemy, streamlit, pytest, jsonschema; print('dependencies ok')"
git status --short
```

## 任务 2：固定业务枚举和评分配置读取

**新增文件：**

- `src/domain/constants.py`
- `src/domain/scoring.py`
- `src/domain/__init__.py`
- `tests/unit/test_domain_rules.py`

**修改文件：**

- `src/core/score.py`
- `src/core/lifecycle.py`
- `src/core/classify.py`

**测试先行：**

1. 断言生命周期、评级、证据等级、个股地位、验证状态和 41 项驱动力完整且唯一。
2. 断言分项边界、总分和评级严格读取 `config/scoring.json`。
3. 断言越界输入被拒绝，不再由旧代码静默截断。

**实现：**

1. 把枚举和驱动力集中到领域模块，旧模块改为调用统一定义。
2. 配置读取使用缓存并校验必要键，不复制第二套评分区间。
3. 保持已有公开函数兼容，新增严格校验函数供 Pydantic 使用。

**验证与提交：**

```powershell
pytest tests/unit/test_domain_rules.py -q
```

提交：`refactor: centralize fixed review domain rules`

## 任务 3：实现标准 JSON 的 Pydantic 契约与 JSON Schema

**新增文件：**

- `src/validation/review_models.py`
- `src/validation/schema_sync.py`
- `src/validation/errors.py`
- `src/validation/__init__.py`
- `tests/unit/test_review_validation.py`
- `tests/fixtures/reviews/valid_strict_partial.json`

**修改文件：**

- `schemas/daily_review.schema.json`
- `schemas/stock_review.schema.json`

**测试先行：**

1. 覆盖合法完整记录、合法严格空值、缺失字段、非法评分、非法评级、非法生命周期、非法股票代码和非法驱动力。
2. 覆盖 `null` 缺少 `missing_reasons`、总分公式不一致、评级不匹配和 D 级证据违规支撑强结论。
3. 用相同样例同时运行 Pydantic 与 JSON Schema，保证接受/拒绝结论一致。
4. 断言错误格式包含精确 JSON 路径和值。

**实现：**

1. 建立市场、完整度、评分、题材、股票、证据、风险和次日验证模型。
2. 用模型验证器实现跨字段一致性，不用字符串拼接解析 JSON。
3. 更新两份 JSON Schema，使外部校验契约与运行时模型一致。

**验证与提交：**

```powershell
pytest tests/unit/test_review_validation.py -q
```

提交：`feat: define strict daily review data contract`

## 任务 4：实现 SQLAlchemy 模型和 SQLite 初始化

**新增文件：**

- `src/storage/database.py`
- `src/storage/models.py`
- `src/storage/repositories.py`
- `src/storage/__init__.py`
- `tests/integration/test_database_schema.py`

**修改文件：**

- `sql/schema.sql`

**测试先行：**

1. 在临时 SQLite 中分别执行 SQLAlchemy `create_all` 和 `sql/schema.sql`。
2. 断言两种初始化方式都包含设计规定的表、外键、唯一约束和索引。
3. 断言同日期不同 `data_kind` 可共存，同日期同类型被拒绝。
4. 断言明细必须通过 `trading_day_id` 关联，外键约束开启。
5. 断言评分列允许 `null`，缺失原因可以持久化。

**实现：**

1. 建立 `review_import`、`trading_day`、题材、股票、驱动力、证据、风险、验证和关系模型。
2. 使用 SQLAlchemy 2.x typed declarative 风格和显式 session 工厂。
3. 同步更新 `sql/schema.sql`，不引入迁移框架。

**验证与提交：**

```powershell
pytest tests/integration/test_database_schema.py -q
```

提交：`feat: add auditable review database schema`

## 任务 5：实现归档、题材归一化和原子导入器

**新增文件：**

- `src/services/archive_service.py`
- `src/services/theme_normalizer.py`
- `src/services/comparison_service.py`
- `src/services/import_service.py`
- `src/services/__init__.py`
- `import_daily_review.py`
- `tests/integration/test_import_daily_review.py`

**测试先行：**

1. 覆盖新交易日、新题材、新股票、题材别名和原始 JSON SHA256 归档。
2. 覆盖重复日期与类型、未知别名、非法输入和精确错误输出。
3. 人为制造子表写入失败，断言业务事务全部回滚且审计记录为失败。
4. 覆盖评分上涨、下降、首次出现、暂不评分和证伪的 `delta_score/delta_reason`。
5. 断言前日比较只在相同 `data_kind` 中进行。

**实现：**

1. 先完成内容寻址归档，再建立审计记录和执行校验。
2. 别名只使用显式映射；未知名称创建新标准题材，不自动猜测。
3. 使用一个业务事务写入整日数据，并以非零退出码报告失败。
4. CLI 输出导入日期、类型、表记录数、归档摘要和失败路径。

**验证与提交：**

```powershell
pytest tests/integration/test_import_daily_review.py -q
python import_daily_review.py tests/fixtures/reviews/valid_strict_partial.json --database data/test-import.db
```

提交：`feat: import daily reviews transactionally`

## 任务 6：实现次日验证闭环

**新增文件：**

- `src/services/tomorrow_check_service.py`
- `tests/integration/test_tomorrow_checks.py`

**修改文件：**

- `src/services/import_service.py`

**测试先行：**

1. 导入首日后验证条件为 `pending`。
2. 次日 JSON 可把历史条件更新为 `confirmed`、`weakened` 或 `invalidated`。
3. 非法状态、错误实体和重复解决被拒绝。
4. 更新保留原提出日和原描述，并记录解决日与结果。

**实现与验证：**

```powershell
pytest tests/integration/test_tomorrow_checks.py -q
```

提交：`feat: close the loop on tomorrow checks`

## 任务 7：生成 10 日演示数据和 9 月 1 日真实严格记录

**新增文件：**

- `scripts/seed_demo_data.py`
- `data/json/demo/*.json`
- `data/json/2026-09-01.json`
- `tests/integration/test_seed_data.py`

**测试先行：**

1. 断言脚本生成并导入恰好 10 个 `demo` 交易日。
2. 断言五条指定主线均出现，并覆盖上涨、下降、新增、扩散、兑现和证伪。
3. 断言 AI 算力的评分、事件原因和生命周期演变逻辑一致，不是随机数。
4. 断言真实 9 月 1 日记录为 `real + strict_mode`，证据不足分数为 `null` 且有原因。
5. 断言真实和模拟数据不会互相计算 delta。

**实现：**

1. 使用确定性场景数据生成器，不使用随机数。
2. 演示数据通过正式导入服务写库，不直接插表。
3. 真实记录只填写已有可靠市场、题材和梯队事实；缺口显式保留。

**验证与提交：**

```powershell
pytest tests/integration/test_seed_data.py -q
python scripts/seed_demo_data.py --reset-demo
python import_daily_review.py data/json/2026-09-01.json
```

提交：`testdata: add deterministic review history`

## 任务 8：实现 Dashboard 查询服务

**新增文件：**

- `src/queries/dashboard_queries.py`
- `src/queries/theme_queries.py`
- `src/queries/stock_queries.py`
- `src/queries/statistics_queries.py`
- `src/queries/evidence_queries.py`
- `src/queries/__init__.py`
- `tests/integration/test_queries.py`

**测试先行：**

1. 覆盖首页摘要、TOP5、同类型历史曲线和次日验证汇总。
2. 覆盖题材详情、股票名称/代码搜索、驱动力统计、生命周期统计和证据筛选。
3. 覆盖空数据库、无匹配日期、题材和股票。
4. 断言所有趋势和统计默认只包含一个 `data_kind`，平均分忽略 `null` 而不是按零计算。

**实现与验证：**

```powershell
pytest tests/integration/test_queries.py -q
```

提交：`feat: add dashboard read models and queries`

## 任务 9：实现 Streamlit 密集工作台首页

**新增文件：**

- `app.py`
- `src/ui/layout.py`
- `src/ui/formatters.py`
- `src/ui/charts.py`
- `src/ui/styles.py`
- `src/ui/__init__.py`
- `tests/ui/test_dashboard_home.py`

**测试先行：**

1. 使用 `streamlit.testing.v1.AppTest` 验证首页在有数据和无数据时都能启动。
2. 断言日期和类型筛选、市场指标、TOP5、历史图、验证汇总和数据缺口出现。
3. 断言 `null` 显示“暂不评分/数据不足”，真实记录带严格模式标签。

**实现：**

1. 按已确认的密集工作台原型实现侧栏、顶部筛选、指标条、TOP5 表、趋势图和验证面板。
2. 使用 Streamlit 原生控件和 Altair，不创建营销首页、嵌套卡片或装饰性渐变。
3. 颜色以黑色正文、白/浅灰工作区、有限的红绿状态色为主；保证中文字体和高对比度。

**验证与提交：**

```powershell
pytest tests/ui/test_dashboard_home.py -q
streamlit run app.py --server.headless true
```

提交：`feat: build dense market review workbench`

## 任务 10：实现五个详情与统计页面

**新增文件：**

- `pages/1_主线详情.py`
- `pages/2_核心个股.py`
- `pages/3_上涨驱动力.py`
- `pages/4_生命周期统计.py`
- `pages/5_证据中心.py`
- `tests/ui/test_dashboard_pages.py`

**测试先行：**

1. 每个页面至少有一个正常数据和一个空状态测试。
2. 覆盖题材因果链与逐日原因、个股搜索、41 项驱动力统计、生命周期转移和证据筛选。
3. 断言页面只通过查询服务读取数据库，不执行写操作。

**实现与验证：**

```powershell
pytest tests/ui/test_dashboard_pages.py -q
```

提交：`feat: add review detail and evidence pages`

## 任务 11：全量验证、视觉检查和 README

**修改文件：**

- `README.md`
- 必要时修复前述实现文件，但不扩大功能范围

**验证顺序：**

1. 在干净临时数据库执行完整初始化和导入流程。
2. 运行全部测试，确认用户要求的 12 类测试和新增隔离/事务测试均通过。
3. 启动 Streamlit，检查控制台无异常。
4. 使用 Playwright 分别在 1440×900 和 390×844 视口截图；检查文字、表格、筛选控件、图表和侧栏无重叠、截断或空白。
5. 修复视觉或运行问题后重新执行相关测试和截图。
6. README 写明安装、生成演示数据、导入真实记录、测试和启动命令，以及当前数据类型说明。

**最终命令：**

```powershell
pip install -r requirements.txt
python scripts/seed_demo_data.py
python import_daily_review.py data/json/2026-09-01.json
pytest -q
streamlit run app.py
```

**最终提交：** `docs: document verified phase 1 workflow`

**完成汇报只包含：** 已完成模块、准确启动命令、当前数据类型、下一阶段最值得接入的真实数据。

