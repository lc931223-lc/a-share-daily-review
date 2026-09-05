from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.inflection.pipeline import InflectionPipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the objective A-share trend inflection scanner.")
    parser.add_argument("--date", required=True)
    parser.add_argument("--limit", type=int, default=None, help="Optional deterministic stock limit for acceptance runs")
    parser.add_argument("--no-fetch", action="store_true", help="Read existing Parquet history only")
    args = parser.parse_args()
    result = InflectionPipeline().run(date.fromisoformat(args.date), scan_limit=args.limit, ensure_history=not args.no_fetch)
    packet = result["packet"]
    print(f"inflection_packet={result['paths']['full']}")
    print(f"inflection_compact={result['paths']['compact']}")
    print(f"quality_status={packet['data_quality']['status']}")
    print(f"scanned_count={packet['scan_summary']['scanned_count']}")
    print(f"candidate_count={packet['scan_summary']['candidate_count']}")
    return 0 if packet["data_quality"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
