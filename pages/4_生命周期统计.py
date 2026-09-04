import pandas as pd
import streamlit as st

from src.queries.statistics_queries import delta_score_statistics, lifecycle_statistics, rating_sample_statistics, stock_role_statistics, tomorrow_check_statistics
from src.storage.database import create_db_engine, create_schema, session_factory
from src.ui.layout import setup_page


setup_page("生命周期统计")
st.title("生命周期统计")
engine = create_db_engine(); create_schema(engine)
with session_factory(engine)() as session:
    st.subheader("主线生命周期")
    rows = lifecycle_statistics(session)
    frame = pd.DataFrame(rows).rename(columns={"stage": "生命周期", "count": "出现次数"})
    st.bar_chart(frame.set_index("生命周期"))
    st.dataframe(frame, hide_index=True, width="stretch")

    st.subheader("评级样本")
    rating_rows = rating_sample_statistics(session)
    if rating_rows:
        st.dataframe(pd.DataFrame(rating_rows).rename(columns={"rating": "评级", "sample_count": "样本数", "avg_delta_score": "平均delta_score", "next_day_return": "次日表现", "five_day_return": "5日表现", "ten_day_return": "10日表现", "twenty_day_return": "20日表现", "return_data_status": "收益数据状态"}), hide_index=True, width="stretch")
    else:
        st.info("暂无正式评级样本")

    st.subheader("delta_score 分布")
    delta_rows = delta_score_statistics(session)
    if delta_rows:
        st.dataframe(pd.DataFrame(delta_rows).rename(columns={"entity_type": "对象", "count": "样本数", "positive": "升分", "negative": "降分", "flat": "持平或首次"}), hide_index=True, width="stretch")
    else:
        st.info("暂无历史评分变化")

    st.subheader("个股角色样本")
    role_rows = stock_role_statistics(session)
    if role_rows:
        st.dataframe(pd.DataFrame(role_rows).rename(columns={"role": "角色", "sample_count": "样本数", "avg_delta_score": "平均delta_score", "return_data_status": "收益数据状态"}), hide_index=True, width="stretch")
    else:
        st.info("暂无个股角色样本")

    st.subheader("tomorrow_check 验证")
    check_rows = tomorrow_check_statistics(session)
    if check_rows:
        st.dataframe(pd.DataFrame(check_rows).rename(columns={"status": "状态", "count": "数量", "ratio": "占比%"}), hide_index=True, width="stretch")
    else:
        st.info("暂无验证样本")
