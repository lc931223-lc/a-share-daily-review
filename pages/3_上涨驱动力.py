import pandas as pd
import streamlit as st

from src.queries.statistics_queries import driver_statistics
from src.storage.database import create_db_engine, create_schema, session_factory
from src.ui.layout import setup_page


setup_page("上涨驱动力统计")
st.title("上涨驱动力统计")
engine = create_db_engine(); create_schema(engine)
with session_factory(engine)() as session:
    window = st.select_slider("统计窗口", options=[5, 10, 20, 40, 60], value=20, format_func=lambda value: f"近{value}个交易日")
    rows = driver_statistics(session, window)
    frame = pd.DataFrame(rows).rename(columns={"driver_code": "编号", "driver_name": "上涨因素", "count": "出现次数", "average_score": "平均有效评分", "sa_count": "S/A级次数"})
    st.dataframe(frame, hide_index=True, width="stretch")
    active = frame[frame["出现次数"] > 0]
    if not active.empty: st.bar_chart(active.set_index("上涨因素")["出现次数"])
