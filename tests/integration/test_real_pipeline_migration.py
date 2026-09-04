from datetime import date

from sqlalchemy import func, select

from scripts.migrate_real_pipeline import migrate_database
from src.storage.database import create_db_engine, create_schema, session_factory
from src.storage.models import ReviewImport, TradingDay


def count_rows(database_path, model, *criteria):
    engine = create_db_engine(database_path)
    factory = session_factory(engine)
    with factory() as session:
        statement = select(func.count()).select_from(model)
        for criterion in criteria:
            statement = statement.where(criterion)
        return session.scalar(statement)


def build_legacy_database_with_demo_and_real(tmp_path):
    database_path = tmp_path / "legacy.db"
    engine = create_db_engine(database_path)
    create_schema(engine)
    factory = session_factory(engine)
    with factory.begin() as session:
        demo_import = ReviewImport(
            source_path="demo.json",
            sha256="d" * 64,
            archive_path="archive/demo.json",
            data_kind="demo",
            status="success",
        )
        real_import = ReviewImport(
            source_path="real.json",
            sha256="r" * 64,
            archive_path="archive/real.json",
            data_kind="real",
            status="success",
        )
        session.add_all([demo_import, real_import])
        session.flush()
        session.add_all(
            [
                TradingDay(
                    trade_date=date(2026, 9, 1),
                    data_kind="demo",
                    strict_mode=False,
                    completeness_score=100,
                    missing_items="[]",
                    market_regime="测试",
                    position_min=0,
                    position_max=2,
                    import_id=demo_import.id,
                ),
                TradingDay(
                    trade_date=date(2026, 9, 1),
                    data_kind="real",
                    strict_mode=True,
                    completeness_score=100,
                    missing_items="[]",
                    market_regime="测试",
                    position_min=0,
                    position_max=2,
                    import_id=real_import.id,
                ),
            ]
        )
    return database_path


def test_migration_removes_demo_rows_after_backup(tmp_path):
    database_path = build_legacy_database_with_demo_and_real(tmp_path)

    backup = migrate_database(database_path)

    assert backup.exists()
    assert count_rows(database_path, TradingDay, TradingDay.data_kind == "demo") == 0
    assert count_rows(database_path, TradingDay, TradingDay.data_kind == "real") == 1
    assert count_rows(database_path, ReviewImport, ReviewImport.data_kind == "demo") == 0
