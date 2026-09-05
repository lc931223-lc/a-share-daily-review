from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pytest
from sqlalchemy import func, select

from src.storage.database import create_db_engine, session_factory
from src.storage.fact_store import FactStore
from src.storage.models import FactPartition


ROOT = Path(__file__).resolve().parents[2]


def test_fact_store_writes_idempotent_partition_and_catalog(tmp_path):
    store = FactStore(tmp_path / "facts")
    rows = [{"stock_code": "000001", "close": 12.3}, {"stock_code": "000002", "close": None}]
    first = store.write_dataset("daily", date(2026, 9, 2), rows)
    second = store.write_dataset("daily", date(2026, 9, 2), rows)
    assert first is not None and second is not None
    assert first.path == second.path
    assert first.path.exists()
    assert len(list(first.path.parent.glob("*.parquet"))) == 1


def test_fact_store_duckdb_date_query(tmp_path):
    pytest.importorskip("duckdb")
    store = FactStore(tmp_path / "facts")
    store.write_dataset("daily", date(2026, 9, 1), [{"stock_code": "000001", "close": 10.0}])
    store.write_dataset("daily", date(2026, 9, 2), [{"stock_code": "000001", "close": 11.0}])
    result = store.query_dataset("daily", start=date(2026, 9, 2), end=date(2026, 9, 2))
    assert result["close"].tolist() == [11.0]
    assert str(result.iloc[0]["trade_date"])[:10] == "2026-09-02"


def test_fact_store_does_not_leave_partial_parquet_when_write_fails(tmp_path, monkeypatch):
    store = FactStore(tmp_path / "facts")

    def fail_after_partial_write(self, path, **kwargs):
        Path(path).write_bytes(b"partial")
        raise RuntimeError("simulated writer failure")

    monkeypatch.setattr("pandas.DataFrame.to_parquet", fail_after_partial_write)
    with pytest.raises(RuntimeError, match="simulated writer failure"):
        store.write_dataset("daily", date(2026, 9, 2), [{"stock_code": "000001", "close": 12.3}])

    assert list((tmp_path / "facts").rglob("*.parquet")) == []
    assert list((tmp_path / "facts").rglob("*.tmp")) == []


def test_packet_fact_partitions_match_sqlite_catalog(tmp_path):
    packet = json.loads((ROOT / "data" / "market_packets" / "2026-09-02.json").read_text(encoding="utf-8"))
    database = tmp_path / "catalog.db"
    store = FactStore(tmp_path / "facts")
    written = store.persist_packet(packet, database)
    factory = session_factory(create_db_engine(database))
    with factory() as session:
        catalog_count = session.scalar(select(func.count()).select_from(FactPartition))
    assert catalog_count == len(written)
    assert all(item.path.exists() and item.record_count > 0 for item in written)
