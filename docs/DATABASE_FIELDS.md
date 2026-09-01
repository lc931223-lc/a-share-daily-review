# 历史复盘数据库字段设计

建议使用 SQLite 起步，后续数据量扩大再迁移 PostgreSQL。

## 1. trading_day
记录每天市场状态：
- trade_date
- market_regime
- turnover
- turnover_delta
- advancers
- decliners
- limit_up_count
- limit_down_count
- max_board_height

## 2. theme
主线标准表：
- theme_id
- canonical_name

避免“AI算力”“算力”“人工智能算力”每天被当成三个不同主题。

## 3. theme_daily_score
最核心的历史表：
- trade_date
- theme_id
- rank_no
- stage
- change_status
- causal_chain
- base_logic_score
- realization_score
- expectation_gap_score
- persistence_score
- market_confirmation_score
- risk_penalty
- total_score
- rating
- logic_quality
- market_strength
- risk_reward
- delta_score
- delta_reason

## 4. theme_driver
保存每天每条主线命中了哪些上涨因素：
- driver_code
- driver_name
- evidence_level

## 5. stock
个股基础信息：
- stock_code
- stock_name
- exchange

## 6. stock_daily_score
保存个股每日判断：
- trade_date
- stock_code
- theme_id
- role
- stage
- catalyst
- benefit_path
- causal_chain
- realization_score
- expectation_gap
- logic_quality
- market_strength
- risk_reward
- total_score
- rating
- delta_score
- delta_reason

## 7. evidence
保存评分证据：
- entity_type
- entity_key
- evidence_level
- evidence_type
- title
- source_name
- source_url
- published_at
- excerpt
- verified

## 8. risk_event
保存风险与扣分理由：
- risk_type
- severity
- penalty
- description
- invalidation_condition

## 9. tomorrow_check
这是长期系统非常重要的一张表。

每天写下“明天需要验证什么”，次日自动回填：
- pending
- confirmed
- weakened
- invalidated

长期以后可以统计：
“我们的验证条件到底准不准？”

## 10. theme_relationship
用于保存主线关系：
例如：
AI → 算力 → 光模块
机器人 → 减速器
涨价 → 化工某细分

关系类型可以是：
- parent
- upstream
- downstream
- mapping
- catchup
- competing
