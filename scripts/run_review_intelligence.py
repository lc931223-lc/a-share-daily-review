from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.review_intelligence.pipeline import ReviewIntelligencePipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the objective Review Intelligence Packet.")
    parser.add_argument("--date", required=True, help="Trading date in YYYY-MM-DD format")
    args = parser.parse_args()
    result = ReviewIntelligencePipeline().run(date.fromisoformat(args.date))
    print(f"review_intelligence_packet={result['paths']['full']}")
    print(f"review_intelligence_compact={result['paths']['compact']}")
    print(f"quality_status={result['packet']['data_quality']['status']}")
    print(f"theme_count={len(result['packet']['theme_features'])}")
    print(f"role_candidate_count={len(result['packet']['role_candidates'])}")
    return 0 if result["packet"]["data_quality"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
