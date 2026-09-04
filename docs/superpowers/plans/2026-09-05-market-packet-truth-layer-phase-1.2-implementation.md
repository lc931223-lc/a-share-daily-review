# A股数据层真实性修复 Phase 1.2 实施计划

## 第一批：真实性与质量门禁

1. 扩展 Market Packet 状态、schema 与分域质量模型，先补失败测试。
2. 将政策采集改为独立来源规则、严格日期窗口、乱码/导航过滤和 EMPTY_VALID。
3. 修复北向全 null 假 PASS，并补 UNAVAILABLE 原因。
4. 建立缓存 manifest、失败 TTL、原始 retrieved_at 和 `--refresh-dataset`。
5. 实现多来源冲突记录与 INVALID 硬门禁。
6. 将 source batch、observation、quality run/check 和 fallback 写入 Market Packet 主链。
7. 将公告/政策当前事实改成版本化 upsert，审计记录 append-only。
8. 运行 compileall、非 real-data 测试并重放 2026-09-01 至 2026-09-04。
9. 更新 checkpoint，选择性提交并推送第一批到 `origin/main`。

## 第二批：存储与路由

1. 增加 Parquet 事实仓及 DuckDB 查询层，SQLite 保留目录和服务元数据。
2. 将公告/政策逐条 JSON 改为每日压缩 JSONL 批次并以内容哈希去重。
3. 引入明确的数据源路由配置，优先消除板块逐项请求和公告逐股全源请求。
4. 验证 SQLite/Parquet 一致性、压缩归档、小文件数量和历史重放。
5. 更新文档与 checkpoint，提交并推送第二批，确认本地 HEAD 等于远端 main。
