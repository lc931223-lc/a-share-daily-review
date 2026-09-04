import pandas as pd
import streamlit as st

from src.queries.statistics_queries import delta_score_statistics, rating_sample_statistics, stock_role_statistics, tomorrow_check_statistics
from src.storage.database import create_db_engine, create_schema, session_factory
from src.ui.layout import setup_page


setup_page("回测统计")
st.title("回测统计")
st.caption("这里统计 ChatGPT official_review 的历史结果。当前阶段不自动生成交易建议；未来收益字段在价格验证链路接入前保持空值。")

engine = create_db_engine()
create_schema(engine)
with session_factory(engine)() as session:
    sections = [
        ("评级历史表现", rating_sample_statistics(session)),
        ("delta_score 统计", delta_score_statistics(session)),
        ("龙头 / 中军 / 补涨样本", stock_role_statistics(session)),
        ("tomorrow_check 成功率", tomorrow_check_statistics(session)),
    ]
    for title, rows in sections:
        st.subheader(title)
        if rows:
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        else:
            st.info("暂无样本")
