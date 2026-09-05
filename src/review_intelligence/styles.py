from __future__ import annotations

from typing import Any

import pandas as pd

from src.review_intelligence.helpers import clamp, mean, number, percentile_rank, stock_code


TECH = ("电子", "计算机", "通信", "半导体", "软件", "互联网", "自动化", "设备")
CYCLICAL = ("煤炭", "钢铁", "有色", "化工", "建材", "石油", "航运", "机械")
CONSUMER = ("食品", "饮料", "家电", "医药", "零售", "农业", "养殖", "美容", "纺织")
FINANCIAL = ("银行", "证券", "保险", "金融")


def compute_style_rankings(
    current: pd.DataFrame,
    history: pd.DataFrame,
    metadata: dict[str, dict[str, Any]],
    packet_stocks: list[dict[str, Any]],
    inflections: dict[str, dict[str, Any]],
    previous_scores: dict[str, float],
    five_day_scores: dict[str, float] | None = None,
    twenty_day_scores: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    frame = current.copy()
    if frame.empty:
        return []
    frame["ts_code"] = frame["ts_code"].astype(str)
    frame["industry"] = frame["ts_code"].map(lambda code: str(metadata.get(code, {}).get("industry") or ""))
    frame["stock_name"] = frame["ts_code"].map(lambda code: metadata.get(code, {}).get("stock_name"))
    frame["pct_chg"] = pd.to_numeric(frame["pct_chg"], errors="coerce")
    frame["amount"] = pd.to_numeric(frame["amount"], errors="coerce")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame["amount_change"] = _amount_changes(history, frame)
    market_caps = {stock_code(row.get("stock_code")): number(row.get("market_cap")) for row in packet_stocks}
    turnovers = {stock_code(row.get("stock_code")): number(row.get("turnover_rate")) for row in packet_stocks}
    cap_values = [value for value in market_caps.values() if value is not None]
    turnover_values = [value for value in turnovers.values() if value is not None]
    cap_coverage = len(cap_values) / len(frame) if len(frame) else 0
    turnover_coverage = len(turnover_values) / len(frame) if len(frame) else 0
    low_price, high_price = frame["close"].quantile([0.25, 0.75]).tolist()

    masks: dict[str, pd.Series] = {
        "growth": frame["ts_code"].str.startswith(("300", "688")),
        "value": ~frame["ts_code"].str.startswith(("300", "688")),
        "technology": frame["industry"].map(lambda text: any(word in text for word in TECH)),
        "cyclical": frame["industry"].map(lambda text: any(word in text for word in CYCLICAL)),
        "consumer": frame["industry"].map(lambda text: any(word in text for word in CONSUMER)),
        "financial": frame["industry"].map(lambda text: any(word in text for word in FINANCIAL)),
        "high_price_position": frame["close"] >= high_price,
        "low_price_position": frame["close"] <= low_price,
        "trend_style": frame["ts_code"].isin([code for code, row in inflections.items() if row.get("status") not in (None, "NO_SIGNAL", "TREND_BROKEN")]),
        "limit_up_style": frame.apply(lambda row: _limit_up(row["ts_code"], row["pct_chg"]), axis=1),
    }
    cap_percentiles = frame["ts_code"].map(lambda code: percentile_rank(cap_values, market_caps.get(code)))
    turnover_percentiles = frame["ts_code"].map(lambda code: percentile_rank(turnover_values, turnovers.get(code)))
    masks["large_cap"] = cap_percentiles >= 75
    masks["small_cap"] = cap_percentiles <= 25
    masks["institutional_trend"] = (cap_percentiles >= 50) & masks["trend_style"]
    masks["short_term_speculation"] = masks["limit_up_style"] | (turnover_percentiles >= 75)
    masks["high_turnover"] = turnover_percentiles >= 75
    masks["low_turnover"] = turnover_percentiles <= 25

    rows = []
    five_day_scores = five_day_scores or {}
    twenty_day_scores = twenty_day_scores or {}
    for style, mask in masks.items():
        subset = frame[mask.fillna(False)]
        count = len(subset)
        avg_return = mean(subset["pct_chg"].tolist())
        breadth = float((subset["pct_chg"] > 0).mean() * 100) if count else None
        amount_change = mean(subset["amount_change"].tolist())
        limit_count = int(sum(_limit_up(row.ts_code, row.pct_chg) for row in subset.itertuples()))
        score = None if not count else clamp((avg_return or 0) * 4 + (breadth or 0) * 0.35 + clamp((amount_change or 0) * 15, -15, 15) + min(limit_count, 10), 0, 100)
        top = subset.sort_values("pct_chg", ascending=False).head(1)
        previous = number(previous_scores.get(style))
        prior_five = number(five_day_scores.get(style))
        prior_twenty = number(twenty_day_scores.get(style))
        limited_proxy = style in {"large_cap", "small_cap", "institutional_trend", "high_turnover", "low_turnover", "short_term_speculation", "value"}
        rows.append({
            "style": style, "return": avg_return, "breadth": breadth,
            "amount_change": amount_change, "limit_up_count": limit_count,
            "top_stock_performance": None if top.empty else {
                "ts_code": top.iloc[0]["ts_code"], "stock_name": top.iloc[0]["stock_name"],
                "return": number(top.iloc[0]["pct_chg"]),
            },
            "style_strength_score": round(score, 2) if score is not None else None,
            "style_change_1d": score - previous if score is not None and previous is not None else None,
            "style_change_5d": score - prior_five if score is not None and prior_five is not None else None,
            "style_change_20d": score - prior_twenty if score is not None and prior_twenty is not None else None,
            "sample_count": count,
            "coverage_status": "PARTIAL" if count and limited_proxy else "PASS" if count >= 30 else "PARTIAL" if count else "UNAVAILABLE",
            "source_coverage": cap_coverage if style in {"large_cap", "small_cap", "institutional_trend"} else turnover_coverage if style in {"high_turnover", "low_turnover", "short_term_speculation"} else 1.0,
            "methodology": "non-growth-board proxy; valuation factors unavailable" if style == "value" else "market-cap sample proxy" if style in {"large_cap", "small_cap", "institutional_trend"} else "turnover sample proxy" if style in {"high_turnover", "low_turnover", "short_term_speculation"} else "full-market daily facts",
        })
    return sorted(rows, key=lambda row: (-(row["style_strength_score"] or -1), row["style"]))


def _amount_changes(history: pd.DataFrame, current: pd.DataFrame) -> pd.Series:
    if history.empty:
        return pd.Series([float("nan")] * len(current), index=current.index)
    older = history.copy()
    older["amount"] = pd.to_numeric(older["amount"], errors="coerce")
    current_date = str(current["trade_date"].max()) if "trade_date" in current else None
    if current_date:
        older = older[older["trade_date"].astype(str) < current_date]
    recent = older.sort_values("trade_date").groupby("ts_code", group_keys=False).tail(5)
    averages = recent.groupby("ts_code")["amount"].mean()
    return current.apply(lambda row: number(row["amount"] / averages.get(row["ts_code"]) - 1) if averages.get(row["ts_code"]) else None, axis=1)


def _limit_up(code: str, change: Any) -> bool:
    value = number(change)
    if value is None:
        return False
    threshold = 29.5 if str(code).endswith(".BJ") else 19.5 if str(code).startswith(("300", "688")) else 9.5
    return value >= threshold
