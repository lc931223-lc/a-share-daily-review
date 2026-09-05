from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import select

from src.storage.database import create_db_engine, create_schema, session_factory
from src.storage.models import FactPartition


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class WrittenPartition:
    dataset: str
    trade_date: date
    path: Path
    content_hash: str
    record_count: int
    schema_json: str


class FactStore:
    def __init__(self, root: Path | None = None):
        self.root = root or PROJECT_ROOT / "data" / "facts"

    def write_dataset(self, dataset: str, trade_date: date, rows: list[dict[str, Any]]) -> WrittenPartition | None:
        if not rows:
            return None
        normalized = [_json_safe(row) for row in rows]
        canonical = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        partition_dir = self.root / f"dataset={dataset}" / f"trade_date={trade_date.isoformat()}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        path = partition_dir / f"part-{content_hash[:16]}.parquet"
        frame = pd.DataFrame(normalized)
        if not path.exists():
            temporary = path.with_suffix(path.suffix + ".tmp")
            try:
                frame.to_parquet(temporary, engine="pyarrow", index=False, compression="zstd")
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        schema_json = json.dumps({str(name): str(dtype) for name, dtype in frame.dtypes.items()}, ensure_ascii=False, sort_keys=True)
        return WrittenPartition(dataset, trade_date, path, content_hash, len(frame), schema_json)

    def read_dataset(self, dataset: str, trade_date: date) -> list[dict[str, Any]]:
        partition_dir = self.root / f"dataset={dataset}" / f"trade_date={trade_date.isoformat()}"
        parts = sorted(partition_dir.glob("*.parquet"), key=lambda path: path.stat().st_mtime, reverse=True)
        if not parts:
            return []
        frame = pd.read_parquet(parts[0], engine="pyarrow")
        return [_json_safe(row) for row in frame.to_dict("records")]

    def persist_packet(self, packet: dict[str, Any], database_path: Path | None = None) -> list[WrittenPartition]:
        trade_date = date.fromisoformat(packet["meta"]["trade_date"])
        sections: dict[str, list[dict[str, Any]]] = {
            "market_overview": [packet.get("market_overview", {})],
            "indices": packet.get("indices", []),
            "industries": packet.get("industries", []),
            "themes": packet.get("themes", []),
            "stocks": packet.get("stocks", []),
            "announcements": packet.get("announcements", {}).get("records", []),
            "policies": packet.get("policies", {}).get("records", []),
            "quality_checks": packet.get("data_quality", {}).get("checks", []),
        }
        written = [partition for name, rows in sections.items() if (partition := self.write_dataset(name, trade_date, rows))]
        self._catalog(written, database_path)
        return written

    def query_dataset(self, dataset: str, *, start: date | None = None, end: date | None = None) -> pd.DataFrame:
        try:
            import duckdb
        except ImportError as exc:  # pragma: no cover - dependency contract
            raise RuntimeError("duckdb is required for fact-store queries") from exc
        pattern = (self.root / f"dataset={dataset}" / "trade_date=*" / "*.parquet").as_posix()
        if not list((self.root / f"dataset={dataset}").glob("trade_date=*/*.parquet")):
            return pd.DataFrame()
        clauses = []
        parameters: list[Any] = [pattern]
        if start:
            clauses.append("trade_date >= ?")
            parameters.append(start.isoformat())
        if end:
            clauses.append("trade_date <= ?")
            parameters.append(end.isoformat())
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        return duckdb.execute(
            f"SELECT * FROM read_parquet(?, hive_partitioning=true, union_by_name=true){where} ORDER BY trade_date",
            parameters,
        ).fetch_df()

    def _catalog(self, partitions: list[WrittenPartition], database_path: Path | None) -> None:
        engine = create_db_engine(database_path)
        create_schema(engine)
        factory = session_factory(engine)
        with factory.begin() as session:
            for item in partitions:
                exists = session.scalar(select(FactPartition.id).where(
                    FactPartition.dataset == item.dataset,
                    FactPartition.trade_date == item.trade_date,
                    FactPartition.content_hash == item.content_hash,
                ))
                if exists is None:
                    session.add(FactPartition(
                        dataset=item.dataset, trade_date=item.trade_date, content_hash=item.content_hash,
                        path=str(item.path), record_count=item.record_count, schema_json=item.schema_json,
                    ))


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, (date, pd.Timestamp)):
        return value.isoformat()
    if pd.isna(value):
        return None
    return value
