from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.market_packet.packet_builder import build_market_packet, write_outputs
from tools.import_official_review import main as import_official_review_main
from tools.update_validation_results import main as update_validation_results_main


def _resolve_date(value: str) -> date:
    if value != "auto":
        return date.fromisoformat(value)
    packet_dir = PROJECT_ROOT / "data" / "market_packets"
    candidates = sorted(packet_dir.glob("????-??-??.json"))
    if candidates:
        return date.fromisoformat(candidates[-1].stem)
    return date.today()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build packet, import official review if present, and update validation snapshots.")
    parser.add_argument("--date", required=True, help="auto or YYYY-MM-DD")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--database", default=None)
    args = parser.parse_args(argv)
    trade_date = _resolve_date(args.date)

    packet = build_market_packet(trade_date, refresh=args.refresh)
    paths = write_outputs(packet)
    print(f"packet_status={packet['data_quality']['status']}")
    print(f"packet_score={packet['data_quality']['score']}")
    print(f"packet={paths['packet']}")

    review_path = PROJECT_ROOT / "data" / "official_reviews" / f"{trade_date.isoformat()}.json"
    if review_path.exists():
        code = import_official_review_main([str(review_path), *(["--database", args.database] if args.database else [])])
        if code != 0:
            return code
        return update_validation_results_main(["--date", trade_date.isoformat(), *(["--database", args.database] if args.database else [])])

    print("official_review_status=MISSING")
    print(f"expected_official_review={review_path}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
