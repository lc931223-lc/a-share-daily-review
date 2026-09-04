from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.market_packet.packet_builder import build_market_packet, write_outputs
from src.market_packet.trading_calendar import resolve_auto_trade_date


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build A-share Market Research Packet.")
    parser.add_argument("--date", required=True, help="YYYY-MM-DD or auto")
    parser.add_argument("--refresh", action="store_true", help="Ignore packet raw cache and refetch")
    return parser.parse_args()


def resolve_date(value: str) -> date:
    return resolve_auto_trade_date(value)


def main() -> int:
    args = parse_args()
    trade_date = resolve_date(args.date)
    packet = build_market_packet(trade_date, refresh=args.refresh)
    paths = write_outputs(packet)
    print(f"market_packet={paths['packet']}")
    print(f"quality={paths['quality']}")
    print(f"compact={paths['compact']}")
    print(f"summary={paths['summary']}")
    print(f"quality_score={packet['data_quality']['score']} status={packet['data_quality']['status']}")
    if packet["missing_data"]:
        print("missing_data=" + ",".join(packet["missing_data"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
