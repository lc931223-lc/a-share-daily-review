from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.inflection.backtest import evaluate_forward_returns
from src.inflection.history import DailyHistoryRepository


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate stored inflection signals with later daily bars.")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    signals = []
    for path in sorted((ROOT / "data" / "inflection").glob("????-??-??.json")):
        target = date.fromisoformat(path.stem)
        if start <= target <= end:
            signals.extend(json.loads(path.read_text(encoding="utf-8")).get("candidates") or [])
    codes = sorted({str(item["ts_code"]) for item in signals})
    daily = DailyHistoryRepository(ROOT).query(start, end, codes=codes)
    rows = evaluate_forward_returns(signals, daily)
    output_dir = ROOT / "data" / "inflection" / "backtests"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"{start.isoformat()}_to_{end.isoformat()}.json"
    output.write_text(json.dumps({
        "schema_version": "inflection_backtest.1", "start_date": start.isoformat(),
        "end_date": end.isoformat(), "signal_count": len(signals), "evaluated_count": len(rows),
        "records": rows,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"backtest={output}")
    print(f"signal_count={len(signals)}")
    print(f"evaluated_count={len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
