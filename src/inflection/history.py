from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from src.adapters.tushare_market import TushareMarketAdapter
from src.market_packet.trading_calendar import load_trading_calendar
from src.storage.fact_store import FactStore


class DailyHistoryRepository:
    def __init__(
        self,
        root: Path,
        *,
        fact_store: FactStore | None = None,
        daily_loader: Callable[[date], list[dict[str, Any]]] | None = None,
    ):
        self.root = root
        self.fact_store = fact_store or FactStore(root / "data" / "facts")
        self.daily_loader = daily_loader or self._load_tushare

    def trading_days(self, target: date, count: int = 280) -> list[date]:
        days = []
        for year in range(target.year - 2, target.year + 1):
            days.extend(item.cal_date for item in load_trading_calendar(date(year, 7, 1), cache_root=self.root / "data" / "reference") if item.is_open)
        return sorted(day for day in set(days) if day <= target)[-count:]

    def ensure_history(self, target: date, *, count: int = 280) -> dict[str, Any]:
        dates = self.trading_days(target, count)
        return self._ensure_dates(dates)

    def ensure_range(self, start: date, end: date) -> dict[str, Any]:
        dates = [day for day in self.trading_days(end, 600) if start <= day <= end]
        return self._ensure_dates(dates)

    def _ensure_dates(self, dates: list[date]) -> dict[str, Any]:
        loaded = 0
        cached = 0
        failed: list[str] = []
        for trading_day in dates:
            if self.fact_store.read_dataset("stock_daily_ohlcv", trading_day):
                cached += 1
                continue
            try:
                rows = self._load_archived(trading_day) or self.daily_loader(trading_day)
                normalized = [_normalize_daily(row, trading_day) for row in rows]
                normalized = [row for row in normalized if row]
                if not normalized:
                    raise RuntimeError("empty daily rows")
                partition = self.fact_store.write_dataset("stock_daily_ohlcv", trading_day, normalized)
                if partition is not None:
                    self.fact_store._catalog([partition], self.root / "data" / "a_share_review.db")
                loaded += 1
            except Exception:
                failed.append(trading_day.isoformat())
        return {"requested_dates": len(dates), "cached_dates": cached, "loaded_dates": loaded, "failed_dates": failed}

    def query(self, start: date, end: date, codes: list[str] | None = None) -> pd.DataFrame:
        if not codes:
            return self.fact_store.query_dataset("stock_daily_ohlcv", start=start, end=end)
        import duckdb

        pattern = (self.fact_store.root / "dataset=stock_daily_ohlcv" / "trade_date=*" / "*.parquet").as_posix()
        placeholders = ",".join("?" for _ in codes)
        sql = (
            "SELECT * FROM read_parquet(?, hive_partitioning=true, union_by_name=true) "
            f"WHERE trade_date >= ? AND trade_date <= ? AND ts_code IN ({placeholders}) ORDER BY trade_date"
        )
        return duckdb.execute(sql, [pattern, start.isoformat(), end.isoformat(), *codes]).fetch_df()

    def stock_metadata(self, target: date) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        reference = self.root / "data" / "reference" / "inflection_stock_basic.json"
        payload = _read_json(reference, {})
        rows = payload.get("rows") or []
        if not rows:
            try:
                record = TushareMarketAdapter().stock_basic(target)
                rows = record.payload
                reference.parent.mkdir(parents=True, exist_ok=True)
                reference.write_text(json.dumps({"data_date": target.isoformat(), "rows": rows}, ensure_ascii=False), encoding="utf-8")
            except Exception:
                rows = []
        for row in rows:
            result[str(row.get("ts_code"))] = {
                "stock_name": row.get("name"), "industry": row.get("industry"),
                "list_date": row.get("list_date"), "is_st": str(row.get("name") or "").upper().startswith(("ST", "*ST")),
            }
        packet = _read_json(self.root / "data" / "market_packets" / f"{target.isoformat()}.json", {})
        for row in packet.get("stocks") or []:
            code = _with_suffix(row.get("stock_code") or row.get("code"))
            if code:
                result.setdefault(code, {}).update({
                    "stock_name": row.get("stock_name") or row.get("name"),
                    "industry": row.get("industry"), "themes": row.get("themes") or [],
                })
        return result

    def _load_archived(self, trading_day: date) -> list[dict[str, Any]]:
        path = self.root / "data" / "raw" / "market_packets" / trading_day.isoformat() / "tushare_daily_all.json"
        payload = _read_json(path, {})
        if not payload:
            return []
        if str(payload.get("data_date"))[:10] != trading_day.isoformat():
            raise ValueError("archived daily date mismatch")
        return payload.get("rows") or []

    @staticmethod
    def _load_tushare(trading_day: date) -> list[dict[str, Any]]:
        return TushareMarketAdapter().stock_daily(trading_day).payload


def _normalize_daily(row: dict[str, Any], trading_day: date) -> dict[str, Any] | None:
    code = row.get("ts_code")
    if not code:
        return None
    return {
        "trade_date": trading_day.isoformat(), "ts_code": str(code),
        "open": _float(row.get("open")), "high": _float(row.get("high")),
        "low": _float(row.get("low")), "close": _float(row.get("close")),
        "pre_close": _float(row.get("pre_close")), "pct_chg": _float(row.get("pct_chg")),
        "vol": _scaled(row.get("vol"), 100), "amount": _scaled(row.get("amount"), 1000),
        "turnover_rate": _float(row.get("turnover_rate")),
        "raw_vol": _float(row.get("vol")), "raw_vol_unit": "lot",
        "raw_amount": _float(row.get("amount")), "raw_amount_unit": "thousand_cny",
        "source": "tushare.daily", "quality_status": "PASS", "schema_version": "stock_daily_ohlcv.1",
    }


def _scaled(value: Any, factor: float) -> float | None:
    parsed = _float(value)
    return parsed * factor if parsed is not None else None


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _with_suffix(value: Any) -> str | None:
    code = str(value or "").split(".", 1)[0]
    if len(code) != 6: return None
    return f"{code}.{'SH' if code.startswith(('5', '6')) else 'BJ' if code.startswith(('4', '8', '9')) else 'SZ'}"


def _read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default
