# 9:25集合竞价验证系统审计与整改记录

审计日期：2026-09-08
审计基线：`d4f0698faccb579884d180245142be940c107979`
审计样本：2026-09-04 历史竞价缓存，100只重点股票

## 审计结论

当前 Phase A2 已经具备真实 `eltdx` 竞价过程、独立09:25正式撮合、Parquet/SQLite审计、腾讯/东方财富开盘核验和Tushare盘后复核的基础链路，但尚未形成完整的“上一日正式复盘 -> 连续竞价 -> 自动验证 -> 100分追溯评分 -> 09:30-10:00验证”生产系统。

当前状态必须判定为 `PARTIALLY READY`，不能判定为 `READY`。

## 十项现状核对

1. **09:15-09:25数据源**：主数据源是 `eltdx` 的 `0x056a` 集合竞价过程快照；09:25正式撮合来自 `0x0fc5/0x0fc6` opening match。实时开盘校验使用腾讯，失败时东方财富回退，盘后使用Tushare daily.open。
2. **是否保存连续快照**：部分实现。系统保存数据源返回的全部非规则原始过程点，并映射到9个checkpoint；实时模式只主动轮询9次，不是连续10秒或30秒采集。
3. **实际频率**：2026-09-04缓存单股52-201个原始点，中位161个；相邻点中位3秒、P95为9秒、最大51秒。该频率由主站原始序列决定，不是固定频率。实时runner当前仅在checkpoint轮询。
4. **09:20-09:25完整性**：2026-09-04的09:20、09:21、09:22、09:23、09:24、09:25均为100/100；09:15仅52/100。09:16和09:18 checkpoint为 `NOT IMPLEMENTED`。
5. **字段能力**：`match_price`、虚拟`matched_volume`、派生`matched_amount`、带符号未匹配量原始值和未匹配方向原始值可取。`buy_unmatched`、`sell_unmatched`、标准化`unmatched_side`和源生`unmatched_amount`为 `NOT IMPLEMENTED/UNAVAILABLE`。现有代码虽然定义`unmatched_buy/unmatched_sell`，实际覆盖率为0。
6. **是否读取上一交易日正式复盘**：使用真实A股交易日历定位上一交易日，并只尝试同日 `official_reviews/YYYY-MM-DD.json` 或旧同日review路径，不会用更早日期冒充；但不读取上一交易日 `review_context`，缺失时仅使质量检查失败，没有明确`report_status=degraded`。
7. **正式复盘字段继承**：只使用 `main_themes.name/rank/stage`、股票角色和tomorrow_check选股。`mainline_score`、完整lifecycle、leader/zhongjun/buzhang/trend_core/sentiment_core结构、41类`factor_ids`、催化证据链、产业证据、资金证据和风险结构化继承均为 `NOT IMPLEMENTED`。
8. **tomorrow_check自动验证**：`NOT IMPLEMENTED`。当前只把相关股票加入watchlist；输出没有逐条 `confirmed/partially_confirmed/weakened/invalidated/unverified` 状态。
9. **当前评分字段**：当前只有0-20分 `auction_volume_anomaly_score`，由20日竞价额比、60日竞价额分位、竞价额/昨日全天成交额、09:20后金额增长、最后1-2分钟增长和09:20到09:25价格确认组成。要求的100分综合模型为 `NOT IMPLEMENTED`。
10. **文字推断项目**：上一主线验证只列竞价排名和中位高开；弱转强/强转弱只用角色、开盘涨幅和异常标签；09:30-10:00只是四条 `PENDING` 条件。生命周期迁移、催化变化、订单硬验证、超预期基准、完整状态机和最终100分均未由可追溯字段实现。

## 数据真实性核对

