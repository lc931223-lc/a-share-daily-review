from __future__ import annotations

import math
import statistics
from typing import Any

import pandas as pd


WINDOWS = (5, 10, 20, 60, 120, 250)


def compute_stock_features(frame: pd.DataFrame) -> dict[str, Any]:
    data = frame.sort_values("trade_date").reset_index(drop=True).copy()
    if data.empty:
        return {"quality_status": "UNAVAILABLE", "risk_flags": ["NO_DAILY_DATA"]}
    for column in ("open", "high", "low", "close", "pre_close", "pct_chg", "vol", "amount", "turnover_rate"):
        if column not in data:
            data[column] = None
        data[column] = pd.to_numeric(data[column], errors="coerce")

    current = data.iloc[-1]
    result: dict[str, Any] = {
        "trade_date": str(current["trade_date"])[:10],
        "ts_code": str(current["ts_code"]),
        "stock_name": current.get("stock_name"),
        "industry": current.get("industry"),
        "themes": current.get("themes") if isinstance(current.get("themes"), list) else [],
        "open": _value(current.get("open")), "high": _value(current.get("high")),
        "low": _value(current.get("low")), "close": _value(current.get("close")),
        "pre_close": _value(current.get("pre_close")), "pct_chg": _value(current.get("pct_chg")),
        "vol": _value(current.get("vol")), "amount": _value(current.get("amount")),
        "turnover_rate": _value(current.get("turnover_rate")),
    }
    history_count = len(data)
    result["history_observation_count"] = history_count
    result["risk_flags"] = []
    if bool(current.get("is_st")):
        result["risk_flags"].append("ST")
    if history_count < 60:
        result["risk_flags"].append("INSUFFICIENT_HISTORY")
    if current.get("vol") == 0 or pd.isna(current.get("vol")):
        result["risk_flags"].append("SUSPENDED_OR_NO_VOLUME")

    for window in (5, 20, 60):
        result[f"amount_ratio_{window}d"] = _ratio_to_prior_mean(data["amount"], window)
    for window in (60, 120, 250):
        result[f"amount_percentile_{window}d"] = _percentile_current(data["amount"], window)
    for window in (5, 20):
        result[f"volume_ratio_{window}d"] = _ratio_to_prior_mean(data["vol"], window)
    for window in (60, 120):
        result[f"turnover_percentile_{window}d"] = _percentile_current(data["turnover_rate"], window)

    returns = data["close"].pct_change()
    result["volatility_20d"] = _std_tail(returns, 20)
    volatility_series = returns.rolling(20, min_periods=15).std()
    result["volatility_percentile_120d"] = _percentile_current(volatility_series, 120)
    result.update(_up_down_structure(data))
    result.update(_pullback_structure(data))
    result.update(_daily_structure(data))
    result.update(_weekly_structure(data))
    result.update(_chip_features(data, result))
    return result


def _up_down_structure(data: pd.DataFrame) -> dict[str, Any]:
    tail = data.tail(10)
    up = tail[tail["pct_chg"] > 0]
    down = tail[tail["pct_chg"] < 0]
    up_amount = _mean(up["amount"])
    down_amount = _mean(down["amount"])
    return {
        "up_day_avg_amount_10d": up_amount,
        "down_day_avg_amount_10d": down_amount,
        "up_down_amount_ratio": _ratio(up_amount, down_amount),
        "up_day_volume_ratio": _ratio(_mean(up["vol"]), _mean(tail["vol"])),
        "down_day_volume_ratio": _ratio(_mean(down["vol"]), _mean(tail["vol"])),
    }


def _pullback_structure(data: pd.DataFrame) -> dict[str, Any]:
    if len(data) < 10:
        return {"impulse_avg_amount": None, "pullback_avg_amount": None, "pullback_volume_ratio": None}
    tail = data.tail(20).reset_index(drop=True)
    peak = int(tail["close"].idxmax())
    if peak < 2 or peak >= len(tail) - 1:
        return {"impulse_avg_amount": None, "pullback_avg_amount": None, "pullback_volume_ratio": None}
    impulse = tail.iloc[max(0, peak - 4):peak + 1]
    pullback = tail.iloc[peak + 1:]
    impulse_amount = _mean(impulse["amount"])
    pullback_amount = _mean(pullback["amount"])
    return {
        "impulse_avg_amount": impulse_amount,
        "pullback_avg_amount": pullback_amount,
        "pullback_volume_ratio": _ratio(pullback_amount, impulse_amount),
    }


