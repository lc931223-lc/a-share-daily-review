from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.capital_preference.replay import run_replay


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay capital-preference evidence packets.")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    result = run_replay(ROOT, date.fromisoformat(args.start), date.fromisoformat(args.end))
    print(f"capital_preference_replay={result['path']}")
    print(f"trading_day_count={result['report']['trading_day_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
