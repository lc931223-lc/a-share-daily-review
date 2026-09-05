from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from src.auction.realtime_open import RealtimeOpenRouter


TZ = ZoneInfo("Asia/Shanghai")


def test_realtime_open_router_rejects_cross_date_pollution():
    router = RealtimeOpenRouter(tencent_loader=lambda _: ({}, set()), eastmoney_loader=lambda _: ({}, set()))
    with pytest.raises(ValueError, match="current-only"):
        router.load(date(2026, 9, 4), ["000001.SZ"], now=datetime(2026, 9, 5, 9, 30, tzinfo=TZ))


def test_realtime_open_router_records_fallback():
    router = RealtimeOpenRouter(
        tencent_loader=lambda _: (_ for _ in ()).throw(RuntimeError("down")),
        eastmoney_loader=lambda _: ({"000001.SZ": 10.0}, {date(2026, 9, 7)}),
    )
    source, values, fallbacks = router.load(
        date(2026, 9, 7), ["000001.SZ"], now=datetime(2026, 9, 7, 9, 30, tzinfo=TZ),
    )
    assert source == "eastmoney_realtime"
    assert values["000001.SZ"] == 10.0
    assert len(fallbacks) == 1
