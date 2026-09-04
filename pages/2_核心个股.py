import pandas as pd
import streamlit as st

from src.queries.stock_queries import search_stocks, stock_detail, stock_history
from src.storage.database import create_db_engine, create_schema, session_factory
from src.ui.charts import history_line
from src.ui.formatters import format_score
from src.ui.layout import empty_state, setup_page


setup_page("核心个股")
st.title("核心个股")
engine = create_db_engine(); create_schema(engine)
with session_factory(engine)() as session:
    query = st.text_input("股票名称或代码", value="")
    matches = search_stocks(session, query)
    if not matches: empty_state("没有匹配的核心个股"); st.stop()
    selected = st.selectbox("匹配结果", matches, format_func=lambda item: f'{item["code"]} {item["name"]}')
    detail = stock_detail(session, selected["code"])
    if detail is None: empty_state("该股票暂无正式真实评分记录"); st.stop()
    st.subheader(f'{detail["name"]} · {detail["code"]}')
    columns = st.columns(5)
    for column, label, value in zip(columns, ("所属主线", "市场地位", "综合评级", "行情强度", "风险收益比"), (detail["theme"], f'{detail["role"]} / {detail["role_detail"] or "—"}', format_score(detail["total_score"], detail["rating"]), detail["market_strength"] if detail["market_strength"] is not None else "暂不评分", detail["risk_reward"] if detail["risk_reward"] is not None else "暂不评分")):
        column.metric(label, value)
    st.subheader("公司受益路径")
    st.markdown(f'<div class="chain">{"　→　".join(detail["benefit_path"])}</div>', unsafe_allow_html=True)
    st.subheader("评分拆解")
    st.table(
        pd.DataFrame(
            [
                {"维度": "兑现强度", "数值": detail["realization_score"] if detail["realization_score"] is not None else "暂不评分"},
                {"维度": "预期差", "数值": detail["expectation_gap"] if detail["expectation_gap"] is not None else "暂不评分"},
                {"维度": "逻辑质量", "数值": detail["logic_quality"] if detail["logic_quality"] is not None else "暂不评分"},
                {"维度": "行情强度", "数值": detail["market_strength"] if detail["market_strength"] is not None else "暂不评分"},
                {"维度": "风险收益比", "数值": detail["risk_reward"] if detail["risk_reward"] is not None else "暂不评分"},
                {"维度": "综合评级", "数值": format_score(detail["total_score"], detail["rating"])},
            ]
        )
    )
    history = stock_history(session, selected["code"])
    chart = history_line(history, "total_score", "综合评分")
    if chart: st.altair_chart(chart, width="stretch")
    else: empty_state("暂无可绘制的有效综合分")
    st.table(pd.DataFrame(history))
