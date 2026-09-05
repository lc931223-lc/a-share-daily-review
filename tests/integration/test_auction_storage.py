from datetime import date

from sqlalchemy import func, select

from src.auction.storage import persist_auction_run
from src.storage.database import create_db_engine, session_factory
from src.storage.fact_store import FactStore
from src.storage.models import FactPartition, QualityGateCheck, QualityGateRun, SourceBatch, SourceObservation


def test_auction_run_uses_fact_store_and_existing_audit_tables(tmp_path):
    snapshot = {
        "trade_date": "2026-09-04", "ts_code": "000001.SZ", "stock_name": "平安银行",
        "snapshot_time": "2026-09-04T09:25:00+08:00", "checkpoint_time": "09:25:00",
        "match_price": 10.0, "matched_volume": 1000, "matched_amount": 10_000,
        "unmatched_signed_volume": None, "unmatched_direction_raw": None,
        "unmatched_buy": None, "unmatched_sell": None, "raw_matched_volume": 10,
        "raw_volume_unit": "lot", "matched_amount_value_kind": "DERIVED", "source": "eltdx",
        "source_batch_id": None, "retrieved_at": "2026-09-05T01:00:00+00:00",
        "source_data_time": "2026-09-04T09:25:00+08:00", "checkpoint_lag_ms": 0,
        "is_formal_opening_match": True, "quality_status": "PASS", "content_hash": "abc",
        "schema_version": "auction_snapshot.1", "observation_kind": "checkpoint",
    }
    summary = {
        "trade_date": "2026-09-04", "ts_code": "000001.SZ", "auction_price": 10.0,
        "auction_amount": 10_000, "quality_status": "PARTIAL", "schema_version": "auction_daily_summary.1",
    }
    database = tmp_path / "auction.db"
    store = FactStore(tmp_path / "facts")

    written = persist_auction_run(
        trade_date=date(2026, 9, 4), snapshots=[snapshot], summaries=[summary],
        source_stats={"success_count": 1, "failure_count": 0, "stock_completion_rate": 1.0},
        quality_status="PARTIAL", quality_checks=[{"name": "stock_completion_rate", "actual": 1.0, "threshold": 0.95, "passed": True}],
        conflicts=[], failures=[], fact_store=store, database_path=database,
    )

    assert {item.dataset for item in written} == {"auction_snapshot", "auction_daily_summary"}
    assert len(store.read_dataset("auction_snapshot", date(2026, 9, 4))) == 1
    factory = session_factory(create_db_engine(database))
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(SourceBatch)) == 1
        assert session.scalar(select(func.count()).select_from(SourceObservation)) == 1
        assert session.scalar(select(func.count()).select_from(QualityGateRun)) == 1
        assert session.scalar(select(func.count()).select_from(QualityGateCheck)) == 1
        assert session.scalar(select(func.count()).select_from(FactPartition)) == 2
