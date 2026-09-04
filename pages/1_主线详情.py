import pandas as pd
import streamlit as st

from src.queries.theme_queries import list_themes, theme_detail, theme_history
from src.storage.database import create_db_engine, create_schema, session_factory
from src.ui.charts import history_line
from src.ui.formatters import format_score
from src.ui.layout import empty_state, setup_page


setup_page("主线详情")
st.title("主线详情")
engine = create_db_engine(); create_schema(engine)
with session_factory(engine)() as session:
    themes = list_themes(session)
    selected = st.selectbox("选择主线", themes, format_func=lambda item: item.canonical_name)
    detail = theme_detail(session, selected.id) if selected else None
    if detail is None:
        empty_state("该主线暂无正式真实记录"); st.stop()
    columns = st.columns(4)
    columns[0].metric("当前评分", format_score(detail["scores"]["total_score"], detail["rating"]))
    columns[1].metric("生命周期", detail["stage"])
    columns[2].metric("当日变化", detail["delta_score"] if detail["delta_score"] is not None else "—")
    columns[3].metric("交易日", detail["trade_date"].isoformat())
    st.subheader("因果链")
    st.markdown(f'<div class="chain">{"　→　".join(detail["causal_chain"])}</div>', unsafe_allow_html=True)
    st.subheader("评分拆解")
    labels = {"base_logic_score": "基础逻辑 /40", "realization_score": "兑现 /25", "expectation_gap_score": "预期差 /15", "persistence_score": "持续性 /10", "market_confirmation_score": "市场确认 /10", "risk_penalty": "风险扣分", "risk_reward": "风险收益比"}
    st.table(pd.DataFrame([{"维度": label, "数值": detail["scores"][key] if detail["scores"][key] is not None else "暂不评分"} for key, label in labels.items()]))
    st.subheader("历史变化")
    history = theme_history(session, selected.id)
    chart = history_line(history, "total_score", "综合分")
    if chart: st.altair_chart(chart, width="stretch")
    else: empty_state("暂无可绘制的有效综合分")
    st.table(pd.DataFrame(history))
