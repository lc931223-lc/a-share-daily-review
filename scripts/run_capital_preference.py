from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.capital_preference.pipeline import CapitalPreferencePipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Build objective capital-preference evidence.")
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    result = CapitalPreferencePipeline().run(date.fromisoformat(args.date))
    print(f"capital_preference={result['paths']['full']}")
    print(f"capital_preference_compact={result['paths']['compact']}")
    print(f"quality_status={result['packet']['data_quality']['status']}")
    print(f"theme_count={len(result['packet']['theme_capital_preference'])}")
    print(f"stock_count={len(result['packet']['stock_capital_preference'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
