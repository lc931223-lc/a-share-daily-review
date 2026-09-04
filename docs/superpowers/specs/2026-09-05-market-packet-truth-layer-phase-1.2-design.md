# A股数据层真实性修复 Phase 1.2 设计

日期：2026-09-05

## 目标与边界

本阶段只把 Market Packet 从接口完成率统计升级为可信、可审计、可按历史时点重放的数据快照。不会新增研究功能、竞价系统、PDF优化、产业数据全行业铺设或新 Skill。

实施分为两个独立验收批次。第一批先修事实正确性、质量门禁、缓存语义和审计链；第一批通过并推送后，第二批再引入 SQLite + Parquet + DuckDB、压缩批次归档和数据源路由优化。

## 核心定义

- `Market Packet`：指定 `trade_date` 与 `as_of_time` 下，从事实层选择出来的不可变研究快照，不是事实主库。
- `daily_policy_events`：默认只接受 `published_at` 位于目标自然日且不晚于 `as_of_time` 的正式政策记录。只有调用方显式指定增量窗口时才可扩大日期范围。
- `background_reference`：目标日期以前发布、仍有研究背景价值的历史政策。它不参与当日政策数量、质量 PASS 或当日新增催化判断。
- `EMPTY_VALID`：允许为空的数据域已完成规定来源扫描，且确认合法无记录。它不是采集失败。
- `INVALID`：存在未来信息、跨日/current-only污染、关键冲突未解决或内容污染。INVALID 优先于数值评分。

## 第一批架构

### 政策采集

建立每个官方机构独立的 adapter。每个 adapter 明确列表入口、允许 URL 模式、拒绝 URL 模式、编码、发布日期提取和政策文档识别规则。通用 HTML 工具只能负责请求、编码检测和 DOM 辅助，不能把任意 `<a>` 标签直接转成政策。

正式记录必须满足：来源属于官方 allowlist；URL 属于政策、通知、公告或文件栏目；标题可正常解码、长度合理且通过导航噪声过滤；`published_at` 存在；发布日期在允许窗口内；记录不晚于 `as_of_time`。旧文件进入 `background_reference`，无日期、乱码、导航和页脚内容进入拒绝审计，不进入正式 Packet。

政策质量以来源扫描完整性和记录合法性决定：全部主要源完成且记录合法时为 PASS；全部主要源完成且无当日记录时为 EMPTY_VALID；部分源失败或部分非关键字段缺失时为 PARTIAL；主要源不可用为 FAIL；任何内容或日期污染为 INVALID。

### 分域质量门禁

质量报告包含六个分域：`market_core` 35、`sector_theme` 20、`announcements` 15、`policies` 15、`capital_flow` 10、`continuity_audit` 5。每个分域保存原始检查、状态、分数、扣分原因和可用性说明，整体分数由配置化权重计算。

交易日、全市场日线、成交额、涨跌家数、主要指数或涨跌停任一 FAIL 时，总分封顶 69。政策跨日污染、公告未来信息污染或 current-only 数据进入历史正式字段时，整体状态直接为 INVALID。状态统一为 PASS、PARTIAL、FAIL、EMPTY_VALID、UNAVAILABLE、STALE、INVALID。

北向资金只有在关键金额字段存在且通过日期检查时才能 PASS。目标历史阶段本身不提供净流入时标记 UNAVAILABLE 并写明原因；十大成交股只能作为替代观察数据。

### 冲突检测

冲突检测器接收同一规范字段的多来源 observation，至少比较指数、成交额、涨跌停数量、公告发布时间和政策标题/日期。每条冲突保存字段、两端来源和值、差异、严重度、解决规则和最终选中源。严重且无法自动解决的冲突进入硬门禁；所有冲突写入 Packet 和数据库，禁止固定空数组。

### 缓存语义

缓存 manifest 保存 `cache_created_at`、`retrieved_at`、`last_attempt_at`、`status`、`error_type`、`retry_after`、`source_data_date`、`content_hash` 和原始来源。读取缓存时保留原始抓取时间。

成功且已确认的历史数据永久复用。失败缓存按错误分类设置 TTL：网络失败 15 分钟、限频 60 分钟、空响应 30 分钟、解析错误 6 小时。TTL 到期后只重试对应数据集。CLI 增加可重复的 `--refresh-dataset`，首批支持 policy、announcements、industry_board、northbound；原 `--refresh` 保留。

### 审计与版本

