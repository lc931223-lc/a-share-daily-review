from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from src.storage.database import create_db_engine, create_schema, session_factory
from src.storage.fact_store import FactStore, WrittenPartition
from src.storage.models import QualityGateCheck, QualityGateRun, SourceBatch, SourceFallback, SourceObservation


def persist_auction_run(
    *,
    trade_date: date,
    snapshots: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    source_stats: dict[str, Any],
    quality_status: str,
    quality_checks: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    failures: list[dict[str, Any]],
    fact_store: FactStore,
    database_path: Path,
    fallbacks: list[dict[str, Any]] | None = None,
) -> list[WrittenPartition]:
    canonical = json.dumps(_stable_rows(snapshots), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    batch_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    engine = create_db_engine(database_path)
    create_schema(engine)
    factory = session_factory(engine)
    pending_path = f"pending:auction_snapshot:{trade_date.isoformat()}:{batch_hash[:16]}"
    with factory.begin() as session:
        batch = session.scalar(select(SourceBatch).where(
            SourceBatch.sha256 == batch_hash,
            SourceBatch.dataset == "auction_snapshot",
            SourceBatch.trade_date == trade_date,
        ))
        if batch is None:
            batch = SourceBatch(
                source_name="eltdx", dataset="auction_snapshot", trade_date=trade_date,
                fetched_at=datetime.now(UTC), sha256=batch_hash, archive_path=pending_path,
                record_count=len(snapshots), status=quality_status,
                error_category="partial_stock_failures" if failures else None,
            )
            session.add(batch)
            session.flush()
        batch_id = batch.id
        existing_observations = {
            item.entity_key for item in session.scalars(select(SourceObservation).where(SourceObservation.batch_id == batch_id)).all()
        }
        codes = sorted({str(row.get("ts_code")) for row in snapshots if row.get("ts_code")})
        failed_codes = {str(item.get("ts_code")) for item in failures}
        for code in codes:
            entity_key = f"{trade_date.isoformat()}:{code}"
            if entity_key in existing_observations:
                continue
            session.add(SourceObservation(
                batch_id=batch_id, entity_type="stock", entity_key=entity_key,
                field_name="auction_collection_status",
                value_json=json.dumps("FAIL" if code in failed_codes else "PASS"),
                unit=None, selected=code not in failed_codes,
                selected_reason="formal opening match and process collected" if code not in failed_codes else "stock collection failed",
                conflict_status="none",
            ))

    for row in snapshots:
        row["source_batch_id"] = batch_id
    for row in summaries:
        row["source_batch_id"] = batch_id
    written = [
        item for item in (
            fact_store.write_dataset("auction_snapshot", trade_date, snapshots),
            fact_store.write_dataset("auction_daily_summary", trade_date, summaries),
        ) if item is not None
    ]
    fact_store._catalog(written, database_path)

    with factory.begin() as session:
        batch = session.get(SourceBatch, batch_id)
        snapshot_partition = next((item for item in written if item.dataset == "auction_snapshot"), None)
        if snapshot_partition is not None:
            batch.archive_path = str(snapshot_partition.path)
        run = QualityGateRun(
            trade_date=trade_date, rule_version="auction.phaseA2.1", status=quality_status,
            confidence=int(round(float(source_stats.get("stock_completion_rate") or 0) * 100)),
            summary_json=json.dumps({"source_stats": source_stats, "conflicts": conflicts, "failures": failures}, ensure_ascii=False),
        )
        session.add(run)
        session.flush()
        for check in quality_checks:
            session.add(QualityGateCheck(
                gate_run_id=run.id, check_name=str(check["name"]),
                actual_value=json.dumps(check.get("actual"), ensure_ascii=False),
                threshold_value=json.dumps(check.get("threshold"), ensure_ascii=False),
                passed=bool(check.get("passed")), reason=str(check.get("reason") or ""),
            ))
        for fallback in fallbacks or []:
            session.add(SourceFallback(
                trade_date=trade_date,
                primary_source=str(fallback.get("primary_source") or "tencent_realtime"),
                fallback_source=str(fallback.get("fallback_source") or "eastmoney_realtime"),
                dataset="auction_open_validation", reason=str(fallback.get("reason") or "primary unavailable"),
                fields_json=json.dumps(["open"], ensure_ascii=False), fetched_at=datetime.now(UTC),
                coverage=fallback.get("coverage"), cross_validation_status="pending_eod_reconciliation",
            ))
    return written


def _stable_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in row.items() if key not in {"source_batch_id", "retrieved_at"}}
        for row in rows
    ]


def persist_eod_reconciliation(
    *,
    trade_date: date,
    summaries: list[dict[str, Any]],
    validation_count: int,
    conflicts: list[dict[str, Any]],
    fact_store: FactStore,
    database_path: Path,
    packet_path: Path,
) -> WrittenPartition | None:
    canonical = json.dumps(summaries, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    batch_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    engine = create_db_engine(database_path)
    create_schema(engine)
    factory = session_factory(engine)
    status = "PASS" if validation_count == len(summaries) and not conflicts else "PARTIAL"
    with factory.begin() as session:
        batch = session.scalar(select(SourceBatch).where(
            SourceBatch.sha256 == batch_hash,
            SourceBatch.dataset == "auction_open_eod",
            SourceBatch.trade_date == trade_date,
        ))
        if batch is None:
            batch = SourceBatch(
                source_name="tushare", dataset="auction_open_eod", trade_date=trade_date,
                fetched_at=datetime.now(UTC), sha256=batch_hash, archive_path=str(packet_path),
                record_count=validation_count, status=status,
                error_category="open_price_conflict" if conflicts else None,
            )
            session.add(batch)
            session.flush()
            for item in summaries:
                if item.get("eod_open_price") is None:
                    continue
                session.add(SourceObservation(
                    batch_id=batch.id, entity_type="stock", entity_key=f"{trade_date.isoformat()}:{item.get('ts_code')}",
                    field_name="official_open_price", value_json=json.dumps(item.get("eod_open_price")),
                    unit="CNY", selected=True, selected_reason="Tushare daily EOD reconciliation",
                    conflict_status=str(item.get("eod_conflict_status") or "none"),
                ))
        run = QualityGateRun(
            trade_date=trade_date, rule_version="auction.phaseA2.eod.1", status=status,
            confidence=int(round(validation_count / len(summaries) * 100)) if summaries else 0,
            summary_json=json.dumps({"validation_count": validation_count, "conflicts": conflicts}, ensure_ascii=False),
        )
        session.add(run)
        session.flush()
        session.add(QualityGateCheck(
            gate_run_id=run.id, check_name="tushare_eod_open_reconciliation",
            actual_value=str(validation_count), threshold_value=str(len(summaries)),
            passed=status == "PASS", reason="all formal opening prices must reconcile without conflicts",
        ))
    partition = fact_store.write_dataset("auction_daily_summary", trade_date, summaries)
    if partition is not None:
        fact_store._catalog([partition], database_path)
    return partition
