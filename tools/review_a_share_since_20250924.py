from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import akshare as ak
import numpy as np
import pandas as pd


START = "2025-09-24"
END = "2026-08-28"
OUT_DIR = Path("data/market_reviews/2025-09-24_to_2026-08-28")


@dataclass(frozen=True)
class Symbol:
    code: str
    name: str


INDEXES = [
    Symbol("sh000001", "上证指数"),
    Symbol("sz399001", "深证成指"),
    Symbol("sz399006", "创业板指"),
    Symbol("sh000300", "沪深300"),
    Symbol("sh000905", "中证500"),
    Symbol("sh000852", "中证1000"),
    Symbol("sh000688", "科创50"),
]


def fetch_index(symbol: Symbol) -> pd.DataFrame:
    df = ak.stock_zh_index_daily(symbol=symbol.code).copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["date"] >= START) & (df["date"] <= END)].copy()
    df = df.sort_values("date").reset_index(drop=True)
    df["symbol"] = symbol.code
    df["name"] = symbol.name
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def max_drawdown(series: pd.Series) -> tuple[float, str, str]:
    values = series.to_numpy(dtype=float)
    dates = series.index
    peak = np.maximum.accumulate(values)
    dd = values / peak - 1
    trough_i = int(np.nanargmin(dd))
    peak_i = int(np.nanargmax(values[: trough_i + 1]))
    return float(dd[trough_i]), str(dates[peak_i].date()), str(dates[trough_i].date())


def summarize_index(df: pd.DataFrame) -> dict:
    s = df.set_index("date")["close"]
    ret = s.iloc[-1] / s.iloc[0] - 1
    mdd, peak_date, trough_date = max_drawdown(s)
    return {
        "name": df["name"].iloc[0],
        "symbol": df["symbol"].iloc[0],
        "start_date": str(s.index[0].date()),
        "end_date": str(s.index[-1].date()),
        "start_close": round(float(s.iloc[0]), 3),
        "end_close": round(float(s.iloc[-1]), 3),
        "return_pct": round(ret * 100, 2),
        "max_drawdown_pct": round(mdd * 100, 2),
        "drawdown_peak": peak_date,
        "drawdown_trough": trough_date,
        "period_high": round(float(s.max()), 3),
        "period_high_date": str(s.idxmax().date()),
        "period_low": round(float(s.min()), 3),
        "period_low_date": str(s.idxmin().date()),
    }


def close_panel(index_data: dict[str, pd.DataFrame]) -> pd.DataFrame:
    panel = []
    for symbol, df in index_data.items():
        item = df[["date", "close"]].copy()
        item = item.rename(columns={"close": symbol})
        panel.append(item.set_index("date"))
    return pd.concat(panel, axis=1).dropna(how="any")


def buy_and_hold(panel: pd.DataFrame) -> dict:
    returns = panel.pct_change().fillna(0)
    rows = {}
    for col in panel.columns:
        equity = (1 + returns[col]).cumprod()
        mdd, peak, trough = max_drawdown(equity)
        rows[col] = {
            "return_pct": round((equity.iloc[-1] - 1) * 100, 2),
            "max_drawdown_pct": round(mdd * 100, 2),
            "drawdown_peak": peak,
            "drawdown_trough": trough,
        }
    return rows


def trend_filter(panel: pd.DataFrame, fast: int = 20, slow: int = 60) -> dict:
    returns = panel.pct_change().fillna(0)
    rows = {}
    for col in panel.columns:
        ma_fast = panel[col].rolling(fast).mean()
        ma_slow = panel[col].rolling(slow).mean()
        signal = ((panel[col] > ma_fast) & (ma_fast > ma_slow)).shift(1).fillna(False)
        strat_ret = returns[col].where(signal, 0)
        equity = (1 + strat_ret).cumprod()
        mdd, peak, trough = max_drawdown(equity)
        rows[col] = {
            "return_pct": round((equity.iloc[-1] - 1) * 100, 2),
            "max_drawdown_pct": round(mdd * 100, 2),
            "exposure_pct": round(float(signal.mean()) * 100, 2),
            "max_drawdown_peak": peak,
            "max_drawdown_trough": trough,
        }
    return rows


def relative_strength_rotation(panel: pd.DataFrame) -> dict:
    returns = panel.pct_change().fillna(0)
    ma20 = panel.rolling(20).mean()
    ma60 = panel.rolling(60).mean()
    mom60 = panel / panel.shift(60) - 1
    eligible = (panel > ma20) & (ma20 > ma60)
    chosen = []
    daily_ret = []
    for i, date in enumerate(panel.index):
        if i == 0:
            chosen.append("cash")
            daily_ret.append(0.0)
            continue
        prev = panel.index[i - 1]
        prev_eligible = eligible.loc[prev]
        candidates = prev_eligible[prev_eligible].index.tolist()
        if not candidates:
            chosen.append("cash")
            daily_ret.append(0.0)
            continue
        pick = mom60.loc[prev, candidates].sort_values(ascending=False).index[0]
        chosen.append(pick)
        daily_ret.append(float(returns.loc[date, pick]))
    equity = pd.Series(1 + np.array(daily_ret), index=panel.index).cumprod()
    mdd, peak, trough = max_drawdown(equity)
    counts = pd.Series(chosen).value_counts().to_dict()
    return {
        "return_pct": round((equity.iloc[-1] - 1) * 100, 2),
        "max_drawdown_pct": round(mdd * 100, 2),
        "drawdown_peak": peak,
        "drawdown_trough": trough,
        "cash_days": int(counts.get("cash", 0)),
        "holding_days_by_symbol": {k: int(v) for k, v in counts.items() if k != "cash"},
        "last_signal": chosen[-1],
    }


def monthly_returns(panel: pd.DataFrame) -> pd.DataFrame:
    monthly = panel.resample("ME").last().pct_change()
    if panel.index[0] not in monthly.index:
        base = panel.iloc[0]
        first_month = panel[panel.index.month == panel.index[0].month].iloc[-1] / base - 1
        monthly.iloc[0] = first_month
    return (monthly * 100).round(2)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    index_data = {sym.code: fetch_index(sym) for sym in INDEXES}
    for code, df in index_data.items():
        df.to_csv(OUT_DIR / f"{code}.csv", index=False, encoding="utf-8-sig")

    panel = close_panel(index_data)
    summary = [summarize_index(df) for df in index_data.values()]
    names = {s.code: s.name for s in INDEXES}
    result = {
        "window": {"start": START, "end": END, "trading_days": int(len(panel))},
        "symbol_names": names,
        "index_summary": summary,
        "buy_and_hold": buy_and_hold(panel),
        "trend_filter_20_60": trend_filter(panel),
        "relative_strength_rotation": relative_strength_rotation(panel),
    }

    monthly = monthly_returns(panel.rename(columns=names))
    monthly.to_csv(OUT_DIR / "monthly_returns_pct.csv", encoding="utf-8-sig")
    (OUT_DIR / "review_metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"Saved to {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
