from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.feedback.pipeline import FeedbackPipeline


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run strict as-of A-share research feedback tracking."
    )
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2026-09-04")
    parser.add_argument(
        "--skip-fetch", action="store_true", help="Use only locally cached daily history."
    )
    args = parser.parse_args()
    result = FeedbackPipeline().run(
        date.fromisoformat(args.start),
        date.fromisoformat(args.end),
        ensure_history=not args.skip_fetch,
    )
    print(f"as_of_backtest={result['paths']['backtest']}")
    print(f"research_feedback={result['paths']['feedback']}")
    print(f"prediction_count={result['backtest']['meta']['prediction_count']}")
    print(f"validation_count={result['backtest']['meta']['validation_count']}")
    print(f"quality_status={result['report']['data_quality']['status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