def _daily_structure(data: pd.DataFrame) -> dict[str, Any]:
    close = data["close"]
    result: dict[str, Any] = {}
    for window in (5, 10, 20, 60, 120, 250):
        result[f"ma{window}"] = _tail_mean(close, window)
    for window in (5, 10, 20, 60):
        result[f"slope_ma{window}"] = _ma_slope(close, window)
    breakouts = []
    breakout_levels: dict[int, float] = {}
    for window in (20, 60, 120, 250):
        level = _prior_high(close, window)
        breakout_levels[window] = level
        flag = level is not None and _value(close.iloc[-1]) is not None and float(close.iloc[-1]) > level
        result[f"breakout_{window}d"] = flag if level is not None else None
        if flag:
            breakouts.append(window)
    breakout_type = f"BREAKOUT_{max(breakouts)}D" if breakouts else None
    recent = _recent_breakout(data, max(breakouts) if breakouts else 20)
    result.update(recent)
    result["breakout_type"] = breakout_type or recent.get("breakout_type")
    result["breakout_volume_confirmation"] = _volume_confirmation(
        _ratio_to_prior_mean(data["amount"], 20), _percentile_current(data["amount"], 120)
    )
    ma5, ma10, ma20, ma60 = (result[f"ma{x}"] for x in (5, 10, 20, 60))
    result["ma5_gt_ma10_gt_ma20"] = _ordered(ma5, ma10, ma20)
    result["ma20_gt_ma60"] = ma20 > ma60 if ma20 is not None and ma60 is not None else None
    result["close_above_ma60"] = _above(close, ma60)
    result["close_above_ma120"] = _above(close, result["ma120"])
    result["close_above_ma250"] = _above(close, result["ma250"])
    previous_ma60 = _tail_mean(close.iloc[:-1], 60)
    previous_above_ma60 = float(close.iloc[-2]) > previous_ma60 if previous_ma60 is not None and len(close) >= 2 else None
    crossed_below_ma60 = bool(previous_above_ma60 and result["close_above_ma60"] is False)
    bearish_break = bool(
        result["close_above_ma60"] is False
        and result["ma20_gt_ma60"] is False
        and (result.get("slope_ma60") or 0) < 0
        and (_value(data["pct_chg"].iloc[-1]) or 0) <= -3
    )
    result["trend_broken"] = crossed_below_ma60 or bearish_break
    return result


def _recent_breakout(data: pd.DataFrame, window: int) -> dict[str, Any]:
    if len(data) <= window:
        return {"days_since_breakout": None, "breakout_hold_days": None, "breakout_failure": None, "breakout_hold_status": "UNAVAILABLE"}
    close = data["close"].reset_index(drop=True)
    for offset in range(0, min(10, len(close) - window)):
        index = len(close) - 1 - offset
        level = close.iloc[max(0, index - window):index].max()
        if pd.notna(level) and close.iloc[index] > level:
            held = bool((close.iloc[index:] >= level).all())
            return {
                "days_since_breakout": offset,
                "breakout_hold_days": offset + 1 if held else 0,
                "breakout_failure": not held,
                "breakout_hold_status": "BREAKOUT_HELD" if held else "BREAKOUT_FAILED",
                "breakout_type": f"BREAKOUT_{window}D",
                "breakout_level": float(level),
            }
    return {"days_since_breakout": None, "breakout_hold_days": 0, "breakout_failure": False, "breakout_hold_status": "BREAKOUT_UNCONFIRMED"}


def _weekly_structure(data: pd.DataFrame) -> dict[str, Any]:
    indexed = data.copy()
    indexed.index = pd.to_datetime(indexed["trade_date"])
    weekly = indexed.resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last", "vol": "sum", "amount": "sum"}).dropna(subset=["close"])
    result: dict[str, Any] = {"weekly_observation_count": len(weekly)}
    for window in (5, 10, 20, 40, 52):
        result[f"wma{window}"] = _tail_mean(weekly["close"], window)
    for window in (5, 10, 20):
        result[f"slope_wma{window}"] = _ma_slope(weekly["close"], window)
    breaks = []
    for window in (12, 26, 52):
        level = _prior_high(weekly["close"], window)
        flag = level is not None and float(weekly["close"].iloc[-1]) > level
        result[f"week_breakout_{window}w"] = flag if level is not None else None
        if flag:
            breaks.append(window)
    result["weekly_breakout_type"] = f"WEEK_BREAKOUT_{max(breaks)}W" if breaks else None
    result["weekly_amount_percentile_52w"] = _percentile_current(weekly["amount"], 52)
    result["wma5_gt_wma10_gt_wma20"] = _ordered(result["wma5"], result["wma10"], result["wma20"])
    return result


