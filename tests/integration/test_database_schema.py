import sqlite3
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from src.storage.database import create_db_engine, create_schema, session_factory
from src.storage.models import ReviewImport, TradingDay


ROOT = Path(__file__).resolve().parents[2]
REQUIRED_PIPELINE_TABLES = {
    "source_batch",
    "source_observation",
    "quality_gate_run",
    "quality_gate_check",
    "source_fallback",
    "analysis_snapshot",
    "fact_version",
    "fact_partition",
}
REQUIRED_TABLES = {
    "review_import", "trading_day", "theme", "theme_alias", "theme_daily_score",
    "theme_driver", "stock", "stock_daily_score", "stock_driver", "evidence",
    "risk_event", "tomorrow_check", "theme_relationship", *REQUIRED_PIPELINE_TABLES,
}


def test_sqlalchemy_and_sql_script_create_required_tables(tmp_path):
    orm_engine = create_db_engine(tmp_path / "orm.db")
    create_schema(orm_engine)
    assert REQUIRED_TABLES <= set(inspect(orm_engine).get_table_names())
    connection = sqlite3.connect(tmp_path / "script.db")
    connection.executescript((ROOT / "sql" / "schema.sql").read_text("utf-8"))
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    connection.close()
    assert REQUIRED_TABLES <= tables


def test_pipeline_tables_exist(tmp_path):
    engine = create_db_engine(tmp_path / "pipeline.db")
    create_schema(engine)
    assert REQUIRED_PIPELINE_TABLES <= set(inspect(engine).get_table_names())


def test_date_and_kind_are_jointly_unique(tmp_path):
    engine = create_db_engine(tmp_path / "unique.db")
    create_schema(engine)
    factory = session_factory(engine)
    with factory() as session:
        imports = [ReviewImport(source_path=f"{i}.json", sha256=str(i) * 64, archive_path="x", status="ok") for i in range(3)]
        session.add_all(imports)
        session.flush()
        session.add_all([TradingDay(trade_date=date(2026, 9, 1), data_kind=kind, strict_mode=kind == "real", completeness_score=100, missing_items="[]", market_regime="测试", position_min=0, position_max=2, import_id=record.id) for kind, record in zip(("demo", "real"), imports[:2])])
        session.commit()
        session.add(TradingDay(trade_date=date(2026, 9, 1), data_kind="real", strict_mode=True, completeness_score=100, missing_items="[]", market_regime="重复", position_min=0, position_max=2, import_id=imports[2].id))
        with pytest.raises(IntegrityError):
            session.commit()


def test_foreign_keys_are_enabled(tmp_path):
    engine = create_db_engine(tmp_path / "fk.db")
    create_schema(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
    foreign_keys = inspect(engine).get_foreign_keys("theme_daily_score")
    assert any(item["referred_table"] == "trading_day" for item in foreign_keys)
