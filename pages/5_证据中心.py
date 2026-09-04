import pandas as pd
import streamlit as st

from src.queries.evidence_queries import evidence_list
from src.storage.database import create_db_engine, create_schema, session_factory
from src.ui.layout import empty_state, setup_page


setup_page("证据中心")
st.title("证据中心")
engine = create_db_engine(); create_schema(engine)
with session_factory(engine)() as session:
    left, right = st.columns(2)
    level = left.selectbox("证据等级", ["全部", "A", "B", "C", "D"])
    state = right.selectbox("核验状态", ["全部", "已核验", "未核验"])
    verified = None if state == "全部" else state == "已核验"
    rows = evidence_list(session, None if level == "全部" else level, verified)
    if not rows: empty_state("当前筛选条件下没有证据"); st.stop()
    frame = pd.DataFrame(rows).rename(columns={"trade_date": "日期", "entity_key": "关联对象", "evidence_level": "等级", "title": "标题", "source_name": "来源", "published_at": "发布时间", "excerpt": "摘要", "verified": "已核验", "source_url": "原始URL"})
    st.dataframe(frame[["日期", "等级", "关联对象", "标题", "来源", "发布时间", "摘要", "已核验", "原始URL"]], hide_index=True, width="stretch")
