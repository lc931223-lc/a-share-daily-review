import streamlit as st


CSS = """
<style>
:root { color-scheme: light; }
.stApp { background: #eef1f3; color: #111417; }
[data-testid="stSidebar"] { background: #20282f; }
[data-testid="stSidebarNav"] { display: none; }
[data-testid="stSidebar"] *, [data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3, [data-testid="stSidebar"] p { color: #f4f6f7 !important; }
[data-testid="stHeader"] { background: transparent; }
h1, h2, h3, p, label, [data-testid="stMarkdownContainer"] { color: #111417; }
h1 { font-size: 1.65rem !important; margin-bottom: .2rem !important; letter-spacing: 0; }
h2 { font-size: 1.2rem !important; margin-top: .8rem !important; letter-spacing: 0; }
h3 { font-size: 1rem !important; letter-spacing: 0; }
[data-testid="stMetric"] { background: #ffffff; border: 1px solid #aab0b5; border-radius: 4px; padding: .65rem .75rem; min-height: 92px; }
[data-testid="stMetricLabel"] { color: #4e5961; }
[data-testid="stMetricValue"] { color: #111417; font-size: 1.05rem; line-height: 1.25; white-space: normal; overflow: visible; }
[data-testid="stMetricValue"] > div { font-size: 1.05rem !important; white-space: normal !important; text-overflow: clip !important; overflow: visible !important; }
[data-testid="stDataFrame"], [data-testid="stTable"] { border: 1px solid #aab0b5; background: white; }
.status-real { display:inline-block; border:1px solid #39704f; background:#edf6f0; color:#24573d; padding:3px 8px; }
.status-demo { display:inline-block; border:1px solid #6c7680; background:#f3f5f6; color:#39434a; padding:3px 8px; }
.quality-warning { border-left:4px solid #9a7328; background:#fff7e6; padding:10px 12px; color:#2b2b2b; }
.chain { font-weight:600; color:#24343d; padding:8px 0 12px; }
.muted { color:#58636b; }
div[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 4px; border-color:#aab0b5; background:#fff; }
button { border-radius: 4px !important; }
</style>
"""


def apply_styles() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
