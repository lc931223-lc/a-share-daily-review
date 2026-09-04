import altair as alt
import pandas as pd


def history_line(rows: list[dict], field: str, label: str):
    frame = pd.DataFrame(rows)
    if frame.empty or field not in frame or frame[field].dropna().empty:
        return None
    return alt.Chart(frame).mark_line(point=True, color="#2f657f").encode(
        x=alt.X("trade_date:T", title="交易日"),
        y=alt.Y(f"{field}:Q", title=label, scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("trade_date:T", title="日期"), alt.Tooltip(f"{field}:Q", title=label)],
    ).properties(height=260)
