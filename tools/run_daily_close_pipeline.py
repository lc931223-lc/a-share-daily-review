from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.daily_close.orchestrator import DailyCloseOrchestrator


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the production A-share daily close pipeline.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--date", help="Historical or explicit date in YYYY-MM-DD format")
    group.add_argument("--latest", action="store_true", help="Run the latest completed trading day")
    parser.add_argument("--backfill-missing", action="store_true", help="Run every missing trading day in order")
    parser.add_argument("--force", action="store_true", help="Regenerate valid existing artifacts")
    args = parser.parse_args(argv)
    pipeline = DailyCloseOrchestrator()
    results = (
        [pipeline.run_date(date.fromisoformat(args.date), force=args.force)]
        if args.date
        else pipeline.run_latest(backfill_missing=args.backfill_missing, force=args.force)
    )
    for result in results:
        print(json.dumps({"date": result["date"], "status": result["status"], "manifest": result["manifest_path"], "blockers": result["blockers"]}, ensure_ascii=False))
    return 0 if results and all(row["status"] in {"PASS", "PARTIAL"} for row in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
