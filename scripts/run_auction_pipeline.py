from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.auction.pipeline import AuctionPipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the A-share call-auction Phase A2 pipeline.")
    parser.add_argument("--date", required=True, help="Trading date in YYYY-MM-DD format")
    parser.add_argument("--mode", choices=("historical", "live", "eod"), default="historical")
    parser.add_argument("--baseline-days", type=int, choices=range(0, 121), default=60)
    parser.add_argument("--min-watchlist", type=int, default=100)
    parser.add_argument("--max-watchlist", type=int, default=200)
    parser.add_argument("--max-checkpoint-lag", type=int, default=65)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    trade_date = date.fromisoformat(args.date)
    pipeline = AuctionPipeline()
    if args.mode == "eod":
        result = pipeline.reconcile_eod(trade_date)
        print(f"auction_packet={result['path']}")
        print(f"auction_packet_compact={result['compact_path']}")
        print(f"eod_reconciliation_status={result['status']}")
        return 0 if result["status"] == "PASS" else 2
    runner = pipeline.run_live if args.mode == "live" else pipeline.run_historical
    result = runner(
        trade_date,
        min_watchlist_size=args.min_watchlist,
        max_watchlist_size=args.max_watchlist,
        baseline_days=args.baseline_days,
        max_checkpoint_lag_seconds=args.max_checkpoint_lag,
    )
    packet = result["packet"]
    summary = packet["market_auction_summary"]
    print(f"watchlist={result['paths']['watchlist']}")
    print(f"auction_packet={result['paths']['packet']}")
    print(f"auction_packet_compact={result['paths']['compact_packet']}")
    print(f"quality_status={packet['data_quality']['status']}")
    for key in ("stock_completion_rate", "checkpoint_coverage", "post_0920_checkpoint_coverage", "formal_opening_match_success_rate"):
        print(f"{key}={summary.get(key)}")
    return 0 if packet["data_quality"]["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