Market Packet 主链必须写入 `source_batch`、`source_observation`、`quality_gate_run`、`quality_gate_check` 和 `source_fallback`。每次外部请求或缓存命中对应一个批次；规范字段及候选值写 observation；最终选择通过 `selected`、`selected_reason` 和冲突状态表达。

公告和政策审计 append-only。事实索引表维护当前有效版本，但不得通过删除当天全部记录来丢失历史。记录以稳定自然键和 `content_hash` 去重，并关联首次批次、当前批次、前一版本和修订状态。重跑同一输入保持幂等；内容变化产生新版本。

## 第二批架构

### 混合存储

SQLite 继续承担目录和服务层：批次、observation、质量门禁、来源切换、公告/政策索引、official review、Dashboard 元数据。

Parquet/ZSTD 保存体量较大的规范事实：`full_market_daily`、`sector_daily`、`concept_daily`、`capital_flow` 和 `normalized_fact`，按数据集和交易日期分区。DuckDB 只作为嵌入式跨日期查询引擎，不引入常驻服务或 PostgreSQL。

所有事实至少包含 `event_date`、`source_data_date`、`published_at`、`retrieved_at`、`as_of_time`、`source_batch_id`、`content_hash`、`schema_version`、`quality_status`、`source` 和 `source_url`。

### 原始归档

公告和政策不再每条生成一个 JSON。每个来源批次写入压缩 JSONL 或等价的压缩批次文件，并通过 manifest 与内容哈希索引去重。迁移保留旧文件作为历史证据，不在未验证新归档前删除。

### 数据源路由

- 全市场日线：Tushare `daily` 主源；腾讯/通达信交叉验证；东财应急。
- 交易日历：Tushare 年度缓存；交易所日历校验。
- 指数：腾讯批量主备；Tushare `index_daily` 有权限时核验。
- 涨跌停：东财/AKShare 主源；同花顺或第二公开源交叉验证。
- 行业/概念：同日一次拉取全板块；避免逐板块请求；历史查询只使用已落盘快照或合规历史源。
- 公告：巨潮按日期批量抓取并在本地筛选核心股票；交易所按失败股票回补。
- 政策：每部委独立解析器，不允许通用 `<a>` 扫描。
- 两融：上交所和深交所官方源为主；Tushare/东财核验。
- 北向：不可获得时明确 UNAVAILABLE。

## 数据流

1. 根据统一交易日历解析目标日期和 `as_of_time`。
2. 路由器按数据集选择主源、核验源和允许的降级源。
3. 每次请求、缓存命中或失败先归档，再创建 `source_batch`。
4. 标准化器把候选事实写入 `source_observation`，保留来源日期和抓取时间。
5. 冲突检测器比较候选值，记录解决结果和选中源。
6. 分域质量门禁写入运行及逐项检查记录。
7. 事实层提交成功后，按 `as_of_time` 生成 Market Packet 快照。
8. Packet 通过 schema 校验后写文件、哈希和 `market_packet_log`；official review 流程保持独立。

## 错误处理与原子性

单一增强源失败不会破坏已确认事实，但必须影响对应分域状态。核心源失败按硬门禁处理。数据库批次、observation、质量运行和 Packet 日志在一次事务中完成；Parquet 与原始归档先写临时文件并原子替换，数据库只引用已完成文件。任何 INVALID 结果都可以留存审计，但不能作为正式可用 Packet。

## 历史数据修复

第一批完成后重新采集并生成 2026-09-01 至 2026-09-04。旧污染政策从当前有效事实和正式 Packet 中移除，但保留原始归档及审计标记。验收不设置最低 90 分目标，只要求分数与缺口真实。

每日汇报 overall quality、六个分域分数、INVALID、STALE、UNAVAILABLE 和冲突数量，并核验 source batch、observation 和 quality gate 表均产生记录。

## 测试与验收

新增单元和集成测试覆盖：政策导航、无日期、旧文件、未来日期、乱码和 EMPTY_VALID；北向全 null；失败缓存 TTL；原始 retrieved_at；单数据集刷新；五类审计表写入；冲突检测；append-only 幂等与修订；current-only 历史污染；SQLite/Parquet 一致性；压缩批次去重；四个历史交易日重放。

第一批完成后运行 compileall、全部非 real-data 测试和 9.1-9.4 真实重放，提交并推送。第二批完成后重复验证、提交并推送。最终要求工作区干净且本地 HEAD 与 `origin/main` 一致；不使用 force push，不提交 token、数据库或原始缓存。
