from __future__ import annotations

import json
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pandas as pd

import src.market_packet.collector as collector_module
from src.market_packet.announcement_collector import _core_stock_codes
from src.market_packet.collector import CollectedDataset, MarketPacketCollector
from src.market_packet.packet_builder import compact_packet
from src.storage.fact_store import FactStore


def _dataset(name: str, rows: list[dict]) -> CollectedDataset:
    return CollectedDataset(name, f"fixture.{name}", date(2026, 9, 4), datetime.now(UTC), rows, "PASS" if rows else "EMPTY_VALID", "historical", False)


def test_announcement_core_pool_includes_each_required_group():
    datasets = {
        "limit_up": _dataset("limit_up", [{"代码": "000001"}]),
        "limit_down": _dataset("limit_down", [{"代码": "000002"}]),
        "previous_limit": _dataset("previous_limit", [{"代码": "000003"}]),
        "failed_limit": _dataset("failed_limit", []),
        "dragon_tiger_daily": _dataset("dragon_tiger_daily", []),
        "tushare_daily_all": _dataset("tushare_daily_all", [{"ts_code": "000004.SZ", "amount": 999}]),
    }
    codes = _core_stock_codes(datasets, 20, extra_codes=["000005", "000006"])
    assert codes[:4] == ["000001", "000002", "000003", "000004"]
    assert {"000005", "000006"} <= set(codes)


def test_tushare_core_skips_optional_endpoints_by_default(tmp_path, monkeypatch):
    calls: list[str] = []

    class Pro:
        def trade_cal(self, **_kwargs):
            calls.append("trade_cal")
            return pd.DataFrame([{"cal_date": "20260904", "is_open": 1}])

        def stock_basic(self, **_kwargs):
            calls.append("stock_basic")
            return pd.DataFrame([{"ts_code": "000001.SZ", "name": "平安银行"}])

        def daily(self, **kwargs):
            calls.append("daily")
            return pd.DataFrame([{"ts_code": "000001.SZ", "trade_date": kwargs["trade_date"], "amount": 1, "pct_chg": 1}])

        def daily_basic(self, **_kwargs):
            calls.append("daily_basic")
            return pd.DataFrame()

        def adj_factor(self, **_kwargs):
            calls.append("adj_factor")
            return pd.DataFrame()

    class Ts:
        @staticmethod
        def pro_api(_token):
            return Pro()

    monkeypatch.setattr(collector_module, "ts", Ts())
    monkeypatch.setenv("TUSHARE_TOKEN", "configured-for-test")
    monkeypatch.delenv("MARKET_PACKET_INCLUDE_DAILY_BASIC", raising=False)
    monkeypatch.delenv("MARKET_PACKET_INCLUDE_ADJ_FACTOR", raising=False)
    collector = MarketPacketCollector(raw_root=tmp_path)
    datasets: dict[str, CollectedDataset] = {}
    collector._collect_tushare_core(datasets, date(2026, 9, 4))
    assert "daily" in calls
    assert "daily_basic" not in calls
    assert "adj_factor" not in calls
    assert datasets["tushare_daily_basic_all"].quality == "UNAVAILABLE"
    assert datasets["tushare_adj_factor_all"].quality == "UNAVAILABLE"


def test_missing_tushare_token_records_credential_status_without_api_call(tmp_path, monkeypatch):
    class Ts:
        @staticmethod
        def pro_api(_token):
            raise AssertionError("Tushare must not be called without credentials")

    monkeypatch.setattr(collector_module, "ts", Ts())
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    collector = MarketPacketCollector(raw_root=tmp_path)
    datasets: dict[str, CollectedDataset] = {}
    collector._collect_tushare_core(datasets, date(2026, 9, 4))
    assert datasets["tushare_credential"].quality == "UNAVAILABLE"
    assert datasets["tushare_credential"].error_type == "credentials"


