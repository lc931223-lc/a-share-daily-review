from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.inflection.history import DailyHistoryRepository
from src.review_intelligence.pipeline import ReviewIntelligencePipeline
from src.review_intelligence.replay import summarize_replay


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay objective review-intelligence features over trading days.")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    history = DailyHistoryRepository(ROOT)
    days = [day for day in history.trading_days(end, 280) if start <= day <= end]
    pipeline = ReviewIntelligencePipeline(ROOT, history_repository=history)
    for day in days:
        pipeline.run(day)
        print(f"replayed={day.isoformat()}")
    report = summarize_replay(ROOT, start, end)
    output = ROOT / "data" / "review_intelligence" / "backtests" / f"{start.isoformat()}_to_{end.isoformat()}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"replay_report={output}")
    print(f"trading_day_count={report['trading_day_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
