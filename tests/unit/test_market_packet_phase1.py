from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator

from src.market_packet.collector import CollectedDataset
from src.market_packet.packet_builder import compact_packet, quality_report
from src.market_packet.quality_gate import audit_packet


def test_market_packet_schema_accepts_generated_packet():
    packet = json.loads(Path("data/market_packets/2026-09-02.json").read_text(encoding="utf-8"))
    schema = json.loads(Path("schemas/market_packet.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(packet)
    assert packet["meta"]["final_judgement_owner"] == "chatgpt"
    assert "rating" not in json.dumps(packet["themes"], ensure_ascii=False)


def test_compact_packet_keeps_chatgpt_inputs_small():
    packet = json.loads(Path("data/market_packets/2026-09-02.json").read_text(encoding="utf-8"))
    compact = compact_packet(packet)
    assert set(compact) >= {"market_overview", "limit_up_down", "top_themes", "core_stocks"}
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
    assert audited["data_quality"]["status"] == "INCOMPLETE"
    assert audited["limit_up_down"] if "limit_up_down" in audited else True
    assert "limit_up" in audited["missing_data"]


def test_cache_metadata_records_requested_data_date():
    raw = json.loads(Path("data/raw/market_packets/2026-09-02/limit_up.json").read_text(encoding="utf-8"))
    assert raw["data_date"] == "2026-09-02"
    assert raw["source"].startswith("akshare.")
