from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from src.storage.database import create_db_engine, create_schema, session_factory
from src.storage.fact_store import FactStore
from src.storage.models import QualityGateCheck, QualityGateRun, SourceBatch, SourceObservation


def persist_review_intelligence(
    target: date,
    packet: dict[str, Any],
    *,
    fact_store: FactStore,
    database_path: Path,
) -> None:
    summary = packet["market_operability"] | {
        "trade_date": target.isoformat(),
        "cycle_candidates_json": json.dumps(packet["cycle_candidates"], ensure_ascii=False),
        "quality_status": packet["data_quality"]["status"],
        "schema_version": "review_intelligence_daily.1",
    }
    theme_rows = [_storage_row(row, ("score_components", "top_gainers", "top_losers", "leader_candidates", "capacity_candidates", "catch_up_candidates", "trend_candidates")) for row in packet["theme_features"]]
    role_rows = [_storage_row(row, ("role_scores", "all_role_candidates")) for row in packet["role_candidates"]]
    written = []
    for dataset, rows in (
        ("review_intelligence_daily", [summary]),
        ("review_theme_features", theme_rows),
        ("review_role_candidates", role_rows),
    ):
        partition = fact_store.write_dataset(dataset, target, rows)
        if partition:
            written.append(partition)
    fact_store._catalog(written, database_path)
    _audit(target, packet, written, database_path)


def _storage_row(row: dict[str, Any], json_fields: tuple[str, ...]) -> dict[str, Any]:
    output = dict(row)
    for field in json_fields:
        if field in output:
            output[f"{field}_json"] = json.dumps(output.pop(field), ensure_ascii=False, sort_keys=True)
    return output


def _audit(target, packet, written, database_path):
    digest = hashlib.sha256(json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    engine = create_db_engine(database_path)
    create_schema(engine)
    factory = session_factory(engine)
    checks = packet["data_quality"]["checks"]
    status = packet["data_quality"]["status"]
    with factory.begin() as session:
        batch = session.scalar(select(SourceBatch).where(
            SourceBatch.sha256 == digest,
            SourceBatch.dataset == "review_intelligence_daily",
            SourceBatch.trade_date == target,
        ))
        if batch is None:
            batch = SourceBatch(
                source_name="review_intelligence", dataset="review_intelligence_daily", trade_date=target,
                fetched_at=datetime.now(UTC), sha256=digest,
                archive_path=";".join(str(item.path) for item in written),
                record_count=1 + len(packet["theme_features"]) + len(packet["role_candidates"]),
                status=status, error_category=None if status == "PASS" else "partial_inputs",
            )
            session.add(batch)
            session.flush()
            session.add(SourceObservation(
                batch_id=batch.id, entity_type="market", entity_key=target.isoformat(),
                field_name="market_operability_score",
                value_json=json.dumps(packet["market_operability"].get("market_operability_score")),
                unit="point", selected=True, selected_reason="objective review intelligence feature",
                conflict_status="none",
            ))
        run = QualityGateRun(
            trade_date=target, rule_version="review_intelligence.phase1.1", status=status,
            confidence=round(sum(bool(row["passed"]) for row in checks) / len(checks) * 100) if checks else 0,
            summary_json=json.dumps({"checks": checks}, ensure_ascii=False),
        )
        session.add(run)
        session.flush()
        for check in checks:
            session.add(QualityGateCheck(
                gate_run_id=run.id, check_name=check["name"], actual_value=json.dumps(check.get("actual")),
                threshold_value=json.dumps(check.get("threshold")), passed=bool(check["passed"]),
                reason=str(check.get("reason") or ""),
            ))
