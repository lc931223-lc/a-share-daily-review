from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src.config.environment import load_project_environment

try:
    import akshare as ak
except Exception:  # pragma: no cover - surfaced through runtime error
    ak = None

try:
    import tushare as ts
except Exception:  # pragma: no cover - surfaced through runtime error
    ts = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
MARKET_PACKET_CLOSE_READY = time(15, 5)


@dataclass(frozen=True)
class TradingCalendarDay:
    cal_date: date
    is_open: bool


def resolve_auto_trade_date(
    value: str,
    *,
    now: datetime | None = None,
    calendar_days: list[TradingCalendarDay] | None = None,
    cache_root: Path | None = None,
) -> date:
    if value != "auto":
        return date.fromisoformat(value)
    current = now.astimezone(SHANGHAI_TZ) if now else datetime.now(SHANGHAI_TZ)
    days = calendar_days or load_trading_calendar(current.date(), cache_root=cache_root)
    open_days = sorted(day.cal_date for day in days if day.is_open)
    if current.date() in open_days and current.time() >= MARKET_PACKET_CLOSE_READY:
        return current.date()
    previous = [day for day in open_days if day < current.date()]
    if not previous:
        raise RuntimeError("No previous A-share trading day is available from the trading calendar")
    return previous[-1]


def load_trading_calendar(anchor: date, *, cache_root: Path | None = None) -> list[TradingCalendarDay]:
    root = cache_root or PROJECT_ROOT / "data" / "reference"
    path = root / f"trade_calendar_{anchor.year}.json"
    if path.exists():
        return _read_calendar(path)
    rows = _fetch_tushare_calendar(anchor) or _fetch_akshare_calendar(anchor)
    if not rows:
        raise RuntimeError("Unable to load a real A-share trading calendar from cache, Tushare, or AKShare")
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "source": rows[0].get("source", "unknown"),
        "year": anchor.year,
        "retrieved_at": datetime.now(SHANGHAI_TZ).isoformat(),
        "rows": rows,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return _rows_to_calendar(rows)


def _read_calendar(path: Path) -> list[TradingCalendarDay]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return _rows_to_calendar(payload.get("rows", []))


def _fetch_tushare_calendar(anchor: date) -> list[dict] | None:
    load_project_environment()
    token = os.environ.get("TUSHARE_TOKEN")
    if ts is None or not token:
        return None
    start = date(anchor.year, 1, 1).strftime("%Y%m%d")
    end = date(anchor.year, 12, 31).strftime("%Y%m%d")
    try:
        frame = ts.pro_api(token).trade_cal(exchange="", start_date=start, end_date=end)
    except Exception:
        return None
    if frame is None or frame.empty:
        return None
    rows = []
    for row in frame.to_dict("records"):
        rows.append({"cal_date": str(row.get("cal_date")), "is_open": int(row.get("is_open") or 0), "source": "tushare.trade_cal"})
    return rows


def _fetch_akshare_calendar(anchor: date) -> list[dict] | None:
    if ak is None:
        return None
    try:
        frame = ak.tool_trade_date_hist_sina()
    except Exception:
        return None
    if frame is None or frame.empty:
        return None
    rows = []
    for row in frame.to_dict("records"):
        value = row.get("trade_date") or row.get("交易日") or row.get("date")
        if value is None:
            continue
        cal_date = _parse_date(value)
        if cal_date and cal_date.year == anchor.year:
            rows.append({"cal_date": cal_date.strftime("%Y%m%d"), "is_open": 1, "source": "akshare.tool_trade_date_hist_sina"})
    return rows or None


def _rows_to_calendar(rows: list[dict]) -> list[TradingCalendarDay]:
    days: list[TradingCalendarDay] = []
    for row in rows:
        cal_date = _parse_date(row.get("cal_date") or row.get("trade_date") or row.get("交易日"))
        if cal_date is None:
            continue
        days.append(TradingCalendarDay(cal_date=cal_date, is_open=bool(int(row.get("is_open", 1) or 0))))
    return days


def _parse_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value)
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def previous_calendar_date(value: date) -> date:
    return value - timedelta(days=1)
