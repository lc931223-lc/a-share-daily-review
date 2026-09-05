import pandas as pd

from src.inflection.backtest import evaluate_forward_returns


def test_backtest_uses_only_rows_after_signal_for_forward_outcomes():
    daily = pd.DataFrame([
        {"trade_date": f"2026-09-{day:02d}", "ts_code": "000001.SZ", "close": 10 + day, "high": 10.5 + day, "low": 9.5 + day, "pct_chg": 1}
        for day in range(1, 25)
    ])
    signal = {"trade_date": "2026-09-03", "ts_code": "000001.SZ", "status": "INFLECTION_WATCH", "breakout_level": 12}

    result = evaluate_forward_returns([signal], daily)[0]

    assert result["return_1d"] == (14 / 13) - 1
    assert result["return_20d"] == (33 / 13) - 1
    assert result["max_gain_20d"] > result["return_20d"]
    assert result["broke_breakout_level"] is False
