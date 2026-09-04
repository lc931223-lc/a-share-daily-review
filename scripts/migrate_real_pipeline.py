import shutil
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, text

from src.storage.database import create_schema, database_url


def migrate_database(path: str | Path) -> Path:
    db_path = Path(path).resolve()
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = db_path.with_name(f"{db_path.stem}.pre-real-pipeline-{timestamp}.bak")
    shutil.copy2(db_path, backup_path)

    engine = create_engine(database_url(db_path), future=True)
    create_schema(engine)
    with engine.begin() as connection:
        demo_ids = [
            row[0]
            for row in connection.execute(
                text("SELECT id FROM trading_day WHERE data_kind = 'demo'")
            )
        ]
        if not demo_ids:
            return backup_path

        id_params = {f"id_{index}": value for index, value in enumerate(demo_ids)}
        placeholders = ", ".join(f":id_{index}" for index in range(len(demo_ids)))
        for table, column in (
            ("theme_relationship", "trading_day_id"),
            ("tomorrow_check", "resolved_day_id"),
            ("tomorrow_check", "proposed_day_id"),
            ("risk_event", "trading_day_id"),
            ("evidence", "trading_day_id"),
            ("stock_driver", "trading_day_id"),
            ("stock_daily_score", "trading_day_id"),
            ("theme_driver", "trading_day_id"),
            ("theme_daily_score", "trading_day_id"),
        ):
            connection.execute(
                text(f"DELETE FROM {table} WHERE {column} IN ({placeholders})"),
                id_params,
            )
        connection.execute(
            text(f"DELETE FROM trading_day WHERE id IN ({placeholders})"),
            id_params,
        )
        connection.execute(text("DELETE FROM review_import WHERE data_kind = 'demo'"))
    return backup_path


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Migrate an existing database to real pipeline schema.")
    parser.add_argument("database", help="SQLite database path")
    args = parser.parse_args()
    backup = migrate_database(args.database)
    print(f"Backup written to {backup}")