def _chip_features(data: pd.DataFrame, result: dict[str, Any]) -> dict[str, Any]:
    tail = data.tail(20)
    spread = (tail["high"] - tail[["open", "close"]].max(axis=1)) / tail["close"].replace(0, math.nan)
    body = (tail["close"] / tail["open"].replace(0, math.nan) - 1)
    upper_shadow = float((spread >= 0.03).mean()) if not spread.dropna().empty else None
    large_negative = float((body <= -0.05).mean()) if not body.dropna().empty else None
    high_level = result.get("amount_percentile_120d") is not None and result["amount_percentile_120d"] >= 90
    distribution = bool(
        high_level
        and (result.get("turnover_percentile_120d") or 0) >= 90
        and (result.get("volatility_percentile_120d") or 0) >= 80
        and (upper_shadow or 0) >= 0.15
        and (large_negative or 0) >= 0.05
    )
    return {
        "upper_shadow_frequency_20d": upper_shadow,
        "large_negative_candle_frequency_20d": large_negative,
        "high_level_turnover_percentile": result.get("turnover_percentile_120d"),
        "high_level_volatility_percentile": result.get("volatility_percentile_120d"),
        "breakout_retest_hold": result.get("breakout_hold_status") == "BREAKOUT_HELD",
        "capacity_confirmation": None,
        "breadth_confirmation": None,
        "distribution_warning": distribution,
        "positive_catalyst_fatigue": None,
    }


def _ratio_to_prior_mean(series: pd.Series, window: int) -> float | None:
    if len(series) <= window or pd.isna(series.iloc[-1]):
        return None
    return _ratio(float(series.iloc[-1]), _mean(series.iloc[-window - 1:-1]))


def _percentile_current(series: pd.Series, window: int) -> float | None:
    valid = series.dropna().tail(window)
    if len(valid) < max(5, int(window * 0.6)):
        return None
    return float((valid <= valid.iloc[-1]).mean() * 100)


def _std_tail(series: pd.Series, window: int) -> float | None:
    valid = series.dropna().tail(window)
    return float(valid.std()) if len(valid) >= max(5, window // 2) else None


def _mean(series: pd.Series) -> float | None:
    valid = series.dropna()
    return float(valid.mean()) if not valid.empty else None


def _tail_mean(series: pd.Series, window: int) -> float | None:
    valid = series.dropna().tail(window)
    return float(valid.mean()) if len(valid) >= window else None


def _ma_slope(series: pd.Series, window: int, periods: int = 5) -> float | None:
    ma = series.rolling(window, min_periods=window).mean().dropna()
    if len(ma) <= periods or ma.iloc[-periods - 1] == 0:
        return None
    return float(ma.iloc[-1] / ma.iloc[-periods - 1] - 1)


def _prior_high(series: pd.Series, window: int) -> float | None:
    prior = series.iloc[-window - 1:-1].dropna()
    return float(prior.max()) if len(prior) >= window else None


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    return numerator / denominator if numerator is not None and denominator not in {None, 0} else None


def _value(value: Any) -> float | None:
    return None if value is None or pd.isna(value) else float(value)


def _ordered(*values: float | None) -> bool | None:
    return all(a > b for a, b in zip(values, values[1:])) if all(value is not None for value in values) else None


def _above(series: pd.Series, level: float | None) -> bool | None:
    return float(series.iloc[-1]) > level if level is not None and pd.notna(series.iloc[-1]) else None


def _volume_confirmation(ratio: float | None, percentile: float | None) -> str | None:
    if ratio is None or percentile is None:
        return None
    if ratio >= 1.5 and percentile >= 80:
        return "HIGH_VOLUME_CONFIRMED"
    if ratio < 1:
        return "LOW_VOLUME_BREAKOUT"
    return "NORMAL_VOLUME"
