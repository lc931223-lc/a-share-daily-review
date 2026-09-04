import argparse
import sys
from datetime import date

from sqlalchemy import select

from src.reports.pdf_report import FormalReportBlocked, generate_pdf
from src.storage.database import create_db_engine, create_schema, session_factory
from src.storage.models import AnalysisSnapshot


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate formal A-share daily review PDF.")
    parser.add_argument("--date", required=True, help="Target trade date, for example 2026-09-01")
    parser.add_argument("--output", required=True, help="Output PDF path")
    args = parser.parse_args(argv)

    engine = create_db_engine()
    create_schema(engine)
    target_date = date.fromisoformat(args.date)
    with session_factory(engine)() as session:
        snapshot = session.execute(
            select(AnalysisSnapshot)
            .where(AnalysisSnapshot.trade_date == target_date, AnalysisSnapshot.status == "PASSED")
            .order_by(AnalysisSnapshot.id.desc())
        ).scalar()
    if snapshot is None:
        print("未找到 PASSED 正式快照，请先运行真实数据采集")
        return 3
    try:
        output = generate_pdf(snapshot, args.output)
    except FormalReportBlocked as exc:
        print(str(exc))
        return 3
    except Exception as exc:
        print(f"ERROR: {exc}")
        return 1
    print(f"PDF written to {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
