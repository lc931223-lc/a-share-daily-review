from __future__ import annotations

import pandas as pd

from src.feedback.backtest import ERROR_TYPES, run_as_of_backtest


def _history(periods: int = 90) -> tuple[pd.DataFrame, dict]:
    rows = []
    stocks = [
        ("000001.SZ", "BANK", 1.0),
        ("000002.SZ", "PROPERTY", 1.4),
        ("300001.SZ", "TECH", 1.8),
        ("600001.SH", "BANK", 0.8),
        ("688001.SH", "TECH", 1.6),
        ("002001.SZ", "PROPERTY", 1.2),
    ]
    for index, timestamp in enumerate(pd.bdate_range("2025-01-01", periods=periods)):
        for code, industry, slope in stocks:
            close = 10 + index * 0.03 * slope
            rows.append(
                {
                    "trade_date": timestamp.date().isoformat(),
                    "ts_code": code,
                    "close": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "pct_chg": 0.3 * slope,
                    "amount": 1_000_000 * slope,
                }
            )
    metadata = {code: {"industry": industry, "stock_name": code} for code, industry, _ in stocks}
    return pd.DataFrame(rows), metadata


def test_future_changes_do_not_change_as_of_prediction():
    frame, metadata = _history()
    target = "2025-02-14"
    first = run_as_of_backtest(frame, metadata, start=target, end=target)
    changed = frame.copy()
    changed.loc[changed["trade_date"] > target, ["close", "high", "low", "pct_chg"]] *= 10
    second = run_as_of_backtest(changed, metadata, start=target, end=target)
    assert first["predictions"] == second["predictions"]
    assert first["validations"] != second["validations"]


def test_backtest_has_required_records_metrics_and_known_error_types():
    frame, metadata = _history()
    result = run_as_of_backtest(frame, metadata, start="2025-01-20", end="2025-04-30")
    prediction = result["predictions"][0]
    validation = result["validations"][0]
    assert {
        "prediction_date",
        "source_review",
        "theme_prediction",
        "style_prediction",
        "leader_candidates",
        "next_day_plan",
        "inflection_candidates",
        "risk_points",
        "confidence_level",
    } <= prediction.keys()
    assert {
        "validation_date",
        "actual_market_state",
        "actual_theme_result",
        "theme_return_5d",
        "theme_return_10d",
        "theme_return_20d",
        "leader_result",
        "stock_result",
        "max_gain",
        "max_drawdown",
        "error_type",
    } <= validation.keys()
    assert set(validation["error_type"]) <= ERROR_TYPES
    assert result["metrics"]["theme_top1_accuracy"]["denominator"] > 0
    assert result["meta"]["strict_as_of"] is True
