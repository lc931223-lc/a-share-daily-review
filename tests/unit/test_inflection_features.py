from datetime import date, timedelta

import pandas as pd

from src.inflection.features import compute_stock_features
from src.inflection.scoring import score_features


def _frame(days: int = 280, *, pullback: bool = False, false_breakout: bool = False) -> pd.DataFrame:
    start = date(2025, 7, 1)
    rows = []
    for index in range(days):
        close = 10 + index * 0.01
        amount = 10_000_000 + index * 10_000
        if pullback and index >= days - 5:
            close = 13 - (index - (days - 5)) * 0.05
            amount = 4_000_000
        rows.append({
            "trade_date": (start + timedelta(days=index)).isoformat(), "ts_code": "000001.SZ",
            "open": close * 0.99, "high": close * 1.01, "low": close * 0.98, "close": close,
            "pre_close": close / 1.001, "pct_chg": 0.1, "vol": amount / close,
            "amount": amount, "turnover_rate": 2 + index * 0.001,
        })
    if not pullback:
        rows[-1]["close"] = rows[-2]["close"] * 1.08
        rows[-1]["high"] = rows[-1]["close"] * 1.01
        rows[-1]["amount"] = 40_000_000
        rows[-1]["vol"] = rows[-1]["amount"] / rows[-1]["close"]
    if false_breakout:
        rows[-3]["close"] = max(row["close"] for row in rows[:-3]) * 1.02
        rows[-2]["close"] = rows[-3]["close"] * 0.95
        rows[-1]["close"] = rows[-3]["close"] * 0.94
    return pd.DataFrame(rows)


def test_volume_breakout_and_weekly_breakout_are_detected_without_future_rows():
    result = compute_stock_features(_frame())
    assert result["breakout_20d"] is True
    assert result["breakout_60d"] is True
    assert result["breakout_volume_confirmation"] == "HIGH_VOLUME_CONFIRMED"
    assert result["weekly_breakout_type"] is not None
    assert result["amount_ratio_20d"] > 1


def test_pullback_contraction_is_an_objective_ratio():
    result = compute_stock_features(_frame(pullback=True))
    assert result["pullback_volume_ratio"] < 0.5


def test_false_breakout_is_marked_failed():
    result = compute_stock_features(_frame(false_breakout=True))
    assert result["breakout_failure"] is True
    assert result["breakout_hold_status"] == "BREAKOUT_FAILED"


def test_breakout_hold_is_counted():
    frame = _frame()
    prior_high = frame.iloc[:-5]["close"].max()
    for index in range(len(frame) - 5, len(frame)):
        frame.loc[index, "close"] = prior_high * (1.01 + (index - len(frame) + 5) * 0.002)
    result = compute_stock_features(frame)
    assert result["breakout_hold_status"] == "BREAKOUT_HELD"
    assert result["breakout_hold_days"] >= 1


def test_distribution_warning_requires_combined_high_level_deterioration():
    frame = _frame()
    for index in range(len(frame) - 4, len(frame)):
        frame.loc[index, "turnover_rate"] = 20 + index
        frame.loc[index, "high"] = frame.loc[index, "close"] * 1.15
        frame.loc[index, "open"] = frame.loc[index, "close"] * 1.06
    frame.loc[len(frame) - 2, "close"] *= 0.9
    result = compute_stock_features(frame)
    scored = score_features(result)
    assert result["distribution_warning"] is True
    assert scored["status"] == "DISTRIBUTION_WARNING"


def test_missing_and_short_history_stay_partial_instead_of_zero_filled():
    frame = _frame(30)
    frame["turnover_rate"] = None
    result = compute_stock_features(frame)
    scored = score_features(result)
    assert result["amount_ratio_60d"] is None
    assert result["ma60"] is None
    assert "INSUFFICIENT_HISTORY" in result["risk_flags"]
    assert scored["score_components"]["price_volume"]["turnover_volatility_health"] is None
    assert scored["score_component_coverage"]["ratio"] < 1
    assert scored["trend_inflection_score"] <= scored["score_component_coverage"]["available_points"]


def test_suspension_is_flagged():
    frame = _frame()
    frame.loc[len(frame) - 1, "vol"] = 0
    result = compute_stock_features(frame)
    assert "SUSPENDED_OR_NO_VOLUME" in result["risk_flags"]


def test_trend_broken_requires_a_real_break_not_only_a_weak_ma60():
    frame = _frame()
    frame.loc[len(frame) - 2, "close"] = frame.iloc[-60:]["close"].mean() * 1.02
    frame.loc[len(frame) - 1, "close"] = frame.iloc[-60:]["close"].mean() * 0.95
    frame.loc[len(frame) - 1, "pct_chg"] = -5
    result = compute_stock_features(frame)
    assert result["trend_broken"] is True
    assert score_features(result)["status"] == "TREND_BROKEN"