- 2026-09-04保存14,446条snapshot事实，其中13,546条为原始过程点、900条为checkpoint映射。
- `match_price/matched_volume/matched_amount`覆盖14,398/14,446。
- `unmatched_signed_volume/unmatched_direction_raw`覆盖14,298/14,446。
- `unmatched_buy/unmatched_sell/unmatched_amount/buy_unmatched/sell_unmatched`覆盖均为0。
- 正式09:25成功率、历史Tushare开盘校验率均为100%，零价格冲突。
- 上一交易日2026-09-03正式复盘缺失，因此主线和角色验证为 `UNAVAILABLE`，这项降级是诚实的。

## 问题分级

### P0

- 11个分钟checkpoint不完整，实时轮询不满足30秒优先要求。
- 缺少上一日 `review_context` 和正式复盘完整字段继承。
- 100分模型、可用分、缺失分项、风险实扣均未实现。
- tomorrow_check结构化自动验证未实现。
- Trading Day Gate只在live模式执行；historical模式可能为非交易日生成包。
- 09:30-10:00没有数据采集和状态更新执行链。

### P1

- 未匹配方向只有原始值，尚无经过来源契约确认的buy/sell语义；相关订单方向评分必须N/A。
- 缺少每分钟价格、订单增长/衰减、5/10/20日分位与zscore的完整派生字段。
- 板块breadth字段不足，未区分龙头独强、龙头+补涨、龙头+中军和全板块共振。
- 弱转强/强转弱不是完整状态机。
- 催化和41类因素没有进入竞价验证，Evidence D限制没有执行。
- Data Quality Gate缺少Evidence Gate、刷新时间、HIGH/MEDIUM/LOW和显式degraded状态。

### P2

- Auction Packet JSON Schema约束过松，大部分对象只校验类型，不校验关键字段。
- 09:25正式撮合在事实表中被改写为checkpoint kind，无法单独统计正式记录类型。
- 历史模式没有09:30后30分钟结果库，样本量和相似样本评分不可用。
- 没有固定十节报告结构的结构化输出。

## 整改原则

1. 保留现有数据源与FactStore，不创建第二行情库。
2. 所有日期严格按A股交易日历和as-of时间处理，不读取未来信息。
3. 源不能确认的买卖方向、未匹配金额和历史模式结果保持 `null/N/A`。
4. 先完成可追溯数据结构、评分与质量门，再生成固定报告投影。
5. 正式复盘缺失时只允许 `report_status=degraded`，不得回退更早复盘。
6. 任何D级信息不得计入订单、业绩或高可信催化分。

## 整改实施结果

- checkpoint已扩展为09:15-09:25每分钟11点，live runner改为30秒轮询21次；原始源返回的秒级非规则过程点继续完整入库。
- 新增上一实际交易日严格继承器，同时读取同日official review、review context和Market Packet；不存在时降级，不使用更早日期替代。带fixture、sample、synthetic或“模拟”标记的review拒绝作为正式输入。
- 新增5/10/20日竞价金额和竞价量分位、z-score，昨日金额/量比，09:15/09:20/09:24/09:25价格变化，以及09:20后订单绝对量增长/衰减和稳定性。由于源协议未确认买卖语义，方向分、撤单率和未匹配金额保持N/A。
- 新增100分可追溯模型与0-20风险实扣。可用分母按子项计算，不把缺失的订单方向、撤单或历史30分钟样本计入available max。
- 新增板块breadth、结构状态、tomorrow_check五态验证、生命周期候选迁移、个股五态状态机和固定十节结构化报告。
- 新增当日09:30-10:00 `post-open` 执行入口；腾讯实时源优先、东方财富回退，当前源日期不匹配时拒绝写入历史日期。

## 2026-09-04真实缓存回放

- 股票数：100。
- 11点checkpoint覆盖率：95.73%。
- 09:20-09:25逐分钟覆盖率：100%。
- 09:25正式撮合覆盖率：100%。
- 输出质量：`MEDIUM/PARTIAL`，报告状态：`degraded`。
- 降级原因：2026-09-03正式official review和review context不存在；历史回放不能代替真实当日live验收。
- 当前生产结论：`PARTIALLY READY`。生产调度尚未经过下一真实交易日端到端验收，且现有数据源不能可靠拆分买卖未匹配量和撤单。
