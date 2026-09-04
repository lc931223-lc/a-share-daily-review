from __future__ import annotations

from datetime import date

import pandas as pd

import src.market_packet.collector as collector_module
from src.market_packet.collector import MarketPacketCollector
from src.market_packet.source_router import SourceRouter


class BoardSnapshotAk:
    def __init__(self):
        self.snapshot_calls = 0
        self.history_calls = 0

    def stock_board_industry_name_em(self):
        self.snapshot_calls += 1
        return pd.DataFrame([{"板块名称": f"行业{i}", "板块代码": f"BK{i:04d}", "涨跌幅": i / 10, "成交额": i * 100} for i in range(35)])

    def stock_board_industry_hist_em(self, **_kwargs):
        self.history_calls += 1
        raise AssertionError("N+1 history lookup must not be called")


def test_source_routes_are_explicit():
    router = SourceRouter()
    assert router.route("industry_board")["request_mode"] == "single_snapshot"
    assert router.route("announcements")["primary"] == "cninfo.official"


def test_current_board_collection_uses_one_snapshot_call(tmp_path, monkeypatch):
    fake = BoardSnapshotAk()
    monkeypatch.setattr(collector_module, "ak", fake)
    collector = MarketPacketCollector(raw_root=tmp_path)
    monkeypatch.setattr(collector_module, "datetime", _CurrentDateTime)
    result = collector._collect_board_daily(date(2026, 9, 5), "industry")
    assert result.quality == "PASS"
    assert fake.snapshot_calls == 1
    assert fake.history_calls == 0


def test_missing_historical_board_snapshot_is_unavailable_without_network(tmp_path, monkeypatch):
    fake = BoardSnapshotAk()
    monkeypatch.setattr(collector_module, "ak", fake)
    collector = MarketPacketCollector(raw_root=tmp_path)
    result = collector._collect_board_daily(date(2026, 8, 31), "industry")
    assert result.quality == "UNAVAILABLE"
    assert fake.snapshot_calls == 0
    assert fake.history_calls == 0


class _CurrentDateTime:
    @classmethod
    def now(cls, _tz=None):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        return datetime(2026, 9, 5, 12, tzinfo=ZoneInfo("Asia/Shanghai"))
