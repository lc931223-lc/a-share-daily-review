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


def persist_inflection_run(
    target: date,
    rows: list[dict[str, Any]],
    checks: list[dict[str, Any]],
    status: str,
    *,
    fact_store: FactStore,
    database_path: Path,
) -> None:
    partition = fact_store.write_dataset("inflection_daily", target, rows)
    if partition is None:
        return
    fact_store._catalog([partition], database_path)
    engine = create_db_engine(database_path)
    create_schema(engine)
    factory = session_factory(engine)
    digest = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with factory.begin() as session:
        batch = session.scalar(select(SourceBatch).where(
            SourceBatch.sha256 == digest, SourceBatch.dataset == "inflection_daily", SourceBatch.trade_date == target,
        ))
        if batch is None:
            batch = SourceBatch(
                source_name="inflection_scanner", dataset="inflection_daily", trade_date=target,
                fetched_at=datetime.now(UTC), sha256=digest, archive_path=str(partition.path),
                record_count=len(rows), status=status, error_category=None if status == "PASS" else "partial_features",
            )
            session.add(batch)
            session.flush()
            for row in rows:
                session.add(SourceObservation(
                    batch_id=batch.id, entity_type="stock", entity_key=f"{target.isoformat()}:{row['ts_code']}",
                    field_name="trend_inflection_score", value_json=json.dumps(row.get("trend_inflection_score")),
                    unit="point", selected=row.get("status") != "NO_SIGNAL",
                    selected_reason="objective inflection feature threshold", conflict_status="none",
                ))
        run = QualityGateRun(
            trade_date=target, rule_version="inflection.phase1.1", status=status,
            confidence=int(round(sum(bool(item["passed"]) for item in checks) / len(checks) * 100)) if checks else 0,
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
