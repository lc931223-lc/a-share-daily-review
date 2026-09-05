from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.review_context.builder import ReviewContextBuilder


def main() -> int:
    parser = argparse.ArgumentParser(description="Assemble objective inputs for ChatGPT's official A-share review.")
    parser.add_argument("--date", required=True, help="Trading date in YYYY-MM-DD format")
    args = parser.parse_args()
    result = ReviewContextBuilder().build(date.fromisoformat(args.date))
    print(f"review_context={result['paths']['full']}")
    print(f"review_context_compact={result['paths']['compact']}")
    print(f"quality_status={result['packet']['data_quality']['status']}")
    print(f"theme_candidate_count={len(result['packet']['next_day_theme_candidates'])}")
    print(f"next_day_plan_count={len(result['packet']['next_day_plan'])}")
    return 0 if result["packet"]["data_quality"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
