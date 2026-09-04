from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from src.market_packet.trading_calendar import TradingCalendarDay, resolve_auto_trade_date


TZ = ZoneInfo("Asia/Shanghai")


def _calendar():
    open_days = {
        "2026-02-13",
        "2026-02-23",
        "2026-09-30",
        "2026-10-09",
        "2026-11-06",
    }
    days = []
    for text in (
        "2026-02-13",
        "2026-02-16",
        "2026-02-17",
        "2026-02-18",
        "2026-02-19",
        "2026-02-20",
        "2026-02-23",
        "2026-09-30",
        "2026-10-01",
        "2026-10-02",
        "2026-10-03",
        "2026-10-04",
        "2026-10-05",
        "2026-10-06",
        "2026-10-07",
        "2026-10-08",
        "2026-10-09",
        "2026-11-06",
        "2026-11-07",
        "2026-11-08",
    ):
        days.append(TradingCalendarDay(datetime.fromisoformat(text).date(), text in open_days))
    return days


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=TZ)


def test_auto_trade_date_uses_previous_day_before_close_ready():
    assert resolve_auto_trade_date("auto", now=_dt("2026-11-06T14:59:00"), calendar_days=_calendar()).isoformat() == "2026-10-09"


def test_auto_trade_date_uses_today_after_close_ready():
    assert resolve_auto_trade_date("auto", now=_dt("2026-11-06T15:05:00"), calendar_days=_calendar()).isoformat() == "2026-11-06"


def test_auto_trade_date_uses_previous_trading_day_on_saturday():
    assert resolve_auto_trade_date("auto", now=_dt("2026-11-07T16:00:00"), calendar_days=_calendar()).isoformat() == "2026-11-06"


def test_auto_trade_date_uses_previous_trading_day_on_sunday():
    assert resolve_auto_trade_date("auto", now=_dt("2026-11-08T16:00:00"), calendar_days=_calendar()).isoformat() == "2026-11-06"


def test_auto_trade_date_uses_real_calendar_for_spring_festival_close():
    assert resolve_auto_trade_date("auto", now=_dt("2026-02-18T16:00:00"), calendar_days=_calendar()).isoformat() == "2026-02-13"


def test_auto_trade_date_uses_real_calendar_for_national_day_close():
    assert resolve_auto_trade_date("auto", now=_dt("2026-10-05T16:00:00"), calendar_days=_calendar()).isoformat() == "2026-09-30"
