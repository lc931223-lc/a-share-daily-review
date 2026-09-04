import pandas as pd
import streamlit as st
from sqlalchemy import select

from src.queries.dashboard_queries import check_summary, core_stocks_by_theme, market_summary, top_themes
from src.queries.theme_queries import theme_history
from src.storage.database import create_db_engine, create_schema, session_factory
from src.storage.models import AnalysisSnapshot
from src.ui.charts import history_line
from src.ui.formatters import format_delta, format_number, format_score, format_status
from src.ui.layout import choose_day, empty_state, setup_page


setup_page("A股市场复盘 Dashboard")
engine = create_db_engine()
create_schema(engine)

st.title("A股市场复盘 Dashboard")
with session_factory(engine)() as session:
    filter_col, note_col = st.columns([1, 3])
    with filter_col:
        day = choose_day(session, "home_day")
    if day is None:
        empty_state()
        st.stop()
    summary = market_summary(day)
    snapshot = session.execute(
        select(AnalysisSnapshot)
        .where(AnalysisSnapshot.trade_date == day.trade_date, AnalysisSnapshot.status == "PASSED")
        .order_by(AnalysisSnapshot.id.desc())
    ).scalar()
    snapshot_data = {}
    if snapshot and snapshot.result_json:
        import json

        snapshot_data = json.loads(snapshot.result_json)
    with note_col:
        st.markdown(
            f'<span class="status-real">正式真实数据快照</span>　完整度 {summary["completeness_score"]}%',
            unsafe_allow_html=True,
        )
        st.caption(summary["market_regime"])

    st.subheader("今日市场")
    metrics = st.columns(7)
    values = [
        ("市场状态", summary["market_regime"].split("、")[0]),
        ("两市成交额", f'{summary["turnover"] / 10000:.2f}万亿' if summary["turnover"] is not None else "数据不足"),
        ("成交额变化", format_number(summary["turnover_delta"], "亿元")),
        ("上涨 / 下跌", f'{format_number(summary["advancers"])} / {format_number(summary["decliners"])}'),
        ("涨停 / 跌停", f'{format_number(summary["limit_up_count"])} / {format_number(summary["limit_down_count"])}'),
        ("最高板", format_number(summary["max_board_height"], "板")),
        ("仓位约束", f'{summary["position_min"]}—{summary["position_max"]}成'),
    ]
    for column, (label, value) in zip(metrics, values):
        column.metric(label, value)

    index_rows = snapshot_data.get("indices", [])
    if index_rows:
        st.subheader("指数与量能")
        st.table(
            pd.DataFrame(
                [
                    {
                        "指数": item["name"],
                        "收盘": item["close"],
                        "涨跌幅": f'{item["change_pct"]:.2f}%',
                        "成交额": f'{item["turnover_yi"]:.0f}亿元' if item.get("turnover_yi") else "缺失",
                    }
                    for item in index_rows
                ]
            )
        )

    sentiment = snapshot_data.get("sentiment_dashboard", {})
    if sentiment:
        st.subheader("情绪温度")
        sentiment_cols = st.columns(3)
        sentiment_cols[0].metric("温度", sentiment["temperature"])
        sentiment_cols[1].metric("流动性", sentiment["liquidity"])
        sentiment_cols[2].metric("涨跌宽度", sentiment["breadth"])
        st.markdown(f'<div class="quality-warning"><b>亏钱效应</b><br>{sentiment["loss_feedback"]}</div>', unsafe_allow_html=True)

    st.subheader("今日主线 TOP5")
    themes = top_themes(session, day.id)
    stock_labels = core_stocks_by_theme(session, day.id)
    table = pd.DataFrame([{
        "排名": item["rank_no"], "主线": item["name"],
        "综合评分": format_score(item["total_score"], item["rating"]),
        "变化": format_delta(item["delta_score"]), "生命周期": item["stage"],
        "状态": format_status(item["change_status"]), "龙头 / 中军 / 补涨": stock_labels.get(item["theme_id"], "—"),
    } for item in themes])
    st.table(table)

    score_rows = []
    for item in snapshot_data.get("main_themes", []):
        scores = item.get("scores", {})
        score_rows.append(
            {
                "排名": item.get("rank_no"),
                "主线": item.get("name"),
                "基础逻辑/40": scores.get("base_logic_score"),
                "兑现/25": scores.get("realization_score"),
                "预期差/15": scores.get("expectation_gap_score"),
                "持续性/10": scores.get("persistence_score"),
                "市场确认/10": scores.get("market_confirmation_score"),
                "风险扣分": scores.get("risk_penalty"),
                "综合": format_score(scores.get("total_score"), scores.get("rating")),
            }
        )
    if score_rows:
        st.subheader("主线评分拆解")
        st.table(pd.DataFrame(score_rows))

    stock_score_rows = []
    for item in snapshot_data.get("stocks", []):
        scores = item.get("scores", {})
        stock_score_rows.append(
            {
                "代码": item.get("code"),
                "名称": item.get("name"),
                "主线": item.get("theme"),
                "地位": item.get("role"),
                "综合": format_score(scores.get("total_score"), scores.get("rating")),
                "行情强度": scores.get("market_strength"),
                "逻辑质量": scores.get("logic_quality"),
                "风险收益": scores.get("risk_reward"),
                "催化": item.get("catalyst"),
            }
        )
    if stock_score_rows:
        st.subheader("核心个股评分")
        st.table(pd.DataFrame(stock_score_rows))

    engine_detail = snapshot_data.get("sentiment_engine") or {}
    engine_metric = engine_detail.get("daily_metric") or {}
    if engine_metric:
        st.subheader("东方财富情绪引擎校验")
        engine_cols = st.columns(5)
        engine_cols[0].metric("情绪分", engine_metric["sentiment_score"])
        engine_cols[1].metric("状态", engine_metric["sentiment_state"])
        engine_cols[2].metric("炸板率", f'{engine_metric["failed_limit_rate"]:.2f}%')
        engine_cols[3].metric("昨日涨停红盘率", f'{engine_metric["prev_limit_positive_rate"]:.2f}%')
        engine_cols[4].metric("纪律", engine_metric["discipline"])
        theme_rank_rows = engine_detail.get("theme_ranking", [])
        if theme_rank_rows:
            st.table(
                pd.DataFrame(theme_rank_rows).rename(
                    columns={
                        "rank": "排名",
                        "theme_name": "题材",
                        "theme_score": "综合分",
                        "limit_up_count": "涨停",
                        "failed_limit_count": "炸板",
                        "failed_limit_rate": "炸板率",
                        "highest_board": "最高板",
                        "persistence_days": "持续",
                        "cycle_phase": "阶段",
                        "top_stocks": "代表股",
                    }
                )
            )
        role_rows = engine_detail.get("stock_role_classification", [])
        if role_rows:
            st.table(
                pd.DataFrame(
                    [
                        {
                            "代码": item["code"],
                            "名称": item["name"],
                            "题材": item["theme_name"],
                            "地位": item["role"],
                            "置信分": item["role_score"],
                            "证据": "；".join(item.get("evidence", [])[:2]),
                        }
                        for item in role_rows
                    ]
                )
            )

    strength_rows = snapshot_data.get("sector_strength", [])
    weakness_rows = snapshot_data.get("sector_weakness", [])
    if strength_rows or weakness_rows:
        sector_left, sector_right = st.columns(2)
        with sector_left:
            st.subheader("强势方向")
            st.table(pd.DataFrame(strength_rows).rename(columns={"rank": "排名", "name": "方向", "status": "状态", "evidence": "证据"}))
        with sector_right:
            st.subheader("弱势方向")
            st.table(pd.DataFrame(weakness_rows).rename(columns={"rank": "排名", "name": "方向", "status": "状态", "evidence": "证据"}))

    ladder_rows = snapshot_data.get("limit_ladder", [])
    if ladder_rows:
        st.subheader("涨停梯队与亏钱反馈")
        st.table(pd.DataFrame(ladder_rows).rename(columns={"height": "高度", "stocks": "代表个股", "read": "解读"}))

    dragon_tiger = snapshot_data.get("dragon_tiger", {})
    if dragon_tiger:
        st.subheader("龙虎榜摘要")
        lhb_cols = st.columns(3)
        lhb_cols[0].metric("上榜成交额", f'{dragon_tiger["amount_yi"]:.2f}亿元')
        lhb_cols[1].metric("上榜个股", f'{dragon_tiger["stock_count"]}只')
        lhb_cols[2].metric("机构净买入", f'{dragon_tiger["institution_net_buy_count"]}只')
        st.caption(dragon_tiger["read"])

    tomorrow_plan = snapshot_data.get("tomorrow_plan", [])
    if tomorrow_plan:
        st.subheader("次日推演")
        st.table(pd.DataFrame(tomorrow_plan).rename(columns={"item": "观察项", "trigger": "触发条件", "meaning": "含义"}))

    left, right = st.columns([1.55, 1])
    with left:
        st.subheader("主线历史走势")
        selected_theme = st.selectbox("主线", themes, format_func=lambda item: item["name"], key="home_theme")
        dimensions = {"综合分": "total_score", "基础逻辑": "base_logic_score", "兑现程度": "realization_score", "预期差": "expectation_gap_score", "持续性": "persistence_score", "市场确认": "market_confirmation_score", "风险收益比": "risk_reward"}
        dimension = st.selectbox("评分维度", list(dimensions), key="home_dimension")
        chart = history_line(theme_history(session, selected_theme["theme_id"]), dimensions[dimension], dimension)
        if chart is None:
            empty_state("该维度证据不足，暂不绘制趋势")
        else:
            st.altair_chart(chart, width="stretch")
    with right:
        st.subheader("次日验证与数据质量")
        checks = check_summary(session, day.id)
        check_columns = st.columns(4)
        for column, key, label in zip(check_columns, ("pending", "confirmed", "weakened", "invalidated"), ("待确认", "已确认", "弱化", "失效")):
            column.metric(label, checks[key])
        if summary["missing_items"]:
            missing = "、".join(summary["missing_items"])
            st.markdown(f'<div class="quality-warning"><b>真实记录缺口</b><br>{missing}</div>', unsafe_allow_html=True)
        else:
            st.success("数据完整度检查通过")
