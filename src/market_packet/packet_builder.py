from __future__ import annotations

import json
import hashlib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from sqlalchemy import delete, select

from src.market_packet.collector import MarketPacketCollector
from src.market_packet.models import MarketPacket
from src.market_packet.normalizer import normalize_packet_data
from src.market_packet.previous_review_loader import load_previous_review
from src.market_packet.quality_gate import audit_packet
from src.storage.database import create_db_engine, create_schema, session_factory
from src.storage.models import MarketDaily, MarketPacketLog, OfficialAnnouncement, OfficialPolicy


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_market_packet(trade_date: date, *, refresh: bool = False) -> dict[str, Any]:
    collector = MarketPacketCollector(refresh=refresh)
    datasets = collector.collect(trade_date)
    normalized = normalize_packet_data(trade_date, datasets)
    previous_review, tomorrow_context = load_previous_review(trade_date)
    packet = {
        "meta": {
            "schema_version": "market_packet.1",
            "trade_date": trade_date.isoformat(),
            "generated_at": datetime.now(UTC).isoformat(),
            "generated_by": "codex_market_packet_phase1",
            "codex_role": "data_engineer_data_validator_research_clerk",
            "final_judgement_owner": "chatgpt",
        },
        "data_quality": {"status": "INCOMPLETE", "score": 0, "checks": [], "sources": [], "conflicts": []},
        **normalized,
        "announcements": datasets.get("official_announcements").rows if datasets.get("official_announcements") else [],
        "policies": datasets.get("official_policies").rows if datasets.get("official_policies") else [],
        "industry_events": [],
        "previous_review": previous_review,
        "tomorrow_check_context": tomorrow_context,
        "missing_data": [],
    }
    packet = audit_packet(packet, datasets)
    return MarketPacket.model_validate(packet).model_dump(mode="json")


def compact_packet(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "meta": packet["meta"],
        "data_quality": packet["data_quality"],
        "market_overview": packet["market_overview"],
        "limit_up_down": packet["limit_up_down"],
        "liquidity": packet["liquidity"],
        "top_industries": packet["industries"][:20],
        "top_themes": packet["themes"][:20],
        "weak_themes": [item for item in packet["themes"] if item.get("limit_down_count") or item.get("failed_limit_count")][:20],
        "core_stocks": packet["stocks"][:80],
        "leader_candidates": packet["leader_candidates"][:40],
        "previous_review": packet["previous_review"],
        "tomorrow_check_context": packet["tomorrow_check_context"],
        "announcements": packet["announcements"][:50],
        "policies": packet["policies"][:30],
        "industry_events": packet["industry_events"][:50],
        "missing_data": packet["missing_data"],
    }


def quality_report(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "trade_date": packet["meta"]["trade_date"],
        "generated_at": packet["meta"]["generated_at"],
        "data_quality": packet["data_quality"],
        "missing_data": packet["missing_data"],
        "note": "PASS means usable factual source. PARTIAL/FAIL fields must remain null or be judged by ChatGPT with caveats.",
    }


def write_outputs(packet: dict[str, Any], output_root: Path | None = None) -> dict[str, Path]:
    root = output_root or PROJECT_ROOT
    trade_date = packet["meta"]["trade_date"]
    packet_dir = root / "data" / "market_packets"
    report_dir = root / "reports" / "market_packets"
    packet_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "packet": packet_dir / f"{trade_date}.json",
        "quality": packet_dir / f"{trade_date}_quality.json",
        "compact": packet_dir / f"{trade_date}_compact.json",
        "summary": report_dir / f"{trade_date}-summary.md",
    }
    paths["packet"].write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    paths["quality"].write_text(json.dumps(quality_report(packet), ensure_ascii=False, indent=2), encoding="utf-8")
    paths["compact"].write_text(json.dumps(compact_packet(packet), ensure_ascii=False, indent=2), encoding="utf-8")
    paths["summary"].write_text(markdown_summary(packet), encoding="utf-8")
    validate_with_schema(paths["packet"])
    log_packet_outputs(packet, paths)
    return paths


