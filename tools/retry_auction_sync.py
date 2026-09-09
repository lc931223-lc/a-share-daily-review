"""Retry distribution of SHA-verified local facts; never import a collector."""

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.auction.git_sync import persist
from src.auction.host_lock import auction_lock


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, required=True)
    args = parser.parse_args(argv)
    with auction_lock(ROOT, args.date):
        print(persist(ROOT, args.date, require_frozen=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
