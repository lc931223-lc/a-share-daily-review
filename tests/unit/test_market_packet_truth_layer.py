from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pandas as pd

import src.market_packet.collector as collector_module
from src.market_packet.collector import CollectedDataset, MarketPacketCollector
from src.market_packet.normalizer import _capital_flow
from src.market_packet.quality_gate import detect_conflicts


def _dataset(name: str, rows: list[dict]) -> CollectedDataset:
    return CollectedDataset(name, f"source.{name}", date(2026, 9, 2), datetime.now(UTC), rows, "PASS" if rows else "FAIL", "historical", False)


def test_northbound_all_null_amounts_are_unavailable():
    datasets = {
        "northbound_hist": _dataset("northbound_hist", [{"日期": "2026-09-02", "当日成交净买额": None, "买入成交额": None, "卖出成交额": None}]),
        "szse_margin": _dataset("szse_margin", []),
    }
    result = _capital_flow(date(2026, 9, 2), datasets)
    assert result["northbound"]["quality"] == "UNAVAILABLE"
    assert result["northbound"]["net_buy_amount"] is None
    assert result["northbound"]["reason"]


def test_success_cache_keeps_original_retrieved_at(tmp_path, monkeypatch):
    monkeypatch.setattr(collector_module, "ak", object())
    collector = MarketPacketCollector(raw_root=tmp_path)
    original = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)
    path = collector._cache_path(date(2026, 9, 2), "sample")
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"source": "fixture", "dataset": "sample", "retrieved_at": original.isoformat(), "data_date": "2026-09-02", "rows": [{"x": 1}], "error": None}), encoding="utf-8")
    result = collector._collect_frame("sample", "fixture", lambda: pd.DataFrame([{"x": 2}]), date(2026, 9, 2), date(2026, 9, 2), "historical")
    assert result.is_cached is True
    assert result.retrieved_at == original
    assert result.rows == [{"x": 1}]


def test_failure_cache_retries_only_after_retry_after(tmp_path, monkeypatch):
    monkeypatch.setattr(collector_module, "ak", object())
    collector = MarketPacketCollector(raw_root=tmp_path)
    now = datetime.now(UTC)
    path = collector._cache_path(date(2026, 9, 2), "sample")
    path.parent.mkdir(parents=True)
    calls = {"count": 0}

    def fetch():
        calls["count"] += 1
        return pd.DataFrame([{"x": 2}])

    payload = {"source": "fixture", "dataset": "sample", "retrieved_at": now.isoformat(), "last_attempt_at": now.isoformat(), "retry_after": (now + timedelta(minutes=10)).isoformat(), "data_date": "2026-09-02", "rows": [], "quality": "FAIL", "error": "TimeoutError"}
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert collector._collect_frame("sample", "fixture", fetch, date(2026, 9, 2), date(2026, 9, 2), "historical").quality == "FAIL"
    assert calls["count"] == 0
    payload["retry_after"] = (now - timedelta(seconds=1)).isoformat()
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert collector._collect_frame("sample", "fixture", fetch, date(2026, 9, 2), date(2026, 9, 2), "historical").rows == [{"x": 2}]
    assert calls["count"] == 1


def test_dataset_refresh_does_not_refresh_unrelated_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(collector_module, "ak", object())
    trade_date = date(2026, 9, 2)
    collector = MarketPacketCollector(raw_root=tmp_path, refresh_datasets={"northbound"})
    for name in ("northbound_hist", "limit_up"):
        path = collector._cache_path(trade_date, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"source": "fixture", "dataset": name, "retrieved_at": datetime.now(UTC).isoformat(), "data_date": "2026-09-02", "rows": [{"value": "old"}], "error": None}), encoding="utf-8")
    northbound = collector._collect_frame("northbound_hist", "fixture", lambda: pd.DataFrame([{"value": "new"}]), trade_date, trade_date, "historical")
    limit_up = collector._collect_frame("limit_up", "fixture", lambda: pd.DataFrame([{"value": "new"}]), trade_date, trade_date, "historical")
    assert northbound.rows == [{"value": "new"}]
    assert limit_up.rows == [{"value": "old"}]


def test_conflicting_official_facts_are_recorded():
    packet = {"announcements": {"records": [
        {"stock_code": "000001", "normalized_title": "同一公告", "published_at": "2026-09-02T09:00:00+08:00", "source": "巨潮"},
        {"stock_code": "000001", "normalized_title": "同一公告", "published_at": "2026-09-02T10:00:00+08:00", "source": "深交所"},
    ]}, "policies": {"records": []}}
    conflicts = detect_conflicts(packet)
    assert conflicts[0]["severity"] == "critical"
    assert conflicts[0]["resolution"] is None
