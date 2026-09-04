from __future__ import annotations

from datetime import date, datetime
import json

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
    collector = MarketPacketCollector(raw_root=tmp_path / "raw", fact_root=tmp_path / "facts")
    monkeypatch.setattr(collector_module, "datetime", _CurrentDateTime)
    result = collector._collect_board_daily(date(2026, 9, 5), "industry")
    assert result.quality == "PASS"
    assert fake.snapshot_calls == 1
    assert fake.history_calls == 0


def test_current_industry_snapshot_falls_back_to_ths_batch(tmp_path, monkeypatch):
    class FallbackAk:
        def __init__(self):
            self.primary_calls = 0
            self.fallback_calls = 0

        def stock_board_industry_name_em(self):
            self.primary_calls += 1
            raise TimeoutError("eastmoney unavailable")

        def stock_board_industry_summary_ths(self):
            self.fallback_calls += 1
            return pd.DataFrame([{
                "板块": f"行业{i}", "涨跌幅": i / 10, "总成交额": i * 100,
                "上涨家数": i, "下跌家数": 30 - i,
            } for i in range(35)])

    fake = FallbackAk()
    monkeypatch.setattr(collector_module, "ak", fake)
    collector = MarketPacketCollector(raw_root=tmp_path / "raw", fact_root=tmp_path / "facts")
    monkeypatch.setattr(collector_module, "datetime", _CurrentDateTime)

    result = collector._collect_board_daily(date(2026, 9, 5), "industry")

    assert result.quality == "PASS"
    assert result.source == "ths.industry_summary"
    assert result.rows[0]["snapshot_source"] == "ths.industry_summary"
    assert fake.primary_calls == 1
    assert fake.fallback_calls == 1


def test_expired_failed_board_cache_is_retried(tmp_path, monkeypatch):
    fake = BoardSnapshotAk()
    monkeypatch.setattr(collector_module, "ak", fake)
    collector = MarketPacketCollector(raw_root=tmp_path / "raw", fact_root=tmp_path / "facts")
    monkeypatch.setattr(collector_module, "datetime", _CurrentDateTime)
    cache = collector._cache_path(date(2026, 9, 5), "industry_board_daily")
    cache.parent.mkdir(parents=True)
    cache.write_text(json.dumps({
        "source": "eastmoney.industry_snapshot",
        "data_date": "2026-09-05",
        "rows": [],
        "quality": "FAIL",
        "error": "network timeout",
        "retrieved_at": "2026-09-04T23:00:00+00:00",
        "last_attempt_at": "2026-09-04T23:00:00+00:00",
        "retry_after": "2026-09-05T00:00:00+00:00",
    }), encoding="utf-8")

    result = collector._collect_board_daily(date(2026, 9, 5), "industry")

    assert result.quality == "PASS"
    assert fake.snapshot_calls == 1


def test_missing_historical_board_snapshot_is_unavailable_without_network(tmp_path, monkeypatch):
    fake = BoardSnapshotAk()
    monkeypatch.setattr(collector_module, "ak", fake)
    collector = MarketPacketCollector(raw_root=tmp_path)
    result = collector._collect_board_daily(date(2026, 8, 31), "industry")
    assert result.quality == "UNAVAILABLE"
    assert fake.snapshot_calls == 0
    assert fake.history_calls == 0


def test_historical_board_snapshot_prefers_parquet_without_network(tmp_path, monkeypatch):
    fake = BoardSnapshotAk()
    monkeypatch.setattr(collector_module, "ak", fake)
    trade_date = date(2026, 8, 31)
    collector = MarketPacketCollector(raw_root=tmp_path / "raw", fact_root=tmp_path / "facts")
    collector.fact_store.write_dataset("industry_board_daily", trade_date, [{
        "board_type": "industry",
        "board_name": "银行",
        "source_data_date": trade_date.isoformat(),
        "change_pct": 1.2,
    }])
    result = collector._collect_board_daily(trade_date, "industry")
    assert result.rows[0]["board_name"] == "银行"
    assert result.source == "parquet.industry_board_daily"
    assert fake.snapshot_calls == 0
    assert fake.history_calls == 0


class _CurrentDateTime(datetime):
    @classmethod
    def now(cls, _tz=None):
        from zoneinfo import ZoneInfo

        return datetime(2026, 9, 5, 12, tzinfo=ZoneInfo("Asia/Shanghai"))
