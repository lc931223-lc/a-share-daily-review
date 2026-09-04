from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from src.market_packet.collector import CollectedDataset
from src.market_packet.packet_builder import compact_packet, quality_report
from src.market_packet.quality_gate import audit_packet
from src.market_packet.normalizer import normalize_packet_data


def test_market_packet_schema_accepts_generated_packet():
    packet = json.loads(Path("data/market_packets/2026-09-02.json").read_text(encoding="utf-8"))
    schema = json.loads(Path("schemas/market_packet.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(packet)
    assert packet["meta"]["final_judgement_owner"] == "chatgpt"
    assert "rating" not in json.dumps(packet["themes"], ensure_ascii=False)


def test_compact_packet_keeps_chatgpt_inputs_small():
    packet = json.loads(Path("data/market_packets/2026-09-02.json").read_text(encoding="utf-8"))
    compact = compact_packet(packet)
    assert set(compact) >= {"market_overview", "limit_up_down", "theme_strength", "core_stocks"}
    assert len(compact["core_stocks"]) <= 80


def test_quality_report_separates_null_from_zero():
    packet = json.loads(Path("data/market_packets/2026-09-02.json").read_text(encoding="utf-8"))
    report = quality_report(packet)
    assert report["data_quality"]["score"] >= 0
    assert packet["market_breadth"]["rise_count"] is not None
    assert packet["market_breadth"]["fall_count"] is not None
    assert "market_breadth" not in report["missing_data"]


def test_quality_gate_marks_api_failure_without_silent_fill():
    packet = {
        "indices": [],
        "liquidity": {"sh_sz_turnover": None, "total_market_turnover": None, "previous_turnover": None},
        "market_breadth": {},
        "industries": [],
        "themes": [],
        "stocks": [],
        "announcements": [],
        "policies": [],
        "previous_review": {},
        "missing_data": [],
    }
    datasets = {
        name: CollectedDataset(
            name=name,
            source=f"source.{name}",
            data_date=date(2026, 9, 2),
            retrieved_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            rows=[],
            quality="FAIL",
            freshness="historical",
            is_cached=False,
            error="forced failure",
        )
        for name in ("limit_up", "failed_limit", "limit_down", "previous_limit", "dragon_tiger_daily")
    }
    audited = audit_packet(packet, datasets)
    assert audited["data_quality"]["status"] == "FAIL"
    assert audited["data_quality"]["score"] <= 69
    assert audited["limit_up_down"] if "limit_up_down" in audited else True
    assert "limit_pools" in audited["missing_data"]


def test_cache_metadata_records_requested_data_date():
    raw = json.loads(Path("data/raw/market_packets/2026-09-02/limit_up.json").read_text(encoding="utf-8"))
    assert raw["data_date"] == "2026-09-02"
    assert raw["source"].startswith("akshare.")


def test_official_announcements_and_policies_raise_quality_without_codex_judgement():
    packet = {
        "indices": [{"quality": "PASS"} for _ in range(5)],
        "liquidity": {"sh_sz_turnover": 1, "total_market_turnover": 10, "previous_turnover": 9},
        "market_breadth": {"quality": "PASS", "rise_count": 1, "fall_count": 1, "flat_count": 0, "source": "tushare.daily"},
        "industries": [{"name": f"行业{i}", "change_pct": 1.0} for i in range(30)],
        "themes": [{"theme_name": f"概念{i}", "change_pct": 1.0} for i in range(50)],
        "stocks": [{"stock_code": f"{i:06d}"} for i in range(80)],
        "announcements": [{"title": "公司正式公告", "evidence_level": "A"}],
        "policies": [{"title": "国务院政策文件", "evidence_level": "A"}],
        "previous_review": {},
        "missing_data": [],
    }
    datasets = {
        name: CollectedDataset(
            name=name,
            source=f"source.{name}",
            data_date=date(2026, 9, 2),
            retrieved_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
            rows=[{"x": 1}],
            quality="PASS",
            freshness="historical",
            is_cached=False,
        )
        for name in ("limit_up", "failed_limit", "limit_down", "previous_limit", "dragon_tiger_daily", "industry_board_daily", "concept_board_daily", "stock_top_ohlcv", "official_announcements", "official_policies")
    }
    datasets["stock_top_ohlcv"] = CollectedDataset("stock_top_ohlcv", "tushare.daily", date(2026, 9, 2), __import__("datetime").datetime.now(__import__("datetime").UTC), [{"x": 1}] * 80, "PASS", "historical", False)
    audited = audit_packet(packet, datasets)
    assert audited["data_quality"]["score"] <= 69
    assert audited["data_quality"]["status"] == "FAIL"
    assert "rating" not in json.dumps(audited["themes"], ensure_ascii=False)


def test_current_only_sources_do_not_pollute_historical_packet_fields():
    dt = __import__("datetime").datetime.now(__import__("datetime").UTC)
    empty = CollectedDataset("empty", "fixture", date(2026, 9, 2), dt, [], "FAIL", "historical", False)
    datasets = {
        "limit_up": empty,
        "failed_limit": empty,
        "limit_down": empty,
        "previous_limit": empty,
        "dragon_tiger_daily": empty,
        "northbound_hist": empty,
        "szse_margin": empty,
        "industry_fund_flow_current": CollectedDataset("industry_fund_flow_current", "akshare.current", None, dt, [{"主力净流入": 1}], "PASS", "current_only", False),
        "concept_fund_flow_current": CollectedDataset("concept_fund_flow_current", "akshare.current", None, dt, [{"主力净流入": 1}], "PASS", "current_only", False),
        "hsgt_summary": CollectedDataset("hsgt_summary", "akshare.current", None, dt, [{"当日净流入": 1}], "PASS", "current_only", False),
        "stock_top_ohlcv": empty,
        "tushare_daily_all": empty,
        "tushare_previous_daily_all": empty,
        "tushare_daily_basic_all": empty,
        "tushare_stock_basic": empty,
        "industry_board_daily": empty,
        "concept_board_daily": empty,
    }
    normalized = normalize_packet_data(date(2026, 9, 2), datasets)
    assert normalized["capital_flow"]["industry_fund_flow"] is None
    assert normalized["capital_flow"]["concept_fund_flow"] is None
    assert normalized["capital_flow"]["current_only_exclusions"][0]["status"] == "not_historical_available"
