from __future__ import annotations

from typing import Any

import pandas as pd


HORIZONS = (1, 3, 5, 10, 20)


def evaluate_forward_returns(signals: list[dict[str, Any]], daily: pd.DataFrame) -> list[dict[str, Any]]:
    frame = daily.copy()
    frame["trade_date"] = frame["trade_date"].astype(str).str[:10]
    results = []
    for signal in signals:
        code = str(signal["ts_code"])
        signal_date = str(signal["trade_date"])[:10]
        stock = frame[frame["ts_code"] == code].sort_values("trade_date").reset_index(drop=True)
        matches = stock.index[stock["trade_date"] == signal_date].tolist()
        if not matches:
            continue
        index = matches[-1]
        entry = float(stock.loc[index, "close"])
        future = stock.iloc[index + 1:index + 21]
        row = {"trade_date": signal_date, "ts_code": code, "status": signal.get("status")}
        for horizon in HORIZONS:
            row[f"return_{horizon}d"] = float(stock.loc[index + horizon, "close"] / entry - 1) if index + horizon < len(stock) else None
        row["max_gain_20d"] = float(future["high"].max() / entry - 1) if not future.empty else None
        row["max_drawdown_20d"] = float(future["low"].min() / entry - 1) if not future.empty else None
        row["limit_up_within_20d"] = bool((pd.to_numeric(future["pct_chg"], errors="coerce") >= 9.5).any()) if not future.empty else None
        row["new_high_within_20d"] = bool((future["high"] > float(stock.iloc[:index + 1]["high"].max())).any()) if not future.empty else None
        level = signal.get("breakout_level")
        row["broke_breakout_level"] = bool((future["close"] < float(level)).any()) if level is not None and not future.empty else None
        results.append(row)
    return results
