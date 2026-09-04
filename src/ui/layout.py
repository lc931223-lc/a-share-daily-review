from datetime import date

import streamlit as st

from src.queries.dashboard_queries import get_day, list_days
from src.ui.styles import apply_styles


def setup_page(title: str) -> None:
    st.set_page_config(page_title=title, layout="wide", initial_sidebar_state="auto")
    apply_styles()
    st.sidebar.markdown("## A股复盘")
    st.sidebar.caption("数据库与历史跟踪工作台")
    st.sidebar.page_link("app.py", label="市场总览")
    st.sidebar.page_link("pages/1_主线详情.py", label="主线详情")
    st.sidebar.page_link("pages/2_核心个股.py", label="核心个股")
    st.sidebar.page_link("pages/3_上涨驱动力.py", label="上涨驱动力")
    st.sidebar.page_link("pages/4_生命周期统计.py", label="生命周期统计")
    st.sidebar.page_link("pages/5_证据中心.py", label="证据中心")
    st.sidebar.page_link("pages/6_数据质量.py", label="数据质量")
    st.sidebar.page_link("pages/7_验证中心.py", label="验证中心")
    st.sidebar.page_link("pages/8_回测统计.py", label="回测统计")


def choose_day(session, key: str = "trade_date"):
    days = list_days(session)
    if not days:
        return None
    options = [day.trade_date for day in days]
    selected = st.selectbox("交易日", options, format_func=lambda value: value.isoformat(), key=key)
    return get_day(session, selected)


def empty_state(message: str = "当前筛选条件下暂无复盘数据") -> None:
    st.info(message)