def test_tushare_low_frequency_reference_endpoints_use_cache(tmp_path):
    calls = {"trade_cal": 0, "stock_basic": 0}

    class Pro:
        def trade_cal(self, **_kwargs):
            calls["trade_cal"] += 1
            return pd.DataFrame([{"cal_date": "20260904", "is_open": 1}])

        def stock_basic(self, **_kwargs):
            calls["stock_basic"] += 1
            return pd.DataFrame([{"ts_code": "000001.SZ", "name": "平安银行"}])

    collector = MarketPacketCollector(raw_root=tmp_path / "raw", reference_root=tmp_path / "reference")
    collector._collect_tushare_trade_cal(Pro(), date(2026, 9, 4))
    collector._collect_tushare_trade_cal(Pro(), date(2026, 9, 4))
    collector._collect_tushare_stock_basic(Pro(), date(2026, 9, 4))
    collector._collect_tushare_stock_basic(Pro(), date(2026, 9, 4))
    assert calls == {"trade_cal": 1, "stock_basic": 1}


def test_board_snapshot_uses_exact_partition_names_and_can_be_reloaded(tmp_path):
    store = FactStore(tmp_path / "facts")
    trade_date = date(2026, 9, 4)
    rows = [{
        "board_name": "银行",
        "board_code": "BK0475",
        "change_pct": 1.2,
        "amount": 10,
        "source_tags": ["eastmoney", "daily_snapshot"],
    }]
    store.write_dataset("industry_board_daily", trade_date, rows)
    assert store.read_dataset("industry_board_daily", trade_date) == rows


def test_packet_persistence_does_not_mislabel_derived_boards_as_raw_snapshots(tmp_path):
    packet = json.loads(open("data/market_packets/2026-09-04.json", encoding="utf-8").read())
    store = FactStore(tmp_path / "facts")
    written = store.persist_packet(packet, tmp_path / "catalog.db")
    names = {item.dataset for item in written}

    assert {"industries", "themes"} <= names
    assert "industry_board_daily" not in names
    assert "concept_board_daily" not in names


def test_live_board_snapshot_is_persisted_as_raw_daily_fact(tmp_path, monkeypatch):
    class Ak:
        @staticmethod
        def stock_board_industry_name_em():
            return pd.DataFrame([{"板块名称": "银行", "板块代码": "BK0475", "涨跌幅": 1.2}])

    monkeypatch.setattr(collector_module, "ak", Ak())
    collector = MarketPacketCollector(raw_root=tmp_path / "raw", fact_root=tmp_path / "facts")
    trade_date = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    result = collector._collect_board_daily(trade_date, "industry")

    assert result.rows
    assert collector.fact_store.read_dataset("industry_board_daily", trade_date)[0]["board_name"] == "银行"


def test_historical_board_reader_rejects_mislabeled_derived_rows(tmp_path):
    trade_date = date(2026, 9, 4)
    collector = MarketPacketCollector(raw_root=tmp_path / "raw", fact_root=tmp_path / "facts")
    collector.fact_store.write_dataset("industry_board_daily", trade_date, [{
        "name": "银行",
        "source": "limit pools",
        "quality": "PARTIAL",
    }])

    result = collector._collect_board_daily(trade_date, "industry")

    assert result.quality == "UNAVAILABLE"
    assert result.rows == []


def test_compact_packet_prioritizes_research_fields_and_is_materially_smaller():
    packet = json.loads(open("data/market_packets/2026-09-04.json", encoding="utf-8").read())
    compact = compact_packet(packet)
    required = {
        "market_overview", "sector_strength", "sector_weakness", "theme_strength", "theme_weakness",
        "limit_up_ladder", "core_stocks", "important_announcements", "risk_announcements",
        "official_policies", "previous_review", "tomorrow_check_context", "data_quality",
    }
    assert required <= set(compact)
    assert "announcements" not in compact
    assert "policies" not in compact
    full_size = len(json.dumps(packet, ensure_ascii=False, separators=(",", ":")).encode())
    compact_size = len(json.dumps(compact, ensure_ascii=False, separators=(",", ":")).encode())
    assert compact_size < full_size * 0.35
    assert set(compact["data_quality"]) <= {"status", "score", "domains", "sources", "missing", "conflicts", "unavailable", "partial"}