def log_packet_outputs(packet: dict[str, Any], paths: dict[str, Path], database_path: Path | None = None) -> None:
    packet_bytes = paths["packet"].read_bytes()
    digest = hashlib.sha256(packet_bytes).hexdigest()
    trade_date = date.fromisoformat(packet["meta"]["trade_date"])
    engine = create_db_engine(database_path)
    create_schema(engine)
    factory = session_factory(engine)
    with factory.begin() as session:
        existing_market = session.scalar(select(MarketDaily).where(MarketDaily.trade_date == trade_date))
        liquidity = packet["liquidity"]
        breadth = packet["market_breadth"]
        limit = packet["limit_up_down"]
        if existing_market is None:
            existing_market = MarketDaily(trade_date=trade_date)
            session.add(existing_market)
        existing_market.data_quality_status = packet["data_quality"]["status"]
        existing_market.data_quality_score = packet["data_quality"]["score"]
        existing_market.turnover = liquidity.get("total_market_turnover")
        existing_market.previous_turnover = liquidity.get("previous_turnover")
        existing_market.turnover_delta = liquidity.get("turnover_delta")
        existing_market.turnover_delta_pct = liquidity.get("turnover_delta_pct")
        existing_market.rise_count = breadth.get("rise_count")
        existing_market.fall_count = breadth.get("fall_count")
        existing_market.flat_count = breadth.get("flat_count")
        existing_market.limit_up_count = limit.get("limit_up_count")
        existing_market.limit_down_count = limit.get("limit_down_count")
        existing_market.failed_limit_count = limit.get("failed_limit_count")
        existing_market.highest_board = limit.get("highest_board")
        existing_market.source_json = json.dumps(packet["data_quality"]["sources"], ensure_ascii=False)
        existing_market.missing_data = json.dumps(packet["missing_data"], ensure_ascii=False)
        exists = session.scalar(
            select(MarketPacketLog.id).where(
                MarketPacketLog.trade_date == trade_date,
                MarketPacketLog.packet_sha256 == digest,
            )
        )
        if exists is None:
            session.add(
                MarketPacketLog(
                    trade_date=trade_date,
                    packet_path=str(paths["packet"]),
                    compact_path=str(paths["compact"]),
                    quality_path=str(paths["quality"]),
                    packet_sha256=digest,
                    data_quality_status=packet["data_quality"]["status"],
                    data_quality_score=packet["data_quality"]["score"],
                    missing_data=json.dumps(packet["missing_data"], ensure_ascii=False),
                    generated_at=datetime.fromisoformat(packet["meta"]["generated_at"].replace("Z", "+00:00")),
                )
            )
        session.execute(delete(OfficialAnnouncement).where(OfficialAnnouncement.trade_date == trade_date))
        for item in packet["announcements"]:
            session.add(
                OfficialAnnouncement(
                    trade_date=trade_date,
                    stock_code=str(item.get("stock_code") or ""),
                    stock_name=str(item.get("stock_name") or ""),
                    title=str(item.get("title") or ""),
                    published_at=item.get("published_at"),
                    source=str(item.get("source") or ""),
                    url=item.get("url"),
                    category=str(item.get("category") or "other"),
                    summary=str(item.get("summary") or ""),
                    confirmed_fact=str(item.get("confirmed_fact") or ""),
                    evidence_level=str(item.get("evidence_level") or ""),
                    clarification_flags=json.dumps(item.get("clarification_flags") or [], ensure_ascii=False),
                    risk_flags=json.dumps(item.get("risk_flags") or [], ensure_ascii=False),
                )
            )
        session.execute(delete(OfficialPolicy).where(OfficialPolicy.trade_date == trade_date))
        for item in packet["policies"]:
            session.add(
                OfficialPolicy(
                    trade_date=trade_date,
                    title=str(item.get("title") or ""),
                    agency=str(item.get("agency") or ""),
                    published_at=item.get("published_at"),
                    url=item.get("url"),
                    summary=str(item.get("summary") or ""),
                    policy_level=str(item.get("policy_level") or ""),
                    related_industries=json.dumps(item.get("related_industries") or [], ensure_ascii=False),
                    related_themes=json.dumps(item.get("related_themes") or [], ensure_ascii=False),
                    evidence_level=str(item.get("evidence_level") or ""),
                )
            )


def validate_with_schema(packet_path: Path) -> None:
    schema = json.loads((PROJECT_ROOT / "schemas" / "market_packet.schema.json").read_text(encoding="utf-8"))
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(packet)


def markdown_summary(packet: dict[str, Any]) -> str:
    overview = packet["market_overview"]
    limit = packet["limit_up_down"]
    lines = [
        f"# Market Packet Summary {packet['meta']['trade_date']}",
        "",
        "Codex role: data engineer / validator / research clerk. No final market conclusion is made here.",
        "",
        "## Data Quality",
        "",
        f"- Status: {packet['data_quality']['status']}",
        f"- Score: {packet['data_quality']['score']}",
        f"- Missing: {', '.join(packet['missing_data']) if packet['missing_data'] else 'none'}",
        "",
        "## Market Facts",
        "",
        f"- Trading day: {overview['is_trading_day']}",
        f"- Limit up / failed / limit down: {limit['limit_up_count']} / {limit['failed_limit_count']} / {limit['limit_down_count']}",
        f"- Failed limit rate: {limit['failed_limit_rate']}%",
        f"- Highest board: {limit['highest_board']}",
        "",
        "## Top Objective Themes",
        "",
        "| Theme | Limit Up | Failed | Limit Down | Amount |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for item in packet["themes"][:20]:
        lines.append(f"| {item['theme_name']} | {item['limit_up_count']} | {item['failed_limit_count']} | {item['limit_down_count']} | {item['amount']} |")
    lines.extend(["", "## Candidate Stocks", "", "| Code | Name | Industry | Leader | Capacity | Catch-up |", "| --- | --- | --- | ---: | ---: | ---: |"])
    for item in packet["leader_board"][:40]:
        lines.append(f"| {item['stock_code']} | {item['stock_name']} | {item['industry']} | {item['leader_candidate_score']} | {item['capacity_candidate_score']} | {item['catch_up_candidate_score']} |")
    return "\n".join(lines) + "\n"
