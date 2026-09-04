from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.storage.database import create_db_engine, create_schema, session_factory
from src.storage.models import TomorrowCheck, TradingDay, ValidationResult
from src.market_packet.trading_calendar import resolve_auto_trade_date


def _resolve_date(value: str) -> date:
    return resolve_auto_trade_date(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Persist current tomorrow_check validation status snapshots.")
    parser.add_argument("--date", required=True, help="auto or YYYY-MM-DD")
    parser.add_argument("--database", default=None, help="Optional SQLite database path")
    args = parser.parse_args(argv)
    trade_date = _resolve_date(args.date)

    engine = create_db_engine(args.database)
    create_schema(engine)
    count = 0
    with session_factory(engine).begin() as session:
        day = session.scalar(select(TradingDay).where(TradingDay.trade_date == trade_date, TradingDay.data_kind == "real"))
        if day is None:
            print(f"validation_status=NO_OFFICIAL_REVIEW")
            print(f"date={trade_date.isoformat()}")
            return 2
        checks = session.scalars(select(TomorrowCheck).where(TomorrowCheck.proposed_day_id == day.id)).all()
        for check in checks:
            exists = session.scalar(
                select(ValidationResult.id).where(
                    ValidationResult.trade_date == trade_date,
                    ValidationResult.source_check_id == check.id,
                    ValidationResult.status == check.status,
                )
            )
            if exists is None:
                session.add(
                    ValidationResult(
                        trade_date=trade_date,
                        entity_type=check.entity_type,
                        entity_key=check.entity_key,
                        validation_type=check.check_type,
                        status=check.status,
                        result=check.result,
                        source_check_id=check.id,
                    )
                )
                count += 1
    print("validation_status=UPDATED")
    print(f"date={trade_date.isoformat()}")
    print(f"rows_added={count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
