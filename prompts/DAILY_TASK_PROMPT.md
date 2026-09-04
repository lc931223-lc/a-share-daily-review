# DAILY TASK PROMPT

执行日期：{{TRADE_DATE}}

请严格依据 SYSTEM_PROMPT，对 {{TRADE_DATE}} A股收盘进行完整复盘。

## Step 1：交易日检查
- 判断今天是否为A股交易日。
- 若不是，输出 `NO_TRADING_DAY` 并结束。
- 若尚无完整收盘数据，输出 `MARKET_NOT_CLOSED` 并结束。

## Step 2：市场总览
采集并输出：
- 上证指数
- 深证成指
- 创业板指
- 科创50
- 北证50
- 两市成交额
- 较前一交易日成交额增减
- 上涨家数
- 下跌家数
- 涨停家数
- 跌停家数
- 连板高度
- 大盘/小盘
- 成长/价值
- 权重/题材
- 高位/低位

最后用一句话定义今日市场：
【主升 / 轮动 / 震荡 / 高低切 / 退潮 / 修复】

## Step 3：主线 TOP5
每条主线必须给出：
- 主线名称
- 今日核心催化
- 41类上涨因素编号
- 驱动层级
- 因果链
- 龙头
- 中军
- 补涨
- 当前生命周期
- 今日属于：新增 / 强化 / 扩散 / 兑现 / 弱化

## Step 4：主线打分
逐项输出：
- 基础逻辑 /40
- 兑现程度 /25
- 预期差 /15
- 持续性 /10
- 市场确认 /10
- 风险扣分 0~-20
- 综合 /100
- 评级

并额外输出：
- 逻辑质量 0-100
- 预期差 0-100
- 行情强度 0-100
- 风险收益比 0-100

任何评分变化必须给出 `delta_reason`。

## Step 5：核心个股 TOP10
每只输出：
- name
- code
- theme
- role：龙头/中军/补涨/跟风/情绪股
- drivers
- catalyst
- benefit_path
- causal_chain
- evidence[]
- realization_score
- expectation_gap
- lifecycle_stage
- logic_quality
- market_strength
- risk_reward
- rating
- risks[]
- invalidation_conditions[]

## Step 6：与上一交易日对比
读取上一交易日结构化JSON，输出：
- 新增
- 强化
- 弱化
- 扩散
- 兑现
- 证伪

要求：
- 所有变化必须给出证据
- 不允许无理由调分

## Step 7：明日观察
每条核心主线输出：
- tomorrow_checks
- strengthen_conditions
- weaken_conditions
- invalidation_conditions

禁止写“看涨/看跌必然结论”。
只写验证条件。

## Step 8：输出
生成：
1. `data/daily/{{TRADE_DATE}}.md`
2. `data/json/{{TRADE_DATE}}.json`
3. 写入 SQLite
4. 更新主线评分历史
5. 更新个股评分历史
6. 保存证据与来源

如果是本周最后一个交易日：
额外生成周报。

如果是本月最后一个交易日：
额外生成月报。
